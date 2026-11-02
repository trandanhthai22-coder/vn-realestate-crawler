"""Mode ``lowrise``: giá bán biệt thự / liền kề / shophouse các KĐT (port từ ``crawl_thấp_tầng 1.py``).

Chỉ đọc card ở trang danh mục (không mở trang chi tiết) -> nhanh. Xuất 3 sheet:
``Data`` (chi tiết), ``Raw data crawl`` (template Year/Month/Week...), ``Phân khu trống``.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

import pandas as pd

from bdscrawler.config import Project
from bdscrawler.dates import fmt, week_of_month
from bdscrawler.features import construction_area, extract_direction, extract_view, property_type, unit_code
from bdscrawler.numbers import parse_area, parse_price
from bdscrawler.pipelines.base import Pipeline
from bdscrawler.sites import batdongsan as bds
from bdscrawler.text import fold

log = logging.getLogger(__name__)

RAW_COLUMNS = ["Year", "Month", "Week", "Thời gian", "KĐT", "Phân khu", "Mã Căn", "Loại hình", "Diện tích",
               "Tổng giá", "Đơn giá", "Diện tích xây dựng", "Chi phí xây dựng", "Giá NO đất & hạ tầng",
               "Đơn giá NO đất & hạ tầng /m2 đất", "Ghi chú"]


def identify_subdivision(text: str, project: Project, code: str) -> str:
    """Ưu tiên tên phân khu viết đầy đủ (đáng tin hơn), sau đó tới tiền tố mã căn dài nhất."""
    folded = f" {fold(text)} "
    for canonical, aliases in project.subdivisions.items():
        for alias in [canonical, *aliases]:
            if f" {fold(alias)} " in folded:
                return canonical
    if code and code != "N/A":
        compact = re.sub(r"[^A-Z0-9]", "", code.upper())
        hits = sorted(((len(p), name) for name, prefixes in project.code_prefixes.items()
                       for p in prefixes if compact.startswith(p.upper())), reverse=True)
        if hits:
            return hits[0][1]
    return "N/A"


def classify_type(base_type: str, project: Project, zone: str, area: float | None) -> str:
    for rule in project.type_rules:
        if rule.matches(zone, area):
            return rule.resolve(base_type)
    return base_type


class LowrisePipeline(Pipeline):
    columns = ["Dự án", "Phân khu", "Mã căn", "Loại hình", "Diện tích đất (m2)", "Tổng giá (tỷ)",
               "Đơn giá All-in (triệu/m2)", "Diện tích xây dựng (m2)", "Chi phí xây dựng (tỷ)",
               "Giá NO đất & hạ tầng (tỷ)", "Đơn giá NO đất & hạ tầng (triệu/m2)", "Hướng", "Phân loại view",
               "Mô tả view", "Địa điểm", "Ngày đăng", "Tiêu đề", "Mô tả", "Giá gốc trên tin",
               "Diện tích gốc trên tin", "Link", "ScrapedAt"]
    sort_by = ["Dự án", "Phân khu", "Loại hình", "Diện tích đất (m2)"]
    summary_by = ["Dự án", "Phân khu", "Loại hình"]
    dedup_keys = ("Tiêu đề",)

    def process_page(self, cards: list[bds.Card], project: Project, base_url: str) -> list[dict]:
        rows = []
        for card in cards:
            if not self.in_range(card.published) or not self.project_matches(card.text, project):
                continue
            area = parse_area(card.area_raw)
            total, unit = parse_price(card.price_raw, area)
            if self.job.require_area_and_price and (area is None or total is None):
                continue  # cần cả diện tích đất và tổng giá để tính đơn giá

            text = card.text
            code = unit_code(text, project.all_prefixes)
            zone = identify_subdivision(text, project, code)
            zone = project.zone_renames.get(zone, zone)
            if zone in project.exclude_zones:
                continue
            ptype = classify_type(property_type(text), project, zone, area)

            build_area = construction_area(text)
            build_cost = land_price = land_unit = None
            if build_area is not None and self.job.construction_rate > 0 and total is not None:
                build_cost = build_area * self.job.construction_rate / 1000
                land_price = total - build_cost
                if land_price >= 0 and area:
                    land_unit = land_price * 1000 / area
                else:
                    build_cost = land_price = None
            view, view_terms = extract_view(text)
            rows.append({
                "Dự án": project.display,
                "Phân khu": zone,
                "Mã căn": code,
                "Loại hình": ptype,
                "Diện tích đất (m2)": area,
                "Tổng giá (tỷ)": total,
                "Đơn giá All-in (triệu/m2)": unit,
                "Diện tích xây dựng (m2)": build_area,
                "Chi phí xây dựng (tỷ)": round(build_cost, 4) if build_cost is not None else None,
                "Giá NO đất & hạ tầng (tỷ)": round(land_price, 4) if land_price is not None else None,
                "Đơn giá NO đất & hạ tầng (triệu/m2)": round(land_unit, 2) if land_unit is not None else None,
                "Hướng": extract_direction(text),
                "Phân loại view": view,
                "Mô tả view": view_terms,
                "Địa điểm": card.location or "N/A",
                "Ngày đăng": fmt(card.published),
                "Tiêu đề": card.title or "N/A",
                "Mô tả": card.description,
                "Giá gốc trên tin": card.price_raw or "N/A",
                "Diện tích gốc trên tin": card.area_raw or "N/A",
                "Link": card.link,
                "ScrapedAt": self.scraped_at,
            })
        return rows

    def extra_sheets(self, rows: list[dict]) -> dict[str, pd.DataFrame]:
        raw = []
        for r in rows:
            d = datetime.strptime(r["Ngày đăng"], "%d/%m/%Y")
            raw.append([d.year, d.month, week_of_month(d.day), d, r["Dự án"], r["Phân khu"], r["Mã căn"],
                        r["Loại hình"], r["Diện tích đất (m2)"], r["Tổng giá (tỷ)"], r["Đơn giá All-in (triệu/m2)"],
                        r["Diện tích xây dựng (m2)"], r["Chi phí xây dựng (tỷ)"], r["Giá NO đất & hạ tầng (tỷ)"],
                        r["Đơn giá NO đất & hạ tầng (triệu/m2)"], r["Link"]])
        df = pd.DataFrame(raw, columns=RAW_COLUMNS)
        missing = df["Phân khu"].isin(["N/A", ""]) | df["Phân khu"].isna()
        return {"Raw data crawl": df[~missing], "Phân khu trống": df[missing]}
