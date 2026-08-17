import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "eval", "scripts"))

import pytest  # noqa: E402
from _stats import bootstrap_ci, cohens_kappa, paired_bootstrap  # noqa: E402


class TestBootstrapCI:
    def test_point_estimate_is_the_mean(self):
        point, lo, hi = bootstrap_ci([1.0, 0.0, 1.0, 1.0])
        assert point == pytest.approx(0.75)
        assert lo <= point <= hi

    def test_interval_narrows_as_sample_grows(self):
        _, lo_small, hi_small = bootstrap_ci([1.0, 0.0] * 10)
        _, lo_big, hi_big = bootstrap_ci([1.0, 0.0] * 500)
        assert (hi_big - lo_big) < (hi_small - lo_small)

    def test_constant_values_give_zero_width_interval(self):
        point, lo, hi = bootstrap_ci([1.0] * 50)
        assert (point, lo, hi) == (1.0, 1.0, 1.0)

    def test_empty_input_does_not_crash(self):
        assert bootstrap_ci([]) == (0.0, 0.0, 0.0)


class TestPairedBootstrap:
    def test_detects_consistent_improvement(self):
        a = [0.0] * 40
        b = [1.0] * 40
        result = paired_bootstrap(a, b)
        assert result["diff"] == pytest.approx(1.0)
        assert result["significant"] is True

    def test_reports_noise_as_not_significant(self):
        """Chênh lệch nhỏ trên mẫu nhỏ phải bị coi là nhiễu — đây chính là lý do
        cần paired test thay vì so 2 con số trung bình."""
        a = [1.0, 0.0] * 15
        b = [1.0, 0.0] * 14 + [1.0, 1.0]
        result = paired_bootstrap(a, b)
        assert result["significant"] is False
        assert result["p_value"] > 0.05

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError, match="không cùng độ dài"):
            paired_bootstrap([1.0, 0.0], [1.0])


class TestCohensKappa:
    def test_perfect_agreement(self):
        assert cohens_kappa([2, 1, 0, 2], [2, 1, 0, 2]) == pytest.approx(1.0)

    def test_chance_level_agreement_is_near_zero(self):
        a = [1, 0] * 25
        b = [1, 1, 0, 0] * 12 + [1, 0]
        assert abs(cohens_kappa(a, b)) < 0.3

    def test_disagreement_gives_negative_kappa(self):
        assert cohens_kappa([1, 1, 0, 0], [0, 0, 1, 1]) < 0

    def test_single_category_on_both_sides(self):
        """Cả hai cùng gán 1 nhãn duy nhất: đồng thuận quan sát = 1 nhưng đồng
        thuận kỳ vọng cũng = 1, kappa không xác định — quy ước trả về 1.0."""
        assert cohens_kappa([2, 2, 2], [2, 2, 2]) == 1.0
