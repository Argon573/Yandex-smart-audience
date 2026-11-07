import { LayoutDashboard, Sparkles, Wrench } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { cn } from '@/lib/utils'

const nav = [
  { to: '/', label: 'Control Plane', icon: LayoutDashboard, end: true },
  { to: '/operator', label: 'Симулятор', icon: Wrench, end: false },
]

export function AppShell() {
  return (
    <div className="mx-auto flex min-h-screen max-w-[1400px] flex-col px-4 py-5 md:px-6">
      <header className="glass mb-6 flex flex-wrap items-center justify-between gap-4 rounded-3xl px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-alice-violet to-alice-cyan alice-glow">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-alice-lilac/80">Яндекс · Алиса</p>
            <h1 className="text-lg font-bold md:text-xl">
              <span className="text-gradient-alice">Умная аудитория</span>
            </h1>
          </div>
        </div>

        <nav className="flex items-center gap-2">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-medium transition',
                  isActive
                    ? 'bg-alice-violet/25 text-alice-text alice-glow'
                    : 'text-alice-muted hover:bg-white/5 hover:text-alice-text',
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="flex-1 pb-8">
        <Outlet />
      </main>
    </div>
  )
}
