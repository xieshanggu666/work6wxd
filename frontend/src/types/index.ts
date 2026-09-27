/** 后端统一响应结构 */
export interface APIResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface PageResponse<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export type Role = 'admin' | 'teacher' | 'student'

export interface User {
  id: number
  username: string
  email: string
  real_name: string
  role: Role
  status: number
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export type QuestionType =
  | 'single_choice'
  | 'multiple_choice'
  | 'judgment'
  | 'fill_blank'
  | 'short_answer'
  | 'programming'

export interface QuestionOption {
  id?: number
  content: string
  is_correct: number
  order_index: number
}

export interface QuestionListItem {
  id: number
  question_type: QuestionType
  content: string
  difficulty: number
  knowledge_point_id: number
  subject_id: number
}

export interface Question extends QuestionListItem {
  analysis: string
  discrimination: number
  created_at: string
  options: QuestionOption[]
  tags: Tag[]
}

export interface QuestionCreatePayload {
  question_type: QuestionType
  content: string
  analysis?: string
  difficulty: number
  knowledge_point_id: number
  subject_id: number
  options?: QuestionOption[]
  tag_ids?: number[]
}

export interface Subject {
  id: number
  name: string
  code: string
  description: string
}

export interface KnowledgePoint {
  id: number
  name: string
  parent_id: number | null
  subject_id: number
  children?: KnowledgePoint[]
}

export interface Tag {
  id: number
  name: string
  color: string
}

export type ExamStatus = 'draft' | 'published' | 'ended'
export type ExamType = 'formal' | 'practice' | 'mock'

export interface Exam {
  id: number
  title: string
  description: string
  subject_id: number
  exam_type: ExamType
  duration_minutes: number
  total_score: number
  pass_score: number
  start_time: string | null
  end_time: string | null
  is_random_order: number
  is_option_random: number
  allow_back: number
  anti_cheat_enabled: number
  status: ExamStatus
  created_at: string
}

export interface ExamDetail extends Exam {
  question_count: number
}

export interface ExamCreatePayload {
  title: string
  description?: string
  subject_id: number
  exam_type?: ExamType
  duration_minutes: number
  total_score: number
  pass_score: number
  is_random_order?: number
  is_option_random?: number
  anti_cheat_enabled?: number
}

export interface ExamQuestionBrief {
  exam_question_id: number
  question_id: number
  question_type: QuestionType
  content: string
  score: number
  options: Array<{ id: number; content: string; is_correct?: number }>
}

export interface ExamStartData {
  attempt_id: number
  exam_id: number
  title: string
  duration_minutes: number
  total_score: number
  start_time: string
  questions: ExamQuestionBrief[]
}

export interface AnswerSubmit {
  question_id: number
  user_answer: string
  time_spent_seconds: number
}

export interface ExamAnswerResult {
  id: number
  question_id: number
  user_answer: string
  is_correct: number
  score: number
  time_spent_seconds: number
}

export interface ExamResult {
  attempt_id: number
  exam_id: number
  score: number
  total_score: number
  is_passed: boolean
  submit_time: string | null
  answers: ExamAnswerResult[]
  rank: number | null
  percentile: number | null
}

export interface Certificate {
  id: number
  certificate_no: string
  exam_id: number
  score: number
  issue_date: string
  is_valid: number
}

export interface ExamStats {
  exam_id: number
  attempt_count: number
  avg_score: number
  max_score: number
  min_score: number
  pass_rate: number
  distribution: Record<string, number>
}

export interface LeaderboardItem {
  user_id: number
  username: string
  real_name: string
  score: number
  rank: number
  submit_time: string | null
}
