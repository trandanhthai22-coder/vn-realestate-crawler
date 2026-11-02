"""Adapter cho batdongsan.com.vn: parse trang danh mục (card) và trang chi tiết tin đăng.

Selector bám theo DOM thực tế (10/2026). Khi website đổi giao diện, chỉ cần sửa file này.

Trang chi tiết gồm các khối:
  1) ``.re__pr-short-info-item.js__pr-short-info-item``  -> khoảng giá (+ đơn giá ở ``span.ext``), diện tích, phòng ngủ
  2) ``.re__pr-short-info.re__pr-config.js__pr-config``   -> ngày đăng, ngày hết hạn, loại tin, mã tin
  3) ``h1.re__pr-title``                                   -> tiêu đề
  4) ``.js__pr-description``                               -> mô tả
  5) ``.re__pr-specs-content-item``                        -> bảng đặc điểm (hướng, số phòng ngủ, pháp lý...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from bdscrawler.dates import parse_date
from bdscrawler.text import clean_text, label_key

SITE_URL = "https://batdongsan.com.vn"


@dataclass
class Card:
    title: str = ""
    price_raw: str = ""
    area_raw: str = ""
    beds_raw: str = ""
    description: str = ""
    location: str = ""
    link: str = ""
    date_raw: str = ""
    product_id: str = ""

    @property
    def published(self) -> date | None:
        return parse_date(self.date_raw)

    @property
    def text(self) -> str:
        return " ".join((self.title, self.description, self.location, self.link))


@dataclass
class Detail:
    url: str = ""
    title: str = ""
    description: str = ""
    price_raw: str = ""
    unit_price_raw: str = ""
    area_raw: str = ""
    beds_raw: str = ""
    published: date | None = None
    expires: date | None = None
    listing_type: str = ""
    listing_id: str = ""
    address: str = ""
    specs: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join([self.title, self.description, *self.specs.values()])


def page_url(base_url: str, page: int) -> str:
    """Trang 1 = URL gốc; trang N = ``<path>/pN`` (giữ nguyên query string, vd ``?expired=true``)."""
    if page <= 1:
        return base_url
    p = urlparse(base_url)
    qs = f"?{p.query}" if p.query else ""
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}/p{page}{qs}"


def _first_text(item: Tag, selectors: tuple[str, ...]) -> str:
    for sel in selectors:
        el = item.select_one(sel)
        if el:
            text = clean_text(el)
            if text:
                return text
    return ""


def find_cards(soup: BeautifulSoup) -> list[Tag]:
    for selector in ("div.js__card", "div.re__card-full", "div[class*='re__card'][data-product-id]",
                     "article[data-product-id]"):
        cards = soup.select(selector)
        if cards:
            seen: set[str] = set()
            out = []
            for card in cards:
                marker = str(card.get("data-product-id") or id(card))
                if marker not in seen:
                    seen.add(marker)
                    out.append(card)
            return out
    return []


def _card_date(item: Tag) -> str:
    for sel in ("span.re__card-published-info-published-at", "span[class*='published-at']", "time"):
        el = item.select_one(sel)
        if not el:
            continue
        for attr in ("aria-label", "title", "datetime"):
            if el.get(attr):
                return str(el[attr]).strip()
        if clean_text(el):
            return clean_text(el)
    m = re.search(r"hôm nay|hôm qua|\d+\s*(?:phút|giờ|ngày|tuần|tháng)\s*trước|\d{1,2}/\d{1,2}/\d{4}",
                  clean_text(item), re.IGNORECASE)
    return m.group(0) if m else ""


def _card_link(item: Tag, base: str) -> str:
    for sel in ("a.js__product-link-for-product-id[href]", "a.re__card-title[href]", "a[href*='-pr'][href]", "a[href]"):
        el = item.select_one(sel)
        if el and el.get("href"):
            return urljoin(base, str(el["href"]).split("#")[0])
    return ""


def parse_cards(html: str, base: str = SITE_URL) -> list[Card]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for item in find_cards(soup):
        bed_el = item.select_one("span.re__card-config-bedroom span, span.pr-bedroom span, span.re__card-config-bedroom")
        out.append(Card(
            title=_first_text(item, ("h3.re__card-title", "span.re__card-title", "span.pr-title", "h3")),
            price_raw=_first_text(item, ("span.re__card-config-price", "span[class*='config-price']", "span.pr-price")),
            area_raw=_first_text(item, ("span.re__card-config-area", "span[class*='config-area']", "span.pr-area")),
            beds_raw=clean_text(bed_el) if bed_el else "",
            description=_first_text(item, ("div.re__card-description", "div[class*='card-description']", "div.pr-description")),
            location=_first_text(item, ("div.re__card-location", "span.re__card-location", "span.pr-location")),
            link=_card_link(item, base),
            date_raw=_card_date(item),
            product_id=str(item.get("data-product-id") or ""),
        ))
    return out


_SHORT_INFO = {"khoang gia": "price_raw", "muc gia": "price_raw", "gia": "price_raw",
               "dien tich": "area_raw", "phong ngu": "beds_raw", "so phong ngu": "beds_raw"}
# "ngay het han" phải đứng trước "ngay dang" để so khớp nới lỏng không nhầm
_CONFIG = {"ngay het han": "expires", "ngay dang": "published", "loai tin": "listing_type", "ma tin": "listing_id"}


def _lookup(label: str, mapping: dict[str, str]) -> str | None:
    if label in mapping:
        return mapping[label]
    for key, fld in mapping.items():
        if key in label:
            return fld
    return None


def parse_detail(html: str, url: str = "") -> Detail:
    soup = BeautifulSoup(html, "html.parser")
    d = Detail(url=url)

    for si in soup.select(".re__pr-short-info-item.js__pr-short-info-item"):
        label, value = label_key(si.find("span", class_="title")), clean_text(si.find("span", class_="value"))
        fld = _lookup(label, _SHORT_INFO) if label and value else None
        if fld:
            setattr(d, fld, value)
            if fld == "price_raw":
                d.unit_price_raw = clean_text(si.find("span", class_="ext"))

    cfg = soup.select_one(".re__pr-short-info.re__pr-config.js__pr-config") or soup.select_one(".js__pr-config")
    if cfg is not None:
        items = cfg.select(".js__pr-config-item") or cfg.select(".re__pr-short-info-item")
    else:
        items = [it for it in soup.select(".re__pr-short-info-item")
                 if "js__pr-short-info-item" not in (it.get("class") or [])]
    for it in items:
        label, value = label_key(it.find("span", class_="title")), clean_text(it.find("span", class_="value"))
        fld = _lookup(label, _CONFIG) if label and value else None
        if fld in ("published", "expires"):
            setattr(d, fld, parse_date(value))
        elif fld:
            setattr(d, fld, value)

    d.title = clean_text(soup.select_one("h1.re__pr-title") or soup.select_one(".re__pr-title") or soup.select_one("h1"))
    d.description = clean_text(soup.select_one(".js__pr-description") or soup.select_one(".re__detail-content")
                               or soup.select_one(".re__section-body"))
    for it in soup.select(".re__pr-specs-content-item"):
        k = label_key(it.select_one(".re__pr-specs-content-item-title"))
        v = clean_text(it.select_one(".re__pr-specs-content-item-value"))
        if k and v:
            d.specs[k] = v
    if not d.price_raw:
        d.price_raw = d.specs.get("muc gia", "")
    if not d.area_raw:
        d.area_raw = d.specs.get("dien tich", "")

    addr = soup.find("meta", attrs={"property": "og:street-address"})
    d.address = clean_text(addr.get("content")) if addr and addr.get("content") else clean_text(
        soup.select_one(".re__pr-short-description, .js__pr-address"))

    # Dự phòng: bắt trực tiếp trên HTML thô
    if d.published is None:
        m = re.search(r"Ngày\s*đăng[^<\d]*(\d{2}/\d{2}/\d{4})", html, re.IGNORECASE)
        if m:
            d.published = parse_date(m.group(1))
    if not d.listing_id:
        m = re.search(r"-pr(\d+)(?:[/?#]|$)", url)
        if m:
            d.listing_id = m.group(1)
    return d


def is_listing_url(href: str) -> bool:
    """URL tin đăng chi tiết luôn kết thúc bằng ``-pr<mã tin>``; URL ``/du-an-`` là trang dự án."""
    return bool(re.search(r"-pr\d+", href)) and "/du-an-" not in href
