"""Bóc tách đặc điểm từ văn bản tự do của tin đăng (hướng, view, nội thất, thông số thấp tầng...)."""

from __future__ import annotations

import re

from bdscrawler.numbers import first_number
from bdscrawler.text import fold

# ──────────────────────────────────────────────────────────────────────────────
# Hướng / view
# ──────────────────────────────────────────────────────────────────────────────
_DIRECTIONS = [
    ("Đông Nam", r"\bdong nam\b"),
    ("Tây Bắc", r"\btay bac\b"),
    ("Đông Bắc", r"\bdong bac\b"),
    ("Tây Nam", r"\btay nam\b"),
    ("Đông", r"\bhuong dong\b"),
    ("Tây", r"\bhuong tay\b"),
    ("Nam", r"\bhuong nam\b"),
    ("Bắc", r"\bhuong bac\b"),
]


def extract_direction(text: str) -> str:
    value = fold(text)
    for label, pattern in _DIRECTIONS:
        if re.search(pattern, value):
            return label
    return ""


def direction_from_specs(specs: dict[str, str]) -> str:
    """Hướng nhà / hướng ban công lấy trực tiếp từ bảng đặc điểm (chuẩn nhất)."""
    for key in ("huong nha", "huong ban cong"):
        if specs.get(key):
            return specs[key]
    return ""


_CORNER = ("can goc", "lo goc", "goc 2 mat thoang", "2 mat tien", "hai mat tien", "xe khe", "dau hoi")
_RIVER = ("view song", "mat song", "song sau", "ven song", "view kenh", "mat kenh")
_OPEN = ("view ho", "view bien ho", "view cong vien", "mat cong vien", "doi dien cong vien",
         "view vuon hoa", "mat vuon hoa", "view thoang", "view dep", "thoang vinh vien")
_NORMAL = ("view thuong", "view noi khu", "noi khu")


def extract_view(text: str) -> tuple[str, str]:
    """Trả về ``(phân loại view, các cụm từ khớp)`` — vd ``("Căn góc_View sông", "view song")``."""
    value = fold(text)
    for terms, label in ((_RIVER, "View sông"), (_OPEN, "View thoáng, đẹp"), (_NORMAL, "View thường")):
        matched = [t for t in terms if t in value]
        if matched:
            prefix = "Căn góc_" if any(t in value for t in _CORNER) else "Căn thường_"
            return prefix + label, ", ".join(dict.fromkeys(matched))
    return "Không phân loại", ""


# ──────────────────────────────────────────────────────────────────────────────
# Nội thất / đối tượng thuê (căn hộ cho thuê)
# ──────────────────────────────────────────────────────────────────────────────
_NO_FURNITURE = ("khong noi that", "khong do", "ko do", "khong co do", "khong co noi that", "nha trong")
_FULL_FURNITURE = ("full noi that", "day du noi that", "full nt", "full do", "du do", "noi that day du")
_FURNITURE_ITEMS = {
    "Điều hòa": ("dieu hoa", "may lanh"),
    "Nóng lạnh": ("nong lanh",),
    "Tủ lạnh": ("tu lanh",),
    "Máy giặt": ("may giat",),
    "Giường": ("giuong",),
    "Tủ quần áo": ("tu quan ao", "tu ao"),
    "Sofa/Bàn ghế": ("sofa", "ban ghe", "salong", "salon"),
    "Bàn ăn": ("ban an",),
    "Tivi": ("tivi", "television"),
    "Bếp/Tủ bếp": ("tu bep", "bep tu", "bep tu", "bep dien"),
    "Hút mùi": ("hut mui",),
    "Rèm cửa": ("rem cua",),
    "Lò vi sóng": ("lo vi song", "lo nuong"),
}


def infer_furniture(text: str) -> str:
    t = fold(text)
    if any(k in t for k in _NO_FURNITURE):
        return "Không đồ"
    if any(k in t for k in _FULL_FURNITURE) or "noi that" in t:
        return "Có đồ"
    return ""


def furniture_details(text: str) -> str:
    t = fold(text)
    if any(k in t for k in _NO_FURNITURE):
        return "Không đồ"
    items = [label for label, keys in _FURNITURE_ITEMS.items() if any(k in t for k in keys)]
    if items:
        return ", ".join(items)
    if any(k in t for k in _FULL_FURNITURE):
        return "Đầy đủ (không liệt kê chi tiết)"
    return ""


_AUDIENCES = {
    "Chuyên gia/Người nước ngoài": ("chuyen gia", "nuoc ngoai", "ky su", "expat"),
    "Gia đình": ("gia dinh",),
    "Sinh viên": ("sinh vien", "hoc sinh"),
    "Người đi làm": ("nguoi di lam",),
    "Kinh doanh/Văn phòng": ("kinh doanh", "van phong", "cong ty", "spa"),
}


def target_audience(text: str) -> str:
    t = fold(text)
    return ", ".join(label for label, keys in _AUDIENCES.items() if any(k in t for k in keys))


# ──────────────────────────────────────────────────────────────────────────────
# Thấp tầng: loại hình, mặt tiền, đường, số tầng, tình trạng, cho thuê
# ──────────────────────────────────────────────────────────────────────────────
def property_type(text: str, detailed: bool = False) -> str:
    """``Shophouse`` / ``Biệt thự`` / ``Liền kề``; ``detailed=True`` tách đơn lập / song lập."""
    t = fold(text)
    if any(k in t for k in ("shophouse", "shop house", "nha pho thuong mai", "nha pho kinh doanh", "boutique")):
        return "Shophouse"
    if detailed and "don lap" in t:
        return "Biệt thự đơn lập"
    if detailed and "song lap" in t:
        return "Biệt thự song lập"
    if any(k in t for k in ("biet thu", "song lap", "don lap", "tu lap", "villa", "dinh thu")):
        return "Biệt thự"
    if "lien ke" in t:
        return "Liền kề"
    return "N/A"


def construction_area(text: str) -> float | None:
    """Chỉ lấy diện tích xây dựng / tổng sàn khi tin nói rõ — không tự nhân số tầng."""
    t = (text or "").lower().replace("²", "2")
    for pattern in (
        r"tổng\s*(?:diện\s*tích\s*)?(?:sàn|xây\s*dựng)\s*[:\-]?\s*(\d{2,5}(?:[.,]\d{1,2})?)\s*m2",
        r"(?:diện\s*tích\s*xây\s*dựng|dtxd|dt\s*xd)\s*[:\-]?\s*(\d{2,5}(?:[.,]\d{1,2})?)\s*m2(?!\s*/\s*sàn)",
        r"diện\s*tích\s*sàn\s*[:\-]?\s*(\d{2,5}(?:[.,]\d{1,2})?)\s*m2",
    ):
        v = first_number(t, pattern)
        if v is not None:
            return round(v, 2)
    return None


def frontage(text: str) -> float | None:
    return first_number(text, r"(?:mặt\s*tiền|mat\s*tien|\bmt)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*m\b")


def road_width(text: str) -> str:
    t = (text or "").lower()
    m = re.search(
        r"(?:lộ\s*giới|lo\s*gioi|đường\s*rộng|duong\s*rong|mặt\s*đường\s*rộng|đường\s*vào)"
        r"\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*m", t)
    if m:
        return f"Lộ giới {m.group(1)}m"
    m = re.search(r"(?:đường|phố)\s+\w+\s+rộng\s+(\d+(?:[.,]\d+)?)\s*m", t)
    return f"Rộng {m.group(1)}m" if m else ""


def floors(text: str) -> int | None:
    m = re.search(r"(\d+)\s*tầng", text or "", re.IGNORECASE)
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 15 else None


def unit_status(text: str) -> str:
    t = fold(text)
    if any(k in t for k in ("dang kinh doanh", "dang cho thue", "co nguoi thue", "hop dong thue")):
        return "Đang kinh doanh/Cho thuê"
    if any(k in t for k in ("hoan thien", "full noi that")):
        return "Hoàn thiện"
    if any(k in t for k in ("xay tho", "ban giao tho", "nha tho")):
        return "Bàn giao thô"
    if "chua co nguoi thue" in t or "nha trong" in t:
        return "Trống"
    return ""


def rental_terms(text: str) -> tuple[float | None, str, float | None]:
    """``(giá thuê nguyên căn, các tầng cho thuê, giá thuê/tầng)`` — đơn vị triệu/tháng."""
    t = (text or "").lower()
    floors_found: list[str] = []
    per_floor = None
    for pat in (
        r"tầng\s*(\d)\s*[:\-]?\s*(?:giá)?\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)\b",
        r"cho\s*thuê\s*tầng\s*(\d)\s+(?:giá)?\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)\b",
    ):
        for m in re.finditer(pat, t):
            floors_found.append(m.group(1))
            per_floor = float(m.group(2).replace(",", "."))

    whole = None
    for pat in (
        r"cho\s*thuê\s*(?:nguyên\s*căn|cả\s*nhà|toàn\s*bộ)?\s*(?:giá)?\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)\b",
        r"giá\s*thuê\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)\b",
        r"(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)\s*/\s*tháng",
    ):
        m = re.search(pat, t)
        if m:
            val = float(m.group(1).replace(",", "."))
            if 5 <= val <= 500:
                whole = val
                break
    floors_str = ", ".join(f"Tầng {x}" for x in sorted(set(floors_found)))
    return (None if floors_found else whole), floors_str, per_floor


_BUSINESS = {
    "Nhà hàng / Ăn uống": ("nha hang", "an uong", "cafe", "ca phe"),
    "Spa / Làm đẹp": ("spa", "lam dep", "tham my", "massage", "nail"),
    "Bán lẻ / Showroom": ("ban le", "showroom", "cua hang"),
    "Văn phòng": ("van phong", "office"),
    "Siêu thị / Tạp hóa": ("sieu thi", "tap hoa"),
    "Giáo dục / Trung tâm": ("trung tam", "day hoc", "lop hoc"),
    "Y tế / Phòng khám": ("phong kham", "nha khoa", "y te"),
}


def business_purpose(text: str) -> str:
    t = fold(text)
    return ", ".join(label for label, keys in _BUSINESS.items() if any(k in t for k in keys))


_LOCATION_KEYS = ("căn góc", "lô góc", "mặt đường", "trục đường", "trục chính", "ven sông", "view sông",
                  "công viên", "đối diện", "tọa lạc", "nằm tại", "tiếp giáp", "mặt tiền", "hồ điều hòa", "cách")


def location_description(text: str, max_len: int = 500) -> str:
    """Ghép tối đa 4 câu có nhắc tới vị trí (góc, mặt đường, view...)."""
    parts = []
    for sentence in re.split(r"[.\n!?]", text or ""):
        s = sentence.strip()
        if s and any(k in s.lower() for k in _LOCATION_KEYS):
            parts.append(s)
        if len(parts) >= 4 or sum(map(len, parts)) > 300:
            break
    return ". ".join(parts)[:max_len]


_UNIT_BLOCKED = {"M2", "M3", "PN1", "PN2", "PN3", "PN4", "PN5", "VND", "SDT", "TP"}


def unit_code(text: str, prefixes: list[str] | tuple[str, ...] = ()) -> str:
    """Mã căn thấp tầng: ``SB12-34``, ``NT05.12``, ``MHT-25``... (``N/A`` nếu không thấy)."""
    value = (text or "").upper().replace("–", "-").replace("—", "-")
    patterns = [
        r"(?:MÃ\s*CĂN|MA\s*CAN|CĂN|CAN|DÃY|DAY|LÔ|LO)\s*(?:SỐ\s*)?[:#\-]?\s*([A-ZĐ]{1,5}\s*-?\s*\d{1,3}(?:[.\-/][A-Z0-9]{1,5}){0,4})\b",
        r"\b([A-ZĐ]{1,4}\d{1,3}(?:[.\-/][A-Z0-9]{1,5}){1,4})\b",
    ]
    if prefixes:
        alt = "|".join(sorted({re.escape(p.upper()) for p in prefixes}, key=len, reverse=True))
        patterns.append(rf"\b((?:{alt})\s*-?\s*\d{{1,3}}[A-Z]?)\b")
    for pattern in patterns:
        for m in re.finditer(pattern, value):
            code = re.sub(r"\s+", "", m.group(1)).strip(".-/")
            if code not in _UNIT_BLOCKED and len(code) >= 3:
                return code
    return "N/A"
