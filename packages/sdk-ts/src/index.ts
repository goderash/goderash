/**
 * @goderash/sdk — Audit any AI agent with one import.
 *
 * @example
 * ```ts
 * import { GoderashClient, wrapTool } from '@goderash/sdk'
 *
 * const goderash = new GoderashClient({
 *   apiKey: process.env.GODERASH_API_KEY!,
 *   tenant: 'my-company',
 *   agentId: 'ops-agent-v1',
 * })
 *
 * const transfer = wrapTool(goderash, { category: 'action', confirmation: 'biometric' },
 *   async (src: string, dst: string, amount: number) => {
 *     // ... your logic ...
 *   }
 * )
 * ```
 */

export { GoderashClient, type GoderashContext, type GoderashClientOptions } from './client.js'
export {
  type GoderashEvent,
  type GoderashEventPayload,
  type ToolCategory,
  type ConfirmationType,
} from './events/types.js'
export { wrapTool } from './wrap/wrapTool.js'
export { wrapLLM } from './wrap/wrapLLM.js'
export { wrapAgent } from './wrap/wrapAgent.js'
