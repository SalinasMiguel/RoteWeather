#!/usr/bin/env python3
"""Wrapper para ejecutar backend/scripts/precache_demo.py desde la raíz del repositorio."""

from pathlib import Path
import runpy
import subprocess
import sys

root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
backend_script = backend_dir / "scripts" / "precache_demo.py"
venv_python = backend_dir / ".venv" / "bin" / "python"

if not backend_script.exists():
    raise FileNotFoundError(
        f"No se encontró el script de backend en: {backend_script}"
    )

if __name__ == "__main__":
    if venv_python.exists() and sys.executable != str(venv_python.resolve()):
        result = subprocess.run(
            [str(venv_python), str(backend_script)] + sys.argv[1:]
        )
        sys.exit(result.returncode)
    else:
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        runpy.run_path(str(backend_script), run_name="__main__")
