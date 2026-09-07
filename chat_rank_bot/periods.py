from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


WEEKLY_CUTOFF_HOUR = 18


@dataclass(frozen=True)
class PeriodKeys:
    day_key: str
    week_key: str


def period_keys(moment: datetime, timezone: ZoneInfo) -> PeriodKeys:
    local = moment.astimezone(timezone)
    monday_date = local.date() - timedelta(days=local.weekday())
    monday_cutoff = datetime.combine(
        monday_date,
        time(hour=WEEKLY_CUTOFF_HOUR),
        tzinfo=timezone,
    )
    if local < monday_cutoff:
        monday_date -= timedelta(days=7)
    return PeriodKeys(
        day_key=local.date().isoformat(),
        week_key=monday_date.isoformat(),
    )


def previous_week_key(moment: datetime, timezone: ZoneInfo) -> str:
    current_monday = parse_key(period_keys(moment, timezone).week_key)
    return (current_monday - timedelta(days=7)).isoformat()


def next_monday_cutoff(moment: datetime, timezone: ZoneInfo) -> datetime:
    local = moment.astimezone(timezone)
    days_until_monday = (-local.weekday()) % 7
    target_date = local.date() + timedelta(days=days_until_monday)
    target = datetime.combine(
        target_date,
        time(hour=WEEKLY_CUTOFF_HOUR),
        tzinfo=timezone,
    )
    if target <= local:
        target += timedelta(days=7)
    return target


def parse_key(key: str) -> date:
    return date.fromisoformat(key)


def day_label(day_key: str) -> str:
    day = parse_key(day_key)
    return f"{day.month}월 {day.day}일"


def week_label(week_key: str) -> str:
    monday = parse_key(week_key)
    next_monday = monday + timedelta(days=7)
    if monday.month == next_monday.month:
        return (
            f"{monday.month}월 {monday.day}일 18시 ~ "
            f"{next_monday.day}일 18시"
        )
    return (
        f"{monday.month}월 {monday.day}일 18시 ~ "
        f"{next_monday.month}월 {next_monday.day}일 18시"
    )
