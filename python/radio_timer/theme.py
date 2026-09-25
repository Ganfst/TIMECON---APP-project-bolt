"""Colores y tipografías de la interfaz."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

BG = "#081316"
PANEL = "#0f2327"
PANEL_DARK = "#0b191c"
ROW_ACTIVE = "#183034"
FIELD = "#11272a"
LINE = "#1e3538"
TEXT = "#eefcfb"
TEXT_SOFT = "#d7e4e3"
MUTED = "#789093"
DIM = "#5e797c"
GREEN = "#74ddae"
AMBER = "#e0b070"
RED = "#ff3a3a"
RED_GLOW = "#5a1717"
RED_GLOW_BRIGHT = "#9a2626"
SWITCH_ON = "#237d72"
SWITCH_OFF = "#263b3d"
KNOB_ON = "#b8f1e5"
KNOB_OFF = "#6d8888"
PANIC = "#b62f49"
PANIC_BRIGHT = "#d83d5a"
ACCENT_DEFAULT = "#0e8f88"
BUTTON_BG = "#12292d"
BUTTON_ACTIVE = "#1f4246"
PRIMARY = "#a9e6db"
PRIMARY_ACTIVE = "#c4f0e8"
PRIMARY_TEXT = "#071416"
DANGER = "#d34c62"
DANGER_BG = "#2a1418"

SANS_CANDIDATES = ("Manrope", "Segoe UI", "Helvetica", "Arial")
MONO_CANDIDATES = ("DM Mono", "Cascadia Mono", "Consolas", "Courier New")


def pick_family(root: tk.Misc, candidates: tuple[str, ...]) -> str:
    available = set(tkfont.families(root))
    for name in candidates:
        if name in available:
            return name
    return "TkDefaultFont"


def shade(hex_color: str, factor: float) -> str:
    """Oscurece (factor < 1) o aclara (factor > 1) un color #rrggbb."""
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i:i + 2], 16) for i in (0, 2, 4)]
    adjusted = [max(0, min(255, round(channel * factor))) for channel in channels]
    return "#{:02x}{:02x}{:02x}".format(*adjusted)


def mix(hex_a: str, hex_b: str, amount: float) -> str:
    """Mezcla dos colores; amount = 0 devuelve `hex_a`, amount = 1 devuelve `hex_b`."""
    a = [int(hex_a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(hex_b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    blended = [round(x + (y - x) * amount) for x, y in zip(a, b)]
    return "#{:02x}{:02x}{:02x}".format(*blended)
