import { Card, StatPill } from '@/components/Card'
import { verifyChain } from '@/lib/api'

export const dynamic = 'force-dynamic'

export default async function VerifyPage() {
  let result: Awaited<ReturnType<typeof verifyChain>> | null = null
  let error: string | null = null
  try {
    result = await verifyChain()
  } catch (e) {
    error = e instanceof Error ? e.message : String(e)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Verify</h1>
        <p className="text-ink-400 text-sm mt-1">
          Re-walks the full hash chain for this tenant. Every page load runs a fresh check.
        </p>
      </div>

      {error && (
        <Card title="Error">
          <pre className="text-bad text-xs whitespace-pre-wrap">{error}</pre>
        </Card>
      )}

      {result && (
        <Card title="Chain status">
          <div className="space-y-3">
            <StatPill ok={result.ok} label={result.ok ? 'verified' : 'tampered'} />
            <p className="text-sm">
              <span className="text-ink-400">events checked:</span>{' '}
              <span className="font-mono">{result.checked}</span>
            </p>
            {result.first_broken_index !== null && (
              <p className="text-bad text-sm">
                first broken at sequence index{' '}
                <span className="font-mono">{result.first_broken_index}</span>
              </p>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}
