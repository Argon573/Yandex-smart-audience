import {
  BookOpen,
  Coffee,
  MonitorPlay,
  Power,
  Sunrise,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { MODE_META } from '@/lib/constants'
import { cn } from '@/lib/utils'
import type { ModeSummary } from '@/types/api'

const ICONS: Record<string, LucideIcon> = {
  sunrise: Sunrise,
  book: BookOpen,
  presentation: MonitorPlay,
  coffee: Coffee,
  power: Power,
}

interface ModePanelProps {
  modes?: ModeSummary[]
  isLoading: boolean
  selectedModeId: string | null
  onSelect: (modeId: string) => void
  onPreview: (modeId: string) => void
  previewPending?: boolean
}

export function ModePanel({
  modes,
  isLoading,
  selectedModeId,
  onSelect,
  onPreview,
  previewPending,
}: ModePanelProps) {
  return (
    <aside className="glass sticky top-4 space-y-4 rounded-3xl p-5">
      <div>
        <h2 className="text-lg font-semibold">Режимы занятия</h2>
        <p className="text-sm text-alice-muted">S3 · выберите сценарий и откройте preview</p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : (
        <div className="space-y-3">
          {(modes ?? []).map((mode) => {
            const meta = MODE_META[mode.id]
            const Icon = ICONS[meta?.icon ?? 'book'] ?? BookOpen
            const active = selectedModeId === mode.id

            return (
              <Card
                key={mode.id}
                className={cn(
                  'cursor-pointer p-3.5 transition',
                  active && 'alice-glow border-alice-violet/50',
                  `bg-gradient-to-br ${meta?.accent ?? 'from-violet-500/10 to-transparent'}`,
                )}
                onClick={() => onSelect(mode.id)}
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-alice-lilac" />
                    <CardTitle className="text-sm">{mode.title}</CardTitle>
                  </div>
                  <Badge tone={mode.enabled ? 'success' : 'danger'}>
                    {mode.enabled ? `${mode.step_count} шагов` : 'выкл'}
                  </Badge>
                </div>
                <CardDescription className="mb-3 text-xs">
                  {mode.description || meta?.hint}
                </CardDescription>
                <Button
                  size="sm"
                  className="w-full"
                  disabled={!mode.enabled || (previewPending && active)}
                  onClick={(e) => {
                    e.stopPropagation()
                    onPreview(mode.id)
                  }}
                >
                  {previewPending && active ? <Spinner /> : null}
                  Preview
                </Button>
              </Card>
            )
          })}
        </div>
      )}
    </aside>
  )
}
