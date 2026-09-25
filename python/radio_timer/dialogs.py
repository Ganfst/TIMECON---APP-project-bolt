"""Ventanas secundarias: configuración e historial."""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Callable

from . import model, theme, widgets

if TYPE_CHECKING:
    from .app import RadioTimerApp

KIND_OPTIONS = {
    "En cadena (se suma)": model.KIND_CHAIN,
    "Independiente (no se suma)": model.KIND_SEPARATE,
}


class _Dialog(tk.Toplevel):
    """Ventana flotante oscura anclada a la derecha de la ventana principal."""

    WIDTH = 540

    def __init__(self, app: "RadioTimerApp", title: str):
        super().__init__(app.root, bg=theme.PANEL_DARK)
        self.app = app
        self.title(title)
        self.transient(app.root)
        self.configure(highlightthickness=1, highlightbackground=theme.LINE)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self._place()

    def _place(self) -> None:
        app = self.app
        root = app.root
        root.update_idletasks()
        width = app.px(self.WIDTH)
        height = min(app.px(860), max(app.px(560), root.winfo_screenheight() - app.px(160)))
        if root.winfo_width() >= 200:
            x = root.winfo_rootx() + max(0, root.winfo_width() - width - app.px(40))
            y = root.winfo_rooty() + app.px(30)
        else:
            x, y = 200, 80
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.minsize(app.px(460), app.px(480))

    def _header(self, parent: tk.Frame, caption: str, title: str) -> None:
        P = self.app.px
        header = tk.Frame(parent, bg=parent.cget("bg"))
        header.pack(fill="x", pady=(0, P(20)))
        copy = tk.Frame(header, bg=parent.cget("bg"))
        copy.pack(side="left", fill="x", expand=True)
        widgets.label(copy, caption, font=self.app.f["dialog_caption"], fg="#7ba7a3").pack(anchor="w")
        widgets.label(copy, title, font=self.app.f["dialog_title"], fg="#e6f4f2").pack(anchor="w", pady=(P(6), 0))
        widgets.button(header, "✕", self.close, font=self.app.f["button"], padx=P(12), pady=P(6)).pack(side="right", anchor="n")

    def close(self) -> None:
        if self.winfo_exists():
            self.destroy()


class SettingsDialog(_Dialog):
    def __init__(self, app: "RadioTimerApp"):
        super().__init__(app, "Configuración")
        fonts = app.f
        P = app.px
        self.scroll = widgets.ScrollFrame(self, bg=theme.PANEL_DARK)
        self.scroll.pack(fill="both", expand=True)
        body = tk.Frame(self.scroll.body, bg=theme.PANEL_DARK, padx=P(28), pady=P(24))
        body.pack(fill="both", expand=True)
        self._header(body, "CONFIGURACIÓN", "Secciones del timer")

        # Emisora
        self._label(body, "NOMBRE DE LA EMISORA")
        self.station_var = tk.StringVar(value=app.station)
        self.station_entry = widgets.entry(body, self.station_var, font=fonts["field"],
                                           max_length=model.MAX_STATION_LENGTH)
        self.station_entry.pack(fill="x", pady=(P(8), 0))
        self.station_var.trace_add("write", lambda *_args: app.set_station(self.station_var.get()))

        # Hora de inicio
        self._label(body, "HORA DE INICIO DEL PROGRAMA", pady=(P(20), 0))
        time_row = tk.Frame(body, bg=theme.PANEL_DARK)
        time_row.pack(fill="x", pady=(P(8), 0))
        self.hour_var = tk.StringVar(value=f"{app.start_hour:02d}")
        self.minute_var = tk.StringVar(value=f"{app.start_minute:02d}")
        self._field(time_row, "Hora", self.hour_var, 0, 23, fmt="%02.0f")
        widgets.label(time_row, ":", font=fonts["dialog_title"], fg=theme.MUTED).pack(side="left", padx=P(8), pady=(P(14), 0))
        self._field(time_row, "Minutos", self.minute_var, 0, 59, fmt="%02.0f")
        widgets.button(time_row, "Aplicar", self._apply_time, font=fonts["button"], kind="primary",
                       padx=P(20), pady=P(10)).pack(side="right", anchor="s")
        widgets.separator(body, pady=(P(22), 0))

        # Nueva sección
        self._label(body, "NUEVA SECCIÓN", pady=(P(20), 0))
        self.name_entry = widgets.PlaceholderEntry(body, "Nombre (ej: ENTREVISTA)", font=fonts["field"],
                                                   max_length=model.MAX_LABEL_LENGTH)
        self.name_entry.pack(fill="x", pady=(P(8), 0))
        self.name_entry.bind("<Return>", lambda _event: self._add_segment())
        new_row = tk.Frame(body, bg=theme.PANEL_DARK)
        new_row.pack(fill="x", pady=(P(12), 0))
        self.minutes_var = tk.StringVar(value="5")
        self._field(new_row, "Minutos", self.minutes_var, 1, model.MAX_SEGMENT_MINUTES, width=6)
        kind_box = tk.Frame(new_row, bg=theme.PANEL_DARK)
        kind_box.pack(side="left", fill="x", expand=True, padx=(P(14), 0))
        widgets.label(kind_box, "Tipo", font=fonts["small"], fg="#83a3a3").pack(anchor="w")
        self.kind_var = tk.StringVar(value=next(iter(KIND_OPTIONS)))
        widgets.option_menu(kind_box, self.kind_var, list(KIND_OPTIONS), font=fonts["body"]).pack(fill="x", pady=(P(4), 0))
        self.error_label = widgets.label(body, "", font=fonts["small"], fg=theme.DANGER)
        self.error_label.pack(fill="x", pady=(P(6), 0))
        widgets.button(body, "+   Agregar sección", self._add_segment, font=fonts["button"], kind="primary",
                       pady=P(12)).pack(fill="x", pady=(P(4), 0))
        widgets.separator(body, pady=(P(22), 0))

        # Lista de secciones
        self._label(body, "SECCIONES ACTUALES", pady=(P(20), P(8)))
        self.list_frame = tk.Frame(body, bg=theme.PANEL_DARK)
        self.list_frame.pack(fill="x")
        widgets.separator(body, pady=(P(12), 0))

        # Interruptores
        self.alert_var = tk.BooleanVar(value=app.alert_enabled)
        self.sound_var = tk.BooleanVar(value=app.sound_enabled)
        self.alert_switch = self._switch_row(
            body, "Alerta de cambio",
            f"Parpadea en rojo los últimos {model.FLASH_WINDOW_SECONDS} segundos de cada bloque",
            self.alert_var, lambda: app.set_alert_enabled(self.alert_var.get()))
        self.sound_switch = self._switch_row(
            body, "Sonido de señal", "Tono breve al cambiar de bloque",
            self.sound_var, lambda: app.set_sound_enabled(self.sound_var.get()))

        widgets.button(body, "Guardar preferencias", self._save, font=fonts["button"], kind="primary",
                       pady=P(14)).pack(fill="x", pady=(P(28), 0))
        self.refresh()

    # ------------------------------------------------------------ helpers ---

    def _label(self, parent: tk.Frame, text: str, pady: tuple[int, int] = (0, 0)) -> None:
        widgets.label(parent, text, font=self.app.f["dialog_label"], fg="#83a3a3").pack(fill="x", pady=pady)

    def _field(self, parent: tk.Frame, caption: str, variable: tk.StringVar, low: int, high: int,
               width: int = 4, fmt: str | None = None) -> None:
        box = tk.Frame(parent, bg=theme.PANEL_DARK)
        box.pack(side="left")
        widgets.label(box, caption, font=self.app.f["small"], fg="#83a3a3").pack(anchor="w")
        widgets.spinbox(box, variable, font=self.app.f["field"], low=low, high=high, width=width,
                        fmt=fmt).pack(pady=(self.app.px(4), 0))

    def _switch_row(self, parent: tk.Frame, title: str, detail: str, variable: tk.BooleanVar,
                    command: Callable[[], None]) -> widgets.Switch:
        P = self.app.px
        row = tk.Frame(parent, bg=theme.PANEL_DARK)
        row.pack(fill="x", pady=(P(18), 0))
        copy = tk.Frame(row, bg=theme.PANEL_DARK)
        copy.pack(side="left", fill="x", expand=True)
        widgets.label(copy, title, font=self.app.f["body_bold"], fg="#dbeae8").pack(anchor="w")
        widgets.label(copy, detail, font=self.app.f["small"], fg=theme.MUTED, wraplength=P(360),
                      justify="left").pack(anchor="w", pady=(P(3), 0))
        switch = widgets.Switch(row, variable, command, scale=self.app.scale)
        switch.pack(side="right", padx=(P(12), 0))
        return switch

    # ------------------------------------------------------------ acciones ---

    def _apply_time(self) -> None:
        start = self.app.apply_start_time(self.hour_var.get(), self.minute_var.get(), "Configuración")
        self.hour_var.set(f"{start.hour:02d}")
        self.minute_var.set(f"{start.minute:02d}")

    def _add_segment(self) -> None:
        try:
            self.app.add_segment(self.name_entry.value(), self.minutes_var.get(), KIND_OPTIONS[self.kind_var.get()])
        except ValueError as exc:
            self.error_label.configure(text=str(exc))
            return
        self.error_label.configure(text="")
        self.name_entry.clear()
        self.minutes_var.set("5")
        self.kind_var.set(next(iter(KIND_OPTIONS)))

    def _save(self) -> None:
        self.app.save_preferences()
        self.close()

    def refresh(self) -> None:
        P = self.app.px
        for child in self.list_frame.winfo_children():
            child.destroy()
        fonts = self.app.f
        if not self.app.segments:
            widgets.label(self.list_frame, "Sin secciones. Agrega una arriba.", font=fonts["small"],
                          fg=theme.DIM, anchor="center").pack(fill="x", pady=P(14))
        for segment in self.app.segments:
            row = tk.Frame(self.list_frame, bg=theme.PANEL_DARK, pady=P(10))
            row.pack(fill="x")
            widgets.label(row, "●", font=fonts["body"], fg=segment.color).pack(side="left", padx=(0, P(12)))
            copy = tk.Frame(row, bg=theme.PANEL_DARK)
            copy.pack(side="left", fill="x", expand=True)
            widgets.label(copy, segment.label, font=fonts["body_bold"], fg=theme.TEXT_SOFT).pack(anchor="w")
            widgets.label(copy, f"{model.format_duration(segment.duration)} · {segment.kind_name}",
                          font=fonts["small"], fg=theme.DIM).pack(anchor="w")
            widgets.button(row, "Eliminar", lambda sid=segment.id: self.app.delete_segment(sid),
                           font=fonts["small"], kind="danger", padx=P(12), pady=P(6)).pack(side="right")
            tk.Frame(self.list_frame, bg="#152a2e", height=1).pack(fill="x")


class HistoryDialog(_Dialog):
    def __init__(self, app: "RadioTimerApp"):
        super().__init__(app, "Historial")
        fonts = app.f
        P = app.px
        body = tk.Frame(self, bg=theme.PANEL_DARK, padx=P(28), pady=P(24))
        body.pack(fill="both", expand=True)
        self._header(body, "REGISTRO DE ACTIVIDAD", "Historial de bloques")

        frame = tk.Frame(body, bg=theme.PANEL_DARK)
        frame.pack(fill="both", expand=True)
        self.text = tk.Text(frame, bg=theme.PANEL_DARK, fg=theme.TEXT_SOFT, relief="flat", bd=0,
                            highlightthickness=0, wrap="word", cursor="arrow", padx=P(4), pady=P(4),
                            font=fonts["body"], spacing3=2)
        scrollbar = widgets.dark_scrollbar(frame, self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("stamp", font=fonts["mono_small"], foreground="#dcebe9", spacing1=P(14))
        self.text.tag_configure("title", font=fonts["body"], foreground="#a1bab9")
        self.text.tag_configure("detail", font=fonts["small"], foreground="#678281", spacing3=P(12))
        self.text.tag_configure("empty", font=fonts["small"], foreground=theme.DIM, justify="center", spacing1=P(30))

        self.status_label = widgets.label(body, "", font=fonts["small"], fg=theme.GREEN, wraplength=P(460), justify="left")
        self.status_label.pack(fill="x", pady=(P(10), 0))
        self.export_button = widgets.button(body, "↓   Exportar historial CSV", self._export, font=fonts["button"], pady=P(12))
        self.export_button.pack(fill="x", pady=(P(8), 0))
        self.refresh()

    def _export(self) -> None:
        path = self.app.export_history()
        if path is not None:
            self.status_label.configure(text=f"Exportado a {path}")

    def refresh(self) -> None:
        if not self.winfo_exists():
            return
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        entries = self.app.log.entries
        if not entries:
            self.text.insert("end", "Sin actividad registrada\n", "empty")
        for entry in entries:
            self.text.insert("end", model.format_log_stamp(entry.at) + "\n", "stamp")
            self.text.insert("end", entry.title + "\n", "title")
            self.text.insert("end", f"{entry.detail} · {entry.source}\n", "detail")
        self.text.configure(state="disabled")
        self.export_button.configure(state="normal" if entries else "disabled")
