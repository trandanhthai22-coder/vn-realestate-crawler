# Đóng góp

Cảm ơn bạn muốn đóng góp! Một số hướng dẫn ngắn:

## Môi trường

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev,browser]"
pytest
```

## Thêm / sửa dự án

Hầu hết thay đổi chỉ cần sửa file trong `configs/` — xem [docs/CONFIG.md](docs/CONFIG.md).
Khi thêm quy tắc mã tòa, hãy thêm vài câu mẫu thật vào `tests/test_rules.py` để tránh hồi quy.

## Khi batdongsan đổi giao diện

Selector nằm tập trung trong `src/bdscrawler/sites/batdongsan.py`. Lưu một trang danh mục bằng trình duyệt
(Ctrl+S), rồi:

```bash
bdscrawl parse-html configs/apartment/vhsc_sapphire.toml trang_da_luu.html
```

Sửa selector tới khi ra đúng dữ liệu, rồi cập nhật fixture trong `tests/fixtures/` (đã xoá thông tin cá nhân).

## Thêm website mới

Tạo `src/bdscrawler/sites/<ten_site>.py` cung cấp:

- `page_url(base_url, page) -> str`
- `parse_cards(html, base) -> list[Card]`
- `parse_detail(html, url) -> Detail`

(dùng lại dataclass `Card`, `Detail` trong `sites/batdongsan.py`), sau đó cho pipeline chọn adapter theo
`site` trong config. Các nguồn đã từng dùng nhưng **chưa có adapter**: alonhadat.com.vn (hay chặn CAPTCHA
khi crawl nhanh), mogi.vn, guland.vn, thuviennhadat.vn, nhatot.com, housenow.com.vn.

## Quy ước

- Comment / log bằng tiếng Việt có dấu, tên hàm/biến tiếng Anh.
- Không commit dữ liệu crawl, cookie, API key, file có số điện thoại thật.
- Pull request kèm test cho logic parse mới.
