import PageShell from '../components/PageShell'

export default function Optimizer() {
  return (
    <PageShell title="Optimizer Mode">
      <div className="max-w-4xl mx-auto flex flex-col gap-6">
        <div>
          <h2 className="text-2xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>
            Optimizer
          </h2>
          <p style={{ color: 'var(--text-secondary)' }}>
            Full grid simulation. Rival behavior modeled per driver style. Undercut &amp; overcut
            windows detected automatically.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <InfoCard label="Mode" value="Full grid (20 cars)" color="var(--color-mercedes)" />
          <InfoCard label="Engine" value="PPO + GridRaceEnv" color="var(--color-redbull)" />
          <InfoCard label="Rivals" value="Behavior-cloned policies" color="var(--color-mclaren)" />
          <InfoCard label="Status" value="Phase 4.5 — coming soon" color="var(--text-muted)" />
        </div>

        <div
          className="rounded-xl border p-6 flex items-center justify-center h-48"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text-muted)' }}
        >
          Strategy recommendation panel — coming in Phase 8
        </div>
      </div>
    </PageShell>
  )
}

function InfoCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
    >
      <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>
        {label}
      </div>
      <div className="font-semibold text-sm" style={{ color }}>
        {value}
      </div>
    </div>
  )
}
