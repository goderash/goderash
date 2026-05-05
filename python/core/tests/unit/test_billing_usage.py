"""Unit tests for billing/usage.py — quota logic and warning thresholds."""

from __future__ import annotations

import pytest

from goderash_core.billing.usage import is_quota_exceeded, quota_warning_threshold


class TestIsQuotaExceeded:
    def test_returns_false_when_under_quota(self):
        assert is_quota_exceeded(999, 1000) is False

    def test_returns_true_when_at_quota(self):
        assert is_quota_exceeded(1000, 1000) is True

    def test_returns_true_when_over_quota(self):
        assert is_quota_exceeded(1500, 1000) is True

    def test_unlimited_quota_never_exceeded(self):
        assert is_quota_exceeded(10_000_000, -1) is False

    def test_zero_usage_under_quota(self):
        assert is_quota_exceeded(0, 50_000) is False

    def test_zero_quota_immediately_exceeded(self):
        assert is_quota_exceeded(0, 0) is True


class TestQuotaWarningThreshold:
    def test_eighty_percent_of_1000(self):
        assert quota_warning_threshold(1000) == 800

    def test_eighty_percent_of_50000(self):
        assert quota_warning_threshold(50_000) == 40_000

    def test_zero_quota_gives_zero_threshold(self):
        assert quota_warning_threshold(0) == 0

    def test_small_quota_rounds_down(self):
        # 80% of 5 = 4.0 → int(4.0) = 4
        assert quota_warning_threshold(5) == 4
