from datetime import datetime

from bdscrawler import zalo


def test_parse_message_text():
    text = "🔥 STT: 12\nToà/Giá: V3 - 6100tv\n2N+/64M/ĐN-TN\nNội thất: full\nLH: 09xx\nBonus: tặng phí"
    fields, extras = zalo.parse_message_text(text)
    assert fields["STT"] == "12"
    assert fields["Toà"] == "V3" and fields["Giá"] == "6100tv"
    assert fields["Loại căn"] == "2N+/64M/ĐN-TN" and fields["Số PN"] == 2 and fields["Diện tích"] == "64"
    assert extras == {"Bonus": "tặng phí"}


def test_to_frame_filters_non_listings():
    msgs = [
        {"msg_id": "1", "dt": datetime(2026, 8, 14, 9), "sender": "A", "text": "STT: 1\nGiá: 3 tỷ", "has_image": True},
        {"msg_id": "2", "dt": datetime(2026, 8, 14, 10), "sender": "B", "text": "chào cả nhà", "has_image": False},
        {"msg_id": "3", "dt": datetime(2026, 7, 1, 10), "sender": "C", "text": "STT: 9\nGiá: 1 tỷ", "has_image": False},
    ]
    df = zalo.to_frame(msgs, datetime(2026, 8, 13), datetime(2026, 8, 20))
    assert df["msg_id"].tolist() == ["1"]
    assert df.iloc[0]["Có ảnh"] == "x"
