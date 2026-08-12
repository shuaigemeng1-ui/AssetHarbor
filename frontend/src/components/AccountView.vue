<script setup>
import { onMounted, ref } from 'vue'
import {
  changePassword,
  createApiKey,
  deleteApiKey,
  listApiKeys,
  rotateApiKey,
} from '../api'
import { copyText } from '../utils/clipboard'

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const pwdMsg = ref('')
const pwdError = ref('')

const keys = ref([])
const keyName = ref('')
const newKey = ref(null) // 只显示一次的完整 key
const keyError = ref('')

async function loadKeys() {
  try {
    keys.value = await listApiKeys()
  } catch (err) {
    keyError.value = err.message
  }
}

onMounted(loadKeys)

function fmtDate(s) {
  return new Date(s).toLocaleString()
}

async function doChangePassword() {
  pwdMsg.value = ''
  pwdError.value = ''
  if (newPassword.value !== confirmPassword.value) {
    pwdError.value = '两次输入的新密码不一致'
    return
  }
  try {
    await changePassword(oldPassword.value, newPassword.value)
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    pwdMsg.value = '密码已修改 ✓'
  } catch (err) {
    pwdError.value = err.message
  }
}

async function doCreateKey() {
  newKey.value = null
  keyError.value = ''
  try {
    newKey.value = await createApiKey(keyName.value.trim())
    keyName.value = ''
    await loadKeys()
  } catch (err) {
    keyError.value = err.message
  }
}

async function doRotate(k) {
  if (!window.confirm(`重新生成 Key「${k.name || k.key_prefix}」？旧 Key 将立即失效。`)) return
  newKey.value = null
  keyError.value = ''
  try {
    newKey.value = await rotateApiKey(k.id)
    await loadKeys()
  } catch (err) {
    keyError.value = err.message
  }
}

async function doDeleteKey(k) {
  if (!window.confirm(`撤销 Key「${k.name || k.key_prefix}」？使用它的脚本将立即失效。`)) return
  try {
    await deleteApiKey(k.id)
    await loadKeys()
  } catch (err) {
    keyError.value = err.message
  }
}

async function copyKey() {
  const ok = await copyText(newKey.value.key)
  if (ok) {
    newKey.value.copied = true
    setTimeout(() => (newKey.value.copied = false), 1500)
  } else {
    window.alert('复制失败，请手动选中复制')
  }
}
</script>

<template>
  <section>
    <h2 class="section-title">修改密码</h2>
    <div class="account-form">
      <input v-model="oldPassword" type="password" placeholder="当前密码" autocomplete="current-password" />
      <input v-model="newPassword" type="password" placeholder="新密码（至少 6 位）" autocomplete="new-password" />
      <input v-model="confirmPassword" type="password" placeholder="确认新密码" autocomplete="new-password" />
      <div class="form-actions">
        <button class="primary" :disabled="!oldPassword || !newPassword" @click="doChangePassword">修改密码</button>
        <span v-if="pwdMsg" class="ok-msg">{{ pwdMsg }}</span>
        <span v-if="pwdError" class="form-error">{{ pwdError }}</span>
      </div>
    </div>

    <h2 class="section-title">鉴权 Key（API Key）</h2>
    <p class="status hint">
      用于脚本/命令行调用 oss API（上传、下载、删除图片）。通过
      <code>Authorization: Bearer &lt;key&gt;</code> 或 <code>X-API-Key: &lt;key&gt;</code> 请求头使用。
    </p>

    <div class="options key-create">
      <input v-model="keyName" class="name-input" placeholder="Key 名称（可选，如「我的脚本」）" maxlength="64" />
      <button class="primary" @click="doCreateKey">生成新 Key</button>
    </div>

    <div v-if="newKey" class="key-reveal">
      <p class="warn">⚠️ 完整 Key 仅显示这一次，关闭后无法再次查看，请立即保存！</p>
      <div class="key-line">
        <code class="key-value">{{ newKey.key }}</code>
        <button class="copy" @click="copyKey">{{ newKey.copied ? '已复制 ✓' : '复制' }}</button>
      </div>
      <p class="status hint">用法示例：<code>curl -X POST .../api/upload -H "Authorization: Bearer {{ newKey.key }}" -F "file=@a.png"</code></p>
    </div>
    <p v-if="keyError" class="form-error">{{ keyError }}</p>

    <table class="data-table">
      <thead>
        <tr><th>名称</th><th>前缀</th><th>创建时间</th><th>最近使用</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-if="!keys.length">
          <td colspan="5" class="muted">还没有 Key，点击上方「生成新 Key」创建一个</td>
        </tr>
        <tr v-for="k in keys" :key="k.id">
          <td class="username">{{ k.name || '（未命名）' }}</td>
          <td><code class="prefix">{{ k.key_prefix }}…</code></td>
          <td class="muted">{{ fmtDate(k.created_at) }}</td>
          <td class="muted">{{ k.last_used_at ? fmtDate(k.last_used_at) : '从未使用' }}</td>
          <td class="key-actions">
            <button class="ghost" title="重新生成（旧 Key 立即失效）" @click="doRotate(k)">重新生成</button>
            <button class="ghost danger" title="撤销" @click="doDeleteKey(k)">撤销</button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
