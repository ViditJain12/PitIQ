const TEAM_COLORS: Record<string, string> = {
  'Red Bull Racing':  'var(--team-red-bull)',
  'Ferrari':          'var(--team-ferrari)',
  'Mercedes':         'var(--team-mercedes)',
  'McLaren':          'var(--team-mclaren)',
  'Aston Martin':     'var(--team-aston)',
  'Alpine':           'var(--team-alpine)',
  'Williams':         'var(--team-williams)',
  'Haas F1 Team':     'var(--team-haas)',
  'Kick Sauber':      'var(--team-sauber)',
  'RB':               'var(--team-rb)',
}

interface DriverBadgeProps {
  code: string
  team?: string
  fullName?: string
  size?: 'sm' | 'md'
}

export default function DriverBadge({ code, team, fullName, size = 'md' }: DriverBadgeProps) {
  const teamColor = team ? (TEAM_COLORS[team] ?? 'var(--color-text-dim)') : 'var(--color-text-dim)'
  const isSmall = size === 'sm'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        borderLeft: `3px solid ${teamColor}`,
        paddingLeft: 8,
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontWeight: 700,
          fontSize: isSmall ? 12 : 14,
          color: 'var(--color-text)',
          letterSpacing: '0.08em',
        }}
      >
        {code}
      </span>
      {fullName && !isSmall && (
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 12,
            color: 'var(--color-text-dim)',
          }}
        >
          {fullName}
        </span>
      )}
    </span>
  )
}
