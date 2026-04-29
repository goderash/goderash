import { Card } from '@/components/Card'
import { listEvents } from '@/lib/api'

export const dynamic = 'force-dynamic'

const TYPE_COLORS: Record<string, string> = {
  'agent.turn.started': 'text-sky-400',
  'agent.turn.completed': 'text-sky-400',
  'tool.invoked': 'text-amber-300',
  'tool.completed': 'text-ok',
  'tool.failed': 'text-bad',
  'llm.call.started': 'text-violet-300',
  'llm.call.completed': 'text-violet-300',
  'permission.granted': 'text-ok',
  'permission.denied': 'text-bad',
  'contract.violated': 'text-bad',
}

export default async function EventsPage({
  searchParams,
}: {
  searchParams?: { conversation_id?: string }
}) {
  const conversationId = searchParams?.conversation_id
  const events = await listEvents({ conversation_id: conversationId, limit: 200 }).catch((e) => {
    return [] as never
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Events</h1>
        <p className="text-ink-400 text-sm mt-1">
          {events.length} event{events.length === 1 ? '' : 's'}
          {conversationId && (
            <span>
              {' '}
              in conversation <span className="font-mono text-white">{conversationId}</span>
            </span>
          )}
        </p>
      </div>

      <Card title="Latest" subtitle="Newest at the top">
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="text-ink-400 text-xs uppercase tracking-wider border-b border-ink-800">
                <th className="text-left py-2 pr-4">#</th>
                <th className="text-left py-2 pr-4">type</th>
                <th className="text-left py-2 pr-4">conversation</th>
                <th className="text-left py-2 pr-4">when</th>
                <th className="text-left py-2 pr-4">hash</th>
              </tr>
            </thead>
            <tbody>
              {events
                .slice()
                .reverse()
                .map((e) => (
                  <tr key={e.event_id} className="border-b border-ink-800/50">
                    <td className="py-2 pr-4 text-ink-400">{e.sequence_no}</td>
                    <td className={`py-2 pr-4 ${TYPE_COLORS[e.event_type] ?? 'text-white'}`}>
                      {e.event_type}
                    </td>
                    <td className="py-2 pr-4 text-ink-400 truncate max-w-[12rem]">
                      {e.conversation_id}
                    </td>
                    <td className="py-2 pr-4 text-ink-400">
                      {new Date(e.occurred_at).toISOString().slice(11, 19)}
                    </td>
                    <td className="py-2 pr-4 text-ink-400 truncate max-w-[16rem]">
                      {e.hash.slice(0, 12)}…
                    </td>
                  </tr>
                ))}
              {events.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-ink-400 text-center">
                    no events yet — emit some via the SDK and reload.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
