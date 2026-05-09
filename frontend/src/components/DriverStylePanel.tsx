import { useState, useEffect, useRef } from 'react'
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from 'recharts'
import type { DriverInfo } from '../api/types'

// ── constants ──────────────────────────────────────────────────────────────

const CLUSTER_LABELS: Record<number, string> = {
  0: 'Midfield veterans',
  1: 'Back-of-grid',
  2: 'Veteran outliers',
  3: 'Newer/backmarkers',
  4: 'Top-tier all-rounders',
}

const RADAR_AXES = ['Pace', 'Tire Saving', 'Wet Skill', 'Smoothness', 'Aggression', 'Consistency'] as const

// ── helpers ────────────────────────────────────────────────────────────────

function sv(d: DriverInfo, key: string): number | null {
  return d.style_vector[key] ?? null
}

function allSV(drivers: DriverInfo[], key: string): (number | null)[] {
  return drivers.map(d => sv(d, key))
}

function norm(value: number | null, allVals: (number | null)[], invert = false): number {
  if (value === null) return 0
  const valid = allVals.filter((v): v is number => v !== null)
  if (valid.length < 2) return 0.5
  const min = Math.min(...valid)
  const max = Math.max(...valid)
  if (max === min) return 0.5
  const n = (value - min) / (max - min)
  return invert ? 1 - n : n
}

function radarNorms(d: DriverInfo, normDrivers: DriverInfo[]): Record<typeof RADAR_AXES[number], number> {
  return {
    'Pace':        norm(sv(d, 'overall_pace_rank'),    allSV(normDrivers, 'overall_pace_rank'), true),
    'Tire Saving': norm(sv(d, 'tire_saving_coef'),     allSV(normDrivers, 'tire_saving_coef')),
    'Wet Skill':   norm(sv(d, 'wet_skill_delta'),      allSV(normDrivers, 'wet_skill_delta'), true),
    'Smoothness':  norm(sv(d, 'throttle_smoothness'),  allSV(normDrivers, 'throttle_smoothness')),
    'Aggression':  norm(sv(d, 'cornering_aggression'), allSV(normDrivers, 'cornering_aggression')),
    'Consistency': 0.5,
  }
}

function defaultComparison(ego: DriverInfo, allDrivers: DriverInfo[]): string {
  const egoRank = ego.style_vector['overall_pace_rank'] ?? 0
  const next = allDrivers
    .filter(d => d.code !== ego.code && (d.style_vector['overall_pace_rank'] ?? 0) > egoRank)
    .sort((a, b) => (a.style_vector['overall_pace_rank'] ?? 0) - (b.style_vector['overall_pace_rank'] ?? 0))
  return next[0]?.code ?? allDrivers.find(d => d.code !== ego.code)?.code ?? ''
}

function generateInsight(d1: DriverInfo, d2: DriverInfo): string {
  const r1 = d1.style_vector['overall_pace_rank'] ?? 0
  const r2 = d2.style_vector['overall_pace_rank'] ?? 0
  const t1 = d1.style_vector['tire_saving_coef'] ?? 0
  const t2 = d2.style_vector['tire_saving_coef'] ?? 0
  const paceDiff = r2 - r1
  const tireDiff = t1 - t2
  if (Math.abs(paceDiff) > 5) {
    const faster = paceDiff > 0 ? d1.code : d2.code
    return `${faster} is significantly faster overall (${Math.abs(paceDiff).toFixed(1)} rank positions).`
  }
  if (Math.abs(tireDiff) > 0.003) {
    const saver = tireDiff > 0 ? d1.code : d2.code
    return `${saver} is the better tire manager — extended stints will favour them.`
  }
  return `${d1.code} and ${d2.code} have similar style profiles.`
}

// ── MetricBar ──────────────────────────────────────────────────────────────

function MetricBar({
  label, value, normalized, accent, decimals = 3, note, showSign = false,
}: {
  label: string
  value: number | null
  normalized: number
  accent: boolean
  decimals?: number
  note?: string
  showSign?: boolean
}) {
  const filled = Math.round(Math.min(1, Math.max(0, normalized)) * 10)
  const barColor = accent ? 'var(--color-accent)' : 'rgba(255,255,255,0.35)'
  const display = value === null
    ? 'N/A'
    : (showSign && value > 0 ? '+' : '') + value.toFixed(decimals)
  return (
    <div style={{ marginBottom: 9 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 3 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          {label}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text)', fontWeight: 600 }}>
          {display}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 1 }}>
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} style={{ flex: 1, height: 3, background: i < filled ? barColor : 'var(--color-surface-2)' }} />
        ))}
      </div>
      {note && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', fontStyle: 'italic', marginTop: 2 }}>
          {note}
        </div>
      )}
    </div>
  )
}

// ── DriverColumn ───────────────────────────────────────────────────────────

function DriverColumn({ driver, isEgo, normDrivers }: {
  driver: DriverInfo
  isEgo: boolean
  normDrivers: DriverInfo[]
}) {
  const accent = isEgo ? 'var(--color-accent)' : 'var(--color-text-muted)'
  const paceVals  = allSV(normDrivers, 'overall_pace_rank')
  const tireVals  = allSV(normDrivers, 'tire_saving_coef')
  const wetVals   = allSV(normDrivers, 'wet_skill_delta')
  const smoothVals = allSV(normDrivers, 'throttle_smoothness')
  const aggrVals  = allSV(normDrivers, 'cornering_aggression')

  function Section({ label }: { label: string }) {
    return (
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: accent, letterSpacing: '0.12em', textTransform: 'uppercase', borderBottom: '1px solid var(--color-border)', paddingBottom: 4, marginBottom: 8, marginTop: 14 }}>
        {label}
      </div>
    )
  }

  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      {/* Driver header */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, letterSpacing: '0.05em', color: isEgo ? 'var(--color-accent)' : 'var(--color-text)', marginBottom: 2 }}>
          {driver.code}
        </div>
        <div style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--color-text-dim)', marginBottom: 4 }}>
          {driver.full_name}
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', marginBottom: 6 }}>
          {driver.team_2024}
        </div>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.08em', color: isEgo ? 'var(--color-accent)' : 'var(--color-text-muted)', border: `1px solid ${isEgo ? 'var(--color-accent)' : 'var(--color-border)'}`, padding: '1px 6px' }}>
          {CLUSTER_LABELS[driver.cluster] ?? `Cluster ${driver.cluster}`}
        </span>
      </div>

      {/* Style Metrics */}
      <Section label="Style Metrics" />
      <MetricBar label="Pace Rank" value={sv(driver, 'overall_pace_rank')} normalized={norm(sv(driver, 'overall_pace_rank'), paceVals, true)} accent={isEgo} decimals={1} note="lower = faster" />
      <MetricBar label="Tire Saving" value={sv(driver, 'tire_saving_coef')} normalized={norm(sv(driver, 'tire_saving_coef'), tireVals)} accent={isEgo} decimals={4} />
      <MetricBar label="Wet Skill Δ" value={sv(driver, 'wet_skill_delta')} normalized={norm(sv(driver, 'wet_skill_delta'), wetVals, true)} accent={isEgo} decimals={2} note="negative = faster in wet" showSign />
      <MetricBar label="Cornering Aggr." value={sv(driver, 'cornering_aggression')} normalized={norm(sv(driver, 'cornering_aggression'), aggrVals)} accent={isEgo} />
      <MetricBar label="Throttle Smooth." value={sv(driver, 'throttle_smoothness')} normalized={norm(sv(driver, 'throttle_smoothness'), smoothVals)} accent={isEgo} />

      {/* Sector Profile */}
      <Section label="Sector Profile" />
      {(['s1', 's2', 's3'] as const).map(s => {
        const val = sv(driver, `sector_relative_${s}`)
        return (
          <div key={s} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
              S{s.slice(1)} Relative
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: val === null ? 'var(--color-text-muted)' : val < 0 ? '#39B54A' : 'var(--color-text)' }}>
              {val === null ? 'N/A' : `${val >= 0 ? '+' : ''}${val.toFixed(2)}s`}
            </span>
          </div>
        )
      })}

      {/* Pace Trends */}
      <Section label="Pace Trends (s/lap)" />
      <div style={{ display: 'flex', gap: 10 }}>
        {(['soft', 'medium', 'hard'] as const).map(c => {
          const val = sv(driver, `pace_trend_${c}`)
          return (
            <div key={c} style={{ flex: 1 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', textTransform: 'uppercase', marginBottom: 3 }}>{c}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-text)', fontWeight: 600 }}>
                {val === null ? 'N/A' : val.toFixed(3)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── main panel ─────────────────────────────────────────────────────────────

interface Props {
  isOpen: boolean
  egoDriver: DriverInfo | null
  allDrivers: DriverInfo[]          // season-filtered list — used for dropdown
  normDrivers: DriverInfo[]         // full 33-driver roster — used for min/max normalisation
  onClose: () => void
}

export default function DriverStylePanel({ isOpen, egoDriver, allDrivers, normDrivers, onClose }: Props) {
  const [compCode, setCompCode] = useState<string>('')
  const panelRef = useRef<HTMLDivElement>(null)

  // Default comparison driver when ego changes
  useEffect(() => {
    if (!egoDriver || allDrivers.length === 0) return
    setCompCode(prev => {
      if (prev && prev !== egoDriver.code && allDrivers.some(d => d.code === prev)) return prev
      return defaultComparison(egoDriver, allDrivers)
    })
  }, [egoDriver?.code, allDrivers.length]) // eslint-disable-line

  // Escape to close
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  // Click-outside to close (using mousedown so click still fires on elements behind)
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [isOpen, onClose])

  const compDriver = allDrivers.find(d => d.code === compCode) ?? null

  // Build radar data — normalise against full 33-driver roster
  const base = normDrivers.length > 0 ? normDrivers : allDrivers
  const radarData = egoDriver
    ? RADAR_AXES.map(axis => {
        const egoR = radarNorms(egoDriver, base)
        const compR = compDriver ? radarNorms(compDriver, base) : null
        return { axis, ego: egoR[axis], comp: compR ? compR[axis] : 0 }
      })
    : []

  return (
    <div
      ref={panelRef}
      style={{
        position: 'fixed', top: 0, right: 0,
        width: 'min(600px, 100vw)', height: '100vh',
        background: 'var(--color-surface)', borderLeft: 'var(--border)',
        zIndex: 200, overflowY: 'auto',
        transform: isOpen ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        display: 'flex', flexDirection: 'column',
        boxShadow: '-8px 0 40px rgba(0,0,0,0.5)',
      }}
    >
      {/* Panel header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: 'var(--border)', flexShrink: 0, background: 'var(--color-surface)' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.2em', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
          Driver Style Inspector
        </span>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: '0 4px' }}
        >
          ×
        </button>
      </div>

      {egoDriver ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Comparison driver selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.12em', textTransform: 'uppercase', flexShrink: 0 }}>
              Compare with
            </span>
            <select
              value={compCode}
              onChange={e => setCompCode(e.target.value)}
              style={{ flex: 1, padding: '6px 8px', background: 'var(--color-surface-2)', border: 'var(--border)', color: 'var(--color-text)', fontFamily: 'var(--font-mono)', fontSize: 11, outline: 'none', appearance: 'none' }}
            >
              {allDrivers.filter(d => d.code !== egoDriver.code).map(d => (
                <option key={d.code} value={d.code}>{d.code} — {d.full_name}</option>
              ))}
            </select>
          </div>

          {/* Radar chart */}
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 8 }}>
              Style Comparison
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={radarData} outerRadius={100} margin={{ top: 16, right: 48, bottom: 16, left: 48 }}>
                <PolarGrid stroke="var(--color-border)" />
                <PolarAngleAxis
                  dataKey="axis"
                  tick={{ fill: 'var(--color-text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                />
                <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
                {compDriver && (
                  <Radar
                    name={compDriver.code}
                    dataKey="comp"
                    stroke="rgba(255,255,255,0.3)"
                    fill="rgba(255,255,255,0.12)"
                    fillOpacity={1}
                    strokeWidth={1}
                  />
                )}
                <Radar
                  name={egoDriver.code}
                  dataKey="ego"
                  stroke="var(--color-accent)"
                  fill="var(--color-accent)"
                  fillOpacity={0.28}
                  strokeWidth={1.5}
                />
              </RadarChart>
            </ResponsiveContainer>
            <div style={{ display: 'flex', gap: 20, justifyContent: 'center', marginTop: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 12, height: 12, background: 'var(--color-accent)', opacity: 0.7 }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>{egoDriver.code}</span>
              </div>
              {compDriver && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 12, height: 12, background: 'rgba(255,255,255,0.25)' }} />
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>{compDriver.code}</span>
                </div>
              )}
            </div>
          </div>

          {/* Key insight */}
          {compDriver && (
            <div style={{ padding: '10px 14px', background: 'rgba(232,0,45,0.05)', border: '1px solid rgba(232,0,45,0.15)' }}>
              <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, fontStyle: 'italic', color: 'var(--color-text-dim)', lineHeight: 1.6 }}>
                {generateInsight(egoDriver, compDriver)}
              </span>
            </div>
          )}

          {/* Two-column driver details */}
          <div style={{ display: 'flex', gap: 20 }}>
            <DriverColumn driver={egoDriver} isEgo={true} normDrivers={base} />
            {compDriver && (
              <DriverColumn driver={compDriver} isEgo={false} normDrivers={base} />
            )}
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)' }}>
          Select a driver to inspect
        </div>
      )}
    </div>
  )
}
