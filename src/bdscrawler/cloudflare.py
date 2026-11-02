"""Vượt Cloudflare Managed Challenge theo mô hình "trình duyệt mở đường, curl_cffi chạy việc".

batdongsan.com.vn trả ``403`` + header ``cf-mitigated: challenge`` cho mọi request HTTP thuần,
kể cả khi đã giả lập TLS. Challenge phải được giải bằng JS trong trình duyệt thật mới được cấp
cookie ``cf_clearance``. Module này:

1. Mở Chromium thật (DrissionPage, KHÔNG headless) đúng một lần để lấy ``cf_clearance``.
2. Cấy cookie + User-Agent tương ứng vào session curl_cffi -> các request sau chạy nhanh.
3. Cache cookie ra đĩa, dùng chung giữa nhiều tiến trình, có khoá liên tiến trình để khi
   chạy song song nhiều job thì trình duyệt cũng chỉ mở 1 lần.

Phương án thủ công (không cài được DrissionPage): mở site bằng Chrome, copy cookie
``cf_clearance`` + User-Agent (F12 -> Application -> Cookies) vào file cache::

    {"saved_at": <unix ts>, "user_agent": "Mozilla/5.0 ...", "cookies": {"cf_clearance": "..."}}

Lưu ý: cookie bị ràng buộc với User-Agent VÀ địa chỉ IP — đổi mạng/VPN là phải lấy lại.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

COOKIE_TTL = 20 * 60      # cf_clearance sống ~30 phút, làm mới sớm cho chắc
SOLVE_TIMEOUT = 90        # thời gian tối đa chờ trình duyệt giải challenge
LOCK_WAIT = 150           # thời gian tối đa chờ tiến trình khác giải xong
LOCK_STALE = 240          # khoá cũ hơn mốc này coi như tiến trình đã chết
BROWSER_PORT = 9333       # cổng điều khiển riêng, không đụng trình duyệt cá nhân đang mở

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}

_BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
_BROWSER_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]


def cache_dir() -> Path:
    d = Path(os.environ.get("BDS_CACHE_DIR") or Path.home() / ".cache" / "bdscrawler")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cookie_file(domain: str) -> Path:
    return cache_dir() / f"cf_cookies_{domain}.json"


def _lock_file(domain: str) -> Path:
    return Path(tempfile.gettempdir()) / f"bdscrawler_cf_{domain}.lock"


def domain_of(url: str) -> str:
    host = urlparse(url).hostname or url
    return host[4:] if host.startswith("www.") else host


# ──────────────────────────────────────────────────────────────────────────────
# Cache cookie
# ──────────────────────────────────────────────────────────────────────────────
def load_cached(domain: str, max_age: int = COOKIE_TTL) -> tuple[dict, str, float] | None:
    path = _cookie_file(domain)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        saved_at = float(data.get("saved_at", 0))
        if time.time() - saved_at > max_age or "cf_clearance" not in (data.get("cookies") or {}):
            return None
        return data["cookies"], data.get("user_agent", ""), saved_at
    except Exception as exc:  # file hỏng / đang ghi dở
        log.warning("Không đọc được cache cookie Cloudflare %s: %s", path, exc)
        return None


def save_cached(domain: str, cookies: dict, user_agent: str) -> float:
    """Ghi file tạm rồi ``os.replace`` để tiến trình khác không đọc phải file ghi dở."""
    saved_at = time.time()
    path = _cookie_file(domain)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps({"saved_at": saved_at, "user_agent": user_agent, "cookies": cookies},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("Không ghi được cache cookie Cloudflare: %s", exc)
        tmp.unlink(missing_ok=True)
    return saved_at


def is_challenge(response) -> bool:
    """Phân biệt challenge Cloudflare với lỗi 403 thông thường."""
    if response is None:
        return False
    try:
        if (response.headers.get("cf-mitigated") or "").lower() == "challenge":
            return True
        if response.status_code in (403, 429, 503):
            head = (response.text or "")[:3000].lower()
            return any(k in head for k in ("just a moment", "challenges.cloudflare.com",
                                           "cf-browser-verification", "cf_chl_opt"))
    except Exception:
        return False
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Khoá liên tiến trình
# ──────────────────────────────────────────────────────────────────────────────
def _acquire_lock(domain: str) -> None:
    lock = _lock_file(domain)
    deadline = time.time() + LOCK_WAIT
    announced = False
    while time.time() < deadline:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE:
                    log.warning("Khoá Cloudflare treo quá lâu — thu hồi.")
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if not announced:
                log.info("Tiến trình khác đang giải Cloudflare challenge — chờ dùng chung cookie.")
                announced = True
            time.sleep(3)
        except OSError as exc:
            log.warning("Không tạo được khoá Cloudflare (%s) — vẫn tiếp tục.", exc)
            return
    log.warning("Chờ khoá Cloudflare quá lâu — tự giải challenge.")


def _release_lock(domain: str) -> None:
    _lock_file(domain).unlink(missing_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# Giải challenge bằng trình duyệt thật
# ──────────────────────────────────────────────────────────────────────────────
def find_browser() -> str | None:
    env_path = os.environ.get("BDS_BROWSER_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    for candidate in _BROWSER_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    for name in _BROWSER_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def solve(url: str) -> tuple[dict, str, float] | None:
    """Mở trình duyệt thật, chờ Cloudflare cấp ``cf_clearance``. Trả ``(cookies, ua, saved_at)``."""
    try:
        from DrissionPage import ChromiumOptions, ChromiumPage
    except ImportError:
        log.error("Thiếu DrissionPage để vượt Cloudflare: pip install 'vn-realestate-crawler[browser]' "
                  "(hoặc tạo cache cookie thủ công — xem docs/CLOUDFLARE.md).")
        return None
    browser = find_browser()
    if not browser:
        log.error("Không tìm thấy trình duyệt Chromium. Đặt biến BDS_BROWSER_PATH trỏ tới chrome/msedge.")
        return None

    domain = domain_of(url)
    log.info("Mở trình duyệt để giải Cloudflare challenge (%s): %s", domain, browser)
    page = None
    try:
        opts = ChromiumOptions()
        opts.set_browser_path(browser)
        opts.set_user_data_path(str(Path(tempfile.gettempdir()) / "bdscrawler_cf_profile"))
        opts.set_local_port(BROWSER_PORT)
        for arg in ("--no-first-run", "--no-default-browser-check", "--disable-blink-features=AutomationControlled"):
            opts.set_argument(arg)
        # KHÔNG bật headless — Cloudflare chặn trình duyệt headless.
        page = ChromiumPage(opts)
        page.get(url)

        deadline = time.time() + SOLVE_TIMEOUT
        while time.time() < deadline:
            title = (page.title or "").lower()
            if "just a moment" not in title and "attention required" not in title and len(page.html or "") > 50000:
                break
            try:  # một số challenge cần tick ô Turnstile
                box = page.ele("xpath://input[@type='checkbox']", timeout=1)
                if box:
                    box.click()
            except Exception:
                pass
            time.sleep(2)

        cookies = {c["name"]: c["value"] for c in page.cookies()}
        try:
            ua = page.run_js("return navigator.userAgent")
        except Exception:
            ua = ""
        if "cf_clearance" not in cookies:
            log.error("Trình duyệt chưa nhận được cookie cf_clearance (challenge chưa qua).")
            return None
        log.info("Đã vượt Cloudflare challenge.")
        return cookies, ua, save_cached(domain, cookies, ua)
    except Exception as exc:
        log.error("Lỗi khi giải Cloudflare challenge bằng trình duyệt: %s", exc)
        return None
    finally:
        if page is not None:
            try:
                page.quit()
            except Exception:
                pass


class CloudflareSession:
    """Quản lý cookie ``cf_clearance`` cho một session curl_cffi."""

    def __init__(self, session, site_url: str):
        self.session = session
        self.domain = domain_of(site_url)
        self.site_url = site_url
        self._applied_at = 0.0
        self._last_refresh = 0.0
        self._refresh_count = 0
        cached = load_cached(self.domain)
        if cached:
            self._apply(*cached)
            log.info("Dùng lại cookie Cloudflare đã cache (tuổi %ds).", int(time.time() - cached[2]))

    def _apply(self, cookies: dict, user_agent: str, saved_at: float) -> None:
        try:
            self.session.cookies.clear()
        except Exception:
            pass
        for name, value in (cookies or {}).items():
            try:
                self.session.cookies.set(name, value, domain="." + self.domain)
            except Exception:
                pass
        if user_agent:
            # cf_clearance ràng buộc với UA đã sinh ra nó -> phải khớp tuyệt đối
            self.session.headers["User-Agent"] = user_agent
        self._applied_at = saved_at

    def has_cookie(self) -> bool:
        try:
            return any(c.name == "cf_clearance" for c in self.session.cookies.jar)
        except Exception:
            return False

    def refresh(self, url: str | None = None) -> bool:
        """Lấy cookie mới (ưu tiên cache do tiến trình khác vừa giải). Có hãm tần suất."""
        if time.time() - self._last_refresh < 30:
            return False
        if self._refresh_count >= 5:
            log.error("Đã làm mới cookie Cloudflare quá 5 lần — dừng thử lại.")
            return False
        self._last_refresh = time.time()
        self._refresh_count += 1

        cached = load_cached(self.domain)
        if cached and cached[2] > self._applied_at:
            self._apply(*cached)
            return True
        _acquire_lock(self.domain)
        try:
            cached = load_cached(self.domain)
            if cached and cached[2] > self._applied_at:
                log.info("Tiến trình khác đã giải xong Cloudflare — dùng chung cookie.")
                self._apply(*cached)
                return True
            result = solve(url or self.site_url)
            if not result:
                return False
            self._apply(*result)
            return True
        finally:
            _release_lock(self.domain)
