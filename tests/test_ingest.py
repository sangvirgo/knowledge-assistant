import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.documents.models import Chunk, Document
from apps.documents.services.ingest import ingest

MD = b"# Nghi phep\nNhan vien duoc 12 ngay phep moi nam.\n# Bao hiem\nBao hiem y te toan phan."


def upload(user, name="a.md", content=MD):
    c = APIClient()
    c.force_authenticate(user)
    return c, c.post(
        "/api/documents/",
        {"title": "t", "file": SimpleUploadedFile(name, content)},
        format="multipart",
    )


@pytest.mark.django_db(transaction=True)
def test_upload_creates_chunks_and_vectors(hr_user):
    _, r = upload(hr_user)
    assert r.status_code == 201
    doc = Document.objects.get()
    assert doc.status == "ready" and doc.department == hr_user.department
    assert doc.chunks.count() == 2
    ch = doc.chunks.first()
    assert len(ch.embedding) == 1536 and ch.search_vector


@pytest.mark.django_db(transaction=True)
def test_ingest_is_idempotent(hr_user):
    upload(hr_user)
    doc = Document.objects.get()
    ingest(doc.pk)
    ingest(doc.pk)
    assert Chunk.objects.filter(document=doc).count() == 2


@pytest.mark.django_db(transaction=True)
def test_duplicate_content_rejected(hr_user):
    upload(hr_user)
    upload(hr_user, name="b.md")
    assert Document.objects.get(file__endswith="b.md").status == "failed"


@pytest.mark.django_db(transaction=True)
def test_bad_extension_rejected(hr_user):
    _, r = upload(hr_user, name="x.exe")
    assert r.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_other_department_cannot_see_or_delete(hr_user, eng_user):
    c, _ = upload(hr_user)
    doc = Document.objects.get()
    c2 = APIClient()
    c2.force_authenticate(eng_user)
    assert c2.get("/api/documents/").json() == []
    assert c2.delete(f"/api/documents/{doc.pk}/").status_code == 404
