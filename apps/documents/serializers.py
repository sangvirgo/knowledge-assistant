from rest_framework import serializers

from .models import Document

ALLOWED_EXT = (".pdf", ".md", ".markdown", ".txt")


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "file",
            "department",
            "visibility",
            "status",
            "status_detail",
            "created_at",
        ]
        read_only_fields = ["status", "status_detail", "created_at", "department"]

    def validate_file(self, f):
        if not f.name.lower().endswith(ALLOWED_EXT):
            raise serializers.ValidationError("Chỉ hỗ trợ PDF, MD, TXT.")
        return f
