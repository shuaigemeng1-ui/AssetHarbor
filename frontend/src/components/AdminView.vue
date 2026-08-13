<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  createUser,
  deleteTeam,
  deleteUser,
  getAdminStats,
  getAdminTrafficStats,
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
const traffic = ref(null)
const trafficDays = ref(7)
const trafficLoading = ref(true)
const trafficError = ref('')
const dialogMode = ref('')
const targetUser = ref(null)
const submitting = ref(false)
const formError = ref('')
const userForm = reactive({ username: '', password: '', confirmPassword: '', role: 'user' })
let trafficGeneration = 0

const trafficRanges = [
  { value: 7, label: '近 7 天' },
  { value: 30, label: '近 30 天' },
  { value: 90, label: '近 90 天' },
]
const trafficSummary = computed(() => traffic.value?.summary || {})
const maxDailyRequests = computed(() => Math.max(
  1,
  ...(traffic.value?.daily || []).map(item => Number(item.request_count) || 0),
))
const membersByUsage = computed(() => [...(traffic.value?.members || [])].sort((a, b) => (
  Number(b.total_usage_bytes || 0) - Number(a.total_usage_bytes || 0)
)))
const topRoutes = computed(() => [...(traffic.value?.routes || [])]
  .sort((a, b) => Number(b.request_count || 0) - Number(a.request_count || 0))
  .slice(0, 8))
const topApiKeys = computed(() => [...(traffic.value?.api_keys || [])]
  .sort((a, b) => Number(b.request_count || 0) - Number(a.request_count || 0))
  .slice(0, 8))

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-CN')
}

function formatErrorRate(summary) {
  const requests = Number(summary?.request_count || 0)
  return requests ? `${(Number(summary?.error_count || 0) / requests * 100).toFixed(1)}%` : '0%'
}

function fmtDay(value) {
  if (!value) return '—'
  return new Date(`${value}T00:00:00Z`).toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    timeZone: 'UTC',
  })
}

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

async function loadTraffic() {
  const generation = ++trafficGeneration
  const days = Number(trafficDays.value)
  trafficLoading.value = true
  trafficError.value = ''
  try {
    const result = await getAdminTrafficStats(days)
    if (generation !== trafficGeneration || days !== Number(trafficDays.value)) return
    traffic.value = result
  } catch (error) {
    if (generation === trafficGeneration) trafficError.value = error.message
  } finally {
    if (generation === trafficGeneration) trafficLoading.value = false
  }
}

onMounted(() => {
  loadDashboard()
  loadTraffic()
})

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
      await loadTraffic()
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
    await Promise.all([loadDashboard(), loadTraffic()])
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
    await Promise.all([loadDashboard(), loadTraffic()])
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
        <p>查看媒体存储与 API 使用状态，管理用户与协作团队。</p>
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

    <div class="admin-section-head traffic-section-head">
      <div>
        <h3>API 调用与流量</h3>
        <p>仅统计使用用户生成 API Key 鉴权的请求，管理页面操作与匿名访问不计入；流量按 UTC 自然日和应用层字节计量。</p>
      </div>
      <label class="traffic-range">
        <span>统计范围</span>
        <select v-model.number="trafficDays" :disabled="trafficLoading" @change="loadTraffic">
          <option v-for="range in trafficRanges" :key="range.value" :value="range.value">{{ range.label }}</option>
        </select>
      </label>
    </div>

    <div class="traffic-stat-cards" :aria-busy="trafficLoading" aria-live="polite">
      <article class="traffic-stat-card">
        <span>调用数量</span>
        <strong>{{ traffic ? formatNumber(trafficSummary.request_count) : '–' }}</strong>
        <small>API Key · {{ traffic?.start_date || '—' }} 至 {{ traffic?.end_date || '—' }}</small>
      </article>
      <article class="traffic-stat-card">
        <span>总流量</span>
        <strong>{{ traffic ? formatBytes(trafficSummary.total_bytes) : '–' }}</strong>
        <small>请求与响应合计</small>
      </article>
      <article class="traffic-stat-card">
        <span>请求流量</span>
        <strong>{{ traffic ? formatBytes(trafficSummary.request_bytes) : '–' }}</strong>
        <small>上传及 API 请求体</small>
      </article>
      <article class="traffic-stat-card">
        <span>响应流量</span>
        <strong>{{ traffic ? formatBytes(trafficSummary.response_bytes) : '–' }}</strong>
        <small>媒体读取及 API 响应</small>
      </article>
      <article class="traffic-stat-card">
        <span>错误率</span>
        <strong>{{ traffic ? formatErrorRate(trafficSummary) : '–' }}</strong>
        <small>{{ traffic ? `${formatNumber(trafficSummary.error_count)} 次错误` : '按 HTTP 4xx / 5xx 统计' }}</small>
      </article>
    </div>

    <div v-if="trafficError" class="traffic-error" role="alert">
      <span>{{ trafficError }}</span>
      <button class="ghost" type="button" @click="loadTraffic">重新加载</button>
    </div>

    <div v-if="traffic && traffic.telemetry_complete === false" class="traffic-warning" role="status" aria-live="polite">
      当前进程已检测到统计队列遗漏 {{ formatNumber(traffic.telemetry_dropped_events) }} 次调用；以下数据可能偏低。该标记不跨进程重启，请结合服务日志核查。
    </div>

    <div v-if="traffic" class="traffic-dashboard">
      <section class="traffic-panel" aria-labelledby="traffic-trend-heading">
        <div class="traffic-panel-head">
          <div>
            <h4 id="traffic-trend-heading">每日调用趋势</h4>
            <p>仅包含 API Key 调用，进度条以当前范围内最高调用日为基准。</p>
          </div>
          <span class="total-badge">{{ traffic.days }} 天</span>
        </div>
        <div class="traffic-trend-scroll">
          <table class="traffic-table trend-table">
            <caption class="sr-only">每日 API 调用数量与流量趋势</caption>
            <thead><tr><th>日期</th><th>调用趋势</th><th>调用</th><th>请求</th><th>响应</th><th>错误</th></tr></thead>
            <tbody>
              <tr v-for="day in traffic.daily" :key="day.date">
                <td><time :datetime="day.date">{{ fmtDay(day.date) }}</time></td>
                <td class="trend-cell">
                  <progress
                    :value="Number(day.request_count || 0)"
                    :max="maxDailyRequests"
                    :aria-label="`${day.date} 调用 ${formatNumber(day.request_count)} 次`"
                  />
                </td>
                <td>{{ formatNumber(day.request_count) }}</td>
                <td>{{ formatBytes(day.request_bytes) }}</td>
                <td>{{ formatBytes(day.response_bytes) }}</td>
                <td>{{ formatNumber(day.error_count) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="traffic-panel member-usage-panel" aria-labelledby="member-usage-heading">
        <div class="traffic-panel-head">
          <div>
            <h4 id="member-usage-heading">成员使用空间与调用量</h4>
            <p>空间包含媒体与上传预留，调用量仅包含该成员的 API Key。</p>
          </div>
          <span class="total-badge">{{ membersByUsage.length }} 位</span>
        </div>
        <div class="table-shell">
          <table class="traffic-table member-usage-table">
            <caption class="sr-only">每个成员的媒体空间占用和 API 使用量</caption>
            <thead><tr><th>成员</th><th>总占用</th><th>图片</th><th>视频</th><th>待完成</th><th>调用</th><th>流量</th></tr></thead>
            <tbody>
              <tr v-for="member in membersByUsage" :key="member.user_id">
                <td>
                  <span class="admin-user-avatar">{{ member.username.slice(0, 1).toUpperCase() }}</span>
                  <span class="username">{{ member.username }}</span>
                  <span class="role-badge" :class="{ admin: member.role === 'admin' }">{{ member.role === 'admin' ? '管理员' : '用户' }}</span>
                </td>
                <td><strong>{{ formatBytes(member.total_usage_bytes) }}</strong></td>
                <td>{{ formatBytes(member.image_bytes) }}</td>
                <td>{{ formatBytes(member.video_bytes) }}</td>
                <td>{{ formatBytes(member.pending_upload_bytes) }}</td>
                <td>{{ formatNumber(member.request_count) }}</td>
                <td>{{ formatBytes(member.total_bytes) }}</td>
              </tr>
              <tr v-if="!membersByUsage.length"><td colspan="7" class="empty-table-cell">当前范围内暂无成员数据</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="traffic-breakdown-grid">
        <section class="traffic-panel" aria-labelledby="route-ranking-heading">
          <div class="traffic-panel-head"><div><h4 id="route-ranking-heading">高频接口</h4><p>按 API Key 调用数量排序的前 8 个路由。</p></div></div>
          <div class="table-shell">
            <table class="traffic-table compact-traffic-table">
              <caption class="sr-only">高频 API 路由排行</caption>
              <thead><tr><th>路由</th><th>调用</th><th>流量</th></tr></thead>
              <tbody>
                <tr v-for="route in topRoutes" :key="`${route.method}:${route.route}`">
                  <td><span class="route-method">{{ route.method }}</span><code>{{ route.route }}</code></td>
                  <td>{{ formatNumber(route.request_count) }}</td>
                  <td>{{ formatBytes(route.total_bytes) }}</td>
                </tr>
                <tr v-if="!topRoutes.length"><td colspan="3" class="empty-table-cell">暂无路由调用</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="traffic-panel" aria-labelledby="key-ranking-heading">
          <div class="traffic-panel-head"><div><h4 id="key-ranking-heading">API Key 调用</h4><p>只显示名称和前缀，不暴露完整密钥。</p></div></div>
          <div class="table-shell">
            <table class="traffic-table compact-traffic-table">
              <caption class="sr-only">API Key 调用排行</caption>
              <thead><tr><th>API Key</th><th>成员</th><th>调用</th><th>流量</th></tr></thead>
              <tbody>
                <tr v-for="key in topApiKeys" :key="key.api_key_id">
                  <td><span class="username">{{ key.key_name || '未命名 Key' }}</span><small>{{ key.key_prefix || '—' }}</small></td>
                  <td>{{ key.username || '已删除用户' }}</td>
                  <td>{{ formatNumber(key.request_count) }}</td>
                  <td>{{ formatBytes(key.total_bytes) }}</td>
                </tr>
                <tr v-if="!topApiKeys.length"><td colspan="4" class="empty-table-cell">当前范围内没有 API Key 调用</td></tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
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
.traffic-section-head { margin-top: 38px; }
.traffic-range { display: grid; gap: 5px; color: var(--muted); font-size: 10px; font-weight: 650; }
.traffic-range select {
  min-width: 118px;
  min-height: 38px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 7px 10px;
  background: var(--panel);
  color: var(--text);
  outline: 0;
}
.traffic-range select:focus-visible { border-color: var(--accent); box-shadow: 0 0 0 3px rgb(91 91 214 / 12%); }
.traffic-stat-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.traffic-stat-card {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
  background: var(--panel);
  box-shadow: 0 7px 24px rgb(34 45 73 / 4%);
}
.traffic-stat-card span { display: block; color: var(--muted); font-size: 10px; font-weight: 650; }
.traffic-stat-card strong { display: block; margin-top: 5px; color: #252d3b; font-size: clamp(18px, 2vw, 24px); letter-spacing: -.03em; }
.traffic-stat-card small { display: block; margin-top: 3px; overflow: hidden; color: var(--muted-light); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.traffic-error {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #f3c9c6;
  border-radius: 12px;
  padding: 10px 12px;
  background: #fff7f6;
  color: var(--danger);
  font-size: 11px;
}
.traffic-warning {
  margin-top: 12px;
  border: 1px solid #e8cf91;
  border-radius: 12px;
  padding: 10px 12px;
  background: #fffaf0;
  color: #765314;
  font-size: 11px;
  line-height: 1.6;
}
.traffic-dashboard { margin-top: 12px; display: grid; gap: 12px; }
.traffic-panel {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--panel);
  box-shadow: 0 7px 24px rgb(34 45 73 / 4%);
}
.traffic-panel-head {
  min-height: 62px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  padding: 12px 15px;
}
.traffic-panel-head h4 { margin: 0; color: var(--text); font-size: 13px; }
.traffic-panel-head p { margin: 2px 0 0; color: var(--muted); font-size: 10px; }
.traffic-trend-scroll { max-height: 340px; overflow: auto; }
.traffic-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.traffic-table th,
.traffic-table td { border-bottom: 1px solid #edf0f5; padding: 9px 11px; text-align: left; vertical-align: middle; }
.traffic-table thead th { position: sticky; z-index: 1; top: 0; background: #fafbfd; color: var(--muted); font-size: 9px; font-weight: 700; white-space: nowrap; }
.traffic-table tbody tr:last-child td { border-bottom: 0; }
.traffic-table time { color: var(--muted); white-space: nowrap; }
.trend-cell { width: 42%; min-width: 160px; }
.trend-cell progress {
  width: 100%;
  height: 7px;
  display: block;
  overflow: hidden;
  border: 0;
  border-radius: 999px;
  background: #eceefa;
  color: var(--accent);
}
.trend-cell progress::-webkit-progress-bar { border-radius: 999px; background: #eceefa; }
.trend-cell progress::-webkit-progress-value { border-radius: 999px; background: #5b5bd6; }
.trend-cell progress::-moz-progress-bar { border-radius: 999px; background: #5b5bd6; }
.member-usage-table { min-width: 820px; }
.member-usage-table td:first-child { white-space: nowrap; }
.member-usage-table .role-badge { margin-left: 7px; }
.traffic-breakdown-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.compact-traffic-table { min-width: 480px; }
.compact-traffic-table code { margin-left: 7px; color: var(--text); font: 10px ui-monospace, SFMono-Regular, Menlo, monospace; }
.compact-traffic-table small { display: block; margin: 2px 0 0; color: var(--muted-light); font: 9px ui-monospace, monospace; }
.route-method { display: inline-block; min-width: 36px; color: var(--accent); font: 750 9px ui-monospace, monospace; }
.empty-table-cell { padding-block: 20px !important; color: var(--muted); text-align: center !important; }
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
  .traffic-section-head { align-items: stretch; }
  .traffic-range select { width: 100%; }
}

@media (max-width: 1120px) {
  .traffic-stat-cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
  .traffic-stat-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .traffic-breakdown-grid { grid-template-columns: 1fr; }
}

@media (max-width: 430px) {
  .traffic-stat-cards { grid-template-columns: 1fr; }
}
</style>
