import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  fetchFaults,
  injectFault,
  removeFault,
  resetSimulator,
  setOccupancy,
} from '@/api/operator'
import type { FaultCreateBody, OccupancyBody } from '@/types/api'

export function useFaults() {
  return useQuery({
    queryKey: ['faults'],
    queryFn: () => fetchFaults(),
    refetchInterval: 4000,
  })
}

export function useInjectFault() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: FaultCreateBody) => injectFault(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['faults'] })
      void queryClient.invalidateQueries({ queryKey: ['room'] })
    },
  })
}

export function useRemoveFault() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (faultId: string) => removeFault(faultId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['faults'] })
      void queryClient.invalidateQueries({ queryKey: ['room'] })
    },
  })
}

export function useSetOccupancy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: OccupancyBody) => setOccupancy(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['room'] })
    },
  })
}

export function useResetSimulator() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => resetSimulator(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['room'] })
      void queryClient.invalidateQueries({ queryKey: ['faults'] })
      void queryClient.invalidateQueries({ queryKey: ['modes'] })
    },
  })
}
