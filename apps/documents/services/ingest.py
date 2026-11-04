import hashlib

from django.contrib.postgres.search import SearchVector
from django.db import transaction

from apps.documents.models import Chunk, Document
from services.embeddings import get_embedder

from .chunking import chunk_segments
from .parsing import parse

FTS_CONFIG = "simple"  # 'simple': không stem theo ngôn ngữ => hợp với tiếng Việt
BATCH = 64


def ingest(document_id: int) -> None:
    doc = Document.objects.get(pk=document_id)
    doc.status, doc.status_detail = Document.Status.PROCESSING, ""
    doc.save(update_fields=["status", "status_detail"])
    try:
        with doc.file.open("rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        dup = (
            Document.objects.filter(content_hash=digest, status=Document.Status.READY)
            .exclude(pk=doc.pk)
            .first()
        )
        if dup:
            doc.content_hash = digest
            doc.status, doc.status_detail = Document.Status.FAILED, f"Trùng nội dung với #{dup.pk}"
            doc.save(update_fields=["status", "status_detail", "content_hash"])
            return

        chunks = chunk_segments(parse(doc.file.path))
        embedder = get_embedder()
        vectors: list[list[float]] = []
        for i in range(0, len(chunks), BATCH):
            batch = chunks[i : i + BATCH]
            # Ghép heading vào văn bản được embed để vector "biết" chunk thuộc mục nào.
            vectors += embedder.embed_documents(
                [f"{c.metadata.get('heading', '')}\n{c.text}".strip() for c in batch]
            )

        # Idempotent: xoá chunk cũ rồi ghi mới trong CÙNG transaction.
        with transaction.atomic():
            doc.chunks.all().delete()
            Chunk.objects.bulk_create(
                Chunk(
                    document=doc,
                    index=i,
                    text=c.text,
                    embedding=v,
                    metadata=c.metadata,
                    token_count=c.token_count,
                )
                for i, (c, v) in enumerate(zip(chunks, vectors, strict=True))
            )
            doc.chunks.update(search_vector=SearchVector("text", config=FTS_CONFIG))
            doc.content_hash, doc.status = digest, Document.Status.READY
            doc.save(update_fields=["content_hash", "status"])
    except Exception as e:  # noqa: BLE001 - ghi lý do cho người dùng, không nuốt im lặng
        Document.objects.filter(pk=document_id).update(
            status=Document.Status.FAILED, status_detail=str(e)[:500]
        )
