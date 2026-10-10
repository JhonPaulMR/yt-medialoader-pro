from tkinter import filedialog

import customtkinter as ctk

from .. import theme as T
from ..config import AUDIO_FORMATS, NAME_TEMPLATES
from ..errors import friendly_error
from ..utils import open_folder, truncate_text
from .base import Screen
from .widgets import PageHeader, StatChip


class DashboardScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.grid_columnconfigure(0, weight=1)

        PageHeader(self, "Início", "Baixe playlists ou vídeos do YouTube em alta qualidade.").grid(
            row=0, column=0, sticky="ew", pady=(0, 20))

        # ---------------- URL ----------------
        hero = T.card(self)
        hero.grid(row=1, column=0, sticky="ew")
        hero.grid_columnconfigure(0, weight=1)

        T.label(hero, "URL da playlist ou do vídeo", "bold").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=24, pady=(20, 8))

        self.url_box = ctk.CTkComboBox(
            hero, values=[], height=44, corner_radius=T.RADIUS_CONTROL, border_width=1,
            fg_color=T.SURFACE_2, border_color=T.BORDER, button_color=T.SURFACE_3,
            button_hover_color="#363636", dropdown_fg_color=T.SURFACE_2,
            dropdown_hover_color=T.SURFACE_3, font=T.body(), dropdown_font=T.body(),
            text_color=T.TEXT,
        )
        self.url_box.set("")
        self.url_box.grid(row=1, column=0, sticky="ew", padx=(24, 12))
        self.url_box.bind("<Return>", lambda _e: self.load())

        self.btn_load = T.primary_button(hero, "Carregar", self.load, height=44, width=150)
        self.btn_load.grid(row=1, column=1, padx=(0, 24))

        self.status = T.label(hero, "Dica: pressione Enter para carregar. Playlists e vídeos avulsos são aceitos.",
                              "caption", T.SUBTLE)
        self.status.grid(row=2, column=0, columnspan=2, sticky="w", padx=24, pady=(8, 16))

        ctk.CTkFrame(hero, height=1, fg_color=T.BORDER).grid(row=3, column=0, columnspan=2, sticky="ew")

        # Resumo das configurações que afetam o download
        info = ctk.CTkFrame(hero, fg_color="transparent")
        info.grid(row=4, column=0, columnspan=2, sticky="ew", padx=24, pady=16)
        info.grid_columnconfigure(1, weight=1)

        self.folder_label = self._info_row(info, 0, "Pasta", [
            ("Alterar…", self.choose_folder), ("Abrir", self.open_folder)])
        self.format_label = self._info_row(info, 1, "Saída", [
            ("Ajustar", lambda: self.app.navigate("settings"))])
        self.cookie_label = self._info_row(info, 2, "Cookies", [
            ("Configurar", lambda: self.app.navigate("settings"))])

        # ---------------- Biblioteca ----------------
        T.label(self, "BIBLIOTECA LOCAL", "caption", T.SUBTLE).grid(
            row=2, column=0, sticky="w", pady=(26, 8))
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.grid(row=3, column=0, sticky="ew")
        stats.grid_columnconfigure((0, 1, 2), weight=1, uniform="stats")
        self.stat_files = StatChip(stats, "arquivos de áudio na pasta")
        self.stat_archive = StatChip(stats, "IDs no histórico (.archive.txt)")
        self.stat_index = StatChip(stats, "arquivos ligados a um ID (.library.json)")
        for col, chip in enumerate((self.stat_files, self.stat_archive, self.stat_index)):
            chip.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))

        # ---------------- Atalhos ----------------
        T.label(self, "ATALHOS", "caption", T.SUBTLE).grid(row=4, column=0, sticky="w", pady=(26, 8))
        shortcuts = ctk.CTkFrame(self, fg_color="transparent")
        shortcuts.grid(row=5, column=0, sticky="ew")
        shortcuts.grid_columnconfigure((0, 1, 2), weight=1, uniform="short")
        cards = (
            ("✓  Verificar faltantes", "Compare a playlist online com a pasta local.",
             lambda: self.app.navigate("diagnostics")),
            ("✎  Renomeador em massa", "Limpe e padronize os nomes dos arquivos.",
             lambda: self.app.navigate("renamer")),
            ("⚙  Configurações", "Formato, SponsorBlock, M3U e cookies.",
             lambda: self.app.navigate("settings")),
        )
        for col, (title, text, command) in enumerate(cards):
            self._shortcut(shortcuts, title, text, command).grid(
                row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0))

        self.refresh_summary()

    # ---------------- construção ----------------
    def _info_row(self, parent, row, caption, actions):
        T.label(parent, caption.upper(), "caption", T.SUBTLE, width=70).grid(row=row, column=0, sticky="w", pady=3)
        value = T.label(parent, "", "body", T.TEXT)
        value.grid(row=row, column=1, sticky="w", padx=(8, 8), pady=3)
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=row, column=2, sticky="e")
        for text, command in actions:
            T.ghost_button(box, text, command, width=80, height=26).pack(side="left", padx=(4, 0))
        return value

    def _shortcut(self, parent, title, text, command):
        frame = T.card(parent, cursor="hand2")
        title_label = T.label(frame, title, "bold")
        title_label.pack(anchor="w", padx=18, pady=(16, 2))
        text_label = T.label(frame, text, "caption", T.MUTED, wraplength=260)
        text_label.pack(anchor="w", padx=18, pady=(0, 16))

        def on_enter(_e):
            frame.configure(border_color=T.ACCENT)

        def on_leave(_e):
            frame.configure(border_color=T.BORDER)

        for widget in (frame, title_label, text_label):
            widget.bind("<Button-1>", lambda _e: command())
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
        return frame

    # ---------------- estado ----------------
    def on_show(self):
        self.refresh_summary()

    def refresh_summary(self):
        settings = self.app.settings
        current = self.url_box.get()
        self.url_box.configure(values=settings.url_history or [""])
        self.url_box.set(current)
        self.folder_label.configure(text=truncate_text(settings.download_folder, 80))
        fmt = AUDIO_FORMATS[settings.audio_format][0].split(" (")[0]
        parts = [fmt, f"nome: {NAME_TEMPLATES[settings.name_template][0]}"]
        if settings.sponsorblock:
            parts.append("SponsorBlock")
        if settings.write_m3u:
            parts.append("M3U")
        if settings.playlist_subfolder:
            parts.append("subpasta por playlist")
        self.format_label.configure(text=" · ".join(parts))
        self.cookie_label.configure(text=self.app.cookie_config.describe())

        library = self.app.library
        self.stat_files.set(len(library.files))
        self.stat_archive.set(len(library.archive_ids))
        self.stat_index.set(len(library.index))

    def focus_url(self, clear=False):
        if clear:
            self.url_box.set("")
        self.url_box.focus_set()

    def set_status(self, text, color=T.MUTED):
        self.status.configure(text=text, text_color=color)

    # ---------------- ações ----------------
    def load(self):
        url = self.url_box.get().strip()
        if not url:
            self.set_status("Cole uma URL antes de carregar.", T.WARNING)
            self.focus_url()
            return
        self.btn_load.configure(state="disabled", text="Carregando…")
        self.set_status("Lendo a playlist e comparando com a pasta local… playlists grandes levam alguns segundos.",
                        T.TEXT)

        def done(result):
            self.btn_load.configure(state="normal", text="Carregar")
            self.set_status(f"Carregado: {result.title} ({len(result.entries)} item(ns)).", T.SUCCESS)
            self.refresh_summary()
            self.app.open_playlist(result)

        def failed(exc):
            self.btn_load.configure(state="normal", text="Carregar")
            hint = friendly_error(str(exc))
            self.set_status(f"Erro: {hint or exc}", T.DANGER)

        self.app.fetch_playlist(url, done, failed)

    def choose_folder(self):
        selected = filedialog.askdirectory(
            title="Pasta de destino", initialdir=self.app.settings.download_folder, mustexist=False)
        if selected:
            self.app.set_download_folder(selected)
            self.app.toast("Pasta de destino atualizada.", "success")

    def open_folder(self):
        folder = self.app.settings.folder
        folder.mkdir(parents=True, exist_ok=True)
        open_folder(folder)
