"""Publica una versión de Radio Timer: crea el ZIP y actualiza el manifiesto `updates.json`.

Uso (desde la carpeta `python`):

    python tools/make_release.py --out "D:/actualizaciones" --titulo "Parrilla web" --nuevo "Sincronización de la parrilla desde la web" --arreglado "El reloj ya no se reinicia entre secciones en cadena"

(Todo en una línea: la continuación con ^ solo funciona en cmd, no en PowerShell.)

Si no se pasan --titulo/--nuevo/..., el título y las notas se toman de la sección de esta versión
en `CHANGELOG.md` (raíz del repositorio). Así es como lo usa la GitHub Action que publica releases.

Además del ZIP y `updates.json`, deja en `--out`:
- `notas-v<versión>.md`: las notas en Markdown, para el texto del GitHub Release.
- `titulo-v<versión>.txt`: el título del GitHub Release.

La carpeta `--out` sirve como fuente de actualizaciones (Configuración → Versiones): puede subirse
a una web o compartirse por red o USB. La versión se toma de `radio_timer/__init__.py`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
from radio_timer.updates import (  # noqa: E402
    format_release_notes, is_prerelease_version, next_dev_version, parse_release_notes,
)

DEFAULT_CHANGELOG = APP_DIR.parent / "CHANGELOG.md"
# "## 3.4.0 — 2026-10-01 — Título", "## [3.4.0] - 2026-10-01", "## 3.4.0 (2026-10-01)", "## v3.4.0: Título"…
_SECTION = re.compile(
    r"^##\s+\[?v?(?P<version>\d[0-9A-Za-z._+-]*)\]?"
    r"(?:\s*(?:[-–—·|:]\s*)?\(?(?P<date>\d{4}-\d{1,2}-\d{1,2})\)?)?"
    r"(?:\s*[-–—·|:]\s*(?P<title>.+?))?\s*$"
)
MANIFEST_NAME = "updates.json"
# Lo que forma parte de la app instalada. tests/ y tools/ no viajan en las actualizaciones.
INCLUDE = ("radio_timer", "run.py", "Abrir Radio Timer.bat", "README.md")
EXCLUDE_DIRS = {"__pycache__"}


def read_version() -> str:
    source = (APP_DIR / "radio_timer" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', source)
    if match is None:
        raise SystemExit("No se encontró __version__ en radio_timer/__init__.py")
    return match.group(1)


def iter_files():
    for item in INCLUDE:
        path = APP_DIR / item
        if path.is_file():
            yield path, item
        elif path.is_dir():
            for file in sorted(path.rglob("*")):
                if file.is_file() and not (EXCLUDE_DIRS & set(file.relative_to(APP_DIR).parts)):
                    yield file, file.relative_to(APP_DIR).as_posix()


def changelog_section(path: Path, version: str) -> tuple[str, str, dict[str, list[str]]] | None:
    """(fecha, título, notas) de la sección `## <versión> — fecha — título` de CHANGELOG.md."""
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    header, body, in_fence = None, [], False
    for line in lines:
        fence = line.strip().startswith(("```", "~~~"))
        if header is None:
            # Los encabezados dentro de bloques de código (como la plantilla del archivo) no cuentan.
            if fence:
                in_fence = not in_fence
            elif not in_fence:
                match = _SECTION.match(line.strip())
                if match is not None and match.group("version") == version:
                    header = match
            continue
        if fence:
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            break
        body.append(line)
    if header is None:
        return None
    date_text = header.group("date") or ""
    if date_text:
        year, month, day = (int(part) for part in date_text.split("-"))
        date_text = f"{year:04d}-{month:02d}-{day:02d}"
    return date_text, (header.group("title") or "").strip(), parse_release_notes("\n".join(body))


def build_zip(out_dir: Path, version: str) -> Path:
    """ZIP de la app. Si `version` no es la del código (compilación de desarrollo), el
    `__version__` del paquete se reescribe: así la app instalada sabe qué compilación es."""
    target = out_dir / f"radio-timer-{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for file, arcname in iter_files():
            if arcname == "radio_timer/__init__.py" and version != read_version():
                source = file.read_text(encoding="utf-8")
                archive.writestr(arcname, re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', source))
            else:
                archive.write(file, arcname)
    return target


_COMMIT_PREFIX = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?!?:\s*", re.IGNORECASE)


def notes_from_commits(subjects: list[str]) -> dict[str, list[str]]:
    """Notas de una compilación de desarrollo a partir de los títulos de sus commits.

    Entiende prefijos convencionales (feat:, fix:, security:) y palabras en español al inicio
    («Agrega…», «Corrige…»); el resto va a «Cambiado». Los merges se omiten.
    """
    notes: dict[str, list[str]] = {}
    for raw in subjects:
        subject = " ".join(raw.split())
        if not subject or subject.lower().startswith(("merge ", "merge:")):
            continue
        prefix = _COMMIT_PREFIX.match(subject)
        kind = prefix.group("type").lower() if prefix else ""
        text = subject[prefix.end():] if prefix else subject
        first = text.split(" ")[0].lower()
        if kind in ("feat", "feature") or first.startswith(("agreg", "añad", "anad", "nuev", "implement", "crea", "add")):
            key = "nuevo"
        elif kind in ("fix", "bugfix", "hotfix") or first.startswith(("arregl", "corrig", "correg", "soluc", "fix")):
            key = "arreglado"
        elif kind in ("security", "sec") or first.startswith(("segur", "secur")):
            key = "seguridad"
        else:
            key = "cambiado"
        if text:
            notes.setdefault(key, []).append(text[:1].upper() + text[1:])
    return notes


def update_manifest(out_dir: Path, entry: dict) -> Path:
    manifest_path = out_dir / MANIFEST_NAME
    manifest = {"app": "radio-timer", "releases": []}
    if manifest_path.exists():
        try:
            # utf-8-sig: tolera el BOM que agregan PowerShell y algunos editores.
            loaded = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            raise SystemExit(f"{manifest_path} existe pero no es JSON válido ({exc}).\n"
                             "Corrígelo o quítalo a mano; no se sobrescribe para no perder el historial.")
        if not isinstance(loaded, dict) or not isinstance(loaded.get("releases"), list):
            raise SystemExit(f"{manifest_path} no tiene la forma esperada; corrígelo o quítalo a mano.")
        manifest = loaded
    manifest["releases"] = [entry] + [
        release for release in manifest["releases"]
        if isinstance(release, dict) and release.get("version") != entry["version"]
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera el ZIP de la versión actual y actualiza updates.json")
    parser.add_argument("--out", required=True, help="carpeta donde publicar (updates.json + ZIPs)")
    parser.add_argument("--titulo", default=None, help="título corto (por defecto, el del CHANGELOG)")
    parser.add_argument("--fecha", default=None, help="fecha AAAA-MM-DD (por defecto, la del CHANGELOG u hoy)")
    parser.add_argument("--nuevo", action="append", default=[], help="nota de función nueva (repetible)")
    parser.add_argument("--arreglado", action="append", default=[], help="nota de corrección (repetible)")
    parser.add_argument("--cambiado", action="append", default=[], help="nota de cambio (repetible)")
    parser.add_argument("--seguridad", action="append", default=[], help="nota de seguridad (repetible)")
    parser.add_argument("--changelog", default=str(DEFAULT_CHANGELOG),
                        help="CHANGELOG.md de donde tomar título y notas si no se pasan a mano")
    parser.add_argument("--exigir-changelog", action="store_true",
                        help="fallar si CHANGELOG.md no tiene la sección de la versión (versiones estables)")
    parser.add_argument("--dev", type=int, metavar="N",
                        help="compilación de desarrollo número N: versión siguiente con sufijo -dev.N")
    parser.add_argument("--commits", metavar="ARCHIVO",
                        help="títulos de commits (uno por línea) para las notas de una compilación de desarrollo")
    args = parser.parse_args(argv)

    version = read_version()
    notes = {key: values for key, values in (
        ("nuevo", args.nuevo), ("arreglado", args.arreglado),
        ("cambiado", args.cambiado), ("seguridad", args.seguridad),
    ) if values}
    if args.dev is not None:
        # Compilación de desarrollo: notas desde los commits, sin CHANGELOG.
        version = next_dev_version(version, args.dev)
        if not notes and args.commits:
            notes = notes_from_commits(Path(args.commits).read_text(encoding="utf-8").splitlines())
        title = args.titulo if args.titulo is not None else f"Desarrollo #{args.dev}"
        release_date = args.fecha or date.today().isoformat()
    else:
        # Lo que se pase a mano manda; lo que falte se completa con la sección del CHANGELOG.
        section = changelog_section(Path(args.changelog), version)
        if section is None and args.exigir_changelog:
            raise SystemExit(f"{args.changelog} no tiene la sección '## {version}'. "
                             "Escríbela antes de publicar esta versión.")
        changelog_date, changelog_title, changelog_notes = section or ("", "", {})
        if section is None and not notes:
            print(f"Aviso: {args.changelog} no tiene una sección '## {version}'; la versión sale sin notas.")
        notes = notes or changelog_notes
        title = args.titulo if args.titulo is not None else changelog_title
        release_date = args.fecha or changelog_date or date.today().isoformat()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = build_zip(out_dir, version)
    body = zip_path.read_bytes()
    (out_dir / f"notas-v{version}.md").write_text(format_release_notes(notes), encoding="utf-8")
    (out_dir / f"titulo-v{version}.txt").write_text(f"v{version}" + (f" · {title}" if title else ""),
                                                   encoding="utf-8")
    entry = {
        "version": version,
        "date": release_date,
        "title": title,
        "notes": notes,
        "file": zip_path.name,
        "sha256": hashlib.sha256(body).hexdigest(),
        "size": len(body),
        "prerelease": is_prerelease_version(version),
    }
    manifest_path = update_manifest(out_dir, entry)
    (out_dir / "version.txt").write_text(version, encoding="utf-8")   # para la Action
    print(f"v{version} publicada:")
    print(f"  {zip_path}  ({len(body) / 1024:.0f} KB)")
    print(f"  {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
