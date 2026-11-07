import { AlertTriangle, ShieldAlert } from 'lucide-react'
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Spinner } from '@/components/ui/spinner'
import { useApplyMode, usePreviewMode } from '@/hooks/use-modes'
import { humanizeBlockingReason } from '@/lib/utils'
import { useUiStore } from '@/stores/ui-store'
import { ApiError } from '@/types/api'

interface PreviewModalProps {
  presenceDetected: boolean
}

export function PreviewModal({ presenceDetected }: PreviewModalProps) {
  const navigate = useNavigate()
  const previewOpen = useUiStore((s) => s.previewOpen)
  const selectedModeId = useUiStore((s) => s.selectedModeId)
  const ackWarnings = useUiStore((s) => s.ackWarnings)
  const closePreview = useUiStore((s) => s.closePreview)
  const toggleAckWarning = useUiStore((s) => s.toggleAckWarning)
  const setAckWarnings = useUiStore((s) => s.setAckWarnings)
  const setActiveRunId = useUiStore((s) => s.setActiveRunId)

  const preview = usePreviewMode()
  const apply = useApplyMode()

  useEffect(() => {
    if (previewOpen && selectedModeId) {
      setAckWarnings([])
      preview.mutate(selectedModeId)
    }
    // mutate/setAckWarnings стабильны; триггерим только на открытие режима
  }, [previewOpen, selectedModeId])

  const data = preview.data
  const lightOffRisk =
    Boolean(data?.steps.some((s) => {
      const turnsLightOff =
        s.device_id.startsWith('D0') &&
        (s.device_id === 'D01' || s.device_id === 'D05' || s.device_id === 'D06') &&
        s.target.on === false
      return turnsLightOff
    })) && presenceDetected

  const unacked = (data?.warnings ?? [])
    .map((w) => w.code)
    .filter((code) => !ackWarnings.includes(code))

  const canApply =
    Boolean(data?.can_apply) &&
    unacked.length === 0 &&
    !apply.isPending &&
    !preview.isPending

  const applyError =
    apply.error instanceof ApiError
      ? apply.error.message
      : apply.error
        ? 'Не удалось применить режим'
        : null

  const handleApply = () => {
    if (!selectedModeId || !data) return
    apply.mutate(
      {
        mode_id: selectedModeId,
        preview_hash: data.preview_hash,
        ack_warnings: ackWarnings,
      },
      {
        onSuccess: (run) => {
          setActiveRunId(run.id)
          closePreview()
          void navigate(`/executions/${run.id}`)
        },
      },
    )
  }

  return (
    <Dialog
      open={previewOpen}
      onClose={closePreview}
      title="Предпросмотр режима"
      description="S4 · дельта изменений без сайд-эффектов. Apply доступен только при выполнении предусловий."
      footer={
        <>
          <Button variant="secondary" onClick={closePreview}>
            Отмена
          </Button>
          <Button disabled={!canApply} onClick={handleApply}>
            {apply.isPending ? <Spinner /> : null}
            Применить
          </Button>
        </>
      }
    >
      {preview.isPending ? (
        <div className="flex justify-center py-10">
          <Spinner className="h-6 w-6" />
        </div>
      ) : preview.isError ? (
        <p className="text-alice-danger">
          {preview.error instanceof ApiError
            ? preview.error.message
            : 'Ошибка preview'}
        </p>
      ) : data ? (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            <Badge tone={data.can_apply ? 'success' : 'danger'}>
              {data.can_apply ? 'можно применить' : 'заблокировано'}
            </Badge>
            <Badge>hash {data.preview_hash.slice(0, 8)}</Badge>
            <Badge tone="info">
              Δ {data.summary.will_change ?? 0} · ok {data.summary.already_in_state ?? 0}
            </Badge>
          </div>

          {data.blocking_reasons.length > 0 ? (
            <div className="rounded-2xl border border-alice-danger/30 bg-alice-danger/10 p-4">
              <div className="mb-2 flex items-center gap-2 text-alice-danger">
                <ShieldAlert className="h-4 w-4" />
                <span className="font-semibold">Предусловия не выполнены</span>
              </div>
              <ul className="space-y-1 text-sm text-alice-text/90">
                {data.blocking_reasons.map((reason) => (
                  <li key={reason}>• {humanizeBlockingReason(reason)}</li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-alice-muted">
                Кнопка «Применить» заблокирована (например, проектор оффлайн).
              </p>
            </div>
          ) : null}

          {lightOffRisk ? (
            <div className="rounded-2xl border border-alice-warning/40 bg-alice-warning/10 p-4 text-sm">
              <div className="mb-1 flex items-center gap-2 text-alice-warning">
                <AlertTriangle className="h-4 w-4" />
                <span className="font-semibold">Люди в аудитории</span>
              </div>
              Датчик присутствия фиксирует движение, а режим выключает свет. Убедитесь, что это
              ожидаемо.
            </div>
          ) : null}

          {data.warnings.length > 0 ? (
            <div className="space-y-2">
              <p className="text-sm font-medium text-alice-lilac">Предупреждения (нужен ack)</p>
              {data.warnings.map((warning) => (
                <label
                  key={warning.code}
                  className="flex cursor-pointer items-start gap-3 rounded-xl border border-alice-border/70 bg-alice-surface/50 p-3"
                >
                  <input
                    type="checkbox"
                    className="mt-1 accent-alice-violet"
                    checked={ackWarnings.includes(warning.code)}
                    onChange={() => toggleAckWarning(warning.code)}
                  />
                  <span className="text-sm">
                    <span className="font-medium text-alice-text">{warning.code}</span>
                    <span className="mt-0.5 block text-alice-muted">{warning.text}</span>
                  </span>
                </label>
              ))}
            </div>
          ) : null}

          <div className="overflow-hidden rounded-2xl border border-white/10">
            <table className="w-full text-left text-sm">
              <thead className="bg-white/5 text-xs uppercase tracking-wide text-alice-muted">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Устройство</th>
                  <th className="px-3 py-2">Дельта</th>
                  <th className="px-3 py-2">Статус</th>
                </tr>
              </thead>
              <tbody>
                {data.steps.map((step) => (
                  <tr key={step.sequence} className="border-t border-white/5">
                    <td className="px-3 py-2 text-alice-muted">{step.sequence}</td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{step.device_name}</div>
                      <div className="text-xs text-alice-muted">{step.device_id}</div>
                    </td>
                    <td className="px-3 py-2 text-alice-lilac/90">
                      {step.delta ?? 'без изменений'}
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={step.status === 'will_change' ? 'info' : 'default'}>
                        {step.status}
                      </Badge>
                      {step.critical ? (
                        <Badge tone="warning" className="ml-1">
                          critical
                        </Badge>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {applyError ? <p className="text-sm text-alice-danger">{applyError}</p> : null}
        </div>
      ) : null}
    </Dialog>
  )
}
