<script setup>
import { onMounted, ref } from 'vue'
import { deleteTeam, getAdminStats, listAdminTeams, listUsers, setUserRole } from '../api'

const props = defineProps({ user: { type: Object, required: true } })

const stats = ref(null)
const users = ref([])
const teams = ref([])

function fmtBytes(n) {
  if (n >= 1 << 30) return `${(n / (1 << 30)).toFixed(2)} GB`
  if (n >= 1 << 20) return `${(n / (1 << 20)).toFixed(2)} MB`
  if (n >= 1 << 10) return `${(n / (1 << 10)).toFixed(2)} KB`
  return `${n} B`
}

function fmtDate(s) {
  return new Date(s).toLocaleString()
}

onMounted(async () => {
  try {
    const [s, u, t] = await Promise.all([getAdminStats(), listUsers(), listAdminTeams()])
    stats.value = s
    users.value = u
    teams.value = t
  } catch (err) {
    window.alert(err.message)
  }
})

async function toggleRole(u) {
  const next = u.role === 'admin' ? 'user' : 'admin'
  if (!window.confirm(`把 ${u.username} ${next === 'admin' ? '设为管理员' : '降为普通用户'}？`)) return
  try {
    await setUserRole(u.id, next)
    users.value = await listUsers()
  } catch (err) {
    window.alert(err.message)
  }
}

async function doDeleteTeam(t) {
  if (!window.confirm(`解散团队「${t.name}」？团队图片将回到上传者的个人空间。`)) return
  try {
    await deleteTeam(t.id)
    teams.value = await listAdminTeams()
  } catch (err) {
    window.alert(err.message)
  }
}
</script>

<template>
  <section>
    <h2 class="section-title">系统概览</h2>
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-num">{{ stats?.users ?? '–' }}</div>
        <div class="stat-label">用户</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats?.images ?? '–' }}</div>
        <div class="stat-label">图片</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats?.teams ?? '–' }}</div>
        <div class="stat-label">团队</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats ? fmtBytes(stats.storage_bytes) : '–' }}</div>
        <div class="stat-label">存储占用</div>
      </div>
    </div>

    <h2 class="section-title">用户管理 <span class="count">{{ users.length }}</span></h2>
    <table class="data-table">
      <thead>
        <tr><th>ID</th><th>用户名</th><th>角色</th><th>注册时间</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.id">
          <td class="muted">{{ u.id }}</td>
          <td class="username">{{ u.username }}</td>
          <td>
            <span class="role-badge" :class="{ admin: u.role === 'admin' }">
              {{ u.role === 'admin' ? '管理员' : '用户' }}
            </span>
          </td>
          <td class="muted">{{ fmtDate(u.created_at) }}</td>
          <td>
            <button v-if="u.id !== user.id" class="ghost" @click="toggleRole(u)">
              {{ u.role === 'admin' ? '降为用户' : '设为管理员' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <h2 class="section-title">团队总览 <span class="count">{{ teams.length }}</span></h2>
    <table class="data-table">
      <thead>
        <tr><th>ID</th><th>团队</th><th>简介</th><th>拥有者</th><th>成员数</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="t in teams" :key="t.id">
          <td class="muted">{{ t.id }}</td>
          <td class="username">{{ t.name }}</td>
          <td class="muted">{{ t.description || '–' }}</td>
          <td>{{ t.owner_username }}</td>
          <td>{{ t.member_count }}</td>
          <td><button class="ghost danger" @click="doDeleteTeam(t)">解散</button></td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
