"""Mọi lời gọi LLM đi qua đây. Test/dev offline dùng FakeChatModel."""

import os
import re
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

NO_ANSWER = "Tôi không tìm thấy thông tin này trong tài liệu được phép truy cập."


class FakeChatModel(BaseChatModel):
    """Hai chế độ:
    - `script` (test): trả lần lượt các AIMessage dựng sẵn (kể cả tool_calls) -> kiểm soát agent.
    - không script (dev offline): "extractive" — trích đoạn ngữ cảnh khớp nhất, kèm [n].
    """

    script: list[AIMessage] = []
    calls: list[Any] = []
    agentic: bool = False  # có tool gắn vào => hành xử như agent đơn giản

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):
        # Giữ chung `script`/`calls` (shallow copy) để test vẫn quan sát được.
        return self.model_copy(update={"agentic": True})

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kw):
        self.calls.append(messages)
        if self.script:
            msg = self.script.pop(0)
        elif self.agentic and not isinstance(messages[-1], ToolMessage):
            # dev offline: luôn tìm trước (search_docs) bằng chính câu hỏi
            q = next(m.content for m in reversed(messages) if isinstance(m, HumanMessage))
            msg = AIMessage(
                content="",
                tool_calls=[{"name": "search_docs", "args": {"query": q}, "id": uuid4().hex}],
            )
        else:
            msg = AIMessage(content=self._extractive(messages))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @staticmethod
    def _extractive(messages: list[BaseMessage]) -> str:
        text = "\n".join(str(m.content) for m in messages)
        question = next(
            (str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)), ""
        ).lower()
        ctx = re.findall(r"^\[(\d+)\] (.*)$", text, flags=re.MULTILINE)
        q = set(re.findall(r"\w+", question))
        best, best_n = None, 0
        for n, body in ctx:
            overlap = len(q & set(re.findall(r"\w+", body.lower())))
            if overlap > best_n:
                best, best_n = (n, body), overlap
        if not best:
            return NO_ANSWER
        body = re.sub(r"^\(document_id=.*?\) ", "", best[1])  # bỏ tiền tố của search_docs
        return f"{body} [{best[0]}]"


_override: BaseChatModel | None = None


def set_chat_model(m: BaseChatModel | None) -> None:
    """Test hook."""
    global _override
    _override = m


def get_chat_model() -> BaseChatModel:
    if _override is not None:
        return _override
    if os.environ.get("LLM_API_KEY") and os.environ.get("LLM_MODEL"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.environ["LLM_MODEL"],
            api_key=os.environ["LLM_API_KEY"],
            base_url=os.environ.get("LLM_BASE_URL") or None,
            temperature=0,
        )
    return FakeChatModel()
