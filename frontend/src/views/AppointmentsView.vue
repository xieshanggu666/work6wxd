<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  applyAppointment,
  cancelAppointment,
  createSession,
  deleteSession,
  getAppointmentStats,
  listAppointments,
  listMyAppointments,
  listSessions,
  reviewAppointment,
  updateSession,
} from '@/api/appointments'
import { listExams } from '@/api/exams'
import { useAuthStore } from '@/stores/auth'
import type {
  AppointmentDetail,
  AppointmentType,
  Exam,
  ExamAppointmentStats,
  ExamSessionWithBooked,
} from '@/types'

const auth = useAuthStore()
const isStudent = computed(() => auth.role === 'student')
const isAdmin = computed(() => auth.role === 'admin')

/* ---------- 页签 ---------- */
type TabKey = 'book' | 'mine' | 'review' | 'sessions' | 'stats'
const tabs = computed<Array<{ key: TabKey; label: string }>>(() => {
  if (isStudent.value) {
    return [
      { key: 'book', label: '场次预约' },
      { key: 'mine', label: '我的预约' },
    ]
  }
  const t: Array<{ key: TabKey; label: string }> = [{ key: 'review', label: '预约审核' }]
  if (isAdmin.value) t.push({ key: 'sessions', label: '场次与名额' })
  t.push({ key: 'stats', label: '预约统计' })
  return t
})
const activeTab = ref<TabKey>(isStudent.value ? 'book' : 'review')

const statusText: Record<string, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已驳回',
  cancelled: '已取消',
  completed: '已完成',
}
const statusClass: Record<string, string> = {
  pending: 'badge-draft',
  approved: 'badge-published',
  rejected: 'badge-ended',
  cancelled: '',
  completed: 'badge-type',
}
const typeText: Record<string, string> = { regular: '正考', retake: '补考' }

function fmtTime(t: string | null) {
  return t ? new Date(t).toLocaleString() : '-'
}

/* ---------- 学生：可预约场次 ---------- */
const sessions = ref<ExamSessionWithBooked[]>([])
const loadingSessions = ref(false)

async function loadSessions() {
  loadingSessions.value = true
  try {
    sessions.value = await listSessions()
  } finally {
    loadingSessions.value = false
  }
}

function sessionBookable(s: ExamSessionWithBooked) {
  const now = Date.now()
  return s.status === 'open' && s.remaining > 0 && new Date(s.end_time).getTime() > now
}

/* ---------- 学生：申请弹窗 ---------- */
const applyVisible = ref(false)
const applyError = ref('')
const applying = ref(false)
const applyForm = reactive({
  session_id: 0,
  exam_title: '',
  appointment_type: 'regular' as AppointmentType,
  reason: '',
})

function openApply(s: ExamSessionWithBooked) {
  applyForm.session_id = s.id
  applyForm.exam_title = s.exam_title
  applyForm.appointment_type = 'regular'
  applyForm.reason = ''
  applyError.value = ''
  applyVisible.value = true
}

async function submitApply() {
  if (applyForm.appointment_type === 'retake' && !applyForm.reason.trim()) {
    applyError.value = '补考申请请填写申请理由'
    return
  }
  applying.value = true
  applyError.value = ''
  try {
    await applyAppointment(applyForm.session_id, applyForm.appointment_type, applyForm.reason.trim())
    applyVisible.value = false
    window.alert('预约申请已提交，请等待教师审核')
    await Promise.all([loadSessions(), loadMine()])
  } catch (e) {
    applyError.value = e instanceof Error ? e.message : '申请失败'
  } finally {
    applying.value = false
  }
}

/* ---------- 学生：我的预约 ---------- */
const mine = ref<AppointmentDetail[]>([])

async function loadMine() {
  mine.value = await listMyAppointments()
}

async function cancelMine(id: number) {
  if (!window.confirm('确定取消该预约？')) return
  try {
    await cancelAppointment(id)
    await Promise.all([loadMine(), loadSessions()])
  } catch (e) {
    window.alert(e instanceof Error ? e.message : '取消失败')
  }
}

/* ---------- 教师：审核 ---------- */
const reviewList = ref<AppointmentDetail[]>([])
const reviewFilter = ref<'pending' | ''>('pending')

async function loadReview() {
  reviewList.value = await listAppointments(
    reviewFilter.value ? { status: reviewFilter.value as 'pending' } : {},
  )
}

async function review(id: number, approve: boolean) {
  let comment = ''
  if (!approve) {
    comment = window.prompt('请输入驳回原因（可空）') ?? ''
    if (comment === null) return
  }
  try {
    await reviewAppointment(id, approve, comment)
    await loadReview()
  } catch (e) {
    window.alert(e instanceof Error ? e.message : '操作失败')
  }
}

/* ---------- 管理员：场次与名额 ---------- */
const exams = ref<Exam[]>([])
const sessionModalVisible = ref(false)
const sessionError = ref('')
const savingSession = ref(false)
const sessionForm = reactive({
  exam_id: 0,
  name: '',
  start_time: '',
  end_time: '',
  quota: 50,
  max_attempts: 1,
})

function openSessionModal() {
  sessionForm.exam_id = exams.value[0]?.id ?? 0
  sessionForm.name = ''
  sessionForm.start_time = ''
  sessionForm.end_time = ''
  sessionForm.quota = 50
  sessionForm.max_attempts = 1
  sessionError.value = ''
  sessionModalVisible.value = true
}

async function submitSession() {
  if (!sessionForm.name.trim()) {
    sessionError.value = '请填写场次名称'
    return
  }
  if (!sessionForm.start_time || !sessionForm.end_time) {
    sessionError.value = '请选择考试时段'
    return
  }
  savingSession.value = true
  sessionError.value = ''
  try {
    await createSession({
      exam_id: sessionForm.exam_id,
      name: sessionForm.name.trim(),
      start_time: sessionForm.start_time,
      end_time: sessionForm.end_time,
      quota: sessionForm.quota,
      max_attempts: sessionForm.max_attempts,
    })
    sessionModalVisible.value = false
    await loadSessions()
  } catch (e) {
    sessionError.value = e instanceof Error ? e.message : '创建失败'
  } finally {
    savingSession.value = false
  }
}

async function toggleSession(s: ExamSessionWithBooked) {
  try {
    await updateSession(s.id, { status: s.status === 'open' ? 'closed' : 'open' })
    await loadSessions()
  } catch (e) {
    window.alert(e instanceof Error ? e.message : '操作失败')
  }
}

async function removeSession(id: number) {
  if (!window.confirm('确定删除该场次？')) return
  try {
    await deleteSession(id)
    await loadSessions()
  } catch (e) {
    window.alert(e instanceof Error ? e.message : '删除失败')
  }
}

/* ---------- 预约统计 ---------- */
const statsExamId = ref(0)
const stats = ref<ExamAppointmentStats | null>(null)

async function loadStats() {
  if (!statsExamId.value) return
  stats.value = await getAppointmentStats(statsExamId.value)
}

/* ---------- 初始化 ---------- */
onMounted(async () => {
  if (isStudent.value) {
    await Promise.all([loadSessions(), loadMine()])
  } else {
    const examPage = await listExams({ page: 1, page_size: 100 })
    exams.value = examPage.items
    statsExamId.value = exams.value[0]?.id ?? 0
    const jobs: Array<Promise<void>> = [loadReview(), loadStats()]
    if (isAdmin.value) jobs.push(loadSessions())
    await Promise.all(jobs)
  }
})
</script>

<template>
  <h2>📅 考试预约</h2>

  <div class="toolbar">
    <button
      v-for="t in tabs"
      :key="t.key"
      class="btn"
      :class="{ 'btn-primary': activeTab === t.key }"
      @click="activeTab = t.key"
    >{{ t.label }}</button>
  </div>

  <!-- 学生：可预约场次 -->
  <template v-if="activeTab === 'book'">
    <table class="table">
      <thead>
        <tr>
          <th>考试</th><th>场次</th><th>考试时段</th><th>剩余名额</th>
          <th>限考次数</th><th>状态</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in sessions" :key="s.id">
          <td>{{ s.exam_title }}</td>
          <td>{{ s.name }}</td>
          <td>{{ fmtTime(s.start_time) }} ~ {{ fmtTime(s.end_time) }}</td>
          <td>{{ s.remaining }} / {{ s.quota }}</td>
          <td>{{ s.max_attempts }} 次</td>
          <td>
            <span class="badge" :class="s.status === 'open' ? 'badge-published' : 'badge-ended'">
              {{ s.status === 'open' ? '开放中' : '已关闭' }}
            </span>
          </td>
          <td>
            <button
              class="btn btn-sm btn-primary"
              :disabled="!sessionBookable(s)"
              @click="openApply(s)"
            >{{ s.remaining <= 0 ? '名额已满' : '预约' }}</button>
          </td>
        </tr>
        <tr v-if="!loadingSessions && !sessions.length" class="empty-row">
          <td colspan="7">暂无可预约的考试场次</td>
        </tr>
      </tbody>
    </table>
  </template>

  <!-- 学生：我的预约 -->
  <template v-if="activeTab === 'mine'">
    <table class="table">
      <thead>
        <tr>
          <th>考试</th><th>场次</th><th>类型</th><th>第几次</th>
          <th>状态</th><th>审核意见</th><th>申请时间</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="a in mine" :key="a.id">
          <td>{{ a.exam_title }}</td>
          <td>{{ a.session_name }}</td>
          <td>{{ typeText[a.appointment_type] || a.appointment_type }}</td>
          <td>第 {{ a.attempt_no }} 次</td>
          <td><span class="badge" :class="statusClass[a.status]">{{ statusText[a.status] || a.status }}</span></td>
          <td>{{ a.review_comment || '-' }}</td>
          <td>{{ fmtTime(a.created_at) }}</td>
          <td>
            <button
              v-if="a.status === 'pending' || a.status === 'approved'"
              class="btn btn-sm btn-danger"
              @click="cancelMine(a.id)"
            >取消</button>
            <RouterLink
              v-if="a.status === 'approved'"
              class="btn btn-sm btn-primary"
              :to="{ name: 'exam-take', params: { examId: a.exam_id } }"
            >去考试</RouterLink>
          </td>
        </tr>
        <tr v-if="!mine.length" class="empty-row">
          <td colspan="8">暂无预约记录</td>
        </tr>
      </tbody>
    </table>
  </template>

  <!-- 教师：预约审核 -->
  <template v-if="activeTab === 'review'">
    <div class="toolbar">
      <select v-model="reviewFilter" @change="loadReview">
        <option value="pending">仅待审核</option>
        <option value="">全部预约</option>
      </select>
      <button class="btn" @click="loadReview">刷新</button>
    </div>
    <table class="table">
      <thead>
        <tr>
          <th>学生</th><th>考试</th><th>场次</th><th>类型</th><th>第几次</th>
          <th>申请理由</th><th>状态</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="a in reviewList" :key="a.id">
          <td>{{ a.real_name }}（{{ a.username }}）</td>
          <td>{{ a.exam_title }}</td>
          <td>{{ a.session_name }}</td>
          <td>{{ typeText[a.appointment_type] || a.appointment_type }}</td>
          <td>第 {{ a.attempt_no }} 次</td>
          <td>{{ a.reason || '-' }}</td>
          <td><span class="badge" :class="statusClass[a.status]">{{ statusText[a.status] || a.status }}</span></td>
          <td>
            <template v-if="a.status === 'pending'">
              <button class="btn btn-sm btn-primary" @click="review(a.id, true)">通过</button>
              <button class="btn btn-sm btn-danger" @click="review(a.id, false)">驳回</button>
            </template>
            <span v-else class="muted">{{ a.review_comment || '-' }}</span>
          </td>
        </tr>
        <tr v-if="!reviewList.length" class="empty-row">
          <td colspan="8">暂无预约申请</td>
        </tr>
      </tbody>
    </table>
  </template>

  <!-- 管理员：场次与名额 -->
  <template v-if="activeTab === 'sessions'">
    <div class="toolbar">
      <span class="spacer"></span>
      <button class="btn btn-primary" @click="openSessionModal">+ 新建场次</button>
    </div>
    <table class="table">
      <thead>
        <tr>
          <th>考试</th><th>场次</th><th>考试时段</th><th>已用/名额</th>
          <th>限考次数</th><th>状态</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in sessions" :key="s.id">
          <td>{{ s.exam_title }}</td>
          <td>{{ s.name }}</td>
          <td>{{ fmtTime(s.start_time) }} ~ {{ fmtTime(s.end_time) }}</td>
          <td>{{ s.booked }} / {{ s.quota }}</td>
          <td>{{ s.max_attempts }} 次</td>
          <td>
            <span class="badge" :class="s.status === 'open' ? 'badge-published' : 'badge-ended'">
              {{ s.status === 'open' ? '开放中' : '已关闭' }}
            </span>
          </td>
          <td>
            <button class="btn btn-sm" @click="toggleSession(s)">
              {{ s.status === 'open' ? '关闭预约' : '开放预约' }}
            </button>
            <button class="btn btn-sm btn-danger" @click="removeSession(s.id)">删除</button>
          </td>
        </tr>
        <tr v-if="!sessions.length" class="empty-row">
          <td colspan="7">暂无场次，点击右上角新建</td>
        </tr>
      </tbody>
    </table>
  </template>

  <!-- 教师/管理员：预约统计 -->
  <template v-if="activeTab === 'stats'">
    <div class="toolbar">
      <select v-model.number="statsExamId" @change="loadStats">
        <option v-for="e in exams" :key="e.id" :value="e.id">{{ e.title }}</option>
      </select>
      <button class="btn" @click="loadStats">刷新</button>
    </div>
    <template v-if="stats">
      <div class="card-grid">
        <div class="card stat-card">
          <div class="stat-num">{{ stats.total_appointments }}</div>
          <div class="stat-label">预约总数</div>
        </div>
        <div class="card stat-card">
          <div class="stat-num">{{ stats.by_status.pending || 0 }}</div>
          <div class="stat-label">待审核</div>
        </div>
        <div class="card stat-card">
          <div class="stat-num">{{ stats.regular_pass_rate }}%</div>
          <div class="stat-label">正考及格率（{{ stats.regular_attempts }} 人次）</div>
        </div>
        <div class="card stat-card">
          <div class="stat-num">{{ stats.retake_pass_rate }}%</div>
          <div class="stat-label">补考及格率（{{ stats.retake_attempts }} 人次）</div>
        </div>
      </div>
      <h3>场次名额使用情况</h3>
      <table class="table">
        <thead>
          <tr><th>场次</th><th>名额</th><th>已占用</th><th>剩余</th><th>已完成考试</th></tr>
        </thead>
        <tbody>
          <tr v-for="s in stats.sessions" :key="s.session_id">
            <td>{{ s.name }}</td>
            <td>{{ s.quota }}</td>
            <td>{{ s.booked }}</td>
            <td>{{ s.remaining }}</td>
            <td>{{ s.completed }}</td>
          </tr>
          <tr v-if="!stats.sessions.length" class="empty-row">
            <td colspan="5">该考试尚未配置场次</td>
          </tr>
        </tbody>
      </table>
    </template>
  </template>

  <!-- 学生：申请弹窗 -->
  <div v-if="applyVisible" class="modal-mask" @click.self="applyVisible = false">
    <div class="modal-content">
      <h3>预约考试 - {{ applyForm.exam_title }}</h3>
      <div class="form-group">
        <label>预约类型</label>
        <select v-model="applyForm.appointment_type">
          <option value="regular">正考（首次参加）</option>
          <option value="retake">补考（未通过后重考）</option>
        </select>
      </div>
      <div class="form-group">
        <label>申请理由{{ applyForm.appointment_type === 'retake' ? '（补考必填）' : '（选填）' }}</label>
        <textarea v-model="applyForm.reason" rows="3" placeholder="请简要说明"></textarea>
      </div>
      <div v-if="applyError" class="error-msg">{{ applyError }}</div>
      <div class="modal-actions">
        <button class="btn btn-primary" :disabled="applying" @click="submitApply">
          {{ applying ? '提交中...' : '提交申请' }}
        </button>
        <button class="btn" @click="applyVisible = false">取消</button>
      </div>
    </div>
  </div>

  <!-- 管理员：新建场次弹窗 -->
  <div v-if="sessionModalVisible" class="modal-mask" @click.self="sessionModalVisible = false">
    <div class="modal-content">
      <h3>新建考试场次</h3>
      <div class="form-group">
        <label>考试</label>
        <select v-model.number="sessionForm.exam_id">
          <option v-for="e in exams" :key="e.id" :value="e.id">{{ e.title }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>场次名称</label>
        <input v-model="sessionForm.name" type="text" placeholder="如：第一场次（上午）" />
      </div>
      <div class="form-group">
        <label>开始时间</label>
        <input v-model="sessionForm.start_time" type="datetime-local" />
      </div>
      <div class="form-group">
        <label>结束时间</label>
        <input v-model="sessionForm.end_time" type="datetime-local" />
      </div>
      <div class="form-group">
        <label>名额</label>
        <input v-model.number="sessionForm.quota" type="number" min="1" />
      </div>
      <div class="form-group">
        <label>每人限考次数（1=仅正考，2=正考+1次补考）</label>
        <input v-model.number="sessionForm.max_attempts" type="number" min="1" max="10" />
      </div>
      <div v-if="sessionError" class="error-msg">{{ sessionError }}</div>
      <div class="modal-actions">
        <button class="btn btn-primary" :disabled="savingSession" @click="submitSession">
          {{ savingSession ? '创建中...' : '创建' }}
        </button>
        <button class="btn" @click="sessionModalVisible = false">取消</button>
      </div>
    </div>
  </div>
</template>
