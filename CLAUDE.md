# Internal Knowledge Assistant

Hệ thống hỏi đáp tài liệu nội bộ: Django + DRF, pgvector, LangChain/LangGraph (RAG hybrid + rerank), AI agent, MCP server, Celery, tracing, Docker.

Spec đầy đủ: skill `knowledge-assistant` (`.claude/skills/knowledge-assistant/SKILL.md`).
Dựng dự án: agent `knowledge-assistant-builder` (`.claude/agents/`), làm theo phase 0 → 11.

## Trạng thái
Mới có khung thư mục. Chưa có code. Bắt đầu từ phase 0.

## Lệnh (sẽ có sau phase 0-1)
- `docker compose up` chạy toàn bộ hệ thống
- `uv run pytest` chạy test
- `uv run ruff check .` lint

## Quy tắc
- `views` mỏng → `services` chứa logic → `models`.
- Mọi truy vấn tài liệu (UI, agent, MCP) **phải** qua `retrieval.services.search(user, query, k)`; quyền phòng ban áp dụng ở đó.
- Mọi lời gọi LLM/embedding đi qua `services/llm.py`, `services/embeddings.py` để test thay bằng bản giả. Test không gọi dịch vụ ngoài.
- Khóa API chỉ đọc từ `.env`, không commit.
- Kiểm tra docs của đúng phiên bản thư viện đã cài trước khi dùng API (LangChain, LangGraph, MCP SDK đổi nhanh).

## Phần người dùng muốn tự viết để hiểu
Chunking + retrieval, hybrid search + rerank, graph của agent, MCP server. Giữ code tối giản, có chú thích "tại sao", dừng lại giải thích sau khi xong. Phần boilerplate thì làm nhanh.
