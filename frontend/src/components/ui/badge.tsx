import type { HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

const tones = {
  default: 'bg-alice-surface-2 text-alice-lilac border-alice-border',
  success: 'bg-alice-success/15 text-alice-success border-alice-success/30',
  warning: 'bg-alice-warning/15 text-alice-warning border-alice-warning/30',
  danger: 'bg-alice-danger/15 text-alice-danger border-alice-danger/30',
  info: 'bg-alice-cyan/15 text-alice-cyan border-alice-cyan/30',
} as const

export function Badge({
  className,
  tone = 'default',
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
        tones[tone],
        className,
      )}
      {...props}
    />
  )
}
