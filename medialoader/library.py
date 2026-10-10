"""Biblioteca local: archive do yt-dlp + índice id→arquivo + arquivos no disco."""

import json
import os
from datetime import datetime
from pathlib import Path

from .config import ARCHIVE_NAME, LIBRARY_NAME, SUPPORTED_MEDIA_EXTS
from .matching import TitleMatcher, title_keys  # noqa: F401 (title_keys é reexportado)
from .utils import clean_filename

NEW = "new"
DOWNLOADED = "downloaded"
LOCAL = "local"
MISSING_FILE = "missing_file"
UNAVAILABLE = "unavailable"

STATUS_LABELS = {
    NEW: "NOVO",
    DOWNLOADED: "BAIXADO",
    LOCAL: "NA PASTA",
    MISSING_FILE: "REMOVIDO",
    UNAVAILABLE: "INDISPONÍVEL",
}

_UNAVAILABLE_TITLES = {"[private video]", "[deleted video]", "[unavailable video]"}
def is_unavailable(entry):
    title = str(entry.get("title") or "").strip().lower()
    return title in _UNAVAILABLE_TITLES or entry.get("availability") == "private"


def read_archive_ids(archive_path):
    """Lê as linhas 'youtube <id>' do archive do yt-dlp."""
    ids = set()
    try:
        with open(archive_path, "r", encoding="utf-8", errors="ignore") as file:
            for line in file:
                parts = line.strip().split()
                if len(parts) >= 2:
                    ids.add(parts[1])
    except FileNotFoundError:
        pass
    return ids


def append_archive_ids(archive_path, ids, extractor="youtube"):
    ids = [i for i in ids if i]
    if not ids:
        return
    with open(archive_path, "a", encoding="utf-8") as file:
        for video_id in ids:
            file.write(f"{extractor} {video_id}\n")


def _same_path(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


class LibraryIndex:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.archive_ids = set()
        self.index = {}
        self.files = []
        self.matcher = TitleMatcher()

    @property
    def archive_path(self):
        return self.folder / ARCHIVE_NAME

    @property
    def index_path(self):
        return self.folder / LIBRARY_NAME

    # ---------------- leitura ----------------
    def load(self):
        self.archive_ids = read_archive_ids(self.archive_path)
        self.index = {}
        try:
            with open(self.index_path, "r", encoding="utf-8") as file:
                raw = json.load(file)
            if isinstance(raw, dict):
                self.index = {
                    str(k): v for k, v in raw.items()
                    if isinstance(v, dict) and v.get("file")
                }
        except (OSError, ValueError):
            pass
        self.scan_disk()
        return self

    def scan_disk(self):
        files = []
        if self.folder.is_dir():
            for root, dirs, names in os.walk(self.folder):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in names:
                    if name.lower().endswith(SUPPORTED_MEDIA_EXTS):
                        rel = os.path.relpath(os.path.join(root, name), self.folder)
                        files.append(Path(rel).as_posix())
        files.sort(key=str.lower)
        self.files = files
        self.matcher = TitleMatcher(files)

    def file_exists(self, rel):
        return (self.folder / rel).is_file()

    # ---------------- correspondência ----------------
    def local_match(self, title):
        """Procura um arquivo do disco cujo nome corresponda ao título."""
        return self.matcher.match(title)

    def path_for(self, entry):
        record = self.index.get(entry.get("id"))
        if record and self.file_exists(record["file"]):
            return record["file"]
        return self.local_match(entry.get("title"))

    def status_for(self, entry):
        if is_unavailable(entry):
            return UNAVAILABLE
        video_id = entry.get("id")
        record = self.index.get(video_id)
        if record:
            return DOWNLOADED if self.file_exists(record["file"]) else MISSING_FILE
        if video_id in self.archive_ids:
            return DOWNLOADED
        if self.local_match(entry.get("title")):
            return LOCAL
        return NEW

    # ---------------- escrita ----------------
    def save_index(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(self.index, file, ensure_ascii=False, indent=1)
        os.replace(tmp, self.index_path)

    def record_download(self, video_id, filepath, title):
        if not video_id or not filepath:
            return
        try:
            rel = Path(os.path.relpath(filepath, self.folder)).as_posix()
        except ValueError:  # outro drive no Windows
            rel = Path(filepath).as_posix()
        self.index[video_id] = {
            "file": rel,
            "title": title or "",
            "added": datetime.now().isoformat(timespec="seconds"),
        }
        self.archive_ids.add(video_id)
        if rel not in self.files:
            self.files.append(rel)
            self.matcher.add(rel)
        self.save_index()

    def rename_files(self, pairs):
        """Atualiza o índice após renomeações [(rel_antigo, rel_novo), ...]."""
        if not pairs:
            return
        changed = False
        for old_rel, new_rel in pairs:
            for record in self.index.values():
                if _same_path(record["file"], old_rel):
                    record["file"] = Path(new_rel).as_posix()
                    changed = True
        if changed:
            self.save_index()
        self.scan_disk()

    def register_local(self, entries):
        """Grava no archive/índice os itens que já existem na pasta."""
        new_ids = []
        for entry in entries:
            video_id = entry.get("id")
            rel = self.local_match(entry.get("title"))
            if not video_id or not rel:
                continue
            self.index[video_id] = {
                "file": rel,
                "title": entry.get("title") or "",
                "added": datetime.now().isoformat(timespec="seconds"),
            }
            if video_id not in self.archive_ids:
                new_ids.append(video_id)
                self.archive_ids.add(video_id)
        self.folder.mkdir(parents=True, exist_ok=True)
        append_archive_ids(self.archive_path, new_ids)
        self.save_index()
        return len(new_ids)

    def write_m3u(self, name, entries):
        """Gera <nome>.m3u8 na ordem da playlist com os arquivos encontrados."""
        lines = ["#EXTM3U"]
        count = 0
        for entry in sorted(entries, key=lambda e: e.get("position") or 0):
            rel = self.path_for(entry)
            if not rel:
                continue
            duration = int(entry.get("duration") or -1)
            lines.append(f"#EXTINF:{duration},{entry.get('title') or ''}")
            lines.append(rel)
            count += 1
        if not count:
            return None
        path = self.folder / f"{clean_filename(name or 'playlist')}.m3u8"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
