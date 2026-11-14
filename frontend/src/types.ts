/**
 * RotaClima Interface Contracts — Mirror of backend/app/schemas.py & PLAN §2.
 * Strictly typed for frontend/src/types.ts.
 */

// =============================================================================
// Agricultural Calendar & Sowing Dates
// =============================================================================

export type MonthStr =
  | "01"
  | "02"
  | "03"
  | "04"
  | "05"
  | "06"
  | "07"
  | "08"
  | "09"
  | "10"
  | "11"
  | "12";

export type FortnightDayStr = "01" | "16";

/**
 * Sowing date format "MM-DD", restricted to the 24 fortnights (days 01 or 16).
 */
export type SowDate = `${MonthStr}-${FortnightDayStr}`;

export const ALL_SOW_DATES: SowDate[] = [
  "01-01", "01-16", "02-01", "02-16", "03-01", "03-16",
  "04-01", "04-16", "05-01", "05-16", "06-01", "06-16",
  "07-01", "07-16", "08-01", "08-16", "09-01", "09-16",
  "10-01", "10-16", "11-01", "11-16", "12-01", "12-16",
];

// =============================================================================
// Crop Catalog
// =============================================================================

export interface CropSummary {
  id: string;
  nombre: string;
  familia: string;
  cosechable: boolean;
  n_verificar_pendientes: number;
  /** Alias for n_verificar_pendientes */
  unverified_count?: number;
}

// =============================================================================
// Request Contracts (§2.1)
// =============================================================================

export interface SlotIn {
  crop_id: string; // must exist in crops catalog
  sow_date: SowDate;
}

export interface RotationYear {
  slots: SlotIn[]; // 1..2 slots per year
}

export interface Rotation {
  years: RotationYear[]; // 1..3 years cycle
}

export type SoilTexture = "arenoso" | "franco" | "arcilloso";

export interface AnalyzeRequest {
  lat: number; // -60.0 .. 60.0
  lon: number; // -180.0 .. 180.0
  soil_texture: SoilTexture;
  current_rotation: Rotation;
  include_diversified?: boolean;
  /** Alias for current_rotation if passed */
  rotation?: Rotation;
}

// =============================================================================
// Evidence & Fact-Checking (§2.2)
// =============================================================================

export interface Source {
  dataset: string; // "NASA POWER (MERRA-2 / CERES SYN1deg)"
  parameters: string[]; // ["PRECTOTCORR", ...] exact POWER names
  period: string; // e.g. "campañas 2005/06–2024/25"
  citation?: string;
}

export interface Evidence {
  label: string; // e.g. "Campañas malas evaluadas"
  value: number | string;
  unit: string; // "de 20", "mm", "días", "%", etc.
  source: Source;
}

export interface Claim {
  text: string; // Every number in text exists in evidence[].value
  evidence: Evidence[];
}

export interface SoilScore {
  total: number; // 0..100
  nitrogen: number;
  diversity: number;
  erosion: number;
  organic_matter: number;
}

// =============================================================================
// Simulation Output Contracts (§2.2)
// =============================================================================

export interface SlotOut {
  crop_id: string;
  crop_name: string;
  family: string;
  harvested: boolean;
  sow_date: SowDate | string;
  sow_offset: number; // Days from ag year start (non-leap year)
  stage_ends: [number, number, number, number] | number[]; // Cumulative offsets: ini, dev, mid, late(harvest)
  sens_window: [number, number] | number[]; // Critical flowering window [start, end)
  prev_mode: "fallow" | "crop";
  mean_yield: number; // 0..1 relative yield
  failures: number; // Number of failed seasons (Y_rel < 0.3)

  // Convenience computed fields
  cycle_days?: number;
  harvest_date?: string;
  end_offset?: number;
  limiting_factor?: string;
  failure_fraction?: number;
}

export type LimitingFactor = "agua" | "calor" | "helada" | "temperatura" | "ninguno";

export interface SeasonOut {
  season: number; // Start year of season (e.g. 1991)
  label: string; // "1991/92" (S) or "1991" (N)
  index: number; // I_y (0..1)
  productivity: number; // P_y
  bad: boolean;
  limiting: LimitingFactor;
  p_y?: number; // Alias for productivity
  pot?: number;
}

export interface RotationMetrics {
  mean_index: number; // Mean index in eval window (0..1)
  p10_index: number; // 10th percentile index
  mean_productivity: number; // Mean productivity in eval
  productivity_vs_current: number; // 100 = equal to current
  bad_seasons: number; // Bad seasons count in eval (out of 20)
  n_seasons: number; // Evaluation seasons count (20)
  bad_before: number; // Bad seasons in before period (out of 15)
  bad_recent: number; // Bad seasons in recent period (out of 15)
  n_period: number; // Period seasons count (15)
  soil: SoilScore;
  failures?: number;
}

export type ProfileType = "actual" | "adaptada" | "regenerativa" | "diversificada";

export interface RotationCard {
  profile: ProfileType;
  title: string;
  why: Claim[];
  benefits: Claim[];
  risks: Claim[];
  changes_vs_current: string[];
  relaxed_constraints: string[];
  improves_on_current: boolean;
}

export interface RotationResult {
  profile: ProfileType | string;
  rotation: Rotation;
  slots: SlotOut[][]; // By rotation year
  metrics: RotationMetrics;
  seasons: SeasonOut[]; // All valid campaigns (~34)
  card: RotationCard;
}

// =============================================================================
// Climate & Agroclimatology (§2.2)
// =============================================================================

export interface ClimateMetric {
  id: string; // e.g. "rain_total", "hot_days"
  label: string;
  unit: string;
  before: number;
  recent: number;
  delta: number;
  p_value: number | null; // Mann-Whitney bilateral p-value
  significant: boolean; // p < 0.10
  series: [number, number | null][]; // [(campaign_year, value)]
  source: Source;
}

export interface Climatology {
  rain_mm: number[]; // 24 fortnights from ag year start
  et0_mm: number[];
  tmax_c: number[];
  tmin_c: number[];
}

export interface Meta {
  lat: number;
  lon: number;
  elevation_m: number;
  hemisphere: "N" | "S";
  ag_year_start: "07-01" | "01-01" | string;
  seasons: number[];
  periods: Record<"before" | "recent" | "eval" | string, [number, number]>;
  et0_hargreaves_share: number;
  resolution_note: string;
  assumptions: string[];
}

export interface AnalyzeResponse {
  meta: Meta;
  climate: ClimateMetric[];
  climatology: {
    before: Climatology;
    recent: Climatology;
  };
  rotations: RotationResult[]; // Fixed order: actual, adaptada, regenerativa[, diversificada]
}
