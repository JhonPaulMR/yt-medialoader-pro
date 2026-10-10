from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from .. import theme as T
from ..errors import friendly_error
from ..library import NEW
from ..utils import truncate_text
from .base import Screen
from .widgets import Badge, EmptyState, PageHeader


def _fmt_checked(value):
    if not value:
        return "nunca verificada"
    try:
        return "verificada em " + datetime.fromisoformat(value).strftime("%d/%m %H:%M")
    except ValueError:
        return value


class PlaylistCard(ctk.CTkFrame):
    def __init__(self, parent, screen, record):
        super().__init__(parent, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_CONTROL)
        self.screen = screen
        self.url = record["url"]
        self.grid_columnconfigure(0, weight=1)

        self.title = T.label(self, "", "bold", height=22)
        self.title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))
        self.info = T.label(self, "", "caption", T.MUTED, height=18)
        self.info.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))
        self.badge = Badge(self, "", "neutral")
        self.badge.grid(row=0, column=1, rowspan=2, padx=8)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=0, column=2, rowspan=2, padx=(4, 12))
        T.secondary_button(actions, "Abrir", lambda: screen.open(self.url), width=70, height=30).pack(side="left")
        self.btn_check = T.secondary_button(actions, "Verificar", lambda: screen.check(self.url), width=86, height=30)
        self.btn_check.pack(side="left", padx=6)
        T.ghost_button(actions, "Remover", lambda: screen.remove(self.url), width=76, height=30).pack(side="left")
        self.update_record(record)

    def update_record(self, record, busy=False):
        counts = record.get("counts") or {}
        total = counts.get("total", len(record.get("entries") or []))
        self.title.configure(text=truncate_text(record.get("title") or record["url"], 80))
        self.info.configure(text=f"{total} vídeo(s) · {_fmt_checked(record.get('last_checked'))}   ·   "
                                 f"{truncate_text(record['url'], 60)}")
        if busy:
            self.badge.set("verificando…", "info")
            self.btn_check.configure(state="disabled")
            return
        self.btn_check.configure(state="normal")
        new = counts.get(NEW, 0)
        if not record.get("last_checked"):
            self.badge.set("não verificada", "neutral")
        elif new:
            self.badge.set(f"{new} novo(s)", "success")
        else:
            self.badge.set("em dia", "neutral")


class PlaylistsScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.cards = {}
        self.results = {}       # url -> PlaylistResult da última verificação nesta sessão
        self._pending = []
        self._sync_after_check = False

        self.header = PageHeader(self, "Playlists", "Suas playlists salvas. Verifique e baixe as novidades de todas.")
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.btn_sync = T.primary_button(self.header.actions, "↓  Sincronizar tudo", self.sync_all, width=190, height=42)
        self.btn_sync.pack(side="right", padx=(8, 0))
        self.btn_check_all = T.secondary_button(self.header.actions, "⟳  Verificar todas", self.check_all,
                                                width=160, height=42)
        self.btn_check_all.pack(side="right")

        add = T.card(self)
        add.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        add.grid_columnconfigure(0, weight=1)
        self.url_entry = T.entry(add, "Cole a URL de uma playlist para salvar…")
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(16, 10), pady=12)
        self.url_entry.bind("<Return>", lambda _e: self.add_url())
        T.secondary_button(add, "＋ Adicionar", self.add_url, width=120).grid(row=0, column=1, padx=(0, 16))

        self.list_frame = T.scrollable(self)
        self.list_frame.grid(row=2, column=0, sticky="nsew")
        self.empty = EmptyState(
            self.list_frame, "♫", "Nenhuma playlist salva",
            "Cole uma URL acima, ou use '☆ Salvar playlist' na tela Seleção. "
            "Depois, 'Sincronizar tudo' baixa o que entrou de novo em todas elas.")
        self.status = T.label(self, "", "caption", T.MUTED)
        self.status.grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.refresh()

    # ---------------- lista ----------------
    def refresh(self):
        items = self.app.playlists.items
        urls = [p["url"] for p in items]
        for url in list(self.cards):
            if url not in urls:
                self.cards.pop(url).destroy()
        for record in items:
            card = self.cards.get(record["url"])
            if card is None:
                card = PlaylistCard(self.list_frame, self, record)
                card.pack(fill="x", padx=6, pady=3)
                self.cards[record["url"]] = card
            else:
                card.update_record(record, busy=record["url"] in self._pending)
        if items:
            self.empty.pack_forget()
        else:
            self.empty.pack(fill="both", expand=True)
        self.btn_sync.configure(state="normal" if items else "disabled")
        self.btn_check_all.configure(state="normal" if items else "disabled")

    def on_show(self):
        self.refresh()

    # ---------------- ações ----------------
    def add_url(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        if self.app.playlists.is_saved(url):
            self.app.toast("Essa playlist já está salva.", "info")
            return
        self.app.playlists.add(url)
        self.url_entry.delete(0, "end")
        self.refresh()
        self.check(url)

    def remove(self, url):
        record = self.app.playlists.get(url)
        if record and messagebox.askyesno("Remover playlist",
                                          f"Remover '{record.get('title') or url}' da lista? "
                                          "Nenhum arquivo é apagado."):
            self.app.playlists.remove(url)
            self.results.pop(url, None)
            self.refresh()

    def open(self, url):
        result = self.results.get(url)
        if result is not None:
            self.app.annotate(result.entries)
            self.app.open_playlist(result)
            return
        self.check(url, open_after=True)

    def check(self, url, open_after=False, on_finish=None):
        if url in self._pending:
            return
        self._pending.append(url)
        record = self.app.playlists.get(url)
        if record and url in self.cards:
            self.cards[url].update_record(record, busy=True)

        def done(result):
            self._finish_check(url)
            self.results[url] = result
            if open_after:
                self.app.open_playlist(result)
            if on_finish:
                on_finish(result)

        def failed(exc):
            self._finish_check(url)
            self.app.toast(f"Falha ao verificar: {friendly_error(str(exc)) or exc}", "danger", 6000)
            if on_finish:
                on_finish(None)

        self.app.fetch_playlist(url, done, failed)

    def _finish_check(self, url):
        if url in self._pending:
            self._pending.remove(url)
        self.refresh()

    def check_all(self, then=None):
        """Verifica uma playlist por vez (evita muitas requisições simultâneas ao YouTube)."""
        urls = [p["url"] for p in self.app.playlists.items]
        if not urls:
            return
        self.btn_check_all.configure(state="disabled")
        self.btn_sync.configure(state="disabled")

        def step(index):
            if index >= len(urls):
                self.status.configure(text=f"{len(urls)} playlist(s) verificada(s).")
                self.refresh()
                if then:
                    then()
                return
            self.status.configure(text=f"Verificando {index + 1}/{len(urls)}…")
            self.check(urls[index], on_finish=lambda _r: step(index + 1))

        step(0)

    def sync_all(self):
        def start():
            jobs, total = [], 0
            for record in self.app.playlists.items:
                result = self.results.get(record["url"])
                if result is None:
                    continue
                new = [e for e in result.entries if e.get("status") == NEW]
                if new:
                    jobs.append((new, result.title, result.entries))
                    total += len(new)
            if not jobs:
                self.app.toast("Tudo em dia: nenhuma música nova nas playlists salvas.", "success")
                return
            if messagebox.askyesno("Sincronizar tudo",
                                   f"Baixar {total} música(s) nova(s) de {len(jobs)} playlist(s)?"):
                self.app.start_download_queue(jobs)

        self.check_all(then=start)
