import math
from tkinter import messagebox

import customtkinter as ctk

from .. import theme as T
from ..config import ITEMS_PER_PAGE
from ..library import DOWNLOADED, LOCAL, MISSING_FILE, NEW, STATUS_LABELS, UNAVAILABLE
from ..utils import format_duration, parse_positive_int, truncate_text
from .base import Screen
from .widgets import Badge, EmptyState, PageHeader, Paginator, RowPool, clear_entry, scroll_to_top

STATUS_BADGE = {
    NEW: "success",
    DOWNLOADED: "neutral",
    LOCAL: "info",
    MISSING_FILE: "warning",
    UNAVAILABLE: "danger",
}

FILTERS = {
    "Todos": None,
    "Novos": {NEW},
    "Na pasta": {LOCAL},
    "Baixados": {DOWNLOADED, MISSING_FILE},
    "Indisponíveis": {UNAVAILABLE},
}


class SelectionRow(ctk.CTkFrame):
    def __init__(self, parent, screen):
        super().__init__(parent, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_CONTROL, height=52)
        self.screen = screen
        self.entry = None
        self.visible_index = 0
        self.grid_columnconfigure(2, weight=1)

        self.var = ctk.IntVar(value=0)
        self.checkbox = T.checkbox(self, "", variable=self.var, width=24, command=self._on_check)
        self.checkbox.grid(row=0, column=0, rowspan=2, padx=(12, 4), pady=8)

        self.pos = T.label(self, "", "mono", T.SUBTLE, width=44, anchor="e")
        self.pos.grid(row=0, column=1, rowspan=2, padx=(0, 12))

        self.title = T.label(self, "", "bold", height=20)
        self.title.grid(row=0, column=2, sticky="sw", pady=(8, 0))
        self.uploader = T.label(self, "", "caption", T.MUTED, height=16)
        self.uploader.grid(row=1, column=2, sticky="nw", pady=(0, 8))

        self.duration = T.label(self, "", "mono", T.MUTED, width=64, anchor="e")
        self.duration.grid(row=0, column=3, rowspan=2, padx=8)

        self.badge = Badge(self, "", "neutral", width=96)
        self.badge.grid(row=0, column=4, rowspan=2, padx=(4, 14))

        for widget in (self, self.title, self.uploader, self.pos):
            widget.bind("<Button-1>", self._on_click)

    def bind_item(self, entry, visible_index):
        self.entry = entry
        self.visible_index = visible_index
        status = entry.get("status", NEW)
        self.var.set(1 if self.screen.selected.get(entry["id"]) else 0)
        self.pos.configure(text=str(entry["position"]))
        self.title.configure(
            text=truncate_text(entry["title"], 90),
            text_color=T.TEXT if status in (NEW, MISSING_FILE) else T.MUTED,
        )
        self.uploader.configure(text=entry.get("uploader") or " ")
        self.duration.configure(text=format_duration(entry.get("duration")))
        self.badge.set(STATUS_LABELS[status], STATUS_BADGE[status])

    def _on_click(self, _event):
        self.var.set(0 if self.var.get() else 1)
        self._on_check()

    def _on_check(self):
        self.screen.on_row_toggle(self)


class SelectionScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.result = None
        self.entries = []
        self.filtered = []
        self.selected = {}
        self.page = 0
        self.last_clicked = None
        self._search_job = None

        # ---------------- cabeçalho ----------------
        self.header = PageHeader(self, "Seleção", "Nenhuma playlist carregada.")
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.btn_download = T.primary_button(self.header.actions, "↓  Baixar selecionadas", self.start_download,
                                             width=220, height=42)
        self.btn_download.pack(side="right")
        self.btn_save = T.secondary_button(self.header.actions, "☆  Salvar playlist", self.save_playlist,
                                           width=170, height=42)

        # ---------------- busca + filtros ----------------
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)

        self.search = T.entry(toolbar, "Buscar por título ou canal…  (Ctrl+F)")
        self.search.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.search.bind("<KeyRelease>", self._on_search_key)

        self.filter = T.segmented(toolbar, FILTERS.keys(), command=lambda _v: self.apply_filter())
        self.filter.set("Todos")
        self.filter.grid(row=0, column=1)

        # ---------------- intervalo + ações ----------------
        bar = T.card(self)
        bar.grid(row=2, column=0, sticky="ew", pady=12)
        T.label(bar, "Intervalo da playlist", "bold").pack(side="left", padx=(16, 10), pady=12)
        self.range_start = T.entry(bar, "Início", width=80)
        self.range_start.pack(side="left")
        T.label(bar, "até", "body", T.MUTED).pack(side="left", padx=8)
        self.range_end = T.entry(bar, "Fim", width=80)
        self.range_end.pack(side="left")
        self.range_end.bind("<Return>", lambda _e: self.select_interval())
        self.only_new = ctk.BooleanVar(value=True)
        T.checkbox(bar, "Só novos", variable=self.only_new).pack(side="left", padx=14)
        T.secondary_button(bar, "Selecionar intervalo", self.select_interval, width=150).pack(side="left")

        T.ghost_button(bar, "Desmarcar todos", self.deselect_all, width=120).pack(side="right", padx=(4, 12))
        T.ghost_button(bar, "Marcar todos", self.select_all, width=110).pack(side="right")

        # ---------------- lista ----------------
        self.list_frame = T.scrollable(self)
        self.list_frame.grid(row=3, column=0, sticky="nsew")
        self.pool = RowPool(self.list_frame, lambda parent: SelectionRow(parent, self),
                            dict(fill="x", padx=6, pady=3))
        self.empty = EmptyState(
            self.list_frame, "☰", "Nenhuma playlist carregada",
            "Cole a URL de uma playlist ou vídeo na tela Início.",
            "Ir para Início", lambda: self.app.new_download(),
        )
        self.empty.pack(fill="both", expand=True)

        # ---------------- rodapé ----------------
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        footer.grid_columnconfigure(1, weight=1)
        self.summary = T.label(footer, "", "body", T.MUTED)
        self.summary.grid(row=0, column=0, sticky="w")
        self.paginator = Paginator(footer, self.goto_page)
        self.paginator.grid(row=0, column=1)
        self.page_info = T.label(footer, "", "caption", T.SUBTLE)
        self.page_info.grid(row=0, column=2, sticky="e")

        self._update_summary()

    # ========================================================
    # DADOS
    # ========================================================
    def set_playlist(self, result, select_ids=None):
        self.result = result
        self.entries = result.entries
        if select_ids is None:
            self.selected = {e["id"]: e.get("status") == NEW for e in self.entries}
        else:
            select_ids = set(select_ids)
            self.selected = {e["id"]: e["id"] in select_ids for e in self.entries}
        clear_entry(self.search)
        self.filter.set("Todos")
        self._update_header()
        self._update_save_button()
        self.apply_filter()

    def refresh_statuses(self):
        """Chamado após downloads/recarga da pasta: o que já existe sai da seleção."""
        if not self.entries:
            return
        for entry in self.entries:
            if entry.get("status") != NEW and entry.get("status") != MISSING_FILE:
                self.selected[entry["id"]] = False
        self._update_header()
        self.apply_filter(keep_page=True)

    def _update_save_button(self):
        if not self.result or not self.result.is_playlist:
            self.btn_save.pack_forget()
            return
        self.btn_save.pack(side="right", padx=(0, 8))
        saved = self.app.playlists.is_saved(self.result.url)
        self.btn_save.configure(text="★  Playlist salva" if saved else "☆  Salvar playlist",
                                state="disabled" if saved else "normal")

    def save_playlist(self):
        if self.result:
            self.app.save_playlist(self.result)
            self._update_save_button()

    def _update_header(self):
        if not self.result:
            return
        counts = {status: 0 for status in STATUS_LABELS}
        for entry in self.entries:
            counts[entry.get("status", NEW)] += 1
        kind = "Playlist" if self.result.is_playlist else "Vídeo"
        self.header.set_title(truncate_text(self.result.title, 60))
        parts = [f"{kind} · {len(self.entries)} item(ns)", f"{counts[NEW]} novos"]
        if counts[LOCAL]:
            parts.append(f"{counts[LOCAL]} já na pasta")
        parts.append(f"{counts[DOWNLOADED] + counts[MISSING_FILE]} baixados")
        if counts[UNAVAILABLE]:
            parts.append(f"{counts[UNAVAILABLE]} indisponíveis")
        self.header.set_subtitle(" · ".join(parts))

    def _on_search_key(self, _event):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(200, self.apply_filter)

    def apply_filter(self, keep_page=False):
        self._search_job = None
        allowed = FILTERS.get(self.filter.get())
        query = self.search.get().strip().casefold()
        self.filtered = [
            e for e in self.entries
            if (allowed is None or e.get("status") in allowed)
            and (not query or query in e["title"].casefold() or query in (e.get("uploader") or "").casefold())
        ]
        self.goto_page(self.page if keep_page else 0)

    @property
    def total_pages(self):
        return max(1, math.ceil(len(self.filtered) / ITEMS_PER_PAGE))

    def goto_page(self, page):
        self.page = max(0, min(page, self.total_pages - 1))
        self.render()

    def render(self):
        self.last_clicked = None
        if not self.entries:
            self.pool.render([])
            self.empty.pack(fill="both", expand=True)
            self.paginator.update_pages(0, 0)
            self._update_summary()
            return

        if not self.filtered:
            self.empty.set_text("Nada encontrado", "Nenhum item corresponde à busca ou ao filtro atual.")
            self.empty.pack(fill="both", expand=True)
        else:
            self.empty.pack_forget()
        start = self.page * ITEMS_PER_PAGE
        self.pool.render(self.filtered[start:start + ITEMS_PER_PAGE])
        scroll_to_top(self.list_frame)
        self.paginator.update_pages(self.page, self.total_pages)
        end = min(start + ITEMS_PER_PAGE, len(self.filtered))
        self.page_info.configure(text=f"{start + 1 if self.filtered else 0}–{end} de {len(self.filtered)}")
        self._update_summary()

    def _update_summary(self):
        chosen = [e for e in self.entries if self.selected.get(e["id"])]
        seconds = sum(int(e.get("duration") or 0) for e in chosen)
        duration = format_duration(seconds)
        self.summary.configure(
            text=f"{len(chosen)} selecionada(s)" + (f" · ~{duration}" if duration else ""))
        self.btn_download.configure(
            text=f"↓  Baixar selecionadas ({len(chosen)})",
            state="normal" if chosen else "disabled",
        )

    # ========================================================
    # SELEÇÃO
    # ========================================================
    def on_row_toggle(self, row):
        state = bool(row.var.get())
        self.selected[row.entry["id"]] = state
        if self.app.shift_pressed and self.last_clicked is not None:
            rows = self.pool.visible_rows()
            low, high = sorted((self.last_clicked, row.visible_index))
            for other in rows[low:high + 1]:
                other.var.set(1 if state else 0)
                self.selected[other.entry["id"]] = state
        self.last_clicked = row.visible_index
        self._update_summary()

    def _set_filtered(self, state):
        for entry in self.filtered:
            self.selected[entry["id"]] = state
        for row in self.pool.visible_rows():
            row.var.set(1 if state else 0)
        self._update_summary()

    def select_all(self):
        self._set_filtered(True)

    def deselect_all(self):
        self._set_filtered(False)

    def focus_search(self):
        self.search.focus_set()
        self.search.select_range(0, "end")

    def select_interval(self):
        if not self.entries:
            self.app.toast("Carregue uma playlist primeiro.", "warning")
            return
        try:
            start = parse_positive_int(self.range_start.get(), "Início")
            end = parse_positive_int(self.range_end.get(), "Fim")
        except ValueError as exc:
            messagebox.showerror("Intervalo inválido", str(exc))
            return
        if start > end:
            messagebox.showerror("Intervalo inválido", "O início não pode ser maior que o fim.")
            return
        max_pos = max(e["position"] for e in self.entries)
        if start > max_pos:
            messagebox.showwarning("Fora da playlist", f"O início {start} é maior que a última posição ({max_pos}).")
            return
        end = min(end, max_pos)
        only_new = bool(self.only_new.get())

        count = 0
        for entry in self.entries:
            status = entry.get("status")
            chosen = (
                start <= entry["position"] <= end
                and status != UNAVAILABLE
                and (not only_new or status == NEW)
            )
            self.selected[entry["id"]] = chosen
            count += chosen

        # Mostra a página onde o intervalo começa.
        clear_entry(self.search)
        self.filter.set("Todos")
        self.filtered = list(self.entries)
        first = next((i for i, e in enumerate(self.filtered) if e["position"] >= start), 0)
        self.goto_page(first // ITEMS_PER_PAGE)
        suffix = " (só novos)" if only_new else ""
        self.app.toast(f"Intervalo {start}–{end}{suffix}: {count} item(ns) selecionado(s).", "success")

    # ========================================================
    # DOWNLOAD
    # ========================================================
    def start_download(self):
        chosen = [e for e in self.entries if self.selected.get(e["id"])]
        if not chosen:
            self.app.toast("Nenhum item selecionado.", "warning")
            return
        title = self.result.title if self.result and self.result.is_playlist else None
        self.app.start_download(chosen, title, self.entries if title else None)
