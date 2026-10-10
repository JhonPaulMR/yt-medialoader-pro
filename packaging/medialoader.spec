# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: python -m PyInstaller --noconfirm --clean packaging/medialoader.spec
#
# O yt-dlp (e o yt-dlp-ejs) NÃO vão para o pacote compilado: são copiados
# como arquivos-fonte em _internal/vendor, e o music.py os põe no sys.path.
# Assim o app consegue atualizá-los sozinho (wheel em %LOCALAPPDATA%\MediaLoader\lib)
# sem precisar gerar um instalador novo a cada versão do YouTube.
import os

import yt_dlp
import yt_dlp_ejs
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
UPDATABLE = ("yt_dlp", "yt_dlp_ejs")

a = Analysis(
    [os.path.join(ROOT, "music.py")],
    pathex=[ROOT],
    datas=collect_data_files("customtkinter") + [
        (os.path.join(ROOT, "assets", "icon.ico"), "assets"),
        (os.path.join(ROOT, "README.md"), "."),
    ],
    # Analisar o yt-dlp garante que as dependências dele (stdlib, websockets,
    # mutagen, Cryptodome, brotli, certifi…) entrem no pacote.
    hiddenimports=collect_submodules("yt_dlp") + collect_submodules("websockets") + [
        "mutagen", "Cryptodome", "brotli", "certifi", "requests", "urllib3", "sqlite3",
    ],
    excludes=["pytest", "pyftpdlib"],
    noarchive=False,
)

# Tira o yt-dlp do PYZ (fica só como fonte em vendor/, atualizável).
a.pure = [entry for entry in a.pure if entry[0].split(".")[0] not in UPDATABLE]

vendor = []
for package in (yt_dlp, yt_dlp_ejs):
    folder = os.path.dirname(package.__file__)
    name = os.path.basename(folder)
    vendor += Tree(folder, prefix=os.path.join("vendor", name), excludes=["__pycache__", "*.pyc"])

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MediaLoader",
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    console=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, vendor, name="MediaLoader", upx=False)
