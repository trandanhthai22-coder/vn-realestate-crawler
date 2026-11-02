"""Nhận diện loại căn hộ (Studio / 1PN / 2PN+ / Duplex ...) từ tin đăng.

Quy trình 2 bước:

1. Lấy SỐ ngủ gốc từ khối short-info của trang chi tiết (batdongsan đã chuẩn hoá,
   đáng tin nhất) — dự phòng bằng bảng đặc điểm và card ngoài trang danh mục.
2. VERIFY dấu ``+`` trong tiêu đề + mô tả, vì short-info luôn quy ``2PN+`` về ``2 PN``.
   Hai cạm bẫy được xử lý:

   a. ``2PN + 1 phòng vệ sinh`` / ``3PN + 2WC``: dấu ``+`` chỉ là liệt kê, không phải ``2PN+``.
   b. Tin liệt kê nhiều căn (``2PN 55m² 3,3 tỷ … 2PN + 64m² 3,9 tỷ``): chỉ nhận token có
      diện tích/giá đứng ngay sau KHỚP với diện tích/giá của chính tin đăng.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from bdscrawler.text import clean_text, to_float

# 'pn' KHÔNG đặt \b phía sau để bắt được kiểu viết liền "2PN2VS", "2PN1".
_BED_TOKEN_RE = re.compile(
    r"(?:(?P<studio>\bstudio\b)"
    r"|(?P<n>\d+)\s*(?:pn|p\s*n\b|phòng\s*ngủ|phong\s*ngu|ngủ\b|ngu\b|n\b))"
    r"\s*(?P<plus>\+)?",
    re.IGNORECASE,
)

# '+' đứng trước các danh từ này chỉ là phép liệt kê thêm, không phải loại căn "PN+"
_PLUS_NOT_TYPE_RE = re.compile(
    r"^\s*\d*\s*"
    r"(?:(?:phòng|phong)\s*)?"
    r"(?:vệ\s*sinh|ve\s*sinh|tắm|tam|wc\b|vs\b|nvs\b|toilet|tolet"
    r"|\d+\s*(?:pn\b|phòng\s*ngủ|phong\s*ngu))",
    re.IGNORECASE,
)

_CTX_AREA_RE = re.compile(r"(\d+[.,]?\d*)\s*(?:m2\b|m²|mét\s*vuông|met\s*vuong|m\b)", re.IGNORECASE)
_CTX_PRICE_RE = re.compile(r"(\d+[.,]?\d*)\s*(?:tỷ|tỉ|ty\b)", re.IGNORECASE)
# Giá viết tắt không kèm đơn vị, vd: "* 2PN full nội thất 62 m 3,75."
_CTX_BARE_RE = re.compile(r"(?<![\d.,])(\d{1,2}[.,]\d{1,3})(?![\d])")

DUPLEX_KEYS = ("duplex", "căn hộ 2 tầng", "can ho 2 tang")
SPECIAL_3PN_KEYS = ("3pn đặc biệt", "3pn db", "penthouse", "3 ngủ đặc biệt")


def _score_context(ctx: str, area: float | None, price: float | None, after: bool) -> int:
    """Ngữ cảnh có diện tích/giá trùng với chính tin đăng thì điểm cao."""
    if not ctx:
        return 0
    score = 0
    if area:
        for m in _CTX_AREA_RE.finditer(ctx):
            v = to_float(m.group(1))
            if v and abs(v - area) <= 0.6:
                score += 3 if after else 2
                break
    if price:
        hit = False
        for m in _CTX_PRICE_RE.finditer(ctx):
            v = to_float(m.group(1))
            if v and abs(v - price) <= 0.03:
                score += 2 if after else 1
                hit = True
                break
        if not hit:
            for m in _CTX_BARE_RE.finditer(ctx):
                v = to_float(m.group(1))
                if v and abs(v - price) <= 0.03:
                    score += 1
                    break
    return score


def _candidates(text: str, in_title: bool, area: float | None, price: float | None) -> list[dict]:
    if not text:
        return []
    t = text.lower()
    matches = list(_BED_TOKEN_RE.finditer(t))
    out = []
    for i, m in enumerate(matches):
        # Cửa sổ ngữ cảnh dừng trước token kế tiếp để không "mượn" giá của căn khác
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(t)
        after = t[m.end():min(m.end() + 90, nxt)]
        prev = matches[i - 1].end() if i > 0 else 0
        before = t[max(prev, m.start() - 45):m.start()]

        is_studio = m.group("studio") is not None
        n = None if is_studio else int(m.group("n"))
        if n is not None and not 1 <= n <= 5:  # bắt nhầm số nhà, số tầng...
            continue
        plus = bool(m.group("plus")) and not _PLUS_NOT_TYPE_RE.match(after)
        out.append({
            "studio": is_studio,
            "n": 1 if is_studio else n,
            "plus": False if is_studio else plus,
            "in_title": in_title,
            "score": _score_context(after, area, price, True) + _score_context(before, area, price, False),
        })
    return out


def extract_bedrooms(
    title: str,
    description: str,
    base_values: Iterable[str | None] = (),
    area: float | None = None,
    price: float | None = None,
) -> tuple[str, int | None]:
    """Trả về ``(loại căn, số ngủ)`` — vd ``("2PN+", 2)``, ``("Studio", 1)``, ``("N/A", None)``.

    ``base_values``: các chuỗi số ngủ "chuẩn" theo thứ tự ưu tiên (short-info, bảng đặc điểm, card).
    ``area``/``price``: diện tích (m²) và giá (tỷ) của chính tin, để chọn đúng token trong tin liệt kê nhiều căn.
    """
    title = (title or "").lower()
    desc = (description or "").lower()

    # Chỉ xét TIÊU ĐỀ khi tiêu đề đã nêu loại căn: phần giới thiệu dự án ở cuối mô tả
    # hay liệt kê đủ "studio, 1PN, 2PN, duplex, penthouse" -> dễ gán nhầm.
    special_text = title if _BED_TOKEN_RE.search(title) else f"{title} {desc}"
    if any(k in special_text for k in DUPLEX_KEYS):
        return "Duplex", None
    if any(k in special_text for k in SPECIAL_3PN_KEYS):
        return "3PN đặc biệt", 3

    base_n, base_studio = None, False
    for raw in base_values:
        s = clean_text(raw or "").lower()
        if not s:
            continue
        if "studio" in s:
            base_studio, base_n = True, 1
            break
        m = re.search(r"(\d+)", s)
        if m and 1 <= int(m.group(1)) <= 5:
            base_n = int(m.group(1))
            break

    cands = _candidates(title, True, area, price) + _candidates(desc, False, area, price)
    if base_n is None:
        eligible = cands
    else:
        eligible = [c for c in cands if (c["studio"] and base_n <= 1) or (not c["studio"] and c["n"] == base_n)]

    if not eligible:
        if base_studio:
            return "Studio", 1
        if base_n is not None:
            return f"{base_n}PN", base_n
        return "N/A", None

    best = max(c["score"] for c in eligible)
    winners = [c for c in eligible if c["score"] == best]
    pool = [c for c in winners if c["in_title"]] or winners
    if best == 0:
        # Không có diện tích/giá đối chiếu -> chỉ nhận '+' khi mọi ứng viên thống nhất
        plus = all(c["plus"] for c in pool)
    else:
        plus = sum(c["plus"] for c in pool) * 2 > len(pool)

    if base_studio or (any(c["studio"] for c in winners) and (base_n is None or base_n <= 1)):
        return "Studio", 1
    n = winners[0]["n"] if base_n is None else base_n
    if n is None:
        return "N/A", None
    return (f"{n}PN+" if plus else f"{n}PN"), n


def infer_unit_type_simple(text: str) -> str:
    """Bản rút gọn cho tin thuê: chỉ cần nhãn ``Studio``/``2PN``/``Duplex``... từ văn bản tự do."""
    t = (text or "").lower()
    if "studio" in t:
        return "Studio"
    if "penthouse" in t:
        return "Penthouse"
    if "duplex" in t:
        return "Duplex"
    m = re.search(r"\b(\d+)\s*(?:phòng\s*ngủ|phong\s*ngu|pn|br|bed(?:room)?|n)\b", t)
    if m and 1 <= int(m.group(1)) <= 6:
        return f"{int(m.group(1))}PN"
    return ""
