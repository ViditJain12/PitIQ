import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ComposedChart,
  BarChart,
  Bar,
  Cell,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { MapPin, Flag, Sparkles, Target, TrendingUp } from 'lucide-react'
import { api } from '../api/client'
import { useStore } from '../store'
import type { LapData, RivalPrediction, UndercutWindow } from '../api/types'
import DriverStylePanel from '../components/DriverStylePanel'
import { CircuitMap } from '../components/CircuitMap'
import RaceReplay from '../components/RaceReplay'

// ── constants ──────────────────────────────────────────────────────────────

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: '#E8002D', MEDIUM: '#FFF200', HARD: '#FFFFFF',
}
const COMPOUNDS = ['SOFT', 'MEDIUM', 'HARD'] as const
const YEARS = [2021, 2022, 2023, 2024, 2025]

const LOADING_MESSAGES = [
  'RUNNING GRID SIMULATION',
  'MODELING RIVAL BEHAVIOR',
  'COMPUTING UNDERCUT WINDOWS',
  'OPTIMIZING YOUR STRATEGY',
]

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

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function interpolateRivalPosition(rival: RivalPrediction, totalLaps: number): number[] {
  const pits = [...rival.pit_history].sort((a, b) => a.lap - b.lap)
  type KF = { lap: number; pos: number }
  const frames: KF[] = [{ lap: 1, pos: rival.starting_position }]
  for (const pit of pits) {
    const t = pit.lap / totalLaps
    const basePos = lerp(rival.starting_position, rival.final_position, t)
    frames.push({ lap: pit.lap, pos: Math.min(20, basePos + 4) })
  }
  frames.push({ lap: totalLaps, pos: rival.final_position })
  frames.sort((a, b) => a.lap - b.lap)
  const result: number[] = []
  for (let lap = 1; lap <= totalLaps; lap++) {
    let lo = frames[0], hi = frames[frames.length - 1]
    for (let f = 0; f < frames.length - 1; f++) {
      if (frames[f].lap <= lap && frames[f + 1].lap >= lap) {
        lo = frames[f]; hi = frames[f + 1]; break
      }
    }
    const t = lo.lap === hi.lap ? 0 : (lap - lo.lap) / (hi.lap - lo.lap)
    result.push(Math.max(1, Math.min(20, lerp(lo.pos, hi.pos, t))))
  }
  return result
}

function buildGridChartData(
  egoDriver: string,
  egoLapByLap: LapData[],
  rivals: RivalPrediction[],
  totalLaps: number,
): Array<Record<string, number>> {
  const egoPos: Record<number, number> = {}
  for (const l of egoLapByLap) egoPos[l.lap] = l.position
  const rivalPos: Record<string, number[]> = {}
  for (const r of rivals) {
    if (r.driver !== egoDriver) {
      rivalPos[r.driver] = interpolateRivalPosition(r, totalLaps)
    }
  }
  const data: Array<Record<string, number>> = []
  for (let lap = 1; lap <= totalLaps; lap++) {
    const point: Record<string, number> = { lap }
    point[egoDriver] = egoPos[lap] ?? 0
    for (const r of rivals) {
      if (r.driver !== egoDriver) {
        point[r.driver] = rivalPos[r.driver][lap - 1] ?? 0
      }
    }
    data.push(point)
  }
  return data
}

// ── types ──────────────────────────────────────────────────────────────────

interface OptimizerResult {
  mode: 'recommend' | 'simulate'
  ego_driver: string
  final_position: number
  race_time_s: number
  positions_gained: number
  pit_stops: Array<{ lap: number; compound: string }>
  lap_by_lap: LapData[]
  rival_predictions: RivalPrediction[]
  undercut_windows: UndercutWindow[]
  confidence?: string
  strategy_rationale?: string
  total_laps: number
}

interface FormState {
  circuit: string
  year: number
  driver: string
  startingPosition: number
  startingCompound: string
}

// ── chart constants ────────────────────────────────────────────────────────

const AXIS_STYLE = { fill: 'var(--color-text-dim)', fontSize: 10, fontFamily: 'var(--font-mono)' }
const GRID_STYLE = { stroke: 'var(--color-border)', strokeOpacity: 0.3 }
const TOOLTIP_STYLE = { background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 0, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text)' }

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

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 5 }}>
      {children}
    </div>
  )
}

function CompoundButtons({ value, onChange }: { value: string; onChange: (c: string) => void }) {
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

function StyledSelect({
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
          style={{ flex: s.laps.length / totalLaps, background: COMPOUND_COLORS[s.compound] ?? '#888', opacity: 0.85 }}
        />
      ))}
    </div>
  )
}

// ── GridPositionTracker ────────────────────────────────────────────────────

function GridPositionTracker({
  egoDriver, chartData, rivals, pitStops,
}: {
  egoDriver: string
  chartData: Array<Record<string, number>>
  rivals: RivalPrediction[]
  pitStops: Array<{ lap: number; compound: string }>
}) {
  if (chartData.length === 0) return null
  const allDrivers = Object.keys(chartData[0]).filter(k => k !== 'lap')
  const rivalDrivers = allDrivers.filter(d => d !== egoDriver)

  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 8 }}>
        Grid Position Tracker
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <XAxis
            dataKey="lap"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
            axisLine={{ stroke: 'var(--color-border)' }}
            tickLine={false}
          />
          <YAxis
            domain={[1, 20]}
            reversed
            tick={{ fill: 'var(--color-text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
            axisLine={false}
            tickLine={false}
            width={28}
            tickCount={5}
            tickFormatter={(v: number) => `P${v}`}
          />
          <Tooltip
            content={(props) => {
              if (!props.active || !props.payload?.length) return null
              const sorted = [...props.payload]
                .filter(p => typeof p.value === 'number' && (p.value as number) > 0)
                .sort((a, b) => (a.value as number) - (b.value as number))
                .slice(0, 6)
              return (
                <div style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                  <div style={{ color: 'var(--color-text-muted)', marginBottom: 4, letterSpacing: '0.1em' }}>
                    LAP {props.label as number}
                  </div>
                  {sorted.map(e => (
                    <div
                      key={e.dataKey as string}
                      style={{ display: 'flex', gap: 8, padding: '1px 0', color: e.dataKey === egoDriver ? 'var(--color-accent)' : 'var(--color-text-dim)' }}
                    >
                      <span style={{ width: 24 }}>P{Math.round(e.value as number)}</span>
                      <span>{e.dataKey as string}</span>
                    </div>
                  ))}
                </div>
              )
            }}
          />
          {pitStops.map(p => (
            <ReferenceLine
              key={`pit-${p.lap}`}
              x={p.lap}
              stroke="var(--color-accent)"
              strokeDasharray="3 3"
              strokeWidth={1}
              strokeOpacity={0.4}
            />
          ))}
          {rivalDrivers.map(driver => (
            <Line
              key={driver}
              type="monotone"
              dataKey={driver}
              stroke="rgba(255,255,255,0.1)"
              strokeWidth={1}
              dot={false}
              isAnimationActive={false}
            />
          ))}
          <Line
            type="monotone"
            dataKey={egoDriver}
            stroke="var(--color-accent)"
            strokeWidth={2.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <div style={{ display: 'flex', gap: 20, marginTop: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 20, height: 2.5, background: 'var(--color-accent)' }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>{egoDriver}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 20, height: 1, background: 'rgba(255,255,255,0.2)' }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>RIVALS ({rivals.length})</span>
        </div>
      </div>
    </div>
  )
}

// ── RivalPanel ─────────────────────────────────────────────────────────────

// Reconstruct compound stints from pit history. All rivals start on SOFT.
function buildRivalStints(pitHistory: Array<{ lap: number; compound: string }>): string[] {
  const compounds = ['SOFT', ...pitHistory.map(p => p.compound)]
  return compounds
}

function RivalPanel({ rivals, egoDriver }: { rivals: RivalPrediction[]; egoDriver: string }) {
  const sorted = [...rivals].sort((a, b) => a.final_position - b.final_position)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
          Rival Predictions
        </span>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 10, fontStyle: 'italic', color: 'var(--color-text-muted)' }}>
          ±2–3 position accuracy
        </span>
      </div>

      {/* Table header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '36px 44px 1fr 1fr',
        gap: '0 12px',
        padding: '6px 12px',
        borderBottom: '1px solid var(--color-border)',
        marginBottom: 2,
      }}>
        {['POS', 'DRIVER', 'COMPOUND SEQ', 'PIT STOPS'].map(h => (
          <span key={h} style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
            {h}
          </span>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {sorted.map(r => {
          const isEgo = r.driver === egoDriver
          const stintCompounds = buildRivalStints(r.pit_history)
          const pitLaps = r.pit_history.map(p => `L${p.lap}`)

          return (
            <div
              key={r.driver}
              style={{
                display: 'grid',
                gridTemplateColumns: '36px 44px 1fr 1fr',
                gap: '0 12px',
                alignItems: 'center',
                padding: '7px 12px',
                background: isEgo ? 'rgba(232,0,45,0.08)' : 'var(--color-surface-2)',
                border: isEgo ? '1px solid rgba(232,0,45,0.25)' : '1px solid transparent',
              }}
            >
              {/* POS */}
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
                color: isEgo ? 'var(--color-accent)' : 'var(--color-text-dim)',
              }}>
                P{Math.round(r.final_position)}
              </span>

              {/* Driver */}
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
                color: isEgo ? 'var(--color-accent)' : 'var(--color-text)',
                letterSpacing: '0.04em',
              }}>
                {r.driver}
              </span>

              {/* Compound sequence — colored circles, one per stint */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {stintCompounds.map((cmp, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {i > 0 && (
                      <div style={{ width: 10, height: 1, background: 'var(--color-border)' }} />
                    )}
                    <div
                      title={cmp}
                      style={{
                        width: 10, height: 10, borderRadius: '50%',
                        background: COMPOUND_COLORS[cmp] ?? '#888',
                        flexShrink: 0,
                        opacity: isEgo ? 1 : 0.85,
                        boxShadow: isEgo ? `0 0 4px ${COMPOUND_COLORS[cmp] ?? '#888'}66` : 'none',
                      }}
                    />
                  </div>
                ))}
              </div>

              {/* Pit stop laps */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                {pitLaps.length > 0 ? pitLaps.map((label, i) => (
                  <span
                    key={i}
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700,
                      color: isEgo ? 'var(--color-accent)' : 'var(--color-text-dim)',
                      background: isEgo ? 'rgba(232,0,45,0.12)' : 'var(--color-surface)',
                      border: `1px solid ${isEgo ? 'rgba(232,0,45,0.3)' : 'var(--color-border)'}`,
                      padding: '1px 6px',
                      borderRadius: 3,
                      letterSpacing: '0.06em',
                    }}
                  >
                    {label}
                  </span>
                )) : (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
                    no stops
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── UndercutPanel ──────────────────────────────────────────────────────────

function UndercutPanel({ windows }: { windows: UndercutWindow[] }) {
  if (windows.length === 0) return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
      No undercut windows detected
    </div>
  )
  return (
    <div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
        <thead>
          <tr style={{ borderBottom: 'var(--border)' }}>
            {['Lap', 'Rival', 'Gap', 'Tire Age', 'Type'].map(h => (
              <th key={h} style={{ textAlign: 'left', padding: '5px 8px', color: 'var(--color-text-muted)', fontWeight: 400, fontSize: 8, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {windows.map((w, i) => {
            const isTight = w.gap_s < 0.5
            const typeLabel = isTight ? 'TIGHT BATTLE' : 'UNDERCUT'
            const typeColor = isTight ? '#FF8C00' : '#FFF200'
            return (
              <tr key={i} style={{ borderBottom: '1px solid var(--color-border)', background: i % 2 === 0 ? 'var(--color-surface-2)' : 'transparent' }}>
                <td style={{ padding: '6px 8px', color: '#FFF200', fontWeight: 700 }}>L{w.lap}</td>
                <td style={{ padding: '6px 8px', color: 'var(--color-text)' }}>{w.rival_driver}</td>
                <td style={{ padding: '6px 8px', color: 'var(--color-text-dim)' }}>{w.gap_s.toFixed(2)}s</td>
                <td style={{ padding: '6px 8px', color: 'var(--color-text-dim)' }}>{w.rival_tire_age}L</td>
                <td style={{ padding: '6px 8px' }}>
                  <span style={{ color: typeColor, fontSize: 8, letterSpacing: '0.06em' }}>{typeLabel}</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── SimulateModal ──────────────────────────────────────────────────────────

function SimulateModal({
  totalLaps, startingCompound, onSubmit, onClose,
}: {
  totalLaps: number
  startingCompound: string
  onSubmit: (pitStops: Array<{ lap: number; compound: string }>) => void
  onClose: () => void
}) {
  const [pitStops, setPitStops] = useState<Array<{ lap: number; compound: string }>>([])

  function addStop() {
    if (pitStops.length >= 4) return
    setPitStops(prev => [...prev, { lap: Math.round(totalLaps / 2), compound: 'HARD' }])
  }

  function updateStop(i: number, field: 'lap' | 'compound', value: string | number) {
    setPitStops(prev => {
      const stops = [...prev]
      stops[i] = { ...stops[i], [field]: value }
      return stops
    })
  }

  function removeStop(i: number) {
    setPitStops(prev => prev.filter((_, idx) => idx !== i))
  }

  const earlyStop = pitStops.find(p => p.lap < 5)
  const noCompoundChange = pitStops.length === 0 || pitStops.every(p => p.compound === startingCompound)
  const canSubmit = !earlyStop && !noCompoundChange

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        style={{ background: 'var(--color-surface)', border: 'var(--border)', padding: 28, width: 440, maxHeight: '80vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 20 }}
        onClick={e => e.stopPropagation()}
      >
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: 'var(--color-text)', letterSpacing: '0.1em', marginBottom: 6 }}>
            CONFIGURE PIT STRATEGY
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.08em' }}>
            Starting on{' '}
            <span style={{ color: COMPOUND_COLORS[startingCompound], fontWeight: 700 }}>{startingCompound}</span>
            {' '}— {totalLaps} laps total
          </div>
        </div>

        <div>
          {pitStops.map((stop, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, padding: '8px 10px', background: 'var(--color-surface-2)', border: 'var(--border)' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', width: 16, flexShrink: 0 }}>P{i + 1}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)' }}>L</span>
                <input
                  type="number"
                  min={2}
                  max={totalLaps - 2}
                  value={stop.lap}
                  onChange={e => updateStop(i, 'lap', Math.max(2, Math.min(totalLaps - 2, Number(e.target.value))))}
                  style={{ width: 48, padding: '4px 6px', background: 'var(--color-surface)', border: 'var(--border)', color: 'var(--color-text)', fontFamily: 'var(--font-mono)', fontSize: 12, outline: 'none' }}
                />
              </div>
              <CompoundButtons value={stop.compound} onChange={c => updateStop(i, 'compound', c)} />
              <button
                onClick={() => removeStop(i)}
                style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 14, lineHeight: 1, padding: '0 4px' }}
              >
                ×
              </button>
            </div>
          ))}

          {pitStops.length < 4 && (
            <button
              onClick={addStop}
              style={{ width: '100%', padding: '8px', marginTop: 4, background: 'none', border: '1px dashed var(--color-border)', color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer', letterSpacing: '0.1em' }}
            >
              + ADD PIT STOP
            </button>
          )}

          {earlyStop && (
            <div style={{ marginTop: 8, padding: '6px 10px', background: 'rgba(232,0,45,0.08)', border: '1px solid rgba(232,0,45,0.3)', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-accent)', letterSpacing: '0.04em' }}>
              ✕ Pit stops before lap 5 are not allowed
            </div>
          )}
          {noCompoundChange && (
            <div style={{ marginTop: 8, padding: '6px 10px', background: 'rgba(255,242,0,0.08)', border: '1px solid rgba(255,242,0,0.3)', fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200', letterSpacing: '0.05em' }}>
              ⚠ {pitStops.length === 0 ? 'Add at least one pit stop (two-compound rule)' : 'Two-compound rule requires at least one compound change'}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => onSubmit(pitStops)}
            disabled={!canSubmit}
            style={{ flex: 1, padding: '12px', background: canSubmit ? 'var(--color-accent)' : 'var(--color-surface-2)', border: 'none', color: '#fff', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, letterSpacing: '0.15em', cursor: canSubmit ? 'pointer' : 'not-allowed' }}
          >
            RUN SIMULATION
          </button>
          <button
            onClick={onClose}
            style={{ padding: '12px 20px', background: 'none', border: 'var(--border)', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12, cursor: 'pointer', letterSpacing: '0.1em' }}
          >
            CANCEL
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Placeholder ────────────────────────────────────────────────────────────

function Placeholder() {
  return (
    <div style={{ height: '100%', minHeight: 400, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
      <div style={{ width: 1, height: 60, background: 'linear-gradient(to bottom, transparent, var(--color-border))' }} />
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
        Configure race setup to optimize strategy
      </span>
    </div>
  )
}

// ── AI Insight from rationale ──────────────────────────────────────────────

function generateRationaleInsights(rationale: string | undefined, stints: Stint[], pitStops: Array<{ lap: number; compound: string }>) {
  const insights: Array<{ icon: 'Target' | 'TrendingUp' | 'Sparkles'; title: string; body: string }> = []

  if (rationale) {
    insights.push({ icon: 'Sparkles', title: 'Strategy Rationale', body: rationale })
  }

  if (stints.length > 0) {
    const stintsWithAvg = stints.map(s => ({ ...s, avgTime: avg(s.laps.map(l => l.lap_time)) }))
    const bestStint = stintsWithAvg.reduce((best, s) => s.avgTime < best.avgTime ? s : best)
    insights.push({
      icon: 'Target',
      title: `Optimal ${bestStint.compound} Stint`,
      body: `The ${bestStint.compound.toLowerCase()} stint from L${bestStint.startLap}–L${bestStint.endLap} delivers the best average pace at ${bestStint.avgTime.toFixed(3)}s/lap.`,
    })
  }

  if (pitStops.length > 0) {
    insights.push({
      icon: 'TrendingUp',
      title: 'Pit Window',
      body: `First pit on lap ${pitStops[0].lap} → ${pitStops[0].compound.toLowerCase()} tires.${pitStops.length > 1 ? ` Second on lap ${pitStops[1].lap} → ${pitStops[1].compound.toLowerCase()}.` : ''}`,
    })
  }

  return insights
}

const INSIGHT_ICONS = {
  Target: <Target size={13} color="var(--color-accent)" />,
  TrendingUp: <TrendingUp size={13} color="#27F4D2" />,
  Sparkles: <Sparkles size={13} color="#A78BFA" />,
}

// ── ResultsView ────────────────────────────────────────────────────────────

type ChartTab = 'laptime' | 'pacedelta'

function ResultsView({
  result, stints, chartData, gridChartData, referenceResult,
  circuitSvgPoints, circuitViewBox,
}: {
  result: OptimizerResult
  stints: Stint[]
  chartData: Array<{ lap: number; time: number; compound: string; tire_age: number; position: number }>
  gridChartData: Array<Record<string, number>>
  referenceResult: OptimizerResult | null
  circuitSvgPoints?: string | null
  circuitViewBox?: string | null
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
  const bestLap = Math.min(...times)
  const deltaData = chartData.map(d => ({ ...d, delta: +(d.time - bestLap).toFixed(3) }))

  const refByLap: Record<number, number> = {}
  referenceResult?.lap_by_lap.forEach(l => { refByLap[l.lap] = +l.lap_time.toFixed(3) })
  const mergedChartData = chartData.map(d => ({ ...d, refTime: refByLap[d.lap] ?? null }))

  const positionsGained = result.positions_gained
  const insights = generateRationaleInsights(result.strategy_rationale, stints, result.pit_stops)

  const hasReference = referenceResult !== null && referenceResult.mode !== result.mode

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Mode badge + confidence */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.15em', color: result.mode === 'recommend' ? 'var(--color-accent)' : 'var(--color-text-muted)', border: `1px solid ${result.mode === 'recommend' ? 'var(--color-accent)' : 'var(--color-border)'}`, padding: '2px 8px', borderRadius: 3 }}>
          {result.mode === 'recommend' ? 'PPO OPTIMIZER RECOMMENDATION' : 'USER STRATEGY SIMULATION'}
        </span>
        {result.confidence && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em', color: result.confidence === 'high' ? '#39B54A' : result.confidence === 'medium' ? '#FFF200' : 'var(--color-text-muted)' }}>
            {result.confidence.toUpperCase()} CONFIDENCE
          </span>
        )}
      </div>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
        {[
          { value: `P${Math.round(result.final_position)}`, label: 'Predicted Finish', accent: result.final_position <= 3 },
          { value: formatRaceTime(result.race_time_s), label: 'Race Time', accent: false },
          { value: positionsGained >= 0 ? `+${positionsGained}` : String(positionsGained), label: 'Positions', accent: false },
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
        <StintBar stints={stints} totalLaps={result.total_laps} />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>LAP 1</span>
          {result.pit_stops.map(p => (
            <span key={p.lap} style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-dim)' }}>L{p.lap}</span>
          ))}
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>LAP {result.total_laps}</span>
        </div>
      </div>

      {/* Tabbed chart */}
      <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)', padding: '16px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--color-border)' }}>
            {([
              { key: 'laptime', label: 'LAP TIME' },
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
                  if (!hasReference) { setShowHint(h => !h) }
                  else { setShowHint(false); setShowRef(r => !r) }
                }}
                style={{
                  padding: '5px 12px',
                  background: showRef && hasReference ? 'rgba(232,0,45,0.08)' : 'transparent',
                  border: showRef && hasReference ? '1px solid var(--color-accent)' : 'var(--border)',
                  borderRadius: 'var(--radius-btn)', fontFamily: 'var(--font-mono)', fontSize: 9,
                  color: !hasReference ? 'var(--color-text-muted)' : showRef ? 'var(--color-accent)' : 'var(--color-text-dim)',
                  opacity: !hasReference ? 0.5 : 1,
                  cursor: !hasReference ? 'help' : 'pointer',
                  letterSpacing: '0.1em',
                }}
              >
                {showRef && hasReference ? 'HIDE REFERENCE ▾' : 'SHOW REFERENCE ▾'}
              </button>
              {showHint && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 8px)', right: 0, zIndex: 50,
                  background: 'var(--color-surface-2)', border: '1px solid var(--color-border)',
                  borderRadius: 0, padding: 12, width: 240,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                }}>
                  <div style={{
                    position: 'absolute', top: -5, right: 14,
                    width: 8, height: 8, background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border)', borderRight: 'none', borderBottom: 'none',
                    transform: 'rotate(45deg)',
                  }} />
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-accent)', letterSpacing: '0.12em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span>⚡</span> HOW TO USE SHOW REFERENCE
                  </div>
                  {['1. Click OPTIMIZE STRATEGY to get AI recommendation', '2. Click SIMULATE MY STRATEGY with your own strategy', '3. Toggle SHOW REFERENCE to compare them'].map((step, i) => (
                    <div key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-dim)', lineHeight: 1.7 }}>
                      {step}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* LAP TIME */}
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
                  if (name === 'refTime') return [`${value.toFixed(3)}s`, referenceResult?.mode === 'recommend' ? 'AI Reference' : 'User Reference']
                  return [`${value.toFixed(3)}s`, `${props.payload?.compound ?? ''} (age ${props.payload?.tire_age ?? 0})`]
                }) as any}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                labelFormatter={((lap: number) => `Lap ${lap} · P${chartData.find(d => d.lap === lap)?.position ?? '?'}`) as any}
              />
              <Line dataKey="time" stroke="var(--color-text)" strokeWidth={1.5} dot={false} activeDot={{ r: 3, fill: 'var(--color-accent)', stroke: 'none' }} />
              {showRef && hasReference && (
                <Line dataKey="refTime" stroke="#555" strokeWidth={1} strokeDasharray="5 3" dot={false} activeDot={{ r: 2, fill: '#555', stroke: 'none' }} connectNulls />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        )}

        {/* PACE DELTA */}
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
                content={(props) => {
                  if (!props.active || !props.payload?.length) return null
                  const d = props.payload[0]?.payload as { lap: number; delta: number; compound: string; position: number }
                  return (
                    <div style={{ ...TOOLTIP_STYLE, padding: '8px 12px' }}>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', marginBottom: 4 }}>
                        LAP {d.lap} · P{d.position}
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: COMPOUND_COLORS[d.compound] ?? 'var(--color-text)', letterSpacing: '0.02em' }}>
                        +{d.delta.toFixed(3)}s
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', marginTop: 3 }}>
                        vs best lap · {d.compound}
                      </div>
                    </div>
                  )
                }}
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

      {/* Bottom row: Grid Position Tracker (left) + Strategy Rationale + Undercut Windows (right) */}
      <div style={{ display: 'grid', gridTemplateColumns: '60% 40%', gap: 12 }}>
        {/* Grid Position Tracker */}
        <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)', padding: '16px 18px' }}>
          <GridPositionTracker
            egoDriver={result.ego_driver}
            chartData={gridChartData}
            rivals={result.rival_predictions}
            pitStops={result.pit_stops}
          />
        </div>

        {/* Right column: Strategy Rationale + Undercut Windows */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Strategy Rationale */}
          <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)', padding: '16px 18px', flex: '0 0 auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Sparkles size={12} color="var(--color-accent)" />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
                AI Insight
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {insights.map((ins, i) => (
                <div key={i} style={{ background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 4, padding: '10px 12px' }}>
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

          {/* Undercut Windows */}
          <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)', padding: '16px 18px', flex: 1 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: result.undercut_windows.length > 0 ? '#FFF200' : 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 10 }}>
              {result.undercut_windows.length > 0 ? `⚡ UNDERCUT WINDOWS (${result.undercut_windows.length})` : 'UNDERCUT WINDOWS'}
            </div>
            <UndercutPanel windows={result.undercut_windows} />
          </div>
        </div>
      </div>

      {/* Race Replay */}
      {circuitSvgPoints && (
        <RaceReplay
          circuitSvgPoints={circuitSvgPoints}
          circuitViewBox={circuitViewBox ?? '0 0 200 120'}
          totalLaps={result.total_laps}
          egoDriver={result.ego_driver}
          egoLapByLap={result.lap_by_lap}
          rivalPredictions={result.rival_predictions}
        />
      )}

      {/* Rival Predictions — full width */}
      <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)', padding: '16px 18px' }}>
        <RivalPanel rivals={result.rival_predictions} egoDriver={result.ego_driver} />
      </div>
    </div>
  )
}

// ── main ───────────────────────────────────────────────────────────────────

export default function Optimizer() {
  const navigate = useNavigate()
  const allDrivers = useStore(s => s.drivers)
  const seasonDrivers = useStore(s => s.seasonDrivers)
  const seasonCircuits = useStore(s => s.seasonCircuits)
  const setSeasonDrivers = useStore(s => s.setSeasonDrivers)
  const setSeasonCircuits = useStore(s => s.setSeasonCircuits)

  const [form, setForm] = useState<FormState>({
    circuit: '', year: 2024, driver: '', startingPosition: 1, startingCompound: 'SOFT',
  })
  const [grid, setGrid] = useState<string[]>([])
  const [loadingGrid, setLoadingGrid] = useState(false)
  const [loadingSeason, setLoadingSeason] = useState(false)
  const [result, setResult] = useState<OptimizerResult | null>(null)
  const [recommendResult, setRecommendResult] = useState<OptimizerResult | null>(null)
  const [simulateResult, setSimulateResult] = useState<OptimizerResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [showStylePanel, setShowStylePanel] = useState(false)
  const [loadingMsgIdx, setLoadingMsgIdx] = useState(0)
  const loadingInterval = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (isLoading) {
      setLoadingMsgIdx(0)
      loadingInterval.current = setInterval(() => {
        setLoadingMsgIdx(i => (i + 1) % LOADING_MESSAGES.length)
      }, 1500)
    } else {
      if (loadingInterval.current) { clearInterval(loadingInterval.current); loadingInterval.current = null }
    }
    return () => { if (loadingInterval.current) clearInterval(loadingInterval.current) }
  }, [isLoading])

  const activeDrivers = seasonDrivers[form.year] ?? []
  const activeCircuits = seasonCircuits[form.year] ?? []
  const circuitInfo = activeCircuits.find(c => c.name === form.circuit) ?? null
  const totalLaps = circuitInfo?.total_laps_typical ?? 58

  const fetchSeasonData = useCallback(async (year: number) => {
    const needsD = !seasonDrivers[year], needsC = !seasonCircuits[year]
    if (!needsD && !needsC) return
    setLoadingSeason(true)
    try {
      const [d, c] = await Promise.all([
        needsD ? api.getSeasonDrivers(year) : Promise.resolve(seasonDrivers[year]),
        needsC ? api.getSeasonCircuits(year) : Promise.resolve(seasonCircuits[year]),
      ])
      if (needsD) setSeasonDrivers(year, d)
      if (needsC) setSeasonCircuits(year, c)
    } catch { /* leave empty */ }
    finally { setLoadingSeason(false) }
  }, [seasonDrivers, seasonCircuits, setSeasonDrivers, setSeasonCircuits])

  useEffect(() => { void fetchSeasonData(form.year) }, []) // eslint-disable-line

  const handleYearChange = useCallback(async (newYear: number) => {
    await fetchSeasonData(newYear)
    setForm(prev => ({
      ...prev,
      year: newYear,
      circuit: (seasonCircuits[newYear] ?? []).some(c => c.name === prev.circuit) ? prev.circuit : '',
      driver: (seasonDrivers[newYear] ?? []).some(d => d.code === prev.driver) ? prev.driver : '',
      startingPosition: 1,
    }))
    setGrid([])
  }, [fetchSeasonData, seasonCircuits, seasonDrivers])

  const fetchGrid = useCallback(async (circuit: string, year: number) => {
    if (!circuit) return
    setLoadingGrid(true)
    try { setGrid(await api.getHistoricalGrid(year, circuit)) }
    catch { setGrid([]) }
    finally { setLoadingGrid(false) }
  }, [])

  useEffect(() => {
    if (form.circuit && form.year) void fetchGrid(form.circuit, form.year)
  }, [form.circuit, form.year, fetchGrid])

  useEffect(() => {
    if (!form.driver || grid.length === 0) return
    const pos = grid.indexOf(form.driver)
    if (pos !== -1) setForm(prev => ({ ...prev, startingPosition: pos + 1 }))
  }, [form.driver, grid])

  function buildGridParams() {
    let startingGrid = grid.length > 0 ? [...grid] : activeDrivers.map(d => d.code).slice(0, 20)
    if (startingGrid.length < 20) {
      const extra = activeDrivers.map(d => d.code).filter(c => !startingGrid.includes(c))
      startingGrid = [...startingGrid, ...extra].slice(0, 20)
    }
    startingGrid = startingGrid.slice(0, 20)
    const targetIdx = form.startingPosition - 1
    const currentIdx = startingGrid.indexOf(form.driver)
    if (currentIdx !== -1 && currentIdx !== targetIdx && targetIdx >= 0 && targetIdx < startingGrid.length) {
      const displaced = startingGrid[targetIdx]
      startingGrid[targetIdx] = form.driver
      startingGrid[currentIdx] = displaced
    }
    const startingCompounds: Record<string, string> = {}
    for (const driver of startingGrid) {
      startingCompounds[driver] = driver === form.driver ? form.startingCompound : 'SOFT'
    }
    return { startingGrid, startingCompounds }
  }

  const canSubmit = !!form.circuit && !!form.driver

  async function handleRecommend() {
    setIsLoading(true); setError(null)
    const { startingGrid, startingCompounds } = buildGridParams()
    try {
      const res = await api.optimizerRecommend({
        ego_driver: form.driver,
        circuit: form.circuit,
        year: form.year,
        ego_starting_position: form.startingPosition,
        starting_compound: form.startingCompound,
        total_laps: totalLaps,
        starting_grid: startingGrid,
        starting_compounds: startingCompounds,
      })
      const r: OptimizerResult = {
        mode: 'recommend',
        ego_driver: res.ego_driver,
        final_position: res.predicted_finish_position,
        race_time_s: res.race_time_s,
        positions_gained: res.positions_gained,
        pit_stops: res.recommended_strategy,
        lap_by_lap: res.ego_lap_by_lap,
        rival_predictions: res.rival_predictions,
        undercut_windows: res.undercut_windows_identified,
        confidence: res.confidence,
        strategy_rationale: res.strategy_rationale,
        total_laps: totalLaps,
      }
      setResult(r)
      setRecommendResult(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Optimizer failed')
    } finally { setIsLoading(false) }
  }

  async function handleSimulate(pitStops: Array<{ lap: number; compound: string }>) {
    setShowModal(false); setIsLoading(true); setError(null)
    const { startingGrid, startingCompounds } = buildGridParams()
    try {
      const res = await api.optimizerSimulate({
        ego_driver: form.driver,
        circuit: form.circuit,
        year: form.year,
        ego_starting_position: form.startingPosition,
        starting_compound: form.startingCompound,
        total_laps: totalLaps,
        starting_grid: startingGrid,
        starting_compounds: startingCompounds,
        pit_stops: pitStops,
      })
      const r: OptimizerResult = {
        mode: 'simulate',
        ego_driver: res.ego_driver,
        final_position: res.ego_predicted_position,
        race_time_s: res.ego_race_time_s,
        positions_gained: res.positions_gained,
        pit_stops: res.ego_strategy,
        lap_by_lap: res.ego_lap_by_lap,
        rival_predictions: res.rival_predictions,
        undercut_windows: res.undercut_windows_identified,
        total_laps: totalLaps,
      }
      setResult(r)
      setSimulateResult(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Simulation failed')
    } finally { setIsLoading(false) }
  }

  const stints = result ? buildStints(result.lap_by_lap) : []
  const chartData = result?.lap_by_lap.map(l => ({
    lap: l.lap, time: +l.lap_time.toFixed(3),
    compound: l.compound, tire_age: l.tire_age, position: l.position,
  })) ?? []
  const gridChartData = result
    ? buildGridChartData(result.ego_driver, result.lap_by_lap, result.rival_predictions, result.total_laps)
    : []

  // Reference result is the "other" mode's result for comparison
  const referenceResult = result?.mode === 'simulate' ? recommendResult : simulateResult

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg)', display: 'flex', flexDirection: 'column' }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Nav */}
      <nav style={{ display: 'flex', alignItems: 'center', padding: '14px 28px', borderBottom: 'var(--border)', background: 'var(--color-surface)', flexShrink: 0, gap: 16 }}>
        <button onClick={() => navigate('/')} style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 900, letterSpacing: '0.1em', color: 'var(--color-text)', background: 'none', border: 'none', cursor: 'pointer' }}>
          PIT<span style={{ color: 'var(--color-accent)' }}>IQ</span>
        </button>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
          OPTIMIZER MODE
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 24 }}>
          {[{ label: 'SANDBOX', path: '/sandbox' }, { label: 'HISTORICAL', path: '/historical' }].map(({ label, path }) => (
            <button
              key={path}
              onClick={() => navigate(path)}
              onMouseEnter={e => {
                const el = e.currentTarget as HTMLElement
                el.style.color = '#FFFFFF'
                el.style.textShadow = '0 0 8px rgba(255,255,255,0.8), 0 0 20px rgba(255,255,255,0.4)'
              }}
              onMouseLeave={e => {
                const el = e.currentTarget as HTMLElement
                el.style.color = 'var(--color-text-muted)'
                el.style.textShadow = 'none'
              }}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.12em', transition: 'color 0.15s, text-shadow 0.15s' }}
            >
              {label} →
            </button>
          ))}
        </div>
      </nav>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Left panel — 38% */}
        <div style={{ width: '38%', flexShrink: 0, borderRight: 'var(--border)', overflowY: 'auto', padding: '20px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Section 01 — Race Selection */}
          <SectionCard number="01" title="Race Selection">
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <FieldLabel>Circuit</FieldLabel>
                <StyledSelect
                  value={form.circuit}
                  onChange={e => setForm(prev => ({ ...prev, circuit: e.target.value, driver: '', startingPosition: 1 }))}
                  placeholder={loadingSeason ? 'Loading…' : 'Select circuit'}
                  disabled={loadingSeason}
                >
                  {activeCircuits.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                </StyledSelect>
              </div>
              <div style={{ width: 80 }}>
                <FieldLabel>Year</FieldLabel>
                <StyledSelect value={form.year} onChange={e => { void handleYearChange(Number(e.target.value)) }}>
                  {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                </StyledSelect>
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
                  <div style={{ background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 4, padding: '10px 12px', marginTop: 8 }}>
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
            <div style={{ display: 'flex', gap: 8 }}>
              <div style={{ flex: 1 }}>
                <FieldLabel>Driver</FieldLabel>
                <StyledSelect
                  value={form.driver}
                  onChange={e => setForm(prev => ({ ...prev, driver: e.target.value }))}
                  placeholder={loadingSeason ? 'Loading…' : 'Select driver'}
                  disabled={loadingSeason}
                >
                  {activeDrivers.map(d => <option key={d.code} value={d.code}>{d.code} — {d.full_name}</option>)}
                </StyledSelect>
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
            {loadingGrid && (
              <div style={{ marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.1em' }}>Loading grid…</div>
            )}
          </SectionCard>

          {/* Section 03 — Starting Compound */}
          <SectionCard number="03" title="Starting Compound">
            <CompoundButtons value={form.startingCompound} onChange={c => setForm(prev => ({ ...prev, startingCompound: c }))} />
          </SectionCard>

          {/* Action buttons */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
            <button
              onClick={() => void handleRecommend()}
              disabled={!canSubmit || isLoading}
              style={{ height: 48, background: canSubmit && !isLoading ? 'var(--color-accent)' : 'var(--color-surface-2)', border: 'none', color: '#fff', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, letterSpacing: '0.15em', cursor: canSubmit && !isLoading ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 'var(--radius-btn)' }}
            >
              <Flag size={15} /> OPTIMIZE STRATEGY
            </button>
            <button
              onClick={() => setShowModal(true)}
              disabled={!canSubmit || isLoading}
              style={{ height: 48, background: 'transparent', border: canSubmit && !isLoading ? '1px solid var(--color-accent)' : 'var(--border)', color: canSubmit && !isLoading ? 'var(--color-accent)' : 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, letterSpacing: '0.15em', cursor: canSubmit && !isLoading ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 'var(--radius-btn)' }}
            >
              SIMULATE MY STRATEGY
            </button>
            {error && (
              <div style={{ padding: '8px 10px', background: 'rgba(232,0,45,0.08)', border: '1px solid rgba(232,0,45,0.3)', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-accent)', letterSpacing: '0.05em' }}>
                {error}
              </div>
            )}
          </div>

          {/* Info note */}
          <div style={{ padding: '10px 12px', background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 4 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.06em', lineHeight: 1.7 }}>
              Full 20-car grid simulation. Rivals modeled with behavior-cloned style policies. Undercut &amp; overcut windows detected automatically.
            </div>
          </div>
        </div>

        {/* Right panel — 62% */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {isLoading ? (
            <div style={{ height: '100%', minHeight: 400, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20 }}>
              <div style={{ width: 36, height: 36, border: '2px solid var(--color-border)', borderTopColor: 'var(--color-accent)', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-dim)', letterSpacing: '0.2em' }}>
                {LOADING_MESSAGES[loadingMsgIdx]}
              </span>
            </div>
          ) : result ? (
            <ResultsView
              result={result}
              stints={stints}
              chartData={chartData}
              gridChartData={gridChartData}
              referenceResult={referenceResult ?? null}
              circuitSvgPoints={circuitInfo?.svg_points ?? null}
              circuitViewBox={circuitInfo?.viewBox ?? null}
            />
          ) : (
            <Placeholder />
          )}
        </div>
      </div>

      {showModal && (
        <SimulateModal
          totalLaps={totalLaps}
          startingCompound={form.startingCompound}
          onSubmit={pitStops => void handleSimulate(pitStops)}
          onClose={() => setShowModal(false)}
        />
      )}

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
