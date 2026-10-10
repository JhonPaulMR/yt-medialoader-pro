import os

import pytest

from medialoader.config import Settings
from medialoader.cookies import CookieConfig
from medialoader.downloader import (
    FAILED,
    SKIPPED,
    SUCCESS,
    DownloadItem,
    DownloadService,
    build_ydl_opts,
)
from medialoader.library import LibraryIndex


def pp_keys(opts):
    return [pp["key"] for pp in opts["postprocessors"]]


@pytest.mark.parametrize("fmt, codec", [("m4a", "m4a"), ("mp3", "mp3"), ("opus", "opus")])
def test_audio_format(tmp_path, fmt, codec):
    opts = build_ydl_opts(Settings(audio_format=fmt), {}, tmp_path)
    extract = next(pp for pp in opts["postprocessors"] if pp["key"] == "FFmpegExtractAudio")
    assert extract["preferredcodec"] == codec


def test_default_postprocessor_order(tmp_path):
    opts = build_ydl_opts(Settings(), {}, tmp_path)
    assert pp_keys(opts) == [
        "FFmpegThumbnailsConvertor", "FFmpegExtractAudio", "FFmpegMetadata", "EmbedThumbnail"]
    assert opts["download_archive"] == os.path.join(str(tmp_path), ".archive.txt")


def test_sponsorblock_adds_postprocessors_before_metadata(tmp_path):
    keys = pp_keys(build_ydl_opts(Settings(sponsorblock=True), {}, tmp_path))
    assert keys[0] == "SponsorBlock"
    assert keys.index("ModifyChapters") < keys.index("FFmpegMetadata")


def test_templates_and_subfolder(tmp_path):
    opts = build_ydl_opts(Settings(name_template="index_title"), {}, tmp_path, use_subfolder=True)
    assert opts["outtmpl"].endswith(os.path.join("", "%(playlist_title)s/%(playlist_index)03d - %(title)s.%(ext)s"))


def test_cookie_opts_are_merged(tmp_path):
    opts = build_ydl_opts(Settings(), {"cookiefile": "c.txt"}, tmp_path)
    assert opts["cookiefile"] == "c.txt"


class FakeYDL:
    """Simula o YoutubeDL: um item baixa, outro falha."""

    def __init__(self, folder):
        self.folder = folder

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True, extra_info=None):
        if "falha" in url:
            raise RuntimeError("ERROR: HTTP Error 403: Forbidden")
        path = self.folder / "Baixada.m4a"
        path.write_bytes(b"audio")
        (self.folder / "Baixada.jpg").write_bytes(b"capa")  # capa que sobrou
        return {"requested_downloads": [{"filepath": str(path)}]}


def test_service_counts_success_skip_and_failure(tmp_path, monkeypatch):
    import medialoader.downloader as D

    monkeypatch.setattr(D.yt_dlp, "YoutubeDL", lambda opts: FakeYDL(tmp_path))
    (tmp_path / ".archive.txt").write_text("youtube ja\n", encoding="utf-8")
    library = LibraryIndex(tmp_path).load()
    events = []
    service = DownloadService(
        Settings(download_folder=str(tmp_path)),
        CookieConfig(),
        library,
        emit=lambda event, **data: events.append((event, data)),
    )
    items = [
        DownloadItem("ja", "u-ja", "Já baixada", 1),
        DownloadItem("ok", "u-ok", "Baixada", 2),
        DownloadItem("bad", "u-falha", "Quebrada", 3),
    ]
    summary = service.run(items)

    assert [r.status for r in summary.results] == [SKIPPED, SUCCESS, FAILED]
    assert "403" in summary.results[2].hint
    assert library.index["ok"]["file"] == "Baixada.m4a"
    assert not (tmp_path / "Baixada.jpg").exists()
    assert events[-1][0] == "finished"


def test_service_stop_after_current(tmp_path, monkeypatch):
    import medialoader.downloader as D

    monkeypatch.setattr(D.yt_dlp, "YoutubeDL", lambda opts: FakeYDL(tmp_path))
    library = LibraryIndex(tmp_path).load()
    service = DownloadService(Settings(download_folder=str(tmp_path)), CookieConfig(), library, emit=lambda *a, **k: None)

    def emit(event, **data):
        if event == "item_done":
            service.request_stop(immediately=False)

    service.emit = emit
    summary = service.run([DownloadItem("a", "u-a", "A", 1), DownloadItem("b", "u-b", "B", 2)])
    assert len(summary.results) == 1
    assert summary.cancelled
