import math
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

from .. import theme as T
from ..config import ITEMS_PER_PAGE
from ..downloader import INSTALL_COMMANDS, update_ytdlp
from ..errors import friendly_error
from ..library import DOWNLOADED, LOCAL, MISSING_FILE, NEW, STATUS_LABELS, UNAVAILABLE
from ..utils import truncate_text
from .base import Screen
from .library_tab import LibraryTab
from .selection import STATUS_BADGE
from .widgets import Badge, EmptyState, PageHeader, Paginator, RowPool, StatChip, scroll_to_top

VIEWS = {
    "Faltando": {NEW},
    "Na pasta (sem registro)": {LOCAL},
    "Removidos do disco": {MISSING_FILE},
    "Indisponíveis": {UNAVAILABLE},
}


class DiagRow(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_CONTROL)
        self.entry = None
        self.grid_columnconfigure(1, weight=1)
        self.pos = T.label(self, "", "mono", T.SUBTLE, width=44, anchor="e")
        self.pos.grid(row=0, column=0, rowspan=2, padx=(12, 12))
        self.title = T.label(self, "", "bold", height=20)
        self.title.grid(row=0, column=1, sticky="sw", pady=(8, 0))
        self.detail = T.label(self, "", "caption", T.MUTED, height=16)
        self.detail.grid(row=1, column=1, sticky="nw", pady=(0, 8))
        self.badge = Badge(self, "", "neutral", width=96)
        self.badge.grid(row=0, column=2, rowspan=2, padx=8)
        T.ghost_button(self, "Abrir ↗", self._open, width=70, height=28).grid(
            row=0, column=3, rowspan=2, padx=(0, 10))

    def bind_item(self, entry, _index):
        self.entry = entry
        status = entry["status"]
        self.pos.configure(text=str(entry["position"]))
        self.title.configure(text=truncate_text(entry["title"], 90))
        detail = entry.get("uploader") or ""
        if status == LOCAL:
            detail = f"Arquivo: {entry.get('_match', '')}"
        self.detail.configure(text=f"{detail}   ·   youtu.be/{entry['id']}" if detail else f"youtu.be/{entry['id']}")
        self.badge.set(STATUS_LABELS[status], STATUS_BADGE[status])

    def _open(self):
        if self.entry:
            webbrowser.open(f"https://youtu.be/{self.entry['id']}")


class DiagnosticsScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.result = None
        self.filtered = []
        self.page = 0

        PageHeader(self, "Diagnóstico",
                   "Compare uma playlist online com a pasta local e confira o ambiente do yt-dlp.").grid(
            row=0, column=0, sticky="ew", pady=(0, 8))

        self.tabs = ctk.CTkTabview(
            self, fg_color="transparent", segmented_button_fg_color=T.SURFACE_2,
            segmented_button_selected_color=T.ACCENT, segmented_button_selected_hover_color=T.ACCENT_HOVER,
            segmented_button_unselected_color=T.SURFACE_2, segmented_button_unselected_hover_color=T.SURFACE_3,
            text_color=T.TEXT, anchor="w",
        )
        self.tabs.grid(row=1, column=0, sticky="nsew")
        self.tabs._segmented_button.configure(font=T.body("bold"), height=34)
        self._build_playlist_tab(self.tabs.add("Playlist"))
        self.library_tab = LibraryTab(self.tabs.add("Biblioteca"), app)
        self._build_env_tab(self.tabs.add("Ambiente"))

    # ========================================================
    # ABA PLAYLIST
    # ========================================================
    def _build_playlist_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(4, weight=1)

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(4, 12))
        bar.grid_columnconfigure(0, weight=1)
        self.url_box = ctk.CTkComboBox(
            bar, values=[""], height=40, corner_radius=T.RADIUS_CONTROL, border_width=1,
            fg_color=T.SURFACE_2, border_color=T.BORDER, button_color=T.SURFACE_3,
            button_hover_color="#363636", dropdown_fg_color=T.SURFACE_2,
            dropdown_hover_color=T.SURFACE_3, font=T.body(), dropdown_font=T.body(), text_color=T.TEXT,
        )
        self.url_box.set("")
        self.url_box.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.url_box.bind("<Return>", lambda _e: self.start())
        self.btn_check = T.primary_button(bar, "Verificar", self.start, width=130, height=40)
        self.btn_check.grid(row=0, column=1)
        self.status = T.label(tab, "Cole a URL da playlist que você quer comparar com a pasta.", "caption", T.SUBTLE)
        self.status.grid(row=1, column=0, sticky="w", pady=(0, 10))

        stats = ctk.CTkFrame(tab, fg_color="transparent")
        stats.grid(row=2, column=0, sticky="ew")
        stats.grid_columnconfigure(tuple(range(5)), weight=1, uniform="diag")
        self.chips = {
            "total": StatChip(stats, "na playlist"),
            DOWNLOADED: StatChip(stats, "baixadas", T.MUTED),
            LOCAL: StatChip(stats, "na pasta, sem registro", T.INFO),
            NEW: StatChip(stats, "faltando", T.SUCCESS),
            UNAVAILABLE: StatChip(stats, "indisponíveis", T.DANGER),
        }
        for col, chip in enumerate(self.chips.values()):
            chip.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))

        actions = ctk.CTkFrame(tab, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", pady=12)
        self.btn_download = T.primary_button(actions, "↓  Baixar faltantes", self.download_missing, width=200)
        self.btn_download.pack(side="left")
        self.btn_register = T.secondary_button(actions, "Registrar 'na pasta' no histórico",
                                               self.register_local, width=250)
        self.btn_register.pack(side="left", padx=8)
        self.view = T.segmented(actions, VIEWS.keys(), command=lambda _v: self.apply_view())
        self.view.set("Faltando")
        self.view.pack(side="right")

        list_area = ctk.CTkFrame(tab, fg_color="transparent")
        list_area.grid(row=4, column=0, sticky="nsew")
        list_area.grid_columnconfigure(0, weight=1)
        list_area.grid_rowconfigure(0, weight=1)
        self.list_frame = T.scrollable(list_area)
        self.list_frame.grid(row=0, column=0, sticky="nsew")
        self.pool = RowPool(self.list_frame, DiagRow, dict(fill="x", padx=6, pady=3))
        self.empty = EmptyState(self.list_frame, "✓", "Nenhuma verificação ainda",
                                "O resultado aparece aqui, separado por situação.")
        self.empty.pack(fill="both", expand=True)
        self.paginator = Paginator(list_area, self.goto_page)
        self.paginator.grid(row=1, column=0, pady=(10, 0))
        self._update_actions()

    def on_show(self):
        history = self.app.settings.url_history
        self.url_box.configure(values=history or [""])
        if not self.url_box.get() and history:
            self.url_box.set(history[0])

    def start(self):
        url = self.url_box.get().strip()
        if not url:
            self.status.configure(text="Cole uma URL primeiro.", text_color=T.WARNING)
            return
        self.btn_check.configure(state="disabled", text="Verificando…")
        self.status.configure(text="Consultando a playlist e a pasta local…", text_color=T.TEXT)

        def failed(exc):
            self.btn_check.configure(state="normal", text="Verificar")
            self.status.configure(text=f"Erro: {friendly_error(str(exc)) or exc}", text_color=T.DANGER)

        self.app.fetch_playlist(url, self.show_result, failed)

    def show_result(self, result):
        self.btn_check.configure(state="normal", text="Verificar")
        self.result = result
        self.refresh_counts()
        missing = sum(1 for e in result.entries if e["status"] == NEW)
        self.status.configure(
            text=f"{result.title}: {missing} faltando de {len(result.entries)}.",
            text_color=T.SUCCESS if not missing else T.WARNING,
        )
        self.view.set("Faltando")
        self.apply_view()

    def refresh_counts(self):
        entries = self.result.entries if self.result else []
        for entry in entries:
            if entry["status"] == LOCAL:
                entry["_match"] = self.app.library.local_match(entry["title"]) or ""
        self.chips["total"].set(len(entries))
        for status in (DOWNLOADED, LOCAL, NEW, UNAVAILABLE):
            count = sum(1 for e in entries if e["status"] == status)
            if status == DOWNLOADED:
                count += sum(1 for e in entries if e["status"] == MISSING_FILE)
            self.chips[status].set(count)
        self._update_actions()

    def _update_actions(self):
        entries = self.result.entries if self.result else []
        missing = sum(1 for e in entries if e["status"] == NEW)
        local = sum(1 for e in entries if e["status"] == LOCAL)
        self.btn_download.configure(text=f"↓  Baixar faltantes ({missing})", state="normal" if missing else "disabled")
        self.btn_register.configure(text=f"Registrar 'na pasta' no histórico ({local})",
                                    state="normal" if local else "disabled")

    def apply_view(self):
        allowed = VIEWS[self.view.get()]
        entries = self.result.entries if self.result else []
        self.filtered = [e for e in entries if e["status"] in allowed]
        self.goto_page(0)

    def goto_page(self, page):
        pages = max(1, math.ceil(len(self.filtered) / ITEMS_PER_PAGE))
        self.page = max(0, min(page, pages - 1))
        start = self.page * ITEMS_PER_PAGE
        visible = self.filtered[start:start + ITEMS_PER_PAGE]
        if visible:
            self.empty.pack_forget()
        else:
            if self.result:
                self.empty.set_text("Nada aqui 🎉", "Nenhum item nessa situação.")
            self.empty.pack(fill="both", expand=True)
        self.pool.render(visible)
        scroll_to_top(self.list_frame)
        self.paginator.update_pages(self.page, pages)

    def download_missing(self):
        if not self.result:
            return
        ids = [e["id"] for e in self.result.entries if e["status"] == NEW]
        self.app.open_playlist(self.result, select_ids=ids)
        self.app.toast(f"{len(ids)} item(ns) faltante(s) marcados. Revise e clique em Baixar.", "info")

    def register_local(self):
        if not self.result:
            return
        local = [e for e in self.result.entries if e["status"] == LOCAL]
        if not messagebox.askyesno(
                "Registrar no histórico",
                f"{len(local)} item(ns) foram encontrados na pasta pelo título, mas não estão no "
                ".archive.txt.\n\nRegistrá-los evita que sejam baixados de novo. Continuar?"):
            return
        added = self.app.library.register_local(local)
        self.app.annotate(self.result.entries)
        self.refresh_counts()
        self.apply_view()
        self.app.screens["dashboard"].refresh_summary()
        if self.app.playlist is self.result:
            self.app.screens["selection"].refresh_statuses()
        self.app.toast(f"{added} item(ns) registrados no histórico.", "success")

    # ========================================================
    # ABA AMBIENTE
    # ========================================================
    def _build_env_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        card = T.card(tab)
        card.grid(row=0, column=0, sticky="ew", pady=(4, 12))
        card.grid_columnconfigure(1, weight=1)

        self.env_rows = {}
        specs = (
            ("ytdlp", "yt-dlp", "Faz a extração e o download.", "ytdlp"),
            ("ffmpeg", "FFmpeg", "Converte o áudio e embute capa/metadados.", "ffmpeg"),
            ("deno", "Deno", "Runtime JavaScript para os desafios do YouTube.", "deno"),
            ("ejs", "yt-dlp-ejs", "Solucionador dos desafios (vem com yt-dlp[default]).", "ytdlp"),
        )
        for row, (key, name, text, command_key) in enumerate(specs):
            T.label(card, name, "bold", width=110).grid(row=row * 2, column=0, sticky="w", padx=(20, 12),
                                                       pady=(14, 0))
            detail = T.label(card, text, "caption", T.MUTED)
            detail.grid(row=row * 2 + 1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 12))
            value = T.label(card, "…", "mono", T.TEXT)
            value.grid(row=row * 2, column=1, sticky="w", pady=(14, 0))
            badge = Badge(card, "…", "neutral", width=90)
            badge.grid(row=row * 2, column=2, padx=8, pady=(14, 0))
            T.ghost_button(card, "Copiar comando", lambda c=command_key: self._copy(INSTALL_COMMANDS[c]),
                           width=130, height=28).grid(row=row * 2, column=3, padx=(0, 16), pady=(14, 0))
            self.env_rows[key] = (value, badge)

        buttons = ctk.CTkFrame(tab, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="w")
        T.secondary_button(buttons, "⟳  Verificar novamente",
                           lambda: self.app.refresh_env(force=True), width=180).pack(side="left")
        self.btn_update = T.primary_button(buttons, "Atualizar yt-dlp", self.update_ytdlp, width=170, height=34)
        self.btn_update.pack(side="left", padx=8)

        self.update_output = ctk.CTkTextbox(tab, height=160, font=T.mono(11), fg_color=T.BG,
                                            text_color=T.MUTED, border_width=1, border_color=T.BORDER)
        self.update_output.grid(row=2, column=0, sticky="ew", pady=12)
        self.update_output.insert("end", "A saída do pip aparece aqui.\n")
        self.update_output.configure(state="disabled")

    def show_env(self, env):
        def put(key, value, ok):
            label, badge = self.env_rows[key]
            label.configure(text=value)
            badge.set("OK" if ok else "AUSENTE", "success" if ok else "danger")

        put("ytdlp", env.ytdlp_version, True)
        put("ffmpeg", env.ffmpeg or "não encontrado no PATH", bool(env.ffmpeg))
        put("deno", env.deno_version or (env.deno or "não encontrado no PATH"), bool(env.deno))
        put("ejs", "instalado" if env.ejs else "não instalado", env.ejs)

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.toast("Comando copiado.", "success", 2000)

    def _set_update_output(self, text):
        self.update_output.configure(state="normal")
        self.update_output.delete("1.0", "end")
        self.update_output.insert("end", text)
        self.update_output.see("end")
        self.update_output.configure(state="disabled")

    def update_ytdlp(self):
        if self.app.download_running:
            self.app.toast("Espere o download terminar para atualizar.", "warning")
            return
        self.btn_update.configure(state="disabled", text="Atualizando…")
        self._set_update_output("Executando pip install -U \"yt-dlp[default]\"…\n")

        def done(result):
            ok, output = result
            self.btn_update.configure(state="normal", text="Atualizar yt-dlp")
            self._set_update_output(output or "(sem saída)")
            if ok:
                self.app.toast("yt-dlp atualizado. Reinicie o app para usar a nova versão.", "success", 6000)
            else:
                self.app.toast("A atualização falhou. Veja a saída do pip.", "danger", 6000)

        def failed(exc):
            self.btn_update.configure(state="normal", text="Atualizar yt-dlp")
            self._set_update_output(str(exc))

        self.app.run_task(update_ytdlp, done, failed)
