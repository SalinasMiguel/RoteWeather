"""PLAN §3 T4.5 — Generación offline del fixture precacheado para el demo Santa Cruz.

Genera frontend/public/demo_santa_cruz.json validado estrictamente contra AnalyzeResponse.
"""

from pathlib import Path
import json
import shutil
import sys
import time

# Asegurar backend en sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import DATA_END, DATA_START
from app.pipeline import analyze
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    Rotation,
    RotationYear,
    SlotIn,
)


def precache_demo() -> Path:
    root_dir = backend_dir.parent
    frontend_public = root_dir / "frontend" / "public"
    frontend_public.mkdir(parents=True, exist_ok=True)
    out_file = frontend_public / "demo_santa_cruz.json"

    # Asegurar que el caché local de POWER existe en backend/cache/power/
    # Usando el fixture tests/fixtures/power_demo.json si no existe aún
    cache_dir = backend_dir / "cache" / "power"
    cache_dir.mkdir(parents=True, exist_ok=True)
    lat, lon = -17.30, -62.25
    power_cache_file = (
        cache_dir / f"{lat:.2f}_{lon:.2f}_{DATA_START}_{DATA_END}.json"
    )

    if not power_cache_file.exists():
        fixture_file = backend_dir / "tests" / "fixtures" / "power_demo.json"
        if fixture_file.exists():
            shutil.copyfile(fixture_file, power_cache_file)
            print(f"Copiado fixture a caché de POWER: {power_cache_file}")

    req = AnalyzeRequest(
        lat=lat,
        lon=lon,
        soil_texture="franco",
        current_rotation=Rotation(
            years=[
                RotationYear(
                    slots=[
                        SlotIn(crop_id="soya", sow_date="11-16"),
                        SlotIn(crop_id="soya", sow_date="05-01"),
                    ]
                )
            ]
        ),
        include_diversified=False,
    )

    print(
        f"Ejecutando análisis offline para el punto demo Santa Cruz ({lat}, {lon})..."
    )
    start_time = time.perf_counter()
    response = analyze(req)
    elapsed = time.perf_counter() - start_time

    # Serializar JSON con formato legible
    json_str = response.model_dump_json(indent=2)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(json_str)

    # Validar que el archivo escrito vuelve a cargar y validar perfectamente contra AnalyzeResponse
    with open(out_file, "r", encoding="utf-8") as f:
        reloaded_data = json.load(f)
    validated = AnalyzeResponse.model_validate(reloaded_data)

    file_size_kb = out_file.stat().st_size / 1024.0
    profiles = [r.profile for r in validated.rotations]
    print(f"Precache completado exitosamente en {elapsed:.2f} s")
    print(f"Archivo generado: {out_file} ({file_size_kb:.1f} KB)")
    print(f"Perfiles incluidos: {profiles}")
    print(f"Campañas analizadas: {len(validated.meta.seasons)}")
    return out_file


if __name__ == "__main__":
    precache_demo()
