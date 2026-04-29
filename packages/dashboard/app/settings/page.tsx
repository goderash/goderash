import { Card } from '@/components/Card'

export default function SettingsPage() {
  const endpoint = process.env.GODERASH_ENDPOINT ?? '—'
  const tenant = process.env.GODERASH_TENANT ?? '—'
  const keyHint = process.env.GODERASH_API_KEY
    ? `${process.env.GODERASH_API_KEY.slice(0, 8)}…${process.env.GODERASH_API_KEY.slice(-4)}`
    : '—'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-ink-400 text-sm mt-1">
          Read-only view of the control-plane connection. To change these, set environment
          variables when starting the dashboard.
        </p>
      </div>

      <Card title="Connection">
        <dl className="text-sm space-y-3 font-mono">
          <div className="flex justify-between">
            <dt className="text-ink-400">GODERASH_ENDPOINT</dt>
            <dd>{endpoint}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ink-400">GODERASH_TENANT</dt>
            <dd>{tenant}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ink-400">GODERASH_API_KEY</dt>
            <dd>{keyHint}</dd>
          </div>
        </dl>
      </Card>

      <Card title="Tips">
        <ul className="text-sm space-y-2 text-ink-400 list-disc list-inside">
          <li>The dashboard is server-rendered; the API key never leaves the host.</li>
          <li>For multi-tenant ops, run one dashboard per tenant with distinct env files.</li>
          <li>Pin the dashboard behind your SSO / VPN for production.</li>
        </ul>
      </Card>
    </div>
  )
}
