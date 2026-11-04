# Internal Knowledge Assistant

Hỏi đáp tài liệu nội bộ bằng RAG, có AI agent và MCP server để Claude Code đọc tài liệu trực tiếp.

## Cấu trúc

```
.claude/        agent builder + skill spec
config/         settings, urls, celery
apps/           accounts, documents, retrieval, chat, agent
mcp_server/     MCP server độc lập
eval/           golden set + báo cáo đánh giá
docs/           architecture, interview, mcp-setup
tests/
```

## Bắt đầu

1. `cp .env.example .env` và điền khóa.
2. Mở Claude Code trong thư mục này và gõ: `dùng knowledge-assistant-builder dựng phase 0 và 1`.
3. Tiếp tục từng phase theo bảng trong `.claude/agents/knowledge-assistant-builder.md`.

README sẽ được hoàn thiện ở phase 11.
