import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ComposedChart,
  BarChart,
  Bar,
  Cell,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { MapPin, Flag, Settings2, Plus, Minus, Target, TrendingUp, Sparkles } from 'lucide-react'
import { CircuitMap } from '../components/CircuitMap'
import { api } from '../api/client'
import { useStore } from '../store'
import type { LapData, PitStop, SimulateResponse, PPORecommendResponse } from '../api/types'
import TireBadge from '../components/TireBadge'
import LoadingState from '../components/LoadingState'
import DriverStylePanel from '../components/DriverStylePanel'

// ── constants ──────────────────────────────────────────────────────────────

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: '#E8002D', MEDIUM: '#FFF200', HARD: '#FFFFFF',
}
const COMPOUNDS = ['SOFT', 'MEDIUM', 'HARD'] as const
const YEARS = [2021, 2022, 2023, 2024, 2025]

// ── helpers ────────────────────────────────────────────────────────────────

interface Stint { compound: string; startLap: number; endLap: number; laps: LapData[] }

function buildStints(lapData: LapData[]): Stint[] {
  const stints: Stint[] = []
  let cur: Stint | null = null
  for (const lap of lapData) {
    if (!cur || cur.compound !== lap.compound) {
      if (cur) stints.push(cur)
      cur = { compound: lap.compound, startLap: lap.lap, endLap: lap.lap, laps: [lap] }
    } else {
      cur.endLap = lap.lap
      cur.laps.push(lap)
    }
  }
  if (cur) stints.push(cur)
  return stints
}

function formatRaceTime(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

function avg(nums: number[]): number {
  return nums.reduce((a, b) => a + b, 0) / nums.length
}

// ── unified result type ────────────────────────────────────────────────────

interface SandboxResult {
  final_position: number
  race_time_s: number
  pit_stops: PitStop[]
  lap_by_lap: LapData[]
  mode: 'simulate' | 'recommend'
  confidence?: string
  strategy_overridden?: boolean
  ppo_note?: string
  position_capped?: boolean
}

// ── sub-components ─────────────────────────────────────────────────────────

function SectionCard({ number, title, children }: { number: string; title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        background: 'var(--color-surface)',
        borderLeft: '3px solid var(--color-accent)',
        borderRadius: 'var(--radius-card)',
        padding: '18px 20px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, color: 'var(--color-accent)', letterSpacing: '0.05em' }}>
          {number}
        </span>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 900, color: 'var(--color-text)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          {title}
        </span>
      </div>
      {children}
    </div>
  )
}

function CompoundButtons({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <div style={{ display: 'flex', gap: 4 }}>
      {COMPOUNDS.map(c => {
        const active = value === c
        return (
          <button
            key={c}
            onClick={() => onChange(c)}
            style={{
              padding: '5px 10px',
              fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
              letterSpacing: '0.08em', cursor: 'pointer',
              border: active ? 'none' : `1px solid ${COMPOUND_COLORS[c]}55`,
              background: active ? COMPOUND_COLORS[c] : 'transparent',
              color: active ? (c === 'SOFT' ? '#fff' : '#000') : COMPOUND_COLORS[c],
              borderRadius: 'var(--radius-btn)',
              transition: 'all 0.1s',
            }}
          >
            {c[0]}
          </button>
        )
      })}
    </div>
  )
}

function CompoundButtonsFull({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <div style={{ display: 'flex', gap: 3 }}>
      {COMPOUNDS.map(c => {
        const active = value === c
        return (
          <button
            key={c}
            onClick={() => onChange(c)}
            style={{
              padding: '4px 8px',
              fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700,
              letterSpacing: '0.08em', cursor: 'pointer',
              border: active ? 'none' : `1px solid ${COMPOUND_COLORS[c]}55`,
              background: active ? COMPOUND_COLORS[c] : 'transparent',
              color: active ? (c === 'SOFT' ? '#fff' : '#000') : COMPOUND_COLORS[c],
              borderRadius: 'var(--radius-btn)',
              transition: 'all 0.1s',
            }}
          >
            {c}
          </button>
        )
      })}
    </div>
  )
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 5 }}>
      {children}
    </div>
  )
}

function Select({ value, onChange, placeholder, children, disabled }: React.SelectHTMLAttributes<HTMLSelectElement> & { placeholder?: string }) {
  return (
    <select
      value={value ?? ''}
      onChange={onChange}
      disabled={disabled}
      style={{
        width: '100%', padding: '8px 10px',
        background: 'var(--color-surface-2)', border: 'var(--border)',
        color: value ? 'var(--color-text)' : 'var(--color-text-muted)',
        fontFamily: 'var(--font-mono)', fontSize: 11,
        cursor: disabled ? 'not-allowed' : 'pointer', outline: 'none',
        appearance: 'none', borderRadius: 4,
      }}
    >
      {placeholder && <option value="" disabled>{placeholder}</option>}
      {children}
    </select>
  )
}

function StintBar({ stints, totalLaps }: { stints: Stint[]; totalLaps: number }) {
  return (
    <div style={{ display: 'flex', height: 20, gap: 2, width: '100%', borderRadius: 4, overflow: 'hidden' }}>
      {stints.map((s, i) => (
        <div
          key={i}
          title={`${s.compound}: L${s.startLap}–L${s.endLap} (${s.laps.length} laps)`}
          style={{
            flex: s.laps.length / totalLaps,
            background: COMPOUND_COLORS[s.compound] ?? '#888',
            opacity: 0.85,
          }}
        />
      ))}
    </div>
  )
}

function StintTable({ stints }: { stints: Stint[] }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
      <thead>
        <tr style={{ borderBottom: 'var(--border)' }}>
          {['Stint', 'Compound', 'Laps', 'Avg Time', 'Deg/Lap'].map(h => (
            <th key={h} style={{ textAlign: 'left', padding: '5px 10px', color: 'var(--color-text-muted)', fontWeight: 400, fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {stints.map((s, i) => {
          const times = s.laps.map(l => l.lap_time)
          const avgTime = avg(times)
          const shortStint = s.laps.length < 5
          const rawDeg = s.laps.length > 1 ? (times[times.length - 1] - times[0]) / (s.laps.length - 1) : 0
          const deg = Math.max(0, rawDeg)
          return (
            <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
              <td style={{ padding: '7px 10px', color: 'var(--color-text-dim)' }}>{i + 1}</td>
              <td style={{ padding: '7px 10px' }}><TireBadge compound={s.compound} size="sm" /></td>
              <td style={{ padding: '7px 10px', color: 'var(--color-text)' }}>L{s.startLap}–L{s.endLap}</td>
              <td style={{ padding: '7px 10px', color: 'var(--color-text)' }}>{avgTime.toFixed(3)}s</td>
              <td style={{ padding: '7px 10px', color: shortStint ? 'var(--color-text-muted)' : deg > 0.05 ? '#E8002D' : '#39B54A' }}>
                {shortStint ? 'N/A' : `+${deg.toFixed(3)}s`}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// ── FormState ──────────────────────────────────────────────────────────────

interface FormState {
  circuit: string
  year: number
  driver: string
  startingPosition: number
  startingCompound: string
  pitStops: PitStop[]
}

// ── main page ──────────────────────────────────────────────────────────────

export default function Sandbox() {
  const navigate = useNavigate()
  const allDrivers = useStore(s => s.drivers)
  const seasonDrivers = useStore(s => s.seasonDrivers)
  const seasonCircuits = useStore(s => s.seasonCircuits)
  const setSeasonDrivers = useStore(s => s.setSeasonDrivers)
  const setSeasonCircuits = useStore(s => s.setSeasonCircuits)

  const [form, setForm] = useState<FormState>({
    circuit: '',
    year: 2024,
    driver: '',
    startingPosition: 1,
    startingCompound: 'SOFT',
    pitStops: [],
  })
  const [grid, setGrid] = useState<string[]>([])
  const [loadingGrid, setLoadingGrid] = useState(false)
  const [loadingSeason, setLoadingSeason] = useState(false)
  const [result, setResult] = useState<SandboxResult | null>(null)
  const [ppoResult, setPpoResult] = useState<SandboxResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showStylePanel, setShowStylePanel] = useState(false)

  // ── season-aware dropdown data ─────────────────────────────────────────

  const activeDrivers = seasonDrivers[form.year] ?? []
  const activeCircuits = seasonCircuits[form.year] ?? []

  const fetchSeasonData = useCallback(async (year: number) => {
    const needsDrivers = !seasonDrivers[year]
    const needsCircuits = !seasonCircuits[year]
    if (!needsDrivers && !needsCircuits) return
    setLoadingSeason(true)
    try {
      const [d, c] = await Promise.all([
        needsDrivers ? api.getSeasonDrivers(year) : Promise.resolve(seasonDrivers[year]),
        needsCircuits ? api.getSeasonCircuits(year) : Promise.resolve(seasonCircuits[year]),
      ])
      if (needsDrivers) setSeasonDrivers(year, d)
      if (needsCircuits) setSeasonCircuits(year, c)
    } catch { /* leave empty */ }
    finally { setLoadingSeason(false) }
  }, [seasonDrivers, seasonCircuits, setSeasonDrivers, setSeasonCircuits])

  useEffect(() => { fetchSeasonData(form.year) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleYearChange = useCallback(async (newYear: number) => {
    await fetchSeasonData(newYear)
    setForm(prev => {
      const circuits = seasonCircuits[newYear] ?? []
      const drivers = seasonDrivers[newYear] ?? []
      const circuitValid = circuits.some(c => c.name === prev.circuit)
      const driverValid = drivers.some(d => d.code === prev.driver)
      return { ...prev, year: newYear, circuit: circuitValid ? prev.circuit : '', driver: driverValid ? prev.driver : '', startingPosition: 1 }
    })
    setGrid([])
  }, [fetchSeasonData, seasonCircuits, seasonDrivers])

  // ── fetch grid when circuit + year change ──────────────────────────────

  const fetchGrid = useCallback(async (circuit: string, year: number) => {
    if (!circuit) return
    setLoadingGrid(true)
    try {
      const g = await api.getHistoricalGrid(year, circuit)
      setGrid(g)
    } catch { setGrid([]) }
    finally { setLoadingGrid(false) }
  }, [])

  useEffect(() => {
    if (form.circuit && form.year) fetchGrid(form.circuit, form.year)
  }, [form.circuit, form.year, fetchGrid])

  useEffect(() => {
    if (!form.driver || grid.length === 0) return
    const pos = grid.indexOf(form.driver)
    if (pos !== -1) setForm(prev => ({ ...prev, startingPosition: pos + 1 }))
  }, [form.driver, grid])

  // ── derived ────────────────────────────────────────────────────────────

  const circuitInfo = activeCircuits.find(c => c.name === form.circuit) ?? null
  const totalLaps = circuitInfo?.total_laps_typical ?? 58
  const earlyPitStop = form.pitStops.find(p => p.lap < 5) ?? null
  const canSubmit = !!form.circuit && !!form.driver && !earlyPitStop
  const noTwoCompound = form.pitStops.length === 0 || form.pitStops.every(p => p.compound === form.startingCompound)
  const isMultiStop = form.pitStops.length >= 3
  const isMidGrid = form.startingPosition > 10

  // ── handlers ───────────────────────────────────────────────────────────

  function addPitStop() {
    if (form.pitStops.length >= 4) return
    setForm(prev => ({ ...prev, pitStops: [...prev.pitStops, { lap: Math.round(totalLaps / 2), compound: 'HARD' }] }))
  }

  function updatePitStop(i: number, field: 'lap' | 'compound', value: string | number) {
    setForm(prev => {
      const stops = [...prev.pitStops]
      stops[i] = { ...stops[i], [field]: value }
      return { ...prev, pitStops: stops }
    })
  }

  function removePitStop(i: number) {
    setForm(prev => ({ ...prev, pitStops: prev.pitStops.filter((_, idx) => idx !== i) }))
  }

  async function handleSimulate() {
    setIsLoading(true); setError(null)
    try {
      const res: SimulateResponse = await api.sandboxSimulate({
        driver: form.driver, circuit: form.circuit, starting_compound: form.startingCompound,
        starting_position: form.startingPosition, pit_stops: form.pitStops, year: form.year, total_laps: totalLaps,
      })
      setResult({ final_position: res.final_position, race_time_s: res.race_time_s, pit_stops: res.pit_stops_executed, lap_by_lap: res.lap_by_lap, mode: 'simulate', position_capped: res.position_capped })
    } catch (e) { setError(e instanceof Error ? e.message : 'Simulation failed') }
    finally { setIsLoading(false) }
  }

  async function handleRecommend() {
    setIsLoading(true); setError(null)
    try {
      const res: PPORecommendResponse = await api.sandboxRecommend({
        driver: form.driver, circuit: form.circuit, starting_compound: form.startingCompound,
        starting_position: form.startingPosition, year: form.year, total_laps: totalLaps,
      })
      const rec = { final_position: res.final_position, race_time_s: res.race_time_s, pit_stops: res.recommended_pit_stops, lap_by_lap: res.lap_by_lap, mode: 'recommend' as const, confidence: res.confidence, strategy_overridden: res.strategy_overridden, ppo_note: res.ppo_note }
      setResult(rec)
      setPpoResult(rec)
    } catch (e) { setError(e instanceof Error ? e.message : 'Recommendation failed') }
    finally { setIsLoading(false) }
  }

  // ── render ─────────────────────────────────────────────────────────────

  const stints = result ? buildStints(result.lap_by_lap) : []
  const positionsGained = result ? form.startingPosition - result.final_position : 0
  const chartData = result?.lap_by_lap.map(l => ({ lap: l.lap, time: +l.lap_time.toFixed(3), compound: l.compound, tire_age: l.tire_age, position: l.position })) ?? []

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg)', display: 'flex', flexDirection: 'column' }}>

      {/* Nav */}
      <nav style={{ display: 'flex', alignItems: 'center', padding: '14px 28px', borderBottom: 'var(--border)', background: 'var(--color-surface)', flexShrink: 0, gap: 16 }}>
        <button onClick={() => navigate('/')} style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 900, letterSpacing: '0.1em', color: 'var(--color-text)', background: 'none', border: 'none', cursor: 'pointer' }}>
          PIT<span style={{ color: 'var(--color-accent)' }}>IQ</span>
        </button>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
          SANDBOX MODE
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 24 }}>
          {[{ label: 'OPTIMIZER', path: '/optimizer' }, { label: 'HISTORICAL', path: '/historical' }].map(({ label, path }) => (
            <button key={path} onClick={() => navigate(path)} style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.12em' }}>
              {label} →
            </button>
          ))}
        </div>
      </nav>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* ── Left panel (38%) ───────────────────────────────────────── */}
        <div style={{ width: '38%', flexShrink: 0, borderRight: 'var(--border)', overflowY: 'auto', padding: '20px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Section 01 — Race Selection */}
          <SectionCard number="01" title="Race Selection">
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <FieldLabel>Circuit</FieldLabel>
                <Select value={form.circuit} onChange={e => setForm(prev => ({ ...prev, circuit: e.target.value, driver: '', startingPosition: 1 }))} placeholder={loadingSeason ? 'Loading…' : 'Select circuit'} disabled={loadingSeason}>
                  {activeCircuits.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                </Select>
              </div>
              <div style={{ width: 80 }}>
                <FieldLabel>Year</FieldLabel>
                <Select value={form.year} onChange={e => { void handleYearChange(Number(e.target.value)) }}>
                  {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                </Select>
              </div>
            </div>

            {circuitInfo && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 4, padding: '10px 12px' }}>
                  <MapPin size={13} color="var(--color-accent)" style={{ flexShrink: 0, marginRight: 10 }} />
                  {[
                    { label: 'Circuit Length', value: `${circuitInfo.length_km} km` },
                    { label: 'Laps', value: String(circuitInfo.total_laps_typical) },
                    { label: 'Track Type', value: circuitInfo.circuit_type },
                  ].map((m, i) => (
                    <div key={m.label} style={{ display: 'flex', alignItems: 'stretch', flex: 1 }}>
                      {i > 0 && <div style={{ width: 1, background: 'var(--color-border)', marginRight: 12, alignSelf: 'stretch' }} />}
                      <div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 2 }}>{m.label}</div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-text)', fontWeight: 600, textTransform: 'capitalize' }}>{m.value}</div>
                      </div>
                    </div>
                  ))}
                </div>
                {circuitInfo.svg_points && (
                  <div style={{ background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 4, padding: '10px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end', marginBottom: 3 }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                        Click to magnify
                      </span>
                    </div>
                    <CircuitMap
                      svgPoints={circuitInfo.svg_points}
                      viewBox={circuitInfo.viewBox ?? '0 0 200 120'}
                      width="100%"
                      height={100}
                      animated
                      circuitInfo={{
                        name: circuitInfo.name,
                        length_km: circuitInfo.length_km,
                        circuit_type: circuitInfo.circuit_type,
                        pit_loss_s: circuitInfo.pit_loss_s,
                        total_laps_typical: circuitInfo.total_laps_typical,
                      }}
                    />
                  </div>
                )}
              </>
            )}
          </SectionCard>

          {/* Section 02 — Driver Setup */}
          <SectionCard number="02" title="Driver Setup">
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <FieldLabel>Driver</FieldLabel>
                <Select value={form.driver} onChange={e => setForm(prev => ({ ...prev, driver: e.target.value }))} placeholder={loadingSeason ? 'Loading…' : 'Select driver'} disabled={loadingSeason}>
                  {activeDrivers.map(d => <option key={d.code} value={d.code}>{d.code} — {d.full_name}</option>)}
                </Select>
                {form.driver && (
                  <button
                    onClick={() => setShowStylePanel(true)}
                    style={{
                      marginTop: 6, display: 'inline-flex', alignItems: 'center', gap: 5,
                      padding: '4px 10px',
                      background: 'rgba(232,0,45,0.08)',
                      border: '1px solid rgba(232,0,45,0.5)',
                      borderRadius: 'var(--radius-btn)',
                      fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em',
                      color: 'var(--color-accent)', cursor: 'pointer', textTransform: 'uppercase',
                      animation: 'style-pulse 2.5s ease-in-out infinite',
                    }}
                  >
                    <span style={{ fontSize: 10 }}>◈</span> View Driver Style
                  </button>
                )}
              </div>
              <div style={{ width: 72 }}>
                <FieldLabel>Grid Pos</FieldLabel>
                <input
                  type="number" min={1} max={20} value={form.startingPosition}
                  onChange={e => setForm(prev => ({ ...prev, startingPosition: Math.max(1, Math.min(20, Number(e.target.value))) }))}
                  style={{ width: '100%', padding: '8px 8px', background: 'var(--color-surface-2)', border: 'var(--border)', color: 'var(--color-text)', fontFamily: 'var(--font-mono)', fontSize: 12, outline: 'none', borderRadius: 4 }}
                />
              </div>
            </div>

            {loadingGrid && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.1em', marginBottom: 8 }}>Loading grid…</div>}

            {isMidGrid && (
              <div style={{ marginBottom: 10, padding: '7px 10px', background: 'rgba(255,242,0,0.06)', border: '1px solid rgba(255,242,0,0.3)', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200', letterSpacing: '0.04em', lineHeight: 1.5 }}>
                ⚠ Sandbox is most accurate P1–P10. For mid-grid, use{' '}
                <span style={{ textDecoration: 'underline', cursor: 'pointer' }} onClick={() => navigate('/optimizer')}>Optimizer mode</span>.
              </div>
            )}

            <div>
              <FieldLabel>Starting Compound</FieldLabel>
              <CompoundButtonsFull value={form.startingCompound} onChange={c => setForm(prev => ({ ...prev, startingCompound: c }))} />
            </div>
          </SectionCard>

          {/* Section 03 — Strategy Builder */}
          <SectionCard number="03" title="Strategy Builder">
            {form.pitStops.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: '32px 1fr 1fr 28px', gap: '0 8px', marginBottom: 6, paddingBottom: 6, borderBottom: 'var(--border)' }}>
                {['STINT', 'PIT LAP', 'COMPOUND', ''].map(h => (
                  <div key={h} style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>{h}</div>
                ))}
              </div>
            )}

            {form.pitStops.map((stop, i) => (
              <PitStopRow key={i} stop={stop} index={i} totalLaps={totalLaps} onUpdate={(field, value) => updatePitStop(i, field, value)} onRemove={() => removePitStop(i)} />
            ))}

            {form.pitStops.length < 4 && (
              <button
                onClick={addPitStop}
                style={{ width: '100%', padding: '9px', marginTop: form.pitStops.length > 0 ? 6 : 0, background: 'transparent', border: '1px dashed var(--color-border)', borderRadius: 4, color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)', fontSize: 10, cursor: 'pointer', letterSpacing: '0.1em', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
              >
                <Plus size={12} /> ADD STINT
              </button>
            )}

            {earlyPitStop && (
              <div style={{ marginTop: 8, padding: '6px 10px', background: 'rgba(232,0,45,0.08)', border: '1px solid rgba(232,0,45,0.3)', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-accent)', letterSpacing: '0.04em' }}>
                ✕ Pit stops before lap 5 are not allowed
              </div>
            )}

            {noTwoCompound && form.circuit && (
              <div style={{ marginTop: 6, padding: '6px 10px', background: 'rgba(255,242,0,0.08)', border: '1px solid rgba(255,242,0,0.3)', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200', letterSpacing: '0.05em' }}>
                ⚠ Two-compound rule requires at least one compound change
              </div>
            )}

            {isMultiStop && (
              <div style={{ marginTop: 6, padding: '6px 10px', background: 'rgba(255,242,0,0.04)', border: '1px solid rgba(255,242,0,0.2)', borderRadius: 4, fontFamily: 'var(--font-body)', fontSize: 10, fontStyle: 'italic', color: 'var(--color-text-dim)', lineHeight: 1.5 }}>
                Multi-stop may show optimistic predictions. Use Optimizer for full 20-car dynamics.
              </div>
            )}
          </SectionCard>

          {/* Action buttons */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
            <button
              onClick={handleSimulate}
              disabled={!canSubmit || isLoading}
              style={{ height: 48, background: canSubmit && !isLoading ? 'var(--color-accent)' : 'var(--color-surface-2)', border: 'none', color: '#fff', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, letterSpacing: '0.15em', cursor: canSubmit && !isLoading ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 'var(--radius-btn)' }}
            >
              <Flag size={15} /> SIMULATE STRATEGY
            </button>
            <button
              onClick={handleRecommend}
              disabled={!canSubmit || isLoading}
              style={{ height: 48, background: 'transparent', border: canSubmit && !isLoading ? '1px solid var(--color-accent)' : 'var(--border)', color: canSubmit && !isLoading ? 'var(--color-accent)' : 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, letterSpacing: '0.15em', cursor: canSubmit && !isLoading ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 'var(--radius-btn)' }}
            >
              <Settings2 size={15} /> GET AI PICK
            </button>
            {error && (
              <div style={{ padding: '8px 10px', background: 'rgba(232,0,45,0.08)', border: '1px solid rgba(232,0,45,0.3)', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-accent)', letterSpacing: '0.05em' }}>
                {error}
              </div>
            )}
          </div>

        </div>

        {/* ── Right panel (62%) ──────────────────────────────────────── */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {isLoading ? (
            <LoadingState label={form.pitStops.length === 0 ? 'RUNNING PPO AGENT' : 'SIMULATING RACE'} />
          ) : result ? (
            <ResultView
              result={result}
              stints={stints}
              chartData={chartData}
              startingPosition={form.startingPosition}
              positionsGained={positionsGained}
              totalLaps={totalLaps}
              mode={result.mode}
              confidence={result.confidence}
              strategyOverridden={result.strategy_overridden}
              ppoNote={result.ppo_note}
              positionCapped={result.position_capped}
              ppoResult={result.mode === 'simulate' ? ppoResult : null}
            />
          ) : (
            <Placeholder />
          )}
        </div>
      </div>

      <DriverStylePanel
        isOpen={showStylePanel}
        egoDriver={activeDrivers.find(d => d.code === form.driver) ?? null}
        allDrivers={activeDrivers}
        normDrivers={allDrivers.length > 0 ? allDrivers : activeDrivers}
        onClose={() => setShowStylePanel(false)}
      />
    </div>
  )
}

// ── PitStopRow ─────────────────────────────────────────────────────────────

function PitStopRow({ stop, index, totalLaps, onUpdate, onRemove }: {
  stop: PitStop; index: number; totalLaps: number
  onUpdate: (field: 'lap' | 'compound', value: string | number) => void
  onRemove: () => void
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '32px 1fr 1fr 28px', gap: '0 8px', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--color-border)' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-muted)', fontWeight: 700 }}>
        {index + 1}
      </span>
      <input
        type="number" min={2} max={totalLaps - 2} value={stop.lap}
        onChange={e => onUpdate('lap', Math.max(2, Math.min(totalLaps - 2, Number(e.target.value))))}
        style={{ width: '100%', padding: '5px 8px', background: 'var(--color-surface-2)', border: 'var(--border)', color: 'var(--color-text)', fontFamily: 'var(--font-mono)', fontSize: 12, outline: 'none', borderRadius: 4 }}
      />
      <CompoundButtons value={stop.compound} onChange={c => onUpdate('compound', c)} />
      <button onClick={onRemove} style={{ background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', padding: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Minus size={13} />
      </button>
    </div>
  )
}

// ── Placeholder ────────────────────────────────────────────────────────────

function Placeholder() {
  return (
    <div style={{ height: '100%', minHeight: 400, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
      <div style={{ width: 1, height: 60, background: 'linear-gradient(to bottom, transparent, var(--color-border))' }} />
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
        Configure a race on the left to run simulation
      </span>
    </div>
  )
}

// ── AI Insights ────────────────────────────────────────────────────────────

function generateInsights(stints: Stint[], pitStops: PitStop[]) {
  if (stints.length === 0) return []
  const insights: Array<{ icon: 'Target' | 'TrendingUp' | 'Sparkles'; title: string; body: string }> = []

  const stintsWithAvg = stints.map(s => ({ ...s, avgTime: avg(s.laps.map(l => l.lap_time)) }))
  const bestStint = stintsWithAvg.reduce((best, s) => s.avgTime < best.avgTime ? s : best)
  insights.push({
    icon: 'Target',
    title: `Optimal ${bestStint.compound} Stint`,
    body: `The ${bestStint.compound.toLowerCase()} stint from L${bestStint.startLap}–L${bestStint.endLap} delivers the best average pace at ${bestStint.avgTime.toFixed(3)}s/lap.`,
  })

  const lastStint = stints[stints.length - 1]
  insights.push({
    icon: 'TrendingUp',
    title: `${lastStint.compound} Finish`,
    body: `${lastStint.compound} compound offers stability through the final ${lastStint.endLap - lastStint.startLap} laps.`,
  })

  if (pitStops.length > 0) {
    const firstPit = pitStops[0]
    insights.push({
      icon: 'Sparkles',
      title: 'Pit Window',
      body: `First pit stop on lap ${firstPit.lap} — switching to ${firstPit.compound.toLowerCase()} tires.`,
    })
  }

  return insights
}

const INSIGHT_ICONS = {
  Target: <Target size={14} color="var(--color-accent)" />,
  TrendingUp: <TrendingUp size={14} color="#27F4D2" />,
  Sparkles: <Sparkles size={14} color="#A78BFA" />,
}

// ── ResultView ─────────────────────────────────────────────────────────────

type ChartTab = 'laptime' | 'tirewear' | 'position' | 'pacedelta'

const CLIFF_LAPS: Record<string, number> = { SOFT: 18, MEDIUM: 32, HARD: 45 }
const CLIFF_COLORS: Record<string, string> = { SOFT: '#E8002D', MEDIUM: '#FFF200', HARD: '#888888' }
const CLIFF_LABELS: Record<string, string> = { SOFT: 'SOFT CLIFF', MEDIUM: 'MED CLIFF', HARD: 'HARD CLIFF' }

const AXIS_STYLE = { fill: 'var(--color-text-dim)', fontSize: 10, fontFamily: 'var(--font-mono)' }
const GRID_STYLE = { stroke: 'var(--color-border)', strokeOpacity: 0.3 }
const TOOLTIP_STYLE = { background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 0, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text)' }

function ResultView({
  result, stints, chartData, startingPosition, positionsGained, totalLaps, mode,
  confidence, strategyOverridden, ppoNote, positionCapped, ppoResult,
}: {
  result: SandboxResult
  stints: Stint[]
  chartData: Array<{ lap: number; time: number; compound: string; tire_age: number; position: number }>
  startingPosition: number
  positionsGained: number
  totalLaps: number
  mode: 'simulate' | 'recommend'
  confidence?: string
  strategyOverridden?: boolean
  ppoNote?: string
  positionCapped?: boolean
  ppoResult?: SandboxResult | null
}) {
  const [activeTab, setActiveTab] = useState<ChartTab>('laptime')
  const [showRef, setShowRef] = useState(false)
  const [showHint, setShowHint] = useState(false)
  const hintWrapperRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showHint) return
    const handler = (e: MouseEvent) => {
      if (hintWrapperRef.current && !hintWrapperRef.current.contains(e.target as Node)) {
        setShowHint(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showHint])
  const times = chartData.map(d => d.time)
  const minT = Math.min(...times)
  const maxT = Math.max(...times)
  const usedCompounds = Array.from(new Set(chartData.map(d => d.compound)))
  const bestLap = Math.min(...times)
  const deltaData = chartData.map(d => ({ ...d, delta: +(d.time - bestLap).toFixed(3) }))
  const ppoByLap: Record<number, number> = {}
  ppoResult?.lap_by_lap.forEach(l => { ppoByLap[l.lap] = +l.lap_time.toFixed(3) })
  const mergedChartData = chartData.map(d => ({ ...d, ppoTime: ppoByLap[d.lap] ?? null }))
  const insights = generateInsights(stints, result.pit_stops)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Warnings */}
      {(positionCapped || strategyOverridden) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {positionCapped && (
            <div style={{ padding: '8px 12px', background: 'rgba(255,242,0,0.06)', border: '1px solid rgba(255,242,0,0.35)', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200', letterSpacing: '0.04em', lineHeight: 1.5 }}>
              ⚠ Position estimate adjusted — use Optimizer mode for full 20-car simulation.
            </div>
          )}
          {strategyOverridden && (
            <div style={{ padding: '8px 12px', background: 'rgba(255,242,0,0.06)', border: '1px solid rgba(255,242,0,0.35)', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200', letterSpacing: '0.04em', lineHeight: 1.5 }}>
              ⚠ AI recommendation adjusted for limited training data at this circuit.
            </div>
          )}
        </div>
      )}

      {/* Mode badge + ppo note */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em', color: mode === 'recommend' ? 'var(--color-accent)' : 'var(--color-text-muted)', border: `1px solid ${mode === 'recommend' ? 'var(--color-accent)' : 'var(--color-border)'}`, padding: '2px 8px', borderRadius: 3 }}>
          {mode === 'recommend' ? 'PPO AGENT RECOMMENDATION' : 'USER STRATEGY SIMULATION'}
        </span>
        {confidence && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em', color: confidence === 'high' ? '#39B54A' : confidence === 'medium' ? '#FFF200' : 'var(--color-text-muted)' }}>
            {confidence.toUpperCase()} CONFIDENCE
          </span>
        )}
        {ppoNote && <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, fontStyle: 'italic', color: 'var(--color-text-dim)' }}>{ppoNote}</span>}
      </div>

      {/* Stat cards row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
        {[
          { value: `P${Math.round(result.final_position)}`, label: 'Predicted Finish', accent: true },
          { value: formatRaceTime(result.race_time_s), label: 'Race Time', accent: false },
          { value: positionsGained >= 0 ? `+${positionsGained}` : `${positionsGained}`, label: 'Positions', accent: false },
          { value: String(result.pit_stops.length), label: 'Pit Stops', accent: false },
        ].map(({ value, label, accent }) => (
          <div
            key={label}
            style={{
              background: accent ? 'linear-gradient(135deg, rgba(232,0,45,0.22) 0%, rgba(232,0,45,0.06) 100%)' : 'var(--color-surface)',
              border: accent ? '1px solid rgba(232,0,45,0.45)' : 'var(--border)',
              borderRadius: 'var(--radius-card)',
              padding: '14px 16px',
              display: 'flex', flexDirection: 'column', gap: 4,
            }}
          >
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 900, color: accent ? 'var(--color-accent)' : 'var(--color-text)', lineHeight: 1, letterSpacing: '-0.01em' }}>
              {value}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: accent ? 'rgba(232,0,45,0.7)' : 'var(--color-text-muted)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              {label}
            </div>
          </div>
        ))}
      </div>

      {/* Strategy Timeline */}
      <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)', padding: '16px 18px' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 10 }}>
          Strategy Timeline
        </div>
        {/* Legend */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 10 }}>
          {[['SOFT', '#E8002D'], ['MEDIUM', '#FFF200'], ['HARD', '#FFFFFF']].map(([c, col]) => (
            <div key={c} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: col as string, flexShrink: 0, display: 'inline-block' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.1em' }}>{c}</span>
            </div>
          ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-muted)' }}>✦</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.1em' }}>PIT STOP</span>
          </div>
        </div>
        <StintBar stints={stints} totalLaps={totalLaps} />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>LAP 1</span>
          {result.pit_stops.map(p => (
            <span key={p.lap} style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-dim)' }}>L{p.lap}</span>
          ))}
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>LAP {totalLaps}</span>
        </div>
      </div>

      {/* Tabbed chart */}
      <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)', padding: '16px 18px' }}>
        {/* Tab bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--color-border)' }}>
            {([
              { key: 'laptime', label: 'LAP TIME' },
              { key: 'tirewear', label: 'TIRE WEAR' },
              { key: 'position', label: 'POSITION TRACE' },
              { key: 'pacedelta', label: 'PACE DELTA' },
            ] as { key: ChartTab; label: string }[]).map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                style={{
                  padding: '6px 14px', background: 'none', border: 'none',
                  borderBottom: activeTab === tab.key ? '2px solid var(--color-accent)' : '2px solid transparent',
                  fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em',
                  color: activeTab === tab.key ? 'var(--color-text)' : 'var(--color-text-muted)',
                  cursor: 'pointer', marginBottom: -1, borderRadius: 0,
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
          {activeTab === 'laptime' && (
            <div ref={hintWrapperRef} style={{ position: 'relative' }}>
              <button
                onClick={() => {
                  if (!ppoResult) { setShowHint(h => !h) }
                  else { setShowHint(false); setShowRef(r => !r) }
                }}
                style={{
                  padding: '5px 12px',
                  background: showRef && ppoResult ? 'rgba(232,0,45,0.08)' : 'transparent',
                  border: showRef && ppoResult ? '1px solid var(--color-accent)' : 'var(--border)',
                  borderRadius: 'var(--radius-btn)', fontFamily: 'var(--font-mono)', fontSize: 9,
                  color: !ppoResult ? 'var(--color-text-muted)' : showRef ? 'var(--color-accent)' : 'var(--color-text-dim)',
                  opacity: !ppoResult ? 0.5 : 1,
                  cursor: !ppoResult ? 'help' : 'pointer',
                  letterSpacing: '0.1em',
                }}
              >
                {showRef && ppoResult ? 'HIDE REFERENCE ▾' : 'SHOW REFERENCE ▾'}
              </button>
              {showHint && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 8px)', right: 0, zIndex: 50,
                  background: 'var(--color-surface-2)', border: '1px solid var(--color-border)',
                  borderRadius: 0, padding: 12, width: 220,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                }}>
                  {/* Arrow */}
                  <div style={{
                    position: 'absolute', top: -5, right: 14,
                    width: 8, height: 8, background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border)', borderRight: 'none', borderBottom: 'none',
                    transform: 'rotate(45deg)',
                  }} />
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-accent)', letterSpacing: '0.12em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span>⚡</span> HOW TO USE SHOW REFERENCE
                  </div>
                  {['1. First run SIMULATE with your strategy', '2. Then click GET AI PICK', '3. Toggle SHOW REFERENCE to compare'].map((step, i) => (
                    <div key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-dim)', lineHeight: 1.7 }}>
                      {step}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── LAP TIME ─────────────────────────────────────────────────── */}
        {activeTab === 'laptime' && (
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={mergedChartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...GRID_STYLE} />
              {stints.map((s, i) => (
                <ReferenceArea key={i} x1={s.startLap} x2={s.endLap} fill={COMPOUND_COLORS[s.compound] ?? '#888'} fillOpacity={0.07} />
              ))}
              {result.pit_stops.map(p => (
                <ReferenceLine key={`pit-${p.lap}`} x={p.lap} stroke="var(--color-text-dim)" strokeDasharray="3 3" strokeWidth={1} />
              ))}
              <XAxis dataKey="lap" tick={AXIS_STYLE} axisLine={{ stroke: 'var(--color-border)' }} tickLine={false} />
              <YAxis domain={[minT - 0.5, maxT + 0.5]} tick={AXIS_STYLE} axisLine={false} tickLine={false} width={44} tickFormatter={(v: number) => v.toFixed(1)} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                formatter={((value: number, name: string, props: { payload?: { compound?: string; tire_age?: number; position?: number } }) => {
                  if (name === 'ppoTime') return [`${value.toFixed(3)}s`, 'PPO Reference']
                  return [`${value.toFixed(3)}s`, `${props.payload?.compound ?? ''} (age ${props.payload?.tire_age ?? 0})`]
                }) as any}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                labelFormatter={((lap: number) => `Lap ${lap} · P${chartData.find(d => d.lap === lap)?.position ?? '?'}`) as any}
              />
              <Line dataKey="time" stroke="var(--color-text)" strokeWidth={1.5} dot={false} activeDot={{ r: 3, fill: 'var(--color-accent)', stroke: 'none' }} />
              {showRef && ppoResult && (
                <Line dataKey="ppoTime" stroke="#555" strokeWidth={1} strokeDasharray="5 3" dot={false} activeDot={{ r: 2, fill: '#555', stroke: 'none' }} connectNulls />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        )}

        {/* ── TIRE WEAR ────────────────────────────────────────────────── */}
        {activeTab === 'tirewear' && (
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...GRID_STYLE} />
              {usedCompounds.map(cmp => (
                <ReferenceLine
                  key={`cliff-${cmp}`}
                  y={CLIFF_LAPS[cmp]}
                  stroke={CLIFF_COLORS[cmp] ?? '#888'}
                  strokeDasharray="4 2"
                  strokeWidth={1}
                  label={{ value: CLIFF_LABELS[cmp] ?? cmp, position: 'insideBottomRight', fill: CLIFF_COLORS[cmp] ?? '#888', fontSize: 8, fontFamily: 'var(--font-mono)' }}
                />
              ))}
              <XAxis dataKey="lap" tick={AXIS_STYLE} axisLine={{ stroke: 'var(--color-border)' }} tickLine={false} />
              <YAxis domain={[0, 50]} tick={AXIS_STYLE} axisLine={false} tickLine={false} width={36}
                label={{ value: 'TIRE AGE (LAPS)', angle: -90, position: 'insideLeft', fill: 'var(--color-text-dim)', fontSize: 9, fontFamily: 'var(--font-mono)', dx: -4 }}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                formatter={((value: number, _: string, props: { payload?: { compound?: string } }) => [`Age: ${value} laps`, props.payload?.compound ?? '']) as any}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                labelFormatter={((lap: number) => `Lap ${lap}`) as any}
              />
              {stints.map((s, i) => (
                <Line
                  key={i}
                  data={s.laps.map(l => ({ lap: l.lap, tire_age: l.tire_age, compound: l.compound }))}
                  dataKey="tire_age"
                  stroke={COMPOUND_COLORS[s.compound] ?? '#888'}
                  strokeWidth={1.5}
                  dot={false}
                  activeDot={{ r: 3, stroke: 'none' }}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        )}

        {/* ── POSITION TRACE ───────────────────────────────────────────── */}
        {activeTab === 'position' && (
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...GRID_STYLE} />
              <ReferenceLine y={startingPosition} stroke="#444" strokeDasharray="4 2" strokeWidth={1}
                label={{ value: 'START', position: 'insideTopRight', fill: '#666', fontSize: 8, fontFamily: 'var(--font-mono)' }}
              />
              {result.pit_stops.map(p => (
                <ReferenceLine key={`pit-${p.lap}`} x={p.lap} stroke="var(--color-text-dim)" strokeDasharray="3 3" strokeWidth={1} />
              ))}
              <XAxis dataKey="lap" tick={AXIS_STYLE} axisLine={{ stroke: 'var(--color-border)' }} tickLine={false} />
              <YAxis
                domain={[20, 1]} reversed ticks={[1, 5, 10, 15, 20]}
                tick={AXIS_STYLE} axisLine={false} tickLine={false} width={36}
                tickFormatter={(v: number) => `P${v}`}
                label={{ value: 'POSITION', angle: -90, position: 'insideLeft', fill: 'var(--color-text-dim)', fontSize: 9, fontFamily: 'var(--font-mono)', dx: -4 }}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                formatter={((value: number) => [`P${value}`, 'Position']) as any}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                labelFormatter={((lap: number) => `Lap ${lap}`) as any}
              />
              <Line dataKey="position" stroke="var(--color-accent)" strokeWidth={2} dot={false} activeDot={{ r: 3, fill: 'var(--color-accent)', stroke: 'none' }} />
            </ComposedChart>
          </ResponsiveContainer>
        )}

        {/* ── PACE DELTA ───────────────────────────────────────────────── */}
        {activeTab === 'pacedelta' && (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={deltaData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...GRID_STYLE} />
              <ReferenceLine y={0} stroke="var(--color-text-dim)" strokeWidth={1} />
              <XAxis dataKey="lap" tick={AXIS_STYLE} axisLine={{ stroke: 'var(--color-border)' }} tickLine={false} />
              <YAxis tick={AXIS_STYLE} axisLine={false} tickLine={false} width={44} tickFormatter={(v: number) => `+${v.toFixed(0)}s`}
                label={{ value: 'DELTA TO BEST (s)', angle: -90, position: 'insideLeft', fill: 'var(--color-text-dim)', fontSize: 9, fontFamily: 'var(--font-mono)', dx: -4 }}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                formatter={((value: number, _: string, props: { payload?: { compound?: string } }) => [`+${value.toFixed(3)}s vs best`, props.payload?.compound ?? '']) as any}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                labelFormatter={((lap: number) => `Lap ${lap}`) as any}
              />
              <Bar dataKey="delta" maxBarSize={8}>
                {deltaData.map((d, i) => (
                  <Cell key={i} fill={COMPOUND_COLORS[d.compound] ?? '#888'} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Bottom row: Stint Summary + AI Insight */}
      <div style={{ display: 'grid', gridTemplateColumns: '65% 35%', gap: 12 }}>
        {/* Stint Summary */}
        <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)', padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 10 }}>
            Stint Summary
          </div>
          <StintTable stints={stints} />
        </div>

        {/* AI Insight */}
        <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)', padding: '16px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Sparkles size={12} color="var(--color-accent)" />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
              AI Insight
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {insights.map((ins, i) => (
              <div key={i} style={{ background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 6, padding: '10px 12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                  {INSIGHT_ICONS[ins.icon]}
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, color: 'var(--color-text)', letterSpacing: '0.05em' }}>
                    {ins.title}
                  </span>
                </div>
                <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--color-text-dim)', lineHeight: 1.5, margin: 0 }}>
                  {ins.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
