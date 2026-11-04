# Internal Knowledge Assistant

Hỏi đáp tài liệu nội bộ: Django + DRF, pgvector, RAG hybrid (vector + FTS → RRF → rerank), agent LangGraph
(có xác nhận cho hành động), MCP server cho Claude Code, Celery, Langfuse, Docker.

Kiến trúc: [docs/architecture.md](docs/architecture.md) · MCP: [docs/mcp-setup.md](docs/mcp-setup.md) ·
Phỏng vấn: [docs/INTERVIEW.md](docs/INTERVIEW.md) · Đánh giá: [eval/REPORT.md](eval/REPORT.md)

## Chạy
```bash
cp .env.example .env          # khóa API là tuỳ chọn: thiếu thì dùng provider giả (offline)
docker compose up --build     # web :8000, langfuse :3000 (admin@example.com / adminadmin)
docker compose exec web python manage.py createsuperuser
```
Vào http://localhost:8000/login/ → Chat (`/`) và Tài liệu (`/documents/`). Admin: `/admin/` (tạo Department, gán user).

Để dùng mô hình thật: điền `LLM_MODEL`, `LLM_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY` (endpoint tương thích OpenAI;
đặt `*_BASE_URL` nếu cần), `RERANK_MODEL` (cài extra `rerank`). Đổi embedding sang chiều khác 1536 cần migration mới.

## API
`POST /api/token/` · `POST/GET /api/documents/` · `POST /api/ask` · `GET /api/sessions/[id/messages/]` ·
`POST /api/agent/ask[?stream=1]` · `POST /api/actions/{id}/approve|reject`

## Phát triển
```bash
docker compose up -d postgres redis
uv sync && uv run pytest && uv run ruff check .
```

## Giới hạn đã biết
Chưa kiểm chứng với dịch vụ AI thật; eval hiện bão hòa (corpus nhỏ, embedding giả); chưa chạy Ragas;
UI chưa thử trên trình duyệt thật (chỉ test server + SSE qua curl).
