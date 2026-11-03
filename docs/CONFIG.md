# Tham chiếu file cấu hình (TOML)

Mỗi file `.toml` là một **job**. Lưu ý cú pháp TOML: các key cấp cao (`name`, `zone_order`...) phải đứng
**trước** mọi bảng `[crawl]`, `[[projects]]`, `[[towers]]`... Regex nên viết trong nháy đơn `'...'`
(chuỗi literal, không phải escape `\`).

## Cấp cao

| Key | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `name` | str | tên file | Tên hiển thị |
| `mode` | `apartment` \| `lowrise` \| `detail` | `apartment` | Chế độ crawl |
| `record` | `apartment_rent` \| `apartment_sale` \| `lowrise_rent` \| `lowrise_sale` | `apartment_sale` | Bộ cột output (chỉ mode `detail`) |
| `site` | URL | `https://batdongsan.com.vn` | Website nguồn — chọn adapter (`batdongsan.com.vn` hoặc `guland.vn`) và là gốc để ghép `urls` dạng path |
| `output` | str | tên file | Tiền tố file kết quả |
| `benchmark` | str | `""` | Giá trị cột `Benchmark` (mode `apartment`) |
| `project_label` | str | `""` | Giá trị cột `Dự án` cho mọi project (mặc định = `name` của project) |
| `default_address` | str | `""` | Vị trí mặc định khi tin không ghi (mode `detail`) |
| `zone_order` | list[str] | `[]` | Thứ tự sắp xếp phân khu trong báo cáo |
| `zone_colors` | table | tự sinh | Màu nền theo phân khu, vd `{ "Sapphire 1 (S1xx)" = "E8F4FD" }` |

## `[crawl]`

| Key | Mặc định | Ý nghĩa |
|---|---|---|
| `start_date` / `end_date` | — / hôm nay | Khoảng ngày đăng (`2026-10-01`) |
| `days_back` | — | Thay cho `start_date`: lấy N ngày gần nhất. Không có cả hai -> từ đầu tháng |
| `max_pages` | 30 | Số trang danh mục tối đa mỗi URL |
| `delay` | 1.0 | Giây nghỉ tối thiểu giữa 2 request (có jitter) |
| `fetch_detail` | true | Mở trang chi tiết để lấy ngày đăng chuẩn, mã tin, mô tả đầy đủ |
| `stop_on_empty_page` | true | Dừng URL khi một trang không có tin hợp lệ nào |
| `include_expired` | false | Quét thêm biến thể `?expired=true` (tin hết hạn) |

## `[filters]`

| Key | Ý nghĩa |
|---|---|
| `apartments_only` | Chỉ giữ link `/ban-can-ho-chung-cu...` (bỏ shophouse lẫn trong URL `nha-dat-ban-...`) |
| `studio_only` | Chỉ giữ căn Studio |
| `exclude_lowrise` | Bỏ tin shophouse / liền kề / biệt thự (mode `detail`, record căn hộ) |
| `unit_price_min` / `unit_price_max` | Lọc theo đơn giá (triệu/m²) |
| `location_any` | Danh sách regex, khớp trên text **không dấu**; tin không khớp bị loại (trừ khi link thuộc đúng path dự án) |
| `require_area_and_price` | Bỏ tin thiếu diện tích hoặc giá (mặc định bật ở mode `lowrise`) |

## `[[projects]]`

| Key | Ý nghĩa |
|---|---|
| `name` | Tên dự án (cột `Dự án`, hoặc `Phân khu` khi có `project_label`) |
| `urls` | Danh sách URL danh mục — path (`/ban-can-ho-...`) hoặc URL đầy đủ |
| `zone` | Phân khu mặc định khi quy tắc `zones` không khớp (mặc định = `name`) |
| `label` | Ghi đè `project_label` cho riêng project này |
| `keywords` / `aliases` | Từ khoá (OR, không phân biệt dấu) phải xuất hiện trong tiêu đề/mô tả/vị trí/link — chặn tin "liên quan" của dự án khác |
| `towers`, `tower_options`, `zones` | Ghi đè quy tắc cấp job cho riêng project (`[[projects.towers]]`...) |

Chỉ cho thấp tầng (`lowrise` và `detail` record `lowrise_*`):

| Key | Ý nghĩa |
|---|---|
| `[projects.subdivisions]` | `"Tên phân khu" = ["alias", ...]` — tên chuẩn luôn được tự thêm làm alias |
| `[projects.code_prefixes]` | `"Tên phân khu" = ["SB", ...]` — suy phân khu từ tiền tố mã căn (ưu tiên tiền tố dài nhất) |
| `zone_renames` | Đổi tên phân khu trong output, vd `{ "Ban Mai" = "Hừng Đông" }` |
| `exclude_zones` | Loại các phân khu này (so sau khi đổi tên) |
| `[[projects.type_rules]]` | Phân loại Liền kề / Biệt thự theo phân khu + diện tích — xem dưới |
| `province`, `district` | Thông tin tham khảo |

### `type_rules`

Xét theo thứ tự, quy tắc khớp đầu tiên thắng; không quy tắc nào khớp -> giữ loại hình đọc từ tin.

```toml
[[projects.type_rules]]
zones = ["Sao Biển"]     # bỏ trống = mọi phân khu
area_lt = 70             # area_lt | area_lte | area_gt | area_gte  (m² đất)
type = "Liền kề"
keep_types = []          # nếu loại hình đọc được nằm trong danh sách này thì giữ nguyên
```

Có điều kiện diện tích (hoặc `keep_types`) mà tin không có diện tích -> quy tắc không khớp.

## `[[towers]]` — mã tòa

```toml
[tower_options]
exclude = ["PN1", "M2"]        # bỏ các giá trị bắt nhầm
accent_insensitive = false     # true: so khớp trên text đã bỏ dấu (viết regex không dấu)
on_multiple = "first"          # "blank": một đoạn văn nêu NHIỀU tòa khác nhau -> để trống thay vì lấy tòa đầu

[[towers]]
pattern = '\bt[oòóô]a\s+(s[1-4][.\-\s]?\d{2})\b'
value = "{1}"          # template: {0} cả cụm, {1}.. các group; hỗ trợ format spec, vd "S{2}.{3:0>2}"
normalize = "compact"  # compact: bỏ . - _ space + IN HOA | dot: thay - _ space bằng "." | upper | title | none
fallback = false       # true: chỉ xét khi mọi quy tắc thường thất bại trên mọi đoạn văn
```

Thứ tự xét: với mỗi đoạn văn theo ưu tiên **tiêu đề → mô tả → vị trí + link**, thử lần lượt các quy tắc
thường; hết mới tới quy tắc `fallback`. Text luôn được viết thường trước khi so khớp.

## `[[zones]]` — phân khu

```toml
[[zones]]
on = "tower"                    # "tower": khớp trên mã tòa vừa nhận diện | "text": trên tiêu đề + mô tả + vị trí (KHÔNG DẤU, viết thường)
pattern = '^S([1-4])(\d{2})?$'
value = "Sapphire {1} (S{1}xx)"
```

Quy tắc đầu tiên khớp thắng; không khớp -> `projects.zone` hoặc tên project.

## `[lowrise]`

| Key | Mặc định | Ý nghĩa |
|---|---|---|
| `construction_rate` | 8.0 | Đơn giá xây dựng giả định (triệu/m² sàn) để tính giá NO đất & hạ tầng |
