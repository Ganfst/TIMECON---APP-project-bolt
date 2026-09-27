"""Lógica pura del Radio Timer: secciones, programación y formato.

Este módulo no depende de Tkinter, así que se puede probar sin interfaz.
El contador nunca se decrementa "a mano": cada sección tiene una hora de
inicio y fin calculadas a partir de la hora de inicio del programa, y el
tiempo restante se obtiene comparando con el reloj del sistema.
"""
from __future__ import annotations

import math
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Sequence

KIND_CHAIN = "sums"          # En cadena: se suma al total y encadena con la siguiente
KIND_SEPARATE = "separate"   # Independiente: no se suma al total
KINDS = (KIND_CHAIN, KIND_SEPARATE)
KIND_LABELS = {KIND_CHAIN: "EN CADENA", KIND_SEPARATE: "INDEPENDIENTE"}
KIND_NAMES = {KIND_CHAIN: "En cadena", KIND_SEPARATE: "Independiente"}

FLASH_WINDOW_SECONDS = 10
HOUR_SECONDS = 60 * 60
MAX_SEGMENT_MINUTES = 24 * 60
MAX_LABEL_LENGTH = 24
MAX_STATION_LENGTH = 40
MAX_PROGRAM_TITLE_LENGTH = 40
DEFAULT_STATION_FALLBACK = "Radio"

PALETTE: tuple[tuple[str, str], ...] = (
    ("#0e8f88", "#f1fffc"),
    ("#ec8d2d", "#fffaf1"),
    ("#238ac2", "#f1f9ff"),
    ("#d34c62", "#fff4f5"),
    ("#7c5ec2", "#f5f1ff"),
    ("#3c9c5e", "#f1fff4"),
    ("#c2963c", "#fff8ef"),
)

WEEKDAYS_ES = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
WEEKDAYS_SHORT_ES = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


@dataclass(frozen=True)
class Segment:
    """Una sección de la programación (p. ej. EN AIRE, 55 minutos, en cadena)."""

    id: str
    label: str
    detail: str
    duration: int  # segundos
    color: str
    text: str
    kind: str

    @property
    def is_chain(self) -> bool:
        return self.kind == KIND_CHAIN

    @property
    def kind_label(self) -> str:
        return KIND_LABELS[self.kind]

    @property
    def kind_name(self) -> str:
        return KIND_NAMES[self.kind]

    def to_dict(self) -> dict:
        # Se usa la clave "type" para mantener compatibilidad con el JSON de la versión web.
        return {
            "id": self.id,
            "label": self.label,
            "detail": self.detail,
            "duration": self.duration,
            "color": self.color,
            "text": self.text,
            "type": self.kind,
        }

    @classmethod
    def from_dict(cls, data: object) -> "Segment":
        if not isinstance(data, dict):
            raise ValueError(f"segmento inválido: {data!r}")
        kind = data.get("type", data.get("kind"))
        try:
            segment = cls(
                id=str(data["id"]),
                label=str(data["label"]),
                detail=str(data.get("detail", "")),
                duration=int(data["duration"]),
                color=str(data["color"]),
                text=str(data.get("text", "#ffffff")),
                kind=str(kind),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"segmento inválido: {data!r}") from exc
        if segment.duration <= 0 or segment.kind not in KINDS or not segment.label.strip():
            raise ValueError(f"segmento inválido: {data!r}")
        return segment


def default_segments() -> list[Segment]:
    """Los bloques de la hora en Radio Luz: 50 + 5 en cadena y 5 de corte; suman 60 porque se reinicia cada hora."""
    return [
        Segment("s1", "EN AIRE", "Programa en vivo", 50 * 60, "#0e8f88", "#f1fffc", KIND_CHAIN),
        Segment("s3", "CIERRE", "Cierre de bloque", 5 * 60, "#238ac2", "#f1f9ff", KIND_CHAIN),
        Segment("s4", "CORTE Y PROMOCIONES", "Corte comercial y promociones", 5 * 60, "#d34c62", "#fff4f5",
                KIND_SEPARATE),
    ]


@dataclass(frozen=True)
class ScheduledSegment:
    """Una sección ya ubicada en el tiempo, con su estado respecto a `now`."""

    segment: Segment
    start: datetime
    end: datetime
    remaining: int
    is_done: bool
    is_active: bool
    is_pending: bool

    @property
    def progress(self) -> float:
        """Porcentaje transcurrido (0 a 100)."""
        if self.segment.duration <= 0:
            return 0.0
        return (self.segment.duration - self.remaining) / self.segment.duration * 100

    # Accesos directos a los datos de la sección.
    @property
    def id(self) -> str:
        return self.segment.id

    @property
    def label(self) -> str:
        return self.segment.label

    @property
    def detail(self) -> str:
        return self.segment.detail

    @property
    def duration(self) -> int:
        return self.segment.duration

    @property
    def color(self) -> str:
        return self.segment.color

    @property
    def text(self) -> str:
        return self.segment.text

    @property
    def kind(self) -> str:
        return self.segment.kind

    @property
    def is_chain(self) -> bool:
        return self.segment.is_chain


def top_of_hour(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0)


def start_at(now: datetime, hour: int, minute: int) -> datetime:
    """La hora `hour:minute` del día de `now`."""
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def build_schedule(segments: Sequence[Segment], program_start: datetime, now: datetime) -> list[ScheduledSegment]:
    """Ubica cada sección en el tiempo, una tras otra, desde `program_start`."""
    result: list[ScheduledSegment] = []
    cursor = program_start
    for segment in segments:
        start = cursor
        end = start + timedelta(seconds=segment.duration)
        cursor = end
        # Tiempo que le queda a la propia sección: su duración completa mientras espera su turno,
        # lo que falte para su fin mientras está activa y cero cuando terminó.
        remaining = min(segment.duration, max(0, math.floor((end - now).total_seconds())))
        result.append(ScheduledSegment(
            segment=segment,
            start=start,
            end=end,
            remaining=remaining,
            is_done=now >= end,
            is_active=start <= now < end,
            is_pending=now < start,
        ))
    return result


def find_active(schedule: Sequence[ScheduledSegment]) -> ScheduledSegment | None:
    for item in schedule:
        if item.is_active:
            return item
    return None


def next_after(schedule: Sequence[ScheduledSegment], active: ScheduledSegment | None) -> ScheduledSegment | None:
    if active is None:
        return None
    for index, item in enumerate(schedule):
        if item.id == active.id:
            return schedule[index + 1] if index + 1 < len(schedule) else None
    return None


def schedule_status(schedule: Sequence[ScheduledSegment]) -> str:
    """'empty', 'pending' (aún no inicia), 'done' (todo terminó) o 'running'."""
    if not schedule:
        return "empty"
    if all(item.is_done for item in schedule):
        return "done"
    if all(item.is_pending for item in schedule):
        return "pending"
    return "running"


def chain_remaining(schedule: Sequence[ScheduledSegment]) -> int:
    """Tiempo que falta de las secciones en cadena (las independientes no se suman)."""
    return sum(item.remaining for item in schedule if item.is_chain)


def chain_duration(segments: Sequence[Segment]) -> int:
    return sum(segment.duration for segment in segments if segment.is_chain)


@dataclass(frozen=True)
class ClockReading:
    """Lo que muestra el reloj central: segundos, avance del anillo (0 a 100) y si es una sección independiente."""

    seconds: int
    progress: float
    separate: bool


def clock_reading(schedule: Sequence[ScheduledSegment]) -> ClockReading:
    """El reloj central muestra el tiempo en cadena: no se reinicia al pasar de una sección en cadena a la
    siguiente. Mientras corre una sección independiente (que no se suma a la cadena) muestra su propio contador."""
    active = find_active(schedule)
    if active is not None and not active.is_chain:
        return ClockReading(active.remaining, active.progress, True)
    total = sum(item.duration for item in schedule if item.is_chain)
    remaining = chain_remaining(schedule)
    progress = (total - remaining) / total * 100 if total else 0.0
    return ClockReading(remaining, progress, False)


def sequence_duration(segments: Sequence[Segment]) -> int:
    """Duración de toda la secuencia, en cadena e independientes (cada una espera su turno)."""
    return sum(segment.duration for segment in segments)


def cut_by_hour(segments: Sequence[Segment]) -> list[Segment]:
    """Secciones que no terminan antes de la siguiente hora en punto si la secuencia arranca a las HH:00."""
    cut = []
    elapsed = 0
    for segment in segments:
        elapsed += segment.duration
        if elapsed > HOUR_SECONDS:
            cut.append(segment)
    return cut


def with_minutes(segment: Segment, minutes: object) -> Segment:
    return replace(segment, duration=clamp_int(minutes, 1, MAX_SEGMENT_MINUTES) * 60)


def is_flashing(remaining: int, alert_enabled: bool = True) -> bool:
    return alert_enabled and 0 < remaining <= FLASH_WINDOW_SECONDS


def clamp_int(value: object, low: int, high: int) -> int:
    """Convierte `value` a entero dentro de [low, high]; si no es válido devuelve `low`."""
    try:
        number = int(math.floor(float(str(value).strip())))
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def new_id() -> str:
    return f"seg-{secrets.token_hex(4)}"


def clean_station(name: str) -> str:
    """Normaliza el nombre de la emisora (espacios, largo máximo) y nunca lo deja vacío."""
    clean = " ".join(str(name).split())[:MAX_STATION_LENGTH].strip()
    return clean or DEFAULT_STATION_FALLBACK


def new_segment(label: str, minutes: int, kind: str, index: int) -> Segment:
    """Crea una sección nueva con el siguiente color de la paleta."""
    clean_label = " ".join(label.split()).upper()[:MAX_LABEL_LENGTH].strip()
    if not clean_label:
        raise ValueError("La sección necesita un nombre")
    if kind not in KINDS:
        raise ValueError(f"Tipo desconocido: {kind}")
    minutes = clamp_int(minutes, 1, MAX_SEGMENT_MINUTES)
    color, text = PALETTE[index % len(PALETTE)]
    detail = "Sección en cadena" if kind == KIND_CHAIN else "Sección independiente"
    return Segment(new_id(), clean_label, detail, minutes * 60, color, text, kind)


# ------------------------------------------------------ parrilla semanal ---

DAY_MINUTES = 24 * 60


@dataclass(frozen=True)
class Program:
    """Un programa de la parrilla: un día de la semana y un horario (minutos desde la medianoche)."""

    id: str
    day: int     # 0 = lunes … 6 = domingo
    start: int   # minuto de inicio, 0 a 1439 (07:30 = 450)
    end: int     # minuto de fin (no incluido), 1 a 1440
    title: str

    @property
    def hours_label(self) -> str:
        return f"{format_minutes(self.start)}–{format_minutes(self.end)}"

    def contains(self, moment: datetime) -> bool:
        return moment.weekday() == self.day and self.start <= moment.hour * 60 + moment.minute < self.end

    def to_dict(self) -> dict:
        return {"id": self.id, "day": self.day, "start": format_minutes(self.start),
                "end": format_minutes(self.end), "title": self.title}

    @classmethod
    def from_dict(cls, data: object) -> "Program":
        if not isinstance(data, dict):
            raise ValueError(f"programa inválido: {data!r}")
        try:
            program = cls(
                id=str(data["id"]),
                day=int(data["day"]),
                start=_stored_minutes(data["start"]),
                end=_stored_minutes(data["end"]),
                title=clean_program_title(data["title"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"programa inválido: {data!r}") from exc
        if not (0 <= program.day <= 6 and 0 <= program.start < program.end <= DAY_MINUTES and program.title):
            raise ValueError(f"programa inválido: {data!r}")
        return program


def _stored_minutes(value: object) -> int:
    """'07:30' → 450. Un número suelto es una hora en punto (formato de la primera versión de la parrilla)."""
    if isinstance(value, bool):
        raise ValueError(value)
    if isinstance(value, int):
        return value * 60
    return parse_clock_minutes(str(value))


def parse_clock_minutes(text: str) -> int:
    """'HH:MM' o 'HH:MM:SS' → minutos desde la medianoche ('24:00' = 1440)."""
    parts = text.strip().split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"hora inválida: {text!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 24 and 0 <= minute <= 59) or (hour == 24 and minute):
        raise ValueError(f"hora inválida: {text!r}")
    return hour * 60 + minute


def format_minutes(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_hour(hour: int) -> str:
    return f"{hour:02d}:00"


def clean_program_title(title: object) -> str:
    return " ".join(str(title).split())[:MAX_PROGRAM_TITLE_LENGTH].strip()


def make_program(day: int, start: int, end: int, title: str) -> Program:
    """Programa con horario en minutos desde la medianoche."""
    clean_title = clean_program_title(title)
    if not clean_title:
        raise ValueError("El programa necesita un título")
    if not (0 <= start < end <= DAY_MINUTES):
        raise ValueError("La hora de fin debe ser posterior a la de inicio")
    return Program(f"prog-{secrets.token_hex(4)}", clamp_int(day, 0, 6), start, end, clean_title)


def new_program(day: object, start: object, end: object, title: str) -> Program:
    """Programa cargado a mano, en horas en punto."""
    start_hour = clamp_int(start, 0, 23)
    end_hour = clamp_int(end, 1, 24)
    if end_hour <= start_hour and clean_program_title(title):
        raise ValueError("La hora de fin debe ser posterior a la de inicio")
    return make_program(clamp_int(day, 0, 6), start_hour * 60, end_hour * 60, title)


def overlapping_program(programs: Sequence[Program], candidate: Program) -> Program | None:
    """El primer programa del mismo día cuyo horario se cruza con `candidate`."""
    for program in programs:
        if (program.id != candidate.id and program.day == candidate.day
                and program.start < candidate.end and candidate.start < program.end):
            return program
    return None


def programs_for_day(programs: Sequence[Program], day: int) -> list[Program]:
    return sorted((program for program in programs if program.day == day), key=lambda program: program.start)


def program_at(programs: Sequence[Program], moment: datetime) -> Program | None:
    for program in programs:
        if program.contains(moment):
            return program
    return None


def next_program(programs: Sequence[Program], moment: datetime) -> tuple[Program, datetime] | None:
    """El siguiente programa distinto al actual y la hora en que empieza (busca hasta una semana adelante)."""
    current = program_at(programs, moment)
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    for offset in range(8):
        day_start = midnight + timedelta(days=offset)
        for program in programs_for_day(programs, day_start.weekday()):
            begins = day_start + timedelta(minutes=program.start)
            if begins > moment and (current is None or program.id != current.id):
                return program, begins
    return None


def copy_day(programs: Sequence[Program], source_day: int, target_days: Sequence[int]) -> list[Program]:
    """Reemplaza los programas de `target_days` por una copia de los de `source_day`."""
    targets = {day for day in target_days if day != source_day}
    result = [program for program in programs if program.day not in targets]
    for day in sorted(targets):
        for program in programs_for_day(programs, source_day):
            result.append(Program(f"prog-{secrets.token_hex(4)}", day, program.start, program.end, program.title))
    return result


def format_relative_day(moment: datetime, now: datetime) -> str:
    """'Hoy', 'Mañana' o el nombre del día."""
    days = (moment.date() - now.date()).days
    if days == 0:
        return "Hoy"
    if days == 1:
        return "Mañana"
    return format_weekday_es(moment)


# ---------------------------------------------------------------- formato ---

def format_clock(seconds: int) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{secs:02d}"


def format_duration(seconds: int) -> str:
    hours, rest = divmod(max(0, int(seconds)), 3600)
    minutes = rest // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def format_time_of_day(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def format_time_with_seconds(moment: datetime) -> str:
    return moment.strftime("%H:%M:%S")


def format_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%H:%M:%S")


def format_iso_date(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d")


def format_log_stamp(moment: datetime) -> str:
    return moment.strftime("%d/%m · %H:%M:%S")


def utc_offset_label(moment: datetime) -> str:
    offset = moment.astimezone().utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "−"
    total_minutes = abs(total_minutes)
    return f"UTC{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def format_weekday_es(moment: datetime) -> str:
    return WEEKDAYS_ES[moment.weekday()]


def format_date_es(moment: datetime) -> str:
    return f"{moment.day} de {MONTHS_ES[moment.month - 1]}"
