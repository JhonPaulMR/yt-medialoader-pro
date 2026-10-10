"""Aba "Biblioteca" do Diagnóstico: duplicatas, órfãos e nomes danificados."""

import math
import subprocess
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from .. import theme as T
from ..config import ITEMS_PER_PAGE
from ..maintenance import find_duplicates, find_orphans, send_to_recycle_bin
from ..utils import format_duration, truncate_text
from .widgets import Badge, EmptyState, Paginator, RowPool, scroll_to_top


def _fmt_size(size):
    return f"{size / 1048576:.1f} MB" if size else ""


class LibRow(ctk.CTkFrame):
    def __init__(self, parent, tab):
        super().__init__(parent, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_CONTROL)
        self.tab = tab
        self.item = None
        self.grid_columnconfigure(2, weight=1)
        self.var = ctk.IntVar(value=0)
        T.checkbox(self, "", variable=self.var, width=24, command=self._on_check).grid(
            row=0, column=0, rowspan=2, padx=(12, 6), pady=8)
        self.badge = Badge(self, "", "neutral", width=86)
        self.badge.grid(row=0, column=1, rowspan=2, padx=(0, 10))
        self.name = T.label(self, "", "bold", height=20)
        self.name.grid(row=0, column=2, sticky="sw", pady=(8, 0))
        self.detail = T.label(self, "", "caption", T.MUTED, height=16)
        self.detail.grid(row=1, column=2, sticky="nw", pady=(0, 8))
        T.ghost_button(self, "Mostrar", self._reveal, width=70, height=28).grid(
            row=0, column=3, rowspan=2, padx=(0, 10))

    def bind_item(self, item, _index):
        self.item = item
        self.var.set(1 if item["selected"] else 0)
        self.badge.set(item["label"], item["kind"])
        self.name.configure(text=truncate_text(item["rel"], 95))
        parts = [format_duration(item.get("duration")), _fmt_size(item.get("size"))]
        if item.get("mtime"):
            parts.append(datetime.fromtimestamp(item["mtime"]).strftime("%d/%m/%Y"))
        if item.get("note"):
            parts.append(item["note"])
        self.detail.configure(text="   ·   ".join(p for p in parts if p))

    def _on_check(self):
        self.item["selected"] = bool(self.var.get())
        self.tab.update_actions()

    def _reveal(self):
        path = self.tab.app.library.folder / self.item["rel"]
        subprocess.Popen(["explorer", "/select,", str(path)])


class LibraryTab:
    def __init__(self, tab, app):
        self.app = app
        self.items = []
        self.page = 0
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(4, 8))
        self.btn_dupes = T.primary_button(bar, "Procurar duplicatas", self.search_duplicates, width=180, height=36)
        self.btn_dupes.pack(side="left")
        self.btn_orphans = T.secondary_button(bar, "Procurar órfãos", self.search_orphans, width=150)
        self.btn_orphans.pack(side="left", padx=8)
        T.secondary_button(bar, "Nomes danificados → Renomeador", self.open_damaged, width=240).pack(side="left")
        self.btn_trash = T.danger_button(bar, "Mover para a Lixeira", self.trash_selected, width=200)
        self.btn_trash.pack(side="right")

        self.status = T.label(tab, "Duplicatas: mesma música (pelo título do metadado) e duração parecida. "
                                   "Órfãos: arquivos que não estão em nenhuma playlist salva.",
                              "caption", T.SUBTLE, wraplength=900)
        self.status.grid(row=1, column=0, sticky="w", pady=(0, 10))

        area = ctk.CTkFrame(tab, fg_color="transparent")
        area.grid(row=2, column=0, sticky="nsew")
        area.grid_columnconfigure(0, weight=1)
        area.grid_rowconfigure(0, weight=1)
        self.list_frame = T.scrollable(area)
        self.list_frame.grid(row=0, column=0, sticky="nsew")
        self.pool = RowPool(self.list_frame, lambda parent: LibRow(parent, self), dict(fill="x", padx=6, pady=3))
        self.empty = EmptyState(self.list_frame, "♫", "Nenhuma análise ainda",
                                "Nada é apagado sem confirmação, e tudo vai para a Lixeira (dá para recuperar).")
        self.empty.pack(fill="both", expand=True)
        self.paginator = Paginator(area, self.goto_page)
        self.paginator.grid(row=1, column=0, pady=(10, 0))
        self.update_actions()

    # ---------------- busca ----------------
    def _busy(self, text):
        self.status.configure(text=text, text_color=T.TEXT)
        self.btn_dupes.configure(state="disabled")
        self.btn_orphans.configure(state="disabled")

    def _idle(self, text, color=T.MUTED):
        self.status.configure(text=text, text_color=color)
        self.btn_dupes.configure(state="normal")
        self.btn_orphans.configure(state="normal")

    def search_duplicates(self):
        self._busy("Lendo os metadados da biblioteca… (alguns segundos)")
        library = self.app.library

        def work():
            library.scan_disk()
            return find_duplicates(library)

        def done(groups):
            items = []
            for number, group in enumerate(groups, 1):
                for position, info in enumerate(group):
                    keep = position == 0  # o maior arquivo do grupo
                    items.append(dict(info, selected=not keep, kind="success" if keep else "warning",
                                      label="MANTER" if keep else "DUPLICATA", note=f"grupo {number}"))
            self.show(items)
            extra = sum(len(g) - 1 for g in groups)
            self._idle(f"{len(groups)} grupo(s) de duplicatas · {extra} cópia(s) marcada(s); o maior arquivo de "
                       "cada grupo fica.", T.WARNING if groups else T.SUCCESS)

        self.app.run_task(work, done, lambda exc: self._idle(f"Erro: {exc}", T.DANGER))

    def search_orphans(self):
        entries = self.app.playlists.all_entries()
        if not entries:
            messagebox.showinfo("Órfãos", "Salve e verifique ao menos uma playlist (tela Playlists) para saber "
                                          "quais arquivos não pertencem a nenhuma delas.")
            return
        self._busy("Comparando a pasta com as playlists salvas…")
        library = self.app.library

        def work():
            library.load()
            return find_orphans(library, entries)

        def done(orphans):
            items = [dict(info, selected=False, kind="neutral", label="ÓRFÃO") for info in orphans]
            self.show(items)
            self._idle(f"{len(orphans)} arquivo(s) fora das {len(self.app.playlists.items)} playlist(s) salva(s). "
                       "Nada vem marcado: escolha o que mandar para a Lixeira.")

        self.app.run_task(work, done, lambda exc: self._idle(f"Erro: {exc}", T.DANGER))

    def open_damaged(self):
        self.app.navigate("renamer")
        self.app.screens["renamer"].set_filter("Nomes genéricos")

    # ---------------- lista ----------------
    def show(self, items):
        self.items = items
        self.goto_page(0)

    def goto_page(self, page):
        pages = max(1, math.ceil(len(self.items) / ITEMS_PER_PAGE))
        self.page = max(0, min(page, pages - 1))
        start = self.page * ITEMS_PER_PAGE
        visible = self.items[start:start + ITEMS_PER_PAGE]
        if visible:
            self.empty.pack_forget()
        else:
            self.empty.set_text("Nada encontrado", "Sua biblioteca está limpa nesse quesito.")
            self.empty.pack(fill="both", expand=True)
        self.pool.render(visible)
        scroll_to_top(self.list_frame)
        self.paginator.update_pages(self.page, pages)
        self.update_actions()

    def update_actions(self):
        count = sum(1 for i in self.items if i["selected"])
        self.btn_trash.configure(text=f"Mover para a Lixeira ({count})", state="normal" if count else "disabled")

    def trash_selected(self):
        chosen = [i for i in self.items if i["selected"]]
        if not chosen or not messagebox.askyesno(
                "Mover para a Lixeira",
                f"Mover {len(chosen)} arquivo(s) para a Lixeira do Windows?\n\n"
                "Você pode restaurá-los pela Lixeira se mudar de ideia."):
            return
        folder = self.app.library.folder
        try:
            moved = send_to_recycle_bin([folder / i["rel"] for i in chosen])
        except OSError as exc:
            messagebox.showerror("Lixeira", str(exc))
            return
        gone = {i["rel"] for i in chosen if not (folder / i["rel"]).exists()}
        self.items = [i for i in self.items if i["rel"] not in gone]
        self.goto_page(self.page)
        self.app.reload_library()
        self.app.screens["renamer"].loaded = False
        self.app.toast(f"{moved} arquivo(s) movido(s) para a Lixeira.", "success")
