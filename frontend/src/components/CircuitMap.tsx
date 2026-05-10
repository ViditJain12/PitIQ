import { useRef, useEffect, useState } from 'react'
import { ZoomIn } from 'lucide-react'

// ── types ──────────────────────────────────────────────────────────────────

interface CircuitMeta {
  name: string
  length_km: number
  circuit_type: string
  pit_loss_s: number
  total_laps_typical: number
}

interface CircuitMapProps {
  svgPoints: string
  viewBox?: string
  width?: number | string
  height?: number
  color?: string
  animated?: boolean
  circuitInfo?: CircuitMeta
}

// ── constants ──────────────────────────────────────────────────────────────

const SECTOR_COLORS = ['#E8002D', '#FFF200', '#27F4D2'] as const
const SECTOR_LABELS = ['SECTOR 1', 'SECTOR 2', 'SECTOR 3'] as const

// ── helpers ────────────────────────────────────────────────────────────────

// Measures SVG polyline length to set stroke-dasharray precisely.
function usePolylineLength(points: string) {
  const ref = useRef<SVGPolylineElement>(null)
  const [len, setLen] = useState(3000)
  useEffect(() => {
    if (ref.current) {
      const l = ref.current.getTotalLength?.() ?? 3000
      setLen(Math.ceil(l) + 10)
    }
  }, [points])
  return { ref, len }
}

// Splits a space-separated points string into 3 equal segments by index.
function splitSectors(svgPoints: string): [string, string, string] {
  const pts = svgPoints.split(' ')
  const third = Math.floor(pts.length / 3)
  return [
    pts.slice(0, third).join(' '),
    pts.slice(third, third * 2).join(' '),
    pts.slice(third * 2).join(' '),
  ]
}

// ── SectorLine ─────────────────────────────────────────────────────────────

// Single sector polyline with glow layer + staggered draw animation.
function SectorLine({ points, stroke, delay }: { points: string; stroke: string; delay: number }) {
  const { ref, len } = usePolylineLength(points)
  return (
    <>
      <polyline
        points={points} fill="none" stroke={stroke}
        strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" opacity={0.18}
      />
      <polyline
        ref={ref}
        points={points} fill="none" stroke={stroke}
        strokeWidth={3} strokeLinecap="round" strokeLinejoin="round"
        style={{
          strokeDasharray: len,
          strokeDashoffset: len,
          animation: 'draw-circuit 0.6s ease forwards',
          animationDelay: `${delay}s`,
        }}
      />
    </>
  )
}

// ── CircuitModal ───────────────────────────────────────────────────────────

function CircuitModal({
  svgPoints,
  viewBox,
  info,
  onClose,
}: {
  svgPoints: string
  viewBox: string
  info: CircuitMeta
  onClose: () => void
}) {
  const [visible, setVisible] = useState(false)
  const [sectors, setSectors] = useState<[string, string, string] | null>(null)

  // Compute sectors immediately; fade in on next frame so CSS transition fires.
  useEffect(() => {
    setSectors(splitSectors(svgPoints))
    const frame = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(frame)
  }, [svgPoints])

  // Escape to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      onMouseDown={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 500,
        background: 'rgba(0,0,0,0.85)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        opacity: visible ? 1 : 0,
        transition: 'opacity 150ms ease',
      }}
    >
      <div
        onMouseDown={e => e.stopPropagation()}
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          width: 500,
          maxWidth: 'calc(100vw - 32px)',
          borderRadius: 0,
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 18px', borderBottom: '1px solid var(--color-border)',
        }}>
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 900,
            letterSpacing: '0.06em', color: 'var(--color-text)', textTransform: 'uppercase',
            lineHeight: 1,
          }}>
            {info.name}
          </span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: 22, lineHeight: 1, padding: '0 4px', flexShrink: 0 }}
          >
            ×
          </button>
        </div>

        {/* Map */}
        <div style={{ padding: '20px 24px 12px' }}>
          <svg viewBox={viewBox} width="100%" height={280} style={{ display: 'block' }}>
            {/* Ghost track in sky blue as base */}
            <polyline
              points={svgPoints} fill="none"
              stroke="#7ECEF4" strokeWidth={1}
              strokeLinecap="round" strokeLinejoin="round" opacity={0.2}
            />
            {/* Sector lines draw sequentially */}
            {sectors?.map((pts, i) => (
              <SectorLine key={i} points={pts} stroke={SECTOR_COLORS[i]} delay={i * 0.6} />
            ))}
          </svg>
        </div>

        {/* Sector legend */}
        <div style={{ display: 'flex', gap: 28, paddingInline: 24, paddingBottom: 14 }}>
          {SECTOR_LABELS.map((label, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <div style={{ width: 18, height: 2, background: SECTOR_COLORS[i], flexShrink: 0 }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--color-text-muted)', letterSpacing: '0.12em' }}>
                {label}
              </span>
            </div>
          ))}
        </div>

        {/* Circuit info row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', borderTop: '1px solid var(--color-border)' }}>
          {[
            { label: 'Length',   value: `${info.length_km} km` },
            { label: 'Laps',     value: String(info.total_laps_typical) },
            { label: 'Type',     value: info.circuit_type },
            { label: 'Pit Loss', value: `${info.pit_loss_s}s` },
          ].map((item, i) => (
            <div
              key={i}
              style={{
                padding: '12px 16px',
                borderRight: i < 3 ? '1px solid var(--color-border)' : 'none',
              }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--color-text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 4 }}>
                {item.label}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--color-text)', fontWeight: 600, textTransform: 'capitalize' }}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── CircuitMap (thumbnail) ─────────────────────────────────────────────────

export function CircuitMap({
  svgPoints,
  viewBox = '0 0 200 120',
  width = '100%',
  height = 100,
  color,
  animated = true,
  circuitInfo,
}: CircuitMapProps) {
  const { ref, len } = usePolylineLength(svgPoints)
  const [animKey, setAnimKey] = useState(0)
  const [modalOpen, setModalOpen] = useState(false)

  useEffect(() => {
    setAnimKey(k => k + 1)
  }, [svgPoints])

  const strokeColor = color ?? 'var(--color-accent)'
  const interactive = !!circuitInfo

  return (
    <>
      <div
        onClick={() => interactive && setModalOpen(true)}
        style={{
          position: 'relative',
          display: 'block',
          width,
          cursor: interactive ? 'pointer' : 'default',
        }}
      >
        <svg
          viewBox={viewBox}
          width="100%"
          height={height}
          style={{ display: 'block', overflow: 'visible' }}
        >
          {/* Faint glow */}
          <polyline
            points={svgPoints} fill="none"
            stroke={strokeColor} strokeWidth={4}
            strokeLinecap="round" strokeLinejoin="round" opacity={0.12}
          />
          {/* Animated trace */}
          <polyline
            key={animKey}
            ref={ref}
            points={svgPoints} fill="none"
            stroke={strokeColor} strokeWidth={1.5}
            strokeLinecap="round" strokeLinejoin="round"
            style={
              animated
                ? { strokeDasharray: len, strokeDashoffset: len, animation: 'draw-circuit 1.5s ease forwards' }
                : {}
            }
          />
        </svg>

        {/* Zoom hint icon */}
        {interactive && (
          <div style={{
            position: 'absolute', bottom: 4, right: 4,
            color: strokeColor, opacity: 0.55,
            pointerEvents: 'none', lineHeight: 0,
          }}>
            <ZoomIn size={12} />
          </div>
        )}
      </div>

      {modalOpen && circuitInfo && (
        <CircuitModal
          svgPoints={svgPoints}
          viewBox={viewBox}
          info={circuitInfo}
          onClose={() => setModalOpen(false)}
        />
      )}
    </>
  )
}
