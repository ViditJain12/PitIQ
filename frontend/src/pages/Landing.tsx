import { useNavigate } from 'react-router-dom'
import { useStore } from '../store'
import StatCard from '../components/StatCard'

export default function Landing() {
  const navigate = useNavigate()
  const circuits = useStore(s => s.circuits)
  const drivers = useStore(s => s.drivers)

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--color-bg)',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Grid background */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage:
            'linear-gradient(var(--color-border) 1px, transparent 1px), linear-gradient(90deg, var(--color-border) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
          opacity: 0.4,
          pointerEvents: 'none',
        }}
      />

      {/* Scanline */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          height: 1,
          background: 'linear-gradient(90deg, transparent, var(--color-accent), transparent)',
          opacity: 0.6,
          animation: 'scanline 6s linear infinite',
          pointerEvents: 'none',
        }}
      />

      {/* Nav */}
      <nav
        style={{
          position: 'relative',
          zIndex: 10,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '20px 40px',
          borderBottom: 'var(--border)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 20,
            fontWeight: 900,
            letterSpacing: '0.1em',
            color: 'var(--color-text)',
          }}
        >
          PIT<span style={{ color: 'var(--color-accent)' }}>IQ</span>
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--color-text-muted)',
            letterSpacing: '0.15em',
            textTransform: 'uppercase',
          }}
        >
          F1 Race Strategy Intelligence
        </span>
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
          padding: '60px 40px',
          gap: 48,
        }}
      >
        {/* Eyebrow */}
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '0.2em',
            color: 'var(--color-accent)',
            textTransform: 'uppercase',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span style={{ display: 'inline-block', width: 32, height: 1, background: 'var(--color-accent)' }} />
          ML-Powered Pit Strategy
          <span style={{ display: 'inline-block', width: 32, height: 1, background: 'var(--color-accent)' }} />
        </div>

        {/* Headline */}
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(48px, 10vw, 96px)',
            fontWeight: 900,
            color: 'var(--color-text)',
            textAlign: 'center',
            lineHeight: 0.9,
            letterSpacing: '-0.01em',
            textTransform: 'uppercase',
            margin: 0,
          }}
        >
          WHAT'S YOUR<br />
          <span style={{ color: 'var(--color-accent)' }}>STRATEGY?</span>
        </h1>

        {/* Sub */}
        <p
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 16,
            color: 'var(--color-text-dim)',
            textAlign: 'center',
            maxWidth: 520,
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          Driver-aware race strategy prediction. 5 seasons of telemetry, multi-agent simulation,
          and reinforcement learning — in your hands.
        </p>

        {/* Stat strip */}
        <div style={{ display: 'flex', gap: 1 }}>
          <StatCard value={circuits.length || 29} label="Circuits" />
          <StatCard value={drivers.length || 33} label="Drivers" />
          <StatCard value={5} label="Seasons" />
          <StatCard value="PPO" label="RL Agent" accent />
        </div>

        {/* Mode cards */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr',
            gap: 1,
            width: '100%',
            maxWidth: 1080,
          }}
        >
          <ModeCard
            label="SANDBOX"
            description="Pick a past race and driver, place your pit stops, see your predicted finish position against the field."
            tag="SINGLE CAR"
            tagColor="var(--team-mclaren)"
            cta="ENTER SANDBOX"
            onClick={() => navigate('/sandbox')}
          />
          <ModeCard
            label="OPTIMIZER"
            description="Full 20-car grid simulation with rival behavior cloning. PPO agent finds the optimal strategy for your driver."
            tag="FULL GRID"
            tagColor="var(--team-mercedes)"
            cta="RUN OPTIMIZER"
            onClick={() => navigate('/optimizer')}
          />
          <ModeCard
            label="HISTORICAL"
            description="See how PitIQ's simulation compares against actual race results. Check accuracy across 5 seasons of F1 data."
            tag="ARCHIVE"
            tagColor="var(--team-aston)"
            cta="VIEW HISTORICAL"
            onClick={() => navigate('/historical')}
          />
        </div>
      </main>

      {/* Footer */}
      <footer
        style={{
          position: 'relative',
          zIndex: 10,
          padding: '16px 40px',
          borderTop: 'var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--color-text-muted)',
            letterSpacing: '0.1em',
          }}
        >
          FastF1 · XGBoost · PPO · GridRaceEnv
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--color-text-muted)',
            letterSpacing: '0.1em',
          }}
        >
          2021–2025 TELEMETRY
        </span>
      </footer>
    </div>
  )
}

interface ModeCardProps {
  label: string
  description: string
  tag: string
  tagColor: string
  cta: string
  onClick: () => void
}

function ModeCard({ label, description, tag, tagColor, cta, onClick }: ModeCardProps) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'var(--color-surface)',
        border: 'none',
        borderTop: `2px solid ${tagColor}`,
        padding: '28px 28px 24px',
        textAlign: 'left',
        cursor: 'pointer',
        transition: 'background 0.1s',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--color-surface-2)' }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'var(--color-surface)' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 24,
            fontWeight: 900,
            color: 'var(--color-text)',
            letterSpacing: '0.05em',
          }}
        >
          {label}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: tagColor,
            letterSpacing: '0.15em',
            border: `1px solid ${tagColor}`,
            padding: '2px 6px',
          }}
        >
          {tag}
        </span>
      </div>
      <p
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 13,
          color: 'var(--color-text-dim)',
          lineHeight: 1.6,
          margin: 0,
          flex: 1,
        }}
      >
        {description}
      </p>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: tagColor,
          letterSpacing: '0.15em',
          fontWeight: 700,
        }}
      >
        {cta} →
      </span>
    </button>
  )
}
