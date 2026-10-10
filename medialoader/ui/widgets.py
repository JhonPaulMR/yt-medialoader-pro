"""Componentes reutilizáveis da interface."""

import customtkinter as ctk

from .. import theme as T


class Badge(ctk.CTkLabel):
    def __init__(self, parent, text="", kind="neutral", **kwargs):
        bg, fg = T.BADGE_COLORS[kind]
        super().__init__(
            parent, text=text, fg_color=bg, text_color=fg, corner_radius=6,
            font=T.caption("bold"), height=22, padx=8, **kwargs,
        )
        self._state = (text, kind)

    def set(self, text, kind="neutral"):
        if (text, kind) == self._state:
            return
        bg, fg = T.BADGE_COLORS[kind]
        self.configure(text=text, fg_color=bg, text_color=fg)
        self._state = (text, kind)


class PageHeader(ctk.CTkFrame):
    def __init__(self, parent, title, subtitle=""):
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.title_label = T.label(self, title, "display")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = T.label(self, subtitle, "body", T.MUTED)
        self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.actions = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
        self.actions.grid(row=0, column=1, rowspan=2, sticky="e")

    def set_title(self, text):
        self.title_label.configure(text=text)

    def set_subtitle(self, text, color=T.MUTED):
        self.subtitle_label.configure(text=text, text_color=color)


class StatChip(ctk.CTkFrame):
    def __init__(self, parent, caption, color=T.TEXT, value="0"):
        super().__init__(parent, fg_color=T.SURFACE, corner_radius=T.RADIUS_CARD,
                         border_width=1, border_color=T.BORDER)
        self.value_label = T.label(self, value, "title", color)
        self.value_label.pack(anchor="w", padx=16, pady=(12, 0))
        T.label(self, caption, "caption", T.MUTED).pack(anchor="w", padx=16, pady=(0, 12))

    def set(self, value):
        self.value_label.configure(text=str(value))


class Paginator(ctk.CTkFrame):
    """Paginação compacta: < 1 … 4 5 6 … 20 >"""

    def __init__(self, parent, on_change):
        super().__init__(parent, fg_color="transparent", width=1, height=1)
        self.on_change = on_change
        self._state = None

    def update_pages(self, current, total):
        if self._state == (current, total):
            return
        self._state = (current, total)
        for widget in self.winfo_children():
            widget.destroy()
        if total <= 1:
            return

        def nav(text, page, enabled):
            btn = ctk.CTkButton(
                self, text=text, width=34, height=30, corner_radius=T.RADIUS_CONTROL,
                fg_color=T.SURFACE_2, hover_color=T.SURFACE_3, text_color=T.TEXT,
                text_color_disabled=T.SUBTLE, font=T.body(),
                state="normal" if enabled else "disabled",
                command=lambda: self.on_change(page),
            )
            btn.pack(side="left", padx=2)

        def page_btn(page):
            active = page == current
            ctk.CTkButton(
                self, text=str(page + 1), width=34, height=30, corner_radius=T.RADIUS_CONTROL,
                fg_color=T.ACCENT if active else "transparent",
                hover_color=T.ACCENT_HOVER if active else T.SURFACE_2,
                text_color="#ffffff" if active else T.MUTED, font=T.body("bold" if active else "normal"),
                command=lambda p=page: self.on_change(p),
            ).pack(side="left", padx=2)

        def dots():
            T.label(self, "…", "body", T.SUBTLE, width=20, anchor="center").pack(side="left")

        nav("‹", current - 1, current > 0)
        if total <= 7:
            pages = list(range(total))
        elif current < 4:
            pages = list(range(5)) + [None, total - 1]
        elif current > total - 5:
            pages = [0, None] + list(range(total - 5, total))
        else:
            pages = [0, None, current - 1, current, current + 1, None, total - 1]
        for page in pages:
            dots() if page is None else page_btn(page)
        nav("›", current + 1, current < total - 1)


class RowPool:
    """
    Reaproveita as linhas de uma lista paginada em vez de destruir e
    recriar ~50 widgets CTk a cada troca de página.
    `factory(parent)` devolve um widget com `.bind_item(item, visible_index)`.
    """

    def __init__(self, container, factory, pack_opts=None):
        self.container = container
        self.factory = factory
        self.pack_opts = pack_opts or dict(fill="x", padx=8, pady=3)
        self.rows = []
        self._visible = 0

    def render(self, items):
        while len(self.rows) < len(items):
            self.rows.append(self.factory(self.container))
        for index, item in enumerate(items):
            row = self.rows[index]
            row.bind_item(item, index)
            if index >= self._visible:
                row.pack(**self.pack_opts)
        for row in self.rows[len(items):self._visible]:
            row.pack_forget()
        self._visible = len(items)
        return self.rows[: len(items)]

    def visible_rows(self):
        return self.rows[: self._visible]


def clear_entry(entry):
    """Esvazia um CTkEntry sem apagar o placeholder (get() é "" com placeholder)."""
    if entry.get():
        entry.delete(0, "end")


def scroll_to_top(scrollable_frame):
    canvas = getattr(scrollable_frame, "_parent_canvas", None)
    if canvas is not None:
        canvas.yview_moveto(0)


class EmptyState(ctk.CTkFrame):
    def __init__(self, parent, icon, title, text="", action_text=None, action=None):
        super().__init__(parent, fg_color="transparent")
        T.label(self, icon, "display", T.SUBTLE, anchor="center").pack(pady=(40, 6))
        self.title_label = T.label(self, title, "title", T.TEXT, anchor="center", justify="center")
        self.title_label.pack()
        self.text_label = T.label(self, text, "body", T.MUTED, anchor="center",
                                  justify="center", wraplength=520)
        self.text_label.pack(pady=(4, 12))
        if action_text and action:
            T.primary_button(self, action_text, action, width=180).pack(pady=(0, 40))

    def set_text(self, title=None, text=None):
        if title is not None:
            self.title_label.configure(text=title)
        if text is not None:
            self.text_label.configure(text=text)


class ToastManager:
    """Notificações não bloqueantes no canto inferior direito."""

    _ICONS = {"success": "✔", "warning": "⚠", "danger": "✖", "info": "ℹ", "neutral": "ℹ"}

    def __init__(self, root):
        self.root = root
        self.toasts = []

    def show(self, message, kind="info", duration=3500):
        bg, fg = T.BADGE_COLORS.get(kind, T.BADGE_COLORS["info"])
        toast = ctk.CTkFrame(self.root, fg_color=T.SURFACE_2, corner_radius=10,
                             border_width=1, border_color=fg)
        T.label(toast, self._ICONS.get(kind, "ℹ"), "bold", fg, width=18).pack(side="left", padx=(14, 6), pady=10)
        T.label(toast, message, "body", T.TEXT, wraplength=360).pack(side="left", padx=(0, 16), pady=10)
        toast.bind("<Button-1>", lambda _e: self._dismiss(toast))
        self.toasts.append(toast)
        self._layout()
        self.root.after(duration, lambda: self._dismiss(toast))

    def _dismiss(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
            toast.destroy()
            self._layout()

    def _layout(self):
        offset = 20
        for toast in reversed(self.toasts):
            toast.update_idletasks()
            toast.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-offset)
            toast.lift()
            offset += toast.winfo_reqheight() + 8


class NavItem(ctk.CTkFrame):
    def __init__(self, parent, icon, text, command):
        super().__init__(parent, fg_color="transparent", corner_radius=T.RADIUS_CONTROL)
        self.grid_columnconfigure(1, weight=1)
        self.indicator = ctk.CTkFrame(self, width=3, height=24, fg_color="transparent", corner_radius=2)
        self.indicator.grid(row=0, column=0, padx=(0, 6))
        self.button = ctk.CTkButton(
            self, text=f"{icon}   {text}", anchor="w", height=36,
            fg_color="transparent", hover_color=T.SURFACE_2, text_color=T.MUTED,
            corner_radius=T.RADIUS_CONTROL, font=T.body(), command=command,
        )
        self.button.grid(row=0, column=1, sticky="ew")
        # Linha extra opcional (mini progresso), mostrada com show_extra().
        self.extra = ctk.CTkFrame(self, fg_color="transparent")

    def show_extra(self, visible):
        if visible and not self.extra.winfo_manager():
            self.extra.grid(row=1, column=1, sticky="ew", padx=(12, 4), pady=(0, 4))
        elif not visible and self.extra.winfo_manager():
            self.extra.grid_remove()

    def set_active(self, active):
        self.indicator.configure(fg_color=T.ACCENT if active else "transparent")
        self.button.configure(
            fg_color=T.SURFACE_2 if active else "transparent",
            text_color=T.TEXT if active else T.MUTED,
            font=T.body("bold" if active else "normal"),
        )


class Sidebar(ctk.CTkFrame):
    ITEMS = (
        ("dashboard", "⌂", "Início"),
        ("selection", "☰", "Seleção"),
        ("playlists", "♫", "Playlists"),
        ("progress", "↓", "Progresso"),
        ("phone", "☏", "Celular"),
        ("renamer", "✎", "Renomeador"),
        ("diagnostics", "✓", "Diagnóstico"),
        ("settings", "⚙", "Configurações"),
    )

    def __init__(self, parent, on_select, on_new, on_help=None):
        super().__init__(parent, width=230, corner_radius=0, fg_color=T.SIDEBAR)
        self.grid_propagate(False)
        self.pack_propagate(False)

        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(fill="x", padx=20, pady=(24, 18))
        T.label(brand, "⭳", "title", T.ACCENT).pack(side="left")
        T.label(brand, " MediaLoader", "title", T.TEXT).pack(side="left")
        T.label(brand, " PRO", "caption", T.ACCENT).pack(side="left", pady=(4, 0))

        T.primary_button(self, "＋  Novo download", on_new).pack(fill="x", padx=16, pady=(0, 18))

        self.items = {}
        for key, icon, text in self.ITEMS:
            item = NavItem(self, icon, text, lambda k=key: on_select(k))
            item.pack(fill="x", padx=(10, 12), pady=2)
            self.items[key] = item

        # Mini progresso abaixo do item "Progresso"
        progress_item = self.items["progress"]
        self.mini_bar = ctk.CTkProgressBar(progress_item.extra, height=4, progress_color=T.ACCENT,
                                           fg_color=T.SURFACE_3)
        self.mini_bar.set(0)
        self.mini_label = T.label(progress_item.extra, "", "caption", T.MUTED)
        self.mini_bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.mini_label.pack(side="left")

        # Rodapé: estado do ambiente
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.pack(side="bottom", fill="x", padx=16, pady=16)
        if on_help:
            T.ghost_button(self.footer, "?  Ajuda / manual", on_help, anchor="w", height=28).pack(
                fill="x", pady=(0, 10))
        T.label(self.footer, "AMBIENTE", "caption", T.SUBTLE).pack(anchor="w", pady=(0, 6))
        self.env_badges = {}
        for key in ("ytdlp", "ffmpeg", "deno", "cookies"):
            badge = Badge(self.footer, "…", "neutral")
            badge.pack(anchor="w", pady=2)
            self.env_badges[key] = badge

    def set_active(self, key):
        for name, item in self.items.items():
            item.set_active(name == key)

    def show_progress(self, fraction, text):
        self.items["progress"].show_extra(True)
        self.mini_bar.set(max(0.0, min(1.0, fraction)))
        self.mini_label.configure(text=text)

    def hide_progress(self):
        self.items["progress"].show_extra(False)

    def set_env(self, key, text, kind):
        self.env_badges[key].set(text, kind)
