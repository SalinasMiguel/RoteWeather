import React from "react";
import type { ClimateMetric, Meta } from "../types";
import { MetricDelta } from "../components/MetricDelta";

interface ClimateShiftProps {
  metrics: ClimateMetric[];
  meta: Meta;
}

export const ClimateShift: React.FC<ClimateShiftProps> = ({ metrics, meta }) => {
  const beforePeriod = meta.periods.before ?? [1991, 2005];
  const recentPeriod = meta.periods.recent ?? [2010, 2024];

  // Group metrics into 3 logical categories
  const rainMetricIds = ["rain_total", "rain_q1", "rain_q2", "rain_q3", "rain_q4"];
  const seasonalityMetricIds = ["onset", "cessation", "season_length", "dry_spells", "max_dry_spell"];
  const thermalMetricIds = ["hot_days", "gdd", "et0_total", "water_deficit"];

  const rainMetrics = metrics.filter((m) => rainMetricIds.includes(m.id));
  const seasonalityMetrics = metrics.filter((m) => seasonalityMetricIds.includes(m.id));
  const thermalMetrics = metrics.filter((m) => thermalMetricIds.includes(m.id));
  const otherMetrics = metrics.filter(
    (m) =>
      !rainMetricIds.includes(m.id) &&
      !seasonalityMetricIds.includes(m.id) &&
      !thermalMetricIds.includes(m.id)
  );

  const significantCount = metrics.filter((m) => m.significant).length;

  return (
    <div className="climate-shift-view">
      <div className="view-header">
        <div className="title-row">
          <h2 className="page-title">Tu Clima Cambió: Evidencia Satelital NASA</h2>
          <span className="summary-pill">
            {significantCount} de {metrics.length} métricas con cambio significativo (p &lt; 0.10)
          </span>
        </div>
        <p className="page-description">
          Comparación estadística rigurosa entre el período histórico de referencia (
          <strong>{beforePeriod[0]}–{beforePeriod[1]}</strong>, 15 campañas) y el período reciente (
          <strong>{recentPeriod[0]}–{recentPeriod[1]}</strong>, 15 campañas) obtenida de las misiones satelitales
          y reanálisis de NASA POWER (MERRA-2 y CERES SYN1deg).
        </p>
        <div className="resolution-banner">
          <span className="res-icon">🛰️</span>
          <span>
            <strong>Nota de resolución espacial:</strong> {meta.resolution_note}
          </span>
        </div>
      </div>

      {/* Panel 1: Lluvia y Distribución */}
      <section className="metrics-panel">
        <div className="panel-header">
          <h3 className="panel-title">💧 Lluvia Anual y Distribución Trimestral</h3>
          <p className="panel-subtitle">
            Análisis de acumulación total y comportamiento pluviométrico por trimestres agrícolas (Q1 a Q4).
          </p>
        </div>
        <div className="metrics-grid">
          {rainMetrics.map((m) => (
            <MetricDelta
              key={m.id}
              metric={m}
              beforePeriod={beforePeriod}
              recentPeriod={recentPeriod}
            />
          ))}
        </div>
      </section>

      {/* Panel 2: Estacionalidad y Sequías */}
      <section className="metrics-panel">
        <div className="panel-header">
          <h3 className="panel-title">⏳ Estacionalidad, Fechas de Inicio y Racha Seca</h3>
          <p className="panel-subtitle">
            Desplazamiento del inicio y cese de lluvias, duración de la ventana húmeda y frecuencia de veranillos.
          </p>
        </div>
        <div className="metrics-grid">
          {seasonalityMetrics.map((m) => (
            <MetricDelta
              key={m.id}
              metric={m}
              beforePeriod={beforePeriod}
              recentPeriod={recentPeriod}
            />
          ))}
        </div>
      </section>

      {/* Panel 3: Estrés Térmico y Demanda Atmosférica */}
      <section className="metrics-panel">
        <div className="panel-header">
          <h3 className="panel-title">🌡️ Estrés Térmico, Grados Día y Déficit Hídrico</h3>
          <p className="panel-subtitle">
            Días con temperaturas críticas superiores a 35 °C, evapotranspiración de referencia (ET0) y balance oferta/demanda.
          </p>
        </div>
        <div className="metrics-grid">
          {thermalMetrics.map((m) => (
            <MetricDelta
              key={m.id}
              metric={m}
              beforePeriod={beforePeriod}
              recentPeriod={recentPeriod}
            />
          ))}
        </div>
      </section>

      {otherMetrics.length > 0 && (
        <section className="metrics-panel">
          <div className="panel-header">
            <h3 className="panel-title">Otras Variables Agroclimáticas</h3>
          </div>
          <div className="metrics-grid">
            {otherMetrics.map((m) => (
              <MetricDelta
                key={m.id}
                metric={m}
                beforePeriod={beforePeriod}
                recentPeriod={recentPeriod}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
};
