const COMPOUND_COLORS: Record<string, string> = {
  SOFT:         'var(--tire-soft)',
  MEDIUM:       'var(--tire-medium)',
  HARD:         'var(--tire-hard)',
  INTERMEDIATE: 'var(--tire-intermediate)',
  WET:          'var(--tire-wet)',
}

const COMPOUND_LABELS: Record<string, string> = {
  SOFT: 'S', MEDIUM: 'M', HARD: 'H', INTERMEDIATE: 'I', WET: 'W',
}

interface TireBadgeProps {
  compound: string
  size?: 'sm' | 'md' | 'lg'
  showLabel?: boolean
}

export default function TireBadge({ compound, size = 'md', showLabel = true }: TireBadgeProps) {
  const color = COMPOUND_COLORS[compound.toUpperCase()] ?? '#888888'
  const label = COMPOUND_LABELS[compound.toUpperCase()] ?? compound[0]

  const dim = size === 'sm' ? 16 : size === 'md' ? 22 : 28
  const font = size === 'sm' ? 9 : size === 'md' ? 11 : 13

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <svg width={dim} height={dim} viewBox="0 0 24 24" aria-label={compound}>
        <circle cx="12" cy="12" r="11" fill="none" stroke={color} strokeWidth="2" />
        <circle cx="12" cy="12" r="5" fill={color} />
        <text
          x="12" y="16"
          textAnchor="middle"
          fontSize={font}
          fontFamily="var(--font-mono)"
          fontWeight="700"
          fill={compound.toUpperCase() === 'MEDIUM' ? '#000' : compound.toUpperCase() === 'HARD' ? '#000' : '#fff'}
        >
          {label}
        </text>
      </svg>
      {showLabel && (
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: size === 'sm' ? 10 : size === 'md' ? 12 : 14,
            color,
            fontWeight: 600,
            letterSpacing: '0.05em',
          }}
        >
          {compound.toUpperCase()}
        </span>
      )}
    </span>
  )
}
