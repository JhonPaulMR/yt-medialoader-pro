import os
import re
import subprocess
import sys
import unicodedata


def truncate_text(text, max_length=50):
    text = str(text or "")
    return text if len(text) <= max_length else text[: max_length - 3] + "..."


def clean_filename(filename):
    """Remove caracteres problemáticos para Windows e limita o nome."""
    filename = str(filename or "").strip()
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", filename)
    filename = re.sub(r"\s+", " ", filename).strip(" .")
    return filename[:180] or "audio_sem_nome"


def safe_join(directory, filename):
    """Garante que o caminho final fique dentro do diretório de destino."""
    filename = clean_filename(os.path.basename(filename))
    return os.path.join(directory, filename)


def playlist_position(entry, fallback_index):
    """Retorna a posição ORIGINAL da música na playlist."""
    value = entry.get("playlist_index")
    try:
        value = int(value)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return fallback_index + 1


def parse_positive_int(value, field_name):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} deve ser um número inteiro.")
    if number < 1:
        raise ValueError(f"{field_name} deve ser maior ou igual a 1.")
    return number


def build_unique_path(directory, filename, reserved_paths=None):
    """Evita colisão de nomes adicionando (1), (2), etc."""
    reserved = {os.path.abspath(p).lower() for p in (reserved_paths or ())}
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 1

    while os.path.exists(candidate) or os.path.abspath(candidate).lower() in reserved:
        candidate = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1

    return candidate


# Substituições que o yt-dlp faz com "windowsfilenames": True. Aplicá-las
# ao título deixa o título igual ao nome de arquivo que ele gerou.
_YTDLP_WINDOWS_CHARS = str.maketrans({
    "/": "⧸", "\\": "⧹", ":": "：", "*": "＊", "?": "？",
    '"': "＂", "<": "＜", ">": "＞", "|": "｜",
})
_COPY_SUFFIX = re.compile(r"\s\(\d+\)$")


def normalize_title(text):
    """Chave de comparação entre título do YouTube e nome de arquivo."""
    text = str(text or "").translate(_YTDLP_WINDOWS_CHARS)
    text = _COPY_SUFFIX.sub("", text.strip())
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in text if ch.isalnum())


BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|（[^）]*）|【[^】]*】")
_NOISE_WORDS = re.compile(
    r"\b(official|oficial|music|video|vídeo|clipe|lyrics?|audio|áudio|visualizer|"
    r"animated|remaster(ed)?|hd|4k|hq|mv|upgrade|full)\b",
    re.IGNORECASE,
)


_TRACK_NUMBER = re.compile(r"^\s*\d{1,3}(?:[\s._-]+)(?=\D)")
_FEATURING = re.compile(r"\s(?:ft\.?|feat\.?|featuring)\s.*$", re.IGNORECASE)


def core_title(text):
    """
    Título sem tags genéricas ("(Official Video)", "Lyric Video", "[HD]"…),
    sem "feat. X" e sem número de faixa no início. Usado só no casamento
    parcial, para que um arquivo chamado "Official Video.m4a" não case com
    qualquer título que tenha essa tag.
    """
    text = str(text or "").translate(_YTDLP_WINDOWS_CHARS)
    text = unicodedata.normalize("NFKC", text)
    text = BRACKETS.sub(" ", text)
    text = _FEATURING.sub("", text)
    text = _TRACK_NUMBER.sub("", text)
    text = _NOISE_WORDS.sub(" ", text)
    return normalize_title(text)


def format_duration(seconds):
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def open_folder(path):
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 - abre o Explorer na pasta escolhida
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
