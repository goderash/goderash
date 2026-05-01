/**
 * Canonical event type definitions. Mirrors `python/core/.../events/types.py`.
 *
 * Every event is immutable; the SDK never mutates after construction.
 */

export type ToolCategory = 'query' | 'action' | 'intelligence'
export type ConfirmationType = 'none' | 'pin' | 'biometric' | 'otp'

export interface AgentTurnStarted {
  event_type: 'agent.turn.started'
  user_message: string
  language?: string | null
  input_tokens_budget?: number | null
  tool_budget?: number | null
}

export interface AgentTurnCompleted {
  event_type: 'agent.turn.completed'
  assistant_message: string
  input_tokens: number
  output_tokens: number
  tool_calls_made: number
  duration_ms: number
  stop_reason: 'end_turn' | 'max_tokens' | 'tool_use' | 'stopped' | 'error'
}

export interface ToolInvoked {
  event_type: 'tool.invoked'
  tool_name: string
  tool_category: ToolCategory
  input_args_hash: string
  input_args_preview?: Record<string, unknown> | null
  confirmation_type?: ConfirmationType
}

export interface ToolCompleted {
  event_type: 'tool.completed'
  tool_name: string
  success: boolean
  duration_ms: number
  result_hash: string
  result_preview?: Record<string, unknown> | null
}

export interface ToolFailed {
  event_type: 'tool.failed'
  tool_name: string
  error_class: string
  error_message: string
  duration_ms: number
}

export interface LLMCallStarted {
  event_type: 'llm.call.started'
  provider: string
  model: string
  input_tokens_estimated?: number | null
  tools_offered?: string[]
}

export interface LLMCallCompleted {
  event_type: 'llm.call.completed'
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens?: number
  cache_creation_tokens?: number
  duration_ms: number
  stop_reason?: string | null
}

export interface PermissionGranted {
  event_type: 'permission.granted'
  tool_name: string
  source: 'rule' | 'user' | 'hook' | 'classifier' | 'bypass'
  reason?: string | null
}

export interface PermissionDenied {
  event_type: 'permission.denied'
  tool_name: string
  source: 'rule' | 'user' | 'hook' | 'classifier' | 'fraud_guard' | 'velocity' | 'budget'
  reason: string
}

export interface ContractViolated {
  event_type: 'contract.violated'
  contract_id: string
  contract_version: string
  clause: string
  severity: 'info' | 'warn' | 'error' | 'critical'
  details?: Record<string, unknown>
  blame_chain?: string[]
}

export type GoderashEventPayload =
  | AgentTurnStarted
  | AgentTurnCompleted
  | ToolInvoked
  | ToolCompleted
  | ToolFailed
  | LLMCallStarted
  | LLMCallCompleted
  | PermissionGranted
  | PermissionDenied
  | ContractViolated

export interface GoderashEvent {
  event_id: string
  tenant_id: string
  agent_id: string
  conversation_id: string
  turn_id: string
  parent_event_id?: string | null
  schema_version: number
  occurred_at: string // ISO-8601
  payload: GoderashEventPayload
}
