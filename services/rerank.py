"""Rerank sau một interface để thay được (cross-encoder thật hay bản nhẹ)."""

import os
import re
from typing import Protocol


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class LexicalReranker:
    """Mặc định, không phụ thuộc: tỉ lệ từ truy vấn xuất hiện trong chunk.

    Chỉ là chỗ giữ chỗ hợp lệ để pipeline chạy offline; chất lượng thật cần cross-encoder.
    """

    def score(self, query, texts):
        q = set(re.findall(r"\w+", query.lower()))
        out = []
        for t in texts:
            words = set(re.findall(r"\w+", t.lower()))
            out.append(len(q & words) / (len(q) or 1))
        return out


class CrossEncoderReranker:
    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder  # extra "rerank"

        self._m = CrossEncoder(model_name)

    def score(self, query, texts):
        return [float(s) for s in self._m.predict([(query, t) for t in texts])]


_override: Reranker | None = None
_cached: Reranker | None = None


def set_reranker(r: Reranker | None) -> None:
    global _override
    _override = r


def get_reranker() -> Reranker:
    global _cached
    if _override is not None:
        return _override
    if _cached is None:
        name = os.environ.get("RERANK_MODEL")
        _cached = CrossEncoderReranker(name) if name else LexicalReranker()
    return _cached
