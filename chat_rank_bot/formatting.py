from __future__ import annotations

from html import escape

from .periods import day_label, week_label
from .storage import BotAdmin, ExcludedUser, PersonalRank, RankEntry


PRIZES = {}
DEFAULT_TOP_LIMIT = 4
EMPTY_NAME = "집계 없음"
DEFAULT_RANKING_FOOTER = "매주 월요일 오후 6시 초기화 및 최종 순위 확정\n문의 : @zlzl6318"


def _telegram_profile_link(username: str) -> str:
    clean_username = escape(username.lstrip("@"), quote=True)
    return (
        f'<a href="https://t.me/{clean_username}">'
        f'@{clean_username}</a>'
    )


def _format_footer_text(text: str) -> str:
    """Render admin-authored plain text safely, preserving newlines and linking @usernames."""
    import re

    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    def render_line(line: str, *, bold: bool = False) -> str:
        parts: list[str] = []
        last = 0
        for match in re.finditer(r"(?<![\w@])@([A-Za-z0-9_]{5,32})", line):
            parts.append(escape(line[last:match.start()]))
            parts.append(_telegram_profile_link(match.group(1)))
            last = match.end()
        parts.append(escape(line[last:]))
        rendered = "".join(parts)
        return f"<b>{rendered}</b>" if bold and rendered else rendered

    lines = normalized.split("\n")
    return "\n".join(render_line(line, bold=(index == 0)) for index, line in enumerate(lines))


def _display_identity(entry: RankEntry) -> str:
    name = escape(
        entry.display_name
        or (entry.username if entry.username else str(entry.user_id))
    )
    if not entry.username:
        return f"{name} (아이디 없음)"
    return f"{name} ({_telegram_profile_link(entry.username)})"


def _ranking_rows(
    entries: list[RankEntry],
    *,
    show_prizes: bool,
    start_position: int = 1,
    end_position: int = DEFAULT_TOP_LIMIT,
) -> str:
    rows: list[str] = []
    for position in range(start_position, end_position + 1):
        if position <= len(entries):
            entry = entries[position - 1]
            name = _display_identity(entry)
            count = f"{entry.count:,}회"
        else:
            name = EMPTY_NAME
            count = "0회"

        prize_text = PRIZES.get(position) if show_prizes else None
        prize = f" {prize_text}" if prize_text else ""
        rows.append(f"{position}위{prize} - {name} [ {count} ]")
    return "\n".join(rows)


def daily_ranking_message(
    entries: list[RankEntry], day_key: str, ranking_limit: int = DEFAULT_TOP_LIMIT
) -> str:
    return (
        f"📅 <b>일일집계</b> · {day_label(day_key)}\n\n"
        f"{_ranking_rows(entries, show_prizes=False, end_position=ranking_limit)}\n\n"
        "매일 00시 새로 집계"
    )


def weekly_ranking_message(
    entries: list[RankEntry],
    week_key: str,
    ranking_limit: int = DEFAULT_TOP_LIMIT,
    ranking_footer: str = DEFAULT_RANKING_FOOTER,
) -> str:
    base = (
        f"📆 <b>주간집계</b> · {week_label(week_key)}\n\n"
        f"{_ranking_rows(entries, show_prizes=True, end_position=ranking_limit)}"
    )
    footer = _format_footer_text(ranking_footer)
    return base + (f"\n\n{footer}" if footer else "")


def finalized_weekly_ranking_message(
    entries: list[RankEntry],
    week_key: str,
    ranking_limit: int = DEFAULT_TOP_LIMIT,
    ranking_footer: str = DEFAULT_RANKING_FOOTER,
) -> str:
    base = (
        f"🏆 <b>주간 확정 순위</b> · {week_label(week_key)}\n\n"
        f"{_ranking_rows(entries, show_prizes=True, end_position=ranking_limit)}"
    )
    footer = _format_footer_text(ranking_footer)
    return base + (f"\n\n{footer}" if footer else "")


def admin_weekly_ranking_message(
    entries: list[RankEntry], week_key: str, chat_title: str
) -> str:
    return (
        "🔒 <b>관리자 전용 · 주간 5~10위</b>\n"
        f"{escape(chat_title)} · {week_label(week_key)}\n\n"
        f"{_ranking_rows(entries, show_prizes=False, start_position=5, end_position=10)}"
    )


def event_message(emoji: str, title: str, body: str) -> str:
    header = " ".join(part for part in ((emoji or "").strip(), (title or "").strip()) if part)
    content = (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    parts = [part for part in (header, content) if part]
    return "\n\n".join(parts) if parts else "현재 등록된 이벤트가 없습니다."


def excluded_users_message(entries: list[ExcludedUser]) -> str:
    if not entries:
        return "🚫 <b>집계 제외 목록</b>\n\n제외된 회원이 없습니다."

    rows: list[str] = []
    for position, entry in enumerate(entries, start=1):
        name = escape(entry.display_name or str(entry.user_id))
        if entry.username:
            identity = f"{name} ({_telegram_profile_link(entry.username)})"
        else:
            identity = f"{name} (고유번호: <code>{entry.user_id}</code>)"
        rows.append(f"{position}. {identity}")
    return "🚫 <b>집계 제외 목록</b>\n\n" + "\n".join(rows)


def bot_admins_message(entries: list[BotAdmin]) -> str:
    if not entries:
        return "🛡 <b>추가된 봇 관리자</b>\n\n추가된 관리자가 없습니다."

    rows: list[str] = []
    for position, entry in enumerate(entries, start=1):
        name = escape(entry.display_name or str(entry.user_id))
        if entry.username:
            identity = f"{name} ({_telegram_profile_link(entry.username)})"
        else:
            identity = f"{name} (고유번호: <code>{entry.user_id}</code>)"
        rows.append(f"{position}. {identity}")
    return "🛡 <b>추가된 봇 관리자</b>\n\n" + "\n".join(rows)


def _rank_text(result: PersonalRank) -> str:
    return f"{result.rank}위" if result.rank is not None else "집계 전"


def personal_message(
    daily: PersonalRank, weekly: PersonalRank, min_text_length: int = 5
) -> str:
    return (
        "🪶 <b>내 채팅 기록</b>\n\n"
        f"📅 일일: <b>{daily.count:,}회 · {_rank_text(daily)}</b>\n"
        f"📆 주간: <b>{weekly.count:,}회 · {_rank_text(weekly)}</b>\n\n"
        f"{min_text_length}글자 이상 집계 / 초성 집계 X"
    )


def help_message(
    include_admin: bool = False,
    *,
    min_text_length: int = 5,
    ranking_limit: int = 4,
) -> str:
    rows = [
        "💬 <b>채팅 순위 명령어</b>",
        "",
        f".일일순위 — 오늘 1~{ranking_limit}위",
        f".주간순위 — 이번 주 1~{ranking_limit}위와 상금",
        ".이벤트 — 현재 진행 이벤트 확인",
        ".나 — 내 일일·주간 채팅 수와 등수",
    ]
    if include_admin:
        rows.extend(
            [
                "",
                "🛡 <b>관리자 명령어</b>",
                ".관리자순위 — 봇 개인채팅에서 관리자 전용 주간 5~10위",
                ".관리자추가 — 답장한 회원에게 봇 관리 권한 추가",
                ".관리자삭제 — 답장한 회원의 봇 관리 권한 삭제",
                ".관리자목록 — 추가된 봇 관리자 확인",
                ".제외 — 답장한 회원을 집계에서 제외",
                ".제외해제 — 답장한 회원을 다시 집계",
                ".제외목록 — 현재 제외된 회원 확인",
            ]
        )
    rows.extend(["", f"{min_text_length}글자 이상 집계 / 초성 집계 X"])
    return "\n".join(rows)
