def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion.

    TẠI SAO RRF mà không cộng điểm? Điểm cosine (0–1) và ts_rank (0–~1, phân bố khác hẳn)
    không cùng thang đo. RRF chỉ dùng THỨ HẠNG: score(d) = Σ 1/(k + rank_i(d)).
    Chunk đứng cao ở cả hai danh sách thắng; k=60 làm phẳng ảnh hưởng của top-1.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores
