import { useNavigate } from 'react-router-dom'
import { Route, Users, Calendar, Cpu } from 'lucide-react'
import { useStore } from '../store'

export default function Landing() {
  const navigate = useNavigate()
  const circuits = useStore(s => s.circuits)
  const drivers = useStore(s => s.drivers)

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'radial-gradient(ellipse 80% 60% at 0% 100%, #1A0000 0%, #0A0A0A 60%)',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Circuit track SVG background */}
      <svg
        aria-hidden
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
        preserveAspectRatio="xMidYMid slice"
        viewBox="0 0 1440 900"
      >
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        {/* Main circuit sweep — bottom-left origin */}
        <path
          d="M -60 820 C 80 700, 200 600, 320 520 C 460 430, 520 380, 480 260 C 450 170, 380 120, 440 40"
          stroke="#E8002D" strokeWidth="1.5" fill="none" opacity="0.25" filter="url(#glow)"
        />
        {/* Secondary inner line */}
        <path
          d="M -60 860 C 100 740, 240 640, 360 560 C 500 470, 560 420, 520 300 C 490 210, 420 160, 480 80"
          stroke="#E8002D" strokeWidth="1" fill="none" opacity="0.12"
        />
        {/* Wide outer sweep */}
        <path
          d="M 20 900 C 120 780, 280 660, 380 580 C 500 490, 580 440, 560 320 C 540 230, 460 180, 520 100"
          stroke="#E8002D" strokeWidth="2.5" fill="none" opacity="0.15" filter="url(#glow)"
        />
        {/* Speed lines — top right */}
        {[0, 14, 28, 42, 56, 70].map((offset, i) => (
          <line
            key={i}
            x1={1160 + offset} y1={0}
            x2={1440 + offset} y2={200 - offset * 0.5}
            stroke="#E8002D" strokeWidth="0.5" opacity={0.06 + i * 0.012}
          />
        ))}
      </svg>

      {/* Nav */}
      <nav
        style={{
          position: 'relative',
          zIndex: 10,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '20px 48px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 22,
            fontWeight: 900,
            letterSpacing: '0.1em',
            color: 'var(--color-text)',
          }}
        >
          PIT<span style={{ color: 'var(--color-accent)' }}>IQ</span>
        </span>
        <div style={{ display: 'flex', gap: 32, alignItems: 'center' }}>
          {[
            { label: 'SANDBOX', path: '/sandbox' },
            { label: 'OPTIMIZER', path: '/optimizer' },
            { label: 'HISTORICAL', path: '/historical' },
          ].map(({ label, path }) => (
            <button
              key={path}
              onClick={() => navigate(path)}
              style={{
                background: 'none',
                border: 'none',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: '0.15em',
                color: 'var(--color-text-muted)',
                cursor: 'pointer',
                padding: 0,
                transition: 'color 0.15s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = 'var(--color-text)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = 'var(--color-text-muted)' }}
            >
              {label}
            </button>
          ))}
        </div>
      </nav>

      {/* Hero */}
      <main
        style={{
          flex: 1,
          position: 'relative',
          zIndex: 10,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '64px 48px 48px',
          gap: 40,
        }}
      >
        {/* Eyebrow */}
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.25em',
            color: 'var(--color-accent)',
            textTransform: 'uppercase',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span style={{ display: 'inline-block', width: 24, height: 1, background: 'var(--color-accent)', opacity: 0.6 }} />
          AI-Powered Pit Strategy
          <span style={{ display: 'inline-block', width: 24, height: 1, background: 'var(--color-accent)', opacity: 0.6 }} />
        </div>

        {/* Headline */}
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(60px, 10vw, 120px)',
            fontWeight: 900,
            color: 'var(--color-text)',
            textAlign: 'center',
            lineHeight: 0.88,
            letterSpacing: '-0.01em',
            textTransform: 'uppercase',
            margin: 0,
          }}
        >
          WHAT'S YOUR<br />
          <span style={{ color: 'var(--color-accent)' }}>STRATEGY?</span>
        </h1>

        {/* Stat strip */}
        <div style={{ display: 'flex', gap: 1 }}>
          <LandingStatCard value={circuits.length || 29} label="CIRCUITS" icon={<Route size={16} color="var(--color-accent)" />} />
          <LandingStatCard value={drivers.length || 33} label="DRIVERS"  icon={<Users size={16} color="var(--color-accent)" />} />
          <LandingStatCard value={5}                    label="SEASONS"  icon={<Calendar size={16} color="var(--color-accent)" />} />
          <LandingStatCard value="PPO"                  label="AGENT"    icon={<Cpu size={16} color="var(--color-accent)" />} />
        </div>

        {/* Mode cards */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr',
            gap: 16,
            width: '100%',
            maxWidth: 1100,
          }}
        >
          <ModeCard
            label="SANDBOX"
            description="Build and test your own race plan."
            cta="ENTER SANDBOX"
            accentColor="var(--color-accent)"
            onClick={() => navigate('/sandbox')}
            illustration={<SandboxIllustration />}
          />
          <ModeCard
            label="OPTIMIZER"
            description="Let the agent find the fastest strategy."
            cta="RUN OPTIMIZER"
            accentColor="#27F4D2"
            onClick={() => navigate('/optimizer')}
            illustration={<OptimizerIllustration />}
          />
          <ModeCard
            label="HISTORICAL"
            description="Compare simulation accuracy against real race results."
            cta="VIEW HISTORICAL"
            accentColor="#A78BFA"
            onClick={() => navigate('/historical')}
            illustration={<HistoricalIllustration />}
          />
        </div>
      </main>

    </div>
  )
}

// ── Stat card ───────────────────────────────────────────────────────────────

function LandingStatCard({ value, label, icon }: { value: string | number; label: string; icon: React.ReactNode }) {
  return (
    <div
      style={{
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 'var(--radius-card)',
        padding: '18px 24px',
        minWidth: 100,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 6,
      }}
    >
      {icon}
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 26,
          fontWeight: 700,
          color: 'var(--color-text)',
          lineHeight: 1,
          letterSpacing: '-0.02em',
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          color: 'var(--color-text-muted)',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </div>
    </div>
  )
}

// ── Mode card ───────────────────────────────────────────────────────────────

interface ModeCardProps {
  label: string
  description: string
  cta: string
  accentColor: string
  onClick: () => void
  illustration: React.ReactNode
}

function ModeCard({ label, description, cta, accentColor, onClick, illustration }: ModeCardProps) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 'var(--radius-card)',
        padding: '32px',
        textAlign: 'left',
        cursor: 'pointer',
        transition: 'background 0.15s, border-color 0.15s',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        position: 'relative',
        overflow: 'hidden',
        minHeight: 220,
      }}
      onMouseEnter={e => {
        const el = e.currentTarget as HTMLElement
        el.style.background = `${accentColor}12`
        el.style.borderColor = `${accentColor}55`
      }}
      onMouseLeave={e => {
        const el = e.currentTarget as HTMLElement
        el.style.background = 'rgba(255,255,255,0.02)'
        el.style.borderColor = 'rgba(255,255,255,0.07)'
      }}
    >
      {/* Illustration sits in the bottom-right */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          right: 0,
          width: '60%',
          height: '70%',
          opacity: 0.5,
          pointerEvents: 'none',
        }}
      >
        {illustration}
      </div>

      {/* Content */}
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 28,
          fontWeight: 900,
          color: 'var(--color-text)',
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          lineHeight: 1,
          position: 'relative',
          zIndex: 1,
        }}
      >
        {label}
      </span>
      <p
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 13,
          color: 'var(--color-text-dim)',
          lineHeight: 1.6,
          margin: 0,
          maxWidth: 200,
          position: 'relative',
          zIndex: 1,
        }}
      >
        {description}
      </p>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: accentColor,
          letterSpacing: '0.15em',
          fontWeight: 700,
          marginTop: 'auto',
          position: 'relative',
          zIndex: 1,
        }}
      >
        {cta} →
      </span>
    </button>
  )
}

// ── Illustrations ───────────────────────────────────────────────────────────

function SandboxIllustration() {
  return (
    <svg viewBox="0 0 240 160" width="100%" height="100%" fill="none" preserveAspectRatio="xMaxYMax meet">
      <defs>
        <filter id="red-glow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      {/* Road curves — bottom-right origin */}
      <path d="M 280 180 C 200 140, 160 100, 140 60 C 125 30, 130 10, 100 -10"
        stroke="#E8002D" strokeWidth="2" filter="url(#red-glow)" opacity="0.7" />
      <path d="M 260 180 C 180 142, 145 102, 125 62 C 110 32, 115 12, 85 -8"
        stroke="#E8002D" strokeWidth="1" opacity="0.4" />
      <path d="M 240 180 C 165 144, 130 104, 110 64 C 95 34, 100 14, 70 -6"
        stroke="#E8002D" strokeWidth="3" filter="url(#red-glow)" opacity="0.25" strokeDasharray="4 8" />
      {/* Speed dots */}
      <circle cx="148" cy="55" r="2" fill="#E8002D" opacity="0.6" />
      <circle cx="138" cy="35" r="1.5" fill="#E8002D" opacity="0.4" />
      <circle cx="125" cy="18" r="1" fill="#E8002D" opacity="0.3" />
    </svg>
  )
}

function OptimizerIllustration() {
  return (
    <svg viewBox="0 0 240 160" width="100%" height="100%" fill="none" preserveAspectRatio="xMaxYMax meet">
      <defs>
        <filter id="teal-glow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      {/* Rising trend line */}
      <polyline
        points="20,140 55,120 80,130 110,95 135,100 160,70 185,60 210,40 235,20"
        stroke="#27F4D2" strokeWidth="1.5" filter="url(#teal-glow)" opacity="0.7"
      />
      {/* Area fill under line */}
      <polygon
        points="20,140 55,120 80,130 110,95 135,100 160,70 185,60 210,40 235,20 235,160 20,160"
        fill="#27F4D2" opacity="0.06"
      />
      {/* Data points */}
      {[[55,120],[110,95],[160,70],[210,40]].map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="3" fill="#27F4D2" opacity="0.7" />
      ))}
      {/* Grid lines */}
      {[40, 80, 120].map((y, i) => (
        <line key={i} x1="15" y1={y} x2="235" y2={y}
          stroke="#27F4D2" strokeWidth="0.5" opacity="0.08" strokeDasharray="3 6" />
      ))}
    </svg>
  )
}

function HistoricalIllustration() {
  return (
    <svg viewBox="0 0 240 160" width="100%" height="100%" fill="none" preserveAspectRatio="xMaxYMax meet">
      <defs>
        <filter id="purple-glow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      {/* Simulated vs actual bars — racing position style */}
      {[
        { x: 30,  actual: 100, sim: 95  },
        { x: 65,  actual: 75,  sim: 70  },
        { x: 100, actual: 115, sim: 105 },
        { x: 135, actual: 85,  sim: 90  },
        { x: 170, actual: 60,  sim: 55  },
        { x: 205, actual: 95,  sim: 100 },
      ].map(({ x, actual, sim }, i) => (
        <g key={i}>
          <rect x={x} y={160 - actual} width={12} height={actual} fill="#A78BFA" opacity="0.2" rx="1" />
          <rect x={x + 14} y={160 - sim} width={12} height={sim} fill="#A78BFA" opacity="0.4"
            filter="url(#purple-glow)" rx="1" />
        </g>
      ))}
      {/* Baseline */}
      <line x1="15" y1="160" x2="235" y2="160" stroke="#A78BFA" strokeWidth="0.5" opacity="0.2" />
    </svg>
  )
}
