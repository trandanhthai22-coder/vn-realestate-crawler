"""Kiểm tra quy tắc mã tòa / phân khu của từng file cấu hình trên các câu mẫu thật."""

from pathlib import Path

import pytest

from bdscrawler.config import discover, load_job

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def tower_zone(config: str, title: str, desc: str = "", project: int = 0):
    job = load_job(CONFIGS / "apartment" / config)
    p = job.projects[project]
    tower = job.tower_rules(p).extract([title, desc])
    return tower, job.zone_rules(p).identify(tower, f"{title} {desc}", p.zone or p.name)


def test_all_configs_load():
    paths = discover([CONFIGS])
    assert len(paths) >= 20
    for path in paths:
        assert load_job(path).projects


@pytest.mark.parametrize("config,title,desc,project,expected", [
    ("vhsc_sapphire.toml", "Bán 2PN tòa S1.05 giá tốt", "", 0, ("S105", "Sapphire 1 (S1xx)")),
    ("vhsc_sapphire.toml", "Bán căn S2 view hồ", "căn ở tòa S3-02", 0, ("S302", "Sapphire 3 (S3xx)")),
    ("vhsc_sapphire.toml", "Bán căn S2 view hồ", "", 0, ("S2", "Sapphire 2 (S2xx)")),
    ("vhsc_sapphire.toml", "Bán căn hộ đẹp", "", 0, ("", "Không xác định")),
    ("vhsc_canopy_sakura.toml", "Bán căn The Canopy 3 giá rẻ", "", 0, ("TC3", "The Canopy Residences")),
    ("vhsc_canopy_sakura.toml", "Sakura S-A5.2204 cần bán", "", 1, ("SA5", "The Sakura")),
    ("vhsc_imperia_sola.toml", "Bán căn D3 Imperia Sola Park", "", 0, ("D3", "Imperia Sola Park")),
    ("vhsc_lumiere_masteri_west.toml", "Bán căn west b Masteri", "", 1, ("West B", "Masteri West Heights")),
    ("vhsc_lumiere_masteri_west.toml", "Lumiere Evergreen tòa Halo", "", 0, ("The Halo", "Lumiere Evergreen")),
    ("lumi_hanoi.toml", "Bán căn Lumi Signature tòa Soleil 2", "", 0, ("Soleil 2", "Lumi Signature")),
    ("vhsc_tonkin_miami_victoria.toml", "Bán căn Tonkin 2 giá tốt", "", 0, ("TK2", "The Tonkin")),
    ("vhsc_tonkin_miami_victoria.toml", "Bán 2PN 65 m2 The Miami", "", 1, ("", "The Miami")),
    ("vhop_beverly_london_senique.toml", "Bán căn tòa LD2 The London", "", 1, ("LD2", "The London")),
    ("vhop_beverly_london_senique.toml", "Senique Premier view sông", "", 2, ("Senique Premier", "The Senique")),
    ("vhop_masteri_waterfront.toml", "Căn 65m2 The Nomad", "", 0, ("H1", "Hawaii")),
    ("vhop_masteri_waterfront.toml", "Bán căn M2 view biển hồ", "", 0, ("M2", "Miami")),
    ("vhop_masteri_waterfront.toml", "Bán căn 65m2 đẹp", "", 0, ("", "Không xác định")),
    ("vhop_sapphire_1_2.toml", "Bán căn s2-5 tầng cao", "", 1, ("S2.05", "Sapphire 2")),
    ("vhop_sapphire_1_2.toml", "Bán căn đẹp", "", 0, ("", "Sapphire 1")),
    ("vhop_masteri_lakeside_trinity_springbay.toml", "Bán căn tòa R1-02", "", 0, ("R1.02", "Masteri Lakeside")),
    ("vhop_lumiere_orient_masteri_era.toml", "Bán 2PN BF 2 view đẹp", "", 0, ("BF2", "Lumiere Orient Pearl")),
    ("vhop_lumiere_orient_masteri_era.toml", "Bán căn The Vision tòa ES1", "", 1, ("ES1", "The Vision")),
    # Vinhomes Global Gate — Imperia Signature: Y4/Y5 = The Continental, M1–M3 = The Cosmopolitan
    ("vhgg_global_gate.toml", "Bán căn Y4 góc 2PN giá tốt", "", 3, ("Y4", "The Continental")),
    ("vhgg_global_gate.toml", "Chính chủ bán toà M2 view hồ", "", 3, ("M2", "The Cosmopolitan")),
    # Bẫy: "m2" là đơn vị diện tích / đơn giá, KHÔNG phải tòa M2
    ("vhgg_global_gate.toml", "Bán căn 2PN 90 m2 giá 93 tr/m2", "61,8m2", 3, ("", "Imperia Signature")),
    ("vhgg_global_gate.toml", "Bán 2PN The Cosmopolitian giá tốt", "", 3, ("", "The Cosmopolitan")),
    ("vhgg_global_gate.toml", "Bán 2PN tòa A2 Masteri Grand Avenue", "", 0, ("A2", "Masteri Grand Avenue")),
    ("vhgg_global_gate.toml", "Bán căn đẹp", "Mã căn B2-15-02", 1, ("B2", "Lumiere Essence Peak")),
    ("vhgg_global_gate_guland.toml", "Bán căn 2PN tòa Y5", "", 3, ("Y5", "The Continental")),
    # Tiêu đề không ghi tòa, mô tả liệt kê cả 5 tòa -> để trống (không đoán Y4)
    ("vhgg_global_gate.toml", "Bán căn 2PN Imperia Cổ Loa", "Dự án gồm các tòa Y4, Y5, M1, M2, M3", 3,
     ("", "Imperia Signature")),
    # ...nhưng tiêu đề nêu đúng 1 tòa thì tiêu đề thắng
    ("vhgg_global_gate.toml", "Bán căn M1 2PN", "Dự án gồm các tòa Y4, Y5, M1, M2, M3", 3,
     ("M1", "The Cosmopolitan")),
    # Masteri Grand Coast — The Wave: L1, L2, Z1 ; The Sand: L3, L4, Z2, Z3
    ("vhop2_masteri_grand_coast.toml", "Bán căn 2PN toà L1 view hồ tạo sóng", "", 0, ("L1", "The Wave")),
    ("vhop2_masteri_grand_coast.toml", "Chính chủ bán tháp Z 3 giá tốt", "", 0, ("Z3", "The Sand")),
    ("vhop2_masteri_grand_coast.toml", "Bán căn góc", "Mã căn L4-15-02", 0, ("L4", "The Sand")),
    ("vhop2_masteri_grand_coast.toml", "Bán căn Z1 2PN", "Dự án gồm các tòa L1, L2, Z1, L3, L4, Z2, Z3", 0,
     ("Z1", "The Wave")),
    ("vhop2_masteri_grand_coast.toml", "Bán căn 2PN", "Dự án gồm các tòa L1, L2, Z1", 0, ("", "Không xác định")),
    ("vhop2_masteri_grand_coast.toml", "Bán căn L1/L2 giá tốt", "", 0, ("", "Không xác định")),
    ("vhop2_masteri_grand_coast.toml", "Bán căn 2PN phân khu The Sand", "", 0, ("", "The Sand")),
    ("vhop2_masteri_grand_coast.toml", "Bán căn 2PN", "Dự án gồm The Wave và The Sand", 0, ("", "Không xác định")),
    # Tòa không tồn tại / bẫy số liệu
    ("vhop2_masteri_grand_coast.toml", "Bán căn 2PN tòa L5, diện tích 65m2", "", 0, ("", "Không xác định")),
])
def test_tower_and_zone(config, title, desc, project, expected):
    assert tower_zone(config, title, desc, project) == expected
