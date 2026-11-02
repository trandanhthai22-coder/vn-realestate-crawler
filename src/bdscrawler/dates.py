"""Parse ngày đăng tin: ``hôm nay``, ``3 ngày trước``, ``2 tuần trước``, ``17/10/2026``, ``17/10``."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta


def parse_date(raw: str | None, today: date | None = None) -> date | None:
    if not raw:
        return None
    current = today or date.today()
    value = " ".join(str(raw).lower().split())

    if "hôm nay" in value or "hom nay" in value or re.search(r"\b\d+\s*(phút|giờ|phut|gio)\s*trước", value):
        return current
    if "hôm qua" in value or "hom qua" in value:
        return current - timedelta(days=1)

    for pattern, days in ((r"(\d+)\s*ngày\s*trước", 1), (r"(\d+)\s*tuần\s*trước", 7), (r"(\d+)\s*tháng\s*trước", 30)):
        m = re.search(pattern, value)
        if m:
            return current - timedelta(days=days * int(m.group(1)))

    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", value)
    if m:
        day, month, year = map(int, m.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if m:
        year, month, day = map(int, m.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    # "17/10" không kèm năm: lấy năm hiện tại, lùi 1 năm nếu rơi vào tương lai xa
    m = re.search(r"(\d{1,2})[/-](\d{1,2})(?![/-]\d)", value)
    if m:
        day, month = map(int, m.groups())
        try:
            parsed = date(current.year, month, day)
        except ValueError:
            return None
        if parsed > current + timedelta(days=7):
            parsed = date(current.year - 1, month, day)
        return parsed
    return None


def parse_cli_date(value: str) -> date:
    """Nhận ``2026-10-15``, ``15/10/2026`` hoặc ``15-10-2026``."""
    value = value.strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"Ngày không hợp lệ: {value!r} (dùng 15/10/2026 hoặc 2026-10-15)")


def fmt(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def week_of_month(day: int) -> int:
    return min(5, (day - 1) // 7 + 1)
