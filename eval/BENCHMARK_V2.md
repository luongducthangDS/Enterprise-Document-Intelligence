# NexaTech post-MVP benchmark v2

## Mục đích

Bộ v2 dùng cho giai đoạn phát triển sau MVP, dựa trên test case do nhóm cung
cấp và đúng 13 tài liệu NexaTech đang có trong live index. Đây là **dev set** để
phát triển, không phải held-out release.

## Trạng thái

- `nexatech_post_mvp_v2_dev.json`: đã chuẩn hóa case, persona, multi-turn, hành
  vi kỳ vọng và tài liệu dự kiến.
- Kỳ vọng từ Markdown được giữ nguyên ở `expected_behavior_raw`, nhưng chưa mặc
  định coi là contract chính thức.
- Case có mâu thuẫn với Type-C contract hoặc kỳ vọng dạng “A hoặc B” được gắn
  `contract_flags` để nhóm phân xử.
- Case cần retrieval đang ở `qrel_status=pending_adjudication`; chưa được dùng
  để tính Recall/Hit Rate cho tới khi có gold chunk được người kiểm tra.

## Quy trình tiếp theo

1. Chạy `audit_benchmark_corpus.py` để xác nhận đủ 13 source trong live index.
2. Nhóm phân xử các `contract_flags`, đặc biệt câu thuần luật.
3. Pool candidate chunk từ dense và BM25 trên split dev.
4. Người kiểm tra gán relevance 2/1/0 và chốt qrels.
5. Chạy retrieval dev, sau đó mới chạy agent end-to-end dev.
6. Tạo một held-out mới, độc lập với 64 case đã nhìn thấy, khi chuẩn bị release
   phiên bản mở rộng.

Khi thêm tài liệu, không sửa qrel để ép khớp. Chạy audit source/chunk trước;
remap chỉ dùng nếu cùng evidence còn tồn tại nhưng chunk identity thay đổi.

Lệnh tạo candidate pool (45 turn hiện tại, chỉ gọi embedding + Chroma; không
gọi judge và không tự sinh qrel):

```bash
python eval/scripts/pool_nexatech_v2_candidates.py
```

File kết quả để người kiểm tra điền `human_relevance` nằm ở
`eval/results/nexatech_post_mvp_v2_candidate_pool.json`.

Việc chạy lệnh sẽ gửi các câu hỏi dev tới embedding API và Chroma. Cần người sở
hữu dữ liệu xác nhận egress trước; tool không được tự động chạy trong CI.
