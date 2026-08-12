<script setup>
import { onMounted, ref } from 'vue'
import { deleteTeam, getAdminStats, listAdminTeams, listUsers, resetUserPassword, setUserRole } from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { formatBytes } from '../utils/format'

const props = defineProps({ user: { type: Object, required: true } })

const stats = ref(null)
const users = ref([])
const teams = ref([])

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
    toast(err.message, 'error')
  }
})

async function toggleRole(u) {
  const next = u.role === 'admin' ? 'user' : 'admin'
  const ok = await confirmAction({
    title: next === 'admin' ? '设为系统管理员' : '取消管理员权限',
    message: `确定把 ${u.username} ${next === 'admin' ? '设为管理员' : '降为普通用户'}？`,
    confirmText: '确认变更',
  })
  if (!ok) return
  try {
    await setUserRole(u.id, next)
    users.value = await listUsers()
    toast('用户角色已更新', 'success')
  } catch (err) {
    toast(err.message, 'error')
  }
}

async function doResetPassword(u) {
  const np = window.prompt(`为 ${u.username} 设置新密码（至少 6 位）：`)
  if (!np) return
  if (np.length < 6) {
    toast('密码至少 6 位', 'error')
    return
  }
  try {
    await resetUserPassword(u.id, np)
    toast(`已重置 ${u.username} 的密码`, 'success')
  } catch (err) {
    toast(err.message, 'error')
  }
}

async function doDeleteTeam(t) {
  const ok = await confirmAction({
    title: '解散团队',
    message: `解散「${t.name}」？团队图片和视频将回到各上传者的个人空间。`,
    confirmText: '解散团队',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteTeam(t.id)
    teams.value = await listAdminTeams()
    toast('团队已解散', 'success')
  } catch (err) {
    toast(err.message, 'error')
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
        <div class="stat-num">{{ stats?.videos ?? '–' }}</div>
        <div class="stat-label">视频</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats?.media_total ?? '–' }}</div>
        <div class="stat-label">全部媒体</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats?.teams ?? '–' }}</div>
        <div class="stat-label">团队</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats ? formatBytes(stats.storage_bytes) : '–' }}</div>
        <div class="stat-label">存储占用</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats ? formatBytes(stats.pending_upload_bytes) : '–' }}</div>
        <div class="stat-label">待完成上传</div>
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
          <td class="user-actions">
            <button v-if="u.id !== user.id" class="ghost" @click="toggleRole(u)">
              {{ u.role === 'admin' ? '降为用户' : '设为管理员' }}
            </button>
            <button v-if="u.id !== user.id" class="ghost" title="重置密码" @click="doResetPassword(u)">重置密码</button>
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
