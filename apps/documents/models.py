from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField

EMBEDDING_DIM = 1536  # đổi model embedding khác chiều => cần migration mới


class Document(models.Model):
    class Visibility(models.TextChoices):
        DEPARTMENT = "department"
        COMPANY = "company"

    class Status(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    department = models.ForeignKey(
        "accounts.Department", null=True, blank=True, on_delete=models.SET_NULL
    )
    visibility = models.CharField(
        max_length=12, choices=Visibility.choices, default=Visibility.DEPARTMENT
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    status_detail = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    index = models.PositiveIntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=EMBEDDING_DIM)
    search_vector = SearchVectorField(null=True)
    metadata = models.JSONField(default=dict, blank=True)
    token_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "index"], name="uniq_chunk")]
        indexes = [
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            GinIndex(fields=["search_vector"], name="chunk_search_gin"),
        ]
