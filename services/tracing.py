"""Quan sát: mỗi request có trace_id, log JSON (độ trễ từng bước, token, chi phí ước tính),
và (nếu cấu hình LANGFUSE_*) đẩy trace lên Langfuse.

TẠI SAO tự viết callback thay vì CallbackHandler của Langfuse? SDK Langfuse 2.x đòi `langchain<1`,
mâu thuẫn với langchain-core 1.x đang dùng. Callback này chỉ phụ thuộc langchain-core, và gửi
lên Langfuse qua client cấp thấp. Tracing lỗi KHÔNG bao giờ được làm hỏng request.
"""

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

from langchain_core.callbacks import BaseCallbackHandler

log = logging.getLogger("ka.request")
_lf = None


def _langfuse():
    global _lf
    if _lf is None and os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_HOST"):
        from langfuse import Langfuse

        _lf = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
            host=os.environ["LANGFUSE_HOST"],
        )
    return _lf


def _now():
    return datetime.now(UTC)


class RequestTracer(BaseCallbackHandler):
    def __init__(self, name: str, user_id, session_id=None, question: str = ""):
        self.name, self.user_id, self.session_id = name, user_id, session_id
        self.trace_id = uuid.uuid4().hex
        self.t0 = time.perf_counter()
        self.tokens_in = self.tokens_out = 0
        self.steps: list[dict] = []
        self.output = ""  # người gọi gán câu trả lời cuối
        self._open: dict = {}
        self._trace = None
        try:
            lf = _langfuse()
            if lf:
                self._trace = lf.trace(
                    id=self.trace_id,
                    name=name,
                    user_id=str(user_id),
                    session_id=str(session_id) if session_id else None,
                    input=question,
                )
        except Exception:  # noqa: BLE001
            log.exception("langfuse trace init failed")

    @property
    def config(self) -> dict:
        return {"callbacks": [self]}

    # --- LLM ---
    def on_chat_model_start(self, serialized, messages, *, run_id, **kw):
        self._open[run_id] = ("llm", time.perf_counter(), _now())

    on_llm_start = lambda self, s, p, *, run_id, **kw: self._open.__setitem__(  # noqa: E731
        run_id, ("llm", time.perf_counter(), _now())
    )

    def on_llm_end(self, response, *, run_id, **kw):
        kind, t, started = self._open.pop(run_id, ("llm", time.perf_counter(), _now()))
        usage = {}
        try:
            msg = response.generations[0][0].message
            usage = getattr(msg, "usage_metadata", None) or {}
        except Exception:  # noqa: BLE001
            pass
        tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        self.tokens_in += tin
        self.tokens_out += tout
        ms = (time.perf_counter() - t) * 1000
        self.steps.append({"step": "llm", "ms": round(ms, 1), "in": tin, "out": tout})
        self._lf(
            "generation",
            name="llm",
            start_time=started,
            end_time=_now(),
            usage_details={"input": tin, "output": tout},
        )

    # --- Tools ---
    def on_tool_start(self, serialized, input_str, *, run_id, **kw):
        self._open[run_id] = (
            (serialized or {}).get("name") or kw.get("name") or "tool",
            time.perf_counter(),
            _now(),
        )

    def on_tool_end(self, output, *, run_id, **kw):
        name, t, started = self._open.pop(run_id, ("tool", time.perf_counter(), _now()))
        ms = (time.perf_counter() - t) * 1000
        self.steps.append({"step": f"tool:{name}", "ms": round(ms, 1)})
        self._lf("span", name=f"tool:{name}", start_time=started, end_time=_now())

    def _lf(self, kind: str, **kw):
        if self._trace is None:
            return
        try:
            getattr(self._trace, kind)(**kw)
        except Exception:  # noqa: BLE001
            log.exception("langfuse event failed")

    def finish(self) -> dict:
        total_ms = (time.perf_counter() - self.t0) * 1000
        price_in = float(os.environ.get("LLM_PRICE_IN_PER_1M", 0))
        price_out = float(os.environ.get("LLM_PRICE_OUT_PER_1M", 0))
        cost = (self.tokens_in * price_in + self.tokens_out * price_out) / 1_000_000
        rec = {
            "trace_id": self.trace_id,
            "name": self.name,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "latency_ms": round(total_ms, 1),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "est_cost_usd": round(cost, 6),
            "steps": self.steps,
        }
        log.info(json.dumps(rec, ensure_ascii=False))
        try:
            if self._trace is not None:
                self._trace.update(
                    output=output, metadata={"latency_ms": rec["latency_ms"], "est_cost_usd": cost}
                )
                _langfuse().flush()
        except Exception:  # noqa: BLE001
            log.exception("langfuse flush failed")
        return rec


@contextmanager
def trace_request(name: str, user, session_id=None, question: str = ""):
    tracer = RequestTracer(name, user.pk, session_id, question)
    try:
        yield tracer
    finally:
        tracer.finish()
