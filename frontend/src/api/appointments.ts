import { http } from './request'
import type {
  AppointmentDetail,
  AppointmentStatus,
  AppointmentType,
  ExamAppointmentStats,
  ExamSessionWithBooked,
  SessionCreatePayload,
  SessionStatus,
} from '@/types'

/* ---------- 场次（管理员配置名额和时段） ---------- */
export function listSessions(examId?: number) {
  return http<ExamSessionWithBooked[]>({
    url: '/appointments/sessions',
    method: 'GET',
    params: examId ? { exam_id: examId } : {},
  })
}

export function createSession(data: SessionCreatePayload) {
  return http<ExamSessionWithBooked>({ url: '/appointments/sessions', method: 'POST', data })
}

export function updateSession(
  id: number,
  data: Partial<SessionCreatePayload> & { status?: SessionStatus },
) {
  return http<ExamSessionWithBooked>({ url: `/appointments/sessions/${id}`, method: 'PUT', data })
}

export function deleteSession(id: number) {
  return http<null>({ url: `/appointments/sessions/${id}`, method: 'DELETE' })
}

/* ---------- 学生：申请 / 我的预约 / 取消 ---------- */
export function applyAppointment(sessionId: number, appointmentType: AppointmentType, reason = '') {
  return http<AppointmentDetail>({
    url: '/appointments',
    method: 'POST',
    data: { session_id: sessionId, appointment_type: appointmentType, reason },
  })
}

export function listMyAppointments() {
  return http<AppointmentDetail[]>({ url: '/appointments/my', method: 'GET' })
}

export function cancelAppointment(id: number) {
  return http<AppointmentDetail>({ url: `/appointments/${id}/cancel`, method: 'POST' })
}

/* ---------- 教师：审核 ---------- */
export function listAppointments(params: { status?: AppointmentStatus; exam_id?: number } = {}) {
  return http<AppointmentDetail[]>({ url: '/appointments', method: 'GET', params })
}

export function reviewAppointment(id: number, approve: boolean, comment = '') {
  return http<AppointmentDetail>({
    url: `/appointments/${id}/review`,
    method: 'POST',
    data: { approve, comment },
  })
}

/* ---------- 预约驱动的统计 ---------- */
export function getAppointmentStats(examId: number) {
  return http<ExamAppointmentStats>({ url: `/appointments/stats/${examId}`, method: 'GET' })
}
