# Cloudflare & lỗi 403

## Vì sao bị 403

batdongsan.com.vn bật **Cloudflare Managed Challenge**: mọi request HTTP thuần nhận

```text
HTTP/2 403
cf-mitigated: challenge
<title>Just a moment...</title>
```

Đây là trang đố JavaScript, không phải chặn theo User-Agent: đổi header hay đổi profile giả lập TLS
(`chrome`, `safari`, `firefox`...) đều không qua được. Trình duyệt thật phải chạy JS rồi mới được cấp
cookie `cf_clearance`.

## Cách repo xử lý

```text
curl_cffi gửi request ──► 403 + challenge? ──không──► trả HTML
                               │ có
                               ▼
              Mở Chrome/Edge thật (1 lần, KHÔNG headless)
              → nhận cf_clearance → lưu cache → đóng trình duyệt
                               │
              Cấy cookie + đúng User-Agent của trình duyệt vào curl_cffi → thử lại
```

- Cookie cache ở `~/.cache/bdscrawler/cf_cookies_<domain>.json` (đổi bằng `BDS_CACHE_DIR`), coi là hết hạn sau 20 phút.
- Chạy song song (`-j N`): khoá liên tiến trình đảm bảo trình duyệt chỉ mở **1 lần**, các tiến trình khác chờ rồi dùng chung cookie.
- Sau khi lấy cookie mới, crawler gõ lại chính URL đích cho tới khi hết challenge (cookie cần vài giây để đồng bộ giữa các edge của Cloudflare).
- Chỉ gửi thêm `Referer` mỗi request. **Không** hardcode User-Agent hay thêm header tự chế — cookie bị ràng buộc với UA đã sinh ra nó, lệch UA là mất hiệu lực ngay.

Có thể lấy cookie trước: `bdscrawl cf-refresh`.

## Xử lý sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| `Thiếu DrissionPage` | `pip install "vn-realestate-crawler[browser]"` |
| `Không tìm thấy trình duyệt Chromium` | Đặt `BDS_BROWSER_PATH` trỏ tới `chrome.exe` / `msedge.exe` |
| Vẫn 403 liên tục | Xoá file cache cookie để lấy lại từ đầu. Cookie gắn với **IP** — đổi mạng/VPN giữa chừng là phải lấy lại |
| Log "chờ khoá Cloudflare quá lâu" | Xoá `%TEMP%\bdscrawler_cf_<domain>.lock` (hoặc `/tmp/...`) |
| Máy chủ không có màn hình (CI, server) | Lấy cookie thủ công (dưới) hoặc dùng `--backend firecrawl` |

### Lấy cookie thủ công

Mở site bằng Chrome, F12 → Application → Cookies, copy `cf_clearance`; lấy User-Agent bằng
`navigator.userAgent` trong Console. Tạo file `~/.cache/bdscrawler/cf_cookies_batdongsan.com.vn.json`:

```json
{
  "saved_at": 1762070000,
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
  "cookies": { "cf_clearance": "giá_trị_copy_từ_trình_duyệt" }
}
```

`saved_at` là Unix timestamp lúc lấy cookie (`python -c "import time; print(int(time.time()))"`).

## Lưu ý

Cơ chế này chỉ để truy cập trang công khai với tốc độ như người dùng bình thường. Hãy giữ `delay` hợp lý,
tôn trọng Điều khoản sử dụng của website, và dừng lại nếu chủ site yêu cầu.
