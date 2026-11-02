"""Parse giá / diện tích / giá thuê từ chuỗi hiển thị trên tin đăng."""

from __future__ import annotations

import re

_NEGOTIABLE = ("thỏa thuận", "thoả thuận", "thoa thuan", "liên hệ", "lien he")


def parse_area(raw: str | None) -> float | None:
    """``62,5 m²`` -> 62.5. Ưu tiên số đứng trước ``m2``/``m²``."""
    if not raw or raw == "N/A":
        return None
    value = str(raw).lower().replace("²", "2")
    m = re.search(r"(\d{1,5}(?:[.,]\d{1,2})?)\s*m2", value) or re.search(r"(\d{1,5}(?:[.,]\d{1,2})?)", value)
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", ".")), 2)
    except ValueError:
        return None


def parse_price(raw: str | None, area_m2: float | None = None) -> tuple[float | None, float | None]:
    """Trả về ``(tổng giá tỷ đồng, đơn giá triệu/m²)``.

    Hỗ trợ ``3,75 tỷ``, ``850 triệu``, ``65 triệu/m²``. Thiếu diện tích thì vế còn lại là None.
    """
    if not raw:
        return None, None
    value = str(raw).lower().replace("vnđ", "").replace("vnd", "")
    value = " ".join(value.split())
    if any(token in value for token in _NEGOTIABLE):
        return None, None
    m = re.search(r"(\d+(?:[.,]\d+)?)", value)
    if not m:
        return None, None
    number = float(m.group(1).replace(",", "."))

    total: float | None = None
    unit: float | None = None
    if re.search(r"(?:triệu|trieu|tr)\s*/\s*m", value):
        unit = number
        if area_m2:
            total = unit * area_m2 / 1000
    elif "tỷ" in value or "tỉ" in value or re.search(r"\bty\b", value):
        total = number
        if area_m2:
            unit = total * 1000 / area_m2
    elif "triệu" in value or "trieu" in value or re.search(r"\btr\b", value):
        total = number / 1000
        if area_m2:
            unit = number / area_m2
    return (
        round(total, 3) if total is not None else None,
        round(unit, 2) if unit is not None else None,
    )


def parse_price_billion(raw: str | None) -> float | None:
    """Chỉ lấy tổng giá (tỷ). ``triệu/m²`` không đổi được sang tổng giá nếu thiếu diện tích -> None."""
    total, _ = parse_price(raw)
    return round(total, 2) if total is not None else None


def parse_rent_million(raw: str | None) -> float | None:
    """Giá thuê theo tháng, đơn vị triệu: ``15 triệu/tháng``, ``15tr``, ``15.000.000 đ``."""
    text = " ".join((raw or "").lower().split())
    if not text or any(token in text for token in _NEGOTIABLE):
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|trieu|tr)\b", text)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:tỷ|ty)\b", text)
    if m:
        return float(m.group(1).replace(",", ".")) * 1000
    m = re.search(r"([\d.,]{7,})\s*(?:đ|d|vnd|vnđ)?\b", text)
    if m:
        digits = re.sub(r"[.,]", "", m.group(1))
        if digits.isdigit():
            return round(int(digits) / 1_000_000, 2)
    return None


def first_number(text: str, pattern: str) -> float | None:
    """Số đầu tiên ở group(1) của ``pattern`` (không phân biệt hoa thường)."""
    m = re.search(pattern, text or "", re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except (ValueError, IndexError):
        return None
