<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AccountView from './components/AccountView.vue'
import AdminView from './components/AdminView.vue'
import AuthView from './components/AuthView.vue'
import GalleryView from './components/GalleryView.vue'
import TeamsView from './components/TeamsView.vue'
import UiFeedback from './components/UiFeedback.vue'
import VideoView from './components/VideoView.vue'
import { fetchMe, getToken, setToken } from './api'
import { activeVideoUploadCount, initializeVideoUploads, resetVideoUploads } from './stores/videoUploads'

const user = ref(null)
const view = ref('images')
const authLoading = ref(Boolean(getToken()))
const isAdmin = computed(() => user.value?.role === 'admin')

function startUserSession(value) {
  user.value = value
  if (value?.id != null) initializeVideoUploads(value.id)
}

function onUnauthorized() {
  resetVideoUploads()
  user.value = null
}

onMounted(async () => {
  window.addEventListener('oss:unauthorized', onUnauthorized)
  if (getToken()) {
    try {
      startUserSession(await fetchMe())
    } catch {
      // api.js clears expired credentials.
    }
  }
  authLoading.value = false
})

onBeforeUnmount(() => window.removeEventListener('oss:unauthorized', onUnauthorized))

function handleAuthed(value) {
  startUserSession(value)
}

function logout() {
  setToken(null)
  resetVideoUploads()
  user.value = null
  view.value = 'images'
}
</script>

<template>
  <div class="app-shell">
    <UiFeedback />

    <div v-if="authLoading" class="boot-state" aria-live="polite">正在恢复登录状态…</div>
    <AuthView v-else-if="!user" @authed="handleAuthed" />

    <template v-else>
      <header class="site-header">
        <button class="brand" aria-label="回到图片页" @click="view = 'images'">
          <span class="brand-mark">O</span>
          <span class="brand-copy"><strong>OSS</strong><small>自托管媒体库</small></span>
        </button>

        <nav class="tabs-nav" aria-label="主导航">
          <button :class="{ active: view === 'images' }" @click="view = 'images'">图片</button>
          <button :class="{ active: view === 'videos' }" @click="view = 'videos'">
            视频 <span v-if="activeVideoUploadCount" class="nav-count">{{ activeVideoUploadCount }}</span>
          </button>
          <button :class="{ active: view === 'teams' }" @click="view = 'teams'">团队</button>
          <button v-if="isAdmin" :class="{ active: view === 'admin' }" @click="view = 'admin'">管理</button>
          <button :class="{ active: view === 'account' }" @click="view = 'account'">账户</button>
        </nav>

        <div class="userbox">
          <span class="user-avatar">{{ user.username.slice(0, 1).toUpperCase() }}</span>
          <span class="user-details"><strong>{{ user.username }}</strong><small>{{ isAdmin ? '管理员' : '用户' }}</small></span>
          <button class="ghost" @click="logout">退出</button>
        </div>
      </header>

      <main class="page-content">
        <GalleryView v-if="view === 'images'" :user="user" />
        <VideoView v-show="view === 'videos'" :user="user" />
        <TeamsView v-if="view === 'teams'" :user="user" />
        <AdminView v-if="view === 'admin' && isAdmin" :user="user" />
        <AccountView v-if="view === 'account'" />
      </main>

      <footer class="site-footer">
        <span>OSS · 你的私有媒体空间</span>
        <span><a href="/docs">API 文档</a><a href="/healthz">服务状态</a></span>
      </footer>
    </template>
  </div>
</template>
