import os
import time

import pytest

from medialoader import cookies as C
from medialoader.errors import friendly_error

FUTURE = int(time.time()) + 86400 * 365
HEADER = "# Netscape HTTP Cookie File\n"


def cookie_line(domain, name, value="v", expires=FUTURE):
    return f"{domain}\tTRUE\t/\tTRUE\t{expires}\t{name}\t{value}\n"


@pytest.mark.parametrize("message, needle", [
    ("Could not copy Chrome cookie database. See https://...", "Feche o navegador"),
    ("Failed to decrypt with DPAPI. See https://...", "App-Bound"),
    ("could not find chrome cookies database in \"C:\\x\"", "não encontrado"),
    ("Sign in to confirm you're not a bot", "robô"),
    ("ERROR: [youtube] abc: Signature solving failed", "Deno"),
    ("HTTP Error 403: Forbidden", "403"),
    ("ERROR: Private video. Sign in", "privado"),
])
def test_friendly_error_known_messages(message, needle):
    assert needle in friendly_error(message)


def test_friendly_error_unknown_returns_none():
    assert friendly_error("algo totalmente novo") is None


def test_build_opts_modes(tmp_path):
    assert C.CookieConfig("none").build_opts() == {}
    assert C.CookieConfig("browser", "firefox", " Perfil ").build_opts() == {
        "cookiesfrombrowser": ("firefox", "Perfil", None, None)}
    assert C.CookieConfig("browser", "chrome").build_opts()["cookiesfrombrowser"][1] is None

    with pytest.raises(FileNotFoundError):
        C.CookieConfig("file", file=str(tmp_path / "nao.txt")).build_opts()
    path = tmp_path / "c.txt"
    path.write_text(HEADER, encoding="utf-8")
    assert C.CookieConfig("file", file=str(path)).build_opts() == {"cookiefile": str(path)}


def test_validate_cookie_file_logged_in(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(
        HEADER + cookie_line(".youtube.com", "SAPISID") + cookie_line(".youtube.com", "PREF")
        + cookie_line(".example.com", "outro"),
        encoding="utf-8",
    )
    report = C.validate_cookie_file(path)
    assert report.level == C.SUCCESS
    assert report.youtube_count == 2
    assert report.logged_in


def test_validate_cookie_file_without_login(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(HEADER + cookie_line(".youtube.com", "PREF"), encoding="utf-8")
    report = C.validate_cookie_file(path)
    assert report.level == C.WARNING
    assert not report.logged_in


def test_validate_cookie_file_expired_and_stale(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(HEADER + cookie_line(".youtube.com", "SAPISID", expires=1000), encoding="utf-8")
    assert C.validate_cookie_file(path).level == C.DANGER

    path.write_text(HEADER + cookie_line(".youtube.com", "SAPISID"), encoding="utf-8")
    old = time.time() - 86400 * 30
    os.utime(path, (old, old))
    report = C.validate_cookie_file(path)
    assert report.level == C.WARNING
    assert "30 dias" in report.detail


def test_validate_cookie_file_rejects_json_and_missing(tmp_path):
    path = tmp_path / "cookies.json.txt"
    path.write_text('[{"domain": ".youtube.com"}]', encoding="utf-8")
    assert C.validate_cookie_file(path).level == C.DANGER
    assert C.validate_cookie_file(tmp_path / "nao.txt").level == C.DANGER


def test_check_cookies_browser_error_is_translated(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("Failed to decrypt with DPAPI. See https://github.com/yt-dlp/yt-dlp/issues/10927")

    monkeypatch.setattr(C, "load_browser_jar", boom)
    report = C.check_cookies(C.CookieConfig("browser", "chrome"))
    assert report.level == C.DANGER
    assert "Firefox" in report.detail


def test_export_only_youtube_cookies(tmp_path, monkeypatch):
    source = tmp_path / "all.txt"
    source.write_text(
        HEADER + cookie_line(".youtube.com", "SAPISID") + cookie_line(".google.com", "SID")
        + cookie_line(".banco.com.br", "sessao"),
        encoding="utf-8",
    )
    jar = C.YoutubeDLCookieJar(str(source))
    jar.load()
    monkeypatch.setattr(C, "load_browser_jar", lambda *_a, **_k: (jar, []))

    report, path = C.export_youtube_cookies(C.CookieConfig("browser", "firefox"), tmp_path / "out.txt")
    assert path and report.logged_in
    content = open(path, encoding="utf-8").read()
    assert "SAPISID" in content and "SID" in content
    assert "banco.com.br" not in content


def test_resolve_profile_accepts_display_name(tmp_path, monkeypatch):
    user_data = tmp_path / "User Data"
    user_data.mkdir()
    (user_data / "Local State").write_text(
        '{"profile": {"info_cache": {"Default": {"name": "Liptinho Tutoriais"},'
        ' "Profile 1": {"name": "escola.pr.gov.br"}}}}', encoding="utf-8")
    monkeypatch.setattr(C, "user_data_dir", lambda browser: user_data)

    assert C.list_profiles("chrome") == [("Default", "Liptinho Tutoriais"), ("Profile 1", "escola.pr.gov.br")]
    assert C.resolve_profile("chrome", "Liptinho Tutoriais") == "Default"
    assert C.resolve_profile("chrome", "escola.pr.gov.br") == "Profile 1"
    assert C.resolve_profile("chrome", "profile 1") == "Profile 1"
    assert C.resolve_profile("chrome", "") is None
    assert C.CookieConfig("browser", "chrome", "Liptinho Tutoriais").build_opts() == {
        "cookiesfrombrowser": ("chrome", "Default", None, None)}


def test_missing_browser_and_unknown_profile_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "user_data_dir", lambda browser: tmp_path / "nao-existe")
    report = C.check_cookies(C.CookieConfig("browser", "chromium"))
    assert "não está instalado" in report.detail

    user_data = tmp_path / "User Data"
    user_data.mkdir()
    (user_data / "Local State").write_text('{"profile": {"info_cache": {"Default": {"name": "Eu"}}}}',
                                           encoding="utf-8")
    monkeypatch.setattr(C, "user_data_dir", lambda browser: user_data)
    report = C.check_cookies(C.CookieConfig("browser", "chrome", "Outro"))
    assert "Perfis disponíveis" in report.detail and "'Eu' (Default)" in report.detail


def test_cdp_cookies_are_written_as_netscape(tmp_path):
    from medialoader.chrome_export import write_cookie_file

    cdp = [
        {"name": "SAPISID", "value": "abc", "domain": ".youtube.com", "path": "/",
         "expires": FUTURE + 0.5, "secure": True, "httpOnly": False},
        {"name": "YSC", "value": "s", "domain": ".youtube.com", "path": "/",
         "expires": -1, "secure": True, "httpOnly": True},
    ]
    path = write_cookie_file(cdp, tmp_path / "out.txt")
    report = C.validate_cookie_file(path)
    assert report.logged_in and report.youtube_count == 2
