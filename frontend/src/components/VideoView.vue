<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { deleteVideo, fetchPublicConfig, listTeamVideos, listVideos, updateVideo } from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { addVideoFiles, VIDEO_ACCEPT } from '../stores/videoUploads'
import { formatBytes } from '../utils/format'
import UploadDropzone from './UploadDropzone.vue'
import CollectionPickerModal from './CollectionPickerModal.vue'
import VideoCard from './VideoCard.vue'
import VideoPlayerModal from './VideoPlayerModal.vue'
import VideoUploadQueue from './VideoUploadQueue.vue'

const props = defineProps({
  user: { type: Object, required: true },
  teamId: { type: [Number, String], default: null },
  canManage: { type: Boolean, default: false },
})

const videos = ref([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const loadError = ref('')
const query = ref('')
const uploadName = ref('')
const uploadVisibility = ref('private')
const selectedVideo = ref(null)
const groupTarget = ref(null)
const publicConfig = ref(null)
const PAGE_SIZE = 12
let searchTimer
let loadGeneration = 0
let publicConfigPromise = null

const isTeam = computed(() => props.teamId !== null && props.teamId !== undefined)
const hasMore = computed(() => videos.value.length < total.value)
const groupTargetTeamId = computed(() => groupTarget.value?.team_id ?? props.teamId)
const isGlobalAdmin = computed(() => props.user.role === 'admin' && !isTeam.value)
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
  const scope = String(props.teamId ?? 'personal')
  const requestQuery = query.value.trim()
  const offset = append ? videos.value.length : 0
  if (append) loadingMore.value = true
  else loading.value = true
  loadError.value = ''
  try {
    const response = isTeam.value
      ? await listTeamVideos(props.teamId, { limit: PAGE_SIZE, offset, q: requestQuery })
      : await listVideos({ limit: PAGE_SIZE, offset, q: requestQuery })
    if (generation !== loadGeneration || scope !== String(props.teamId ?? 'personal') || requestQuery !== query.value.trim()) return
    videos.value = append ? [...videos.value, ...(response.items || [])] : (response.items || [])
    total.value = Number(response.total || 0)
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
        uploadVisibility.value = config.default_visibility || uploadVisibility.value
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
    videos.value = videos.value.filter(video => video.code !== item.code)
    total.value = Math.max(0, total.value - 1)
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

function onUploadComplete(event) {
  const uploadedTeamId = event.detail?.team_id
  const belongsHere = isTeam.value
    ? String(uploadedTeamId) === String(props.teamId)
    : uploadedTeamId === null || uploadedTeamId === undefined
  if (belongsHere) loadVideos()
}

watch(() => props.teamId, () => {
  query.value = ''
  selectedVideo.value = null
  loadVideos()
})

onMounted(() => {
  window.addEventListener('oss:video-upload-complete', onUploadComplete)
  loadVideos()
  ensurePublicConfig().catch(() => {})
})
onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  window.removeEventListener('oss:video-upload-complete', onUploadComplete)
})
</script>

<template>
  <section class="library-view">
    <div class="section-heading">
      <div>
        <p class="eyebrow">{{ isTeam ? '团队媒体库' : isGlobalAdmin ? '全站媒体库' : '断点续传' }}</p>
        <h2>{{ isTeam ? '团队视频' : isGlobalAdmin ? '全站视频' : '我的视频' }}</h2>
        <p>大文件分片传输，断网或刷新后仍可继续。</p>
      </div>
      <span class="total-badge">{{ total }} 个</span>
    </div>

    <div class="upload-panel video-upload-panel">
      <div class="options">
        <input v-model="uploadName" class="name-input" placeholder="视频命名（可选，多文件自动加序号）" maxlength="255" aria-label="视频显示名称" />
        <select v-model="uploadVisibility" class="vis-select" aria-label="视频可见性">
          <option value="private">私密 · 仅自己/团队可见</option>
          <option value="public">公开 · 任何人可访问</option>
        </select>
      </div>
      <UploadDropzone
        :accept="VIDEO_ACCEPT"
        label="选择视频，或拖拽到这里"
        :description="uploadDescription"
        aria-label="选择或拖拽视频上传"
        @files="handleFiles"
      />
    </div>

    <VideoUploadQueue :team-id="teamId" />

    <div class="library-toolbar">
      <div class="search-row">
        <input v-model="query" class="search" type="search" placeholder="搜索名称、文件名或短码" aria-label="搜索视频" @input="onQueryInput" />
        <button v-if="query" class="clear" aria-label="清除搜索" @click="clearSearch">×</button>
      </div>
    </div>

    <p v-if="loading" class="status loading-state" aria-live="polite">正在加载视频…</p>
    <div v-else-if="loadError" class="status error" role="alert">加载失败：{{ loadError }} <button class="secondary" @click="loadVideos()">重试</button></div>
    <template v-else>
      <div v-if="videos.length" class="media-grid">
        <VideoCard
          v-for="item in videos"
          :key="`${item.code}-${item.visibility}`"
          :item="item"
          :deletable="canDelete(item)"
          :show-scope="isGlobalAdmin"
          :groupable="canGroup(item)"
          @add-to-group="groupTarget = item"
          @play="selectedVideo = item"
          @delete="onDelete(item)"
          @toggle-visibility="onToggleVisibility(item)"
        />
      </div>
      <div v-else class="empty-state">
        <div class="empty-icon">▶</div>
        <h3>{{ query ? '没有找到匹配视频' : '这里还没有视频' }}</h3>
        <p>{{ query ? '换个关键词试试看。' : '从上方上传第一个视频吧。' }}</p>
      </div>
      <div v-if="hasMore" class="load-more-wrap">
        <button class="secondary" :disabled="loadingMore" @click="loadVideos({ append: true })">
          {{ loadingMore ? '加载中…' : `加载更多（还有 ${total - videos.length} 个）` }}
        </button>
      </div>
    </template>

    <VideoPlayerModal v-if="selectedVideo" :item="selectedVideo" @close="selectedVideo = null" />
    <CollectionPickerModal
      v-if="groupTarget"
      :media="groupTarget"
      :team-id="groupTargetTeamId"
      :user-id="user.id"
      :can-manage="canManage || user.role === 'admin'"
      @close="groupTarget = null"
    />
  </section>
</template>
