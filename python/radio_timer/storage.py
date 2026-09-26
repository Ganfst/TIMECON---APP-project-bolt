"""Preferencias persistentes (emisora, secciones, programas e interruptores) en un archivo JSON."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .model import Program, Segment, default_segments

APP_FOLDER = "RadioTimer"
FILE_NAME = "prefs.json"
DEFAULT_STATION = "Radio Luz 93.7 FM"


@dataclass
class Preferences:
    station: str = DEFAULT_STATION
    segments: list[Segment] = field(default_factory=default_segments)
    programs: list[Program] = field(default_factory=list)
    alert_enabled: bool = True
    sound_enabled: bool = False

    def to_dict(self) -> dict:
        return {
            "station": self.station,
            "segments": [segment.to_dict() for segment in self.segments],
            "programs": [program.to_dict() for program in self.programs],
            "alertEnabled": self.alert_enabled,
            "soundEnabled": self.sound_enabled,
        }

    @classmethod
    def from_dict(cls, data: object) -> "Preferences":
        """Construye preferencias a partir de JSON, ignorando cualquier campo inválido."""
        prefs = cls()
        if not isinstance(data, dict):
            return prefs
        station = data.get("station")
        if isinstance(station, str) and station.strip():
            prefs.station = station.strip()
        raw_segments = data.get("segments")
        if isinstance(raw_segments, list):
            try:
                prefs.segments = [Segment.from_dict(item) for item in raw_segments]
            except ValueError:
                pass  # se conservan las secciones por defecto
        raw_programs = data.get("programs")
        if isinstance(raw_programs, list):
            for item in raw_programs:
                try:
                    prefs.programs.append(Program.from_dict(item))
                except ValueError:
                    pass  # un programa dañado no borra el resto de la parrilla
        if isinstance(data.get("alertEnabled"), bool):
            prefs.alert_enabled = data["alertEnabled"]
        if isinstance(data.get("soundEnabled"), bool):
            prefs.sound_enabled = data["soundEnabled"]
        return prefs


def default_path() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return root / APP_FOLDER / FILE_NAME


def load_preferences(path: Path | str | None = None) -> Preferences:
    file = Path(path) if path else default_path()
    try:
        raw = file.read_text(encoding="utf-8")
    except OSError:
        return Preferences()
    try:
        data = json.loads(raw)
    except ValueError:
        return Preferences()
    return Preferences.from_dict(data)


def save_preferences(prefs: Preferences, path: Path | str | None = None) -> Path:
    """Escribe el archivo de forma atómica (archivo temporal + reemplazo)."""
    file = Path(path) if path else default_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(prefs.to_dict(), ensure_ascii=False, indent=2)
    fd, temp_name = tempfile.mkstemp(prefix=".prefs-", suffix=".tmp", dir=file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temp_name, file)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return file
