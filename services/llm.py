"""Mọi lời gọi LLM đi qua đây. Test/dev offline dùng FakeChatModel."""

import os
import re
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

NO_ANSWER = "Tôi không tìm thấy thông tin này trong tài liệu được phép truy cập."


class FakeChatModel(BaseChatModel):
    """Hai chế độ:
    - `script` (test): trả lần lượt các AIMessage dựng sẵn (kể cả tool_calls) -> kiểm soát agent.
    - không script (dev offline): "extractive" — trích đoạn ngữ cảnh khớp nhất, kèm [n].
    """

    script: list[AIMessage] = []
    calls: list[Any] = []

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):
        return self  # kịch bản đã chứa sẵn tool_calls

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kw):
        self.calls.append(messages)
        if self.script:
            msg = self.script.pop(0)
        else:
            msg = AIMessage(content=self._extractive(messages))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @staticmethod
    def _extractive(messages: list[BaseMessage]) -> str:
        text = "\n".join(str(m.content) for m in messages)
        question = str(messages[-1].content).lower()
        ctx = re.findall(r"^\[(\d+)\] (.*)$", text, flags=re.MULTILINE)
        q = set(re.findall(r"\w+", question))
        best, best_n = None, 0
        for n, body in ctx:
            overlap = len(q & set(re.findall(r"\w+", body.lower())))
            if overlap > best_n:
                best, best_n = (n, body), overlap
        return f"{best[1]} [{best[0]}]" if best else NO_ANSWER


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
