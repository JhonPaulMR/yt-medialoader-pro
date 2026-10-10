import os
import re

from .config import SUPPORTED_MEDIA_EXTS
from .utils import BRACKETS, clean_filename, core_title

KEEP = "Manter Original"
DROP_START = "Apagar INÍCIO"
DROP_END = "Apagar FINAL"
STRIP_TAGS = "Remover tags"
FROM_METADATA = "Usar metadado"
ACTIONS = (DROP_START, DROP_END, STRIP_TAGS, FROM_METADATA, KEEP)

# " - " / " : " com espaços, ou travessões (– —) com ou sem espaços.
_SEPARATOR = r"(?:\s+[-:]\s+|\s*[–—]\s*)"
_SONG_KEYWORDS = (
    "official", "lyric", "audio", "video", "visualizer",
    "remaster", "hd", "4k", "hq",
)
_EXTRA_KEYWORDS = ("ao vivo", "cover", "live", "tour", "feat", "part.", "ft.")
_UNWRAP = re.compile(r"[()\[\]（）【】]")


def guess_rename_action(filename):
    """Heurística para sugerir limpeza do nome do arquivo."""
    name_no_ext = os.path.splitext(filename)[0]
    parts = re.split(_SEPARATOR, name_no_ext, maxsplit=1)
    if len(parts) < 2:
        # Hífens sem espaço ("Jay-Z") não são separadores.
        return KEEP

    left, right = parts[0].lower().strip(), parts[1].lower().strip()

    # "Música - Official Video": apagar o início deixaria só a tag
    # (era assim que surgiam arquivos chamados "OFFICIAL VIDEO.m4a").
    if not core_title(right):
        return DROP_END
    if not core_title(left):
        return DROP_START

    # "03 - Música": o lado esquerdo é só o número da faixa.
    if left.isdigit():
        return DROP_START

    # "03 Música - Artista": mantém a parte numerada.
    if re.match(r"^\d+[\s.]", left):
        return DROP_END

    if any(k in right for k in _SONG_KEYWORDS):
        return DROP_START

    if any(k in right for k in _EXTRA_KEYWORDS):
        return DROP_END

    return DROP_START


def strip_tags(stem):
    """
    Remove só as tags genéricas: "Música (Official Video) [HD]" → "Música".
    Mantém informações úteis como "(Ao Vivo)" e "(feat. X)".
    """
    result = BRACKETS.sub(lambda m: "" if not core_title(m.group(0)[1:-1]) else m.group(0), stem)
    parts = re.split(_SEPARATOR, result)
    # Parênteses que sobraram já têm conteúdo útil ("(Sic)"): avalia o texto de dentro.
    kept = [part for part in parts if core_title(_UNWRAP.sub(" ", part))]
    if len(kept) < len(parts):
        result = " - ".join(part.strip() for part in kept)
    return re.sub(r"\s+", " ", result).strip(" -.")


def is_generic_name(filename):
    """Nome que perdeu a música (ex.: "OFFICIAL VIDEO.m4a"); "(Sic)" e "502" não contam."""
    stem = re.sub(r"\s*\(\d+\)$", "", os.path.splitext(filename)[0])  # cópia "(1)"
    return not strip_tags(stem)


def name_from_title(orig_name, title):
    """Novo nome a partir da tag de título, preservando a extensão."""
    ext = os.path.splitext(orig_name)[1]
    title = (title or "").strip()
    title = strip_tags(title) or title
    return clean_filename(title) + ext if title else orig_name


def is_numbered_copy(filename):
    """ "Linkin Park (14).m4a": cópia numerada, típica de nome danificado."""
    return bool(re.search(r"\s\(\d+\)$", os.path.splitext(filename)[0]))


def apply_regex_name(orig_name, mode):
    ext = os.path.splitext(orig_name)[1]
    if ext.lower() not in SUPPORTED_MEDIA_EXTS or mode == KEEP:
        return orig_name

    if mode == STRIP_TAGS:
        stem = strip_tags(os.path.splitext(orig_name)[0])
        return clean_filename(stem) + ext if stem else orig_name

    if mode == DROP_START:
        pattern = rf"^.+?{_SEPARATOR}(.+?){re.escape(ext)}$"
    elif mode == DROP_END:
        pattern = rf"^(.+?){_SEPARATOR}.*{re.escape(ext)}$"
    else:
        return orig_name

    match = re.match(pattern, orig_name, re.IGNORECASE)
    if match and match.group(1).strip():
        return clean_filename(match.group(1).strip()) + ext
    return orig_name
