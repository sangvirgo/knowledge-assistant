"""Chạy đồ thị và phát sự kiện (dùng chung cho JSON và SSE)."""

import uuid
from collections.abc import Iterator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from apps.agent.models import PendingAction
from apps.chat.models import ChatSession, Message

from .checkpoint import get_checkpointer
from .graph import build_graph, current_turn


def _config(session_id: int) -> dict:
    # thread_id = session => memory theo hội thoại + resume sau interrupt
    return {"configurable": {"thread_id": f"session-{session_id}"}}


def _drive(user, session: ChatSession, graph_input) -> Iterator[dict]:
    graph = build_graph(user, session.pk, get_checkpointer())
    cfg = _config(session.pk)
    for mode, data in graph.stream(graph_input, cfg, stream_mode=["updates", "messages"]):
        if mode == "messages":
            chunk, meta = data
            if meta.get("langgraph_node") == "agent" and isinstance(chunk.content, str):
                if chunk.content:
                    yield {"event": "token", "data": {"text": chunk.content}}
        elif mode == "updates":
            for node, update in data.items():
                if node == "agent":
                    for call in getattr(update["messages"][-1], "tool_calls", None) or []:
                        yield {
                            "event": "tool_call",
                            "data": {"name": call["name"], "args": call["args"]},
                        }
                elif node == "tools":
                    for m in update["messages"]:
                        yield {
                            "event": "tool_result",
                            "data": {"name": m.name, "content": str(m.content)[:500]},
                        }

    state = graph.get_state(cfg)
    interrupts = [i for t in state.tasks for i in t.interrupts]
    if interrupts:
        payload = interrupts[0].value
        action, _ = PendingAction.objects.get_or_create(
            session=session,
            user=user,
            tool_call_id=payload["tool_call_id"],
            defaults={"tool": payload["tool"], "args": payload["args"]},
        )
        Message.objects.create(
            session=session,
            role="tool",
            content=f"Chờ xác nhận: {action.tool} {action.args}",
        )
        yield {
            "event": "interrupt",
            "data": {"action_id": action.pk, "tool": action.tool, "args": action.args},
        }
        return

    turn = current_turn(state.values["messages"])
    final = next(m for m in reversed(turn) if isinstance(m, AIMessage))
    sources, seen = [], set()
    for m in turn:
        if isinstance(m, ToolMessage) and isinstance(m.artifact, list):
            for s in m.artifact:
                key = (s["document_id"], s["chunk_index"])
                if key not in seen:
                    seen.add(key)
                    sources.append(s)
    trace_id = uuid.uuid4().hex
    Message.objects.create(
        session=session,
        role="assistant",
        content=str(final.content),
        sources=sources,
        trace_id=trace_id,
    )
    yield {
        "event": "done",
        "data": {
            "answer": str(final.content),
            "sources": sources,
            "trace_id": trace_id,
            "session_id": session.pk,
        },
    }


def start_turn(user, question: str, session_id: int | None = None) -> Iterator[dict]:
    # Phần ghi DB chạy NGAY (không lười như generator) để lỗi/404 nổi lên trong view.
    if session_id:
        session = ChatSession.objects.get(pk=session_id, user=user)
    else:
        session = ChatSession.objects.create(user=user, title=question[:80])
    Message.objects.create(session=session, role="user", content=question)
    # steps=0 mỗi lượt: ngân sách bước tính theo lượt, không cộng dồn qua memory.
    graph_input = {
        "messages": [HumanMessage(content=question)],
        "session_id": session.pk,
        "user_id": user.pk,
        "steps": 0,
    }

    def gen():
        yield {"event": "session", "data": {"session_id": session.pk}}
        yield from _drive(user, session, graph_input)

    return gen()


def resolve_action(user, action: PendingAction, approve: bool) -> Iterator[dict]:
    action.status = PendingAction.Status.APPROVED if approve else PendingAction.Status.REJECTED
    action.save(update_fields=["status"])  # đổi trạng thái NGAY, trong khoá của view
    decision = {"decision": "approve" if approve else "reject"}
    return _drive(user, action.session, Command(resume=decision))


def run_to_result(events: Iterator[dict]) -> dict:
    """Dùng cho endpoint JSON: gom sự kiện thành kết quả cuối."""
    result: dict = {"pending_action": None}
    for e in events:
        if e["event"] == "session":
            result["session_id"] = e["data"]["session_id"]
        elif e["event"] == "interrupt":
            result["pending_action"] = e["data"]
        elif e["event"] == "done":
            result.update(e["data"])
    return result
