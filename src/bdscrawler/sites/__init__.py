"""Adapter cho từng website. Mỗi adapter cung cấp ``page_url``, ``parse_cards``,
``parse_detail``, ``is_listing_url`` và dùng chung dataclass ``Card`` / ``Detail``."""

from __future__ import annotations

from types import ModuleType
from urllib.parse import urlparse

from bdscrawler.sites import batdongsan, guland

ADAPTERS: dict[str, ModuleType] = {
    "batdongsan.com.vn": batdongsan,
    "guland.vn": guland,
}


def adapter_for(site: str) -> ModuleType:
    host = (urlparse(site).hostname or site).removeprefix("www.")
    try:
        return ADAPTERS[host]
    except KeyError:
        raise ValueError(f"Chưa hỗ trợ website {host!r} (có: {', '.join(ADAPTERS)})") from None
