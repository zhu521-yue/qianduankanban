from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from app.responses import ApiError


class Grain(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    HALF = "half"


@dataclass(frozen=True)
class PeriodWindow:
    grain: Grain
    start: date
    end: date

    def clipped(self, as_of: date) -> "PeriodWindow":
        return PeriodWindow(self.grain, self.start, min(self.end, as_of))

    @property
    def label(self) -> str:
        return self.start.isoformat() if self.start == self.end else f"{self.start.isoformat()}—{self.end.isoformat()}"


def parse_date(value: str | None, *, default: date | None = None) -> date:
    if not value:
        if default is None:
            raise ApiError(400, "DATE_REQUIRED", "缺少统计日期。")
        return default
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(400, "DATE_INVALID", "日期必须使用 YYYY-MM-DD 格式。") from exc


def _month_end(year: int, month: int) -> date:
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return next_month - timedelta(days=1)


def period_window(grain: Grain | str, target: date) -> PeriodWindow:
    parsed = grain if isinstance(grain, Grain) else Grain(grain)
    if parsed == Grain.DAY:
        return PeriodWindow(parsed, target, target)
    if parsed == Grain.WEEK:
        start = target - timedelta(days=target.weekday())
        return PeriodWindow(parsed, start, start + timedelta(days=6))
    if parsed == Grain.MONTH:
        return PeriodWindow(parsed, date(target.year, target.month, 1), _month_end(target.year, target.month))
    if parsed == Grain.QUARTER:
        if target.month == 1:
            start = date(target.year - 1, 11, 1)
        elif target.month <= 4:
            start = date(target.year, 2, 1)
        elif target.month <= 7:
            start = date(target.year, 5, 1)
        elif target.month <= 10:
            start = date(target.year, 8, 1)
        else:
            start = date(target.year, 11, 1)
        end_month = ((start.month - 1 + 2) % 12) + 1
        end_year = start.year + ((start.month - 1 + 2) // 12)
        return PeriodWindow(parsed, start, _month_end(end_year, end_month))
    if target.month == 1:
        start = date(target.year - 1, 8, 1)
    elif target.month <= 7:
        start = date(target.year, 2, 1)
    else:
        start = date(target.year, 8, 1)
    end_month = ((start.month - 1 + 5) % 12) + 1
    end_year = start.year + ((start.month - 1 + 5) // 12)
    return PeriodWindow(parsed, start, _month_end(end_year, end_month))


def previous_window(window: PeriodWindow) -> PeriodWindow:
    return period_window(window.grain, window.start - timedelta(days=1))


def recent_windows(grain: Grain | str, as_of: date, count: int = 6) -> list[PeriodWindow]:
    current = period_window(grain, as_of)
    result = [current]
    while len(result) < count:
        result.append(previous_window(result[-1]))
    return list(reversed(result))

