from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date, datetime
from urllib.parse import urlparse

from bdscrawler.config import Job, Project
from bdscrawler.http import Fetcher
from bdscrawler.sites import adapter_for
from bdscrawler.sites import batdongsan as bds
from bdscrawler.text import contains_any, fold, strip_accents

log = logging.getLogger(__name__)


class Pipeline:
    """Khung chung: duyệt các trang danh mục của từng dự án, gom record, khử trùng lặp."""

    columns: list[str] = []
    sort_by: list[str] = []
    summary_by: list[str] = []
    dedup_keys: tuple[str, ...] = ("Tiêu đề",)

    def __init__(self, job: Job, fetcher: Fetcher, start: date | None = None, end: date | None = None,
                 max_pages: int | None = None):
        self.job = job
        self.site = adapter_for(job.site)   # module adapter: batdongsan | guland
        self.fetcher = fetcher
        self.start = start or job.start_date or date(date.today().year, date.today().month, 1)
        self.end = end or job.end_date or date.today()
        if self.start > self.end:
            raise ValueError("Ngày bắt đầu phải <= ngày kết thúc")
        self.max_pages = max(1, max_pages or job.max_pages)
        self.scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── tiện ích ──────────────────────────────────────────────────────────────
    def in_range(self, d: date | None) -> bool:
        return d is not None and self.start <= d <= self.end

    def all_older_than_start(self, cards: list[bds.Card]) -> bool:
        """Trang mà mọi card có ngày đều cũ hơn ngày bắt đầu -> các trang sau cũng cũ, dừng được.

        Không dừng khi trang chỉ có tin MỚI hơn ngày kết thúc (khoảng ngày nằm trong quá khứ)
        hoặc không đọc được ngày nào.
        """
        dated = [c.published for c in cards if c.published]
        return bool(dated) and all(d < self.start for d in dated)

    def base_urls(self, project: Project) -> list[str]:
        urls = list(project.urls)
        if self.job.include_expired:
            urls += [u + ("&" if "?" in u else "?") + "expired=true" for u in project.urls if "expired=" not in u]
        return urls

    def project_matches(self, text: str, project: Project) -> bool:
        """Lọc card quảng cáo/"tin liên quan" lạc từ dự án khác (từ khoá OR, không phân biệt dấu)."""
        keys = project.keywords or project.aliases
        return not keys or contains_any(text, keys)

    def location_ok(self, text: str, project: Project, link: str) -> bool:
        if not self.job.location_any:
            return True
        folded = strip_accents(text).lower()
        if any(p.search(folded) for p in self.job.location_any):
            return True
        return any(urlparse(u).path in link for u in project.urls)

    def iter_pages(self, base_url: str) -> Iterator[tuple[int, list[bds.Card]]]:
        """Trả từng trang (số trang, cards). Dừng khi hết card hoặc site redirect về trang cũ."""
        seen_links: set[str] = set()
        for page in range(1, self.max_pages + 1):
            url = self.site.page_url(base_url, page)
            html = self.fetcher.fetch(url)
            if not html:
                log.error("Không tải được %s", url)
                if page == 1:
                    return
                continue
            cards = self.site.parse_cards(html, self.job.site)
            if not cards:
                log.info("Hết card ở trang %s — dừng.", page)
                return
            links = {c.link for c in cards if c.link}
            if page > 1 and links and links <= seen_links:
                log.info("Trang %s trùng trang trước (site redirect) — dừng.", page)
                return
            seen_links |= links
            yield page, cards

    # ── luồng chính ───────────────────────────────────────────────────────────
    def run(self) -> list[dict]:
        rows: list[dict] = []
        for project in self.job.projects:
            log.info("=== %s: %s ===", self.job.name, project.name)
            before = len(rows)
            for base_url in self.base_urls(project):
                for page, cards in self.iter_pages(base_url):
                    page_rows = self.process_page(cards, project, base_url)
                    log.info("[%s] trang %s: %s/%s tin hợp lệ", project.name, page, len(page_rows), len(cards))
                    rows.extend(page_rows)
                    if not page_rows and self.job.stop_on_empty_page and self.all_older_than_start(cards):
                        log.info("Trang %s chỉ còn tin cũ hơn %s — dừng URL này.", page, self.start)
                        break
            log.info("Xong %s: %s tin", project.name, len(rows) - before)
        return self.dedup(rows)

    def process_page(self, cards: list[bds.Card], project: Project, base_url: str) -> list[dict]:
        raise NotImplementedError

    def dedup(self, rows: list[dict]) -> list[dict]:
        seen_links, seen_keys, out = set(), set(), []
        for r in rows:
            link = r.get("Link") or ""
            key = tuple(fold(str(r.get(k, ""))) for k in self.dedup_keys)
            if (link and link in seen_links) or (any(key) and key in seen_keys):
                continue
            seen_links.add(link)
            seen_keys.add(key)
            out.append(r)
        log.info("Tổng: %s tin sau khử trùng lặp (trước: %s)", len(out), len(rows))
        return out

    def extra_sheets(self, rows: list[dict]) -> dict:
        return {}
