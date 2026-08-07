.PHONY: run test lint format typecheck check clean eval-check eval-retrieval eval-agent eval-router remap-qrels eval-heldout

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

check: lint format test eval-check

# Kiểm tra bộ eval còn khớp với chunk hiện tại (không gọi API).
# Chạy sau MỌI lần đổi cấu hình chunker hoặc rebuild data/chunks.
eval-check:
	python eval/scripts/check_dataset_integrity.py

# Map lại qrel theo chunk mới sau khi re-chunk (dùng anchor text, không LLM).
remap-qrels:
	python scripts/rag_pipeline/remap_qrels.py

# Eval mặc định chạy trên split dev — held-out phải giữ sạch, chỉ chạy khi cần số cuối.
eval-retrieval:
	python eval/scripts/eval_retrieval.py --dataset eval/datasets/retrieval_eval_set.json 		--qrels eval/datasets/retrieval_eval_qrels.json --min-relevance 2 --split dev --top-k 25 --rerank

eval-router:
	python eval/scripts/eval_router.py

eval-agent:
	python eval/scripts/eval_agent.py

# Chạy ĐÚNG MỘT LẦN sau khi Phase A đã chốt — tập held-out chỉ có giá trị nếu
# không bị dùng để tune. Không chạy lại rồi chỉnh code dựa trên kết quả này.
eval-heldout:
	python eval/scripts/eval_agent.py --dataset eval/datasets/qa_heldout_set.json --out eval/results/heldout_agent_report.json
	python eval/scripts/eval_retrieval.py --dataset eval/datasets/retrieval_eval_set.json 		--qrels eval/datasets/retrieval_eval_qrels.json --min-relevance 2 --split heldout --top-k 25 --rerank 		--out eval/results/heldout_retrieval_report.json

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
