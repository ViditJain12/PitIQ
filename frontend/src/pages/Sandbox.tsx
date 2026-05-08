import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { api } from '../api/client'
import { useStore } from '../store'
import type { LapData, PitStop, SimulateResponse, PPORecommendResponse } from '../api/types'
import StatCard from '../components/StatCard'
import TireBadge from '../components/TireBadge'
import LoadingState from '../components/LoadingState'

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

function SectionLabel({ n, label }: { n: number; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
      <span
        style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
          color: 'var(--color-accent)', background: 'rgba(232,0,45,0.12)',
          border: '1px solid var(--color-accent)', padding: '1px 6px',
          letterSpacing: '0.05em',
        }}
      >
        {n}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)',
          letterSpacing: '0.15em', textTransform: 'uppercase',
        }}
      >
        {label}
      </span>
    </div>
  )
}

function CompoundButtons({
  value, onChange,
}: { value: string; onChange: (c: string) => void }) {
  return (
    <div style={{ display: 'flex', gap: 1 }}>
      {COMPOUNDS.map(c => {
        const active = value === c
        return (
          <button
            key={c}
            onClick={() => onChange(c)}
            style={{
              padding: '5px 12px',
              fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
              letterSpacing: '0.1em', cursor: 'pointer', border: 'none',
              background: active ? COMPOUND_COLORS[c] : 'var(--color-surface-2)',
              color: active ? (c === 'SOFT' ? '#fff' : '#000') : COMPOUND_COLORS[c],
              outline: active ? 'none' : `1px solid ${COMPOUND_COLORS[c]}44`,
              transition: 'background 0.1s',
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
    <div
      style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)',
        letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 5,
      }}
    >
      {children}
    </div>
  )
}

function Select({
  value, onChange, placeholder, children, disabled,
}: React.SelectHTMLAttributes<HTMLSelectElement> & { placeholder?: string }) {
  return (
    <select
      value={value ?? ''}
      onChange={onChange}
      disabled={disabled}
      style={{
        width: '100%', padding: '8px 10px',
        background: 'var(--color-surface-2)', border: 'var(--border)',
        color: value ? 'var(--color-text)' : 'var(--color-text-muted)',
        fontFamily: 'var(--font-mono)', fontSize: 12,
        cursor: disabled ? 'not-allowed' : 'pointer', outline: 'none',
        appearance: 'none',
      }}
    >
      {placeholder && <option value="" disabled>{placeholder}</option>}
      {children}
    </select>
  )
}

function StintBar({ stints, totalLaps }: { stints: Stint[]; totalLaps: number }) {
  return (
    <div style={{ display: 'flex', height: 20, gap: 1, width: '100%' }}>
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
    <table
      style={{
        width: '100%', borderCollapse: 'collapse',
        fontFamily: 'var(--font-mono)', fontSize: 12,
      }}
    >
      <thead>
        <tr style={{ borderBottom: 'var(--border)' }}>
          {['Stint', 'Compound', 'Laps', 'Avg Time', 'Deg/Lap'].map(h => (
            <th
              key={h}
              style={{
                textAlign: 'left', padding: '6px 12px',
                color: 'var(--color-text-muted)', fontWeight: 400,
                fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase',
              }}
            >
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
          const rawDeg = s.laps.length > 1
            ? (times[times.length - 1] - times[0]) / (s.laps.length - 1)
            : 0
          const deg = Math.max(0, rawDeg)
          return (
            <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
              <td style={{ padding: '8px 12px', color: 'var(--color-text-dim)' }}>{i + 1}</td>
              <td style={{ padding: '8px 12px' }}>
                <TireBadge compound={s.compound} size="sm" />
              </td>
              <td style={{ padding: '8px 12px', color: 'var(--color-text)' }}>
                L{s.startLap}–L{s.endLap}
              </td>
              <td style={{ padding: '8px 12px', color: 'var(--color-text)' }}>
                {avgTime.toFixed(3)}s
              </td>
              <td
                style={{
                  padding: '8px 12px',
                  color: shortStint ? 'var(--color-text-muted)' : deg > 0.05 ? '#E8002D' : '#39B54A',
                }}
              >
                {shortStint ? 'N/A' : `+${deg.toFixed(3)}s`}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// ── main page ──────────────────────────────────────────────────────────────

interface FormState {
  circuit: string
  year: number
  driver: string
  startingPosition: number
  startingCompound: string
  pitStops: PitStop[]
}

export default function Sandbox() {
  const navigate = useNavigate()
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
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ── season-aware dropdown data ─────────────────────────────────────────

  const activeDrivers = seasonDrivers[form.year] ?? []
  const activeCircuits = seasonCircuits[form.year] ?? []

  // Fetch season data when year changes (cached in store)
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
    } catch { /* leave empty — dropdowns will be blank */ }
    finally { setLoadingSeason(false) }
  }, [seasonDrivers, seasonCircuits, setSeasonDrivers, setSeasonCircuits])

  // Initial fetch for default year
  useEffect(() => { fetchSeasonData(form.year) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // On year change: re-fetch season data, then reset circuit/driver if no longer valid
  const handleYearChange = useCallback(async (newYear: number) => {
    await fetchSeasonData(newYear)
    setForm(prev => {
      const circuits = seasonCircuits[newYear] ?? []
      const drivers = seasonDrivers[newYear] ?? []
      const circuitValid = circuits.some(c => c.name === prev.circuit)
      const driverValid = drivers.some(d => d.code === prev.driver)
      return {
        ...prev,
        year: newYear,
        circuit: circuitValid ? prev.circuit : '',
        driver: driverValid ? prev.driver : '',
        startingPosition: 1,
      }
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
    } catch {
      setGrid([])
    } finally {
      setLoadingGrid(false)
    }
  }, [])

  useEffect(() => {
    if (form.circuit && form.year) fetchGrid(form.circuit, form.year)
  }, [form.circuit, form.year, fetchGrid])

  // ── auto-populate starting position when driver or grid changes ────────

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
  const noTwoCompound =
    form.pitStops.length === 0 ||
    form.pitStops.every(p => p.compound === form.startingCompound)
  const isMultiStop = form.pitStops.length >= 3
  const isMidGrid = form.startingPosition > 10

  // ── handlers ───────────────────────────────────────────────────────────

  function addPitStop() {
    if (form.pitStops.length >= 4) return
    setForm(prev => ({
      ...prev,
      pitStops: [...prev.pitStops, { lap: Math.round(totalLaps / 2), compound: 'HARD' }],
    }))
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
    setIsLoading(true)
    setError(null)
    try {
      const res: SimulateResponse = await api.sandboxSimulate({
        driver: form.driver,
        circuit: form.circuit,
        starting_compound: form.startingCompound,
        starting_position: form.startingPosition,
        pit_stops: form.pitStops,
        year: form.year,
        total_laps: totalLaps,
      })
      setResult({
        final_position: res.final_position,
        race_time_s: res.race_time_s,
        pit_stops: res.pit_stops_executed,
        lap_by_lap: res.lap_by_lap,
        mode: 'simulate',
        position_capped: res.position_capped,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Simulation failed')
    } finally {
      setIsLoading(false)
    }
  }

  async function handleRecommend() {
    setIsLoading(true)
    setError(null)
    try {
      const res: PPORecommendResponse = await api.sandboxRecommend({
        driver: form.driver,
        circuit: form.circuit,
        starting_compound: form.startingCompound,
        starting_position: form.startingPosition,
        year: form.year,
        total_laps: totalLaps,
      })
      setResult({
        final_position: res.final_position,
        race_time_s: res.race_time_s,
        pit_stops: res.recommended_pit_stops,
        lap_by_lap: res.lap_by_lap,
        mode: 'recommend',
        confidence: res.confidence,
        strategy_overridden: res.strategy_overridden,
        ppo_note: res.ppo_note,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Recommendation failed')
    } finally {
      setIsLoading(false)
    }
  }

  // ── render ─────────────────────────────────────────────────────────────

  const stints = result ? buildStints(result.lap_by_lap) : []
  const positionsGained = result ? form.startingPosition - result.final_position : 0

  const chartData = result?.lap_by_lap.map(l => ({
    lap: l.lap,
    time: +l.lap_time.toFixed(3),
    compound: l.compound,
    tire_age: l.tire_age,
    position: l.position,
  })) ?? []

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg)', display: 'flex', flexDirection: 'column' }}>
      {/* Nav */}
      <nav
        style={{
          display: 'flex', alignItems: 'center', gap: 32,
          padding: '16px 32px', borderBottom: 'var(--border)',
          background: 'var(--color-surface)', flexShrink: 0,
        }}
      >
        <button
          onClick={() => navigate('/')}
          style={{
            fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 900,
            letterSpacing: '0.1em', color: 'var(--color-text)', background: 'none', border: 'none',
            cursor: 'pointer',
          }}
        >
          PIT<span style={{ color: 'var(--color-accent)' }}>IQ</span>
        </button>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-dim)', letterSpacing: '0.15em' }}>
          SANDBOX MODE
        </span>
        <button
          onClick={() => navigate('/optimizer')}
          style={{
            marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 10,
            color: 'var(--color-text-muted)', background: 'none', border: 'none',
            cursor: 'pointer', letterSpacing: '0.12em',
          }}
        >
          OPTIMIZER →
        </button>
      </nav>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* ── Left panel (40%) ───────────────────────────────────────── */}
        <div
          style={{
            width: '40%', flexShrink: 0,
            borderRight: 'var(--border)',
            overflowY: 'auto', padding: 28, display: 'flex', flexDirection: 'column', gap: 28,
          }}
        >
          {/* Step 1 */}
          <div>
            <SectionLabel n={1} label="Race Selection" />
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <FieldLabel>Circuit</FieldLabel>
                <Select
                  value={form.circuit}
                  onChange={e => setForm(prev => ({ ...prev, circuit: e.target.value, driver: '', startingPosition: 1 }))}
                  placeholder={loadingSeason ? 'Loading…' : 'Select circuit'}
                  disabled={loadingSeason}
                >
                  {activeCircuits.map(c => (
                    <option key={c.name} value={c.name}>{c.name}</option>
                  ))}
                </Select>
              </div>
              <div style={{ width: 90 }}>
                <FieldLabel>Year</FieldLabel>
                <Select
                  value={form.year}
                  onChange={e => { void handleYearChange(Number(e.target.value)) }}
                >
                  {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                </Select>
              </div>
            </div>

            {circuitInfo && (
              <div
                style={{
                  background: 'var(--color-surface-2)', padding: '10px 12px',
                  display: 'flex', gap: 20,
                }}
              >
                {[
                  { label: 'Length', value: `${circuitInfo.length_km} km` },
                  { label: 'Laps', value: circuitInfo.total_laps_typical },
                  { label: 'Type', value: circuitInfo.circuit_type },
                ].map(m => (
                  <div key={m.label}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>{m.label}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--color-text)', fontWeight: 600 }}>{m.value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Step 2 */}
          <div>
            <SectionLabel n={2} label="Driver Setup" />
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <FieldLabel>Driver</FieldLabel>
                <Select
                  value={form.driver}
                  onChange={e => setForm(prev => ({ ...prev, driver: e.target.value }))}
                  placeholder={loadingSeason ? 'Loading…' : 'Select driver'}
                  disabled={loadingSeason}
                >
                  {activeDrivers.map(d => (
                    <option key={d.code} value={d.code}>{d.code} — {d.full_name}</option>
                  ))}
                </Select>
              </div>
              <div style={{ width: 80 }}>
                <FieldLabel>Grid Pos</FieldLabel>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={form.startingPosition}
                  onChange={e => setForm(prev => ({ ...prev, startingPosition: Math.max(1, Math.min(20, Number(e.target.value))) }))}
                  style={{
                    width: '100%', padding: '8px 10px',
                    background: 'var(--color-surface-2)', border: 'var(--border)',
                    color: 'var(--color-text)', fontFamily: 'var(--font-mono)', fontSize: 12,
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            {loadingGrid && (
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.1em' }}>
                Loading grid…
              </div>
            )}

            {isMidGrid && (
              <div
                style={{
                  marginBottom: 10, padding: '7px 10px',
                  background: 'rgba(255,242,0,0.06)', border: '1px solid rgba(255,242,0,0.3)',
                  fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200',
                  letterSpacing: '0.04em', lineHeight: 1.5,
                }}
              >
                ⚠ Sandbox is most accurate for P1–P10. For mid-grid drivers, use{' '}
                <span
                  style={{ textDecoration: 'underline', cursor: 'pointer' }}
                  onClick={() => navigate('/optimizer')}
                >
                  Optimizer mode
                </span>
                {' '}which simulates all 20 rivals.
              </div>
            )}

            <div>
              <FieldLabel>Starting Compound</FieldLabel>
              <CompoundButtons value={form.startingCompound} onChange={c => setForm(prev => ({ ...prev, startingCompound: c }))} />
            </div>
          </div>

          {/* Step 3 */}
          <div>
            <SectionLabel n={3} label="Pit Stop Configuration" />

            {form.pitStops.map((stop, i) => (
              <PitStopRow
                key={i}
                stop={stop}
                index={i}
                totalLaps={totalLaps}
                onUpdate={(field, value) => updatePitStop(i, field, value)}
                onRemove={() => removePitStop(i)}
              />
            ))}

            {form.pitStops.length < 4 && (
              <button
                onClick={addPitStop}
                style={{
                  width: '100%', padding: '8px', marginTop: 4,
                  background: 'none', border: '1px dashed var(--color-border)',
                  color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)',
                  fontSize: 11, cursor: 'pointer', letterSpacing: '0.1em',
                }}
              >
                + ADD PIT STOP
              </button>
            )}

            {earlyPitStop && (
              <div
                style={{
                  marginTop: 6, padding: '6px 10px',
                  background: 'rgba(232,0,45,0.08)', border: '1px solid rgba(232,0,45,0.3)',
                  fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-accent)',
                  letterSpacing: '0.04em',
                }}
              >
                ✕ Pit stops before lap 5 are not allowed
              </div>
            )}

            {noTwoCompound && form.circuit && (
              <div
                style={{
                  marginTop: 6, padding: '6px 10px',
                  background: 'rgba(255,242,0,0.08)', border: '1px solid rgba(255,242,0,0.3)',
                  fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200',
                  letterSpacing: '0.05em',
                }}
              >
                ⚠ Two-compound rule requires at least one compound change
              </div>
            )}

            {isMultiStop && (
              <div
                style={{
                  marginTop: 6, padding: '6px 10px',
                  background: 'rgba(255,242,0,0.04)', border: '1px solid rgba(255,242,0,0.2)',
                  fontFamily: 'var(--font-body)', fontSize: 10, fontStyle: 'italic',
                  color: 'var(--color-text-dim)', lineHeight: 1.5,
                }}
              >
                Multi-stop strategies may show optimistic predictions in Sandbox mode.
                For realistic multi-car dynamics, use Optimizer mode.
              </div>
            )}
          </div>

          {/* Action buttons */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <button
              onClick={handleSimulate}
              disabled={!canSubmit || isLoading}
              style={{
                padding: '12px', background: canSubmit && !isLoading ? 'var(--color-accent)' : 'var(--color-surface-2)',
                border: 'none', color: '#fff', fontFamily: 'var(--font-mono)',
                fontSize: 12, fontWeight: 700, letterSpacing: '0.15em',
                cursor: canSubmit && !isLoading ? 'pointer' : 'not-allowed',
                transition: 'background 0.1s',
              }}
            >
              SIMULATE
            </button>
            <button
              onClick={handleRecommend}
              disabled={!canSubmit || isLoading}
              style={{
                padding: '12px', background: 'none',
                border: canSubmit && !isLoading ? '1px solid var(--color-accent)' : 'var(--border)',
                color: canSubmit && !isLoading ? 'var(--color-accent)' : 'var(--color-text-muted)',
                fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
                letterSpacing: '0.15em', cursor: canSubmit && !isLoading ? 'pointer' : 'not-allowed',
              }}
            >
              GET AI PICK
            </button>
            {error && (
              <div
                style={{
                  padding: '8px 10px', background: 'rgba(232,0,45,0.08)',
                  border: '1px solid rgba(232,0,45,0.3)',
                  fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-accent)',
                  letterSpacing: '0.05em',
                }}
              >
                {error}
              </div>
            )}
          </div>
        </div>

        {/* ── Right panel (60%) ──────────────────────────────────────── */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 28 }}>
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
            />
          ) : (
            <Placeholder />
          )}
        </div>
      </div>
    </div>
  )
}

// ── PitStopRow ─────────────────────────────────────────────────────────────

function PitStopRow({
  stop, index, totalLaps, onUpdate, onRemove,
}: {
  stop: PitStop
  index: number
  totalLaps: number
  onUpdate: (field: 'lap' | 'compound', value: string | number) => void
  onRemove: () => void
}) {
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
        padding: '8px 10px', background: 'var(--color-surface-2)',
        border: 'var(--border)',
      }}
    >
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', width: 16, flexShrink: 0 }}>
        P{index + 1}
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)' }}>L</span>
        <input
          type="number"
          min={2}
          max={totalLaps - 2}
          value={stop.lap}
          onChange={e => onUpdate('lap', Math.max(2, Math.min(totalLaps - 2, Number(e.target.value))))}
          style={{
            width: 48, padding: '4px 6px',
            background: 'var(--color-surface)', border: 'var(--border)',
            color: 'var(--color-text)', fontFamily: 'var(--font-mono)', fontSize: 12,
            outline: 'none',
          }}
        />
      </div>
      <CompoundButtons value={stop.compound} onChange={c => onUpdate('compound', c)} />
      <button
        onClick={onRemove}
        style={{
          marginLeft: 'auto', background: 'none', border: 'none',
          color: 'var(--color-text-muted)', cursor: 'pointer',
          fontFamily: 'var(--font-mono)', fontSize: 14, lineHeight: 1,
          padding: '0 4px',
        }}
      >
        ×
      </button>
    </div>
  )
}

// ── Placeholder ────────────────────────────────────────────────────────────

function Placeholder() {
  return (
    <div
      style={{
        height: '100%', minHeight: 400, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 16,
      }}
    >
      <div
        style={{
          width: 1, height: 80, background: 'linear-gradient(to bottom, transparent, var(--color-border))',
        }}
      />
      <span
        style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)',
          letterSpacing: '0.15em', textTransform: 'uppercase',
        }}
      >
        Configure a race on the left to run simulation
      </span>
    </div>
  )
}

// ── ResultView ─────────────────────────────────────────────────────────────

function ResultView({
  result, stints, chartData, startingPosition, positionsGained, totalLaps, mode,
  confidence, strategyOverridden, ppoNote, positionCapped,
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
}) {
  const times = chartData.map(d => d.time)
  const minT = Math.min(...times)
  const maxT = Math.max(...times)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      {/* Mode badge + confidence + ppo note */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em',
              color: mode === 'recommend' ? 'var(--color-accent)' : 'var(--color-text-muted)',
              border: `1px solid ${mode === 'recommend' ? 'var(--color-accent)' : 'var(--color-border)'}`,
              padding: '2px 8px',
            }}
          >
            {mode === 'recommend' ? 'PPO AGENT RECOMMENDATION' : 'USER STRATEGY SIMULATION'}
          </span>
          {confidence && (
            <span
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em',
                color: confidence === 'high' ? '#39B54A' : confidence === 'medium' ? '#FFF200' : 'var(--color-text-muted)',
              }}
            >
              {confidence.toUpperCase()} CONFIDENCE
            </span>
          )}
        </div>
        {ppoNote && (
          <span
            style={{
              fontFamily: 'var(--font-body)', fontSize: 11, fontStyle: 'italic',
              color: 'var(--color-text-dim)',
            }}
          >
            {ppoNote}
          </span>
        )}
      </div>

      {/* Position cap warning */}
      {positionCapped && (
        <div
          style={{
            padding: '10px 14px',
            background: 'rgba(255,242,0,0.06)',
            border: '1px solid rgba(255,242,0,0.35)',
            display: 'flex', gap: 10, alignItems: 'flex-start',
          }}
        >
          <span style={{ color: '#FFF200', fontSize: 14, flexShrink: 0 }}>⚠</span>
          <span
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200',
              letterSpacing: '0.04em', lineHeight: 1.5,
            }}
          >
            Position estimate adjusted — Sandbox mode cannot model rival counter-strategies
            for multi-stop scenarios. Use Optimizer mode for full 20-car simulation.
          </span>
        </div>
      )}

      {/* Override warning */}
      {strategyOverridden && (
        <div
          style={{
            padding: '10px 14px',
            background: 'rgba(255,242,0,0.06)',
            border: '1px solid rgba(255,242,0,0.35)',
            display: 'flex', gap: 10, alignItems: 'flex-start',
          }}
        >
          <span style={{ color: '#FFF200', fontSize: 14, flexShrink: 0 }}>⚠</span>
          <span
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200',
              letterSpacing: '0.04em', lineHeight: 1.5,
            }}
          >
            AI recommendation adjusted for this circuit — the model has limited training data here.
            Showing a rule-compliant corrected strategy.
          </span>
        </div>
      )}

      {/* Row 1 — stat cards */}
      <div style={{ display: 'flex', gap: 1 }}>
        <StatCard
          value={`P${Math.round(result.final_position)}`}
          label="Predicted Finish"
          accent={result.final_position <= 3}
        />
        <StatCard value={formatRaceTime(result.race_time_s)} label="Race Time" />
        <StatCard
          value={positionsGained >= 0 ? `+${positionsGained}` : `${positionsGained}`}
          label="Positions"
        />
        <StatCard value={result.pit_stops.length} label="Pit Stops" />
      </div>

      {/* Pit stop summary */}
      {result.pit_stops.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {result.pit_stops.map((p, i) => (
            <div
              key={i}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                background: 'var(--color-surface-2)', padding: '5px 10px',
                border: 'var(--border)',
              }}
            >
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)' }}>
                L{p.lap}
              </span>
              <TireBadge compound={p.compound} size="sm" showLabel={false} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: COMPOUND_COLORS[p.compound] }}>
                {p.compound}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Row 2 — stint bar */}
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 6 }}>
          Race Strategy
        </div>
        <StintBar stints={stints} totalLaps={totalLaps} />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>L1</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>L{totalLaps}</span>
        </div>
      </div>

      {/* Row 3 — lap time chart */}
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 8 }}>
          Lap Times
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            {/* Compound background areas */}
            {stints.map((s, i) => (
              <ReferenceArea
                key={i}
                x1={s.startLap}
                x2={s.endLap}
                fill={COMPOUND_COLORS[s.compound] ?? '#888'}
                fillOpacity={0.07}
              />
            ))}
            {/* Pit stop markers */}
            {result.pit_stops.map(p => (
              <ReferenceLine
                key={`pit-${p.lap}`}
                x={p.lap}
                stroke="var(--color-text-dim)"
                strokeDasharray="3 3"
                strokeWidth={1}
              />
            ))}
            <XAxis
              dataKey="lap"
              tick={{ fill: 'var(--color-text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={{ stroke: 'var(--color-border)' }}
              tickLine={false}
            />
            <YAxis
              domain={[minT - 0.5, maxT + 0.5]}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={false}
              tickLine={false}
              width={44}
              tickFormatter={v => v.toFixed(1)}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                borderRadius: 0, fontFamily: 'var(--font-mono)', fontSize: 11,
                color: 'var(--color-text)',
              }}
              formatter={(value: number, _: string, props: { payload?: { compound?: string; tire_age?: number; position?: number } }) => [
                `${value.toFixed(3)}s`,
                `${props.payload?.compound ?? ''} (age ${props.payload?.tire_age ?? 0})`,
              ]}
              labelFormatter={(lap: number) => `Lap ${lap} · P${chartData.find(d => d.lap === lap)?.position ?? '?'}`}
            />
            <Line
              dataKey="time"
              stroke="var(--color-text)"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: 'var(--color-accent)', stroke: 'none' }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Row 4 — stint table */}
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 8 }}>
          Stint Summary
        </div>
        <StintTable stints={stints} />
      </div>
    </div>
  )
}
