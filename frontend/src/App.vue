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
import UploadCenterView from './components/UploadCenterView.vue'
import VideoView from './components/VideoView.vue'
import { fetchMe, getToken, setToken } from './api'
import { activeVideoUploadCount, initializeVideoUploads, resetVideoUploads } from './stores/videoUploads'
import { toast } from './stores/feedback'

const user = ref(null)
const view = ref('overview')
const authLoading = ref(Boolean(getToken()))
const openImageUpload = ref(false)
const accountCredentialBusy = ref(false)
const isAdmin = computed(() => user.value?.role === 'admin')

const viewMeta = {
  overview: { section: '资料库', title: '媒体概览' },
  'upload-center': { section: '工作台', title: '视频上传中心' },
  images: { section: '个人空间', title: '我的图片' },
  'my-images': { section: '个人空间', title: '我的图片' },
  videos: { section: '个人空间', title: '我的视频' },
  'my-videos': { section: '个人空间', title: '我的视频' },
  groups: { section: '资料库', title: '分组' },
  teams: { section: '团队空间', title: '团队' },
  admin: { section: '设置', title: '管理中心' },
  account: { section: '设置', title: '账户与密钥' },
}

const currentMeta = computed(() => {
  if (isAdmin.value && view.value === 'images') return { section: '全站媒体库', title: '全站图片' }
  if (isAdmin.value && view.value === 'videos') return { section: '全站媒体库', title: '全站视频' }
  return viewMeta[view.value] || viewMeta.overview
})
const adminOnlyViews = new Set(['admin', 'my-images', 'my-videos'])

function viewFromHash() {
  const candidate = window.location.hash.replace(/^#\/?/, '').split(/[?&]/, 1)[0]
  return viewMeta[candidate] ? candidate : 'overview'
}

function startUserSession(value) {
  user.value = value
  if (value?.id != null) initializeVideoUploads(value.id)
}

function authorizedView(next) {
  if (!user.value) return next
  if (!adminOnlyViews.has(next) || isAdmin.value) return next
  if (next === 'my-images') return 'images'
  if (next === 'my-videos') return 'videos'
  return 'overview'
}

function onUnauthorized() {
  accountCredentialBusy.value = false
  resetVideoUploads()
  user.value = null
  view.value = 'overview'
}

function navigate(next, { replace = false, upload = false } = {}) {
  if (!viewMeta[next]) return
  if (accountCredentialBusy.value && next !== view.value) {
    toast('凭据操作正在进行，请等待完成后再离开此页面', 'info')
    return
  }
  const target = authorizedView(next)
  openImageUpload.value = ['images', 'my-images'].includes(target) && upload
  view.value = target
  const hash = `#/${target}`
  if (window.location.hash !== hash) {
    if (replace) window.history.replaceState(null, '', hash)
    else window.location.hash = hash
  }
  window.scrollTo?.({ top: 0, behavior: 'smooth' })
}

function onHashChange() {
  const next = viewFromHash()
  if (accountCredentialBusy.value && next !== view.value) {
    // Restore the current route as a new entry instead of overwriting the
    // destination the user tried to visit. Once the mutation finishes, Back
    // can still reach that original destination.
    window.history.pushState(null, '', `#/${view.value}`)
    toast('凭据操作正在进行，请等待完成后再离开此页面', 'info')
    return
  }
  const target = authorizedView(next)
  view.value = target
  if (target !== next) window.history.replaceState(null, '', `#/${target}`)
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
  if (accountCredentialBusy.value) {
    toast('凭据操作正在进行，请等待完成后再退出登录', 'info')
    return
  }
  setToken(null)
  resetVideoUploads()
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

    <div v-else class="workspace-shell" :inert="accountCredentialBusy || undefined" :aria-busy="accountCredentialBusy || undefined">
      <aside class="app-sidebar context-sidebar" aria-label="工作台导航">
        <div class="sidebar-head">
          <button class="sidebar-brand" type="button" aria-label="回到媒体概览" @click="navigate('overview')">
            <span class="sidebar-brand-mark">OSS</span>
            <span class="sidebar-brand-copy">
              <span class="context-kicker">OSS Media</span>
              <strong class="context-title">{{ currentMeta.section }}</strong>
            </span>
          </button>
        </div>

        <div class="sidebar-nav-scroll">
          <div class="sidebar-nav-group">
            <span class="sidebar-section-label">工作台</span>
            <nav class="side-nav" aria-label="工作台导航">
              <button :class="{ active: view === 'overview' }" :aria-current="view === 'overview' ? 'page' : undefined" @click="navigate('overview')">
                <AppIcon name="overview" /><span>媒体概览</span>
              </button>
              <button
                :class="['nav-upload-center', { active: view === 'upload-center' }]"
                :aria-current="view === 'upload-center' ? 'page' : undefined"
                :aria-label="activeVideoUploadCount ? `打开视频上传中心，${activeVideoUploadCount} 个未完成任务` : '打开视频上传中心'"
                @click="navigate('upload-center')"
              >
                <AppIcon name="upload" /><span>视频上传中心</span>
                <span v-if="activeVideoUploadCount" class="nav-upload-count">{{ activeVideoUploadCount }}</span>
              </button>
            </nav>
          </div>

          <div v-if="isAdmin" class="sidebar-nav-group">
            <span class="sidebar-section-label">全站媒体库</span>
            <nav class="side-nav" aria-label="全站媒体库导航">
              <button :class="{ active: view === 'images' }" :aria-current="view === 'images' ? 'page' : undefined" @click="navigate('images')">
                <AppIcon name="image" /><span>全站图片</span>
              </button>
              <button :class="{ active: view === 'videos' }" :aria-current="view === 'videos' ? 'page' : undefined" @click="navigate('videos')">
                <AppIcon name="video" /><span>全站视频</span>
              </button>
            </nav>
          </div>

          <div class="sidebar-nav-group">
            <span class="sidebar-section-label">个人空间</span>
            <nav class="side-nav" aria-label="个人空间导航">
              <button
                :class="{ active: view === (isAdmin ? 'my-images' : 'images') }"
                :aria-current="view === (isAdmin ? 'my-images' : 'images') ? 'page' : undefined"
                @click="navigate(isAdmin ? 'my-images' : 'images')"
              >
                <AppIcon name="image" /><span>我的图片</span>
              </button>
              <button
                :class="{ active: view === (isAdmin ? 'my-videos' : 'videos') }"
                :aria-current="view === (isAdmin ? 'my-videos' : 'videos') ? 'page' : undefined"
                @click="navigate(isAdmin ? 'my-videos' : 'videos')"
              >
                <AppIcon name="video" /><span>我的视频</span>
              </button>
            </nav>
          </div>

          <div class="sidebar-nav-group">
            <span class="sidebar-section-label">协作与整理</span>
            <nav class="side-nav" aria-label="协作与整理导航">
              <button :class="{ active: view === 'teams' }" :aria-current="view === 'teams' ? 'page' : undefined" @click="navigate('teams')">
                <AppIcon name="teams" /><span>团队</span>
              </button>
              <button :class="{ active: view === 'groups' }" :aria-current="view === 'groups' ? 'page' : undefined" @click="navigate('groups')">
                <AppIcon name="collection" /><span>所有分组</span>
              </button>
            </nav>
          </div>

          <div class="sidebar-nav-group">
            <span class="sidebar-section-label">设置</span>
            <nav class="side-nav" aria-label="设置导航">
              <button v-if="isAdmin" :class="{ active: view === 'admin' }" :aria-current="view === 'admin' ? 'page' : undefined" @click="navigate('admin')">
                <AppIcon name="admin" /><span>管理中心</span>
              </button>
              <button :class="{ active: view === 'account' }" :aria-current="view === 'account' ? 'page' : undefined" @click="navigate('account')">
                <AppIcon name="account" /><span>账户与密钥</span>
              </button>
              <button class="nav-logout nav-logout-mobile" type="button" @click="logout">
                <AppIcon name="logout" /><span>退出登录</span>
              </button>
            </nav>
          </div>
        </div>

        <div class="sidebar-spacer"></div>
        <div class="sidebar-user">
          <span class="user-avatar">{{ user.username.slice(0, 1).toUpperCase() }}</span>
          <span class="user-details"><strong>{{ user.username }}</strong><small>{{ isAdmin ? '系统管理员' : '媒体库用户' }}</small></span>
          <button class="sidebar-user-logout" type="button" aria-label="退出登录" title="退出登录" @click="logout">
            <AppIcon name="logout" size="16" />
          </button>
        </div>
      </aside>

      <div
        class="workspace-main"
        :class="{
          'workspace-main-library': ['images', 'my-images', 'videos', 'my-videos'].includes(view),
          'workspace-main-full': view === 'teams',
        }"
      >
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
          <UploadCenterView v-if="view === 'upload-center'" />
          <GalleryView
            v-if="view === 'images' || view === 'my-images'"
            :key="view"
            :user="user"
            :scope="isAdmin && view === 'images' ? 'all' : 'mine'"
            :open-upload="openImageUpload"
            @upload-request-consumed="openImageUpload = false"
          />
          <VideoView
            v-if="view === 'videos' || view === 'my-videos'"
            :key="view"
            :user="user"
            :scope="isAdmin && view === 'videos' ? 'all' : 'mine'"
          />
          <CollectionsView v-if="view === 'groups'" :user="user" />
          <TeamsView v-if="view === 'teams'" :user="user" />
          <AdminView v-if="view === 'admin' && isAdmin" :user="user" />
          <AccountView v-if="view === 'account'" @credential-busy="accountCredentialBusy = $event" />
        </main>

        <footer class="site-footer">
          <span>OSS Media · 你的私有媒体空间</span>
          <span><a href="/docs">API 文档</a><a href="/healthz">服务状态</a></span>
        </footer>
      </div>
    </div>

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
  font-size: 14px;
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
