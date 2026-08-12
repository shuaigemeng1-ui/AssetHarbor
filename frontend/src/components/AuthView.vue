<script setup>
import { ref } from 'vue'
import { login, register } from '../api'

const emit = defineEmits(['authed'])

const mode = ref('login')
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    if (mode.value === 'login') {
      const res = await login(username.value, password.value)
      emit('authed', res.user)
    } else {
      await register(username.value, password.value)
      const res = await login(username.value, password.value)
      emit('authed', res.user)
    }
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="auth-card">
    <h1>oss<span>.</span></h1>
    <p class="subtitle">自托管图床 · 登录后上传</p>

    <div class="tabs">
      <button :class="{ active: mode === 'login' }" @click="mode = 'login'; error = ''">登录</button>
      <button :class="{ active: mode === 'register' }" @click="mode = 'register'; error = ''">注册</button>
    </div>

    <form @submit.prevent="submit">
      <input v-model="username" type="text" placeholder="用户名（3 位以上字母/数字/_-）"
             autocomplete="username" required minlength="3" maxlength="64" />
      <input v-model="password" type="password" placeholder="密码（至少 6 位）"
             autocomplete="current-password" required minlength="6" />
      <p v-if="error" class="form-error">{{ error }}</p>
      <button type="submit" class="primary" :disabled="busy">
        {{ busy ? '请稍候…' : mode === 'login' ? '登录' : '注册并登录' }}
      </button>
    </form>
  </div>
</template>
