"""Configuração, teste e exportação de cookies para o yt-dlp."""

import http.cookiejar
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from yt_dlp.cookies import YDLLogger, YoutubeDLCookieJar, extract_cookies_from_browser

from .errors import friendly_error

# (rótulo exibido, nome no yt-dlp)
BROWSERS = (
    ("Firefox (recomendado)", "firefox"),
    ("Chrome", "chrome"),
    ("Edge", "edge"),
    ("Brave", "brave"),
    ("Opera", "opera"),
    ("Vivaldi", "vivaldi"),
    ("Chromium", "chromium"),
)
BROWSER_LABELS = {key: label for label, key in BROWSERS}
CHROMIUM_BROWSERS = {"chrome", "edge", "brave", "opera", "vivaldi", "chromium"}

YOUTUBE_DOMAINS = ("youtube.com", "google.com")
LOGIN_COOKIES = {"SAPISID", "__Secure-3PAPISID", "__Secure-1PSID", "LOGIN_INFO", "SID"}
STALE_DAYS = 14

SUCCESS, WARNING, DANGER, NEUTRAL = "success", "warning", "danger", "neutral"

# Pasta "User Data" de cada navegador Chromium no Windows.
_USER_DATA_DIRS = {
    "chrome": r"%LOCALAPPDATA%\Google\Chrome\User Data",
    "edge": r"%LOCALAPPDATA%\Microsoft\Edge\User Data",
    "brave": r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data",
    "vivaldi": r"%LOCALAPPDATA%\Vivaldi\User Data",
    "chromium": r"%LOCALAPPDATA%\Chromium\User Data",
}


def user_data_dir(browser):
    raw = _USER_DATA_DIRS.get(browser)
    return Path(os.path.expandvars(raw)) if raw else None


def list_profiles(browser):
    """[(pasta, nome exibido)] dos perfis de um navegador Chromium."""
    base = user_data_dir(browser)
    if not base:
        return []
    try:
        with open(base / "Local State", "r", encoding="utf-8") as file:
            cache = json.load(file)["profile"]["info_cache"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return sorted(((folder, (info or {}).get("name") or folder) for folder, info in cache.items()),
                  key=lambda item: (item[0] != "Default", item[0]))


def resolve_profile(browser, profile):
    """
    Aceita o nome exibido no navegador ("Liptinho Tutoriais") e devolve
    a pasta que o yt-dlp espera ("Default", "Profile 1").
    """
    profile = (profile or "").strip()
    if not profile or browser not in _USER_DATA_DIRS:
        return profile or None
    for folder, name in list_profiles(browser):
        if profile.casefold() in (folder.casefold(), name.casefold()):
            return folder
    return profile


def browser_installed(browser):
    base = user_data_dir(browser)
    return base is None or base.is_dir()


@dataclass
class CookieConfig:
    mode: str = "none"        # none | browser | file
    browser: str = "firefox"
    profile: str = ""
    file: str = ""

    @classmethod
    def from_settings(cls, settings):
        return cls(
            mode=settings.cookie_mode,
            browser=settings.cookie_browser,
            profile=settings.cookie_profile,
            file=settings.cookie_file,
        )

    def build_opts(self):
        """Somente as opções que o usuário escolheu; nenhum navegador é lido à toa."""
        if self.mode == "browser":
            return {"cookiesfrombrowser": (self.browser, resolve_profile(self.browser, self.profile), None, None)}
        if self.mode == "file":
            if not self.file or not os.path.isfile(self.file):
                raise FileNotFoundError("O arquivo cookies.txt não foi selecionado ou não existe.")
            return {"cookiefile": self.file}
        return {}

    def describe(self):
        if self.mode == "browser":
            label = BROWSER_LABELS.get(self.browser, self.browser).replace(" (recomendado)", "")
            return f"Navegador: {label}" + (f" ({self.profile})" if self.profile.strip() else "")
        if self.mode == "file":
            return f"Arquivo: {os.path.basename(self.file)}" if self.file else "Arquivo: não escolhido"
        return "Sem cookies"


@dataclass
class CookieReport:
    level: str          # success | warning | danger | neutral
    summary: str        # texto curto para a pílula
    detail: str = ""    # explicação / próximo passo
    youtube_count: int = 0
    logged_in: bool = False

    @property
    def ok(self):
        return self.level in (SUCCESS, WARNING, NEUTRAL)


class _CaptureLogger(YDLLogger):
    """Guarda avisos e erros da extração de cookies para mostrar na UI."""

    def __init__(self):
        super().__init__(None)
        self.messages = []

    def warning(self, message, only_once=False):
        self.messages.append(str(message))

    def error(self, message, *, is_error=True):
        self.messages.append(str(message))


def _is_youtube_cookie(cookie):
    domain = (cookie.domain or "").lstrip(".").lower()
    return any(domain == d or domain.endswith("." + d) for d in YOUTUBE_DOMAINS)


def youtube_cookies(jar):
    return [c for c in jar if _is_youtube_cookie(c)]


def _report_from_cookies(cookies, source, age_days=None):
    now = time.time()
    valid = [c for c in cookies if not c.expires or c.expires > now]
    logged_in = any(c.name in LOGIN_COOKIES for c in valid)
    count = len(valid)

    if not count:
        return CookieReport(
            DANGER, "Nenhum cookie do YouTube",
            f"{source} não tem cookies válidos de youtube.com. Entre no YouTube "
            "nesse navegador (ou exporte de novo) e teste outra vez.",
        )

    detail = f"{count} cookies do YouTube/Google lidos de {source}."
    if age_days is not None and age_days > STALE_DAYS:
        detail += (
            f" O arquivo tem {age_days} dias; o YouTube troca os cookies com "
            "frequência, então exporte de novo se der erro."
        )
    if not logged_in:
        return CookieReport(
            WARNING, f"{count} cookies · sem login",
            detail + " Nenhum cookie de login encontrado: vídeos privados ou "
            "com restrição de idade vão falhar.",
            youtube_count=count,
        )
    level = WARNING if age_days is not None and age_days > STALE_DAYS else SUCCESS
    return CookieReport(level, f"{count} cookies · logado", detail, count, True)


def _error_report(exc, browser=None):
    text = str(exc)
    hint = friendly_error(text)
    if hint is None and browser in CHROMIUM_BROWSERS and isinstance(exc, PermissionError):
        hint = friendly_error("could not copy cookie database")
    return CookieReport(DANGER, "Falha ao ler cookies", hint or text)


def load_browser_jar(browser, profile=""):
    """Lê o jar do navegador. Erros sobem com a mensagem do yt-dlp."""
    label = BROWSER_LABELS.get(browser, browser).replace(" (recomendado)", "")
    if not browser_installed(browser):
        raise RuntimeError(f"O {label} não está instalado neste computador (pasta de dados não encontrada).")
    folder = resolve_profile(browser, profile)
    profiles = list_profiles(browser)
    if folder and profiles and folder not in {f for f, _ in profiles}:
        options = ", ".join(f"'{name}' ({f})" for f, name in profiles)
        raise RuntimeError(f"Perfil '{profile}' não encontrado no {label}. Perfis disponíveis: {options}.")

    logger = _CaptureLogger()
    try:
        jar = extract_cookies_from_browser(browser, folder, logger)
    except Exception as exc:
        # O yt-dlp loga o motivo antes de levantar um erro genérico.
        detail = " ".join(logger.messages) or str(exc)
        raise RuntimeError(detail) from exc
    return jar, logger.messages


def validate_cookie_file(path):
    path = str(path or "")
    if not path or not os.path.isfile(path):
        return CookieReport(DANGER, "Arquivo não encontrado", "Escolha um cookies.txt existente.")
    jar = YoutubeDLCookieJar(path)
    try:
        jar.load()
    except (http.cookiejar.LoadError, ValueError, OSError) as exc:
        hint = friendly_error(str(exc)) or (
            "O arquivo não está no formato Netscape (a primeira linha deve ser "
            "'# Netscape HTTP Cookie File')."
        )
        return CookieReport(DANGER, "cookies.txt inválido", hint)
    age_days = int((time.time() - os.path.getmtime(path)) // 86400)
    return _report_from_cookies(youtube_cookies(jar), os.path.basename(path), age_days)


def check_cookies(config):
    """Verifica a configuração atual sem baixar nada."""
    if config.mode == "none":
        return CookieReport(
            NEUTRAL, "Sem cookies",
            "Funciona para vídeos públicos. Para privados ou com restrição de "
            "idade, configure cookies.",
        )
    if config.mode == "file":
        return validate_cookie_file(config.file)

    label = BROWSER_LABELS.get(config.browser, config.browser).replace(" (recomendado)", "")
    try:
        jar, messages = load_browser_jar(config.browser, config.profile)
    except Exception as exc:
        return _error_report(exc, config.browser)

    report = _report_from_cookies(youtube_cookies(jar), label)
    # Cookies que falharam na descriptografia não derrubam a leitura,
    # mas deixam o jar vazio — mostre o motivo real.
    if report.level == DANGER and messages:
        hint = friendly_error(" ".join(messages))
        if hint:
            report.detail = hint
    return report


def export_youtube_cookies(config, destination):
    """Exporta só os cookies do YouTube/Google do navegador para um cookies.txt."""
    label = BROWSER_LABELS.get(config.browser, config.browser).replace(" (recomendado)", "")
    try:
        jar, _ = load_browser_jar(config.browser, config.profile)
    except Exception as exc:
        return _error_report(exc, config.browser), None

    selected = youtube_cookies(jar)
    report = _report_from_cookies(selected, label)
    if not selected:
        return report, None

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    out = YoutubeDLCookieJar(str(destination))
    for cookie in selected:
        out.set_cookie(cookie)
    out.save()
    report.detail = f"{len(selected)} cookies salvos em {destination.name}. " + report.detail
    return report, str(destination)
