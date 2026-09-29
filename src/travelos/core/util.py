"""Small shared helpers (dates, distance, parsing)."""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta

from .errors import ValidationError

IATA_RE = re.compile(r"^[A-Za-z]{3}$")


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def parse_date(v, field: str = "date") -> date:
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"Invalid {field}: expected YYYY-MM-DD.")


def daterange(a: date, b: date, step: int = 1):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=step)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def num(v, field: str, lo=None, hi=None, default=None, integer=False):
    if v is None or v == "":
        if default is not None:
            return default
        raise ValidationError(f"Missing {field}.")
    try:
        x = int(v) if integer else float(v)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number.")
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise ValidationError(f"{field} must be between {lo} and {hi}.")
    return x


def text(v, field: str, max_len: int = 300, required: bool = False) -> str | None:
    if v is None or str(v).strip() == "":
        if required:
            raise ValidationError(f"Missing {field}.")
        return None
    s = str(v).strip()
    if len(s) > max_len:
        raise ValidationError(f"{field} is too long (max {max_len}).")
    return s


def month_range(month_from: int, month_to: int) -> list[int]:
    out, m = [month_from], month_from
    while m != month_to:
        m = m % 12 + 1
        out.append(m)
    return out


def next_occurrence(month: int, today: date | None = None) -> tuple[date, date]:
    """First and last day of the next occurrence of `month` (current month counts if not over)."""
    today = today or date.today()
    y = today.year if month >= today.month else today.year + 1
    first = date(y, month, 1)
    last = date(y + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return first, last
