"""Logic của MCP server, tách khỏi giao thức để test được.

Quyền: KHÔNG có truy vấn tài liệu nào ở đây ngoài `retrieval.search` và `visible_documents`
(cùng quy tắc với UI và agent).
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from rest_framework.authtoken.models import Token  # noqa: E402

from apps.documents.models import Document  # noqa: E402
from apps.documents.services.access import visible_documents  # noqa: E402
from apps.retrieval.services import search  # noqa: E402

MAX_K = 20
MAX_DOC_CHARS = 20000


class AuthError(Exception):
    pass


def user_from_token(key: str | None):
    """Token DRF -> User. Sai/thiếu => AuthError (không lộ lý do chi tiết)."""
    if not key:
        raise AuthError(
            "Thiếu token. Đặt MCP_API_TOKEN hoặc gửi header Authorization: Bearer <token>."
        )
    try:
        return Token.objects.select_related("user").get(key=key).user
    except Token.DoesNotExist:
        raise AuthError("Token không hợp lệ.") from None


def token_from_headers(headers) -> str | None:
    auth = (headers or {}).get("authorization", "")
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() in ("bearer", "token"):
        return parts[1].strip()
    return None


def search_docs(user, query: str, k: int = 5) -> str:
    k = max(1, min(k, MAX_K))
    results = search(user, query, k=k)
    if not results:
        return "Không có kết quả trong các tài liệu bạn được phép truy cập."
    lines = []
    for i, r in enumerate(results, start=1):
        s = r.source_ref
        snippet = " ".join(s["snippet"].split())[:240]
        lines.append(
            f"[{i}] document_id={s['document_id']} | {s['title']} | đoạn {s['chunk_index']}"
            f"\n    {snippet}"
        )
    return "\n".join(lines)


def read_doc(user, document_id: int) -> str:
    doc = visible_documents(user).filter(pk=document_id, status=Document.Status.READY).first()
    if doc is None:  # không tồn tại và không có quyền => cùng một thông báo
        raise ValueError(f"Không tìm thấy tài liệu {document_id} (hoặc bạn không có quyền xem).")
    text = "\n\n".join(doc.chunks.order_by("index").values_list("text", flat=True))
    suffix = "\n\n[...đã cắt bớt]" if len(text) > MAX_DOC_CHARS else ""
    return f"# {doc.title}\n\n{text[:MAX_DOC_CHARS]}{suffix}"
