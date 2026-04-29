import { Card } from '@/components/Card'
import { projectWhatIf } from '@/lib/api'

export const dynamic = 'force-dynamic'

const DEFAULT_POLICY = {
  velocity_caps: {},
  velocity_amount_caps: {},
  deny_tools: [] as string[],
  require_confirmation: [] as string[],
  new_permission_mode: null,
}

export default async function WhatIfPage() {
  let result: Awaited<ReturnType<typeof projectWhatIf>> | null = null
  let error: string | null = null
  try {
    result = await projectWhatIf({ policy: DEFAULT_POLICY })
  } catch (e) {
    error = e instanceof Error ? e.message : String(e)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">What-If</h1>
        <p className="text-ink-400 text-sm mt-1">
          Replay the last 30 days of ledger events under an alternate policy bundle. Defaults to a
          pass-through policy (zero diffs).
        </p>
      </div>

      {error && (
        <Card title="Error">
          <pre className="text-bad text-xs whitespace-pre-wrap">{error}</pre>
        </Card>
      )}

      {result && (
        <>
          <Card title="Summary">
            <pre className="text-xs whitespace-pre-wrap font-mono text-ink-200">
              {JSON.stringify(result.summary, null, 2)}
            </pre>
          </Card>

          {result.diffs.length > 0 ? (
            <Card title={`Diffs (${result.diff_count})`}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm font-mono">
                  <thead>
                    <tr className="text-ink-400 text-xs uppercase tracking-wider border-b border-ink-800">
                      <th className="text-left py-2 pr-4">#</th>
                      <th className="text-left py-2 pr-4">tool</th>
                      <th className="text-left py-2 pr-4">real</th>
                      <th className="text-left py-2 pr-4">counter</th>
                      <th className="text-left py-2 pr-4">reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.diffs.slice(0, 200).map((d) => (
                      <tr key={d.sequence_no} className="border-b border-ink-800/50">
                        <td className="py-2 pr-4 text-ink-400">{d.sequence_no}</td>
                        <td className="py-2 pr-4">{d.tool_name ?? '—'}</td>
                        <td className="py-2 pr-4 text-ok">{d.real_decision}</td>
                        <td className="py-2 pr-4 text-bad">{d.counter_decision}</td>
                        <td className="py-2 pr-4 text-ink-400">{d.reason ?? ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : (
            <Card title="No diffs under this policy">
              <p className="text-ink-400 text-sm">
                The default policy is pass-through. Edit{' '}
                <code className="text-white">app/whatif/page.tsx</code> to try alternate policies
                (velocity caps, deny lists, plan mode) until interactive policy editing ships.
              </p>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
