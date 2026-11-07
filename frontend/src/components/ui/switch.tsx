import { cn } from '@/lib/utils'

interface SwitchProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
  id?: string
  label?: string
}

export function Switch({ checked, onCheckedChange, disabled, id, label }: SwitchProps) {
  return (
    <label
      htmlFor={id}
      className={cn(
        'inline-flex cursor-pointer items-center gap-3',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          'relative h-6 w-11 rounded-full border transition',
          checked
            ? 'border-alice-violet bg-alice-violet alice-glow'
            : 'border-alice-border bg-alice-surface',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 left-0.5 h-[18px] w-[18px] rounded-full bg-white transition',
            checked && 'translate-x-5',
          )}
        />
      </button>
      {label ? <span className="text-sm text-alice-text">{label}</span> : null}
    </label>
  )
}
