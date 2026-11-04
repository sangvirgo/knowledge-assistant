import pytest

from apps.accounts.models import Department, User


@pytest.fixture
def depts(db):
    return Department.objects.create(name="HR"), Department.objects.create(name="Eng")


@pytest.fixture
def hr_user(depts):
    return User.objects.create_user("hr", password="x", department=depts[0])


@pytest.fixture
def eng_user(depts):
    return User.objects.create_user("eng", password="x", department=depts[1])


@pytest.fixture
def admin_user(depts):
    return User.objects.create_user("boss", password="x", role="admin")
