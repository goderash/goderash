import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import Link from 'next/link'

import './globals.css'

export const metadata: Metadata = {
  title: 'Goderash — Audit & Governance',
  description: 'Audit & governance fabric for regulated AI agents',
}

const NAV: { href: string; label: string }[] = [
  { href: '/', label: 'Overview' },
  { href: '/events', label: 'Events' },
  { href: '/verify', label: 'Verify' },
  { href: '/packs', label: 'Packs' },
  { href: '/whatif', label: 'What-If' },
  { href: '/settings', label: 'Settings' },
]

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-ink-800 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="font-mono text-lg font-semibold tracking-tight">
              goderash
              <span className="ml-2 text-xs px-2 py-0.5 rounded bg-ink-800 text-ink-400">
                v0.1.0
              </span>
            </Link>
            <nav className="flex items-center gap-4 text-sm text-ink-400">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="hover:text-white">
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="text-xs text-ink-400 font-mono">
            audit & governance fabric
          </div>
        </header>
        <main className="px-6 py-8 max-w-7xl mx-auto">{children}</main>
      </body>
    </html>
  )
}
