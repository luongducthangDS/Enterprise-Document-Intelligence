"""Thống kê dùng chung cho các script eval.

Lý do tồn tại: với n = 100 câu, sai số của một tỉ lệ khoảng ±8-10 điểm. Nếu chỉ
báo con số trần (vd "75.7%") thì không phân biệt được cải thiện thật với dao
động ngẫu nhiên, và mọi so sánh trước/sau đều vô nghĩa. Ba hàm ở đây trả lời
đúng 3 câu hỏi:

- `bootstrap_ci`  — con số này dao động trong khoảng nào?
- `paired_bootstrap` — chênh lệch giữa 2 cấu hình có thật không, hay là nhiễu?
  (dùng paired: cùng tập câu hỏi, nên so từng câu với nhau mạnh hơn nhiều so
  với so 2 giá trị trung bình rời rạc)
- `cohens_kappa` — hai người/model chấm có đồng thuận không, sau khi trừ đi phần
  đồng thuận do may rủi.
"""

import random


def bootstrap_ci(
    values: list[float],
    n_resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 20260806,
) -> tuple[float, float, float]:
    """Trả về (điểm ước lượng, cận dưới, cận trên) của giá trị trung bình."""
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    point = sum(values) / n
    means = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((1 - confidence) / 2 * n_resamples)]
    hi = means[min(n_resamples - 1, int((1 + confidence) / 2 * n_resamples))]
    return point, lo, hi


def paired_bootstrap(
    values_a: list[float],
    values_b: list[float],
    n_resamples: int = 2000,
    seed: int = 20260806,
) -> dict:
    """So 2 cấu hình trên CÙNG tập câu hỏi (values_a[i] và values_b[i] là điểm
    của cùng câu i). Trả về chênh lệch trung bình, khoảng tin cậy của chênh
    lệch, và p-value hai phía.

    `significant = True` khi khoảng tin cậy không chứa 0 — tức chênh lệch khó
    giải thích bằng may rủi.
    """
    if len(values_a) != len(values_b):
        raise ValueError(f"hai tập điểm không cùng độ dài: {len(values_a)} vs {len(values_b)}")
    if not values_a:
        return {"diff": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_value": 1.0, "significant": False}

    rng = random.Random(seed)
    n = len(values_a)
    diffs = [b - a for a, b in zip(values_a, values_b)]
    observed = sum(diffs) / n

    boot = []
    for _ in range(n_resamples):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        boot.append(sum(sample) / n)
    boot.sort()
    ci_low = boot[int(0.025 * n_resamples)]
    ci_high = boot[min(n_resamples - 1, int(0.975 * n_resamples))]

    # p-value: tỉ lệ mẫu bootstrap nằm ở phía đối diện với chênh lệch quan sát.
    if observed >= 0:
        p = sum(1 for d in boot if d <= 0) / n_resamples
    else:
        p = sum(1 for d in boot if d >= 0) / n_resamples
    p = min(1.0, 2 * p)

    return {
        "diff": round(observed, 4),
        "ci_low": round(ci_low, 4),
        "ci_high": round(ci_high, 4),
        "p_value": round(p, 4),
        "significant": not (ci_low <= 0 <= ci_high),
    }


def cohens_kappa(labels_a: list, labels_b: list) -> float:
    """Độ đồng thuận giữa 2 người/model chấm, đã trừ phần đồng thuận ngẫu nhiên.

    Quy ước diễn giải thường dùng: < 0.2 rất kém, 0.2-0.4 yếu, 0.4-0.6 trung
    bình, 0.6-0.8 khá, > 0.8 tốt. Dưới 0.6 thì KHÔNG nên dùng nhãn tự động thay
    cho nhãn người.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError(f"hai tập nhãn không cùng độ dài: {len(labels_a)} vs {len(labels_b)}")
    n = len(labels_a)
    if n == 0:
        return 0.0

    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    categories = set(labels_a) | set(labels_b)
    expected = sum(
        (labels_a.count(c) / n) * (labels_b.count(c) / n) for c in categories
    )
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def format_ci(point: float, lo: float, hi: float, as_percent: bool = True) -> str:
    if as_percent:
        return f"{point:.1%} [{lo:.1%}–{hi:.1%}]"
    return f"{point:.3f} [{lo:.3f}–{hi:.3f}]"
