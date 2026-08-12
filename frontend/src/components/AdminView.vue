<script setup>
import { onMounted, reactive, ref } from 'vue'
import {
  createUser,
  deleteTeam,
  deleteUser,
  getAdminStats,
  listAdminTeams,
  listUsers,
  resetUserPassword,
  setUserRole,
} from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { formatBytes } from '../utils/format'
import BaseModal from './BaseModal.vue'

const props = defineProps({ user: { type: Object, required: true } })

const stats = ref(null)
const users = ref([])
const teams = ref([])
const loading = ref(true)
const dialogMode = ref('')
const targetUser = ref(null)
const submitting = ref(false)
const formError = ref('')
const userForm = reactive({ username: '', password: '', confirmPassword: '', role: 'user' })

function fmtDate(value) {
  return new Date(value).toLocaleString()
}

async function loadDashboard() {
  loading.value = true
  try {
    const [nextStats, nextUsers, nextTeams] = await Promise.all([
      getAdminStats(),
      listUsers(),
      listAdminTeams(),
    ])
    stats.value = nextStats
    users.value = nextUsers
    teams.value = nextTeams
  } catch (error) {
    toast(error.message, 'error')
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)

async function toggleRole(item) {
  const next = item.role === 'admin' ? 'user' : 'admin'
  const ok = await confirmAction({
    title: next === 'admin' ? '设为系统管理员' : '取消管理员权限',
    message: `确定把 ${item.username} ${next === 'admin' ? '设为管理员' : '降为普通用户'}？`,
    confirmText: '确认变更',
  })
  if (!ok) return
  try {
    const updated = await setUserRole(item.id, next)
    Object.assign(item, updated)
    toast('用户角色已更新', 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}

function resetForm() {
  Object.assign(userForm, { username: '', password: '', confirmPassword: '', role: 'user' })
  formError.value = ''
}

function openCreateUser() {
  resetForm()
  targetUser.value = null
  dialogMode.value = 'create'
}

function openResetPassword(item) {
  resetForm()
  targetUser.value = item
  dialogMode.value = 'reset'
}

function resetDialog() {
  dialogMode.value = ''
  targetUser.value = null
  resetForm()
}

function closeDialog() {
  if (submitting.value) return
  resetDialog()
}

function validateUserForm() {
  if (dialogMode.value === 'create') {
    if (!/^[a-zA-Z0-9_-]{3,64}$/.test(userForm.username.trim())) {
      return '用户名需为 3–64 位，仅支持字母、数字、下划线和连字符'
    }
  }
  if (userForm.password.length < 6 || userForm.password.length > 128) return '密码需为 6–128 位'
  if (userForm.password !== userForm.confirmPassword) return '两次输入的密码不一致'
  return ''
}

async function submitUserForm() {
  formError.value = validateUserForm()
  if (formError.value) return
  submitting.value = true
  try {
    if (dialogMode.value === 'create') {
      const created = await createUser(userForm.username.trim(), userForm.password, userForm.role)
      users.value.push(created)
      users.value.sort((a, b) => a.id - b.id)
      if (stats.value) stats.value.users = users.value.length
      toast(`用户 ${created.username} 已创建`, 'success')
    } else {
      await resetUserPassword(targetUser.value.id, userForm.password)
      toast(`已重置 ${targetUser.value.username} 的密码`, 'success')
    }
    resetDialog()
  } catch (error) {
    formError.value = error.message
  } finally {
    submitting.value = false
  }
}

async function doDeleteUser(item) {
  const ok = await confirmAction({
    title: '删除用户',
    message: `确定永久删除「${item.username}」？其媒体文件、上传会话、API Key 和团队关系都会被清理，此操作不可恢复。`,
    confirmText: '永久删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteUser(item.id)
    await loadDashboard()
    toast(`用户 ${item.username} 已删除`, 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}

async function doDeleteTeam(team) {
  const ok = await confirmAction({
    title: '解散团队',
    message: `解散「${team.name}」？团队图片和视频将回到各上传者的个人空间。`,
    confirmText: '解散团队',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteTeam(team.id)
    await loadDashboard()
    toast('团队已解散', 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}
</script>

<template>
  <section class="admin-view">
    <div class="section-heading">
      <div>
        <p class="eyebrow">系统控制台</p>
        <h2>管理中心</h2>
        <p>查看媒体存储状态，管理用户与协作团队。</p>
      </div>
      <button class="primary" type="button" @click="openCreateUser">＋ 创建用户</button>
    </div>

    <div class="stat-cards" :aria-busy="loading">
      <div class="stat-card"><div class="stat-num">{{ stats?.users ?? '–' }}</div><div class="stat-label">用户</div></div>
      <div class="stat-card"><div class="stat-num">{{ stats?.images ?? '–' }}</div><div class="stat-label">图片</div></div>
      <div class="stat-card"><div class="stat-num">{{ stats?.videos ?? '–' }}</div><div class="stat-label">视频</div></div>
      <div class="stat-card"><div class="stat-num">{{ stats?.media_total ?? '–' }}</div><div class="stat-label">全部媒体</div></div>
      <div class="stat-card"><div class="stat-num">{{ stats?.teams ?? '–' }}</div><div class="stat-label">团队</div></div>
      <div class="stat-card"><div class="stat-num">{{ stats ? formatBytes(stats.storage_bytes) : '–' }}</div><div class="stat-label">存储占用</div></div>
      <div class="stat-card"><div class="stat-num">{{ stats ? formatBytes(stats.pending_upload_bytes) : '–' }}</div><div class="stat-label">待完成上传</div></div>
    </div>

    <div class="admin-section-head">
      <div><h3>用户管理</h3><p>创建账号、配置权限或处理离职账号。</p></div>
      <span class="total-badge">{{ users.length }} 位</span>
    </div>
    <div class="table-shell">
      <table class="data-table admin-table">
        <thead><tr><th>用户</th><th>角色</th><th>注册时间</th><th><span class="sr-only">操作</span></th></tr></thead>
        <tbody>
          <tr v-for="item in users" :key="item.id">
            <td><span class="admin-user-avatar">{{ item.username.slice(0, 1).toUpperCase() }}</span><span class="username">{{ item.username }}</span><small>#{{ item.id }}</small></td>
            <td><span class="role-badge" :class="{ admin: item.role === 'admin' }">{{ item.role === 'admin' ? '管理员' : '用户' }}</span></td>
            <td class="muted">{{ fmtDate(item.created_at) }}</td>
            <td>
              <div v-if="item.id !== user.id" class="user-actions">
                <button class="ghost" @click="toggleRole(item)">{{ item.role === 'admin' ? '降为用户' : '设为管理员' }}</button>
                <button class="ghost" @click="openResetPassword(item)">重置密码</button>
                <button class="ghost danger" @click="doDeleteUser(item)">删除</button>
              </div>
              <span v-else class="muted">当前账号</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="admin-section-head">
      <div><h3>团队总览</h3><p>查看全部协作空间及其负责人。</p></div>
      <span class="total-badge">{{ teams.length }} 个</span>
    </div>
    <div class="table-shell">
      <table class="data-table admin-table">
        <thead><tr><th>团队</th><th>简介</th><th>拥有者</th><th>成员</th><th><span class="sr-only">操作</span></th></tr></thead>
        <tbody>
          <tr v-for="team in teams" :key="team.id">
            <td><span class="username">{{ team.name }}</span><small>#{{ team.id }}</small></td>
            <td class="muted">{{ team.description || '暂无简介' }}</td>
            <td>{{ team.owner_username }}</td>
            <td>{{ team.member_count }}</td>
            <td><button class="ghost danger" @click="doDeleteTeam(team)">解散</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <BaseModal
      v-if="dialogMode"
      :title="dialogMode === 'create' ? '创建用户' : `重置 ${targetUser?.username} 的密码`"
      :description="dialogMode === 'create' ? '创建后，用户可以立即登录媒体库。' : '保存后旧密码会立即失效。'"
      labelled-by="admin-user-dialog-title"
      @close="closeDialog"
    >
      <form id="admin-user-form" class="admin-user-form" @submit.prevent="submitUserForm">
        <label v-if="dialogMode === 'create'">
          <span>用户名</span>
          <input v-model="userForm.username" autofocus autocomplete="off" maxlength="64" placeholder="例如 media_editor" />
          <small>3–64 位，仅支持字母、数字、下划线和连字符。</small>
        </label>
        <label>
          <span>新密码</span>
          <input v-model="userForm.password" :autofocus="dialogMode === 'reset'" type="password" autocomplete="new-password" maxlength="128" placeholder="至少 6 位" />
        </label>
        <label>
          <span>确认密码</span>
          <input v-model="userForm.confirmPassword" type="password" autocomplete="new-password" maxlength="128" placeholder="再次输入密码" />
        </label>
        <label v-if="dialogMode === 'create'">
          <span>系统角色</span>
          <select v-model="userForm.role">
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
        </label>
        <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
      </form>
      <template #footer>
        <button class="ghost" type="button" :disabled="submitting" @click="closeDialog">取消</button>
        <button class="primary" type="submit" form="admin-user-form" :disabled="submitting">
          {{ submitting ? '保存中…' : dialogMode === 'create' ? '创建用户' : '保存新密码' }}
        </button>
      </template>
    </BaseModal>
  </section>
</template>

<style scoped>
.admin-section-head {
  margin: 34px 0 12px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.admin-section-head h3 { margin: 0 0 2px; font-size: 17px; }
.admin-section-head p { margin: 0; color: var(--muted); font-size: 12px; }
.table-shell { overflow-x: auto; border-radius: 14px; }
.admin-table { min-width: 720px; margin: 0; }
.admin-table td:first-child { white-space: nowrap; }
.admin-table td:last-child { text-align: right; }
.admin-table small { margin-left: 7px; color: var(--muted-light); }
.admin-user-avatar {
  width: 28px;
  height: 28px;
  margin-right: 9px;
  display: inline-grid;
  place-items: center;
  border-radius: 9px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11px;
  font-weight: 750;
}

.user-actions { justify-content: flex-end; }
.admin-user-form { display: grid; gap: 15px; }
.admin-user-form label { display: grid; gap: 6px; color: var(--text); font-size: 12px; font-weight: 650; }
.admin-user-form input,
.admin-user-form select {
  width: 100%;
  min-height: 42px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 11px;
  background: var(--panel);
  color: var(--text);
  outline: 0;
}
.admin-user-form input:focus,
.admin-user-form select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgb(37 99 235 / 10%); }
.admin-user-form small { color: var(--muted); font-size: 10px; font-weight: 400; }
.admin-user-form .form-error { margin: 0; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

@media (max-width: 580px) {
  .section-heading { align-items: stretch; flex-direction: column; }
  .section-heading > button { align-self: flex-start; }
}
</style>
