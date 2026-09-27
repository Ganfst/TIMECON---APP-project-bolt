"""Ventana principal del Radio Timer (Tkinter)."""
from __future__ import annotations

import math
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog
from tkinter import font as tkfont
from typing import Callable

from . import __version__, layout, model, schedule_sync, theme, widgets
from .activity_log import ActivityLog
from .dialogs import HistoryDialog, SettingsDialog
from .storage import Preferences, load_preferences, save_preferences

APP_TITLE = "Radio Timer"
TICK_MS = 100
WAVE_BAR_COUNT = 22
SIDE_PANEL_WIDTH = 320
SIDE_MARGIN = 28
STAGE_PADY = 12
DEFAULT_SIZE = (1440, 900)
MIN_SIZE = (680, 560)
_UNSET = object()

# Tamaños de letra en píxeles a 96 ppp, iguales a la versión web para leer a distancia.
# nombre: (familia, px, peso[, tachado])
FONT_SPECS: dict[str, tuple] = {
    "brand_mark": ("sans", 16, "bold"),
    "brand": ("sans", 18, "bold"),
    "brand_sub": ("sans", 11, "normal"),
    "status": ("mono", 14, "normal"),
    "button": ("sans", 13, "bold"),
    "heading": ("sans", 14, "bold"),
    "caption": ("sans", 12, "bold"),
    "chip_label": ("sans", 12, "normal"),
    "chip_value": ("mono", 16, "normal"),
    "row_index": ("mono", 16, "normal"),
    "row_label": ("sans", 16, "bold"),
    "row_label_done": ("sans", 16, "bold", True),
    "row_meta": ("sans", 13, "normal"),
    "tag": ("sans", 10, "bold"),
    "dot": ("sans", 11, "normal"),
    "arrow": ("sans", 20, "bold"),
    "next_label": ("sans", 18, "bold"),
    "small": ("sans", 13, "normal"),
    "body": ("sans", 15, "normal"),
    "body_bold": ("sans", 15, "bold"),
    "live": ("sans", 15, "bold"),
    "clock": ("mono", 96, "normal"),
    "clock_long": ("mono", 80, "normal"),
    "clock_label": ("sans", 14, "normal"),
    "clock_sub": ("sans", 16, "bold"),
    "program_title": ("sans", 36, "bold"),
    "active_caption": ("sans", 13, "bold"),
    "active_title": ("sans", 24, "bold"),
    "active_detail": ("sans", 15, "normal"),
    "mono_small": ("mono", 14, "normal"),
    "mono_tiny": ("mono", 13, "normal"),
    "reset": ("sans", 16, "bold"),
    "total": ("mono", 24, "normal"),
    "dt_weekday": ("sans", 24, "bold"),
    "dt_date": ("sans", 28, "bold"),
    "dt_time": ("mono", 56, "normal"),
    "card_caption": ("sans", 11, "bold"),
    "card_sub": ("sans", 11, "normal"),
    "card_clock": ("mono", 24, "normal"),
    "sep_title": ("sans", 16, "bold"),
    "sep_detail": ("sans", 12, "normal"),
    "sep_status": ("sans", 12, "bold"),
    "sep_count": ("mono", 36, "normal"),
    "summary_count": ("sans", 28, "bold"),
    "panic": ("mono", 16, "bold"),
    "footer_live": ("mono", 14, "normal"),
    "footer_station": ("sans", 14, "normal"),
    "footer_version": ("mono", 12, "normal"),
    "dialog_caption": ("sans", 13, "bold"),
    "dialog_title": ("sans", 28, "bold"),
    "dialog_label": ("sans", 13, "bold"),
    "field": ("sans", 16, "normal"),
}


class RadioTimerApp:
    """Controlador de la ventana: estado, reloj y dibujo de todos los paneles."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        clock: Callable[[], datetime] = datetime.now,
        prefs_path: Path | str | None = None,
        preferences: Preferences | None = None,
        start_compact: bool = False,
        start_fullscreen: bool = False,
        start_maximized: bool = False,
        autostart: bool = True,
    ) -> None:
        self.root = root
        self.clock = clock
        self.prefs_path = Path(prefs_path) if prefs_path else None
        prefs = preferences or load_preferences(self.prefs_path)
        self.station = model.clean_station(prefs.station)
        self.segments: list[model.Segment] = list(prefs.segments)
        self.programs: list[model.Program] = list(prefs.programs)
        self.programs_synced_at = prefs.programs_synced_at
        self.sync_running = False
        self.sync_message = ""
        self._sync_results: queue.Queue = queue.Queue()
        self._sync_job: str | None = None
        self.alert_enabled = prefs.alert_enabled
        self.sound_enabled = prefs.sound_enabled

        now = clock()
        self.now = now
        self.program_start = model.top_of_hour(now)
        self.start_hour = self.program_start.hour
        self.start_minute = 0
        # La secuencia vuelve a empezar sola en cada hora en punto; esta es la hora que se está cubriendo.
        self._hour_anchor = self.program_start
        self.program: model.Program | None = None
        self.upcoming: tuple[model.Program, datetime] | None = None
        self._program_minute: datetime | None = None

        self.log = ActivityLog(listener=self._on_log_changed)
        self.compact = start_compact
        self.panic = False
        self.fullscreen = False
        self.scale = self._detect_scale(root)
        self.mode = layout.MODE_COMPACT if start_compact else layout.MODE_NORMAL

        # Estado calculado en cada paso del reloj.
        self.schedule: list[model.ScheduledSegment] = []
        self.active: model.ScheduledSegment | None = None
        self.next_segment: model.ScheduledSegment | None = None
        self.status = "empty"
        self.remaining = 0  # lo que falta del bloque activo
        self.reading = model.ClockReading(0, 0.0, False)  # lo que muestra el reloj central
        self.flashing = False
        self.accent = theme.ACCENT_DEFAULT
        self.ring_size = self.px(300)
        self.clock_font_px = self.px(96)

        self.left_panel: tk.Frame | None = None
        self.left_scroll: widgets.ScrollFrame | None = None
        self._previous_active_id: object = _UNSET
        self._previous_program_id: object = _UNSET
        self._settings_dialog: SettingsDialog | None = None
        self._history_dialog: HistoryDialog | None = None
        self._timeline_rows: list[dict] = []
        self._separate_cards: list[dict] = []
        self._wave_bars: list[int] = []
        self._wave_periods: list[float] = []
        self._row_pad: dict[tk.Misc, int] = {}
        self._fit_cache: dict[tuple, str] = {}
        self._size_override: tuple[int, int] | None = None
        self._layout_job: str | None = None
        self._tick_job: str | None = None
        self._panic_phase: int | None = None
        self._flash_phase: bool | None = None
        self._last_slow_second: int | None = None
        self._dirty = True
        self._topbar_mode: str | None = None
        self._clock_sub_max = self.px(200)

        self._build_fonts()
        self._build_ui()
        self._bind_keys()
        self._build_left_panel()
        self._rebuild_separate_cards()
        self.step(now)
        self._apply_layout()
        if start_maximized:
            self._maximize()
        if start_fullscreen:
            self.root.after(200, self.toggle_fullscreen)
        if autostart:
            self._tick_job = self.root.after(TICK_MS, self._tick)

    # ---------------------------------------------------------- utilidades ---

    @staticmethod
    def _detect_scale(root: tk.Misc) -> float:
        """Factor de escala respecto a 96 ppp (1.0 en pantallas al 100 %)."""
        try:
            dpi = float(root.winfo_fpixels("1i"))
        except tk.TclError:
            return 1.0
        return max(1.0, round(dpi / 96.0, 2))

    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def _set_font_px(self, name: str, size_px: int) -> None:
        font = self.f[name]
        if int(font.cget("size")) != -int(size_px):
            font.configure(size=-int(size_px))

    def _fit_text(self, font_name: str, text: str, max_width: int) -> str:
        """Recorta `text` con '…' si no cabe en `max_width` píxeles."""
        font = self.f[font_name]
        key = (font_name, text, int(max_width), font.cget("size"))
        cached = self._fit_cache.get(key)
        if cached is not None:
            return cached
        result = text
        if font.measure(text) > max_width:
            trimmed = text
            while trimmed and font.measure(trimmed + "…") > max_width:
                trimmed = trimmed[:-1]
            result = trimmed.rstrip() + "…"
        if len(self._fit_cache) > 256:
            self._fit_cache.clear()
        self._fit_cache[key] = result
        return result

    # ------------------------------------------------------------- fuentes ---

    def _build_fonts(self) -> None:
        families = {
            "sans": theme.pick_family(self.root, theme.SANS_CANDIDATES),
            "mono": theme.pick_family(self.root, theme.MONO_CANDIDATES),
        }
        self.f: dict[str, tkfont.Font] = {}
        for name, spec in FONT_SPECS.items():
            family, size, weight, *extra = spec
            self.f[name] = tkfont.Font(
                root=self.root, family=families[family], size=-self.px(size), weight=weight,
                overstrike=1 if extra and extra[0] else 0,
            )

    # ------------------------------------------------------------ interfaz ---

    def _build_ui(self) -> None:
        root = self.root
        root.title(APP_TITLE)
        root.configure(bg=theme.BG)
        width = min(self.px(DEFAULT_SIZE[0]), max(self.px(MIN_SIZE[0]), root.winfo_screenwidth() - 40))
        height = min(self.px(DEFAULT_SIZE[1]), max(self.px(MIN_SIZE[1]), root.winfo_screenheight() - 80))
        x = max(0, (root.winfo_screenwidth() - width) // 2)
        y = max(0, (root.winfo_screenheight() - height) // 3)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.minsize(self.px(MIN_SIZE[0]), self.px(MIN_SIZE[1]))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        self.icon = self._build_icon()
        try:
            root.iconphoto(True, self.icon)
        except tk.TclError:
            pass
        widgets.install_wheel_router(root)
        self._build_topbar()
        self._build_panic_banner()
        self._build_content()
        self._build_footer()
        root.bind("<Configure>", self._on_configure)

    @staticmethod
    def _build_icon(size: int = 64) -> tk.PhotoImage:
        """Icono de la ventana dibujado en memoria: un anillo con un punto central."""
        image = tk.PhotoImage(width=size, height=size)
        center = (size - 1) / 2
        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                distance = math.hypot(x - center, y - center) / (size / 2)
                if distance > 0.98:
                    color = theme.BG
                elif distance > 0.72:
                    color = theme.ACCENT_DEFAULT
                elif distance > 0.62:
                    color = theme.PRIMARY
                elif distance > 0.24:
                    color = theme.BG
                else:
                    color = theme.TEXT
                row.append(color)
            rows.append("{" + " ".join(row) + "}")
        image.put(" ".join(rows))
        return image

    def _build_topbar(self) -> None:
        P = self.px
        bar = tk.Frame(self.root, bg=theme.PANEL_DARK, padx=P(SIDE_MARGIN), pady=P(16))
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)
        self.topbar = bar

        brand = tk.Frame(bar, bg=theme.PANEL_DARK)
        brand.grid(row=0, column=0, sticky="w")
        self.brand_frame = brand
        tk.Label(brand, text="((•))", font=self.f["brand_mark"], bg=theme.PRIMARY, fg=theme.PRIMARY_TEXT,
                 width=5, pady=P(9)).pack(side="left", padx=(0, P(14)))
        names = tk.Frame(brand, bg=theme.PANEL_DARK)
        names.pack(side="left")
        self.station_label = widgets.label(names, self.station, font=self.f["brand"], fg=theme.TEXT)
        self.station_label.pack(anchor="w")
        widgets.label(names, "CONTROL MASTER / ON AIR", font=self.f["brand_sub"], fg=theme.DIM).pack(anchor="w")

        self.status_label = widgets.label(bar, "●  SEÑAL ESTABLE    |    MONITOR 01", font=self.f["status"],
                                          fg=theme.MUTED, anchor="center")
        self.status_label.grid(row=0, column=1)

        tools = tk.Frame(bar, bg=theme.PANEL_DARK)
        tools.grid(row=0, column=2, sticky="e")
        self.tools = tools
        options = dict(font=self.f["button"], padx=P(14), pady=P(8))
        self.compact_button = widgets.button(tools, self._compact_label(), self.toggle_compact, **options)
        self.fullscreen_button = widgets.button(tools, "Pantalla completa", self.toggle_fullscreen, **options)
        self.panic_button = widgets.button(tools, "Pánico", self.toggle_panic, **options)
        self.history_button = widgets.button(tools, "Historial", self.open_history, **options)
        self.settings_button = widgets.button(tools, "Configuración", self.open_settings, **options)
        for index, button in enumerate((self.compact_button, self.fullscreen_button, self.panic_button,
                                        self.history_button, self.settings_button)):
            button.pack(side="left", padx=(0 if index == 0 else P(8), 0))

    def _compact_label(self) -> str:
        return "Salir de compacto" if self.compact else "Compacto"

    def _build_panic_banner(self) -> None:
        banner = tk.Frame(self.root, bg=theme.PANIC, pady=self.px(10))
        banner.grid(row=1, column=0, sticky="ew")
        self.panic_banner = banner
        self.panic_label = widgets.label(banner, "✦   MODO PÁNICO ACTIVO   —   El operador requiere atención",
                                         font=self.f["panic"], fg=theme.TEXT, bg=theme.PANIC, anchor="center")
        self.panic_label.pack(fill="x")

    def _build_content(self) -> None:
        content = tk.Frame(self.root, bg=theme.BG)
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)
        content.bind("<Configure>", lambda _event: self._schedule_layout())
        self.content = content
        self._build_center(content)
        self._build_right_panel(content)

    def _heading(self, parent: tk.Frame, text: str, pady: tuple[int, int] = (0, 0)) -> None:
        widgets.label(parent, text, font=self.f["heading"], fg="#98b4b4").pack(fill="x", pady=pady)

    def _chip(self, parent: tk.Frame, caption: str) -> tk.Label:
        row = tk.Frame(parent, bg=theme.PANEL, pady=self.px(14))
        row.pack(fill="x")
        widgets.label(row, caption, font=self.f["chip_label"], fg=theme.DIM).pack(side="left")
        value = widgets.label(row, "", font=self.f["chip_value"], fg=theme.TEXT_SOFT, anchor="e")
        value.pack(side="right")
        widgets.separator(parent)
        return value

    def _grid_stage_row(self, widget: tk.Misc, row: int, top: int, bottom: int = 0, sticky: str = "ew") -> None:
        widget.grid(row=row, column=0, sticky=sticky, pady=(top, bottom))
        self._row_pad[widget] = top + bottom

    def _build_center(self, content: tk.Frame) -> None:
        P = self.px
        self.center_area = widgets.CenteredScrollArea(content, bg=theme.BG)
        self.center_area.grid(row=0, column=1, sticky="nsew")
        stage = self.center_area.body
        stage.configure(pady=P(STAGE_PADY), padx=P(8))
        stage.columnconfigure(0, weight=1, minsize=P(520))
        self.stage = stage

        meta = tk.Frame(stage, bg=theme.BG)
        self._grid_stage_row(meta, 0, 0, P(16))
        self.stage_meta = meta
        widgets.label(meta, "●  EN VIVO", font=self.f["live"], fg="#b9eae0").pack(side="left")
        self.zone_label = widgets.label(meta, "", font=self.f["status"], fg=theme.MUTED, anchor="e")
        self.zone_label.pack(side="right")

        # Programa de la hora según la parrilla semanal.
        program = tk.Frame(stage, bg=theme.BG)
        self._grid_stage_row(program, 1, 0, P(14))
        self.program_block = program
        self.program_caption = widgets.label(program, "PROGRAMA", font=self.f["caption"], fg=theme.MUTED,
                                             anchor="center")
        self.program_caption.pack(fill="x")
        self.program_title = widgets.label(program, "", font=self.f["program_title"], fg=theme.TEXT, anchor="center")
        self.program_title.pack(fill="x", pady=(P(2), 0))

        self.clock_canvas = tk.Canvas(stage, width=self.ring_size, height=self.ring_size, bg=theme.BG,
                                      highlightthickness=0, bd=0)
        self.clock_canvas.grid(row=2, column=0)
        self._create_clock_items()

        block = tk.Frame(stage, bg=theme.ACCENT_DEFAULT, padx=P(26), pady=P(16))
        self._grid_stage_row(block, 3, P(22))
        self.active_block = block
        top = tk.Frame(block, bg=theme.ACCENT_DEFAULT)
        top.pack(fill="x")
        self.active_caption = widgets.label(top, "BLOQUE ACTIVO", font=self.f["active_caption"])
        self.active_caption.pack(side="left")
        self.active_title = widgets.label(top, "", font=self.f["active_title"])
        self.active_title.pack(side="left", padx=(P(14), 0))
        self.active_detail = widgets.label(block, "", font=self.f["active_detail"])
        self.active_detail.pack(fill="x", pady=(P(6), 0))
        self.active_progress = tk.Canvas(block, height=P(5), highlightthickness=0, bd=0, bg=theme.ACCENT_DEFAULT)
        self.active_progress.pack(fill="x", pady=(P(16), 0))
        self._active_progress_bar = self.active_progress.create_rectangle(0, 0, 0, P(5), width=0, fill=theme.TEXT)
        range_row = tk.Frame(block, bg=theme.ACCENT_DEFAULT)
        range_row.pack(fill="x", pady=(P(10), 0))
        self.active_range = widgets.label(range_row, "", font=self.f["mono_small"])
        self.active_range.pack(side="left")
        self.active_remaining = widgets.label(range_row, "", font=self.f["mono_small"], anchor="e")
        self.active_remaining.pack(side="right")
        self._active_frames = [block, top, range_row]
        self._active_labels = [self.active_caption, self.active_title, self.active_detail,
                               self.active_range, self.active_remaining]

        reset = tk.Frame(stage, bg=theme.BG)
        self._grid_stage_row(reset, 4, P(18))
        self.reset_bar = reset
        self.reset_button = widgets.button(reset, "↺   Reiniciar al inicio", self.reset_program,
                                           font=self.f["reset"], padx=P(24), pady=P(12))
        self.reset_button.pack(side="left")
        totals = tk.Frame(reset, bg=theme.BG)
        totals.pack(side="right")
        widgets.label(totals, "RESTA DEL BLOQUE", font=self.f["caption"], fg=theme.MUTED, anchor="e").pack(anchor="e")
        self.block_left_label = widgets.label(totals, "00:00", font=self.f["total"], fg=theme.TEXT_SOFT, anchor="e")
        self.block_left_label.pack(anchor="e")

        dt = tk.Frame(stage, bg=theme.PANEL, padx=P(20), pady=P(12), highlightthickness=1, highlightbackground=theme.LINE)
        self._grid_stage_row(dt, 5, P(20))
        self.datetime_block = dt
        self.dt_weekday = widgets.label(dt, "", font=self.f["dt_weekday"], fg="#9ab8b8", anchor="center")
        self.dt_weekday.pack(fill="x")
        self.dt_date = widgets.label(dt, "", font=self.f["dt_date"], fg="#c5dcd9", anchor="center")
        self.dt_date.pack(fill="x", pady=(P(4), 0))
        self.dt_time = widgets.label(dt, "", font=self.f["dt_time"], fg=theme.TEXT, anchor="center")
        self.dt_time.pack(fill="x", pady=(P(4), 0))

    def _clock_card(self, parent: tk.Frame, caption: str, sub: str) -> tuple[tk.Label, tk.Label]:
        P = self.px
        card = tk.Frame(parent, bg=theme.PANEL_DARK, padx=P(14), pady=P(12),
                        highlightthickness=1, highlightbackground=theme.LINE)
        card.pack(fill="x", pady=(P(10), 0))
        left = tk.Frame(card, bg=theme.PANEL_DARK)
        left.pack(side="left", fill="x", expand=True)
        widgets.label(left, caption, font=self.f["card_caption"], fg=theme.DIM).pack(anchor="w")
        sub_label = widgets.label(left, sub, font=self.f["card_sub"], fg=theme.MUTED)
        sub_label.pack(anchor="w", pady=(P(3), 0))
        value = widgets.label(card, "00:00:00", font=self.f["card_clock"], fg=theme.TEXT, anchor="e")
        value.pack(side="right")
        return value, sub_label

    def _build_right_panel(self, content: tk.Frame) -> None:
        P = self.px
        panel = tk.Frame(content, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.LINE)
        panel.grid(row=0, column=2, padx=(P(14), P(SIDE_MARGIN)), pady=P(SIDE_MARGIN))
        self.right_panel = panel
        self.right_scroll = widgets.ScrollFrame(panel, bg=theme.PANEL, width=P(SIDE_PANEL_WIDTH), fit_height=True)
        self.right_scroll.pack(fill="both", expand=True)
        body = tk.Frame(self.right_scroll.body, bg=theme.PANEL, padx=P(18), pady=P(20))
        body.pack(fill="x")
        self._heading(body, "MONITOR DE AUDIO")

        monitor = tk.Frame(body, bg=theme.PANEL_DARK, padx=P(12), pady=P(12),
                           highlightthickness=1, highlightbackground=theme.LINE)
        monitor.pack(fill="x", pady=(P(14), 0))
        self.wave_canvas = tk.Canvas(monitor, height=P(56), bg=theme.PANEL_DARK, highlightthickness=0, bd=0)
        self.wave_canvas.pack(fill="x")
        meta = tk.Frame(monitor, bg=theme.PANEL_DARK)
        meta.pack(fill="x", pady=(P(10), 0))
        self.audio_status = widgets.label(meta, "●  SIN PROGRAMA", font=self.f["mono_tiny"], fg=theme.DIM)
        self.audio_status.pack(side="left")
        self.audio_block = widgets.label(meta, "STANDBY", font=self.f["mono_tiny"], fg=theme.DIM, anchor="e")
        self.audio_block.pack(side="right")
        for index in range(WAVE_BAR_COUNT):
            self._wave_bars.append(self.wave_canvas.create_rectangle(0, 0, 0, 0, width=0, fill=theme.DIM))
            period = 1.1
            if (index + 1) % 3 == 0:
                period = 1.45
            if (index + 1) % 4 == 1:
                period = 0.85
            if (index + 1) % 5 == 2:
                period = 1.7
            self._wave_periods.append(period)

        self.main_clock_value, self.main_clock_sub = self._clock_card(body, "RELOJ PRINCIPAL", "HORA LOCAL")
        self.utc_clock_value, _ = self._clock_card(body, "RELOJ SECUNDARIO", "UTC · TIEMPO UNIVERSAL")
        self.utc_clock_value.configure(fg="#a9c4c3")

        self._heading(body, "SECCIONES INDEPENDIENTES", pady=(P(24), 0))
        self.separate_container = tk.Frame(body, bg=theme.PANEL)
        self.separate_container.pack(fill="x")

        summary = tk.Frame(body, bg="#10292a", pady=P(14))
        summary.pack(fill="x", pady=(P(18), 0))
        widgets.label(summary, "SECCIONES EN CADENA", font=self.f["caption"], fg=theme.MUTED, anchor="center").pack(fill="x")
        self.summary_count = widgets.label(summary, "0", font=self.f["summary_count"], fg=theme.GREEN, anchor="center")
        self.summary_count.pack(fill="x")
        self.summary_total = widgets.label(summary, "", font=self.f["small"], fg=theme.DIM, anchor="center")
        self.summary_total.pack(fill="x")
        widgets.button(body, "Gestionar secciones   ›", self.open_settings, font=self.f["button"],
                       kind="ghost", pady=P(10)).pack(fill="x", pady=(P(18), 0))

    def _build_footer(self) -> None:
        P = self.px
        footer = tk.Frame(self.root, bg=theme.BG, padx=P(SIDE_MARGIN), pady=P(12))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        self.footer = footer
        self.footer_live = widgets.label(footer, "●  EN AIRE", font=self.f["footer_live"], fg="#79a499")
        self.footer_live.grid(row=0, column=0, sticky="w")
        self.footer_station = widgets.label(footer, self.station, font=self.f["footer_station"], fg="#8badad",
                                            anchor="center")
        self.footer_station.grid(row=0, column=1)
        self.footer_version = widgets.label(footer, f"v{__version__}", font=self.f["footer_version"],
                                            fg="#4c6264", anchor="e")
        self.footer_version.grid(row=0, column=2, sticky="e")

    def _bind_keys(self) -> None:
        self.root.bind("<Escape>", self._on_escape)
        self.root.bind("<F11>", lambda _event: self.toggle_fullscreen())
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    # ---------------------------------------------------- panel izquierdo ---

    def _build_left_panel(self) -> None:
        """Construye la programación: al costado (ventana ancha) o bajo el reloj (ventana angosta)."""
        P = self.px
        if self.left_panel is not None:
            self.left_panel.destroy()
        if self.mode == layout.MODE_STACKED:
            panel = tk.Frame(self.stage, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.LINE)
            panel.grid(row=6, column=0, sticky="ew", pady=(P(26), 0))
            self.left_scroll = None
            host: tk.Misc = panel
        else:
            panel = tk.Frame(self.content, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.LINE)
            panel.grid(row=0, column=0, padx=(P(SIDE_MARGIN), P(14)), pady=P(SIDE_MARGIN))
            self.left_scroll = widgets.ScrollFrame(panel, bg=theme.PANEL, width=P(SIDE_PANEL_WIDTH), fit_height=True)
            self.left_scroll.pack(fill="both", expand=True)
            host = self.left_scroll.body
        self.left_panel = panel

        body = tk.Frame(host, bg=theme.PANEL, padx=P(20), pady=P(20))
        body.pack(fill="x")
        self._heading(body, "PROGRAMACIÓN", pady=(0, P(4)))
        self.start_chip = self._chip(body, "INICIO DE SECUENCIA")
        self.chain_chip = self._chip(body, "CADENA TOTAL")
        self.timeline = tk.Frame(body, bg=theme.PANEL)
        self.timeline.pack(fill="x", pady=(P(12), 0))
        self.next_box = tk.Frame(body, bg=theme.PANEL_DARK, padx=P(16), pady=P(14))
        self.next_box.pack(fill="x", pady=(P(16), 0))
        self.next_caption = widgets.label(self.next_box, "PRÓXIMA SECCIÓN", font=self.f["caption"], fg=theme.MUTED)
        self.next_caption.pack(anchor="w")
        self.next_title = widgets.label(self.next_box, "", font=self.f["next_label"], fg=theme.GREEN, justify="left")
        self.next_title.pack(anchor="w", pady=(P(6), 0))
        self.next_meta = widgets.label(self.next_box, "", font=self.f["small"], fg=theme.DIM)
        self.next_meta.pack(anchor="w", pady=(P(4), 0))
        self.next_program_box = tk.Frame(body, bg=theme.PANEL_DARK, padx=P(16), pady=P(14))
        self.next_program_box.pack(fill="x", pady=(P(12), 0))
        widgets.label(self.next_program_box, "PROGRAMA SIGUIENTE", font=self.f["caption"], fg=theme.MUTED).pack(anchor="w")
        self.next_program_title = widgets.label(self.next_program_box, "", font=self.f["next_label"], fg=theme.TEXT_SOFT,
                                                justify="left", wraplength=self._left_text_width() + P(60))
        self.next_program_title.pack(anchor="w", pady=(P(6), 0))
        self.next_program_meta = widgets.label(self.next_program_box, "", font=self.f["small"], fg=theme.DIM)
        self.next_program_meta.pack(anchor="w", pady=(P(4), 0))
        self._rebuild_timeline()
        self._dirty = True

    def _left_text_width(self) -> int:
        if self.mode == layout.MODE_STACKED:
            columns = self.stage.grid_columnconfigure(0)
            return max(self.px(200), int(columns.get("minsize", self.px(520))) - self.px(150))
        return self.px(SIDE_PANEL_WIDTH - 130)

    def _rebuild_timeline(self) -> None:
        P = self.px
        for child in self.timeline.winfo_children():
            child.destroy()
        self._timeline_rows = []
        if not self.segments:
            widgets.label(self.timeline, "No hay secciones programadas", font=self.f["small"],
                          fg=theme.DIM, anchor="center").pack(fill="x", pady=P(20))
        wrap = self._left_text_width()
        for index, segment in enumerate(self.segments):
            row = tk.Frame(self.timeline, bg=theme.PANEL, padx=P(10), pady=P(10))
            row.pack(fill="x", pady=P(2))
            row.columnconfigure(1, weight=1)
            marker = tk.Frame(row, bg=theme.PANEL)
            marker.grid(row=0, column=0, sticky="n", padx=(0, P(12)))
            widgets.label(marker, "●", font=self.f["dot"], fg=segment.color).pack(side="left")
            index_label = widgets.label(marker, f"{index + 1:02d}", font=self.f["row_index"], fg="#a9c4c3")
            index_label.pack(side="left", padx=(P(4), 0))
            copy = tk.Frame(row, bg=theme.PANEL)
            copy.grid(row=0, column=1, sticky="ew")
            title = widgets.label(copy, segment.label, font=self.f["row_label"], fg=theme.TEXT_SOFT,
                                  wraplength=wrap, justify="left")
            title.pack(anchor="w")
            meta = widgets.label(copy, "", font=self.f["row_meta"], fg=theme.DIM)
            meta.pack(anchor="w", pady=(P(3), 0))
            tag_fg = theme.GREEN if segment.is_chain else theme.AMBER
            tag = tk.Label(copy, text=segment.kind_label, font=self.f["tag"], fg=tag_fg,
                           bg=theme.mix(theme.PANEL, tag_fg, 0.12), padx=P(7), pady=P(2))
            tag.pack(anchor="w", pady=(P(5), 0))
            arrow = widgets.label(row, "›", font=self.f["arrow"], fg=theme.GREEN)
            arrow.grid(row=0, column=2, sticky="e")
            self._timeline_rows.append({
                "frames": [row, marker, copy], "index": index_label, "title": title,
                "meta": meta, "tag": tag, "arrow": arrow, "tag_fg": tag_fg,
            })

    # ----------------------------------------------------- panel derecho ---

    def _rebuild_separate_cards(self) -> None:
        P = self.px
        for child in self.separate_container.winfo_children():
            child.destroy()
        self._separate_cards = []
        separate = [segment for segment in self.segments if not segment.is_chain]
        if not separate:
            widgets.label(self.separate_container, "No hay secciones independientes", font=self.f["small"],
                          fg=theme.DIM, anchor="center").pack(fill="x", pady=P(18))
        for segment in separate:
            card = tk.Frame(self.separate_container, bg=theme.PANEL_DARK, highlightthickness=1,
                            highlightbackground=theme.LINE)
            card.pack(fill="x", pady=(P(14), 0))
            stripe = tk.Frame(card, bg=segment.color, width=P(4))
            stripe.pack(side="left", fill="y")
            body = tk.Frame(card, bg=theme.PANEL_DARK, padx=P(14), pady=P(14))
            body.pack(side="left", fill="both", expand=True)
            head = tk.Frame(body, bg=theme.PANEL_DARK)
            head.pack(fill="x")
            names = tk.Frame(head, bg=theme.PANEL_DARK)
            names.pack(side="left", fill="x", expand=True)
            title = widgets.label(names, segment.label, font=self.f["sep_title"], fg=theme.TEXT_SOFT,
                                  wraplength=P(170), justify="left")
            title.pack(anchor="w")
            detail = widgets.label(names, segment.detail, font=self.f["sep_detail"], fg=theme.DIM)
            detail.pack(anchor="w", pady=(P(3), 0))
            status = tk.Label(head, text="EN ESPERA", font=self.f["sep_status"], fg=theme.MUTED,
                              bg=theme.mix(theme.PANEL_DARK, theme.MUTED, 0.15), padx=P(10), pady=P(4))
            status.pack(side="right", anchor="n")
            countdown = widgets.label(body, "00:00", font=self.f["sep_count"], fg=theme.TEXT)
            countdown.pack(anchor="w", pady=(P(10), P(8)))
            progress = tk.Canvas(body, height=P(5), bg="#020c0e", highlightthickness=0, bd=0)
            progress.pack(fill="x")
            bar = progress.create_rectangle(0, 0, 0, P(5), width=0, fill=segment.color)
            foot = tk.Frame(body, bg=theme.PANEL_DARK)
            foot.pack(fill="x", pady=(P(10), 0))
            range_label = widgets.label(foot, "", font=self.f["mono_tiny"], fg="#a9c4c3")
            range_label.pack(side="left")
            widgets.label(foot, "INDEPENDIENTE", font=self.f["mono_tiny"], fg=theme.MUTED, anchor="e").pack(side="right")
            self._separate_cards.append({
                "segment": segment, "frames": [card, body, head, names, foot], "labels": [title, detail, range_label],
                "card": card, "status": status, "countdown": countdown, "progress": progress, "bar": bar,
                "range": range_label,
            })

    # ------------------------------------------------------- reloj (canvas) ---

    def _create_clock_items(self) -> None:
        canvas = self.clock_canvas
        self._clock_items = {
            "track": canvas.create_oval(0, 0, 0, 0, outline=theme.LINE, width=1),
            "glow": canvas.create_arc(0, 0, 0, 0, start=90, extent=-1, style="arc", outline=theme.RED_GLOW,
                                      width=1, state="hidden"),
            "arc": canvas.create_arc(0, 0, 0, 0, start=90, extent=-1, style="arc", outline=theme.ACCENT_DEFAULT,
                                     width=1, state="hidden"),
            "caption": canvas.create_text(0, 0, text="", font=self.f["clock_label"], fill=theme.MUTED),
            "time": canvas.create_text(0, 0, text="00:00", font=self.f["clock"], fill=theme.TEXT),
            "sub": canvas.create_text(0, 0, text="", font=self.f["clock_sub"], fill=theme.ACCENT_DEFAULT),
        }

    def _place_clock_items(self) -> None:
        """Ubica anillo y textos según el tamaño actual; los textos se separan según su altura real."""
        size = self.ring_size
        canvas = self.clock_canvas
        items = self._clock_items
        canvas.configure(width=size, height=size)
        ring_w = max(6, round(size * 0.022))
        pad = ring_w * 2 + 2
        box = (pad, pad, size - pad, size - pad)
        for key in ("track", "glow", "arc"):
            canvas.coords(items[key], *box)
        canvas.itemconfigure(items["arc"], width=ring_w)
        canvas.itemconfigure(items["glow"], width=ring_w * 3)
        center = size / 2
        time_h = self.f["clock"].metrics("linespace")
        caption_h = self.f["clock_label"].metrics("linespace")
        sub_h = self.f["clock_sub"].metrics("linespace")
        gap = size * 0.02
        canvas.coords(items["time"], center, center)
        canvas.coords(items["caption"], center, center - time_h / 2 - gap - caption_h / 2)
        sub_y = center + time_h / 2 + gap + sub_h / 2
        canvas.coords(items["sub"], center, sub_y)
        inner_r = center - pad - ring_w
        dy = min(inner_r - 1, sub_y + sub_h / 2 - center)
        self._clock_sub_max = int(2 * math.sqrt(max(0.0, inner_r ** 2 - dy ** 2)) * 0.9)

    def _fit_clock_fonts(self, mode: str, ring: int) -> None:
        """Dígitos dentro del rango del documento y sin salirse del anillo."""
        limit = ring * layout.CLOCK_TEXT_MAX_FRACTION
        size = layout.clock_font_px(mode, ring, self.scale)
        self._set_font_px("clock", size)
        while size > self.px(24) and self.f["clock"].measure("00:00") > limit:
            size -= 2
            self._set_font_px("clock", size)
        self.clock_font_px = size
        long_size = size
        self._set_font_px("clock_long", long_size)
        while long_size > self.px(20) and self.f["clock_long"].measure("000:00") > limit:
            long_size -= 2
            self._set_font_px("clock_long", long_size)

    def _fit_program_title(self, stage_w: int) -> None:
        """Título del programa en una línea: se achica hasta el mínimo del modo y, si aún no cabe, se recorta."""
        text = self.program.title if self.program is not None else "Sin programa asignado"
        low, high = layout.PROGRAM_TITLE_PX[self.mode]
        limit = max(self.px(120), stage_w - self.px(16))
        size = self.px(high)
        self._set_font_px("program_title", size)
        while size > self.px(low) and self.f["program_title"].measure(text) > limit:
            size -= 2
            self._set_font_px("program_title", size)
        self.program_title.configure(text=self._fit_text("program_title", text, limit),
                                     fg=theme.TEXT if self.program is not None else theme.DIM)

    # --------------------------------------------------------- disposición ---

    def _maximize(self) -> None:
        try:
            self.root.state("zoomed")
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)
            except tk.TclError:
                pass

    def _window_size(self) -> tuple[int, int]:
        if self._size_override is not None:
            return self._size_override
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        if width < 100 or height < 100:
            return self.px(DEFAULT_SIZE[0]), self.px(DEFAULT_SIZE[1])
        return width, height

    def _on_configure(self, event: tk.Event) -> None:
        if event.widget is self.root:
            self._schedule_layout()

    def _schedule_layout(self) -> None:
        if self._layout_job is not None:
            try:
                self.root.after_cancel(self._layout_job)
            except tk.TclError:
                pass
        self._layout_job = self.root.after(40, self._apply_layout)

    def _layout_topbar(self, width: int) -> None:
        """Oculta el estado de señal o pasa los botones a una segunda fila si no caben."""
        P = self.px
        inner = width - 2 * P(SIDE_MARGIN)
        brand = self.brand_frame.winfo_reqwidth()
        tools = self.tools.winfo_reqwidth()
        status = self.status_label.winfo_reqwidth()
        if brand + status + tools + P(96) <= inner:
            mode = "full"
        elif brand + tools + P(32) <= inner:
            mode = "no-status"
        else:
            mode = "wrapped"
        if mode == self._topbar_mode:
            return
        self._topbar_mode = mode
        if mode == "full":
            self.status_label.grid()
        else:
            self.status_label.grid_remove()
        if mode == "wrapped":
            self.tools.grid(row=1, column=0, columnspan=3, sticky="w", pady=(P(12), 0))
        else:
            self.tools.grid(row=0, column=2, columnspan=1, sticky="e", pady=0)

    def _apply_mode(self, width: int | None = None) -> None:
        """Muestra u oculta cada zona según el modo (normal, angosto, compacto, pantalla completa)."""
        if width is None:
            width = self._window_size()[0]
        mode = layout.pick_mode(width, self.compact, self.fullscreen, self.scale)
        if (mode == layout.MODE_STACKED) != (self.mode == layout.MODE_STACKED) or self.left_panel is None:
            self.mode = mode
            self._build_left_panel()
        self.mode = mode
        minimal = self.compact or self.fullscreen
        visibility = (
            (self.topbar, not self.fullscreen),
            (self.panic_banner, self.panic and not self.fullscreen),
            (self.left_panel, not minimal),
            (self.right_panel, layout.show_right_panel(mode, width, self.scale)),
            (self.stage_meta, not minimal),
            (self.program_block, bool(self.programs)),
            (self.active_block, not minimal and self.active is not None),
            (self.reset_bar, not minimal),
            (self.datetime_block, not self.compact),
            (self.footer, not self.compact),
        )
        for widget, show in visibility:
            if show:
                widget.grid()
            else:
                widget.grid_remove()
        dt_bg = theme.BG if self.fullscreen else theme.PANEL
        self.datetime_block.configure(bg=dt_bg, highlightthickness=0 if self.fullscreen else 1)
        for label in (self.dt_weekday, self.dt_date, self.dt_time):
            label.configure(bg=dt_bg)
        self.footer_version.configure(text="Esc · salir de pantalla completa" if self.fullscreen else f"v{__version__}")
        live_px, station_px = layout.FOOTER_PX[self.fullscreen]
        self._set_font_px("footer_live", self.px(live_px))
        self._set_font_px("footer_station", self.px(station_px))
        self._dirty = True

    def _center_viewport(self, width: int, height: int) -> tuple[int, int]:
        view_w, view_h = self.center_area.viewport_size()
        if self._size_override is None and view_w > 1 and view_h > 1:
            return view_w, view_h
        side = 0
        for panel in (self.left_panel, self.right_panel):
            if panel is not None and panel.winfo_manager() == "grid" and panel.master is self.content:
                side += self.px(SIDE_PANEL_WIDTH + SIDE_MARGIN + 16)
        used_h = sum(widget.winfo_reqheight() for widget in (self.topbar, self.panic_banner, self.footer)
                     if widget.winfo_manager())
        return max(1, width - side), max(1, height - used_h)

    def _stage_reserved_height(self) -> int:
        rows = [self.stage_meta, self.program_block]
        if self.mode != layout.MODE_STACKED:
            rows += [self.active_block, self.reset_bar, self.datetime_block]
        total = 2 * self.px(STAGE_PADY) + self.px(8)
        for widget in rows:
            if widget.winfo_manager():
                total += widget.winfo_reqheight() + self._row_pad.get(widget, 0)
        return total

    def _update_side_heights(self, height: int) -> None:
        content_h = self.content.winfo_height()
        if self._size_override is not None or content_h <= 1:
            used_h = sum(widget.winfo_reqheight() for widget in (self.topbar, self.panic_banner, self.footer)
                         if widget.winfo_manager())
            content_h = height - used_h
        limit = max(self.px(160), content_h - 2 * self.px(SIDE_MARGIN) - 2)
        self.right_scroll.set_max_height(limit)
        if self.left_scroll is not None:
            self.left_scroll.set_max_height(limit)

    def _apply_layout(self, size: tuple[int, int] | None = None) -> None:
        """Recalcula tamaños: reloj, fecha/hora, anillo, paneles y barra superior."""
        self._layout_job = None
        if not self.clock_canvas.winfo_exists():
            return
        if size is not None:
            self._size_override = size
        width, height = self._window_size()
        self.root.update_idletasks()
        self._layout_topbar(width)
        self._apply_mode(width)
        mode = self.mode

        fonts = layout.datetime_fonts(width, height, self.fullscreen, self.scale)
        self._set_font_px("dt_weekday", fonts.weekday)
        self._set_font_px("dt_date", fonts.date)
        self._set_font_px("dt_time", fonts.time)
        self._set_font_px("clock_label", self.px(layout.CLOCK_LABEL_PX[mode]))
        self._set_font_px("clock_sub", self.px(layout.CLOCK_SUB_PX[mode]))
        self.root.update_idletasks()

        view_w, view_h = self._center_viewport(width, height)
        # El alto del título depende de su letra, y la letra del ancho: se ajusta antes y después del anillo.
        self._fit_program_title(layout.stage_width(mode, view_w, self.ring_size, self.scale))
        self.root.update_idletasks()
        ring = layout.ring_size(mode, view_w, view_h, self._stage_reserved_height(), self.scale)
        self.ring_size = ring
        stage_w = layout.stage_width(mode, view_w, ring, self.scale)
        self.stage.columnconfigure(0, minsize=stage_w)
        self._fit_program_title(stage_w)
        self._fit_clock_fonts(mode, ring)
        self._place_clock_items()
        if mode == layout.MODE_STACKED:
            wrap = self._left_text_width()
            for row in self._timeline_rows:
                row["title"].configure(wraplength=wrap)
        self._update_side_heights(height)
        self._dirty = True
        self._render()
        self.center_area.reflow()

    # --------------------------------------------------------------- reloj ---

    def _tick(self) -> None:
        self.step(self.clock())
        self._tick_job = self.root.after(TICK_MS, self._tick)

    def step(self, now: datetime) -> None:
        """Recalcula todo el estado para el instante `now` y redibuja."""
        self.now = now
        hour = model.top_of_hour(now)
        if hour != self._hour_anchor:
            self._restart_for_hour(hour)
        minute = now.replace(second=0, microsecond=0)
        if minute != self._program_minute:
            self._update_program(minute)
        self.schedule = model.build_schedule(self.segments, self.program_start, now)
        self.active = model.find_active(self.schedule)
        self.next_segment = model.next_after(self.schedule, self.active)
        self.status = model.schedule_status(self.schedule)
        self.remaining = self.active.remaining if self.active else 0
        self.reading = model.clock_reading(self.schedule)
        # La alerta avisa cuando el número del reloj central está por llegar a 0.
        flashing = model.is_flashing(self.reading.seconds, self.alert_enabled)
        if flashing != self.flashing:
            self._dirty = True
        self.flashing = flashing
        program_changed = self._track_program_change()
        if self._track_block_change() or program_changed:
            self._dirty = True
            self._apply_mode()
            self._schedule_layout()
        self._render()

    def _restart_for_hour(self, hour: datetime) -> None:
        """En cada hora en punto la secuencia vuelve a empezar, como en el timer original de cabina."""
        self._hour_anchor = hour
        self.program_start = hour
        self.start_hour = hour.hour
        self.start_minute = 0
        if self._previous_active_id is not _UNSET:
            # Aunque el bloque sea el mismo de antes (p. ej. EN AIRE largo), cuenta como una entrada nueva.
            self._previous_active_id = None
        self.log.add("Nueva hora", f"Secuencia reiniciada a las {model.format_time_of_day(hour)}", "Programación",
                     at=self.now)

    def _update_program(self, minute: datetime) -> None:
        """Programa en curso y siguiente; solo pueden cambiar de un minuto a otro o al editar la parrilla."""
        self._program_minute = minute
        self.program = model.program_at(self.programs, self.now)
        self.upcoming = model.next_program(self.programs, self.now)

    def _track_program_change(self) -> bool:
        """Registra en el historial cada cambio de programa. Devuelve si hubo cambio."""
        program_id = self.program.id if self.program else None
        previous = self._previous_program_id
        if previous is not _UNSET and previous == program_id:
            return False
        self._previous_program_id = program_id
        if self.program is not None:
            self.log.add(f"Programa: {self.program.title}", self.program.hours_label, "Parrilla", at=self.now)
        elif previous is not _UNSET:
            self.log.add("Sin programa asignado", "La parrilla no tiene programa para esta hora", "Parrilla",
                         at=self.now)
        self._render_program()
        if self._settings_dialog is not None and self._settings_dialog.winfo_exists():
            self._settings_dialog.refresh_programs()
        return True

    def _render_program(self) -> None:
        program = self.program
        self.root.title(f"{program.title} · {APP_TITLE}" if program is not None else APP_TITLE)
        caption = f"PROGRAMA  ·  {program.hours_label}" if program is not None else "PROGRAMA"
        self.program_caption.configure(text=caption)
        self._fit_program_title(int(self.stage.grid_columnconfigure(0).get("minsize", self.px(520))))
        self._dirty = True  # el panel izquierdo muestra el programa siguiente

    def _track_block_change(self) -> bool:
        """Registra en el historial cada cambio de bloque. Devuelve si hubo cambio."""
        active_id = self.active.id if self.active else None
        previous = self._previous_active_id
        if previous is not _UNSET and previous == active_id:
            return False
        first = previous is _UNSET
        self._previous_active_id = active_id
        reason = "Bloque en curso al abrir el monitor" if first else "Cambio automático por reloj"
        if self.active is not None:
            self.log.add(f"Entrada a bloque: {self.active.label}", reason, "Programación", at=self.now)
        else:
            title = "Programación completada" if self.status == "done" else "En espera del inicio"
            self.log.add(title, "Estado al abrir el monitor" if first else reason, "Programación", at=self.now)
        if not first and self.sound_enabled:
            self.play_cue()
        return True

    # -------------------------------------------------------------- dibujo ---

    def _render(self) -> None:
        """Animaciones en cada paso; textos y paneles solo cuando cambia el segundo o el estado."""
        now = self.now
        flash_phase = self.flashing and int(now.timestamp() * 2) % 2 == 0
        if self.panic:
            accent = theme.PANIC
        elif self.flashing:
            accent = theme.RED
        elif self.active is not None:
            accent = self.active.color
        else:
            accent = theme.ACCENT_DEFAULT
        if accent != self.accent:
            self._dirty = True
        self.accent = accent
        second = int(now.timestamp())
        slow = self._dirty or second != self._last_slow_second

        self._update_clock(accent, flash_phase)
        self._animate_wave(now, accent if self.active is not None else theme.DIM, self.active is not None)
        self._render_panic(now)
        if slow or flash_phase != self._flash_phase:
            self._render_active(accent, flash_phase)
        self._flash_phase = flash_phase
        if slow:
            self._render_left()
            self._render_center(now)
            self._render_right(now)
            self._last_slow_second = second
            self._dirty = False

    def _update_clock(self, accent: str, flash_phase: bool) -> None:
        canvas = self.clock_canvas
        items = self._clock_items
        extent = -min(359.9, max(0.0, self.reading.progress * 3.6))
        if extent <= -0.5:
            canvas.itemconfigure(items["arc"], extent=extent, outline=accent, state="normal")
            if self.flashing:
                glow = theme.RED_GLOW_BRIGHT if flash_phase else theme.RED_GLOW
                canvas.itemconfigure(items["glow"], extent=extent, outline=glow, state="normal")
            else:
                canvas.itemconfigure(items["glow"], state="hidden")
        else:
            canvas.itemconfigure(items["arc"], state="hidden")
            canvas.itemconfigure(items["glow"], state="hidden")
        time_text = model.format_clock(self.reading.seconds)
        if self.active is not None:
            sub = self.active.label
        else:
            sub = "COMPLETADO" if self.status == "done" else "EN ESPERA"
        if self.flashing:
            caption = "ATENCIÓN"
        else:
            caption = "INDEPENDIENTE" if self.reading.separate else "TIEMPO EN CADENA"
        canvas.itemconfigure(items["caption"], text=caption,
                             fill=theme.RED if self.flashing else theme.MUTED)
        canvas.itemconfigure(items["time"], text=time_text,
                             font=self.f["clock"] if len(time_text) <= 5 else self.f["clock_long"],
                             fill=theme.RED if flash_phase else theme.TEXT)
        canvas.itemconfigure(items["sub"], text=self._fit_text("clock_sub", sub, self._clock_sub_max), fill=accent)

    def _render_left(self) -> None:
        self.start_chip.configure(text=f"{model.format_time_of_day(self.program_start)} hrs")
        self.chain_chip.configure(text=f"{model.format_clock(model.chain_remaining(self.schedule))} / "
                                       f"{model.format_duration(model.chain_duration(self.segments))}")
        for row, item in zip(self._timeline_rows, self.schedule):
            row["meta"].configure(text=f"{model.format_time_of_day(item.start)}–{model.format_time_of_day(item.end)}"
                                       f" · {model.format_duration(item.duration)}")
            if item.is_active:
                bg, title_fg, meta_fg, font = theme.ROW_ACTIVE, theme.TEXT, theme.MUTED, self.f["row_label"]
            elif item.is_done:
                bg, title_fg, meta_fg, font = theme.PANEL, theme.DIM, "#3f5659", self.f["row_label_done"]
            else:
                bg, title_fg, meta_fg, font = theme.PANEL, "#6f8a8c", "#4b6467", self.f["row_label"]
            for frame in row["frames"]:
                frame.configure(bg=bg)
            row["index"].configure(bg=bg)
            row["title"].configure(bg=bg, fg=title_fg, font=font)
            row["meta"].configure(bg=bg, fg=meta_fg)
            row["tag"].configure(bg=theme.mix(bg, row["tag_fg"], 0.12))
            row["arrow"].configure(bg=bg, fg=self.accent if item.is_active else bg)

        next_hour = self._hour_anchor + timedelta(hours=1)
        if self.next_segment is not None and self.next_segment.start < next_hour:
            self._show_next_box("PRÓXIMA SECCIÓN", self.next_segment.label, self.accent,
                                f"{model.format_time_of_day(self.next_segment.start)} · "
                                f"{model.format_duration(self.next_segment.duration)}")
        elif self.status == "running" and self.segments:
            # Lo que sigue es la nueva hora: la secuencia vuelve a empezar desde la primera sección.
            first = self.segments[0]
            self._show_next_box("PRÓXIMA SECCIÓN", first.label, first.color,
                                f"{model.format_time_of_day(next_hour)} · nueva hora")
        elif self.status == "done":
            restart = model.format_time_of_day(self._hour_anchor + timedelta(hours=1))
            self._show_next_box("PROGRAMACIÓN COMPLETADA", f"Vuelve a empezar a las {restart}", theme.GREEN, "")
        elif self.status == "pending":
            self._show_next_box("EN ESPERA", f"El programa inicia a las {model.format_time_of_day(self.program_start)}",
                                theme.GREEN, "")
        else:
            self.next_box.pack_forget()
        self._render_next_program()

    def _show_next_box(self, caption: str, title: str, color: str, meta: str) -> None:
        self.next_caption.configure(text=caption)
        self.next_title.configure(text=title, fg=color, font=self.f["next_label"] if meta else self.f["body_bold"],
                                  wraplength=self._left_text_width() + self.px(60))
        self.next_meta.configure(text=meta)
        if meta:
            self.next_meta.pack(anchor="w", pady=(self.px(4), 0))
        else:
            self.next_meta.pack_forget()
        if not self.next_box.winfo_manager():
            self.next_box.pack(fill="x", pady=(self.px(16), 0), before=self.next_program_box)

    def _render_next_program(self) -> None:
        if self.upcoming is None:
            self.next_program_box.pack_forget()
            return
        upcoming, begins = self.upcoming
        self.next_program_title.configure(text=upcoming.title, wraplength=self._left_text_width() + self.px(60))
        self.next_program_meta.configure(text=f"{model.format_relative_day(begins, self.now)} · {upcoming.hours_label}")
        if not self.next_program_box.winfo_manager():
            self.next_program_box.pack(fill="x", pady=(self.px(12), 0))

    def _render_active(self, accent: str, flash_phase: bool) -> None:
        active = self.active
        if active is None:
            return
        fg = theme.TEXT if flash_phase else active.text
        for frame in self._active_frames:
            frame.configure(bg=accent)
        for label in self._active_labels:
            label.configure(bg=accent, fg=fg)
        self.active_title.configure(text=active.label)
        self.active_detail.configure(text=active.detail)
        self.active_range.configure(text=f"{model.format_time_of_day(active.start)} — {model.format_time_of_day(active.end)}")
        self.active_remaining.configure(text=model.format_clock(self.remaining))
        width = max(self.active_progress.winfo_width(), 1)
        self.active_progress.configure(bg=theme.shade(accent, 0.6))
        self.active_progress.coords(self._active_progress_bar, 0, 0, width * active.progress / 100, self.px(5))
        self.active_progress.itemconfigure(self._active_progress_bar, fill=fg)

    def _render_center(self, now: datetime) -> None:
        self.block_left_label.configure(text=model.format_clock(self.remaining))
        self.zone_label.configure(text=model.utc_offset_label(now))
        self.dt_weekday.configure(text=model.format_weekday_es(now))
        self.dt_date.configure(text=model.format_date_es(now))
        self.dt_time.configure(text=model.format_time_with_seconds(now))

    def _render_right(self, now: datetime) -> None:
        live = self.active is not None
        self.audio_status.configure(text="●  PGM · SEÑAL" if live else "●  SIN PROGRAMA",
                                    fg=theme.GREEN if live else theme.DIM)
        self.audio_block.configure(text=self.active.label if live else "STANDBY", fg=theme.MUTED if live else theme.DIM)
        self.main_clock_value.configure(text=model.format_time_with_seconds(now))
        self.main_clock_sub.configure(text=f"{model.utc_offset_label(now)} · HORA LOCAL")
        self.utc_clock_value.configure(text=model.format_utc(now))
        separate = [item for item in self.schedule if not item.is_chain]
        for card, item in zip(self._separate_cards, separate):
            self._style_separate_card(card, item)
        self.summary_count.configure(text=str(sum(1 for segment in self.segments if segment.is_chain)))
        self.summary_total.configure(text=f"Total: {model.format_duration(model.chain_duration(self.segments))}")

    def _animate_wave(self, now: datetime, color: str, live: bool) -> None:
        canvas = self.wave_canvas
        width = canvas.winfo_width()
        if width < 20:
            width = self.px(SIDE_PANEL_WIDTH - 64)
        height = int(float(canvas.cget("height")))
        gap = max(2, self.px(3))
        bar_width = (width - gap * (WAVE_BAR_COUNT - 1)) / WAVE_BAR_COUNT
        moment = now.timestamp()
        for index, (bar, period) in enumerate(zip(self._wave_bars, self._wave_periods)):
            if live:
                phase = 0.5 - 0.5 * math.cos(2 * math.pi * ((moment + index * 0.085) / period))
                fraction = 0.12 + 0.88 * phase
            else:
                fraction = 0.1
            bar_height = fraction * height
            x0 = index * (bar_width + gap)
            canvas.coords(bar, x0, (height - bar_height) / 2, x0 + bar_width, (height + bar_height) / 2)
            canvas.itemconfigure(bar, fill=color)

    def _style_separate_card(self, card: dict, item: model.ScheduledSegment) -> None:
        if item.is_done:
            status, status_fg = "HECHO", theme.DIM
        elif item.is_active:
            status, status_fg = "ACTIVO", theme.GREEN
        else:
            status, status_fg = "EN ESPERA", theme.MUTED
        bg = theme.mix(theme.PANEL_DARK, item.color, 0.12) if item.is_active else theme.PANEL_DARK
        for frame in card["frames"]:
            frame.configure(bg=bg)
        for label in card["labels"]:
            label.configure(bg=bg)
        card["card"].configure(highlightbackground=item.color if item.is_active else theme.LINE)
        card["status"].configure(text=status, fg=status_fg, bg=theme.mix(bg, status_fg, 0.15))
        card["countdown"].configure(text=model.format_clock(item.remaining), bg=bg)
        card["range"].configure(text=f"{model.format_time_of_day(item.start)}–{model.format_time_of_day(item.end)}")
        width = max(card["progress"].winfo_width(), 1)
        card["progress"].coords(card["bar"], 0, 0, width * item.progress / 100, self.px(5))

    def _render_panic(self, now: datetime) -> None:
        if not self.panic:
            if self._panic_phase is not None:
                self._panic_phase = None
                self.panic_button.configure(bg=theme.BUTTON_BG, fg=theme.TEXT_SOFT)
            return
        phase = int(now.timestamp() / 0.65) % 2
        if phase != self._panic_phase:
            self._panic_phase = phase
            color = theme.PANIC if phase == 0 else theme.PANIC_BRIGHT
            self.panic_banner.configure(bg=color)
            self.panic_label.configure(bg=color)
            self.panic_button.configure(bg=theme.PANIC, fg=theme.TEXT)

    # ------------------------------------------------------------- acciones ---

    def toggle_compact(self) -> None:
        self.compact = not self.compact
        self.compact_button.configure(text=self._compact_label())
        self._apply_mode()
        self._schedule_layout()

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        try:
            self.root.attributes("-fullscreen", self.fullscreen)
        except tk.TclError:
            pass
        self._apply_mode()
        self._schedule_layout()

    def toggle_panic(self) -> None:
        self.panic = not self.panic
        self.log.add("Modo pánico activado" if self.panic else "Modo pánico desactivado",
                     "Banner de alerta encendido" if self.panic else "Banner de alerta apagado", "Operador", at=self.now)
        self._apply_mode()
        self._render()
        self._schedule_layout()

    def reset_program(self) -> None:
        self.apply_start_time(self.start_hour, self.start_minute, "Reiniciar al inicio")

    def apply_start_time(self, hour: object, minute: object, source: str = "Configuración") -> datetime:
        self.start_hour = model.clamp_int(hour, 0, 23)
        self.start_minute = model.clamp_int(minute, 0, 59)
        now = self.clock()
        self.program_start = model.start_at(now, self.start_hour, self.start_minute)
        self.log.add("Inicio de programación",
                     f"Secuencia programada desde las {model.format_time_of_day(self.program_start)}", source, at=now)
        self._dirty = True
        self.step(now)
        return self.program_start

    def set_station(self, name: str) -> str:
        self.station = model.clean_station(name)
        self.station_label.configure(text=self.station)
        self.footer_station.configure(text=self.station)
        self.save_preferences()
        return self.station

    def set_alert_enabled(self, enabled: bool) -> None:
        self.alert_enabled = bool(enabled)
        self.save_preferences()
        self._dirty = True
        self.step(self.clock())

    def set_sound_enabled(self, enabled: bool) -> None:
        self.sound_enabled = bool(enabled)
        if self.sound_enabled:
            self.play_cue()
        self.save_preferences()

    def add_segment(self, label: str, minutes: object, kind: str) -> model.Segment:
        segment = model.new_segment(label, model.clamp_int(minutes, 1, model.MAX_SEGMENT_MINUTES), kind, len(self.segments))
        self.segments.append(segment)
        self.log.add(f"Sección agregada: {segment.label}",
                     f"{segment.duration // 60} min · {segment.kind_name}", "Configuración", at=self.now)
        self._segments_changed()
        return segment

    def delete_segment(self, segment_id: str) -> bool:
        target = next((segment for segment in self.segments if segment.id == segment_id), None)
        if target is None:
            return False
        self.segments = [segment for segment in self.segments if segment.id != segment_id]
        self.log.add(f"Sección eliminada: {target.label}", model.format_duration(target.duration), "Configuración", at=self.now)
        self._segments_changed()
        return True

    def set_segment_minutes(self, segment_id: str, minutes: object) -> model.Segment | None:
        """Cambia la duración de una sección sin moverla de su lugar en la secuencia."""
        for index, segment in enumerate(self.segments):
            if segment.id == segment_id:
                updated = model.with_minutes(segment, minutes)
                if updated.duration == segment.duration:
                    return segment
                self.segments[index] = updated
                self.log.add(f"Duración cambiada: {updated.label}", model.format_duration(updated.duration),
                             "Configuración", at=self.now)
                # La lista de configuración no se redibuja: el operador está escribiendo en ella.
                self._segments_changed(refresh_dialog=False)
                return updated
        return None

    def _segments_changed(self, refresh_dialog: bool = True) -> None:
        self._rebuild_timeline()
        self._rebuild_separate_cards()
        self.save_preferences()
        self._dirty = True
        self.step(self.clock())
        self._schedule_layout()
        if refresh_dialog and self._settings_dialog is not None and self._settings_dialog.winfo_exists():
            self._settings_dialog.refresh()

    # ------------------------------------------------------ parrilla semanal ---

    def add_program(self, day: object, start: object, end: object, title: str) -> model.Program:
        program = model.new_program(day, start, end, title)
        clash = model.overlapping_program(self.programs, program)
        if clash is not None:
            raise ValueError(f"Se cruza con «{clash.title}» ({clash.hours_label})")
        self.programs.append(program)
        self.log.add(f"Programa agregado: {program.title}",
                     f"{model.WEEKDAYS_ES[program.day]} {program.hours_label}", "Configuración", at=self.now)
        self._programs_changed()
        return program

    def delete_program(self, program_id: str) -> bool:
        target = next((program for program in self.programs if program.id == program_id), None)
        if target is None:
            return False
        self.programs = [program for program in self.programs if program.id != program_id]
        self.log.add(f"Programa eliminado: {target.title}",
                     f"{model.WEEKDAYS_ES[target.day]} {target.hours_label}", "Configuración", at=self.now)
        self._programs_changed()
        return True

    def copy_program_day(self, source_day: int, target_days: list[int]) -> None:
        self.programs = model.copy_day(self.programs, source_day, target_days)
        names = ", ".join(model.WEEKDAYS_ES[day] for day in target_days if day != source_day)
        self.log.add(f"Parrilla del {model.WEEKDAYS_ES[source_day].lower()} copiada", names, "Configuración",
                     at=self.now)
        self._programs_changed()

    def sync_programs(self, fetch: Callable[[], schedule_sync.SyncResult] = schedule_sync.download_programs) -> bool:
        """Descarga la parrilla de la web en segundo plano; el resultado se aplica en el hilo de Tk."""
        if self.sync_running:
            return False
        self.sync_running = True
        self.sync_message = "Descargando la programación…"
        self._notify_sync()

        def work() -> None:
            try:
                self._sync_results.put(fetch())
            except schedule_sync.SyncError as exc:
                self._sync_results.put(exc)
            except Exception as exc:  # cualquier otro fallo no debe dejar el botón bloqueado
                self._sync_results.put(schedule_sync.SyncError(f"Error inesperado: {exc}"))

        threading.Thread(target=work, daemon=True).start()
        self._sync_job = self.root.after(150, self._poll_sync)
        return True

    def _poll_sync(self) -> None:
        self._sync_job = None
        try:
            outcome = self._sync_results.get_nowait()
        except queue.Empty:
            self._sync_job = self.root.after(150, self._poll_sync)
            return
        self.sync_running = False
        if isinstance(outcome, schedule_sync.SyncError):
            self.sync_message = f"No se pudo sincronizar: {outcome}"
            self.log.add("Sincronización fallida", str(outcome), "Parrilla", at=self.now)
            self._notify_sync()
        else:
            self.apply_synced_programs(outcome)

    def apply_synced_programs(self, result: schedule_sync.SyncResult) -> None:
        """Reemplaza la parrilla por la descargada de la web."""
        now = self.clock()
        self.programs = list(result.programs)
        self.programs_synced_at = now.isoformat(timespec="seconds")
        self.sync_message = f"{len(result.programs)} programas descargados"
        if result.skipped:
            self.sync_message += f" · {len(result.skipped)} omitidos: " + "; ".join(result.skipped[:3])
        self.log.add("Parrilla sincronizada con la web", self.sync_message, "Parrilla", at=now)
        self._programs_changed()
        self._notify_sync()

    def _notify_sync(self) -> None:
        if self._settings_dialog is not None and self._settings_dialog.winfo_exists():
            self._settings_dialog.refresh_sync()

    def _programs_changed(self) -> None:
        self.save_preferences()
        self._program_minute = None
        self._dirty = True
        self.step(self.clock())
        self._render_program()
        self._apply_mode()
        self._schedule_layout()
        if self._settings_dialog is not None and self._settings_dialog.winfo_exists():
            self._settings_dialog.refresh_programs()

    def save_preferences(self) -> None:
        prefs = Preferences(station=self.station, segments=list(self.segments), programs=list(self.programs),
                            programs_synced_at=self.programs_synced_at,
                            alert_enabled=self.alert_enabled, sound_enabled=self.sound_enabled)
        try:
            save_preferences(prefs, self.prefs_path)
        except OSError as exc:
            self.log.add("No se pudieron guardar las preferencias", str(exc), "Sistema", at=self.now)

    def play_cue(self) -> None:
        """Tono breve de dos notas (winsound en Windows, campana del sistema en otros)."""
        if sys.platform == "win32":
            def beep() -> None:
                try:
                    import winsound
                    winsound.Beep(880, 150)
                    winsound.Beep(1320, 150)
                except Exception:
                    pass
            threading.Thread(target=beep, daemon=True).start()
        else:
            try:
                self.root.bell()
            except tk.TclError:
                pass

    def export_history(self, path: Path | str | None = None) -> Path | None:
        if len(self.log) == 0:
            return None
        if path is None:
            chosen = filedialog.asksaveasfilename(
                parent=self.root, title="Exportar historial",
                defaultextension=".csv", initialfile=ActivityLog.suggested_filename(self.now),
                filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")],
            )
            if not chosen:
                return None
            path = chosen
        count = self.log.export_csv(path)
        self.log.add("Historial exportado", f"{count} registros en CSV", "Operador", at=self.now)
        return Path(path)

    # -------------------------------------------------------------- diálogos ---

    def open_settings(self) -> SettingsDialog:
        if self._settings_dialog is not None and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
            self._settings_dialog.focus_set()
            return self._settings_dialog
        self._settings_dialog = SettingsDialog(self)
        return self._settings_dialog

    def open_history(self) -> HistoryDialog:
        if self._history_dialog is not None and self._history_dialog.winfo_exists():
            self._history_dialog.lift()
            self._history_dialog.focus_set()
            return self._history_dialog
        self._history_dialog = HistoryDialog(self)
        return self._history_dialog

    def close_dialogs(self) -> None:
        for dialog in (self._settings_dialog, self._history_dialog):
            if dialog is not None and dialog.winfo_exists():
                dialog.close()

    def _on_log_changed(self) -> None:
        if self._history_dialog is not None and self._history_dialog.winfo_exists():
            self._history_dialog.refresh()

    def _on_escape(self, _event: tk.Event | None = None) -> None:
        self.close_dialogs()
        if self.fullscreen:
            self.toggle_fullscreen()

    def shutdown(self) -> None:
        """Cancela las tareas programadas y cierra los diálogos (sin destruir la ventana)."""
        for attribute in ("_tick_job", "_layout_job", "_sync_job"):
            job = getattr(self, attribute)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)
        self.close_dialogs()

    def quit(self) -> None:
        self.shutdown()
        self.save_preferences()
        self.root.destroy()
