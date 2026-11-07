import { OperatorPanel } from '@/components/operator/OperatorPanel'
import { useClockTick } from '@/hooks/use-clock-tick'

export function OperatorPage() {
  useClockTick()
  return <OperatorPanel />
}
