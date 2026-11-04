"""Tools của agent. Tạo theo từng request để đóng gói `user` (quyền KHÔNG nằm trong tham số LLM).

TẠI SAO user nằm trong closure chứ không phải tham số tool? Nếu để LLM truyền user_id, một
prompt-injection có thể đổi danh tính. Danh tính đến từ phiên đăng nhập, LLM không chạm tới.
"""

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from apps.agent.models import Ticket
from apps.documents.models import Document
from apps.documents.services.access import visible_documents
from apps.retrieval.services import search
from services.llm import get_chat_model

EVIDENCE_TOOLS = {"search_docs", "read_doc", "summarize"}
ACTION_TOOLS = {"create_ticket"}  # tool có tác dụng phụ => cần người dùng xác nhận
MAX_DOC_CHARS = 20000
NO_RESULTS = "NO_RESULTS"


def _doc_text(user, document_id: int) -> tuple[Document | None, str]:
    doc = visible_documents(user).filter(pk=document_id, status=Document.Status.READY).first()
    if doc is None:  # không tồn tại HOẶC không có quyền: cùng một thông báo, không lộ sự tồn tại
        return None, ""
    text = "\n\n".join(doc.chunks.order_by("index").values_list("text", flat=True))
    return doc, text[:MAX_DOC_CHARS]


def build_tools(user, session_id: int | None = None):
    @tool(response_format="content_and_artifact")
    def search_docs(query: str) -> tuple[str, list]:
        """Tìm đoạn liên quan trong tài liệu nội bộ mà người dùng được phép xem.
        Dùng đầu tiên cho mọi câu hỏi về nội dung tài liệu. Trả về các đoạn kèm document_id."""
        results = search(user, query, k=5)
        if not results:
            return NO_RESULTS, []
        lines = [
            f"[{i}] (document_id={r.source_ref['document_id']}, "
            f"title={r.source_ref['title']}) {r.chunk.text[:500]}"
            for i, r in enumerate(results, start=1)
        ]
        return "\n".join(lines), [r.source_ref for r in results]

    @tool
    def read_doc(document_id: int) -> str:
        """Đọc toàn văn một tài liệu theo document_id (lấy từ search_docs).
        Dùng khi cần chi tiết hơn các đoạn trích."""
        doc, text = _doc_text(user, document_id)
        return f"# {doc.title}\n{text}" if doc else NO_RESULTS

    @tool
    def summarize(document_id: int) -> str:
        """Tóm tắt một tài liệu theo document_id. Dùng khi người dùng muốn bản tóm tắt."""
        doc, text = _doc_text(user, document_id)
        if not doc:
            return NO_RESULTS
        msg = get_chat_model().invoke(
            [HumanMessage(content=f"Tóm tắt ngắn gọn tài liệu sau bằng tiếng Việt:\n\n{text}")]
        )
        return str(msg.content)

    @tool
    def create_ticket(title: str, body: str) -> str:
        """Tạo ticket hỗ trợ. CÓ TÁC DỤNG PHỤ nên người dùng sẽ phải xác nhận trước khi chạy."""
        raise RuntimeError("create_ticket chỉ được chạy qua execute_action sau khi được duyệt")

    return [search_docs, read_doc, summarize, create_ticket]


def execute_action(user, session_id: int | None, tool_call_id: str, name: str, args: dict) -> str:
    """Chỗ DUY NHẤT thực thi tool hành động; chỉ node `tools` gọi, sau khi được duyệt."""
    if name != "create_ticket":
        raise ValueError(name)
    ticket, _ = Ticket.objects.get_or_create(
        session_id=session_id,
        tool_call_id=tool_call_id,
        defaults={"title": args["title"], "body": args.get("body", ""), "created_by": user},
    )
    return f"Đã tạo ticket #{ticket.pk}: {ticket.title}"
