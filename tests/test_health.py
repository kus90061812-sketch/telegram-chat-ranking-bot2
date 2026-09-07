import http.cookiejar
import unittest
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from chat_rank_bot.health import start_health_server
from chat_rank_bot.storage import Storage


class HealthServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = Storage("sqlite:///:memory:")
        self.storage.initialize()
        self.storage.register_chat(-100, "테스트 소통방", datetime.now(timezone.utc))
        self.server = start_health_server(
            0,
            storage=self.storage,
            admin_username="admin",
            admin_password="secret123",
        )
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.storage.close()

    def _logged_in_opener(self):
        jar = http.cookiejar.CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))
        login = Request(
            f"{self.base_url}/login",
            data=urlencode({"username": "admin", "password": "secret123"}).encode(),
            method="POST",
        )
        with opener.open(login, timeout=2) as response:
            self.assertEqual(response.status, 200)
        return opener

    def test_health_and_legacy_paths_stay_compatible(self) -> None:
        for path in ("/health", "/old-admin-path"):
            with urlopen(f"{self.base_url}{path}", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"OK")

    def test_root_shows_login_page(self) -> None:
        with urlopen(f"{self.base_url}/", timeout=2) as response:
            body = response.read().decode("utf-8")
        self.assertIn("채팅 순위 봇 관리자", body)
        self.assertIn("관리자 아이디", body)

    def test_ranking_save_does_not_touch_event(self) -> None:
        opener = self._logged_in_opener()
        self.storage.set_setting("chat:-100:event_emoji", "🎉")
        self.storage.set_setting("chat:-100:event_title", "현재 이벤트")
        self.storage.set_setting("chat:-100:event_body", "지금 내용 유지")

        save = Request(
            f"{self.base_url}/save",
            data=urlencode(
                {
                    "chat_id": "-100",
                    "section": "ranking",
                    "min_text_length": "4",
                    "ranking_limit": "10",
                }
            ).encode(),
            method="POST",
        )
        with opener.open(save, timeout=2) as response:
            body = response.read().decode("utf-8")
            self.assertIn("이벤트 내용은 변경하지 않았습니다", body)

        self.assertEqual(self.storage.get_setting("chat:-100:min_text_length"), "4")
        self.assertEqual(self.storage.get_setting("chat:-100:ranking_limit"), "10")
        self.assertEqual(self.storage.get_setting("chat:-100:event_title"), "현재 이벤트")
        self.assertEqual(self.storage.get_setting("chat:-100:event_body"), "지금 내용 유지")

    def test_event_save_preserves_newlines_and_updates_only_event(self) -> None:
        opener = self._logged_in_opener()
        self.storage.set_setting("chat:-100:min_text_length", "7")
        self.storage.set_setting("chat:-100:ranking_limit", "15")
        save = Request(
            f"{self.base_url}/save",
            data=urlencode(
                {
                    "chat_id": "-100",
                    "section": "event",
                    "event_emoji": "🎰",
                    "event_title": "매주 월요일 6시 바카라 꿍 이벤트",
                    "event_body": "채팅 갯수 2222개 달성 시 참여가능\n선착순 5명 (각 2만원씩 지급)",
                }
            ).encode(),
            method="POST",
        )
        with opener.open(save, timeout=2) as response:
            body = response.read().decode("utf-8")
            self.assertIn("이벤트 저장 완료", body)
            self.assertIn("2222개 달성", body)

        self.assertEqual(self.storage.get_setting("chat:-100:min_text_length"), "7")
        self.assertEqual(self.storage.get_setting("chat:-100:ranking_limit"), "15")
        self.assertEqual(self.storage.get_setting("chat:-100:event_emoji"), "🎰")
        self.assertEqual(
            self.storage.get_setting("chat:-100:event_body"),
            "채팅 갯수 2222개 달성 시 참여가능\n선착순 5명 (각 2만원씩 지급)",
        )


    def test_footer_save_preserves_newlines_and_does_not_touch_other_settings(self) -> None:
        opener = self._logged_in_opener()
        self.storage.set_setting("chat:-100:min_text_length", "5")
        self.storage.set_setting("chat:-100:ranking_limit", "4")
        self.storage.set_setting("chat:-100:event_title", "현재 이벤트")
        save = Request(
            f"{self.base_url}/save",
            data=urlencode(
                {
                    "chat_id": "-100",
                    "section": "footer",
                    "ranking_footer": "매주 화요일 오후 7시 마감\n문의 : @new_manager",
                }
            ).encode(),
            method="POST",
        )
        with opener.open(save, timeout=2) as response:
            body = response.read().decode("utf-8")
            self.assertIn("순위 하단 안내문구 저장 완료", body)

        self.assertEqual(
            self.storage.get_setting("chat:-100:ranking_footer"),
            "매주 화요일 오후 7시 마감\n문의 : @new_manager",
        )
        self.assertEqual(self.storage.get_setting("chat:-100:min_text_length"), "5")
        self.assertEqual(self.storage.get_setting("chat:-100:ranking_limit"), "4")
        self.assertEqual(self.storage.get_setting("chat:-100:event_title"), "현재 이벤트")

    def test_head_returns_ok(self) -> None:
        request = Request(f"{self.base_url}/health", method="HEAD")
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
