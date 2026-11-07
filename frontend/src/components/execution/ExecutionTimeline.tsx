import { CheckCircle2, CircleDashed, SkipForward, XCircle } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { LONG_RUNNING_DEVICES } from '@/lib/constants'
import { cn } from '@/lib/utils'
import type { RunPayload, RunStepPayload } from '@/types/api'

function StepIcon({ status }: { status: RunStepPayload['status'] }) {
  if (status === 'applied') return <CheckCircle2 className="h-5 w-5 text-alice-success" />
  if (status === 'skipped') return <SkipForward className="h-5 w-5 text-alice-muted" />
  if (status === 'error') return <XCircle className="h-5 w-5 text-alice-danger" />
  return <CircleDashed className="h-5 w-5 text-alice-lilac" />
}

interface ExecutionTimelineProps {
  run?: RunPayload
  isLoading?: boolean
}

export function ExecutionTimeline({ run, isLoading }: ExecutionTimelineProps) {
  if (isLoading && !run) {
    return (
      <div className="glass flex min-h-64 items-center justify-center rounded-3xl">
        <Spinner className="h-6 w-6" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="glass rounded-3xl p-6 text-alice-muted">Запуск не найден</div>
    )
  }

  const statusTone =
    run.status === 'applied' ? 'success' : run.status === 'failed' ? 'danger' : 'info'

  return (
    <div className="space-y-5">
      <Card className="rounded-3xl p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-alice-lilac/80">S5 · Execution</p>
            <h2 className="mt-1 text-2xl font-semibold">{run.mode_title}</h2>
            <p className="mt-1 text-sm text-alice-muted">
              {run.id} · policy {run.policy}
            </p>
          </div>
          <Badge tone={statusTone} className="text-sm">
            {run.status === 'running' ? (
              <span className="inline-flex items-center gap-2">
                <Spinner /> выполняется
              </span>
            ) : (
              run.status
            )}
          </Badge>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <Stat label="applied" value={run.counters.applied} />
          <Stat label="skipped" value={run.counters.skipped} />
          <Stat label="error" value={run.counters.error} />
        </div>

        {run.outcome_message ? (
          <p className="mt-4 rounded-2xl bg-white/5 px-4 py-3 text-sm text-alice-text/90">
            {run.outcome_message}
          </p>
        ) : null}
      </Card>

      <ol className="space-y-3">
        {run.steps.map((step) => {
          const longOp = LONG_RUNNING_DEVICES[step.device_id]
          const pendingLong = step.status === 'pending' && Boolean(longOp)

          return (
            <li key={step.sequence}>
              <Card
                className={cn(
                  'flex gap-4 p-4',
                  step.status === 'error' && 'border-alice-danger/40',
                  pendingLong && 'alice-glow',
                )}
              >
                <div className="pt-0.5">
                  {pendingLong ? <Spinner className="h-5 w-5" /> : <StepIcon status={step.status} />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-alice-muted">#{step.sequence}</span>
                    <h3 className="font-semibold">
                      {step.device_name || step.device_id}
                    </h3>
                    <Badge
                      tone={
                        step.status === 'error'
                          ? 'danger'
                          : step.status === 'applied'
                            ? 'success'
                            : 'default'
                      }
                    >
                      {step.status === 'error' ? 'Ошибка' : step.status}
                    </Badge>
                  </div>

                  {pendingLong && longOp ? (
                    <p className="mt-2 text-sm text-alice-cyan">
                      {longOp.label}… ожидание {longOp.expectedSec[0]}–{longOp.expectedSec[1]} с
                    </p>
                  ) : null}

                  <p className="mt-1 text-sm text-alice-muted">
                    target: {JSON.stringify(step.target)}
                    {step.duration_ms != null ? ` · ${step.duration_ms} мс` : ''}
                  </p>

                  {step.status === 'error' ? (
                    <div className="mt-3 rounded-xl border border-alice-danger/25 bg-alice-danger/10 px-3 py-2 text-sm">
                      <p className="font-medium text-alice-danger">
                        {step.error_text || step.error_code || 'Сбой устройства'}
                      </p>
                      {step.manual_hint ? (
                        <p className="mt-1 text-alice-text/85">
                          Подсказка: {step.manual_hint}
                        </p>
                      ) : (
                        <p className="mt-1 text-alice-muted">
                          Проверьте питание/сеть устройства и повторите режим после устранения.
                        </p>
                      )}
                    </div>
                  ) : null}
                </div>
              </Card>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl bg-white/5 px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-alice-muted">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
    </div>
  )
}
