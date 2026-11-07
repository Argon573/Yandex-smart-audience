import { RoomPlanView } from '@/components/control-plane/RoomPlanView'
import { ModePanel } from '@/components/modes/ModePanel'
import { PreviewModal } from '@/components/preview/PreviewModal'
import { useClockTick } from '@/hooks/use-clock-tick'
import { useModes } from '@/hooks/use-modes'
import { useRoomPlan } from '@/hooks/use-room'
import { useUiStore } from '@/stores/ui-store'
import { ApiError } from '@/types/api'

export function ControlPlanePage() {
  useClockTick()

  const room = useRoomPlan()
  const modes = useModes()

  const selectedModeId = useUiStore((s) => s.selectedModeId)
  const previewOpen = useUiStore((s) => s.previewOpen)
  const setSelectedModeId = useUiStore((s) => s.setSelectedModeId)
  const openPreview = useUiStore((s) => s.openPreview)

  const occupancy = room.data?.zones
    .flatMap((z) => z.devices)
    .find((d) => d.id === 'D11')
  const presenceDetected = String(occupancy?.state?.motion ?? '') === 'detected'

  return (
    <>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <RoomPlanView
          room={room.data}
          isLoading={room.isLoading}
          errorMessage={
            room.error instanceof ApiError
              ? room.error.message
              : room.error
                ? 'сеть недоступна'
                : undefined
          }
        />
        <ModePanel
          modes={modes.data?.items}
          isLoading={modes.isLoading}
          selectedModeId={selectedModeId}
          onSelect={setSelectedModeId}
          onPreview={openPreview}
          previewPending={previewOpen}
        />
      </div>
      <PreviewModal presenceDetected={presenceDetected} />
    </>
  )
}
