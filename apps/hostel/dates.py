import calendar
from datetime import date, timedelta


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def days_in_month(d: date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def months_between(first: date, last: date):
    """Month starts from `first` to `last`, inclusive."""
    m = month_start(first)
    while m <= last:
        yield m
        m = add_months(m, 1)


def days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def overlap(a_start: date, a_end: date | None, b_start: date, b_end: date) -> tuple[date, date] | None:
    s = max(a_start, b_start)
    e = min(a_end or b_end, b_end)
    return (s, e) if s <= e else None
