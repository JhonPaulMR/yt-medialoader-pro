"""Serviço de download em lote (roda numa thread; fala com a UI por eventos)."""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadCancelled

from .config import AUDIO_FORMATS, FROZEN, IMAGE_EXTS, NAME_TEMPLATES
from .errors import friendly_error

SUCCESS = "success"
SKIPPED = "skipped"
FAILED = "failed"
CANCELLED = "cancelled"

INSTALL_COMMANDS = {
    "deno": "winget install DenoLand.Deno",
    "ffmpeg": "winget install Gyan.FFmpeg",
    "ytdlp": ('Use o botão "Atualizar yt-dlp" em Diagnóstico → Ambiente' if FROZEN
              else f'"{sys.executable}" -m pip install -U "yt-dlp[default]"'),
}


def get_ytdlp_version():
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:
        return getattr(yt_dlp, "__version__", "?")


# ============================================================
# AMBIENTE
# ============================================================
@dataclass
class EnvStatus:
    ytdlp_version: str
    ffmpeg: str = None
    deno: str = None
    deno_version: str = ""
    ejs: bool = False

    def blocking_problems(self):
        problems = []
        if not self.deno:
            problems.append(
                "O Deno não foi encontrado no PATH. O yt-dlp precisa de um runtime "
                "JavaScript para resolver os desafios do YouTube.\n"
                f"Instale com: {INSTALL_COMMANDS['deno']} (e reabra o app)."
            )
        if not self.ejs:
            problems.append(
                "O pacote yt-dlp-ejs não está instalado no mesmo Python do app.\n"
                f"Execute: {INSTALL_COMMANDS['ytdlp']}"
            )
        return problems


_env_cache = None
_env_lock = threading.Lock()


def check_environment(force=False):
    """Detecta FFmpeg, Deno e yt-dlp-ejs. Lento (subprocess): use fora da UI."""
    global _env_cache
    with _env_lock:
        if _env_cache is not None and not force:
            return _env_cache
        status = EnvStatus(
            ytdlp_version=get_ytdlp_version(),
            ffmpeg=shutil.which("ffmpeg"),
            deno=shutil.which("deno"),
            ejs=importlib.util.find_spec("yt_dlp_ejs") is not None,
        )
        if status.deno:
            try:
                out = subprocess.run(
                    [status.deno, "--version"], capture_output=True, text=True,
                    timeout=10, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                ).stdout.strip().splitlines()
                status.deno_version = out[0] if out else ""
            except Exception:
                status.deno_version = "versão não identificada"
        _env_cache = status
        return status


def update_ytdlp():
    """pip install -U yt-dlp[default] no Python atual (ou wheels, no executável). Retorna (ok, saída)."""
    if FROZEN:
        from .updater import update_from_wheels
        return update_from_wheels()
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "yt-dlp[default]"],
        capture_output=True, text=True, timeout=600, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output.strip()


# ============================================================
# OPÇÕES DO YT-DLP
# ============================================================
def build_ydl_opts(settings, cookie_opts, folder, *, use_subfolder=False,
                   progress_hook=None, postprocessor_hook=None, logger=None):
    _, codec, quality, format_selector = AUDIO_FORMATS[settings.audio_format]
    template = NAME_TEMPLATES[settings.name_template][1]
    if use_subfolder:
        template = "%(playlist_title)s/" + template

    postprocessors = []
    if settings.sponsorblock:
        postprocessors.append({
            "key": "SponsorBlock",
            "categories": {"music_offtopic"},
            "when": "after_filter",
        })
    postprocessors += [
        {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
        {"key": "FFmpegExtractAudio", "preferredcodec": codec, "preferredquality": quality},
    ]
    if settings.sponsorblock:
        # ModifyChapters precisa rodar antes do FFmpegMetadata.
        postprocessors.append({
            "key": "ModifyChapters",
            "remove_sponsor_segments": {"music_offtopic"},
        })
    postprocessors += [
        {"key": "FFmpegMetadata", "add_metadata": True},
        {"key": "EmbedThumbnail", "already_have_thumbnail": False},
    ]

    opts = {
        "format": format_selector,
        # O YouTube exige resolver desafios JavaScript; Deno é o runtime
        # recomendado pelo yt-dlp.
        "js_runtimes": {"deno": {}},
        "outtmpl": os.path.join(str(folder), template + ".%(ext)s"),
        "download_archive": os.path.join(str(folder), ".archive.txt"),
        "ignoreerrors": False,
        "noplaylist": True,
        "continuedl": True,
        "retries": 5,
        "fragment_retries": 5,
        "windowsfilenames": True,
        "writethumbnail": True,
        "postprocessors": postprocessors,
        "quiet": True,
        "noprogress": True,
        "no_warnings": False,
    }
    if progress_hook:
        opts["progress_hooks"] = [progress_hook]
    if postprocessor_hook:
        opts["postprocessor_hooks"] = [postprocessor_hook]
    if logger:
        opts["logger"] = logger
    try:
        limit = float(str(getattr(settings, "speed_limit_mb", "") or 0).replace(",", "."))
    except ValueError:
        limit = 0
    if limit > 0:
        opts["ratelimit"] = int(limit * 1024 * 1024)
    opts.update(cookie_opts or {})
    return opts


class YtDlpLogger:
    """Intercepta os logs do yt-dlp e manda para a UI com um nível."""

    _NOISE = ("ETA", "Destination", "100%", "has already been recorded")

    def __init__(self, emit):
        self.emit = emit

    def debug(self, msg):
        if not msg or msg.startswith("[debug]"):
            return
        # A barra de progresso já mostra o andamento.
        if msg.startswith("[download]") and any(n in msg for n in self._NOISE):
            return
        self.emit(msg, "info")

    def info(self, msg):
        self.debug(msg)

    def warning(self, msg):
        if msg:
            self.emit(f"AVISO: {msg}", "warning")

    def error(self, msg):
        if msg:
            self.emit(f"ERRO: {msg}", "error")


# ============================================================
# SERVIÇO
# ============================================================
@dataclass
class DownloadItem:
    id: str
    url: str
    title: str
    position: int
    duration: float = None

    @classmethod
    def from_entry(cls, entry):
        return cls(entry["id"], entry["url"], entry["title"], entry["position"], entry.get("duration"))


@dataclass
class ItemResult:
    item: DownloadItem
    status: str
    filepath: str = None
    error: str = ""
    hint: str = None


@dataclass
class BatchSummary:
    results: list = field(default_factory=list)
    total: int = 0
    cancelled: bool = False
    elapsed: float = 0.0
    m3u_path: str = None
    fatal_error: str = None

    def count(self, status):
        return sum(1 for r in self.results if r.status == status)

    @property
    def failures(self):
        return [r for r in self.results if r.status == FAILED]


def _human_bytes(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _human_eta(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    minutes, secs = divmod(max(seconds, 0), 60)
    return f"{minutes}:{secs:02d}"


_STAGE_NAMES = {
    "SponsorBlock": "Consultando SponsorBlock",
    "FFmpegThumbnailsConvertor": "Convertendo capa",
    "FFmpegExtractAudio": "Extraindo áudio (FFmpeg)",
    "ModifyChapters": "Removendo trechos sem música",
    "FFmpegMetadata": "Gravando metadados",
    "EmbedThumbnail": "Embutindo capa",
    "MoveFiles": "Movendo arquivo",
}


class DownloadService:
    """
    Executa um lote com UMA instância do YoutubeDL (os cookies são lidos
    uma vez só). `emit(event, **data)` é chamado da thread de trabalho.
    """

    def __init__(self, settings, cookie_config, library, emit):
        self.settings = settings
        self.cookie_config = cookie_config
        self.library = library
        self.emit = emit
        self.stop_now = threading.Event()
        self.stop_after_current = threading.Event()
        self._last_progress_emit = 0.0
        self._last_filepath = None

    # ---------------- controle ----------------
    def request_stop(self, immediately=False):
        self.stop_after_current.set()
        if immediately:
            self.stop_now.set()

    @property
    def stopping(self):
        return self.stop_after_current.is_set() or self.stop_now.is_set()

    # ---------------- hooks ----------------
    def _log(self, message, level="info"):
        self.emit("log", message=message, level=level)

    def _progress_hook(self, data):
        if self.stop_now.is_set():
            raise DownloadCancelled("Interrompido pelo usuário.")

        status = data.get("status")
        if data.get("filename"):
            self._last_filepath = data["filename"]

        if status == "downloading":
            now = time.monotonic()
            if now - self._last_progress_emit < 0.15:
                return
            self._last_progress_emit = now

            done = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            if total:
                percent = done / total * 100
            else:
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(data.get("_percent_str", "")))
                percent = float(match.group(1)) if match else 0.0

            speed = data.get("speed")
            self.emit(
                "progress",
                percent=max(0.0, min(100.0, percent)),
                speed=f"{_human_bytes(speed)}/s" if speed else "",
                eta=_human_eta(data.get("eta")) if data.get("eta") is not None else "",
                size=_human_bytes(total) if total else "",
            )
        elif status == "finished":
            self.emit("progress", percent=100.0, speed="", eta="", size="")
            self.emit("stage", text="Download concluído, pós-processando…")

    def _postprocessor_hook(self, data):
        name = data.get("postprocessor", "")
        if data.get("status") == "started":
            self.emit("stage", text=_STAGE_NAMES.get(name, name) + "…")
        elif data.get("status") == "finished":
            path = (data.get("info_dict") or {}).get("filepath")
            if path:
                self._last_filepath = path

    # ---------------- execução ----------------
    def _final_path(self, info):
        candidates = []
        for download in (info or {}).get("requested_downloads") or []:
            candidates.append(download.get("filepath"))
        candidates += [(info or {}).get("filepath"), self._last_filepath]
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        return None

    def _cleanup_thumbnail(self, audio_path):
        """Remove a capa que sobrou quando o EmbedThumbnail falhou."""
        stem = Path(audio_path).with_suffix("")
        for ext in IMAGE_EXTS:
            image = stem.with_name(stem.name + ext)
            if image.is_file():
                try:
                    image.unlink()
                    self._log(f"Capa não embutida; arquivo solto removido: {image.name}", "warning")
                except OSError:
                    pass

    def run(self, items, playlist_title=None, playlist_entries=None):
        """Bloqueante. Chame numa thread."""
        started = time.monotonic()
        summary = BatchSummary(total=len(items))
        folder = Path(self.settings.download_folder)
        use_subfolder = bool(self.settings.playlist_subfolder and playlist_title)

        try:
            folder.mkdir(parents=True, exist_ok=True)
            cookie_opts = self.cookie_config.build_opts()
            if self.cookie_config.mode != "none":
                self._log(f"Cookies: {self.cookie_config.describe()}")

            opts = build_ydl_opts(
                self.settings, cookie_opts, folder,
                use_subfolder=use_subfolder,
                progress_hook=self._progress_hook,
                postprocessor_hook=self._postprocessor_hook,
                logger=YtDlpLogger(self._log),
            )
            self._log(f"Iniciando lote com {len(items)} item(ns) em {folder}.", "info")

            with yt_dlp.YoutubeDL(opts) as ydl:
                for index, item in enumerate(items, 1):
                    if self.stopping:
                        summary.cancelled = True
                        break

                    self.emit("item_start", index=index, total=len(items), item=item)

                    if item.id in self.library.archive_ids:
                        result = ItemResult(item, SKIPPED, error="Já está no histórico (.archive.txt).")
                        summary.results.append(result)
                        self._log(f"[{item.position}] {item.title}: já baixado, pulando.", "muted")
                        self.emit("item_done", index=index, total=len(items), result=result)
                        continue

                    self._last_filepath = None
                    # Sem a chave "playlist" o yt-dlp zera o playlist_index
                    # (usado no template "NNN - Título").
                    extra = {
                        "playlist": playlist_title or "MediaLoader",
                        "playlist_title": playlist_title or "MediaLoader",
                        "playlist_index": item.position,
                    }
                    try:
                        info = ydl.extract_info(item.url, download=True, extra_info=extra)
                        path = self._final_path(info)
                        if path:
                            self.library.record_download(item.id, path, item.title)
                            self._cleanup_thumbnail(path)
                        else:
                            self.library.archive_ids.add(item.id)
                        result = ItemResult(item, SUCCESS, filepath=path)
                        self._log(f"✔ [{item.position}] {item.title}", "success")
                    except DownloadCancelled:
                        result = ItemResult(item, CANCELLED, error="Interrompido.")
                        summary.cancelled = True
                    except Exception as exc:
                        text = str(exc)
                        result = ItemResult(item, FAILED, error=text, hint=friendly_error(text))
                        self._log(f"✖ [{item.position}] {item.title}: {text}", "error")
                        if result.hint:
                            self._log(f"   ↳ {result.hint}", "warning")

                    summary.results.append(result)
                    self.emit("item_done", index=index, total=len(items), result=result)
                    if result.status == CANCELLED:
                        break

            if self.settings.write_m3u and playlist_entries:
                path = self.library.write_m3u(playlist_title or "playlist", playlist_entries)
                if path:
                    summary.m3u_path = str(path)
                    self._log(f"Playlist M3U gerada: {path.name}", "success")

        except Exception as exc:
            summary.fatal_error = friendly_error(str(exc)) or str(exc)
            self._log(f"ERRO GRAVE no lote: {exc}", "error")

        summary.elapsed = time.monotonic() - started
        self.emit("finished", summary=summary)
        return summary
