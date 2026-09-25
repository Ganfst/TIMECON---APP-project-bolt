"""Widgets de Tkinter con el estilo oscuro de la aplicación."""
from __future__ import annotations

import tkinter as tk
import weakref
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable

from . import theme

SCROLLBAR_STYLE = "Dark.Vertical.TScrollbar"

# Áreas desplazables registradas por su lienzo, para dirigir la rueda del ratón.
_SCROLL_AREAS: "weakref.WeakKeyDictionary[tk.Misc, _ScrollableBase]" = weakref.WeakKeyDictionary()


# ------------------------------------------------------------ básicos ---

def label(parent: tk.Misc, text: str = "", *, font: tkfont.Font, fg: str = theme.TEXT_SOFT,
          bg: str | None = None, anchor: str = "w", **kwargs) -> tk.Label:
    if bg is None:
        bg = parent.cget("bg")
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, anchor=anchor, **kwargs)


def button(parent: tk.Misc, text: str, command: Callable[[], None], *, font: tkfont.Font,
           kind: str = "default", padx: int = 14, pady: int = 8, **kwargs) -> tk.Button:
    """kind: 'default', 'primary', 'danger' o 'ghost'."""
    styles = {
        "default": dict(bg=theme.BUTTON_BG, fg=theme.TEXT_SOFT, activebackground=theme.BUTTON_ACTIVE, activeforeground=theme.TEXT),
        "primary": dict(bg=theme.PRIMARY, fg=theme.PRIMARY_TEXT, activebackground=theme.PRIMARY_ACTIVE, activeforeground=theme.PRIMARY_TEXT),
        "danger": dict(bg=theme.DANGER_BG, fg=theme.DANGER, activebackground=theme.DANGER, activeforeground=theme.TEXT),
        "ghost": dict(bg=parent.cget("bg"), fg=theme.MUTED, activebackground=theme.BUTTON_ACTIVE, activeforeground=theme.TEXT),
    }
    return tk.Button(
        parent, text=text, command=command, font=font, relief="flat", bd=0,
        highlightthickness=0, padx=padx, pady=pady, cursor="hand2",
        disabledforeground=theme.DIM, **styles[kind], **kwargs,
    )


def _limit_length(widget: tk.Entry, max_length: int) -> None:
    command = (widget.register(lambda proposed: len(proposed) <= max_length), "%P")
    widget.configure(validate="key", validatecommand=command)


def entry(parent: tk.Misc, variable: tk.Variable, *, font: tkfont.Font, width: int | None = None,
          justify: str = "left", max_length: int | None = None) -> tk.Entry:
    widget = tk.Entry(
        parent, textvariable=variable, font=font, justify=justify,
        bg=theme.FIELD, fg=theme.TEXT_SOFT, insertbackground=theme.TEXT,
        relief="flat", bd=6, highlightthickness=1,
        highlightbackground=theme.LINE, highlightcolor=theme.PRIMARY,
    )
    if width is not None:
        widget.configure(width=width)
    if max_length:
        _limit_length(widget, max_length)
    return widget


def spinbox(parent: tk.Misc, variable: tk.Variable, *, font: tkfont.Font, low: int, high: int,
            width: int = 4, fmt: str | None = None) -> tk.Spinbox:
    widget = tk.Spinbox(
        parent, textvariable=variable, from_=low, to=high, width=width, font=font,
        justify="center", bg=theme.FIELD, fg=theme.TEXT_SOFT, buttonbackground=theme.BUTTON_BG,
        insertbackground=theme.TEXT, relief="flat", bd=6, highlightthickness=1,
        highlightbackground=theme.LINE, highlightcolor=theme.PRIMARY, wrap=True,
    )
    if fmt:
        widget.configure(format=fmt)
    return widget


def option_menu(parent: tk.Misc, variable: tk.StringVar, options: list[str], *, font: tkfont.Font) -> tk.OptionMenu:
    widget = tk.OptionMenu(parent, variable, *options)
    widget.configure(
        font=font, bg=theme.FIELD, fg=theme.TEXT_SOFT, activebackground=theme.BUTTON_ACTIVE,
        activeforeground=theme.TEXT, relief="flat", bd=0, highlightthickness=1,
        highlightbackground=theme.LINE, indicatoron=True, padx=10, pady=6, cursor="hand2",
    )
    widget["menu"].configure(bg=theme.FIELD, fg=theme.TEXT_SOFT, activebackground=theme.BUTTON_ACTIVE,
                             activeforeground=theme.TEXT, font=font, bd=0)
    return widget


def separator(parent: tk.Misc, pady: tuple[int, int] | int = 0) -> tk.Frame:
    line = tk.Frame(parent, bg=theme.LINE, height=1)
    line.pack(fill="x", pady=pady)
    return line


# ------------------------------------------------- campos especiales ---

class PlaceholderEntry(tk.Entry):
    """Campo con texto de ayuda gris. `value()` nunca devuelve el texto de ayuda."""

    def __init__(self, parent: tk.Misc, placeholder: str, *, font: tkfont.Font, max_length: int | None = None):
        super().__init__(
            parent, font=font, bg=theme.FIELD, fg=theme.TEXT_SOFT, insertbackground=theme.TEXT,
            relief="flat", bd=6, highlightthickness=1,
            highlightbackground=theme.LINE, highlightcolor=theme.PRIMARY,
        )
        self.placeholder = placeholder
        self.showing_placeholder = False
        if max_length:
            command = (self.register(lambda proposed: self.showing_placeholder or len(proposed) <= max_length), "%P")
            self.configure(validate="key", validatecommand=command)
        self.bind("<FocusIn>", self._hide_placeholder, add="+")
        self.bind("<FocusOut>", self._show_placeholder, add="+")
        self._show_placeholder()

    def _has_focus(self) -> bool:
        try:
            return self.focus_get() is self
        except (KeyError, tk.TclError):
            return False

    def _hide_placeholder(self, _event: tk.Event | None = None) -> None:
        if self.showing_placeholder:
            self.delete(0, "end")
            self.showing_placeholder = False
            self.configure(fg=theme.TEXT_SOFT)

    def _show_placeholder(self, _event: tk.Event | None = None) -> None:
        if not self.get() and not self._has_focus():
            self.showing_placeholder = True
            self.insert(0, self.placeholder)
            self.configure(fg=theme.DIM)

    def value(self) -> str:
        return "" if self.showing_placeholder else self.get()

    def set_value(self, text: str) -> None:
        self._hide_placeholder()
        self.delete(0, "end")
        self.insert(0, text)
        self._show_placeholder()

    def clear(self) -> None:
        self.set_value("")


class Switch(tk.Canvas):
    """Interruptor de encendido/apagado ligado a un BooleanVar (clic, espacio o Enter)."""

    def __init__(self, parent: tk.Misc, variable: tk.BooleanVar, command: Callable[[], None] | None = None,
                 *, scale: float = 1.0):
        self._sw_width = round(48 * scale)
        self._sw_height = round(26 * scale)
        bg = parent.cget("bg")
        super().__init__(parent, width=self._sw_width, height=self._sw_height, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=1)
        self.variable = variable
        self.command = command
        radius = self._sw_height / 2
        self._pad = round(3 * scale)
        self._knob_d = self._sw_height - 2 * self._pad
        self._track = [
            self.create_oval(0, 0, self._sw_height, self._sw_height, width=0),
            self.create_oval(self._sw_width - self._sw_height, 0, self._sw_width, self._sw_height, width=0),
            self.create_rectangle(radius, 0, self._sw_width - radius, self._sw_height, width=0),
        ]
        self._knob = self.create_oval(0, 0, 0, 0, width=0)
        self.bind("<Button-1>", self.toggle)
        self.bind("<space>", self.toggle)
        self.bind("<Return>", self.toggle)
        self._trace = variable.trace_add("write", lambda *_args: self.redraw())
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.redraw()

    def toggle(self, _event: tk.Event | None = None) -> str:
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()
        return "break"

    def redraw(self) -> None:
        on = bool(self.variable.get())
        for item in self._track:
            self.itemconfigure(item, fill=theme.SWITCH_ON if on else theme.SWITCH_OFF)
        x = self._sw_width - self._pad - self._knob_d if on else self._pad
        self.coords(self._knob, x, self._pad, x + self._knob_d, self._pad + self._knob_d)
        self.itemconfigure(self._knob, fill=theme.KNOB_ON if on else theme.KNOB_OFF)

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self:
            try:
                self.variable.trace_remove("write", self._trace)
            except (tk.TclError, ValueError):
                pass


# ------------------------------------------------ áreas desplazables ---

def _scrollbar_style(widget: tk.Misc) -> str:
    style = ttk.Style(widget)
    if style.theme_use() != "clam":
        style.theme_use("clam")
    style.configure(
        SCROLLBAR_STYLE, background=theme.BUTTON_BG, troughcolor=theme.PANEL_DARK,
        bordercolor=theme.PANEL_DARK, lightcolor=theme.BUTTON_BG, darkcolor=theme.BUTTON_BG,
        arrowcolor=theme.MUTED, gripcount=0, arrowsize=12,
    )
    style.map(SCROLLBAR_STYLE, background=[("active", theme.BUTTON_ACTIVE)])
    return SCROLLBAR_STYLE


def dark_scrollbar(parent: tk.Misc, command: Callable[..., object]) -> ttk.Scrollbar:
    """Barra de desplazamiento vertical con los colores oscuros de la aplicación."""
    return ttk.Scrollbar(parent, orient="vertical", command=command, style=_scrollbar_style(parent))


class _ScrollableBase(tk.Frame):
    """Lienzo + barra vertical que solo aparece cuando el contenido no cabe."""

    def _init_scroll(self, bg: str) -> None:
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, width=1, height=1, yscrollincrement=24)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                       style=_scrollbar_style(self))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self._scroll_visible = False
        _SCROLL_AREAS[self.canvas] = self

    def _set_scrollbar(self, visible: bool) -> None:
        if visible == self._scroll_visible:
            return
        self._scroll_visible = visible
        if visible:
            self.scrollbar.pack(side="right", fill="y", before=self.canvas)
        else:
            self.scrollbar.pack_forget()
            self.canvas.yview_moveto(0)

    def can_scroll(self) -> bool:
        return self._scroll_visible

    def scroll_units(self, units: int) -> None:
        self.canvas.yview_scroll(units, "units")


class ScrollFrame(_ScrollableBase):
    """Contenido vertical desplazable en `self.body`.

    fit_height=False: ocupa el espacio que le dé su contenedor (ventanas de diálogo).
    fit_height=True: mide lo que su contenido, hasta `max_height` (paneles laterales).
    """

    def __init__(self, parent: tk.Misc, bg: str, *, width: int | None = None, fit_height: bool = False):
        super().__init__(parent, bg=bg)
        self._init_scroll(bg)
        if width:
            self.canvas.configure(width=width)
        self.fit_height = fit_height
        self.max_height: int | None = None
        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _event: self.sync())
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self.sync()

    def set_max_height(self, height: int) -> None:
        height = max(1, int(height))
        if height != self.max_height:
            self.max_height = height
            self.sync()

    def sync(self) -> None:
        body_h = self.body.winfo_reqheight()
        if self.fit_height:
            target = body_h if self.max_height is None else min(body_h, self.max_height)
            target = max(1, target)
            if int(float(self.canvas.cget("height"))) != target:
                self.canvas.configure(height=target)
            visible_h = target
        else:
            visible_h = self.canvas.winfo_height()
        self._set_scrollbar(visible_h > 1 and body_h > visible_h)
        width = max(1, self.canvas.winfo_width(), int(float(self.canvas.cget("width"))))
        self.canvas.configure(scrollregion=(0, 0, width, max(body_h, visible_h)))


class CenteredScrollArea(_ScrollableBase):
    """Mantiene `self.body` centrado; si no cabe en alto, lo alinea arriba y permite desplazarlo."""

    def __init__(self, parent: tk.Misc, bg: str):
        super().__init__(parent, bg=bg)
        self._init_scroll(bg)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(0, 0, window=self.body, anchor="n")
        self.body.bind("<Configure>", lambda _event: self.reflow())
        self.canvas.bind("<Configure>", lambda _event: self.reflow())

    def viewport_size(self) -> tuple[int, int]:
        return self.canvas.winfo_width(), self.canvas.winfo_height()

    def reflow(self) -> None:
        view_w, view_h = self.viewport_size()
        if view_w <= 1 or view_h <= 1:
            return
        body_w = self.body.winfo_reqwidth()
        body_h = self.body.winfo_reqheight()
        overflow = body_h > view_h
        self._set_scrollbar(overflow)
        x = max(view_w, body_w) / 2
        y = 0 if overflow else (view_h - body_h) / 2
        self.canvas.coords(self._window, x, y)
        self.canvas.configure(scrollregion=(0, 0, max(view_w, body_w), max(view_h, body_h)))


# ---------------------------------------------------- rueda del ratón ---

def scroll_widget(widget: tk.Misc | None, units: int) -> bool:
    """Desplaza el área desplazable más cercana que contenga a `widget`. Devuelve si hubo desplazamiento."""
    current = widget
    while current is not None:
        area = _SCROLL_AREAS.get(current)
        if area is not None and area.can_scroll():
            area.scroll_units(units)
            return True
        current = getattr(current, "master", None)
    return False


def install_wheel_router(root: tk.Tk) -> None:
    """Una sola vinculación global: la rueda desplaza el área que está bajo el puntero."""
    if getattr(root, "_radio_timer_wheel_router", False):
        return
    root._radio_timer_wheel_router = True  # type: ignore[attr-defined]

    def on_wheel(event: tk.Event) -> str | None:
        try:
            target = root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return None
        num = getattr(event, "num", None)
        if num == 4:
            units = -3
        elif num == 5:
            units = 3
        else:
            delta = getattr(event, "delta", 0) or 0
            units = -3 if delta > 0 else 3
        return "break" if scroll_widget(target, units) else None

    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        root.bind_all(sequence, on_wheel, add="+")
