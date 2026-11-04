import asyncio

import pytest
from django.core.files.base import ContentFile
from rest_framework.authtoken.models import Token

from apps.documents.models import Document
from apps.documents.services.ingest import ingest
from mcp_server import core


@pytest.fixture
def docs(hr_user):
    d = Document.objects.create(
        title="Luong", owner=hr_user, department=hr_user.department, visibility="department"
    )
    d.file.save("l.md", ContentFile(b"Bang luong bi mat"), save=True)
    ingest(d.pk)
    return d


def test_token_auth(hr_user):
    t = Token.objects.create(user=hr_user)
    assert core.user_from_token(t.key) == hr_user
    with pytest.raises(core.AuthError):
        core.user_from_token("bad")
    with pytest.raises(core.AuthError):
        core.user_from_token(None)
    assert core.token_from_headers({"authorization": "Bearer abc"}) == "abc"
    assert core.token_from_headers({}) is None


@pytest.mark.django_db(transaction=True)
def test_search_and_read_respect_department(docs, hr_user, eng_user):
    assert "document_id=" in core.search_docs(hr_user, "bang luong")
    assert "Không có kết quả" in core.search_docs(eng_user, "bang luong")
    assert "bi mat" in core.read_doc(hr_user, docs.pk)
    with pytest.raises(ValueError):
        core.read_doc(eng_user, docs.pk)


@pytest.mark.django_db(transaction=True)
def test_protocol_level_tools_and_resource(docs, hr_user, eng_user, monkeypatch):
    """Gọi qua MCPServer (đường đi thật của giao thức), token lấy từ biến môi trường."""
    from mcp_server.server import mcp

    async def go(token):
        monkeypatch.setenv("MCP_API_TOKEN", token)
        tools = {t.name for t in (await mcp.list_tools())}
        out = await mcp.call_tool("search_docs", {"query": "bang luong", "k": 3})
        return tools, out

    tools, out = asyncio.run(go(Token.objects.create(user=hr_user).key))
    assert {"search_docs", "read_doc"} <= tools
    assert "Luong" in str(out)
    _, out2 = asyncio.run(go(Token.objects.create(user=eng_user).key))
    assert "Luong" not in str(out2)
