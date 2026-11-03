"""Adapter cho guland.vn (port từ ``GulandScraper`` trong ``Data_Crawler.py``).

Trang danh mục: ``.c-sdb-card``  — link ``h3.c-sdb-card__tle a`` (URL tin có ``/post/``),
                 ngày ``.profile-info__stl span`` (dạng tương đối: "2 tuần trước").
                 Phân trang bằng query ``?page=N``.
Trang chi tiết:  ``h1.dtl-tle``; giá ``.dtl-prc__ttl``; diện tích ``.dtl-prc__dtc``;
                 đơn giá ``.dtl-prc__sgl``; các dòng phụ ``.dtl-stl__row`` (địa chỉ, "Mã tin:",
                 "Dự án:", "Cập nhật ... trước"); mô tả ``.dtl-inf__dsr``.
Guland không công khai "Ngày hết hạn" / "Loại tin" -> để trống. Ngày đăng là ngày CẬP NHẬT gần nhất.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from bdscrawler.dates import parse_date
from bdscrawler.sites.batdongsan import Card, Detail
from bdscrawler.text import clean_text, strip_accents

SITE_URL = "https://guland.vn"


def page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    p = urlparse(base_url)
    query = dict(parse_qsl(p.query))
    query["page"] = str(page)
    return urlunparse(p._replace(query=urlencode(query)))


def is_listing_url(href: str) -> bool:
    return "/post/" in href


def _card_numbers(card) -> tuple[str, str]:
    """Giá / diện tích hiển thị trên card (nếu có) — trang chi tiết vẫn là nguồn chính."""
    price = area = ""
    big = card.select_one(".sdb-inf-data.data-size-xl b")
    if big:
        price = clean_text(big)
    for node in card.select(".sdb-inf-data b"):
        text = clean_text(node)
        if not area and re.search(r"m²|m2", text, re.IGNORECASE) and not re.search(r"/\s*m", text):
            area = text
        if not price and re.search(r"tỷ|triệu", text, re.IGNORECASE) and not re.search(r"/\s*m", text):
            price = text
    return price, area


def parse_cards(html: str, base: str = SITE_URL) -> list[Card]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select(".c-sdb-card"):
        anchor = card.select_one("h3.c-sdb-card__tle a[href]")
        if anchor is None:
            continue
        link = urljoin(base, str(anchor["href"]).split("#")[0])
        if not is_listing_url(link):
            continue
        date_el = card.select_one(".profile-info__stl span")
        price, area = _card_numbers(card)
        m = re.search(r"-(\d{5,})/?$", link)
        out.append(Card(
            title=clean_text(anchor),
            price_raw=price,
            area_raw=area,
            location=clean_text(card.select_one(".c-sdb-card__adr, .sdb-inf-adr")),
            link=link,
            date_raw=clean_text(date_el),
            product_id=m.group(1) if m else "",
        ))
    return out


def parse_detail(html: str, url: str = "") -> Detail:
    soup = BeautifulSoup(html, "html.parser")
    d = Detail(url=url)
    d.title = clean_text(soup.select_one("h1.dtl-tle") or soup.select_one("h1"))
    d.description = clean_text(soup.select_one(".dtl-inf__dsr"))
    d.price_raw = clean_text(soup.select_one(".dtl-prc__ttl"))
    d.area_raw = clean_text(soup.select_one(".dtl-prc__dtc"))
    for node in soup.select(".dtl-prc__sgl"):
        text = clean_text(node)
        if re.search(r"/\s*m", text, re.IGNORECASE):
            d.unit_price_raw = text
            break

    for row in soup.select(".dtl-stl__row"):
        text = clean_text(row)
        plain = strip_accents(text).lower()
        if "ma tin" in plain:
            m = re.search(r"ma tin\s*:?\s*(\d+)", plain)
            if m:
                d.listing_id = m.group(1)
        elif "du an" in plain:
            bold = row.select_one("b")
            d.specs["du an"] = clean_text(bold) if bold else text
        elif "cap nhat" in plain or "dang" in plain:
            d.published = d.published or parse_date(text)
        elif row.select_one("i.mdi-map-marker-outline") or "huyen" in plain or "ha noi" in plain:
            d.address = d.address or text

    if not d.listing_id:
        m = re.search(r"-(\d{5,})/?$", url)
        d.listing_id = m.group(1) if m else ""
    return d
