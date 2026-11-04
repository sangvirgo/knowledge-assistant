---
name: knowledge-assistant
description: Spec đầy đủ cho đồ án Internal Knowledge Assistant (Django + DRF, pgvector, LangChain/LangGraph, RAG hybrid + rerank, AI agent, MCP server, Celery, tracing, Docker). Dùng khi dựng, mở rộng hoặc debug dự án này, hoặc khi cần quy ước thiết kế RAG/agent/MCP của nó.
---

# Internal Knowledge Assistant: spec

Hệ thống hỏi đáp tài liệu nội bộ: người dùng đăng nhập, tải tài liệu theo phòng ban, hỏi bằng chat, agent tra cứu và hành động, và toàn bộ kho tài liệu được phơi bày qua MCP cho các công cụ như Claude Code.

> Lưu ý: tên API của Django/DRF/LangChain/LangGraph/MCP SDK thay đổi theo phiên bản. Dưới đây là **thiết kế**; khi cài đặt, kiểm tra tài liệu của phiên bản đã khoá trong `uv.lock`.

## 1. Stack

| Lớp | Lựa chọn |
|---|---|
| Ngôn ngữ / quản lý gói | Python 3.12, `uv` |
| Web | Django, Django REST Framework |
| DB | PostgreSQL + `pgvector` (vector) + Full-Text Search (BM25-like) |
| Queue | Celery + Redis |
| RAG | LangChain (loader, splitter, embeddings, retriever) |
| Agent | LangGraph |
| MCP | Python MCP SDK (`mcp` 2.x: `MCPServer`; 1.x called it `FastMCP`) |
| Rerank | cross-encoder (vd `bge-reranker`) hoặc API rerank; đặt sau interface để thay được |
| Đánh giá | Ragas + golden set tự viết |
| Tracing | Langfuse (self-host qua Docker) hoặc LangSmith |
| Test | pytest, pytest-django, factory-boy |
| Chất lượng | ruff, mypy (nới lỏng), pre-commit |
| Đóng gói | Docker Compose |

Chỉ dùng **một** embedding model và **một** LLM chính, cấu hình qua biến môi trường (`EMBEDDING_MODEL`, `LLM_MODEL`). Mọi lời gọi LLM/embedding đi qua một lớp mỏng (`services/llm.py`, `services/embeddings.py`) để test thay bằng bản giả.

## 2. Cấu trúc repo

```
knowledge-assistant/
├── CLAUDE.md
├── pyproject.toml
├── docker-compose.yml
├── .env.example
├── manage.py
├── config/                 # settings, urls, celery.py
├── apps/
│   ├── accounts/           # User, Department, token auth
│   ├── documents/          # Document, Chunk, ingest tasks
│   ├── retrieval/          # vector, keyword, fusion, rerank
│   ├── chat/               # ChatSession, Message, /ask, SSE
│   └── agent/              # LangGraph graph, tools, guardrails
├── mcp_server/             # MCP server độc lập (gọi retrieval qua service layer)
├── eval/                   # golden.jsonl, run_eval.py, REPORT.md
├── docs/                   # architecture.md, INTERVIEW.md, mcp-setup.md
└── tests/
```

Quy tắc phân tầng: `views` mỏng → `services` chứa logic → `models`. Agent và MCP **không** truy cập ORM trực tiếp cho việc tìm kiếm; cả hai gọi `retrieval.services.search(user, query, k)` để quyền truy cập được áp dụng ở một chỗ duy nhất.

## 3. Mô hình dữ liệu

- `Department(name)`
- `User` (custom): `department` (FK), `role` (`member` | `admin`)
- `Document`: `title`, `file`, `owner`, `department` (FK, null = công khai nội bộ), `visibility` (`department` | `company`), `status` (`pending` | `processing` | `ready` | `failed`), `content_hash` (chống ingest trùng), `created_at`
- `Chunk`: `document` (FK), `index`, `text`, `embedding` (vector), `search_vector` (tsvector), `metadata` (JSON: trang, heading), `token_count`
- `ChatSession`: `user`, `title`, `created_at`
- `Message`: `session`, `role` (`user` | `assistant` | `tool`), `content`, `sources` (JSON), `trace_id`, `created_at`
- `PendingAction`: `session`, `tool`, `args` (JSON), `status` (`pending` | `approved` | `rejected`) cho human-in-the-loop

Chỉ mục: HNSW trên `embedding`, GIN trên `search_vector`, index `(document, index)` duy nhất.

## 4. Ingest (Celery)

1. `POST /api/documents/` lưu file, tạo `Document(status=pending)`, đẩy task.
2. Task: tính `content_hash` (bỏ qua nếu đã có) → parse (PDF/MD/TXT) → chia chunk → embed theo batch → lưu `Chunk` trong một transaction → `status=ready`. Lỗi → `failed` kèm lý do.
3. **Chunking**: tách theo cấu trúc (heading Markdown / đoạn) trước, rồi theo kích thước ~500–800 token, overlap ~10–15%. Giữ `metadata` (trang, heading) để trích dẫn.
4. **Idempotent**: chạy lại task không tạo chunk trùng (xoá chunk cũ của document trước khi ghi).

## 5. Retrieval

`search(user, query, k=8) -> list[ScoredChunk]`

1. **Lọc quyền trước**: giới hạn tập chunk theo `visibility`/`department` của `user` *trong câu truy vấn SQL* (không lọc sau khi lấy kết quả).
2. **Vector**: top-N theo cosine từ pgvector.
3. **Keyword**: top-N theo Postgres FTS (`ts_rank_cd`).
4. **Fusion**: Reciprocal Rank Fusion (k≈60) hợp nhất hai danh sách.
5. **Rerank**: cross-encoder chấm lại top ~30, giữ top-k.
6. Trả về `ScoredChunk(chunk, score, source_ref)`.

Mỗi bước bật/tắt được bằng cờ để phục vụ so sánh trong đánh giá.

## 6. RAG và API

- Prompt: trả lời **chỉ** dựa trên ngữ cảnh; nếu không đủ → nói không biết; luôn kèm trích dẫn `[n]` ứng với `sources`.
- `POST /api/ask` `{session_id?, question}` → `{answer, sources:[{document_id,title,chunk_index,snippet}], trace_id}`
- `GET /api/sessions/`, `GET /api/sessions/{id}/messages/`
- `POST /api/documents/`, `GET /api/documents/`, `DELETE /api/documents/{id}/`
- Auth: session cookie cho UI, token cho API/MCP. Throttle cho `/ask`.

## 7. Agent (LangGraph)

State: `messages`, `session_id`, `user_id`, `steps`.

Node: `router` → (`retrieve` | `tools` | `answer`) → `guard` → kết thúc.

Tools:
| Tool | Hành vi | Cần xác nhận |
|---|---|---|
| `search_docs(query)` | gọi `retrieval.search` | không |
| `read_doc(document_id)` | đọc toàn văn nếu có quyền | không |
| `summarize(document_id)` | tóm tắt một tài liệu | không |
| `create_ticket(title, body)` | tạo bản ghi ticket (mô phỏng, lưu DB) | **có** |

Quy tắc:
- Giới hạn tối đa N bước (vd 6); vượt → dừng và trả lời bằng thông tin hiện có.
- Tool hành động tạo `PendingAction` và dừng đồ thị (interrupt) đến khi người dùng duyệt qua `POST /api/actions/{id}/approve|reject`.
- Không có nguồn hỗ trợ → từ chối thay vì suy đoán.
- Checkpoint theo `session_id` để có memory và resume.
- Streaming token + sự kiện tool qua SSE.

## 8. MCP server

- Chạy độc lập (`python -m mcp_server`), hỗ trợ stdio (Claude Code local) và HTTP.
- Tools: `search_docs(query, k)`, `read_doc(document_id)`.
- Resource: `docs://{document_id}` trả toàn văn.
- Xác thực: token người dùng qua biến môi trường/header; mọi truy vấn đi qua `retrieval.search` với user tương ứng nên quyền phòng ban được tôn trọng.
- Mô tả tool viết cho LLM đọc: nói rõ khi nào dùng, tham số, và định dạng kết quả; trả kết quả ngắn gọn, có `document_id` và trích đoạn.
- `docs/mcp-setup.md` hướng dẫn thêm vào Claude Code (`claude mcp add ...`) và ví dụ hỏi thử.

## 9. UI

Django template + HTMX (hoặc JS thuần): trang đăng nhập, danh sách/tải tài liệu (hiện trạng thái ingest), trang chat streaming qua SSE, hộp xác nhận cho `PendingAction`. Không dựng SPA.

## 10. Đánh giá

- `eval/golden.jsonl`: ≥20 dòng `{question, expected_answer, expected_sources}`, gồm cả câu **không có đáp án** và câu **bị cấm theo quyền**.
- `eval/run_eval.py`: chạy 3 cấu hình (vector, hybrid, hybrid+rerank) → metric Ragas (faithfulness, answer relevancy, context precision/recall) + hit-rate@k + độ trễ.
- `eval/REPORT.md`: bảng so sánh và nhận xét ngắn. Không công bố con số chưa chạy thật.

## 11. Quan sát

Langfuse/LangSmith gắn vào chain và agent; mỗi `Message` lưu `trace_id`. Ghi log JSON gồm user, độ trễ từng bước, số token, chi phí ước tính.

## 12. Kiểm thử

- Unit: chunker, fusion (RRF), guardrails, quyền.
- Integration: ingest end-to-end với embedding giả; `/ask` với LLM giả.
- **Bắt buộc có**: test quyền (người dùng khác phòng không thấy chunk, kể cả qua agent và MCP), test idempotent ingest, test `create_ticket` không chạy khi chưa duyệt, test giới hạn bước agent.
- Không gọi dịch vụ ngoài trong test; dùng fake qua lớp `services/`.

## 13. Cấu hình môi trường (`.env.example`)

```
DJANGO_SECRET_KEY=
DATABASE_URL=postgres://...
REDIS_URL=redis://redis:6379/0
LLM_MODEL=
LLM_API_KEY=
EMBEDDING_MODEL=
EMBEDDING_API_KEY=
RERANK_MODEL=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
MCP_API_TOKEN=
```

## 14. Nội dung `CLAUDE.md` của repo

Ghi: lệnh chạy (`docker compose up`, `uv run pytest`, `uv run ruff check`), sơ đồ thư mục, quy tắc phân tầng, quy ước "mọi truy vấn tài liệu phải qua `retrieval.search`", cách thay fake provider trong test, và danh sách phần người dùng muốn tự viết (chunking, hybrid/rerank, graph agent, MCP).

## 15. Định nghĩa hoàn thành

- [ ] `docker compose up` chạy đủ web, worker, redis, postgres, (langfuse)
- [ ] Upload → ingest → hỏi đáp có trích dẫn hoạt động
- [ ] Phân quyền được kiểm thử ở retrieval, agent, MCP
- [ ] `eval/REPORT.md` có số liệu thật cho 3 cấu hình
- [ ] Agent: tool hành động cần duyệt, có giới hạn bước, streaming
- [ ] MCP kết nối được từ Claude Code và trả kết quả đúng quyền
- [ ] Mỗi request có trace
- [ ] `pytest` và `ruff` xanh
- [ ] README + `docs/architecture.md` + `docs/INTERVIEW.md` + `docs/mcp-setup.md`
