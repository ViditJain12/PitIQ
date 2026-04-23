import { useNavigate, useLocation } from 'react-router-dom'

const NAV_LINKS = [
  { label: 'Sandbox', path: '/sandbox' },
  { label: 'Optimizer', path: '/optimizer' },
]

interface PageShellProps {
  children: React.ReactNode
  title?: string
}

export default function PageShell({ children, title }: PageShellProps) {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-base)' }}>
      <nav
        className="flex items-center gap-8 px-8 py-4 border-b"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
      >
        <button
          onClick={() => navigate('/')}
          className="text-xl font-bold tracking-wider cursor-pointer"
          style={{ color: 'var(--text-primary)', background: 'none', border: 'none' }}
        >
          PIT<span style={{ color: 'var(--accent)' }}>IQ</span>
        </button>
        <div className="flex gap-6">
          {NAV_LINKS.map(link => (
            <button
              key={link.path}
              onClick={() => navigate(link.path)}
              className="text-sm font-medium pb-0.5 cursor-pointer transition-colors"
              style={{
                background: 'none',
                border: 'none',
                borderBottom: location.pathname === link.path
                  ? '2px solid var(--accent)'
                  : '2px solid transparent',
                color: location.pathname === link.path
                  ? 'var(--text-primary)'
                  : 'var(--text-secondary)',
              }}
            >
              {link.label}
            </button>
          ))}
        </div>
        {title && (
          <span className="ml-auto text-sm font-semibold" style={{ color: 'var(--text-muted)' }}>
            {title}
          </span>
        )}
      </nav>
      <main className="flex-1 p-8">{children}</main>
    </div>
  )
}
