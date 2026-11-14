"""PLAN §2.4 — Catálogo y cargador de cultivos."""

import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel

DEFAULT_CROPS_PATH = Path(__file__).resolve().parent / "crops.json"

ClaseN = Literal[
    "cobertura_leguminosa",
    "leguminosa_grano",
    "cobertura_no_leguminosa",
    "extractiva",
    "muy_extractiva",
]
ClaseRastrojo = Literal["bajo", "medio", "alto"]

REQUIRED_CROPS = {
    "soya",
    "maiz",
    "sorgo",
    "trigo",
    "girasol",
    "frijol",
    "mani",
    "algodon",
    "cebada",
    "papa",
    "mijo",
    "avena_cob",
    "crotalaria",
}

AGRONOMIC_FIELDS = [
    "etapas_dias",
    "kc",
    "zr_max_m",
    "p",
    "ky",
    "t_ecocrop",
    "t_calor",
    "t_helada",
    "clase_n",
    "clase_rastrojo",
]


class Crop(BaseModel):
    id: str
    nombre: str
    familia: str
    cosechable: bool
    value_weight: float
    etapas_dias: list[int]
    kc: list[float]
    zr_max_m: float
    p: float
    ky: float
    t_ecocrop: list[float]
    t_calor: list[float]
    t_helada: float
    clase_n: ClaseN
    clase_rastrojo: ClaseRastrojo
    n_verificar_pendientes: int

    @property
    def ciclo(self) -> int:
        return sum(self.etapas_dias)

    @property
    def L_ini(self) -> int:
        return self.etapas_dias[0]

    @property
    def L_dev(self) -> int:
        return self.etapas_dias[1]

    @property
    def L_mid(self) -> int:
        return self.etapas_dias[2]

    @property
    def L_late(self) -> int:
        return self.etapas_dias[3]

    @property
    def kc_ini(self) -> float:
        return self.kc[0]

    @property
    def kc_mid(self) -> float:
        return self.kc[1]

    @property
    def kc_end(self) -> float:
        return self.kc[2]


class CropSummary(BaseModel):
    id: str
    nombre: str
    familia: str
    cosechable: bool
    n_verificar_pendientes: int


def load_crops(path: Path | str | None = None) -> dict[str, Crop]:
    """Carga y valida el catálogo completo de 13 cultivos desde crops.json."""
    file_path = Path(path) if path else DEFAULT_CROPS_PATH
    if not file_path.exists():
        raise FileNotFoundError(f"Crops file not found at {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    missing = REQUIRED_CROPS - set(data.keys())
    if missing:
        raise ValueError(f"Missing required crop(s): {missing}")

    catalog: dict[str, Crop] = {}
    for cid, raw in data.items():
        # Validar campos de metadatos superiores
        for field in ["nombre", "familia", "cosechable", "value_weight"]:
            if field not in raw:
                raise ValueError(f"Crop '{cid}' missing top-level field '{field}'")

        # Validar campos agronómicos
        n_pendientes = 0
        unwrapped = {}
        for afield in AGRONOMIC_FIELDS:
            if afield not in raw:
                raise ValueError(f"Crop '{cid}' missing agronomic field '{afield}'")
            entry = raw[afield]
            if (
                not isinstance(entry, dict)
                or "valor" not in entry
                or "fuente" not in entry
                or "verificar" not in entry
            ):
                raise ValueError(
                    f"Crop '{cid}' field '{afield}' must have {{valor, fuente, verificar}}"
                )
            if not isinstance(entry["fuente"], str) or not entry["fuente"].strip():
                raise ValueError(f"Crop '{cid}' field '{afield}' has empty fuente")
            if not isinstance(entry["verificar"], bool):
                raise ValueError(f"Crop '{cid}' field '{afield}' verificar must be bool")
            if entry["verificar"]:
                n_pendientes += 1
            unwrapped[afield] = entry["valor"]

        # Validar etapas_dias (4 enteros positivos)
        etapas = unwrapped["etapas_dias"]
        if (
            not isinstance(etapas, list)
            or len(etapas) != 4
            or any(not isinstance(d, int) or d <= 0 for d in etapas)
        ):
            raise ValueError(f"Crop '{cid}' etapas_dias must be 4 positive integers")

        # Validar kc (3 valores, Kc_mid >= Kc_ini)
        kc = unwrapped["kc"]
        if not isinstance(kc, list) or len(kc) != 3:
            raise ValueError(f"Crop '{cid}' kc must have 3 float values")
        if kc[1] < kc[0]:
            raise ValueError(
                f"Crop '{cid}' Kc_mid ({kc[1]}) must be >= Kc_ini ({kc[0]})"
            )

        crop = Crop(
            id=cid,
            nombre=raw["nombre"],
            familia=raw["familia"],
            cosechable=raw["cosechable"],
            value_weight=float(raw["value_weight"]),
            etapas_dias=[int(x) for x in etapas],
            kc=[float(x) for x in kc],
            zr_max_m=float(unwrapped["zr_max_m"]),
            p=float(unwrapped["p"]),
            ky=float(unwrapped["ky"]),
            t_ecocrop=[float(x) for x in unwrapped["t_ecocrop"]],
            t_calor=[float(x) for x in unwrapped["t_calor"]],
            t_helada=float(unwrapped["t_helada"]),
            clase_n=unwrapped["clase_n"],
            clase_rastrojo=unwrapped["clase_rastrojo"],
            n_verificar_pendientes=n_pendientes,
        )
        catalog[cid] = crop

    return catalog


def get_crop(crop_id: str, catalog: dict[str, Crop] | None = None) -> Crop:
    """Obtiene un cultivo por su ID desde el catálogo."""
    cat = catalog if catalog is not None else load_crops()
    if crop_id not in cat:
        raise KeyError(f"Crop '{crop_id}' not found in catalog")
    return cat[crop_id]
