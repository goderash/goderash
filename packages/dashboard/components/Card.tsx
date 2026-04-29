import type { ReactNode } from 'react'

export function Card({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border border-ink-800 bg-ink-900/50 p-5">
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-white tracking-wide uppercase">{title}</h2>
        {subtitle && <p className="text-xs text-ink-400 mt-1">{subtitle}</p>}
      </header>
      {children}
    </section>
  )
}

export function StatPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-mono ${
        ok ? 'bg-ok/10 text-ok' : 'bg-bad/10 text-bad'
      }`}
    >
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${ok ? 'bg-ok' : 'bg-bad'}`}
      />
      {label}
    </span>
  )
}
