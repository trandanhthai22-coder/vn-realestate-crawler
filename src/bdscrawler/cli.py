"""Dòng lệnh ``bdscrawl``.

Ví dụ::

    bdscrawl list configs/
    bdscrawl run configs/apartment/vhsc_sapphire.toml --from 2026-10-01 --pages 5
    bdscrawl run configs/apartment -j 4                # chạy cả thư mục, 4 job song song
    bdscrawl parse-html configs/apartment/vhsc_sapphire.toml saved_page.html
    bdscrawl zalo zalo_messages.json --from 2026-08-13
    bdscrawl cf-refresh                               # giải Cloudflare trước, lưu cache cookie
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dtime
from pathlib import Path

from bdscrawler import __version__
from bdscrawler.config import discover, load_job
from bdscrawler.dates import parse_cli_date

log = logging.getLogger("bdscrawler")


def force_utf8_console() -> None:
    """Console Windows / output bị chuyển hướng mặc định cp1252 -> in tiếng Việt văng lỗi 'charmap'.

    Phải gọi TRƯỚC mọi lệnh print, kể cả trước argparse (vì --help / thông báo lỗi tham số có tiếng Việt).
    """
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")  # tiến trình con kế thừa
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _setup_logging(verbose: bool, log_file: Path | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", handlers=handlers, force=True)


def _date(value: str) -> date:
    try:
        return parse_cli_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


# ──────────────────────────────────────────────────────────────────────────────
def cmd_list(args) -> int:
    for path in discover(args.paths):
        try:
            job = load_job(path)
            urls = sum(len(p.urls) for p in job.projects)
            print(f"{str(path):<60} {job.mode:<10} {len(job.projects):>2} dự án, {urls:>2} URL  {job.name}")
        except Exception as exc:
            print(f"{str(path):<60} LỖI: {exc}")
    return 0


def run_job(path: Path, args) -> Path | None:
    from bdscrawler.export import output_path, to_frame, write_excel
    from bdscrawler.http import make_fetcher
    from bdscrawler.pipelines import PIPELINES

    job = load_job(path)
    if args.no_detail:
        job.fetch_detail = False
    fetcher = make_fetcher(args.backend, job.site, delay=args.delay if args.delay is not None else job.delay)
    pipeline = PIPELINES[job.mode](job, fetcher, start=args.date_from, end=args.date_to, max_pages=args.pages)
    log.info("Job %s (%s) — lọc tin từ %s đến %s", job.name, job.mode, pipeline.start, pipeline.end)

    rows = pipeline.run()
    if not rows:
        log.warning("Không có dữ liệu hợp lệ cho %s.", job.name)
        return None
    df = to_frame(rows, pipeline.columns, pipeline.sort_by, job.zone_order)
    out = output_path(args.out, job.output)
    write_excel(df, out, summary_by=pipeline.summary_by, extra=pipeline.extra_sheets(rows),
                zone_colors=job.zone_colors)
    if args.csv:
        df.to_csv(out.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    log.info("Đã xuất %s dòng -> %s", len(df), out)
    return out


def _run_parallel(paths: list[Path], args) -> int:
    """Mỗi job một tiến trình con; cookie Cloudflare dùng chung qua cache + khoá liên tiến trình."""
    log_dir = Path(args.out) / "_logs" / datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)
    passthrough = ["--out", str(args.out), "--backend", args.backend]
    for flag, value in (("--from", args.date_from), ("--to", args.date_to), ("--pages", args.pages),
                        ("--delay", args.delay)):
        if value is not None:
            passthrough += [flag, str(value)]
    passthrough += ["--csv"] * args.csv + ["--no-detail"] * args.no_detail

    def one(path: Path):
        started = time.time()
        log_path = log_dir / f"{path.stem}.log"
        with log_path.open("w", encoding="utf-8") as fh:
            proc = subprocess.run([sys.executable, "-m", "bdscrawler", "run", str(path), *passthrough],
                                  stdout=fh, stderr=subprocess.STDOUT)
        return path, proc.returncode, time.time() - started, log_path

    failed = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for fut in as_completed([pool.submit(one, p) for p in paths]):
            path, code, secs, log_path = fut.result()
            failed += code != 0
            print(f"[{'OK  ' if code == 0 else f'FAIL({code})'}] {path.stem:<45} {secs:7.1f}s  log: {log_path}")
    return 1 if failed else 0


def cmd_run(args) -> int:
    if args.date_from and args.date_to and args.date_from > args.date_to:
        print(f"Lỗi: --from {args.date_from:%d/%m/%Y} sau --to {args.date_to:%d/%m/%Y}.")
        return 2
    paths = discover(args.configs)
    if not paths:
        print("Không tìm thấy file cấu hình .toml nào.")
        return 1
    if args.jobs > 1 and len(paths) > 1:
        return _run_parallel(paths, args)
    failed = 0
    for path in paths:
        try:
            run_job(path, args)
        except KeyboardInterrupt:
            raise
        except Exception:
            log.exception("Job %s lỗi", path)
            failed += 1
    return 1 if failed else 0


def cmd_parse_html(args) -> int:
    """Chạy pipeline trên file HTML trang danh mục đã lưu (không mở trang chi tiết) — để debug selector."""
    import pandas as pd

    from bdscrawler.http import FileFetcher
    from bdscrawler.pipelines import PIPELINES

    job = load_job(args.config)
    job.fetch_detail = False
    job.projects = job.projects[:1]
    url = job.projects[0].urls[0]
    job.projects[0].urls = [url]
    start = args.date_from or date(2000, 1, 1)
    pipeline = PIPELINES[job.mode](job, FileFetcher({url: args.html}), start=start, max_pages=1)
    rows = pipeline.run()
    pd.set_option("display.width", 200)
    print(pd.DataFrame(rows, columns=pipeline.columns).head(args.limit).to_string())
    print(f"\n{len(rows)} dòng.")
    return 0


def cmd_zalo(args) -> int:
    from bdscrawler import zalo
    from bdscrawler.export import write_excel

    messages = zalo.load(args.source)
    end = args.date_to or date.today()
    df = zalo.to_frame(messages, datetime.combine(args.date_from, dtime.min), datetime.combine(end, dtime.max),
                       keep_all=args.all)
    print(f"Đọc {len(messages)} tin, giữ {len(df)} tin đăng bán.")
    if df.empty:
        return 1
    out = Path(args.output or Path(args.out) / f"zalo_{args.date_from:%Y%m%d}_{end:%Y%m%d}.xlsx")
    write_excel(df, out, zone_col="Người đăng")
    print(f"-> {out}")
    return 0


def _ask(prompt: str, default: str = "") -> str:
    try:
        value = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:
        value = ""
    return value or default


def _ask_date(prompt: str) -> date | None:
    """Hỏi ngày tới khi hợp lệ; Enter bỏ trống -> None."""
    while True:
        raw = _ask(prompt)
        if not raw:
            return None
        try:
            return parse_cli_date(raw)
        except ValueError as exc:
            print(f"  {exc}")


def cmd_menu(args) -> int:
    """Menu cho người không quen dòng lệnh: chọn job, khoảng ngày, số trang rồi chạy."""
    jobs = []
    for path in discover(args.paths):
        try:
            jobs.append((path, load_job(path)))
        except Exception as exc:
            print(f"[bỏ qua] {path}: {exc}")
    if not jobs:
        print("Không tìm thấy file cấu hình nào trong", args.paths)
        return 1

    print("\n=== CÁC JOB CÓ SẴN ===")
    for i, (path, job) in enumerate(jobs, 1):
        print(f"  {i:>2}. [{job.mode:<9}] {job.name}")
    print("   0. Chạy TẤT CẢ")
    choice = _ask("\nChọn số (nhiều job cách nhau dấu phẩy, vd 1,3)", "1")
    if choice.strip() == "0":
        picked = [p for p, _ in jobs]
    else:
        try:
            picked = [jobs[int(x) - 1][0] for x in choice.replace(" ", "").split(",") if x]
        except (ValueError, IndexError):
            print("Lựa chọn không hợp lệ.")
            return 1

    date_from = _ask_date("Lấy tin đăng TỪ ngày (vd 15/10/2026, Enter = theo cấu hình)")
    date_to = _ask_date("ĐẾN ngày (Enter = hôm nay)")
    if date_from and date_to and date_from > date_to:
        print(f"Ngày bắt đầu {date_from:%d/%m/%Y} sau ngày kết thúc {date_to:%d/%m/%Y}.")
        return 1
    pages = _ask("Số trang tối đa mỗi URL (Enter = theo cấu hình)")
    argv = ["run", *map(str, picked), "--out", args.out]
    if date_from:
        argv += ["--from", date_from.isoformat()]
    if date_to:
        argv += ["--to", date_to.isoformat()]
    if pages:
        argv += ["--pages", pages]
    if len(picked) > 1:
        argv += ["-j", str(min(4, len(picked)))]
    print("\n> bdscrawl " + " ".join(argv[1:]) + "\n")
    run_args = build_parser().parse_args(argv)
    code = run_args.func(run_args)
    print(f"\nXong. Kết quả trong thư mục: {Path(args.out).resolve()}")
    return code


def cmd_cf_refresh(args) -> int:
    from bdscrawler import cloudflare

    result = cloudflare.solve(args.url)
    print("OK — cookie đã lưu vào", cloudflare.cache_dir()) if result else print("Không lấy được cookie.")
    return 0 if result else 1


# ──────────────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdscrawl", description="Crawler bất động sản Việt Nam cấu hình bằng TOML.")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="liệt kê các job trong file/thư mục cấu hình")
    p.add_argument("paths", nargs="*", default=["configs"])
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("run", help="chạy 1 hoặc nhiều job")
    p.add_argument("configs", nargs="+", help="file .toml hoặc thư mục chứa .toml")
    p.add_argument("--from", dest="date_from", type=_date, help="lọc tin đăng từ ngày (YYYY-MM-DD)")
    p.add_argument("--to", dest="date_to", type=_date, help="đến ngày (mặc định hôm nay)")
    p.add_argument("--pages", type=int, help="số trang danh mục tối đa mỗi URL")
    p.add_argument("--delay", type=float, help="giây nghỉ tối thiểu giữa 2 request")
    p.add_argument("--out", default="output", help="thư mục đầu ra (mặc định ./output)")
    p.add_argument("--csv", action="store_true", help="xuất thêm file CSV")
    p.add_argument("--backend", default="curl", choices=["curl", "firecrawl"])
    p.add_argument("--no-detail", action="store_true", help="không mở trang chi tiết (nhanh, ít trường hơn)")
    p.add_argument("-j", "--jobs", type=int, default=1, help="số job chạy song song (tiến trình con)")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("parse-html", help="parse thử 1 file HTML trang danh mục đã lưu")
    p.add_argument("config")
    p.add_argument("html")
    p.add_argument("--from", dest="date_from", type=_date)
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_parse_html)

    p = sub.add_parser("zalo", help="parse tin đăng bán từ nhóm Zalo (JSON của tools/zalo_dump.js)")
    p.add_argument("source")
    p.add_argument("--from", dest="date_from", type=_date, default=date(date.today().year, 1, 1))
    p.add_argument("--to", dest="date_to", type=_date)
    p.add_argument("--all", action="store_true", help="giữ mọi tin, không chỉ tin đăng bán")
    p.add_argument("--out", default="output")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_zalo)

    p = sub.add_parser("menu", help="menu tương tác: chọn job rồi chạy")
    p.add_argument("paths", nargs="*", default=["configs"])
    p.add_argument("--out", default="output")
    p.set_defaults(func=cmd_menu)

    p = sub.add_parser("cf-refresh", help="mở trình duyệt giải Cloudflare và lưu cookie")
    p.add_argument("--url", default="https://batdongsan.com.vn/")
    p.set_defaults(func=cmd_cf_refresh)
    return ap


def main(argv: list[str] | None = None) -> int:
    force_utf8_console()
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
