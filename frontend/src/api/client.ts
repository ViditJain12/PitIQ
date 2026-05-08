import type {
  CircuitInfo,
  DriverInfo,
  HistoricalRace,
  DegradationCurveRequest,
  DegradationCurveResponse,
  SimulateRequest,
  SimulateResponse,
  PPORecommendRequest,
  PPORecommendResponse,
  GridSimulateRequest,
  GridSimulateResponse,
  OptimizerRecommendRequest,
  OptimizerRecommendResponse,
  HistoricalValidationResponse,
} from './types'

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function post<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json() as Promise<TRes>
}

export const api = {
  health: () => get<{ status: string }>('/health'),

  // ── Data endpoints ─────────────────────────────────────────────────────────
  getCircuits: () => get<CircuitInfo[]>('/api/circuits'),
  getCircuit: (name: string) => get<CircuitInfo>(`/api/circuits/${encodeURIComponent(name)}`),
  getDrivers: () => get<DriverInfo[]>('/api/drivers'),
  getDriver: (code: string) => get<DriverInfo>(`/api/drivers/${encodeURIComponent(code)}`),
  getHistoricalRace: (year: number, circuit: string) =>
    get<HistoricalRace>(`/api/historical/${year}/${encodeURIComponent(circuit)}`),
  getHistoricalGrid: (year: number, circuit: string) =>
    get<{ grid: string[]; compounds: Record<string, string> }>(
      `/api/historical/${year}/${encodeURIComponent(circuit)}/grid`,
    ),

  // ── Sandbox endpoints ──────────────────────────────────────────────────────
  getDegradationCurve: (req: DegradationCurveRequest) =>
    post<DegradationCurveRequest, DegradationCurveResponse>('/api/sandbox/degradation-curve', req),
  sandboxSimulate: (req: SimulateRequest) =>
    post<SimulateRequest, SimulateResponse>('/api/sandbox/simulate', req),
  sandboxRecommend: (req: PPORecommendRequest) =>
    post<PPORecommendRequest, PPORecommendResponse>('/api/sandbox/recommend', req),

  // ── Optimizer endpoints ────────────────────────────────────────────────────
  optimizerSimulate: (req: GridSimulateRequest) =>
    post<GridSimulateRequest, GridSimulateResponse>('/api/optimizer/simulate', req),
  optimizerRecommend: (req: OptimizerRecommendRequest) =>
    post<OptimizerRecommendRequest, OptimizerRecommendResponse>('/api/optimizer/recommend', req),
  getHistoricalValidation: (year: number, circuit: string) =>
    get<HistoricalValidationResponse>(
      `/api/optimizer/historical-validation/${year}/${encodeURIComponent(circuit)}`,
    ),
}
