<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

onMounted(() => {
  if (!auth.user) auth.fetchCurrentUser()
})

function handleLogout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <nav class="topbar">
    <div class="brand">📝 在线考试与题库系统</div>
    <div class="nav-links">
      <RouterLink :to="{ name: 'dashboard' }">仪表盘</RouterLink>
      <RouterLink :to="{ name: 'questions' }">题库管理</RouterLink>
      <RouterLink :to="{ name: 'exams' }">考试中心</RouterLink>
      <RouterLink :to="{ name: 'certificates' }">我的证书</RouterLink>
      <button type="button" @click="handleLogout">退出登录</button>
      <span v-if="auth.user" class="nav-user">
        {{ auth.user.real_name }}（{{ auth.user.role }}）
      </span>
    </div>
  </nav>
  <main class="container">
    <RouterView />
  </main>
</template>
