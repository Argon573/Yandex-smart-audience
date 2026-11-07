import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { ExecutionTimeline } from '@/components/execution/ExecutionTimeline'
import { useRun } from '@/hooks/use-run'

export function ExecutionPage() {
  const { runId = null } = useParams()
  const { run, isLoading, isError } = useRun(runId)

  return (
    <div className="space-y-4">
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-sm font-medium text-alice-lilac hover:text-alice-text"
      >
        <ArrowLeft className="h-4 w-4" />
        Назад к пульту
      </Link>

      {isError ? (
        <div className="glass rounded-3xl p-6 text-alice-danger">
          Не удалось загрузить журнал выполнения
        </div>
      ) : (
        <ExecutionTimeline run={run} isLoading={isLoading} />
      )}
    </div>
  )
}
