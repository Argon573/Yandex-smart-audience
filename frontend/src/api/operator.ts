import { CLASSROOM_ID } from '@/lib/constants'
import { apiRequest } from '@/lib/api-client'
import type {
  Fault,
  FaultCreateBody,
  FaultList,
  OccupancyBody,
  OccupancyResult,
} from '@/types/api'

export function fetchFaults(classroomId = CLASSROOM_ID): Promise<FaultList> {
  return apiRequest<FaultList>(`/api/v1/operator/classrooms/${classroomId}/simulator/faults`)
}

export function injectFault(
  body: FaultCreateBody,
  classroomId = CLASSROOM_ID,
): Promise<Fault> {
  return apiRequest<Fault>(`/api/v1/operator/classrooms/${classroomId}/simulator/faults`, {
    method: 'POST',
    body,
  })
}

export function removeFault(faultId: string): Promise<{ id: string; active: boolean }> {
  return apiRequest(`/api/v1/operator/simulator/faults/${faultId}`, {
    method: 'DELETE',
  })
}

export function setOccupancy(
  body: OccupancyBody,
  classroomId = CLASSROOM_ID,
): Promise<OccupancyResult> {
  return apiRequest<OccupancyResult>(
    `/api/v1/operator/classrooms/${classroomId}/simulator/occupancy`,
    { method: 'POST', body },
  )
}

export function resetSimulator(classroomId = CLASSROOM_ID): Promise<{
  restored: boolean
  state_version: number
  restored_devices: number
  faults_cleared: number
  runs_cleared: number
}> {
  return apiRequest(`/api/v1/operator/classrooms/${classroomId}/simulator/reset`, {
    method: 'POST',
  })
}
