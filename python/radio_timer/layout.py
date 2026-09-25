"""Cálculo de tamaños de la interfaz, sin Tkinter.

Los rangos salen del documento del proyecto (radio-timer.md) y están en píxeles a 96 ppp.
El parámetro `scale` los adapta a pantallas con otra densidad (125 %, 150 %...).
"""
from __future__ import annotations

from dataclasses import dataclass

MODE_NORMAL = "normal"          # paneles laterales + reloj
MODE_STACKED = "stacked"        # ventana angosta: reloj arriba y programación debajo
MODE_COMPACT = "compact"        # solo el reloj
MODE_FULLSCREEN = "fullscreen"  # reloj, fecha/hora y barra "EN AIRE"

RIGHT_PANEL_MIN_WIDTH = 1180    # por debajo se oculta el panel derecho
STACK_BELOW_WIDTH = 820         # por debajo todo se apila en una columna
CLOCK_TEXT_MAX_FRACTION = 0.82  # el texto "00:00" no ocupa más de este ancho del anillo

# Documento: "Minutos y segundos ... 64–110 px, hasta 160 px en pantalla completa".
CLOCK_FONT_RANGE = {
    MODE_NORMAL: (64, 110),
    MODE_STACKED: (64, 110),
    MODE_COMPACT: (72, 140),
    MODE_FULLSCREEN: (80, 160),
}
RING_RANGE = {
    MODE_NORMAL: (240, 440),
    MODE_STACKED: (240, 400),
    MODE_COMPACT: (260, 620),
    MODE_FULLSCREEN: (280, 600),
}
CLOCK_LABEL_PX = {MODE_NORMAL: 14, MODE_STACKED: 14, MODE_COMPACT: 16, MODE_FULLSCREEN: 18}
CLOCK_SUB_PX = {MODE_NORMAL: 16, MODE_STACKED: 16, MODE_COMPACT: 20, MODE_FULLSCREEN: 22}
FOOTER_PX = {False: (14, 14), True: (16, 18)}  # (indicador EN AIRE, emisora) según pantalla completa


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def pick_mode(width: int, compact: bool, fullscreen: bool, scale: float = 1.0) -> str:
    if fullscreen:
        return MODE_FULLSCREEN
    if compact:
        return MODE_COMPACT
    if width < STACK_BELOW_WIDTH * scale:
        return MODE_STACKED
    return MODE_NORMAL


def show_right_panel(mode: str, width: int, scale: float = 1.0) -> bool:
    """Documento: 'Pantallas medianas: se oculta el panel derecho'."""
    return mode == MODE_NORMAL and width >= RIGHT_PANEL_MIN_WIDTH * scale


@dataclass(frozen=True)
class DateTimeFonts:
    weekday: int
    date: int
    time: int


def datetime_fonts(width: int, height: int, fullscreen: bool, scale: float = 1.0) -> DateTimeFonts:
    """Documento: día/fecha 20–32 px y hora 40–68 px; crecen con la ventana y en pantalla completa."""
    s = scale
    if fullscreen:
        return DateTimeFonts(
            weekday=round(clamp(min(width * 0.04, height * 0.04), 22 * s, 40 * s)),
            date=round(clamp(min(width * 0.045, height * 0.045), 24 * s, 44 * s)),
            time=round(clamp(min(width * 0.09, height * 0.09), 40 * s, 84 * s)),
        )
    # El alto pesa más que el ancho para dejar espacio al reloj principal, que es lo prioritario.
    return DateTimeFonts(
        weekday=round(clamp(min(width * 0.03, height * 0.024), 20 * s, 28 * s)),
        date=round(clamp(min(width * 0.035, height * 0.028), 22 * s, 32 * s)),
        time=round(clamp(min(width * 0.08, height * 0.058), 40 * s, 68 * s)),
    )


def ring_size(mode: str, avail_w: float, avail_h: float, reserved_h: float, scale: float = 1.0) -> int:
    """Diámetro del anillo: lo que quede libre en vertical, dentro del rango del modo."""
    low, high = RING_RANGE[mode]
    free_h = avail_h - reserved_h
    if mode == MODE_COMPACT:
        target = min(avail_w * 0.6, free_h)
    elif mode == MODE_FULLSCREEN:
        target = min(avail_w * 0.5, free_h)
    else:
        target = min(avail_w * 0.8, free_h)
    return int(round(clamp(target, low * scale, high * scale)))


def stage_width(mode: str, avail_w: float, ring: int, scale: float = 1.0) -> int:
    """Ancho de la columna central (bloque activo, reinicio, fecha y hora)."""
    s = scale
    if mode == MODE_COMPACT:
        return int(ring + 40 * s)
    if mode == MODE_FULLSCREEN:
        return int(clamp(avail_w * 0.6, max(ring + 40 * s, 420 * s), 800 * s))
    if mode == MODE_STACKED:
        return int(clamp(avail_w - 48 * s, 320 * s, 640 * s))
    return int(clamp(avail_w - 40 * s, 420 * s, 640 * s))


def clock_font_px(mode: str, ring: int, scale: float = 1.0) -> int:
    """Tamaño inicial de los dígitos; la app lo reduce si el texto medido no cabe en el anillo."""
    low, high = CLOCK_FONT_RANGE[mode]
    return int(round(clamp(ring * 0.3, low * scale, high * scale)))
