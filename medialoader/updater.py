"""
Atualização do yt-dlp no executável (onde não existe pip).

Baixa os wheels puros de yt-dlp e yt-dlp-ejs do PyPI, confere o sha256
informado pela própria API do PyPI e extrai em LIB_DIR, que o music.py
coloca na frente do sys.path na próxima abertura do app.
"""

import hashlib
import io
import json
import shutil
import urllib.request
import zipfile

from .config import LIB_DIR

PACKAGES = (("yt-dlp", "yt_dlp"), ("yt-dlp-ejs", "yt_dlp_ejs"))


def _pure_wheel(project):
    with urllib.request.urlopen(f"https://pypi.org/pypi/{project}/json", timeout=20) as resp:
        data = json.load(resp)
    for file in data["urls"]:
        if file["packagetype"] == "bdist_wheel" and file["filename"].endswith("py3-none-any.whl"):
            return data["info"]["version"], file
    raise RuntimeError(f"O PyPI não tem um wheel compatível de {project}.")


def _download(file):
    with urllib.request.urlopen(file["url"], timeout=120) as resp:
        payload = resp.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != file["digests"]["sha256"]:
        raise RuntimeError(f"Checksum inválido em {file['filename']}; download descartado.")
    return payload


def update_from_wheels(lib_dir=LIB_DIR):
    """Retorna (ok, texto). Tudo é extraído numa pasta temporária e só então trocado."""
    lib_dir.mkdir(parents=True, exist_ok=True)
    staging = lib_dir.with_name(lib_dir.name + ".novo")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    log = []
    try:
        for project, package in PACKAGES:
            version, file = _pure_wheel(project)
            log.append(f"{project} {version}: baixando {file['filename']}…")
            with zipfile.ZipFile(io.BytesIO(_download(file))) as wheel:
                for member in wheel.namelist():
                    top = member.split("/", 1)[0]
                    if top == package or top.endswith(".dist-info"):
                        wheel.extract(member, staging)
            log.append(f"{project} {version}: OK (sha256 conferido)")
        # Troca a pasta antiga pela nova só depois de tudo baixado.
        backup = lib_dir.with_name(lib_dir.name + ".antigo")
        shutil.rmtree(backup, ignore_errors=True)
        if lib_dir.exists():
            lib_dir.rename(backup)
        staging.rename(lib_dir)
        shutil.rmtree(backup, ignore_errors=True)
        log.append("Pronto. Feche e abra o MediaLoader para usar a nova versão.")
        return True, "\n".join(log)
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        log.append(f"Falhou: {exc}")
        return False, "\n".join(log)
