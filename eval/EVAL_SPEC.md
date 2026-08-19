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
| `qa_eval_set.json` | 137 câu tính metric (+3 retired) | Đo & tinh chỉnh router + agent end-to-end. **Sau 13/08: router development/regression set** — xem 1.1 | Chạy thoải mái |
| `qa_heldout_set.json` | 30 câu | Con số cuối cho agent | **Chỉ chạy khi chốt kết quả** |

### 1.1. Verbatim leakage vs test-informed tuning

Hai thứ khác nhau, và chỉ loại được thứ nhất là chưa đủ để gọi một bộ là held-out sạch:

| Loại | Nghĩa | Xử lý |
|---|---|---|
| **Verbatim leakage** | Câu eval nằm nguyên văn trong prompt | Cấm — prompt chỉ dùng ví dụ synthetic |
| **Test-informed tuning** | Soi lỗi trên bộ eval rồi sửa prompt theo chính các lỗi đó | Được phép, nhưng bộ đó **mất tư cách held-out** |

Ca thực tế (13/08, `report_1208.md` mục 11): prompt router được sửa sau khi soi 6/7 failure trong `qa_eval_set`; rule "chiều hỏi" sinh ra từ pattern của chính các failure ấy. Ví dụ trong prompt đều là synthetic (0/24 trùng eval), nhưng bộ 137 câu vẫn **không còn** là bằng chứng không thiên lệch cho generalization của router.

Hệ quả phải ghi rõ mỗi khi báo số: accuracy trên bộ này đủ mạnh để **chọn giữa các phương án**, nhưng không phải **ước lượng production**.

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
python scripts/rag_pipeline/remap_qrels.py            # map nhãn sang chunk_id mới
python eval/scripts/check_dataset_integrity.py   # xác nhận không có nhãn nào lạc
```

Trước khi chạy eval có gọi API, phải kiểm tra qrel với **live index** (CI chỉ
thấy `data/chunks/` cục bộ nên không phát hiện được collection cloud đã đổi):

```bash
python eval/scripts/audit_live_index_alignment.py \
  --dataset eval/datasets/retrieval_eval_set.json \
  --qrels eval/datasets/retrieval_eval_qrels.json --split dev --strict
```

`eval_retrieval.py` cũng tự chạy preflight này và dừng trước khi gọi
embedding/reranker nếu có gold chunk đã biến mất. Cờ `--allow-stale-qrels` chỉ
dùng để chẩn đoán; report sinh ra trong chế độ đó không được coi là số chất
lượng hợp lệ.

`check_dataset_integrity.py` chạy trong CI (phần không cần `data/`) và nên gắn vào pre-push hook. Đây là gate chặn đúng sự cố đã xảy ra ngày 06-08: đổi `chunk_max_chars` 2000 → 1500 làm hỏng 78/128 nhãn mà không ai phát hiện cho tới khi metric tụt.

### 5.1. Giới hạn của `remap_qrels.py` — remap KHÔNG phải cách chữa mọi lỗi toàn vẹn

> **Chỉ remap khi cùng một evidence bị đổi chunk identity/boundary.** Tuyệt đối không dùng remap để tìm "evidence gần giống" cho một câu hỏi mà nguồn gốc của nó đã bị loại khỏi corpus.

Phân biệt trước khi chạy bất cứ lệnh nào:

| Tình huống | Cách xử lý đúng |
|---|---|
| Chunker đổi cấu hình, cùng đoạn văn nằm ở `chunk_id` khác | **Remap** — evidence vẫn nguyên vẹn, chỉ đổi địa chỉ |
| Chunk biến mất **ngoài ý muốn** (bug ingestion, mất file) | **Restore/regenerate** rồi rerun CI — remap ở đây là che bug |
| Tài liệu nguồn bị loại **có chủ đích**, evidence không còn hợp lệ về nội dung | **Retire câu hỏi**, không remap |

Lý do rất cụ thể: remap map nhãn sang chunk gần nhất theo nội dung neo. Nếu evidence gốc đã không còn hợp lệ (vd tài liệu là mẫu rỗng bị gỡ), tool vẫn tìm được "một chunk nào đó" và CI sẽ xanh — nhưng benchmark từ đó chấm agent dựa trên nguồn **không phải nguồn gốc của câu hỏi**. Đó là sửa benchmark để thích nghi với vấn đề, không phải sửa vấn đề.

Ca thực tế (12/08, xem `report_1208.md` mục 8): `amis_mau-thong-bao-quy-dinh-nghi-phep.docx` là file mẫu rỗng (toàn `………`), bị loại có chủ đích từ 06/08. qa_117/118/119 sinh từ chính các dòng trống đó và qrel chỉ trỏ tới đúng chunk đã mất → **retired**. Nhưng rq_040 có 7 chunk có nhãn, chunk mất chỉ là 1 với score 1 → **giữ câu, chỉ gỡ entry stale**. Cùng một sự cố, hai cách xử lý khác nhau, và cả hai đều không phải remap.

**Câu `retired`**: giữ nguyên trong dataset kèm `retired: true`, `retired_at`, `retired_reason` để truy vết, nhưng bị loại khỏi mọi phép tính metric (`eval_router.py`, `eval_agent.py`, `check_dataset_integrity.py` đều lọc). Đếm chúng vào mẫu số là làm loãng metric bằng câu không thể chấm.

---

## 5b. Boundary eval (runtime decision)

`eval/datasets/boundary_eval_set.json` + `eval/scripts/eval_boundary.py` (`make eval-boundary`).

Đo lớp boundary — thứ mà eval intent/retrieval không chạm tới: câu hỏi được map
sang scenario nào trong 64 scenario canonical, và decision kèm theo có đúng
`assistant_role` / `runtime_action` / `sensitivity` / người phụ trách không.

- Deterministic, **không gọi LLM** → chạy được trong CI, chi phí 0.
- Ngoài accuracy còn kiểm tra invariant runtime; có vi phạm thì exit code 1:
  `runtime_action` không bao giờ là `CREATE_CASE` ở MVP-1; scenario
  `HUMAN_FIRST` không sinh action tạo workflow; scenario `Critical` không có
  field bắt buộc nhập.
- Báo cáo tách 5 chiều thay vì một con số, vì map nhầm sang scenario cùng owner
  nhẹ hơn hẳn map nhầm một scenario ER sang scenario hành chính.

**Giới hạn đã biết**: 64 câu hiện tại do chính người viết registry soạn nên
thiên lệch về đúng từ khóa đã khai — con số 1.0 hiện tại là *baseline chống hồi
quy*, không phải ước lượng accuracy khách quan. Cần bộ held-out do người khác
viết trước khi trích dẫn như một chỉ số chất lượng.

## 6. Những gì bộ eval này **chưa** đo được

Ghi ra để không nhầm tưởng đã phủ hết:

- **Multi-turn**: mọi câu hỏi đều là một lượt độc lập, không có hội thoại nhiều lượt.
- **Greeting**: router có lớp này nhưng dataset có 0 câu.
- **Adversarial**: không có typo, trộn ngôn ngữ, hay prompt injection.
- **Người thật**: 0 câu được người xác nhận. Câu hỏi do LLM sinh nên phân bố có thể lệch so với câu hỏi thật của nhân viên.
- **Online**: không có log query thật, không có phản hồi người dùng. Offline eval chỉ là proxy để chặn hồi quy, không chứng minh được sản phẩm tốt.
