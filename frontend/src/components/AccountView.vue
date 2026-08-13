<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  changePassword,
  createApiKey,
  deleteApiKey,
  listApiKeys,
  rotateApiKey,
  setToken,
} from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const pwdMsg = ref('')
const pwdError = ref('')
const changingPassword = ref(false)

const keys = ref([])
const keyName = ref('')
const keyDialogOpen = ref(false)
const keyCreateError = ref('')
const newKey = ref(null)
const keyError = ref('')
const creatingKey = ref(false)
let copiedTimer = null

async function loadKeys() {
  try {
    keys.value = await listApiKeys()
  } catch (err) {
    keyError.value = err.message
  }
}

onMounted(loadKeys)

function fmtDate(value) {
  return new Date(value).toLocaleString()
}

async function doChangePassword() {
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
  changingPassword.value = true
  try {
    await changePassword(oldPassword.value, newPassword.value)
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    pwdMsg.value = '密码已修改，请重新登录'
    toast('密码已安全更新，请使用新密码重新登录', 'success')
    // The backend revokes every previously issued JWT, including this tab's
    // token. Reuse the app-wide unauthorized cleanup so active upload state and
    // account-scoped views cannot linger with a guaranteed-invalid credential.
    setToken(null)
    window.dispatchEvent(new Event('oss:unauthorized'))
  } catch (err) {
    pwdError.value = err.message
  } finally {
    changingPassword.value = false
  }
}

function openKeyDialog() {
  keyName.value = ''
  keyCreateError.value = ''
  keyError.value = ''
  keyDialogOpen.value = true
}

function closeKeyDialog() {
  if (creatingKey.value) return
  keyDialogOpen.value = false
  keyName.value = ''
  keyCreateError.value = ''
}

async function doCreateKey() {
  const name = keyName.value.trim()
  keyCreateError.value = ''
  if (!name) {
    keyCreateError.value = '请输入密钥名称'
    return
  }
  creatingKey.value = true
  try {
    newKey.value = await createApiKey(name)
    keyName.value = ''
    await loadKeys()
    keyDialogOpen.value = false
  } catch (err) {
    keyCreateError.value = err.message
  } finally {
    creatingKey.value = false
  }
}

async function doRotate(key) {
  const ok = await confirmAction({
    title: '重新生成 API Key',
    message: `重新生成「${key.name || key.key_prefix}」？旧 Key 将立即失效。`,
    confirmText: '重新生成',
    danger: true,
  })
  if (!ok) return
  newKey.value = null
  keyError.value = ''
  try {
    newKey.value = await rotateApiKey(key.id)
    await loadKeys()
    toast('API Key 已重新生成', 'success')
  } catch (err) {
    keyError.value = err.message
  }
}

async function doDeleteKey(key) {
  const ok = await confirmAction({
    title: '撤销 API Key',
    message: `撤销「${key.name || key.key_prefix}」？使用它的脚本将立即失效。`,
    confirmText: '撤销',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteApiKey(key.id)
    await loadKeys()
    toast('API Key 已撤销', 'success')
  } catch (err) {
    keyError.value = err.message
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

onBeforeUnmount(() => clearTimeout(copiedTimer))
</script>

<template>
  <section class="account-view">
    <div class="section-heading">
      <div>
        <p class="eyebrow">账户安全</p>
        <h2>账户与访问密钥</h2>
        <p>更新登录密码，并管理脚本或第三方工具使用的 API Key。</p>
      </div>
    </div>

    <div class="account-layout">
      <section class="account-panel password-panel">
        <header class="account-panel-head">
          <span class="panel-icon"><AppIcon name="account" /></span>
          <div><h3>登录密码</h3><p>定期更新密码有助于保护媒体资产。</p></div>
        </header>

        <form class="security-form" @submit.prevent="doChangePassword">
          <label><span>当前密码</span><input v-model="oldPassword" type="password" autocomplete="current-password" placeholder="输入当前密码" required /></label>
          <label><span>新密码</span><input v-model="newPassword" type="password" autocomplete="new-password" placeholder="至少 6 位" required minlength="6" /></label>
          <label><span>确认新密码</span><input v-model="confirmPassword" type="password" autocomplete="new-password" placeholder="再次输入新密码" required minlength="6" /></label>
          <p v-if="pwdError" class="form-error" role="alert">{{ pwdError }}</p>
          <p v-if="pwdMsg" class="ok-msg" role="status">✓ {{ pwdMsg }}</p>
          <button class="primary password-submit" :disabled="changingPassword || !oldPassword || !newPassword || !confirmPassword">
            {{ changingPassword ? '正在保存…' : '更新密码' }}
          </button>
        </form>
      </section>

      <section class="account-panel api-panel">
        <header class="account-panel-head">
          <span class="panel-icon key-icon" aria-hidden="true">⌁</span>
          <div><h3>API Key</h3><p>让命令行、脚本和自动化工具安全访问媒体库。</p></div>
        </header>

        <div class="key-create-actions">
          <button class="primary" type="button" :disabled="creatingKey" @click="openKeyDialog">生成密钥</button>
        </div>

        <div v-if="newKey" class="key-reveal">
          <div class="key-warning"><strong>请立即保存</strong><span>完整密钥仅展示这一次，关闭后无法再次查看。</span></div>
          <div class="key-line"><code class="key-value">{{ newKey.key }}</code><button class="copy" @click="copyKey">{{ newKey.copied ? '已复制' : '复制' }}</button></div>
        </div>
        <p v-if="keyError" class="form-error" role="alert">{{ keyError }}</p>

        <div class="key-list-head"><strong>有效密钥</strong><span>{{ keys.length }}</span></div>
        <div v-if="keys.length" class="key-list">
          <article v-for="key in keys" :key="key.id" class="key-row">
            <span class="key-row-icon" aria-hidden="true">⌁</span>
            <span class="key-row-info">
              <strong>{{ key.name || '未命名密钥' }}</strong>
              <small><code>{{ key.key_prefix }}…</code> · 创建于 {{ fmtDate(key.created_at) }}</small>
              <small>最近使用：{{ key.last_used_at ? fmtDate(key.last_used_at) : '从未使用' }}</small>
            </span>
            <span class="key-row-actions">
              <button class="ghost" @click="doRotate(key)">重新生成</button>
              <button class="ghost danger" @click="doDeleteKey(key)">撤销</button>
            </span>
          </article>
        </div>
        <div v-else class="key-empty"><span>⌁</span><p>还没有 API Key。仅在需要脚本访问时创建。</p></div>
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
          :disabled="creatingKey || !keyName.trim()"
        >
          {{ creatingKey ? '生成中…' : '确认生成' }}
        </button>
      </template>
    </BaseModal>

    <section class="api-help">
      <div><strong>如何使用 API Key？</strong><p>通过标准 Bearer Token 或 X-API-Key 请求头调用图片、视频及分组接口。</p></div>
      <code>Authorization: Bearer &lt;your-key&gt;</code>
      <a href="/docs">查看 API 文档 →</a>
    </section>
  </section>
</template>

<style scoped>
.account-view { display: grid; }
.account-layout {
  display: grid;
  grid-template-columns: minmax(300px, .78fr) minmax(420px, 1.22fr);
  gap: 16px;
  align-items: start;
}
.account-panel {
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 8px;
  padding: 20px;
  background: #fff;
}
.account-panel-head {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border, #e5e5e3);
}
.panel-icon {
  width: 36px;
  height: 36px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 6px;
  background: #f7f7f6;
  color: #525252;
}
.panel-icon.key-icon { color: #525252; font-size: 20px; }
.account-panel-head h3 { margin: 0 0 2px; color: var(--text, #242424); font-size: 15px; }
.account-panel-head p { margin: 0; color: var(--muted, #737373); font-size: 11px; }
.security-form { display: grid; gap: 13px; }
.security-form label { display: grid; gap: 6px; color: #525252; font-size: 11px; font-weight: 650; }
.security-form input,
.key-create-form input {
  width: 100%;
  min-height: 40px;
  border: 1px solid var(--border-strong, #d1d1ce);
  border-radius: 5px;
  padding: 8px 10px;
  background: #fff;
  color: var(--text, #242424);
  outline: 0;
  font-size: 12px;
}
.security-form input:focus,
.key-create-form input:focus {
  border-color: var(--accent, #0b63e5);
  box-shadow: 0 0 0 2px rgb(11 99 229 / 10%);
}
.password-submit { width: fit-content; margin-top: 3px; }
.security-form .form-error,
.security-form .ok-msg { margin: 0; font-size: 11px; }
.key-create-actions { margin-bottom: 14px; display: flex; justify-content: flex-end; }
.key-create-form { display: grid; gap: 7px; }
.key-create-form label { color: #525252; font-size: 12px; font-weight: 650; }
.key-create-form small { color: var(--muted, #737373); font-size: 10px; }
.key-create-form .form-error { margin: 4px 0 0; font-size: 11px; }
.key-reveal {
  margin-bottom: 16px;
  border: 1px solid var(--border, #e5e5e3);
  border-left: 3px solid #c58a34;
  border-radius: 6px;
  padding: 12px;
  background: #fafaf9;
}
.key-warning { display: grid; margin-bottom: 9px; }
.key-warning strong { color: #6b4d1f; font-size: 11px; }
.key-warning span { color: var(--muted, #737373); font-size: 10px; }
.key-line { display: flex; align-items: stretch; gap: 7px; }
.key-value {
  min-width: 0;
  flex: 1;
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 5px;
  padding: 8px;
  background: #fff;
  color: #44403c;
  overflow-wrap: anywhere;
  font-size: 10px;
}
.key-list-head { margin: 18px 0 7px; display: flex; align-items: center; justify-content: space-between; }
.key-list-head strong { color: #3f3f3f; font-size: 11px; }
.key-list-head span {
  min-width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 4px;
  background: #fafaf9;
  color: var(--muted, #737373);
  font-size: 9px;
}
.key-list { display: grid; }
.key-row {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  border-top: 1px solid var(--border, #e5e5e3);
  padding: 12px 0;
}
.key-row-icon {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 5px;
  background: #fafaf9;
  color: #737373;
}
.key-row-info { min-width: 0; display: grid; }
.key-row-info strong,
.key-row-info small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.key-row-info strong { color: #3f3f3f; font-size: 11px; }
.key-row-info small { color: var(--muted, #737373); font-size: 9px; }
.key-row-info code { color: #57534e; }
.key-row-actions { display: flex; gap: 5px; }
.key-empty {
  min-height: 112px;
  display: grid;
  place-content: center;
  justify-items: center;
  color: var(--muted, #737373);
  text-align: center;
}
.key-empty span { font-size: 22px; }
.key-empty p { margin: 5px 0 0; font-size: 10px; }
.api-help {
  margin-top: 16px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 18px;
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 8px;
  padding: 15px 18px;
  background: #fff;
}
.api-help strong { color: #3f3f3f; font-size: 11px; }
.api-help p { margin: 2px 0 0; color: var(--muted, #737373); font-size: 10px; }
.api-help code {
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 5px;
  padding: 7px 9px;
  background: #fafaf9;
  color: #57534e;
  font-size: 9px;
}
.api-help a {
  color: #44403c;
  font-size: 10px;
  font-weight: 650;
  text-decoration: underline;
  text-underline-offset: 3px;
  white-space: nowrap;
}
@media (max-width: 950px) { .account-layout { grid-template-columns: 1fr; } }
@media (max-width: 650px) {
  .account-panel { padding: 16px; }
  .key-row { grid-template-columns: auto minmax(0, 1fr); }
  .key-row-actions { grid-column: 2; }
  .api-help { grid-template-columns: 1fr; gap: 9px; }
  .api-help code { overflow-x: auto; }
}
</style>
