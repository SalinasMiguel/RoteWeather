import React, { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import type { Climatology, Meta, RotationResult, SlotOut } from "../types";

interface CalendarChartProps {
  climatology: {
    before: Climatology;
    recent: Climatology;
  };
  rotations: RotationResult[];
  meta: Meta;
}

// Helper to generate fortnight labels according to ag_year_start
const MONTH_NAMES_ES = [
  "Ene", "Feb", "Mar", "Abr", "May", "Jun",
  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
];

function getFortnightLabels(agYearStart: string): { label: string; offsetDays: number }[] {
  const isSouth = agYearStart === "07-01";
  const startMonthIndex = isSouth ? 6 : 0; // 6 = July (0-indexed)

  const fortnights: { label: string; offsetDays: number }[] = [];
  for (let i = 0; i < 24; i++) {
    const monthOffset = Math.floor(i / 2);
    const isSecondFortnight = i % 2 === 1;
    const monthIdx = (startMonthIndex + monthOffset) % 12;
    const dayStr = isSecondFortnight ? "16" : "1";
    const label = `${MONTH_NAMES_ES[monthIdx]} ${dayStr}`;
    // Approximate non-leap day offset
    const offsetDays = Math.round((i * 365) / 24);
    fortnights.push({ label, offsetDays });
  }
  return fortnights;
}

// 365-day circular interval split algorithm
export interface IntervalSegment {
  startOffset: number; // 0..365
  endOffset: number;   // 0..365
  part: "start_year" | "wrapped_next_year";
}

export function splitCircularInterval(start: number, end: number): IntervalSegment[] {
  if (end <= 365) {
    return [{ startOffset: start, endOffset: end, part: "start_year" }];
  } else if (start >= 365) {
    return [{ startOffset: start - 365, endOffset: end - 365, part: "wrapped_next_year" }];
  } else {
    // Interval crosses the 365-day campaign boundary
    return [
      { startOffset: start, endOffset: 365, part: "start_year" },
      { startOffset: 0, endOffset: end - 365, part: "wrapped_next_year" },
    ];
  }
}

export const CalendarChart: React.FC<CalendarChartProps> = ({
  climatology,
  rotations,
  meta,
}) => {
  const fortnightLabels = getFortnightLabels(meta.ag_year_start);
  const [selectedSlot, setSelectedSlot] = useState<SlotOut | null>(null);

  // Prepare data for the 24-fortnight weather ComposedChart
  const weatherChartData = fortnightLabels.map((fn, idx) => {
    const rain = climatology.recent.rain_mm[idx] ?? 0;
    const et0Recent = climatology.recent.et0_mm[idx] ?? 0;
    const et0Before = climatology.before.et0_mm[idx] ?? 0;
    const tmax = climatology.recent.tmax_c[idx] ?? 0;
    const tmin = climatology.recent.tmin_c[idx] ?? 0;

    return {
      name: fn.label,
      rain_mm: parseFloat(rain.toFixed(1)),
      et0_recent: parseFloat(et0Recent.toFixed(1)),
      et0_before: parseFloat(et0Before.toFixed(1)),
      tmax_c: parseFloat(tmax.toFixed(1)),
      tmin_c: parseFloat(tmin.toFixed(1)),
    };
  });

  return (
    <div className="calendar-chart-view card">
      <div className="card-header">
        <div>
          <h2 className="page-title">Calendario Agroclimático y Fenología de Cultivos</h2>
          <p className="page-description">
            Superposición de la climatología satelital de 24 quincenas (lluvia, evapotranspiración y temperatura)
            frente a los ciclos fenológicos de cada rotación. El período crítico de floración se resalta en rojo.
          </p>
        </div>
      </div>

      {/* Top Section: Climatology Chart */}
      <div className="weather-chart-section">
        <h4 className="chart-section-title">
          1. Oferta y Demanda Hídrica Reciente (2010–2024) vs Histórica (1991–2005)
        </h4>

        <div className="chart-container" style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <ComposedChart
              data={weatherChartData}
              margin={{ top: 20, right: 30, left: 10, bottom: 25 }}
            >
              <XAxis
                dataKey="name"
                interval={0}
                angle={-45}
                textAnchor="end"
                height={60}
                tick={{ fontSize: 11, fill: "#475569" }}
              />
              <YAxis
                yAxisId="left"
                orientation="left"
                stroke="#0284c7"
                label={{
                  value: "Lluvia y ET0 (mm/quincena)",
                  angle: -90,
                  position: "insideLeft",
                  style: { fill: "#0284c7", fontSize: 11 },
                }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                stroke="#e11d48"
                label={{
                  value: "Temperatura (°C)",
                  angle: 90,
                  position: "insideRight",
                  style: { fill: "#e11d48", fontSize: 11 },
                }}
              />
              <Tooltip
                formatter={(value: any, name: any) => {
                  if (name === "Lluvia reciente (mm)") return [`${value} mm`, name];
                  if (name === "ET0 reciente (mm)") return [`${value} mm`, name];
                  if (name === "ET0 histórica (mm)") return [`${value} mm`, name];
                  if (name === "Tmax reciente (°C)") return [`${value} °C`, name];
                  if (name === "Tmin reciente (°C)") return [`${value} °C`, name];
                  return [value, name];
                }}
                contentStyle={{
                  backgroundColor: "rgba(15, 23, 42, 0.95)",
                  borderColor: "#334155",
                  borderRadius: "8px",
                  color: "#f8fafc",
                }}
              />
              <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: 12 }} />

              {/* Rain Bars */}
              <Bar
                yAxisId="left"
                dataKey="rain_mm"
                name="Lluvia reciente (mm)"
                fill="#38bdf8"
                opacity={0.75}
                radius={[4, 4, 0, 0]}
              />

              {/* ET0 Recent Line */}
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="et0_recent"
                name="ET0 reciente (mm)"
                stroke="#d97706"
                strokeWidth={2.5}
                dot={false}
              />

              {/* ET0 Before Line (Faint dashed) */}
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="et0_before"
                name="ET0 histórica (mm)"
                stroke="#94a3b8"
                strokeWidth={1.8}
                strokeDasharray="4 4"
                dot={false}
              />

              {/* Temperature Lines */}
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="tmax_c"
                name="Tmax reciente (°C)"
                stroke="#e11d48"
                strokeWidth={2}
                dot={false}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="tmin_c"
                name="Tmin reciente (°C)"
                stroke="#3b82f6"
                strokeWidth={1.5}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bottom Section: Phenology Gantt Chart */}
      <div className="gantt-section" style={{ marginTop: "32px" }}>
        <div className="gantt-header-row">
          <h4 className="chart-section-title">
            2. Cronograma Fenológico por Rotación (Alineado a 365 días de Campaña)
          </h4>
          <div className="gantt-legend">
            <span className="gantt-legend-item">
              <span className="legend-color-box stage-ini" /> Inicial
            </span>
            <span className="gantt-legend-item">
              <span className="legend-color-box stage-dev" /> Desarrollo
            </span>
            <span className="gantt-legend-item">
              <span className="legend-color-box stage-mid" /> Mediados
            </span>
            <span className="gantt-legend-item">
              <span className="legend-color-box stage-late" /> Maduración
            </span>
            <span className="gantt-legend-item">
              <span className="legend-color-box stage-sens" /> Ventana Crítica (Floración)
            </span>
          </div>
        </div>

        {/* 24-fortnight timeline scale header */}
        <div className="gantt-timeline-scale">
          <div className="gantt-row-label-col" />
          <div className="gantt-timeline-track">
            {fortnightLabels.map((fn, idx) => (
              <div key={idx} className="scale-tick-col">
                <span className="scale-tick-label">{fn.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Gantt Rows for each rotation */}
        <div className="gantt-rows-wrapper">
          {rotations.map((r) => {
            const isCurrent = r.profile === "actual";

            return (
              <div key={r.profile} className="gantt-rotation-block">
                <div className="gantt-profile-heading">
                  <span className={`badge ${isCurrent ? "badge-neutral" : "badge-success"}`}>
                    {isCurrent ? "Rotación Actual" : r.card.title}
                  </span>
                  <span className="profile-yield-tag">
                    Rendimiento relativo medio: {(r.metrics.mean_index * 100).toFixed(0)}%
                  </span>
                </div>

                {r.slots.map((yearSlots, yIdx) => (
                  <div key={`y-${yIdx}`} className="gantt-year-row">
                    <div className="gantt-row-label-col">
                      <span className="year-label-text">
                        {r.slots.length > 1 ? `Año ${yIdx + 1}` : "Anual"}
                      </span>
                    </div>

                    <div className="gantt-timeline-track track-canvas">
                      {/* Grid guidelines for 24 fortnights */}
                      {fortnightLabels.map((_, idx) => (
                        <div key={idx} className="track-grid-line" />
                      ))}

                      {/* Render slots */}
                      {yearSlots.map((slot, sIdx) => {
                        const sowOffset = slot.sow_offset;
                        const [iniEnd, devEnd, midEnd, lateEnd] = slot.stage_ends;
                        const [sensStart, sensEnd] = slot.sens_window;

                        // Calculate stage intervals
                        const stage1Segs = splitCircularInterval(sowOffset, iniEnd);
                        const stage2Segs = splitCircularInterval(iniEnd, devEnd);
                        const stage3Segs = splitCircularInterval(devEnd, midEnd);
                        const stage4Segs = splitCircularInterval(midEnd, lateEnd);
                        const sensSegs = splitCircularInterval(sensStart, sensEnd);

                        return (
                          <React.Fragment key={`slot-${yIdx}-${sIdx}`}>
                            {/* Stage 1: Initial */}
                            {stage1Segs.map((seg, i) => (
                              <div
                                key={`st1-${i}`}
                                className="gantt-bar stage-ini"
                                style={{
                                  left: `${(seg.startOffset / 365) * 100}%`,
                                  width: `${((seg.endOffset - seg.startOffset) / 365) * 100}%`,
                                }}
                                onClick={() => setSelectedSlot(slot)}
                                title={`${slot.crop_name}: Etapa Inicial (${seg.startOffset}d a ${seg.endOffset}d)`}
                              />
                            ))}

                            {/* Stage 2: Development */}
                            {stage2Segs.map((seg, i) => (
                              <div
                                key={`st2-${i}`}
                                className="gantt-bar stage-dev"
                                style={{
                                  left: `${(seg.startOffset / 365) * 100}%`,
                                  width: `${((seg.endOffset - seg.startOffset) / 365) * 100}%`,
                                }}
                                onClick={() => setSelectedSlot(slot)}
                                title={`${slot.crop_name}: Desarrollo Vegetativo (${seg.startOffset}d a ${seg.endOffset}d)`}
                              />
                            ))}

                            {/* Stage 3: Mid-season */}
                            {stage3Segs.map((seg, i) => (
                              <div
                                key={`st3-${i}`}
                                className="gantt-bar stage-mid"
                                style={{
                                  left: `${(seg.startOffset / 365) * 100}%`,
                                  width: `${((seg.endOffset - seg.startOffset) / 365) * 100}%`,
                                }}
                                onClick={() => setSelectedSlot(slot)}
                                title={`${slot.crop_name}: Mediados / Llenado (${seg.startOffset}d a ${seg.endOffset}d)`}
                              />
                            ))}

                            {/* Stage 4: Late / Ripening */}
                            {stage4Segs.map((seg, i) => (
                              <div
                                key={`st4-${i}`}
                                className="gantt-bar stage-late"
                                style={{
                                  left: `${(seg.startOffset / 365) * 100}%`,
                                  width: `${((seg.endOffset - seg.startOffset) / 365) * 100}%`,
                                }}
                                onClick={() => setSelectedSlot(slot)}
                                title={`${slot.crop_name}: Maduración / Cosecha (${seg.startOffset}d a ${seg.endOffset}d)`}
                              />
                            ))}

                            {/* Sensitive Window Overlay */}
                            {sensSegs.map((seg, i) => (
                              <div
                                key={`sens-${i}`}
                                className="gantt-bar stage-sens-overlay"
                                style={{
                                  left: `${(seg.startOffset / 365) * 100}%`,
                                  width: `${((seg.endOffset - seg.startOffset) / 365) * 100}%`,
                                }}
                                onClick={() => setSelectedSlot(slot)}
                                title={`⚠️ ${slot.crop_name}: Ventana Crítica de Floración (${seg.startOffset}d a ${seg.endOffset}d)`}
                              />
                            ))}

                            {/* Text label on main segment */}
                            {stage1Segs[0] && (
                              <div
                                className="gantt-slot-label"
                                style={{
                                  left: `${(stage1Segs[0].startOffset / 365) * 100}%`,
                                }}
                              >
                                {slot.crop_name} (siembra: {slot.sow_date})
                              </div>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        {selectedSlot && (
          <div className="slot-detail-modal" onClick={() => setSelectedSlot(null)}>
            <div className="slot-detail-box" onClick={(e) => e.stopPropagation()}>
              <div className="slot-detail-header">
                <h4>Detalle del Cultivo: {selectedSlot.crop_name}</h4>
                <button type="button" className="btn-close" onClick={() => setSelectedSlot(null)}>
                  ✕
                </button>
              </div>
              <div className="slot-detail-body">
                <p>
                  <strong>Familia botánica:</strong> {selectedSlot.family}
                </p>
                <p>
                  <strong>Fecha de siembra:</strong> {selectedSlot.sow_date} (Día relativo {selectedSlot.sow_offset})
                </p>
                <p>
                  <strong>Duración total del ciclo:</strong> {selectedSlot.stage_ends[3] - selectedSlot.sow_offset} días
                </p>
                <p>
                  <strong>Ventana crítica de estrés:</strong> Día {selectedSlot.sens_window[0]} a {selectedSlot.sens_window[1]}
                </p>
                <p>
                  <strong>Rendimiento relativo medio:</strong> {(selectedSlot.mean_yield * 100).toFixed(1)}%
                </p>
                <p>
                  <strong>Campañas con falla biológica severa:</strong> {selectedSlot.failures} de 20
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
