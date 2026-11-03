"""Các backend tải trang HTML: curl_cffi (+ Cloudflare), Firecrawl, và đọc file offline."""

from __future__ import annotations

import logging
import os
import random
import shutil
import tempfile
import time
from pathlib import Path
from typing import Protocol

from bdscrawler import cloudflare

log = logging.getLogger(__name__)


def ca_bundle_path() -> str | None:
    """Đường dẫn file chứng chỉ CA mà libcurl đọc được.

    libcurl (curl_cffi) trên Windows KHÔNG mở được file CA nếu đường dẫn có ký tự non-ASCII
    -> lỗi ``curl: (77) error setting certificate verify locations``. File ``cacert.pem`` của certifi
    nằm trong ``.venv`` của repo, nên chỉ cần repo được clone vào thư mục có dấu (``Tài liệu``,
    ``Khu vực phía Nam``...) là dính. Cách xử lý: copy sang thư mục có đường dẫn toàn ASCII.
    Có thể chỉ định file riêng bằng biến môi trường ``BDS_CA_BUNDLE``.
    """
    custom = os.environ.get("BDS_CA_BUNDLE")
    if custom:
        return custom
    try:
        import certifi
    except ImportError:
        return None
    src = Path(certifi.where())
    if str(src).isascii():
        return str(src)

    candidates = [Path(tempfile.gettempdir()), Path(os.environ.get("PUBLIC", r"C:\Users\Public")),
                  Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")), Path.home()]
    for base in candidates:
        dst = base / "bdscrawler" / "cacert.pem"
        if not str(dst).isascii():
            continue  # vd tên user Windows có dấu -> %TEMP% cũng có dấu
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copyfile(src, dst)
            log.info("Đường dẫn chứng chỉ có ký tự tiếng Việt -> dùng bản sao %s", dst)
            return str(dst)
        except OSError:
            continue
    log.error("Không tìm được thư mục ASCII để đặt cacert.pem — có thể gặp lỗi curl (77). "
              "Hãy clone repo vào thư mục không dấu (vd C:\\tools\\vn-realestate-crawler) "
              "hoặc đặt biến BDS_CA_BUNDLE trỏ tới một file cacert.pem có đường dẫn không dấu.")
    return None


class Fetcher(Protocol):
    def fetch(self, url: str, referer: str | None = None, retries: int = 4) -> str | None: ...


class CurlFetcher:
    """Tải trang bằng curl_cffi giả lập TLS Chrome, tự xử lý Cloudflare challenge.

    Chỉ gửi thêm ``Referer`` cho mỗi request: các header "tự chế" (``Connection: keep-alive``,
    ``Cache-Control``, ``DNT``...) hay User-Agent hardcode khiến Cloudflare chấm điểm bot thấp
    và trả challenge dù cookie còn hợp lệ (đo thực tế: ~50% request bị chặn so với 0%).
    """

    def __init__(self, site_url: str, delay: float = 1.0, timeout: int = 30, min_html: int = 1500):
        from curl_cffi import requests

        self.site_url = site_url.rstrip("/")
        self.delay = delay
        self.timeout = timeout
        self.min_html = min_html
        self.session = requests.Session(impersonate=os.environ.get("BDS_IMPERSONATE", "chrome"))
        self.session.headers.update(cloudflare.DEFAULT_HEADERS)
        ca = ca_bundle_path()
        if ca:
            self.session.verify = ca
        self.cf = cloudflare.CloudflareSession(self.session, self.site_url)
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self.delay + random.uniform(0, self.delay * 0.5) - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()

    def _get(self, url: str, referer: str):
        self._throttle()
        return self.session.get(url, headers={"Referer": referer}, timeout=self.timeout, allow_redirects=True)

    def _wait_cookie_active(self, url: str, referer: str, max_wait: int = 60) -> None:
        """Cookie vừa cấp chưa đồng bộ ngay trên mọi edge của Cloudflare -> gõ lại URL đích tới khi qua."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                if not cloudflare.is_challenge(self._get(url, referer)):
                    return
            except Exception as exc:
                log.warning("Lỗi mạng khi chờ cookie Cloudflare có hiệu lực: %s", exc)
            time.sleep(8 + random.uniform(0, 1))
        log.warning("Cookie Cloudflare chưa có hiệu lực sau %ss: %s", max_wait, url)

    def fetch(self, url: str, referer: str | None = None, retries: int = 4) -> str | None:
        referer = referer or self.site_url + "/"
        cf_hits = 0
        for attempt in range(retries):
            if attempt:
                time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
            try:
                log.info("GET %s%s", url, f" (lần {attempt + 1})" if attempt else "")
                resp = self._get(url, referer)
            except Exception as exc:
                log.warning("Lỗi kết nối (%s/%s): %s", attempt + 1, retries, exc)
                continue

            if cloudflare.is_challenge(resp):
                cf_hits += 1
                if cf_hits == 1 and self.cf.has_cookie():
                    # Còn cookie mà vẫn bị challenge: thường do tần suất -> nghỉ dài trước khi mở trình duyệt
                    wait = random.uniform(10, 18)
                    log.warning("Cloudflare challenge dù đã có cookie — nghỉ %.0fs: %s", wait, url)
                    time.sleep(wait)
                    continue
                log.warning("Cloudflare challenge (HTTP %s) — lấy lại cookie cf_clearance: %s", resp.status_code, url)
                if self.cf.refresh(url):
                    self._wait_cookie_active(url, referer)
                else:
                    time.sleep(random.uniform(5, 9))
                continue
            if resp.status_code == 200:
                if len(resp.text) < self.min_html:
                    log.warning("HTML quá ngắn (%s bytes) — có thể là trang chặn: %s", len(resp.text), url)
                    return None
                return resp.text
            if resp.status_code == 404:
                return None
            if resp.status_code in (403, 429, 503):
                log.warning("HTTP %s — nghỉ rồi thử lại: %s", resp.status_code, url)
                time.sleep(random.uniform(5, 9) * (attempt + 1))
            else:
                log.warning("HTTP %s: %s", resp.status_code, url)
        return None


class FirecrawlFetcher:
    """Tải trang qua dịch vụ Firecrawl (trả phí) — hữu ích khi không mở được trình duyệt."""

    def __init__(self, api_key: str | None = None, max_age_ms: int = 3_600_000):
        try:
            from firecrawl import Firecrawl
        except ImportError as exc:
            raise RuntimeError("Cần cài: pip install 'vn-realestate-crawler[firecrawl]'") from exc
        key = api_key or os.environ.get("FIRECRAWL_API_KEY")
        if not key:
            raise RuntimeError("Thiếu FIRECRAWL_API_KEY (đặt biến môi trường, KHÔNG hardcode vào code).")
        self.client = Firecrawl(api_key=key)
        self.max_age_ms = max_age_ms

    def fetch(self, url: str, referer: str | None = None, retries: int = 3) -> str | None:
        for attempt in range(retries):
            try:
                doc = self.client.scrape(url, formats=["rawHtml"], max_age=self.max_age_ms)
                html = getattr(doc, "raw_html", None) or getattr(doc, "html", None)
                if html is None and isinstance(doc, dict):
                    html = doc.get("rawHtml") or doc.get("html")
                if html:
                    return html
            except Exception as exc:
                log.warning("Firecrawl lỗi (%s/%s) %s: %s", attempt + 1, retries, url, exc)
            time.sleep(2 * (attempt + 1))
        return None


class FileFetcher:
    """Đọc HTML đã lưu sẵn: ``mapping`` url -> đường dẫn file. Dùng cho test / debug selector."""

    def __init__(self, mapping: dict[str, str | Path]):
        self.mapping = {k: Path(v) for k, v in mapping.items()}

    def fetch(self, url: str, referer: str | None = None, retries: int = 1) -> str | None:
        path = self.mapping.get(url)
        return path.read_text(encoding="utf-8") if path and path.exists() else None


def make_fetcher(backend: str, site_url: str, delay: float = 1.0) -> Fetcher:
    if backend == "curl":
        return CurlFetcher(site_url, delay=delay)
    if backend == "firecrawl":
        return FirecrawlFetcher()
    raise ValueError(f"Backend không hỗ trợ: {backend!r} (curl | firecrawl)")
