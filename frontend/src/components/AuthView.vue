<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchPublicConfig, login, register, setToken } from '../api'
import AppIcon from './AppIcon.vue'

const emit = defineEmits(['authed'])

const mode = ref('login')
const username = ref('')
const password = ref('')
const inviteCode = ref('')
const error = ref('')
const busy = ref(false)
const showPassword = ref(false)
const config = ref({ registration_mode: 'closed' })

const canRegister = computed(() => ['open', 'invite'].includes(config.value.registration_mode))
const needsInvite = computed(() => config.value.registration_mode === 'invite')

const submitText = computed(() => {
  if (busy.value) return mode.value === 'login' ? '正在登录…' : '正在创建…'
  return mode.value === 'login' ? '进入媒体库' : '创建账户'
})

function switchMode(next) {
  if (next === 'register' && !canRegister.value) return
  mode.value = next
  error.value = ''
}

async function submit() {
  error.value = ''
  busy.value = true
  try {
    if (mode.value === 'register') await register(username.value, password.value, inviteCode.value.trim())
    const res = await login(username.value, password.value)
    setToken(res.access_token)
    emit('authed', res.user)
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 3500)
  try {
    config.value = await fetchPublicConfig({ signal: controller.signal })
  } catch {
    // Fail closed: a login remains possible while registration is hidden.
    config.value = { registration_mode: 'closed' }
  } finally { clearTimeout(timeout) }
})
</script>

<template>
  <main class="auth-shell">
    <section class="auth-brand-panel" aria-label="OSS Media 品牌介绍">
      <div class="auth-brand">
        <span class="auth-logo">O</span>
        <span class="auth-brand-copy">
          <strong>OSS Media</strong>
          <small>你的私有媒体空间</small>
        </span>
      </div>
    </section>

    <section class="auth-form-side">
      <div class="auth-panel">
        <div class="auth-card-head">
          <h2>{{ mode === 'login' ? '欢迎回来' : '创建你的空间' }}</h2>
          <p>{{ mode === 'login' ? '登录以继续管理你的媒体库' : '创建账户，开始整理你的媒体资料' }}</p>
        </div>

        <div v-if="canRegister" class="auth-tabs" role="group" aria-label="账户操作">
          <button type="button" :aria-pressed="mode === 'login'" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
          <button type="button" :aria-pressed="mode === 'register'" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
        </div>

        <form :aria-busy="busy" @submit.prevent="submit">
          <label class="auth-field">
            <span>用户名</span>
            <div class="auth-input-wrap">
              <AppIcon name="account" size="19" />
              <input
                v-model.trim="username"
                type="text"
                placeholder="输入用户名"
                autocomplete="username"
                required
                minlength="3"
                maxlength="64"
              />
            </div>
            <small v-if="mode === 'register'">3–64 位，仅支持字母、数字、下划线和连字符</small>
          </label>

          <label v-if="mode === 'register' && needsInvite" class="auth-field">
            <span>邀请码</span>
            <div class="auth-input-wrap">
              <AppIcon name="invite" size="19" />
              <input
                v-model.trim="inviteCode"
                type="text"
                placeholder="输入管理员提供的邀请码"
                autocomplete="one-time-code"
                required
                maxlength="256"
              />
            </div>
          </label>

          <label class="auth-field">
            <span>密码</span>
            <div class="auth-input-wrap">
              <AppIcon name="lock" size="19" />
              <input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="至少 6 位密码"
                :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
                required
                minlength="6"
                maxlength="128"
              />
              <button class="password-toggle" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
                {{ showPassword ? '隐藏' : '显示' }}
              </button>
            </div>
          </label>

          <div v-if="error" id="auth-error" class="auth-error" role="alert">
            <AppIcon name="alert" size="18" />
            <p>{{ error }}</p>
          </div>

          <button type="submit" class="auth-submit" :disabled="busy || !username || password.length < 6 || (mode === 'register' && needsInvite && !inviteCode)">
            <span>{{ submitText }}</span>
            <span v-if="busy" class="submit-spinner" aria-hidden="true"></span>
          </button>
        </form>

        <p class="auth-security">
          <AppIcon name="security" size="14" />
          <span>凭据仅用于访问当前自建服务</span>
        </p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.auth-shell {
  --auth-accent: #5656d8;
  --auth-accent-hover: #4747c6;
  --auth-text: #1b2433;
  --auth-muted: #667085;
  --auth-border: #dce2eb;
  min-height: 100vh;
  min-height: 100dvh;
  display: grid;
  grid-template-columns: minmax(360px, 42fr) minmax(560px, 58fr);
  background: #fff;
  color: var(--auth-text);
}

.auth-brand-panel {
  min-height: inherit;
  display: grid;
  align-items: center;
  padding: clamp(52px, 8vw, 132px);
  background: #f3f3fb;
}

.auth-brand {
  display: flex;
  align-items: center;
  gap: 20px;
}

.auth-logo {
  width: 68px;
  height: 68px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 20px;
  background: var(--auth-accent);
  box-shadow: 0 8px 24px rgb(86 86 216 / 14%);
  color: #fff;
  font-size: 22px;
  font-weight: 800;
}

.auth-brand-copy {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.auth-brand strong {
  font-size: clamp(20px, 1.8vw, 25px);
  line-height: 1.2;
  letter-spacing: -.02em;
}

.auth-brand small {
  color: #626b7d;
  font-size: clamp(13px, 1.25vw, 16px);
}

.auth-form-side {
  min-height: inherit;
  display: grid;
  place-items: center;
  overflow-y: auto;
  padding: clamp(48px, 7vw, 112px);
  background: #fff;
}

.auth-panel {
  width: min(480px, 100%);
}

.auth-card-head {
  margin-bottom: 38px;
}

.auth-card-head h2 {
  margin: 0 0 10px;
  color: var(--auth-text);
  font-size: clamp(31px, 3vw, 38px);
  line-height: 1.2;
  letter-spacing: -.045em;
  text-align: left;
}

.auth-card-head p {
  margin: 0;
  color: var(--auth-muted);
  font-size: 15px;
  line-height: 1.6;
}

.auth-tabs {
  width: max-content;
  margin-bottom: 28px;
  display: flex;
  gap: 4px;
  border-radius: 10px;
  padding: 3px;
  background: #f0f1f5;
}

.auth-tabs button {
  min-width: 74px;
  min-height: 36px;
  border: 0;
  border-radius: 8px;
  padding: 0 18px;
  background: transparent;
  color: #626b7d;
  cursor: pointer;
  font-size: 13px;
  font-weight: 650;
}

.auth-tabs button.active {
  background: #fff;
  box-shadow: 0 1px 3px rgb(27 36 51 / 9%);
  color: var(--auth-accent);
}

.auth-panel form {
  display: grid;
  gap: 22px;
}

.auth-field {
  display: grid;
  gap: 9px;
  color: var(--auth-text);
  font-size: 14px;
  font-weight: 650;
}

.auth-field > small {
  color: #667085;
  font-size: 12px;
  font-weight: 400;
}

.auth-input-wrap {
  min-height: 52px;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--auth-border);
  border-radius: 11px;
  padding: 0 15px;
  background: #fff;
  color: #667085;
  transition: border-color 150ms ease, box-shadow 150ms ease, color 150ms ease;
}

.auth-input-wrap:focus-within {
  border-color: var(--auth-accent);
  box-shadow: 0 0 0 3px rgb(86 86 216 / 11%);
  color: var(--auth-accent);
}

.auth-input-wrap input {
  min-width: 0;
  min-height: 50px;
  flex: 1;
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--auth-text);
  outline: 0;
  font-size: 15px;
}

.auth-input-wrap input::placeholder {
  color: #667085;
}

.password-toggle {
  min-width: 44px;
  min-height: 44px;
  border: 0;
  border-radius: 8px;
  padding: 0 4px;
  background: transparent;
  color: #626b7d;
  cursor: pointer;
  font-size: 12px;
}

.password-toggle:hover {
  background: #f5f5fa;
  color: var(--auth-accent);
}

.auth-error {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  border: 1px solid #f2cfcc;
  border-radius: 10px;
  padding: 11px 12px;
  background: #fff6f5;
  color: #b42318;
}

.auth-error p {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
}

.auth-submit {
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  border: 0;
  border-radius: 11px;
  background: var(--auth-accent);
  color: #fff;
  cursor: pointer;
  font-size: 15px;
  font-weight: 700;
  transition: background 150ms ease, transform 150ms ease;
}

.auth-submit:hover:not(:disabled) {
  background: var(--auth-accent-hover);
  transform: translateY(-1px);
}

.auth-submit:active:not(:disabled) {
  transform: translateY(0);
}

.auth-submit:disabled {
  opacity: .52;
}

.submit-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgb(255 255 255 / 40%);
  border-top-color: #fff;
  border-radius: 50%;
  animation: submit-spin .8s linear infinite;
}

@keyframes submit-spin {
  to { transform: rotate(360deg); }
}

.auth-security {
  margin: 25px 0 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  color: #667085;
  font-size: 12px;
  text-align: center;
}

@media (max-width: 920px) {
  .auth-shell {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }

  .auth-brand-panel {
    min-height: auto;
    padding: 24px clamp(24px, 7vw, 56px);
  }

  .auth-brand {
    gap: 12px;
  }

  .auth-logo {
    width: 42px;
    height: 42px;
    border-radius: 13px;
    font-size: 15px;
  }

  .auth-brand-copy {
    gap: 1px;
  }

  .auth-brand strong {
    font-size: 16px;
  }

  .auth-brand small {
    font-size: 12px;
  }

  .auth-form-side {
    min-height: auto;
    place-items: start center;
    padding: clamp(48px, 9vh, 88px) clamp(24px, 7vw, 56px);
  }
}

@media (max-width: 600px) {
  .auth-brand-panel {
    padding: 20px 24px;
  }

  .auth-form-side {
    padding: 40px 24px max(40px, env(safe-area-inset-bottom));
  }

  .auth-card-head {
    margin-bottom: 32px;
  }

  .auth-card-head h2 {
    font-size: 30px;
  }

  .auth-card-head p {
    font-size: 14px;
  }

  .auth-panel form {
    gap: 20px;
  }
}

@media (max-height: 700px) and (min-width: 921px) {
  .auth-form-side {
    place-items: start center;
    padding-block: 48px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-submit,
  .auth-input-wrap {
    transition: none;
  }

  .submit-spinner {
    animation-duration: 1.4s;
  }
}
</style>
