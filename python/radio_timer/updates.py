"""Gestor de versiones: manifiesto de versiones, descarga verificada e instalación sin reinstalar.

La app se distribuye como carpeta de código fuente, así que "instalar" una versión es reemplazar
esos archivos por los del paquete ZIP de la versión elegida y reiniciar. El diseño completo está
documentado en `gestor-de-versiones.md` (raíz del proyecto), pensado para reutilizarse en otras apps.

Fuente de actualizaciones: una dirección configurable que apunta a un `updates.json` (el manifiesto)
acompañado de los ZIP de cada versión. Puede ser una URL `https://` (el `http://` sin cifrar se
rechaza: quien controle la red podría inyectar código) o una carpeta local o de red (por ejemplo
una memoria USB o una carpeta compartida de la emisora).

Este módulo no depende de Tkinter.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__

MANIFEST_NAME = "updates.json"
TIMEOUT_SECONDS = 30
APP_FOLDER = "RadioTimer"
MANIFEST_MAX_BYTES = 2 * 1024 * 1024        # un índice de versiones jamás pesa más que esto
PACKAGE_MAX_BYTES = 200 * 1024 * 1024       # tope absoluto para el ZIP de una versión

# Cadencia de comprobación automática. "manual" = solo con el botón.
CHECK_MODES = ("manual", "daily", "weekly")
CHECK_MODE_NAMES = {"manual": "Manual", "daily": "Cada día", "weekly": "Cada semana"}
CHECK_INTERVAL_DAYS = {"daily": 1, "weekly": 7}

# Categorías de las notas de versión, en el orden en que se muestran.
NOTE_KINDS = (
    ("nuevo", "Nuevo"),
    ("arreglado", "Arreglado"),
    ("cambiado", "Cambiado"),
    ("seguridad", "Seguridad"),
)

_VERSION_IN_SOURCE = re.compile(r'__version__\s*=\s*"([^"]+)"')
_SAFE_VERSION = re.compile(r"^[0-9A-Za-z._+-]+$")  # apta para nombres de archivo y carpeta


class UpdateError(Exception):
    """Error con un mensaje apto para mostrar al operador."""


# ------------------------------------------------------------- versiones ---

def parse_version(text: str) -> tuple[int, ...]:
    """'3.2.0' → (3, 2, 0). Ignora sufijos no numéricos ('3.2.1-beta' → (3, 2, 1))."""
    numbers = []
    for part in str(text).strip().split("."):
        match = re.match(r"\d+", part)
        if match is None:
            break
        numbers.append(int(match.group()))
    return tuple(numbers)


def compare_versions(a: str, b: str) -> int:
    """Negativo si a < b, 0 si son iguales, positivo si a > b."""
    va, vb = parse_version(a), parse_version(b)
    length = max(len(va), len(vb))
    va += (0,) * (length - len(va))
    vb += (0,) * (length - len(vb))
    return (va > vb) - (va < vb)


# ------------------------------------------------------------ manifiesto ---

@dataclass(frozen=True)
class Release:
    """Una versión publicada en el manifiesto."""

    version: str
    date: str          # "2026-09-26"
    title: str
    notes: dict[str, list[str]] = field(default_factory=dict)  # nuevo / arreglado / cambiado / seguridad
    file: str = ""     # nombre del ZIP, relativo al manifiesto (o URL absoluta)
    sha256: str = ""
    size: int = 0

    def notes_lines(self) -> list[tuple[str, str]]:
        """[('Nuevo', 'texto'), ('Arreglado', 'texto'), ...] en orden de presentación."""
        lines = []
        for key, label in NOTE_KINDS:
            for text in self.notes.get(key, []):
                lines.append((label, text))
        return lines

    def is_newer_than(self, version: str) -> bool:
        return compare_versions(self.version, version) > 0


def parse_manifest(data: object) -> list[Release]:
    """Convierte el JSON del manifiesto en versiones, de la más nueva a la más vieja.

    Las entradas incompletas o rotas se ignoran para que una versión mal publicada
    no impida ver las demás.
    """
    if not isinstance(data, dict) or not isinstance(data.get("releases"), list):
        raise UpdateError("El manifiesto de versiones no tiene el formato esperado")
    releases: list[Release] = []
    for entry in data["releases"]:
        if not isinstance(entry, dict):
            continue
        version = str(entry.get("version", "")).strip()
        file = str(entry.get("file", "")).strip()
        sha256 = str(entry.get("sha256", "")).strip().lower()
        # La versión termina en nombres de archivo y carpeta: solo caracteres seguros.
        if (not parse_version(version) or _SAFE_VERSION.match(version) is None
                or not file or len(sha256) != 64):
            continue
        notes = {}
        raw_notes = entry.get("notes")
        if isinstance(raw_notes, dict):
            for key, _label in NOTE_KINDS:
                items = raw_notes.get(key)
                if isinstance(items, list):
                    cleaned = [" ".join(str(item).split()) for item in items if str(item).strip()]
                    if cleaned:
                        notes[key] = cleaned
        try:
            size = max(0, int(entry.get("size", 0)))
        except (TypeError, ValueError):
            size = 0
        releases.append(Release(
            version=version,
            date=str(entry.get("date", "")).strip(),
            title=" ".join(str(entry.get("title", "")).split()),
            notes=notes,
            file=file,
            sha256=sha256,
            size=size,
        ))
    releases.sort(key=lambda release: (parse_version(release.version), release.date), reverse=True)
    return releases


def first_newer(releases: list[Release], current: str = __version__) -> Release | None:
    """La versión más nueva del manifiesto que supere a `current` (la lista ya viene ordenada)."""
    for release in releases:
        if release.is_newer_than(current):
            return release
    return None


# -------------------------------------------------- descarga del manifiesto ---

def _is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def _manifest_location(source: str) -> str:
    """Normaliza la fuente: si apunta a una carpeta, el manifiesto es `updates.json` dentro de ella."""
    source = source.strip().strip('"')
    if not source:
        raise UpdateError("Configura la dirección de actualizaciones")
    if source.lower().startswith("http://"):
        # Por http cualquiera en la red podría reemplazar manifiesto y paquete (el hash viaja
        # por el mismo canal). Como el paquete es código que se ejecutará, se exige cifrado.
        raise UpdateError("Por seguridad la fuente debe ser https:// o una carpeta local o de red")
    if _is_url(source):
        return source if source.lower().endswith(".json") else source.rstrip("/") + "/" + MANIFEST_NAME
    path = Path(source)
    return str(path / MANIFEST_NAME if path.is_dir() or not source.lower().endswith(".json") else path)


def _read_source(location: str, timeout: float, limit: int) -> bytes:
    """Lee una URL https o un archivo local, con un tope de tamaño para no agotar la memoria."""
    if _is_url(location):
        # Deja intactos los % ya codificados y codifica espacios, acentos, etc.
        encoded = urllib.parse.quote(location, safe="%/:=&?~#+!$,;'@()*[]|")
        request = urllib.request.Request(encoded, headers={"User-Agent": f"RadioTimer/{__version__}"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                final = str(response.url or "")
                if not final.lower().startswith("https://"):
                    raise UpdateError("La descarga fue redirigida a una dirección sin cifrar")
                body = response.read(limit + 1)
        except UpdateError:
            raise
        except urllib.error.HTTPError as exc:
            raise UpdateError(f"La dirección respondió con error {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise UpdateError(f"No se pudo conectar: {getattr(exc, 'reason', exc)}") from exc
        if len(body) > limit:
            raise UpdateError("La descarga supera el tamaño máximo permitido")
        return body
    try:
        if os.path.getsize(location) > limit:
            raise UpdateError("El archivo supera el tamaño máximo permitido")
        return Path(location).read_bytes()
    except OSError as exc:
        raise UpdateError(f"No se pudo leer {location}") from exc


def fetch_manifest(source: str, timeout: float = TIMEOUT_SECONDS) -> object:
    """Descarga y devuelve el JSON del manifiesto desde una URL https o una carpeta local."""
    body = _read_source(_manifest_location(source), timeout, MANIFEST_MAX_BYTES)
    try:
        # utf-8-sig: tolera el BOM que agregan PowerShell y algunos editores de Windows.
        return json.loads(body.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise UpdateError("El manifiesto de versiones no es un JSON válido") from exc


def fetch_releases(source: str, timeout: float = TIMEOUT_SECONDS) -> list[Release]:
    return parse_manifest(fetch_manifest(source, timeout))


def _resolve_file(source: str, file: str) -> str:
    """Dirección completa del ZIP de una versión, relativa al manifiesto salvo que sea absoluta."""
    if _is_url(file):
        return file
    location = _manifest_location(source)
    if _is_url(location):
        return urllib.parse.urljoin(location, file)
    return str(Path(location).parent / file)


# ----------------------------------------------------- descarga del paquete ---

def download_release(release: Release, source: str, dest_dir: Path | str,
                     timeout: float = TIMEOUT_SECONDS) -> Path:
    """Descarga el ZIP de `release` y verifica su hash SHA-256 antes de darlo por bueno."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    limit = release.size if 0 < release.size <= PACKAGE_MAX_BYTES else PACKAGE_MAX_BYTES
    body = _read_source(_resolve_file(source, release.file), timeout, limit)
    if release.size and len(body) != release.size:
        raise UpdateError(f"El paquete de v{release.version} no tiene el tamaño esperado")
    digest = hashlib.sha256(body).hexdigest()
    if digest != release.sha256:
        raise UpdateError(f"El paquete de v{release.version} no pasó la verificación de integridad")
    target = dest_dir / f"radio-timer-{release.version}.zip"
    fd, temp_name = tempfile.mkstemp(prefix=".update-", suffix=".zip", dir=dest_dir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target


# ------------------------------------------------------------ instalación ---

def validate_zip(zip_path: Path | str) -> list[str]:
    """Revisa que el ZIP sea un paquete de la app y no escape de su carpeta al extraerse."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise UpdateError("El paquete descargado está dañado") from exc
    for name in names:
        clean = name.replace("\\", "/")
        if clean.startswith("/") or re.match(r"[A-Za-z]:", clean) or ".." in clean.split("/"):
            raise UpdateError(f"El paquete contiene una ruta insegura: {name}")
    if "radio_timer/__init__.py" not in {name.replace("\\", "/") for name in names}:
        raise UpdateError("El paquete no contiene la aplicación (falta radio_timer/__init__.py)")
    return names


def packaged_version(zip_path: Path | str) -> str:
    """La versión declarada dentro del ZIP (en radio_timer/__init__.py)."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            source = archive.read("radio_timer/__init__.py").decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise UpdateError("El paquete descargado está dañado") from exc
    match = _VERSION_IN_SOURCE.search(source)
    if match is None:
        raise UpdateError("El paquete no declara su versión")
    return match.group(1)


def install_release(zip_path: Path | str, app_dir: Path | str, backup_root: Path | str,
                    expect_version: str | None = None) -> list[str]:
    """Reemplaza los archivos de la app por los del ZIP; lo anterior queda en una copia de respaldo.

    Solo se tocan las entradas de primer nivel que trae el ZIP (p. ej. `radio_timer/`, `run.py`);
    cualquier otro archivo de la carpeta se conserva. Las carpetas se reemplazan completas, así los
    módulos eliminados en la versión nueva no quedan huérfanos.

    El intercambio se hace con renombres dentro de la misma carpeta (misma unidad de disco, así cada
    paso es atómico y no hay copias a medias): lo viejo se aparta a una carpeta temporal junto a la
    app, entra lo nuevo, y solo cuando la app quedó completa el respaldo se lleva a `backup_root`
    (que puede estar en otra unidad). Si un renombre falla (p. ej. un archivo bloqueado por el
    antivirus), se deshace lo hecho y la app queda como estaba; el respaldo nunca se restaura sobre
    una carpeta existente (eso podría anidarlo). Las preferencias no se tocan: viven en %APPDATA%,
    no junto al código.
    """
    names = validate_zip(zip_path)
    if expect_version is not None:
        found = packaged_version(zip_path)
        if compare_versions(found, expect_version) != 0 or found.strip() != expect_version.strip():
            raise UpdateError(f"El paquete dice ser v{found}, pero el manifiesto anuncia v{expect_version}")
    app_dir = Path(app_dir)
    if not app_dir.is_dir():
        raise UpdateError(f"No existe la carpeta de la aplicación: {app_dir}")
    top_level = sorted({name.replace("\\", "/").split("/")[0] for name in names if name.strip("/")})
    old_version = _installed_version(app_dir)

    staging = Path(tempfile.mkdtemp(prefix=".instalando-", dir=app_dir))
    parked = Path(tempfile.mkdtemp(prefix=".anterior-", dir=app_dir))
    steps: list[tuple[Path, Path | None, bool]] = []  # (destino, dónde quedó lo viejo, si entró lo nuevo)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging)
        for name in top_level:
            target = app_dir / name
            kept = None
            if target.exists() or target.is_symlink():
                kept = parked / name
                os.rename(target, kept)            # misma unidad: atómico, sin estados a medias
            steps.append((target, kept, False))
            os.rename(staging / name, target)
            steps[-1] = (target, kept, True)
    except BaseException as exc:
        problems = _undo_install(steps, staging)
        shutil.rmtree(staging, ignore_errors=True)
        message = str(exc) if isinstance(exc, UpdateError) else f"No se pudo instalar la versión: {exc}"
        if problems:
            message += f" ATENCIÓN: no se pudo restaurar {', '.join(problems)}; lo anterior está en {parked}"
        else:
            shutil.rmtree(parked, ignore_errors=True)
        raise UpdateError(message) from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    _store_backup(parked, Path(backup_root), old_version, app_dir)
    return top_level


def _undo_install(steps: list[tuple[Path, Path | None, bool]], staging: Path) -> list[str]:
    """Deshace un intercambio a medias. Devuelve los nombres que no se pudieron restaurar."""
    problems = []
    for target, kept, placed in reversed(steps):
        if placed:
            try:
                os.rename(target, staging / f"fallida-{target.name}")
            except OSError:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    try:
                        target.unlink()
                    except OSError:
                        pass
        if kept is None:
            continue
        if target.exists() or target.is_symlink():
            # Nunca mover el respaldo sobre algo existente: lo anidaría dentro.
            problems.append(target.name)
            continue
        try:
            os.rename(kept, target)
        except OSError:
            problems.append(target.name)
    return problems


def _store_backup(parked: Path, backup_root: Path, old_version: str, app_dir: Path) -> None:
    """Lleva lo reemplazado al respaldo en `backup_root`; la app ya quedó sana, esto es lo secundario.

    Si la copia a otra unidad falla, el respaldo se queda junto a la app con un nombre visible en
    vez de perderse.
    """
    if not any(parked.iterdir()):
        shutil.rmtree(parked, ignore_errors=True)
        return
    try:
        backup_dir = _unique_dir(backup_root, old_version)
        for entry in list(parked.iterdir()):
            shutil.move(str(entry), str(backup_dir / entry.name))
        shutil.rmtree(parked, ignore_errors=True)
    except OSError:
        fallback = app_dir / f"respaldo-v{old_version}"
        counter = 2
        while fallback.exists():
            fallback = app_dir / f"respaldo-v{old_version}-{counter}"
            counter += 1
        try:
            os.rename(parked, fallback)
        except OSError:
            pass  # queda la carpeta .anterior-*; peor es fallar la instalación ya terminada


def _installed_version(app_dir: Path) -> str:
    try:
        match = _VERSION_IN_SOURCE.search((app_dir / "radio_timer" / "__init__.py").read_text(encoding="utf-8"))
        return match.group(1) if match else "desconocida"
    except OSError:
        return "desconocida"


def _unique_dir(root: Path, base_name: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / f"v{base_name}"
    counter = 2
    while candidate.exists():
        candidate = root / f"v{base_name}-{counter}"
        counter += 1
    candidate.mkdir(parents=True)
    return candidate


# --------------------------------------------------- cadencia y utilidades ---

def should_check(last_check_iso: str, mode: str, now: datetime) -> bool:
    """Si toca comprobar actualizaciones según la cadencia elegida."""
    if mode not in CHECK_INTERVAL_DAYS:
        return False  # manual o modo desconocido
    if not last_check_iso:
        return True
    try:
        last = datetime.fromisoformat(last_check_iso)
        if last.tzinfo is not None:
            last = last.astimezone().replace(tzinfo=None)  # comparar con el reloj local de la app
        elapsed = now - last
    except (ValueError, TypeError, OSError):
        return True
    if elapsed < timedelta(0):
        return True  # fecha en el futuro (reloj que estuvo adelantado): tratarla como inválida
    return elapsed >= timedelta(days=CHECK_INTERVAL_DAYS[mode])


def app_directory() -> Path:
    """La carpeta que contiene la app (donde están `radio_timer/` y `run.py`)."""
    return Path(__file__).resolve().parent.parent


def _appdata_root() -> Path:
    base = os.environ.get("APPDATA")
    return (Path(base) if base else Path.home() / ".config") / APP_FOLDER


def default_updates_dir() -> Path:
    return _appdata_root() / "updates"


def default_backup_root() -> Path:
    return _appdata_root() / "backups"


def format_size(size: int) -> str:
    if size <= 0:
        return ""
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
