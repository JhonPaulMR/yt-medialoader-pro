import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from .. import theme as T
from ..config import IMAGE_EXTS, ITEMS_PER_PAGE, RENAME_HISTORY_FILE
from ..metadata import read_tags
from ..rename_rules import (
    ACTIONS,
    FROM_METADATA,
    KEEP,
    apply_regex_name,
    guess_rename_action,
    is_generic_name,
    is_numbered_copy,
    name_from_title,
)
from ..utils import core_title
from ..utils import build_unique_path, clean_filename, truncate_text
from .base import Screen
from .widgets import EmptyState, PageHeader, Paginator, RowPool, scroll_to_top

GENERIC = "Nomes genéricos"
FILTERS = ("Todos", "Selecionados", "Com conflito", GENERIC) + ACTIONS
SORTS = ("Nome (A-Z)", "Nome (Z-A)", "Mais recentes", "Mais antigos")
HISTORY_LIMIT = 20


def load_history():
    try:
        with open(RENAME_HISTORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_history(history):
    RENAME_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RENAME_HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history[-HISTORY_LIMIT:], file, ensure_ascii=False, indent=1)


def _final_name(orig_name, typed):
    """Nome limpo, preservando a extensão original se o usuário apagá-la."""
    ext = os.path.splitext(orig_name)[1]
    name = clean_filename(typed)
    if os.path.splitext(name)[1].lower() != ext.lower():
        name = clean_filename(name + ext)
    return name


class RenameRow(ctk.CTkFrame):
    def __init__(self, parent, screen):
        super().__init__(parent, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_CONTROL)
        self.screen = screen
        self.rel = None
        self.visible_index = 0
        self.grid_columnconfigure(3, weight=1)

        self.var = ctk.IntVar(value=0)
        self.checkbox = T.checkbox(self, "", variable=self.var, width=24, command=self._on_check)
        self.checkbox.grid(row=0, column=0, padx=(12, 8), pady=8)
        self.original = T.label(self, "", "body", T.MUTED, width=340)
        self.original.grid(row=0, column=1, sticky="w")
        self.action = T.option_menu(self, ACTIONS, self._on_action, width=150, height=30)
        self.action.grid(row=0, column=2, padx=10)
        self.name = T.entry(self, height=32)
        self.name.grid(row=0, column=3, sticky="ew", padx=(0, 12))
        self.name.bind("<KeyRelease>", self._on_edit)

    def bind_item(self, rel, visible_index):
        self.rel = rel
        self.visible_index = visible_index
        data = self.screen.state[rel]
        self.var.set(1 if data["selected"] else 0)
        self.original.configure(text=truncate_text(rel, 48))
        self.action.set(data["action"])
        self.name.delete(0, "end")
        self.name.insert(0, data["new_name"])
        self.refresh_conflict()

    def refresh_conflict(self):
        conflict = self.screen.has_conflict(self.rel)
        changed = self.screen.state[self.rel]["new_name"] != Path(self.rel).name
        self.name.configure(border_color=T.WARNING if conflict else T.BORDER,
                            text_color="#86efac" if changed else T.TEXT)

    def _on_check(self):
        self.screen.on_row_toggle(self)

    def _on_action(self, choice):
        self.screen.on_action_change(self, choice)

    def _on_edit(self, _event):
        self.screen.on_name_edit(self)


class RenamerScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.state = {}       # rel -> {selected, action, new_name, mtime}
        self.filtered = []
        self.page = 0
        self.last_clicked = None
        self.loaded = False
        self._search_job = None

        self.header = PageHeader(
            self, "Renomeador",
            "Sugestões automáticas para limpar nomes. Edições são mantidas ao trocar de página ou filtro.")
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.btn_apply = T.primary_button(self.header.actions, "Aplicar", self.execute_rename, width=170, height=42)
        self.btn_apply.pack(side="right", padx=(8, 0))
        self.btn_undo = T.secondary_button(self.header.actions, "↶  Desfazer última", self.undo_last,
                                           width=160, height=42)
        self.btn_undo.pack(side="right")

        toolbar = T.card(self)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        toolbar.grid_columnconfigure(1, weight=1)
        T.secondary_button(toolbar, "⟳  Recarregar pasta", self.load_folder, width=160).grid(
            row=0, column=0, padx=(14, 10), pady=12)
        self.search = T.entry(toolbar, "Buscar arquivo…  (Ctrl+F)")
        self.search.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self.search.bind("<KeyRelease>", self._on_search_key)
        self.filter = T.option_menu(toolbar, FILTERS, lambda _v: self.apply_filter(), width=160)
        self.filter.grid(row=0, column=2, padx=(0, 10))
        self.sort = T.option_menu(toolbar, SORTS, lambda _v: self.apply_filter(), width=150)
        self.sort.grid(row=0, column=3, padx=(0, 14))

        # --- edição em massa (vale para as linhas do filtro atual) ---
        bulk = T.card(self)
        bulk.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        T.label(bulk, "Em massa", "bold").pack(side="left", padx=(16, 10), pady=12)
        self.find = T.entry(bulk, "Localizar…", width=170)
        self.find.pack(side="left")
        T.label(bulk, "→", "body", T.MUTED).pack(side="left", padx=6)
        self.replace = T.entry(bulk, "Substituir por…", width=170)
        self.replace.pack(side="left")
        self.use_regex = ctk.BooleanVar(value=False)
        T.checkbox(bulk, "Regex", variable=self.use_regex).pack(side="left", padx=10)
        T.secondary_button(bulk, "Substituir", self.find_replace, width=100).pack(side="left")
        T.secondary_button(bulk, "Aplicar", self.apply_bulk_action, width=80).pack(side="right", padx=(6, 16))
        self.bulk_action = T.option_menu(bulk, ACTIONS, width=160)
        self.bulk_action.set(ACTIONS[2])
        self.bulk_action.pack(side="right")
        T.label(bulk, "Ação nos filtrados:", "body", T.MUTED).pack(side="right", padx=8)

        self.list_frame = T.scrollable(self)
        self.list_frame.grid(row=3, column=0, sticky="nsew")
        self.pool = RowPool(self.list_frame, lambda parent: RenameRow(parent, self), dict(fill="x", padx=6, pady=3))
        self.empty = EmptyState(self.list_frame, "✎", "Nenhum arquivo carregado",
                                "Clique em 'Recarregar pasta' para ler os arquivos de áudio.")
        self.empty.pack(fill="both", expand=True)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        footer.grid_columnconfigure(1, weight=1)
        self.summary = T.label(footer, "", "body", T.MUTED)
        self.summary.grid(row=0, column=0, sticky="w")
        self.paginator = Paginator(footer, self.goto_page)
        self.paginator.grid(row=0, column=1)
        self.legend = T.label(footer, "Verde = nome vai mudar · borda amarela = nome já existe",
                              "caption", T.SUBTLE)
        self.legend.grid(row=0, column=2, sticky="e")

        self._update_buttons()

    # ========================================================
    # CARGA
    # ========================================================
    def on_show(self):
        if not self.loaded:
            self.load_folder()
        self._update_buttons()

    @property
    def folder(self):
        return self.app.settings.folder

    def load_folder(self):
        self.loaded = True
        library = self.app.library
        library.scan_disk()
        previous = self.state
        self.state = {}
        for rel in library.files:
            try:
                mtime = os.path.getmtime(self.folder / rel)
            except OSError:
                mtime = 0
            if rel in previous:
                self.state[rel] = previous[rel]
                self.state[rel]["mtime"] = mtime
                continue
            name = Path(rel).name
            damaged = self._is_damaged(rel)
            # Nome danificado ("OFFICIAL VIDEO.m4a", "Linkin Park (14).m4a"): o título está no metadado.
            action = FROM_METADATA if damaged else guess_rename_action(name)
            new_name = self._suggest(rel, action)
            self.state[rel] = {
                "selected": action != KEEP and new_name != name,
                "action": action,
                "new_name": new_name,
                "mtime": mtime,
                "damaged": damaged,
            }
        if not self.state:
            self.empty.set_text("Nenhum arquivo de áudio", f"A pasta {self.folder} não tem arquivos compatíveis.")
        self.apply_filter()

    def _on_search_key(self, _event):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(200, self.apply_filter)

    def apply_filter(self, keep_page=False):
        self._search_job = None
        mode = self.filter.get()
        query = self.search.get().strip().casefold()
        items = []
        for rel, data in self.state.items():
            if query and query not in rel.casefold() and query not in data["new_name"].casefold():
                continue
            if mode == "Selecionados" and not data["selected"]:
                continue
            if mode == "Com conflito" and not self.has_conflict(rel):
                continue
            if mode == GENERIC and not data.get("damaged"):
                continue
            if mode in ACTIONS and data["action"] != mode:
                continue
            items.append(rel)

        sort = self.sort.get()
        if sort == "Nome (A-Z)":
            items.sort(key=str.casefold)
        elif sort == "Nome (Z-A)":
            items.sort(key=str.casefold, reverse=True)
        elif sort == "Mais recentes":
            items.sort(key=lambda r: self.state[r]["mtime"], reverse=True)
        else:
            items.sort(key=lambda r: self.state[r]["mtime"])
        self.filtered = items
        self.goto_page(self.page if keep_page else 0)

    @property
    def total_pages(self):
        return max(1, math.ceil(len(self.filtered) / ITEMS_PER_PAGE))

    def goto_page(self, page):
        self.page = max(0, min(page, self.total_pages - 1))
        self.last_clicked = None
        start = self.page * ITEMS_PER_PAGE
        visible = self.filtered[start:start + ITEMS_PER_PAGE]
        if visible:
            self.empty.pack_forget()
        else:
            if self.state:
                self.empty.set_text("Nada encontrado", "Nenhum arquivo corresponde à busca ou ao filtro.")
            self.empty.pack(fill="both", expand=True)
        self.pool.render(visible)
        scroll_to_top(self.list_frame)
        self.paginator.update_pages(self.page, self.total_pages)
        self._update_buttons()

    # ========================================================
    # EDIÇÃO
    # ========================================================
    def _target_path(self, rel):
        data = self.state[rel]
        directory = (self.folder / rel).parent
        return directory / _final_name(Path(rel).name, data["new_name"])

    def has_conflict(self, rel):
        data = self.state.get(rel)
        if not data or Path(rel).name == data["new_name"]:
            return False
        target = self._target_path(rel)
        source = self.folder / rel
        return target.exists() and os.path.normcase(str(target)) != os.path.normcase(str(source))

    def on_row_toggle(self, row):
        state = bool(row.var.get())
        self.state[row.rel]["selected"] = state
        if self.app.shift_pressed and self.last_clicked is not None:
            low, high = sorted((self.last_clicked, row.visible_index))
            for other in self.pool.visible_rows()[low:high + 1]:
                other.var.set(1 if state else 0)
                self.state[other.rel]["selected"] = state
        self.last_clicked = row.visible_index
        self._update_buttons()

    def _is_damaged(self, rel):
        name = Path(rel).name
        if is_generic_name(name):
            return True
        if not is_numbered_copy(name):
            return False
        # "Linkin Park (14)": o título real não começa pelo nome do arquivo.
        # Uma cópia legítima ("Numb (1)") tem título que começa pelo próprio nome.
        title_core = core_title(read_tags(self.folder / rel).get("title"))
        name_core = core_title(name.rsplit(" (", 1)[0])
        return bool(title_core) and not title_core.startswith(name_core)

    def _suggest(self, rel, action):
        name = Path(rel).name
        if action == FROM_METADATA:
            return name_from_title(name, read_tags(self.folder / rel).get("title"))
        return apply_regex_name(name, action)

    def set_filter(self, name):
        """Usado pelo Diagnóstico para abrir já filtrado (ex.: nomes genéricos)."""
        if not self.loaded:
            self.load_folder()
        self.filter.set(name)
        self.apply_filter()

    def apply_bulk_action(self):
        action = self.bulk_action.get()
        if action == FROM_METADATA and len(self.filtered) > 300 and not messagebox.askyesno(
                "Usar metadado", f"Ler o metadado de {len(self.filtered)} arquivos pode levar alguns segundos. "
                                 "Continuar?"):
            return
        changed = 0
        for rel in self.filtered:
            data = self.state[rel]
            data["action"] = action
            data["new_name"] = self._suggest(rel, action)
            data["selected"] = data["new_name"] != Path(rel).name
            changed += data["selected"]
        self.apply_filter(keep_page=True)
        self.app.toast(f"'{action}' aplicada a {len(self.filtered)} arquivo(s): {changed} vão mudar.", "info")

    def find_replace(self):
        needle = self.find.get()
        if not needle:
            self.app.toast("Digite o texto a localizar.", "warning")
            return
        replacement = self.replace.get()
        if self.use_regex.get():
            try:
                pattern = re.compile(needle, re.IGNORECASE)
            except re.error as exc:
                messagebox.showerror("Regex inválida", str(exc))
                return

            def transform(stem):
                return pattern.sub(replacement, stem)
        else:
            def transform(stem):
                return stem.replace(needle, replacement)

        changed = 0
        for rel in self.filtered:
            data = self.state[rel]
            stem, ext = os.path.splitext(data["new_name"])
            new_stem = transform(stem).strip()
            if new_stem and new_stem != stem:
                data["new_name"] = new_stem + ext
                data["selected"] = data["new_name"] != Path(rel).name
                changed += 1
        self.apply_filter(keep_page=True)
        self.app.toast(f"Substituição feita em {changed} nome(s) (ainda não aplicada aos arquivos).",
                       "success" if changed else "info")

    def on_action_change(self, row, choice):
        data = self.state[row.rel]
        data["action"] = choice
        data["new_name"] = self._suggest(row.rel, choice)
        data["selected"] = data["new_name"] != Path(row.rel).name
        row.bind_item(row.rel, row.visible_index)
        self._update_buttons()

    def on_name_edit(self, row):
        data = self.state[row.rel]
        data["new_name"] = row.name.get().strip()
        # Editar o nome já marca a linha (antes a edição era ignorada).
        data["selected"] = bool(data["new_name"]) and data["new_name"] != Path(row.rel).name
        row.var.set(1 if data["selected"] else 0)
        row.refresh_conflict()
        self._update_buttons()

    def select_all(self):
        for rel in self.filtered:
            self.state[rel]["selected"] = True
        for row in self.pool.visible_rows():
            row.var.set(1)
        self._update_buttons()

    def focus_search(self):
        self.search.focus_set()
        self.search.select_range(0, "end")

    def _pending(self):
        return [
            rel for rel, data in self.state.items()
            if data["selected"] and data["new_name"].strip() and data["new_name"] != Path(rel).name
        ]

    def _update_buttons(self):
        pending = len(self._pending())
        self.btn_apply.configure(text=f"Aplicar ({pending})", state="normal" if pending else "disabled")
        history = [h for h in load_history() if h.get("folder") == str(self.folder)]
        self.btn_undo.configure(state="normal" if history else "disabled")
        self.summary.configure(text=f"{len(self.state)} arquivo(s) · {pending} renomeação(ões) pendente(s)")

    # ========================================================
    # RENOMEAR / DESFAZER
    # ========================================================
    def execute_rename(self):
        pending = self._pending()
        if not pending:
            return
        if not messagebox.askyesno("Renomear arquivos",
                                   f"Renomear {len(pending)} arquivo(s)? Você pode desfazer depois."):
            return

        renames, audio_pairs, failures, reserved = [], [], [], set()
        for rel in pending:
            source = self.folder / rel
            if not source.is_file():
                continue
            new_name = _final_name(source.name, self.state[rel]["new_name"])
            target = source.parent / new_name
            if os.path.normcase(str(target)) == os.path.normcase(str(source)):
                continue
            if target.exists() or str(target).lower() in reserved:
                target = Path(build_unique_path(str(source.parent), new_name, reserved))
            try:
                os.rename(source, target)
            except OSError as exc:
                failures.append(f"{source.name}: {exc}")
                continue
            reserved.add(str(target).lower())
            new_rel = Path(os.path.relpath(target, self.folder)).as_posix()
            renames.append([rel, new_rel])
            audio_pairs.append((rel, new_rel))

            # A capa solta (se existir) acompanha o áudio.
            for ext in IMAGE_EXTS:
                thumb = source.with_suffix(ext)
                new_thumb = target.with_suffix(ext)
                if thumb.is_file() and not new_thumb.exists():
                    try:
                        os.rename(thumb, new_thumb)
                        renames.append([Path(os.path.relpath(thumb, self.folder)).as_posix(),
                                        Path(os.path.relpath(new_thumb, self.folder)).as_posix()])
                    except OSError:
                        pass

        if renames:
            history = load_history()
            history.append({
                "folder": str(self.folder),
                "time": datetime.now().isoformat(timespec="seconds"),
                "renames": renames,
            })
            save_history(history)
        self.app.library.rename_files(audio_pairs)
        for old_rel, _ in audio_pairs:
            self.state.pop(old_rel, None)
        self.load_folder()
        self.app.screens["dashboard"].refresh_summary()

        if failures:
            messagebox.showwarning("Renomeador", f"{len(audio_pairs)} renomeado(s), {len(failures)} falha(s):\n\n"
                                   + "\n".join(failures[:10]))
        else:
            self.app.toast(f"{len(audio_pairs)} arquivo(s) renomeado(s).", "success")

    def undo_last(self):
        history = load_history()
        index = next((i for i in range(len(history) - 1, -1, -1)
                      if history[i].get("folder") == str(self.folder)), None)
        if index is None:
            return
        batch = history[index]
        if not messagebox.askyesno(
                "Desfazer", f"Desfazer a renomeação de {batch['time'].replace('T', ' ')} "
                            f"({len(batch['renames'])} arquivo(s))?"):
            return

        restored, audio_pairs, skipped = 0, [], 0
        for old_rel, new_rel in reversed(batch["renames"]):
            current, original = self.folder / new_rel, self.folder / old_rel
            if current.is_file() and not original.exists():
                try:
                    os.rename(current, original)
                    restored += 1
                    audio_pairs.append((new_rel, old_rel))
                    continue
                except OSError:
                    pass
            skipped += 1

        history.pop(index)
        save_history(history)
        self.app.library.rename_files(audio_pairs)
        for new_rel, _ in audio_pairs:
            self.state.pop(new_rel, None)
        self.load_folder()
        message = f"{restored} arquivo(s) restaurado(s)."
        if skipped:
            message += f" {skipped} não puderam ser restaurados (movidos ou recriados)."
        self.app.toast(message, "warning" if skipped else "success", 5000)
