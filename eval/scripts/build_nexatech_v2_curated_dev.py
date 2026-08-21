#!/usr/bin/env python3
"""Build a transparent, single-reviewer NexaTech v2 retrieval dev set.

This is intentionally separate from ``finalize_nexatech_v2_qrels.py``.  The
finalizer is the release path and requires every pooled candidate to receive an
independent human label.  This script records a smaller AI-assisted semantic
review that is useful for development, but must not be presented as release
ground truth.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

# Relevance 2 means that the chunk contains evidence needed to answer safely.
# Relevance 1 means useful context that is not answer-bearing by itself.
CURATED: dict[str, dict] = {
    "nxv2_001_l1": {
        "labels": {
            "01_chinh-sach-lam-them-gio-OT::0005": 2,
            "01_chinh-sach-lam-them-gio-OT::0010": 2,
        },
        "reason": "Both the limits section and FAQ state the monthly OT limit.",
    },
    "nxv2_002_l1": {
        "labels": {
            "01_chinh-sach-lam-them-gio-OT::0006": 2,
            "01_chinh-sach-lam-them-gio-OT::0010": 2,
        },
        "reason": "The pay table and FAQ directly distinguish Sunday and holiday OT rates.",
    },
    "nxv2_003_l1": {
        "labels": {"01_chinh-sach-lam-them-gio-OT::0007": 2},
        "reason": "The approval procedure requires registration at least one working day in advance.",
    },
    "nxv2_003_l2": {
        "labels": {
            "01_chinh-sach-lam-them-gio-OT::0008": 2,
            "01_chinh-sach-lam-them-gio-OT::0010": 2,
            "01_chinh-sach-lam-them-gio-OT::0007": 1,
        },
        "reason": "The recording rule and FAQ answer unregistered voluntary overtime directly.",
    },
    "nxv2_004_l1": {
        "labels": {"01_chinh-sach-lam-them-gio-OT::0007": 2},
        "reason": "The procedure names form HR-FRM-OT-01 and the HRIS approval flow.",
    },
    "nxv2_016_l1": {
        "labels": {
            "04_quy-trinh-offboarding::0004": 2,
            "04_quy-trinh-offboarding::0011": 2,
        },
        "reason": "The notice-period section and FAQ state the indefinite-contract deadline.",
    },
    "nxv2_017_l1": {
        "labels": {
            "04_quy-trinh-offboarding::0006": 2,
            "04_quy-trinh-offboarding::0009": 2,
        },
        "reason": "The handover step lists work/assets and the RACI identifies the accountable manager.",
    },
    "nxv2_019_l1": {
        "labels": {
            "05_chinh-sach-lam-viec-tu-xa::0007": 2,
            "05_chinh-sach-lam-viec-tu-xa::0031": 2,
            "05_chinh-sach-lam-viec-tu-xa::0005": 1,
        },
        "reason": "The Hybrid 3-2 section and FAQ state the weekly WFH maximum.",
    },
    "nxv2_020_l1": {
        "labels": {"05_chinh-sach-lam-viec-tu-xa::0006": 2},
        "reason": "The exception rule supplies the age condition, approval path, and duration limits needed for a conditional guide.",
    },
    "nxv2_023_l1": {
        "labels": {
            "06_chinh-sach-dao-tao-phat-trien::0004": 2,
            "06_chinh-sach-dao-tao-phat-trien::0005": 2,
        },
        "reason": "The budget table and proposal process establish available support and its approval conditions.",
    },
    "nxv2_024_l2": {
        "labels": {
            "06_chinh-sach-dao-tao-phat-trien::0006": 2,
            "06_chinh-sach-dao-tao-phat-trien::0009": 2,
        },
        "reason": "The commitment rule and FAQ directly cover repayment after early departure.",
    },
    "nxv2_024_l3": {
        "labels": {
            "06_chinh-sach-dao-tao-phat-trien::0006": 2,
            "06_chinh-sach-dao-tao-phat-trien::0009": 1,
        },
        "reason": "The policy provides the repayment formula; personal inputs still require handoff.",
    },
    "nxv2_026_l1": {
        "labels": {
            "07_chinh-sach-nghi-phep::0004": 2,
            "07_chinh-sach-nghi-phep::0023": 2,
            "07_chinh-sach-nghi-phep::0005": 1,
        },
        "reason": "The annual-leave table and FAQ state standard entitlement; seniority is supporting context.",
    },
    "nxv2_029_l1": {
        "labels": {
            "07_chinh-sach-nghi-phep::0003": 2,
            "07_chinh-sach-nghi-phep::0008": 2,
            "07_chinh-sach-nghi-phep::0006": 2,
        },
        "reason": "Definitions and the paid/unpaid rules directly support the comparison.",
    },
    "nxv2_030_l1": {
        "labels": {
            "07_chinh-sach-nghi-phep::0019": 2,
            "07_chinh-sach-nghi-phep::0023": 2,
            "07_chinh-sach-nghi-phep::0024": 2,
            "07_chinh-sach-nghi-phep::0020": 1,
        },
        "reason": "The carry-over rule and FAQs state the five-day cap and treatment of the excess.",
    },
    "nxv2_030_l2": {
        "labels": {
            "07_chinh-sach-nghi-phep::0021": 2,
            "07_chinh-sach-nghi-phep::0006": 1,
        },
        "reason": "The termination rule directly requires payment for unused annual leave.",
    },
    "nxv2_033_l1": {
        "labels": {
            "08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen::0012": 2,
            "08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen::0019": 1,
        },
        "reason": "The dependent-coverage section directly lists eligible spouse and children.",
    },
    "nxv2_034_l2": {
        "labels": {
            "08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen::0014": 2,
            "08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen::0015": 1,
        },
        "reason": "The reimbursement section lists the 30-day deadline, documents, and submission route.",
    },
    "nxv2_035_l1": {
        "labels": {
            "10_chinh-sach-an-toan-ve-sinh-lao-dong::0007": 2,
            "10_chinh-sach-an-toan-ve-sinh-lao-dong::0009": 2,
            "10_chinh-sach-an-toan-ve-sinh-lao-dong::0004": 1,
        },
        "reason": "The answer is in the safety policy, not the source predicted by the imported test case.",
    },
    "nxv2_036_l1": {
        "labels": {"09_chinh-sach-bao-hiem-xa-hoi-bat-buoc::0005": 2},
        "reason": "The contribution table directly lists employee deductions and rates.",
    },
    "nxv2_039_l1": {
        "labels": {
            "10_chinh-sach-an-toan-ve-sinh-lao-dong::0007": 2,
            "10_chinh-sach-an-toan-ve-sinh-lao-dong::0004": 1,
            "10_chinh-sach-an-toan-ve-sinh-lao-dong::0009": 2,
        },
        "reason": "The frequency is explicit and the employer-responsibility section identifies NexaTech as organizer.",
    },
    "nxv2_040_l1": {
        "labels": {
            "10_chinh-sach-an-toan-ve-sinh-lao-dong::0006": 2,
            "10_chinh-sach-an-toan-ve-sinh-lao-dong::0009": 2,
            "10_chinh-sach-an-toan-ve-sinh-lao-dong::0008": 1,
        },
        "reason": "The accident procedure gives immediate first aid and reporting steps.",
    },
    "nxv2_043_l1": {
        "labels": {
            "11_chinh-sach-danh-gia-hieu-suat-kpi::0005": 2,
            "11_chinh-sach-danh-gia-hieu-suat-kpi::0008": 1,
        },
        "reason": "The four-step process begins with employee self-evaluation.",
    },
    "nxv2_045_l2": {
        "labels": {
            "11_chinh-sach-danh-gia-hieu-suat-kpi::0004": 2,
            "11_chinh-sach-danh-gia-hieu-suat-kpi::0006": 2,
            "11_chinh-sach-danh-gia-hieu-suat-kpi::0009": 1,
        },
        "reason": "The rating table covers bonus impact and the PIP rule limits when termination may follow.",
    },
    "nxv2_047_l1": {
        "labels": {
            "12_quy-che-cong-tac-phi::0004": 2,
            "12_quy-che-cong-tac-phi::0005": 2,
        },
        "reason": "Separate tables directly cover meal/per-diem and accommodation limits.",
    },
    "nxv2_048_l2": {
        "labels": {"12_quy-che-cong-tac-phi::0006": 2},
        "reason": "The settlement procedure states submission to Accounting within five working days.",
    },
    "nxv2_048_l3": {
        "labels": {
            "12_quy-che-cong-tac-phi::0006": 2,
            "12_quy-che-cong-tac-phi::0003": 1,
        },
        "reason": "The policy requires valid travel evidence but provides no lost-invoice exception, supporting a bounded insufficient-evidence response.",
    },
}


EXCLUDED: dict[str, dict[str, str]] = {
    "nxv2_006_l1": {"kind": "partial_only", "reason": "Interview rounds are documented, but no final candidate approver is identified."},
    "nxv2_007_l1": {"kind": "missing_policy_detail", "reason": "Referral is only named as a sourcing channel; procedure and credit rules are absent."},
    "nxv2_010_l1": {"kind": "missing_policy_detail", "reason": "The onboarding document says an email will list documents but does not provide that list."},
    "nxv2_011_l2": {"kind": "missing_policy_detail", "reason": "No original-versus-notarized-degree rule is present."},
    "nxv2_011_l3": {"kind": "missing_policy_detail", "reason": "No consequence for a late original document is present."},
    "nxv2_012_l1": {"kind": "missing_policy_detail", "reason": "IT preparation is documented, but activation instructions are absent."},
    "nxv2_015_l3": {"kind": "missing_policy_detail", "reason": "Notice periods are documented, but consequences of quitting without notice are not."},
    "nxv2_025_l1": {"kind": "partial_only", "reason": "Annual TNA timing exists, but no specific internal-course registration channel or deadline exists."},
    "nxv2_027_l1": {"kind": "requires_personal_data", "reason": "A personal leave balance cannot be derived from policy text."},
    "nxv2_028_l1": {"kind": "missing_policy_detail", "reason": "The leave policy does not explicitly settle annual leave during probation."},
    "nxv2_030_l3": {"kind": "requires_personal_data", "reason": "Exact payable days require employment dates and the employee's actual leave ledger."},
    "nxv2_037_l1": {"kind": "contract_conflict", "reason": "A pure statutory question conflicts with the current Type-C scope contract."},
    "nxv2_038_l1": {"kind": "requires_personal_data", "reason": "Contribution months require the employee's insurance record."},
    "nxv2_042_l1": {"kind": "missing_policy_detail", "reason": "The policy names annual/monthly/quarterly cycles but gives no calendar months."},
    "nxv2_049_l1": {"kind": "conditional_contract", "reason": "Foreign travel is in scope but no foreign rates or procedures are specified."},
    "nxv2_050_l1": {"kind": "missing_policy_detail", "reason": "The work rules give start time but no lateness threshold in minutes."},
    "nxv2_050_l2": {"kind": "missing_policy_detail", "reason": "No monthly lateness count for a formal warning is specified."},
    "nxv2_054_l1": {"kind": "missing_fixture", "reason": "The corpus has no conflicting HR email fixture to compare with the policy."},
}


def build_outputs(pool: dict) -> tuple[list[dict], dict[str, dict[str, int]], dict]:
    results = pool.get("results") or []
    result_by_id = {result["id"]: result for result in results}
    pool_ids = set(result_by_id)
    curated_ids = set(CURATED)
    excluded_ids = set(EXCLUDED)

    if curated_ids & excluded_ids:
        raise ValueError(f"IDs cannot be both curated and excluded: {sorted(curated_ids & excluded_ids)}")
    if pool_ids != curated_ids | excluded_ids:
        missing = sorted(pool_ids - curated_ids - excluded_ids)
        unknown = sorted((curated_ids | excluded_ids) - pool_ids)
        raise ValueError(f"Review coverage mismatch: missing={missing}, unknown={unknown}")

    dataset: list[dict] = []
    qrels: dict[str, dict[str, int]] = {}
    included_report: list[dict] = []
    excluded_report: list[dict] = []

    for query_id in sorted(curated_ids):
        result = result_by_id[query_id]
        candidates = {candidate["chunk_id"]: candidate for candidate in result.get("candidates", [])}
        labels = CURATED[query_id]["labels"]
        if not labels or not any(score == 2 for score in labels.values()):
            raise ValueError(f"{query_id} must have at least one relevance-2 label")
        invalid_scores = {chunk_id: score for chunk_id, score in labels.items() if score not in (1, 2)}
        if invalid_scores:
            raise ValueError(f"{query_id} has invalid relevance scores: {invalid_scores}")
        missing_chunks = sorted(set(labels) - set(candidates))
        if missing_chunks:
            raise ValueError(f"{query_id} labels chunks outside its candidate pool: {missing_chunks}")
        if result.get("contract_flags"):
            raise ValueError(f"Flagged query {query_id} cannot enter curated dev metrics")

        source_files = sorted({candidates[chunk_id]["source_file"] for chunk_id in labels})
        highly_relevant = sum(score == 2 for score in labels.values())
        item = {
            "id": query_id,
            "query": result["contextual_query"],
            # Keep the final turn for audit/display without populating the
            # runner's ``question`` field.  Retrieval datasets are normalized
            # from ``query``; setting both fields caused follow-up cases to be
            # evaluated without their conversation context.
            "original_question": result["query"],
            "type": "multi_chunk" if highly_relevant > 1 else "single_chunk",
            "category": Path(result["expected_source_file"]).stem,
            "source_files": source_files,
            "expected_states": result["expected_states"],
            "num_relevant": len(labels),
            "num_highly_relevant": highly_relevant,
            "split": "dev",
            "qrel_status": "curated_dev_single_reviewer",
        }
        dataset.append(item)
        qrels[query_id] = dict(sorted(labels.items()))
        included_report.append(
            {
                "id": query_id,
                "question": result["query"],
                "expected_source_file": result["expected_source_file"],
                "labeled_source_files": source_files,
                "reason": CURATED[query_id]["reason"],
            }
        )

    for query_id in sorted(excluded_ids):
        result = result_by_id[query_id]
        excluded_report.append(
            {
                "id": query_id,
                "question": result["query"],
                "expected_states": result["expected_states"],
                "contract_flags": result.get("contract_flags") or [],
                **EXCLUDED[query_id],
            }
        )

    counts = Counter(item["kind"] for item in excluded_report)
    report = {
        "status": "CURATED_DEV_ONLY",
        "reviewer_type": "single_ai_assisted_local_semantic_review",
        "release_ground_truth": False,
        "limitations": [
            "Positive labels were selected from the saved candidate pool by one AI-assisted local review.",
            "Unselected candidates are implicit negatives for this dev benchmark, not independent human judgments.",
            "Release reporting still requires independent human adjudication through finalize_nexatech_v2_qrels.py.",
        ],
        "pool_query_count": len(results),
        "included_query_count": len(dataset),
        "excluded_query_count": len(excluded_report),
        "exclusion_counts": dict(sorted(counts.items())),
        "included": included_report,
        "excluded": excluded_report,
    }
    return dataset, qrels, report


def _write_json(path: str, value: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="eval/results/nexatech_post_mvp_v2_candidate_pool.json")
    parser.add_argument("--dataset-out", default="eval/datasets/nexatech_post_mvp_v2_retrieval_dev.json")
    parser.add_argument("--qrels-out", default="eval/datasets/nexatech_post_mvp_v2_retrieval_dev_qrels.json")
    parser.add_argument("--report-out", default="eval/results/nexatech_post_mvp_v2_adjudication_report.json")
    args = parser.parse_args()

    with open(args.pool, encoding="utf-8") as handle:
        pool = json.load(handle)
    dataset, qrels, report = build_outputs(pool)
    _write_json(args.dataset_out, dataset)
    _write_json(args.qrels_out, qrels)
    _write_json(args.report_out, report)
    print(
        f"included={report['included_query_count']} excluded={report['excluded_query_count']} "
        f"status={report['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
