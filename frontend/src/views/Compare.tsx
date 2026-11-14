import React from "react";
import type { Meta, RotationResult } from "../types";
import { CompareTable } from "../components/CompareTable";
import { RotationCard } from "../components/RotationCard";

interface CompareProps {
  rotations: RotationResult[];
  meta: Meta;
}

export const Compare: React.FC<CompareProps> = ({ rotations, meta }) => {
  const evalPeriod = meta.periods.eval ?? [2005, 2024];

  return (
    <div className="compare-view">
      <div className="view-header">
        <h2 className="page-title">Comparación de Alternativas de Rotación</h2>
        <p className="page-description">
          Evaluación objetiva y determinista de la rotación actual frente a alternativas optimizadas para resistir los cambios climáticos observados.
          Toda afirmación está respaldada por datos satelitales NASA POWER (MERRA-2 / CERES SYN1deg) y modelos biofísicos FAO-56.
        </p>
      </div>

      {/* Side-by-side comparison table */}
      <section className="compare-table-section">
        <CompareTable rotations={rotations} />
      </section>

      {/* Rotation cards with detailed claims, evidence chips, and 20-campaign evaluation strip */}
      <section className="rotation-cards-section">
        <div className="section-title-row">
          <h3 className="section-title">Fichas Agronómicas de Decisión</h3>
          <p className="section-subtitle">
            Haga clic en cualquier etiqueta de evidencia (🔍) para auditar los parámetros y fuentes de NASA POWER detrás de cada afirmación.
          </p>
        </div>

        <div className="rotation-cards-grid">
          {rotations.map((r) => (
            <RotationCard key={r.profile} rotation={r} evalPeriod={evalPeriod} />
          ))}
        </div>
      </section>
    </div>
  );
};
