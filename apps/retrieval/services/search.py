"""Điểm vào DUY NHẤT để truy vấn tài liệu (UI, agent, MCP đều gọi hàm này)."""

import re
from dataclasses import dataclass

from django.contrib.postgres.search import SearchQuery, SearchRank
from pgvector.django import CosineDistance

from apps.documents.models import Chunk, Document
from apps.documents.services.access import visible_documents
from apps.documents.services.ingest import FTS_CONFIG
from services.embeddings import get_embedder
from services.rerank import get_reranker

from .fusion import rrf

CANDIDATES = 30  # mỗi nhánh lấy top-N; rerank chỉ chấm ~30 để rẻ


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float
    source_ref: dict


def _source_ref(c: Chunk) -> dict:
    return {
        "document_id": c.document_id,
        "title": c.document.title,
        "chunk_index": c.index,
        "snippet": c.text[:300],
        "metadata": c.metadata,
    }


def _allowed_chunks(user):
    """Bước 1 — LỌC QUYỀN TRONG SQL, trước khi xếp hạng.

    TẠI SAO không lọc sau? Lọc sau top-k có thể trả ít/không kết quả (chunk bị cấm chiếm chỗ),
    và rủi ro rò rỉ nếu quên lọc ở một đường nào đó. Đặt ở đây thì mọi nhánh đều an toàn.
    """
    docs = visible_documents(user).filter(status=Document.Status.READY).values("id")
    return Chunk.objects.filter(document_id__in=docs).select_related("document")


def _vector_ids(qs, query: str) -> list[int]:
    qvec = get_embedder().embed_query(query)
    rows = qs.annotate(dist=CosineDistance("embedding", qvec)).order_by("dist")[:CANDIDATES]
    return [c.pk for c in rows]


def _keyword_ids(qs, query: str) -> list[int]:
    # Postgres 'plain' = AND tất cả từ => câu hỏi dài hầu như không khớp. Dùng OR (|)
    # rồi để ts_rank_cd xếp hạng chunk khớp nhiều từ lên đầu (gần BM25 hơn).
    terms = re.findall(r"\w+", query.lower())
    if not terms:
        return []
    q = SearchQuery(" | ".join(terms), config=FTS_CONFIG, search_type="raw")
    rows = (
        qs.filter(search_vector=q)
        .annotate(rank=SearchRank("search_vector", q, cover_density=True))
        .order_by("-rank")[:CANDIDATES]
    )
    return [c.pk for c in rows]


def search(
    user,
    query: str,
    k: int = 8,
    *,
    use_vector: bool = True,
    use_keyword: bool = True,
    use_rerank: bool = True,
) -> list[ScoredChunk]:
    qs = _allowed_chunks(user)
    rankings = []
    if use_vector:
        rankings.append(_vector_ids(qs, query))
    if use_keyword:
        rankings.append(_keyword_ids(qs, query))
    fused = rrf(rankings)  # 1 nhánh => RRF vẫn giữ nguyên thứ hạng
    if not fused:
        return []
    ordered = sorted(fused, key=fused.get, reverse=True)[:CANDIDATES]
    by_id = {c.pk: c for c in qs.filter(pk__in=ordered)}
    cands = [by_id[i] for i in ordered if i in by_id]

    if use_rerank and cands:
        scores = get_reranker().score(query, [c.text for c in cands])
        scored = sorted(zip(cands, scores, strict=True), key=lambda t: t[1], reverse=True)
    else:
        scored = [(c, fused[c.pk]) for c in cands]
    return [ScoredChunk(c, float(s), _source_ref(c)) for c, s in scored[:k]]
