import { Card, StatPill } from '@/components/Card'
import { listEvents, listPacks, verifyChain } from '@/lib/api'

export const dynamic = 'force-dynamic'

export default async function Overview() {
  let chainOk = false
  let chainChecked = 0
  let chainBroken: number | null = null
  let totalEvents = 0
  let packCount = 0
  let connected = true
  let connectError = ''

  try {
    const [v, ev, p] = await Promise.all([verifyChain(), listEvents({ limit: 1000 }), listPacks()])
    chainOk = v.ok
    chainChecked = v.checked
    chainBroken = v.first_broken_index
    totalEvents = ev.length
    packCount = p.count
  } catch (err) {
    connected = false
    connectError = err instanceof Error ? err.message : String(err)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="text-ink-400 text-sm mt-1">
          Tenant <span className="font-mono text-white">{process.env.GODERASH_TENANT ?? '—'}</span>{' '}
          on <span className="font-mono text-white">{process.env.GODERASH_ENDPOINT ?? '—'}</span>
        </p>
      </div>

      {!connected && (
        <Card title="Cannot reach control plane" subtitle="Set GODERASH_ENDPOINT, GODERASH_API_KEY, GODERASH_TENANT">
          <pre className="text-bad text-xs whitespace-pre-wrap">{connectError}</pre>
        </Card>
      )}

      {connected && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card title="Chain integrity" subtitle="Last verify result">
            <div className="flex items-baseline gap-3">
              <StatPill ok={chainOk} label={chainOk ? 'OK' : 'broken'} />
              <span className="text-3xl font-mono text-white">{chainChecked}</span>
              <span className="text-xs text-ink-400">events checked</span>
            </div>
            {!chainOk && chainBroken !== null && (
              <p className="text-bad text-xs mt-2">
                first broken index: <span className="font-mono">{chainBroken}</span>
              </p>
            )}
          </Card>

          <Card title="Recent events" subtitle="Last 1000">
            <div className="text-3xl font-mono text-white">{totalEvents}</div>
          </Card>

          <Card title="Compliance packs" subtitle="Available regulations">
            <div className="text-3xl font-mono text-white">{packCount}</div>
          </Card>
        </div>
      )}

      <Card title="Quick actions">
        <ul className="text-sm space-y-2">
          <li>
            <a href="/events">→ Browse events</a>
          </li>
          <li>
            <a href="/verify">→ Re-verify the chain</a>
          </li>
          <li>
            <a href="/packs">→ Generate a compliance pack</a>
          </li>
          <li>
            <a href="/whatif">→ Run a What-If projection</a>
          </li>
        </ul>
      </Card>
    </div>
  )
}
