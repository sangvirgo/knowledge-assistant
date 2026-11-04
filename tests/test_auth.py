import pytest
from django.test import Client


@pytest.mark.django_db
def test_token_endpoint(hr_user):
    r = Client().post("/api/token/", {"username": "hr", "password": "x"})
    assert r.status_code == 200 and r.json()["token"]
