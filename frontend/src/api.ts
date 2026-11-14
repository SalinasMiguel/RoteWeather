/**
 * RotaClima API Client — T5.1
 * Communicates with backend endpoints (/analyze, /crops, /health)
 * with robust offline fallback to /demo_santa_cruz.json and strict
 * propagation of HTTP 422 Spanish agronomic validation errors.
 */

import type {
  AnalyzeRequest,
  AnalyzeResponse,
  CropSummary,
} from "./types";

// Base URL configuration (VITE_API_URL or relative proxy)
const API_BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/+$/, "")
  : "";

export interface AnalyzeResult {
  data: AnalyzeResponse;
  offline: boolean;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * 13 canonical crops static fallback when backend is unreachable offline.
 */
export const STATIC_CROPS: CropSummary[] = [
  { id: "soya", nombre: "Soya", familia: "Fabaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "maiz", nombre: "Maíz", familia: "Poaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "sorgo", nombre: "Sorgo", familia: "Poaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "trigo", nombre: "Trigo", familia: "Poaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "girasol", nombre: "Girasol", familia: "Asteraceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "frijol", nombre: "Frijol", familia: "Fabaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "mani", nombre: "Maní", familia: "Fabaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "algodon", nombre: "Algodón", familia: "Malvaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "cebada", nombre: "Cebada", familia: "Poaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "papa", nombre: "Papa", familia: "Solanaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "mijo", nombre: "Mijo", familia: "Poaceae", cosechable: true, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "avena_cob", nombre: "Avena (cobertura)", familia: "Poaceae", cosechable: false, n_verificar_pendientes: 10, unverified_count: 10 },
  { id: "crotalaria", nombre: "Crotalaria", familia: "Fabaceae", cosechable: false, n_verificar_pendientes: 10, unverified_count: 10 },
];

/**
 * Fetches the crop catalog from GET /crops with fallback to STATIC_CROPS if offline.
 */
export async function fetchCrops(): Promise<CropSummary[]> {
  try {
    const res = await fetch(`${API_BASE}/crops`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      console.warn(`[RotaClima API] GET /crops respondió con HTTP ${res.status}. Usando catálogo estático.`);
      return STATIC_CROPS;
    }
    const data: CropSummary[] = await res.json();
    return data.map((c) => ({
      ...c,
      unverified_count: c.unverified_count ?? c.n_verificar_pendientes,
      n_verificar_pendientes: c.n_verificar_pendientes ?? c.unverified_count ?? 0,
    }));
  } catch (err) {
    console.warn("[RotaClima API] Error de red al consultar /crops. Usando catálogo estático.", err);
    return STATIC_CROPS;
  }
}

/**
 * Loads the precached Santa Cruz demo response from public/demo_santa_cruz.json.
 */
export async function loadDemoSantaCruz(): Promise<AnalyzeResponse> {
  const basePath = import.meta.env.BASE_URL || "/";
  const demoUrl = `${basePath.replace(/\/+$/, "")}/demo_santa_cruz.json`;
  const res = await fetch(demoUrl);
  if (!res.ok) {
    throw new Error(`No se pudo cargar el fixture demo (${demoUrl}): HTTP ${res.status}`);
  }
  return (await res.json()) as AnalyzeResponse;
}

/**
 * Analyzes a crop rotation against NASA POWER series.
 * 
 * Rules:
 * 1. Sends POST /analyze with properly structured AnalyzeRequest.
 * 2. If the backend responds with HTTP 422, extracts the Spanish detail message and THROWS ApiError (never falls back to demo).
 * 3. If a network failure occurs (backend offline, connection refused, failed to fetch), falls back to demo_santa_cruz.json with offline=true.
 */
export async function analyzeRotation(req: AnalyzeRequest): Promise<AnalyzeResult> {
  // Normalize payload ensuring current_rotation is set
  const payload: AnalyzeRequest = {
    lat: req.lat,
    lon: req.lon,
    soil_texture: req.soil_texture ?? "franco",
    current_rotation: req.current_rotation ?? req.rotation!,
    include_diversified: Boolean(req.include_diversified),
  };

  try {
    const res = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const data: AnalyzeResponse = await res.json();
      return { data, offline: false };
    }

    // Handle 422 Validation Error: MUST THROW, NEVER FALLBACK
    if (res.status === 422) {
      let detailMsg = "Error de validación en la rotación seleccionada.";
      try {
        const errorBody = await res.json();
        if (typeof errorBody.detail === "string") {
          detailMsg = errorBody.detail;
        } else if (Array.isArray(errorBody.detail)) {
          detailMsg = errorBody.detail
            .map((item: { msg?: string; message?: string }) => item.msg || item.message || JSON.stringify(item))
            .join("; ");
        }
      } catch {
        detailMsg = await res.text();
      }
      throw new ApiError(422, detailMsg);
    }

    // Handle 503 NASA POWER Unavailable
    if (res.status === 503) {
      let detailMsg = "El servicio NASA POWER no está disponible temporalmente.";
      try {
        const errorBody = await res.json();
        if (errorBody.detail) detailMsg = errorBody.detail;
      } catch {
        // use default detailMsg
      }
      console.warn(`[RotaClima API] Backend retornó HTTP 503 (${detailMsg}). Usando demo precacheada.`);
      const demoData = await loadDemoSantaCruz();
      return { data: demoData, offline: true };
    }

    // Other non-OK HTTP status (e.g. 500)
    const errText = await res.text();
    throw new ApiError(res.status, `Error del servidor (HTTP ${res.status}): ${errText}`);
  } catch (err: unknown) {
    // If it is already an ApiError (e.g. 422), propagate it immediately!
    if (err instanceof ApiError) {
      throw err;
    }

    // If it is a network error (TypeError: Failed to fetch, connection refused, etc.)
    console.warn("[RotaClima API] Conexión rechazada o red no disponible. Activando modo demo offline.", err);
    try {
      const demoData = await loadDemoSantaCruz();
      return { data: demoData, offline: true };
    } catch (fallbackErr) {
      const msg = fallbackErr instanceof Error ? fallbackErr.message : String(fallbackErr);
      throw new Error(`Modo offline falló: no se pudo cargar el demo precargado. (${msg})`);
    }
  }
}
