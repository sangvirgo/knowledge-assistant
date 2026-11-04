"""Quy tắc quyền xem tài liệu: MỘT chỗ duy nhất (UI, agent, MCP đều dùng)."""

from django.db.models import Q

from apps.documents.models import Document


def visible_documents(user):
    """Document mà `user` được xem.

    admin: tất cả; còn lại: tài liệu company + tài liệu cùng phòng ban.
    Trả QuerySet để retrieval nhúng thẳng vào SQL (lọc trước khi xếp hạng).
    """
    if not user.is_authenticated:
        return Document.objects.none()
    if user.is_company_admin:
        return Document.objects.all()
    q = Q(visibility=Document.Visibility.COMPANY)
    if user.department_id:
        q |= Q(department_id=user.department_id)
    return Document.objects.filter(q)
