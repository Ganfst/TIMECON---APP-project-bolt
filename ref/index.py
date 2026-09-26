"""
Radio Timer Pro — Versión Ultra Profesional Avanzada Multi-Monitor.

Atajos de teclado:
  S       — Abrir / cerrar panel de configuración
  M       — Alternar modo compacto / expandido
  F       — Alternar Pantalla Completa (Multi-monitor nativo)
  P       — Modo Pánico (Resaltar estado actual / Refrescar)
  L       — Abrir visor de logs avanzado
  Q       — Guardar y cerrar la aplicación de forma segura
"""

import csv
import json
import tkinter as tk
import tkinter.messagebox
import tkinter.colorchooser as colorchooser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# ---------------------------------------------------------------------------
# Rutas de Almacenamiento
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "radio_timer_config.json"
LOG_FILE    = BASE_DIR / "radio_timer_log.csv"

# ---------------------------------------------------------------------------
# Modelos de Datos
# ---------------------------------------------------------------------------
@dataclass
class BlockConfig:
    """Representa un bloque de tiempo lógico dentro de la hora de transmisión."""
    name:         str
    minute_start: int   
    minute_end:   int   
    color:        str
    fg:           str = "#ffffff"

    def contains(self, minute: int) -> bool:
        return self.minute_start <= minute < self.minute_end

@dataclass
class AppConfig:
    station_name:    str   = "Radio Timer Pro"
    timezone:        str   = "America/Santo_Domingo"
    secondary_tz:    str   = "UTC"
    compact_height:  int   = 70
    expanded_height: int   = 260  
    window_width:    int   = 420
    window_x:        int   = 100
    window_y:        int   = 100
    opacity:         float = 0.95
    blink_enabled:   bool  = True
    blink_seconds:   int   = 15
    log_enabled:     bool  = True
    fullscreen:      bool  = False  
    blocks: list = field(default_factory=lambda: [
        {"name": "EN AIRE / PROGRAMA",  "minute_start": 0,  "minute_end": 45, "color": "#1a7a3c", "fg": "#ffffff"},
        {"name": "PROMO / AVANCES",     "minute_start": 45, "minute_end": 50, "color": "#d97706", "fg": "#ffffff"},
        {"name": "CIERRE DE BLOQUE",    "minute_start": 50, "minute_end": 55, "color": "#2563eb", "fg": "#ffffff"},
        {"name": "CORTE COMERCIAL",     "minute_start": 55, "minute_end": 60, "color": "#dc2626", "fg": "#ffffff"},
    ])

    def save(self) -> None:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls) -> "AppConfig":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                    return cls(**data)
            except Exception:
                pass
        return cls()

# ---------------------------------------------------------------------------
# Registrador de Logs (CSV)
# ---------------------------------------------------------------------------
class BlockLogger:
    def __init__(self, path: Path, enabled: bool):
        self.path    = path
        self.enabled = enabled
        self._last   = ""
        if enabled and not path.exists():
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["timestamp", "evento", "zona_horaria"])

    def record(self, state_name: str, tz_name: str) -> None:
        if not self.enabled or state_name == self._last:
            return
        self._last = state_name
        try:
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    f"Entrada a bloque: {state_name}",
                    tz_name,
                ])
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Gestor de Movimiento y Redimensionado de Ventana
# ---------------------------------------------------------------------------
class WindowManager:
    def __init__(self, root: tk.Tk, drag_widget: tk.Widget, resize_widget: tk.Widget, on_resize_cb):
        self._root = root
        self._x = self._y = 0
        self.on_resize_cb = on_resize_cb
        drag_widget.bind("<ButtonPress-1>", self._drag_start)
        drag_widget.bind("<B1-Motion>",     self._drag_move)
        resize_widget.bind("<B1-Motion>",   self._on_resize)

    def _drag_start(self, e):
        self._x, self._y = e.x, e.y

    def _drag_move(self, e):
        if getattr(self._root, "_is_fullscreen", False): return  
        x = self._root.winfo_x() + (e.x - self._x)
        y = self._root.winfo_y() + (e.y - self._y)
        self._root.geometry(f"+{x}+{y}")

    def _on_resize(self, e):
        if getattr(self._root, "_is_fullscreen", False): return  
        w = max(250, e.x_root - self._root.winfo_x())
        h = max(60,  e.y_root - self._root.winfo_y())
        self._root.geometry(f"{w}x{h}")
        self.on_resize_cb()

# ---------------------------------------------------------------------------
# Panel de Configuración Visual Avanzado
# ---------------------------------------------------------------------------
class SettingsPanel(tk.Toplevel):
    def __init__(self, parent, config: AppConfig, on_save):
        super().__init__(parent)
        self.title("Configuración Profesional")
        self.geometry("620x560")
        self.resizable(True, True)
        try:
            self.iconbitmap(BASE_DIR / "logo_radio.ico")
        except Exception:
            pass
        self.grab_set()
        
        self._cfg = config
        self._on_save = on_save
        self._vars = {}
        self._block_rows = []
        
        self._build_ui()

    def _build_ui(self):
        canvas = tk.Canvas(self, borderwidth=0, background="#f3f4f6")
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="#f3f4f6", padx=15, pady=15)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._section("CONFIGURACIÓN GENERAL DE LA EMISORA")
        self._field("Nombre de la Emisora", "station_name", self._cfg.station_name)
        self._field("Zona Horaria Principal (ej. America/Santo_Domingo)", "timezone", self._cfg.timezone)
        self._field("Zona Horaria Secundaria / UTC", "secondary_tz", self._cfg.secondary_tz)
        self._field("Opacidad de Ventana (0.2 - 1.0)", "opacity", self._cfg.opacity)
        self._check("Activar parpadeo de alerta antes de cambios", "blink_enabled", self._cfg.blink_enabled)
        self._field("Segundos de anticipación para alerta", "blink_seconds", self._cfg.blink_seconds)
        self._check("Habilitar Log / Historial en CSV", "log_enabled", self._cfg.log_enabled)

        self._section("DIMENSIONES POR DEFECTO (PX)")
        self._field("Ancho de Ventana", "window_width", self._cfg.window_width)
        self._field("Alto Modo Expandido", "expanded_height", self._cfg.expanded_height)
        self._field("Alto Modo Compacto", "compact_height", self._cfg.compact_height)

        self._section("PLANIFICACIÓN HORARIA DE BLOQUES (MINUTOS DE LA HORA)")
        
        self.blocks_container = tk.Frame(self.scrollable_frame, bg="#f3f4f6")
        self.blocks_container.pack(fill="x", pady=5)

        hdr = tk.Frame(self.blocks_container, bg="#f3f4f6")
        hdr.pack(fill="x", pady=2)
        headers = [("Min Inicio", 8), ("Min Fin", 8), ("Color Fondo", 12), ("Texto", 8), ("Identificador / Nombre", 24)]
        for text, width in headers:
            tk.Label(hdr, text=text, bg="#f3f4f6", fg="#4b5563", font=("Arial", 9, "bold"), width=width, anchor="w").pack(side="left", padx=2)

        for b in self._cfg.blocks:
            self._add_block_row(b)

        btn_add = tk.Button(self.scrollable_frame, text="+ Añadir Nuevo Bloque", command=lambda: self._add_block_row(),
                            bg="#10b981", fg="white", relief="flat", font=("Arial", 9, "bold"), padx=10, pady=4)
        btn_add.pack(anchor="w", pady=10)

        btn_row = tk.Frame(self.scrollable_frame, bg="#f3f4f6")
        btn_row.pack(fill="x", pady=(20, 10))
        tk.Button(btn_row, text="Cancelar", command=self.destroy, bg="#9ca3af", fg="white", relief="flat", padx=15, pady=6).pack(side="right", padx=5)
        tk.Button(btn_row, text="Guardar Cambios y Aplicar", command=self._save, bg="#2563eb", fg="white", relief="flat", font=("Arial", 9, "bold"), padx=15, pady=6).pack(side="right")

    def _section(self, text):
        tk.Label(self.scrollable_frame, text=text, font=("Arial", 10, "bold"), bg="#f3f4f6", fg="#1f2937", anchor="w").pack(fill="x", pady=(15, 2))
        tk.Frame(self.scrollable_frame, height=2, bg="#d1d5db").pack(fill="x", pady=(0, 8))

    def _field(self, label, key, default):
        row = tk.Frame(self.scrollable_frame, bg="#f3f4f6")
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg="#f3f4f6", fg="#374151", width=35, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(default))
        tk.Entry(row, textvariable=var, width=30, relief="solid", bd=1).pack(side="left", padx=5)
        self._vars[key] = var

    def _check(self, label, key, default):
        var = tk.BooleanVar(value=default)
        tk.Checkbutton(self.scrollable_frame, text=label, variable=var, bg="#f3f4f6", fg="#374151", activebackground="#f3f4f6", anchor="w").pack(fill="x", pady=3)
        self._vars[key] = var

    def _add_block_row(self, block_data=None):
        b = block_data or {"minute_start": 0, "minute_end": 10, "color": "#7c3aed", "fg": "#ffffff", "name": "NUEVO BLOQUE"}
        row = tk.Frame(self.blocks_container, bg="#f3f4f6")
        row.pack(fill="x", pady=2)

        r_vars = {
            "minute_start": tk.StringVar(value=str(b["minute_start"])),
            "minute_end": tk.StringVar(value=str(b["minute_end"])),
            "color": tk.StringVar(value=str(b["color"])),
            "fg": tk.StringVar(value=str(b["fg"])),
            "name": tk.StringVar(value=str(b["name"]))
        }

        tk.Entry(row, textvariable=r_vars["minute_start"], width=8).pack(side="left", padx=2)
        tk.Entry(row, textvariable=r_vars["minute_end"], width=8).pack(side="left", padx=2)
        
        bg_entry = tk.Entry(row, textvariable=r_vars["color"], width=12)
        bg_entry.pack(side="left", padx=2)
        def pick_bg(e=None, var=r_vars["color"]):
            color = colorchooser.askcolor(initialcolor=var.get(), title="Elegir Color de Fondo")[1]
            if color: var.set(color)
        bg_entry.bind("<Double-1>", pick_bg)

        tk.Entry(row, textvariable=r_vars["fg"], width=8).pack(side="left", padx=2)
        tk.Entry(row, textvariable=r_vars["name"], width=24).pack(side="left", padx=2)

        btn_del = tk.Label(row, text="×", fg="#dc2626", font=("Arial", 14, "bold"), cursor="hand2", bg="#f3f4f6")
        btn_del.pack(side="left", padx=5)
        btn_del.bind("<Button-1>", lambda e: self._remove_block_row(row, r_vars))

        self._block_rows.append((row, r_vars))

    def _remove_block_row(self, row_frame, r_vars):
        row_frame.destroy()
        self._block_rows = [r for r in self._block_rows if r[1] != r_vars]

    def _save(self):
        try:
            pytz.timezone(self._vars["timezone"].get().strip())
            pytz.timezone(self._vars["secondary_tz"].get().strip())

            self._cfg.station_name    = self._vars["station_name"].get().strip()
            self._cfg.timezone        = self._vars["timezone"].get().strip()
            self._cfg.secondary_tz    = self._vars["secondary_tz"].get().strip()
            self._cfg.opacity         = max(0.2, min(1.0, float(self._vars["opacity"].get())))
            self._cfg.blink_enabled   = bool(self._vars["blink_enabled"].get())
            self._cfg.blink_seconds   = int(self._vars["blink_seconds"].get())
            self._cfg.log_enabled     = bool(self._vars["log_enabled"].get())
            self._cfg.window_width    = int(self._vars["window_width"].get())
            self._cfg.expanded_height = int(self._vars["expanded_height"].get())
            self._cfg.compact_height  = int(self._vars["compact_height"].get())

            new_blocks = []
            for _, row in self._block_rows:
                start = int(row["minute_start"].get())
                end = int(row["minute_end"].get())
                if start >= end or start < 0 or end > 60:
                    raise ValueError("Los minutos deben cumplir el rango lógico (0 a 60) y el inicio debe ser menor al fin.")
                
                new_blocks.append({
                    "minute_start": start,
                    "minute_end":   end,
                    "color": row["color"].get().strip(),
                    "fg":    row["fg"].get().strip(),
                    "name":  row["name"].get().strip(),
                })
            
            new_blocks.sort(key=lambda x: x["minute_start"])
            self._cfg.blocks = new_blocks
            self._cfg.save()
            self._on_save(self._cfg)
            self.destroy()
        except Exception as exc:
            tk.messagebox.showerror("Error de Configuración", f"Datos inválidos detectados:\n{exc}", parent=self)

# ---------------------------------------------------------------------------
# Visor de Historial / Logs Profesional
# ---------------------------------------------------------------------------
class LogViewer(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Historial de Transmisión / Auditoría de Bloques")
        self.geometry("650x450")
        self._build_ui()

    def _build_ui(self):
        frame = tk.Frame(self, bg="#111827")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        sb = tk.Scrollbar(frame)
        sb.pack(side="right", fill="y")

        txt = tk.Text(frame, font=("Consolas", 10), yscrollcommand=sb.set, state="disabled", relief="flat", bg="#1f2937", fg="#f9fafb")
        txt.pack(fill="both", expand=True)
        sb.config(command=txt.yview)

        if LOG_FILE.exists():
            content = LOG_FILE.read_text(encoding="utf-8")
        else:
            content = "Log Vacío — El historial de bloques se creará dinámicamente al cambiar de segmentos."

        txt.config(state="normal")
        txt.insert("1.0", content)
        txt.config(state="disabled")
        txt.see("end")

        btn_box = tk.Frame(self, padx=5, pady=5)
        btn_box.pack(fill="x", side="bottom")
        tk.Button(btn_box, text="Cerrar Historial", command=self.destroy, bg="#4b5563", fg="white", relief="flat", padx=12, pady=4).pack(side="right", padx=5)
        tk.Button(btn_box, text="Limpiar Historial", command=self._clear_logs, bg="#dc2626", fg="white", relief="flat", padx=12, pady=4).pack(side="left", padx=5)

    def _clear_logs(self):
        if tk.messagebox.askyesno("Confirmar", "¿Seguro que deseas purgar todo el archivo de logs?"):
            if LOG_FILE.exists(): LOG_FILE.unlink()
            self.destroy()

# ---------------------------------------------------------------------------
# Aplicación Principal
# ---------------------------------------------------------------------------
class RadioTimer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = AppConfig.load()
        self._compact = False
        self._settings_open = False
        self._force_panic = False
        self._is_fullscreen = False 

        self._setup_root_window()
        self._build_ui_elements()
        self._setup_global_hotkeys()

        self.logger = BlockLogger(LOG_FILE, self.config.log_enabled)
        self._wm = WindowManager(self.root, self.frame, self.btn_resize, self._on_window_resize)

        # Cargar estado guardado de pantalla completa si aplica
        if self.config.fullscreen:
            self._toggle_fullscreen()

        self.root.update_idletasks()
        self._on_window_resize()

        self._tick()

    def _setup_root_window(self):
        cfg = self.config
        self.root.title(cfg.station_name)
        self.root.geometry(f"{cfg.window_width}x{cfg.expanded_height}+{cfg.window_x}+{cfg.window_y}")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", cfg.opacity)
        self.root.config(bg="grey")
        self.root.attributes("-transparentcolor", "grey")

    def _build_ui_elements(self):
        self.frame = tk.Frame(self.root, bd=0, highlightthickness=2, highlightbackground="#111")
        self.frame.pack(expand=True, fill="both", padx=2, pady=2)

        # Barra de Control Superior
        self.top_bar = tk.Frame(self.frame)
        self.top_bar.pack(fill="x", side="top")

        self.lbl_station = tk.Label(self.top_bar, text=self.config.station_name, font=("Arial", 9, "bold"), anchor="w")
        self.lbl_station.pack(side="left", padx=6, pady=4)

        self._ctrl_btns = {}
        for text, key, cmd in [
            ("×", "close",    self._safe_quit),
            ("⚙", "settings", self._open_settings),
            ("☰", "log",      self._open_log),
            ("⚠", "panic",    self._trigger_panic),
            ("⛶", "fullscreen", self._toggle_fullscreen), 
            ("⊡", "compact",  self._toggle_compact),
        ]:
            btn = tk.Label(self.top_bar, text=text, font=("Arial", 12), cursor="hand2", padx=5)
            btn.pack(side="right")
            btn.bind("<Button-1>", lambda e, c=cmd: c())
            self._ctrl_btns[key] = btn

        # Bloque de Estado Superior
        self.lbl_status = tk.Label(self.frame, text="SINCRONIZANDO...")
        self.lbl_status.pack(expand=True, fill="both", pady=(2, 0))

        # Temporizador Central
        self.lbl_timer = tk.Label(self.frame, text="00:00")
        self.lbl_timer.pack(expand=True, fill="both")

        # Texto Gigante de la Fecha
        self.lbl_date_footer = tk.Label(self.frame, text="", anchor="center")
        self.lbl_date_footer.pack(expand=True, fill="both", pady=(0, 2))

        # Contenedor inferior de relojes horarios duales
        self.clocks_frame = tk.Frame(self.frame)
        self.clocks_frame.pack(side="bottom", fill="x", pady=2)
        
        self.lbl_clock_main = tk.Label(self.clocks_frame, text="", font=("Arial", 9, "bold"))
        self.lbl_clock_main.pack(side="left", padx=10)

        self.lbl_clock_sec = tk.Label(self.clocks_frame, text="", font=("Arial", 8))
        self.lbl_clock_sec.pack(side="right", padx=10)

        self.btn_resize = tk.Label(self.frame, text="⇲", cursor="size_nw_se", font=("Arial", 10))
        self.btn_resize.place(relx=1.0, rely=1.0, anchor="se")

    def _setup_global_hotkeys(self):
        for k in ("s", "S"): self.root.bind(f"<KeyPress-{k}>", lambda _: self._open_settings())
        for k in ("m", "M"): self.root.bind(f"<KeyPress-{k}>", lambda _: self._toggle_compact())
        for k in ("f", "F"): self.root.bind(f"<KeyPress-{k}>", lambda _: self._toggle_fullscreen()) 
        for k in ("l", "L"): self.root.bind(f"<KeyPress-{k}>", lambda _: self._open_log())
        for k in ("p", "P"): self.root.bind(f"<KeyPress-{k}>", lambda _: self._trigger_panic())
        for k in ("q", "Q"): self.root.bind(f"<KeyPress-{k}>", lambda _: self._safe_quit())

    def _get_formatted_date(self, dt: datetime) -> str:
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        
        dia_semana = dias[dt.weekday()]
        dia_num = dt.day
        mes_nombre = meses[dt.month - 1]
        anio = dt.year
        
        return f"{dia_semana}, {dia_num} De {mes_nombre} {anio}"

    def _tick(self):
        try:
            tz_main = pytz.timezone(self.config.timezone)
            tz_sec = pytz.timezone(self.config.secondary_tz)
        except Exception:
            tz_main = tz_sec = pytz.utc

        now_main = datetime.now(tz_main)
        now_sec = datetime.now(tz_sec)

        blocks = [BlockConfig(**b) for b in self.config.blocks]
        current_block = self._find_active_block(blocks, now_main.minute)
        target_time = self._calculate_block_end(now_main, current_block)

        remaining = max(0, int((target_time - now_main).total_seconds()))
        
        color_bg = current_block.color
        color_fg = current_block.fg

        if self.config.blink_enabled and remaining <= self.config.blink_seconds:
            if now_main.second % 2 == 0:
                color_bg, color_fg = ("#f59e0b", "#000000")

        if self._force_panic:
            color_bg, color_fg = ("#ef4444", "#ffffff")
            if now_main.second % 2 == 0: self._force_panic = False

        mins, secs = divmod(remaining, 60)
        date_str = self._get_formatted_date(now_main)

        self._update_ui_theme(
            bg=color_bg, fg=color_fg,
            status=current_block.name.upper(),
            timer=f"{mins:02d}:{secs:02d}",
            clock_m=f"LOC: {now_main.strftime('%H:%M:%S')}",
            clock_s=f"{self.config.secondary_tz}: {now_sec.strftime('%H:%M:%S')}",
            date_text=date_str
        )
        
        self.logger.record(current_block.name, self.config.timezone)
        self.root.after(1000, self._tick)

    @staticmethod
    def _find_active_block(blocks: list, minute: int) -> BlockConfig:
        for b in blocks:
            if b.contains(minute): return b
        return blocks[0] if blocks else BlockConfig("SIN ASIGNAR", 0, 60, "#374151")

    @staticmethod
    def _calculate_block_end(now: datetime, block: BlockConfig) -> datetime:
        end_m = block.minute_end
        if end_m >= 60:
            return (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        target = now.replace(minute=end_m, second=0, microsecond=0)
        if target <= now:
            target += timedelta(hours=1)
        return target

    def _update_ui_theme(self, *, bg, fg, status, timer, clock_m, clock_s, date_text):
        widgets = [
            self.frame, self.top_bar, self.lbl_station,
            self.lbl_status, self.lbl_timer, self.clocks_frame,
            self.lbl_clock_main, self.lbl_clock_sec, self.lbl_date_footer, self.btn_resize
        ] + list(self._ctrl_btns.values())

        for w in widgets:
            try:
                w.configure(bg=bg, fg=fg)
            except Exception:
                w.configure(bg=bg)

        self.lbl_status.configure(text=status)
        self.lbl_timer.configure(text=timer)
        self.lbl_clock_main.configure(text=clock_m)
        self.lbl_clock_sec.configure(text=clock_s)
        self.lbl_date_footer.configure(text=date_text)

    def _on_window_resize(self, _=None):
        h = self.root.winfo_height()
        if self._compact:
            self.lbl_timer.config(font=("Arial", max(20, int(h * 0.55)), "bold"))
        else:
            font_size_status = max(10, int(h * 0.10))
            self.lbl_status.config(font=("Arial", font_size_status, "bold"))
            self.lbl_date_footer.config(font=("Arial", font_size_status, "bold"))
            self.lbl_timer.config(font=("Arial", max(24, int(h * 0.32)), "bold"))

    def _toggle_compact(self):
        if getattr(self, "_is_fullscreen", False): return  
        
        self._compact = not self._compact
        cfg = self.config
        h = cfg.compact_height if self._compact else cfg.expanded_height

        if self._compact:
            self.lbl_status.pack_forget()
            self.lbl_date_footer.pack_forget()
            self.clocks_frame.pack_forget()
            self._ctrl_btns["compact"].config(text="⊞")
        else:
            self.lbl_status.pack(expand=True, fill="both", pady=(2, 0))
            self.lbl_timer.pack_forget()
            self.lbl_timer.pack(expand=True, fill="both")
            self.lbl_date_footer.pack(expand=True, fill="both", pady=(0, 2))
            self.clocks_frame.pack(side="bottom", fill="x", pady=2)
            self._ctrl_btns["compact"].config(text="⊡")

        self.root.geometry(f"{self.root.winfo_width()}x{h}")
        self._on_window_resize()

    def _toggle_fullscreen(self):
        """Alterna el modo pantalla completa real en el monitor actual donde está la ventana."""
        self._is_fullscreen = not self._is_fullscreen
        
        if self._is_fullscreen:
            if self._compact: self._toggle_compact()  
            self.btn_resize.place_forget()           
            
            # Guardamos la posición exacta antes de expandirse
            self._saved_geometry = self.root.geometry()
            
            # Capturamos el tamaño de la pantalla donde está reposando la app en este instante
            scr_width = self.root.winfo_screenwidth()
            scr_height = self.root.winfo_screenheight()
            
            # Calculamos el desfase X del monitor actual para forzar la posición (0,0) de ESE monitor
            # Nota: winfo_x() nos da la posición global combinada en el escritorio expandido.
            win_x = self.root.winfo_x()
            monitor_offset_x = (win_x // scr_width) * scr_width
            
            # Forzamos tamaño de monitor completo manteniendo overrideredirect intacto
            self.root.geometry(f"{scr_width}x{scr_height}+{monitor_offset_x}+0")
        else:
            self.btn_resize.place(relx=1.0, rely=1.0, anchor="se")
            
            if hasattr(self, "_saved_geometry"):
                self.root.geometry(self._saved_geometry)
            else:
                self.root.geometry(f"{self.config.window_width}x{self.config.expanded_height}+{self.config.window_x}+{self.config.window_y}")
            
        self.config.fullscreen = self._is_fullscreen
        self.root.update_idletasks()
        self._on_window_resize()

    def _trigger_panic(self):
        self._force_panic = True

    def _open_settings(self):
        if self._settings_open: return
        self._settings_open = True

        def on_save(new_cfg: AppConfig):
            self.config = new_cfg
            self.logger = BlockLogger(LOG_FILE, new_cfg.log_enabled)
            self.lbl_station.config(text=new_cfg.station_name)
            self.root.attributes("-alpha", new_cfg.opacity)
            if not getattr(self, "_is_fullscreen", False):
                self.root.geometry(f"{new_cfg.window_width}x{new_cfg.expanded_height}")
            self._settings_open = False
            self._on_window_resize()

        panel = SettingsPanel(self.root, self.config, on_save)
        panel.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "_settings_open", False), panel.destroy()))

    def _open_log(self):
        LogViewer(self.root)

    def _safe_quit(self):
        is_fs = getattr(self, "_is_fullscreen", False)
        self.config.fullscreen = is_fs
        
        if not is_fs:
            self.config.window_width = self.root.winfo_width()
            if not self._compact:
                self.config.expanded_height = self.root.winfo_height()
            self.config.window_x = self.root.winfo_x()
            self.config.window_y = self.root.winfo_y()
            
        self.config.save()
        self.root.destroy()

# ---------------------------------------------------------------------------
# Punto de Entrada
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = RadioTimer(root)
    root.mainloop()