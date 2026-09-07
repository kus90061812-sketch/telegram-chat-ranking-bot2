import unittest

from chat_rank_bot.chat_settings import (
    get_event_settings,
    get_min_text_length,
    get_ranking_limit,
    save_chat_settings,
    save_event_settings,
    save_ranking_footer,
    save_ranking_settings,
)
from chat_rank_bot.storage import Storage


class ChatSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = Storage("sqlite:///:memory:")
        self.storage.initialize()

    def tearDown(self) -> None:
        self.storage.close()

    def test_defaults_preserve_five_characters_and_top_four_without_preloading_event(self) -> None:
        self.assertEqual(get_min_text_length(self.storage, -100), 5)
        self.assertEqual(get_ranking_limit(self.storage, -100), 4)
        event = get_event_settings(self.storage, -100)
        self.assertEqual(event.event_emoji, "")
        self.assertEqual(event.event_title, "")
        self.assertEqual(event.event_body, "")

    def test_event_settings_are_saved_per_chat(self) -> None:
        save_chat_settings(
            self.storage,
            -100,
            min_text_length=3,
            ranking_limit=12,
            event_emoji="🔥",
            event_title="테스트 이벤트",
            event_body="첫째 줄\n둘째 줄",
        )
        first = get_event_settings(self.storage, -100)
        second = get_event_settings(self.storage, -200)
        self.assertEqual((first.min_text_length, first.ranking_limit), (3, 12))
        self.assertEqual(first.event_body, "첫째 줄\n둘째 줄")
        self.assertEqual((second.min_text_length, second.ranking_limit), (5, 4))
        self.assertEqual(second.event_body, "")

    def test_ranking_save_never_changes_existing_event(self) -> None:
        save_event_settings(
            self.storage,
            -100,
            event_emoji="🎉",
            event_title="지금 진행 중인 이벤트",
            event_body="현재 내용\n그대로 유지",
        )
        save_ranking_settings(
            self.storage,
            -100,
            min_text_length=4,
            ranking_limit=10,
        )
        event = get_event_settings(self.storage, -100)
        self.assertEqual(event.event_emoji, "🎉")
        self.assertEqual(event.event_title, "지금 진행 중인 이벤트")
        self.assertEqual(event.event_body, "현재 내용\n그대로 유지")

    def test_event_save_never_changes_ranking_settings(self) -> None:
        save_ranking_settings(self.storage, -100, min_text_length=7, ranking_limit=15)
        save_event_settings(
            self.storage,
            -100,
            event_emoji="🎲",
            event_title="새 이벤트",
            event_body="오후 6시에 저장",
        )
        self.assertEqual(get_min_text_length(self.storage, -100), 7)
        self.assertEqual(get_ranking_limit(self.storage, -100), 15)


    def test_ranking_footer_defaults_to_current_text_and_saves_per_chat(self) -> None:
        current = get_event_settings(self.storage, -100)
        self.assertEqual(
            current.ranking_footer,
            "매주 월요일 오후 6시 초기화 및 최종 순위 확정\n문의 : @zlzl6318",
        )
        save_ranking_footer(
            self.storage,
            -100,
            ranking_footer="매주 화요일 오후 7시 마감\n문의 : @new_manager",
        )
        changed = get_event_settings(self.storage, -100)
        untouched = get_event_settings(self.storage, -200)
        self.assertEqual(
            changed.ranking_footer,
            "매주 화요일 오후 7시 마감\n문의 : @new_manager",
        )
        self.assertEqual(
            untouched.ranking_footer,
            "매주 월요일 오후 6시 초기화 및 최종 순위 확정\n문의 : @zlzl6318",
        )

    def test_invalid_range_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            save_ranking_settings(
                self.storage,
                -100,
                min_text_length=0,
                ranking_limit=10,
            )


if __name__ == "__main__":
    unittest.main()
