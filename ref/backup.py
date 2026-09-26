import tkinter as tk
from datetime import datetime, timedelta
import pytz

class RadioTimer:
    def __init__(self, root):
        self.root = root
        self.root.title("Timer Pro SD")
        self.root.geometry("400x200")
        
        # 1. QUITAR BARRA DE TÍTULO ESTÁNDAR
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        # 2. HACER BORDES REDONDEADOS (Simulado con transparencia en Windows)
        # Nota: En Windows, la forma real de redondear es usar un color transparente
        self.root.config(bg='grey')
        self.root.attributes("-transparentcolor", "grey")

        self.timezone = pytz.timezone('America/Santo_Domingo')

        # Contenedor principal con bordes redondeados (vía Canvas o Frame con radio)
        # Para simplicidad y fluidez, usaremos un Frame con borde resaltado
        self.main_frame = tk.Frame(root, bd=0, highlightthickness=2, highlightbackground="#333333")
        self.main_frame.pack(expand=True, fill="both", padx=5, pady=5)

        # Botón de cerrar (X oculta/discreta en la esquina)
        self.close_btn = tk.Label(self.main_frame, text="×", font=("Arial", 14), fg="white", cursor="hand2")
        self.close_btn.place(relx=1.0, x=-5, y=5, anchor="ne")
        self.close_btn.bind("<Button-1>", lambda e: self.root.destroy())

        self.label_status = tk.Label(self.main_frame, text="INICIANDO...", fg="white")
        self.label_status.pack(expand=True, fill="both", pady=(20, 0))

        self.label_timer = tk.Label(self.main_frame, text="00:00", fg="white")
        self.label_timer.pack(expand=True, fill="both")

        # EVENTOS PARA MOVER LA VENTANA (Ya que no hay barra)
        self.main_frame.bind("<ButtonPress-1>", self.start_move)
        self.main_frame.bind("<B1-Motion>", self.do_move)
        
        # EVENTO PARA REDIMENSIONAR (Esquina inferior derecha)
        self.resizer = tk.Label(self.main_frame, text="⇲", fg="white", cursor="size_nw_se")
        self.resizer.place(relx=1.0, rely=1.0, anchor="se")
        self.resizer.bind("<B1-Motion>", self.resize_window)

        self.root.bind('<Configure>', self.resize_text)
        self.update_clock()

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def resize_window(self, event):
        # Permite agrandar o achicar arrastrando el icono ⇲
        new_width = max(200, event.x_root - self.root.winfo_x())
        new_height = max(100, event.y_root - self.root.winfo_y())
        self.root.geometry(f"{new_width}x{new_height}")

    def resize_text(self, event=None):
        height = self.root.winfo_height()
        status_font_size = max(10, int(height / 10))
        timer_font_size = max(20, int(height / 2.5))
        self.label_status.config(font=("Helvetica", status_font_size, "bold"))
        self.label_timer.config(font=("Helvetica", timer_font_size, "bold"))

    def update_clock(self):
        now = datetime.now(self.timezone)
        current_min = now.minute
        current_sec = now.second

        if current_min < 50:
            bg_color = "#228B22" # Forest Green
            status_text = "EN AIRE"
            target = now.replace(minute=55, second=0, microsecond=0)
        elif 50 <= current_min < 55:
            bg_color = "#0056b3" # Azul profundo
            status_text = "CIERRE DE BLOQUE"
            target = now.replace(minute=55, second=0, microsecond=0)
        else:
            bg_color = "#cc0000" # Rojo fuerte
            status_text = "CORTE / COMERCIALES"
            target = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        remaining = target - now
        total_seconds = max(0, int(remaining.total_seconds()))

        # Parpadeo últimos 10s antes del minuto 55
        if current_min == 54 and 50 <= current_sec <= 59:
            bg_color = "#ffcc00" if current_sec % 2 == 0 else "#cc0000"
            fg_color = "black" if bg_color == "#ffcc00" else "white"
        else:
            fg_color = "white"

        m, s = divmod(total_seconds, 60)
        self.main_frame.configure(bg=bg_color)
        self.label_status.configure(bg=bg_color, fg=fg_color, text=status_text)
        self.label_timer.configure(bg=bg_color, fg=fg_color, text=f"{m:02d}:{s:02d}")
        self.resizer.configure(bg=bg_color, fg=fg_color)
        self.close_btn.configure(bg=bg_color, fg=fg_color)

        self.root.after(1000, self.update_clock)

if __name__ == "__main__":
    root = tk.Tk()
    app = RadioTimer(root)
    root.mainloop()