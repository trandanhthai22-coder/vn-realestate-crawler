"""Quy tắc khai báo (trong file TOML) để nhận diện mã tòa và phân khu.

Mỗi dự án có cách đặt mã tòa riêng (``S1.01``, ``TC3``, ``West A``, ``BF2``...). Thay vì
viết một hàm ``extract_tower`` cho từng dự án, ta mô tả chúng bằng danh sách quy tắc::

    [[towers]]
    pattern = '\\bt[oòóô]a\\s+(s[1-4][.\\-\\s]?\\d{2})\\b'   # regex, không phân biệt hoa thường
    value = "{1}"            # template; {0} = cả cụm khớp, {1}.. = các group (mặc định {1} hoặc {0})
    normalize = "compact"    # compact | dot | upper | title | none
    fallback = false         # true = chỉ xét sau khi mọi quy tắc thường thất bại trên mọi đoạn văn

Thứ tự xét: với từng đoạn văn (tiêu đề trước, rồi mô tả, rồi vị trí + link) thử lần lượt các
quy tắc thường; nếu không có kết quả mới tới các quy tắc ``fallback``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from bdscrawler.text import strip_accents

NORMALIZERS = {
    "compact": lambda s: re.sub(r"[.\-_\s]", "", s).upper(),
    "dot": lambda s: re.sub(r"[\-_\s]+", ".", s.strip()).upper(),
    "upper": lambda s: s.strip().upper(),
    "title": lambda s: s.strip().title(),
    "none": lambda s: s.strip(),
}


def _render(template: str | None, m: re.Match) -> str:
    groups = [m.group(0)] + [g or "" for g in m.groups()]
    if template is None:
        return groups[1] if len(groups) > 1 and groups[1] else groups[0]
    return template.format(*groups)


@dataclass
class Rule:
    pattern: re.Pattern
    value: str | None = None
    normalize: str = "compact"
    fallback: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any], default_normalize: str = "compact") -> "Rule":
        norm = d.get("normalize", default_normalize)
        if norm not in NORMALIZERS:
            raise ValueError(f"normalize không hợp lệ: {norm!r} (chọn {', '.join(NORMALIZERS)})")
        return cls(
            pattern=re.compile(d["pattern"], re.IGNORECASE),
            value=d.get("value"),
            normalize=norm,
            fallback=bool(d.get("fallback", False)),
        )

    def apply(self, text: str) -> str:
        m = self.pattern.search(text)
        if not m:
            return ""
        return NORMALIZERS[self.normalize](_render(self.value, m))

    def apply_all(self, text: str) -> list[str]:
        """Mọi giá trị khác nhau khớp trong đoạn văn, giữ thứ tự xuất hiện."""
        values = (NORMALIZERS[self.normalize](_render(self.value, m)) for m in self.pattern.finditer(text))
        return list(dict.fromkeys(v for v in values if v))


@dataclass
class TowerRules:
    rules: list[Rule] = field(default_factory=list)
    exclude: set[str] = field(default_factory=set)
    accent_insensitive: bool = False
    # "first": lấy mã đầu tiên | "blank": một đoạn văn nêu NHIỀU tòa khác nhau (tin rổ hàng,
    # phần giới thiệu "dự án gồm tòa Y4, Y5, M1...") -> để trống thay vì đoán
    on_multiple: str = "first"

    @classmethod
    def from_config(cls, rules: list[dict], exclude: list[str] | None = None,
                    accent_insensitive: bool = False, on_multiple: str = "first") -> "TowerRules":
        if on_multiple not in ("first", "blank"):
            raise ValueError(f"on_multiple phải là 'first' hoặc 'blank', nhận {on_multiple!r}")
        return cls([Rule.from_dict(r) for r in rules or []], {e.upper() for e in exclude or []},
                   accent_insensitive, on_multiple)

    def _prep(self, text: str) -> str:
        t = (text or "").lower()
        return strip_accents(t) if self.accent_insensitive else t

    def extract(self, texts: list[str]) -> str:
        prepared = [self._prep(t) for t in texts if t]
        for group in ([r for r in self.rules if not r.fallback], [r for r in self.rules if r.fallback]):
            for text in prepared:
                if self.on_multiple == "blank":
                    # Gom mã của MỌI quy tắc trong đoạn văn này rồi mới đếm
                    values = list(dict.fromkeys(v for rule in group for v in rule.apply_all(text)
                                                if v.upper() not in self.exclude))
                    if len(values) > 1:
                        return ""
                    if values:
                        return values[0]
                    continue
                for rule in group:
                    value = rule.apply(text)
                    if value and value.upper() not in self.exclude:
                        return value
        return ""


@dataclass
class ZoneRule:
    pattern: re.Pattern
    value: str
    on: str = "tower"  # "tower" | "text"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ZoneRule":
        on = d.get("on", "tower")
        if on not in ("tower", "text"):
            raise ValueError(f"zones.on phải là 'tower' hoặc 'text', nhận {on!r}")
        return cls(re.compile(d["pattern"], re.IGNORECASE), d["value"], on)


@dataclass
class ZoneRules:
    rules: list[ZoneRule] = field(default_factory=list)

    @classmethod
    def from_config(cls, rules: list[dict]) -> "ZoneRules":
        return cls([ZoneRule.from_dict(r) for r in rules or []])

    def identify(self, tower: str, text: str, default: str) -> str:
        folded = strip_accents(text or "").lower()
        for rule in self.rules:
            target = tower if rule.on == "tower" else folded
            if not target:
                continue
            m = rule.pattern.search(target)
            if m:
                return _render(rule.value, m)
        return default
