"""Registro de actividad (historial) con exportación a CSV."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .model import format_iso_date, format_time_with_seconds

CSV_HEADER = ("fecha", "hora", "evento", "detalle", "origen")


@dataclass(frozen=True)
class LogEntry:
    at: datetime
    title: str
    detail: str
    source: str


class ActivityLog:
    """Lista de eventos, la más reciente primero, con un máximo de entradas."""

    def __init__(self, max_entries: int = 200, listener: Callable[[], None] | None = None):
        self.max_entries = max_entries
        self._entries: list[LogEntry] = []
        self._listener = listener

    @property
    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, title: str, detail: str, source: str = "Sistema", at: datetime | None = None) -> LogEntry:
        entry = LogEntry(at or datetime.now(), title, detail, source)
        self._entries.insert(0, entry)
        del self._entries[self.max_entries:]
        if self._listener:
            self._listener()
        return entry

    @staticmethod
    def suggested_filename(now: datetime) -> str:
        return f"historial-radio-timer-{format_iso_date(now)}.csv"

    def export_csv(self, path: Path | str) -> int:
        """Escribe el historial (del más antiguo al más reciente) y devuelve cuántas filas exportó.

        Se usa UTF-8 con BOM para que Excel reconozca acentos al abrirlo directamente.
        """
        rows = list(reversed(self._entries))
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
            writer.writerow(CSV_HEADER)
            for entry in rows:
                writer.writerow((
                    format_iso_date(entry.at),
                    format_time_with_seconds(entry.at),
                    entry.title,
                    entry.detail,
                    entry.source,
                ))
        return len(rows)
