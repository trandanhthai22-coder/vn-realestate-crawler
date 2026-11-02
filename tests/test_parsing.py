from datetime import date

import pytest

from bdscrawler.bedrooms import extract_bedrooms, infer_unit_type_simple
from bdscrawler.dates import parse_cli_date, parse_date
from bdscrawler.features import extract_direction, extract_view, property_type, rental_terms, unit_code
from bdscrawler.numbers import parse_area, parse_price, parse_price_billion, parse_rent_million
from bdscrawler.text import contains_any, label_key

TODAY = date(2026, 10, 20)


@pytest.mark.parametrize("raw,expected", [
    ("Hôm nay", TODAY),
    ("Đăng hôm qua", date(2026, 10, 19)),
    ("3 ngày trước", date(2026, 10, 17)),
    ("2 tuần trước", date(2026, 10, 6)),
    ("5 giờ trước", TODAY),
    ("15/10/2026", date(2026, 10, 15)),
    ("2026-10-01", date(2026, 10, 1)),
    ("25/12", date(2025, 12, 25)),   # không có năm, rơi vào tương lai xa -> năm trước
    ("", None),
    ("không rõ", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw, TODAY) == expected


@pytest.mark.parametrize("raw,area,expected", [
    ("3,75 tỷ", 62.0, (3.75, 60.48)),
    ("850 triệu", 30.0, (0.85, 28.33)),
    ("65 triệu/m²", 100.0, (6.5, 65.0)),
    ("Thỏa thuận", 50.0, (None, None)),
    ("12 tỷ", None, (12.0, None)),
])
def test_parse_price(raw, area, expected):
    assert parse_price(raw, area) == expected


def test_price_and_area_helpers():
    assert parse_price_billion("3,9 tỷ") == 3.9
    assert parse_price_billion("65 triệu/m²") is None  # thiếu diện tích -> không suy ra tổng giá
    assert parse_area("62,5 m²") == 62.5
    assert parse_area("N/A") is None
    assert parse_rent_million("15 triệu/tháng") == 15
    assert parse_rent_million("12.000.000 đ") == 12
    assert parse_rent_million("Thỏa thuận") is None


@pytest.mark.parametrize("raw", ["2026-10-15", "15/10/2026", "15-10-2026", " 15/10/2026 "])
def test_parse_cli_date(raw):
    assert parse_cli_date(raw) == date(2026, 10, 15)


def test_parse_cli_date_invalid():
    with pytest.raises(ValueError):
        parse_cli_date("32/10/2026")


def test_menu_rejects_reversed_range(monkeypatch, capsys):
    from bdscrawler import cli

    answers = iter(["11", "abc", "20/10/2026", "15/10/2026"])  # nhập sai 1 lần, rồi đảo ngược khoảng ngày
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert cli.main(["menu", "configs"]) == 1
    out = capsys.readouterr().out
    assert "Ngày không hợp lệ" in out and "sau ngày kết thúc" in out


def test_text_helpers():
    assert label_key("Ngày\n           đăng:") == "ngay dang"
    assert contains_any("ban-can-ho-diamond-crown-hai-phong-pr123", ["Diamond Crown"])
    assert not contains_any("Gem Park", ["diamond crown"])


@pytest.mark.parametrize("title,desc,base,area,price,expected", [
    # '+' liệt kê phòng vệ sinh, không phải loại căn 2PN+
    ("Bán căn 2PN + 1 phòng vệ sinh", "", ["2 PN"], 55, 3.3, ("2PN", 2)),
    # tin liệt kê nhiều căn: chọn token có diện tích/giá khớp chính tin
    ("Bán nhiều căn", "2PN 55m² 3,3 tỷ … 2PN + 64m² 3,9 tỷ", ["2"], 64, 3.9, ("2PN+", 2)),
    ("Bán nhiều căn", "2PN 55m² 3,3 tỷ … 2PN + 64m² 3,9 tỷ", ["2"], 55, 3.3, ("2PN", 2)),
    ("Studio full đồ 30m2", "", ["1"], 30, 1.8, ("Studio", 1)),
    ("Bán duplex 2 tầng", "", [], None, None, ("Duplex", None)),
    ("Bán căn hộ đẹp", "", ["3 phòng ngủ"], None, None, ("3PN", 3)),
    ("Bán căn hộ đẹp", "", [], None, None, ("N/A", None)),
])
def test_extract_bedrooms(title, desc, base, area, price, expected):
    assert extract_bedrooms(title, desc, base, area, price) == expected


def test_simple_unit_type():
    assert infer_unit_type_simple("Cho thuê 2 phòng ngủ full đồ") == "2PN"
    assert infer_unit_type_simple("cho thuê studio") == "Studio"
    assert infer_unit_type_simple("cho thuê căn hộ") == ""


def test_features():
    assert extract_direction("Căn hộ hướng Đông Nam") == "Đông Nam"
    assert extract_view("Căn góc view sông thoáng") == ("Căn góc_View sông", "view song")
    assert property_type("Bán biệt thự song lập", detailed=True) == "Biệt thự song lập"
    assert property_type("Shophouse mặt đường") == "Shophouse"
    assert unit_code("Bán liền kề SB12-34 Ocean Park") == "SB12-34"
    assert unit_code("Bán căn MHT 25 đẹp", ["MHT"]) == "MHT25"
    assert rental_terms("Cho thuê nguyên căn giá 45 triệu/tháng") == (45.0, "", None)
