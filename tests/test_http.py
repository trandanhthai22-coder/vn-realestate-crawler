"""Lỗi curl (77): libcurl không đọc được file CA nằm ở đường dẫn có dấu tiếng Việt."""

import certifi

from bdscrawler import http


def test_ascii_path_used_as_is(monkeypatch, tmp_path):
    pem = tmp_path / "cacert.pem"
    pem.write_text("CERT")
    monkeypatch.delenv("BDS_CA_BUNDLE", raising=False)
    monkeypatch.setattr(certifi, "where", lambda: str(pem))
    assert http.ca_bundle_path() == str(pem)


def test_non_ascii_path_is_copied_to_ascii_dir(monkeypatch, tmp_path):
    src_dir = tmp_path / "Khu vực phía Nam" / ".venv"
    src_dir.mkdir(parents=True)
    pem = src_dir / "cacert.pem"
    pem.write_text("CERT-DATA")
    ascii_tmp = tmp_path / "tmp_ascii"
    ascii_tmp.mkdir()
    monkeypatch.delenv("BDS_CA_BUNDLE", raising=False)
    monkeypatch.setattr(certifi, "where", lambda: str(pem))
    monkeypatch.setattr(http.tempfile, "gettempdir", lambda: str(ascii_tmp))

    result = http.ca_bundle_path()
    assert result.isascii()
    assert open(result, encoding="utf-8").read() == "CERT-DATA"


def test_env_override(monkeypatch):
    monkeypatch.setenv("BDS_CA_BUNDLE", r"C:\certs\my.pem")
    assert http.ca_bundle_path() == r"C:\certs\my.pem"


def test_curl_fetcher_uses_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv("BDS_CA_BUNDLE", str(tmp_path / "x.pem"))
    monkeypatch.setenv("BDS_CACHE_DIR", str(tmp_path / "cache"))
    fetcher = http.CurlFetcher("https://batdongsan.com.vn")
    assert fetcher.session.verify == str(tmp_path / "x.pem")
