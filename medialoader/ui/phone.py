import math
import threading
from tkinter import messagebox

import customtkinter as ctk

from .. import theme as T
from ..config import ITEMS_PER_PAGE
from ..library import NEW
from ..phone import (
    MISSING,
    ON_PHONE,
    ONLY_PC,
    STATUS_LABELS,
    PhoneClient,
    PhoneConfig,
    UploadCancelled,
    compare_entries,
    compare_files,
    m3u_for_phone,
)
from ..utils import clean_filename, truncate_text
from .base import Screen
from .widgets import Badge, EmptyState, PageHeader, Paginator, RowPool, StatChip, scroll_to_top

STATUS_BADGE = {ON_PHONE: "neutral", ONLY_PC: "success", MISSING: "warning"}
SOURCES = ("Playlist atual", "Playlist salva", "Pasta inteira do PC")
VIEWS = {"Faltando no celular": {ONLY_PC, MISSING}, "Já no celular": {ON_PHONE}, "Todos": None}


class PhoneRow(ctk.CTkFrame):
    def __init__(self, parent, screen):
        super().__init__(parent, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_CONTROL)
        self.screen = screen
        self.item = None
        self.grid_columnconfigure(2, weight=1)
        self.var = ctk.IntVar(value=0)
        self.checkbox = T.checkbox(self, "", variable=self.var, width=24, command=self._on_check)
        self.checkbox.grid(row=0, column=0, rowspan=2, padx=(12, 4), pady=8)
        self.pos = T.label(self, "", "mono", T.SUBTLE, width=44, anchor="e")
        self.pos.grid(row=0, column=1, rowspan=2, padx=(0, 12))
        self.title = T.label(self, "", "bold", height=20)
        self.title.grid(row=0, column=2, sticky="sw", pady=(8, 0))
        self.detail = T.label(self, "", "caption", T.MUTED, height=16)
        self.detail.grid(row=1, column=2, sticky="nw", pady=(0, 8))
        self.badge = Badge(self, "", "neutral", width=110)
        self.badge.grid(row=0, column=3, rowspan=2, padx=(4, 14))

    def bind_item(self, item, _index):
        self.item = item
        self.var.set(1 if item["selected"] else 0)
        self.checkbox.configure(state="disabled" if item["status"] == ON_PHONE else "normal")
        self.pos.configure(text=str(item["position"] or ""))
        self.title.configure(text=truncate_text(item["title"], 90))
        if item["status"] == ON_PHONE:
            detail = f"No celular: {item['remote']}"
        elif item["status"] == ONLY_PC:
            detail = f"No PC: {item['local']}"
        else:
            detail = "Ainda não baixada: use 'Baixar faltantes e enviar'"
        self.detail.configure(text=truncate_text(detail, 110))
        self.badge.set(STATUS_LABELS[item["status"]], STATUS_BADGE[item["status"]])

    def _on_check(self):
        self.item["selected"] = bool(self.var.get())
        self.screen.update_actions()


class PhoneScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)
        self.items = []
        self.filtered = []
        self.page = 0
        self.manifest = {"ids": {}, "files": {}}
        self.phone_files = []
        self.source_entries = None      # entradas da playlist comparada (None = pasta inteira)
        self.source_title = None
        self.cancel = threading.Event()
        self.uploading = False
        self._after_download_ids = None
        app.batch_listeners.append(self._on_batch_finished)

        self.header = PageHeader(self, "Celular",
                                 "Envie músicas para o Android pelo Wi-Fi, sem cabo. Só o que falta é enviado.")
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        # ---------------- conexão ----------------
        conn = T.card(self)
        conn.grid(row=1, column=0, sticky="ew")
        row = ctk.CTkFrame(conn, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(14, 6))
        self.host = T.entry(row, "IP do celular (ex.: 192.168.0.15)", width=230)
        self.host.pack(side="left")
        self.port = T.entry(row, "Porta", width=80)
        self.port.pack(side="left", padx=6)
        self.user = T.entry(row, "Usuário (vazio = anônimo)", width=190)
        self.user.pack(side="left")
        self.password = T.entry(row, "Senha", width=140, show="•")
        self.password.pack(side="left", padx=6)
        self.folder = T.entry(row, "Pasta no celular", width=170)
        self.folder.pack(side="left")
        self.btn_test = T.secondary_button(row, "Testar conexão", self.test_connection, width=140)
        self.btn_test.pack(side="right")
        status_row = ctk.CTkFrame(conn, fg_color="transparent")
        status_row.pack(fill="x", padx=16, pady=(0, 12))
        self.conn_badge = Badge(status_row, "Não conectado", "neutral")
        self.conn_badge.pack(side="left")
        self.conn_detail = T.label(status_row, "No celular: Material Files → menu ☰ → Servidor FTP → Iniciar. "
                                               "Use o IP e a porta que aparecem lá (mesmo Wi-Fi do PC).",
                                   "caption", T.MUTED, wraplength=820)
        self.conn_detail.pack(side="left", padx=10)

        # ---------------- origem + ações ----------------
        bar = T.card(self)
        bar.grid(row=2, column=0, sticky="ew", pady=12)
        self.source = T.segmented(bar, SOURCES, command=lambda _v: self._on_source())
        self.source.set(SOURCES[0])
        self.source.pack(side="left", padx=(16, 8), pady=12)
        self.saved = T.option_menu(bar, ["(nenhuma)"], width=260)
        self.btn_compare = T.primary_button(bar, "Comparar", self.compare, width=120, height=34)
        self.btn_compare.pack(side="left", padx=8)
        self.send_m3u = ctk.BooleanVar(value=True)
        T.checkbox(bar, "Enviar também a playlist (.m3u8)", variable=self.send_m3u,
                   command=self._save_options).pack(side="right", padx=16)

        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.grid(row=3, column=0, sticky="ew")
        stats.grid_columnconfigure((0, 1, 2), weight=1, uniform="ph")
        self.chip_on = StatChip(stats, "já no celular", T.MUTED)
        self.chip_pc = StatChip(stats, "no PC, faltando no celular", T.SUCCESS)
        self.chip_missing = StatChip(stats, "faltando no PC e no celular", T.WARNING)
        for col, chip in enumerate((self.chip_on, self.chip_pc, self.chip_missing)):
            chip.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", pady=12)
        self.btn_send = T.primary_button(actions, "Enviar selecionadas", self.send_selected, width=210)
        self.btn_send.pack(side="left")
        self.btn_download_send = T.secondary_button(actions, "↓ Baixar faltantes e enviar",
                                                    self.download_and_send, width=220)
        self.btn_download_send.pack(side="left", padx=8)
        self.btn_cancel = T.danger_button(actions, "Cancelar envio", self.cancel_upload, width=140)
        self.view = T.segmented(actions, VIEWS.keys(), command=lambda _v: self.apply_view())
        self.view.set("Faltando no celular")
        self.view.pack(side="right")

        area = ctk.CTkFrame(self, fg_color="transparent")
        area.grid(row=5, column=0, sticky="nsew")
        area.grid_columnconfigure(0, weight=1)
        area.grid_rowconfigure(0, weight=1)
        self.list_frame = T.scrollable(area)
        self.list_frame.grid(row=0, column=0, sticky="nsew")
        self.pool = RowPool(self.list_frame, lambda parent: PhoneRow(parent, self), dict(fill="x", padx=6, pady=3))
        self.empty = EmptyState(self.list_frame, "☏", "Nada comparado ainda",
                                "Teste a conexão e clique em Comparar. O app reconhece o que já está no celular "
                                "pelo nome do arquivo (e, depois do primeiro envio, por um registro exato).")
        self.empty.pack(fill="both", expand=True)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        footer.grid_columnconfigure(1, weight=1)
        self.progress_label = T.label(footer, "", "body", T.MUTED)
        self.progress_label.grid(row=0, column=0, sticky="w")
        self.paginator = Paginator(footer, self.goto_page)
        self.paginator.grid(row=0, column=1)
        self.progress = ctk.CTkProgressBar(footer, width=220, height=8, progress_color=T.ACCENT, fg_color=T.SURFACE_3)
        self.progress.set(0)

        self.load_from_settings()
        self.update_actions()

    # ========================================================
    # CONFIGURAÇÃO
    # ========================================================
    def _set(self, entry, value):
        if entry.get():
            entry.delete(0, "end")
        if value:
            entry.insert(0, value)

    def load_from_settings(self):
        s = self.app.settings
        self._set(self.host, s.phone_host)
        self._set(self.port, s.phone_port)
        self._set(self.user, s.phone_user)
        self._set(self.password, s.phone_password)
        self._set(self.folder, s.phone_folder)
        self.send_m3u.set(s.phone_send_m3u)

    def _save_options(self):
        s = self.app.settings
        s.phone_host = self.host.get().strip()
        s.phone_port = self.port.get().strip() or "2121"
        s.phone_user = self.user.get().strip()
        s.phone_password = self.password.get()
        s.phone_folder = self.folder.get().strip() or "/Music"
        s.phone_send_m3u = bool(self.send_m3u.get())
        self.app.save_settings()

    def config(self):
        self._save_options()
        return PhoneConfig.from_settings(self.app.settings)

    def on_show(self):
        names = [p.get("title") or p["url"] for p in self.app.playlists.items]
        self.saved.configure(values=names or ["(nenhuma)"])
        if names and self.saved.get() not in names:
            self.saved.set(names[0])
        self._on_source()

    def _on_source(self):
        if self.source.get() == "Playlist salva":
            self.saved.pack(side="left", padx=(0, 8), after=self.source)
        else:
            self.saved.pack_forget()

    # ========================================================
    # CONEXÃO / COMPARAÇÃO
    # ========================================================
    def test_connection(self):
        try:
            config = self.config()
            config.validate()
        except ValueError as exc:
            self.conn_badge.set("Dados incompletos", "warning")
            self.conn_detail.configure(text=str(exc))
            return
        self.btn_test.configure(state="disabled", text="Testando…")
        self.conn_badge.set("Conectando…", "info")

        def work():
            with PhoneClient(config) as client:
                return client.root, len(client.list_audio())

        def done(result):
            root, count = result
            self.btn_test.configure(state="normal", text="Testar conexão")
            self.conn_badge.set("Conectado", "success")
            self.conn_detail.configure(text=f"Pasta {root}: {count} arquivo(s) de áudio no celular.")

        def failed(exc):
            self.btn_test.configure(state="normal", text="Testar conexão")
            self.conn_badge.set("Falha na conexão", "danger")
            self.conn_detail.configure(text=str(exc))

        self.app.run_task(work, done, failed)

    def _source_entries(self):
        """(entradas, título) da origem escolhida; (None, None) = pasta inteira."""
        source = self.source.get()
        if source == "Pasta inteira do PC":
            return None, None
        if source == "Playlist atual":
            if not self.app.playlist:
                raise ValueError("Nenhuma playlist carregada. Carregue uma na tela Início ou escolha outra origem.")
            result = self.app.playlist
            return result.entries, (result.title if result.is_playlist else None)
        record = next((p for p in self.app.playlists.items
                       if (p.get("title") or p["url"]) == self.saved.get()), None)
        if not record or not record.get("entries"):
            raise ValueError("Escolha uma playlist salva que já tenha sido verificada (tela Playlists).")
        return [dict(e) for e in record["entries"]], record.get("title")

    def compare(self, then=None):
        try:
            config = self.config()
            config.validate()
            entries, title = self._source_entries()
        except ValueError as exc:
            self.app.toast(str(exc), "warning", 5000)
            return
        self.btn_compare.configure(state="disabled", text="Comparando…")
        library = self.app.library

        def work():
            library.load()
            with PhoneClient(config) as client:
                phone_files = client.list_audio()
                manifest = client.read_manifest()
            if entries is None:
                items = compare_files(library.files, phone_files, manifest)
            else:
                items = compare_entries(entries, phone_files, manifest, library)
            return phone_files, manifest, items

        def done(result):
            self.btn_compare.configure(state="normal", text="Comparar")
            self.phone_files, self.manifest, items = result
            self.source_entries, self.source_title = entries, title
            for item in items:
                item["selected"] = item["status"] == ONLY_PC
            self.items = items
            self.conn_badge.set("Conectado", "success")
            self._update_counts()
            self.apply_view()
            if then:
                then()

        def failed(exc):
            self.btn_compare.configure(state="normal", text="Comparar")
            self.conn_badge.set("Falha na conexão", "danger")
            self.conn_detail.configure(text=str(exc))

        self.app.run_task(work, done, failed)

    def _update_counts(self):
        count = {s: sum(1 for i in self.items if i["status"] == s) for s in (ON_PHONE, ONLY_PC, MISSING)}
        self.chip_on.set(count[ON_PHONE])
        self.chip_pc.set(count[ONLY_PC])
        self.chip_missing.set(count[MISSING])

    def apply_view(self):
        allowed = VIEWS[self.view.get()]
        self.filtered = [i for i in self.items if allowed is None or i["status"] in allowed]
        self.goto_page(0)

    def goto_page(self, page):
        pages = max(1, math.ceil(len(self.filtered) / ITEMS_PER_PAGE))
        self.page = max(0, min(page, pages - 1))
        start = self.page * ITEMS_PER_PAGE
        visible = self.filtered[start:start + ITEMS_PER_PAGE]
        if visible:
            self.empty.pack_forget()
        elif self.items:
            self.empty.set_text("Nada aqui", "Nenhum item nessa visão.")
            self.empty.pack(fill="both", expand=True)
        self.pool.render(visible)
        scroll_to_top(self.list_frame)
        self.paginator.update_pages(self.page, pages)
        self.update_actions()

    def update_actions(self):
        chosen = sum(1 for i in self.items if i["selected"] and i["status"] == ONLY_PC)
        missing = sum(1 for i in self.items if i["status"] == MISSING)
        busy = self.uploading
        self.btn_send.configure(text=f"Enviar selecionadas ({chosen})",
                                state="normal" if chosen and not busy else "disabled")
        self.btn_download_send.configure(text=f"↓ Baixar faltantes e enviar ({missing})",
                                         state="normal" if missing and not busy else "disabled")

    def select_all(self):
        for item in self.filtered:
            if item["status"] == ONLY_PC:
                item["selected"] = True
        self.goto_page(self.page)

    # ========================================================
    # ENVIO
    # ========================================================
    def _remote_name(self, local_rel):
        return local_rel.replace("\\", "/")

    def send_selected(self, items=None):
        items = items if items is not None else [i for i in self.items if i["selected"] and i["status"] == ONLY_PC]
        if not items or self.uploading:
            return
        config = self.config()
        folder = self.app.library.folder
        entries, title = self.source_entries, self.source_title
        send_m3u = bool(self.send_m3u.get()) and entries is not None and title
        self.uploading = True
        self.cancel.clear()
        self.btn_cancel.pack(side="left", padx=8)
        self.progress.grid(row=0, column=2, sticky="e")
        self.update_actions()

        def work():
            done_count, errors = 0, []
            with PhoneClient(config) as client:
                manifest = client.read_manifest()
                for number, item in enumerate(items, 1):
                    if self.cancel.is_set():
                        break
                    remote = self._remote_name(item["local"])
                    label = f"Enviando {number}/{len(items)}: {truncate_text(item['title'], 60)}"
                    self.app.post(self._upload_progress, label, (number - 1) / len(items))

                    def progress(fraction, n=number):
                        self.app.post(self._upload_progress, None, (n - 1 + fraction) / len(items))

                    try:
                        client.upload(str(folder / item["local"]), remote, progress, self.cancel)
                    except UploadCancelled:
                        break
                    except Exception as exc:
                        errors.append(f"{item['title']}: {exc}")
                        continue
                    done_count += 1
                    item["status"], item["remote"], item["selected"] = ON_PHONE, remote, False
                    if item["entry"] is not None:
                        manifest["ids"][item["entry"]["id"]] = remote
                    else:
                        manifest["files"][item["local"]] = remote
                    if done_count % 10 == 0:
                        client.write_manifest(manifest)
                client.write_manifest(manifest)

                if send_m3u and not self.cancel.is_set():
                    remote_by_id = {i["entry"]["id"]: i["remote"] for i in self.items
                                    if i["entry"] is not None and i["status"] == ON_PHONE}
                    text = m3u_for_phone(entries, lambda e: remote_by_id.get(e.get("id")))
                    if text:
                        client.upload_bytes(text.encode("utf-8"), f"{clean_filename(title)}.m3u8")
            return done_count, errors

        self.app.run_task(work, self._upload_finished, self._upload_failed)

    def _upload_progress(self, label, fraction):
        if label:
            self.progress_label.configure(text=label)
        self.progress.set(fraction)
        self.app.sidebar.show_progress(fraction, "celular")

    def _end_upload(self):
        self.uploading = False
        self.btn_cancel.pack_forget()
        self.progress.grid_remove()
        self.app.sidebar.hide_progress()
        self._update_counts()
        self.apply_view()

    def _upload_finished(self, result):
        done_count, errors = result
        self._end_upload()
        cancelled = self.cancel.is_set()
        self.progress_label.configure(
            text=f"{done_count} música(s) enviada(s)" + (" (cancelado)" if cancelled else "")
                 + (f" · {len(errors)} erro(s)" if errors else ""))
        if errors:
            messagebox.showwarning("Envio ao celular", "\n".join(errors[:10]))
        self.app.toast(f"{done_count} música(s) enviada(s) ao celular.", "warning" if errors else "success", 5000)

    def _upload_failed(self, exc):
        self._end_upload()
        self.progress_label.configure(text="Envio interrompido.")
        self.conn_badge.set("Falha na conexão", "danger")
        self.conn_detail.configure(text=str(exc))
        self.app.toast(f"Falha ao enviar: {exc}", "danger", 6000)

    def cancel_upload(self):
        self.cancel.set()
        self.progress_label.configure(text="Cancelando após o bloco atual…")

    # ========================================================
    # BAIXAR E ENVIAR
    # ========================================================
    def download_and_send(self):
        missing = [i["entry"] for i in self.items if i["status"] == MISSING and i["entry"] is not None]
        if not missing:
            return
        entries = [dict(e, status=NEW) for e in missing]
        self._after_download_ids = {e["id"] for e in entries}
        self.app.start_download(entries, self.source_title, self.source_entries)

    def _on_batch_finished(self, summary):
        """Depois de um lote: envia ao celular o que foi pedido aqui ou, se ligado, tudo que foi baixado."""
        wanted = self._after_download_ids
        auto = self.app.settings.phone_auto_send and self.app.settings.phone_host.strip()
        if not wanted and not auto:
            return
        self._after_download_ids = None
        downloaded = {r.item.id for r in summary.results if r.status == "success"}
        ids = (wanted & downloaded) if wanted else downloaded
        if not ids:
            return

        def after_reload():
            def upload_new():
                items = [i for i in self.items if i["status"] == ONLY_PC
                         and i["entry"] is not None and i["entry"].get("id") in ids]
                if items:
                    self.app.toast(f"Enviando {len(items)} música(s) nova(s) ao celular…", "info")
                    self.send_selected(items)

            if wanted:
                self.compare(then=upload_new)
            else:
                # Envio automático: compara só os itens recém-baixados.
                self._auto_send([r for r in summary.results if r.status == "success" and r.item.id in ids])

        self.app.reload_library(on_done=after_reload)

    def _auto_send(self, results):
        config = PhoneConfig.from_settings(self.app.settings)
        entries = [{"id": r.item.id, "title": r.item.title, "position": r.item.position,
                    "duration": r.item.duration} for r in results]
        library = self.app.library

        def work():
            with PhoneClient(config) as client:
                return client.list_audio(), client.read_manifest()

        def done(result):
            phone_files, manifest = result
            items = compare_entries(entries, phone_files, manifest, library)
            for item in items:
                item["selected"] = item["status"] == ONLY_PC
            pending = [i for i in items if i["selected"]]
            if pending:
                self.items, self.source_entries, self.source_title = items, None, None
                self.send_selected(pending)

        def failed(exc):
            self.app.toast(f"Envio automático ao celular falhou: {exc}", "warning", 6000)

        self.app.run_task(work, done, failed)
