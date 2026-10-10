import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


# ============================================================
# CAMINHOS
# ============================================================
# Executável (PyInstaller): o programa fica em Arquivos de Programas/
# AppData\Local\Programs (pode não ser gravável) e os dados do usuário em
# %LOCALAPPDATA%\MediaLoader. Como script: tudo ao lado do music.py.
# Nunca depende do diretório atual: abrir por atalho não troca a pasta.
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "MediaLoader"
    DEFAULT_DOWNLOAD_FOLDER = Path.home() / "Music" / "MediaLoader"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    RESOURCE_DIR = APP_DIR
    DATA_DIR = APP_DIR / "data"
    DEFAULT_DOWNLOAD_FOLDER = APP_DIR / "Downloads_Playlist_HQ"

# yt-dlp atualizado pelo próprio app (modo executável) fica aqui e tem
# prioridade sobre o que veio no instalador.
LIB_DIR = DATA_DIR / "lib"
VENDOR_DIR = RESOURCE_DIR / "vendor"
ICON_FILE = RESOURCE_DIR / "assets" / "icon.ico"
README_FILE = RESOURCE_DIR / "README.md"
SETTINGS_FILE = DATA_DIR / "settings.json"
RENAME_HISTORY_FILE = DATA_DIR / "rename_history.json"
PLAYLISTS_FILE = DATA_DIR / "playlists.json"
EXPORTED_COOKIES_FILE = DATA_DIR / "cookies_youtube.txt"
LEGACY_COOKIES_FILE = APP_DIR / "cookies.txt"

ARCHIVE_NAME = ".archive.txt"
LIBRARY_NAME = ".library.json"

ITEMS_PER_PAGE = 50
URL_HISTORY_SIZE = 10
SUPPORTED_MEDIA_EXTS = (".m4a", ".mp3", ".opus", ".webm", ".mp4", ".mkv")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


# ============================================================
# OPÇÕES DE DOWNLOAD
# ============================================================
# chave -> (rótulo, codec do FFmpegExtractAudio, qualidade, seletor de formato)
AUDIO_FORMATS = {
    "m4a": ("M4A (AAC, sem reconversão)", "m4a", "320", "bestaudio[ext=m4a]/bestaudio/best"),
    "mp3": ("MP3 320 kbps", "mp3", "320", "bestaudio/best"),
    "opus": ("Opus (melhor qualidade/tamanho)", "opus", "0", "bestaudio[acodec=opus]/bestaudio/best"),
}

# chave -> (rótulo, template do yt-dlp)
NAME_TEMPLATES = {
    "title": ("Título", "%(title)s"),
    # playlist_index é injetado pelo downloader (extra_info), pois cada
    # item é baixado pela URL do vídeo, fora do contexto da playlist.
    "index_title": ("NNN - Título", "%(playlist_index)03d - %(title)s"),
    "channel_title": ("Canal - Título", "%(uploader,channel|Desconhecido)s - %(title)s"),
}

COOKIE_MODES = ("none", "browser", "file")


@dataclass
class Settings:
    download_folder: str = str(DEFAULT_DOWNLOAD_FOLDER)
    audio_format: str = "m4a"
    name_template: str = "title"
    sponsorblock: bool = False
    write_m3u: bool = False
    playlist_subfolder: bool = False
    cookie_mode: str = "none"
    cookie_browser: str = "firefox"
    cookie_profile: str = ""
    cookie_file: str = ""
    url_history: list = field(default_factory=list)
    speed_limit_mb: str = ""
    phone_host: str = ""
    phone_port: str = "2121"
    phone_user: str = ""
    phone_password: str = ""
    phone_folder: str = "/Music"
    phone_auto_send: bool = False
    phone_send_m3u: bool = True

    @classmethod
    def load(cls, path=SETTINGS_FILE):
        """Lê o JSON; campos inválidos ou um arquivo corrompido voltam ao padrão."""
        settings = cls()
        try:
            with open(path, "r", encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, ValueError):
            return settings
        if not isinstance(raw, dict):
            return settings

        for spec in fields(cls):
            if spec.name not in raw:
                continue
            value = raw[spec.name]
            default = getattr(settings, spec.name)
            if isinstance(default, bool):
                if isinstance(value, bool):
                    setattr(settings, spec.name, value)
            elif isinstance(default, list):
                if isinstance(value, list):
                    setattr(settings, spec.name, [str(v) for v in value if v])
            elif isinstance(value, str):
                setattr(settings, spec.name, value)

        if settings.audio_format not in AUDIO_FORMATS:
            settings.audio_format = cls.audio_format
        if settings.name_template not in NAME_TEMPLATES:
            settings.name_template = cls.name_template
        if settings.cookie_mode not in COOKIE_MODES:
            settings.cookie_mode = cls.cookie_mode
        if not settings.download_folder.strip():
            settings.download_folder = str(DEFAULT_DOWNLOAD_FOLDER)
        settings.url_history = settings.url_history[:URL_HISTORY_SIZE]
        return settings

    def save(self, path=SETTINGS_FILE):
        """Grava de forma atômica (arquivo temporário + replace)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(asdict(self), file, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def remember_url(self, url):
        url = (url or "").strip()
        if not url:
            return
        self.url_history = [url] + [u for u in self.url_history if u != url]
        self.url_history = self.url_history[:URL_HISTORY_SIZE]

    @property
    def folder(self):
        return Path(self.download_folder)
