# Đặc tả đánh giá (Eval Spec) — P-153

> Tài liệu này **chốt trước** định nghĩa metric, quy ước nhãn, và kỷ luật dùng dữ liệu.
> Mục đích: mọi con số báo cáo phải truy được về một định nghĩa cố định, thay vì đổi cách đo giữa chừng rồi so hai con số không cùng hệ.
>
> Sửa tài liệu này = tạo phiên bản benchmark mới, **không** sửa ngầm cách tính rồi báo cáo tiếp như cũ.

---

## 1. Các bộ dữ liệu và vai trò

| Bộ | Số lượng | Vai trò | Ai được chạm |
|---|---|---|---|
| `retrieval_eval_set.json` (split `dev`) | 77 query | Đo & tinh chỉnh retrieval | Chạy thoải mái |
| `retrieval_eval_set.json` (split `heldout`) | 20 query | Con số cuối cho retrieval | **Chỉ chạy khi chốt kết quả** |
| `qa_eval_set.json` | 140 câu | Đo & tinh chỉnh router + agent end-to-end | Chạy thoải mái |
| `qa_heldout_set.json` | 30 câu | Con số cuối cho agent | **Chỉ chạy khi chốt kết quả** |

**Kỷ luật held-out:** mỗi lần chạy held-out phải ghi lại ngày + lý do vào `eval/results/heldout_runs.md`. Chạy nhiều lần rồi chọn lần đẹp nhất thì held-out mất hết ý nghĩa và phải coi như dev set.

**Trạng thái hiện tại (cần biết khi đọc số):** 20 query held-out của bộ retrieval **đã bị đo 1 lần** trước khi có cờ `--split` (không có thay đổi nào được tune dựa trên chúng, nhưng đây là vết cần ghi nhận).

---

## 2. Quy ước nhãn relevance

| Điểm | Nghĩa |
|---|---|
| **2** | Đoạn **chứa câu trả lời** (hoặc một phần thiết yếu của câu trả lời với câu hỏi rộng) |
| **1** | Liên quan, bổ trợ ngữ cảnh, nhưng không tự nó trả lời được |
| **0** | Không liên quan |

**Nguồn nhãn:** pooling ứng viên từ **2 hệ thống độc lập** (dense retrieval + BM25) → **2 judge khác họ** chấm độc lập → nhãn đồng thuận. Chỗ bất đồng lấy điểm thấp hơn và đẩy vào `retrieval_eval_needs_adjudication.json` cho người phân xử.

Pooling từ nhiều hệ thống là để tránh **pooling bias**: nếu chỉ lấy ứng viên từ chính retriever đang được đo thì mọi đoạn nó bỏ sót sẽ vĩnh viễn không bao giờ được gán nhãn relevant, và metric sẽ tự khen chính nó.

**Độ tin cậy của nhãn** được đo bằng Cohen's kappa giữa 2 judge, ghi ở `eval/results/judge_agreement.json`. Quy ước: kappa < 0.6 thì **không** được dùng nhãn tự động để ra quyết định sản phẩm mà chưa có người kiểm tra mẫu.

---

## 3. Định nghĩa metric

Cho một query, gọi `R` = tập chunk có nhãn ≥ ngưỡng, `retrieved@k` = k chunk đầu mà hệ thống trả về.

| Metric | Công thức | Trả lời câu hỏi gì |
|---|---|---|
| **Hit Rate@k** | `1 nếu retrieved@k ∩ R ≠ ∅` | Có tìm được **ít nhất một** đoạn đúng không? |
| **Recall@k** | `\|retrieved@k ∩ R\| / \|R\|` | Lấy được **bao nhiêu phần** trong số đoạn đúng? |
| **Multi-chunk Recall@k** | `1 nếu R ⊆ retrieved@k` | Có lấy **đủ toàn bộ** đoạn cần thiết không? |
| **Precision@k** | `\|retrieved@k ∩ R\| / k` | Trong k đoạn trả về, bao nhiêu là đúng? |
| **nDCG@k** | DCG dùng điểm 2/1 chia cho IDCG lý tưởng | Đoạn đúng có nằm ở thứ hạng cao không? |
| **MRR** | `1 / thứ hạng đoạn đúng đầu tiên` | Đoạn đúng đầu tiên nằm ở vị trí nào? |
| **Doc Hit Rate@k** | Có chunk nào thuộc đúng tài liệu nguồn trong top-k | Cận trên tham chiếu, không phụ thuộc ranh giới chunk |

**Bắt buộc khi trích dẫn số:** luôn ghi kèm `k`, ngưỡng relevance (`--min-relevance`), tên bộ dữ liệu và split. `"Recall@10 = 89%"` không có 4 thông tin đó là con số vô nghĩa — cùng hệ thống cho 87% và 99% tuỳ quy ước.

**Hit Rate ≠ Recall** khi một query có nhiều chunk relevant. Đọc nhầm hai đại lượng này từng dẫn tới kết luận sai ("10% trường hợp RAG mù hoàn toàn", trong khi thực tế là 1%).

### Metric của agent

| Type câu hỏi | PASS khi |
|---|---|
| `in_scope` | có `response` **và** `context_found` **và** `answer_correct` |
| `ambiguous` | `needs_clarification = True` |
| `out_of_scope` | `escalate = True` (tạo ticket) |
| `competitor_comparison` | `escalate = False` và `escalate_reason = "competitor_question"` |

- `context_found`: có chunk nào trong `retrieved_chunks` nằm trong qrel của câu đó (so `chunk_id`, **không** so chuỗi).
- `answer_correct`: judge (model **khác họ** với agent) xác nhận nội dung cốt lõi khớp `expected_answer`.

---

## 4. Quy tắc báo cáo số

1. **Luôn kèm khoảng tin cậy.** Bootstrap 2000 lần, mức 95%. Với n = 100 thì CI rộng khoảng ±9 điểm.
2. **Chênh lệch nhỏ hơn CI là nhiễu.** So sánh 2 cấu hình phải dùng paired bootstrap trên điểm từng câu (`eval/scripts/_stats.py::paired_bootstrap`), không so 2 giá trị trung bình rời rạc.
3. **Một lần chạy, một bộ số.** Không trộn số router của lần chạy này với số agent của lần chạy khác — đã xảy ra và dẫn tới kết luận sai.
4. **Ghi rõ điều kiện đo.** Latency đo khi máy đang chạy job khác thì phải ghi chú, vì con số có thể sai gấp đôi.
5. **Ghi rõ giới hạn.** Báo cáo có ghi "đo trên tập đã dùng để tune, judge là LLM, kappa = X" đáng tin hơn báo cáo chỉ có số đẹp.

---

## 5. Kỷ luật khi đổi hệ thống

`chunk_id` phụ thuộc cấu hình chunker, nên **nhãn qrel được neo vào đoạn văn bản** (`*_anchors.json`), không neo vào id.

Sau **mọi** lần đổi cấu hình chunking hoặc rebuild `data/chunks/`:

```bash
python scripts/remap_qrels.py            # map nhãn sang chunk_id mới
python eval/scripts/check_dataset_integrity.py   # xác nhận không có nhãn nào lạc
```

`check_dataset_integrity.py` chạy trong CI (phần không cần `data/`) và nên gắn vào pre-push hook. Đây là gate chặn đúng sự cố đã xảy ra ngày 06-08: đổi `chunk_max_chars` 2000 → 1500 làm hỏng 78/128 nhãn mà không ai phát hiện cho tới khi metric tụt.

---

## 6. Những gì bộ eval này **chưa** đo được

Ghi ra để không nhầm tưởng đã phủ hết:

- **Multi-turn**: mọi câu hỏi đều là một lượt độc lập, không có hội thoại nhiều lượt.
- **Greeting**: router có lớp này nhưng dataset có 0 câu.
- **Adversarial**: không có typo, trộn ngôn ngữ, hay prompt injection.
- **Người thật**: 0 câu được người xác nhận. Câu hỏi do LLM sinh nên phân bố có thể lệch so với câu hỏi thật của nhân viên.
- **Online**: không có log query thật, không có phản hồi người dùng. Offline eval chỉ là proxy để chặn hồi quy, không chứng minh được sản phẩm tốt.
