"""Mọi lời gọi embedding đi qua đây để test thay bằng bản giả (không gọi dịch vụ ngoài)."""

import hashlib
import math
import os
import re
from typing import Protocol

from apps.documents.models import EMBEDDING_DIM


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FakeEmbedder:
    """Hashing trick trên từ: tất định, không mạng, và các câu chung từ thì gần nhau.

    Đủ để test retrieval có "ngữ nghĩa thô"; KHÔNG dùng cho chất lượng thật.
    """

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * EMBEDDING_DIM
        for tok in re.findall(r"\w+", text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % EMBEDDING_DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts):
        return [self._one(t) for t in texts]

    def embed_query(self, text):
        return self._one(text)


class OpenAICompatEmbedder:
    def __init__(self):
        from langchain_openai import OpenAIEmbeddings

        self._e = OpenAIEmbeddings(
            model=os.environ["EMBEDDING_MODEL"],
            api_key=os.environ["EMBEDDING_API_KEY"],
            base_url=os.environ.get("EMBEDDING_BASE_URL") or None,
            dimensions=EMBEDDING_DIM,
        )

    def embed_documents(self, texts):
        return self._e.embed_documents(texts)

    def embed_query(self, text):
        return self._e.embed_query(text)


_override: Embedder | None = None


def set_embedder(e: Embedder | None) -> None:
    """Test hook."""
    global _override
    _override = e


def get_embedder() -> Embedder:
    if _override is not None:
        return _override
    if os.environ.get("EMBEDDING_API_KEY") and os.environ.get("EMBEDDING_MODEL"):
        return OpenAICompatEmbedder()
    return FakeEmbedder()
