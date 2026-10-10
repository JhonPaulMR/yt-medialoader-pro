"""Leitura de tags (título, artista, duração) dos arquivos de áudio."""

import json
import shutil
import subprocess


def _ffprobe(path):
    exe = shutil.which("ffprobe")
    if not exe:
        return {}
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration:format_tags=title,artist",
             "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=15, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        fmt = json.loads(out or "{}").get("format", {})
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    try:
        duration = float(fmt.get("duration") or 0)
    except ValueError:
        duration = 0.0
    return {"title": tags.get("title", ""), "artist": tags.get("artist", ""), "duration": duration}


def read_tags(path):
    """{"title", "artist", "duration"}; dicionário vazio se não conseguir ler."""
    try:
        import mutagen

        audio = mutagen.File(str(path), easy=True)
    except Exception:
        audio = None
    if audio is None:
        return _ffprobe(path)
    tags = audio.tags or {}

    def first(key):
        try:
            value = tags.get(key)
        except Exception:
            return ""
        return str(value[0]) if value else ""

    return {
        "title": first("title"),
        "artist": first("artist"),
        "duration": float(getattr(audio.info, "length", 0) or 0),
    }
