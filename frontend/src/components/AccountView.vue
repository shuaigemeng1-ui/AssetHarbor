<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  changePassword,
  createApiKey,
  deleteApiKey,
  getToken,
  listApiKeys,
  rotateApiKey,
  setToken,
} from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'

const emit = defineEmits(['credential-busy'])

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const pwdMsg = ref('')
const pwdError = ref('')
const changingPassword = ref(false)
const showOldPassword = ref(false)
const showNewPassword = ref(false)
const showConfirmPassword = ref(false)

const keys = ref([])
const keysLoading = ref(true)
const keyName = ref('')
const keyDialogOpen = ref(false)
const keyCreateError = ref('')
const newKey = ref(null)
const keyError = ref('')
const creatingKey = ref(false)
const keyActionId = ref(null)
const keyActionType = ref(null)
const apiAuthMode = ref('bearer')
const credentialsBusy = computed(() => changingPassword.value || creatingKey.value || keyActionId.value !== null)
const accountRoot = ref(null)
const copyButton = ref(null)
let copiedTimer = null
let keyLoadRequest = 0

function setCredentialBusy(busy) {
  emit('credential-busy', busy)
}

function onBeforePageUnload(event) {
  if (!credentialsBusy.value) return
  event.preventDefault()
  event.returnValue = ''
}

async function focusAfterUnlock(selector) {
  await nextTick()
  const target = selector === 'copy'
    ? copyButton.value
    : accountRoot.value?.querySelector(selector) || document.querySelector(selector)
  target?.focus()
}

const bearerExample = [
  'GET /api/images?limit=20 HTTP/1.1',
  'Host: <YOUR_DOMAIN>',
  'Authorization: Bearer <YOUR_API_KEY>',
]
const headerExample = [
  'GET /api/images?limit=20 HTTP/1.1',
  'Host: <YOUR_DOMAIN>',
  'X-API-Key: <YOUR_API_KEY>',
]

async function loadKeys() {
  const requestId = ++keyLoadRequest
  keysLoading.value = true
  keyError.value = ''
  try {
    const nextKeys = await listApiKeys()
    if (requestId !== keyLoadRequest) return
    keys.value = nextKeys
  } catch (err) {
    if (requestId !== keyLoadRequest) return
    keyError.value = err.message
  } finally {
    if (requestId === keyLoadRequest) keysLoading.value = false
  }
}

onMounted(() => {
  loadKeys()
  window.addEventListener('beforeunload', onBeforePageUnload)
})

function fmtDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function fmtLastUsed(value) {
  if (!value) return '从未使用'
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime())
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  if (elapsed < minute) return '刚刚'
  if (elapsed < hour) return `${Math.floor(elapsed / minute)} 分钟前`
  if (elapsed < day) return `${Math.floor(elapsed / hour)} 小时前`
  if (elapsed < 30 * day) return `${Math.floor(elapsed / day)} 天前`
  return fmtDate(value)
}

function isRecentlyUsed(value) {
  if (!value) return false
  return Date.now() - new Date(value).getTime() < 24 * 60 * 60 * 1000
}

function clearRequestSession(requestToken) {
  if (!requestToken || getToken() !== requestToken) return false
  setToken(null)
  window.dispatchEvent(new Event('oss:unauthorized'))
  return true
}

async function doChangePassword() {
  if (credentialsBusy.value) return
  pwdMsg.value = ''
  pwdError.value = ''
  if (newPassword.value.length < 6) {
    pwdError.value = '新密码至少需要 6 位'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    pwdError.value = '两次输入的新密码不一致'
    return
  }
  const requestToken = getToken()
  changingPassword.value = true
  setCredentialBusy(true)
  try {
    await changePassword(oldPassword.value, newPassword.value)
    if (getToken() !== requestToken) return
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    pwdMsg.value = '密码已修改，请重新登录'
    toast('密码已安全更新，请使用新密码重新登录', 'success')
    // The backend revokes every previously issued JWT, including this tab's
    // token. Reuse the app-wide unauthorized cleanup so active upload state and
    // account-scoped views cannot linger with a guaranteed-invalid credential.
    clearRequestSession(requestToken)
  } catch (err) {
    if (getToken() !== requestToken) return
    pwdError.value = err.message
    if (err.status === 401 || err.status === 409) {
      toast(err.message || '账户凭据已失效，请重新登录', 'error')
      clearRequestSession(requestToken)
    }
  } finally {
    changingPassword.value = false
    setCredentialBusy(false)
  }
}

function openKeyDialog() {
  if (credentialsBusy.value) return
  keyName.value = ''
  keyCreateError.value = ''
  keyDialogOpen.value = true
}

function closeKeyDialog() {
  if (creatingKey.value) return
  keyDialogOpen.value = false
  keyName.value = ''
  keyCreateError.value = ''
}

async function doCreateKey() {
  if (credentialsBusy.value) return
  const name = keyName.value.trim()
  keyCreateError.value = ''
  if (!name) {
    keyCreateError.value = '请输入密钥名称'
    return
  }
  creatingKey.value = true
  setCredentialBusy(true)
  let created = false
  try {
    newKey.value = await createApiKey(name)
    keys.value = [
      ...keys.value,
      {
        id: newKey.value.id,
        name: newKey.value.name,
        key_prefix: newKey.value.key_prefix,
        created_at: newKey.value.created_at,
        last_used_at: null,
      },
    ]
    keyName.value = ''
    keyDialogOpen.value = false
    created = true
    void loadKeys()
  } catch (err) {
    keyCreateError.value = err.message
  } finally {
    creatingKey.value = false
    setCredentialBusy(false)
    await focusAfterUnlock(created ? 'copy' : '#create-api-key-name')
  }
}

async function doRotate(key) {
  if (credentialsBusy.value) return
  keyActionId.value = key.id
  keyActionType.value = 'rotate'
  setCredentialBusy(true)
  const ok = await confirmAction({
    title: '重新生成 API Key',
    message: `重新生成「${key.name || key.key_prefix}」？旧 Key 将立即失效。`,
    confirmText: '重新生成',
    danger: true,
  })
  if (!ok) {
    keyActionId.value = null
    keyActionType.value = null
    setCredentialBusy(false)
    await focusAfterUnlock(`[data-key-action="rotate"][data-key-id="${key.id}"]`)
    return
  }
  keyError.value = ''
  let rotated = false
  try {
    const rotatedKey = await rotateApiKey(key.id)
    newKey.value = rotatedKey
    keys.value = keys.value.map(item => item.id === key.id
      ? {
          id: newKey.value.id,
          name: newKey.value.name,
          key_prefix: newKey.value.key_prefix,
          created_at: newKey.value.created_at,
          last_used_at: null,
        }
      : item)
    void loadKeys()
    rotated = true
    toast('API Key 已重新生成', 'success')
  } catch (err) {
    keyError.value = err.message
  } finally {
    keyActionId.value = null
    keyActionType.value = null
    setCredentialBusy(false)
    await focusAfterUnlock(rotated ? 'copy' : `[data-key-action="rotate"][data-key-id="${key.id}"]`)
  }
}

async function doDeleteKey(key) {
  if (credentialsBusy.value) return
  keyActionId.value = key.id
  keyActionType.value = 'delete'
  setCredentialBusy(true)
  const ok = await confirmAction({
    title: '撤销 API Key',
    message: `撤销「${key.name || key.key_prefix}」？使用它的脚本将立即失效。`,
    confirmText: '撤销',
    danger: true,
  })
  if (!ok) {
    keyActionId.value = null
    keyActionType.value = null
    setCredentialBusy(false)
    await focusAfterUnlock(`[data-key-action="delete"][data-key-id="${key.id}"]`)
    return
  }
  keyError.value = ''
  let deleted = false
  try {
    await deleteApiKey(key.id)
    keys.value = keys.value.filter(item => item.id !== key.id)
    if (newKey.value?.id === key.id) {
      clearTimeout(copiedTimer)
      newKey.value = null
    }
    void loadKeys()
    deleted = true
    toast('API Key 已撤销', 'success')
  } catch (err) {
    keyError.value = err.message
  } finally {
    keyActionId.value = null
    keyActionType.value = null
    setCredentialBusy(false)
    await focusAfterUnlock(deleted
      ? '#api-key-heading'
      : `[data-key-action="delete"][data-key-id="${key.id}"]`)
  }
}

async function copyKey() {
  const copiedKey = newKey.value
  if (!copiedKey) return
  const ok = await copyText(copiedKey.key)
  if (!ok) {
    toast('复制失败，请手动选中复制', 'error')
    return
  }
  copiedKey.copied = true
  toast('完整 API Key 已复制', 'success')
  clearTimeout(copiedTimer)
  copiedTimer = window.setTimeout(() => {
    if (copiedKey) copiedKey.copied = false
  }, 1500)
}

onBeforeUnmount(() => {
  keyLoadRequest += 1
  clearTimeout(copiedTimer)
  window.removeEventListener('beforeunload', onBeforePageUnload)
  setCredentialBusy(false)
})
</script>

<template>
  <section ref="accountRoot" class="account-view">
    <div class="section-heading account-heading">
      <div>
        <h2>账户与访问密钥</h2>
        <p>使用 API Key 安全地访问 OSS Media 服务。请妥善保管密钥，避免泄露。</p>
      </div>
    </div>

    <div class="account-layout">
      <div class="account-primary-column">
        <section class="account-panel api-panel" aria-labelledby="api-key-heading">
          <header class="api-panel-head">
            <div>
              <h3 id="api-key-heading" tabindex="-1">API Key</h3>
              <p>使用 API Key 进行身份验证，请在每个媒体数据请求的 Header 中携带认证信息。</p>
            </div>
            <button class="primary generate-key-button" type="button" :disabled="credentialsBusy || keysLoading" @click="openKeyDialog">
              <AppIcon name="key" size="15" />
              生成密钥
            </button>
          </header>

          <div v-if="newKey" class="key-reveal">
            <div class="key-warning">
              <strong>请立即保存完整密钥</strong>
              <span>完整密钥仅展示这一次，关闭页面后无法再次查看。</span>
            </div>
            <div class="key-line">
              <code class="key-value">{{ newKey.key }}</code>
              <button ref="copyButton" class="copy" type="button" @click="copyKey">{{ newKey.copied ? '已复制' : '复制' }}</button>
            </div>
          </div>
          <p v-if="keyError" class="form-error panel-error" role="alert">{{ keyError }}</p>

          <div class="key-table-wrap">
            <table class="key-table">
              <caption class="sr-only">当前账户的有效 API Key</caption>
              <thead>
                <tr>
                  <th scope="col">密钥名称</th>
                  <th scope="col">API Key</th>
                  <th scope="col">创建时间</th>
                  <th scope="col">最近使用</th>
                  <th scope="col">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="key in keys" :key="key.id">
                  <th scope="row" data-label="密钥名称"><strong class="key-name">{{ key.name || '未命名密钥' }}</strong></th>
                  <td data-label="API Key">
                    <span class="masked-key" :title="`${key.key_prefix}（完整密钥仅在生成时展示）`">
                      <code>{{ key.key_prefix }}••••••••</code>
                      <AppIcon name="lock" size="13" />
                    </span>
                  </td>
                  <td data-label="创建时间"><time :datetime="key.created_at">{{ fmtDate(key.created_at) }}</time></td>
                  <td data-label="最近使用">
                    <time
                      v-if="key.last_used_at"
                      :datetime="key.last_used_at"
                      :title="fmtDate(key.last_used_at)"
                      :class="['last-used', { recent: isRecentlyUsed(key.last_used_at) }]"
                    >{{ fmtLastUsed(key.last_used_at) }}</time>
                    <span v-else class="last-used">从未使用</span>
                  </td>
                  <td data-label="操作">
                    <span class="key-row-actions">
                      <button
                        class="ghost compact"
                        type="button"
                        data-key-action="rotate"
                        :data-key-id="key.id"
                        :disabled="credentialsBusy || keysLoading"
                        :aria-label="`${keyActionId === key.id && keyActionType === 'rotate' ? '正在重新生成' : '重新生成'} API Key：${key.name || key.key_prefix || '未命名密钥'}`"
                        @click="doRotate(key)"
                      >{{ keyActionId === key.id && keyActionType === 'rotate' ? '…' : '重新生成' }}</button>
                      <button
                        class="ghost compact danger"
                        type="button"
                        data-key-action="delete"
                        :data-key-id="key.id"
                        :disabled="credentialsBusy || keysLoading"
                        :aria-label="`${keyActionId === key.id && keyActionType === 'delete' ? '正在撤销' : '撤销'} API Key：${key.name || key.key_prefix || '未命名密钥'}`"
                        @click="doDeleteKey(key)"
                      >{{ keyActionId === key.id && keyActionType === 'delete' ? '…' : '撤销' }}</button>
                    </span>
                  </td>
                </tr>
                <tr v-if="keysLoading" class="empty-row">
                  <td colspan="5">
                    <span class="key-empty" role="status">正在加载 API Key…</span>
                  </td>
                </tr>
                <tr v-else-if="!keys.length && !keyError" class="empty-row">
                  <td colspan="5">
                    <span class="key-empty">
                      <AppIcon name="key" size="20" />
                      <span>还没有 API Key，仅在需要脚本访问时创建。</span>
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="account-panel api-help" aria-labelledby="api-help-heading">
          <header class="api-help-head">
            <div>
              <h3 id="api-help-heading">如何使用 API Key</h3>
              <p>通过标准 Bearer Token 或 X-API-Key 请求头调用接口。</p>
            </div>
            <a href="/docs" target="_blank" rel="noreferrer">
              查看 API 文档
              <AppIcon name="external" size="14" />
            </a>
          </header>

          <div class="api-auth-tabs" role="group" aria-label="API Key 认证方式">
            <button
              id="bearer-tab"
              type="button"
              :aria-pressed="apiAuthMode === 'bearer'"
              :class="{ active: apiAuthMode === 'bearer' }"
              @click="apiAuthMode = 'bearer'"
            >Bearer Token（推荐）</button>
            <button
              id="header-tab"
              type="button"
              :aria-pressed="apiAuthMode === 'header'"
              :class="{ active: apiAuthMode === 'header' }"
              @click="apiAuthMode = 'header'"
            >X-API-Key</button>
          </div>

          <ol
            id="api-auth-example"
            class="api-code-example"
          >
            <li v-for="line in (apiAuthMode === 'bearer' ? bearerExample : headerExample)" :key="line"><code>{{ line }}</code></li>
          </ol>
        </section>
      </div>

      <section class="account-panel password-panel" aria-labelledby="password-heading">
        <header class="password-panel-head">
          <span class="panel-icon"><AppIcon name="lock" size="18" /></span>
          <div>
            <h3 id="password-heading">登录密码</h3>
            <p>定期更新密码有助于保护账户安全。</p>
          </div>
        </header>

        <form class="security-form" @submit.prevent="doChangePassword">
          <div class="security-field">
            <label for="current-password">当前密码</label>
            <span class="password-input">
              <input id="current-password" v-model="oldPassword" :type="showOldPassword ? 'text' : 'password'" autocomplete="current-password" maxlength="128" placeholder="输入当前密码" required />
              <button type="button" aria-controls="current-password" :aria-label="showOldPassword ? '隐藏当前密码' : '显示当前密码'" :aria-pressed="showOldPassword" @click="showOldPassword = !showOldPassword">
                <AppIcon :name="showOldPassword ? 'eyeOff' : 'preview'" size="15" />
              </button>
            </span>
          </div>
          <div class="security-field">
            <label for="new-password">新密码</label>
            <span class="password-input">
              <input id="new-password" v-model="newPassword" :type="showNewPassword ? 'text' : 'password'" autocomplete="new-password" maxlength="128" placeholder="至少 6 位" required minlength="6" />
              <button type="button" aria-controls="new-password" :aria-label="showNewPassword ? '隐藏新密码' : '显示新密码'" :aria-pressed="showNewPassword" @click="showNewPassword = !showNewPassword">
                <AppIcon :name="showNewPassword ? 'eyeOff' : 'preview'" size="15" />
              </button>
            </span>
          </div>
          <div class="security-field">
            <label for="confirm-password">确认新密码</label>
            <span class="password-input">
              <input id="confirm-password" v-model="confirmPassword" :type="showConfirmPassword ? 'text' : 'password'" autocomplete="new-password" maxlength="128" placeholder="再次输入新密码" required minlength="6" />
              <button type="button" aria-controls="confirm-password" :aria-label="showConfirmPassword ? '隐藏确认密码' : '显示确认密码'" :aria-pressed="showConfirmPassword" @click="showConfirmPassword = !showConfirmPassword">
                <AppIcon :name="showConfirmPassword ? 'eyeOff' : 'preview'" size="15" />
              </button>
            </span>
          </div>
          <p v-if="pwdError" class="form-error" role="alert">{{ pwdError }}</p>
          <p v-if="pwdMsg" class="ok-msg" role="status"><AppIcon name="check" size="14" />{{ pwdMsg }}</p>
          <button class="primary password-submit" :disabled="credentialsBusy || !oldPassword || !newPassword || !confirmPassword">
            {{ changingPassword ? '正在保存…' : '更新密码' }}
          </button>
        </form>

        <aside class="security-note">
          <strong>安全提示</strong>
          <p>更新密码后，所有现有网页登录令牌都会失效，需要重新登录。已有 API Key 不会随密码更新自动撤销，如需停用请在左侧单独撤销。</p>
        </aside>
      </section>
    </div>

    <BaseModal
      v-if="keyDialogOpen"
      title="生成 API Key"
      description="输入一个便于识别的名称。生成后，完整密钥只会展示一次。"
      labelled-by="create-api-key-title"
      @close="closeKeyDialog"
    >
      <form id="create-api-key-form" class="key-create-form" @submit.prevent="doCreateKey">
        <label for="create-api-key-name">密钥名称</label>
        <input
          id="create-api-key-name"
          v-model="keyName"
          autofocus
          maxlength="64"
          autocomplete="off"
          placeholder="例如：备份脚本"
          aria-label="API Key 名称"
        />
        <small>名称仅用于区分密钥用途，最多 64 个字符。</small>
        <p v-if="keyCreateError" class="form-error" role="alert">{{ keyCreateError }}</p>
      </form>
      <template #footer>
        <button class="ghost" type="button" :disabled="creatingKey" @click="closeKeyDialog">取消</button>
        <button
          class="primary"
          type="submit"
          form="create-api-key-form"
          :disabled="credentialsBusy || !keyName.trim()"
        >
          {{ creatingKey ? '生成中…' : '确认生成' }}
        </button>
      </template>
    </BaseModal>

  </section>
</template>

<style scoped>
.account-view {
  display: grid;
  container: account-page / inline-size;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  clip-path: inset(50%);
  margin: -1px;
  padding: 0;
  border: 0;
  white-space: nowrap;
}

.account-heading {
  margin-bottom: 20px;
}

.account-heading h2 {
  margin-bottom: 5px;
}

.account-heading p {
  max-width: 720px;
  font-size: 14px;
  line-height: 1.6;
}

.account-layout {
  display: grid;
  grid-template-columns: minmax(0, 2.15fr) minmax(280px, 1fr);
  gap: 16px;
  align-items: start;
}

.account-primary-column {
  min-width: 0;
  display: grid;
  gap: 16px;
}

.account-panel {
  min-width: 0;
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 7px;
  background: #fff;
  box-shadow: none;
}

.api-panel {
  overflow: hidden;
  container: api-key-panel / inline-size;
}

.api-panel-head,
.api-help-head,
.password-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.api-panel-head {
  min-height: 80px;
  padding: 17px 20px;
}

.api-panel-head h3,
.api-help-head h3,
.password-panel-head h3 {
  margin: 0 0 4px;
  color: var(--text, #242424);
  font-size: 16px;
  line-height: 1.3;
}

.api-panel-head p,
.api-help-head p,
.password-panel-head p {
  margin: 0;
  color: var(--muted, #737373);
  font-size: 13px;
  line-height: 1.55;
}

.generate-key-button {
  flex: 0 0 auto;
  gap: 7px;
  min-height: 38px;
  padding-inline: 13px;
  white-space: nowrap;
}

.key-reveal {
  margin: 0 18px 16px;
  border: 1px solid #e4d4b8;
  border-left: 3px solid #b8812c;
  border-radius: 5px;
  padding: 12px;
  background: #fffdf8;
}

.key-warning {
  display: grid;
  gap: 2px;
  margin-bottom: 9px;
}

.key-warning strong {
  color: #6b4d1f;
  font-size: 13px;
}

.key-warning span {
  color: var(--muted, #737373);
  font-size: 12px;
  line-height: 1.5;
}

.key-line {
  display: flex;
  align-items: stretch;
  gap: 7px;
}

.key-value {
  min-width: 0;
  flex: 1;
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 5px;
  padding: 9px 10px;
  background: #fff;
  color: #44403c;
  overflow-wrap: anywhere;
  font-size: 12px;
  line-height: 1.45;
}

.panel-error {
  margin: 0 18px 14px;
  font-size: 13px;
}

.key-table-wrap {
  width: 100%;
  overflow-x: auto;
  border-top: 1px solid var(--border, #e5e5e3);
  overscroll-behavior-inline: contain;
}

.key-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.key-table thead th:nth-child(1) { width: 16%; }
.key-table thead th:nth-child(2) { width: 30%; }
.key-table thead th:nth-child(3) { width: 19%; }
.key-table thead th:nth-child(4) { width: 15%; }
.key-table thead th:nth-child(5) { width: 20%; }

.key-table th,
.key-table td {
  min-width: 0;
  border-bottom: 1px solid var(--border, #e5e5e3);
  padding: 13px 14px;
  text-align: left;
  vertical-align: middle;
}

.key-table th:last-child,
.key-table td:last-child {
  padding-inline: 8px;
}

.key-table thead th {
  height: 46px;
  background: #fafaf9;
  color: #626262;
  font-size: 12px;
  font-weight: 680;
  white-space: nowrap;
}

.key-table tbody th {
  height: 62px;
  border-bottom: 1px solid var(--border, #e5e5e3);
  padding: 13px 14px;
  background: #fff;
  text-align: left;
  vertical-align: middle;
}

.key-table td {
  height: 62px;
  color: #585858;
  font-size: 14px;
}

.key-table tbody tr:last-child td,
.key-table tbody tr:last-child th {
  border-bottom: 0;
}

.key-name {
  display: block;
  overflow: hidden;
  color: #454545;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.masked-key {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  max-width: 100%;
  color: #6a6a6a;
}

.masked-key code {
  min-width: 0;
  overflow: hidden;
  color: #4f5661;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.masked-key :deep(.app-icon) {
  color: #919191;
}

.last-used {
  color: #777;
  white-space: nowrap;
}

.last-used.recent {
  color: #2c9b52;
  font-weight: 650;
}

.key-row-actions {
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}

.key-row-actions .compact {
  min-height: 30px;
  padding: 5px 8px;
  font-size: 13px;
}

.key-row-actions .danger {
  border-color: #f0cdcd;
  color: var(--danger, #dc2626);
}

.key-row-actions .danger:hover {
  border-color: #e5b2b2;
  background: var(--danger-soft, #fff3f3);
  color: var(--danger, #dc2626);
}

.key-empty {
  min-height: 88px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--muted, #737373);
  font-size: 13px;
  text-align: center;
}

.empty-row td {
  padding: 0 18px;
  text-align: center;
}

.api-help {
  padding: 0 18px 18px;
  overflow: hidden;
}

.api-help-head {
  min-height: 72px;
  padding: 13px 0 8px;
}

.api-help-head h3 {
  font-size: 16px;
}

.api-help-head a {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 5px;
  color: var(--accent, #0b63e5);
  font-size: 13px;
  font-weight: 650;
  text-decoration: none;
  white-space: nowrap;
}

.api-help-head a:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.api-auth-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  border-bottom: 1px solid var(--border, #e5e5e3);
}

.api-auth-tabs button {
  position: relative;
  min-height: 38px;
  flex: 0 0 auto;
  border: 0;
  border-radius: 0;
  padding: 7px 12px;
  background: transparent;
  color: #616161;
  cursor: pointer;
  font-size: 14px;
  font-weight: 620;
}

.api-auth-tabs button:hover {
  color: var(--text, #242424);
}

.api-auth-tabs button.active {
  color: var(--accent, #0b63e5);
}

.api-auth-tabs button.active::after {
  content: '';
  position: absolute;
  right: 8px;
  bottom: -1px;
  left: 8px;
  height: 2px;
  background: var(--accent, #0b63e5);
}

.api-auth-tabs button:focus-visible,
.password-input button:focus-visible {
  outline: 2px solid var(--accent, #0b63e5);
  outline-offset: -2px;
}

.api-code-example {
  margin: 0;
  overflow-x: auto;
  border: 1px solid var(--border, #e5e5e3);
  border-top: 0;
  border-radius: 0 0 5px 5px;
  padding: 13px 14px 13px 40px;
  background: #fafaf9;
  color: #8a8a8a;
  font-size: 12px;
  line-height: 1.8;
}

.api-code-example li {
  padding-left: 7px;
}

.api-code-example code {
  color: #4d5969;
  font-size: 12px;
  white-space: pre;
}

.password-panel {
  padding: 20px;
}

.password-panel-head {
  justify-content: flex-start;
  margin-bottom: 19px;
}

.panel-icon {
  width: 22px;
  height: 22px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  color: #535353;
}

.security-form {
  display: grid;
  gap: 15px;
}

.security-field {
  min-width: 0;
  display: grid;
  gap: 7px;
}

.security-field > label {
  color: #525252;
  font-size: 14px;
  font-weight: 650;
}

.password-input {
  min-width: 0;
  min-height: 40px;
  display: flex;
  align-items: stretch;
  overflow: hidden;
  border: 1px solid var(--border-strong, #d1d1ce);
  border-radius: 5px;
  background: #fff;
}

.password-input:focus-within {
  border-color: var(--accent, #0b63e5);
  box-shadow: 0 0 0 2px rgb(11 99 229 / 10%);
}

.password-input input {
  min-width: 0;
  flex: 1;
  border: 0;
  padding: 8px 10px;
  background: transparent;
  color: var(--text, #242424);
  outline: 0;
  font-size: 14px;
}

.password-input input::placeholder,
.key-create-form input::placeholder {
  color: #9a9a9a;
}

.password-input button {
  width: 38px;
  min-height: 38px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-left: 1px solid transparent;
  border-radius: 0;
  padding: 0;
  background: transparent;
  color: #888;
  cursor: pointer;
}

.password-input button:hover {
  background: #f7f7f6;
  color: #4a4a4a;
}

.password-submit {
  width: fit-content;
  min-height: 38px;
  margin-top: 1px;
}

.security-form .form-error,
.security-form .ok-msg {
  margin: 0;
  font-size: 13px;
}

.security-form .ok-msg {
  display: flex;
  align-items: center;
  gap: 5px;
}

.security-note {
  margin-top: 16px;
  border-top: 1px solid var(--border, #e5e5e3);
  padding-top: 14px;
}

.security-note strong {
  color: #555;
  font-size: 14px;
}

.security-note p {
  margin: 5px 0 0;
  color: var(--muted, #737373);
  font-size: 13px;
  line-height: 1.6;
}

.key-create-form {
  display: grid;
  gap: 7px;
}

.key-create-form label {
  color: #525252;
  font-size: 14px;
  font-weight: 650;
}

.key-create-form input {
  width: 100%;
  min-height: 40px;
  border: 1px solid var(--border-strong, #d1d1ce);
  border-radius: 5px;
  padding: 8px 10px;
  background: #fff;
  color: var(--text, #242424);
  outline: 0;
  font-size: 14px;
}

.key-create-form input:focus {
  border-color: var(--accent, #0b63e5);
  box-shadow: 0 0 0 2px rgb(11 99 229 / 10%);
}

.key-create-form small {
  color: var(--muted, #737373);
  font-size: 12px;
}

.key-create-form .form-error {
  margin: 4px 0 0;
  font-size: 13px;
}

@container account-page (max-width: 900px) {
  .account-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .account-primary-column {
    display: contents;
  }

  .api-panel { order: 1; }
  .password-panel { order: 2; }
  .api-help { order: 3; }
}

@container api-key-panel (max-width: 720px) {
  .key-table {
    min-width: 720px;
  }
}

@container account-page (max-width: 620px) {
  .account-heading h2 {
    font-size: 26px;
  }

  .account-layout,
  .account-primary-column {
    gap: 12px;
  }

  .api-panel-head {
    align-items: flex-start;
    flex-wrap: wrap;
    padding: 16px;
  }

  .generate-key-button {
    width: 100%;
  }

  .key-reveal,
  .panel-error {
    margin-right: 16px;
    margin-left: 16px;
  }

  .password-panel {
    padding: 16px;
  }

  .api-help {
    padding: 0 16px 16px;
  }

  .api-help-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 7px;
    padding: 14px 0 10px;
  }

  .api-auth-tabs {
    margin-inline: -2px;
  }

  .key-line {
    display: grid;
  }

  .password-input input,
  .key-create-form input {
    font-size: 16px;
  }
}

@container account-page (max-width: 560px) {
  .key-table {
    min-width: 0;
  }

  .key-table,
  .key-table tbody,
  .key-table tr,
  .key-table tbody th,
  .key-table td {
    display: block;
    width: 100%;
  }

  .key-table thead {
    display: none;
  }

  .key-table tbody {
    padding: 0 14px;
  }

  .key-table tr {
    border-bottom: 1px solid var(--border, #e5e5e3);
    padding: 10px 0;
  }

  .key-table tbody tr:last-child {
    border-bottom: 0;
  }

  .key-table td,
  .key-table tbody th {
    min-height: 0;
    display: grid;
    grid-template-columns: 82px minmax(0, 1fr);
    align-items: center;
    gap: 8px;
    border: 0;
    padding: 6px 0;
  }

  .key-table td::before,
  .key-table tbody th::before {
    content: attr(data-label);
    color: #777;
    font-size: 11px;
    font-weight: 650;
  }

  .key-name,
  .masked-key code {
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .key-row-actions {
    flex-wrap: wrap;
  }

  .empty-row {
    padding: 0 !important;
  }

  .empty-row td {
    display: block;
    padding: 0;
  }

  .empty-row td::before {
    content: none;
  }

  .key-empty {
    min-height: 96px;
  }
}
</style>
