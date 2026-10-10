import customtkinter as ctk
import yt_dlp
import os
import threading
import shutil
import re
import math
import importlib.util
import subprocess
from datetime import datetime
from tkinter import filedialog, messagebox


# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

ITEMS_PER_PAGE = 50
DEFAULT_DOWNLOAD_FOLDER = "Downloads_Playlist_HQ"
SUPPORTED_MEDIA_EXTS = (".m4a", ".mp3", ".webm", ".mp4", ".mkv")


def get_ytdlp_version():
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:
        return getattr(yt_dlp, "__version__", "?")


# ============================================================
# UTILITÁRIOS
# ============================================================
def truncate_text(text, max_length=50):
    text = str(text or "")
    return text if len(text) <= max_length else text[: max_length - 3] + "..."


def clean_filename(filename):
    """Remove caracteres problemáticos para Windows e limita o nome."""
    filename = str(filename or "").strip()
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", filename)
    filename = re.sub(r"\s+", " ", filename).strip(" .")
    return filename[:180] or "audio_sem_nome"


def safe_join(directory, filename):
    """Garante que o caminho final fique dentro do diretório de destino."""
    filename = clean_filename(os.path.basename(filename))
    return os.path.join(directory, filename)


def playlist_position(entry, fallback_index):
    """Retorna a posição ORIGINAL da música na playlist."""
    value = entry.get("playlist_index")
    try:
        value = int(value)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return fallback_index + 1


def parse_positive_int(value, field_name):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} deve ser um número inteiro.")
    if number < 1:
        raise ValueError(f"{field_name} deve ser maior ou igual a 1.")
    return number


def guess_rename_action(filename):
    """Heurística para sugerir limpeza do nome do arquivo."""
    name_no_ext = os.path.splitext(filename)[0]

    if " - " in name_no_ext:
        parts = name_no_ext.split(" - ", 1)
    elif "–" in name_no_ext:
        parts = name_no_ext.split("–", 1)
    elif " - " not in name_no_ext and "-" in name_no_ext:
        # Evita mexer agressivamente em nomes com hífens comuns.
        return "Manter Original"
    else:
        return "Manter Original"

    left, right = parts[0].lower().strip(), parts[1].lower().strip()

    if re.match(r"^\d+[\s.]", left) or left.isdigit():
        return "Apagar FINAL"

    song_keywords = [
        "official", "lyric", "audio", "video", "visualizer",
        "remaster", "hd", "4k", "hq"
    ]
    if any(k in right for k in song_keywords):
        return "Apagar INÍCIO"

    extra_keywords = ["ao vivo", "cover", "live", "tour", "feat", "part.", "ft."]
    if any(k in right for k in extra_keywords):
        return "Apagar FINAL"

    return "Apagar INÍCIO"


def apply_regex_name(orig_name, mode):
    ext = os.path.splitext(orig_name)[1]
    if ext.lower() not in SUPPORTED_MEDIA_EXTS or mode == "Manter Original":
        return orig_name

    if mode == "Apagar INÍCIO":
        pattern = re.compile(
            r"^.+?\s+[-:]\s+(.+?)" + re.escape(ext) + r"$",
            re.IGNORECASE,
        )
        match = pattern.match(orig_name)
        if match:
            return clean_filename(match.group(1).strip()) + ext
    elif mode == "Apagar FINAL":
        pattern = re.compile(
            r"^(.+?)\s+[-:]\s+.*" + re.escape(ext) + r"$",
            re.IGNORECASE,
        )
        match = pattern.match(orig_name)
        if match:
            return clean_filename(match.group(1).strip()) + ext

    return orig_name


def build_unique_path(directory, filename, reserved_paths=None):
    """Evita colisão de nomes adicionando (1), (2), etc."""
    reserved_paths = reserved_paths or set()
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 1

    while os.path.exists(candidate) or os.path.abspath(candidate).lower() in {
        os.path.abspath(p).lower() for p in reserved_paths
    }:
        candidate = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1

    return candidate


# ============================================================
# LOGGER
# ============================================================
class YtDlpLogger:
    """Intercepta os logs do yt-dlp e envia para a GUI."""

    def __init__(self, log_callback):
        self.log_callback = log_callback

    def debug(self, msg):
        if not msg:
            return
        # Ignora spam do progresso porque a própria barra já mostra isso.
        if "[download]" in msg and (
            "ETA" in msg or "Destination" in msg or "100%" in msg
        ):
            return
        if not msg.startswith("[debug]"):
            self.log_callback(msg)

    def warning(self, msg):
        if msg:
            self.log_callback(f"⚠️ AVISO: {msg}")

    def error(self, msg):
        if msg:
            self.log_callback(f"❌ ERRO: {msg}")


# ============================================================
# APLICAÇÃO
# ============================================================
class MediaLoaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MediaLoader Pro Suite")
        self.geometry("1250x820")
        self.minsize(1100, 700)

        # ---------------- Estado global ----------------
        self.download_folder = DEFAULT_DOWNLOAD_FOLDER
        self.downloaded_cache = set()

        # ---------------- Playlist ----------------
        self.playlist_info = []
        self.filtered_sel_info = []
        self.selection_state = {}  # video_id -> bool
        self.current_page_sel = 0

        # ---------------- Renamer ----------------
        self.raw_files = []
        self.filtered_files = []
        self.renamer_state = {}
        self.current_page_ren = 0

        # ---------------- Diagnostics ----------------
        self.diag_missing_cache = []
        self.current_page_diag = 0

        # ---------------- Controles ----------------
        self.shift_pressed = False
        self.last_checked_index_sel = None
        self.last_checked_index_ren = None
        self.selected_urls = []
        self.download_running = False
        self.cancel_requested = False

        # Cookies:
        # "none" = nenhum cookie (padrão)
        # "browser" = navegador selecionado
        # "file" = arquivo cookies.txt
        self.cookie_mode = "none"
        self.cookie_browser = "chrome"
        self.cookie_file = ""

        self.setup_bindings()
        self.setup_ui()
        self.check_system()

    # ========================================================
    # EVENTOS / THREAD SAFETY
    # ========================================================
    def setup_bindings(self):
        self.bind(
            "<KeyPress-Shift_L>",
            lambda e: setattr(self, "shift_pressed", True),
        )
        self.bind(
            "<KeyPress-Shift_R>",
            lambda e: setattr(self, "shift_pressed", True),
        )
        self.bind(
            "<KeyRelease-Shift_L>",
            lambda e: setattr(self, "shift_pressed", False),
        )
        self.bind(
            "<KeyRelease-Shift_R>",
            lambda e: setattr(self, "shift_pressed", False),
        )

    def log_msg_safe(self, msg):
        if not msg:
            return
        # O widget pode ainda não existir em uma falha muito precoce.
        if hasattr(self, "log_console") and self.log_console.winfo_exists():
            self.after(
                0,
                lambda m=str(msg): self.log_console.insert(ctk.END, f"{m}\n"),
            )
            self.after(0, lambda: self.log_console.see(ctk.END))

    def set_status(self, text, color="white"):
        if hasattr(self, "status_label"):
            self.after(
                0,
                lambda: self.status_label.configure(
                    text=text, text_color=color
                ),
            )

    # ========================================================
    # UI
    # ========================================================
    def setup_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ---------------- SIDEBAR ----------------
        self.sidebar_frame = ctk.CTkFrame(
            self,
            width=225,
            corner_radius=0,
            fg_color="#121212",
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(7, weight=1)

        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="MediaLoader Pro",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#e50914",
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(25, 20))

        self.btn_new = ctk.CTkButton(
            self.sidebar_frame,
            text="+ New Download",
            font=ctk.CTkFont(weight="bold"),
            fg_color="#e50914",
            hover_color="#b20710",
            command=self.reset_to_dashboard,
        )
        self.btn_new.grid(
            row=1, column=0, padx=20, pady=(0, 20), sticky="ew"
        )

        self.btn_dash = ctk.CTkButton(
            self.sidebar_frame,
            text="Dashboard",
            anchor="w",
            fg_color="transparent",
            hover_color="#2a2a2a",
            command=lambda: self.show_frame("dashboard"),
        )
        self.btn_dash.grid(row=2, column=0, padx=15, pady=5, sticky="ew")

        self.btn_renamer = ctk.CTkButton(
            self.sidebar_frame,
            text="Renamer",
            anchor="w",
            fg_color="transparent",
            hover_color="#2a2a2a",
            command=lambda: self.show_frame("renamer"),
        )
        self.btn_renamer.grid(row=3, column=0, padx=15, pady=5, sticky="ew")

        self.btn_diag = ctk.CTkButton(
            self.sidebar_frame,
            text="Diagnostics",
            anchor="w",
            fg_color="transparent",
            hover_color="#2a2a2a",
            command=lambda: self.show_frame("diagnostics"),
        )
        self.btn_diag.grid(row=4, column=0, padx=15, pady=5, sticky="ew")

        self.ytdlp_badge = ctk.CTkLabel(
            self.sidebar_frame,
            text=f"yt-dlp {get_ytdlp_version()}",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
        )
        self.ytdlp_badge.grid(
            row=6, column=0, padx=20, pady=(10, 3), sticky="s"
        )

        self.ffmpeg_badge = ctk.CTkLabel(
            self.sidebar_frame,
            text="Verificando dependências...",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        )
        self.ffmpeg_badge.grid(
            row=7, column=0, padx=20, pady=(0, 20), sticky="s"
        )

        # ---------------- TELAS ----------------
        self.frames = {}
        self.build_dashboard()
        self.build_selection()
        self.build_progress()
        self.build_renamer()
        self.build_diagnostics()

        self.show_frame("dashboard")

    def show_frame(self, frame_name):
        for name, frame in self.frames.items():
            if name == frame_name:
                frame.grid(
                    row=0,
                    column=1,
                    sticky="nsew",
                    padx=30,
                    pady=30,
                )
            else:
                frame.grid_remove()

    def reset_to_dashboard(self):
        self.cancel_requested = False
        if hasattr(self, "url_entry"):
            self.url_entry.delete(0, ctk.END)
        self.set_status("")
        self.show_frame("dashboard")

    def check_system(self):
        if shutil.which("ffmpeg"):
            self.ffmpeg_badge.configure(
                text="✅ FFmpeg Detectado", text_color="#00C851"
            )
        else:
            self.ffmpeg_badge.configure(
                text="❌ FFmpeg Ausente", text_color="#ff4444"
            )

    # ========================================================
    # PAGINADOR
    # ========================================================
    def draw_paginator(
        self, frame_container, current_page, total_pages, callback_cmd
    ):
        for widget in frame_container.winfo_children():
            widget.destroy()

        if total_pages <= 1:
            return

        inner_frame = ctk.CTkFrame(
            frame_container, fg_color="transparent"
        )
        inner_frame.pack(anchor="center")

        btn_prev = ctk.CTkButton(
            inner_frame,
            text="<",
            width=40,
            state="normal" if current_page > 0 else "disabled",
            command=lambda: callback_cmd(current_page - 1),
        )
        btn_prev.pack(side="left", padx=2)

        def add_btn(page):
            is_active = page == current_page
            bg = "#e50914" if is_active else "#333333"
            hover = "#b20710" if is_active else "#444444"
            btn = ctk.CTkButton(
                inner_frame,
                text=str(page + 1),
                width=40,
                fg_color=bg,
                hover_color=hover,
                command=lambda px=page: callback_cmd(px),
            )
            btn.pack(side="left", padx=2)

        def add_dots():
            ctk.CTkLabel(
                inner_frame, text="...", width=30
            ).pack(side="left", padx=2)

        if total_pages <= 7:
            for page in range(total_pages):
                add_btn(page)
        else:
            if current_page < 4:
                for page in range(5):
                    add_btn(page)
                add_dots()
                add_btn(total_pages - 1)
            elif current_page > total_pages - 5:
                add_btn(0)
                add_dots()
                for page in range(total_pages - 5, total_pages):
                    add_btn(page)
            else:
                add_btn(0)
                add_dots()
                for page in range(current_page - 1, current_page + 2):
                    add_btn(page)
                add_dots()
                add_btn(total_pages - 1)

        btn_next = ctk.CTkButton(
            inner_frame,
            text=">",
            width=40,
            state=(
                "normal"
                if current_page < total_pages - 1
                else "disabled"
            ),
            command=lambda: callback_cmd(current_page + 1),
        )
        btn_next.pack(side="left", padx=2)

    # ========================================================
    # DASHBOARD
    # ========================================================
    def build_dashboard(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        self.frames["dashboard"] = frame

        ctk.CTkLabel(
            frame,
            text="Dashboard",
            font=ctk.CTkFont(size=32, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        ctk.CTkLabel(
            frame,
            text="Download em lote de playlists do YouTube.",
            text_color="#aaaaaa",
        ).grid(row=1, column=0, sticky="w", pady=(0, 25))

        url_frame = ctk.CTkFrame(
            frame, fg_color="#1e1e1e", corner_radius=8
        )
        url_frame.grid(
            row=2, column=0, sticky="ew", ipadx=20, ipady=20
        )
        url_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            url_frame,
            text="🔗 YouTube Playlist URL",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            url_frame,
            text=f"Pasta padrão: {self.download_folder}",
            text_color="#888888",
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=1, sticky="e")

        self.url_entry = ctk.CTkEntry(
            url_frame,
            placeholder_text="Cole a URL da Playlist aqui...",
            height=45,
            border_width=1,
            border_color="#333333",
        )
        self.url_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(10, 0),
            padx=(0, 15),
        )

        self.btn_analyze = ctk.CTkButton(
            url_frame,
            text="Load Playlist",
            height=45,
            fg_color="#e50914",
            hover_color="#b20710",
            font=ctk.CTkFont(weight="bold"),
            command=self.start_analysis,
        )
        self.btn_analyze.grid(row=1, column=1, pady=(10, 0))

        # -------- Configuração de cookies --------
        ctk.CTkLabel(
            url_frame,
            text="Autenticação / Cookies",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=2, column=0, sticky="w", pady=(18, 0))

        cookie_config = ctk.CTkFrame(
            url_frame, fg_color="transparent"
        )
        cookie_config.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(5, 0),
        )
        cookie_config.grid_columnconfigure(3, weight=1)

        self.cookie_mode_menu = ctk.CTkOptionMenu(
            cookie_config,
            values=[
                "Sem cookies",
                "Usar navegador",
                "Usar cookies.txt",
            ],
            width=170,
            command=self.on_cookie_mode_change,
        )
        self.cookie_mode_menu.set("Sem cookies")
        self.cookie_mode_menu.grid(row=0, column=0, padx=(0, 10))

        self.cookie_browser_menu = ctk.CTkOptionMenu(
            cookie_config,
            values=["Chrome", "Edge", "Firefox", "Brave"],
            width=130,
            command=self.on_cookie_browser_change,
        )
        self.cookie_browser_menu.set("Chrome")
        self.cookie_browser_menu.grid(row=0, column=1, padx=5)
        self.cookie_browser_menu.grid_remove()

        self.btn_cookie_file = ctk.CTkButton(
            cookie_config,
            text="Escolher cookies.txt",
            width=170,
            fg_color="#333333",
            hover_color="#444444",
            command=self.choose_cookie_file,
        )
        self.btn_cookie_file.grid(row=0, column=2, padx=5)
        self.btn_cookie_file.grid_remove()

        self.cookie_status = ctk.CTkLabel(
            cookie_config,
            text="Nenhum cookie será acessado automaticamente.",
            text_color="#8d8d8d",
            anchor="w",
        )
        self.cookie_status.grid(
            row=0, column=3, padx=(12, 0), sticky="ew"
        )

        self.status_label = ctk.CTkLabel(
            frame, text="", text_color="#ffbb33"
        )
        self.status_label.grid(
            row=3, column=0, sticky="w", pady=(10, 20)
        )

        cards_frame = ctk.CTkFrame(
            frame, fg_color="transparent"
        )
        cards_frame.grid(
            row=4, column=0, sticky="ew", pady=(10, 0)
        )
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            cards_frame,
            text="📊 Analisar Playlist\n\nExtraia metadados e contagem.",
            height=100,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            border_width=1,
            border_color="#333",
            command=lambda: self.url_entry.focus(),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 10))

        ctk.CTkButton(
            cards_frame,
            text="⚠️ Verificar Faltando\n\nCompare local vs online.",
            height=100,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            border_width=1,
            border_color="#333",
            command=lambda: self.show_frame("diagnostics"),
        ).grid(row=0, column=1, sticky="ew", padx=10)

        ctk.CTkButton(
            cards_frame,
            text="✏️ Renomeador em Massa\n\nPadronize nomes de arquivos.",
            height=100,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            border_width=1,
            border_color="#333",
            command=lambda: self.show_frame("renamer"),
        ).grid(row=0, column=2, sticky="ew", padx=(10, 0))

    def on_cookie_mode_change(self, choice):
        if choice == "Sem cookies":
            self.cookie_mode = "none"
            self.cookie_browser_menu.grid_remove()
            self.btn_cookie_file.grid_remove()
            self.cookie_status.configure(
                text="Nenhum cookie do navegador será acessado."
            )
        elif choice == "Usar navegador":
            self.cookie_mode = "browser"
            self.cookie_browser_menu.grid()
            self.btn_cookie_file.grid_remove()
            self.cookie_status.configure(
                text=(
                    "O navegador escolhido só será lido durante o download."
                )
            )
        else:
            self.cookie_mode = "file"
            self.cookie_browser_menu.grid_remove()
            self.btn_cookie_file.grid()
            self.cookie_status.configure(
                text=(
                    os.path.basename(self.cookie_file)
                    if self.cookie_file
                    else "Selecione um arquivo cookies.txt."
                )
            )

    def on_cookie_browser_change(self, choice):
        self.cookie_browser = choice.lower()
        self.cookie_status.configure(
            text=f"Navegador configurado: {choice}."
        )

    def choose_cookie_file(self):
        selected = filedialog.askopenfilename(
            title="Selecionar cookies.txt",
            filetypes=[
                ("Cookies TXT", "*.txt"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if selected:
            self.cookie_file = os.path.abspath(selected)
            self.cookie_status.configure(
                text=f"Cookies: {os.path.basename(selected)}"
            )

    # ========================================================
    # SELEÇÃO
    # ========================================================
    def build_selection(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)
        self.frames["selection"] = frame

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(
            row=0, column=0, sticky="ew", pady=(0, 10)
        )
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Playlist Selection",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.selection_subtitle = ctk.CTkLabel(
            header,
            text="Carregando itens...",
            text_color="#aaaaaa",
        )
        self.selection_subtitle.grid(row=1, column=0, sticky="w")

        self.btn_start_dl = ctk.CTkButton(
            header,
            text="Start Download",
            height=40,
            fg_color="#e50914",
            hover_color="#b20710",
            font=ctk.CTkFont(weight="bold"),
            command=self.start_download,
        )
        self.btn_start_dl.grid(
            row=0, column=1, rowspan=2, sticky="e"
        )

        # -------- Filtros --------
        filters = ctk.CTkFrame(
            frame, fg_color="transparent"
        )
        filters.grid(row=1, column=0, sticky="ew", pady=5)

        self.seg_filter = ctk.CTkSegmentedButton(
            filters,
            values=["Todos", "Apenas Novos", "Já Baixados"],
            command=self.apply_list_filter,
            selected_color="#e50914",
            selected_hover_color="#b20710",
        )
        self.seg_filter.pack(side="left", padx=(0, 20))
        self.seg_filter.set("Todos")

        ctk.CTkButton(
            filters,
            text="Selecionar Todos",
            width=135,
            fg_color="#333333",
            hover_color="#444444",
            command=self.select_all,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            filters,
            text="Desmarcar Todos",
            width=135,
            fg_color="#333333",
            hover_color="#444444",
            command=self.deselect_all,
        ).pack(side="left")

        # -------- Intervalo ORIGINAL --------
        range_frame = ctk.CTkFrame(
            frame,
            fg_color="#1e1e1e",
            corner_radius=8,
        )
        range_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(8, 8),
        )

        ctk.CTkLabel(
            range_frame,
            text="Selecionar intervalo da playlist:",
            font=ctk.CTkFont(weight="bold"),
        ).pack(side="left", padx=(12, 8), pady=10)

        self.range_start_entry = ctk.CTkEntry(
            range_frame,
            width=80,
            placeholder_text="Início",
        )
        self.range_start_entry.pack(
            side="left", padx=(0, 6), pady=10
        )

        ctk.CTkLabel(
            range_frame, text="até"
        ).pack(side="left", padx=4)

        self.range_end_entry = ctk.CTkEntry(
            range_frame,
            width=80,
            placeholder_text="Fim",
        )
        self.range_end_entry.pack(
            side="left", padx=(6, 10), pady=10
        )

        self.only_new_interval = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            range_frame,
            text="Ignorar já baixadas",
            variable=self.only_new_interval,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            range_frame,
            text="Selecionar Intervalo",
            width=155,
            fg_color="#333333",
            hover_color="#444444",
            command=self.select_interval,
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            range_frame,
            text="Ex.: 1 até 213",
            text_color="#777777",
        ).pack(side="right", padx=15)

        # -------- Lista --------
        self.scroll_selection = ctk.CTkScrollableFrame(
            frame,
            fg_color="#1e1e1e",
            corner_radius=8,
        )
        self.scroll_selection.grid(
            row=3,
            column=0,
            sticky="nsew",
            pady=(8, 0),
        )
        self.ui_sel_checkboxes = []

        self.pag_frame_sel = ctk.CTkFrame(
            frame, fg_color="transparent"
        )
        self.pag_frame_sel.grid(
            row=4, column=0, sticky="ew", pady=10
        )

    # ========================================================
    # PROGRESSO
    # ========================================================
    def build_progress(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        self.frames["progress"] = frame

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Active Processing",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 20))

        self.btn_cancel = ctk.CTkButton(
            header,
            text="Parar após a música atual",
            width=190,
            fg_color="#333333",
            hover_color="#444444",
            command=self.request_cancel_download,
        )
        self.btn_cancel.grid(
            row=0, column=1, sticky="e", pady=(0, 20)
        )

        p_frame = ctk.CTkFrame(
            frame, fg_color="#1e1e1e", corner_radius=8
        )
        p_frame.grid(row=1, column=0, sticky="ew")

        self.lbl_batch_progress = ctk.CTkLabel(
            p_frame,
            text="Progresso Geral: Calculando lote...",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#00C851",
        )
        self.lbl_batch_progress.pack(
            anchor="w", padx=25, pady=(20, 5)
        )

        self.lbl_current_song = ctk.CTkLabel(
            p_frame,
            text="Aguardando inicialização...",
            font=ctk.CTkFont(size=13),
            text_color="#aaaaaa",
        )
        self.lbl_current_song.pack(
            anchor="w", padx=25, pady=(0, 5)
        )

        self.lbl_speed_eta = ctk.CTkLabel(
            p_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        )
        self.lbl_speed_eta.pack(
            anchor="w", padx=25, pady=(0, 8)
        )

        self.progress_bar = ctk.CTkProgressBar(
            p_frame, progress_color="#e50914", height=12
        )
        self.progress_bar.pack(
            fill="x", padx=25, pady=(0, 25)
        )
        self.progress_bar.set(0)

        log_frame = ctk.CTkFrame(
            frame, fg_color="transparent"
        )
        log_frame.grid(
            row=2, column=0, sticky="nsew", pady=(20, 0)
        )
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            log_frame,
            text="CONSOLE DE LOGS",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#888888",
        ).grid(row=0, column=0, sticky="w")

        self.log_console = ctk.CTkTextbox(
            log_frame,
            font=("Consolas", 13),
            fg_color="#121212",
            text_color="#e0e0e0",
            border_width=1,
            border_color="#333333",
        )
        self.log_console.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(5, 0),
        )

    # ========================================================
    # RENAMER
    # ========================================================
    def build_renamer(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)
        self.frames["renamer"] = frame

        header = ctk.CTkFrame(
            frame, fg_color="transparent"
        )
        header.grid(
            row=0, column=0, sticky="ew", pady=(0, 10)
        )
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Limpeza e Renomeação Inteligente",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=(
                "A heurística sugere mudanças; suas edições manuais "
                "são preservadas ao trocar de página ou filtro."
            ),
            text_color="#aaaaaa",
        ).grid(row=1, column=0, sticky="w")

        controls = ctk.CTkFrame(
            frame, fg_color="#1e1e1e", corner_radius=8
        )
        controls.grid(
            row=1, column=0, sticky="ew", pady=10,
            ipadx=10, ipady=10
        )

        ctk.CTkLabel(
            controls,
            text="Filtrar:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(10, 5))

        self.filter_var = ctk.CTkOptionMenu(
            controls,
            values=[
                "Todos",
                "Apagar INÍCIO",
                "Apagar FINAL",
                "Manter Original",
            ],
            fg_color="#333",
            button_color="#444",
            command=self.apply_rename_filters,
        )
        self.filter_var.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(
            controls,
            text="Ordenar:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(0, 5))

        self.sort_var = ctk.CTkOptionMenu(
            controls,
            values=[
                "Nome (A-Z)",
                "Nome (Z-A)",
                "Mais Recentes",
                "Mais Antigos",
            ],
            fg_color="#333",
            button_color="#444",
            command=self.apply_rename_filters,
        )
        self.sort_var.pack(side="left", padx=(0, 20))

        ctk.CTkButton(
            controls,
            text="Ler Pasta Local",
            height=35,
            fg_color="#e50914",
            hover_color="#b20710",
            command=self.init_renamer_data,
        ).pack(side="right", padx=10)

        self.btn_apply_rename = ctk.CTkButton(
            frame,
            text="Aplicar Correções",
            height=40,
            fg_color="#e50914",
            hover_color="#b20710",
            font=ctk.CTkFont(weight="bold"),
            state="disabled",
            command=self.execute_rename,
        )
        self.btn_apply_rename.grid(
            row=2, column=0, sticky="e", pady=(0, 10)
        )

        self.scroll_renamer = ctk.CTkScrollableFrame(
            frame, fg_color="#1e1e1e", corner_radius=8
        )
        self.scroll_renamer.grid(
            row=3, column=0, sticky="nsew", pady=(0, 10)
        )
        self.ui_ren_rows = []

        self.pag_frame_ren = ctk.CTkFrame(
            frame, fg_color="transparent"
        )
        self.pag_frame_ren.grid(
            row=4, column=0, sticky="ew", pady=10
        )

    # ========================================================
    # DIAGNÓSTICO
    # ========================================================
    def build_diagnostics(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)
        self.frames["diagnostics"] = frame

        ctk.CTkLabel(
            frame,
            text="Missing Media Diagnostics",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )

        ctk.CTkLabel(
            frame,
            text="Compare o arquivo de histórico local com a playlist online.",
            text_color="#aaaaaa",
        ).grid(row=1, column=0, sticky="w")

        controls = ctk.CTkFrame(
            frame, fg_color="transparent"
        )
        controls.grid(
            row=2, column=0, sticky="ew", pady=20
        )

        self.diag_url_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Cole a URL da Playlist aqui...",
            width=450,
            height=40,
            border_width=1,
            border_color="#333333",
        )
        self.diag_url_entry.pack(
            side="left", padx=(0, 15)
        )

        ctk.CTkButton(
            controls,
            text="Verificar Falhas",
            fg_color="#e50914",
            hover_color="#b20710",
            height=40,
            font=ctk.CTkFont(weight="bold"),
            command=self.start_diagnostics,
        ).pack(side="left")

        self.diag_status = ctk.CTkLabel(
            controls,
            text="",
            text_color="#aaaaaa",
        )
        self.diag_status.pack(
            side="left", padx=15
        )

        self.scroll_diag = ctk.CTkScrollableFrame(
            frame, fg_color="#1e1e1e", corner_radius=8
        )
        self.scroll_diag.grid(
            row=3, column=0, sticky="nsew", pady=(0, 10)
        )

        self.pag_frame_diag = ctk.CTkFrame(
            frame, fg_color="transparent"
        )
        self.pag_frame_diag.grid(
            row=4, column=0, sticky="ew", pady=10
        )

    # ========================================================
    # COOKIES / YT-DLP
    # ========================================================
    def _build_cookie_opts(self):
        """
        Constrói somente as opções de cookies escolhidas pelo usuário.
        Importante: NÃO tenta abrir Chrome/Edge/Firefox automaticamente.
        """
        opts = {}

        if self.cookie_mode == "browser":
            browser = self.cookie_browser
            opts["cookiesfrombrowser"] = (browser,)
            self.log_msg_safe(
                f"🔐 Cookies habilitados manualmente via {browser.upper()}."
            )
            return opts

        if self.cookie_mode == "file":
            if not self.cookie_file or not os.path.isfile(self.cookie_file):
                raise FileNotFoundError(
                    "O arquivo cookies.txt não foi selecionado ou não existe."
                )
            opts["cookiefile"] = self.cookie_file
            self.log_msg_safe(
                f"🔐 Usando cookies.txt: "
                f"{os.path.basename(self.cookie_file)}"
            )

        return opts

    def _validate_ytdlp_environment(self):
        """
        Verifica os componentes necessários para o YouTube antes de
        iniciar um lote grande. O problema EJS deve ser detectado aqui,
        em vez de aparecer repetidamente em todas as músicas.
        """
        deno_path = shutil.which("deno")
        ejs_available = importlib.util.find_spec("yt_dlp_ejs") is not None

        if not deno_path:
            raise RuntimeError(
                "O Deno não foi encontrado no PATH. O yt-dlp atual precisa "
                "de um runtime JavaScript para resolver os desafios do YouTube. "
                "Instale o Deno e abra um novo terminal.\n\n"
                "Windows: winget install DenoLand.Deno"
            )

        try:
            deno_version = subprocess.run(
                [deno_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            ).stdout.strip().splitlines()[0]
        except Exception:
            deno_version = "versão não identificada"

        self.log_msg_safe(f"🧩 Runtime JS: {deno_version}")

        if not ejs_available:
            self.log_msg_safe(
                "⚠️ yt-dlp-ejs não está instalado no mesmo ambiente do yt-dlp."
            )
            self.log_msg_safe(
                '➡️ Execute: py -m pip install -U "yt-dlp[default]"'
            )
            # Não prosseguimos: sem EJS, o lote pode falhar em massa.
            raise RuntimeError(
                "O pacote yt-dlp-ejs não está instalado/atualizado. "
                'Execute: py -m pip install -U "yt-dlp[default]"'
            )

        self.log_msg_safe("✅ EJS challenge solver disponível.")
        return deno_path

    def _base_ydl_opts(self, archive_file):
        """Opções comuns de download."""
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            # YouTube passou a exigir resolução de desafios JavaScript.
            # Deno é o runtime recomendado pelo yt-dlp e já é o runtime
            # padrão quando está disponível no PATH.
            "js_runtimes": {"deno": {}},
            "outtmpl": os.path.join(
                self.download_folder,
                "%(title)s.%(ext)s",
            ),
            "download_archive": archive_file,
            "ignoreerrors": False,
            "noplaylist": True,
            "continuedl": True,
            "retries": 5,
            "fragment_retries": 5,
            "windowsfilenames": True,
            "writethumbnail": True,
            "progress_hooks": [self._progress_hook],
            "logger": YtDlpLogger(self.log_msg_safe),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "320",
                },
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                },
                {
                    "key": "FFmpegThumbnailsConvertor",
                    "format": "jpg",
                },
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                },
            ],
            "quiet": True,
            "no_warnings": False,
        }
        opts.update(self._build_cookie_opts())
        return opts

    # ========================================================
    # ANÁLISE DA PLAYLIST
    # ========================================================
    def start_analysis(self):
        url = self.url_entry.get().strip()
        if not url:
            self.set_status(
                "Cole uma URL de playlist antes de analisar.",
                "#ffbb33",
            )
            return

        self.status_label.configure(
            text="Extraindo dados da playlist... Aguarde.",
            text_color="white",
        )
        self.btn_analyze.configure(state="disabled")
        threading.Thread(
            target=self._analyze_worker,
            args=(url,),
            daemon=True,
        ).start()

    def _analyze_worker(self, url):
        try:
            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "ignoreerrors": True,
                "noplaylist": False,
                "js_runtimes": {"deno": {}},
            }

            # Cookies só são utilizados se o usuário explicitamente os ativou.
            ydl_opts.update(self._build_cookie_opts())

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info or "entries" not in info:
                raise ValueError(
                    "A URL não retornou uma playlist válida."
                )

            entries = []
            for index, entry in enumerate(info.get("entries") or []):
                if entry is None:
                    continue
                item = dict(entry)
                item["_playlist_pos"] = playlist_position(
                    item, index
                )
                entries.append(item)

            if not entries:
                raise ValueError(
                    "Nenhuma música utilizável foi encontrada na playlist."
                )

            self.playlist_info = entries
            self.after(0, self._prepare_selection)

        except Exception as exc:
            msg = str(exc)
            self.log_msg_safe(
                f"❌ Falha ao analisar playlist: {msg}"
            )
            self.set_status(
                f"Erro ao analisar: {msg}",
                "#ff4444",
            )
        finally:
            self.after(
                0,
                lambda: self.btn_analyze.configure(
                    state="normal"
                ),
            )

    def _read_download_archive(self):
        archive_file = os.path.join(
            self.download_folder, ".archive.txt"
        )
        downloaded = set()

        if os.path.exists(archive_file):
            try:
                with open(
                    archive_file,
                    "r",
                    encoding="utf-8",
                    errors="ignore",
                ) as file:
                    for line in file:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            downloaded.add(parts[1])
            except OSError as exc:
                self.log_msg_safe(
                    f"⚠️ Não foi possível ler .archive.txt: {exc}"
                )

        return downloaded

    def _prepare_selection(self):
        self.downloaded_cache = self._read_download_archive()
        self.selection_state.clear()

        for entry in self.playlist_info:
            video_id = entry.get("id")
            if video_id:
                self.selection_state[video_id] = (
                    video_id not in self.downloaded_cache
                )

        self.filtered_sel_info = list(self.playlist_info)
        self.current_page_sel = 0
        self.seg_filter.set("Todos")

        total = len(self.playlist_info)
        new_count = sum(
            1
            for item in self.playlist_info
            if item.get("id") not in self.downloaded_cache
        )

        self.selection_subtitle.configure(
            text=(
                f"Encontrados {total} vídeos • "
                f"{new_count} ainda não registrados no arquivo de histórico."
            )
        )

        self.show_frame("selection")
        self.render_selection_page()

    # ========================================================
    # FILTROS / INTERVALO DA PLAYLIST
    # ========================================================
    def apply_list_filter(self, choice):
        filtered = []

        for video in self.playlist_info:
            video_id = video.get("id", "")
            is_new = video_id not in self.downloaded_cache

            if choice == "Todos":
                filtered.append(video)
            elif choice == "Apenas Novos" and is_new:
                filtered.append(video)
            elif choice == "Já Baixados" and not is_new:
                filtered.append(video)

        self.filtered_sel_info = filtered
        self.goto_page_sel(0)

    def select_interval(self):
        if not self.playlist_info:
            messagebox.showwarning(
                "Playlist",
                "Analise uma playlist primeiro.",
            )
            return

        try:
            start = parse_positive_int(
                self.range_start_entry.get(),
                "Início",
            )
            end = parse_positive_int(
                self.range_end_entry.get(),
                "Fim",
            )
        except ValueError as exc:
            messagebox.showerror(
                "Intervalo inválido",
                str(exc),
            )
            return

        if start > end:
            messagebox.showerror(
                "Intervalo inválido",
                "O início não pode ser maior que o fim.",
            )
            return

        max_pos = max(
            playlist_position(item, idx)
            for idx, item in enumerate(self.playlist_info)
        )

        if start > max_pos:
            messagebox.showwarning(
                "Fora da playlist",
                f"O início {start} é maior que a última posição ({max_pos}).",
            )
            return

        end = min(end, max_pos)
        only_new = bool(self.only_new_interval.get())

        selected_count = 0

        # Desmarca tudo primeiro para o intervalo representar exatamente
        # o que o usuário digitou.
        for video_id in list(self.selection_state.keys()):
            self.selection_state[video_id] = False

        for fallback_index, video in enumerate(self.playlist_info):
            pos = playlist_position(video, fallback_index)
            if not (start <= pos <= end):
                continue

            video_id = video.get("id")
            if not video_id:
                continue

            is_new = video_id not in self.downloaded_cache
            if only_new and not is_new:
                continue

            self.selection_state[video_id] = True
            selected_count += 1

        self.seg_filter.set("Todos")
        self.filtered_sel_info = list(self.playlist_info)
        self.current_page_sel = max(
            0,
            min(
                (start - 1) // ITEMS_PER_PAGE,
                max(
                    0,
                    math.ceil(len(self.filtered_sel_info) / ITEMS_PER_PAGE)
                    - 1,
                ),
            ),
        )
        self.render_selection_page()

        suffix = " (somente novas)" if only_new else ""
        self.set_status(
            f"Intervalo {start}–{end}{suffix}: "
            f"{selected_count} música(s) selecionada(s).",
            "#00C851",
        )

    def goto_page_sel(self, page_index):
        total_pages = max(
            1,
            math.ceil(len(self.filtered_sel_info) / ITEMS_PER_PAGE),
        )
        self.current_page_sel = max(
            0, min(page_index, total_pages - 1)
        )
        self.render_selection_page()

    def render_selection_page(self):
        for widget in self.scroll_selection.winfo_children():
            widget.destroy()
        self.ui_sel_checkboxes.clear()

        total_items = len(self.filtered_sel_info)
        total_pages = math.ceil(total_items / ITEMS_PER_PAGE)
        self.draw_paginator(
            self.pag_frame_sel,
            self.current_page_sel,
            total_pages,
            self.goto_page_sel,
        )

        start_idx = self.current_page_sel * ITEMS_PER_PAGE
        end_idx = min(
            start_idx + ITEMS_PER_PAGE,
            total_items,
        )
        self.last_checked_index_sel = None

        for visible_index, i in enumerate(
            range(start_idx, end_idx)
        ):
            video = self.filtered_sel_info[i]
            video_id = video.get("id", "")
            title = video.get("title", "Título Desconhecido")
            pos = playlist_position(video, i)

            is_new = video_id not in self.downloaded_cache
            status = "NEW" if is_new else "DOWNLOADED"
            text_color = "#666666" if not is_new else "white"

            display_title = truncate_text(
                f"{pos}. {title} [{status}]",
                max_length=100,
            )

            cb_var = ctk.IntVar(
                value=1 if self.selection_state.get(video_id, False) else 0
            )

            def on_check(
                vid=video_id,
                var=cb_var,
                idx=visible_index,
            ):
                self.selection_state[vid] = bool(var.get())
                self._handle_sel_shift_click(idx)

            cb = ctk.CTkCheckBox(
                self.scroll_selection,
                text=display_title,
                text_color=text_color,
                font=ctk.CTkFont(weight="bold"),
                variable=cb_var,
                command=on_check,
            )
            cb.pack(
                fill="x",
                pady=4,
                padx=15,
                anchor="n",
            )

            self.ui_sel_checkboxes.append(
                {
                    "cb": cb,
                    "var": cb_var,
                    "video_id": video_id,
                    "position": pos,
                }
            )

    def _handle_sel_shift_click(self, current_index):
        if (
            self.shift_pressed
            and self.last_checked_index_sel is not None
            and self.ui_sel_checkboxes
        ):
            target_state = self.ui_sel_checkboxes[
                current_index
            ]["var"].get()

            start = min(
                self.last_checked_index_sel,
                current_index,
            )
            end = max(
                self.last_checked_index_sel,
                current_index,
            )

            for i in range(start, end + 1):
                item = self.ui_sel_checkboxes[i]
                item["var"].set(target_state)
                self.selection_state[
                    item["video_id"]
                ] = bool(target_state)

        self.last_checked_index_sel = current_index

    def select_all(self):
        # Agora atua sobre TODA a lista filtrada, não apenas sobre a página.
        for video in self.filtered_sel_info:
            video_id = video.get("id")
            if video_id:
                self.selection_state[video_id] = True
        self.render_selection_page()

    def deselect_all(self):
        for video in self.filtered_sel_info:
            video_id = video.get("id")
            if video_id:
                self.selection_state[video_id] = False
        self.render_selection_page()

    # ========================================================
    # DOWNLOAD
    # ========================================================
    def start_download(self):
        self.selected_urls = []

        for video in self.playlist_info:
            video_id = video.get("id")
            if not video_id or not self.selection_state.get(
                video_id, False
            ):
                continue

            self.selected_urls.append(
                {
                    "id": video_id,
                    "url": (
                        f"https://www.youtube.com/watch?v={video_id}"
                    ),
                    "title": video.get(
                        "title",
                        "Título Desconhecido",
                    ),
                    "position": video.get(
                        "_playlist_pos",
                        len(self.selected_urls) + 1,
                    ),
                }
            )

        if not self.selected_urls:
            messagebox.showinfo(
                "Download",
                "Nenhuma música foi selecionada.",
            )
            return

        # Valida EJS/Deno antes de começar um lote potencialmente grande.
        try:
            self._validate_ytdlp_environment()
        except RuntimeError as exc:
            self.log_msg_safe(f"❌ Ambiente do YouTube não está pronto: {exc}")
            messagebox.showerror("Ambiente yt-dlp incompleto", str(exc))
            return

        if not shutil.which("ffmpeg"):
            proceed = messagebox.askyesno(
                "FFmpeg ausente",
                (
                    "O FFmpeg não foi encontrado no PATH. "
                    "A conversão/thumbnail provavelmente irá falhar.\n\n"
                    "Deseja continuar mesmo assim?"
                ),
            )
            if not proceed:
                return

        self.download_running = True
        self.cancel_requested = False
        self.btn_start_dl.configure(state="disabled")
        self.show_frame("progress")
        self.log_console.delete("1.0", ctk.END)
        self.progress_bar.set(0)
        self.lbl_speed_eta.configure(text="")
        self.btn_cancel.configure(state="normal")

        os.makedirs(self.download_folder, exist_ok=True)

        threading.Thread(
            target=self._download_worker,
            daemon=True,
        ).start()

    def request_cancel_download(self):
        if self.download_running:
            self.cancel_requested = True
            self.btn_cancel.configure(
                state="disabled",
                text="Parando após atual...",
            )
            self.log_msg_safe(
                "⏹️ Cancelamento solicitado. "
                "A música atual será concluída antes de parar."
            )

    def _progress_hook(self, data):
        status = data.get("status")

        if status == "downloading":
            percent = data.get("_percent")
            if not isinstance(percent, (int, float)):
                raw = str(
                    data.get("_percent_str", "0")
                )
                match = re.search(
                    r"([0-9]+(?:\.[0-9]+)?)",
                    raw,
                )
                percent = (
                    float(match.group(1))
                    if match
                    else 0.0
                )

            speed = data.get("_speed_str", "")
            eta = data.get("_eta_str", "")
            percent = max(0.0, min(100.0, float(percent)))

            self.after(
                0,
                lambda p=percent: self.progress_bar.set(
                    p / 100.0
                ),
            )
            self.after(
                0,
                lambda s=speed, e=eta: self.lbl_speed_eta.configure(
                    text=(
                        f"Velocidade: {s or '-'}    "
                        f"ETA: {e or '-'}"
                    )
                ),
            )

        elif status == "finished":
            self.after(
                0,
                lambda: self.lbl_current_song.configure(
                    text=(
                        "Download concluído. "
                        "Executando pós-processamento FFmpeg..."
                    )
                ),
            )

    def _download_worker(self):
        archive_file = os.path.join(
            self.download_folder,
            ".archive.txt",
        )

        success_count = 0
        failure_count = 0
        skipped_count = 0
        total = len(self.selected_urls)

        try:
            try:
                ydl_opts = self._base_ydl_opts(archive_file)
            except Exception as exc:
                raise RuntimeError(
                    f"Configuração de cookies/yt-dlp inválida: {exc}"
                ) from exc

            self.log_msg_safe(
                f"▶️ Iniciando lote com {total} música(s)."
            )

            for index, item in enumerate(
                self.selected_urls, 1
            ):
                if self.cancel_requested:
                    break

                title = item["title"]
                position = item["position"]

                self.after(
                    0,
                    lambda i=index, t=total: self.lbl_batch_progress.configure(
                        text=(
                            f"Progresso Geral: {i} / {t} "
                            "músicas processadas"
                        )
                    ),
                )
                self.after(
                    0,
                    lambda p=position, tt=title: self.lbl_current_song.configure(
                        text=f"[{p}] {truncate_text(tt, 100)}"
                    ),
                )
                self.after(
                    0,
                    lambda: self.progress_bar.set(0),
                )

                try:
                    # O archive é consultado novamente pelo próprio yt-dlp.
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        result = ydl.download([item["url"]])

                    if result == 0:
                        success_count += 1
                    else:
                        failure_count += 1
                        self.log_msg_safe(
                            f"❌ Falha no item [{position}] "
                            f"(código yt-dlp={result})."
                        )

                except Exception as exc:
                    error_text = str(exc)
                    lower = error_text.lower()

                    # Mensagem específica para o problema relatado.
                    if (
                        "signature solving failed" in lower
                        or "n challenge solving failed" in lower
                        or "the page needs to be reloaded" in lower
                    ):
                        self.log_msg_safe(
                            "🧩 Falha EJS/JavaScript do YouTube: o vídeo não "
                            "foi liberado para download porque o desafio do "
                            "player não foi resolvido."
                        )
                        self.log_msg_safe(
                            "➡️ Confirme Deno + yt-dlp-ejs instalados no "
                            "mesmo ambiente do py que executa este programa."
                        )
                    elif (
                        "failed to decrypt with dpapi" in lower
                        or "could not copy chrome cookie database" in lower
                    ):
                        self.log_msg_safe(
                            "🔐 O navegador não permitiu ler os cookies "
                            "(DPAPI/banco do Chrome)."
                        )
                        self.log_msg_safe(
                            "➡️ Tente 'Sem cookies' ou use um cookies.txt "
                            "exportado de uma sessão recente."
                        )

                    failure_count += 1
                    self.log_msg_safe(
                        f"❌ ERRO no item [{position}] {title}: {exc}"
                    )

            self.after(
                0,
                lambda: self.progress_bar.set(
                    0 if self.cancel_requested else 1.0
                ),
            )

            if self.cancel_requested:
                self.log_msg_safe(
                    "⏹️ Lote interrompido pelo usuário."
                )
                summary = (
                    f"Interrompido: {success_count} concluída(s), "
                    f"{failure_count} falha(s)."
                )
            else:
                summary = (
                    f"Finalizado: {success_count} sucesso(s), "
                    f"{failure_count} falha(s)."
                )

            self.log_msg_safe(f"✔️ {summary}")

            self.after(
                0,
                lambda s=success_count, f=failure_count: (
                    self.lbl_batch_progress.configure(
                        text=(
                            f"Resultado: {s} sucesso(s) • "
                            f"{f} falha(s)"
                        )
                    )
                ),
            )
            self.after(
                0,
                lambda: self.lbl_current_song.configure(
                    text=(
                        "Lote interrompido."
                        if self.cancel_requested
                        else "Processamento concluído."
                    )
                ),
            )

        except Exception as exc:
            self.log_msg_safe(
                f"❌ ERRO GRAVE no lote: {exc}"
            )
            self.after(
                0,
                lambda e=str(exc): self.lbl_current_song.configure(
                    text=f"Falha no processamento: {e}"
                ),
            )
        finally:
            self.download_running = False
            self.after(
                0,
                lambda: self.btn_start_dl.configure(
                    state="normal"
                ),
            )
            self.after(
                0,
                lambda: self.btn_cancel.configure(
                    state="normal",
                    text="Parar após a música atual",
                ),
            )

    # ========================================================
    # RENAMER
    # ========================================================
    def init_renamer_data(self):
        if not os.path.exists(self.download_folder):
            messagebox.showinfo(
                "Renamer",
                f"A pasta '{self.download_folder}' não existe.",
            )
            return

        self.raw_files = []

        try:
            with os.scandir(
                self.download_folder
            ) as entries:
                for entry in entries:
                    if (
                        entry.is_file()
                        and entry.name.lower().endswith(
                            SUPPORTED_MEDIA_EXTS
                        )
                    ):
                        try:
                            mtime = entry.stat().st_mtime
                        except OSError:
                            mtime = 0
                        self.raw_files.append(
                            {
                                "name": entry.name,
                                "mtime": mtime,
                            }
                        )
        except OSError as exc:
            messagebox.showerror(
                "Renamer",
                f"Não foi possível ler a pasta: {exc}",
            )
            return

        if not self.raw_files:
            self.btn_apply_rename.configure(
                state="disabled"
            )
            self.filtered_files = []
            self.render_renamer_page()
            return

        self.renamer_state.clear()

        for item in self.raw_files:
            orig = item["name"]
            guess = guess_rename_action(orig)
            new_name = apply_regex_name(
                orig, guess
            )

            is_selected = (
                guess != "Manter Original"
                and new_name != orig
            )

            self.renamer_state[orig] = {
                "selected": is_selected,
                "action": guess,
                "new_name": new_name,
                "mtime": item["mtime"],
            }

        self.btn_apply_rename.configure(
            state="normal"
        )
        self.apply_rename_filters()

    def apply_rename_filters(self, _=None):
        if not self.raw_files:
            return

        self.save_current_page_edits()

        sort_mode = self.sort_var.get()
        filter_mode = self.filter_var.get()

        temp_list = []

        for orig, data in self.renamer_state.items():
            if (
                filter_mode == "Todos"
                or filter_mode == data["action"]
            ):
                temp_list.append(
                    {
                        "name": orig,
                        "data": data,
                    }
                )

        if sort_mode == "Nome (A-Z)":
            temp_list.sort(
                key=lambda x: x["name"].lower()
            )
        elif sort_mode == "Nome (Z-A)":
            temp_list.sort(
                key=lambda x: x["name"].lower(),
                reverse=True,
            )
        elif sort_mode == "Mais Recentes":
            temp_list.sort(
                key=lambda x: x["data"]["mtime"],
                reverse=True,
            )
        elif sort_mode == "Mais Antigos":
            temp_list.sort(
                key=lambda x: x["data"]["mtime"]
            )

        self.filtered_files = [
            item["name"] for item in temp_list
        ]

        self.goto_page_ren(0)

    def goto_page_ren(self, page_index):
        self.save_current_page_edits()
        total_pages = max(
            1,
            math.ceil(
                len(self.filtered_files) / ITEMS_PER_PAGE
            ),
        )
        self.current_page_ren = max(
            0,
            min(page_index, total_pages - 1),
        )
        self.render_renamer_page()

    def save_current_page_edits(self):
        if not hasattr(self, "ui_ren_rows"):
            return

        for item in self.ui_ren_rows:
            orig = item["orig"]
            if orig in self.renamer_state:
                self.renamer_state[orig]["new_name"] = (
                    item["entry"].get().strip()
                )

    def render_renamer_page(self):
        for widget in self.scroll_renamer.winfo_children():
            widget.destroy()
        self.ui_ren_rows.clear()

        total_items = len(self.filtered_files)
        total_pages = math.ceil(
            total_items / ITEMS_PER_PAGE
        )

        self.draw_paginator(
            self.pag_frame_ren,
            self.current_page_ren,
            total_pages,
            self.goto_page_ren,
        )

        start_idx = self.current_page_ren * ITEMS_PER_PAGE
        end_idx = min(
            start_idx + ITEMS_PER_PAGE,
            total_items,
        )
        self.last_checked_index_ren = None

        if total_items == 0:
            ctk.CTkLabel(
                self.scroll_renamer,
                text="Nenhum arquivo compatível.",
                text_color="#888888",
            ).pack(pady=40)
            return

        header_row = ctk.CTkFrame(
            self.scroll_renamer,
            fg_color="transparent",
        )
        header_row.pack(
            fill="x", pady=(5, 5)
        )

        ctk.CTkLabel(
            header_row,
            text="ARQUIVO ORIGINAL",
            text_color="#ff4444",
            font=ctk.CTkFont(weight="bold"),
            width=320,
            anchor="w",
        ).pack(
            side="left",
            padx=(10, 10),
        )

        ctk.CTkLabel(
            header_row,
            text="AÇÃO",
            text_color="#ffbb33",
            font=ctk.CTkFont(weight="bold"),
            width=150,
            anchor="w",
        ).pack(
            side="left", padx=10
        )

        ctk.CTkLabel(
            header_row,
            text="NOVO NOME (Editável)",
            text_color="#00C851",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).pack(
            side="left",
            padx=10,
            fill="x",
            expand=True,
        )

        for visible_index, i in enumerate(
            range(start_idx, end_idx)
        ):
            orig_name = self.filtered_files[i]
            data = self.renamer_state[orig_name]

            row_frame = ctk.CTkFrame(
                self.scroll_renamer,
                fg_color="#181818",
                corner_radius=6,
            )
            row_frame.pack(
                fill="x", pady=3, padx=5
            )

            cb_var = ctk.IntVar(
                value=1 if data["selected"] else 0
            )

            def on_check(
                name=orig_name,
                var=cb_var,
                idx=visible_index,
            ):
                self.renamer_state[name]["selected"] = bool(
                    var.get()
                )
                self._handle_ren_shift_click(idx)

            cb = ctk.CTkCheckBox(
                row_frame,
                text=truncate_text(orig_name, 45),
                variable=cb_var,
                width=320,
                command=on_check,
            )
            cb.pack(
                side="left",
                padx=(10, 10),
                pady=8,
            )

            entry = ctk.CTkEntry(
                row_frame,
                fg_color="#222222",
                border_width=1,
            )

            def on_action_change(
                choice,
                name=orig_name,
                ent=entry,
                var=cb_var,
            ):
                self.renamer_state[name]["action"] = choice
                new_str = apply_regex_name(
                    name, choice
                )

                ent.delete(0, ctk.END)
                ent.insert(0, new_str)

                self.renamer_state[name]["new_name"] = (
                    new_str
                )

                should_select = (
                    new_str != name
                )
                var.set(1 if should_select else 0)
                self.renamer_state[name]["selected"] = (
                    should_select
                )

            combo = ctk.CTkOptionMenu(
                row_frame,
                values=[
                    "Apagar INÍCIO",
                    "Apagar FINAL",
                    "Manter Original",
                ],
                width=150,
                fg_color="#333",
                button_color="#444",
                command=on_action_change,
            )
            combo.set(data["action"])
            combo.pack(side="left", padx=10)

            entry.insert(0, data["new_name"])
            entry.pack(
                side="left",
                fill="x",
                expand=True,
                padx=(10, 10),
            )

            self.ui_ren_rows.append(
                {
                    "cb": cb,
                    "var": cb_var,
                    "orig": orig_name,
                    "entry": entry,
                }
            )

    def _handle_ren_shift_click(self, current_index):
        if (
            self.shift_pressed
            and self.last_checked_index_ren is not None
            and self.ui_ren_rows
        ):
            target_state = self.ui_ren_rows[
                current_index
            ]["var"].get()

            start = min(
                self.last_checked_index_ren,
                current_index,
            )
            end = max(
                self.last_checked_index_ren,
                current_index,
            )

            for i in range(start, end + 1):
                item = self.ui_ren_rows[i]
                item["var"].set(target_state)
                self.renamer_state[
                    item["orig"]
                ]["selected"] = bool(target_state)

        self.last_checked_index_ren = current_index

    def execute_rename(self):
        self.save_current_page_edits()

        changes = 0
        failures = 0

        os.makedirs(self.download_folder, exist_ok=True)

        for orig, data in self.renamer_state.items():
            if not data["selected"]:
                continue

            new_name = clean_filename(
                data["new_name"]
            ).strip()

            if (
                not new_name
                or new_name == orig
            ):
                continue

            old_path = os.path.join(
                self.download_folder,
                orig,
            )

            if not os.path.exists(old_path):
                continue

            new_path = os.path.join(
                self.download_folder,
                new_name,
            )

            try:
                if os.path.abspath(
                    old_path
                ).lower() == os.path.abspath(
                    new_path
                ).lower():
                    continue

                if os.path.exists(new_path):
                    new_path = build_unique_path(
                        self.download_folder,
                        new_name,
                    )

                os.rename(old_path, new_path)
                changes += 1

            except OSError as exc:
                failures += 1
                self.log_msg_safe(
                    f"❌ Erro ao renomear '{orig}': {exc}"
                )

        self.init_renamer_data()

        messagebox.showinfo(
            "Renamer",
            (
                f"{changes} arquivo(s) renomeado(s)."
                + (
                    f"\n{failures} falha(s)."
                    if failures
                    else ""
                )
            ),
        )

    # ========================================================
    # DIAGNÓSTICO
    # ========================================================
    def start_diagnostics(self):
        url = self.diag_url_entry.get().strip()
        if not url:
            self.diag_status.configure(
                text="Cole uma URL primeiro.",
                text_color="#ffbb33",
            )
            return

        for widget in self.scroll_diag.winfo_children():
            widget.destroy()

        self.diag_status.configure(
            text="Consultando playlist...",
            text_color="#aaaaaa",
        )

        threading.Thread(
            target=self._diag_worker,
            args=(url,),
            daemon=True,
        ).start()

    def _diag_worker(self, url):
        try:
            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "ignoreerrors": True,
                "noplaylist": False,
            }
            ydl_opts.update(self._build_cookie_opts())

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    url, download=False
                )

            if not info or "entries" not in info:
                raise ValueError(
                    "A URL não retornou uma playlist válida."
                )

            downloaded = self._read_download_archive()

            missing = []
            valid_entries = 0

            for entry in info.get("entries") or []:
                if not entry:
                    continue

                valid_entries += 1
                if entry.get("id") not in downloaded:
                    item = dict(entry)
                    item["_playlist_pos"] = playlist_position(
                        item,
                        valid_entries - 1,
                    )
                    missing.append(item)

            self.diag_missing_cache = missing

            self.after(
                0,
                lambda n=len(missing), t=valid_entries: (
                    self.diag_status.configure(
                        text=f"{n} faltando / {t} na playlist",
                        text_color=(
                            "#00C851"
                            if n == 0
                            else "#ffbb33"
                        ),
                    ),
                    self.goto_page_diag(0),
                ),
            )

        except Exception as exc:
            self.after(
                0,
                lambda e=str(exc): self.diag_status.configure(
                    text=f"Erro: {e}",
                    text_color="#ff4444",
                ),
            )

    def goto_page_diag(self, page_index):
        total_pages = max(
            1,
            math.ceil(
                len(self.diag_missing_cache)
                / ITEMS_PER_PAGE
            ),
        )
        self.current_page_diag = max(
            0,
            min(page_index, total_pages - 1),
        )
        self.render_diag_page()

    def render_diag_page(self):
        for widget in self.scroll_diag.winfo_children():
            widget.destroy()

        total_items = len(
            self.diag_missing_cache
        )

        if total_items == 0:
            ctk.CTkLabel(
                self.scroll_diag,
                text="Perfeito! Todas as músicas estão registradas localmente.",
                text_color="#00C851",
            ).pack(pady=40)
            self.draw_paginator(
                self.pag_frame_diag,
                0,
                0,
                self.goto_page_diag,
            )
            return

        total_pages = math.ceil(
            total_items / ITEMS_PER_PAGE
        )
        self.draw_paginator(
            self.pag_frame_diag,
            self.current_page_diag,
            total_pages,
            self.goto_page_diag,
        )

        start_idx = (
            self.current_page_diag
            * ITEMS_PER_PAGE
        )
        end_idx = min(
            start_idx + ITEMS_PER_PAGE,
            total_items,
        )

        for i in range(start_idx, end_idx):
            vid = self.diag_missing_cache[i]
            pos = vid.get("_playlist_pos", i + 1)

            row = ctk.CTkFrame(
                self.scroll_diag,
                fg_color="#181818",
                corner_radius=6,
            )
            row.pack(
                fill="x",
                pady=4,
                padx=15,
                ipadx=10,
                ipady=10,
            )

            ctk.CTkLabel(
                row,
                text=truncate_text(
                    f"[{pos}] "
                    f"{vid.get('title', 'Excluído')}",
                    85,
                ),
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w")

            ctk.CTkLabel(
                row,
                text=(
                    f"ID: {vid.get('id', '')}  |  "
                    f"URL: youtu.be/{vid.get('id', '')}"
                ),
                text_color="#aaaaaa",
            ).pack(anchor="w")


if __name__ == "__main__":
    app = MediaLoaderApp()
    app.mainloop()
