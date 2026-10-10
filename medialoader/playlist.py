"""Leitura de playlists (ou vídeo único) sem baixar nada."""

from dataclasses import dataclass, field

import yt_dlp

from .utils import playlist_position


@dataclass
class PlaylistResult:
    url: str
    title: str
    is_playlist: bool
    entries: list = field(default_factory=list)


def _video_url(entry):
    video_id = entry.get("id")
    url = entry.get("url") or entry.get("webpage_url") or ""
    if video_id and (not url.startswith("http") or "watch?v=" not in url):
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


def normalize_entry(entry, fallback_index):
    return {
        "id": entry.get("id") or "",
        "title": entry.get("title") or "Título desconhecido",
        "uploader": entry.get("uploader") or entry.get("channel") or "",
        "duration": entry.get("duration"),
        "availability": entry.get("availability"),
        "position": playlist_position(entry, fallback_index),
        "url": _video_url(entry),
    }


def fetch_entries(url, extra_opts=None, logger=None):
    """Lê os metadados da URL. Aceita playlist e vídeo único."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
        "noplaylist": False,
        "skip_download": True,
        "js_runtimes": {"deno": {}},
    }
    if logger is not None:
        opts["logger"] = logger
    opts.update(extra_opts or {})

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Não foi possível ler essa URL. Confira o link e tente de novo.")

    if "entries" not in info:
        # Vídeo único.
        entry = normalize_entry(info, 0)
        if not entry["id"]:
            raise ValueError("A URL não aponta para um vídeo ou playlist do YouTube.")
        return PlaylistResult(url, info.get("title") or "Vídeo", False, [entry])

    # A posição de fallback conta também as entradas None (vídeos que o
    # yt-dlp não conseguiu ler), para casar com a numeração da playlist.
    entries = [
        normalize_entry(entry, index)
        for index, entry in enumerate(info.get("entries") or [])
        if entry and entry.get("id")
    ]
    if not entries:
        raise ValueError("Nenhum vídeo utilizável foi encontrado na playlist.")
    return PlaylistResult(url, info.get("title") or "Playlist", True, entries)
