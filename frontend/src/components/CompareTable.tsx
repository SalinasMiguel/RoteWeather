import React from "react";
import type { RotationResult } from "../types";

interface CompareTableProps {
  rotations: RotationResult[];
}

export const CompareTable: React.FC<CompareTableProps> = ({ rotations }) => {
  return (
    <div className="compare-table-container card">
      <div className="card-header">
        <div>
          <h3 className="section-title">Matriz Comparativa de Rendimiento, Riesgo y Suelo</h3>
          <p className="section-subtitle">
            Evaluación simultánea contra la ventana climática de 20 campañas (2005/06 a 2024/25) y degradación de suelo.
          </p>
        </div>
      </div>

      <div className="table-responsive">
        <table className="compare-table">
          <thead>
            <tr>
              <th className="th-metric">Métrica / Criterio de Decisión</th>
              {rotations.map((r) => {
                const isCurrent = r.profile === "actual";
                return (
                  <th
                    key={r.profile}
                    className={`th-profile ${isCurrent ? "th-current" : ""}`}
                  >
                    <div className="profile-th-content">
                      <span className="profile-tag">
                        {isCurrent ? "Rotación Actual" : r.card.title}
                      </span>
                      <span className="profile-subtag">
                        {r.profile === "actual"
                          ? "Línea base declarada"
                          : r.profile === "adaptada"
                          ? "Mínimo cambio operativo"
                          : r.profile === "regenerativa"
                          ? "Prioridad salud de suelo"
                          : "Diversificación botánica"}
                      </span>
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {/* Row 1: Campañas Malas */}
            <tr>
              <td className="td-label">
                <strong>Campañas malas (evaluación de 20)</strong>
                <span className="td-hint">Pérdida &gt; 40% del potencial biológico en la campaña</span>
              </td>
              {rotations.map((r) => {
                const bad = r.metrics.bad_seasons;
                return (
                  <td key={r.profile} className="td-value font-bold">
                    <span
                      className={`badge ${
                        bad === 0 ? "badge-success" : bad <= 2 ? "badge-warning" : "badge-danger"
                      }`}
                    >
                      {bad} de {r.metrics.n_seasons}
                    </span>
                  </td>
                );
              })}
            </tr>

            {/* Row 2: Campañas malas histórico */}
            <tr>
              <td className="td-label">
                <strong>Evolución histórica de riesgo</strong>
                <span className="td-hint">Campañas malas: antes (1991–2005) → reciente (2010–2024)</span>
              </td>
              {rotations.map((r) => (
                <td key={r.profile} className="td-value">
                  {r.metrics.bad_before} de {r.metrics.n_period} (antes) →{" "}
                  <strong>{r.metrics.bad_recent} de {r.metrics.n_period}</strong> (reciente)
                </td>
              ))}
            </tr>

            {/* Row 3: Productividad vs actual */}
            <tr>
              <td className="td-label">
                <strong>Productividad acumulada vs Actual</strong>
                <span className="td-hint">Producción media anual en relación al 100% de la actual</span>
              </td>
              {rotations.map((r) => {
                const prod = r.metrics.productivity_vs_current;
                const isCurrent = r.profile === "actual";
                return (
                  <td key={r.profile} className="td-value font-bold">
                    {isCurrent ? (
                      <span className="text-muted">100.0% (Base)</span>
                    ) : (
                      <span
                        className={
                          prod >= 100 ? "text-success font-bold" : "text-amber font-bold"
                        }
                      >
                        {prod.toFixed(1)}% {prod > 100 ? "▲" : prod < 100 ? "▼" : ""}
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>

            {/* Row 4: Índice I */}
            <tr>
              <td className="td-label">
                <strong>Rendimiento relativo medio (Índice I)</strong>
                <span className="td-hint">Rendimiento medio relativo al potencial de cada cultivo (0 a 100%)</span>
              </td>
              {rotations.map((r) => (
                <td key={r.profile} className="td-value font-bold">
                  {(r.metrics.mean_index * 100).toFixed(0)}%
                </td>
              ))}
            </tr>

            {/* Row 5: Riesgo P10 */}
            <tr>
              <td className="td-label">
                <strong>Rendimiento en campaña adversa (P10)</strong>
                <span className="td-hint">Percentil 10: piso mínimo de rendimiento garantizado en 9 de cada 10 años</span>
              </td>
              {rotations.map((r) => (
                <td key={r.profile} className="td-value">
                  {(r.metrics.p10_index * 100).toFixed(0)}%
                </td>
              ))}
            </tr>

            {/* Section separator: Soil */}
            <tr className="tr-section-divider">
              <td colSpan={rotations.length + 1}>
                <strong>🌱 Salud y Sostenibilidad del Suelo (Modelo Agronómico FAO/USDA)</strong>
              </td>
            </tr>

            {/* Row 6: Suelo total */}
            <tr>
              <td className="td-label">
                <strong>Puntaje integral de suelo</strong>
                <span className="td-hint">Índice combinado ponderado de salud edáfica (0 a 100)</span>
              </td>
              {rotations.map((r) => {
                const score = r.metrics.soil.total;
                return (
                  <td key={r.profile} className="td-value font-bold">
                    <div className="soil-score-cell">
                      <span
                        className={`badge ${
                          score >= 70
                            ? "badge-success"
                            : score >= 50
                            ? "badge-warning"
                            : "badge-danger"
                        }`}
                      >
                        {score.toFixed(0)} / 100
                      </span>
                      <div className="progress-bar-bg">
                        <div
                          className="progress-bar-fill"
                          style={{
                            width: `${Math.min(100, Math.max(0, score))}%`,
                            backgroundColor:
                              score >= 70 ? "#059669" : score >= 50 ? "#d97706" : "#dc2626",
                          }}
                        />
                      </div>
                    </div>
                  </td>
                );
              })}
            </tr>

            {/* Row 7: Nitrógeno */}
            <tr>
              <td className="td-label indent">
                — Balance biológico de nitrógeno
                <span className="td-hint">Fijación simbiótica por leguminosas vs extracción</span>
              </td>
              {rotations.map((r) => (
                <td key={r.profile} className="td-value">
                  {r.metrics.soil.nitrogen.toFixed(0)} / 100
                </td>
              ))}
            </tr>

            {/* Row 8: Diversidad */}
            <tr>
              <td className="td-label indent">
                — Diversidad botánica
                <span className="td-hint">Alternancia de familias botánicas (corte de ciclos de plagas)</span>
              </td>
              {rotations.map((r) => (
                <td key={r.profile} className="td-value">
                  {r.metrics.soil.diversity.toFixed(0)} / 100
                </td>
              ))}
            </tr>

            {/* Row 9: Erosión */}
            <tr>
              <td className="td-label indent">
                — Protección contra erosión hídrica
                <span className="td-hint">Cobertura vegetal viva y rastrojo durante los meses lluviosos</span>
              </td>
              {rotations.map((r) => (
                <td key={r.profile} className="td-value">
                  {r.metrics.soil.erosion.toFixed(0)} / 100
                </td>
              ))}
            </tr>

            {/* Row 10: Materia orgánica */}
            <tr>
              <td className="td-label indent">
                — Aporte de rastrojo y biomasa
                <span className="td-hint">Mantenimiento de estructura y materia orgánica edáfica</span>
              </td>
              {rotations.map((r) => (
                <td key={r.profile} className="td-value">
                  {r.metrics.soil.organic_matter.toFixed(0)} / 100
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};
