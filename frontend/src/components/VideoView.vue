<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { deleteVideo, fetchPublicConfig, listTeamVideos, listVideos, updateVideo } from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { acquireModalLock, releaseModalLock } from '../stores/modalLock'
import { addVideoFiles, VIDEO_ACCEPT, videoUploadState } from '../stores/videoUploads'
import { formatBytes } from '../utils/format'
import { WORKSPACE_DRAWER_MAX_WIDTH, WORKSPACE_DRAWER_MEDIA_QUERY } from '../utils/layout'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'
import UploadDropzone from './UploadDropzone.vue'
import VideoCard from './VideoCard.vue'
import VideoInspector from './VideoInspector.vue'
import VideoPlayerModal from './VideoPlayerModal.vue'
import VideoUploadQueue from './VideoUploadQueue.vue'

const props = defineProps({
  user: { type: Object, required: true },
  teamId: { type: [Number, String], default: null },
  canManage: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
  scope: {
    type: String,
    default: 'mine',
    validator: value => ['mine', 'all'].includes(value),
  },
})

const videos = ref([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const loadError = ref('')
const query = ref('')
const uploadName = ref('')
// 前端上传默认私密，符合“私有媒体空间”的用户心智；后端仍保持 public 兼容契约。
// 用户在弹窗中做出的选择会记忆到 localStorage，后续上传沿用该偏好。
const uploadVisibility = ref(
  typeof localStorage !== 'undefined' && localStorage.getItem('oss_upload_visibility') === 'public'
    ? 'public'
    : 'private'
)
watch(uploadVisibility, value => {
  if (typeof localStorage !== 'undefined') localStorage.setItem('oss_upload_visibility', value)
})
const selectedVideo = ref(null)
const playerVideo = ref(null)
const uploadOpen = ref(false)
const inspectorOpen = ref(false)
const inspectorPanel = ref(null)
const isNarrowLayout = ref(typeof window !== 'undefined' && window.innerWidth <= WORKSPACE_DRAWER_MAX_WIDTH)
const publicConfig = ref(null)
const PAGE_SIZE = 12
let searchTimer
let loadGeneration = 0
let publicConfigPromise = null
let layoutMedia = null
let drawerLocked = false
let previousInspectorFocus = null

const isTeam = computed(() => props.teamId !== null && props.teamId !== undefined)
const hasMore = computed(() => videos.value.length < total.value)
const isGlobalAdmin = computed(() => props.user.role === 'admin' && !isTeam.value && props.scope === 'all')
const inspectorDrawerMode = computed(() => props.embedded || isNarrowLayout.value)
const drawerActive = computed(() => inspectorOpen.value && inspectorDrawerMode.value)
const inspectorHidden = computed(() => inspectorDrawerMode.value && !inspectorOpen.value)
const uploadButtonLabel = computed(() => (
  props.user.role === 'admin' && !isTeam.value ? '上传到我的个人空间' : '上传'
))
const uploadModalTitle = computed(() => (
  props.user.role === 'admin' && !isTeam.value ? '上传视频到我的个人空间' : '上传视频'
))
const uploadModalDescription = computed(() => (
  isTeam.value
    ? '视频会保存到当前团队空间；支持分片传输和断点续传。'
    : '视频会保存到当前账号的个人空间；支持分片传输和断点续传。'
))
const uploadTasks = computed(() => videoUploadState.tasks.filter(task => {
  if (isTeam.value) return String(task.teamId) === String(props.teamId)
  return task.teamId === null || task.teamId === undefined
}))
const uploadDescription = computed(() => {
  const parts = ['支持 MP4、MOV、WebM、MKV、AVI、MPEG、TS、OGV、3GP、FLV、WMV']
  if (Number(publicConfig.value?.max_video_size_mb) > 0) {
    parts.push(`单文件最大 ${publicConfig.value.max_video_size_mb} MB`)
  }
  if (Number(publicConfig.value?.video_chunk_size_mb) > 0) {
    parts.push(`${publicConfig.value.video_chunk_size_mb} MB 分片`)
  }
  const userQuota = Number(publicConfig.value?.user_storage_quota_bytes)
  const teamQuota = Number(publicConfig.value?.team_storage_quota_bytes)
  if (userQuota > 0) parts.push(`用户累计额度 ${formatBytes(userQuota)}`)
  if (isTeam.value && teamQuota > 0) parts.push(`团队累计额度 ${formatBytes(teamQuota)}`)
  return parts.join(' · ')
})

async function loadVideos({ append = false } = {}) {
  const generation = ++loadGeneration
  const requestScope = isTeam.value ? `team:${props.teamId}` : props.scope
  const requestQuery = query.value.trim()
  const offset = append ? videos.value.length : 0
  if (append) loadingMore.value = true
  else loading.value = true
  loadError.value = ''
  try {
    const response = isTeam.value
      ? await listTeamVideos(props.teamId, { limit: PAGE_SIZE, offset, q: requestQuery })
      : await listVideos({ limit: PAGE_SIZE, offset, q: requestQuery, scope: props.scope })
    const currentScope = isTeam.value ? `team:${props.teamId}` : props.scope
    if (generation !== loadGeneration || requestScope !== currentScope || requestQuery !== query.value.trim()) return
    const incoming = response.items || []
    videos.value = append ? [...videos.value, ...incoming] : incoming
    total.value = Number(response.total || 0)
    if (!append) {
      const selectedCode = selectedVideo.value?.code
      selectedVideo.value = props.embedded
        ? null
        : (incoming.find(item => item.code === selectedCode) || incoming[0] || null)
      if (!selectedVideo.value) inspectorOpen.value = false
    }
  } catch (error) {
    if (generation === loadGeneration) loadError.value = error.message
  } finally {
    if (generation === loadGeneration) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function onQueryInput() {
  loadGeneration++
  clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => loadVideos(), 300)
}

async function ensurePublicConfig() {
  if (publicConfig.value) return publicConfig.value
  if (!publicConfigPromise) {
    publicConfigPromise = fetchPublicConfig()
      .then(config => {
        publicConfig.value = config
        return config
      })
      .finally(() => { publicConfigPromise = null })
  }
  return publicConfigPromise
}

async function handleFiles(files) {
  try { await ensurePublicConfig() } catch { /* server validation remains authoritative */ }
  const list = Array.from(files || [])
  const base = uploadName.value.trim()
  list.forEach((file, index) => {
    const name = base ? (list.length > 1 ? `${base}-${index + 1}` : base) : ''
    const [result] = addVideoFiles([file], {
      name,
      visibility: uploadVisibility.value,
      teamId: props.teamId,
      maxSize: Number(publicConfig.value?.max_video_size_mb || 0) > 0
        ? Number(publicConfig.value.max_video_size_mb) * 1024 * 1024
        : Infinity,
    })
    if (result?.error) toast(`${file.name}：${result.error}`, 'error')
    else if (result?.duplicate) toast(`${file.name} 已在相同上传队列中`, 'info')
  })
}

async function onDelete(item) {
  const ok = await confirmAction({
    title: '删除视频',
    message: `确定删除「${item.name || item.original_filename || item.code}」${isGlobalAdmin.value ? `（属主：${item.owner_username || `用户 #${item.owner_id}`}）` : ''}？原文件将无法恢复。`,
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteVideo(item.code)
    const deletedIndex = videos.value.findIndex(video => video.code === item.code)
    videos.value = videos.value.filter(video => video.code !== item.code)
    total.value = Math.max(0, total.value - 1)
    if (selectedVideo.value?.code === item.code) {
      selectedVideo.value = videos.value[deletedIndex] || videos.value[deletedIndex - 1] || null
      if (!selectedVideo.value) inspectorOpen.value = false
    }
    toast('视频已删除', 'success')
  } catch (error) {
    toast(`删除失败：${error.message}`, 'error')
  }
}

async function onToggleVisibility(item) {
  const next = item.visibility === 'private' ? 'public' : 'private'
  if (next === 'public') {
    const ok = await confirmAction({
      title: '公开视频',
      message: `公开后，任何拿到链接的人都能播放或下载这个视频。${isGlobalAdmin.value ? ` 属主：${item.owner_username || `用户 #${item.owner_id}`}。` : ''}`,
      confirmText: '设为公开',
    })
    if (!ok) return
  }
  try {
    const updated = await updateVideo(item.code, { visibility: next })
    Object.assign(item, updated)
    if (selectedVideo.value?.code === item.code) selectedVideo.value = item
    toast(next === 'public' ? '视频已公开' : '视频已设为私密', 'success')
  } catch (error) {
    toast(`操作失败：${error.message}`, 'error')
  }
}

function canDelete(item) {
  return props.user.role === 'admin' || props.canManage || item.owner_id === props.user.id
}

function canGroup(item) {
  if (isTeam.value || props.user.role !== 'admin') return true
  if (item.team_id !== null && item.team_id !== undefined) return true
  return String(item.owner_id) === String(props.user.id)
}

function clearSearch() {
  query.value = ''
  loadVideos()
}

function selectVideo(item) {
  selectedVideo.value = item
  inspectorOpen.value = true
}

function closeInspector() {
  inspectorOpen.value = false
}

function onInspectorKeydown(event) {
  const hasModal = Boolean(document.querySelector('.base-modal-panel'))
  const active = document.activeElement
  const isTyping = active && (
    active.tagName === 'INPUT' ||
    active.tagName === 'TEXTAREA' ||
    active.tagName === 'SELECT' ||
    active.isContentEditable
  )

  if (event.key === 'Escape' && !hasModal) {
    if (inspectorOpen.value) {
      event.preventDefault()
      closeInspector()
      return
    }
  }

  // Handle arrow navigation between video cards when not typing and no modal is blocking
  if (!hasModal && !isTyping && videos.value.length > 1 && selectedVideo.value) {
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      const currentIndex = videos.value.findIndex(v => v.code === selectedVideo.value?.code)
      if (currentIndex !== -1 && currentIndex < videos.value.length - 1) {
        event.preventDefault()
        selectVideo(videos.value[currentIndex + 1])
        return
      }
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      const currentIndex = videos.value.findIndex(v => v.code === selectedVideo.value?.code)
      if (currentIndex > 0) {
        event.preventDefault()
        selectVideo(videos.value[currentIndex - 1])
        return
      }
    }
  }

  // Focus trapping for narrow / embedded drawer mode
  if (!drawerActive.value || hasModal) return
  if (event.key !== 'Tab') return
  const root = inspectorPanel.value?.getElement?.()
  if (!root) return
  const focusable = [...root.querySelectorAll(
    'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
  )]
  const closeButton = root.parentElement?.querySelector('.inspector-mobile-close')
  if (closeButton && !closeButton.disabled) focusable.push(closeButton)
  if (!focusable.length) {
    event.preventDefault()
    root.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && (document.activeElement === first || document.activeElement === root)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  } else if (!root.contains(document.activeElement)) {
    event.preventDefault()
    first.focus()
  }
}

function onUploadComplete(event) {
  const uploadedTeamId = event.detail?.team_id
  const belongsHere = isTeam.value
    ? String(uploadedTeamId) === String(props.teamId)
    : isGlobalAdmin.value || uploadedTeamId === null || uploadedTeamId === undefined
  if (belongsHere) loadVideos()
}

watch(() => [props.teamId, props.scope], () => {
  query.value = ''
  selectedVideo.value = null
  inspectorOpen.value = false
  uploadOpen.value = false
  loadVideos()
})

watch(drawerActive, async active => {
  if (active) {
    previousInspectorFocus = document.activeElement
    if (!drawerLocked) {
      acquireModalLock()
      drawerLocked = true
    }
    await nextTick()
    inspectorPanel.value?.focus?.()
  } else {
    if (drawerLocked) {
      releaseModalLock()
      drawerLocked = false
    }
    await nextTick()
    previousInspectorFocus?.focus?.()
    previousInspectorFocus = null
  }
})

onMounted(() => {
  window.addEventListener('oss:video-upload-complete', onUploadComplete)
  window.addEventListener('keydown', onInspectorKeydown)
  if (window.matchMedia) {
    layoutMedia = window.matchMedia(WORKSPACE_DRAWER_MEDIA_QUERY)
    isNarrowLayout.value = layoutMedia.matches
    layoutMedia.onchange = event => { isNarrowLayout.value = event.matches }
  }
  loadVideos()
  ensurePublicConfig().catch(() => {})
})
onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  window.removeEventListener('oss:video-upload-complete', onUploadComplete)
  window.removeEventListener('keydown', onInspectorKeydown)
  if (layoutMedia) layoutMedia.onchange = null
  if (drawerLocked) {
    releaseModalLock()
    drawerLocked = false
  }
})
</script>

<template>
  <section class="asset-library video-library" :class="{ 'asset-library-embedded': embedded, 'inspector-open': inspectorOpen }">
    <div class="asset-library-main" :inert="drawerActive ? '' : undefined">
      <header v-if="!embedded" class="library-heading">
        <div class="library-title">
          <p>{{ isTeam ? '团队媒体库' : isGlobalAdmin ? '全站媒体库' : '个人媒体库' }}</p>
          <div>
            <h1>{{ isTeam ? '团队视频' : isGlobalAdmin ? '全站视频' : '我的视频' }}</h1>
            <span>{{ total }} 个</span>
          </div>
        </div>
      </header>

      <div class="library-toolbar">
        <div class="search-row">
          <AppIcon name="search" size="17" />
          <input v-model="query" class="search" type="search" placeholder="搜索名称、文件名或短码" aria-label="搜索视频" @input="onQueryInput" />
          <button v-if="query" class="clear" type="button" aria-label="清除搜索" @click="clearSearch">
            <AppIcon name="close" size="15" />
          </button>
        </div>
        <button v-if="uploadTasks.length" class="upload-activity" type="button" @click="uploadOpen = true">
          {{ uploadTasks.length }} 个上传任务
        </button>
        <button class="primary library-upload-button" type="button" @click="uploadOpen = true">
          <AppIcon name="upload" size="16" />
          {{ uploadButtonLabel }}
        </button>
      </div>

      <p v-if="loading" class="status loading-state" aria-live="polite">正在加载视频…</p>
      <div v-else-if="loadError" class="status error" role="alert">
        <span>加载失败：{{ loadError }}</span>
        <button class="secondary" @click="loadVideos()">重试</button>
      </div>
      <template v-else>
        <div v-if="videos.length" class="media-grid asset-grid" role="list" aria-label="视频列表">
          <VideoCard
            v-for="item in videos"
            :key="`${item.code}-${item.visibility}`"
            :item="item"
            selectable
            :selected="selectedVideo?.code === item.code"
            @select="selectVideo(item)"
          />
        </div>
        <div v-else class="empty-state">
          <div class="empty-icon"><AppIcon name="video" size="22" /></div>
          <h3>{{ query ? '没有找到匹配视频' : '这里还没有视频' }}</h3>
          <p>{{ query ? '换个关键词试试看。' : '上传第一个视频，开始建立媒体库。' }}</p>
          <button v-if="!query && !embedded" class="primary" type="button" @click="uploadOpen = true">{{ uploadButtonLabel }}</button>
        </div>
        <div v-if="hasMore" class="load-more-wrap">
          <button class="secondary" :disabled="loadingMore" @click="loadVideos({ append: true })">
            {{ loadingMore ? '加载中…' : `加载更多（还有 ${total - videos.length} 个）` }}
          </button>
        </div>
      </template>
    </div>

    <VideoInspector
      v-if="selectedVideo"
      ref="inspectorPanel"
      tabindex="-1"
      :role="drawerActive ? 'dialog' : undefined"
      :aria-modal="drawerActive ? 'true' : undefined"
      :aria-hidden="inspectorHidden ? 'true' : undefined"
      :inert="inspectorHidden ? '' : undefined"
      :item="selectedVideo"
      :user="user"
      :can-manage="canDelete(selectedVideo)"
      :can-manage-groups="canManage || user.role === 'admin'"
      :is-global-admin="isGlobalAdmin"
      :team-id="selectedVideo.team_id ?? teamId"
      :groupable="canGroup(selectedVideo)"
      @play="playerVideo = selectedVideo"
      @delete="onDelete(selectedVideo)"
      @toggle-visibility="onToggleVisibility(selectedVideo)"
      @updated="Object.assign(selectedVideo, $event)"
    />
    <aside
      v-else
      class="image-inspector image-inspector-empty"
      aria-label="视频详情"
      :aria-hidden="inspectorHidden ? 'true' : undefined"
      :inert="inspectorHidden ? '' : undefined"
    >
      <AppIcon name="video" size="24" />
      <strong>视频详情</strong>
      <p>{{ loading ? '正在加载媒体库…' : '选择一个视频查看详情' }}</p>
    </aside>
    <button v-if="inspectorOpen" class="inspector-mobile-backdrop" type="button" tabindex="-1" aria-label="关闭视频详情" @click="closeInspector" />
    <button v-if="inspectorOpen" class="inspector-mobile-close" type="button" aria-label="关闭视频详情" @click="closeInspector">
      <AppIcon name="close" size="17" />
    </button>

    <BaseModal
      v-if="uploadOpen"
      :title="uploadModalTitle"
      :description="uploadModalDescription"
      labelled-by="video-upload-title"
      wide
      @close="uploadOpen = false"
    >
      <div class="image-upload-dialog video-upload-dialog">
        <div class="upload-settings">
          <label>
            <span>视频命名</span>
            <input v-model="uploadName" class="name-input" type="text" placeholder="可选，多个视频会自动添加序号" maxlength="255" />
          </label>
          <label>
            <span>可见性</span>
            <select v-model="uploadVisibility" class="vis-select">
              <option value="private">私密 · 仅自己/团队可见</option>
              <option value="public">公开 · 任何人可访问</option>
            </select>
          </label>
        </div>
        <UploadDropzone
          :accept="VIDEO_ACCEPT"
          label="选择视频，或拖拽到这里"
          :description="uploadDescription"
          aria-label="选择或拖拽视频上传"
          @files="handleFiles"
        />
        <VideoUploadQueue :team-id="teamId" />
      </div>
      <template #footer>
        <button class="ghost" type="button" @click="uploadOpen = false">关闭</button>
      </template>
    </BaseModal>

    <VideoPlayerModal v-if="playerVideo" :item="playerVideo" @close="playerVideo = null" />
  </section>
</template>
