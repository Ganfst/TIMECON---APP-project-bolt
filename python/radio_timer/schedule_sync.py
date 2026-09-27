"""Descarga de la parrilla semanal publicada en la web de la emisora.

La web (Laravel) entrega la programación con un POST a /weekSchedule, igual que el ajax de su página:
primero se abre la portada para obtener la cookie de sesión y el token CSRF, y luego se pide la parrilla.
Respuesta: {"Lunes": [{"name": ..., "start_time": "07:30", "end_time": "08:00", "is_active": true, ...}], ...}

Este módulo no depende de Tkinter.
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from . import __version__, model

SCHEDULE_URL = "https://radioluz937fm.com/weekSchedule"
TIMEOUT_SECONDS = 15
_TOKEN_PATTERN = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', re.IGNORECASE)


class SyncError(Exception):
    """Error con un mensaje apto para mostrar al operador."""


@dataclass
class SyncResult:
    programs: list[model.Program]
    skipped: list[str] = field(default_factory=list)  # avisos de lo que no se pudo importar


def _plain(text: str) -> str:
    """'Miércoles' → 'miercoles'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).strip().lower()


DAY_INDEX = {_plain(name): index for index, name in enumerate(model.WEEKDAYS_ES)}


def fetch_week_schedule(url: str = SCHEDULE_URL, timeout: float = TIMEOUT_SECONDS) -> object:
    """Pide la parrilla a la web y devuelve el JSON tal cual. Lanza SyncError si algo falla."""
    parts = urllib.parse.urlsplit(url)
    home = f"{parts.scheme}://{parts.netloc}/"
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = {"User-Agent": f"RadioTimer/{__version__}"}
    try:
        with opener.open(urllib.request.Request(home, headers=headers), timeout=timeout) as response:
            page = response.read().decode("utf-8", "replace")
        match = _TOKEN_PATTERN.search(page)
        token = match.group(1) if match else ""
        if not token:
            # Laravel también acepta el token de la cookie XSRF-TOKEN en la cabecera X-XSRF-TOKEN.
            cookie = next((c.value for c in jar if c.name == "XSRF-TOKEN"), "")
            headers["X-XSRF-TOKEN"] = urllib.parse.unquote(cookie)
        else:
            headers["X-CSRF-TOKEN"] = token
        request = urllib.request.Request(
            url, data=urllib.parse.urlencode({"_token": token}).encode("ascii"),
            headers={**headers, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        with opener.open(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise SyncError(f"La web respondió con error {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise SyncError(f"No se pudo conectar con {parts.netloc}: {reason}") from exc
    try:
        return json.loads(body)
    except ValueError as exc:
        raise SyncError("La web no devolvió una parrilla válida") from exc


def parse_week_schedule(data: object) -> SyncResult:
    """Convierte la respuesta de la web en programas de la parrilla.

    Se ignoran los programas inactivos o borrados. Si dos programas tienen exactamente el mismo horario
    se unen en un solo título; si se cruzan de otra forma, queda el que empieza primero y se avisa.
    """
    if not isinstance(data, dict):
        raise SyncError("La web no devolvió una parrilla válida")
    skipped: list[str] = []
    by_slot: dict[tuple[int, int, int], list[str]] = {}
    for day_name, entries in data.items():
        day = DAY_INDEX.get(_plain(str(day_name)))
        if day is None or not isinstance(entries, list):
            skipped.append(f"Día desconocido: {day_name}")
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("is_active") is False or entry.get("is_deleted"):
                continue
            name = model.clean_program_title(entry.get("name", ""))
            try:
                start = model.parse_clock_minutes(str(entry.get("start_time", "")))
                end = model.parse_clock_minutes(str(entry.get("end_time", "")))
            except ValueError:
                skipped.append(f"{name or 'Sin nombre'}: horario inválido")
                continue
            if end == 0:
                end = model.DAY_MINUTES  # termina a medianoche
            if not name or end <= start:
                skipped.append(f"{name or 'Sin nombre'} ({model.WEEKDAYS_ES[day]}): horario inválido")
                continue
            titles = by_slot.setdefault((day, start, end), [])
            if name not in titles:
                titles.append(name)

    programs: list[model.Program] = []
    for (day, start, end), titles in sorted(by_slot.items()):
        program = model.make_program(day, start, end, " / ".join(titles))
        clash = model.overlapping_program(programs, program)
        if clash is not None:
            skipped.append(f"{program.title} ({model.WEEKDAYS_ES[day]} {program.hours_label}) "
                           f"se cruza con {clash.title}")
            continue
        programs.append(program)
    return SyncResult(programs, skipped)


def download_programs(url: str = SCHEDULE_URL, timeout: float = TIMEOUT_SECONDS) -> SyncResult:
    return parse_week_schedule(fetch_week_schedule(url, timeout))
