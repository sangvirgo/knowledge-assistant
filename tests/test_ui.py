import pytest
from django.test import Client


@pytest.mark.django_db
def test_pages_require_login_and_render(hr_user):
    c = Client()
    assert c.get("/").status_code == 302
    c.force_login(hr_user)
    assert b"log" in c.get("/").content
    assert "Tài liệu" in c.get("/documents/").content.decode()


@pytest.mark.django_db
def test_session_login_can_post_with_csrf(hr_user):
    c = Client(enforce_csrf_checks=True)
    c.force_login(hr_user)
    c.get("/")  # đặt cookie csrf
    tok = c.cookies["csrftoken"].value
    r = c.post(
        "/api/ask", {"question": "hi"}, content_type="application/json", HTTP_X_CSRFTOKEN=tok
    )
    assert r.status_code == 200
