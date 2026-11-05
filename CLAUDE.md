# Internal Knowledge Assistant

Hệ thống hỏi đáp tài liệu nội bộ: Django + DRF, pgvector, LangChain/LangGraph (RAG hybrid + rerank), AI agent, MCP server, Celery, tracing, Docker.

Spec đầy đủ: skill `knowledge-assistant` (`.claude/skills/knowledge-assistant/SKILL.md`).
Dựng dự án: agent `knowledge-assistant-builder` (`.claude/agents/`), làm theo phase 0 → 11.

## Trạng thái
Phase 0–11 đã dựng xong. Chưa kiểm chứng với LLM/embedding/rerank thật (mặc định dùng bản giả khi thiếu khóa).

## Lệnh
- `docker compose up` chạy toàn bộ hệ thống (cổng host: WEB_PORT=8000, LANGFUSE_PORT=3000, PG_PORT=5433 trong .env)
- `uv run pytest` chạy test (cần postgres của compose: `docker compose up -d postgres`)
- `uv run ruff check .` lint
- `uv run python -m eval.run_eval` đánh giá retrieval
- `docker compose exec web python manage.py seed_demo` nạp dữ liệu demo (alice/bob/admin_demo, mật khẩu demo1234)
- `uv run python -m mcp_server` MCP server (xem docs/mcp-setup.md)

## Sơ đồ
`apps/{accounts,documents,retrieval,chat,agent}`, `services/{llm,embeddings,rerank,tracing}.py`,
`mcp_server/`, `eval/`, `docs/`. Fake provider cho test: `set_embedder/set_chat_model/set_reranker`.

## Quy tắc
- `views` mỏng → `services` chứa logic → `models`.
- Mọi truy vấn tài liệu (UI, agent, MCP) **phải** qua `retrieval.services.search(user, query, k)`; quyền phòng ban áp dụng ở đó.
- Mọi lời gọi LLM/embedding đi qua `services/llm.py`, `services/embeddings.py` để test thay bằng bản giả. Test không gọi dịch vụ ngoài.
- Khóa API chỉ đọc từ `.env`, không commit.
- Kiểm tra docs của đúng phiên bản thư viện đã cài trước khi dùng API (LangChain, LangGraph, MCP SDK đổi nhanh).

## Phần người dùng muốn tự viết để hiểu
Chunking + retrieval, hybrid search + rerank, graph của agent, MCP server. Giữ code tối giản, có chú thích "tại sao", dừng lại giải thích sau khi xong. Phần boilerplate thì làm nhanh.

- Commit nhỏ theo phase, KHÔNG thêm dòng Co-Authored-By.
