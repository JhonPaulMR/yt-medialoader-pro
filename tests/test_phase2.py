import shutil
import subprocess

import pytest

from medialoader.config import Settings
from medialoader.downloader import build_ydl_opts
from medialoader.library import LibraryIndex
from medialoader.maintenance import find_duplicates, find_orphans
from medialoader.matching import TitleMatcher
from medialoader.metadata import read_tags
from medialoader.notify import is_newer
from medialoader.playlist import PlaylistResult
from medialoader.playlists import PlaylistStore
from medialoader.rename_rules import (
    FROM_METADATA,
    STRIP_TAGS,
    apply_regex_name,
    is_generic_name,
    is_numbered_copy,
    name_from_title,
    strip_tags,
)


# ---------------- matching ----------------
def test_title_matcher_matches_like_library():
    matcher = TitleMatcher(["Numb.m4a", "Rock/Casualty.m4a", "OFFICIAL VIDEO.m4a"])
    assert matcher.match("Linkin Park - Numb (Official Video)") == "Numb.m4a"
    assert matcher.match("Li Rye - Casualty (feat. X)") == "Rock/Casualty.m4a"
    assert matcher.match("Outra Banda - Outra Música (Official Video)") is None
    assert matcher.match_file("pasta/Numb.mp3") == "Numb.m4a"


# ---------------- playlists salvas ----------------
def test_playlist_store_roundtrip_and_counts(tmp_path):
    path = tmp_path / "playlists.json"
    store = PlaylistStore.load(path)
    store.add("https://yt/p1", "Rock")
    entries = [{"id": "a", "title": "A", "position": 1, "status": "new", "url": "u"},
               {"id": "b", "title": "B", "position": 2, "status": "downloaded", "url": "u"}]
    store.update_from_result(PlaylistResult("https://yt/p1", "Rock 2", True, entries))
    loaded = PlaylistStore.load(path)
    record = loaded.get("https://yt/p1")
    assert record["title"] == "Rock 2"
    assert record["counts"] == {"new": 1, "downloaded": 1, "total": 2}
    assert "status" not in record["entries"][0]
    assert [e["id"] for e in loaded.all_entries()] == ["a", "b"]
    loaded.remove("https://yt/p1")
    assert PlaylistStore.load(path).items == []


def test_playlist_store_ignores_corrupt_file(tmp_path):
    path = tmp_path / "playlists.json"
    path.write_text("lixo", encoding="utf-8")
    assert PlaylistStore.load(path).items == []


# ---------------- renomeador ----------------
@pytest.mark.parametrize("stem, expected", [
    ("Numb (Official Video) [HD]", "Numb"),
    ("Song - Official Video", "Song"),
    ("Song (Ao Vivo) (Lyric Video)", "Song (Ao Vivo)"),
    ("Artist - Song (feat. X) (Audio)", "Artist - Song (feat. X)"),
    ("(Sic) (Audio)", "(Sic)"),
    ("OFFICIAL VIDEO", ""),
])
def test_strip_tags(stem, expected):
    assert strip_tags(stem) == expected


@pytest.mark.parametrize("name, generic", [
    ("OFFICIAL VIDEO.m4a", True), ("OFFICIAL VIDEO (1).m4a", True), ("[Clipe Oficial].m4a", True),
    ("Lyric Video.m4a", True), ("(Sic) (Audio).m4a", False), ("502 (Remastered).m4a", False),
    ("Numb.m4a", False),
])
def test_is_generic_name(name, generic):
    assert is_generic_name(name) is generic


def test_numbered_copy_and_name_from_title():
    assert is_numbered_copy("Linkin Park (14).m4a")
    assert not is_numbered_copy("Linkin Park (Meteora).m4a")
    assert name_from_title("Linkin Park (14).m4a",
                           "Papercut [Official HD Music Video] - Linkin Park") == "Papercut - Linkin Park.m4a"
    assert name_from_title("x.m4a", "") == "x.m4a"
    assert apply_regex_name("Numb (Official Video).m4a", STRIP_TAGS) == "Numb.m4a"
    assert apply_regex_name("Numb.m4a", FROM_METADATA) == "Numb.m4a"  # metadado é lido pela tela


@pytest.fixture
def tagged_m4a(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg não instalado")

    def make(name, title, seconds=2):
        path = tmp_path / name
        subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                        "-t", str(seconds), "-c:a", "aac", "-metadata", f"title={title}",
                        "-metadata", "artist=Banda", str(path)], check=True)
        return path
    return make


def test_read_tags_real_m4a(tagged_m4a):
    path = tagged_m4a("OFFICIAL VIDEO.m4a", "Música Real (Official Video)")
    tags = read_tags(path)
    assert tags["title"] == "Música Real (Official Video)"
    assert tags["artist"] == "Banda"
    assert tags["duration"] == pytest.approx(2, abs=0.2)


def test_duplicates_by_metadata_and_duration(tagged_m4a, tmp_path):
    tagged_m4a("Linkin Park (1).m4a", "Numb - Linkin Park (Official Video)", 3)
    tagged_m4a("Numb - Linkin Park.m4a", "Numb - Linkin Park", 3)
    tagged_m4a("Numb (Ao Vivo).m4a", "Numb - Linkin Park", 8)          # duração diferente: outra versão
    tagged_m4a("Numb (Rock Cover).m4a", "Numb (Rock Cover)", 3)        # cover: outra música
    library = LibraryIndex(tmp_path).load()
    groups = find_duplicates(library)
    assert len(groups) == 1
    assert sorted(i["rel"] for i in groups[0]) == ["Linkin Park (1).m4a", "Numb - Linkin Park.m4a"]


def test_orphans(tmp_path):
    for name in ("Numb.m4a", "Sobrando.m4a"):
        (tmp_path / name).write_bytes(b"x")
    library = LibraryIndex(tmp_path).load()
    orphans = find_orphans(library, [{"id": "1", "title": "Linkin Park - Numb"}])
    assert [o["rel"] for o in orphans] == ["Sobrando.m4a"]


# ---------------- qualidade de vida ----------------
def test_speed_limit_option(tmp_path):
    assert "ratelimit" not in build_ydl_opts(Settings(), {}, tmp_path)
    assert build_ydl_opts(Settings(speed_limit_mb="2,5"), {}, tmp_path)["ratelimit"] == int(2.5 * 1024 * 1024)
    assert "ratelimit" not in build_ydl_opts(Settings(speed_limit_mb="abc"), {}, tmp_path)


def test_version_compare():
    assert is_newer("2026.9.1", "2026.08.19")
    assert not is_newer("2026.8.19", "2026.08.19")
    assert is_newer("2026.08.19.1", "2026.08.19")
