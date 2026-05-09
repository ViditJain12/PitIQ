import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useStore } from '../store'
import type { HistoricalValidationResponse } from '../api/types'
import StatCard from '../components/StatCard'

// ── constants ──────────────────────────────────────────────────────────────

const YEARS = [2021, 2022, 2023, 2024, 2025]

// Known race incidents / model limitations per (year, circuit)
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
    LEC: "Leclerc won at his home race in a largely processional race — strategy deviations and Monaco's unique overtaking dynamics reduce simulation accuracy.",
  },
}

// Races with known high stochasticity / model mismatch — show a warning banner
const CHAOTIC_RACE_NOTES: Record<string, string> = {
  '2024_Austrian Grand Prix': 'Austrian GP 2024 was one of the most chaotic races of the season — multiple safety cars, incidents, and retirements significantly affected the result. Expect lower simulation accuracy.',
  '2024_British Grand Prix': 'British GP 2024 featured a pivotal safety car that reshuffled the entire field. Safety cars are not modeled — expect higher position deltas.',
}

// ── helpers ────────────────────────────────────────────────────────────────

function StyledSelect({
  value, onChange, placeholder, children, disabled, style: extraStyle,
}: React.SelectHTMLAttributes<HTMLSelectElement> & { placeholder?: string }) {
  return (
    <select
      value={value ?? ''}
      onChange={onChange}
      disabled={disabled}
      style={{
        padding: '9px 12px',
        background: 'var(--color-surface-2)', border: 'var(--border)',
        color: value ? 'var(--color-text)' : 'var(--color-text-muted)',
        fontFamily: 'var(--font-mono)', fontSize: 12,
        cursor: disabled ? 'not-allowed' : 'pointer', outline: 'none', appearance: 'none',
        minWidth: 220,
        ...extraStyle,
      }}
    >
      {placeholder && <option value="" disabled>{placeholder}</option>}
      {children}
    </select>
  )
}

type BadgeInfo = { label: string; color: string; bg: string }

function deltaBadge(delta: number): BadgeInfo {
  const abs = Math.abs(delta)
  if (abs === 0) return { label: '✓',        color: '#39B54A',              bg: 'rgba(57,181,74,0.10)' }
  if (abs <= 2)  return { label: `±${abs}`,  color: '#39B54A',              bg: 'rgba(57,181,74,0.08)' }
  if (abs === 3) return { label: '±3',        color: '#FFF200',              bg: 'rgba(255,242,0,0.08)' }
  if (abs <= 5)  return { label: `±${abs}`,  color: '#FF8C00',              bg: 'rgba(255,140,0,0.08)' }
  return             { label: `±${abs} ✗`,  color: 'var(--color-accent)',  bg: 'rgba(232,0,45,0.08)' }
}

function accuracyColor(pct: number): string {
  if (pct >= 60) return '#39B54A'
  if (pct >= 40) return '#FFF200'
  return 'var(--color-accent)'
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
      display: 'grid', gridTemplateColumns: '1fr 1fr',
      borderBottom: '1px solid rgba(255,255,255,0.04)',
      background: zebra ? 'var(--color-surface-2)' : 'transparent',
    }}>
      {/* Actual */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px', borderRight: '1px solid var(--color-border)' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-muted)', width: 28, flexShrink: 0 }}>
          P{actualPos}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: isPodium ? 'var(--color-accent)' : 'var(--color-text)' }}>
          {driverCode}
        </span>
      </div>

      {/* Simulated */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-muted)', width: 28, flexShrink: 0 }}>
          {simulatedPos !== null ? `P${simulatedPos}` : '—'}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: 'var(--color-text-dim)' }}>
          {driverCode}
        </span>
        {badge && (
          <span style={{
            marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
            letterSpacing: '0.06em', color: badge.color, background: badge.bg,
            padding: '2px 8px', flexShrink: 0,
          }}>
            {badge.label}
          </span>
        )}
      </div>
    </div>
  )
}

// ── LargeDeltaCallout ──────────────────────────────────────────────────────

function LargeDeltaCallout({
  deltas, raceKey,
}: {
  deltas: Array<{ driver: string; actual: number; simulated: number }>
  raceKey: string
}) {
  if (deltas.length === 0) return null
  const incidents = KNOWN_INCIDENTS[raceKey] ?? {}
  return (
    <div style={{ padding: '16px 20px', background: 'rgba(232,0,45,0.04)', border: '1px solid rgba(232,0,45,0.2)' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-accent)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 10 }}>
        ⚠ Large Delta Drivers
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {deltas.map(d => {
          const note = incidents[d.driver]
            ?? `${d.driver} simulated P${d.simulated} vs actual P${d.actual} — race incident or strategy deviation not captured by simulation.`
          return (
            <div key={d.driver}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--color-text)' }}>
                {d.driver}
              </span>
              {incidents[d.driver] && (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-muted)' }}>
                  {': Simulated P'}{d.simulated}{' vs Actual P'}{d.actual}{' — '}
                </span>
              )}
              <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, fontStyle: 'italic', color: 'var(--color-text-dim)' }}>
                {note}
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
      const res = await api.getHistoricalValidation(year, circuit)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Validation failed')
    } finally {
      setIsLoading(false)
    }
  }

  const raceKey = `${year}_${circuit}`
  const chaoticNote = CHAOTIC_RACE_NOTES[raceKey] ?? null

  // Merge actual + simulated, sorted by actual finishing position
  const rows = result
    ? [...result.actual_results]
        .sort((a, b) => a.position - b.position)
        .map(a => {
          const sim = result.simulated_results.find(s => s.driver === a.driver)
          return {
            driver: a.driver,
            actual: a.position,
            simulated: sim !== undefined ? Math.round(sim.position) : null,
          }
        })
    : []

  const largeDeltaRows = rows
    .filter(r => r.simulated !== null && Math.abs(r.simulated - r.actual) > 5)
    .map(r => ({ driver: r.driver, actual: r.actual, simulated: r.simulated! }))
    .sort((a, b) => Math.abs(b.simulated - b.actual) - Math.abs(a.simulated - a.actual))

  const canRun = !!circuit && !isLoading

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg)', display: 'flex', flexDirection: 'column' }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Nav */}
      <nav style={{ display: 'flex', alignItems: 'center', gap: 32, padding: '16px 32px', borderBottom: 'var(--border)', background: 'var(--color-surface)', flexShrink: 0 }}>
        <button onClick={() => navigate('/')} style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 900, letterSpacing: '0.1em', color: 'var(--color-text)', background: 'none', border: 'none', cursor: 'pointer' }}>
          PIT<span style={{ color: 'var(--color-accent)' }}>IQ</span>
        </button>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-dim)', letterSpacing: '0.15em' }}>
          HISTORICAL VALIDATION
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 20 }}>
          <button onClick={() => navigate('/sandbox')} style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.12em' }}>
            SANDBOX →
          </button>
          <button onClick={() => navigate('/optimizer')} style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.12em' }}>
            OPTIMIZER →
          </button>
        </div>
      </nav>

      {/* Body */}
      <div style={{ flex: 1, maxWidth: 900, width: '100%', margin: '0 auto', padding: '40px 32px', display: 'flex', flexDirection: 'column', gap: 36 }}>

        {/* Heading */}
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 900, letterSpacing: '0.06em', color: 'var(--color-text)', marginBottom: 6 }}>
            SIMULATION ACCURACY
          </div>
          <div style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
            Compare PitIQ's GridRaceEnv simulation against official finishing positions for any historical race.
          </div>
        </div>

        {/* ── Race picker ──────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
            Select Race
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'stretch', flexWrap: 'wrap' }}>
            <StyledSelect
              value={circuit}
              onChange={e => { setCircuit(e.target.value); setResult(null) }}
              placeholder={loadingSeason ? 'Loading…' : 'Select circuit'}
              disabled={loadingSeason}
            >
              {activeCircuits.map(c => (
                <option key={c.name} value={c.name}>{c.name}</option>
              ))}
            </StyledSelect>

            <StyledSelect
              value={year}
              onChange={e => { void handleYearChange(Number(e.target.value)) }}
              style={{ minWidth: 100 }}
            >
              {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
            </StyledSelect>

            <button
              onClick={() => void handleRun()}
              disabled={!canRun}
              style={{
                padding: '9px 24px',
                background: canRun ? 'var(--color-accent)' : 'var(--color-surface-2)',
                border: 'none', color: '#fff',
                fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
                letterSpacing: '0.15em', cursor: canRun ? 'pointer' : 'not-allowed',
                transition: 'background 0.1s',
                flexShrink: 0,
              }}
            >
              RUN VALIDATION
            </button>
          </div>

          {error && (
            <div style={{ padding: '8px 12px', background: 'rgba(232,0,45,0.08)', border: '1px solid rgba(232,0,45,0.3)', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-accent)', letterSpacing: '0.05em' }}>
              {error}
            </div>
          )}

          {chaoticNote && (
            <div style={{ padding: '10px 14px', background: 'rgba(255,242,0,0.05)', border: '1px solid rgba(255,242,0,0.25)', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#FFF200', flexShrink: 0 }}>⚠</span>
              <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--color-text-dim)', lineHeight: 1.6 }}>
                {chaoticNote}
              </span>
            </div>
          )}
        </div>

        {/* ── Loading ──────────────────────────────────────────────────────── */}
        {isLoading && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '48px 0' }}>
            <div style={{ width: 32, height: 32, border: '2px solid var(--color-border)', borderTopColor: 'var(--color-accent)', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-dim)', letterSpacing: '0.2em', textAlign: 'center' }}>
              SIMULATING {year} {circuit.replace(' Grand Prix', ' GP').toUpperCase()} AGAINST ACTUAL RESULTS…
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.1em' }}>
              Running full 20-car GridRaceEnv — this takes 3–8 seconds
            </span>
          </div>
        )}

        {/* ── Results ──────────────────────────────────────────────────────── */}
        {result && !isLoading && (
          <>
            {/* Accuracy stat cards */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
                Accuracy — {result.year} {result.circuit}
              </div>
              <div style={{ display: 'flex', gap: 1 }}>
                <StatCard
                  value={`${result.accuracy_pct_within_3.toFixed(0)}%`}
                  label="Within ±3 Positions"
                  accent={false}
                  valueColor={accuracyColor(result.accuracy_pct_within_3)}
                />
                <StatCard
                  value={`${result.accuracy_pct_within_5.toFixed(0)}%`}
                  label="Within ±5 Positions"
                  accent={false}
                  valueColor={accuracyColor(result.accuracy_pct_within_5)}
                />
                <StatCard
                  value={result.mean_absolute_delta.toFixed(1)}
                  label="Mean Position Error"
                  accent={false}
                />
              </div>
            </div>

            {/* Side-by-side table */}
            <div style={{ border: 'var(--border)', overflow: 'hidden' }}>
              {/* Header row */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', background: 'var(--color-surface)', borderBottom: '2px solid var(--color-border)' }}>
                <div style={{ padding: '10px 20px', fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase', borderRight: '1px solid var(--color-border)' }}>
                  Actual Result
                </div>
                <div style={{ padding: '10px 20px', fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
                  Simulated Result
                </div>
              </div>

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

            {/* Large-delta callout */}
            <LargeDeltaCallout deltas={largeDeltaRows} raceKey={raceKey} />

            {/* Context note */}
            <div style={{ padding: '16px 20px', background: 'var(--color-surface-2)', border: 'var(--border)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 8 }}>
                About This Simulation
              </div>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--color-text-dim)', lineHeight: 1.75, margin: 0 }}>
                This simulation runs a single race using PitIQ's GridRaceEnv with behavior-cloned rival pit strategies.
                Results vary between runs due to stochastic rival pit timing.
                The 70% within ±3 positions accuracy cited in the project documentation is a 5-seed average;
                single runs typically show 55–70% accuracy.
                Safety cars, mechanical failures, and driver errors are not modeled.
              </p>
            </div>
          </>
        )}

        {/* Empty state */}
        {!result && !isLoading && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16, padding: '64px 0' }}>
            <div style={{ width: 1, height: 60, background: 'linear-gradient(to bottom, transparent, var(--color-border))' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
              Select a race and run validation to see simulation accuracy
            </span>
          </div>
        )}

      </div>
    </div>
  )
}
