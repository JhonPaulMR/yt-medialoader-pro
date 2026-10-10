"""MediaLoader Pro — ponto de entrada (script e executável).

O código fica no pacote `medialoader/`; a versão monolítica anterior está
em `music_legacy.py`.
"""

import os
import sys

# Permite rodar de qualquer diretório (duplo clique, atalho, outro terminal).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from medialoader.config import FROZEN, LIB_DIR, VENDOR_DIR  # noqa: E402

if FROZEN:
    # No executável o yt-dlp não fica embutido no pacote compilado: vem de
    # VENDOR_DIR (versão do instalador) ou de LIB_DIR (atualizada pelo app),
    # que tem prioridade. Precisa acontecer antes de qualquer import do yt-dlp.
    for folder in (VENDOR_DIR, LIB_DIR):
        if os.path.isdir(os.path.join(folder, "yt_dlp")):
            sys.path.insert(0, str(folder))


def self_test(target_folder):
    """
    MediaLoader.exe --self-test <pasta>: confere se o executável está completo
    (imports, yt-dlp, FFmpeg/Deno) e baixa um vídeo curto. Relatório em
    <pasta>/selftest.log (o executável não tem console).
    """
    import traceback
    from pathlib import Path

    folder = Path(target_folder)
    folder.mkdir(parents=True, exist_ok=True)
    lines = []
    try:
        import yt_dlp

        from medialoader.config import Settings
        from medialoader.cookies import CookieConfig
        from medialoader.downloader import DownloadItem, DownloadService, check_environment
        from medialoader.library import LibraryIndex
        from medialoader.playlist import fetch_entries

        lines.append(f"yt_dlp: {yt_dlp.version.__version__} em {yt_dlp.__file__}")
        env = check_environment()
        lines.append(f"ambiente: ffmpeg={bool(env.ffmpeg)} deno={bool(env.deno)} ejs={env.ejs}")
        result = fetch_entries("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        lines.append(f"leitura: {result.title}")
        library = LibraryIndex(folder).load()
        summary = DownloadService(Settings(download_folder=str(folder)), CookieConfig(), library,
                                  emit=lambda *_a, **_k: None).run([DownloadItem.from_entry(result.entries[0])])
        for item in summary.results:
            lines.append(f"download: {item.status} {item.filepath or item.error}")
        lines.append("RESULTADO: OK" if summary.count("success") == 1 else "RESULTADO: FALHOU")
    except Exception:
        lines.append(traceback.format_exc())
        lines.append("RESULTADO: FALHOU")
    (folder / "selftest.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-test":
        self_test(sys.argv[2])
    else:
        from medialoader.ui.app import main

        main()
