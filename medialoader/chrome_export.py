"""
Exportação de cookies do Chrome/Edge/Brave via DevTools Protocol.

No Windows, esses navegadores criptografam os cookies com App-Bound
Encryption e o yt-dlp não consegue lê-los do disco. Aqui quem
descriptografa é o próprio navegador: o app o abre num perfil exclusivo
(o Chrome 136+ só permite depuração remota fora do perfil padrão), o
usuário entra no YouTube uma vez e os cookies são pedidos pelo protocolo
de depuração. O login fica salvo nesse perfil para as próximas exportações.
"""

import http.cookiejar
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect
from yt_dlp.cookies import YoutubeDLCookieJar

from .config import DATA_DIR

YOUTUBE_URL = "https://www.youtube.com/"
LOGIN_COOKIES = {"SAPISID", "__Secure-3PAPISID", "__Secure-1PSID", "LOGIN_INFO"}
YOUTUBE_DOMAINS = ("youtube.com", "google.com")

_EXECUTABLES = {
    "chrome": (
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ),
    "edge": (
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    ),
    "brave": (
        r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
    ),
}
SUPPORTED_BROWSERS = set(_EXECUTABLES)


def find_executable(browser):
    for raw in _EXECUTABLES.get(browser, ()):
        path = os.path.expandvars(raw)
        if os.path.isfile(path):
            return path
    return None


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _is_youtube(domain):
    domain = (domain or "").lstrip(".").lower()
    return any(domain == d or domain.endswith("." + d) for d in YOUTUBE_DOMAINS)


def cdp_to_cookie(data):
    """Converte um cookie do DevTools para http.cookiejar.Cookie."""
    domain = data["domain"]
    expires = data.get("expires")
    expires = int(expires) if expires and expires > 0 else None
    rest = {"HttpOnly": None} if data.get("httpOnly") else {}
    return http.cookiejar.Cookie(
        0, data["name"], data["value"], None, False,
        domain, True, domain.startswith("."),
        data.get("path") or "/", True, bool(data.get("secure")),
        expires, expires is None, None, None, rest,
    )


def write_cookie_file(cookies, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    jar = YoutubeDLCookieJar(str(destination))
    for data in cookies:
        jar.set_cookie(cdp_to_cookie(data))
    jar.save()
    return destination


class BrowserSession:
    """Navegador aberto num perfil exclusivo do app, com depuração remota."""

    def __init__(self, browser="chrome"):
        if browser not in SUPPORTED_BROWSERS:
            raise ValueError(f"Exportação assistida não suporta '{browser}'.")
        self.browser = browser
        self.executable = find_executable(browser)
        if not self.executable:
            raise RuntimeError(f"Não encontrei o executável do {browser.capitalize()} neste computador.")
        self.profile_dir = DATA_DIR / f"{browser}-youtube-profile"
        self.port = None
        self.process = None
        self._ws_url = None
        self._next_id = 0

    # ---------------- ciclo de vida ----------------
    def start(self, timeout=20):
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.port = _free_port()
        self.process = subprocess.Popen([
            self.executable,
            f"--user-data-dir={self.profile_dir}",
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            YOUTUBE_URL,
        ])
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    "O navegador fechou logo ao abrir. Se já existe uma janela do perfil "
                    "do MediaLoader aberta, feche-a e tente de novo.")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=2) as resp:
                    self._ws_url = json.load(resp)["webSocketDebuggerUrl"]
                return self
            except (OSError, ValueError, KeyError):
                time.sleep(0.4)
        self.close()
        raise RuntimeError("O navegador não respondeu à depuração remota a tempo.")

    @property
    def alive(self):
        return self.process is not None and self.process.poll() is None

    def close(self):
        if self._ws_url and self.alive:
            try:
                self._call("Browser.close")
            except Exception:
                pass
        if self.process is not None:
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.terminate()
        self.process = None

    # ---------------- DevTools ----------------
    def _call(self, method, params=None):
        self._next_id += 1
        message_id = self._next_id
        with connect(self._ws_url, open_timeout=5, close_timeout=2, max_size=None) as ws:
            ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
            deadline = time.time() + 10
            while time.time() < deadline:
                reply = json.loads(ws.recv(timeout=10))
                if reply.get("id") == message_id:
                    if "error" in reply:
                        raise RuntimeError(reply["error"].get("message", "erro do DevTools"))
                    return reply.get("result", {})
        raise RuntimeError(f"Sem resposta do navegador para {method}.")

    def youtube_cookies(self):
        if not self.alive:
            raise RuntimeError("A janela do navegador foi fechada antes da exportação.")
        cookies = self._call("Storage.getCookies").get("cookies", [])
        return [c for c in cookies if _is_youtube(c.get("domain"))]

    def logged_in(self):
        return any(c["name"] in LOGIN_COOKIES for c in self.youtube_cookies())

    def export(self, destination):
        """Grava o cookies.txt e fecha o navegador (assim os cookies não são rotacionados)."""
        cookies = self.youtube_cookies()
        if not cookies:
            raise RuntimeError("Nenhum cookie do YouTube encontrado nessa janela.")
        path = write_cookie_file(cookies, destination)
        self.close()
        return path, len(cookies)
