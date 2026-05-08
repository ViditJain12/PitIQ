const CONFIDENCE_CONFIG = {
  HIGH:   { color: '#39B54A', bg: 'rgba(57,181,74,0.10)'  },
  MEDIUM: { color: '#FFF200', bg: 'rgba(255,242,0,0.10)'  },
  LOW:    { color: '#888888', bg: 'rgba(136,136,136,0.10)' },
} as const

type ConfidenceLevel = keyof typeof CONFIDENCE_CONFIG

interface ConfidenceBadgeProps {
  level: string
}

export default function ConfidenceBadge({ level }: ConfidenceBadgeProps) {
  const key = level.toUpperCase() as ConfidenceLevel
  const cfg = CONFIDENCE_CONFIG[key] ?? CONFIDENCE_CONFIG.LOW

  return (
    <span
      style={{
        display: 'inline-block',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.12em',
        padding: '2px 8px',
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.color}`,
        textTransform: 'uppercase',
      }}
    >
      {level.toUpperCase()}
    </span>
  )
}
