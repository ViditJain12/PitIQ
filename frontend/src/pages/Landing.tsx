import { useNavigate } from 'react-router-dom'

export default function Landing() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-base)' }}>
      {/* Nav */}
      <nav
        className="flex items-center justify-between px-8 py-4 border-b"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
      >
        <span className="text-xl font-bold tracking-wider" style={{ color: 'var(--text-primary)' }}>
          PIT<span style={{ color: 'var(--accent)' }}>IQ</span>
        </span>
        <div className="flex gap-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
          <span>F1 Race Strategy</span>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 text-center gap-8">
        <div className="flex flex-col items-center gap-4">
          <div
            className="text-xs font-semibold tracking-[0.2em] uppercase px-3 py-1 rounded-full border"
            style={{ color: 'var(--accent)', borderColor: 'var(--accent)', background: 'rgba(232,0,45,0.08)' }}
          >
            ML-Powered Pit Strategy
          </div>
          <h1
            className="text-5xl md:text-7xl font-black tracking-tight leading-none"
            style={{ color: 'var(--text-primary)' }}
          >
            PIT<span style={{ color: 'var(--accent)' }}>IQ</span>
          </h1>
          <p className="text-lg md:text-xl max-w-xl" style={{ color: 'var(--text-secondary)' }}>
            Driver-aware F1 race strategy prediction. Powered by 5 seasons of telemetry,
            multi-agent simulation, and reinforcement learning.
          </p>
        </div>

        {/* Mode cards */}
        <div className="flex flex-col sm:flex-row gap-4 w-full max-w-2xl mt-4">
          <ModeCard
            label="Sandbox"
            description="Pick a race & driver, place your pit stops, see your predicted finish."
            badge="Single car"
            badgeColor="var(--color-mclaren)"
            onClick={() => navigate('/sandbox')}
          />
          <ModeCard
            label="Optimizer"
            description="Full grid simulation with rival behavior. Find the optimal strategy."
            badge="Full grid"
            badgeColor="var(--color-mercedes)"
            onClick={() => navigate('/optimizer')}
          />
        </div>
      </main>

      {/* Footer */}
      <footer className="py-4 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
        PitIQ — built with FastF1 · XGBoost · PPO
      </footer>
    </div>
  )
}

interface ModeCardProps {
  label: string
  description: string
  badge: string
  badgeColor: string
  onClick: () => void
}

function ModeCard({ label, description, badge, badgeColor, onClick }: ModeCardProps) {
  return (
    <button
      onClick={onClick}
      className="flex-1 text-left p-6 rounded-xl border transition-all duration-150 cursor-pointer"
      style={{
        background: 'var(--bg-card)',
        borderColor: 'var(--border)',
      }}
      onMouseEnter={e => {
        ;(e.currentTarget as HTMLButtonElement).style.borderColor = badgeColor
        ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-elevated)'
      }}
      onMouseLeave={e => {
        ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)'
        ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-card)'
      }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
          {label}
        </span>
        <span
          className="text-xs font-semibold px-2 py-0.5 rounded-full"
          style={{ background: `${badgeColor}22`, color: badgeColor }}
        >
          {badge}
        </span>
      </div>
      <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {description}
      </p>
      <div className="mt-4 text-xs font-semibold" style={{ color: badgeColor }}>
        Launch →
      </div>
    </button>
  )
}
