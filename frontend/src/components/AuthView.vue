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
const configLoading = ref(true)

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
  try {
    config.value = await fetchPublicConfig()
  } catch {
    // Fail closed: a login remains possible while registration is hidden.
    config.value = { registration_mode: 'closed' }
  } finally {
    configLoading.value = false
  }
})
</script>

<template>
  <main class="auth-shell">
    <section class="auth-story" aria-label="产品介绍">
      <div class="auth-brand">
        <span class="auth-logo">O</span>
        <span><strong>OSS Media</strong><small>SELF-HOSTED LIBRARY</small></span>
      </div>

      <div class="story-copy">
        <span class="story-kicker">YOUR PRIVATE MEDIA SPACE</span>
        <h1>让每一份媒体素材，<br />都有清晰的归处。</h1>
        <p>从图片分享，到大视频断点续传；从个人分组，到团队协作。数据始终保存在你自己的服务器。</p>
      </div>

      <div class="feature-list">
        <div><span><AppIcon name="image" /></span><strong>原图存储</strong><small>保留原始质量与格式</small></div>
        <div><span><AppIcon name="video" /></span><strong>断点续传</strong><small>大视频稳定分片上传</small></div>
        <div><span><AppIcon name="collection" /></span><strong>灵活分组</strong><small>个人与团队素材井然有序</small></div>
      </div>

      <p class="story-foot">私有部署 · 权限隔离 · 可签名分享</p>
    </section>

    <section class="auth-form-side">
      <div class="auth-card">
        <div class="auth-card-head">
          <span class="mobile-auth-logo">O</span>
          <p class="auth-eyebrow">WELCOME TO OSS</p>
          <h2>{{ mode === 'login' ? '欢迎回来' : '创建你的空间' }}</h2>
          <p>{{ mode === 'login' ? '登录后继续管理图片、视频和团队素材。' : '创建账户，开始搭建你的私有媒体库。' }}</p>
        </div>

        <div class="auth-tabs" role="tablist" aria-label="账户操作">
          <button role="tab" :aria-selected="mode === 'login'" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
          <button v-if="canRegister" role="tab" :aria-selected="mode === 'register'" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
        </div>

        <form @submit.prevent="submit">
          <label class="auth-field">
            <span>用户名</span>
            <div class="auth-input-wrap">
              <AppIcon name="account" size="17" />
              <input
                v-model.trim="username"
                type="text"
                placeholder="输入用户名"
                autocomplete="username"
                required
                minlength="3"
                maxlength="64"
                autofocus
              />
            </div>
            <small v-if="mode === 'register'">3–64 位，仅支持字母、数字、下划线和连字符</small>
          </label>

          <label v-if="mode === 'register' && needsInvite" class="auth-field">
            <span>邀请码</span>
            <div class="auth-input-wrap">
              <span class="invite-icon" aria-hidden="true">#</span>
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
              <span class="lock-icon" aria-hidden="true"></span>
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

          <div v-if="error" class="auth-error" role="alert">
            <span>!</span><p>{{ error }}</p>
          </div>

          <button type="submit" class="auth-submit" :disabled="busy || configLoading || !username || password.length < 6 || (needsInvite && !inviteCode)">
            <span>{{ submitText }}</span>
            <AppIcon v-if="!busy" name="chevron" size="16" />
            <span v-else class="submit-spinner" aria-hidden="true"></span>
          </button>
        </form>

        <p class="auth-security"><span aria-hidden="true">✓</span> 凭据仅用于访问当前自建服务</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.auth-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(420px, 1.08fr) minmax(440px, .92fr);
  background: #f6f7fb;
}

.auth-story {
  position: relative;
  overflow: hidden;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  padding: clamp(35px, 5vw, 74px);
  background:
    radial-gradient(circle at 8% 5%, rgb(124 126 244 / 28%), transparent 24rem),
    radial-gradient(circle at 95% 98%, rgb(71 167 214 / 17%), transparent 28rem),
    linear-gradient(145deg, #242641, #30345d 58%, #282b4d);
  color: #fff;
}

.auth-story::before,
.auth-story::after {
  content: '';
  position: absolute;
  border: 1px solid rgb(255 255 255 / 7%);
  border-radius: 50%;
  pointer-events: none;
}

.auth-story::before { top: -170px; right: -180px; width: 470px; height: 470px; box-shadow: 0 0 0 55px rgb(255 255 255 / 2.5%), 0 0 0 110px rgb(255 255 255 / 1.5%); }
.auth-story::after { bottom: -210px; left: -220px; width: 480px; height: 480px; box-shadow: 0 0 0 64px rgb(255 255 255 / 2%); }

.auth-brand {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}

.auth-logo,
.mobile-auth-logo {
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: linear-gradient(145deg, #8889f1, #6668d8);
  box-shadow: 0 12px 30px rgb(9 10 34 / 26%);
  color: #fff;
  font-weight: 800;
}

.auth-logo { width: 43px; height: 43px; }
.auth-brand > span:last-child { display: grid; }
.auth-brand strong { font-size: 14px; letter-spacing: .02em; }
.auth-brand small { margin-top: 2px; color: #aeb2d1; font-size: 8px; font-weight: 700; letter-spacing: .16em; }

.story-copy {
  position: relative;
  z-index: 1;
  max-width: 650px;
  margin: auto 0 42px;
}

.story-kicker {
  color: #aeb2f6;
  font-size: 10px;
  font-weight: 750;
  letter-spacing: .18em;
}

.story-copy h1 {
  margin: 16px 0 20px;
  font-size: clamp(38px, 5.1vw, 67px);
  line-height: 1.12;
  letter-spacing: -.052em;
}

.story-copy p { max-width: 590px; margin: 0; color: #bcc1d8; font-size: 15px; line-height: 1.85; }

.feature-list {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.feature-list > div {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 2px 10px;
  border: 1px solid rgb(255 255 255 / 9%);
  border-radius: 14px;
  padding: 13px;
  background: rgb(255 255 255 / 5%);
  backdrop-filter: blur(8px);
}

.feature-list > div > span { grid-row: 1 / 3; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 10px; background: rgb(255 255 255 / 9%); color: #c5c8ff; }
.feature-list strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.feature-list small { overflow: hidden; color: #9da3bf; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.story-foot { position: relative; z-index: 1; margin: 32px 0 0; color: #8f96b5; font-size: 9px; letter-spacing: .08em; }

.auth-form-side { min-height: 100vh; display: grid; place-items: center; padding: 42px; }
.auth-card { width: min(440px, 100%); margin: 0; border: 0; border-radius: 0; padding: 0; background: transparent; box-shadow: none; }
.auth-card-head { margin-bottom: 27px; }
.mobile-auth-logo { display: none; width: 40px; height: 40px; margin-bottom: 25px; }
.auth-eyebrow { margin-bottom: 7px; color: #6161ce; font-size: 9px; font-weight: 800; letter-spacing: .15em; }
.auth-card-head h2 { margin: 0 0 8px; color: #202736; font-size: 31px; line-height: 1.2; letter-spacing: -.04em; text-align: left; }
.auth-card-head > p:last-child { margin: 0; color: #7d8596; font-size: 12px; }

.auth-tabs { margin-bottom: 25px; display: grid; grid-template-columns: repeat(auto-fit, minmax(0, 1fr)); gap: 4px; border: 1px solid #e1e5ed; border-radius: 13px; padding: 4px; background: #eef0f5; }
.auth-tabs button { min-height: 38px; border: 0; border-radius: 9px; background: transparent; color: #7a8293; cursor: pointer; font-size: 12px; font-weight: 650; }
.auth-tabs button.active { background: #fff; box-shadow: 0 3px 10px rgb(36 46 73 / 8%); color: #4f4fc3; }

.auth-card form { display: grid; gap: 17px; }
.auth-field { display: grid; gap: 7px; color: #343b49; font-size: 11px; font-weight: 650; }
.auth-field > small { color: #9aa1af; font-size: 9px; font-weight: 400; }
.auth-input-wrap { min-height: 48px; display: flex; align-items: center; gap: 10px; border: 1px solid #dfe4ec; border-radius: 12px; padding: 0 13px; background: #fff; color: #9098a8; transition: 150ms ease; }
.auth-input-wrap:focus-within { border-color: #7171d8; box-shadow: 0 0 0 4px rgb(91 91 214 / 9%); color: #5b5bd6; }
.auth-input-wrap input { min-width: 0; min-height: 46px; flex: 1; border: 0; padding: 0; background: transparent; color: #202736; outline: 0; font-size: 13px; }
.auth-input-wrap input::placeholder { color: #adb3bf; }
.lock-icon { position: relative; width: 15px; height: 12px; border: 1.8px solid currentColor; border-radius: 3px; }
.lock-icon::before { content: ''; position: absolute; left: 2px; top: -8px; width: 7px; height: 8px; border: 1.8px solid currentColor; border-bottom: 0; border-radius: 6px 6px 0 0; }
.invite-icon { width: 15px; color: currentColor; font-size: 15px; font-weight: 750; text-align: center; }
.password-toggle { border: 0; padding: 5px; background: transparent; color: #777f90; cursor: pointer; font-size: 10px; }

.auth-error { display: flex; align-items: flex-start; gap: 9px; border: 1px solid #f5d1ce; border-radius: 10px; padding: 10px 11px; background: #fff5f4; color: #b42318; }
.auth-error > span { width: 18px; height: 18px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 50%; background: #fee4e2; font-size: 10px; font-weight: 800; }
.auth-error p { margin: 0; font-size: 10px; }

.auth-submit { min-height: 49px; display: flex; align-items: center; justify-content: center; gap: 7px; border: 0; border-radius: 12px; background: linear-gradient(135deg, #6262db, #5151c4); box-shadow: 0 12px 25px rgb(78 78 193 / 20%); color: #fff; cursor: pointer; font-size: 12px; font-weight: 700; transition: 150ms ease; }
.auth-submit:hover:not(:disabled) { box-shadow: 0 16px 30px rgb(78 78 193 / 27%); transform: translateY(-1px); }
.auth-submit:disabled { opacity: .56; }
.submit-spinner { width: 15px; height: 15px; border: 2px solid rgb(255 255 255 / 40%); border-top-color: #fff; border-radius: 50%; animation: submit-spin .8s linear infinite; }
@keyframes submit-spin { to { transform: rotate(360deg); } }
.auth-security { margin: 22px 0 0; color: #9ba2b0; font-size: 9px; text-align: center; }
.auth-security span { color: #27866a; }

@media (max-width: 940px) {
  .auth-shell { grid-template-columns: 1fr; }
  .auth-story { display: none; }
  .auth-form-side { padding: 30px 22px; background: radial-gradient(circle at 50% 0, rgb(99 102 241 / 10%), transparent 24rem), #f6f7fb; }
  .mobile-auth-logo { display: grid; }
}

@media (max-width: 480px) {
  .auth-form-side { place-items: start center; padding-top: max(36px, 8vh); }
  .auth-card-head h2 { font-size: 28px; }
}
</style>
