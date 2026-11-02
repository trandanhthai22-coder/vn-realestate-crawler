"""Tiện ích chuẩn hoá chuỗi tiếng Việt dùng chung cho mọi parser."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_WS_RE = re.compile(r"\s+")


def clean_text(node: Any) -> str:
    """Lấy text của node BeautifulSoup (hoặc chuỗi) và gộp mọi khoảng trắng về 1 space.

    Nhãn trong DOM batdongsan bị xuống dòng + thụt lề (vd ``Ngày\\n      đăng``),
    nên luôn phải gộp khoảng trắng trước khi so khớp.
    """
    if node is None:
        return ""
    raw = node if isinstance(node, str) else node.get_text(" ", strip=True)
    return _WS_RE.sub(" ", raw).strip()


def strip_accents(s: str | None) -> str:
    """Bỏ dấu tiếng Việt: ``Ngày đăng`` -> ``Ngay dang``."""
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def label_key(s: Any) -> str:
    """Chuẩn hoá nhãn để so khớp bền vững: gộp space, thường hoá, bỏ dấu, bỏ dấu hai chấm."""
    return strip_accents(clean_text(s)).lower().replace(":", "").strip()


def fold(s: str | None) -> str:
    """Bỏ dấu + thường hoá + thay mọi ký tự không phải chữ/số bằng 1 space."""
    value = strip_accents(s).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def to_float(s: Any) -> float | None:
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return None


def contains_any(text: str, keywords: list[str] | tuple[str, ...]) -> bool:
    """So khớp không phân biệt dấu/hoa thường; ``-`` trong URL được coi như khoảng trắng."""
    folded = fold(text)
    return any(fold(k) and fold(k) in folded for k in keywords)
