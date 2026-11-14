"""PLAN §1, §2.1, §2.4, §3 T4.4 — FastAPI entrypoint, exception handlers, CORS, and endpoints."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.data.crops import CropSummary, load_crops
from app.nasa.power import PowerUnavailable
from app.pipeline import RotationValidationError, analyze
from app.schemas import AnalyzeRequest, AnalyzeResponse

app = FastAPI(
    title="RotaClima API",
    description="Motor de soporte de decisión para rotación de cultivos (NASA Space Apps)",
    version="0.1.0",
)

# Configuración de CORS (§3 T4.4)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RotationValidationError)
async def rotation_validation_exception_handler(
    request: Request, exc: RotationValidationError
) -> JSONResponse:
    """PLAN §2.1 — Retorna HTTP 422 con mensaje descriptivo en español."""
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )


@app.exception_handler(PowerUnavailable)
async def power_unavailable_exception_handler(
    request: Request, exc: PowerUnavailable
) -> JSONResponse:
    """PLAN §2.3 — Retorna HTTP 503 si el servicio POWER no está disponible tras los reintentos."""
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Chequeo de estado del servicio."""
    return {"status": "ok"}


@app.get("/crops", response_model=list[CropSummary])
def get_crops() -> list[CropSummary]:
    """PLAN §2.4 — Catálogo resumido de cultivos con estado de verificación agronómica."""
    catalog = load_crops()
    return [
        CropSummary(
            id=c.id,
            nombre=c.nombre,
            familia=c.familia,
            cosechable=c.cosechable,
            n_verificar_pendientes=c.n_verificar_pendientes,
        )
        for c in catalog.values()
    ]


@app.post("/analyze", response_model=AnalyzeResponse)
def post_analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """PLAN §2.1, §2.2 — Análisis completo de rotación contra series NASA POWER."""
    return analyze(request)
