import json

import pytest
from django.core.files.base import ContentFile
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from rest_framework.test import APIClient

from apps.agent.models import PendingAction, Ticket
from apps.agent.services.checkpoint import set_checkpointer
from apps.agent.services.graph import MAX_STEPS
from apps.documents.models import Document
from apps.documents.services.ingest import ingest
from services.llm import NO_ANSWER, FakeChatModel, set_chat_model


def call(name, args, cid):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": cid}])


@pytest.fixture(autouse=True)
def memory_checkpointer():
    set_checkpointer(InMemorySaver())
    yield
    set_checkpointer(None)
    set_chat_model(None)


def script(*msgs):
    m = FakeChatModel(script=list(msgs), calls=[])
    set_chat_model(m)
    return m


def add_doc(owner, dept, vis, text, title="Nghi phep"):
    d = Document.objects.create(title=title, owner=owner, department=dept, visibility=vis)
    d.file.save("p.md", ContentFile(text.encode()), save=True)
    ingest(d.pk)
    return d


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.mark.django_db(transaction=True)
def test_search_then_answer_with_sources(hr_user):
    add_doc(hr_user, hr_user.department, "department", "Nhan vien co 12 ngay phep nam")
    script(
        call("search_docs", {"query": "ngay phep"}, "c1"), AIMessage(content="Có 12 ngày phép [1].")
    )
    r = (
        client(hr_user)
        .post("/api/agent/ask", {"question": "bao nhieu ngay phep"}, format="json")
        .json()
    )
    assert r["answer"] == "Có 12 ngày phép [1]."
    assert r["sources"][0]["title"] == "Nghi phep"


@pytest.mark.django_db(transaction=True)
def test_guard_rejects_answer_without_evidence(hr_user):
    script(AIMessage(content="Chắc là 20 ngày."))  # LLM bịa, không gọi tool
    r = client(hr_user).post("/api/agent/ask", {"question": "bao nhieu ngay"}, format="json")
    assert r.json()["answer"] == NO_ANSWER


@pytest.mark.django_db(transaction=True)
def test_agent_cannot_read_other_department_doc(hr_user, eng_user):
    secret = add_doc(hr_user, hr_user.department, "department", "luong bi mat", "luong")
    script(call("read_doc", {"document_id": secret.pk}, "c1"), AIMessage(content="Lương là 1 tỷ."))
    r = (
        client(eng_user)
        .post("/api/agent/ask", {"question": "doc tai lieu luong"}, format="json")
        .json()
    )
    assert r["answer"] == NO_ANSWER and r["sources"] == []


@pytest.mark.django_db(transaction=True)
def test_agent_search_respects_permissions(hr_user, eng_user):
    add_doc(hr_user, hr_user.department, "department", "luong bi mat")
    m = script(call("search_docs", {"query": "luong bi mat"}, "c1"), AIMessage(content="x"))
    client(eng_user).post("/api/agent/ask", {"question": "luong"}, format="json")
    tool_outputs = [msg.content for msg in m.calls[1] if getattr(msg, "type", "") == "tool"]
    assert tool_outputs == ["NO_RESULTS"]


@pytest.mark.django_db(transaction=True)
def test_create_ticket_requires_approval(hr_user):
    add_doc(hr_user, hr_user.department, "department", "Quy trinh xin thiet bi")
    script(
        call("search_docs", {"query": "thiet bi"}, "c1"),
        call("create_ticket", {"title": "Xin laptop", "body": "can laptop"}, "c2"),
        AIMessage(content="Đã tạo ticket."),
    )
    c = client(hr_user)
    r = c.post("/api/agent/ask", {"question": "xin laptop"}, format="json").json()
    assert r["pending_action"]["tool"] == "create_ticket"
    assert Ticket.objects.count() == 0  # CHƯA chạy khi chưa duyệt
    aid = r["pending_action"]["action_id"]
    r2 = c.post(f"/api/actions/{aid}/approve").json()
    assert Ticket.objects.count() == 1 and r2["answer"] == "Đã tạo ticket."
    assert PendingAction.objects.get(pk=aid).status == "approved"
    assert c.post(f"/api/actions/{aid}/approve").status_code == 409  # không duyệt hai lần
    assert Ticket.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_reject_does_not_create_ticket(hr_user):
    script(
        call("create_ticket", {"title": "t", "body": "b"}, "c1"),
        AIMessage(content="Đã huỷ theo yêu cầu."),
    )
    c = client(hr_user)
    aid = c.post("/api/agent/ask", {"question": "tao ticket"}, format="json").json()[
        "pending_action"
    ]["action_id"]
    c.post(f"/api/actions/{aid}/reject")
    assert Ticket.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_only_owner_can_approve(hr_user, eng_user):
    script(call("create_ticket", {"title": "t", "body": "b"}, "c1"))
    aid = (
        client(hr_user)
        .post("/api/agent/ask", {"question": "ticket"}, format="json")
        .json()["pending_action"]["action_id"]
    )
    assert client(eng_user).post(f"/api/actions/{aid}/approve").status_code == 404
    assert Ticket.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_step_limit(hr_user):
    add_doc(hr_user, hr_user.department, "department", "noi dung")
    # LLM cứ gọi tool mãi; sau MAX_STEPS bước đồ thị phải dừng và trả lời.
    loop = [call("search_docs", {"query": "noi dung"}, f"c{i}") for i in range(20)]
    m = script(*loop, AIMessage(content="Trả lời bằng thông tin hiện có."))
    r = client(hr_user).post("/api/agent/ask", {"question": "lap"}, format="json").json()
    assert len(m.calls) == MAX_STEPS + 1
    assert r["answer"]


@pytest.mark.django_db(transaction=True)
def test_memory_across_turns(hr_user):
    m = script(AIMessage(content="một"), AIMessage(content="hai"))
    c = client(hr_user)
    sid = c.post("/api/agent/ask", {"question": "q1"}, format="json").json()["session_id"]
    c.post("/api/agent/ask", {"question": "q2", "session_id": sid}, format="json")
    humans = [x.content for x in m.calls[1] if x.type == "human"]
    assert humans == ["q1", "q2"]


@pytest.mark.django_db(transaction=True)
def test_sse_stream(hr_user):
    add_doc(hr_user, hr_user.department, "department", "Nhan vien co 12 ngay phep")
    script(call("search_docs", {"query": "phep"}, "c1"), AIMessage(content="12 ngày [1]"))
    r = client(hr_user).post("/api/agent/ask?stream=1", {"question": "phep"}, format="json")
    assert r["Content-Type"].startswith("text/event-stream")
    body = b"".join(r.streaming_content).decode()
    events = [line[7:] for line in body.splitlines() if line.startswith("event: ")]
    assert events[0] == "session" and "tool_call" in events and events[-1] == "done"
    done = [json.loads(b[6:]) for b in body.splitlines() if b.startswith("data: ")][-1]
    assert done["answer"] == "12 ngày [1]"


@pytest.mark.django_db(transaction=True)
def test_every_request_has_trace_and_json_log(hr_user, caplog):
    import logging

    script(AIMessage(content="x"))
    with caplog.at_level(logging.INFO, logger="ka.request"):
        r = client(hr_user).post("/api/agent/ask", {"question": "q"}, format="json").json()
    rec = json.loads(caplog.records[-1].getMessage())
    assert r["trace_id"] == rec["trace_id"] and rec["latency_ms"] >= 0 and rec["steps"]


@pytest.mark.django_db(transaction=True)
def test_ask_has_trace(hr_user):
    r = client(hr_user).post("/api/ask", {"question": "hello"}, format="json").json()
    assert len(r["trace_id"]) == 32
