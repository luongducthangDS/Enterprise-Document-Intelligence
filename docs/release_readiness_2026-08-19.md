# Báo cáo phần việc của Minhphu — 19/08/2026

## 1. Kết luận ngắn

Các hạng mục triển khai chính được giao cho Minhphu đã hoàn thành về code,
database, worker, kiểm thử và tài liệu. Hệ thống hiện có đủ các thành phần cần
thiết và các bộ test kỹ thuật đều pass. Live E2E, PR và peer review vẫn là các
bước bàn giao cần thực hiện trước khi merge.

Tuy nhiên, kết quả đánh giá chất lượng RAG cuối chưa đạt mục tiêu. Nguyên nhân
không chỉ nằm ở câu trả lời của model: dữ liệu đánh giá cũ, cách chia chunk,
index hiện tại và phạm vi sản phẩm mới đang không còn khớp hoàn toàn với nhau.

Theo plan, các ngưỡng chất lượng không bắt buộc phải đạt trước deadline; yêu cầu
bắt buộc là chạy đo thật và báo cáo trung thực. Phần này đã được thực hiện.

## 2. Những việc đã làm xong

### Sửa lỗi tìm kiếm tài liệu G5

- Sửa case `qa_013` về chính sách giới thiệu ứng viên.
- Sửa case `qa_122` về nghỉ không phép và xử lý kỷ luật.
- Cả hai case đã tìm đúng đoạn tài liệu mong đợi trong kiểm tra regression.

### Hoàn thiện database và migration

- Bổ sung các bảng còn thiếu để migration có thể tạo lại đủ schema backend.
- Sửa migration bị trùng số và chuẩn hóa thứ tự từ `0001` đến `0007`.
- Database hiện có đủ 10/10 bảng chính mà backend sử dụng.
- Migration đã được kiểm tra bằng test và áp dụng phần security lên Supabase thật.

### Hoàn thiện bảo mật RLS

- Bật RLS cho ba bảng worker: `ingestion_jobs`, `index_jobs` và
  `evaluation_runs`.
- Thêm cơ chế ngăn người dùng tự đổi `role`, `access_level` hoặc `manager_id` để
  nâng quyền.
- Kiểm tra trực tiếp trên Supabase xác nhận không còn bảng bắt buộc nào tắt RLS
  và trigger bảo vệ đã tồn tại.

### Hoàn thiện luồng worker

- Backend có thể gửi ba loại job sang Agent:
  - ingestion tài liệu;
  - rebuild vector index;
  - chạy evaluation.
- Backend có thể theo dõi trạng thái và lưu tiến độ/kết quả worker vào database.
- Evaluation không còn tự điền metric mẫu hoặc tự báo `PASSED` khi chưa có kết
  quả thật.
- Đã có test kiểm tra ba loại job đi từ `QUEUED` đến trạng thái kết thúc và lưu
  kết quả đúng.

### Cập nhật kiểm thử và tài liệu

- Sửa lỗi lint trong bộ regression G6.
- Cập nhật `README.md`, `WORKLOG.md`, `JOURNAL.md` và sổ chạy held-out.
- Lưu đầy đủ report evaluation để team có thể kiểm tra lại mà không phải chạy
  lại held-out.

## 3. Những kết quả đã đạt được

| Hạng mục | Kết quả |
|---|---|
| Test Agent/Core | 421 test pass |
| Test Backend | 106 test pass |
| Kiểm tra code bằng Ruff | Pass |
| Schema Backend | Đủ 10/10 bảng |
| Migration | Liên tục từ `0001` đến `0007` |
| RLS trên Supabase | Đã bật đầy đủ cho các bảng bắt buộc |
| Profile privilege guard | Đã có trên Supabase |
| G5 `qa_013` và `qa_122` | Đã sửa và regression test pass |
| Worker integration | Đã có code và lifecycle integration test |
| Release evaluation | Đã chạy và lưu kết quả trung thực |

## 4. Kết quả đánh giá chất lượng cuối

### Đánh giá Agent trên 30 câu held-out

| Chỉ số | Kết quả |
|---|---:|
| Số câu pass toàn bộ điều kiện | 0/30 |
| Lỗi API/hạ tầng | 0 |
| Câu được judge xác nhận trả lời đúng | 2/30 |
| Câu tìm đúng gold chunk | 0/30 |
| Thời gian phản hồi trung vị | Khoảng 10 giây |
| P95 latency | Khoảng 60 giây |

`0/30` không có nghĩa Agent bị crash hoặc không trả lời được. Để một câu được
tính pass, Agent phải vừa trả lời đúng vừa lấy đúng `evidence_chunk_id`. Tất cả
30 câu đều không khớp gold chunk nên kể cả câu trả lời đúng vẫn bị tính fail.

Ngoài ra, 17/30 câu được router xếp là `pure_statutory` theo contract mới, trong
khi bộ held-out cũ vẫn gắn tất cả là `in_scope`. Đây là dấu hiệu bộ đánh giá cũ
không còn khớp hoàn toàn với phạm vi sản phẩm hiện tại.

### Đánh giá Retrieval trên 20 query held-out

| Chỉ số | Kết quả | Mục tiêu |
|---|---:|---:|
| Hit Rate@5 | 45,0% | — |
| Recall@5 | 29,6% | 85% |
| Precision@5 | 15,0% | — |
| Document Hit Rate@5 | 15,0% | — |
| MRR | 0,425 | — |

Kết quả này xác nhận retrieval/index hiện tại chưa tìm đúng phần lớn tài liệu
gold. Có 9/20 query tìm thấy ít nhất một gold chunk trong top 5, nhưng chỉ 3/20
query khớp source document được gắn trong dataset. Điều này cho thấy cần kiểm
tra đồng thời cả chất lượng retrieval lẫn sự nhất quán giữa qrel, chunk ID và
source file của bộ đánh giá.

### Lưu ý về API đánh giá

- Agent chat dùng model `GLM-5.2`.
- Judge dùng model khác là `Llama-3.3-70B-Instruct` để tránh model tự chấm chính
  nó.
- Hai model hiện vẫn dùng chung FPT gateway và `FPT_API_KEY`; chưa có API key
  riêng cho evaluation/judge.
- Việc dùng chung key không gây lỗi hạ tầng trong lần chạy này, nhưng nếu quy
  ước của nhóm yêu cầu API key đánh giá riêng thì cấu hình cần được bổ sung ở
  lần đánh giá tiếp theo.

## 5. Những phần chưa đạt và hướng xử lý

Các phần dưới đây là việc cải thiện chất lượng tiếp theo, không phải phần code
Minhphu còn bỏ dở trong plan:

1. Cập nhật nhãn held-out theo contract hiện tại, đặc biệt là các câu
   `pure_statutory`.
2. Đối chiếu và remap qrel/gold chunk ID theo index hiện tại.
3. Kiểm tra các case có `chunk_hit` nhưng `doc_MISS` để sửa sự không nhất quán
   giữa chunk và source document.
4. Rebuild index sau khi chốt lại corpus/chunking, sau đó tạo một held-out set
   mới chưa từng dùng để tune.
5. Nếu team yêu cầu, thêm API key riêng cho judge/evaluation.
6. Chạy smoke test toàn ứng dụng và live E2E worker trên môi trường triển khai.

Không nên chạy lại cùng bộ held-out hiện tại sau khi sửa để lấy điểm đẹp hơn.
Bộ này nên được dùng cho phân tích lỗi; lần đánh giá release tiếp theo cần một
held-out set mới để kết quả còn khách quan.

## 6. Trạng thái bàn giao

- Code và report đã được chia thành các commit riêng theo worker, migration/RLS,
  test, tài liệu, agent eval và retrieval eval.
- Các thay đổi local có từ trước của thành viên khác vẫn được giữ nguyên.
- Trước khi merge `develop`, cần push branch, mở PR và nhờ Dương review phần
  Minhphu theo vòng peer review trong plan.
