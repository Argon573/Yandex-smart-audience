import { CLASSROOM_ID } from '@/lib/constants'
import { apiRequest } from '@/lib/api-client'
import type { RoomPlan } from '@/types/api'

export function fetchRoomPlan(): Promise<RoomPlan> {
  return apiRequest<RoomPlan>('/api/v1/room')
}

export function fetchClassroom(classroomId = CLASSROOM_ID): Promise<RoomPlan> {
  return apiRequest<RoomPlan>(`/api/v1/classrooms/${classroomId}`)
}
