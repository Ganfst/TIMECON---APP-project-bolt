"""Ventanas secundarias: configuración e historial."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox
from typing import TYPE_CHECKING, Callable

from . import __version__, model, schedule_sync, theme, updates, widgets

if TYPE_CHECKING:
    from .app import RadioTimerApp

KIND_OPTIONS = {
    "En cadena (se suma)": model.KIND_CHAIN,
    "Independiente (no se suma)": model.KIND_SEPARATE,
}
COPY_TARGETS: list[tuple[str, list[int]]] = [
    ("Lunes a viernes", [0, 1, 2, 3, 4]),
    ("Todos los días", list(range(7))),
] + [(name, [day]) for day, name in enumerate(model.WEEKDAYS_ES)]


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
        self._header(body, "CONFIGURACIÓN", "Programas y secciones")

        # Emisora
        self._label(body, "NOMBRE DE LA EMISORA")
        self.station_var = tk.StringVar(value=app.station)
        self.station_entry = widgets.entry(body, self.station_var, font=fonts["field"],
                                           max_length=model.MAX_STATION_LENGTH)
        self.station_entry.pack(fill="x", pady=(P(8), 0))
        self.station_var.trace_add("write", lambda *_args: app.set_station(self.station_var.get()))
        widgets.separator(body, pady=(P(22), 0))

        # Parrilla semanal
        self._build_programs(body)
        widgets.separator(body, pady=(P(22), 0))

        # Hora de inicio
        self._label(body, "INICIO DE LA SECUENCIA", pady=(P(20), 0))
        widgets.label(body, "Se reinicia sola en cada hora en punto; esto solo corrige la hora actual.",
                      font=fonts["small"], fg=theme.MUTED, wraplength=P(460), justify="left").pack(fill="x", pady=(P(4), 0))
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
        self.overflow_label = widgets.label(body, "", font=fonts["small"], fg=theme.AMBER, wraplength=P(460),
                                            justify="left")
        self.overflow_label.pack(fill="x", pady=(P(8), 0))
        widgets.separator(body, pady=(P(12), 0))

        # Interruptores
        self.alert_var = tk.BooleanVar(value=app.alert_enabled)
        self.sound_var = tk.BooleanVar(value=app.sound_enabled)
        self.alert_switch = self._switch_row(
            body, "Alerta de cambio",
            f"Parpadea en rojo los últimos {model.FLASH_WINDOW_SECONDS} segundos antes de que el reloj central llegue a 0",
            self.alert_var, lambda: app.set_alert_enabled(self.alert_var.get()))
        self.sound_switch = self._switch_row(
            body, "Sonido de señal", "Tono breve al cambiar de bloque",
            self.sound_var, lambda: app.set_sound_enabled(self.sound_var.get()))

        widgets.button(body, "Versiones y actualizaciones   ›", app.open_versions, font=fonts["button"],
                       kind="ghost", pady=P(10)).pack(fill="x", pady=(P(20), 0))
        widgets.button(body, "Guardar preferencias", self._save, font=fonts["button"], kind="primary",
                       pady=P(14)).pack(fill="x", pady=(P(10), 0))
        self._minute_jobs: dict[str, str] = {}
        self.refresh()
        self.refresh_programs()
        self.refresh_sync()

    def _build_programs(self, body: tk.Frame) -> None:
        fonts = self.app.f
        P = self.app.px
        self._label(body, "PROGRAMAS POR HORA", pady=(P(20), 0))
        widgets.label(body, "Cada día tiene su propia parrilla. El título del programa aparece sobre el reloj "
                            "durante sus horas.", font=fonts["small"], fg=theme.MUTED, wraplength=P(460),
                      justify="left").pack(fill="x", pady=(P(4), 0))

        sync_row = tk.Frame(body, bg=theme.PANEL_DARK)
        sync_row.pack(fill="x", pady=(P(12), 0))
        self.sync_button = widgets.button(sync_row, "", self._sync_programs, font=fonts["button"], padx=P(14), pady=P(8))
        self.sync_button.pack(side="left")
        self.sync_status = widgets.label(sync_row, "", font=fonts["small"], fg=theme.MUTED, wraplength=P(250),
                                         justify="left")
        self.sync_status.pack(side="left", fill="x", expand=True, padx=(P(12), 0))

        days = tk.Frame(body, bg=theme.PANEL_DARK)
        days.pack(fill="x", pady=(P(12), 0))
        self.program_day = self.app.now.weekday()
        self.day_buttons: list[tk.Button] = []
        for day, name in enumerate(model.WEEKDAYS_SHORT_ES):
            days.columnconfigure(day, weight=1, uniform="days")
            button = widgets.button(days, name, lambda d=day: self.select_day(d), font=fonts["button"],
                                    padx=P(4), pady=P(8))
            button.grid(row=0, column=day, sticky="ew", padx=(0 if day == 0 else P(4), 0))
            self.day_buttons.append(button)

        self.program_day_title = widgets.label(body, "", font=fonts["body_bold"], fg="#dbeae8")
        self.program_day_title.pack(fill="x", pady=(P(14), P(4)))
        self.program_list = tk.Frame(body, bg=theme.PANEL_DARK)
        self.program_list.pack(fill="x")

        new_row = tk.Frame(body, bg=theme.PANEL_DARK)
        new_row.pack(fill="x", pady=(P(14), 0))
        self.program_start_var = tk.StringVar(value="06")
        self.program_end_var = tk.StringVar(value="07")
        self._field(new_row, "Desde", self.program_start_var, 0, 23, fmt="%02.0f")
        widgets.label(new_row, "–", font=fonts["dialog_title"], fg=theme.MUTED).pack(side="left", padx=P(8), pady=(P(14), 0))
        self._field(new_row, "Hasta", self.program_end_var, 1, 24, fmt="%02.0f")
        widgets.label(new_row, "Horas en punto, 00 a 24", font=fonts["small"], fg=theme.DIM, wraplength=P(170),
                      justify="left").pack(side="left", padx=(P(14), 0), pady=(P(18), 0))
        self.program_title_entry = widgets.PlaceholderEntry(body, "Título (ej: Buenos Días Luz)", font=fonts["field"],
                                                            max_length=model.MAX_PROGRAM_TITLE_LENGTH)
        self.program_title_entry.pack(fill="x", pady=(P(10), 0))
        self.program_title_entry.bind("<Return>", lambda _event: self._add_program())
        self.program_error = widgets.label(body, "", font=fonts["small"], fg=theme.DANGER, wraplength=P(460),
                                           justify="left")
        self.program_error.pack(fill="x", pady=(P(6), 0))
        self.add_program_button = widgets.button(body, "", self._add_program, font=fonts["button"], kind="primary",
                                                 pady=P(12))
        self.add_program_button.pack(fill="x", pady=(P(4), 0))

        copy_row = tk.Frame(body, bg=theme.PANEL_DARK)
        copy_row.pack(fill="x", pady=(P(14), 0))
        widgets.label(copy_row, "Copiar este día a", font=fonts["small"], fg="#83a3a3").pack(side="left")
        self.copy_target_var = tk.StringVar(value=COPY_TARGETS[0][0])
        widgets.option_menu(copy_row, self.copy_target_var, [name for name, _ in COPY_TARGETS],
                            font=fonts["small"]).pack(side="left", fill="x", expand=True, padx=(P(10), P(10)))
        widgets.button(copy_row, "Copiar", self._copy_day, font=fonts["small"], padx=P(14), pady=P(6)).pack(side="right")
        widgets.label(body, "Un programa que pasa la medianoche se carga en dos partes: por ejemplo 22–24 el lunes "
                            "y 00–02 el martes.", font=fonts["small"], fg=theme.DIM, wraplength=P(460),
                      justify="left").pack(fill="x", pady=(P(10), 0))

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

    def select_day(self, day: int) -> None:
        self.program_day = day
        self.program_error.configure(text="")
        self.refresh_programs()

    def _add_program(self) -> None:
        try:
            program = self.app.add_program(self.program_day, self.program_start_var.get(),
                                           self.program_end_var.get(), self.program_title_entry.value())
        except ValueError as exc:
            self.program_error.configure(text=str(exc))
            return
        self.program_error.configure(text="")
        self.program_title_entry.clear()
        # Lo más común es cargar el programa siguiente a continuación.
        end_hour = program.end // 60
        self.program_start_var.set(f"{min(end_hour, 23):02d}")
        self.program_end_var.set(f"{min(end_hour + 1, 24):02d}")

    def _sync_programs(self) -> None:
        if self.app.programs and not messagebox.askyesno(
                "Sincronizar programación",
                f"La parrilla actual ({len(self.app.programs)} programas) se reemplazará por la publicada en "
                f"{schedule_sync.SCHEDULE_URL}.\n¿Continuar?", parent=self):
            return
        self.app.sync_programs()

    def refresh_sync(self) -> None:
        if not self.winfo_exists():
            return
        running = self.app.sync_running
        self.sync_button.configure(text="Sincronizando…" if running else "⟳   Sincronizar desde la web",
                                   state="disabled" if running else "normal")
        message = self.app.sync_message
        if not message:
            synced = self.app.programs_synced_at
            if synced:
                try:
                    stamp = model.format_log_stamp(datetime.fromisoformat(synced))
                except ValueError:
                    stamp = synced
                message = f"Última sincronización: {stamp}"
            else:
                message = "radioluz937fm.com/weekSchedule"
        failed = message.startswith("No se pudo")
        self.sync_status.configure(text=message, fg=theme.DANGER if failed else theme.MUTED)

    def _copy_day(self) -> None:
        targets = dict(COPY_TARGETS)[self.copy_target_var.get()]
        targets = [day for day in targets if day != self.program_day]
        if not targets:
            return
        replaced = [day for day in targets if model.programs_for_day(self.app.programs, day)]
        if replaced:
            names = ", ".join(model.WEEKDAYS_ES[day] for day in replaced)
            if not messagebox.askyesno("Copiar parrilla",
                                       f"Se reemplazarán los programas de: {names}.\n¿Continuar?", parent=self):
                return
        self.app.copy_program_day(self.program_day, targets)

    def refresh_programs(self) -> None:
        P = self.app.px
        fonts = self.app.f
        today = self.app.now.weekday()
        for day, button in enumerate(self.day_buttons):
            selected = day == self.program_day
            has_programs = bool(model.programs_for_day(self.app.programs, day))
            button.configure(bg=theme.PRIMARY if selected else theme.BUTTON_BG,
                             fg=theme.PRIMARY_TEXT if selected else (theme.TEXT_SOFT if has_programs else theme.DIM),
                             activebackground=theme.PRIMARY_ACTIVE if selected else theme.BUTTON_ACTIVE)
        name = model.WEEKDAYS_ES[self.program_day]
        self.program_day_title.configure(text=f"{name}{' (hoy)' if self.program_day == today else ''}")
        self.add_program_button.configure(text=f"+   Agregar programa al {name.lower()}")
        for child in self.program_list.winfo_children():
            child.destroy()
        programs = model.programs_for_day(self.app.programs, self.program_day)
        if not programs:
            widgets.label(self.program_list, "Sin programas este día.", font=fonts["small"], fg=theme.DIM,
                          anchor="center").pack(fill="x", pady=P(10))
        current_id = self.app.program.id if self.app.program else None
        for program in programs:
            on_air = program.id == current_id
            bg = theme.ROW_ACTIVE if on_air else theme.PANEL_DARK
            row = tk.Frame(self.program_list, bg=bg, padx=P(8), pady=P(8))
            row.pack(fill="x")
            widgets.label(row, program.hours_label, font=fonts["mono_small"],
                          fg=theme.GREEN if on_air else "#a9c4c3").pack(side="left", padx=(0, P(12)))
            widgets.label(row, program.title, font=fonts["body_bold"], fg=theme.TEXT_SOFT,
                          wraplength=P(250), justify="left").pack(side="left", fill="x", expand=True)
            widgets.button(row, "Eliminar", lambda pid=program.id: self.app.delete_program(pid),
                           font=fonts["small"], kind="danger", padx=P(12), pady=P(6)).pack(side="right")
            tk.Frame(self.program_list, bg="#152a2e", height=1).pack(fill="x")

    def _queue_minutes(self, segment_id: str, variable: tk.StringVar, delay: int = 500) -> None:
        """Aplica los minutos tras una pausa, para no recalcular con cada flecha o tecla."""
        job = self._minute_jobs.pop(segment_id, None)
        if job is not None:
            self.after_cancel(job)
        self._minute_jobs[segment_id] = self.after(delay, lambda: self._apply_minutes(segment_id, variable))

    def _apply_minutes(self, segment_id: str, variable: tk.StringVar) -> None:
        self._minute_jobs.pop(segment_id, None)
        segment = self.app.set_segment_minutes(segment_id, variable.get())
        if not self.winfo_exists():
            return
        if segment is not None:
            variable.set(str(segment.duration // 60))
        self._refresh_overflow()

    def close(self) -> None:
        # Minutos escritos que aún esperaban su pausa: se aplican antes de cerrar.
        for segment_id, job in list(self._minute_jobs.items()):
            self.after_cancel(job)
            variable = self.minute_vars.get(segment_id)
            if variable is not None:
                self._minute_jobs.pop(segment_id, None)
                self.app.set_segment_minutes(segment_id, variable.get())
        super().close()

    def _refresh_overflow(self) -> None:
        cut = model.cut_by_hour(self.app.segments)
        if cut:
            total = model.sequence_duration(self.app.segments) // 60
            names = ", ".join(segment.label for segment in cut)
            self.overflow_label.configure(
                text=f"La secuencia dura {total} min y se reinicia en cada hora en punto: {names} "
                     f"{'no alcanzan a salir completas' if len(cut) > 1 else 'no alcanza a salir completa'}. "
                     f"Ajusta los minutos para que sumen 60.")
        else:
            self.overflow_label.configure(text="")

    def refresh(self) -> None:
        P = self.app.px
        for child in self.list_frame.winfo_children():
            child.destroy()
        fonts = self.app.f
        if not self.app.segments:
            widgets.label(self.list_frame, "Sin secciones. Agrega una arriba.", font=fonts["small"],
                          fg=theme.DIM, anchor="center").pack(fill="x", pady=P(14))
        self.minute_vars: dict[str, tk.StringVar] = {}
        for segment in self.app.segments:
            row = tk.Frame(self.list_frame, bg=theme.PANEL_DARK, pady=P(10))
            row.pack(fill="x")
            widgets.label(row, "●", font=fonts["body"], fg=segment.color).pack(side="left", padx=(0, P(12)))
            copy = tk.Frame(row, bg=theme.PANEL_DARK)
            copy.pack(side="left", fill="x", expand=True)
            widgets.label(copy, segment.label, font=fonts["body_bold"], fg=theme.TEXT_SOFT).pack(anchor="w")
            widgets.label(copy, segment.kind_name, font=fonts["small"], fg=theme.DIM).pack(anchor="w")
            widgets.button(row, "Eliminar", lambda sid=segment.id: self.app.delete_segment(sid),
                           font=fonts["small"], kind="danger", padx=P(12), pady=P(6)).pack(side="right")
            widgets.label(row, "min", font=fonts["small"], fg=theme.DIM).pack(side="right", padx=(P(6), P(14)))
            minutes = tk.StringVar(value=str(segment.duration // 60))
            spin = widgets.spinbox(row, minutes, font=fonts["body"], low=1, high=model.MAX_SEGMENT_MINUTES, width=4)
            spin.configure(wrap=False, command=lambda sid=segment.id, var=minutes: self._queue_minutes(sid, var))
            spin.bind("<Return>", lambda _event, sid=segment.id, var=minutes: self._queue_minutes(sid, var, 0))
            spin.bind("<FocusOut>", lambda _event, sid=segment.id, var=minutes: self._queue_minutes(sid, var, 0))
            spin.pack(side="right")
            self.minute_vars[segment.id] = minutes
            tk.Frame(self.list_frame, bg="#152a2e", height=1).pack(fill="x")
        self._refresh_overflow()


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
UPDATE_MODE_OPTIONS = {label: mode for mode, label in updates.CHECK_MODE_NAMES.items()}
CHANNEL_OPTIONS = {"Estable — versiones publicadas": "stable",
                   "Desarrollo — también cada cambio del código": "dev"}
NOTE_COLORS = {"Nuevo": theme.GREEN, "Arreglado": theme.AMBER, "Cambiado": theme.MUTED, "Seguridad": theme.DANGER}


class VersionsDialog(_Dialog):
    """Gestor de versiones: comprobar actualizaciones e instalar la versión que se elija."""

    def __init__(self, app: "RadioTimerApp"):
        super().__init__(app, "Versiones")
        fonts = app.f
        P = app.px
        self.scroll = widgets.ScrollFrame(self, bg=theme.PANEL_DARK)
        self.scroll.pack(fill="both", expand=True)
        body = tk.Frame(self.scroll.body, bg=theme.PANEL_DARK, padx=P(28), pady=P(24))
        body.pack(fill="both", expand=True)
        self._header(body, "GESTOR DE VERSIONES", "Actualizaciones")

        current = tk.Frame(body, bg=theme.PANEL_DARK)
        current.pack(fill="x")
        widgets.label(current, "Versión instalada", font=fonts["body"], fg="#83a3a3").pack(side="left")
        widgets.label(current, f"v{__version__}", font=fonts["body_bold"], fg=theme.TEXT, anchor="e").pack(side="right")
        widgets.separator(body, pady=(P(14), 0))

        # Cadencia de comprobación
        self._caption(body, "COMPROBACIÓN AUTOMÁTICA", (P(18), 0))
        mode_row = tk.Frame(body, bg=theme.PANEL_DARK)
        mode_row.pack(fill="x", pady=(P(8), 0))
        self.mode_var = tk.StringVar(value=updates.CHECK_MODE_NAMES.get(app.update_mode, "Manual"))
        widgets.option_menu(mode_row, self.mode_var, list(UPDATE_MODE_OPTIONS), font=fonts["body"]).pack(
            side="left", fill="x", expand=True)
        self.mode_var.trace_add("write", lambda *_args: app.set_update_mode(UPDATE_MODE_OPTIONS[self.mode_var.get()]))
        widgets.label(body, "Con cadencia diaria o semanal, la app comprueba sola mientras está abierta "
                            "y avisa en la esquina inferior derecha; nunca instala sin que se lo pidas.",
                      font=fonts["small"], fg=theme.MUTED, wraplength=P(440), justify="left").pack(fill="x", pady=(P(6), 0))

        # Canal
        self._caption(body, "CANAL", (P(16), 0))
        channel_label = next(label for label, key in CHANNEL_OPTIONS.items() if key == app.update_channel)
        self.channel_var = tk.StringVar(value=channel_label)
        widgets.option_menu(body, self.channel_var, list(CHANNEL_OPTIONS), font=fonts["body"]).pack(
            fill="x", pady=(P(8), 0))
        self.channel_var.trace_add("write",
                                   lambda *_args: app.set_update_channel(CHANNEL_OPTIONS[self.channel_var.get()]))
        widgets.label(body, "La PC de cabina va en Estable. Desarrollo sirve para probar cada cambio "
                            "antes de publicarlo como versión.",
                      font=fonts["small"], fg=theme.MUTED, wraplength=P(440), justify="left").pack(fill="x", pady=(P(6), 0))

        # Fuente
        self._caption(body, "FUENTE DE ACTUALIZACIONES", (P(16), 0))
        self.url_var = tk.StringVar(value=app.update_url)
        widgets.entry(body, self.url_var, font=fonts["field"]).pack(fill="x", pady=(P(8), 0))
        self.url_var.trace_add("write", lambda *_args: app.set_update_url(self.url_var.get()))
        widgets.label(body, "Enlace del repositorio de GitHub (versiones = GitHub Releases), o una URL "
                            "https o carpeta (red o USB) con updates.json y el ZIP de cada versión. "
                            "Vacío = repositorio oficial.",
                      font=fonts["small"], fg=theme.DIM, wraplength=P(440), justify="left").pack(fill="x", pady=(P(4), 0))

        buttons = tk.Frame(body, bg=theme.PANEL_DARK)
        buttons.pack(fill="x", pady=(P(12), 0))
        self.check_button = widgets.button(buttons, "⟳   Comprobar ahora", self._check, font=fonts["button"],
                                           kind="primary", padx=P(16), pady=P(10))
        self.check_button.pack(side="left")
        self.restart_button = widgets.button(buttons, "Reiniciar la aplicación", app.restart_app,
                                             font=fonts["button"], padx=P(16), pady=P(10))
        self.status_label = widgets.label(body, "", font=fonts["small"], fg=theme.MUTED,
                                          wraplength=P(440), justify="left")
        self.status_label.pack(fill="x", pady=(P(8), 0))

        self._caption(body, "VERSIONES PUBLICADAS", (P(18), P(4)))
        self.releases_frame = tk.Frame(body, bg=theme.PANEL_DARK)
        self.releases_frame.pack(fill="x")
        self.refresh()

    # ------------------------------------------------------------ helpers ---

    def _caption(self, parent: tk.Frame, text: str, pady: tuple[int, int]) -> None:
        widgets.label(parent, text, font=self.app.f["dialog_label"], fg="#83a3a3").pack(fill="x", pady=pady)

    def _check(self) -> None:
        self.app.check_updates(manual=True)

    def _install(self, release: updates.Release) -> None:
        compared = updates.compare_versions(release.version, __version__)
        if compared < 0 and not messagebox.askyesno(
                "Instalar una versión anterior",
                f"v{release.version} es anterior a la instalada (v{__version__}).\n¿Volver a esa versión?",
                parent=self):
            return
        if compared == 0 and not messagebox.askyesno(
                "Reinstalar", f"v{release.version} ya es la versión instalada.\n¿Reinstalarla?", parent=self):
            return
        if not self.app.install_version(release):
            self.status_label.configure(text="Hay otra operación en curso; espera a que termine.", fg=theme.AMBER)

    # ------------------------------------------------------------- refresh ---

    def refresh(self) -> None:
        if not self.winfo_exists():
            return
        app = self.app
        fonts = app.f
        P = app.px
        self.check_button.configure(state="disabled" if app.update_busy else "normal")
        self.restart_button.configure(state="disabled" if app.update_busy else "normal")
        if app.update_installed_version:
            if not self.restart_button.winfo_manager():
                self.restart_button.pack(side="left", padx=(P(10), 0))
        else:
            self.restart_button.pack_forget()

        status = app.update_status
        if not status:
            status = ("Pulsa «Comprobar ahora» para ver las versiones publicadas."
                      if app.update_url else "Configura la fuente y pulsa «Comprobar ahora».")
        failed = status.startswith("No se pudo")
        self.status_label.configure(text=status, fg=theme.DANGER if failed else theme.MUTED)

        for child in self.releases_frame.winfo_children():
            child.destroy()
        if not app.available_releases:
            widgets.label(self.releases_frame, "Ninguna versión cargada todavía.", font=fonts["small"],
                          fg=theme.DIM, anchor="center").pack(fill="x", pady=P(12))
        for release in app.available_releases:
            self._release_row(release)

    def _release_row(self, release: updates.Release) -> None:
        app = self.app
        fonts = app.f
        P = app.px
        newer = release.is_newer_than(__version__)
        current = updates.compare_versions(release.version, __version__) == 0
        row = tk.Frame(self.releases_frame, bg=theme.PANEL_DARK, pady=P(10))
        row.pack(fill="x")
        head = tk.Frame(row, bg=theme.PANEL_DARK)
        head.pack(fill="x")
        title = f"v{release.version}" + (f" · {release.title}" if release.title else "")
        widgets.label(head, title, font=fonts["body_bold"], fg=theme.TEXT if newer else theme.TEXT_SOFT,
                      wraplength=P(300), justify="left").pack(side="left", fill="x", expand=True)
        if release.version == app.update_installed_version:
            tk.Label(head, text="INSTALADA · REINICIA", font=fonts["tag"], fg=theme.AMBER,
                     bg=theme.mix(theme.PANEL_DARK, theme.AMBER, 0.15), padx=P(8), pady=P(3)).pack(side="right")
        else:
            text = "Instalar" if newer else ("Reinstalar" if current else "Volver a esta")
            widgets.button(head, text, lambda r=release: self._install(r), font=fonts["small"],
                           kind="primary" if newer else "default", padx=P(12), pady=P(6),
                           state="disabled" if app.update_busy else "normal").pack(side="right")
        meta = " · ".join(part for part in (
            "DESARROLLO" if release.prerelease else "",
            release.date, updates.format_size(release.size), "instalada actualmente" if current else "",
        ) if part)
        if meta:
            widgets.label(row, meta, font=fonts["small"], fg=theme.DIM).pack(fill="x", pady=(P(2), 0))
        for kind_label, text in release.notes_lines():
            line = tk.Frame(row, bg=theme.PANEL_DARK)
            line.pack(fill="x", pady=(P(3), 0))
            widgets.label(line, kind_label.upper(), font=fonts["tag"], fg=NOTE_COLORS[kind_label],
                          width=11).pack(side="left", anchor="n")
            widgets.label(line, text, font=fonts["small"], fg=theme.TEXT_SOFT,
                          wraplength=P(330), justify="left").pack(side="left", fill="x", expand=True)
        tk.Frame(self.releases_frame, bg="#152a2e", height=1).pack(fill="x")

