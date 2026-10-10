"""Tokens visuais (dark + vermelho) e fábricas de widgets padronizados."""

from functools import lru_cache

import customtkinter as ctk

# ---------------- cores ----------------
BG = "#0f0f0f"
SIDEBAR = "#0b0b0b"
SURFACE = "#181818"
SURFACE_2 = "#212121"
SURFACE_3 = "#2a2a2a"
BORDER = "#2c2c2c"
TEXT = "#f1f1f1"
MUTED = "#9a9a9a"
SUBTLE = "#6b6b6b"
ACCENT = "#e50914"
ACCENT_HOVER = "#b20710"
SUCCESS = "#22c55e"
WARNING = "#f59e0b"
DANGER = "#ef4444"
INFO = "#3b82f6"

# (fundo, texto) dos badges / pílulas
BADGE_COLORS = {
    "success": ("#11301d", "#4ade80"),
    "warning": ("#3a2a0a", "#fbbf24"),
    "danger": ("#3b1212", "#f87171"),
    "info": ("#10233f", "#60a5fa"),
    "neutral": ("#262626", "#a3a3a3"),
    "accent": ("#3b0a0d", "#ff6b72"),
}

RADIUS_CARD = 12
RADIUS_CONTROL = 8
FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"


def apply_global_theme():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")


@lru_cache(maxsize=None)
def font(size=13, weight="normal", family=FONT_FAMILY):
    """CTkFont em cache. Só chame depois que a janela principal existir."""
    return ctk.CTkFont(family=family, size=size, weight=weight)


def display():
    return font(28, "bold")


def title():
    return font(18, "bold")


def body(weight="normal"):
    return font(13, weight)


def caption(weight="normal"):
    return font(11, weight)


def mono(size=12):
    return font(size, "normal", MONO_FAMILY)


# ---------------- fábricas ----------------
def card(parent, **kwargs):
    options = dict(fg_color=SURFACE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER)
    options.update(kwargs)
    return ctk.CTkFrame(parent, **options)


def primary_button(parent, text, command=None, **kwargs):
    options = dict(
        fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#ffffff",
        corner_radius=RADIUS_CONTROL, height=38, font=body("bold"),
    )
    options.update(kwargs)
    return ctk.CTkButton(parent, text=text, command=command, **options)


def secondary_button(parent, text, command=None, **kwargs):
    options = dict(
        fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=TEXT,
        border_width=1, border_color=BORDER, corner_radius=RADIUS_CONTROL,
        height=34, font=body(),
    )
    options.update(kwargs)
    return ctk.CTkButton(parent, text=text, command=command, **options)


def ghost_button(parent, text, command=None, **kwargs):
    options = dict(
        fg_color="transparent", hover_color=SURFACE_2, text_color=MUTED,
        corner_radius=RADIUS_CONTROL, height=30, font=body(),
    )
    options.update(kwargs)
    return ctk.CTkButton(parent, text=text, command=command, **options)


def danger_button(parent, text, command=None, **kwargs):
    options = dict(
        fg_color="#3b1212", hover_color="#5a1717", text_color="#fca5a5",
        border_width=1, border_color="#5a1717", corner_radius=RADIUS_CONTROL,
        height=34, font=body("bold"),
    )
    options.update(kwargs)
    return ctk.CTkButton(parent, text=text, command=command, **options)


def entry(parent, placeholder="", **kwargs):
    options = dict(
        fg_color=SURFACE_2, border_color=BORDER, border_width=1,
        corner_radius=RADIUS_CONTROL, height=36, font=body(),
        placeholder_text=placeholder, placeholder_text_color=SUBTLE, text_color=TEXT,
    )
    options.update(kwargs)
    return ctk.CTkEntry(parent, **options)


def option_menu(parent, values, command=None, **kwargs):
    options = dict(
        fg_color=SURFACE_2, button_color=SURFACE_3, button_hover_color="#363636",
        dropdown_fg_color=SURFACE_2, dropdown_hover_color=SURFACE_3,
        corner_radius=RADIUS_CONTROL, height=34, font=body(), dropdown_font=body(),
        text_color=TEXT,
    )
    options.update(kwargs)
    return ctk.CTkOptionMenu(parent, values=list(values), command=command, **options)


def segmented(parent, values, command=None, **kwargs):
    options = dict(
        fg_color=SURFACE_2, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
        unselected_color=SURFACE_2, unselected_hover_color=SURFACE_3,
        corner_radius=RADIUS_CONTROL, height=32, font=body(), text_color=TEXT,
    )
    options.update(kwargs)
    return ctk.CTkSegmentedButton(parent, values=list(values), command=command, **options)


def checkbox(parent, text="", **kwargs):
    options = dict(
        fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color="#4a4a4a",
        checkmark_color="#ffffff", corner_radius=5, border_width=2,
        checkbox_width=20, checkbox_height=20, font=body(), text_color=TEXT,
    )
    options.update(kwargs)
    return ctk.CTkCheckBox(parent, text=text, **options)


def switch(parent, text, **kwargs):
    options = dict(
        progress_color=ACCENT, button_color="#e5e5e5", button_hover_color="#ffffff",
        fg_color=SURFACE_3, font=body(), text_color=TEXT,
    )
    options.update(kwargs)
    return ctk.CTkSwitch(parent, text=text, **options)


def label(parent, text="", kind="body", color=TEXT, **kwargs):
    fonts = {
        "display": display, "title": title, "body": body, "caption": caption,
        "bold": lambda: body("bold"), "mono": mono,
    }
    options = dict(text=text, font=fonts[kind](), text_color=color, anchor="w", justify="left")
    options.update(kwargs)
    return ctk.CTkLabel(parent, **options)


def scrollable(parent, **kwargs):
    options = dict(
        fg_color=SURFACE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER,
        scrollbar_button_color=SURFACE_3, scrollbar_button_hover_color="#3a3a3a",
    )
    options.update(kwargs)
    return ctk.CTkScrollableFrame(parent, **options)
