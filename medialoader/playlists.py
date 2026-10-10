"""Playlists salvas pelo usuário (data/playlists.json)."""

import json
import os
from datetime import datetime
from pathlib import Path

from .config import PLAYLISTS_FILE

# Campos das entradas guardados em cache (o "status" é recalculado sempre).
_ENTRY_FIELDS = ("id", "title", "uploader", "duration", "availability", "position", "url")


def _now():
    return datetime.now().isoformat(timespec="seconds")


class PlaylistStore:
    def __init__(self, path=PLAYLISTS_FILE):
        self.path = Path(path)
        self.items = []

    @classmethod
    def load(cls, path=PLAYLISTS_FILE):
        store = cls(path)
        try:
            with open(store.path, "r", encoding="utf-8") as file:
                raw = json.load(file)
            if isinstance(raw, list):
                store.items = [p for p in raw if isinstance(p, dict) and p.get("url")]
        except (OSError, ValueError):
            pass
        return store

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(self.items, file, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def get(self, url):
        url = (url or "").strip()
        return next((p for p in self.items if p["url"] == url), None)

    def is_saved(self, url):
        return self.get(url) is not None

    def add(self, url, title=""):
        record = self.get(url)
        if record is None:
            record = {"url": url.strip(), "title": title or url, "added": _now(),
                      "last_checked": None, "counts": {}, "entries": []}
            self.items.append(record)
            self.save()
        return record

    def remove(self, url):
        self.items = [p for p in self.items if p["url"] != url]
        self.save()

    def update_from_result(self, result, save=True):
        """Atualiza título, cache de entradas e contagens a partir de uma leitura."""
        record = self.get(result.url)
        if record is None:
            return None
        record["title"] = result.title
        record["last_checked"] = _now()
        record["entries"] = [{k: e.get(k) for k in _ENTRY_FIELDS} for e in result.entries]
        counts = {}
        for entry in result.entries:
            status = entry.get("status", "new")
            counts[status] = counts.get(status, 0) + 1
        counts["total"] = len(result.entries)
        record["counts"] = counts
        if save:
            self.save()
        return record

    def all_entries(self):
        seen, entries = set(), []
        for record in self.items:
            for entry in record.get("entries") or []:
                if entry.get("id") and entry["id"] not in seen:
                    seen.add(entry["id"])
                    entries.append(dict(entry))
        return entries
