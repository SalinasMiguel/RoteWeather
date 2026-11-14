#!/usr/bin/env python3
"""Wrapper para ejecutar backend/scripts/fetch_fixture.py desde la raíz del repositorio."""

from pathlib import Path
import runpy
import sys

root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
backend_script = backend_dir / "scripts" / "fetch_fixture.py"

if not backend_script.exists():
    raise FileNotFoundError(f"No se encontró el script de backend en: {backend_script}")

# Añadir backend/ a sys.path
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    runpy.run_path(str(backend_script), run_name="__main__")
