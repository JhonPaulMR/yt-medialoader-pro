import time
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from .. import theme as T
from ..downloader import FAILED, SKIPPED, SUCCESS
from ..notify import append_log_line
from ..utils import open_folder, truncate_text
from .base import Screen
from .widgets import PageHeader, StatChip

MAX_LOG_LINES = 4000


def _fmt_elapsed(seconds):
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


class ProgressScreen(Screen):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.items = []
        self.total = 0
        self.current_index = 0
        self.counts = {SUCCESS: 0, SKIPPED: 0, FAILED: 0}
        self.started_at = None
        self.running = False
        self.playlist_title = None
        self._tick_job = None

        # ---------------- cabeçalho ----------------
        self.header = PageHeader(self, "Progresso", "Nenhum download em andamento.")
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.btn_stop_now = T.danger_button(self.header.actions, "■  Parar agora",
                                            lambda: self.app.stop_download(True), width=140)
        self.btn_stop_now.pack(side="right", padx=(8, 0))
        self.btn_stop_after = T.secondary_button(self.header.actions, "Parar após a atual",
                                                 lambda: self.app.stop_download(False), width=160)
        self.btn_stop_after.pack(side="right")

        # ---------------- item atual + geral ----------------
        now = T.card(self)
        now.grid(row=1, column=0, sticky="ew")
        now.grid_columnconfigure(0, weight=1)

        self.lbl_counter = T.label(now, "AGUARDANDO", "caption", T.ACCENT)
        self.lbl_counter.grid(row=0, column=0, sticky="w", padx=24, pady=(20, 0))
        self.lbl_title = T.label(now, "Nenhum item em processamento", "title")
        self.lbl_title.grid(row=1, column=0, sticky="w", padx=24, pady=(2, 0))
        self.lbl_stage = T.label(now, "", "body", T.MUTED)
        self.lbl_stage.grid(row=2, column=0, sticky="w", padx=24, pady=(2, 10))

        self.item_bar = ctk.CTkProgressBar(now, height=8, progress_color=T.TEXT, fg_color=T.SURFACE_3)
        self.item_bar.grid(row=3, column=0, sticky="ew", padx=24)
        self.item_bar.set(0)
        self.lbl_transfer = T.label(now, "", "mono", T.MUTED)
        self.lbl_transfer.grid(row=4, column=0, sticky="w", padx=24, pady=(6, 14))

        overall_head = ctk.CTkFrame(now, fg_color="transparent")
        overall_head.grid(row=5, column=0, sticky="ew", padx=24)
        T.label(overall_head, "Progresso geral", "bold").pack(side="left")
        self.lbl_percent = T.label(overall_head, "0%", "bold", T.ACCENT)
        self.lbl_percent.pack(side="right")
        self.overall_bar = ctk.CTkProgressBar(now, height=12, progress_color=T.ACCENT, fg_color=T.SURFACE_3)
        self.overall_bar.grid(row=6, column=0, sticky="ew", padx=24, pady=(6, 22))
        self.overall_bar.set(0)

        # ---------------- estatísticas ----------------
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.grid(row=2, column=0, sticky="ew", pady=12)
        stats.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="stats")
        self.chip_ok = StatChip(stats, "concluídas", T.SUCCESS)
        self.chip_skip = StatChip(stats, "puladas (já baixadas)", T.MUTED)
        self.chip_fail = StatChip(stats, "falhas", T.DANGER)
        self.chip_time = StatChip(stats, "tempo decorrido", T.TEXT, "00:00")
        for col, chip in enumerate((self.chip_ok, self.chip_skip, self.chip_fail, self.chip_time)):
            chip.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))

        # ---------------- ações pós-lote ----------------
        self.after_bar = T.card(self, border_color=T.ACCENT)
        self.after_bar.grid_columnconfigure(0, weight=1)
        self.lbl_result = T.label(self.after_bar, "", "bold")
        self.lbl_result.grid(row=0, column=0, sticky="w", padx=18, pady=14)
        actions = ctk.CTkFrame(self.after_bar, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=12)
        self.btn_retry = T.primary_button(actions, "Tentar falhas de novo", self.retry_failures, width=180, height=34)
        self.btn_export = T.secondary_button(actions, "Exportar falhas", self.export_failures, width=130)
        T.secondary_button(actions, "Abrir pasta", self.open_folder, width=110).pack(side="right", padx=4)
        T.ghost_button(actions, "Voltar à seleção", lambda: self.app.navigate("selection"),
                       width=130).pack(side="right", padx=4)

        # ---------------- log ----------------
        log_card = T.card(self)
        log_card.grid(row=4, column=0, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)
        log_head = ctk.CTkFrame(log_card, fg_color="transparent")
        log_head.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        T.label(log_head, "LOG", "caption", T.SUBTLE).pack(side="left")
        T.ghost_button(log_head, "Salvar…", self.save_log, width=70, height=24).pack(side="right")
        T.ghost_button(log_head, "Copiar", self.copy_log, width=70, height=24).pack(side="right")
        T.ghost_button(log_head, "Limpar", self.clear_log, width=70, height=24).pack(side="right")

        self.log = ctk.CTkTextbox(
            log_card, font=T.mono(12), fg_color=T.BG, text_color="#d4d4d4",
            border_width=0, corner_radius=T.RADIUS_CONTROL, wrap="word",
        )
        self.log.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        for tag, color in (("error", "#f87171"), ("warning", "#fbbf24"), ("success", "#4ade80"),
                           ("muted", T.SUBTLE), ("info", "#d4d4d4"), ("time", "#525252")):
            self.log.tag_config(tag, foreground=color)
        self.log.configure(state="disabled")

        self._set_controls(running=False)

    # ========================================================
    # LOG
    # ========================================================
    def append_log(self, message, level="info"):
        append_log_line(f"{datetime.now():%H:%M:%S} [{level}] {message}")
        self.log.configure(state="normal")
        self.log.insert("end", datetime.now().strftime("%H:%M:%S  "), "time")
        self.log.insert("end", f"{message}\n", level if level in ("error", "warning", "success", "muted") else "info")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES:
            self.log.delete("1.0", f"{lines - MAX_LOG_LINES}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.log.get("1.0", "end-1c"))
        self.app.toast("Log copiado.", "success", 2000)

    def save_log(self):
        path = filedialog.asksaveasfilename(
            title="Salvar log", defaultextension=".txt",
            initialfile=f"medialoader-log-{datetime.now():%Y%m%d-%H%M}.txt",
            filetypes=[("Texto", "*.txt")],
        )
        if path:
            with open(path, "w", encoding="utf-8") as file:
                file.write(self.log.get("1.0", "end-1c"))
            self.app.toast("Log salvo.", "success", 2000)

    # ========================================================
    # CICLO DO LOTE
    # ========================================================
    def _set_controls(self, running):
        state = "normal" if running else "disabled"
        self.btn_stop_now.configure(state=state, text="■  Parar agora")
        self.btn_stop_after.configure(state=state, text="Parar após a atual")

    def begin(self, items, playlist_title, label=None):
        self.items = items
        self.total = len(items)
        self.current_index = 0
        self.counts = {SUCCESS: 0, SKIPPED: 0, FAILED: 0}
        self.started_at = time.monotonic()
        self.running = True
        self.playlist_title = playlist_title
        self.after_bar.grid_remove()
        prefix = f"{label} · " if label else ""
        self.header.set_subtitle(
            f"{prefix}{playlist_title or 'Itens avulsos'} · {self.total} item(ns)", T.MUTED)
        self.lbl_counter.configure(text=f"ITEM 0 DE {self.total}")
        self.lbl_title.configure(text="Preparando…")
        self.lbl_stage.configure(text="")
        self.lbl_transfer.configure(text="")
        self.item_bar.set(0)
        self.overall_bar.set(0)
        self.lbl_percent.configure(text="0%")
        for chip in (self.chip_ok, self.chip_skip, self.chip_fail):
            chip.set(0)
        self.chip_time.set("00:00")
        self.clear_log()
        self._set_controls(running=True)
        self._tick()

    def _tick(self):
        if self._tick_job:
            self.after_cancel(self._tick_job)
            self._tick_job = None
        if self.running and self.started_at is not None:
            self.chip_time.set(_fmt_elapsed(time.monotonic() - self.started_at))
            self._tick_job = self.after(1000, self._tick)

    def _set_overall(self, item_fraction=0.0):
        if not self.total:
            return
        done = max(self.current_index - 1, 0) + item_fraction
        fraction = min(done / self.total, 1.0)
        self.overall_bar.set(fraction)
        self.lbl_percent.configure(text=f"{fraction * 100:.0f}%")

    def on_stop_requested(self, immediately):
        self.btn_stop_after.configure(state="disabled", text="Parando após a atual…")
        if immediately:
            self.btn_stop_now.configure(state="disabled", text="Parando…")
            self.append_log("Parada imediata solicitada.", "warning")
        else:
            self.append_log("Parada solicitada: o item atual será concluído antes.", "warning")

    def handle_event(self, event, data):
        if event == "log":
            self.append_log(data["message"], data.get("level", "info"))
        elif event == "item_start":
            item = data["item"]
            self.current_index = data["index"]
            self.lbl_counter.configure(text=f"ITEM {data['index']} DE {data['total']}")
            self.lbl_title.configure(text=truncate_text(f"{item.position}. {item.title}", 90))
            self.lbl_stage.configure(text="Baixando…")
            self.lbl_transfer.configure(text="")
            self.item_bar.set(0)
            self._set_overall(0)
        elif event == "progress":
            fraction = data["percent"] / 100
            self.item_bar.set(fraction)
            parts = [f"{data['percent']:5.1f}%"]
            if data.get("size"):
                parts.append(data["size"])
            if data.get("speed"):
                parts.append(data["speed"])
            if data.get("eta"):
                parts.append(f"ETA {data['eta']}")
            self.lbl_transfer.configure(text="   ·   ".join(parts))
            self._set_overall(fraction * 0.9)  # 10% restantes = pós-processamento
        elif event == "stage":
            self.lbl_stage.configure(text=data["text"])
        elif event == "item_done":
            status = data["result"].status
            if status in self.counts:
                self.counts[status] += 1
            self.chip_ok.set(self.counts[SUCCESS])
            self.chip_skip.set(self.counts[SKIPPED])
            self.chip_fail.set(self.counts[FAILED])
            self._set_overall(1.0)
        elif event == "finished":
            self.finish(data["summary"])

    def finish(self, summary):
        self.running = False
        self._tick()
        self.chip_time.set(_fmt_elapsed(summary.elapsed))
        self._set_controls(running=False)
        ok, skipped, failed = summary.count(SUCCESS), summary.count(SKIPPED), summary.count(FAILED)
        self.chip_ok.set(ok)
        self.chip_skip.set(skipped)
        self.chip_fail.set(failed)
        self.item_bar.set(0)

        if summary.fatal_error:
            headline, color = f"O lote falhou: {summary.fatal_error}", T.DANGER
            self.lbl_counter.configure(text="ERRO")
        elif summary.cancelled:
            headline, color = "Lote interrompido.", T.WARNING
            self.lbl_counter.configure(text="INTERROMPIDO")
        else:
            headline = "Lote concluído." if not failed else f"Lote concluído com {failed} falha(s)."
            color = T.WARNING if failed else T.SUCCESS
            self.lbl_counter.configure(text="CONCLUÍDO")
            self.overall_bar.set(1)
            self.lbl_percent.configure(text="100%")

        self.lbl_title.configure(text=headline)
        self.lbl_stage.configure(text="")
        self.lbl_transfer.configure(text="")
        self.header.set_subtitle(
            f"{ok} baixada(s) · {skipped} pulada(s) · {failed} falha(s) · {_fmt_elapsed(summary.elapsed)}", color)
        self.append_log(f"Resumo: {ok} baixada(s), {skipped} pulada(s), {failed} falha(s).",
                        "success" if not failed and not summary.fatal_error else "warning")

        self.lbl_result.configure(text=headline, text_color=color)
        self.after_bar.configure(border_color=color)
        for btn in (self.btn_retry, self.btn_export):
            btn.pack_forget()
        if failed:
            self.btn_retry.configure(text=f"Tentar {failed} falha(s) de novo")
            self.btn_retry.pack(side="right", padx=4)
            self.btn_export.pack(side="right", padx=4)
        self.after_bar.grid(row=3, column=0, sticky="ew", pady=(0, 12))

    # ========================================================
    # AÇÕES PÓS-LOTE
    # ========================================================
    def retry_failures(self):
        summary = self.app.last_summary
        if not summary or not summary.failures:
            return
        entries = [
            {"id": r.item.id, "url": r.item.url, "title": r.item.title,
             "position": r.item.position, "duration": r.item.duration}
            for r in summary.failures
        ]
        self.app.start_download(entries, self.playlist_title)

    def export_failures(self):
        summary = self.app.last_summary
        if not summary or not summary.failures:
            return
        path = filedialog.asksaveasfilename(
            title="Exportar falhas", defaultextension=".txt",
            initialfile=f"falhas-{datetime.now():%Y%m%d-%H%M}.txt", filetypes=[("Texto", "*.txt")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as file:
            for result in summary.failures:
                item = result.item
                file.write(f"[{item.position}] {item.title}\n{item.url}\n")
                file.write(f"   erro: {result.error}\n")
                if result.hint:
                    file.write(f"   dica: {result.hint}\n")
                file.write("\n")
        self.app.toast("Lista de falhas exportada.", "success", 2500)

    def open_folder(self):
        open_folder(self.app.settings.folder)
