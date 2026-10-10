import queue
import threading
from tkinter import messagebox

import customtkinter as ctk

from .. import theme as T
from tkinter import filedialog

from ..config import FROZEN, ICON_FILE, README_FILE, SETTINGS_FILE, Settings
from ..cookies import CookieConfig, check_cookies
from ..downloader import DownloadItem, DownloadService, check_environment
from ..library import LibraryIndex
from ..notify import is_newer, latest_ytdlp_version, notify_if_unfocused, prune_logs
from ..playlist import fetch_entries
from ..playlists import PlaylistStore
from ..utils import open_folder
from .widgets import Sidebar, ToastManager


class MediaLoaderApp(ctk.CTk):
    def __init__(self):
        T.apply_global_theme()
        super().__init__(fg_color=T.BG)
        self.title("MediaLoader Pro")
        self.geometry("1320x860")
        self.minsize(1120, 720)
        if ICON_FILE.is_file():
            try:
                self.iconbitmap(str(ICON_FILE))
            except Exception:
                pass
        first_run = FROZEN and not SETTINGS_FILE.exists()

        self.settings = Settings.load()
        self.library = LibraryIndex(self.settings.download_folder)
        self.playlists = PlaylistStore.load()
        self._jobs = []               # fila de lotes (Sincronizar tudo)
        self._job_total = 0
        self.batch_listeners = []     # callbacks(summary) ao fim de cada lote
        self.playlist = None          # PlaylistResult com "status" em cada entrada
        self.env = None
        self.service = None
        self.download_thread = None
        self.last_summary = None
        self.current_screen = None
        self.shift_pressed = False
        self._queue = queue.Queue()
        self._closing = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.sidebar = Sidebar(self, on_select=self.navigate, on_new=self.new_download, on_help=self.open_help)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.content = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.toasts = ToastManager(self)

        # Import tardio: as telas importam este módulo indiretamente.
        from .dashboard import DashboardScreen
        from .diagnostics import DiagnosticsScreen
        from .progress import ProgressScreen
        from .renamer import RenamerScreen
        from .phone import PhoneScreen
        from .playlists import PlaylistsScreen
        from .selection import SelectionScreen
        from .settings import SettingsScreen

        self.screens = {
            "dashboard": DashboardScreen(self.content, self),
            "selection": SelectionScreen(self.content, self),
            "playlists": PlaylistsScreen(self.content, self),
            "progress": ProgressScreen(self.content, self),
            "phone": PhoneScreen(self.content, self),
            "renamer": RenamerScreen(self.content, self),
            "diagnostics": DiagnosticsScreen(self.content, self),
            "settings": SettingsScreen(self.content, self),
        }

        self._setup_bindings()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(40, self._drain_queue)

        self.navigate("dashboard")
        self.update_cookie_badge()
        self.refresh_env(on_done=lambda _env: self.check_ytdlp_update())
        self.reload_library()
        self.run_task(prune_logs)
        if first_run:
            self.after(600, self._first_run)

    def _first_run(self):
        """Executável aberto pela primeira vez: onde fica a biblioteca de músicas?"""
        messagebox.showinfo(
            "Bem-vindo ao MediaLoader",
            "Escolha a pasta da sua biblioteca de músicas (onde ficam os downloads).\n\n"
            "Se você já usava o MediaLoader como script, escolha a pasta antiga "
            "(ex.: ...\\python\\Downloads_Playlist_HQ) para continuar de onde parou.")
        folder = filedialog.askdirectory(title="Pasta da biblioteca de músicas",
                                         initialdir=str(self.settings.folder.parent), mustexist=False)
        self.set_download_folder(folder or self.settings.download_folder)

    def open_help(self):
        if README_FILE.is_file():
            try:
                open_folder(README_FILE)
            except OSError:  # .md sem programa associado (comum no Windows 10)
                import subprocess
                subprocess.Popen(["notepad.exe", str(README_FILE)])
        else:
            self.toast("Manual (README.md) não encontrado.", "warning")

    # ========================================================
    # THREADS → UI
    # ========================================================
    def post(self, fn, *args, **kwargs):
        """Agenda `fn` na thread da UI. Seguro de chamar de qualquer thread."""
        self._queue.put((fn, args, kwargs))

    def _drain_queue(self):
        for _ in range(300):
            try:
                fn, args, kwargs = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args, **kwargs)
            except Exception as exc:  # um callback com erro não pode parar a fila
                print(f"[MediaLoader] erro na UI: {exc!r}")
        if not self._closing:
            self.after(40, self._drain_queue)

    def run_task(self, work, on_done=None, on_error=None):
        """Executa `work()` numa thread e entrega o resultado na UI."""

        def runner():
            try:
                result = work()
            except Exception as exc:
                if on_error:
                    self.post(on_error, exc)
                else:
                    self.post(self.toast, f"Erro: {exc}", "danger")
                return
            if on_done:
                self.post(on_done, result)

        threading.Thread(target=runner, daemon=True).start()

    # ========================================================
    # NAVEGAÇÃO / UTILIDADES
    # ========================================================
    def _setup_bindings(self):
        for key in ("Shift_L", "Shift_R"):
            self.bind(f"<KeyPress-{key}>", lambda _e: setattr(self, "shift_pressed", True), add="+")
            self.bind(f"<KeyRelease-{key}>", lambda _e: setattr(self, "shift_pressed", False), add="+")
        self.bind("<Control-f>", self._on_ctrl_f, add="+")
        self.bind("<Control-a>", self._on_ctrl_a, add="+")

    def _focus_is_text_input(self):
        widget = self.focus_get()
        return widget is not None and widget.winfo_class() in ("Entry", "Text", "TEntry")

    def _on_ctrl_f(self, _event):
        screen = self.screens.get(self.current_screen)
        if hasattr(screen, "focus_search"):
            screen.focus_search()
            return "break"

    def _on_ctrl_a(self, _event):
        if self._focus_is_text_input():
            return None
        screen = self.screens.get(self.current_screen)
        if hasattr(screen, "select_all"):
            screen.select_all()
            return "break"

    def navigate(self, key):
        if key not in self.screens:
            return
        for name, screen in self.screens.items():
            if name == key:
                screen.grid(row=0, column=0, sticky="nsew", padx=32, pady=28)
            else:
                screen.grid_remove()
        self.current_screen = key
        self.sidebar.set_active(key)
        self.screens[key].on_show()

    def new_download(self):
        self.navigate("dashboard")
        self.screens["dashboard"].focus_url(clear=True)

    def toast(self, message, kind="info", duration=3500):
        self.toasts.show(message, kind, duration)

    def save_settings(self):
        try:
            self.settings.save()
        except OSError as exc:
            self.toast(f"Não foi possível salvar as configurações: {exc}", "danger")
        self.screens["dashboard"].refresh_summary()

    @property
    def cookie_config(self):
        return CookieConfig.from_settings(self.settings)

    @property
    def download_running(self):
        return self.download_thread is not None and self.download_thread.is_alive()

    # ========================================================
    # AMBIENTE / BIBLIOTECA
    # ========================================================
    def refresh_env(self, force=False, on_done=None):
        def done(env):
            self.env = env
            self.sidebar.set_env("ytdlp", f"yt-dlp {env.ytdlp_version}", "neutral")
            self.sidebar.set_env("ffmpeg", "FFmpeg ✔" if env.ffmpeg else "FFmpeg ausente",
                                 "success" if env.ffmpeg else "danger")
            js_ok = env.deno and env.ejs
            self.sidebar.set_env("deno", "Deno + EJS ✔" if js_ok else "Deno/EJS ausente",
                                 "success" if js_ok else "danger")
            self.screens["diagnostics"].show_env(env)
            if on_done:
                on_done(env)

        self.run_task(lambda: check_environment(force=force), done)

    def check_ytdlp_update(self):
        """Avisa (sem bloquear) quando há yt-dlp mais novo no PyPI."""
        current = self.env.ytdlp_version if self.env else ""

        def done(latest):
            if current and is_newer(latest, current):
                self.sidebar.set_env("ytdlp", f"yt-dlp {current} → {latest}", "warning")
                self.toast(f"Nova versão do yt-dlp ({latest}). Atualize em Diagnóstico → Ambiente: "
                           "versões antigas costumam parar de funcionar com o YouTube.", "warning", 8000)

        self.run_task(latest_ytdlp_version, done, lambda _exc: None)

    def update_cookie_badge(self, report=None):
        config = self.cookie_config
        if report is not None:
            kind = {"success": "success", "warning": "warning", "danger": "danger"}.get(report.level, "neutral")
            self.sidebar.set_env("cookies", f"Cookies: {report.summary}", kind)
        elif config.mode == "none":
            self.sidebar.set_env("cookies", "Sem cookies", "neutral")
        else:
            self.sidebar.set_env("cookies", config.describe(), "info")

    def set_download_folder(self, path):
        self.settings.download_folder = str(path)
        self.save_settings()
        self.library = LibraryIndex(self.settings.download_folder)
        self.reload_library()

    def reload_library(self, on_done=None):
        library = self.library
        entries = self.playlist.entries if self.playlist else []

        def work():
            library.load()
            for entry in entries:
                entry["status"] = library.status_for(entry)
            return library

        def done(_):
            self.screens["dashboard"].refresh_summary()
            if self.playlist:
                self.screens["selection"].refresh_statuses()
            if on_done:
                on_done()

        self.run_task(work, done)

    def annotate(self, entries):
        for entry in entries:
            entry["status"] = self.library.status_for(entry)
        return entries

    def fetch_playlist(self, url, on_done, on_error):
        """Lê a URL e classifica cada item (fora da UI: pode levar segundos)."""
        self.settings.remember_url(url)
        self.save_settings()
        try:
            cookie_opts = self.cookie_config.build_opts()
        except FileNotFoundError as exc:
            on_error(exc)
            return
        library = self.library

        def work():
            result = fetch_entries(url, cookie_opts)
            library.load()
            for entry in result.entries:
                entry["status"] = library.status_for(entry)
            return result

        def done(result):
            if self.playlists.is_saved(result.url):
                self.playlists.update_from_result(result)
                self.screens["playlists"].refresh()
            on_done(result)

        self.run_task(work, done, on_error)

    def save_playlist(self, result):
        self.playlists.add(result.url, result.title)
        self.playlists.update_from_result(result)
        self.screens["playlists"].refresh()
        self.toast(f"Playlist salva: {result.title}", "success")

    def open_playlist(self, result, select_ids=None):
        self.playlist = result
        self.screens["selection"].set_playlist(result, select_ids)
        self.navigate("selection")

    # ========================================================
    # DOWNLOAD
    # ========================================================
    def start_download(self, entries, playlist_title=None, playlist_entries=None):
        self.start_download_queue([(entries, playlist_title, playlist_entries)])

    def start_download_queue(self, jobs):
        """jobs = [(entradas, título_da_playlist, todas_as_entradas), ...] — um lote por playlist."""
        if self.download_running or self._jobs:
            self.toast("Já existe um download em andamento.", "warning")
            self.navigate("progress")
            return
        jobs = [([DownloadItem.from_entry(e) for e in entries], title, all_entries)
                for entries, title, all_entries in jobs if entries]
        if not jobs:
            self.toast("Nenhum item selecionado.", "warning")
            return

        config = self.cookie_config
        try:
            config.build_opts()
        except FileNotFoundError as exc:
            messagebox.showerror("Cookies", str(exc))
            return

        self.toast("Verificando ambiente e cookies…", "info", 2000)

        def preflight():
            env = check_environment()
            report = check_cookies(config) if config.mode != "none" else None
            return env, report

        def after_preflight(result):
            env, report = result
            self.env = env
            problems = env.blocking_problems()
            if problems:
                messagebox.showerror("Ambiente do yt-dlp incompleto", "\n\n".join(problems))
                return
            if not env.ffmpeg and not messagebox.askyesno(
                "FFmpeg ausente",
                "O FFmpeg não foi encontrado no PATH. A conversão e a capa vão falhar.\n\n"
                "Deseja continuar mesmo assim?",
            ):
                return
            if report is not None:
                self.update_cookie_badge(report)
                if not report.ok:
                    messagebox.showerror(
                        "Cookies não funcionaram",
                        f"{report.summary}\n\n{report.detail}\n\n"
                        "Ajuste em Configurações → Cookies ou escolha 'Sem cookies'.",
                    )
                    return
            self._jobs = list(jobs)
            self._job_total = len(jobs)
            self._run_next_job()

        self.run_task(preflight, after_preflight)

    def _run_next_job(self):
        if not self._jobs:
            return
        items, title, all_entries = self._jobs.pop(0)
        number = self._job_total - len(self._jobs)
        label = f"Playlist {number}/{self._job_total}" if self._job_total > 1 else None
        self._launch_download(items, title, all_entries, label)

    def _launch_download(self, items, playlist_title, playlist_entries, label=None):
        self.service = DownloadService(
            self.settings, self.cookie_config, self.library,
            emit=lambda event, **data: self.post(self._on_download_event, event, data),
        )
        progress = self.screens["progress"]
        progress.begin(items, playlist_title, label)
        self.navigate("progress")
        self.download_thread = threading.Thread(
            target=self.service.run, args=(items, playlist_title, playlist_entries), daemon=True,
        )
        self.download_thread.start()

    def stop_download(self, immediately=False):
        if self.service and self.download_running:
            self.service.request_stop(immediately)
            self.screens["progress"].on_stop_requested(immediately)

    def _on_download_event(self, event, data):
        progress = self.screens["progress"]
        progress.handle_event(event, data)

        if event == "item_start":
            done = data["index"] - 1
            self.sidebar.show_progress(done / data["total"], f"{done}/{data['total']}")
        elif event == "item_done":
            self.sidebar.show_progress(data["index"] / data["total"], f"{data['index']}/{data['total']}")
        elif event == "finished":
            summary = data["summary"]
            self.last_summary = summary
            for listener in list(self.batch_listeners):
                try:
                    listener(summary)
                except Exception as exc:
                    print(f"[MediaLoader] listener falhou: {exc!r}")
            if self._jobs and not (summary.cancelled or summary.fatal_error or self._closing):
                self.toast(f"Próxima playlist ({self._job_total - len(self._jobs) + 1}/{self._job_total})…",
                           "info", 2500)
                self.reload_library(on_done=self._run_next_job)
                return
            self._jobs = []
            self.sidebar.hide_progress()
            self.bell()
            ok, failed = summary.count("success"), summary.count("failed")
            notify_if_unfocused(self, "MediaLoader", f"Download concluído: {ok} baixada(s), {failed} falha(s).")
            if summary.fatal_error:
                self.toast(f"O lote falhou: {summary.fatal_error}", "danger", 6000)
            elif failed:
                self.toast(f"Lote concluído: {ok} baixada(s), {failed} falha(s).", "warning", 5000)
            else:
                self.toast(f"Lote concluído: {ok} baixada(s).", "success", 5000)
            if not self._closing:
                self.reload_library()

    # ========================================================
    # FECHAMENTO
    # ========================================================
    def on_close(self):
        if not self.download_running:
            self._closing = True
            self.destroy()
            return
        if not messagebox.askyesno(
            "Download em andamento",
            "Há um download em andamento. Fechar agora interrompe o item atual "
            "(o arquivo parcial fica para ser retomado depois).\n\nDeseja fechar?",
        ):
            return
        self._closing = True
        self.service.request_stop(immediately=True)
        self.title("MediaLoader Pro — encerrando…")
        self._wait_and_close(deadline=40)  # 40 × 250 ms = 10 s

    def _wait_and_close(self, deadline):
        # Continua drenando a fila para o evento "finished" chegar.
        try:
            while True:
                fn, args, kwargs = self._queue.get_nowait()
                fn(*args, **kwargs)
        except queue.Empty:
            pass
        except Exception:
            pass
        if not self.download_running or deadline <= 0:
            self.destroy()
            return
        self.after(250, lambda: self._wait_and_close(deadline - 1))


def main():
    app = MediaLoaderApp()
    app.mainloop()
