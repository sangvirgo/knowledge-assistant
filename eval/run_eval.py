"""So sánh 3 cấu hình retrieval trên golden set.  Chạy:  uv run python -m eval.run_eval

Dùng DB test tạm (tự tạo, tự xoá) nên không đụng dữ liệu dev.
Provider nào đang bật (thật/giả) phụ thuộc .env — kết quả ghi rõ trong REPORT.md.
"""

import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

import django  # noqa: E402

django.setup()

from django.core.files.base import ContentFile  # noqa: E402
from django.test.utils import setup_databases, teardown_databases  # noqa: E402

K = 5
CONFIGS = {
    "vector": dict(use_vector=True, use_keyword=False, use_rerank=False),
    "hybrid": dict(use_vector=True, use_keyword=True, use_rerank=False),
    "hybrid+rerank": dict(use_vector=True, use_keyword=True, use_rerank=True),
}
# file -> (phòng ban, visibility)
ACL = {
    "luong-thuong": ("HR", "department"),
    "tuyen-dung": ("HR", "department"),
    "nghi-phep": ("HR", "company"),
    "deploy": ("Eng", "department"),
    "oncall": ("Eng", "department"),
    "coding-standards": ("Eng", "department"),
    "an-toan-thong-tin": ("HR", "company"),
    "quy-tac-ung-xu": ("HR", "company"),
}


def build_corpus():
    from apps.accounts.models import Department, User
    from apps.documents.models import Document
    from apps.documents.services.ingest import ingest

    depts = {n: Department.objects.create(name=n) for n in ("HR", "Eng")}
    users = {
        "hr": User.objects.create_user("hr", password="x", department=depts["HR"]),
        "eng": User.objects.create_user("eng", password="x", department=depts["Eng"]),
    }
    for stem, (dept, vis) in ACL.items():
        d = Document.objects.create(
            title=stem,
            owner=users["hr" if dept == "HR" else "eng"],
            department=depts[dept],
            visibility=vis,
        )
        d.file.save(f"{stem}.md", ContentFile((ROOT / "corpus" / f"{stem}.md").read_bytes()))
        ingest(d.pk)
    return users


def evaluate(users, golden, flags):
    from apps.retrieval.services import search

    hits = rr = answerable = leaks = forbidden = 0
    lat = []
    for g in golden:
        user = users[g["user"]]
        t = time.perf_counter()
        res = search(user, g["question"], k=K, **flags)
        lat.append((time.perf_counter() - t) * 1000)
        titles = [r.chunk.document.title for r in res]
        if g["type"] == "answerable":
            answerable += 1
            want = set(g["expected_sources"])
            ranks = [i for i, t_ in enumerate(titles, 1) if t_ in want]
            if ranks:
                hits += 1
                rr += 1 / ranks[0]
        elif g["type"] == "forbidden":
            forbidden += 1
            # chunk từ tài liệu phòng ban HR mà user eng không được xem => rò rỉ
            leaks += sum(1 for t_ in titles if ACL[t_][1] == "department" and ACL[t_][0] == "HR")
    lat.sort()
    return {
        f"hit_rate@{K}": hits / answerable,
        "mrr": rr / answerable,
        "forbidden_leaks": leaks,
        "forbidden_questions": forbidden,
        "latency_ms_mean": statistics.mean(lat),
        "latency_ms_p95": lat[int(0.95 * (len(lat) - 1))],
    }


def providers():
    emb = "thật" if os.environ.get("EMBEDDING_API_KEY") else "GIẢ (hashing, không ngữ nghĩa thật)"
    rer = os.environ.get("RERANK_MODEL") or "LexicalReranker (giữ chỗ, không phải cross-encoder)"
    return emb, rer


def main():
    golden = [json.loads(line) for line in (ROOT / "golden.jsonl").read_text().splitlines()]
    cfg = setup_databases(verbosity=0, interactive=False)
    try:
        users = build_corpus()
        results = {name: evaluate(users, golden, flags) for name, flags in CONFIGS.items()}
    finally:
        teardown_databases(cfg, verbosity=0)

    emb, rer = providers()
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "latest.json").write_text(json.dumps(results, indent=2))
    rows = [
        "| Cấu hình | hit-rate@5 | MRR | rò rỉ (forbidden) | latency TB (ms) | p95 (ms) |",
        "|---|---|---|---|---|---|",
    ]
    for n, r in results.items():
        rows.append(
            f"| {n} | {r[f'hit_rate@{K}']:.2f} | {r['mrr']:.2f} | "
            f"{r['forbidden_leaks']}/{r['forbidden_questions']} | "
            f"{r['latency_ms_mean']:.0f} | {r['latency_ms_p95']:.0f} |"
        )
    table = "\n".join(rows)
    print(f"Embedding: {emb}\nRerank: {rer}\n\n{table}")
    (out / "table.md").write_text(f"Embedding: {emb}\nRerank: {rer}\n\n{table}\n")


if __name__ == "__main__":
    main()
