interface StatCardProps {
  value: string | number
  label: string
  unit?: string
  accent?: boolean
}

export default function StatCard({ value, label, unit, accent = false }: StatCardProps) {
  return (
    <div
      style={{
        background: 'var(--color-surface)',
        border: 'var(--border)',
        borderTop: accent ? '2px solid var(--color-accent)' : 'var(--border)',
        padding: '16px 20px',
        minWidth: 100,
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 28,
          fontWeight: 700,
          color: accent ? 'var(--color-accent)' : 'var(--color-text)',
          lineHeight: 1,
          letterSpacing: '-0.02em',
        }}
      >
        {value}
        {unit && (
          <span style={{ fontSize: 14, color: 'var(--color-text-dim)', marginLeft: 4, fontWeight: 400 }}>
            {unit}
          </span>
        )}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 10,
          color: 'var(--color-text-muted)',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          marginTop: 6,
        }}
      >
        {label}
      </div>
    </div>
  )
}
