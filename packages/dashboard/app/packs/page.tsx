import { Card } from '@/components/Card'
import { listPacks } from '@/lib/api'

export const dynamic = 'force-dynamic'

const REGULATION_COPY: Record<string, { title: string; blurb: string }> = {
  soc2: {
    title: 'SOC 2',
    blurb: 'Trust Services Criteria (CC6.1, CC7.2, CC7.4)',
  },
  hipaa: {
    title: 'HIPAA Security Rule',
    blurb: '45 CFR §164.312 audit, integrity, transmission security',
  },
  ffiec: {
    title: 'FFIEC IT Examination',
    blurb: 'Audit, information security, change management',
  },
  finra: {
    title: 'FINRA Rule 4511 / 3110',
    blurb: 'Books and records + supervisory framework',
  },
  sec_17a4: {
    title: 'SEC Rule 17a-4',
    blurb: 'Books and records retention, WORM-compatible',
  },
}

export default async function PacksPage() {
  const list = await listPacks().catch(() => ({ packs: [], count: 0 }))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Compliance packs</h1>
        <p className="text-ink-400 text-sm mt-1">
          Each pack collects the relevant ledger events for the chosen window, verifies the chain,
          and emits a signed-manifest ZIP.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {list.packs.map((reg) => {
          const meta = REGULATION_COPY[reg] ?? { title: reg, blurb: '' }
          return (
            <Card key={reg} title={meta.title} subtitle={meta.blurb}>
              <p className="text-xs text-ink-400">
                Endpoint: <code>POST /v1/packs/{reg}</code>
              </p>
              <p className="text-xs text-ink-400 mt-2">
                Default window: last 30 days. Override via{' '}
                <code className="text-white">{`{ "start": "...", "end": "..." }`}</code>.
              </p>
            </Card>
          )
        })}
        {list.count === 0 && (
          <Card title="No packs registered">
            <p className="text-ink-400 text-sm">
              The control plane reported zero pack generators. Check that{' '}
              <code>goderash_core.packs.PACK_REGISTRY</code> is populated.
            </p>
          </Card>
        )}
      </div>
    </div>
  )
}
