import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchModes, previewMode } from '@/api/modes'
import { applyMode } from '@/api/runs'
import { createIdempotencyKey } from '@/lib/utils'
import type { RunCreateBody } from '@/types/api'

export function useModes() {
  return useQuery({
    queryKey: ['modes'],
    queryFn: () => fetchModes(),
  })
}

export function usePreviewMode() {
  return useMutation({
    mutationFn: (modeId: string) => previewMode(modeId),
  })
}

export function useApplyMode() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: RunCreateBody) =>
      applyMode(body, createIdempotencyKey(`mode-${body.mode_id}`)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['room'] })
      void queryClient.invalidateQueries({ queryKey: ['faults'] })
    },
  })
}
