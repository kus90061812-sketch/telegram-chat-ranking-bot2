import unittest

from chat_rank_bot.formatting import (
    admin_weekly_ranking_message,
    bot_admins_message,
    daily_ranking_message,
    finalized_weekly_ranking_message,
    help_message,
    personal_message,
    weekly_ranking_message,
    excluded_users_message,
)
from chat_rank_bot.storage import BotAdmin, ExcludedUser, PersonalRank, RankEntry


class FormattingTests(unittest.TestCase):
    def test_bot_admins_message_lists_clickable_profiles(self) -> None:
        result = bot_admins_message(
            [BotAdmin(123, "운영자", "manager_user")]
        )
        self.assertIn("추가된 봇 관리자", result)
        self.assertIn(
            '<a href="https://t.me/manager_user">@manager_user</a>',
            result,
        )

    def test_excluded_users_message_lists_clickable_profiles_without_mentions(self) -> None:
        result = excluded_users_message(
            [ExcludedUser(123, "제외회원", "hidden_user")]
        )
        self.assertIn("집계 제외 목록", result)
        self.assertIn('<a href="https://t.me/hidden_user">@hidden_user</a>', result)

    def test_daily_ranking_always_shows_positions_one_to_four(self) -> None:
        entries = [
            RankEntry(1, "기강 & 친구", "test", 1284),
            RankEntry(2, "라온", None, 900),
        ]
        result = daily_ranking_message(entries, "2026-08-22")
        self.assertIn("📅 <b>일일집계</b>", result)
        self.assertIn(
            '1위 - 기강 &amp; 친구 '
            '(<a href="https://t.me/test">@test</a>) [ 1,284회 ]',
            result,
        )
        self.assertIn("2위 - 라온 (아이디 없음) [ 900회 ]", result)
        self.assertIn("3위 - 집계 없음 [ 0회 ]", result)
        self.assertIn("4위 - 집계 없음 [ 0회 ]", result)

    def test_weekly_ranking_contains_fixed_prizes_and_contacts(self) -> None:
        entries = [RankEntry(1, "기강", "TB935", 321)]
        result = weekly_ranking_message(entries, "2026-08-17")
        self.assertIn("📆 <b>주간집계</b>", result)
        self.assertIn(
            '1위 7만 - 기강 '
            '(<a href="https://t.me/TB935">@TB935</a>) [ 321회 ]',
            result,
        )
        self.assertIn("2위 5만 - 집계 없음 [ 0회 ]", result)
        self.assertIn("3위 2만 - 집계 없음 [ 0회 ]", result)
        self.assertIn("4위 1만 - 집계 없음 [ 0회 ]", result)
        self.assertIn(
            "매주 월요일 오후 6시 초기화 및 최종 순위 확정",
            result,
        )
        self.assertNotIn("주간 누적 입금", result)
        self.assertIn(
            '문의 : <a href="https://t.me/zlzl6318">@zlzl6318</a>',
            result,
        )
        self.assertNotIn("tigertk52", result)

    def test_finalized_weekly_ranking_is_clearly_labeled(self) -> None:
        result = finalized_weekly_ranking_message(
            [RankEntry(1, "기강", "TB935", 777)],
            "2026-08-17",
        )
        self.assertIn(
            "🏆 <b>주간 확정 순위</b> · 8월 17일 18시 ~ 24일 18시",
            result,
        )
        self.assertIn("1위 7만 - 기강", result)
        self.assertIn("4위 1만 - 집계 없음 [ 0회 ]", result)

    def test_admin_weekly_ranking_only_contains_positions_five_to_ten(self) -> None:
        entries = [
            RankEntry(position, f"회원{position}", f"user{position}", 110 - position)
            for position in range(1, 11)
        ]
        result = admin_weekly_ranking_message(
            entries,
            "2026-08-24",
            "AXIS & VIP",
        )
        self.assertIn("🔒 <b>관리자 전용 · 주간 5~10위</b>", result)
        self.assertIn(
            "AXIS &amp; VIP · 8월 24일 18시 ~ 31일 18시",
            result,
        )
        self.assertIn("5위 - 회원5", result)
        self.assertIn("10위 - 회원10", result)
        self.assertNotIn("1위 - 회원1", result)
        self.assertNotIn("10만", result)

    def test_usernames_are_regular_profile_links_not_mentions(self) -> None:
        result = daily_ranking_message(
            [RankEntry(1, "회원", "clickable_user", 10)],
            "2026-08-22",
        )
        self.assertIn(
            '<a href="https://t.me/clickable_user">@clickable_user</a>',
            result,
        )
        self.assertNotIn("회원 (@clickable_user)", result)

    def test_personal_message_always_contains_daily_and_weekly_rank(self) -> None:
        result = personal_message(
            PersonalRank(2, 151, 183),
            PersonalRank(4, 891, 1284),
        )
        self.assertIn("📅 일일: <b>151회 · 2위</b>", result)
        self.assertIn("📆 주간: <b>891회 · 4위</b>", result)

    def test_personal_message_says_not_ranked_when_empty(self) -> None:
        result = personal_message(
            PersonalRank(None, 0, 0),
            PersonalRank(None, 0, 0),
        )
        self.assertIn("0회 · 집계 전", result)

    def test_help_hides_admin_commands_from_regular_users(self) -> None:
        result = help_message()
        self.assertIn(".일일순위", result)
        self.assertIn(".주간순위", result)
        self.assertIn(".나", result)
        self.assertNotIn(".관리자순위", result)
        self.assertNotIn(".관리자추가", result)
        self.assertNotIn(".관리자삭제", result)
        self.assertNotIn(".관리자목록", result)
        self.assertNotIn(".제외목록", result)
        self.assertNotIn(".채팅순위", result)

    def test_help_lists_admin_commands_for_bot_admins(self) -> None:
        result = help_message(include_admin=True)
        self.assertIn("🛡 <b>관리자 명령어</b>", result)
        self.assertIn(".관리자순위", result)
        self.assertIn(".관리자추가", result)
        self.assertIn(".관리자삭제", result)
        self.assertIn(".관리자목록", result)
        self.assertIn(".제외", result)
        self.assertIn(".제외해제", result)
        self.assertIn(".제외목록", result)


if __name__ == "__main__":
    unittest.main()
