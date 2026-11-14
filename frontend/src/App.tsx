import React, { useState, useEffect, useCallback } from "react";
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  CropSummary,
  Rotation,
  SoilTexture,
  SowDate,
} from "./types";
import { fetchCrops, analyzeRotation, loadDemoSantaCruz, ApiError } from "./api";
import { MapForm } from "./views/MapForm";
import { ClimateShift } from "./views/ClimateShift";
import { Compare } from "./views/Compare";
import { CalendarChart } from "./components/CalendarChart";

const SANTA_CRUZ_DEFAULT: {
  lat: number;
  lon: number;
  soil: SoilTexture;
  rotation: Rotation;
} = {
  lat: -17.3,
  lon: -62.25,
  soil: "franco",
  rotation: {
    years: [
      {
        slots: [
          { crop_id: "soya", sow_date: "11-16" as SowDate },
          { crop_id: "soya", sow_date: "05-01" as SowDate },
        ],
      },
    ],
  },
};

type TabType = "map" | "climate" | "compare" | "calendar";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>("compare");
  const [crops, setCrops] = useState<CropSummary[]>([]);
  const [lat, setLat] = useState<number>(SANTA_CRUZ_DEFAULT.lat);
  const [lon, setLon] = useState<number>(SANTA_CRUZ_DEFAULT.lon);
  const [soilTexture, setSoilTexture] = useState<SoilTexture>(SANTA_CRUZ_DEFAULT.soil);
  const [currentRotation, setCurrentRotation] = useState<Rotation>(SANTA_CRUZ_DEFAULT.rotation);
  const [includeDiversified, setIncludeDiversified] = useState<boolean>(false);

  const [analyzeData, setAnalyzeData] = useState<AnalyzeResponse | null>(null);
  const [isOffline, setIsOffline] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [showAssumptions, setShowAssumptions] = useState<boolean>(false);

  // Load crop catalog and initial demo data on mount
  useEffect(() => {
    let isMounted = true;
    async function init() {
      const loadedCrops = await fetchCrops();
      if (!isMounted) return;
      setCrops(loadedCrops);

      try {
        const demo = await loadDemoSantaCruz();
        if (!isMounted) return;
        setAnalyzeData(demo);
        setIsOffline(true);
      } catch (err) {
        console.warn("No se pudo precargar demo inicial:", err);
      }
    }
    init();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleLoadDemo = useCallback(async () => {
    setLat(SANTA_CRUZ_DEFAULT.lat);
    setLon(SANTA_CRUZ_DEFAULT.lon);
    setSoilTexture(SANTA_CRUZ_DEFAULT.soil);
    setCurrentRotation(SANTA_CRUZ_DEFAULT.rotation);
    setValidationError(null);
    try {
      setLoading(true);
      const demo = await loadDemoSantaCruz();
      setAnalyzeData(demo);
      setIsOffline(true);
    } catch (err: any) {
      console.error("Error al cargar demo:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleAnalyze = useCallback(async () => {
    setLoading(true);
    setValidationError(null);

    const requestPayload: AnalyzeRequest = {
      lat,
      lon,
      soil_texture: soilTexture,
      current_rotation: currentRotation,
      include_diversified: includeDiversified,
    };

    try {
      const result = await analyzeRotation(requestPayload);
      setAnalyzeData(result.data);
      setIsOffline(result.offline);
      setActiveTab("compare");
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 422) {
        setValidationError(err.detail);
        setActiveTab("map");
      } else {
        const message = err instanceof Error ? err.message : String(err);
        setValidationError(
          `Error en la simulación: ${message}. Verifique la conectividad con el servidor.`
        );
        setActiveTab("map");
      }
    } finally {
      setLoading(false);
    }
  }, [lat, lon, soilTexture, currentRotation, includeDiversified]);

  return (
    <div className="app-container">
      {/* Loading Overlay */}
      {loading && (
        <div className="loading-modal-backdrop">
          <div className="loading-card">
            <div className="loading-spinner" />
            <h3 className="loading-title">Simulando con NASA POWER</h3>
            <p className="loading-text">
              Descargando y procesando ~34 campañas climáticas satelitales (MERRA-2 / CERES SYN1deg)
              y calculando balances hídricos diarios según FAO-56...
            </p>
            <span className="loading-note">
              ⏱️ La primera consulta puede demorar ~20 segundos en calcular el clima regional.
            </span>
          </div>
        </div>
      )}

      {/* Top Banner: Offline / Demo mode warning */}
      {isOffline && (
        <div className="offline-alert-banner">
          <div className="alert-content-inner">
            <span className="banner-icon">ℹ️</span>
            <span>
              <strong>Modo demo offline (Santa Cruz, Bolivia):</strong> Mostrando análisis precacheado
              para lat: -17.30, lon: -62.25 con 34 campañas satelitales de NASA POWER.
            </span>
          </div>
        </div>
      )}

      {/* App Header */}
      <header className="app-header">
        <div className="header-brand">
          <div className="header-logo-badge">🌱</div>
          <div>
            <h1 className="brand-title">RotaClima</h1>
            <span className="brand-subtitle">
              Soporte de decisión agronómica ante cambio climático • NASA Space Apps
            </span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="header-nav">
          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "map" ? "active" : ""}`}
            onClick={() => setActiveTab("map")}
          >
            📍 Parcela y Rotación
          </button>
          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "climate" ? "active" : ""}`}
            onClick={() => setActiveTab("climate")}
            disabled={!analyzeData}
          >
            🌦️ Tu Clima Cambió
          </button>
          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "compare" ? "active" : ""}`}
            onClick={() => setActiveTab("compare")}
            disabled={!analyzeData}
          >
            ⚖️ Comparar Rotaciones
          </button>
          <button
            type="button"
            className={`nav-tab-btn ${activeTab === "calendar" ? "active" : ""}`}
            onClick={() => setActiveTab("calendar")}
            disabled={!analyzeData}
          >
            📅 Calendario Agroclimático
          </button>
        </nav>
      </header>

      {/* Main Content Area */}
      <main className="app-main-content">
        {activeTab === "map" && (
          <MapForm
            lat={lat}
            lon={lon}
            soilTexture={soilTexture}
            currentRotation={currentRotation}
            includeDiversified={includeDiversified}
            crops={crops}
            loading={loading}
            onLatChange={setLat}
            onLonChange={setLon}
            onSoilChange={setSoilTexture}
            onRotationChange={setCurrentRotation}
            onIncludeDiversifiedChange={setIncludeDiversified}
            onLoadDemo={handleLoadDemo}
            onSubmit={handleAnalyze}
            validationError={validationError}
          />
        )}

        {activeTab === "climate" && analyzeData && (
          <ClimateShift metrics={analyzeData.climate} meta={analyzeData.meta} />
        )}

        {activeTab === "compare" && analyzeData && (
          <Compare rotations={analyzeData.rotations} meta={analyzeData.meta} />
        )}

        {activeTab === "calendar" && analyzeData && (
          <CalendarChart
            climatology={analyzeData.climatology}
            rotations={analyzeData.rotations}
            meta={analyzeData.meta}
          />
        )}
      </main>

      {/* Assumptions and Scientific Attribution Footer (T5.6) */}
      <footer className="app-footer">
        <div className="footer-top-row">
          <div className="footer-attribution">
            <span>
              <strong>Datos satelitales y climáticos:</strong> NASA Langley Research Center POWER Project
              (MERRA-2 / CERES SYN1deg) • Modelos biofísicos basados en FAO Irrigation and Drainage Paper 56 (Allen et al., 1998)
              y USDA SCS-CN (1972).
            </span>
          </div>
          <button
            type="button"
            className="btn btn-outline btn-sm btn-assumptions"
            onClick={() => setShowAssumptions(!showAssumptions)}
          >
            {showAssumptions ? "Ocultar supuestos metodológicos (S1–S12)" : "Ver supuestos metodológicos (S1–S12)"}
          </button>
        </div>

        {showAssumptions && analyzeData && (
          <div className="assumptions-panel card">
            <h4 className="assumptions-title">
              📋 Supuestos Metodológicos y Alcance Biofísico del Modelo (PLAN §4.10):
            </h4>
            <ol className="assumptions-list">
              {analyzeData.meta.assumptions.map((assumption, idx) => (
                <li key={idx} className="assumption-item">
                  <strong>S{idx + 1}:</strong> {assumption}
                </li>
              ))}
            </ol>
          </div>
        )}
      </footer>
    </div>
  );
};

export default App;
