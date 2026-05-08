interface LoadingStateProps {
  label?: string
}

export default function LoadingState({ label = 'COMPUTING STRATEGY' }: LoadingStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 20,
        padding: 48,
      }}
    >
      {/* Scan bar animation */}
      <div
        style={{
          position: 'relative',
          width: 240,
          height: 2,
          background: 'var(--color-surface-2)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: '-40%',
            width: '40%',
            height: '100%',
            background: 'linear-gradient(90deg, transparent, var(--color-accent), transparent)',
            animation: 'scan-bar 1.4s linear infinite',
          }}
        />
      </div>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--color-text-muted)',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </span>
    </div>
  )
}
