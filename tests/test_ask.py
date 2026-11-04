import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from apps.documents.models import Document
from apps.documents.services.ingest import ingest
from services.llm import NO_ANSWER


def add(owner, dept, vis, text):
    d = Document.objects.create(title="Chinh sach", owner=owner, department=dept, visibility=vis)
    d.file.save("p.md", ContentFile(text.encode()), save=True)
    ingest(d.pk)


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.mark.django_db(transaction=True)
def test_answer_with_sources(hr_user):
    add(hr_user, hr_user.department, "department", "# Phep\nNhan vien co 12 ngay phep nam.")
    r = client(hr_user).post("/api/ask", {"question": "Co bao nhieu ngay phep nam?"}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert "12 ngay" in body["answer"]
    assert body["sources"][0]["title"] == "Chinh sach" and body["trace_id"]


@pytest.mark.django_db(transaction=True)
def test_refuses_without_sources(hr_user):
    r = client(hr_user).post("/api/ask", {"question": "Gia vang hom nay"}, format="json")
    assert r.json()["answer"] == NO_ANSWER and r.json()["sources"] == []


@pytest.mark.django_db(transaction=True)
def test_irrelevant_context_is_refused_and_no_sources(hr_user):
    add(hr_user, hr_user.department, "department", "Quy trinh deploy production")
    r = client(hr_user).post("/api/ask", {"question": "xyz qwerty"}, format="json")
    assert r.json()["answer"] == NO_ANSWER and r.json()["sources"] == []


@pytest.mark.django_db(transaction=True)
def test_other_department_gets_refusal(hr_user, eng_user):
    add(hr_user, hr_user.department, "department", "Bang luong bi mat")
    r = client(eng_user).post("/api/ask", {"question": "bang luong"}, format="json")
    assert r.json()["sources"] == [] and r.json()["answer"] == NO_ANSWER


@pytest.mark.django_db(transaction=True)
def test_history_and_session_isolation(hr_user, eng_user):
    c = client(hr_user)
    sid = c.post("/api/ask", {"question": "hello"}, format="json").json()["session_id"]
    c.post("/api/ask", {"question": "again", "session_id": sid}, format="json")
    assert len(c.get(f"/api/sessions/{sid}/messages/").json()) == 4
    assert len(c.get("/api/sessions/").json()) == 1
    other = client(eng_user)
    assert other.get(f"/api/sessions/{sid}/messages/").status_code == 404
    assert (
        other.post("/api/ask", {"question": "x", "session_id": sid}, format="json").status_code
        == 404
    )
