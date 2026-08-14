from __future__ import annotations

from datetime import date, timedelta


def week_bounds(value: date) -> tuple[date, date]:
    start = value - timedelta(days=value.weekday())
    return start, start + timedelta(days=6)


def month_bounds(value: date) -> tuple[date, date]:
    start = value.replace(day=1)
    next_month = date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)
    return start, next_month - timedelta(days=1)


def quarter_bounds(value: date) -> tuple[date, date]:
    if 2 <= value.month <= 4:
        start = date(value.year, 2, 1)
    elif 5 <= value.month <= 7:
        start = date(value.year, 5, 1)
    elif 8 <= value.month <= 10:
        start = date(value.year, 8, 1)
    elif value.month >= 11:
        start = date(value.year, 11, 1)
    else:
        start = date(value.year - 1, 11, 1)
    end_month = ((start.month - 1 + 3) % 12) + 1
    end_year = start.year + ((start.month - 1 + 3) // 12)
    return start, date(end_year, end_month, 1) - timedelta(days=1)


def half_year_bounds(value: date) -> tuple[date, date]:
    if 2 <= value.month <= 7:
        start = date(value.year, 2, 1)
        end = date(value.year, 7, 31)
    elif value.month >= 8:
        start = date(value.year, 8, 1)
        end = date(value.year + 1, 1, 31)
    else:
        start = date(value.year - 1, 8, 1)
        end = date(value.year, 1, 31)
    return start, end


def impact_summary(dates: set[date]) -> dict[str, list[dict[str, str]] | list[str]]:
    def ranges(func):
        return [
            {"period_start": start.isoformat(), "period_end": end.isoformat()}
            for start, end in sorted({func(value) for value in dates})
        ]

    return {
        "dates": [value.isoformat() for value in sorted(dates)],
        "weeks": ranges(week_bounds),
        "months": ranges(month_bounds),
        "quarters": ranges(quarter_bounds),
        "half_years": ranges(half_year_bounds),
    }
