import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useStore } from '../store'
import type { HistoricalValidationResponse } from '../api/types'

// ── constants ──────────────────────────────────────────────────────────────

const YEARS = [2021, 2022, 2023, 2024, 2025]

const KNOWN_INCIDENTS: Record<string, Record<string, string>> = {
  '2024_Bahrain Grand Prix': {
    RIC: "Model overestimates pace — style features reflect his stronger 2021–2023 career average, not his 2024 form.",
  },
  '2024_Austrian Grand Prix': {
    RUS: "Russell won after a chaotic race — multiple safety cars and rival retirements are not modeled.",
    VER: "Verstappen suffered car damage after contact — mechanical failures are not modeled.",
    NOR: "Norris led before a late incident — race chaos is not modeled.",
  },
  '2024_British Grand Prix': {
    HAM: "Hamilton's win came from a well-timed safety car pit — safety cars are not modeled.",
    NOR: "Norris lost the lead to an off-strategy safety car — not modeled.",
  },
  '2024_Monaco Grand Prix': {
    LEC: "Leclerc won at his home race in a largely processional race — Monaco's unique overtaking dynamics reduce accuracy.",
  },
}

const CHAOTIC_RACE_NOTES: Record<string, string> = {
  '2024_Austrian Grand Prix': 'Austrian GP 2024 was one of the most chaotic races of the season — multiple safety cars, incidents, and retirements significantly affected the result.',
  '2024_British Grand Prix': 'British GP 2024 featured a pivotal safety car that reshuffled the entire field. Safety cars are not modeled.',
}

// ── helpers ────────────────────────────────────────────────────────────────

type BadgeInfo = { label: string; color: string; bg: string }

function deltaBadge(delta: number): BadgeInfo {
  const abs = Math.abs(delta)
  if (abs === 0) return { label: '✓',       color: '#39B54A',             bg: 'rgba(57,181,74,0.12)' }
  if (abs <= 2)  return { label: `+${abs}`,  color: '#39B54A',             bg: 'rgba(57,181,74,0.10)' }
  if (abs === 3) return { label: `±${abs}`,  color: '#FFF200',             bg: 'rgba(255,242,0,0.10)' }
  if (abs <= 5)  return { label: `±${abs}`,  color: '#FF8C00',             bg: 'rgba(255,140,0,0.10)' }
  return             { label: `±${abs}`,  color: 'var(--color-accent)', bg: 'rgba(232,0,45,0.10)' }
}

function accuracyColor(pct: number): string {
  if (pct >= 60) return '#39B54A'
  if (pct >= 40) return '#FFF200'
  return 'var(--color-accent)'
}

// ── sub-components ─────────────────────────────────────────────────────────

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 5 }}>
      {children}
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

function SectionCard({ number, title, children }: { number: string; title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: 'var(--color-surface)', borderLeft: '3px solid var(--color-accent)', borderRadius: 'var(--radius-card)', padding: '18px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, color: 'var(--color-accent)', letterSpacing: '0.05em' }}>{number}</span>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 900, color: 'var(--color-text)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{title}</span>
      </div>
      {children}
    </div>
  )
}

// Circular accuracy indicator card
function AccuracyStat({ value, label, color, icon }: { value: string; label: string; color: string; icon: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14,
      padding: '16px 18px',
      background: 'var(--color-surface)', border: 'var(--border)',
      borderRadius: 'var(--radius-card)', flex: 1,
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: '50%', flexShrink: 0,
        border: `2px solid ${color}`,
        background: `${color}18`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color }}>{icon}</span>
      </div>
      <div>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 900, color, lineHeight: 1, letterSpacing: '-0.01em' }}>
          {value}
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', letterSpacing: '0.14em', textTransform: 'uppercase', marginTop: 4 }}>
          {label}
        </div>
      </div>
    </div>
  )
}

// ── ResultRow ──────────────────────────────────────────────────────────────

function ResultRow({
  actualPos, simulatedPos, driverCode, zebra,
}: {
  actualPos: number
  simulatedPos: number | null
  driverCode: string
  zebra: boolean
}) {
  const delta = simulatedPos !== null ? simulatedPos - actualPos : null
  const badge = delta !== null ? deltaBadge(delta) : null
  const isPodium = actualPos <= 3

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      borderBottom: '1px solid rgba(255,255,255,0.04)',
      background: zebra ? 'rgba(255,255,255,0.015)' : 'transparent',
    }}>
      {/* Actual */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px', borderRight: '1px solid var(--color-border)' }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 10,
          color: isPodium ? 'var(--color-accent)' : 'var(--color-text-muted)',
          width: 26, flexShrink: 0, fontWeight: isPodium ? 700 : 400,
        }}>
          P{actualPos}
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700,
          color: isPodium ? 'var(--color-accent)' : 'var(--color-text)',
          letterSpacing: '0.04em',
        }}>
          {driverCode}
        </span>
      </div>

      {/* Simulated */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', width: 26, flexShrink: 0 }}>
          {simulatedPos !== null ? `P${simulatedPos}` : '—'}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: 'var(--color-text-dim)', letterSpacing: '0.04em' }}>
          {driverCode}
        </span>
        {badge && (
          <span style={{
            marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700,
            letterSpacing: '0.08em', color: badge.color, background: badge.bg,
            padding: '2px 7px', borderRadius: 3, flexShrink: 0,
            border: `1px solid ${badge.color}33`,
          }}>
            {badge.label}
          </span>
        )}
      </div>
    </div>
  )
}

// ── LargeDeltaCallout ──────────────────────────────────────────────────────

function LargeDeltaCallout({ deltas, raceKey }: { deltas: Array<{ driver: string; actual: number; simulated: number }>; raceKey: string }) {
  if (deltas.length === 0) return null
  const incidents = KNOWN_INCIDENTS[raceKey] ?? {}
  return (
    <div style={{ background: 'var(--color-surface)', borderLeft: '3px solid var(--color-accent)', borderRadius: 'var(--radius-card)', padding: '16px 20px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-accent)', letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 12 }}>
        ⚠ Largest Delta Drivers
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {deltas.map(d => {
          const note = incidents[d.driver]
            ?? `Simulated P${d.simulated} vs actual P${d.actual} — race incident or strategy deviation not captured.`
          return (
            <div key={d.driver} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: 'var(--color-text)', flexShrink: 0, width: 32 }}>
                {d.driver}
              </span>
              <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, fontStyle: 'italic', color: 'var(--color-text-dim)', lineHeight: 1.55 }}>
                {incidents[d.driver]
                  ? `P${d.simulated} vs actual P${d.actual} — ${incidents[d.driver]}`
                  : note}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── main ───────────────────────────────────────────────────────────────────

export default function Historical() {
  const navigate = useNavigate()
  const seasonCircuits = useStore(s => s.seasonCircuits)
  const setSeasonCircuits = useStore(s => s.setSeasonCircuits)

  const [year, setYear] = useState(2024)
  const [circuit, setCircuit] = useState('')
  const [loadingSeason, setLoadingSeason] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<HistoricalValidationResponse | null>(null)

  const activeCircuits = seasonCircuits[year] ?? []

  const fetchSeasonCircuits = useCallback(async (y: number) => {
    if (seasonCircuits[y]) return
    setLoadingSeason(true)
    try {
      const c = await api.getSeasonCircuits(y)
      setSeasonCircuits(y, c)
    } catch { /* leave empty */ }
    finally { setLoadingSeason(false) }
  }, [seasonCircuits, setSeasonCircuits])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void fetchSeasonCircuits(year) }, [])

  async function handleYearChange(newYear: number) {
    setYear(newYear)
    setCircuit(prev => (seasonCircuits[newYear] ?? []).some(c => c.name === prev) ? prev : '')
    setResult(null)
    await fetchSeasonCircuits(newYear)
  }

  async function handleRun() {
    if (!circuit) return
    setIsLoading(true); setError(null); setResult(null)
    try {
      setResult(await api.getHistoricalValidation(year, circuit))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Validation failed')
    } finally { setIsLoading(false) }
  }

  const raceKey = `${year}_${circuit}`
  const chaoticNote = CHAOTIC_RACE_NOTES[raceKey] ?? null
  const canRun = !!circuit && !isLoading

  const rows = result
    ? [...result.actual_results]
        .sort((a, b) => a.position - b.position)
        .map(a => {
          const sim = result.simulated_results.find(s => s.driver === a.driver)
          return { driver: a.driver, actual: a.position, simulated: sim !== undefined ? Math.round(sim.position) : null }
        })
    : []

  const largeDeltaRows = rows
    .filter(r => r.simulated !== null && Math.abs(r.simulated - r.actual) > 3)
    .map(r => ({ driver: r.driver, actual: r.actual, simulated: r.simulated! }))
    .sort((a, b) => Math.abs(b.simulated - b.actual) - Math.abs(a.simulated - a.actual))

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg)', display: 'flex', flexDirection: 'column' }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Nav */}
      <nav style={{ display: 'flex', alignItems: 'center', padding: '14px 28px', borderBottom: 'var(--border)', background: 'var(--color-surface)', flexShrink: 0, gap: 16 }}>
        <button onClick={() => navigate('/')} style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 900, letterSpacing: '0.1em', color: 'var(--color-text)', background: 'none', border: 'none', cursor: 'pointer' }}>
          PIT<span style={{ color: 'var(--color-accent)' }}>IQ</span>
        </button>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
          HISTORICAL VALIDATION
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 24 }}>
          {[{ label: 'SANDBOX', path: '/sandbox' }, { label: 'OPTIMIZER', path: '/optimizer' }].map(({ label, path }) => (
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

      {/* Body — two-panel layout */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Left panel — 38% */}
        <div style={{ width: '38%', flexShrink: 0, borderRight: 'var(--border)', overflowY: 'auto', padding: '20px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Heading */}
          <div style={{ paddingBottom: 4 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 900, letterSpacing: '0.06em', color: 'var(--color-text)', marginBottom: 6, lineHeight: 1.1 }}>
              SIMULATION<br />ACCURACY
            </div>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
              Compare PitIQ's GridRaceEnv simulation against official finishing positions for any historical race.
            </div>
          </div>

          {/* Section 01 — Race Selection */}
          <SectionCard number="01" title="Select Race">
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <div style={{ flex: 1 }}>
                <FieldLabel>Circuit</FieldLabel>
                <StyledSelect
                  value={circuit}
                  onChange={e => { setCircuit(e.target.value); setResult(null) }}
                  placeholder={loadingSeason ? 'Loading…' : 'Select circuit'}
                  disabled={loadingSeason}
                >
                  {activeCircuits.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                </StyledSelect>
              </div>
              <div style={{ width: 80 }}>
                <FieldLabel>Year</FieldLabel>
                <StyledSelect value={year} onChange={e => { void handleYearChange(Number(e.target.value)) }}>
                  {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                </StyledSelect>
              </div>
            </div>

            {chaoticNote && (
              <div style={{ padding: '8px 10px', background: 'rgba(255,242,0,0.05)', border: '1px solid rgba(255,242,0,0.25)', borderRadius: 4, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200', flexShrink: 0 }}>⚠</span>
                <span style={{ fontFamily: 'var(--font-body)', fontSize: 10, color: 'var(--color-text-dim)', lineHeight: 1.55 }}>{chaoticNote}</span>
              </div>
            )}
          </SectionCard>

          {/* Run button */}
          <button
            onClick={() => void handleRun()}
            disabled={!canRun}
            style={{
              height: 48,
              background: canRun ? 'var(--color-accent)' : 'var(--color-surface-2)',
              border: 'none', color: '#fff',
              fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
              letterSpacing: '0.15em', cursor: canRun ? 'pointer' : 'not-allowed',
              borderRadius: 'var(--radius-btn)', transition: 'background 0.1s',
            }}
          >
            RUN VALIDATION
          </button>

          {error && (
            <div style={{ padding: '8px 10px', background: 'rgba(232,0,45,0.08)', border: '1px solid rgba(232,0,45,0.3)', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-accent)', letterSpacing: '0.05em' }}>
              {error}
            </div>
          )}

          {/* Accuracy stats */}
          {result && !isLoading && (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
                  Accuracy — {result.year} {result.circuit}
                </div>
                <AccuracyStat
                  value={`${result.accuracy_pct_within_3.toFixed(0)}%`}
                  label="Within ±3 Positions"
                  color={accuracyColor(result.accuracy_pct_within_3)}
                  icon="✓"
                />
                <AccuracyStat
                  value={`${result.accuracy_pct_within_5.toFixed(0)}%`}
                  label="Within ±5 Positions"
                  color={accuracyColor(result.accuracy_pct_within_5)}
                  icon="✓"
                />
                <AccuracyStat
                  value={result.mean_absolute_delta.toFixed(1)}
                  label="Mean Position Error"
                  color="var(--color-text-dim)"
                  icon="Δ"
                />
              </div>

              {/* Large delta callout */}
              <LargeDeltaCallout deltas={largeDeltaRows} raceKey={raceKey} />

              {/* About */}
              <div style={{ padding: '12px 14px', background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 4 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 8 }}>
                  About This Simulation
                </div>
                <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--color-text-dim)', lineHeight: 1.7, margin: 0 }}>
                  Single-seed run of PitIQ's GridRaceEnv with behavior-cloned rival pit policies. The 70% within ±3 accuracy cited in project docs is a 5-seed average — single runs show 55–70%. Safety cars, mechanical failures, and driver errors are not modeled.
                </p>
              </div>
            </>
          )}

          {/* Info note always shown */}
          {!result && !isLoading && (
            <div style={{ padding: '10px 12px', background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 4 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.06em', lineHeight: 1.7 }}>
                Full 20-car GridRaceEnv simulation. Rivals use behavior-cloned pit policies. Compares simulated finishing order against official race results.
              </div>
            </div>
          )}

        </div>

        {/* Right panel — 62% */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>

          {/* Loading */}
          {isLoading && (
            <div style={{ height: '100%', minHeight: 400, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20 }}>
              <div style={{ width: 36, height: 36, border: '2px solid var(--color-border)', borderTopColor: 'var(--color-accent)', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-dim)', letterSpacing: '0.2em', textAlign: 'center' }}>
                SIMULATING {year} {circuit.replace(' Grand Prix', ' GP').toUpperCase()}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.1em' }}>
                Running full 20-car GridRaceEnv — 3–8 seconds
              </span>
            </div>
          )}

          {/* Results table */}
          {result && !isLoading && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {/* Table header */}
              <div style={{
                display: 'grid', gridTemplateColumns: '1fr 1fr',
                background: 'var(--color-surface)',
                border: 'var(--border)',
                borderBottom: '2px solid var(--color-border)',
                borderRadius: '8px 8px 0 0',
                overflow: 'hidden',
              }}>
                <div style={{ padding: '10px 16px', borderRight: '1px solid var(--color-border)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
                    Actual Result
                  </span>
                </div>
                <div style={{ padding: '10px 16px' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
                    Simulated Result
                  </span>
                </div>
              </div>

              {/* Rows */}
              <div style={{ border: 'var(--border)', borderTop: 'none', borderRadius: '0 0 8px 8px', overflow: 'hidden' }}>
                {rows.map((r, i) => (
                  <ResultRow
                    key={r.driver}
                    actualPos={r.actual}
                    simulatedPos={r.simulated}
                    driverCode={r.driver}
                    zebra={i % 2 !== 0}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Empty state */}
          {!result && !isLoading && (
            <div style={{ height: '100%', minHeight: 400, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
              <div style={{ width: 1, height: 60, background: 'linear-gradient(to bottom, transparent, var(--color-border))' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
                Select a race and run validation
              </span>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
