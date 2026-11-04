# Internal Knowledge Assistant

Hỏi đáp tài liệu nội bộ bằng RAG. Người dùng đăng nhập, tải tài liệu theo phòng ban, chat với trợ lý (có trích dẫn),
agent có thể tra cứu và tạo ticket (cần xác nhận), và kho tài liệu được phơi bày qua MCP cho Claude Code.

**Stack:** Django + DRF · PostgreSQL + pgvector (+ full-text search) · Celery + Redis · LangChain · LangGraph · MCP SDK · Langfuse · Docker.

Tài liệu thêm: [kiến trúc](docs/architecture.md) · [cắm MCP vào Claude Code](docs/mcp-setup.md) ·
[câu hỏi phỏng vấn](docs/INTERVIEW.md) · [báo cáo đánh giá](eval/REPORT.md)

---

## 1. Yêu cầu
- Docker + Docker Compose
- (Chỉ khi phát triển/chạy test ngoài Docker) [uv](https://docs.astral.sh/uv/) — tự cài Python 3.12

## 2. Cài đặt và chạy (cách nhanh nhất)

```bash
git clone git@github.com:sangvirgo/knowledge-assistant.git
cd knowledge-assistant
cp .env.example .env
docker compose up --build
```

Khi các service `healthy`, mở **http://localhost:8000**.

| Service | Địa chỉ | Ghi chú |
|---|---|---|
| Web (Django) | http://localhost:8000 | Chat `/`, Tài liệu `/documents/`, Admin `/admin/` |
| Langfuse | http://localhost:3000 | tài khoản `admin@example.com` / `adminadmin` |
| Postgres (pgvector) | localhost:5433 | user/pass/db: `app` |

> Không cần khóa API để chạy thử: nếu `LLM_*`/`EMBEDDING_*` để trống, hệ thống dùng **mô hình giả chạy offline**
> (embedding băm từ, LLM trích đoạn khớp nhất). Đủ để thấy toàn bộ luồng, nhưng **chất lượng không phải của mô hình thật**.

### Tạo tài khoản đầu tiên
```bash
docker compose exec web python manage.py createsuperuser
```
Vào `/admin/` → tạo **Department** (vd HR, Eng) → mở User, gán `department` và `role` (`member`/`admin`).
`admin` xem được mọi tài liệu; `member` chỉ thấy tài liệu **công ty** và tài liệu **phòng ban của mình**.

## 3. Cách dùng

### Qua giao diện web
1. Đăng nhập tại `/login/`.
2. **Tài liệu** (`/documents/`): chọn file PDF/MD/TXT, đặt phạm vi *Phòng ban* hoặc *Toàn công ty*, bấm Tải lên.
   Trạng thái đi `pending → processing → ready` (trang tự cập nhật). `failed` kèm lý do (vd trùng nội dung).
3. **Chat** (`/`): đặt câu hỏi. Câu trả lời stream từng phần, kèm nguồn `[n]`. Nếu tài liệu không có thông tin,
   trợ lý nói rõ là không tìm thấy thay vì đoán.
4. Nếu bạn nhờ trợ lý *tạo ticket*, một hộp **Cần xác nhận** hiện ra — bấm Duyệt hoặc Từ chối. Chưa duyệt thì chưa có gì được tạo.

### Qua API
```bash
# 1) lấy token
TOKEN=$(curl -s -X POST localhost:8000/api/token/ -d username=USER -d password=PASS | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 2) tải tài liệu
curl -X POST localhost:8000/api/documents/ -H "Authorization: Token $TOKEN" \
  -F title="Quy định nghỉ phép" -F file=@nghi-phep.md -F visibility=company

# 3) hỏi (RAG đơn giản)
curl -X POST localhost:8000/api/ask -H "Authorization: Token $TOKEN" \
  -H 'Content-Type: application/json' -d '{"question":"Tôi có bao nhiêu ngày phép?"}'

# 4) hỏi qua agent (thêm ?stream=1 để nhận SSE)
curl -N -X POST "localhost:8000/api/agent/ask?stream=1" -H "Authorization: Token $TOKEN" \
  -H 'Content-Type: application/json' -d '{"question":"Tạo ticket xin laptop"}'

# 5) duyệt/từ chối hành động đang chờ (action_id lấy từ sự kiện interrupt / trường pending_action)
curl -X POST localhost:8000/api/actions/1/approve -H "Authorization: Token $TOKEN"
```

| Endpoint | Mô tả |
|---|---|
| `POST /api/token/` | lấy token từ username/password |
| `GET/POST /api/documents/`, `GET/DELETE /api/documents/{id}/` | quản lý tài liệu (chỉ chủ sở hữu/admin được xoá) |
| `POST /api/ask` | `{question, session_id?}` → `{answer, sources[], trace_id, session_id}` |
| `GET /api/sessions/`, `GET /api/sessions/{id}/messages/` | lịch sử chat |
| `POST /api/agent/ask[?stream=1]` | agent (tool + memory theo session) |
| `POST /api/actions/{id}/approve\|reject` | duyệt hành động của agent |

### Dùng từ Claude Code (MCP)
Xem [docs/mcp-setup.md](docs/mcp-setup.md). Tóm tắt:
```bash
claude mcp add knowledge-assistant --env MCP_API_TOKEN=<token> \
  -- uv run --directory /đường/dẫn/knowledge-assistant python -m mcp_server
```
(cần `docker compose up -d postgres redis` và `.env` có `DATABASE_URL=postgres://app:app@localhost:5433/app`).

## 4. Dùng mô hình thật
Sửa `.env` rồi `docker compose up -d --build`:
```
LLM_MODEL=...            LLM_API_KEY=...            LLM_BASE_URL=      # tuỳ chọn, endpoint tương thích OpenAI
EMBEDDING_MODEL=...      EMBEDDING_API_KEY=...      EMBEDDING_BASE_URL=
RERANK_MODEL=            # vd BAAI/bge-reranker-base; cần cài extra: uv sync --extra rerank
LANGFUSE_PUBLIC_KEY=pk-lf-dev  LANGFUSE_SECRET_KEY=sk-lf-dev  LANGFUSE_HOST=http://langfuse:3000
```
Lưu ý: vector lưu 1536 chiều. Model embedding khác chiều cần sửa `EMBEDDING_DIM` trong `apps/documents/models.py` và tạo migration mới.
Nếu đổi model embedding, phải ingest lại tài liệu.

## 5. Phát triển
```bash
docker compose up -d postgres redis      # DB cho test (cổng 5433)
cp .env.example .env                     # đặt DATABASE_URL=postgres://app:app@localhost:5433/app, REDIS_URL=redis://localhost:6379/0
uv sync
uv run python manage.py migrate
uv run pytest                            # 43 test, không gọi dịch vụ ngoài
uv run ruff check .                      # lint
uv run python -m eval.run_eval           # so sánh vector / hybrid / hybrid+rerank
uv run python manage.py runserver        # chạy web (cần worker nếu muốn ingest thật: celery -A config worker -l info,
                                         #  hoặc đặt CELERY_ALWAYS_EAGER=1 để ingest chạy ngay trong request)
```

## 6. Cấu trúc
```
apps/accounts    User, Department, quyền
apps/documents   Document/Chunk, ingest (parse → chunk → embed), access rule
apps/retrieval   search(): lọc quyền trong SQL → vector + FTS → RRF → rerank
apps/chat        RAG + /api/ask + trang UI
apps/agent       LangGraph agent, tools, xác nhận hành động, SSE
services/        llm.py, embeddings.py, rerank.py, tracing.py  (điểm thay bản giả khi test)
mcp_server/      MCP server (stdio / HTTP)
eval/            golden set + run_eval.py + REPORT.md
```
Quy tắc cốt lõi: **mọi truy vấn tài liệu đi qua `retrieval.services.search(user, query, k)`** nên quyền phòng ban chỉ áp dụng một chỗ.

## 7. Xử lý sự cố
- **Upload mãi `pending`**: worker chưa chạy (`docker compose ps`, `docker compose logs worker`).
- **`failed: Trùng nội dung`**: file có cùng nội dung với tài liệu đã `ready`.
- **Test báo lỗi kết nối DB**: chạy `docker compose up -d postgres` và kiểm tra `DATABASE_URL` trỏ cổng `5433`.
- **Cổng 5433/8000/3000 bận**: đổi ánh xạ cổng trong `docker-compose.yml`.

## 8. Giới hạn đã biết
Chưa kiểm chứng với LLM/embedding/rerank thật; báo cáo eval bão hòa (corpus nhỏ, embedding giả) và chưa có Ragas;
UI chưa thử trên trình duyệt thật; streaming token phụ thuộc mô hình (mô hình giả trả một khối).
