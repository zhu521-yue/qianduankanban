from datetime import date

from app.periods import Grain, period_window, previous_window, recent_windows


def test_business_quarter_for_january_belongs_to_previous_year() -> None:
    window = period_window(Grain.QUARTER, date(2027, 1, 15))
    assert window.start == date(2026, 11, 1)
    assert window.end == date(2027, 1, 31)


def test_business_half_year_boundaries() -> None:
    first = period_window(Grain.HALF, date(2026, 7, 28))
    second = period_window(Grain.HALF, date(2027, 1, 3))
    assert (first.start, first.end) == (date(2026, 2, 1), date(2026, 7, 31))
    assert (second.start, second.end) == (date(2026, 8, 1), date(2027, 1, 31))


def test_previous_month_crosses_year() -> None:
    current = period_window(Grain.MONTH, date(2026, 1, 8))
    previous = previous_window(current)
    assert (previous.start, previous.end) == (date(2025, 12, 1), date(2025, 12, 31))


def test_recent_windows_are_ordered_old_to_new() -> None:
    windows = recent_windows(Grain.WEEK, date(2026, 7, 28), 3)
    assert len(windows) == 3
    assert windows[0].start < windows[1].start < windows[2].start


def test_natural_week_uses_monday_to_sunday_across_months() -> None:
    window = period_window(Grain.WEEK, date(2026, 7, 28))
    assert (window.start, window.end) == (date(2026, 7, 27), date(2026, 8, 2))
