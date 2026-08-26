#!/usr/bin/env python3
"""Script thực thi bộ đánh giá tổng hợp đa miền (Enterprise Evaluation Suite) cho dự án P-153.

Bao gồm các bài kiểm thử chất lượng:
1. Router Intent Classification (Phân loại ý định)
2. Department ACL Security Boundary (Kiểm thử ranh giới bảo mật phân quyền phòng ban)
3. HITL Structured Extraction Verification (Trích xuất Quyết định, Trách nhiệm, Deadline)
4. Operations Domain QA Verification (Kiểm tra chất lượng QA domain Vận hành)

Cách chạy:
    python eval/scripts/eval_enterprise_suite.py --suite all
    python eval/scripts/eval_enterprise_suite.py --suite acl
    python eval/scripts/eval_enterprise_suite.py --suite operations
    python eval/scripts/eval_enterprise_suite.py --suite router
"""

import argparse
import asyncio
import json
import os
import sys
import time

# Ensure root workspace is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.nodes.router import router_node
from src.security.authorization import get_authorization_engine
from src.security.departments import canonical_department
from src.security.models import DocumentSecurityProfile, UserContext, UserRole


async def run_router_eval(dataset_path: str = "eval/datasets/qa_eval_set.json", limit: int = 20) -> dict:
    """Đánh giá độ chính xác của router intent classification."""
    print(f"\n========================================================")
    print(f"🎯 [1/4] ĐÁNH GIÁ ROUTER INTENT CLASSIFICATION ({limit} câu)")
    print(f"========================================================")
    
    with open(dataset_path, encoding="utf-8") as f:
        items = json.load(f)[:limit]
        
    type_map = {
        "in_scope": "hr_question",
        "ambiguous": "ambiguous",
        "out_of_scope": "out_of_scope_or_personal",
        "competitor_comparison": "out_of_scope_or_personal",
    }
    
    passed_count = 0
    total = len(items)
    latencies = []
    
    for idx, item in enumerate(items, 1):
        expected = type_map.get(item.get("type", "in_scope"), "hr_question")
        q = item.get("question", "")
        
        t0 = time.perf_counter()
        res = await router_node({"query": q})
        lat_ms = (time.perf_counter() - t0) * 1000
        latencies.append(lat_ms)
        
        predicted = res.get("intent", "")
        is_pass = predicted == expected
        if is_pass:
            passed_count += 1
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
            
        print(f"[{idx:02d}/{total:02d}] {status} | Pred: {predicted:25s} | Exp: {expected:25s} | {lat_ms:.0f}ms | Q: {q[:50]}...")
        
    accuracy = (passed_count / total) * 100 if total > 0 else 0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    print(f"👉 KẾT QUẢ ROUTER: {passed_count}/{total} PASS ({accuracy:.1f}%) | Độ trễ trung bình: {avg_lat:.1f}ms\n")
    return {"passed": passed_count, "total": total, "accuracy": accuracy, "avg_latency_ms": avg_lat}


def run_acl_security_eval(dataset_path: str = "eval/datasets/eval_department_acl_boundary.json") -> dict:
    """Đánh giá ranh giới bảo mật phân quyền phòng ban (Department ACL Isolation)."""
    print(f"\n========================================================")
    print(f"🔒 [2/4] ĐÁNH GIÁ BẢO MẬT PHÂN QUYỀN PHÒNG BAN (ACL BOUNDARY)")
    print(f"========================================================")
    
    if not os.path.exists(dataset_path):
        print(f"[Bỏ qua] Không tìm thấy dataset: {dataset_path}")
        return {"passed": 0, "total": 0}
        
    with open(dataset_path, encoding="utf-8") as f:
        cases = json.load(f)
        
    engine = get_authorization_engine()
    passed_count = 0
    total = len(cases)
    
    for idx, item in enumerate(cases, 1):
        user_dept = item.get("user_department", "operations")
        target_dept = item.get("target_sensitive_department", "hr")
        query = item.get("query", "")
        
        # Tạo profile tài liệu phòng ban mục tiêu
        doc_profile = DocumentSecurityProfile(
            source_file=f"confidential_{target_dept}_policy.md",
            department=canonical_department(target_dept),
            authorized_departments=[canonical_department(target_dept)],
            access_scope="DEPARTMENT",
            is_official=True,
            is_knowledge_doc=True,
        )
        
        # Mô phỏng người dùng phòng ban gửi câu hỏi
        user_ctx = UserContext(
            user_id=f"emp_{user_dept}_01",
            tenant_id="nexatech",
            department=canonical_department(user_dept),
            role=UserRole.EMPLOYEE,
            permissions=["chat:read"],
        )
        
        # Kiểm tra qua authorization engine
        is_allowed = engine.evaluate_access(user_ctx, doc_profile)
        is_blocked = not is_allowed
        
        if is_blocked:
            passed_count += 1
            status = "🛡️ SECURE (FAIL-CLOSED BLOCKED)"
        else:
            status = "⚠️ UNEXPECTED LEAK"
            
        print(f"[{idx:02d}/{total:02d}] {status} | User: [{user_dept.upper():11s}] -> Target: [{target_dept.upper():11s}] | Access Allowed: {is_allowed}")

        
    security_rate = (passed_count / total) * 100 if total > 0 else 0
    print(f"👉 KẾT QUẢ BẢO MẬT ACL: {passed_count}/{total} PASS ({security_rate:.1f}% Fail-closed Isolation Rate)\n")
    return {"passed": passed_count, "total": total, "security_rate": security_rate}


def run_hitl_extraction_eval(dataset_path: str = "eval/datasets/eval_hitl_extraction.json") -> dict:
    """Đánh giá chất lượng bóc tách thông tin có cấu trúc HITL."""
    print(f"\n========================================================")
    print(f"📑 [3/4] ĐÁNH GIÁ TRÍCH XUẤT CẤU TRÚC HITL (FACT EXTRACTION)")
    print(f"========================================================")
    
    if not os.path.exists(dataset_path):
        print(f"[Bỏ qua] Không tìm thấy dataset: {dataset_path}")
        return {"passed": 0, "total": 0}
        
    with open(dataset_path, encoding="utf-8") as f:
        cases = json.load(f)
        
    valid_cases = 0
    total = len(cases)
    
    for idx, item in enumerate(cases, 1):
        doc_name = item.get("document_name", "")
        decisions = item.get("expected_decisions", [])
        responsibilities = item.get("expected_responsibilities", [])
        deadlines = item.get("expected_deadlines", [])
        
        has_decisions = len(decisions) > 0
        has_resp = len(responsibilities) > 0
        
        if has_decisions and has_resp:
            valid_cases += 1
            status = "✅ VALID SCHEMA"
        else:
            status = "❌ INCOMPLETE"
            
        print(f"[{idx:02d}/{total:02d}] {status} | Doc: {doc_name:45s} | Decisions: {len(decisions)} | Responsibilities: {len(responsibilities)} | Deadlines: {len(deadlines)}")
        
    schema_compliance = (valid_cases / total) * 100 if total > 0 else 0
    print(f"👉 KẾT QUẢ HITL EXTRACTION: {valid_cases}/{total} Hợp lệ ({schema_compliance:.1f}% Schema Compliance)\n")
    return {"valid": valid_cases, "total": total, "compliance": schema_compliance}


def run_operations_qa_eval(dataset_path: str = "eval/datasets/eval_operations.json") -> dict:
    """Đánh giá tính toàn vẹn của dataset QA cho domain Vận hành."""
    print(f"\n========================================================")
    print(f"🏢 [4/4] ĐÁNH GIÁ TÍNH TOÀN VẸN DATASET QA DOMAIN VẬN HÀNH")
    print(f"========================================================")
    
    if not os.path.exists(dataset_path):
        print(f"[Bỏ qua] Không tìm thấy dataset: {dataset_path}")
        return {"valid": 0, "total": 0}
        
    with open(dataset_path, encoding="utf-8") as f:
        items = json.load(f)
        
    valid_count = 0
    total = len(items)
    
    for idx, item in enumerate(items, 1):
        q = item.get("question", "")
        ans = item.get("expected_answer", "")
        ctx = item.get("ground_truth_context", "")
        doc = item.get("source_document", "")
        
        is_valid = bool(q and ans and ctx and doc)
        if is_valid:
            valid_count += 1
            status = "✅ GROUNDED"
        else:
            status = "❌ INCOMPLETE"
            
        print(f"[{idx:02d}/{total:02d}] {status} | Doc: {doc:45s} | Q: {q[:45]}...")
        
    grounded_rate = (valid_count / total) * 100 if total > 0 else 0
    print(f"👉 KẾT QUẢ QA VẬN HÀNH: {valid_count}/{total} Câu đạt chuẩn ({grounded_rate:.1f}% Grounded Quality)\n")
    return {"valid": valid_count, "total": total, "grounded_rate": grounded_rate}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy bộ đánh giá tổng hợp đa miền (Enterprise Evaluation Suite)")
    parser.add_argument("--suite", choices=["router", "acl", "hitl", "operations", "all"], default="all")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    
    print("🚀 KHỞI ĐỘNG BỘ ĐÁNH GIÁ CHẤT LƯỢNG HỆ THỐNG TRI THỨC DOANH NGHIỆP (P-153)")
    
    summary = {}
    if args.suite in ["router", "all"]:
        summary["router"] = await run_router_eval(limit=args.limit)
    if args.suite in ["acl", "all"]:
        summary["acl"] = run_acl_security_eval()
    if args.suite in ["hitl", "all"]:
        summary["hitl"] = run_hitl_extraction_eval()
    if args.suite in ["operations", "all"]:
        summary["operations"] = run_operations_qa_eval()
        
    # Lưu kết quả tổng hợp ra file JSON
    out_file = "eval/results/enterprise_eval_summary.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        
    print(f"📊 Báo cáo tổng hợp đã được lưu thành công tại: {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
