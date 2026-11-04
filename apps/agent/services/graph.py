r"""Đồ thị LangGraph của agent.

        START -> agent --(có tool_calls & còn bước)--> tools --> agent
                   \--(không)--> guard -> END

- agent : LLM + tools tự quyết định gọi tool nào (đóng vai router).
- tools : chạy tool đọc ngay; tool HÀNH ĐỘNG dừng đồ thị bằng interrupt() chờ người dùng duyệt.
- guard : chặn câu trả lời không có bằng chứng (chống bịa).
"""

import threading
from typing import Annotated, TypedDict

from django.db import connection
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from services.llm import NO_ANSWER, get_chat_model

from .tools import ACTION_TOOLS, EVIDENCE_TOOLS, NO_RESULTS, build_tools, execute_action

MAX_STEPS = 6

SYSTEM = (
    "Bạn là agent tra cứu tài liệu nội bộ. Dùng search_docs để tìm thông tin, read_doc/summarize "
    "khi cần. Chỉ trả lời dựa trên kết quả tool và trích dẫn [n] hoặc tên tài liệu. "
    f'Nếu không có thông tin, trả lời: "{NO_ANSWER}". Muốn tạo ticket thì gọi create_ticket.'
)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    session_id: int
    user_id: int
    steps: int  # số lần gọi LLM trong LƯỢT hiện tại (được reset mỗi lượt)


def current_turn(messages: list) -> list:
    """Các message từ HumanMessage cuối cùng trở đi."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i:]
    return messages


def build_graph(user, session_id: int, checkpointer):
    tools = build_tools(user, session_id)
    request_thread = threading.get_ident()
    by_name = {t.name: t for t in tools}

    def agent(state: AgentState):
        model = get_chat_model()
        if state["steps"] >= MAX_STEPS:
            # Hết ngân sách bước: KHÔNG gắn tool nữa => buộc trả lời bằng thông tin hiện có.
            msgs = [
                SystemMessage(content=SYSTEM + " Đã hết số bước: hãy trả lời bằng thông tin đã có.")
            ]
            reply = model.invoke(msgs + state["messages"])
            if getattr(reply, "tool_calls", None):
                reply = AIMessage(content=reply.content or NO_ANSWER, id=reply.id)
        else:
            reply = model.bind_tools(tools).invoke(
                [SystemMessage(content=SYSTEM)] + state["messages"]
            )
        return {"messages": [reply], "steps": state["steps"] + 1}

    def route(state: AgentState):
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None)
        return "tools" if calls and state["steps"] <= MAX_STEPS else "guard"

    def tools_node(state: AgentState):
        try:
            return _run_tools(state)
        finally:
            # LangGraph có thể chạy node trong thread phụ; Django cấp connection riêng cho mỗi
            # thread và không tự đóng => đóng ở đây để không rò connection.
            if threading.get_ident() != request_thread:
                connection.close()

    def _run_tools(state: AgentState):
        out = []
        for call in state["messages"][-1].tool_calls:
            name, args, cid = call["name"], call["args"], call["id"]
            if name in ACTION_TOOLS:
                # interrupt() dừng đồ thị; lần resume trả về quyết định của người dùng.
                decision = interrupt({"tool": name, "args": args, "tool_call_id": cid})
                if decision.get("decision") == "approve":
                    content = execute_action(user, session_id, cid, name, args)
                else:
                    content = "Người dùng đã từ chối thao tác này."
                out.append(ToolMessage(content=content, tool_call_id=cid, name=name))
            elif name in by_name:
                msg = by_name[name].invoke(call)  # ToolMessage (kèm artifact nếu có)
                out.append(msg)
            else:
                out.append(ToolMessage(content="Tool không tồn tại.", tool_call_id=cid, name=name))
        return {"messages": out}

    def guard(state: AgentState):
        turn = current_turn(state["messages"])
        has_evidence = any(
            isinstance(m, ToolMessage)
            and m.name in (EVIDENCE_TOOLS | ACTION_TOOLS)
            and m.content != NO_RESULTS
            for m in turn
        )
        last = state["messages"][-1]
        if has_evidence or not isinstance(last, AIMessage):
            return {}
        return {"messages": [AIMessage(content=NO_ANSWER, id=last.id)]}  # cùng id => thay thế

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("tools", tools_node)
    g.add_node("guard", guard)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", "guard": "guard"})
    g.add_edge("tools", "agent")
    g.add_edge("guard", END)
    return g.compile(checkpointer=checkpointer)
