# Đặc tả benchmark `thinking_condense` (P1)

> **Chốt TRƯỚC khi chạy** — ngưỡng chấp nhận, cách chấm và cấu trúc artifact đều định nghĩa ở đây trước khi có bất kỳ con số nào. Chạy xong mới chọn threshold thì threshold chỉ là mô tả kết quả, không phải tiêu chí.
>
> Ngày lập: 2026-08-12. Đối tượng đo: `src/agents/nodes/condense.py::condense_node`, biến số duy nhất là `thinking_condense` (ON/OFF).

---

## 1. Vì sao condense phải khắt khe hơn router

Router sai theo hướng an toàn: đẩy sang hỏi lại hoặc escalate, người dùng còn cơ hội sửa. **Condense sai thì âm thầm đổi nghĩa câu hỏi**, rồi retrieval vẫn rất tự tin kéo về một policy khác và agent trả lời trôi chảy về đúng thứ người dùng không hỏi. Không có lớp nào phía sau bắt được lỗi đó — hallucination check chỉ kiểm tra câu trả lời có bám context không, mà context thì đã sai từ đầu.

Vì vậy ngưỡng ở đây chặt hơn `thinking_router`, và **tiêu chí quyết định là downstream, không phải chất lượng rewrite tự thân**.

---

## 2. Nguyên tắc chấm: KHÔNG exact-match

Một rewrite có thể khác câu tham chiếu về câu chữ mà retrieval và câu trả lời vẫn đúng hoàn toàn. Chấm theo 5 tiêu chí ngữ nghĩa:

1. Giữ đúng **intent** của lượt hiện tại
2. **Resolve đúng** tham chiếu lấy từ history
3. **Không thêm** dữ kiện không có trong history
4. Giữ đúng **entity / thời gian / loại policy**
5. Câu hỏi có **tự đứng độc lập** được không

### 2.1. Ba failure mode phải bắt riêng

| Mã | Mô tả | Ví dụ |
|---|---|---|
| `reference_loss` | Mất chủ đề đang nói | *"Vậy ngày thường thì sao?"* → rewrite không còn nhắc làm thêm giờ |
| `reference_misresolution` | Nối sai tiền ngữ | Đang nói OT cuối tuần → rewrite thành nghỉ phép ngày thường |
| `hallucinated_constraint` | Tự thêm ràng buộc không có | History không nói thử việc → rewrite thêm *"đối với nhân viên thử việc"* |

`reference_misresolution` và `hallucinated_constraint` **nguy hiểm hơn hẳn** rewrite vụng câu chữ: chúng tạo ra một câu hỏi hợp lệ nhưng sai đề, và toàn bộ pipeline phía sau sẽ phục vụ câu sai đó một cách tự tin.

---

## 3. Bốn nhóm test case

| Nhóm | Mã | Kiểm tra điều gì |
|---|---|---|
| A. Ellipsis | `ellipsis` | Lược bỏ chủ đề — *"Vậy ngày thường thì sao?"* |
| B. Pronoun/reference | `pronoun_reference` | Đại từ trỏ ngược — *"Cái đó áp dụng cho thử việc không?"* |
| C. Topic continuation | `topic_continuation` | Nối tiếp cùng chủ đề, đổi điều kiện — *"Nếu ngày lễ thì sao?"* |
| D. Topic switch (control) | `topic_switch` | **Nhóm đối chứng**: câu mới độc lập, condense phải **không** kéo context cũ vào |

Nhóm D là nhóm dễ bị bỏ quên nhất và là lý do riêng để có nó: model reasoning mạnh có xu hướng **over-connect** — thấy history là cố nối, biến một câu hỏi độc lập thành câu hỏi bị nhiễm chủ đề cũ (`topic_contamination`). Nếu chỉ đo A/B/C thì thinking ON luôn thắng mà không ai thấy mặt trái của nó.

---

## 4. Hai tầng đo

### Tầng 1 — Condense quality (chỉ mô tả, KHÔNG quyết định)

Với cùng `history` + `current_query`, chạy ON/OFF và ghi: `rewrite`, `condense_latency_ms`, số token sinh ra. Chấm bằng tín hiệu xác định được bằng máy:

- `must_keep`: các khoá thể hiện đã resolve đúng tham chiếu (vd rewrite phải nhắc "làm thêm giờ")
- `must_not_contain`: dấu hiệu nhiễm chủ đề cũ hoặc thêm ràng buộc lạ

Không dùng LLM judge ở tầng này để tránh circular evaluation và để kết quả tái lập được.

### Tầng 2 — Downstream consequence (đây mới là tiêu chí quyết định)

```
standalone_query → retrieval → grade → generate → hallucination check / escalation
```

| Metric | Ý nghĩa |
|---|---|
| Retrieval hit (đúng tài liệu nguồn) | Rewrite còn kéo đúng evidence không |
| Top rerank relevance | Evidence đúng có lên cao không |
| Answer correctness | Cuối cùng có trả lời đúng không |
| Wrong escalation rate | Condense hỏng có gây từ chối oan không |
| Unnecessary clarification | Có làm flow hỏi lại không cần thiết không |
| Condense p50/p95 | Tiết kiệm riêng ở node |
| **E2E p50/p95** | Tiết kiệm **thật** mà người dùng cảm nhận |

---

## 5. Acceptance criteria — `thinking_condense=False` chỉ được chấp nhận nếu đạt CẢ 4

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| 1 | Answer correctness | Không giảm quá **1–2 điểm %** |
| 2 | Wrong escalation | **Không tăng tuyệt đối** trên nhóm critical (A, B, C) |
| 3 | Retrieval hit | Không regression đáng kể |
| 4 | Latency | Cải thiện đủ lớn ở **E2E**, không chỉ riêng node condense |

Không đạt cả 4 → giữ `thinking_condense=True`. Nhanh hơn 10x mà multi-turn tụt thì không đổi.

---

## 6. Kỷ luật A/B

Giữ **giống hệt** giữa hai nhánh: history, current query, corpus snapshot, retrieval config, reranker, generation model/settings, judge.

### 6.1. Báo latency theo paired delta, không phải hiệu của hai median

Mỗi case có cả nhánh ON lẫn OFF trên **cùng input**, nên phép đo mạnh nhất là hiệu theo từng cặp:

```
delta_i = E2E_OFF_i − E2E_ON_i     (âm = OFF nhanh hơn)
```

Report `median / p25 / p75` của tập `delta`, kèm số case mỗi bên thắng. Lý do: **difference of medians ≠ median of paired differences**. Đo thực tế 12/08 cho thấy khoảng cách giữa hai cách đọc là 13 lần:

| Cách đọc | Kết quả |
|---|---|
| difference of medians (OFF p50 − ON p50) | −4.484 ms |
| **median of paired differences** | **−329 ms** |

Cách đầu khiến OFF trông như nhanh 4,5 giây; cách sau cho thấy hiệu ứng ghép cặp gần bằng 0 (p25 = −5.497 ms, p75 = +2.268 ms — khoảng này bao trùm 0). Với A/B cùng case, luôn dùng cách sau để ra quyết định.

### 6.2. Xử lý nhiễu sinh: so theo *effective downstream context*

Nếu hai nhánh có **cùng context thực sự chi phối câu trả lời** mà final answer khác nhau → đánh dấu `generation_variance`, **không** tính thành condense regression khi chưa verify.

Định nghĩa "cùng context" **không** phải `retrieved_ids` bằng nhau tuyệt đối, cũng **không** phải "top-K chunk đầu giống nhau" (K là con số tuỳ tiện, và `generate_node` vốn đưa toàn bộ chunk vào prompt). Định nghĩa đúng:

```
same_effective_context =
    same_high_relevance_evidence      # cùng tập chunk score >= MATERIAL_EVIDENCE_SCORE
    and no_material_new_evidence      # phần chênh lệch không có evidence đáng kể nào mới
```

Ngưỡng neo theo phân phối rerank score đã đo (`rerank_min_score` trong `src/config.py`): in_scope top-1 median 0,975 / p10 0,490; out_of_scope median 0,010. Chunk dưới 0,5 nằm ở vùng "được giữ lại nhưng không phải nguồn trả lời".

Ca thực tế cd_008: hai nhánh ra cùng 7 chunk đầu theo đúng thứ tự, một nhánh kèm thêm 1 chunk đuôi score thấp. So bằng `==` trên cả list thì case rơi nhầm vào nhóm "condense gây regression" — tức đổ cho condense một lỗi thực ra sinh ở tầng generate/hallucination.

---

## 7. Cấu trúc artifact (một bản ghi cho mỗi case)

```json
{
  "id": "cd_002",
  "category": "pronoun_reference",
  "history": [...],
  "query": "Cái đó áp dụng cho nhân viên thử việc không?",
  "thinking_on":  {"rewrite": "...", "condense_latency_ms": 4800, "e2e_latency_ms": 21000,
                   "retrieved_ids": [], "answerable": true,  "final_correct": true,
                   "escalated": false, "needs_clarification": false, "failure_mode": null},
  "thinking_off": {"rewrite": "...", "condense_latency_ms": 380,  "e2e_latency_ms": 11000,
                   "retrieved_ids": [], "answerable": false, "final_correct": false,
                   "escalated": true,  "needs_clarification": false, "failure_mode": "reference_loss"}
}
```

Báo cáo **không** được dừng ở "OFF đạt 88%". Phải bóc được dạng:

```
OFF làm hỏng 6 case:
  3 reference_loss · 2 reference_misresolution · 1 topic_contamination
Trong đó:
  4 làm retrieval trượt · 3 dẫn tới wrong escalation · 2 sai câu trả lời cuối
```

Đó mới là bằng chứng đủ để quyết định.
