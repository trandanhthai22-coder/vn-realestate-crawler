"""Đọc & kiểm tra file cấu hình job (TOML). Xem docs/CONFIG.md để biết toàn bộ trường."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bdscrawler.rules import TowerRules, ZoneRules

MODES = ("apartment", "lowrise", "detail")
RECORDS = ("apartment_sale", "apartment_rent", "lowrise_sale", "lowrise_rent")


@dataclass
class TypeRule:
    """Quy tắc phân loại thấp tầng theo phân khu + diện tích (xét theo thứ tự, khớp đầu tiên thắng)."""
    type: str
    zones: list[str] = field(default_factory=list)
    area_lt: float | None = None
    area_lte: float | None = None
    area_gt: float | None = None
    area_gte: float | None = None
    keep_types: list[str] = field(default_factory=list)

    def matches(self, zone: str, area: float | None) -> bool:
        if self.zones and zone not in self.zones:
            return False
        bounds = (self.area_lt, self.area_lte, self.area_gt, self.area_gte)
        if any(b is not None for b in bounds) or self.keep_types:
            if area is None:
                return False
        return ((self.area_lt is None or area < self.area_lt)
                and (self.area_lte is None or area <= self.area_lte)
                and (self.area_gt is None or area > self.area_gt)
                and (self.area_gte is None or area >= self.area_gte))

    def resolve(self, base_type: str) -> str:
        return base_type if base_type in self.keep_types else self.type


@dataclass
class Project:
    name: str
    urls: list[str]
    zone: str = ""
    label: str = ""          # giá trị cột "Dự án" (mặc định = name)
    keywords: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    towers: TowerRules | None = None
    zones: ZoneRules | None = None
    # thấp tầng
    province: str = ""
    district: str = ""
    subdivisions: dict[str, list[str]] = field(default_factory=dict)
    code_prefixes: dict[str, list[str]] = field(default_factory=dict)
    exclude_zones: list[str] = field(default_factory=list)
    zone_renames: dict[str, str] = field(default_factory=dict)
    type_rules: list[TypeRule] = field(default_factory=list)
    default_address: str = ""

    @property
    def display(self) -> str:
        return self.label or self.name

    @property
    def all_prefixes(self) -> list[str]:
        return [p for prefixes in self.code_prefixes.values() for p in prefixes]


@dataclass
class Job:
    name: str
    mode: str
    path: Path
    site: str = "https://batdongsan.com.vn"
    output: str = "output"
    benchmark: str = ""
    record: str = "apartment_sale"
    projects: list[Project] = field(default_factory=list)
    towers: TowerRules = field(default_factory=TowerRules)
    zones: ZoneRules = field(default_factory=ZoneRules)
    zone_order: list[str] = field(default_factory=list)
    zone_colors: dict[str, str] = field(default_factory=dict)
    # [crawl]
    start_date: date | None = None
    end_date: date | None = None
    max_pages: int = 30
    delay: float = 1.0
    fetch_detail: bool = True
    stop_on_empty_page: bool = True
    include_expired: bool = False
    # [filters]
    apartments_only: bool = False
    studio_only: bool = False
    exclude_lowrise: bool = False
    unit_price_min: float | None = None
    unit_price_max: float | None = None
    location_any: list[re.Pattern] = field(default_factory=list)
    require_area_and_price: bool = False
    # [lowrise]
    construction_rate: float = 8.0

    def tower_rules(self, project: Project) -> TowerRules:
        return project.towers if project.towers is not None else self.towers

    def zone_rules(self, project: Project) -> ZoneRules:
        return project.zones if project.zones is not None else self.zones


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _as_date(v: Any) -> date | None:
    """TOML cho phép ``2026-10-15`` (kiểu date) hoặc ``"2026-10-15"`` (chuỗi)."""
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def _tower_rules(raw: dict, opts: dict) -> TowerRules:
    return TowerRules.from_config(raw, opts.get("exclude"), bool(opts.get("accent_insensitive", False)))


def _project(raw: dict, site: str, defaults: dict) -> Project:
    if "name" not in raw:
        raise ValueError("Mỗi [[projects]] cần có 'name'")
    urls = [urljoin(site + "/", u.lstrip("/")) if not u.startswith("http") else u
            for u in _as_list(raw.get("urls") or raw.get("url") or raw.get("path"))]
    if not urls:
        raise ValueError(f"Dự án {raw['name']!r} thiếu 'urls'")
    towers = None
    if "towers" in raw:
        towers = _tower_rules(raw["towers"], raw.get("tower_options", defaults.get("tower_options", {})))
    return Project(
        name=raw["name"],
        urls=urls,
        zone=raw.get("zone", ""),
        label=raw.get("label", defaults.get("label", "")),
        keywords=_as_list(raw.get("keywords")),
        aliases=_as_list(raw.get("aliases")),
        towers=towers,
        zones=ZoneRules.from_config(raw["zones"]) if "zones" in raw else None,
        province=raw.get("province", ""),
        district=raw.get("district", ""),
        subdivisions={k: _as_list(v) for k, v in raw.get("subdivisions", {}).items()},
        code_prefixes={k: _as_list(v) for k, v in raw.get("code_prefixes", {}).items()},
        exclude_zones=_as_list(raw.get("exclude_zones")),
        zone_renames=dict(raw.get("zone_renames", {})),
        type_rules=[TypeRule(**r) for r in raw.get("type_rules", [])],
        default_address=raw.get("default_address", defaults.get("default_address", "")),
    )


def load_job(path: str | Path) -> Job:
    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)

    mode = raw.get("mode", "apartment")
    if mode not in MODES:
        raise ValueError(f"{path.name}: mode phải là một trong {MODES}, nhận {mode!r}")
    record = raw.get("record", "apartment_sale")
    if mode == "detail" and record not in RECORDS:
        raise ValueError(f"{path.name}: record phải là một trong {RECORDS}")

    site = raw.get("site", "https://batdongsan.com.vn").rstrip("/")
    crawl, filters = raw.get("crawl", {}), raw.get("filters", {})
    defaults = {"label": raw.get("project_label", ""), "default_address": raw.get("default_address", ""),
                "tower_options": raw.get("tower_options", {})}

    start, end = _as_date(crawl.get("start_date")), _as_date(crawl.get("end_date"))
    if start is None and "days_back" in crawl:
        start = date.today() - timedelta(days=int(crawl["days_back"]))

    job = Job(
        name=raw.get("name", path.stem),
        mode=mode,
        path=path,
        site=site,
        output=raw.get("output", path.stem),
        benchmark=raw.get("benchmark", ""),
        record=record,
        projects=[_project(p, site, defaults) for p in raw.get("projects", [])],
        towers=_tower_rules(raw.get("towers", []), raw.get("tower_options", {})),
        zones=ZoneRules.from_config(raw.get("zones", [])),
        zone_order=_as_list(raw.get("zone_order")),
        zone_colors=dict(raw.get("zone_colors", {})),
        start_date=start,
        end_date=end,
        max_pages=int(crawl.get("max_pages", 30)),
        delay=float(crawl.get("delay", 1.0)),
        fetch_detail=bool(crawl.get("fetch_detail", True)),
        stop_on_empty_page=bool(crawl.get("stop_on_empty_page", True)),
        include_expired=bool(crawl.get("include_expired", False)),
        apartments_only=bool(filters.get("apartments_only", False)),
        studio_only=bool(filters.get("studio_only", False)),
        exclude_lowrise=bool(filters.get("exclude_lowrise", False)),
        unit_price_min=filters.get("unit_price_min"),
        unit_price_max=filters.get("unit_price_max"),
        location_any=[re.compile(p, re.IGNORECASE) for p in _as_list(filters.get("location_any"))],
        require_area_and_price=bool(filters.get("require_area_and_price", mode == "lowrise")),
        construction_rate=float(raw.get("lowrise", {}).get("construction_rate", 8.0)),
    )
    if not job.projects:
        raise ValueError(f"{path.name}: cần ít nhất một [[projects]]")
    return job


def discover(paths: list[str | Path]) -> list[Path]:
    """Nhận file .toml hoặc thư mục (quét đệ quy)."""
    out: list[Path] = []
    for p in map(Path, paths):
        out.extend(sorted(p.rglob("*.toml")) if p.is_dir() else [p])
    return out
