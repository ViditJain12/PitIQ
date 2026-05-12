import { useState, useRef, useEffect, useCallback } from 'react'
import { Play, Pause } from 'lucide-react'
import type { LapData, RivalPrediction } from '../api/types'

// ── constants ──────────────────────────────────────────────────────────────

const DRIVER_TEAM_COLORS: Record<string, string> = {
  VER: '#3671C6', PER: '#3671C6',
  LEC: '#E8002D', SAI: '#E8002D',
  HAM: '#27F4D2', RUS: '#27F4D2',
  NOR: '#FF8000', PIA: '#FF8000',
  ALO: '#229971', STR: '#229971',
  GAS: '#FF87BC', OCO: '#FF87BC',
  ALB: '#64C4FF', SAR: '#64C4FF',
  HUL: '#B6BABD', MAG: '#B6BABD',
  BOT: '#52E252', ZHO: '#52E252',
  TSU: '#6692FF', RIC: '#6692FF',
}

// ── helpers ────────────────────────────────────────────────────────────────

function polylineToPath(svgPoints: string): string {
  const pts = svgPoints.trim().split(/\s+/).filter(Boolean)
  if (pts.length < 2) return ''
  const segments: string[] = []
  for (let i = 0; i < pts.length; i++) {
    const [x, y] = pts[i].split(',')
    segments.push(`${i === 0 ? 'M' : 'L'}${x},${y}`)
  }
  // Close the circuit loop back to start
  const [fx, fy] = pts[0].split(',')
  segments.push(`L${fx},${fy}`)
  return segments.join(' ')
}

function parseViewBox(vb: string): { w: number; h: number } {
  const parts = vb.trim().split(/\s+/).map(Number)
  return { w: parts[2] ?? 200, h: parts[3] ?? 120 }
}

interface DriverData {
  driver: string
  totalTime: number
  pitLaps: Set<number>
  color: string
  isEgo: boolean
}

// ── types ──────────────────────────────────────────────────────────────────

export interface RaceReplayProps {
  circuitSvgPoints: string
  circuitViewBox: string
  totalLaps: number
  egoDriver: string
  egoLapByLap: LapData[]
  rivalPredictions: RivalPrediction[]
}

// ── component ──────────────────────────────────────────────────────────────

export default function RaceReplay({
  circuitSvgPoints,
  circuitViewBox,
  totalLaps,
  egoDriver,
  egoLapByLap,
  rivalPredictions,
}: RaceReplayProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentLap, setCurrentLap] = useState(1)
  const [standings, setStandings] = useState<string[]>([])
  const [countdown, setCountdown] = useState<number | null>(null)
  const [speed, setSpeed] = useState(10)
  const [scrubPct, setScrubPct] = useState(0)
  const [finished, setFinished] = useState(false)

  // Performance refs — no re-renders
  const pathRef = useRef<SVGPathElement>(null)
  const dotsRef = useRef<Map<string, SVGCircleElement>>(new Map())
  const raceTimeRef = useRef(0)
  const lastFrameRef = useRef<number | null>(null)
  const animFrameRef = useRef<number | null>(null)
  const speedRef = useRef(10)
  const isPlayingRef = useRef(false)
  const lastStandingsRef = useRef(-1)
  const lastScrubRef = useRef(0)
  const countdownTidRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Pre-computed data refs
  const egoCumTimesRef = useRef<number[]>([])
  const totalRaceTimeRef = useRef(1)
  const driverDataRef = useRef<DriverData[]>([])

  useEffect(() => { speedRef.current = speed }, [speed])

  // Build replay data when panel opens
  useEffect(() => {
    if (!isOpen || egoLapByLap.length === 0) return

    // Cumulative lap times for ego (index i = time after i laps complete)
    const cumTimes = [0]
    let sum = 0
    for (const lap of egoLapByLap) { sum += lap.lap_time; cumTimes.push(sum) }
    egoCumTimesRef.current = cumTimes
    totalRaceTimeRef.current = sum

    // Detect pit laps for ego: tire_age resets to 1 after a stop
    const egoPitLaps = new Set<number>()
    for (let i = 1; i < egoLapByLap.length; i++) {
      if (egoLapByLap[i].tire_age === 1 && egoLapByLap[i - 1].tire_age > 1) {
        egoPitLaps.add(egoLapByLap[i].lap)
      }
    }

    const egoFinalPos = egoLapByLap[egoLapByLap.length - 1]?.position ?? 10
    const drivers: DriverData[] = [
      { driver: egoDriver, totalTime: sum, pitLaps: egoPitLaps, color: '#E8002D', isEgo: true },
      ...rivalPredictions.map(r => ({
        driver: r.driver,
        // Estimate rival total time: ~1.5s per position gap from ego
        totalTime: Math.max(sum * 0.94, sum + (r.final_position - egoFinalPos) * 1.5),
        pitLaps: new Set(r.pit_history.map(p => p.lap)),
        color: DRIVER_TEAM_COLORS[r.driver] ?? '#888888',
        isEgo: false,
      })),
    ]
    driverDataRef.current = drivers

    // Hide all dots on panel open/reset
    for (const dot of dotsRef.current.values()) dot.style.visibility = 'hidden'

    // Initialize standings by starting position
    const initOrder = [egoDriver, ...rivalPredictions
      .sort((a, b) => a.starting_position - b.starting_position)
      .map(r => r.driver)]
    setCurrentLap(1)
    setStandings(initOrder)
    setScrubPct(0)
    setFinished(false)
    raceTimeRef.current = 0
    lastStandingsRef.current = -1
  }, [isOpen, egoLapByLap, rivalPredictions, egoDriver])

  // ── animation loop ─────────────────────────────────────────────────────

  const animate = useCallback((timestamp: number) => {
    if (!isPlayingRef.current) return

    if (lastFrameRef.current === null) lastFrameRef.current = timestamp
    const dtReal = (timestamp - lastFrameRef.current) / 1000
    lastFrameRef.current = timestamp

    const totalRaceTime = totalRaceTimeRef.current
    raceTimeRef.current = Math.min(raceTimeRef.current + dtReal * speedRef.current, totalRaceTime)
    const t = raceTimeRef.current

    const pathEl = pathRef.current
    if (pathEl) {
      const pathLen = pathEl.getTotalLength()
      if (pathLen > 0) {
        const cumTimes = egoCumTimesRef.current

        // Inline: ego fractional laps at time t (avoids stale closure issue)
        let egoFrac = totalLaps
        for (let i = 0; i < cumTimes.length - 1; i++) {
          if (t >= cumTimes[i] && t <= cumTimes[i + 1]) {
            egoFrac = i + (t - cumTimes[i]) / (cumTimes[i + 1] - cumTimes[i])
            break
          }
        }
        if (t >= cumTimes[cumTimes.length - 1]) egoFrac = totalLaps

        // Update each driver dot — direct setAttribute bypasses React reconciler
        for (const d of driverDataRef.current) {
          const fracLaps = d.isEgo
            ? egoFrac
            : Math.min((t / d.totalTime) * totalLaps, totalLaps)
          const lapFrac = fracLaps % 1
          const pt = pathEl.getPointAtLength(lapFrac * pathLen)
          const lapNum = Math.floor(fracLaps) + 1
          const isPitting = d.pitLaps.has(lapNum) && lapFrac < 0.12

          const dot = dotsRef.current.get(d.driver)
          if (dot) {
            dot.style.visibility = 'visible'
            dot.setAttribute('cx', String(isPitting ? pt.x + 6 : pt.x))
            dot.setAttribute('cy', String(isPitting ? pt.y + 4 : pt.y))
            dot.setAttribute('opacity', isPitting ? '0.4' : '1')
          }
        }

        // Throttled React state: standings + current lap every 0.5s race-time
        if (t - lastStandingsRef.current >= 0.5) {
          lastStandingsRef.current = t
          const newLap = Math.min(Math.floor(egoFrac) + 1, totalLaps)
          setCurrentLap(newLap)

          const sorted = driverDataRef.current
            .map(d => ({
              driver: d.driver,
              frac: d.isEgo ? egoFrac : Math.min((t / d.totalTime) * totalLaps, totalLaps),
            }))
            .sort((a, b) => b.frac - a.frac)
          setStandings(sorted.map(s => s.driver))
        }

        // Throttled scrubber update every 100ms real-time
        const nowMs = performance.now()
        if (nowMs - lastScrubRef.current >= 100) {
          lastScrubRef.current = nowMs
          setScrubPct((t / totalRaceTime) * 100)
        }
      }
    }

    if (raceTimeRef.current >= totalRaceTimeRef.current) {
      isPlayingRef.current = false
      setIsPlaying(false)
      setCurrentLap(totalLaps)
      setScrubPct(100)
      setFinished(true)
      return
    }

    animFrameRef.current = requestAnimationFrame(animate)
  }, [totalLaps])

  // ── playback control helpers ───────────────────────────────────────────

  function stopAnimation() {
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = null
    }
    isPlayingRef.current = false
    setIsPlaying(false)
    lastFrameRef.current = null
  }

  function jumpToTime(t: number) {
    stopAnimation()
    raceTimeRef.current = t
    const pathEl = pathRef.current
    if (!pathEl) return
    const pathLen = pathEl.getTotalLength()
    const cumTimes = egoCumTimesRef.current

    let egoFrac = totalLaps
    for (let i = 0; i < cumTimes.length - 1; i++) {
      if (t >= cumTimes[i] && t <= cumTimes[i + 1]) {
        egoFrac = i + (t - cumTimes[i]) / (cumTimes[i + 1] - cumTimes[i])
        break
      }
    }

    for (const d of driverDataRef.current) {
      const fracLaps = d.isEgo ? egoFrac : Math.min((t / d.totalTime) * totalLaps, totalLaps)
      const lapFrac = fracLaps % 1
      const pt = pathEl.getPointAtLength(lapFrac * pathLen)
      const dot = dotsRef.current.get(d.driver)
      if (dot) {
        dot.style.visibility = 'visible'
        dot.setAttribute('cx', String(pt.x))
        dot.setAttribute('cy', String(pt.y))
        dot.setAttribute('opacity', '1')
      }
    }

    const newLap = Math.min(Math.floor(egoFrac) + 1, totalLaps)
    setCurrentLap(newLap)
    const sorted = driverDataRef.current
      .map(d => ({
        driver: d.driver,
        frac: d.isEgo ? egoFrac : Math.min((t / d.totalTime) * totalLaps, totalLaps),
      }))
      .sort((a, b) => b.frac - a.frac)
    setStandings(sorted.map(s => s.driver))
  }

  function startCountdown() {
    if (countdownTidRef.current) clearTimeout(countdownTidRef.current)
    setCountdown(3)
    let c = 3
    const tick = () => {
      c--
      if (c > 0) {
        setCountdown(c)
        countdownTidRef.current = setTimeout(tick, 1000)
      } else {
        setCountdown(0)
        countdownTidRef.current = setTimeout(() => {
          setCountdown(null)
          isPlayingRef.current = true
          setIsPlaying(true)
          animFrameRef.current = requestAnimationFrame(animate)
        }, 700)
      }
    }
    countdownTidRef.current = setTimeout(tick, 1000)
  }

  function handlePlay() {
    if (finished) {
      raceTimeRef.current = 0
      setScrubPct(0)
      setFinished(false)
      setCurrentLap(1)
      lastStandingsRef.current = -1
      for (const dot of dotsRef.current.values()) dot.style.visibility = 'hidden'
    }
    startCountdown()
  }

  function handlePause() {
    if (countdownTidRef.current) {
      clearTimeout(countdownTidRef.current)
      countdownTidRef.current = null
      setCountdown(null)
    }
    stopAnimation()
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopAnimation()
      if (countdownTidRef.current) clearTimeout(countdownTidRef.current)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Stop everything when panel closes
  useEffect(() => {
    if (!isOpen) {
      stopAnimation()
      if (countdownTidRef.current) clearTimeout(countdownTidRef.current)
      setCountdown(null)
    }
  }, [isOpen]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── derived / render constants ─────────────────────────────────────────

  const pathD = polylineToPath(circuitSvgPoints)
  const { w: vbW } = parseViewBox(circuitViewBox)
  const egoR = Math.max(3, vbW * 0.022)
  const rivalR = Math.max(2, vbW * 0.013)
  const trackWidth = Math.max(1, vbW * 0.008)
  const hasRivals = rivalPredictions.length > 0

  // Render circles from props (NOT from driverDataRef — refs aren't reactive)
  const egoCircle = { driver: egoDriver, color: '#E8002D', r: egoR, isEgo: true }
  const rivalCircles = rivalPredictions.map(r => ({
    driver: r.driver,
    color: DRIVER_TEAM_COLORS[r.driver] ?? '#888888',
    r: rivalR,
    isEgo: false,
  }))

  return (
    <div style={{ background: 'var(--color-surface)', border: 'var(--border)', borderRadius: 'var(--radius-card)' }}>

      {/* Header toggle */}
      <button
        onClick={() => setIsOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 18px', background: 'none', border: 'none',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-accent)' }}>
          {isOpen ? '▾' : '▶'}
        </span>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 900, color: 'var(--color-text)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
          Race Replay
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.08em', marginLeft: 2 }}>
          {hasRivals ? '20-car animation' : 'single-car trace'}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.1em' }}>
          {isOpen ? 'COLLAPSE ▴' : 'EXPAND ▾'}
        </span>
      </button>

      {isOpen && (
        <div style={{ borderTop: 'var(--border)', padding: '14px 18px' }}>

          {/* Controls bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>

            {/* Play / Pause / Countdown */}
            {countdown !== null ? (
              <div style={{
                minWidth: 72, padding: '5px 14px', textAlign: 'center',
                background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 'var(--radius-btn)',
                fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 900,
                color: countdown === 0 ? '#39B54A' : 'var(--color-accent)',
                letterSpacing: '0.05em',
              }}>
                {countdown === 0 ? 'GO!' : String(countdown)}
              </div>
            ) : !isPlaying ? (
              <button
                onClick={handlePlay}
                style={{
                  display: 'flex', alignItems: 'center', gap: 5, padding: '6px 14px',
                  background: 'var(--color-accent)', border: 'none', borderRadius: 'var(--radius-btn)',
                  color: '#fff', fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
                  letterSpacing: '0.12em', cursor: 'pointer',
                }}
              >
                <Play size={11} fill="#fff" />
                {finished ? 'REPLAY' : 'PLAY'}
              </button>
            ) : (
              <button
                onClick={handlePause}
                style={{
                  display: 'flex', alignItems: 'center', gap: 5, padding: '6px 14px',
                  background: 'transparent', border: 'var(--border)', borderRadius: 'var(--radius-btn)',
                  color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
                  letterSpacing: '0.12em', cursor: 'pointer',
                }}
              >
                <Pause size={11} />
                PAUSE
              </button>
            )}

            {/* Speed selector */}
            <div style={{ display: 'flex', gap: 3 }}>
              {([1, 5, 10, 30] as const).map(s => (
                <button
                  key={s}
                  onClick={() => setSpeed(s)}
                  style={{
                    padding: '5px 9px',
                    background: speed === s ? 'rgba(232,0,45,0.14)' : 'transparent',
                    border: speed === s ? '1px solid rgba(232,0,45,0.4)' : 'var(--border)',
                    borderRadius: 'var(--radius-btn)',
                    fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700,
                    color: speed === s ? 'var(--color-accent)' : 'var(--color-text-muted)',
                    cursor: 'pointer', letterSpacing: '0.04em',
                  }}
                >
                  {s}×
                </button>
              ))}
            </div>

            {/* Lap counter */}
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--color-text)', letterSpacing: '0.04em', marginLeft: 2 }}>
              LAP&nbsp;
              <span style={{ color: 'var(--color-accent)' }}>{currentLap}</span>
              <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>/{totalLaps}</span>
            </div>

            {/* Scrubber */}
            <div style={{ flex: 1, minWidth: 100 }}>
              <input
                type="range"
                min={0}
                max={100}
                step={0.1}
                value={scrubPct}
                onChange={e => {
                  const pct = Number(e.target.value)
                  setScrubPct(pct)
                  jumpToTime((pct / 100) * totalRaceTimeRef.current)
                }}
                style={{ width: '100%', accentColor: 'var(--color-accent)', cursor: 'pointer', height: 4 }}
              />
            </div>
          </div>

          {/* Visualization */}
          <div style={{ display: 'flex', gap: 10, height: 420 }}>

            {/* SVG circuit map */}
            <div style={{
              flex: hasRivals ? '0 0 65%' : 1,
              background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 4,
              overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center',
              position: 'relative',
            }}>
              <svg
                viewBox={circuitViewBox}
                width="100%"
                height="100%"
                style={{ display: 'block' }}
                preserveAspectRatio="xMidYMid meet"
              >
                <defs>
                  <filter id="rr-ego-glow" x="-80%" y="-80%" width="260%" height="260%">
                    <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>

                {/* Track glow layer */}
                <path
                  d={pathD}
                  fill="none"
                  stroke="rgba(255,255,255,0.06)"
                  strokeWidth={trackWidth * 3}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {/* Track surface — this path is used for getPointAtLength */}
                <path
                  ref={pathRef}
                  d={pathD}
                  fill="none"
                  stroke="rgba(255,255,255,0.2)"
                  strokeWidth={trackWidth}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />

                {/* Rival dots — rendered first (behind ego) */}
                {rivalCircles.map(d => (
                  <circle
                    key={d.driver}
                    ref={el => {
                      if (el) dotsRef.current.set(d.driver, el)
                      else dotsRef.current.delete(d.driver)
                    }}
                    cx={-9999}
                    cy={-9999}
                    r={d.r}
                    fill={d.color}
                    style={{ visibility: 'hidden' }}
                  />
                ))}

                {/* Ego dot — on top with glow */}
                <circle
                  ref={el => {
                    if (el) dotsRef.current.set(egoCircle.driver, el)
                    else dotsRef.current.delete(egoCircle.driver)
                  }}
                  cx={-9999}
                  cy={-9999}
                  r={egoCircle.r}
                  fill={egoCircle.color}
                  filter="url(#rr-ego-glow)"
                  style={{ visibility: 'hidden' }}
                />
              </svg>

              {/* Overlay: driver label (shown when paused/scrubbed) */}
              {!isPlaying && countdown === null && scrubPct === 0 && !finished && (
                <div style={{
                  position: 'absolute', inset: 0,
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  pointerEvents: 'none',
                }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
                    Press PLAY to start
                  </span>
                </div>
              )}
            </div>

            {/* Live standings (only when rivals present) */}
            {hasRivals && (
              <div style={{
                flex: '0 0 35%',
                background: 'var(--color-surface-2)', border: 'var(--border)', borderRadius: 4,
                display: 'flex', flexDirection: 'column', overflow: 'hidden',
              }}>
                <div style={{ padding: '10px 12px', borderBottom: 'var(--border)', flexShrink: 0 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
                    Live Standings
                  </span>
                </div>
                <div style={{ flex: 1, overflowY: 'auto' }}>
                  {standings.map((driver, i) => {
                    const isEgo = driver === egoDriver
                    const color = isEgo
                      ? '#E8002D'
                      : DRIVER_TEAM_COLORS[driver] ?? '#888888'
                    return (
                      <div
                        key={driver}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8, padding: '5px 12px',
                          background: isEgo ? 'rgba(232,0,45,0.08)' : 'transparent',
                          borderBottom: '1px solid rgba(42,42,42,0.6)',
                        }}
                      >
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', width: 22, textAlign: 'right', flexShrink: 0 }}>
                          P{i + 1}
                        </span>
                        <div style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
                        <span style={{
                          fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
                          color: isEgo ? 'var(--color-accent)' : 'var(--color-text)',
                          letterSpacing: '0.04em',
                        }}>
                          {driver}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Legend */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 10, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#E8002D', boxShadow: '0 0 6px rgba(232,0,45,0.5)' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>{egoDriver} (exact)</span>
            </div>
            {hasRivals && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--color-text-muted)' }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)' }}>rivals (estimated)</span>
              </div>
            )}
            <span style={{ fontFamily: 'var(--font-body)', fontSize: 9, fontStyle: 'italic', color: 'var(--color-text-muted)', marginLeft: 'auto' }}>
              {hasRivals ? 'Rival timing estimated from final standings. Ego lap times are exact.' : 'Ego lap-by-lap trace from simulation.'}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
