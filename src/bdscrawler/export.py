"""Xuất kết quả ra Excel (đã định dạng) và CSV."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

log = logging.getLogger(__name__)

HEADER_FILL = PatternFill("solid", fgColor="1A3A4A")
SUMMARY_FILL = PatternFill("solid", fgColor="2E75B6")
_ZEBRA = ["E8F4FD", "EBF5EB", "FEF9E7", "F5EEF8", "FDEBD0", "D5F5E3", "F2F3F4"]


def _number_format(col: str) -> str | None:
    c = col.lower()
    if "tỷ" in c or "ticket" in c:
        return "#,##0.00"
    if "diện tích" in c or "m²" in c or "m2" in c or "triệu" in c or "dt tb" in c or "mặt tiền" in c:
        return "#,##0.0"
    if c in ("số ngủ", "số tầng", "số lượng"):
        return "0"
    return None


def _style(ws: Worksheet, df: pd.DataFrame, fill: PatternFill = HEADER_FILL, zone_col: str | None = None,
           zone_colors: dict[str, str] | None = None) -> None:
    for cell in ws[1]:
        cell.fill = fill
        cell.font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30
    formats = {i + 1: _number_format(str(c)) for i, c in enumerate(df.columns)}

    colors = dict(zone_colors or {})
    if zone_col in df.columns:
        for i, z in enumerate(df[zone_col].dropna().unique()):
            colors.setdefault(str(z), _ZEBRA[i % len(_ZEBRA)])
    zone_idx = list(df.columns).index(zone_col) if zone_col in df.columns else None

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        bg = colors.get(str(row[zone_idx].value)) if zone_idx is not None and row[0].row % 2 == 0 else None
        for cell in row:
            cell.font = Font(name="Arial", size=10)
            fmt = formats.get(cell.column)
            if fmt:
                cell.number_format = fmt
                cell.alignment = Alignment(horizontal="right")
            if bg:
                cell.fill = PatternFill("solid", fgColor=bg)

    for col in ws.columns:
        width = max((len(str(c.value)) for c in list(col)[:300] if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 45)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def build_summary(df: pd.DataFrame, by: list[str]) -> pd.DataFrame | None:
    by = [c for c in by if c in df.columns]
    if not by or df.empty:
        return None
    aggs = {}
    for name, keys in (("DT TB (m²)", ("Diện tích",)), ("Giá TB (tỷ)", ("Giá", "Tổng giá", "Ticket")),
                       ("Đơn giá TB (tr/m²)", ("Đơn giá",)), ("Giá thuê TB (tr/tháng)", ("Giá thuê",))):
        col = next((c for c in df.columns if any(str(c).startswith(k) for k in keys)
                    and pd.api.types.is_numeric_dtype(df[c])), None)
        if col is not None:
            aggs[name] = (col, "mean")
    summary = (df.groupby(by, dropna=False).agg(**{"Số lượng": (df.columns[0], "size")}, **aggs)
               .reset_index().round(2))
    return summary


def to_frame(rows: list[dict], columns: list[str], sort_by: list[str], zone_order: list[str] | None = None,
             zone_col: str = "Phân khu") -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        return df
    for c in df.columns:
        # Chỉ ép kiểu số khi MỌI giá trị không rỗng đều là số (tránh cột text như "Lộ giới 12m")
        nonempty = df[c].replace("", pd.NA).dropna()
        if _number_format(str(c)) and pd.to_numeric(nonempty, errors="coerce").notna().all():
            df[c] = pd.to_numeric(df[c].replace("", pd.NA), errors="coerce")
    keys = [k for k in sort_by if k in df.columns]
    if "Ngày đăng" in keys:
        df["_date"] = pd.to_datetime(df["Ngày đăng"], format="%d/%m/%Y", errors="coerce")
        keys = ["_date" if k == "Ngày đăng" else k for k in keys]
    if zone_order and zone_col in df.columns:
        df["_order"] = df[zone_col].map(lambda z: zone_order.index(z) if z in zone_order else len(zone_order))
        keys = ["_order", *keys]
    if keys:
        df = df.sort_values(keys, ascending=[k != "_date" for k in keys], na_position="last", kind="stable")
    return df.drop(columns=[c for c in ("_date", "_order") if c in df.columns]).reset_index(drop=True)


def write_excel(df: pd.DataFrame, path: Path, summary_by: list[str] | None = None,
                extra: dict[str, pd.DataFrame] | None = None, zone_col: str = "Phân khu",
                zone_colors: dict[str, str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Data")
        _style(writer.sheets["Data"], df, zone_col=zone_col, zone_colors=zone_colors)
        summary = build_summary(df, summary_by or [])
        if summary is not None:
            summary.to_excel(writer, index=False, sheet_name="Summary")
            _style(writer.sheets["Summary"], summary, fill=SUMMARY_FILL)
        for name, frame in (extra or {}).items():
            frame.to_excel(writer, index=False, sheet_name=name[:31])
            _style(writer.sheets[name[:31]], frame)
    return path


def output_path(out_dir: str | Path, prefix: str, ext: str = "xlsx") -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(out_dir) / f"{prefix}_{stamp}.{ext}"
