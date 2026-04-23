import PageShell from '../components/PageShell'

export default function Sandbox() {
  return (
    <PageShell title="Sandbox Mode">
      <div className="max-w-4xl mx-auto flex flex-col gap-6">
        <div>
          <h2 className="text-2xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>
            Sandbox
          </h2>
          <p style={{ color: 'var(--text-secondary)' }}>
            Pick a race, pick a driver, place your pit stops — see your predicted finish.
          </p>
        </div>

        <StubCard step="1" label="Select Circuit" />
        <StubCard step="2" label="Select Driver" />
        <StubCard step="3" label="Configure Pit Windows" />

        <div
          className="rounded-xl border p-6 flex items-center justify-center h-48"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text-muted)' }}
        >
          Results timeline — coming in Phase 7
        </div>
      </div>
    </PageShell>
  )
}

function StubCard({ step, label }: { step: string; label: string }) {
  return (
    <div
      className="rounded-xl border p-4 flex items-center gap-4"
      style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
    >
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0"
        style={{ background: 'var(--accent)', color: '#fff' }}
      >
        {step}
      </div>
      <span className="font-medium" style={{ color: 'var(--text-secondary)' }}>
        {label}
      </span>
      <span
        className="ml-auto text-xs px-2 py-0.5 rounded-full"
        style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}
      >
        stub
      </span>
    </div>
  )
}
