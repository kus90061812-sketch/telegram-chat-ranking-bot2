from __future__ import annotations

from dataclasses import dataclass

from .storage import Storage

DEFAULT_MIN_TEXT_LENGTH = 5
DEFAULT_RANKING_LIMIT = 4
DEFAULT_EVENT_EMOJI = ""
DEFAULT_EVENT_TITLE = ""
DEFAULT_EVENT_BODY = ""
DEFAULT_RANKING_FOOTER = "매주 월요일 오후 6시 초기화 및 최종 순위 확정\n문의 : @zlzl6318"
EVENT_EMOJI_FALLBACK = "🎲"

MIN_TEXT_LENGTH_RANGE = (1, 100)
RANKING_LIMIT_RANGE = (1, 30)
EVENT_TITLE_MAX_LENGTH = 200
EVENT_BODY_MAX_LENGTH = 5000
EVENT_EMOJI_MAX_LENGTH = 16
RANKING_FOOTER_MAX_LENGTH = 2000


@dataclass(frozen=True)
class ChatSettings:
    min_text_length: int = DEFAULT_MIN_TEXT_LENGTH
    ranking_limit: int = DEFAULT_RANKING_LIMIT
    event_emoji: str = DEFAULT_EVENT_EMOJI
    event_title: str = DEFAULT_EVENT_TITLE
    event_body: str = DEFAULT_EVENT_BODY
    ranking_footer: str = DEFAULT_RANKING_FOOTER


def _key(chat_id: int, name: str) -> str:
    return f"chat:{int(chat_id)}:{name}"


def _bounded_int(raw: str | None, default: int, minimum: int, maximum: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if minimum <= value <= maximum else default


def get_min_text_length(storage: Storage, chat_id: int) -> int:
    return _bounded_int(
        storage.get_setting(_key(chat_id, "min_text_length")),
        DEFAULT_MIN_TEXT_LENGTH,
        *MIN_TEXT_LENGTH_RANGE,
    )


def get_ranking_limit(storage: Storage, chat_id: int) -> int:
    return _bounded_int(
        storage.get_setting(_key(chat_id, "ranking_limit")),
        DEFAULT_RANKING_LIMIT,
        *RANKING_LIMIT_RANGE,
    )


def get_event_settings(storage: Storage, chat_id: int) -> ChatSettings:
    return ChatSettings(
        min_text_length=get_min_text_length(storage, chat_id),
        ranking_limit=get_ranking_limit(storage, chat_id),
        event_emoji=(
            DEFAULT_EVENT_EMOJI
            if (raw_emoji := storage.get_setting(_key(chat_id, "event_emoji"))) is None
            else raw_emoji
        ),
        event_title=(
            DEFAULT_EVENT_TITLE
            if (raw_title := storage.get_setting(_key(chat_id, "event_title"))) is None
            else raw_title
        ),
        event_body=(
            DEFAULT_EVENT_BODY
            if (raw_body := storage.get_setting(_key(chat_id, "event_body"))) is None
            else raw_body
        ),
        ranking_footer=(
            DEFAULT_RANKING_FOOTER
            if (raw_footer := storage.get_setting(_key(chat_id, "ranking_footer"))) is None
            else raw_footer
        ),
    )


def save_ranking_settings(
    storage: Storage,
    chat_id: int,
    *,
    min_text_length: int,
    ranking_limit: int,
) -> ChatSettings:
    if not MIN_TEXT_LENGTH_RANGE[0] <= min_text_length <= MIN_TEXT_LENGTH_RANGE[1]:
        raise ValueError("집계 글자 수는 1~100 사이로 입력해주세요.")
    if not RANKING_LIMIT_RANGE[0] <= ranking_limit <= RANKING_LIMIT_RANGE[1]:
        raise ValueError("순위 표시 개수는 1~30 사이로 입력해주세요.")

    storage.set_setting(_key(chat_id, "min_text_length"), str(min_text_length))
    storage.set_setting(_key(chat_id, "ranking_limit"), str(ranking_limit))
    return get_event_settings(storage, chat_id)


def save_event_settings(
    storage: Storage,
    chat_id: int,
    *,
    event_emoji: str,
    event_title: str,
    event_body: str,
) -> ChatSettings:
    event_title = (event_title or "").strip()
    event_body = (event_body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    event_emoji = (event_emoji or EVENT_EMOJI_FALLBACK).strip() if (event_title or event_body) else ""

    if len(event_emoji) > EVENT_EMOJI_MAX_LENGTH:
        raise ValueError("이모지는 너무 길게 입력할 수 없습니다.")
    if len(event_title) > EVENT_TITLE_MAX_LENGTH:
        raise ValueError("이벤트 제목은 200자 이하로 입력해주세요.")
    if len(event_body) > EVENT_BODY_MAX_LENGTH:
        raise ValueError("이벤트 내용은 5000자 이하로 입력해주세요.")

    storage.set_setting(_key(chat_id, "event_emoji"), event_emoji)
    storage.set_setting(_key(chat_id, "event_title"), event_title)
    storage.set_setting(_key(chat_id, "event_body"), event_body)
    return get_event_settings(storage, chat_id)



def save_ranking_footer(
    storage: Storage,
    chat_id: int,
    *,
    ranking_footer: str,
) -> ChatSettings:
    ranking_footer = (ranking_footer or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(ranking_footer) > RANKING_FOOTER_MAX_LENGTH:
        raise ValueError("순위 하단 안내문구는 2000자 이하로 입력해주세요.")
    storage.set_setting(_key(chat_id, "ranking_footer"), ranking_footer)
    return get_event_settings(storage, chat_id)

def save_chat_settings(
    storage: Storage,
    chat_id: int,
    *,
    min_text_length: int,
    ranking_limit: int,
    event_emoji: str,
    event_title: str,
    event_body: str,
) -> ChatSettings:
    # Backward-compatible helper for tests/callers that intentionally save both sections.
    save_ranking_settings(
        storage,
        chat_id,
        min_text_length=min_text_length,
        ranking_limit=ranking_limit,
    )
    return save_event_settings(
        storage,
        chat_id,
        event_emoji=event_emoji,
        event_title=event_title,
        event_body=event_body,
    )
