# Brief: tạo fresh router holdout (blind)

> **Dành cho người viết bộ câu hỏi.** Người viết prompt router **không** tham gia phần này.
>
> Mục đích: có một bộ câu chưa từng được dùng để soi lỗi hay chỉnh prompt, nhằm xác nhận router đang chạy tổng quát hoá được — chứ không phải chỉ hợp với bộ dev đã tune theo.

---

## 1. Vì sao cần bộ này

Bộ `qa_eval_set.json` (137 câu) đã bị dùng để soi lỗi rồi sửa prompt router theo chính các lỗi đó. Ví dụ trong prompt hiện đều là synthetic (0 câu trùng eval), nhưng **rule phân loại được thiết kế từ pattern của các failure trong bộ đó** — nên nó không còn là bằng chứng không thiên lệch. Nó giờ là *development / regression set*.

Con số 94,9% đủ để chọn cấu hình này hơn phương án khác, nhưng không dùng để nói "router đạt 94,9% ngoài production".

## 2. Quy tắc blind — quan trọng nhất

**Người viết KHÔNG được xem:**
- `eval/datasets/qa_eval_set.json` (137 câu dev)
- Nội dung prompt router (`_get_router_system()` trong `src/agents/nodes/router.py`)
- Danh sách các câu router đang phân loại sai
- Mục 10 và 11 của `report_1208.md` (error analysis)

**Được đọc:**
- Định nghĩa 4 intent ở mục 3 dưới đây
- Phạm vi corpus: `data/metadata/document_registry.csv` (danh sách tài liệu) và `docs/knowledge_base_scope_for_pitch.md`

**Không nhận yêu cầu kiểu "viết thêm câu giống các lỗi router đang mắc".** Nếu biết router yếu ở đâu rồi cố viết câu vào đúng chỗ đó, bộ này mất luôn ý nghĩa.

## 3. Bốn intent cần phủ

Chatbot phục vụ **nhân viên đang làm việc** của công ty demo (persona V-NOVA), trả lời bằng tài liệu chính sách chung + văn bản pháp luật VN.

| Intent | Định nghĩa | Hành vi mong đợi |
|---|---|---|
| `greeting` | Chào hỏi, xã giao, không phải câu hỏi HR | Trả lời xã giao ngắn |
| `hr_question` | Chủ đề rõ, trả lời được bằng chính sách chung / luật, không cần mở hồ sơ riêng của người hỏi | Tra tài liệu rồi trả lời |
| `ambiguous` | Thiếu thông tin đến mức không xác định được người hỏi muốn biết gì; đoán sai sẽ ra câu trả lời khác hẳn | Hỏi lại đúng 1 câu làm rõ |
| `out_of_scope_or_personal` | (a) cần dữ liệu riêng của người hỏi mới trả lời chính xác được; (b) hỏi chính sách của một công ty khác có tên cụ thể; (c) ngoài phạm vi HR | Từ chối lịch sự / chuyển HRBP |

Lưu ý ranh giới hay bị nhầm: câu **có** chữ "tôi/mình" vẫn có thể là `hr_question` nếu thứ người hỏi cần là quy định chung. Chỉ là `out_of_scope_or_personal` khi **không thể** trả lời nếu không mở hồ sơ của riêng họ.

## 4. Yêu cầu bộ câu

**Quy mô: 60–80 câu.** Phân bổ gợi ý (không cần khớp chính xác):

| Nhóm | Số câu | Ghi chú |
|---|---|---|
| `hr_question` | 30–40 | Trải đều các chủ đề: lương/OT, nghỉ phép, thai sản, BHXH/BHYT, tuyển dụng, onboarding/offboarding, đào tạo, kỷ luật, công tác phí |
| `ambiguous` | 10–15 | Mơ hồ **thật** — người thật hỏi vậy thì HR cũng phải hỏi lại |
| `out_of_scope_or_personal` | 10–15 | Cả 3 dạng (a)(b)(c) |
| `greeting` | 5 | Nhóm này bộ dev hiện có **0 câu** |

**Cố tình trộn easy và borderline.** Bộ toàn câu dễ thì không phát hiện được gì; toàn câu khó thì không đại diện traffic thật.

**Viết như người dùng thật gõ**: có thể thiếu dấu, viết tắt, dài dòng, hỏi hai ý trong một câu.

**Nhãn phải chốt TRƯỚC khi chạy.** Nhãn quyết sau khi nhìn kết quả router thì bộ này thành vô nghĩa.

## 5. Format

`eval/datasets/router_holdout_v1.json`:

```json
[
  {
    "id": "rh_001",
    "question": "Câu hỏi như người dùng gõ",
    "type": "hr_question",
    "difficulty": "easy",
    "note": "vì sao gán nhãn này (1 câu, giúp người khác phản biện nhãn)"
  }
]
```

`type` ∈ `greeting` | `hr_question` | `ambiguous` | `out_of_scope_or_personal` · `difficulty` ∈ `easy` | `borderline`

## 6. Protocol chạy — đúng MỘT lần

1. Freeze: ghi lại sha256 của dataset + `router.py` + config đang chạy.
2. Chạy `python eval/scripts/eval_router_holdout.py` một lần duy nhất.
3. **Không** xem từng lỗi rồi sửa prompt. Lỗi phát hiện được ghi thành *production risk* / nguồn cho dataset sau, **không** dùng để tune vòng này.
4. Muốn mở đợt optimization mới thì phải dùng một dev set khác — không quay lại tune trên chính bộ holdout đã xem kết quả.
5. Sau khi chạy, bộ này thành **router holdout consumed v1**, không còn dùng làm bằng chứng không thiên lệch được nữa.

## 7. Cách đọc kết quả — KHÔNG hard gate theo accuracy

Với 60–80 câu, sai thêm một câu đã dịch ~1,3–1,7 điểm. Đòi đúng 94,9% trên mẫu này là đòi sai thống kê. Ưu tiên **hướng của lỗi** hơn con số tổng.

**Gate thật (đây mới là thứ veto được):**

| Tiêu chí | Ngưỡng |
|---|---|
| HR false rejection (`hr_question` → `out_of_scope_or_personal`) | 0, hoặc tối đa 1 case và phải review được |
| OOS/competitor → `hr_question` | **0** |
| UAR (`ambiguous` → `hr_question`) | Không cho thấy bot trở nên liều |
| UCR (`hr_question` → `ambiguous`) | Ở mức chấp nhận được |
| Router p50 | < 500 ms |

**Accuracy:** kỳ vọng quanh low/mid-90s, nhưng **không veto** chỉ vì 92–93% trên mẫu nhỏ.

Ví dụ cách đọc:

- `92,5%` · HR rejection 0 · OOS leak 0 · UAR tốt → **C được xác nhận**.
- `96%` nhưng 2 câu personal/out-of-scope bị route thành `hr_question` → **không đạt**, dù headline đẹp hơn. Câu trả lời liều cho thứ lẽ ra phải từ chối là loại lỗi đắt nhất.

## 8. Vì sao không mượn `qa_heldout_set.json`

Bộ đó (30 câu) là held-out của **agent end-to-end**. Chạy router trên nó là tiêu một tài sản có phạm vi rộng hơn để xác nhận đúng một component. Router đã đạt 94,9% với 0 HR rejection và optimization đã đóng — không đáng đổi.

Chỉ mượn khi team thực sự không tạo được bộ mới và cần quyết định release ngay; khi đó **phải** ghi vào `eval/results/heldout_runs.md` rằng đã tiêu một phần shared holdout.
