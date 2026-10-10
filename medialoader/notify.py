"""Avisos do Windows (barra de tarefas piscando + notificação) e logs em arquivo."""

import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

from .config import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_KEEP_DAYS = 30

_TOAST_SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$text = $t.GetElementsByTagName('text')
$text[0].AppendChild($t.CreateTextNode($env:ML_TITLE)) > $null
$text[1].AppendChild($t.CreateTextNode($env:ML_MESSAGE)) > $null
$n = [Windows.UI.Notifications.ToastNotification]::new($t)
$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show($n)
"""


class _FLASHWINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p), ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_uint)]


def flash_taskbar(window):
    """Pisca o ícone na barra de tarefas até a janela receber foco."""
    if not sys.platform.startswith("win"):
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        flash_all, flash_until_focus = 0x3, 0xC
        info = _FLASHWINFO(ctypes.sizeof(_FLASHWINFO), hwnd, flash_all | flash_until_focus, 0, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


def windows_toast(title, message):
    """Notificação nativa via PowerShell (melhor esforço; texto passado por variável de ambiente)."""
    if not sys.platform.startswith("win"):
        return
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", _TOAST_SCRIPT],
            env=dict(os.environ, ML_TITLE=str(title), ML_MESSAGE=str(message)),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def notify_if_unfocused(window, title, message):
    if window.focus_displayof() is None:
        flash_taskbar(window)
        windows_toast(title, message)


# ---------------- logs ----------------
def append_log_line(line):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"
        with open(path, "a", encoding="utf-8") as file:
            file.write(line.rstrip("\n") + "\n")
    except OSError:
        pass


def prune_logs(keep_days=LOG_KEEP_DAYS):
    if not LOG_DIR.is_dir():
        return
    limit = time.time() - keep_days * 86400
    for path in LOG_DIR.glob("*.log"):
        try:
            if path.stat().st_mtime < limit:
                path.unlink()
        except OSError:
            pass


# ---------------- atualização do yt-dlp ----------------
def _version_tuple(version):
    return tuple(int(p) for p in str(version).split(".") if p.isdigit())


def latest_ytdlp_version(timeout=6):
    with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=timeout) as resp:
        return json.load(resp)["info"]["version"]


def is_newer(latest, current):
    return _version_tuple(latest) > _version_tuple(current)
