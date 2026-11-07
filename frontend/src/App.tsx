import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { ControlPlanePage } from '@/pages/ControlPlanePage'
import { ExecutionPage } from '@/pages/ExecutionPage'
import { OperatorPage } from '@/pages/OperatorPage'

export default function App() {
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
