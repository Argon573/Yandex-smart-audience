import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { ControlPlanePage } from '@/pages/ControlPlanePage'
import { ExecutionPage } from '@/pages/ExecutionPage'
import { OperatorPage } from '@/pages/OperatorPage'
import { LoginPage } from '@/pages/LoginPage'
import { hasAuthSession } from '@/lib/api-client'

export default function App() {
  const [authenticated, setAuthenticated] = useState(hasAuthSession)

  useEffect(() => {
    const update = () => setAuthenticated(hasAuthSession())
    window.addEventListener('smart-classroom-auth-changed', update)
    return () => window.removeEventListener('smart-classroom-auth-changed', update)
  }, [])

  if (!authenticated) return <LoginPage />

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<ControlPlanePage />} />
        <Route path="executions/:runId" element={<ExecutionPage />} />
        <Route path="operator" element={<OperatorPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
