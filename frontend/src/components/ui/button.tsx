import { cva, type VariantProps } from 'class-variance-authority'
import type { ButtonHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-xl text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-alice-cyan/70 disabled:pointer-events-none disabled:opacity-45',
  {
    variants: {
      variant: {
        primary:
          'bg-gradient-to-r from-alice-violet to-alice-purple text-white shadow-[0_8px_24px_rgba(139,92,246,0.35)] hover:brightness-110',
        secondary:
          'bg-alice-surface-2/80 text-alice-text border border-alice-border hover:border-alice-lilac/40',
        ghost: 'bg-transparent text-alice-lilac hover:bg-white/5',
        danger:
          'bg-alice-danger/20 text-alice-danger border border-alice-danger/40 hover:bg-alice-danger/30',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-10 px-4',
        lg: 'h-12 px-5 text-base',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return (
    <button className={cn(buttonVariants({ variant, size }), className)} {...props} />
  )
}
