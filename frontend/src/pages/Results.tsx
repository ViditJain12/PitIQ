import PageShell from '../components/PageShell'

export default function Results() {
  return (
    <PageShell title="Results">
      <div className="max-w-4xl mx-auto flex flex-col gap-6">
        <div>
          <h2 className="text-2xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>
            Results
          </h2>
          <p style={{ color: 'var(--text-secondary)' }}>
            Race simulation output — tire degradation curves, predicted finish, lap timeline.
          </p>
        </div>

        <div
          className="rounded-xl border p-6 flex flex-col items-center justify-center gap-3 h-64"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text-muted)' }}
        >
          <div className="text-4xl">📊</div>
          <span>Simulation results will render here</span>
          <span className="text-xs">Recharts tire degradation + race position chart — Phase 7</span>
        </div>

        {/* Tire compound legend */}
        <div className="flex gap-4 flex-wrap">
          {([
            ['Soft', 'var(--tire-soft)'],
            ['Medium', 'var(--tire-medium)'],
            ['Hard', 'var(--tire-hard)'],
            ['Inter', 'var(--tire-inter)'],
            ['Wet', 'var(--tire-wet)'],
          ] as [string, string][]).map(([label, color]) => (
            <div key={label} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ background: color }} />
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </PageShell>
  )
}
