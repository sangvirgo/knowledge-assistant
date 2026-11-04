# Cắm MCP server vào Claude Code

MCP server (`python -m mcp_server`) phơi bày `search_docs`, `read_doc` và resource `docs://{id}`.
Quyền theo phòng ban của **chủ token** được áp dụng (cùng `retrieval.search` với UI/agent).

## 1. Lấy token
```bash
curl -s -X POST localhost:8000/api/token/ -d username=<user> -d password=<pass>
# => {"token": "..."}
```

## 2. Thêm vào Claude Code (stdio, chạy local)
Postgres phải chạy (`docker compose up -d postgres redis`), `.env` trỏ `DATABASE_URL` tới `localhost:5433`.
```bash
claude mcp add knowledge-assistant \
  --env MCP_API_TOKEN=<token> \
  -- uv run --directory /đường/dẫn/knowledge-assistant python -m mcp_server
```

## 3. Hoặc HTTP (nhiều người dùng, token theo header)
```bash
uv run python -m mcp_server --http          # streamable HTTP
claude mcp add --transport http knowledge-assistant http://localhost:8000/mcp \
  --header "Authorization: Bearer <token>"
```
(Địa chỉ/cổng HTTP do SDK quyết định, kiểm tra log khi khởi động.)

## 4. Thử
Trong Claude Code, hỏi: *"Dùng knowledge-assistant tìm quy định nghỉ phép năm"* rồi *"đọc toàn văn tài liệu 3"*.
Người dùng khác phòng ban sẽ nhận "Không có kết quả" / "không có quyền" cho tài liệu bị cấm.

Đã kiểm chứng: client MCP qua stdio gọi `list_tools` và `search_docs` thành công, đúng quyền.
Chưa kiểm chứng trực tiếp trong giao diện Claude Code và chế độ HTTP.
