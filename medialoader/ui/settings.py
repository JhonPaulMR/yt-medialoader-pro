import shutil
import time
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .. import theme as T
from ..config import AUDIO_FORMATS, DATA_DIR, EXPORTED_COOKIES_FILE, LEGACY_COOKIES_FILE, NAME_TEMPLATES
from ..chrome_export import SUPPORTED_BROWSERS as ASSISTED_BROWSERS
from ..chrome_export import BrowserSession
from ..cookies import (
    BROWSERS,
    CookieConfig,
    check_cookies,
    export_youtube_cookies,
    list_profiles,
    validate_cookie_file,
)
from ..utils import open_folder, truncate_text
from .base import Screen
from .widgets import Badge, PageHeader

COOKIE_MODE_LABELS = {"none": "Sem cookies", "browser": "Ler do navegador", "file": "Arquivo cookies.txt"}
FORMAT_SHORT = {"m4a": "M4A", "mp3": "MP3", "opus": "Opus"}
REPORT_BADGE = {"success": "success", "warning": "warning", "danger": "danger", "neutral": "neutral"}


class SettingsScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        PageHeader(self, "Configurações", "Tudo é salvo automaticamente em data/settings.json.").grid(
            row=0, column=0, sticky="ew", pady=(0, 12))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=T.SURFACE_3)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        self._build_folder(body)
        self._build_audio(body)
        self._build_cookies(body)
        self.load_from_settings()

    # ---------------- helpers ----------------
    def _section(self, parent, row, title, subtitle):
        card = T.card(parent)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 14), padx=(0, 8))
        card.grid_columnconfigure(1, weight=1)
        T.label(card, title, "title").grid(row=0, column=0, columnspan=3, sticky="w", padx=22, pady=(18, 0))
        T.label(card, subtitle, "caption", T.MUTED).grid(row=1, column=0, columnspan=3, sticky="w",
                                                        padx=22, pady=(0, 12))
        return card

    def _field(self, card, row, caption):
        T.label(card, caption, "body", T.MUTED, width=150).grid(row=row, column=0, sticky="nw", padx=(22, 12),
                                                               pady=8)

    @property
    def settings(self):
        return self.app.settings

    def _save(self):
        self.app.save_settings()

    # ========================================================
    # PASTA
    # ========================================================
    def _build_folder(self, parent):
        card = self._section(parent, 0, "Pasta de destino",
                             "Onde os áudios, o .archive.txt e o índice .library.json ficam.")
        self._field(card, 2, "Pasta")
        self.folder_label = T.label(card, "", "mono", T.TEXT)
        self.folder_label.grid(row=2, column=1, sticky="w", pady=8)
        box = ctk.CTkFrame(card, fg_color="transparent")
        box.grid(row=2, column=2, sticky="e", padx=(8, 22))
        T.secondary_button(box, "Alterar…", self.choose_folder, width=100).pack(side="left", padx=4)
        T.secondary_button(box, "Abrir", lambda: open_folder(self.settings.folder), width=80).pack(side="left")

        self.sw_subfolder = T.switch(card, "Criar uma subpasta com o nome da playlist",
                                     command=self._on_toggle("playlist_subfolder", "sw_subfolder"))
        self.sw_subfolder.grid(row=3, column=1, columnspan=2, sticky="w", pady=(4, 18))

    def choose_folder(self):
        selected = filedialog.askdirectory(title="Pasta de destino", initialdir=self.settings.download_folder,
                                           mustexist=False)
        if selected:
            self.app.set_download_folder(selected)
            self.folder_label.configure(text=truncate_text(selected, 70))
            self.app.screens["renamer"].loaded = False
            self.app.toast("Pasta de destino atualizada.", "success")

    def _on_toggle(self, attr, widget_name):
        def handler():
            setattr(self.settings, attr, bool(getattr(self, widget_name).get()))
            self._save()
        return handler

    # ========================================================
    # ÁUDIO
    # ========================================================
    def _build_audio(self, parent):
        card = self._section(parent, 1, "Áudio e nomes", "Valem para os próximos downloads.")

        self._field(card, 2, "Formato")
        fmt_box = ctk.CTkFrame(card, fg_color="transparent")
        fmt_box.grid(row=2, column=1, columnspan=2, sticky="w", pady=8)
        self.format = T.segmented(fmt_box, FORMAT_SHORT.values(), command=self._on_format)
        self.format.pack(anchor="w")
        self.format_hint = T.label(fmt_box, "", "caption", T.MUTED)
        self.format_hint.pack(anchor="w", pady=(4, 0))

        self._field(card, 3, "Nome do arquivo")
        self.template = T.option_menu(card, [label for label, _ in NAME_TEMPLATES.values()],
                                      self._on_template, width=200)
        self.template.grid(row=3, column=1, sticky="w", pady=8)

        self._field(card, 4, "Extras")
        extras = ctk.CTkFrame(card, fg_color="transparent")
        extras.grid(row=4, column=1, columnspan=2, sticky="w", pady=(8, 18))
        self.sw_sponsor = T.switch(extras, "Remover trechos sem música (SponsorBlock: music_offtopic)",
                                   command=self._on_toggle("sponsorblock", "sw_sponsor"))
        self.sw_sponsor.pack(anchor="w")
        T.label(extras, "Corta intros, falas e cenas de clipes quando a comunidade marcou o trecho.",
                "caption", T.MUTED).pack(anchor="w", padx=(46, 0), pady=(0, 8))
        self.sw_m3u = T.switch(extras, "Gerar playlist .m3u8 na ordem da playlist do YouTube",
                               command=self._on_toggle("write_m3u", "sw_m3u"))
        self.sw_m3u.pack(anchor="w")

        self._field(card, 5, "Limite de velocidade")
        speed = ctk.CTkFrame(card, fg_color="transparent")
        speed.grid(row=5, column=1, columnspan=2, sticky="w", pady=(0, 18))
        self.speed = T.entry(speed, "sem limite", width=110)
        self.speed.pack(side="left")
        T.label(speed, "MB/s  (vazio = sem limite; útil para não travar a internet de casa)",
                "caption", T.MUTED).pack(side="left", padx=8)
        self.speed.bind("<FocusOut>", self._on_speed)
        self.speed.bind("<Return>", self._on_speed)

        phone = self._section(parent, 3, "Celular", "A conexão (IP, porta, pasta) é configurada na tela Celular.")
        self.sw_auto_phone = T.switch(phone, "Enviar ao celular automaticamente depois de cada download",
                                      command=self._on_toggle("phone_auto_send", "sw_auto_phone"))
        self.sw_auto_phone.grid(row=2, column=0, columnspan=3, sticky="w", padx=22, pady=(0, 18))

    def _on_speed(self, _event=None):
        value = self.speed.get().strip().replace(",", ".")
        try:
            if value and float(value) <= 0:
                raise ValueError
        except ValueError:
            self.app.toast("Limite inválido: use um número como 2 ou 0.5 (MB/s).", "warning")
            return
        if value != self.settings.speed_limit_mb:
            self.settings.speed_limit_mb = value
            self._save()

    def _on_format(self, short):
        key = next(k for k, v in FORMAT_SHORT.items() if v == short)
        self.settings.audio_format = key
        self.format_hint.configure(text=AUDIO_FORMATS[key][0])
        self._save()

    def _on_template(self, label):
        self.settings.name_template = next(k for k, (lbl, _) in NAME_TEMPLATES.items() if lbl == label)
        self._save()

    # ========================================================
    # COOKIES
    # ========================================================
    def _build_cookies(self, parent):
        card = self._section(
            parent, 2, "Cookies (autenticação)",
            "Necessário só para vídeos privados, com restrição de idade ou quando o YouTube pede login.")

        self._field(card, 2, "Origem")
        self.cookie_mode = T.segmented(card, COOKIE_MODE_LABELS.values(), command=self._on_cookie_mode)
        self.cookie_mode.grid(row=2, column=1, columnspan=2, sticky="w", pady=8)

        # --- navegador ---
        self.browser_box = ctk.CTkFrame(card, fg_color="transparent")
        self.browser_box.grid_columnconfigure(1, weight=1)
        T.label(self.browser_box, "Navegador", "body", T.MUTED, width=150).grid(
            row=0, column=0, sticky="w", padx=(22, 12), pady=6)
        row = ctk.CTkFrame(self.browser_box, fg_color="transparent")
        row.grid(row=0, column=1, sticky="w", pady=6)
        self.browser = T.option_menu(row, [label for label, _ in BROWSERS], self._on_browser, width=200)
        self.browser.pack(side="left")
        # Lista os perfis detectados pelo nome exibido no navegador; também
        # aceita digitar a pasta ("Default", "Profile 1").
        self.profile = ctk.CTkComboBox(
            row, values=[""], width=280, height=34, corner_radius=T.RADIUS_CONTROL, border_width=1,
            fg_color=T.SURFACE_2, border_color=T.BORDER, button_color=T.SURFACE_3,
            button_hover_color="#363636", dropdown_fg_color=T.SURFACE_2,
            dropdown_hover_color=T.SURFACE_3, font=T.body(), dropdown_font=T.body(), text_color=T.TEXT,
            command=lambda _v: self._on_profile(),
        )
        self.profile.set("")
        self.profile.pack(side="left", padx=10)
        self.profile.bind("<FocusOut>", self._on_profile)
        self.profile.bind("<Return>", self._on_profile)
        self.profile_hint = T.label(row, "", "caption", T.MUTED)
        self.profile_hint.pack(side="left")
        T.label(self.browser_box,
                "Chrome/Edge/Brave no Windows criptografam os cookies (App-Bound Encryption): ler direto "
                "não funciona. Use 'Entrar no YouTube e exportar', que pede os cookies ao próprio navegador. "
                "O Firefox pode ser lido direto, mesmo aberto.",
                "caption", T.MUTED, wraplength=720).grid(row=1, column=1, sticky="w", pady=(0, 6))

        # --- arquivo ---
        self.file_box = ctk.CTkFrame(card, fg_color="transparent")
        self.file_box.grid_columnconfigure(1, weight=1)
        T.label(self.file_box, "Arquivo", "body", T.MUTED, width=150).grid(
            row=0, column=0, sticky="w", padx=(22, 12), pady=6)
        self.file_label = T.label(self.file_box, "", "mono", T.TEXT)
        self.file_label.grid(row=0, column=1, sticky="w", pady=6)
        T.secondary_button(self.file_box, "Escolher…", self.choose_cookie_file, width=110).grid(
            row=0, column=2, sticky="e", padx=(8, 22))
        T.label(self.file_box,
                "Dica do yt-dlp: abra uma janela anônima, entre no YouTube, acesse youtube.com/robots.txt, "
                "exporte os cookies (ex.: extensão 'Get cookies.txt LOCALLY') e feche a janela. Assim o "
                "YouTube não invalida os cookies.",
                "caption", T.MUTED, wraplength=720).grid(row=1, column=1, columnspan=2, sticky="w", pady=(0, 6))

        # --- ações + resultado ---
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=5, column=1, columnspan=2, sticky="w", pady=(8, 4))
        self.btn_test = T.primary_button(actions, "Testar cookies", self.test_cookies, width=150, height=34)
        self.btn_test.pack(side="left")
        self.btn_export = T.secondary_button(actions, "Exportar do navegador → cookies.txt",
                                             self.export_cookies, width=270)
        self.btn_export.pack(side="left", padx=8)

        # Exportação assistida: o próprio Chrome descriptografa os cookies.
        self._session = None
        self._poll_deadline = 0
        self.btn_assist = T.secondary_button(actions, "Entrar no YouTube e exportar (Chrome)",
                                             self.assisted_export, width=290)
        self.btn_assist_now = T.primary_button(actions, "Já entrei — exportar agora",
                                               self._assist_finish, width=210, height=34)
        self.btn_assist_cancel = T.ghost_button(actions, "Cancelar", self._assist_cancel, width=90)

        result = ctk.CTkFrame(card, fg_color="transparent")
        result.grid(row=6, column=1, columnspan=2, sticky="w", pady=(6, 18))
        self.cookie_badge = Badge(result, "Não testado", "neutral")
        self.cookie_badge.pack(anchor="w")
        self.cookie_detail = T.label(result, "", "caption", T.MUTED, wraplength=720)
        self.cookie_detail.pack(anchor="w", pady=(4, 0))

        # --- cookies.txt antigo ao lado do script ---
        self.legacy_box = ctk.CTkFrame(card, fg_color=T.BADGE_COLORS["warning"][0], corner_radius=T.RADIUS_CONTROL)
        T.label(self.legacy_box,
                f"Há um {LEGACY_COOKIES_FILE.name} solto ao lado do script. Ele contém sua sessão do "
                "navegador: guarde-o na pasta data/ (fora do que você compartilha).",
                "caption", T.BADGE_COLORS["warning"][1], wraplength=560).pack(side="left", padx=14, pady=10)
        T.secondary_button(self.legacy_box, "Mover para data/ e usar", self.move_legacy_cookies,
                           width=190).pack(side="right", padx=10, pady=8)

    def _apply_cookie_visibility(self):
        mode = self.settings.cookie_mode
        assisted = self._assist_browser()
        if mode == "browser":
            self.browser_box.grid(row=3, column=0, columnspan=3, sticky="ew")
        else:
            self.browser_box.grid_remove()
        # Ler direto do disco não funciona com Chrome/Edge/Brave (App-Bound
        # Encryption); para eles só a exportação assistida é oferecida.
        if mode == "browser" and self.settings.cookie_browser not in ASSISTED_BROWSERS:
            self.btn_export.pack(side="left", padx=8)
        else:
            self.btn_export.pack_forget()
        if mode != "none" and self._session is None:
            label = {"chrome": "Chrome", "edge": "Edge", "brave": "Brave"}[assisted]
            self.btn_assist.configure(text=f"Entrar no YouTube e exportar ({label})")
            self.btn_assist.pack(side="left", padx=8)
        elif self._session is None:
            self.btn_assist.pack_forget()
        if mode == "file":
            self.file_box.grid(row=4, column=0, columnspan=3, sticky="ew")
        else:
            self.file_box.grid_remove()
        self.btn_test.configure(state="disabled" if mode == "none" else "normal")
        self.file_label.configure(text=truncate_text(self.settings.cookie_file, 70) or "nenhum arquivo escolhido")

        legacy = LEGACY_COOKIES_FILE.is_file()
        if legacy:
            self.legacy_box.grid(row=7, column=0, columnspan=3, sticky="ew", padx=22, pady=(0, 18))
        else:
            self.legacy_box.grid_remove()

    def _cookies_changed(self):
        self._save()
        self._apply_cookie_visibility()
        self.cookie_badge.set("Não testado", "neutral")
        self.cookie_detail.configure(text="")
        self.app.update_cookie_badge()

    def _on_cookie_mode(self, label):
        self.settings.cookie_mode = next(k for k, v in COOKIE_MODE_LABELS.items() if v == label)
        self._cookies_changed()

    def _on_browser(self, label):
        self.settings.cookie_browser = next(key for lbl, key in BROWSERS if lbl == label)
        self.settings.cookie_profile = ""
        self.profile.set("")
        self._refresh_profiles()
        self._cookies_changed()

    def _refresh_profiles(self):
        profiles = list_profiles(self.settings.cookie_browser)
        names = [name for _folder, name in profiles]
        self.profile.configure(values=names or [""])
        if profiles:
            self.profile_hint.configure(text=f"{len(profiles)} perfil(is) encontrado(s)")
        elif self.settings.cookie_browser == "firefox":
            self.profile_hint.configure(text="vazio = perfil mais usado")
        else:
            self.profile_hint.configure(text="navegador não encontrado")

    def _on_profile(self, _event=None):
        value = self.profile.get().strip()
        if value != self.settings.cookie_profile:
            self.settings.cookie_profile = value
            self._cookies_changed()

    def choose_cookie_file(self):
        selected = filedialog.askopenfilename(
            title="Selecionar cookies.txt", initialdir=str(DATA_DIR if DATA_DIR.exists() else Path.home()),
            filetypes=[("Cookies TXT", "*.txt"), ("Todos os arquivos", "*.*")],
        )
        if not selected:
            return
        self.settings.cookie_file = str(Path(selected).resolve())
        self._cookies_changed()
        self.show_report(validate_cookie_file(self.settings.cookie_file))

    def show_report(self, report):
        self.cookie_badge.set(report.summary, REPORT_BADGE.get(report.level, "neutral"))
        self.cookie_detail.configure(text=report.detail)
        self.app.update_cookie_badge(report)

    def test_cookies(self):
        self._on_profile()
        config = CookieConfig.from_settings(self.settings)
        self.btn_test.configure(state="disabled", text="Testando…")
        self.cookie_badge.set("Testando…", "info")
        self.cookie_detail.configure(text="Lendo os cookies; com o navegador isso pode levar alguns segundos.")

        def done(report):
            self.btn_test.configure(state="normal", text="Testar cookies")
            self.show_report(report)

        def failed(exc):
            self.btn_test.configure(state="normal", text="Testar cookies")
            self.cookie_badge.set("Falha ao ler cookies", "danger")
            self.cookie_detail.configure(text=str(exc))

        self.app.run_task(lambda: check_cookies(config), done, failed)

    def export_cookies(self):
        self._on_profile()
        config = CookieConfig.from_settings(self.settings)
        self.btn_export.configure(state="disabled", text="Exportando…")

        def done(result):
            report, path = result
            self.btn_export.configure(state="normal", text="Exportar do navegador → cookies.txt")
            if path:
                self.settings.cookie_mode = "file"
                self.settings.cookie_file = path
                self._save()
                self.load_from_settings()
                self.app.toast("Cookies do YouTube exportados. O modo mudou para 'Arquivo'.", "success", 5000)
            self.show_report(report)

        def failed(exc):
            self.btn_export.configure(state="normal", text="Exportar do navegador → cookies.txt")
            self.cookie_badge.set("Falha ao exportar", "danger")
            self.cookie_detail.configure(text=str(exc))

        self.app.run_task(lambda: export_youtube_cookies(config, EXPORTED_COOKIES_FILE), done, failed)

    # ========================================================
    # EXPORTAÇÃO ASSISTIDA (Chrome/Edge/Brave)
    # ========================================================
    def _assist_browser(self):
        browser = self.settings.cookie_browser
        return browser if browser in ASSISTED_BROWSERS else "chrome"

    def _assist_ui(self, running):
        if running:
            self.btn_assist.pack_forget()
            self.btn_test.configure(state="disabled")
            self.btn_assist_now.pack(side="left", padx=8)
            self.btn_assist_cancel.pack(side="left")
        else:
            self.btn_assist_now.pack_forget()
            self.btn_assist_cancel.pack_forget()
            self.btn_assist_now.configure(state="normal", text="Já entrei — exportar agora")
            self._apply_cookie_visibility()

    def assisted_export(self):
        try:
            session = BrowserSession(self._assist_browser())
        except (RuntimeError, ValueError) as exc:
            self.cookie_badge.set("Navegador não encontrado", "danger")
            self.cookie_detail.configure(text=str(exc))
            return
        self._session = session
        self._assist_ui(True)
        self.cookie_badge.set("Abrindo o navegador…", "info")
        self.cookie_detail.configure(text="")

        def started(_):
            if self._session is not session:
                return
            self.cookie_badge.set("Aguardando login…", "info")
            self.cookie_detail.configure(text=(
                "Abri uma janela separada do navegador, com um perfil só do MediaLoader (seus perfis "
                "normais não são tocados). Entre na sua conta do YouTube nela. A exportação acontece "
                "sozinha quando o login for detectado, ou clique em 'Já entrei'. Depois a janela fecha "
                "sozinha. Nas próximas vezes o login já estará salvo e a exportação é imediata."))
            self._poll_deadline = time.time() + 15 * 60
            self._assist_poll()

        self.app.run_task(session.start, started, self._assist_failed)

    def _assist_poll(self):
        session = self._session
        if session is None:
            return
        if time.time() > self._poll_deadline:
            self._assist_failed(RuntimeError("Tempo esgotado (15 min) esperando o login."))
            return

        def checked(logged_in):
            if self._session is not session:
                return
            if logged_in:
                self._assist_finish()
            else:
                self.after(2000, self._assist_poll)

        self.app.run_task(session.logged_in, checked, self._assist_failed)

    def _assist_finish(self):
        session = self._session
        if session is None:
            return
        self._session = None  # interrompe o polling
        self.btn_assist_now.configure(state="disabled", text="Exportando…")

        def done(result):
            path, count = result
            self.settings.cookie_mode = "file"
            self.settings.cookie_file = str(path)
            self._save()
            self.load_from_settings()
            self._assist_ui(False)
            self.show_report(validate_cookie_file(path))
            self.app.toast(f"{count} cookies do YouTube exportados. Modo alterado para 'Arquivo'.", "success", 6000)

        def failed(exc):
            self._session = session
            self._assist_failed(exc)

        self.app.run_task(lambda: session.export(EXPORTED_COOKIES_FILE), done, failed)

    def _assist_failed(self, exc):
        session, self._session = self._session, None
        if session is not None:
            self.app.run_task(session.close, None, lambda _e: None)
        self._assist_ui(False)
        self.cookie_badge.set("Exportação não concluída", "danger")
        self.cookie_detail.configure(text=str(exc))

    def _assist_cancel(self):
        session, self._session = self._session, None
        if session is not None:
            self.app.run_task(session.close, None, lambda _e: None)
        self._assist_ui(False)
        self.cookie_badge.set("Cancelado", "neutral")
        self.cookie_detail.configure(text="")

    def move_legacy_cookies(self):
        target = DATA_DIR / LEGACY_COOKIES_FILE.name
        if target.exists() and not messagebox.askyesno(
                "Substituir", f"Já existe {target}. Substituir pelo arquivo ao lado do script?"):
            return
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(LEGACY_COOKIES_FILE), str(target))
        except OSError as exc:
            messagebox.showerror("Cookies", f"Não foi possível mover o arquivo: {exc}")
            return
        self.settings.cookie_mode = "file"
        self.settings.cookie_file = str(target)
        self._save()
        self.load_from_settings()
        self.show_report(validate_cookie_file(target))
        self.app.toast(f"cookies.txt movido para {target.parent.name}/ e selecionado.", "success")

    # ========================================================
    # SINCRONIZAÇÃO
    # ========================================================
    def load_from_settings(self):
        s = self.settings
        self.folder_label.configure(text=truncate_text(s.download_folder, 70))
        self.sw_subfolder.select() if s.playlist_subfolder else self.sw_subfolder.deselect()
        self.format.set(FORMAT_SHORT[s.audio_format])
        self.format_hint.configure(text=AUDIO_FORMATS[s.audio_format][0])
        self.template.set(NAME_TEMPLATES[s.name_template][0])
        self.sw_sponsor.select() if s.sponsorblock else self.sw_sponsor.deselect()
        self.sw_m3u.select() if s.write_m3u else self.sw_m3u.deselect()
        self.sw_auto_phone.select() if s.phone_auto_send else self.sw_auto_phone.deselect()
        if self.speed.get():
            self.speed.delete(0, "end")
        if s.speed_limit_mb:
            self.speed.insert(0, s.speed_limit_mb)
        self.cookie_mode.set(COOKIE_MODE_LABELS[s.cookie_mode])
        self.browser.set(next((lbl for lbl, key in BROWSERS if key == s.cookie_browser), BROWSERS[0][0]))
        self._refresh_profiles()
        self.profile.set(s.cookie_profile or "")
        self._apply_cookie_visibility()

    def on_show(self):
        self.load_from_settings()
