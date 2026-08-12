<script setup>
import { onMounted, ref } from 'vue'
import {
  changePassword,
  createApiKey,
  deleteApiKey,
  listApiKeys,
  rotateApiKey,
} from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import AppIcon from './AppIcon.vue'

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const pwdMsg = ref('')
const pwdError = ref('')
const changingPassword = ref(false)

const keys = ref([])
const keyName = ref('')
const newKey = ref(null)
const keyError = ref('')
const creatingKey = ref(false)

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
    pwdMsg.value = '密码已修改'
    toast('密码已安全更新', 'success')
  } catch (err) {
    pwdError.value = err.message
  } finally {
    changingPassword.value = false
  }
}

async function doCreateKey() {
  newKey.value = null
  keyError.value = ''
  creatingKey.value = true
  try {
    newKey.value = await createApiKey(keyName.value.trim())
    keyName.value = ''
    await loadKeys()
  } catch (err) {
    keyError.value = err.message
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
  const ok = await copyText(newKey.value.key)
  if (!ok) {
    toast('复制失败，请手动选中复制', 'error')
    return
  }
  newKey.value.copied = true
  toast('完整 API Key 已复制', 'success')
  window.setTimeout(() => (newKey.value.copied = false), 1500)
}
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

        <form class="key-create-row" @submit.prevent="doCreateKey">
          <input v-model="keyName" placeholder="密钥名称，例如：备份脚本" maxlength="64" aria-label="API Key 名称" />
          <button class="primary" :disabled="creatingKey">{{ creatingKey ? '生成中…' : '生成密钥' }}</button>
        </form>

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

    <section class="api-help">
      <div><strong>如何使用 API Key？</strong><p>通过标准 Bearer Token 或 X-API-Key 请求头调用图片、视频及分组接口。</p></div>
      <code>Authorization: Bearer &lt;your-key&gt;</code>
      <a href="/docs">查看 API 文档 →</a>
    </section>
  </section>
</template>

<style scoped>
.account-view { display: grid; }
.account-layout { display: grid; grid-template-columns: minmax(300px, .75fr) minmax(420px, 1.25fr); gap: 18px; align-items: start; }
.account-panel { border: 1px solid #e1e6ef; border-radius: 20px; padding: 22px; background: #fff; box-shadow: 0 6px 22px rgb(34 45 73 / 4%); }
.account-panel-head { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; padding-bottom: 17px; border-bottom: 1px solid #edf0f5; }
.panel-icon { width: 42px; height: 42px; display: grid; flex: 0 0 auto; place-items: center; border-radius: 12px; background: #eeeeff; color: #5656c9; }
.panel-icon.key-icon { background: #ebf8f2; color: #18805f; font-size: 22px; }
.account-panel-head h3 { margin: 0 0 2px; color: #242c3a; font-size: 15px; }
.account-panel-head p { margin: 0; color: #858d9e; font-size: 10px; }
.security-form { display: grid; gap: 13px; }
.security-form label { display: grid; gap: 5px; color: #4c5565; font-size: 10px; font-weight: 650; }
.security-form input, .key-create-row input { width: 100%; min-height: 42px; border: 1px solid #dfe4ec; border-radius: 10px; padding: 8px 11px; background: #fff; color: #222b39; outline: 0; font-size: 12px; }
.security-form input:focus, .key-create-row input:focus { border-color: #7474d8; box-shadow: 0 0 0 3px rgb(91 91 214 / 9%); }
.password-submit { width: fit-content; margin-top: 3px; }
.security-form .form-error, .security-form .ok-msg { margin: 0; font-size: 10px; }
.key-create-row { margin-bottom: 16px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.key-reveal { margin-bottom: 17px; border: 1px solid #f0d49b; border-radius: 13px; padding: 13px; background: #fff9ed; }
.key-warning { display: grid; margin-bottom: 9px; }
.key-warning strong { color: #8b5713; font-size: 11px; }
.key-warning span { color: #9a7445; font-size: 9px; }
.key-line { display: flex; align-items: stretch; gap: 7px; }
.key-value { min-width: 0; flex: 1; border: 1px solid #ead7b2; border-radius: 8px; padding: 8px; background: #fff; color: #4c3a23; overflow-wrap: anywhere; font-size: 10px; }
.key-list-head { margin: 18px 0 7px; display: flex; align-items: center; justify-content: space-between; }
.key-list-head strong { color: #3a4250; font-size: 11px; }
.key-list-head span { min-width: 20px; height: 20px; display: grid; place-items: center; border-radius: 7px; background: #f0f1f5; color: #727a8b; font-size: 9px; }
.key-list { display: grid; }
.key-row { min-width: 0; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px; border-top: 1px solid #edf0f5; padding: 12px 0; }
.key-row-icon { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 9px; background: #f1f3f7; color: #727b8d; }
.key-row-info { min-width: 0; display: grid; }
.key-row-info strong, .key-row-info small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.key-row-info strong { color: #313947; font-size: 11px; }
.key-row-info small { color: #9299a7; font-size: 8px; }
.key-row-info code { color: #626b7d; }
.key-row-actions { display: flex; gap: 5px; }
.key-empty { min-height: 120px; display: grid; place-content: center; justify-items: center; color: #969dac; text-align: center; }
.key-empty span { font-size: 25px; }
.key-empty p { margin: 5px 0 0; font-size: 10px; }
.api-help { margin-top: 18px; display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 18px; border: 1px solid #e0e4ef; border-radius: 16px; padding: 16px 19px; background: linear-gradient(135deg, #f8f8ff, #fff); }
.api-help strong { color: #353d4d; font-size: 11px; }
.api-help p { margin: 2px 0 0; color: #838b9b; font-size: 9px; }
.api-help code { border: 1px solid #dfe2ed; border-radius: 8px; padding: 7px 9px; background: #fff; color: #596173; font-size: 9px; }
.api-help a { font-size: 10px; font-weight: 650; white-space: nowrap; }
@media (max-width: 950px) { .account-layout { grid-template-columns: 1fr; } }
@media (max-width: 650px) {
  .account-panel { padding: 17px; }
  .key-row { grid-template-columns: auto minmax(0, 1fr); }
  .key-row-actions { grid-column: 2; }
  .api-help { grid-template-columns: 1fr; gap: 9px; }
  .api-help code { overflow-x: auto; }
}
@media (max-width: 430px) { .key-create-row { grid-template-columns: 1fr; } }
</style>
