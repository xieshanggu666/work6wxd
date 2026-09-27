<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { createExam, listExams, updateExam } from '@/api/exams'
import { listSubjects } from '@/api/questions'
import { useAuthStore } from '@/stores/auth'
import type { Exam, ExamStatus, ExamType, Subject } from '@/types'

const auth = useAuthStore()
const router = useRouter()

const exams = ref<Exam[]>([])
const subjects = ref<Subject[]>([])
const currentStatus = ref<ExamStatus | ''>('published')
const loading = ref(false)

const tabs: Array<{ label: string; value: ExamStatus | '' }> = [
  { label: '进行中', value: 'published' },
  { label: '未发布', value: 'draft' },
  { label: '已结束', value: 'ended' },
  { label: '全部', value: '' },
]

const statusText: Record<string, string> = {
  draft: '未发布',
  published: '进行中',
  ended: '已结束',
}

const examTypeText: Record<string, string> = {
  formal: '正式考试',
  practice: '练习',
  mock: '模拟考',
}

async function loadExams(status: ExamStatus | '') {
  currentStatus.value = status
  loading.value = true
  try {
    const data = await listExams({ status: status || undefined, page: 1, page_size: 100 })
    exams.value = data.items
  } finally {
    loading.value = false
  }
}

async function publishExam(id: number) {
  await updateExam(id, { status: 'published' })
  await loadExams(currentStatus.value)
}

async function endExam(id: number) {
  if (!window.confirm('确定结束该考试？结束后学生将无法继续答题。')) return
  await updateExam(id, { status: 'ended' })
  await loadExams(currentStatus.value)
}

// ---- 创建考试弹窗 ----
const modalVisible = ref(false)
const saving = ref(false)
const modalError = ref('')
const form = reactive({
  title: '',
  subject_id: 1,
  duration_minutes: 60,
  total_score: 100,
  pass_score: 60,
  exam_type: 'formal' as ExamType,
  anti_cheat_enabled: true,
})

function openModal() {
  form.title = ''
  form.subject_id = subjects.value[0]?.id || 1
  form.duration_minutes = 60
  form.total_score = 100
  form.pass_score = 60
  form.exam_type = 'formal'
  form.anti_cheat_enabled = true
  modalError.value = ''
  modalVisible.value = true
}

async function submitExam() {
  if (!form.title.trim()) {
    modalError.value = '请填写考试名称'
    return
  }
  saving.value = true
  modalError.value = ''
  try {
    const exam = await createExam({
      title: form.title.trim(),
      subject_id: form.subject_id,
      duration_minutes: form.duration_minutes,
      total_score: form.total_score,
      pass_score: form.pass_score,
      exam_type: form.exam_type,
      anti_cheat_enabled: form.anti_cheat_enabled ? 1 : 0,
    })
    modalVisible.value = false
    window.alert('考试已创建，请到题库添加题目后发布')
    router.push({ name: 'grades', params: { examId: exam.id } })
  } catch (e) {
    modalError.value = e instanceof Error ? e.message : '创建失败'
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  subjects.value = await listSubjects()
  await loadExams('published')
})
</script>

<template>
  <h2>🎯 考试中心</h2>

  <div class="toolbar">
    <button
      v-for="tab in tabs"
      :key="tab.value"
      class="btn"
      :class="{ 'btn-primary': currentStatus === tab.value }"
      @click="loadExams(tab.value)"
    >{{ tab.label }}</button>
    <span class="spacer"></span>
    <button v-if="auth.canEdit" class="btn btn-primary" @click="openModal">+ 创建考试</button>
  </div>

  <table class="table">
    <thead>
      <tr>
        <th>ID</th><th>考试名称</th><th>类型</th><th>时长</th>
        <th>总分</th><th>及格分</th><th>状态</th><th>操作</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="e in exams" :key="e.id">
        <td>{{ e.id }}</td>
        <td>{{ e.title }}</td>
        <td>{{ examTypeText[e.exam_type] || e.exam_type }}</td>
        <td>{{ e.duration_minutes }}分钟</td>
        <td>{{ e.total_score }}</td>
        <td>{{ e.pass_score }}</td>
        <td><span class="badge" :class="`badge-${e.status}`">{{ statusText[e.status] || e.status }}</span></td>
        <td>
          <RouterLink
            v-if="e.status === 'published'"
            class="btn btn-sm btn-primary"
            :to="{ name: 'exam-take', params: { examId: e.id } }"
          >开始考试</RouterLink>
          <button v-if="e.status === 'draft' && auth.canEdit" class="btn btn-sm" @click="publishExam(e.id)">
            发布
          </button>
          <button v-if="e.status === 'published' && auth.canEdit" class="btn btn-sm btn-danger" @click="endExam(e.id)">
            结束
          </button>
          <RouterLink class="btn btn-sm" :to="{ name: 'grades', params: { examId: e.id } }">
            统计
          </RouterLink>
        </td>
      </tr>
      <tr v-if="!loading && !exams.length" class="empty-row">
        <td colspan="8">暂无考试</td>
      </tr>
    </tbody>
  </table>

  <div v-if="modalVisible" class="modal-mask" @click.self="modalVisible = false">
    <div class="modal-content">
      <h3>创建考试</h3>
      <div class="form-group">
        <label>名称</label>
        <input v-model="form.title" type="text" />
      </div>
      <div class="form-group">
        <label>科目</label>
        <select v-model.number="form.subject_id">
          <option v-for="s in subjects" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>时长(分钟)</label>
        <input v-model.number="form.duration_minutes" type="number" min="1" />
      </div>
      <div class="form-group">
        <label>总分</label>
        <input v-model.number="form.total_score" type="number" min="1" />
      </div>
      <div class="form-group">
        <label>及格分</label>
        <input v-model.number="form.pass_score" type="number" min="0" />
      </div>
      <div class="form-group">
        <label>题型</label>
        <select v-model="form.exam_type">
          <option value="formal">正式考试</option>
          <option value="practice">练习</option>
          <option value="mock">模拟考</option>
        </select>
      </div>
      <div class="form-group">
        <label>
          <input v-model="form.anti_cheat_enabled" type="checkbox" /> 开启防作弊（切屏检测）
        </label>
      </div>
      <div v-if="modalError" class="error-msg">{{ modalError }}</div>
      <div class="modal-actions">
        <button class="btn btn-primary" :disabled="saving" @click="submitExam">
          {{ saving ? '创建中...' : '创建' }}
        </button>
        <button class="btn" @click="modalVisible = false">取消</button>
      </div>
    </div>
  </div>
</template>
