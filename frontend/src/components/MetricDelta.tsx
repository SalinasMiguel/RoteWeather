import React from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
} from "recharts";
import type { ClimateMetric } from "../types";

interface MetricDeltaProps {
  metric: ClimateMetric;
  beforePeriod?: [number, number];
  recentPeriod?: [number, number];
}

export const MetricDelta: React.FC<MetricDeltaProps> = ({
  metric,
  beforePeriod = [1991, 2005],
  recentPeriod = [2010, 2024],
}) => {
  // Format series for Recharts
  const chartData = metric.series.map(([season, val]) => ({
    season,
    label: `${season}`,
    value: val !== null ? parseFloat(val.toFixed(1)) : null,
  }));

  const deltaFormatted =
    metric.delta > 0
      ? `+${metric.delta.toFixed(1)}`
      : metric.delta.toFixed(1);

  // Delta color classification: adverse trends vs favorable trends
  const isAdverse =
    metric.id === "hot_days" ||
    metric.id === "dry_spells" ||
    metric.id === "max_dry_spell" ||
    metric.id === "water_deficit"
      ? metric.delta > 0
      : metric.id === "rain_total" || metric.id === "season_length"
      ? metric.delta < 0
      : false;

  return (
    <div className={`metric-card card ${metric.significant ? "metric-significant" : "metric-not-significant"}`}>
      <div className="metric-header">
        <div className="metric-title-group">
          <h4 className="metric-title">{metric.label}</h4>
          <span className="metric-unit">({metric.unit || "adimensional"})</span>
        </div>
        <div className="metric-badge-container">
          {metric.significant ? (
            <span
              className="badge badge-success"
              title="Diferencia estadísticamente significativa evaluada mediante prueba Mann-Whitney U bilateral (p < 0.10)"
            >
              ✓ Cambio significativo (p = {metric.p_value !== null ? metric.p_value.toFixed(4) : "—"})
            </span>
          ) : (
            <span
              className="badge badge-neutral"
              title="No se detectó cambio estadísticamente significativo (p ≥ 0.10)"
            >
              No significativo (p = {metric.p_value !== null ? metric.p_value.toFixed(4) : "—"})
            </span>
          )}
        </div>
      </div>

      <div className="metric-values-row">
        <div className="metric-val-block">
          <span className="metric-val-label">
            Histórico ({beforePeriod[0]}–{beforePeriod[1]}):
          </span>
          <span className="metric-val-num">{metric.before.toFixed(1)} {metric.unit}</span>
        </div>

        <div className="metric-arrow">→</div>

        <div className="metric-val-block">
          <span className="metric-val-label">
            Reciente ({recentPeriod[0]}–{recentPeriod[1]}):
          </span>
          <span className="metric-val-num font-bold">{metric.recent.toFixed(1)} {metric.unit}</span>
        </div>

        <div className="metric-delta-block">
          <span className="metric-val-label">Variación (Δ):</span>
          <span
            className={`metric-delta-tag ${
              isAdverse ? "delta-adverse" : "delta-positive"
            }`}
          >
            {deltaFormatted} {metric.unit}
          </span>
        </div>
      </div>

      <div className="metric-chart-container">
        <ResponsiveContainer width="100%" height={110}>
          <LineChart data={chartData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
            <XAxis
              dataKey="season"
              tickLine={false}
              axisLine={{ stroke: "#cbd5e1" }}
              tick={{ fontSize: 10, fill: "#64748b" }}
              interval="preserveStartEnd"
            />
            <YAxis
              tickLine={false}
              axisLine={{ stroke: "#cbd5e1" }}
              tick={{ fontSize: 10, fill: "#64748b" }}
              domain={["auto", "auto"]}
            />
            <Tooltip
              formatter={(val: any) => [`${val} ${metric.unit}`, metric.label]}
              labelFormatter={(label) => `Campaña ${label}`}
              contentStyle={{
                backgroundColor: "rgba(15, 23, 42, 0.9)",
                borderColor: "#334155",
                borderRadius: "6px",
                color: "#f8fafc",
                fontSize: "12px",
              }}
            />
            <ReferenceLine y={metric.before} stroke="#94a3b8" strokeDasharray="3 3" />
            <ReferenceLine y={metric.recent} stroke="#0284c7" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#0f766e"
              strokeWidth={2}
              dot={{ r: 2, fill: "#0f766e" }}
              activeDot={{ r: 4 }}
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="metric-footer">
        <span className="source-cite">
          <strong>Fuente NASA:</strong> {metric.source.dataset} | <strong>Variables:</strong>{" "}
          {metric.source.parameters.join(", ")} | <strong>Período:</strong> {metric.source.period}
        </span>
      </div>
    </div>
  );
};
