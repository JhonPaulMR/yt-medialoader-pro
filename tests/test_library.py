import json

from medialoader.library import (
    DOWNLOADED,
    LOCAL,
    MISSING_FILE,
    NEW,
    UNAVAILABLE,
    LibraryIndex,
    read_archive_ids,
)


def make_library(tmp_path, files=(), archive=(), index=None):
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    if archive:
        (tmp_path / ".archive.txt").write_text("".join(f"youtube {i}\n" for i in archive), encoding="utf-8")
    if index is not None:
        (tmp_path / ".library.json").write_text(json.dumps(index), encoding="utf-8")
    return LibraryIndex(tmp_path).load()


def entry(video_id, title, **extra):
    return {"id": video_id, "title": title, "position": 1, **extra}


def test_read_archive_ids_ignores_bad_lines(tmp_path):
    path = tmp_path / ".archive.txt"
    path.write_text("youtube abc\n\nlixo\nyoutube def\n", encoding="utf-8")
    assert read_archive_ids(path) == {"abc", "def"}
    assert read_archive_ids(tmp_path / "nao-existe.txt") == set()


def test_scan_is_recursive_and_ignores_images(tmp_path):
    lib = make_library(tmp_path, ["a.m4a", "sub/b.mp3", "capa.jpg", ".oculta/c.m4a"])
    assert lib.files == ["a.m4a", "sub/b.mp3"]


def test_status_new_downloaded_local_unavailable(tmp_path):
    lib = make_library(tmp_path, ["Numb.m4a", "AC⧸DC ｜ Back In Black.m4a"], archive=["arch1"])
    assert lib.status_for(entry("arch1", "Qualquer coisa")) == DOWNLOADED
    assert lib.status_for(entry("x1", "Numb")) == LOCAL
    assert lib.status_for(entry("x2", "AC/DC | Back In Black")) == LOCAL
    assert lib.status_for(entry("x3", "Música que não existe")) == NEW
    assert lib.status_for(entry("x4", "[Private video]")) == UNAVAILABLE


def test_partial_match_covers_renamed_files(tmp_path):
    lib = make_library(tmp_path, ["Animal I Have Become.m4a"])
    title = "Three Days Grace - Animal I Have Become (Official Video)"
    assert lib.local_match(title) == "Animal I Have Become.m4a"


def test_generic_file_names_do_not_match_everything(tmp_path):
    lib = make_library(tmp_path, ["OFFICIAL VIDEO.m4a", "Lyric Video.m4a"])
    assert lib.status_for(entry("n1", "Banda Nova - Música Inédita (Official Video)")) == NEW
    assert lib.status_for(entry("n2", "Outra Música (Lyric Video)")) == NEW


def test_index_marks_missing_file(tmp_path):
    lib = make_library(tmp_path, ["existe.m4a"], index={
        "a": {"file": "existe.m4a", "title": "A"},
        "b": {"file": "apagado.m4a", "title": "B"},
    })
    assert lib.status_for(entry("a", "A")) == DOWNLOADED
    assert lib.status_for(entry("b", "B")) == MISSING_FILE


def test_record_download_and_rename_update_index(tmp_path):
    lib = make_library(tmp_path, ["Artista - Música.m4a"])
    lib.record_download("vid", str(tmp_path / "Artista - Música.m4a"), "Artista - Música")
    assert lib.index["vid"]["file"] == "Artista - Música.m4a"
    assert "vid" in lib.archive_ids

    (tmp_path / "Artista - Música.m4a").rename(tmp_path / "Música.m4a")
    lib.rename_files([("Artista - Música.m4a", "Música.m4a")])
    saved = json.loads((tmp_path / ".library.json").read_text(encoding="utf-8"))
    assert saved["vid"]["file"] == "Música.m4a"
    assert lib.status_for(entry("vid", "Artista - Música")) == DOWNLOADED


def test_register_local_writes_archive(tmp_path):
    lib = make_library(tmp_path, ["Numb.m4a"], archive=["old"])
    added = lib.register_local([entry("n1", "Numb"), entry("n2", "Não existe")])
    assert added == 1
    assert read_archive_ids(tmp_path / ".archive.txt") == {"old", "n1"}
    assert LibraryIndex(tmp_path).load().status_for(entry("n1", "Numb")) == DOWNLOADED


def test_write_m3u_in_playlist_order(tmp_path):
    lib = make_library(tmp_path, ["B.m4a", "Alpha Song.m4a"])
    entries = [
        {"id": "2", "title": "B", "position": 2, "duration": 100},
        {"id": "1", "title": "Alpha Song", "position": 1, "duration": 200},
        {"id": "3", "title": "Ausente", "position": 3},
    ]
    path = lib.write_m3u("Minha: Lista", entries)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert path.name == "Minha Lista.m3u8"
    assert lines == ["#EXTM3U", "#EXTINF:200,Alpha Song", "Alpha Song.m4a", "#EXTINF:100,B", "B.m4a"]


def test_partial_match_rejects_real_world_false_positives(tmp_path):
    # Casos vistos ao comparar a playlist "Popular Music Videos" com a pasta real.
    lib = make_library(tmp_path, ["Stronger.m4a", "Alejandro (Metal remix).m4a", "Bring Me The Horizon.m4a"])
    assert lib.local_match('Tom MacDonald - "Stronger Version"') is None
    assert lib.local_match("Pharrell Williams, Swae Lee, Rauw Alejandro - Airplane Tickets (Official Video)") is None
    assert lib.local_match("Bring Me The Horizon - 'Kingslayer' ft. BABYMETAL (Live In Tokyo)") is None


def test_partial_match_accepts_track_numbers_and_featuring(tmp_path):
    lib = make_library(tmp_path, ["Casualty.m4a", "03 A Alegria do Senhor.m4a", "Numb.m4a"])
    assert lib.local_match("Li Rye - Casualty (feat. EBK Jaaybo) [Official Music Video]") == "Casualty.m4a"
    assert lib.local_match("A Alegria do Senhor") == "03 A Alegria do Senhor.m4a"
    assert lib.local_match("Numb - Ao Vivo") == "Numb.m4a"
