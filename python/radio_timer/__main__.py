"""Punto de entrada: `python -m radio_timer [opciones]`."""
from __future__ import annotations

import argparse
import sys
import tkinter as tk
from datetime import datetime
from typing import Callable

from .app import RadioTimerApp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="radio_timer",
        description="Radio Timer: temporizador de programación para emisoras, atado al reloj real.",
    )
    parser.add_argument("--hora", metavar="HH:MM[:SS]",
                        help="simula que el reloj arranca en esa hora (sigue avanzando en tiempo real); "
                             "útil para probar la alerta de los últimos 10 segundos")
    parser.add_argument("--prefs", metavar="ARCHIVO", help="archivo JSON de preferencias alternativo")
    parser.add_argument("--compacto", action="store_true", help="iniciar en modo compacto")
    parser.add_argument("--pantalla-completa", action="store_true", help="iniciar en pantalla completa")
    parser.add_argument("--ventana", action="store_true", help="abrir en ventana normal en lugar de maximizada")
    return parser.parse_args(argv)


def parse_clock_time(text: str) -> tuple[int, int, int]:
    parts = text.strip().split(":")
    if len(parts) not in (2, 3):
        raise ValueError("use el formato HH:MM o HH:MM:SS")
    numbers = [int(part) for part in parts] + [0] * (3 - len(parts))
    hour, minute, second = numbers
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValueError("hora fuera de rango")
    return hour, minute, second


def make_clock(simulated: str | None) -> Callable[[], datetime]:
    """Devuelve un reloj real, o uno desplazado para que 'ahora' sea la hora simulada."""
    if not simulated:
        return datetime.now
    hour, minute, second = parse_clock_time(simulated)
    start = datetime.now().replace(hour=hour, minute=minute, second=second, microsecond=0)
    offset = start - datetime.now()
    return lambda: datetime.now() + offset


def enable_dpi_awareness() -> None:
    """Evita que Windows escale la ventana de forma borrosa en pantallas de alta densidad."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        clock = make_clock(args.hora)
    except ValueError as exc:
        print(f"Hora inválida: {exc}", file=sys.stderr)
        return 2
    enable_dpi_awareness()
    root = tk.Tk()
    RadioTimerApp(root, clock=clock, prefs_path=args.prefs, start_compact=args.compacto,
                  start_fullscreen=args.pantalla_completa, start_maximized=not args.ventana)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
