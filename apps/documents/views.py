from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.exceptions import PermissionDenied

from .serializers import DocumentSerializer
from .services.access import visible_documents
from .tasks import ingest_document


class DocumentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return visible_documents(self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        user = self.request.user
        doc = serializer.save(owner=user, department=user.department)
        if not serializer.validated_data.get("title"):
            doc.title = doc.file.name
        transaction.on_commit(lambda: ingest_document.delay(doc.pk))

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.owner_id != user.id and not user.is_company_admin:
            raise PermissionDenied("Chỉ chủ sở hữu hoặc admin được xoá.")
        instance.delete()
