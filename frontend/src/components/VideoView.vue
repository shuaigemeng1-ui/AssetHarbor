<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { deleteVideo, listTeamVideos, listVideos, updateVideo } from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { addVideoFiles, VIDEO_ACCEPT } from '../stores/videoUploads'
import UploadDropzone from './UploadDropzone.vue'
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
const PAGE_SIZE = 12
let searchTimer

const isTeam = computed(() => props.teamId !== null && props.teamId !== undefined)
const hasMore = computed(() => videos.value.length < total.value)

async function fetchPage(offset) {
  const options = { limit: PAGE_SIZE, offset, q: query.value.trim() }
  return isTeam.value ? listTeamVideos(props.teamId, options) : listVideos(options)
}

async function loadVideos({ append = false } = {}) {
  if (append) loadingMore.value = true
  else loading.value = true
  loadError.value = ''
  try {
    const response = await fetchPage(append ? videos.value.length : 0)
    videos.value = append ? [...videos.value, ...(response.items || [])] : (response.items || [])
    total.value = Number(response.total || 0)
  } catch (error) {
    loadError.value = error.message
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function onQueryInput() {
  clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => loadVideos(), 300)
}

function handleFiles(files) {
  const list = Array.from(files || [])
  const base = uploadName.value.trim()
  list.forEach((file, index) => {
    const name = base ? (list.length > 1 ? `${base}-${index + 1}` : base) : ''
    const [result] = addVideoFiles([file], {
      name,
      visibility: uploadVisibility.value,
      teamId: props.teamId,
    })
    if (result?.error) toast(`${file.name}：${result.error}`, 'error')
  })
}

async function onDelete(item) {
  const ok = await confirmAction({
    title: '删除视频',
    message: `确定删除「${item.name || item.original_filename || item.code}」？原文件将无法恢复。`,
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
      message: '公开后，任何拿到链接的人都能播放或下载这个视频。',
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
        <p class="eyebrow">{{ isTeam ? '团队媒体库' : '断点续传' }}</p>
        <h2>{{ isTeam ? '团队视频' : '我的视频' }}</h2>
        <p>大文件分片传输，断网或刷新后仍可继续。</p>
      </div>
      <span class="total-badge">{{ total }} 个</span>
    </div>

    <div class="upload-panel video-upload-panel">
      <div class="options">
        <input v-model="uploadName" class="name-input" placeholder="视频命名（可选，多文件自动加序号）" maxlength="255" />
        <select v-model="uploadVisibility" class="vis-select" aria-label="视频可见性">
          <option value="private">私密 · 仅自己/团队可见</option>
          <option value="public">公开 · 任何人可访问</option>
        </select>
      </div>
      <UploadDropzone
        :accept="VIDEO_ACCEPT"
        label="选择视频，或拖拽到这里"
        description="支持 MP4、MOV、WebM、MKV、AVI、MPEG、TS、OGV、3GP、FLV、WMV · 默认最大 2 GB，以服务器配置为准"
        aria-label="选择或拖拽视频上传"
        @files="handleFiles"
      />
    </div>

    <VideoUploadQueue :team-id="teamId" />

    <div class="library-toolbar">
      <div class="search-row">
        <input v-model="query" class="search" type="search" placeholder="搜索名称、文件名或短码" @input="onQueryInput" />
        <button v-if="query" class="clear" aria-label="清除搜索" @click="clearSearch">×</button>
      </div>
    </div>

    <p v-if="loading" class="status loading-state">正在加载视频…</p>
    <p v-else-if="loadError" class="status error">加载失败：{{ loadError }}</p>
    <template v-else>
      <div v-if="videos.length" class="media-grid">
        <VideoCard
          v-for="item in videos"
          :key="`${item.code}-${item.visibility}`"
          :item="item"
          :deletable="canDelete(item)"
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
  </section>
</template>
