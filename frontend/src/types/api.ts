/** API-контракты бэкенда (C-01 / C-02 / C-06). */

export type DeviceStatus = 'on' | 'off' | 'unavailable'
export type Managability = 'controllable' | 'readonly'
export type AdapterHealth = 'ok' | 'degraded' | 'unreachable'
export type DeviceSource = 'mode_run' | 'voice' | 'manual' | 'simulator'

export type ModeId = 'arrival' | 'lecture' | 'hybrid' | 'break' | 'finish'

export type RunStatus = 'running' | 'applied' | 'failed'
export type StepStatus = 'pending' | 'applied' | 'skipped' | 'error'
export type PreviewStepStatus = 'will_change' | 'already_in_state'
export type FaultKind = 'unavailable' | 'latency' | 'error'

export interface DevicePayload {
  id: string
  name: string
  ya_type: string
  managability: Managability
  state: Record<string, unknown>
  state_version: number
  updated_at: string
  source: DeviceSource
  status: DeviceStatus
}

export interface ZonePayload {
  id: string
  code: string
  name: string
  purpose: string
  devices: DevicePayload[]
}

export interface RoomPlan {
  id: string
  name: string
  state_version: number
  adapter_health: AdapterHealth
  updated_at: string | null
  zones: ZonePayload[]
  device_count: number
  readonly_count: number
}

export interface ModeSummary {
  id: ModeId | string
  title: string
  description: string
  step_count: number
  critical_device_ids: string[]
  enabled: boolean
  preconditions: Array<{
    kind: string
    device_id?: string | null
    device_ids?: string[]
    text?: string
  }>
}

export interface ModeList {
  items: ModeSummary[]
}

export interface PreviewWarning {
  code: string
  severity: 'warning' | 'critical'
  text: string
}

export interface StepDiff {
  sequence: number
  device_id: string
  device_name: string
  before: Record<string, unknown>
  target: Record<string, unknown>
  delta: string | null
  status: PreviewStepStatus
  critical: boolean
}

export interface PreviewResult {
  mode_id: string
  state_version: number
  preview_hash: string
  expires_at: string | null
  can_apply: boolean
  blocking_reasons: string[]
  warnings: PreviewWarning[]
  steps: StepDiff[]
  summary: Record<string, number>
}

export interface RunCounters {
  applied: number
  skipped: number
  error: number
}

export interface RunStepPayload {
  sequence: number
  device_id: string
  device_name: string
  target: Record<string, unknown>
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  status: StepStatus
  error_code: string | null
  error_text: string | null
  manual_hint: string | null
  attempts: number
  duration_ms: number | null
  started_at: string | null
  finished_at: string | null
}

export interface RunPayload {
  id: string
  mode_id: string
  mode_title: string
  classroom_id: string
  status: RunStatus
  outcome_message: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  policy: string
  counters: RunCounters
  error_code: string | null
  warnings: Array<{ code: string; acknowledged: boolean }>
  steps: RunStepPayload[]
  counters_total: number
  preview_hash: string
  state_version: number
  requested_by: { id: string; display_name: string; role: string } | null
  poll_url: string
  step_total: number
}

export interface RunCreateBody {
  mode_id: string
  preview_hash: string
  ack_warnings: string[]
}

export interface Fault {
  id: string
  device_id: string
  kind: FaultKind
  value_ms: number | null
  error_code: string | null
  expires_at: string | null
  active: boolean
  created_at: string
  created_by: string
  comment: string | null
}

export interface FaultCreateBody {
  device_id: string
  kind: FaultKind
  value_ms?: number | null
  error_code?: string | null
  ttl_seconds?: number | null
  comment?: string | null
}

export interface FaultList {
  items: Fault[]
  total: number
  limit: number
  offset: number
  broken_devices: string[]
}

export interface OccupancyBody {
  detected: boolean
  presence_minutes: number
}

export interface OccupancyResult {
  device_id: string
  state: Record<string, unknown>
  presence_minutes: number
  state_version: number
  updated_at: string
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
    request_id?: string
    retryable?: boolean
  }
}

export class ApiError extends Error {
  code: string
  details: Record<string, unknown>
  requestId?: string
  retryable: boolean
  status: number

  constructor(status: number, body: ApiErrorBody['error']) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details ?? {}
    this.requestId = body.request_id
    this.retryable = body.retryable ?? false
  }
}
