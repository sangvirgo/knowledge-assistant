import pytest
from django.core.files.base import ContentFile

from apps.documents.models import Document
from apps.documents.services.access import visible_documents


def make_doc(owner, dept, visibility, title="t"):
    d = Document.objects.create(title=title, owner=owner, department=dept, visibility=visibility)
    d.file.save("a.txt", ContentFile(b"x"), save=True)
    return d


@pytest.mark.django_db
def test_department_isolation(hr_user, eng_user, admin_user, depts):
    hr, eng = depts
    hr_doc = make_doc(hr_user, hr, "department", "hr-only")
    pub = make_doc(hr_user, hr, "company", "public")
    assert set(visible_documents(hr_user)) == {hr_doc, pub}
    assert set(visible_documents(eng_user)) == {pub}
    assert set(visible_documents(admin_user)) == {hr_doc, pub}


@pytest.mark.django_db
def test_user_without_department_sees_only_company(db, depts, hr_user):
    from apps.accounts.models import User

    u = User.objects.create_user("nodept", password="x")
    make_doc(hr_user, depts[0], "department")
    pub = make_doc(hr_user, depts[0], "company")
    assert set(visible_documents(u)) == {pub}
