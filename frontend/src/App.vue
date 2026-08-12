<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AccountView from './components/AccountView.vue'
import AdminView from './components/AdminView.vue'
import AuthView from './components/AuthView.vue'
import GalleryView from './components/GalleryView.vue'
import TeamsView from './components/TeamsView.vue'
import { fetchMe, getToken, setToken } from './api'

const user = ref(null)
const view = ref('gallery')

const isAdmin = computed(() => user.value?.role === 'admin')

function onUnauthorized() {
  user.value = null
}

onMounted(async () => {
  window.addEventListener('oss:unauthorized', onUnauthorized)
  if (getToken()) {
    try {
      user.value = await fetchMe()
    } catch {
      // invalid token — api.js already cleared it
    }
  }
})

onBeforeUnmount(() => window.removeEventListener('oss:unauthorized', onUnauthorized))

function handleAuthed(u) {
  user.value = u
}

function logout() {
  setToken(null)
  user.value = null
}
</script>

<template>
  <main>
    <template v-if="!user">
      <AuthView @authed="handleAuthed" />
    </template>

    <template v-else>
      <header>
        <div>
          <h1>oss<span>.</span></h1>
          <p class="subtitle">自托管图床 · 上传即得短码链接</p>
        </div>
        <div class="userbox">
          <span class="username">{{ user.username }}</span>
          <span class="role-badge" :class="{ admin: isAdmin }">
            {{ isAdmin ? '管理员' : '用户' }}
          </span>
          <button class="ghost" @click="logout">退出</button>
        </div>
      </header>

      <nav class="tabs-nav">
        <button :class="{ active: view === 'gallery' }" @click="view = 'gallery'">我的图片</button>
        <button :class="{ active: view === 'teams' }" @click="view = 'teams'">我的团队</button>
        <button v-if="isAdmin" :class="{ active: view === 'admin' }" @click="view = 'admin'">管理</button>
        <button :class="{ active: view === 'account' }" @click="view = 'account'">账户</button>
      </nav>

      <GalleryView v-if="view === 'gallery'" :user="user" />
      <TeamsView v-else-if="view === 'teams'" :user="user" />
      <AdminView v-else-if="view === 'admin'" :user="user" />
      <AccountView v-else-if="view === 'account'" />

      <footer>
        API 文档见 <a href="/docs">/docs</a> · 健康检查 <a href="/healthz">/healthz</a>
      </footer>
    </template>
  </main>
</template>
