from __future__ import annotations

import hashlib
import re
import unicodedata


COMPLETE_CHARACTER = re.compile(r"[0-9A-Za-z가-힣]")
WHITESPACE = re.compile(r"\s+")


def normalized_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).strip().lower()
    return WHITESPACE.sub(" ", normalized)


def is_countable_text(text: str | None, min_length: int) -> bool:
    if not text or text.lstrip().startswith(("/", ".")):
        return False
    normalized = normalized_text(text)
    actual_characters = COMPLETE_CHARACTER.findall(normalized)
    return len(actual_characters) >= min_length


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalized_text(text).encode("utf-8")).hexdigest()


def dot_command(text: str) -> str | None:
    first = text.strip().split(maxsplit=1)[0].lower() if text.strip() else ""
    return first if first.startswith(".") else None


def is_slash_command(text: str, command: str) -> bool:
    return re.fullmatch(
        rf"/{re.escape(command)}(?:@[A-Za-z0-9_]+)?(?:\s+.*)?",
        text.strip(),
        flags=re.DOTALL,
    ) is not None
