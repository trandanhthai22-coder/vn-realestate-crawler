"""Chạy pipeline end-to-end trên HTML mẫu (không cần mạng)."""

from datetime import date, timedelta
from pathlib import Path

import openpyxl

from bdscrawler.config import load_job
from bdscrawler.export import to_frame, write_excel
from bdscrawler.http import FileFetcher
from bdscrawler.pipelines import ApartmentPipeline, DetailPipeline, LowrisePipeline
from bdscrawler.sites import batdongsan as bds

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
SITE = "https://batdongsan.com.vn"


def test_page_url():
    assert bds.page_url(f"{SITE}/ban-can-ho", 1) == f"{SITE}/ban-can-ho"
    assert bds.page_url(f"{SITE}/ban-can-ho", 3) == f"{SITE}/ban-can-ho/p3"
    assert bds.page_url(f"{SITE}/ban-can-ho?expired=true", 2) == f"{SITE}/ban-can-ho/p2?expired=true"


def test_parse_cards_and_detail():
    cards = bds.parse_cards((FIX / "listing_apartment.html").read_text(encoding="utf-8"))
    assert len(cards) == 3
    assert cards[0].price_raw == "3,9 tỷ" and cards[0].beds_raw == "2"
    assert cards[0].link.endswith("-pr1001")

    d = bds.parse_detail((FIX / "detail_apartment.html").read_text(encoding="utf-8").replace("TODAY", "15/10/2026"),
                         cards[0].link)
    assert (d.price_raw, d.area_raw, d.beds_raw) == ("3,9 tỷ", "64 m²", "2 PN")
    assert d.unit_price_raw == "~60,94 triệu/m²"
    assert d.published == date(2026, 10, 15) and d.expires == date(2099, 12, 31)
    assert (d.listing_type, d.listing_id) == ("Tin thường", "1001")
    assert d.specs["huong ban cong"] == "Đông Nam"


def test_apartment_pipeline_end_to_end(tmp_path):
    job = load_job(ROOT / "configs" / "apartment" / "vhsc_sapphire.toml")
    listing_url = job.projects[0].urls[0]
    cards = bds.parse_cards((FIX / "listing_apartment.html").read_text(encoding="utf-8"))
    detail = tmp_path / "detail.html"
    detail.write_text((FIX / "detail_apartment.html").read_text(encoding="utf-8")
                      .replace("TODAY", date.today().strftime("%d/%m/%Y")), encoding="utf-8")
    fetcher = FileFetcher({listing_url: FIX / "listing_apartment.html", cards[0].link: detail})

    pipe = ApartmentPipeline(job, fetcher, start=date.today() - timedelta(days=7), max_pages=2)
    rows = pipe.run()

    # card 2 quá cũ (2020) bị loại; card 3 không có trang chi tiết -> dùng dữ liệu card
    assert [r["Tòa"] for r in rows] == ["S105", "S402"]
    first = rows[0]
    assert first["Phân khu"] == "Sapphire 1 (S1xx)"
    assert first["Loại căn"] == "2PN+" and first["Số Ngủ"] == 2
    assert first["Giá all-in (VNĐ tỷ)"] == 3.9 and first["Diện tích thông thủy"] == 64
    assert first["Đơn giá (triệu/m²)"] == 60.9
    assert first["Hướng"] == "Đông Nam" and first["Mã tin"] == "1001"
    assert rows[1]["Phân khu"] == "Sapphire 4 (S4xx)" and rows[1]["Loại căn"] == "1PN"

    df = to_frame(rows, pipe.columns, pipe.sort_by, job.zone_order)
    out = write_excel(df, tmp_path / "out.xlsx", summary_by=pipe.summary_by)
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Data", "Summary"]
    assert wb["Data"].max_row == 3


def test_past_date_range_does_not_stop_on_newer_pages():
    """Khoảng ngày trong quá khứ: trang 1 toàn tin mới hơn -> vẫn phải đi tiếp sang trang 2."""
    job = load_job(ROOT / "configs" / "apartment" / "vhsc_sapphire.toml")
    job.fetch_detail = False
    url = job.projects[0].urls[0]
    fetcher = FileFetcher({url: FIX / "listing_apartment.html", bds.page_url(url, 2): FIX / "listing_apartment.html"})
    calls = []
    orig = fetcher.fetch
    fetcher.fetch = lambda u, **kw: calls.append(u) or orig(u, **kw)

    # Mọi tin ở trang 1 đều MỚI hơn khoảng ngày -> 0 tin hợp lệ, nhưng không được dừng
    rows = ApartmentPipeline(job, fetcher, start=date(2019, 1, 1), end=date(2019, 6, 30), max_pages=2).run()
    assert rows == []
    assert bds.page_url(url, 2) in calls

    # Ngược lại: mọi tin đều CŨ hơn ngày bắt đầu -> dừng ngay sau trang 1
    calls.clear()
    ApartmentPipeline(job, fetcher, start=date(2099, 1, 1), end=date(2099, 2, 1), max_pages=2).run()
    assert calls == [url]


def test_detail_pipeline_apartment_sale(tmp_path):
    job = load_job(ROOT / "configs" / "detail" / "haiphong_apartment_sale.toml")
    job.include_expired = False
    project = job.projects[0]
    project.urls, project.aliases = [f"{SITE}/ban-can-ho-chung-cu-the-sapphire-vinhomes-smart-city"], ["sapphire"]
    job.projects = [project]
    cards = bds.parse_cards((FIX / "listing_apartment.html").read_text(encoding="utf-8"))
    detail = tmp_path / "detail.html"
    detail.write_text((FIX / "detail_apartment.html").read_text(encoding="utf-8")
                      .replace("TODAY", date.today().strftime("%d/%m/%Y")), encoding="utf-8")
    fetcher = FileFetcher({project.urls[0]: FIX / "listing_apartment.html", cards[0].link: detail})

    rows = DetailPipeline(job, fetcher, start=date.today() - timedelta(days=7), max_pages=1).run()
    assert len(rows) == 1  # chỉ tin 1001 có trang chi tiết và nằm trong khoảng ngày
    r = rows[0]
    assert r["Loại căn"] == "2PN" and r["Diện tích thông thủy"] == 64
    assert r["Ticket-size tham khảo (all-in, tỷ/ căn)"] == 3.9
    assert r["Đơn giá bán all-in tham khảo (triệu/m2)"] == 60.94
    assert r["Tình trạng căn hộ: Có đồ/ Không đồ"] == "Có đồ"
    assert r["VỊ TRÍ"] == "Tây Mỗ, Nam Từ Liêm, Hà Nội"


def test_lowrise_pipeline():
    job = load_job(ROOT / "configs" / "lowrise" / "hanoi_vinhomes_lowrise.toml")
    job.projects = job.projects[:1]  # Ocean Park 1
    fetcher = FileFetcher({job.projects[0].urls[0]: FIX / "listing_lowrise.html"})
    pipe = LowrisePipeline(job, fetcher, start=date.today() - timedelta(days=1), max_pages=1)
    rows = pipe.run()

    # card 2 không có giá (thỏa thuận) -> loại; card 3 là quảng cáo dự án khác -> loại
    assert len(rows) == 1
    r = rows[0]
    assert (r["Phân khu"], r["Mã căn"], r["Loại hình"]) == ("Sao Biển", "SB12-34", "Liền kề")  # 62,5m² < 70
    assert r["Tổng giá (tỷ)"] == 12.5 and r["Đơn giá All-in (triệu/m2)"] == 200.0
    assert r["Diện tích xây dựng (m2)"] == 250 and r["Chi phí xây dựng (tỷ)"] == 2.0
    assert r["Phân loại view"] == "Căn góc_View thoáng, đẹp"
    sheets = pipe.extra_sheets(rows)
    assert len(sheets["Raw data crawl"]) == 1 and sheets["Phân khu trống"].empty
