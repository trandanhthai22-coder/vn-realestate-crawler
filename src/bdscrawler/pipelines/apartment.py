"""Mode ``apartment``: benchmark giá bán căn hộ theo dự án / phân khu / tòa / loại căn.

Thay thế 12 script ``VH_SM/*.py`` và ``vinhome_OP/*.py`` cũ — mọi khác biệt giữa chúng
(URL, mã tòa, phân khu, bộ lọc) nằm trong file ``configs/apartment/*.toml``.
"""

from __future__ import annotations

import logging

from bdscrawler.bedrooms import extract_bedrooms
from bdscrawler.config import Project
from bdscrawler.dates import fmt
from bdscrawler.features import direction_from_specs, extract_direction
from bdscrawler.numbers import parse_area, parse_price_billion
from bdscrawler.pipelines.base import Pipeline
from bdscrawler.sites import batdongsan as bds

log = logging.getLogger(__name__)

PRICE_COL = "Giá all-in (VNĐ tỷ)"
AREA_COL = "Diện tích thông thủy"
UNIT_COL = "Đơn giá (triệu/m²)"


class ApartmentPipeline(Pipeline):
    columns = ["Benchmark", "Dự án", "Phân khu", "Tòa", "Loại căn", "Số Ngủ", AREA_COL, PRICE_COL, UNIT_COL,
               "Hướng", "Vị trí", "Ngày đăng", "Ngày hết hạn", "Loại tin", "Mã tin", "Tiêu đề", "Link", "ScrapedAt"]
    sort_by = ["Phân khu", "Tòa", "Loại căn", "Ngày đăng"]
    summary_by = ["Phân khu", "Tòa", "Loại căn"]
    dedup_keys = ("Tiêu đề", PRICE_COL)

    def process_page(self, cards: list[bds.Card], project: Project, base_url: str) -> list[dict]:
        rows = []
        for card in cards:
            try:
                row = self.process_card(card, project, base_url)
            except Exception as exc:  # một card lỗi không được làm hỏng cả trang
                log.debug("Bỏ qua card lỗi %s: %s", card.link, exc)
                continue
            if row:
                rows.append(row)
        return rows

    def process_card(self, card: bds.Card, project: Project, base_url: str) -> dict | None:
        job = self.job
        if not card.link:
            return None
        if job.apartments_only and "/ban-can-ho-chung-cu" not in card.link:
            return None  # URL "nha-dat-ban-..." trả về cả shophouse, làm lệch giá trung bình
        if not self.project_matches(card.text, project) or not self.location_ok(card.text, project, card.link):
            return None
        # Ngày trên card là ngày đẩy tin (>= ngày đăng gốc): card đã cũ hơn start thì tin chắc chắn cũ
        # -> bỏ qua luôn, không tốn request mở trang chi tiết.
        if card.published and card.published < self.start:
            return None

        detail = bds.Detail(url=card.link)
        if job.fetch_detail:
            html = self.fetcher.fetch(card.link, referer=base_url, retries=2)
            if html:
                detail = bds.parse_detail(html, card.link)
        published = detail.published or card.published
        if not self.in_range(published):
            return None

        price = parse_price_billion(detail.price_raw) or parse_price_billion(card.price_raw)
        area = parse_area(detail.area_raw) or parse_area(card.area_raw)
        title = detail.title or card.title
        desc = detail.description or card.description
        unit_label, beds = extract_bedrooms(
            title, desc, [detail.beds_raw, detail.specs.get("so phong ngu"), card.beds_raw], area, price)
        if job.studio_only and unit_label != "Studio":
            return None

        tower = job.tower_rules(project).extract([title, desc, f"{card.location} {card.link}"])
        zone = job.zone_rules(project).identify(tower, f"{title} {desc} {card.location}", project.zone or project.name)
        unit_price = round(price * 1000 / area, 1) if price and area else None
        if unit_price is not None and (
                (job.unit_price_min is not None and unit_price < job.unit_price_min)
                or (job.unit_price_max is not None and unit_price > job.unit_price_max)):
            return None

        return {
            "Benchmark": job.benchmark,
            "Dự án": project.display,
            "Phân khu": zone,
            "Tòa": tower,
            "Loại căn": unit_label,
            "Số Ngủ": beds,
            AREA_COL: area,
            PRICE_COL: price,
            UNIT_COL: unit_price,
            "Hướng": direction_from_specs(detail.specs) or extract_direction(f"{title} {desc}"),
            "Vị trí": card.location or detail.address,
            "Ngày đăng": fmt(published),
            "Ngày hết hạn": fmt(detail.expires),
            "Loại tin": detail.listing_type,
            "Mã tin": detail.listing_id or card.product_id,
            "Tiêu đề": title,
            "Link": card.link,
            "ScrapedAt": self.scraped_at,
        }

    def dedup(self, rows: list[dict]) -> list[dict]:
        # Bản gốc bỏ các tin thiếu giá hoặc diện tích trước khi xuất báo cáo
        return super().dedup([r for r in rows if r[PRICE_COL] is not None and r[AREA_COL] is not None])
