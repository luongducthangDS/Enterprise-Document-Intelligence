# Product dataset evaluation contract

Bộ Product có owner và eval riêng, không dùng chung kết quả HR để kết luận chất lượng retrieval.

## Artifacts

- `eval/datasets/product_retrieval_eval_set.json`: 18 câu in-scope + 1 out-of-scope, có `department`, `owner`, `feature` và nguồn kỳ vọng. Ba ca `product_017`–`product_019` là hard-demo bắt buộc tổng hợp đa tài liệu và bao phủ bảng, biểu đồ, PDF scan ảnh.
- `eval/datasets/product_retrieval_qrels.json`: nhãn chunk relevance (2 = highly relevant, 1 = supporting).
- `eval/datasets/product_guardrail_set.json`: 5 hội thoại kiểm tra owner attribution, prompt injection, cross-feature drift và out-of-scope.
- `data/metadata/product_document_registry.csv`: registry generated, mỗi tài liệu bắt buộc có `department=Product` và `owner`.

## Owner contract

`owner` là accountable owner của tài liệu/dataset, không phải một người được nhắc trong action item. Owner được truyền vào `ChunkMetadata.owner`, được index cùng chunk và phải xuất hiện trong registry.

## Hard-demo coverage contract

Mỗi ca có `demo_priority=true` phải:

- dùng ít nhất 3 tài liệu nguồn;
- có `reasoning=multi_document_synthesis`;
- khai báo `modalities` để chứng minh coverage;
- toàn bộ nhóm phải bao phủ ít nhất một bảng, một biểu đồ và một PDF scan ảnh.

## Chạy kiểm tra offline

```powershell
python eval/scripts/eval_product_retrieval.py --lexical
python eval/scripts/check_product_dataset_integrity.py
```

`--lexical` không gọi API, dùng chunks local để kiểm tra qrels và báo cáo Recall@K. Khi Chroma Cloud đã được index, bỏ `--lexical` để đo dense retrieval thật.

Guardrail chạy qua harness hiện có:

```powershell
python eval/scripts/eval_guardrail.py --dataset eval/datasets/product_guardrail_set.json
```
