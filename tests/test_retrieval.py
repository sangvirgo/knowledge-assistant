import itertools

import pytest
from django.core.files.base import ContentFile

from apps.documents.models import Document
from apps.documents.services.ingest import ingest
from apps.retrieval.services import search
from apps.retrieval.services.fusion import rrf


def add(owner, dept, visibility, title, text):
    d = Document.objects.create(title=title, owner=owner, department=dept, visibility=visibility)
    d.file.save(f"{title}.txt", ContentFile(text.encode()), save=True)
    ingest(d.pk)
    return d


def test_rrf_prefers_items_high_in_both_lists():
    s = rrf([[1, 2, 3], [3, 1, 2]])
    assert max(s, key=s.get) == 1 or max(s, key=s.get) == 3
    assert s[1] > s[2]


@pytest.fixture
def corpus(hr_user, eng_user, depts):
    hr, eng = depts
    salary = add(hr_user, hr, "department", "salary", "Bang luong bi mat cua phong nhan su")
    leave = add(hr_user, hr, "company", "leave", "Quy dinh nghi phep nam cho moi nhan vien")
    deploy = add(eng_user, eng, "department", "deploy", "Quy trinh deploy len production")
    return salary, leave, deploy


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "flags",
    [
        dict(zip(("use_vector", "use_keyword", "use_rerank"), f, strict=True))
        for f in itertools.product([True, False], repeat=3)
        if f[0] or f[1]
    ],
)
def test_forbidden_chunks_never_returned(corpus, eng_user, flags):
    salary, leave, deploy = corpus
    res = search(eng_user, "bang luong bi mat phong nhan su", k=10, **flags)
    ids = {r.chunk.document_id for r in res}
    assert salary.pk not in ids
    assert ids <= {leave.pk, deploy.pk}


@pytest.mark.django_db(transaction=True)
def test_owner_department_sees_it(corpus, hr_user):
    salary, *_ = corpus
    res = search(hr_user, "bang luong bi mat", k=3)
    assert res[0].chunk.document_id == salary.pk
    assert res[0].source_ref["title"] == "salary"


@pytest.mark.django_db(transaction=True)
def test_keyword_only_finds_exact_term(corpus, hr_user):
    _, _, deploy = corpus
    from apps.accounts.models import User

    admin = User.objects.create_user("a", password="x", role="admin")
    res = search(admin, "production", use_vector=False, use_rerank=False)
    assert res[0].chunk.document_id == deploy.pk


@pytest.mark.django_db(transaction=True)
def test_not_ready_documents_excluded(corpus, hr_user):
    salary, *_ = corpus
    Document.objects.filter(pk=salary.pk).update(status="failed")
    assert not [r for r in search(hr_user, "bang luong") if r.chunk.document_id == salary.pk]
