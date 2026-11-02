"""Mode ``detail``: mở từng tin chi tiết và xuất theo template báo cáo Hải Phòng.

``record`` trong config chọn bộ cột:

* ``apartment_rent`` / ``apartment_sale`` — căn hộ cho thuê / bán (port ``nha_thue_cao_tang_hoa_cai.py``,
  ``gia mua dut hoa cai.py``, ``Shop_house_chan_de_HP.py``)
* ``lowrise_sale`` / ``lowrise_rent`` — biệt thự, liền kề, shophouse (port ``LK/*.py``,
  ``shop_house_thuong_mai/*.py``, ``mua_SH_hai_phong.py``)
"""

from __future__ import annotations

import logging

from bdscrawler.bedrooms import infer_unit_type_simple
from bdscrawler.config import Project
from bdscrawler.dates import fmt
from bdscrawler.features import (business_purpose, construction_area, floors, frontage, furniture_details,
                                 infer_furniture, location_description, property_type, rental_terms,
                                 road_width, target_audience, unit_code, unit_status)
from bdscrawler.numbers import first_number, parse_area, parse_price, parse_rent_million
from bdscrawler.pipelines.base import Pipeline
from bdscrawler.pipelines.lowrise import identify_subdivision
from bdscrawler.sites import batdongsan as bds
from bdscrawler.text import contains_any

log = logging.getLogger(__name__)

APARTMENT_COLUMNS = [
    "Ngày đăng", "VỊ TRÍ", "DỰ ÁN", "Tòa", "Loại căn", "Diện tích thông thủy",
    "Tình trạng căn hộ: Có đồ/ Không đồ", "Chi tiết nội thất", "Giá thuê/ tháng (all in, triệu/ căn/ tháng)",
    "Phí dịch vụ (nếu có)", "Đơn giá bán all-in tham khảo (triệu/m2)", "Ticket-size tham khảo (all-in, tỷ/ căn)",
    "Tỷ suất cho thuê/ năm", "Đối tượng/Mục đích thuê", "Note (ai hay thuê, công suất lấp đầy…)", "Link",
]
LOWRISE_COLUMNS = [
    "Ngày đăng", "Ngày hết hạn", "Loại tin", "Mã tin", "Dự án", "Phân khu", "Mã căn", "Loại căn",
    "Mô tả vị trí", "Đường mặt tiền / Lộ giới (m)", "Diện tích đất (m²)", "Mặt tiền (m)",
    "Diện tích xây dựng (m²)", "Số tầng", "Tình trạng căn", "Giá bán (tỷ)", "Đơn giá (triệu/m²)",
    "Giá thuê (triệu/tháng)", "Cho thuê nguyên căn – Giá (triệu/tháng)", "Cho thuê theo tầng – Tầng",
    "Cho thuê theo tầng – Giá (triệu/tháng/tầng)", "Mục đích kinh doanh", "Tiêu đề", "Link", "ScrapedAt",
]
_LOWRISE_KEYS = ("shophouse", "shop chan de", "shop khoi de", "lien ke", "biet thu", "nha pho thuong mai")


class DetailPipeline(Pipeline):
    dedup_keys = ("Link",)

    def __init__(self, job, *args, **kwargs):
        super().__init__(job, *args, **kwargs)
        lowrise = job.record.startswith("lowrise")
        self.columns = LOWRISE_COLUMNS if lowrise else APARTMENT_COLUMNS
        self.sort_by = ["Dự án", "Phân khu", "Loại căn"] if lowrise else ["DỰ ÁN", "Tòa", "Loại căn"]
        self.summary_by = ["Dự án", "Phân khu", "Loại căn"] if lowrise else ["DỰ ÁN", "Loại căn"]
        self._seen: set[str] = set()

    def _alias_ok(self, text: str, project: Project) -> bool:
        return not project.aliases or contains_any(text, project.aliases)

    def process_page(self, cards: list[bds.Card], project: Project, base_url: str) -> list[dict]:
        rows = []
        for card in cards:
            link = card.link.rstrip("/")
            if not link or link in self._seen or not bds.is_listing_url(link):
                continue
            if not self._alias_ok(card.text, project):
                continue
            if card.published and card.published < self.start:
                continue
            self._seen.add(link)
            html = self.fetcher.fetch(link, referer=base_url, retries=2)
            if not html:
                continue
            try:
                row = self.build(bds.parse_detail(html, link), card, project)
            except Exception as exc:
                log.debug("Bỏ qua tin lỗi %s: %s", link, exc)
                continue
            if row:
                rows.append(row)
        return rows

    def build(self, d: bds.Detail, card: bds.Card, project: Project) -> dict | None:
        text = f"{d.text} {card.location}"
        if not self._alias_ok(f"{text} {d.url}", project):
            return None
        published = d.published or card.published
        if not self.in_range(published):
            return None
        if self.job.record.startswith("lowrise"):
            return self._lowrise(d, card, project, published, text)
        return self._apartment(d, card, project, published, text)

    def _apartment(self, d, card, project, published, text) -> dict | None:
        if self.job.exclude_lowrise and contains_any(f"{text} {d.url}", list(_LOWRISE_KEYS)):
            return None
        unit_type = infer_unit_type_simple(d.beds_raw and f"{d.beds_raw} pn") or infer_unit_type_simple(text)
        if self.job.record == "apartment_sale" and not unit_type:
            return None
        area = parse_area(d.area_raw) or parse_area(card.area_raw)
        rent = ticket = unit_price = None
        if self.job.record == "apartment_rent":
            rent = parse_rent_million(d.price_raw) or parse_rent_million(card.price_raw)
        else:
            ticket, unit_price = parse_price(d.price_raw or card.price_raw, area)
        furniture = d.specs.get("noi that") or infer_furniture(text)
        details = furniture_details(text) or ("Không đồ" if furniture == "Không đồ" else "")
        tower = self.job.tower_rules(project).extract([d.title, d.description])
        return {
            "Ngày đăng": fmt(published),
            "VỊ TRÍ": d.address or card.location or project.default_address,
            "DỰ ÁN": project.display,
            "Tòa": tower,
            "Loại căn": unit_type,
            "Diện tích thông thủy": area,
            "Tình trạng căn hộ: Có đồ/ Không đồ": furniture,
            "Chi tiết nội thất": details,
            "Giá thuê/ tháng (all in, triệu/ căn/ tháng)": rent,
            "Phí dịch vụ (nếu có)": "",
            "Đơn giá bán all-in tham khảo (triệu/m2)": unit_price,
            "Ticket-size tham khảo (all-in, tỷ/ căn)": ticket,
            "Tỷ suất cho thuê/ năm": "",
            "Đối tượng/Mục đích thuê": target_audience(text),
            "Note (ai hay thuê, công suất lấp đầy…)": " | ".join(p for p in (d.title, d.description[:1000]) if p),
            "Link": d.url,
        }

    def _lowrise(self, d, card, project, published, text) -> dict | None:
        code = unit_code(f"{d.title} {d.description[:400]}", project.all_prefixes)
        zone = identify_subdivision(text, project, code)
        zone = project.zone_renames.get(zone, zone)
        if zone in project.exclude_zones:
            return None
        land_area = parse_area(d.area_raw) or first_number(
            text, r"(?:diện\s*tích\s*đất|dt\s*đất)\s*:?\s*(\d+(?:[.,]\d+)?)\s*(?:m2|m²)")
        sale = rent = None
        unit_price = None
        if self.job.record == "lowrise_sale":
            sale, unit_price = parse_price(d.price_raw or card.price_raw, land_area)
        else:
            rent = parse_rent_million(d.price_raw or card.price_raw)
        whole, floor_list, per_floor = rental_terms(text)
        return {
            "Ngày đăng": fmt(published),
            "Ngày hết hạn": fmt(d.expires),
            "Loại tin": d.listing_type,
            "Mã tin": d.listing_id,
            "Dự án": project.display,
            "Phân khu": zone if zone != "N/A" else (project.zone or ""),
            "Mã căn": code if code != "N/A" else "",
            "Loại căn": property_type(text, detailed=True),
            "Mô tả vị trí": location_description(d.description),
            "Đường mặt tiền / Lộ giới (m)": road_width(text),
            "Diện tích đất (m²)": land_area,
            "Mặt tiền (m)": first_number(d.specs.get("mat tien", ""), r"(\d+(?:[.,]\d+)?)") or frontage(text),
            "Diện tích xây dựng (m²)": construction_area(text),
            "Số tầng": int(first_number(d.specs.get("so tang", ""), r"(\d+)") or 0) or floors(text),
            "Tình trạng căn": unit_status(text),
            "Giá bán (tỷ)": sale,
            "Đơn giá (triệu/m²)": unit_price,
            "Giá thuê (triệu/tháng)": rent,
            "Cho thuê nguyên căn – Giá (triệu/tháng)": whole,
            "Cho thuê theo tầng – Tầng": floor_list,
            "Cho thuê theo tầng – Giá (triệu/tháng/tầng)": per_floor,
            "Mục đích kinh doanh": business_purpose(text),
            "Tiêu đề": d.title,
            "Link": d.url,
            "ScrapedAt": self.scraped_at,
        }
