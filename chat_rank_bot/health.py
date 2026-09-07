from __future__ import annotations

import hashlib
import hmac
import html
import os
import threading
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from .chat_settings import (
    DEFAULT_EVENT_EMOJI,
    get_event_settings,
    save_event_settings,
    save_ranking_footer,
    save_ranking_settings,
)
from .storage import Storage

SESSION_COOKIE = "rank_admin_session"
EMOJI_OPTIONS = [
    "🎲", "🎰", "🔥", "🎉", "🎁", "🏆", "💰", "💸", "💎", "⭐",
    "🚨", "📢", "✅", "⚡", "👑", "🍀", "🎯", "🃏", "💥", "🪙",
]


def _session_token(username: str, password: str) -> str:
    payload = f"{username}|chat-rank-admin-session".encode("utf-8")
    return hmac.new(password.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _page(title: str, body: str) -> bytes:
    document = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, Pretendard, system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:#0e1117; color:#f4f6f8; }}
.wrap {{ width:min(920px, calc(100% - 28px)); margin:36px auto 64px; }}
.card {{ background:#171b22; border:1px solid #2a3039; border-radius:18px; padding:24px; margin-bottom:18px; box-shadow:0 12px 36px rgba(0,0,0,.18); }}
h1 {{ font-size:26px; margin:0 0 8px; }} h2 {{ font-size:18px; margin:0 0 16px; }}
p.muted, .muted {{ color:#9ba5b2; }}
label {{ display:block; font-size:14px; font-weight:700; margin:16px 0 7px; }}
input, select, textarea {{ width:100%; color:#f4f6f8; background:#0f1319; border:1px solid #343b46; border-radius:11px; padding:12px 13px; font:inherit; outline:none; }}
input:focus, select:focus, textarea:focus {{ border-color:#6f87ff; }}
textarea {{ min-height:190px; resize:vertical; line-height:1.55; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
button, .button {{ display:inline-block; border:0; border-radius:11px; padding:12px 18px; background:#6f87ff; color:white; font-weight:800; cursor:pointer; text-decoration:none; }}
.button.secondary {{ background:#29313d; }}
.actions {{ display:flex; gap:10px; align-items:center; margin-top:20px; }}
.notice {{ padding:12px 14px; border-radius:11px; background:#193524; border:1px solid #2d6b43; margin-bottom:16px; }}
.error {{ padding:12px 14px; border-radius:11px; background:#3a1d22; border:1px solid #7b333f; margin-bottom:16px; }}
.preview {{ white-space:pre-wrap; word-break:break-word; background:#0f1319; border:1px solid #343b46; padding:16px; border-radius:12px; min-height:100px; line-height:1.55; }}
.topbar {{ display:flex; justify-content:space-between; gap:14px; align-items:center; margin-bottom:18px; }}
.small {{ font-size:12px; color:#8f99a6; margin-top:7px; }}
@media (max-width:640px) {{ .grid {{ grid-template-columns:1fr; }} .card {{ padding:18px; }} .topbar {{ align-items:flex-start; flex-direction:column; }} }}
</style>
</head><body><main class="wrap">{body}</main></body></html>"""
    return document.encode("utf-8")


def _login_body(message: str = "") -> str:
    notice = f'<div class="error">{html.escape(message)}</div>' if message else ""
    return f"""
<div class="card" style="max-width:520px;margin:80px auto 0">
  <h1>채팅 순위 봇 관리자</h1>
  <p class="muted">이벤트와 채팅 집계 설정을 웹에서 수정합니다.</p>
  {notice}
  <form method="post" action="/login">
    <label>관리자 아이디</label><input name="username" autocomplete="username" required>
    <label>비밀번호</label><input type="password" name="password" autocomplete="current-password" required>
    <div class="actions"><button type="submit">로그인</button></div>
  </form>
</div>"""


def _admin_body(storage: Storage, selected_chat_id: int | None, notice: str = "", error: str = "") -> str:
    chats = storage.list_chats()
    if not chats:
        return """
<div class="topbar"><div><h1>채팅 순위 봇 관리자</h1><p class="muted">이벤트 / 집계 설정</p></div><a class="button secondary" href="/logout">로그아웃</a></div>
<div class="card"><h2>등록된 소통방이 없습니다.</h2><p class="muted">봇이 들어간 소통방에서 메시지나 명령어를 한 번 입력한 뒤 이 페이지를 새로고침해주세요.</p></div>
"""

    chat_ids = {chat_id for chat_id, _ in chats}
    if selected_chat_id not in chat_ids:
        selected_chat_id = chats[0][0]
    cfg = get_event_settings(storage, selected_chat_id)

    options = []
    for chat_id, title in chats:
        selected = " selected" if chat_id == selected_chat_id else ""
        options.append(
            f'<option value="{chat_id}"{selected}>{html.escape(title)} ({chat_id})</option>'
        )

    emoji_values = list(EMOJI_OPTIONS)
    if cfg.event_emoji and cfg.event_emoji not in emoji_values:
        emoji_values.insert(0, cfg.event_emoji)
    emoji_options = "".join(
        f'<option value="{html.escape(emoji, quote=True)}"'
        f'{" selected" if emoji == cfg.event_emoji else ""}>{html.escape(emoji)}</option>'
        for emoji in emoji_values
    )

    notice_html = f'<div class="notice">{html.escape(notice)}</div>' if notice else ""
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    preview = " ".join(part for part in (cfg.event_emoji, cfg.event_title) if part)
    if cfg.event_body:
        preview = (preview + "\n\n" + cfg.event_body).strip()

    return f"""
<div class="topbar">
  <div><h1>채팅 순위 봇 관리자</h1><p class="muted">이벤트 / 집계 설정</p></div>
  <a class="button secondary" href="/logout">로그아웃</a>
</div>
{notice_html}{error_html}
<div class="card">
  <h2>소통방 선택</h2>
  <form method="get" action="/">
    <select name="chat_id" onchange="this.form.submit()">{''.join(options)}</select>
  </form>
</div>
<form method="post" action="/save">
<input type="hidden" name="chat_id" value="{selected_chat_id}">
<input type="hidden" name="section" value="ranking">
<div class="card">
  <h2>채팅 집계 설정</h2>
  <div class="grid">
    <div>
      <label>집계 최소 글자 수</label>
      <input type="number" name="min_text_length" min="1" max="100" value="{cfg.min_text_length}" required>
      <div class="small">현재 기본 5 → 한글·영문·숫자 5글자부터 집계 (웹에서 변경 가능)</div>
    </div>
    <div>
      <label>순위 표시 개수</label>
      <input type="number" name="ranking_limit" min="1" max="30" value="{cfg.ranking_limit}" required>
      <div class="small">예: 10 → .일일순위 / .주간순위에 1~10위 표시</div>
    </div>
  </div>
  <div class="actions"><button type="submit">집계 설정 저장</button></div>
</div>
</form>
<form method="post" action="/save">
<input type="hidden" name="chat_id" value="{selected_chat_id}">
<input type="hidden" name="section" value="footer">
<div class="card">
  <h2>주간 순위 하단 안내문구</h2>
  <textarea name="ranking_footer" maxlength="2000">{html.escape(cfg.ranking_footer)}</textarea>
  <div class="small">.주간순위 / 2시간 자동 주간순위 / 월요일 오후 6시 최종 확정 순위 하단에 동일하게 표시됩니다. 엔터 줄바꿈은 그대로 반영되고, @아이디는 텔레그램 링크로 표시됩니다.</div>
  <div class="actions"><button type="submit">하단 안내문구 저장</button></div>
</div>
</form>
<form method="post" action="/save">
<input type="hidden" name="chat_id" value="{selected_chat_id}">
<input type="hidden" name="section" value="event">
<div class="card">
  <h2>.이벤트 내용</h2>
  <div class="grid">
    <div><label>이모지 선택</label><select name="event_emoji" id="event_emoji">{emoji_options}</select></div>
    <div><label>이벤트 제목</label><input name="event_title" id="event_title" maxlength="200" value="{html.escape(cfg.event_title, quote=True)}"></div>
  </div>
  <label>이벤트 내용</label>
  <textarea name="event_body" id="event_body" maxlength="5000">{html.escape(cfg.event_body)}</textarea>
  <div class="small">엔터로 줄을 바꾸면 텔레그램에서도 같은 줄바꿈으로 표시됩니다.</div>
  <label>텔레그램 미리보기</label>
  <div id="preview" class="preview">{html.escape(preview)}</div>
  <div class="actions"><button type="submit">이벤트 저장</button></div>
</div>
</form>
<script>
const emoji=document.getElementById('event_emoji');
const title=document.getElementById('event_title');
const body=document.getElementById('event_body');
const preview=document.getElementById('preview');
function drawPreview() {{
  const head=[emoji.value.trim(), title.value.trim()].filter(Boolean).join(' ');
  const parts=[head, body.value.replace(/\\r\\n?/g,'\\n').trim()].filter(Boolean);
  preview.textContent=parts.join('\\n\\n') || '현재 등록된 이벤트가 없습니다.';
}}
[emoji,title,body].forEach(el=>el.addEventListener('input',drawPreview));
</script>
"""


class AdminWebServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_cls, storage: Storage, admin_username: str, admin_password: str):
        super().__init__(server_address, handler_cls)
        self.storage = storage
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.session_token = _session_token(admin_username, admin_password) if admin_password else ""


class _AdminHandler(BaseHTTPRequestHandler):
    server: AdminWebServer

    def _send(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _redirect(self, location: str, headers: dict[str, str] | None = None) -> None:
        all_headers = {"Location": location}
        all_headers.update(headers or {})
        self._send(303, b"", headers=all_headers)

    def _form(self) -> dict[str, str]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(min(length, 100_000)).decode("utf-8", errors="replace")
        parsed = parse_qs(raw, keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}

    def _is_authenticated(self) -> bool:
        if not self.server.admin_password:
            return False
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get(SESSION_COOKIE)
        return bool(
            morsel
            and hmac.compare_digest(morsel.value, self.server.session_token)
        )

    def _login_page(self, message: str = "") -> None:
        if not self.server.admin_password and not message:
            message = "Railway Variables에 ADMIN_PASSWORD를 먼저 설정해주세요. ADMIN_USERNAME은 기본값 admin입니다."
        self._send(200, _page("관리자 로그인", _login_body(message)))

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, b"OK", "text/plain; charset=utf-8")
            return
        if parsed.path == "/logout":
            self._redirect(
                "/",
                {"Set-Cookie": f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"},
            )
            return
        if parsed.path != "/":
            # 이전 Railway Healthcheck Path가 남아 있어도 배포가 끊기지 않게 유지합니다.
            self._send(200, b"OK", "text/plain; charset=utf-8")
            return
        if not self._is_authenticated():
            self._login_page()
            return
        query = parse_qs(parsed.query)
        selected = None
        if "chat_id" in query:
            try:
                selected = int(query["chat_id"][-1])
            except (ValueError, TypeError):
                selected = None
        notice = query.get("saved", [""])[-1]
        self._send(200, _page("채팅 순위 봇 관리자", _admin_body(self.server.storage, selected, notice=notice)))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            form = self._form()
            if not self.server.admin_password:
                self._login_page("Railway Variables에 ADMIN_PASSWORD를 먼저 설정해주세요.")
                return
            username = form.get("username", "")
            password = form.get("password", "")
            if not (
                hmac.compare_digest(username, self.server.admin_username)
                and hmac.compare_digest(password, self.server.admin_password)
            ):
                self._login_page("아이디 또는 비밀번호가 올바르지 않습니다.")
                return
            self._redirect(
                "/",
                {"Set-Cookie": f"{SESSION_COOKIE}={self.server.session_token}; Path=/; HttpOnly; SameSite=Lax"},
            )
            return

        if parsed.path != "/save":
            self._send(404, _page("404", '<div class="card"><h1>페이지를 찾을 수 없습니다.</h1></div>'))
            return
        if not self._is_authenticated():
            self._redirect("/")
            return

        form = self._form()
        try:
            chat_id = int(form.get("chat_id", ""))
        except ValueError:
            self._send(400, _page("입력 오류", '<div class="card"><h1>소통방 값을 확인해주세요.</h1><a class="button" href="/">돌아가기</a></div>'))
            return

        if chat_id not in {cid for cid, _ in self.server.storage.list_chats()}:
            self._send(400, _page("입력 오류", '<div class="card"><h1>등록되지 않은 소통방입니다.</h1><a class="button" href="/">돌아가기</a></div>'))
            return

        section = form.get("section", "")
        try:
            if section == "ranking":
                min_text_length = int(form.get("min_text_length", ""))
                ranking_limit = int(form.get("ranking_limit", ""))
                save_ranking_settings(
                    self.server.storage,
                    chat_id,
                    min_text_length=min_text_length,
                    ranking_limit=ranking_limit,
                )
                saved_message = "집계 설정 저장 완료. 이벤트 내용은 변경하지 않았습니다."
            elif section == "footer":
                save_ranking_footer(
                    self.server.storage,
                    chat_id,
                    ranking_footer=form.get("ranking_footer", ""),
                )
                saved_message = "순위 하단 안내문구 저장 완료. 주간순위에 바로 반영됩니다."
            elif section == "event":
                save_event_settings(
                    self.server.storage,
                    chat_id,
                    event_emoji=form.get("event_emoji", DEFAULT_EVENT_EMOJI),
                    event_title=form.get("event_title", ""),
                    event_body=form.get("event_body", ""),
                )
                saved_message = "이벤트 저장 완료. 봇에 바로 반영됩니다."
            else:
                raise ValueError("저장할 설정 종류를 확인해주세요.")
        except ValueError as exc:
            body = _admin_body(self.server.storage, chat_id, error=str(exc))
            self._send(400, _page("설정 오류", body))
            return

        location = "/?" + urlencode({"chat_id": chat_id, "saved": saved_message})
        self._redirect(location)

    def log_message(self, format: str, *args: object) -> None:
        return


def start_health_server(
    port: int,
    storage: Storage | None = None,
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> ThreadingHTTPServer:
    if storage is None:
        storage = Storage("sqlite:///:memory:")
        storage.initialize()
    username = (admin_username if admin_username is not None else os.getenv("ADMIN_USERNAME", "admin")).strip() or "admin"
    password = admin_password if admin_password is not None else os.getenv("ADMIN_PASSWORD", "")
    server = AdminWebServer(("0.0.0.0", port), _AdminHandler, storage, username, password)
    thread = threading.Thread(
        target=server.serve_forever,
        name="railway-admin-web",
        daemon=True,
    )
    thread.start()
    return server
