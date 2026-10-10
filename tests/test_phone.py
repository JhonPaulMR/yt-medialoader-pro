import threading

import pytest

from medialoader.library import LibraryIndex
from medialoader.phone import (
    MISSING,
    ON_PHONE,
    ONLY_PC,
    PhoneClient,
    PhoneConfig,
    UploadCancelled,
    compare_entries,
    compare_files,
    m3u_for_phone,
)

pyftpdlib = pytest.importorskip("pyftpdlib")
from pyftpdlib.authorizers import DummyAuthorizer  # noqa: E402
from pyftpdlib.handlers import FTPHandler  # noqa: E402
from pyftpdlib.servers import ThreadedFTPServer  # noqa: E402


@pytest.fixture
def phone(tmp_path):
    """Servidor FTP local fazendo o papel do celular (pasta /Music já com músicas)."""
    root = tmp_path / "celular"
    music = root / "Music"
    (music / "Rock").mkdir(parents=True)
    (music / "Numb.m4a").write_bytes(b"x")
    (music / "Rock" / "AC⧸DC ｜ Back In Black.m4a").write_bytes(b"x")
    (music / "capa.jpg").write_bytes(b"x")

    authorizer = DummyAuthorizer()
    authorizer.add_anonymous(str(root), perm="elradfmwMT")
    handler = type("Handler", (FTPHandler,), {"authorizer": authorizer, "encoding": "utf-8"})
    server = ThreadedFTPServer(("127.0.0.1", 0), handler)
    port = server.address[1]
    thread = threading.Thread(target=server.serve_forever, kwargs={"timeout": 0.2}, daemon=True)
    thread.start()
    yield PhoneConfig("127.0.0.1", port, folder="/Music"), music
    server.close_all()


def test_list_audio_recursive_and_unicode(phone):
    config, _ = phone
    with PhoneClient(config) as client:
        assert client.list_audio() == ["Numb.m4a", "Rock/AC⧸DC ｜ Back In Black.m4a"]


def test_upload_uses_part_then_rename_and_creates_folders(phone, tmp_path):
    config, music = phone
    local = tmp_path / "Nova Música.m4a"
    local.write_bytes(b"a" * 200_000)
    seen = []
    with PhoneClient(config) as client:
        client.upload(str(local), "Playlist X/Nova Música.m4a", progress=seen.append)
    assert (music / "Playlist X" / "Nova Música.m4a").read_bytes() == local.read_bytes()
    assert not list(music.rglob("*.part"))
    assert seen and seen[-1] == pytest.approx(1.0)


def test_upload_cancel_leaves_nothing(phone, tmp_path):
    config, music = phone
    local = tmp_path / "grande.m4a"
    local.write_bytes(b"a" * 1_000_000)
    cancel = threading.Event()
    with PhoneClient(config) as client:
        with pytest.raises(UploadCancelled):
            client.upload(str(local), "grande.m4a", progress=lambda _f: cancel.set(), cancel=cancel)
    assert not (music / "grande.m4a").exists()


def test_manifest_roundtrip(phone):
    config, music = phone
    with PhoneClient(config) as client:
        assert client.read_manifest() == {"ids": {}, "files": {}}
        client.write_manifest({"ids": {"abc": "Numb.m4a"}, "files": {}})
        assert client.read_manifest()["ids"] == {"abc": "Numb.m4a"}
    assert (music / ".medialoader.json").exists()


def test_bad_host_gives_friendly_message():
    config = PhoneConfig("127.0.0.1", 1, folder="/Music")
    with pytest.raises(ConnectionError) as info:
        PhoneClient(config, timeout=2).connect()
    assert "servidor FTP" in str(info.value) or "não respondeu" in str(info.value)


def test_compare_entries_uses_manifest_title_and_local(tmp_path):
    folder = tmp_path / "pc"
    folder.mkdir()
    (folder / "Só No PC.m4a").write_bytes(b"x")
    library = LibraryIndex(folder).load()
    phone_files = ["Numb.m4a", "renomeado no celular.m4a"]
    manifest = {"ids": {"id-man": "renomeado no celular.m4a"}, "files": {}}
    entries = [
        {"id": "id-num", "title": "Linkin Park - Numb (Official Video)", "position": 1},
        {"id": "id-man", "title": "Título que não bate", "position": 2},
        {"id": "id-pc", "title": "Só No PC", "position": 3},
        {"id": "id-nada", "title": "Inédita", "position": 4},
    ]
    status = {i["entry"]["id"]: i["status"] for i in compare_entries(entries, phone_files, manifest, library)}
    assert status == {"id-num": ON_PHONE, "id-man": ON_PHONE, "id-pc": ONLY_PC, "id-nada": MISSING}


def test_compare_files_and_m3u():
    items = compare_files(["Numb.m4a", "Sub/Nova.m4a"], ["Numb (1).m4a"], {"ids": {}, "files": {}})
    assert [i["status"] for i in items] == [ON_PHONE, ONLY_PC]

    text = m3u_for_phone(
        [{"title": "B", "position": 2, "duration": 10}, {"title": "A", "position": 1}],
        lambda e: {"A": "a.m4a", "B": "b.m4a"}[e["title"]])
    assert text.splitlines() == ["#EXTM3U", "#EXTINF:-1,A", "a.m4a", "#EXTINF:10,B", "b.m4a"]
