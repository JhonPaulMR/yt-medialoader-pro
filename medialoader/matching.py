"""Casamento entre títulos do YouTube e nomes de arquivo (PC ou celular)."""

import re
from pathlib import PurePosixPath

from .utils import core_title, normalize_title

MIN_PARTIAL_MATCH = 4
_TITLE_SEPARATOR = re.compile(r"\s+[-:|｜]\s+|\s*[–—]\s*")
_COMPLEMENT_WORDS = re.compile(
    r"\b(ao vivo|live|cover|ac[uú]stic[oa]|acoustic|remix|vers[aã]o|version|tour|"
    r"instrumental|karaok[eê]|remaster(ed)?)\b",
    re.IGNORECASE,
)


def _is_complement(segment):
    """True se o segmento é só complemento ("Ao Vivo", "Cover", "(Official Video)")."""
    return not core_title(_COMPLEMENT_WORDS.sub(" ", segment))


def title_keys(title):
    """
    Chaves para achar um arquivo renomeado a partir do título do YouTube.
    "Artista - Música (Official Video)" → {"artistamusica", "musica"}.
    O primeiro segmento (normalmente o artista) só entra quando o resto é
    puro complemento ("Música - Ao Vivo").
    """
    title = str(title or "")
    keys = {core_title(title)}
    segments = [s for s in _TITLE_SEPARATOR.split(title) if s.strip()]
    if len(segments) > 1:
        keys.update(core_title(segment) for segment in segments[1:])
        if all(_is_complement(segment) for segment in segments[1:]):
            keys.add(core_title(segments[0]))
    return {key for key in keys if len(key) >= MIN_PARTIAL_MATCH}


def stem_of(path):
    """Nome sem extensão de um caminho relativo (aceita / e barra invertida)."""
    return PurePosixPath(str(path).replace("\\", "/")).stem


class TitleMatcher:
    """Índice de nomes de arquivo para localizar um título rapidamente."""

    def __init__(self, files=()):
        self.files = []
        self._exact = {}
        self._partial = {}
        self.add_many(files)

    def add(self, path):
        self.files.append(path)
        stem = stem_of(path)
        key = normalize_title(stem)
        if not key:
            return
        self._exact.setdefault(key, path)
        core = core_title(stem)
        if len(core) >= MIN_PARTIAL_MATCH:
            self._partial.setdefault(core, path)

    def add_many(self, paths):
        for path in paths:
            self.add(path)

    def match(self, title):
        """Arquivo cujo nome corresponde ao título, ou None."""
        key = normalize_title(title)
        if not key:
            return None
        if key in self._exact:
            return self._exact[key]
        # Parcial: cobre arquivos encurtados pelo Renomeador ("Artista - Música
        # (Official Video)" → "Música"). Igualdade exata por segmento, sem as
        # tags genéricas: "Stronger" não casa com "Stronger Version".
        for candidate in sorted(title_keys(title)):
            if candidate in self._partial:
                return self._partial[candidate]
        return None

    def match_file(self, path):
        """Mesmo arquivo em outra pasta: compara pelo nome sem extensão."""
        return self.match(stem_of(path))
