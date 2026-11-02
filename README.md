# vn-realestate-crawler

> Crawler cấu hình bằng TOML cho website bất động sản Việt Nam (hiện hỗ trợ **batdongsan.com.vn**),
> bóc tách giá / diện tích / loại căn / mã tòa / phân khu và xuất **Excel đã định dạng** để làm benchmark giá.
>
> *A config-driven scraper for Vietnamese real-estate listings (batdongsan.com.vn) that extracts price, area,
> unit type, tower and sub-zone, and exports formatted Excel reports.*

```text
configs/*.toml ──► bdscrawl run ──► fetch (curl_cffi + Cloudflare) ──► parse ──► rules (tòa / phân khu) ──► Excel / CSV
```

## 🚀 Bắt đầu nhanh (Windows — không cần biết code)

Cần có sẵn: **Git**, **Python 3.11+** ([tải tại đây](https://www.python.org/downloads/), nhớ tick *Add python.exe to PATH*) và **Chrome hoặc Edge**.

1. Clone repo:
   ```bash
   git clone <repo-url> vn-realestate-crawler
   ```
2. Mở thư mục vừa clone, **nhấp đúp `setup.bat`** (chỉ làm 1 lần, mất 1–3 phút).
3. **Nhấp đúp `run.bat`** → chọn số thứ tự job → nhập **từ ngày** và **đến ngày** (vd `15/10/2026`) → số trang (Enter = mặc định).

File Excel kết quả nằm trong thư mục `output/`. Lần đầu có thể thấy cửa sổ Chrome/Edge tự bật lên vài giây rồi tắt — đó là bước vượt Cloudflare, cứ để yên.

Chạy bằng dòng lệnh trong **PowerShell** phải có `.\` ở đầu (CMD thì không cần):

```powershell
.\run.bat run configs\apartment\vhsc_sapphire.toml --from 2026-10-15
```

macOS / Linux: `./setup.sh` rồi `./run.sh`.

Cập nhật bản mới: `git pull` rồi chạy lại `setup.bat` nếu có báo lỗi thiếu thư viện.

## Tính năng

- **Một engine, nhiều dự án** — mỗi dự án/cụm dự án là 1 file `.toml` (URL, mã tòa, phân khu, bộ lọc). Thêm dự án mới **không cần viết code**.
- **3 chế độ crawl**
  | mode | dùng cho | nguồn dữ liệu |
  |---|---|---|
  | `apartment` | Benchmark giá bán căn hộ theo Phân khu / Tòa / Loại căn | card danh mục + trang chi tiết |
  | `lowrise` | Giá bán biệt thự / liền kề / shophouse, tính đơn giá NO đất & hạ tầng | card danh mục (nhanh) |
  | `detail` | Báo cáo thuê / bán (căn hộ hoặc thấp tầng) theo template Hải Phòng | trang chi tiết từng tin |
- **Nhận diện loại căn chính xác**: phân biệt `2PN` / `2PN+` / Studio / Duplex, tránh bẫy `2PN + 1WC` và tin liệt kê nhiều căn (đối chiếu diện tích + giá).
- **Quy tắc mã tòa / phân khu khai báo bằng regex** (`S1.01 → S101 → Sapphire 1`, `The Nomad → H1 → Hawaii`...).
- **Vượt Cloudflare Managed Challenge**: trình duyệt thật mở đường 1 lần, `curl_cffi` chạy việc; cookie cache dùng chung giữa nhiều tiến trình.
- **Chạy song song** nhiều job (`-j 4`), log riêng từng job.
- **Xuất Excel** có sheet `Data` + `Summary` (số lượng, DT/giá/đơn giá trung bình theo nhóm), tuỳ chọn CSV.
- **Công cụ Zalo**: trích tin đăng bán từ nhóm Zalo (script console + parser).
- **56 unit test** chạy offline trên HTML mẫu.

## Cài đặt

Yêu cầu Python ≥ 3.11 và một trình duyệt nhân Chromium (Chrome / Edge / Brave) để giải Cloudflare.

```bash
git clone <repo-url> vn-realestate-crawler
cd vn-realestate-crawler
python -m venv .venv
# Windows: .venv\Scripts\activate    |    macOS/Linux: source .venv/bin/activate
pip install -e ".[browser]"          # thêm ,dev để chạy test; ,firecrawl nếu dùng Firecrawl
```

## Dùng nhanh

```bash
# Liệt kê các job có sẵn
bdscrawl list configs

# Chạy 1 job, lọc tin từ 01/10/2026, tối đa 5 trang mỗi URL
bdscrawl run configs/apartment/vhsc_sapphire.toml --from 2026-10-01 --pages 5

# Chạy cả thư mục căn hộ, 4 job song song, xuất thêm CSV
bdscrawl run configs/apartment -j 4 --csv

# Nhanh hơn: chỉ đọc card danh mục, không mở trang chi tiết
bdscrawl run configs/apartment/vhop_sapphire_1_2.toml --no-detail

# Debug selector trên 1 trang HTML đã lưu (không cần mạng)
bdscrawl parse-html configs/apartment/vhsc_sapphire.toml saved_listing.html
```

Kết quả nằm trong `output/<tên job>_<YYYYMMDD_HHMMSS>.xlsx`, log song song trong `output/_logs/`.

Lần chạy đầu, nếu batdongsan bật Cloudflare challenge, **một cửa sổ trình duyệt sẽ bật lên vài giây rồi tự đóng** — đó là bước lấy cookie `cf_clearance`. Chi tiết và cách xử lý sự cố: [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md).

### Các tham số `bdscrawl run`

| Tham số | Ý nghĩa |
|---|---|
| `--from / --to` | Khoảng ngày đăng tin, dạng `15/10/2026` hoặc `2026-10-15`; bỏ `--to` = đến hôm nay (ghi đè `start_date` / `days_back` trong config) |
| `--pages N` | Số trang danh mục tối đa mỗi URL |
| `--delay S` | Giây nghỉ tối thiểu giữa 2 request (mặc định theo config, 1s) |
| `--no-detail` | Không mở trang chi tiết |
| `--out DIR` | Thư mục đầu ra (mặc định `output/`) |
| `--csv` | Xuất thêm CSV (UTF-8 BOM, mở được bằng Excel) |
| `-j N` | Số job chạy song song |
| `--backend curl\|firecrawl` | Backend tải trang (Firecrawl cần `FIRECRAWL_API_KEY`) |

## Các job có sẵn

| File | Nội dung | Thay cho script cũ |
|---|---|---|
| `apartment/vhsc_sapphire.toml` | The Sapphire S1–S4 (VHSC) | `VH_SM/Sapphire 1_4.py` |
| `apartment/vhsc_canopy_sakura.toml` | The Canopy Residences, The Sakura | `VH_SM/Ca_Sa.py` |
| `apartment/vhsc_imperia_sola.toml` | Imperia Smart City, Sola Park | `VH_SM/Imperia_Sola.py` |
| `apartment/vhsc_lumiere_masteri_west.toml` | Lumiere Evergreen, Masteri West Heights | `VH_SM/LMG_MWH.py` |
| `apartment/vhsc_tonkin_miami_victoria.toml` | The Tonkin, The Miami, The Victoria | `VH_SM/Tonkin_Miami_Vic.py` |
| `apartment/lumi_hanoi.toml` | Lumi Hanoi (Signature / Prestige / Elite) | `VH_SM/Lumi_hanoi.py` |
| `apartment/vhop_beverly_london_senique.toml` | The Beverly, The London, The Senique | `vinhome_OP/Ber_Lon_Sen.py` |
| `apartment/vhop_lumiere_orient_masteri_era.toml` | Lumiere Orient Pearl, Masteri Era Landmark | `vinhome_OP/LOP_MEL.py` |
| `apartment/vhop_masteri_waterfront.toml` | Masteri Waterfront (Hawaii / Miami) | `vinhome_OP/MWF_OP.py` |
| `apartment/vhop_masteri_lakeside_trinity_springbay.toml` | Masteri Lakeside, Trinity Square, Lumiere SpringBay | `vinhome_OP/Mas_OP.py` |
| `apartment/vhop_sapphire_1_2.toml` | The Sapphire 1 & 2 (VHOP) | `vinhome_OP/Sapphire1_2_OP.py` |
| `apartment/vhop_zenpark_zurich_pavilion_paris.toml` | Zenpark, Zurich, Pavilion, Paris | `vinhome_OP/zen_zu_pavi_paris.py` |
| `lowrise/hanoi_vinhomes_lowrise.toml` | Thấp tầng 6 KĐT Vinhomes Hà Nội | `crawl_thấp_tầng 1.py` |
| `detail/haiphong_apartment_rent.toml` | Thuê căn hộ Diamond Crown, Sentosa, Hoàng Huy Grand, Minato | `nha_thue_cao_tang_hoa_cai.py`, `hoa cai hai phong.txt` |
| `detail/haiphong_apartment_sale.toml` | Mua đứt căn hộ Gem Park, Diamond Crown | `gia mua dut hoa cai.py` |
| `detail/haiphong_imperia_lowrise_sale.toml` | Bán thấp tầng Vinhomes Imperia HP | `LK/Mua_LK_HP.py`, `mua_SH_hai_phong.py` |
| `detail/haiphong_marina_lowrise_rent.toml` | Thuê thấp tầng Vinhomes Marina | `LK/Thue_LK_HP.py` |
| `detail/haiphong_royal_island_lowrise_rent.toml` | Thuê thấp tầng Vinhomes Royal Island | `shop_house_thuong_mai/*.py` |
| `detail/haiphong_lowrise_rent_multi.toml` | Thuê thấp tầng 12 dự án Hải Phòng | `DATA/fast_Scapling.py`, `DATA/fire_crawl.py` |
| `detail/hanoi_south_land_sale.toml` | Nhà đất bán Thường Tín, Thanh Trì, Thanh Oai, Hoàng Mai | `Khu vực phía Nam/thuong_tin_crawler.py` |

Mặc định các job lọc tin trong `days_back` ngày gần nhất (7–90 ngày tuỳ job); đổi bằng `--from`.

## Thêm một dự án mới

Sao chép file gần giống nhất trong `configs/` rồi sửa. Ví dụ tối thiểu:

```toml
name = "VHSC · The Victoria"
mode = "apartment"
benchmark = "Vinhomes Smart City"
output = "vhsc_victoria"

[crawl]
days_back = 30
max_pages = 20

[[projects]]
name = "The Victoria"
urls = ["/ban-can-ho-chung-cu-the-victoria-vinhomes-smart-city"]   # path danh mục trên batdongsan

[[towers]]                       # mã tòa: "tòa V1", "V2"...
pattern = '\b(v[1-3])\b'

[[zones]]                        # phân khu suy từ mã tòa (bỏ trống -> dùng tên project)
pattern = '^V'
value = "The Victoria"
```

Kiểm tra nhanh: `bdscrawl list configs/your_file.toml`, rồi chạy với `--pages 1`.
Tham chiếu đầy đủ các trường: [docs/CONFIG.md](docs/CONFIG.md).

## Công cụ Zalo

1. Mở <https://chat.zalo.me> trên Chrome, vào nhóm cần lấy tin.
2. F12 → Console → dán toàn bộ [`tools/zalo_dump.js`](tools/zalo_dump.js) (sửa `FROM_DATE` trước) → Enter. Script tự cuộn và tải về `zalo_messages.json`.
3. `bdscrawl zalo zalo_messages.json --from 2026-08-13`

Chỉ dùng với nhóm bạn là thành viên và tôn trọng quyền riêng tư của người đăng.

## Cấu trúc mã nguồn

```text
src/bdscrawler/
├── cli.py            # lệnh bdscrawl
├── config.py         # đọc/kiểm tra file TOML
├── http.py           # backend tải trang: curl_cffi | Firecrawl | file offline
├── cloudflare.py     # lấy & cache cookie cf_clearance, khoá liên tiến trình
├── sites/batdongsan.py   # selector DOM: card danh mục + trang chi tiết
├── pipelines/        # apartment | lowrise | detail
├── rules.py          # engine quy tắc mã tòa / phân khu
├── bedrooms.py       # nhận diện Studio / 2PN / 2PN+ / Duplex
├── features.py       # hướng, view, nội thất, mặt tiền, lộ giới, cho thuê...
├── numbers.py, dates.py, text.py
├── export.py         # Excel (Data + Summary) / CSV
└── zalo.py           # parser tin nhắn Zalo
```

Khi batdongsan đổi giao diện, thường chỉ cần sửa `sites/batdongsan.py`. Muốn hỗ trợ website khác (alonhadat, mogi, guland...), thêm một adapter mới trong `sites/` cung cấp `parse_cards`, `parse_detail`, `page_url` — xem [CONTRIBUTING.md](CONTRIBUTING.md).

## Phát triển

```bash
pip install -e ".[dev]"
pytest
```

Test chạy hoàn toàn offline trên HTML mẫu trong `tests/fixtures/`.

## Sử dụng có trách nhiệm

- Công cụ phục vụ **nghiên cứu thị trường** trên dữ liệu công khai. Bạn tự chịu trách nhiệm tuân thủ Điều khoản sử dụng của website, `robots.txt` và pháp luật Việt Nam về dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP).
- Giữ tốc độ thấp (mặc định ≥ 1 giây/request, không đặt `--delay` quá nhỏ hoặc `-j` quá lớn); không dùng để làm quá tải máy chủ.
- Không công bố thông tin cá nhân của người đăng tin. Các pipeline batdongsan không lấy tên / số điện thoại; riêng output Zalo có cột `Người đăng`, `Liên hệ`, `Nội dung gốc` — xoá các cột này trước khi chia sẻ file.
- Không commit cookie (`cf_cookies*.json`), API key hay file kết quả lên git — `.gitignore` đã chặn sẵn.

## Giấy phép

[MIT](LICENSE)
