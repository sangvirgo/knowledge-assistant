"""RAG: retrieve -> prompt có ngữ cảnh đánh số -> LLM -> chỉ giữ nguồn được trích dẫn."""

import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from apps.chat.models import ChatSession, Message
from apps.retrieval.services import search
from services.llm import NO_ANSWER, get_chat_model
from services.tracing import trace_request

PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Bạn là trợ lý tài liệu nội bộ. Trả lời CHỈ dựa trên NGỮ CẢNH bên dưới. "
            "Mỗi ý phải kèm trích dẫn dạng [n] ứng với đoạn ngữ cảnh. "
            f'Nếu ngữ cảnh không đủ, trả lời đúng câu: "{NO_ANSWER}" và không suy đoán.\n\n'
            "NGỮ CẢNH:\n{context}",
        ),
        ("placeholder", "{history}"),
        ("human", "{question}"),
    ]
)


def _format_context(results) -> str:
    return "\n".join(f"[{i}] {r.chunk.text}" for i, r in enumerate(results, start=1))


def ask(user, question: str, session_id: int | None = None, k: int = 6) -> dict:
    if session_id:
        session = ChatSession.objects.get(pk=session_id, user=user)  # chỉ session của chính mình
    else:
        session = ChatSession.objects.create(user=user, title=question[:80])

    history = [
        (m.role if m.role == "user" else "ai", m.content)
        for m in session.messages.exclude(role="tool").order_by("-id")[:6][::-1]
    ]
    Message.objects.create(session=session, role="user", content=question)

    with trace_request("ask", user, session.pk, question) as tracer:
        answer, sources = _answer(user, question, history, k, tracer)
        tracer.output = answer
    trace_id = tracer.trace_id
    Message.objects.create(
        session=session, role="assistant", content=answer, sources=sources, trace_id=trace_id
    )
    return {"answer": answer, "sources": sources, "trace_id": trace_id, "session_id": session.pk}


def _answer(user, question, history, k, tracer):
    results = search(user, question, k=k)
    if not results:  # không có nguồn => từ chối, không gọi LLM
        answer, sources = NO_ANSWER, []
    else:
        chain = PROMPT | get_chat_model() | StrOutputParser()
        answer = chain.invoke(
            {"context": _format_context(results), "history": history, "question": question},
            config=tracer.config,
        )
        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
        sources = [results[n - 1].source_ref for n in cited if 1 <= n <= len(results)]
        if not sources:  # LLM từ chối hoặc không trích dẫn => không phô nguồn
            answer = NO_ANSWER if NO_ANSWER in answer else answer
    return answer, sources
