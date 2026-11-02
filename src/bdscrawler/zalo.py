"""Parse tin nhắn đăng bán nhà trong nhóm Zalo -> bảng dữ liệu.

Nguồn vào (nhận dạng theo đuôi file):
  * ``.json`` — file xuất bởi ``tools/zalo_dump.js`` chạy trong Console của chat.zalo.me (khuyến nghị)
  * ``.txt`` / ``.html`` — DOM dump thô của khung chat
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from bdscrawler.text import strip_accents

_WS = re.compile(r"[^\S\n]+")


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", strip_accents(s).lower())


# Nhãn xuất hiện trong tin -> cột chuẩn (key bên trái đã qua _key()).
LABEL_MAP = {
    "stt": "STT",
    "toagia": "Toà/Giá", "toa": "Toà",
    "gia": "Giá", "giaban": "Giá", "giachao": "Giá", "giachaoban": "Giá",
    "tang": "Tầng",
    "noithat": "Nội thất", "nt": "Nội thất",
    "phaply": "Pháp lý", "pl": "Pháp lý",
    "trangthai": "Trạng thái", "tt": "Trạng thái",
    "loaican": "Loại căn", "can": "Loại căn", "loaihinh": "Loại căn",
    "dientich": "Diện tích", "dt": "Diện tích",
    "huong": "Hướng", "huongban": "Hướng", "huongcanho": "Hướng",
    "view": "View",
    "macan": "Mã căn", "ma": "Mã căn",
    "lh": "Liên hệ", "lienhe": "Liên hệ", "hotline": "Liên hệ", "sdt": "Liên hệ",
    "ghichu": "Ghi chú", "note": "Ghi chú",
    "duan": "Dự án", "phankhu": "Phân khu",
}
CANONICAL_COLS = ["STT", "Dự án", "Phân khu", "Toà", "Toà/Giá", "Mã căn", "Giá", "Diện tích", "Tầng",
                  "Loại căn", "Hướng", "View", "Nội thất", "Pháp lý", "Trạng thái", "Liên hệ", "Ghi chú"]

# Ký tự trang trí đầu dòng: emoji, bullet, gạch đầu dòng...
_BULLET = re.compile("^[\\s\\-*+>•·▪▫◆◇○●□■»\U0001F000-\U0001FAFF←-⯿☀-➿️‍]+")
# "Nhãn: giá trị" — nhãn ngắn (<= 28 ký tự) để không nuốt nhầm câu văn dài
_FIELD = re.compile(r"^([A-Za-z0-9/.\sÀ-ỹ]{1,28}?)\s*[:：]\s*(.*)$")
_MSG_ID = re.compile(r"^bb_msg_id_(\d{10,})")
# Dòng trần ghi loại căn: '1N+/43M/TN', '3N/82,7m/ĐN-TN GÓC', 'studio/30m/B'
_UNIT_SPEC = re.compile(r"^(?:studio|\d+\s*(?:N|PN|ngủ)\s*\+?)\s*/", re.IGNORECASE)


def parse_message_text(text: str) -> tuple[dict, dict]:
    """Bóc các cặp ``Nhãn: giá trị`` trong 1 tin nhắn -> (trường chuẩn, trường khác)."""
    fields: dict[str, str] = {}
    extras: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = _WS.sub(" ", _BULLET.sub("", raw_line)).strip()
        if not line:
            continue
        m = _FIELD.match(line)
        if not m:
            if _UNIT_SPEC.match(line):
                fields.setdefault("Loại căn", line)
            continue
        label, value = m.group(1).strip(), m.group(2).strip().rstrip(",;.")
        if not label:
            continue
        col = LABEL_MAP.get(_key(label))
        if col:
            if col in fields and value:
                fields[col] = f"{fields[col]} | {value}"
            elif value:
                fields[col] = value
            else:
                fields.setdefault(col, "")
        elif value:
            extras[label] = value

    # 'Toa/ gia: V3 - 6100tv (...)' -> Toà=V3, Giá=6100tv (...)
    tg = fields.get("Toà/Giá")
    if tg:
        m = re.match(r"^\s*([^\-–—/]{1,20}?)\s*[\-–—]\s*(.+)$", tg)
        if m:
            fields.setdefault("Toà", m.group(1).strip())
            fields.setdefault("Giá", m.group(2).strip())
        else:
            fields.setdefault("Giá", tg)

    # '3N/82,7m/DN-TN GOC' -> Số PN=3, Diện tích=82.7
    lc = fields.get("Loại căn") or ""
    m = re.search(r"(\d+)\s*(?:N|PN|ngủ)\b", lc, re.IGNORECASE)
    if m:
        fields["Số PN"] = int(m.group(1))
    elif re.search(r"studio", lc, re.IGNORECASE):
        fields["Số PN"] = 0
    if not fields.get("Diện tích"):
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*m", lc, re.IGNORECASE)
        if m:
            fields["Diện tích"] = m.group(1).replace(",", ".")
    return fields, extras


def load_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    msgs = data.get("messages", data) if isinstance(data, dict) else data
    return [{
        "msg_id": str(m.get("msg_id", "")),
        "dt": datetime.fromtimestamp(m["ts_ms"] / 1000) if m.get("ts_ms") else None,
        "sender": m.get("sender", ""),
        "text": m.get("text", ""),
        "has_image": bool(m.get("has_image")),
    } for m in msgs]


def load_html(path: Path) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    out, last_sender = [], ""
    for node in soup.select('[id^="bb_msg_id_"]'):
        m_id = _MSG_ID.match(node.get("id", ""))
        if not m_id:
            continue
        item = node.find_parent(class_="chat-item") or node
        name_el = item.select_one(".message-sender-name-content .truncate")
        sender = html.unescape(name_el.get_text(" ", strip=True)).replace("\xa0", " ").strip() if name_el else ""
        last_sender = sender or last_sender
        text_el = node.select_one('[data-component="message-text-content"]')
        text = ""
        if text_el:
            parts = [s.get_text() for s in text_el.select("span.text")]  # bỏ span emoji trang trí
            text = ("".join(parts) if parts else text_el.get_text("\n")).replace("\xa0", " ").strip()
        has_image = bool(node.select_one('[data-id*="Msg_Photo"], [data-id*="Msg_GrpPhoto"], '
                                         '.photo-message-v2, .img-msg-v2, .group-photo-message'))
        if not text and not has_image:
            continue
        out.append({"msg_id": m_id.group(1), "dt": datetime.fromtimestamp(int(m_id.group(1)) / 1000),
                    "sender": sender or last_sender, "text": text, "has_image": has_image})
    return out


def to_frame(messages: list[dict], start: datetime, end: datetime, keep_all: bool = False) -> pd.DataFrame:
    rows = []
    for m in messages:
        if not m["dt"] or not start <= m["dt"] <= end:
            continue
        fields, extras = parse_message_text(m["text"])
        # Coi là "tin đăng bán" khi có STT hoặc nhận dạng được >= 2 trường
        if not keep_all and "STT" not in fields and len(fields) < 2:
            continue
        row = {"Ngày": m["dt"].strftime("%d/%m/%Y"), "Giờ": m["dt"].strftime("%H:%M"), "Người đăng": m["sender"]}
        row.update({c: fields.get(c, "") for c in CANONICAL_COLS})
        row["Số PN"] = fields.get("Số PN", "")
        row["Có ảnh"] = "x" if m["has_image"] else ""
        row["Trường khác"] = "; ".join(f"{k}: {v}" for k, v in extras.items())
        row["Nội dung gốc"] = m["text"]
        row["msg_id"] = m["msg_id"]
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset="msg_id")
    empty = [c for c in CANONICAL_COLS + ["Số PN"] if c in df and not df[c].astype(str).str.strip().any()]
    return df.drop(columns=empty)


def load(path: str | Path) -> list[dict]:
    path = Path(path)
    return load_json(path) if path.suffix.lower() == ".json" else load_html(path)
