import React, { useState } from "react";
import type { Claim, Evidence, RotationResult, SeasonOut } from "../types";

interface RotationCardProps {
  rotation: RotationResult;
  evalPeriod?: [number, number];
}

// Modal/Dialog for Evidence Inspection
interface EvidenceModalProps {
  evidence: Evidence | null;
  onClose: () => void;
}

const EvidenceModal: React.FC<EvidenceModalProps> = ({ evidence, onClose }) => {
  if (!evidence) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h4 className="modal-title">🛰️ Evidencia Científica Detallada</h4>
          <button type="button" className="btn-close" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="modal-body">
          <div className="evidence-detail-row">
            <span className="detail-label">Indicador observado:</span>
            <span className="detail-value font-bold">{evidence.label}</span>
          </div>
          <div className="evidence-detail-row">
            <span className="detail-label">Valor exacto calculado:</span>
            <span className="detail-value font-bold text-primary">
              {evidence.value} {evidence.unit}
            </span>
          </div>
          <hr className="modal-divider" />
          <div className="evidence-detail-row">
            <span className="detail-label">Fuente satelital / Reanálisis:</span>
            <span className="detail-value">{evidence.source.dataset}</span>
          </div>
          <div className="evidence-detail-row">
            <span className="detail-label">Parámetros NASA analizados:</span>
            <span className="detail-value">
              <code>{evidence.source.parameters.join(", ")}</code>
            </span>
          </div>
          <div className="evidence-detail-row">
            <span className="detail-label">Período temporal evaluado:</span>
            <span className="detail-value">{evidence.source.period}</span>
          </div>
          {evidence.source.citation && (
            <div className="evidence-detail-row">
              <span className="detail-label">Cita metodológica:</span>
              <span className="detail-value text-muted">{evidence.source.citation}</span>
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
};

// 20-Campaign Evaluation Strip Component (T5.6)
interface EvaluationStripProps {
  seasons: SeasonOut[];
  evalPeriod?: [number, number];
}

export const EvaluationStrip: React.FC<EvaluationStripProps> = ({
  seasons,
  evalPeriod = [2005, 2024],
}) => {
  // Filter seasons in evalPeriod (e.g. 2005 to 2024, exactly 20 seasons)
  const evalSeasons = seasons.filter(
    (s) => s.season >= evalPeriod[0] && s.season <= evalPeriod[1]
  );

  const [activeSeason, setActiveSeason] = useState<SeasonOut | null>(null);

  const badCount = evalSeasons.filter((s) => s.bad).length;

  return (
    <div className="evaluation-strip-component">
      <div className="strip-header">
        <span className="strip-title">
          Tira de Evaluación: 20 Campañas ({evalPeriod[0]}/{String(evalPeriod[0] + 1).slice(-2)} a {evalPeriod[1]}/{String(evalPeriod[1] + 1).slice(-2)})
        </span>
        <span
          className={`badge ${
            badCount === 0 ? "badge-success" : badCount <= 2 ? "badge-warning" : "badge-danger"
          }`}
        >
          {badCount} {badCount === 1 ? "campaña mala" : "campañas malas"} de {evalSeasons.length}
        </span>
      </div>

      <div className="strip-blocks-container">
        {evalSeasons.map((s) => {
          const isBad = s.bad;
          return (
            <div
              key={s.season}
              className={`strip-block ${isBad ? "block-bad" : "block-normal"}`}
              onMouseEnter={() => setActiveSeason(s)}
              onMouseLeave={() => setActiveSeason(null)}
              onClick={() => setActiveSeason(s)}
              title={`${s.label}: ${isBad ? "MALA" : "Normal"} | Rendimiento: ${(s.index * 100).toFixed(0)}% | Factor: ${s.limiting}`}
            >
              <span className="block-year-label">{String(s.season).slice(-2)}</span>
            </div>
          );
        })}
      </div>

      {activeSeason && (
        <div className="strip-tooltip-detail">
          <div className="tooltip-line">
            <strong>Campaña {activeSeason.label}:</strong>{" "}
            <span className={activeSeason.bad ? "text-danger font-bold" : "text-success font-bold"}>
              {activeSeason.bad ? "MALA (pérdida > 40% del potencial)" : "Campaña favorable / normal"}
            </span>
          </div>
          <div className="tooltip-metrics-row">
            <span>
              <strong>Índice I:</strong> {(activeSeason.index * 100).toFixed(0)}%
            </span>
            <span>
              <strong>Productividad P:</strong> {activeSeason.productivity.toFixed(2)}
            </span>
            <span>
              <strong>Factor limitante:</strong>{" "}
              <span className="badge badge-outline">{activeSeason.limiting}</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export const RotationCard: React.FC<RotationCardProps> = ({
  rotation,
  evalPeriod = [2005, 2024],
}) => {
  const { card, metrics, seasons } = rotation;
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);

  const isCurrent = rotation.profile === "actual";

  return (
    <div
      className={`rotation-card card ${
        isCurrent
          ? "card-profile-actual"
          : card.improves_on_current
          ? "card-profile-improves"
          : "card-profile-alt"
      }`}
    >
      <div className="card-header">
        <div>
          <div className="badge-row">
            <span
              className={`badge ${
                isCurrent
                  ? "badge-neutral"
                  : rotation.profile === "adaptada"
                  ? "badge-info"
                  : rotation.profile === "regenerativa"
                  ? "badge-success"
                  : "badge-purple"
              }`}
            >
              {isCurrent
                ? "Rotación Actual"
                : rotation.profile === "adaptada"
                ? "Alternativa Adaptada"
                : rotation.profile === "regenerativa"
                ? "Alternativa Regenerativa"
                : "Alternativa Diversificada"}
            </span>

            {card.improves_on_current && (
              <span className="badge badge-success">✓ Supera a la actual</span>
            )}

            {card.relaxed_constraints && card.relaxed_constraints.length > 0 && (
              <span className="badge badge-warning" title={card.relaxed_constraints.join("; ")}>
                Restricciones relajadas ({card.relaxed_constraints.length})
              </span>
            )}
          </div>

          <h3 className="rotation-card-title">{card.title}</h3>
        </div>

        <div className="header-score-pill">
          <div className="score-val">
            {metrics.productivity_vs_current.toFixed(1)}%
          </div>
          <div className="score-desc">Productividad vs Actual</div>
        </div>
      </div>

      {/* 20-Campaign Evaluation Strip */}
      <div className="card-strip-section">
        <EvaluationStrip seasons={seasons} evalPeriod={evalPeriod} />
      </div>

      {/* Changes vs Current */}
      {card.changes_vs_current && card.changes_vs_current.length > 0 && (
        <div className="changes-section">
          <h4 className="subheading">Cambios respecto a la rotación actual:</h4>
          <ul className="changes-list">
            {card.changes_vs_current.map((ch, idx) => (
              <li key={idx} className="change-item">
                <span className="change-bullet">•</span> {ch}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Why Section */}
      <div className="claims-section">
        <h4 className="subheading text-primary">Por qué se sugiere:</h4>
        <div className="claims-list">
          {card.why.map((claim: Claim, idx: number) => (
            <div key={`why-${idx}`} className="claim-box">
              <p className="claim-text">{claim.text}</p>
              <div className="evidence-chips-row">
                {claim.evidence.map((ev, evIdx) => (
                  <button
                    key={`ev-why-${evIdx}`}
                    type="button"
                    className="evidence-chip"
                    onClick={() => setSelectedEvidence(ev)}
                    title={`Ver fuente NASA para ${ev.label}`}
                  >
                    🔍 {ev.label}: <strong>{ev.value} {ev.unit}</strong>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Benefits Section */}
      <div className="claims-section">
        <h4 className="subheading text-success">Beneficios esperados:</h4>
        <div className="claims-list">
          {card.benefits.map((claim: Claim, idx: number) => (
            <div key={`benefit-${idx}`} className="claim-box benefit-box">
              <p className="claim-text">{claim.text}</p>
              <div className="evidence-chips-row">
                {claim.evidence.map((ev, evIdx) => (
                  <button
                    key={`ev-ben-${evIdx}`}
                    type="button"
                    className="evidence-chip"
                    onClick={() => setSelectedEvidence(ev)}
                    title={`Ver fuente NASA para ${ev.label}`}
                  >
                    🔍 {ev.label}: <strong>{ev.value} {ev.unit}</strong>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Risks Section */}
      <div className="claims-section">
        <h4 className="subheading text-warning">Riesgos y límites operativos:</h4>
        <div className="claims-list">
          {card.risks.map((claim: Claim, idx: number) => (
            <div key={`risk-${idx}`} className="claim-box risk-box">
              <p className="claim-text">{claim.text}</p>
              <div className="evidence-chips-row">
                {claim.evidence.map((ev, evIdx) => (
                  <button
                    key={`ev-risk-${evIdx}`}
                    type="button"
                    className="evidence-chip"
                    onClick={() => setSelectedEvidence(ev)}
                    title={`Ver fuente NASA para ${ev.label}`}
                  >
                    🔍 {ev.label}: <strong>{ev.value} {ev.unit}</strong>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Modal for Evidence inspection */}
      <EvidenceModal
        evidence={selectedEvidence}
        onClose={() => setSelectedEvidence(null)}
      />
    </div>
  );
};
