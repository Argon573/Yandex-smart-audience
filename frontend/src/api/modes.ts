import { CLASSROOM_ID } from '@/lib/constants'
import { apiRequest } from '@/lib/api-client'
import type { ModeList, PreviewResult } from '@/types/api'

export function fetchModes(classroomId = CLASSROOM_ID): Promise<ModeList> {
  return apiRequest<ModeList>(`/api/v1/classrooms/${classroomId}/modes`)
}

export function previewMode(
  modeId: string,
  classroomId = CLASSROOM_ID,
): Promise<PreviewResult> {
  return apiRequest<PreviewResult>(
    `/api/v1/classrooms/${classroomId}/modes/${modeId}/preview`,
    { method: 'POST' },
  )
}
