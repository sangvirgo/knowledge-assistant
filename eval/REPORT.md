# Báo cáo đánh giá retrieval

Chạy: `uv run python -m eval.run_eval` (tạo DB test tạm, nạp `eval/corpus/`, chạy `eval/golden.jsonl`).
Golden set: 24 câu = 18 có đáp án, 3 không có đáp án, 3 bị cấm theo quyền (xem `golden.jsonl`).

## Kết quả lần chạy này (provider GIẢ)

Embedding: **giả** (hashing trên từ, không có ngữ nghĩa thật). Rerank: **LexicalReranker** (giữ chỗ, không phải cross-encoder).

| Cấu hình | hit-rate@5 | MRR | rò rỉ (forbidden) | latency TB (ms) | p95 (ms) |
|---|---|---|---|---|---|
| vector | 1.00 | 1.00 | 0/3 | 8 | 8 |
| hybrid | 1.00 | 1.00 | 0/3 | 10 | 11 |
| hybrid+rerank | 1.00 | 1.00 | 0/3 | 11 | 13 |

## Nhận xét (trung thực)

- **Kết quả bão hòa, không phân biệt được 3 cấu hình.** Corpus chỉ có 8 tài liệu (~25 chunk) và embedding giả
  bản chất là so khớp từ, nên cả vector lẫn hybrid đều tìm đúng. Các con số trên **không** chứng minh hybrid/rerank
  tốt hơn; chúng chỉ xác nhận pipeline chạy đúng và **không có rò rỉ quyền** (0/3).
- Latency đo trên Postgres local với embedding giả; không đại diện cho embedding/cross-encoder thật.
- **Chưa chạy**: các metric Ragas (faithfulness, answer relevancy, context precision/recall) — cần LLM thật
  (`LLM_API_KEY`). `run_eval.py` hiện chưa tích hợp Ragas; đây là việc còn thiếu so với spec.
- Để có so sánh có ý nghĩa: đặt `EMBEDDING_*`, `RERANK_MODEL` (cần extra `rerank`), mở rộng corpus (hàng trăm chunk,
  nhiều câu paraphrase không trùng từ), rồi chạy lại và thay bảng này bằng số thật.
