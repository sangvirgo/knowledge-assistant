from celery import shared_task

from .services.ingest import ingest


@shared_task
def ingest_document(document_id: int) -> None:
    ingest(document_id)
