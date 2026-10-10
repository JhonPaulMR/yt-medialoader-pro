"""Manutenção da biblioteca: duplicatas, órfãos e envio para a Lixeira."""

import ctypes
import os
import re
import sys
from collections import defaultdict

from .metadata import read_tags
from .rename_rules import strip_tags
from .utils import normalize_title

DURATION_TOLERANCE = 2.0


def _file_info(folder, rel, with_tags=True):
    path = folder / rel
    try:
        stat = path.stat()
        size, mtime = stat.st_size, stat.st_mtime
    except OSError:
        size, mtime = 0, 0
    tags = read_tags(path) if with_tags else {}
    return {"rel": rel, "size": size, "mtime": mtime,
            "duration": tags.get("duration") or 0, "title": tags.get("title") or ""}


def _group_key(info):
    """
    Título do metadado (gravado pelo yt-dlp) sem as tags genéricas; se não
    houver, o nome do arquivo sem o "(1)" de cópia. "(Rock Cover)" e
    "(Instrumental)" continuam na chave: são versões diferentes.
    """
    text = info["title"] or re.sub(r"\s*\(\d+\)$", "", os.path.splitext(os.path.basename(info["rel"]))[0])
    return normalize_title(strip_tags(text) or text)


def find_duplicates(library, read_durations=True):
    """
    Grupos de arquivos que parecem a mesma música: mesmo nome sem tags e
    duração parecida (±2 s). Dentro de cada grupo, o maior arquivo vem
    primeiro (provável melhor qualidade) e é o sugerido para manter.
    """
    by_key = defaultdict(list)
    for rel in library.files:
        info = _file_info(library.folder, rel, read_durations)
        key = _group_key(info)
        if key:
            by_key[key].append(info)

    groups = []
    for infos in by_key.values():
        if len(infos) < 2:
            continue
        infos.sort(key=lambda i: i["duration"])
        # Separa versões diferentes (ex.: ao vivo × estúdio) pela duração.
        cluster = [infos[0]]
        for info in infos[1:]:
            if not read_durations or not info["duration"] or not cluster[-1]["duration"] or \
                    abs(info["duration"] - cluster[-1]["duration"]) <= DURATION_TOLERANCE:
                cluster.append(info)
            else:
                if len(cluster) > 1:
                    groups.append(sorted(cluster, key=lambda i: -i["size"]))
                cluster = [info]
        if len(cluster) > 1:
            groups.append(sorted(cluster, key=lambda i: -i["size"]))
    groups.sort(key=lambda g: g[0]["rel"].casefold())
    return groups


def find_orphans(library, entries):
    """Arquivos da pasta que não correspondem a nenhuma entrada das playlists."""
    used = set()
    for entry in entries:
        rel = library.path_for(entry)
        if rel:
            used.add(rel)
    return [_file_info(library.folder, rel, with_tags=False)
            for rel in library.files if rel not in used]


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


def send_to_recycle_bin(paths):
    """Move para a Lixeira do Windows (recuperável). Retorna quantos saíram do disco."""
    paths = [os.path.abspath(str(p)) for p in paths if os.path.exists(str(p))]
    if not paths:
        return 0
    if not sys.platform.startswith("win"):
        raise OSError("A Lixeira só é suportada no Windows.")
    fo_delete, fof_allowundo, fof_noconfirmation, fof_silent, fof_noerrorui = 3, 0x40, 0x10, 0x4, 0x400
    op = _SHFILEOPSTRUCTW()
    op.wFunc = fo_delete
    op.pFrom = "\0".join(paths) + "\0\0"
    op.fFlags = fof_allowundo | fof_noconfirmation | fof_silent | fof_noerrorui
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if result != 0:
        raise OSError(f"O Windows recusou mover para a Lixeira (código {result}).")
    return sum(1 for p in paths if not os.path.exists(p))
