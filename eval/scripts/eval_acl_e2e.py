#!/usr/bin/env python3
"""ACL end-to-end qua agent thật (khác suite `acl` của eval_enterprise_suite.py,
vốn chỉ gọi authorization engine). Mỗi câu chạy bằng identity EMPLOYEE của phòng
hỏi; LEAK khi chunk retrieve hoặc citation nằm ngoài tập file engine cho phép.

Chạy: AGENT_MODE=react python eval/scripts/eval_acl_e2e.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.graph import agent  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.security.authorization import get_authorization_engine  # noqa: E402
from src.security.models import UserContext  # noqa: E402

DATASET = "eval/datasets/eval_department_acl_boundary.json"


async def run_one(i: int, item: dict) -> dict:
    identity = {
        "tenant_id": "nexatech", "user_id": f"eval_acl_{item['user_department']}",
        "department": item["user_department"].upper(), "user_role": "EMPLOYEE", "request_id": f"eval_acl:{i}",
    }
    allowed = set(get_authorization_engine().get_authorized_source_files(UserContext.from_state(identity)))
    state = await agent.ainvoke({"query": item["query"], **identity})
    files = {c.get("source_file") for c in state.get("retrieved_chunks", [])}
    # citation từ bảng định mức (structured_knowledge) không phải file trong registry
    files |= {c.get("source_file") for c in state.get("citations", []) if c.get("category") != "structured_knowledge"}
    leaked = sorted(f for f in files if f and f not in allowed)
    return {
        "i": i, "user": item["user_department"], "target": item["target_sensitive_department"],
        "leaked": leaked, "escalate_reason": state.get("escalate_reason"),
        "access_denied": state.get("access_denied_reason"), "n_files": len(files),
        "response": (state.get("response") or "")[:160],
    }


async def main() -> None:
    items = json.load(open(DATASET, encoding="utf-8"))
    results = []
    for i, item in enumerate(items):
        r = await run_one(i, item)
        results.append(r)
        print(f"[{i:02d}] {'LEAK' if r['leaked'] else 'OK  '} {r['user']:>10} -> {r['target']:<10} "
              f"files={r['n_files']} denied={r['access_denied']} esc={r['escalate_reason']} {r['leaked']}")
    leaks = sum(1 for r in results if r["leaked"])
    mode = get_settings().agent_mode
    print(f"\nAGENT_MODE={mode}: {len(results) - leaks}/{len(results)} không rò rỉ")
    out = f"eval/results/acl_e2e_{mode}_20261109.json"
    json.dump({"mode": mode, "leaks": leaks, "results": results}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
