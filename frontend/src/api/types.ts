// Mirrors Pydantic schemas from Phase 6 backend

// ── Phase 6.1 ─────────────────────────────────────────────────────────────────

export interface CircuitInfo {
  name: string
  length_km: number
  circuit_type: string
  pit_loss_s: number
  is_street_circuit: boolean
  total_laps_typical: number
  available_years: number[]
  svg_points?: string | null
  viewBox?: string | null
}

export interface DriverInfo {
  code: string
  full_name: string
  team_2024: string
  style_vector: Record<string, number | null>
  cluster: number
}

export interface HistoricalRace {
  year: number
  circuit: string
  round_number: number
  winner: string
  winner_strategy: Array<{ lap: number; compound: string }>
  total_laps: number
  race_time_s: number
  grid: string[]
  results: Array<{ driver: string; position: number; start: number }>
}

// ── Phase 6.2 ─────────────────────────────────────────────────────────────────

export interface DegradationCurveRequest {
  driver: string
  circuit: string
  compound: string
  stint_start_lap?: number
  stint_length?: number
  total_race_laps?: number
  year?: number
}

export interface DegradationCurveResponse {
  driver: string
  circuit: string
  compound: string
  lap_times: number[]
  cliff_lap: number
  confidence: string
}

export interface PitStop {
  lap: number
  compound: string
}

export interface LapData {
  lap: number
  compound: string
  tire_age: number
  lap_time: number
  position: number
}

export interface SimulateRequest {
  driver: string
  circuit: string
  starting_compound: string
  starting_position?: number
  pit_stops?: PitStop[]
  year?: number
  total_laps?: number
}

export interface SimulateResponse {
  final_position: number
  race_time_s: number
  pit_stops_executed: PitStop[]
  lap_by_lap: LapData[]
  position_capped: boolean
}

export interface PPORecommendRequest {
  driver: string
  circuit: string
  starting_compound: string
  starting_position?: number
  year?: number
  total_laps?: number
}

export interface PPORecommendResponse {
  recommended_pit_stops: PitStop[]
  final_position: number
  race_time_s: number
  lap_by_lap: LapData[]
  confidence: string
  strategy_overridden: boolean
  ppo_note: string
}

// ── Phase 6.3 ─────────────────────────────────────────────────────────────────

export interface RivalPrediction {
  driver: string
  starting_position: number
  final_position: number
  pit_history: Array<{ lap: number; compound: string }>
  style_summary: Record<string, number | null>
}

export interface UndercutWindow {
  lap: number
  gap_s: number
  rival_driver: string
  rival_tire_age: number
}

export interface GridSimulateRequest {
  ego_driver: string
  circuit: string
  year?: number
  ego_starting_position: number
  starting_compound: string
  total_laps: number
  starting_grid: string[]
  starting_compounds: Record<string, string>
  pit_stops?: Array<{ lap: number; compound: string }>
  weather?: Record<string, unknown> | null
}

export interface GridSimulateResponse {
  ego_driver: string
  circuit: string
  ego_strategy: Array<{ lap: number; compound: string }>
  ego_predicted_position: number
  ego_race_time_s: number
  ego_lap_by_lap: LapData[]
  rival_predictions: RivalPrediction[]
  positions_gained: number
  undercut_windows_identified: UndercutWindow[]
}

export interface OptimizerRecommendRequest {
  ego_driver: string
  circuit: string
  year?: number
  ego_starting_position: number
  starting_compound: string
  total_laps: number
  starting_grid: string[]
  starting_compounds: Record<string, string>
  weather?: Record<string, unknown> | null
}

export interface OptimizerRecommendResponse {
  ego_driver: string
  circuit: string
  recommended_strategy: Array<{ lap: number; compound: string }>
  predicted_finish_position: number
  race_time_s: number
  positions_gained: number
  rival_predictions: RivalPrediction[]
  undercut_windows_identified: UndercutWindow[]
  strategy_rationale: string
  confidence: string
  ego_lap_by_lap: LapData[]
}

export interface HistoricalValidationResponse {
  year: number
  circuit: string
  actual_results: Array<{ driver: string; position: number; starting_position: number }>
  simulated_results: Array<{ driver: string; position: number }>
  accuracy_pct_within_3: number
  accuracy_pct_within_5: number
  mean_absolute_delta: number
}
