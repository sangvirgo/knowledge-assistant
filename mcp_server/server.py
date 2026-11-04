"""MCP server (SDK `mcp` 2.x: lớp `MCPServer`, tiền thân là FastMCP của 1.x).

Chạy:  python -m mcp_server              # stdio (Claude Code local)
       python -m mcp_server --http       # streamable HTTP, token qua header Authorization
Mô tả tool viết cho LLM đọc: nói rõ khi nào dùng, tham số, định dạng kết quả.
"""

import os

from mcp.server.mcpserver import Context, MCPServer

from . import core

mcp = MCPServer(
    "knowledge-assistant",
    instructions=(
        "Tra cứu tài liệu nội bộ công ty. Luôn gọi search_docs trước; dùng read_doc khi cần "
        "toàn văn. Chỉ thấy tài liệu mà người dùng của token được phép xem."
    ),
)


def _user(ctx: Context | None):
    """HTTP: lấy token từ header từng request (đa người dùng). stdio: biến môi trường."""
    token = None
    if ctx is not None:
        try:
            token = core.token_from_headers(ctx.headers)
        except ValueError:  # gọi trực tiếp, không có request (test) => dùng env
            pass
    return core.user_from_token(token or os.environ.get("MCP_API_TOKEN"))


@mcp.tool()
def search_docs(query: str, k: int = 5, ctx: Context | None = None) -> str:
    """Tìm kiếm ngữ nghĩa + từ khoá trong tài liệu nội bộ (chính sách, quy trình, kỹ thuật).

    Dùng KHI người dùng hỏi về nội dung tài liệu công ty. Không dùng cho kiến thức chung.

    Args:
        query: Câu hỏi hoặc từ khoá, nên viết đầy đủ ý (tiếng Việt hoặc Anh).
        k: Số đoạn tối đa trả về (1-20, mặc định 5).

    Trả về: danh sách đánh số, mỗi mục có document_id, tiêu đề, số đoạn và trích đoạn ngắn.
    Dùng document_id với read_doc để đọc toàn văn.
    """
    return core.search_docs(_user(ctx), query, k)


@mcp.tool()
def read_doc(document_id: int, ctx: Context | None = None) -> str:
    """Đọc toàn văn một tài liệu theo document_id (lấy từ kết quả search_docs).

    Dùng khi trích đoạn chưa đủ chi tiết. Lỗi nếu tài liệu không tồn tại hoặc không có quyền xem.

    Args:
        document_id: ID số nguyên của tài liệu.

    Trả về: tiêu đề và nội dung văn bản (cắt ở ~20.000 ký tự).
    """
    return core.read_doc(_user(ctx), document_id)


@mcp.resource("docs://{document_id}", mime_type="text/markdown")
def doc_resource(document_id: str, ctx: Context | None = None) -> str:
    """Toàn văn tài liệu `docs://<document_id>` (cùng quyền như read_doc)."""
    return core.read_doc(_user(ctx), int(document_id))
