# Câu hỏi phỏng vấn (và trả lời theo chính dự án này)

**1. Vì sao lọc quyền trong SQL chứ không lọc sau khi lấy top-k?**
Lọc sau làm chunk bị cấm chiếm chỗ top-k (kết quả thiếu) và chỉ cần quên lọc ở một đường là rò rỉ. Ở đây
`search()` giới hạn tập chunk bằng subquery `visible_documents` trước vector/keyword; test `test_forbidden_chunks_never_returned`
chạy mọi tổ hợp cờ.

**2. Vì sao chunk theo heading rồi mới theo kích thước?**
Giữ trọn một ý, có metadata `heading` để trích dẫn. Chia theo kích thước (~600 token, overlap ~12%) chỉ khi mục quá dài; overlap để câu sát ranh giới không mất.

**3. RRF là gì, vì sao không cộng điểm?**
Điểm cosine và ts_rank khác thang đo. RRF dùng thứ hạng: Σ 1/(60+rank). Bền, không cần chuẩn hoá.

**4. Hybrid khác vector ở đâu, khi nào hybrid thắng?**
Vector bắt ngữ nghĩa/paraphrase; keyword bắt thuật ngữ hiếm, mã, tên riêng. Lưu ý: báo cáo `eval/REPORT.md` bão hòa vì corpus nhỏ + embedding giả — không kết luận được hơn kém.

**5. Rerank để làm gì và đánh đổi?**
Cross-encoder chấm cặp (query, chunk) chính xác hơn bi-encoder nhưng chậm → chỉ chấm ~30 ứng viên. Đặt sau interface để thay.

**6. Human-in-the-loop trong LangGraph hoạt động thế nào?**
Node `tools` gọi `interrupt()`; đồ thị lưu checkpoint (Postgres, `thread_id=session`) và dừng. Tạo `PendingAction`; approve gọi `Command(resume=...)`. Node chạy lại từ đầu khi resume nên `execute_action` idempotent theo `tool_call_id`.

**7. Chống bịa (hallucination) thế nào?**
Prompt chỉ dựa ngữ cảnh + trích dẫn [n]; không có kết quả → từ chối không gọi LLM; chỉ phô nguồn được trích; `guard` của agent chặn câu trả lời không có ToolMessage bằng chứng.

**8. Prompt injection qua tài liệu/tool?**
Danh tính người dùng nằm trong closure của tool, không là tham số LLM; tool hành động luôn cần người dùng duyệt; quyền áp dụng ở tầng dữ liệu, không phụ thuộc LLM "ngoan".

**9. Vì sao ingest idempotent và làm thế nào?**
Celery có thể chạy lại. Hash nội dung chặn trùng; xoá chunk cũ + ghi mới trong một transaction; unique `(document, index)`.

**10. MCP là gì, khác function-calling thường ở đâu?**
Giao thức chuẩn để client (Claude Code) khám phá và gọi tool/resource của server bất kỳ. Ở đây server dùng `MCPServer` (mcp 2.x), token → user → cùng `search()` nên quyền được tôn trọng.

**11. Bạn đo chất lượng RAG thế nào, và hạn chế hiện tại?**
hit-rate@k, MRR, rò rỉ quyền, độ trễ trên golden set 24 câu. Chưa chạy Ragas (cần LLM thật); chưa đo với embedding thật.

**12. Điều gì sẽ làm khác khi lên production?**
Embedding/LLM/cross-encoder thật + eval lại; SSE qua ASGI thay vì gunicorn sync; streaming token thật (hiện model giả trả một khối); giới hạn kích thước upload; quét virus; Langfuse v3 + SDK mới.
