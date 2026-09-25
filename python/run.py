"""Arranque directo sin instalar nada: `python run.py [opciones]`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from radio_timer.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
