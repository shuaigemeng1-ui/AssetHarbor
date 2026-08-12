<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AccountView from './components/AccountView.vue'
import AdminView from './components/AdminView.vue'
import AppIcon from './components/AppIcon.vue'
import AuthView from './components/AuthView.vue'
import CollectionsView from './components/CollectionsView.vue'
import GalleryView from './components/GalleryView.vue'
import HomeView from './components/HomeView.vue'
import TeamsView from './components/TeamsView.vue'
import UiFeedback from './components/UiFeedback.vue'
import VideoView from './components/VideoView.vue'
import VideoUploadQueue from './components/VideoUploadQueue.vue'
import BaseModal from './components/BaseModal.vue'
import { fetchMe, getToken, setToken } from './api'
import { activeVideoUploadCount, initializeVideoUploads, resetVideoUploads } from './stores/videoUploads'

const user = ref(null)
const view = ref('overview')
const authLoading = ref(Boolean(getToken()))
const uploadCenterOpen = ref(false)
const isAdmin = computed(() => user.value?.role === 'admin')

const viewMeta = {
  overview: { section: '工作台', title: '媒体概览' },
  images: { section: '个人空间', title: '图片' },
  videos: { section: '个人空间', title: '视频' },
  groups: { section: '个人空间', title: '媒体分组' },
  teams: { section: '协作空间', title: '团队' },
  admin: { section: '系统设置', title: '管理中心' },
  account: { section: '账户设置', title: '账户与密钥' },
}

const currentMeta = computed(() => viewMeta[view.value] || viewMeta.overview)

function viewFromHash() {
  const candidate = window.location.hash.replace(/^#\/?/, '').split(/[?&]/, 1)[0]
  return viewMeta[candidate] ? candidate : 'overview'
}

function startUserSession(value) {
  user.value = value
  if (value?.id != null) initializeVideoUploads(value.id)
}

function onUnauthorized() {
  resetVideoUploads()
  uploadCenterOpen.value = false
  user.value = null
  view.value = 'overview'
}

function navigate(next, { replace = false } = {}) {
  if (!viewMeta[next]) return
  if (next === 'admin' && !isAdmin.value) return
  view.value = next
  const hash = `#/${next}`
  if (window.location.hash !== hash) {
    if (replace) window.history.replaceState(null, '', hash)
    else window.location.hash = hash
  }
  window.scrollTo?.({ top: 0, behavior: 'smooth' })
}

function onHashChange() {
  const next = viewFromHash()
  view.value = next === 'admin' && !isAdmin.value ? 'overview' : next
}

onMounted(async () => {
  window.addEventListener('oss:unauthorized', onUnauthorized)
  window.addEventListener('hashchange', onHashChange)
  if (getToken()) {
    try {
      startUserSession(await fetchMe())
    } catch {
      // api.js clears expired credentials.
    }
  }
  onHashChange()
  authLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('oss:unauthorized', onUnauthorized)
  window.removeEventListener('hashchange', onHashChange)
})

function handleAuthed(value) {
  startUserSession(value)
  navigate(viewFromHash(), { replace: true })
}

function logout() {
  setToken(null)
  resetVideoUploads()
  uploadCenterOpen.value = false
  user.value = null
  navigate('overview', { replace: true })
}
</script>

<template>
  <div class="app-shell">
    <UiFeedback />

    <div v-if="authLoading" class="boot-state" aria-live="polite">
      <span class="boot-logo">O</span>
      <span>正在恢复媒体空间…</span>
    </div>
    <AuthView v-else-if="!user" @authed="handleAuthed" />

    <div v-else class="workspace-shell">
      <aside class="app-sidebar">
        <div class="sidebar-head">
          <button class="brand" aria-label="回到媒体概览" @click="navigate('overview')">
            <span class="brand-mark">O</span>
            <span class="brand-copy"><strong>OSS Media</strong><small>私有媒体工作台</small></span>
          </button>
        </div>

        <div class="sidebar-nav-scroll">
          <div class="sidebar-nav-group">
            <span class="sidebar-section-label">Workspace</span>
            <nav class="side-nav" aria-label="媒体导航">
              <button :class="{ active: view === 'overview' }" :aria-current="view === 'overview' ? 'page' : undefined" @click="navigate('overview')">
                <AppIcon name="overview" /><span>概览</span>
              </button>
              <button :class="{ active: view === 'images' }" :aria-current="view === 'images' ? 'page' : undefined" @click="navigate('images')">
                <AppIcon name="image" /><span>图片</span>
              </button>
              <div class="nav-video-row">
                <button :class="{ active: view === 'videos' }" :aria-current="view === 'videos' ? 'page' : undefined" @click="navigate('videos')">
                  <AppIcon name="video" /><span>视频</span>
                </button>
                <button
                  class="nav-upload-center"
                  :aria-label="activeVideoUploadCount ? `打开全局上传中心，${activeVideoUploadCount} 个进行中任务` : '打开全局上传中心'"
                  title="全局上传中心"
                  @click="uploadCenterOpen = true"
                >
                  <AppIcon name="upload" size="14" />
                  <span v-if="activeVideoUploadCount" class="nav-upload-count">{{ activeVideoUploadCount }}</span>
                </button>
              </div>
              <button :class="{ active: view === 'groups' }" :aria-current="view === 'groups' ? 'page' : undefined" @click="navigate('groups')">
                <AppIcon name="collection" /><span>分组</span>
              </button>
              <button :class="{ active: view === 'teams' }" :aria-current="view === 'teams' ? 'page' : undefined" @click="navigate('teams')">
                <AppIcon name="teams" /><span>团队</span>
              </button>
            </nav>
          </div>

          <div class="sidebar-nav-group">
            <span class="sidebar-section-label">Settings</span>
            <nav class="side-nav" aria-label="设置导航">
              <button v-if="isAdmin" :class="{ active: view === 'admin' }" :aria-current="view === 'admin' ? 'page' : undefined" @click="navigate('admin')">
                <AppIcon name="admin" /><span>管理中心</span>
              </button>
              <button :class="{ active: view === 'account' }" :aria-current="view === 'account' ? 'page' : undefined" @click="navigate('account')">
                <AppIcon name="account" /><span>账户与密钥</span>
              </button>
            </nav>
          </div>
        </div>

        <div class="sidebar-spacer"></div>
        <div class="sidebar-tip">
          <strong>媒体由你掌控</strong>
          <p>文件、数据库和上传分片都保存在自己的持久化存储中。</p>
        </div>

        <div class="sidebar-user">
          <span class="user-avatar">{{ user.username.slice(0, 1).toUpperCase() }}</span>
          <span class="user-details"><strong>{{ user.username }}</strong><small>{{ isAdmin ? '系统管理员' : '媒体库用户' }}</small></span>
          <button class="sidebar-logout" aria-label="退出登录" title="退出登录" @click="logout">
            <AppIcon name="logout" size="17" />
          </button>
        </div>
      </aside>

      <div class="workspace-main">
        <header class="workspace-topbar">
          <div class="workspace-context">
            <small>{{ currentMeta.section }}</small>
            <strong>{{ currentMeta.title }}</strong>
          </div>
          <div class="workspace-top-actions">
            <button v-if="view !== 'images'" class="top-action" @click="navigate('images')">
              <AppIcon name="image" size="15" /><span>上传图片</span>
            </button>
            <button v-if="view !== 'videos'" class="top-action" @click="navigate('videos')">
              <AppIcon name="video" size="15" /><span>上传视频</span>
            </button>
            <button class="mobile-user-avatar" aria-label="打开账户设置" @click="navigate('account')">
              {{ user.username.slice(0, 1).toUpperCase() }}
            </button>
          </div>
        </header>

        <main class="page-content">
          <HomeView v-if="view === 'overview'" :user="user" @navigate="navigate" />
          <GalleryView v-if="view === 'images'" :user="user" />
          <VideoView v-if="view === 'videos'" :user="user" />
          <CollectionsView v-if="view === 'groups'" :user="user" />
          <TeamsView v-if="view === 'teams'" :user="user" />
          <AdminView v-if="view === 'admin' && isAdmin" :user="user" />
          <AccountView v-if="view === 'account'" />
        </main>

        <footer class="site-footer">
          <span>OSS Media · 你的私有媒体空间</span>
          <span><a href="/docs">API 文档</a><a href="/healthz">服务状态</a></span>
        </footer>
      </div>
    </div>

    <BaseModal v-if="uploadCenterOpen" title="全局上传中心" description="管理所有个人与团队空间的视频上传任务。" labelled-by="global-upload-center-title" wide @close="uploadCenterOpen = false">
      <VideoUploadQueue all-scopes />
    </BaseModal>
  </div>
</template>

<style scoped>
.boot-state {
  min-height: 100vh;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 13px;
  background: radial-gradient(circle at 50% 30%, rgb(99 102 241 / 9%), transparent 23rem), #f5f6fa;
  color: #7a8293;
  font-size: 11px;
}

.boot-logo {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 15px;
  background: linear-gradient(145deg, #7274e8, #5354c8);
  box-shadow: 0 13px 30px rgb(75 75 185 / 22%);
  color: #fff;
  font-size: 18px;
  font-weight: 800;
  animation: boot-pulse 1.4s ease-in-out infinite;
}

@keyframes boot-pulse {
  50% { box-shadow: 0 13px 38px rgb(75 75 185 / 34%); transform: translateY(-2px); }
}
</style>
