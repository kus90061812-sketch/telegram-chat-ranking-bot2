import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from chat_rank_bot.periods import (
    day_label,
    next_monday_cutoff,
    period_keys,
    previous_week_key,
    week_label,
)


KST = ZoneInfo("Asia/Seoul")


class PeriodTests(unittest.TestCase):
    def test_kst_day_changes_at_midnight(self) -> None:
        before = datetime(2026, 8, 21, 14, 59, 59, tzinfo=timezone.utc)
        after = datetime(2026, 8, 21, 15, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(period_keys(before, KST).day_key, "2026-08-21")
        self.assertEqual(period_keys(after, KST).day_key, "2026-08-22")

    def test_week_changes_monday_at_6pm_kst(self) -> None:
        monday_before = datetime(2026, 8, 24, 17, 59, 59, tzinfo=KST)
        monday_cutoff = datetime(2026, 8, 24, 18, 0, 0, tzinfo=KST)
        self.assertEqual(period_keys(monday_before, KST).week_key, "2026-08-17")
        self.assertEqual(period_keys(monday_cutoff, KST).week_key, "2026-08-24")

    def test_labels(self) -> None:
        self.assertEqual(day_label("2026-08-22"), "8월 22일")
        self.assertEqual(
            week_label("2026-08-31"),
            "8월 31일 18시 ~ 9월 7일 18시",
        )

    def test_previous_week_key_after_monday_reset(self) -> None:
        monday_evening = datetime(2026, 8, 24, 18, 30, tzinfo=KST)
        self.assertEqual(previous_week_key(monday_evening, KST), "2026-08-17")

    def test_next_monday_cutoff(self) -> None:
        monday_before = datetime(2026, 8, 24, 17, 59, tzinfo=KST)
        monday_cutoff = datetime(2026, 8, 24, 18, 0, tzinfo=KST)
        self.assertEqual(
            next_monday_cutoff(monday_before, KST),
            datetime(2026, 8, 24, 18, 0, tzinfo=KST),
        )
        self.assertEqual(
            next_monday_cutoff(monday_cutoff, KST),
            datetime(2026, 8, 31, 18, 0, tzinfo=KST),
        )
