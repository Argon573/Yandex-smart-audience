import { type FormEvent, useState } from 'react'
import { Sparkles } from 'lucide-react'

import { apiRequest, storeAuthTokens, type AuthTokens } from '@/lib/api-client'

type LoginResponse = AuthTokens & {
  user: { id: string; display_name: string; role: string }
}

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const tokens = await apiRequest<LoginResponse>('/api/v1/auth/login', {
        method: 'POST',
        body: { email, password },
      })
      storeAuthTokens(tokens)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось выполнить вход.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md items-center px-4 py-10">
      <section className="glass w-full rounded-3xl p-7 md:p-9">
        <div className="mb-7 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-alice-violet to-alice-cyan alice-glow">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-alice-lilac/80">Панель управления</p>
            <h1 className="text-xl font-bold text-gradient-alice">Умная аудитория</h1>
          </div>
        </div>
        <form className="space-y-4" onSubmit={submit}>
          <label className="block space-y-1.5 text-sm text-alice-muted">
            Email
            <input
              className="w-full rounded-xl border border-alice-border bg-alice-bg-elevated px-3.5 py-3 text-alice-text outline-none focus:border-alice-violet"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="block space-y-1.5 text-sm text-alice-muted">
            Пароль
            <input
              className="w-full rounded-xl border border-alice-border bg-alice-bg-elevated px-3.5 py-3 text-alice-text outline-none focus:border-alice-violet"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error && <p className="rounded-xl bg-rose-500/10 p-3 text-sm text-rose-300">{error}</p>}
          <button
            className="w-full rounded-xl bg-alice-violet px-4 py-3 font-semibold text-white transition hover:bg-purple-500 disabled:cursor-wait disabled:opacity-60"
            type="submit"
            disabled={busy}
          >
            {busy ? 'Входим…' : 'Войти'}
          </button>
        </form>
      </section>
    </main>
  )
}
