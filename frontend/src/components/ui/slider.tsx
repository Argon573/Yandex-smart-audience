import { cn } from '@/lib/utils'

interface SliderProps {
  value: number
  min?: number
  max?: number
  step?: number
  onValueChange: (value: number) => void
  className?: string
  disabled?: boolean
}

export function Slider({
  value,
  min = 0,
  max = 100,
  step = 1,
  onValueChange,
  className,
  disabled,
}: SliderProps) {
  return (
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      disabled={disabled}
      onChange={(e) => onValueChange(Number(e.target.value))}
      className={cn(
        'h-2 w-full cursor-pointer appearance-none rounded-full bg-alice-surface-2 accent-alice-violet disabled:opacity-50',
        className,
      )}
    />
  )
}
