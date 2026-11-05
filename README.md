<div align="center">

# Internal Knowledge Assistant

**Permission-aware RAG, a human-in-the-loop AI agent, and an MCP server over your company's internal documents.**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-agent-1C3C3C)
![MCP](https://img.shields.io/badge/MCP-server-6E56CF)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/tests-43%20passing-2EA44F)

[Architecture](docs/architecture.md) ·
[MCP setup](docs/mcp-setup.md) ·
[Evaluation](eval/REPORT.md) ·
[Interview Q&A](docs/INTERVIEW.md)

</div>

---

## Overview

Employees upload documents scoped to a department (or the whole company) and ask questions in natural language.
Answers are grounded in retrieved passages with `[n]` citations, and the system refuses to answer when no
authorized source supports one. An agent can search, read, summarize and take actions (e.g. open a ticket) —
side-effecting actions pause the graph until the user approves. The same document store is exposed over
[MCP](https://modelcontextprotocol.io) so tools such as Claude Code can query it under the caller's own permissions.

### Design goals

| Goal | How it is met |
|---|---|
| **No cross-department leakage** | Authorization is applied *inside the SQL query* of the single retrieval entry point, before any ranking. UI, agent and MCP all go through it. |
| **Grounded answers** | Context-only prompt, numbered citations, refusal without sources, and an agent-level guard that rejects answers lacking tool evidence. |
| **Safe agency** | Side-effecting tools run only after an explicit approval (`interrupt()` + `PendingAction`); bounded step budget; user identity is never a tool argument. |
| **Testable offline** | LLM, embeddings and reranker sit behind thin interfaces in `services/`; tests use deterministic fakes and never touch the network. |
| **Observable** | Every request carries a `trace_id`, emits a structured JSON log line (latency per step, tokens, estimated cost) and is exported to Langfuse. |

## Architecture

```mermaid
flowchart LR
  subgraph Clients
    UI["Browser UI<br/>chat · documents"]
    API["REST clients"]
    CC["Claude Code<br/>(MCP client)"]
  end

  subgraph Django["Django + DRF"]
    V["thin views"]
    RAG["chat.services.rag"]
    AG["agent.services<br/>LangGraph"]
    ING["documents API"]
  end

  MCP["mcp_server<br/>stdio · streamable-HTTP"]
  SEARCH["<b>retrieval.services.search(user, q, k)</b><br/>authorization in SQL"]
  W["Celery worker<br/>parse → chunk → embed"]
  PG[("PostgreSQL<br/>pgvector · FTS · checkpoints")]
  PROV["services/<br/>llm · embeddings · rerank"]
  LF["Langfuse"]

  UI --> V
  API --> V
  CC --> MCP
  V --> RAG & AG & ING
  RAG --> SEARCH
  AG --> SEARCH
  MCP --> SEARCH
  ING -- enqueue --> W
  W --> PG
  SEARCH --> PG
  SEARCH --> PROV
  RAG --> PROV
  AG --> PROV
  W --> PROV
  RAG -.trace.-> LF
  AG -.trace.-> LF
```

Layering is strict: **views → services → models**. Nothing outside `retrieval.services.search` queries chunks
for retrieval purposes.

### Retrieval pipeline

`search(user, query, k, *, use_vector, use_keyword, use_rerank)`

```mermaid
flowchart LR
  Q[query] --> ACL["1 · ACL filter<br/>visible_documents(user)<br/>status = ready"]
  ACL --> VEC["2a · vector<br/>cosine, HNSW<br/>top 30"]
  ACL --> KW["2b · keyword<br/>FTS OR-query<br/>ts_rank_cd, top 30"]
  VEC --> RRF["3 · RRF<br/>Σ 1/(60+rank)"]
  KW --> RRF
  RRF --> RR["4 · rerank<br/>top 30 → top k"]
  RR --> OUT["ScoredChunk[]<br/>chunk · score · source_ref"]
```

- **Authorization first.** The allowed-chunk set is a subquery over `visible_documents(user)`; both retrieval
  branches run against it. Filtering after top-k would let forbidden chunks displace permitted ones and make a
  forgotten filter a data leak.
- **Keyword branch** uses Postgres full-text search with the `simple` configuration (no language stemming, suited
  to Vietnamese) and an OR-joined tsquery so long natural-language questions still match, ranked by `ts_rank_cd`.
- **RRF** fuses by rank rather than score because cosine similarity and `ts_rank` are not on comparable scales.
- **Rerank** is behind an interface: a cross-encoder when `RERANK_MODEL` is set, otherwise a lexical placeholder.
- Each stage is a flag, which is what lets `eval/` compare *vector* vs *hybrid* vs *hybrid + rerank*.

### Ingestion

`POST /api/documents/` → `Document(status=pending)` → Celery task:

1. SHA-256 of the file; reject if another `ready` document has the same hash.
2. Parse PDF (per-page metadata) / Markdown / text.
3. **Structure-aware chunking** — split Markdown by heading (keeping an `A > B` breadcrumb), then by size with
   `RecursiveCharacterTextSplitter` (~600 tokens, ~12% overlap; tokens estimated at 4 chars).
4. Embed in batches of 64 (heading prepended to the embedded text).
5. In **one transaction**: delete the document's old chunks, bulk-insert new ones, populate `search_vector`, set
   `status=ready`. Re-running the task is idempotent. Errors set `status=failed` with a reason.

Indexes: **HNSW** (`vector_cosine_ops`, `m=16`, `ef_construction=64`) on `embedding`, **GIN** on `search_vector`,
unique `(document, index)`.

### Agent

```mermaid
stateDiagram-v2
  [*] --> agent
  agent --> tools: tool_calls and steps ≤ 6
  tools --> agent
  tools --> paused: action tool → interrupt()
  paused --> tools: approve / reject (Command resume)
  agent --> guard: final answer
  guard --> [*]
```

| Tool | Behaviour | Needs approval |
|---|---|---|
| `search_docs(query)` | calls `retrieval.search` | no |
| `read_doc(document_id)` | full text, only if the user may see it | no |
| `summarize(document_id)` | LLM summary of one document | no |
| `create_ticket(title, body)` | persists a `Ticket` | **yes** |

- **State** (`messages`, `session_id`, `user_id`, `steps`) is checkpointed in PostgreSQL with
  `thread_id = session-<id>`, giving per-conversation memory and resumability across processes.
- **Human-in-the-loop:** the action node calls `interrupt()`; a `PendingAction` is stored; `POST /api/actions/{id}/approve|reject`
  resumes with `Command(resume=…)`. The real side effect lives in `execute_action`, reachable only after approval and
  idempotent on `tool_call_id` (nodes re-execute on resume). Approvals are row-locked so a double click cannot resume twice.
- **Bounded:** after 6 LLM steps per turn the model is invoked *without tools* and must answer from what it has.
- **Guard:** a final answer with no supporting tool output in the current turn is replaced by the refusal message.
- **Streaming:** `?stream=1` returns Server-Sent Events: `session`, `token`, `tool_call`, `tool_result`, `interrupt`, `done`.

### MCP server

Standalone process (`python -m mcp_server`, stdio by default, `--http` for streamable HTTP) built on the official
Python SDK (`MCPServer`, mcp 2.x). Exposes tools `search_docs` and `read_doc`, and resource `docs://{document_id}`.
The caller's DRF token (env var for stdio, `Authorization` header for HTTP) resolves to a user, and every call goes
through the same `search` / `visible_documents` as everything else. Details: [docs/mcp-setup.md](docs/mcp-setup.md).

## Security model

- **Department scoping** — `admin` sees everything; others see `company` documents plus their own department's.
  Unauthenticated users see nothing. Implemented once in `documents/services/access.py`.
- **Existence is not leaked** — unreadable and non-existent documents return the same response.
- **Identity is server-side** — tools close over the authenticated user; an LLM (or an injected prompt) cannot
  pass a different `user_id`.
- **Sessions are private** — a session id belonging to another user returns 404.
- **Uploads** are restricted to `.pdf`, `.md`, `.txt`; `/api/ask` is rate-limited (30/min).
- **Secrets** are read from the environment only; `.env` is git-ignored.

## Quick start

Requires Docker with Compose.

```bash
git clone git@github.com:sangvirgo/knowledge-assistant.git
cd knowledge-assistant
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

| Service | URL | Notes |
|---|---|---|
| Web (UI + API) | http://localhost:8000 (`WEB_PORT`) | chat `/`, documents `/documents/`, admin `/admin/` |
| Langfuse | http://localhost:3000 (`LANGFUSE_PORT`) | `admin@example.com` / `adminadmin` (local dev only) |
| PostgreSQL + pgvector | `localhost:5433` (`PG_PORT`) | user / password / db: `app` |

Then in `/admin/`: create **Departments**, and assign each user a `department` and `role`.

### Try it with demo data

```bash
docker compose exec web python manage.py seed_demo
```

Idempotent. Creates departments `HR` / `Eng`, three users (password `demo1234`), and ingests the 8 documents in
[`samples/`](samples/) with mixed visibility:

| User | Department | Sees |
|---|---|---|
| `alice` | HR | company docs + salary / hiring docs |
| `bob` | Eng | company docs + deploy / on-call / coding-standards docs |
| `admin_demo` | — (admin) | everything |

Log in as each user and ask the same question to see permission scoping, e.g. *"Thưởng Tết bằng bao nhiêu tháng lương?"*
(answered for `alice`, refused for `bob`) and *"Rollback phải làm trong bao lâu?"* (the reverse). The command prints each
user's API token.

### Changing ports

Host ports come from `.env` (container ports are fixed): `WEB_PORT` (default 8000), `LANGFUSE_PORT` (3000),
`PG_PORT` (5433). The web UI and the API are the same Django app, so `WEB_PORT` moves both.
Example: `WEB_PORT=8100` → http://localhost:8100. `docker compose up -d` applies the change.

> **No API keys needed to try it.** With `LLM_*` / `EMBEDDING_*` unset the app runs on built-in offline fakes
> (hash-based embeddings, extractive LLM). The whole flow works, but answer quality is *not* representative of a real model.

### Using real models

Set in `.env`, then `docker compose up -d --build`:

```ini
LLM_MODEL=…                 LLM_API_KEY=…            LLM_BASE_URL=      # OpenAI-compatible endpoint
EMBEDDING_MODEL=…           EMBEDDING_API_KEY=…      EMBEDDING_BASE_URL=
RERANK_MODEL=BAAI/bge-reranker-base                  # requires: uv sync --extra rerank
```

Vectors are stored as 1536-dimensional. A different dimension means changing `EMBEDDING_DIM` in
`apps/documents/models.py` and creating a migration; changing the embedding model requires re-ingesting documents.

## API

Authentication: session cookie (UI) or `Authorization: Token <key>` (obtained from `POST /api/token/`).

| Method & path | Description |
|---|---|
| `POST /api/token/` | `username`, `password` → `{token}` |
| `GET` `POST /api/documents/` | list visible / upload (`title`, `file`, `visibility`) |
| `GET` `DELETE /api/documents/{id}/` | detail / delete (owner or admin) |
| `POST /api/ask` | `{question, session_id?}` → `{answer, sources[], trace_id, session_id}` |
| `GET /api/sessions/` · `GET /api/sessions/{id}/messages/` | chat history |
| `POST /api/agent/ask[?stream=1]` | agent turn (JSON, or SSE) |
| `POST /api/actions/{id}/approve` · `…/reject` | resolve a pending agent action (`409` if already resolved) |

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/token/ -d username=USER -d password=PASS \
        | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

curl -X POST localhost:8000/api/documents/ -H "Authorization: Token $TOKEN" \
     -F title="Leave policy" -F file=@leave.md -F visibility=company

curl -X POST localhost:8000/api/ask -H "Authorization: Token $TOKEN" \
     -H 'Content-Type: application/json' -d '{"question":"How many leave days do I get?"}'

curl -N -X POST "localhost:8000/api/agent/ask?stream=1" -H "Authorization: Token $TOKEN" \
     -H 'Content-Type: application/json' -d '{"question":"Open a ticket for a new laptop"}'
```

## Configuration

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` | Django basics (set a real secret outside dev) |
| `DATABASE_URL`, `REDIS_URL` | PostgreSQL (pgvector) and Celery broker/result backend |
| `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` | chat model (OpenAI-compatible); unset → offline fake |
| `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL` | embeddings; unset → offline fake |
| `RERANK_MODEL` | cross-encoder name; unset → lexical placeholder |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | trace export (optional) |
| `LLM_PRICE_IN_PER_1M`, `LLM_PRICE_OUT_PER_1M` | USD per 1M tokens, for cost estimates in logs |
| `MCP_API_TOKEN` | DRF token used by the stdio MCP server |
| `WEB_PORT`, `LANGFUSE_PORT`, `PG_PORT` | host ports published by Docker Compose |
| `CELERY_ALWAYS_EAGER` | `1` runs ingestion synchronously (no worker) |

## Observability

Each request logs one JSON line on logger `ka.request`:

```json
{"trace_id": "62213a56…", "name": "ask", "user_id": 2, "session_id": 3, "latency_ms": 239.7,
 "tokens_in": 0, "tokens_out": 0, "est_cost_usd": 0.0,
 "steps": [{"step": "llm", "ms": 0.5, "in": 0, "out": 0}]}
```

The same `trace_id` is stored on the assistant `Message` and used as the Langfuse trace id. Tracing is implemented as
a small LangChain callback (`services/tracing.py`) that talks to Langfuse's low-level client; it never raises into
the request path. (Langfuse's own LangChain handler in SDK 2.x requires `langchain<1`, which conflicts with the
`langchain-core` 1.x used here.)

## Development

```bash
docker compose up -d postgres redis     # test database on :5433
cp .env.example .env                    # DATABASE_URL=postgres://app:app@localhost:5433/app
                                        # REDIS_URL=redis://localhost:6379/0
uv sync
uv run python manage.py migrate
uv run pytest                           # 43 tests, no network access
uv run ruff check . && uv run ruff format --check .
uv run python manage.py runserver       # add CELERY_ALWAYS_EAGER=1 to ingest without a worker
```

### Test suite

Coverage focuses on the properties that matter:

- department isolation — in retrieval (every flag combination), the agent, and MCP
- ingest idempotency, duplicate rejection, extension validation
- chunker behavior (heading breadcrumbs, overlap, page metadata) and RRF
- `create_ticket` cannot execute before approval; rejection creates nothing; only the owner may approve; no double-approve
- agent step limit, evidence guard, cross-turn memory, SSE event order
- every request produces a `trace_id` and a JSON log record

### Evaluation

```bash
uv run python -m eval.run_eval
```

Builds a throwaway database, ingests `eval/corpus/`, and runs 24 golden questions (18 answerable, 3 unanswerable,
3 forbidden-by-permission) against *vector*, *hybrid* and *hybrid + rerank*, reporting hit-rate@5, MRR, permission
leaks and latency. **Current results are saturated** (corpus is tiny, embeddings are fake) and prove only that the
pipeline works and nothing leaks — not that hybrid or rerank is better. See [eval/REPORT.md](eval/REPORT.md).

## Project layout

```
apps/
  accounts/    User, Department
  documents/   Document, Chunk · parsing, chunking, ingest · access rules · upload API
  retrieval/   search() · RRF fusion
  chat/        RAG chain · /api/ask · sessions · UI pages
  agent/       LangGraph graph · tools · checkpointing · runner (JSON + SSE) · PendingAction, Ticket
services/      llm.py · embeddings.py · rerank.py · tracing.py   ← seams for test fakes
mcp_server/    MCP server (core logic + protocol wiring)
samples/       demo documents for `seed_demo`
eval/          golden set · corpus · run_eval.py · REPORT.md
config/        settings · urls · celery
docs/          architecture · mcp-setup · interview
tests/
```

## Known limitations

- Never exercised against a real LLM, embedding model or cross-encoder; behavior with them is unverified.
- Evaluation is saturated and does not yet include Ragas metrics.
- The UI was verified through server-side tests and `curl` (including SSE), not in a real browser.
- Token-level streaming depends on the model; the offline fake returns a single chunk.
- SSE runs on synchronous gunicorn workers; production load would call for ASGI.
- The MCP server was verified over stdio with a real MCP client, but not yet from Claude Code itself or in HTTP mode.

## License

No license has been chosen yet.
