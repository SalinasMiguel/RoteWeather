#!/usr/bin/env python3
"""PLAN §1, §3 T1.3, §7 — Script de descarga del fixture demo de NASA POWER para Santa Cruz.

Descarga los datos agroclimáticos diarios del punto demo de Santa Cruz (-17.30, -62.25)
para el periodo 19910101 a 20251231 y los guarda en backend/tests/fixtures/power_demo.json.
Valida que contenga exactamente 12.784 días y 0 NaNs en prec, tmax y tmin.
"""

import json
from pathlib import Path
import sys

# Asegurar backend/ en sys.path para importaciones de app.*
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import DATA_END, DATA_START
from app.nasa.power import fetch_power, parse_power_response

# Coordenadas normativas del lote demo de Santa Cruz (PLAN §2.1, §7)
DEMO_LAT: float = -17.30
DEMO_LON: float = -62.25
EXPECTED_DAYS: int = 12784


def main() -> int:
    print(f"=== Descarga de fixture demo NASA POWER: Santa Cruz ({DEMO_LAT}, {DEMO_LON}) ===")
    print(f"Periodo: {DATA_START} a {DATA_END}")

    # 1. Obtener datos (usando fetch_power para aprovechar redondeo y caché)
    repo_root = backend_dir.parent
    cache_dir = backend_dir / "cache" / "power"
    fixtures_dir = backend_dir / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    target_fixture_path = fixtures_dir / "power_demo.json"

    print(f"Consultando NASA POWER API (timeout 60s)...")
    power_data = fetch_power(
        lat=DEMO_LAT,
        lon=DEMO_LON,
        start=DATA_START,
        end=DATA_END,
        cache_dir=cache_dir,
    )

    # 2. Copiar/Guardar raw JSON en target_fixture_path
    raw_cache_file = cache_dir / f"{DEMO_LAT:.2f}_{DEMO_LON:.2f}_{DATA_START}_{DATA_END}.json"
    if raw_cache_file.exists():
        with open(raw_cache_file, "r", encoding="utf-8") as f_in:
            raw_json = json.load(f_in)
    else:
        raise FileNotFoundError(f"No se encontró el archivo de caché generado: {raw_cache_file}")

    with open(target_fixture_path, "w", encoding="utf-8") as f_out:
        json.dump(raw_json, f_out, indent=2)

    print(f"Fixture guardado en: {target_fixture_path} ({target_fixture_path.stat().st_size:,} bytes)")

    # 3. Validación de invariantes duras (PLAN §3 T1.3, ORIGINAL_REQUEST.md R3)
    df = power_data.df
    total_days = len(df)
    nan_prec = int(df["prec"].isna().sum())
    nan_tmax = int(df["tmax"].isna().sum())
    nan_tmin = int(df["tmin"].isna().sum())

    print(f"\n--- Verificación de Invariantes ---")
    print(f"Días totales en serie: {total_days} (esperados: {EXPECTED_DAYS})")
    print(f"NaNs en 'prec': {nan_prec} (esperados: 0)")
    print(f"NaNs en 'tmax': {nan_tmax} (esperados: 0)")
    print(f"NaNs en 'tmin': {nan_tmin} (esperados: 0)")
    print(f"Elevación extraída: {power_data.elevation_m} m")
    print(f"Versión de API: {power_data.api_version}")

    if total_days != EXPECTED_DAYS:
        print(f"ERROR: Se esperaban {EXPECTED_DAYS} días, pero se obtuvieron {total_days}.", file=sys.stderr)
        return 1

    if nan_prec != 0 or nan_tmax != 0 or nan_tmin != 0:
        print(
            f"ERROR: Invariante violada: existen NaNs en variables críticas (prec={nan_prec}, tmax={nan_tmax}, tmin={nan_tmin}).",
            file=sys.stderr,
        )
        return 1

    print("\n[OK] Validación exitosa: 12,784 días y 0 NaNs en prec, tmax, tmin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
