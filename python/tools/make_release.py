"""Publica una versión de Radio Timer: crea el ZIP y actualiza el manifiesto `updates.json`.

Uso (desde la carpeta `python`):

    python tools/make_release.py --out "D:/actualizaciones" --titulo "Parrilla web" --nuevo "Sincronización de la parrilla desde la web" --arreglado "El reloj ya no se reinicia entre secciones en cadena"

(Todo en una línea: la continuación con ^ solo funciona en cmd, no en PowerShell.)

La carpeta `--out` queda lista para usarse como fuente de actualizaciones en la app
(Configuración → Versiones): puede subirse a una web o compartirse por red o USB.
La versión se toma de `radio_timer/__init__.py`; súbela antes de publicar.
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


def build_zip(out_dir: Path, version: str) -> Path:
    target = out_dir / f"radio-timer-{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for file, arcname in iter_files():
            archive.write(file, arcname)
    return target


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
    parser.add_argument("--titulo", default="", help="título corto de la versión")
    parser.add_argument("--fecha", default=date.today().isoformat(), help="fecha AAAA-MM-DD (hoy por defecto)")
    parser.add_argument("--nuevo", action="append", default=[], help="nota de función nueva (repetible)")
    parser.add_argument("--arreglado", action="append", default=[], help="nota de corrección (repetible)")
    parser.add_argument("--cambiado", action="append", default=[], help="nota de cambio (repetible)")
    parser.add_argument("--seguridad", action="append", default=[], help="nota de seguridad (repetible)")
    args = parser.parse_args(argv)

    version = read_version()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = build_zip(out_dir, version)
    body = zip_path.read_bytes()

    notes = {key: values for key, values in (
        ("nuevo", args.nuevo), ("arreglado", args.arreglado),
        ("cambiado", args.cambiado), ("seguridad", args.seguridad),
    ) if values}
    entry = {
        "version": version,
        "date": args.fecha,
        "title": args.titulo,
        "notes": notes,
        "file": zip_path.name,
        "sha256": hashlib.sha256(body).hexdigest(),
        "size": len(body),
    }
    manifest_path = update_manifest(out_dir, entry)
    print(f"v{version} publicada:")
    print(f"  {zip_path}  ({len(body) / 1024:.0f} KB)")
    print(f"  {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
