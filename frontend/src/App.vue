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
const openImageUpload = ref(false)
const isAdmin = computed(() => user.value?.role === 'admin')

const viewMeta = {
  overview: { section: '资料库', title: '媒体概览' },
  images: { section: '个人空间', title: '我的图片' },
  videos: { section: '个人空间', title: '我的视频' },
  groups: { section: '资料库', title: '分组' },
  teams: { section: '团队空间', title: '团队' },
  admin: { section: '设置', title: '管理中心' },
  account: { section: '设置', title: '账户与密钥' },
}

const currentMeta = computed(() => viewMeta[view.value] || viewMeta.overview)
const isSettingsView = computed(() => view.value === 'admin' || view.value === 'account')

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

function navigate(next, { replace = false, upload = false } = {}) {
  if (!viewMeta[next]) return
  if (next === 'admin' && !isAdmin.value) return
  openImageUpload.value = next === 'images' && upload
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
      <aside class="global-rail" aria-label="全局导航">
        <button
          class="rail-brand"
          :class="{ active: view === 'overview' }"
          :aria-current="view === 'overview' ? 'page' : undefined"
          aria-label="回到媒体概览"
          title="媒体概览"
          @click="navigate('overview')"
        >
          <span class="brand-mark"><span>OSS</span><span>MEDIA</span></span>
        </button>

        <nav class="rail-nav" aria-label="主要功能">
          <button
            :class="{ active: ['images', 'videos', 'groups'].includes(view) }"
            aria-label="媒体库"
            title="媒体库"
            @click="navigate('images')"
          >
            <AppIcon name="image" />
          </button>
          <button
            :class="{ active: view === 'teams' }"
            :aria-current="view === 'teams' ? 'page' : undefined"
            aria-label="团队空间"
            title="团队空间"
            @click="navigate('teams')"
          >
            <AppIcon name="teams" />
          </button>
          <button
            v-if="isAdmin"
            :class="{ active: view === 'admin' }"
            :aria-current="view === 'admin' ? 'page' : undefined"
            aria-label="管理中心"
            title="管理中心"
            @click="navigate('admin')"
          >
            <AppIcon name="admin" />
          </button>
          <button
            :class="{ active: view === 'account' }"
            :aria-current="view === 'account' ? 'page' : undefined"
            aria-label="账户与密钥"
            title="账户与密钥"
            @click="navigate('account')"
          >
            <AppIcon name="account" />
          </button>
          <button
            class="rail-upload-center"
            :aria-label="activeVideoUploadCount ? `打开视频上传中心，${activeVideoUploadCount} 个进行中任务` : '打开视频上传中心'"
            title="视频上传中心"
            @click="uploadCenterOpen = true"
          >
            <AppIcon name="upload" />
            <span v-if="activeVideoUploadCount" class="nav-upload-count">{{ activeVideoUploadCount }}</span>
          </button>
        </nav>
      </aside>

      <aside class="app-sidebar context-sidebar">
        <div class="sidebar-head">
          <span class="context-kicker">OSS Media</span>
          <strong class="context-title">{{ currentMeta.section }}</strong>
        </div>

        <div class="sidebar-nav-scroll">
          <template v-if="!isSettingsView">
            <div class="sidebar-nav-group">
              <span class="sidebar-section-label">个人空间</span>
              <nav class="side-nav" aria-label="个人空间导航">
                <button :class="{ active: view === 'images' }" :aria-current="view === 'images' ? 'page' : undefined" @click="navigate('images')">
                  <AppIcon name="image" /><span>我的图片</span>
                </button>
                <div class="nav-video-row">
                  <button :class="{ active: view === 'videos' }" :aria-current="view === 'videos' ? 'page' : undefined" @click="navigate('videos')">
                    <AppIcon name="video" /><span>我的视频</span>
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
              </nav>
            </div>

            <div class="sidebar-nav-group">
              <span class="sidebar-section-label">团队空间</span>
              <nav class="side-nav" aria-label="团队空间导航">
                <button :class="{ active: view === 'teams' }" :aria-current="view === 'teams' ? 'page' : undefined" @click="navigate('teams')">
                  <AppIcon name="teams" /><span>团队</span>
                </button>
              </nav>
            </div>

            <div class="sidebar-nav-group">
              <span class="sidebar-section-label">分组</span>
              <nav class="side-nav" aria-label="分组导航">
                <button :class="{ active: view === 'groups' }" :aria-current="view === 'groups' ? 'page' : undefined" @click="navigate('groups')">
                  <AppIcon name="collection" /><span>所有分组</span>
                </button>
              </nav>
            </div>
          </template>

          <div v-else class="sidebar-nav-group">
            <span class="sidebar-section-label">设置</span>
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
        <div class="sidebar-user">
          <span class="user-avatar">{{ user.username.slice(0, 1).toUpperCase() }}</span>
          <span class="user-details"><strong>{{ user.username }}</strong><small>{{ isAdmin ? '系统管理员' : '媒体库用户' }}</small></span>
          <button class="sidebar-logout" aria-label="退出登录" title="退出登录" @click="logout">
            <AppIcon name="logout" size="17" />
          </button>
        </div>
      </aside>

      <div class="workspace-main" :class="{ 'workspace-main-library': ['images', 'videos'].includes(view) }">
        <header class="workspace-topbar">
          <div class="workspace-context">
            <small>{{ currentMeta.section }}</small>
            <strong>{{ currentMeta.title }}</strong>
          </div>
          <div class="workspace-top-actions">
            <button class="mobile-user-avatar" aria-label="打开账户设置" @click="navigate('account')">
              {{ user.username.slice(0, 1).toUpperCase() }}
            </button>
          </div>
        </header>

        <main class="page-content">
          <HomeView v-if="view === 'overview'" :user="user" @navigate="navigate" />
          <GalleryView v-if="view === 'images'" :user="user" :open-upload="openImageUpload" @upload-request-consumed="openImageUpload = false" />
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
  background: #f7f7f8;
  color: #71717a;
  font-size: 11px;
}

.boot-logo {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: #18181b;
  color: #fff;
  font-size: 18px;
  font-weight: 800;
}
</style>
