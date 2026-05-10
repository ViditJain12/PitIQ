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

const RADAR_AXES = ['Pace', 'Tire Saving', 'Wet Skill', 'Smoothness', 'Aggression'] as const

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
  const mn = Math.min(...valid)
  const mx = Math.max(...valid)
  if (mx === mn) return 0.5
  const n = (value - mn) / (mx - mn)
  return invert ? 1 - n : n
}

function radarNorms(d: DriverInfo, normDrivers: DriverInfo[]): Record<typeof RADAR_AXES[number], number> {
  return {
    'Pace':        norm(sv(d, 'overall_pace_rank'),    allSV(normDrivers, 'overall_pace_rank'), true),
    'Tire Saving': norm(sv(d, 'tire_saving_coef'),     allSV(normDrivers, 'tire_saving_coef')),
    'Wet Skill':   norm(sv(d, 'wet_skill_delta'),      allSV(normDrivers, 'wet_skill_delta'), true),
    'Smoothness':  norm(sv(d, 'throttle_smoothness'),  allSV(normDrivers, 'throttle_smoothness')),
    'Aggression':  norm(sv(d, 'cornering_aggression'), allSV(normDrivers, 'cornering_aggression')),
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
    return `${faster} is significantly faster overall (${Math.abs(paceDiff).toFixed(1)} rank positions). Strategy decisions should favour their pace window.`
  }
  if (Math.abs(tireDiff) > 0.003) {
    const saver = tireDiff > 0 ? d1.code : d2.code
    return `${saver} is the better tire manager — extended stints will work in their favour, allowing a later pit window.`
  }
  return `${d1.code} and ${d2.code} show similar style profiles. Strategy differences will come from circuit fit and starting position, not driver DNA.`
}

function fmt(v: number | null, dec = 3, sign = false): string {
  if (v === null) return 'N/A'
  const s = v.toFixed(dec)
  return sign && v > 0 ? `+${s}` : s
}

// ── SectionLabel ───────────────────────────────────────────────────────────

function SectionLabel({ label }: { label: string }) {
  return (
    <div style={{
      fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.18em',
      color: 'var(--color-text-muted)', textTransform: 'uppercase',
      borderBottom: '1px solid var(--color-border)', paddingBottom: 6, marginBottom: 10, marginTop: 18,
    }}>
      {label}
    </div>
  )
}

// ── ComparisonTable ────────────────────────────────────────────────────────

import type { ReactNode } from 'react'

function ComparisonTable({ rows, col1, col2 }: {
  rows: Array<{ label: ReactNode; v1: string; v2: string; v1Color?: string; v2Color?: string }>
  col1: string
  col2: string
}) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <td style={{ paddingBottom: 6, width: '52%' }} />
          <td style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-accent)', letterSpacing: '0.12em', paddingBottom: 6, paddingRight: 12, textAlign: 'right', width: '24%' }}>{col1}</td>
          <td style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-dim)', letterSpacing: '0.12em', paddingBottom: 6, textAlign: 'right', width: '24%' }}>{col2}</td>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} style={{ borderTop: '1px solid var(--color-border)' }}>
            <td style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.06em', padding: '6px 0', textTransform: 'uppercase' }}>
              {r.label}
            </td>
            <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: r.v1Color ?? 'var(--color-text)', textAlign: 'right', paddingRight: 12 }}>
              {r.v1}
            </td>
            <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: r.v2Color ?? 'var(--color-text-dim)', textAlign: 'right' }}>
              {r.v2}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ── main panel ─────────────────────────────────────────────────────────────

interface Props {
  isOpen: boolean
  egoDriver: DriverInfo | null
  allDrivers: DriverInfo[]
  normDrivers: DriverInfo[]
  onClose: () => void
}

export default function DriverStylePanel({ isOpen, egoDriver, allDrivers, normDrivers, onClose }: Props) {
  const [compCode, setCompCode] = useState<string>('')
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!egoDriver || allDrivers.length === 0) return
    setCompCode(prev => {
      if (prev && prev !== egoDriver.code && allDrivers.some(d => d.code === prev)) return prev
      return defaultComparison(egoDriver, allDrivers)
    })
  }, [egoDriver?.code, allDrivers.length]) // eslint-disable-line

  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  useEffect(() => {
    if (!isOpen) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [isOpen, onClose])

  const compDriver = allDrivers.find(d => d.code === compCode) ?? null
  const base = normDrivers.length > 0 ? normDrivers : allDrivers

  const radarData = egoDriver
    ? RADAR_AXES.map(axis => {
        const egoR = radarNorms(egoDriver, base)
        const compR = compDriver ? radarNorms(compDriver, base) : null
        return { axis, ego: egoR[axis], comp: compR ? compR[axis] : 0 }
      })
    : []

  const metricsRows = egoDriver && compDriver
    ? [
        {
          label: 'Pace Rank',
          v1: fmt(sv(egoDriver, 'overall_pace_rank'), 1),
          v2: fmt(sv(compDriver, 'overall_pace_rank'), 1),
          v1Color: (sv(egoDriver, 'overall_pace_rank') ?? 99) <= (sv(compDriver, 'overall_pace_rank') ?? 99) ? '#39B54A' : 'var(--color-text)',
        },
        {
          label: 'Tire Saving',
          v1: fmt(sv(egoDriver, 'tire_saving_coef'), 4),
          v2: fmt(sv(compDriver, 'tire_saving_coef'), 4),
        },
        {
          label: 'Wet Skill Δ',
          v1: fmt(sv(egoDriver, 'wet_skill_delta'), 2, true),
          v2: fmt(sv(compDriver, 'wet_skill_delta'), 2, true),
          v1Color: (sv(egoDriver, 'wet_skill_delta') ?? 0) < (sv(compDriver, 'wet_skill_delta') ?? 0) ? '#39B54A' : 'var(--color-text)',
        },
        {
          label: 'Cornering Aggr.',
          v1: fmt(sv(egoDriver, 'cornering_aggression'), 3),
          v2: fmt(sv(compDriver, 'cornering_aggression'), 3),
        },
        {
          label: 'Throttle Smooth.',
          v1: fmt(sv(egoDriver, 'throttle_smoothness'), 3),
          v2: fmt(sv(compDriver, 'throttle_smoothness'), 3),
          v1Color: (sv(egoDriver, 'throttle_smoothness') ?? 0) >= (sv(compDriver, 'throttle_smoothness') ?? 0) ? '#39B54A' : 'var(--color-text)',
        },
      ]
    : []

  const COMPOUND_DOT: Record<string, string> = { soft: '#E8002D', medium: '#FFF200', hard: '#FFFFFF' }
  const COMPOUND_ABBR: Record<string, string> = { soft: 'SOFT', medium: 'MED', hard: 'HARD' }

  const sectorRows = egoDriver && compDriver
    ? (['s1', 's2', 's3'] as const).map(s => {
        const v1 = sv(egoDriver, `sector_relative_${s}`)
        const v2 = sv(compDriver, `sector_relative_${s}`)
        return {
          label: `S${s.slice(1)}`,
          v1: fmt(v1, 3, true),
          v2: fmt(v2, 3, true),
          v1Color: v1 === null ? undefined : v1 < 0 ? '#39B54A' : 'var(--color-text)',
          v2Color: v2 === null ? undefined : v2 < 0 ? '#39B54A' : 'var(--color-text-dim)',
        }
      })
    : []

  const trendRows = egoDriver && compDriver
    ? (['soft', 'medium', 'hard'] as const).map(c => ({
        label: (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 7, height: 7, borderRadius: 1, background: COMPOUND_DOT[c], flexShrink: 0, display: 'inline-block' }} />
            {COMPOUND_ABBR[c]}
          </span>
        ),
        v1: fmt(sv(egoDriver, `pace_trend_${c}`), 3, true),
        v2: fmt(sv(compDriver, `pace_trend_${c}`), 3, true),
      }))
    : []

  return (
    <div
      ref={panelRef}
      style={{
        position: 'fixed', top: 0, right: 0,
        width: 'min(520px, 100vw)', height: '100vh',
        background: 'var(--color-surface)', borderLeft: 'var(--border)',
        zIndex: 200, overflowY: 'auto',
        transform: isOpen ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        boxShadow: '-8px 0 40px rgba(0,0,0,0.5)',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: 'var(--border)', background: 'var(--color-surface)', position: 'sticky', top: 0, zIndex: 1 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.2em', color: 'var(--color-text)', textTransform: 'uppercase', fontWeight: 700 }}>
          Driver Style Inspector
        </span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: '0 4px' }}>
          ×
        </button>
      </div>

      {egoDriver ? (
        <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column' }}>

          {/* Compare with dropdown */}
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 6 }}>
              Compare With
            </div>
            <select
              value={compCode}
              onChange={e => setCompCode(e.target.value)}
              style={{ width: '100%', padding: '7px 10px', background: 'var(--color-surface-2)', border: 'var(--border)', color: 'var(--color-text)', fontFamily: 'var(--font-mono)', fontSize: 11, outline: 'none', appearance: 'none', cursor: 'pointer' }}
            >
              {allDrivers.filter(d => d.code !== egoDriver.code).map(d => (
                <option key={d.code} value={d.code}>{d.code} — {d.full_name}</option>
              ))}
            </select>
          </div>

          {/* Style Comparison label */}
          <SectionLabel label="Style Comparison" />

          {/* Radar chart */}
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={radarData} outerRadius={90} margin={{ top: 12, right: 44, bottom: 12, left: 44 }}>
              <PolarGrid stroke="var(--color-border)" />
              <PolarAngleAxis
                dataKey="axis"
                tick={{ fill: 'var(--color-text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              />
              <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
              {compDriver && (
                <Radar name={compDriver.code} dataKey="comp" stroke="rgba(255,255,255,0.25)" fill="rgba(255,255,255,0.08)" fillOpacity={1} strokeWidth={1} />
              )}
              <Radar name={egoDriver.code} dataKey="ego" stroke="var(--color-accent)" fill="var(--color-accent)" fillOpacity={0.25} strokeWidth={1.5} />
            </RadarChart>
          </ResponsiveContainer>

          {/* Legend */}
          <div style={{ display: 'flex', gap: 20, justifyContent: 'center', marginTop: 2, marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 10, height: 10, background: 'var(--color-accent)', opacity: 0.7 }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>{egoDriver.code}</span>
            </div>
            {compDriver && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 10, height: 10, background: 'rgba(255,255,255,0.2)' }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>{compDriver.code}</span>
              </div>
            )}
          </div>

          {/* Insight */}
          {compDriver && (
            <div style={{ padding: '10px 14px', background: 'rgba(232,0,45,0.05)', border: '1px solid rgba(232,0,45,0.15)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                <span style={{ fontSize: 11 }}>⚡</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-accent)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                  {Math.abs((sv(egoDriver, 'overall_pace_rank') ?? 0) - (sv(compDriver, 'overall_pace_rank') ?? 0)) < 5
                    ? 'Similar style profile'
                    : 'Style divergence detected'}
                </span>
              </div>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, fontStyle: 'italic', color: 'var(--color-text-dim)', lineHeight: 1.6, margin: 0 }}>
                {generateInsight(egoDriver, compDriver)}
              </p>
            </div>
          )}

          {/* Style Metrics Comparison */}
          {metricsRows.length > 0 && (
            <>
              <SectionLabel label="Style Metrics Comparison" />
              <ComparisonTable rows={metricsRows} col1={egoDriver.code} col2={compDriver!.code} />
            </>
          )}

          {/* Sector Profile */}
          {sectorRows.length > 0 && (
            <>
              <SectionLabel label="Sector Profile (s/l)" />
              <ComparisonTable rows={sectorRows} col1={egoDriver.code} col2={compDriver!.code} />
            </>
          )}

          {/* Pace Trends */}
          {trendRows.length > 0 && (
            <>
              <SectionLabel label="Pace Trends (s/lap)" />
              <ComparisonTable rows={trendRows} col1={egoDriver.code} col2={compDriver!.code} />
            </>
          )}

        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)' }}>
          Select a driver to inspect
        </div>
      )}
    </div>
  )
}
