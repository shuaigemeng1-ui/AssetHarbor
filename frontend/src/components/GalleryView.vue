<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { deleteImage, fetchPublicConfig, listImages, listTeamImages, updateImage, uploadFile } from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { formatBytes } from '../utils/format'
import CollectionPickerModal from './CollectionPickerModal.vue'
import ImageResult from './ImageResult.vue'
import UploadDropzone from './UploadDropzone.vue'

const props = defineProps({
  user: { type: Object, required: true },
  teamId: { type: [Number, String], default: null },
  canManage: { type: Boolean, default: false },
})

const images = ref([])
const uploads = ref([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const loadError = ref('')
const query = ref('')
const uploadName = ref('')
// Omitted visibility is a fixed public API contract. Users must explicitly
// select "private" when they want restricted access.
const uploadVisibility = ref('public')
const groupTarget = ref(null)
const publicConfig = ref(null)
const PAGE_SIZE = 12
let nextId = 1
let searchTimer = null
let loadGeneration = 0
let publicConfigPromise = null
const uploadQueue = []
const IMAGE_UPLOAD_CONCURRENCY = 3
let activeUploadCount = 0

const isTeam = computed(() => props.teamId !== null && props.teamId !== undefined)
const hasMore = computed(() => images.value.length < total.value)
const groupTargetTeamId = computed(() => groupTarget.value?.team_id ?? props.teamId)
const isGlobalAdmin = computed(() => props.user.role === 'admin' && !isTeam.value)
const uploadDescription = computed(() => {
  const parts = ['支持 JPG、PNG、GIF、WebP、SVG、AVIF 等常用格式']
  if (Number(publicConfig.value?.max_upload_size_mb) > 0) {
    parts.push(`单文件最大 ${publicConfig.value.max_upload_size_mb} MB`)
  }
  const userQuota = Number(publicConfig.value?.user_storage_quota_bytes)
  const teamQuota = Number(publicConfig.value?.team_storage_quota_bytes)
  if (userQuota > 0) parts.push(`用户累计额度 ${formatBytes(userQuota)}`)
  if (isTeam.value && teamQuota > 0) parts.push(`团队累计额度 ${formatBytes(teamQuota)}`)
  return parts.join(' · ')
})

async function loadGallery({ append = false } = {}) {
  const generation = ++loadGeneration
  const scope = String(props.teamId ?? 'personal')
  const requestQuery = query.value.trim()
  const offset = append ? images.value.length : 0
  if (append) loadingMore.value = true
  else loading.value = true
  loadError.value = ''
  try {
    const response = isTeam.value
      ? await listTeamImages(props.teamId, { limit: PAGE_SIZE, offset, q: requestQuery })
      : await listImages({ limit: PAGE_SIZE, offset, q: requestQuery })
    if (generation !== loadGeneration || scope !== String(props.teamId ?? 'personal') || requestQuery !== query.value.trim()) return
    const incoming = response.items || []
    images.value = append ? [...images.value, ...incoming] : incoming
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
  searchTimer = window.setTimeout(() => loadGallery(), 300)
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
  const maxBytes = Number(publicConfig.value?.max_upload_size_mb || 0) * 1024 * 1024
  for (let index = 0; index < list.length; index++) {
    const file = list[index]
    const name = base ? (list.length > 1 ? `${base}-${index + 1}` : base) : ''
    const pendingId = nextId++
    // Keep mutations reactive while the request is in flight. Vue wraps
    // objects inserted into a reactive array, so removing by raw-object
    // identity can leave a completed card stuck in "uploading" forever.
    const oversized = maxBytes > 0 && file.size > maxBytes
    const pending = reactive({
      id: pendingId,
      file,
      name,
      visibility: uploadVisibility.value,
      teamId: props.teamId,
      status: oversized ? 'error' : 'queued',
      result: null,
      error: oversized ? `文件大小超过 ${publicConfig.value.max_upload_size_mb} MB 限制` : '',
      retryable: !oversized,
      queued: false,
    })
    uploads.value.unshift(pending)
    if (!oversized) enqueueUpload(pending)
    else toast(`${file.name} 超过上传大小限制`, 'error')
  }
}

function enqueueUpload(pending) {
  if (pending.queued || pending.status === 'uploading') return
  pending.status = 'queued'
  pending.error = ''
  pending.queued = true
  uploadQueue.push(pending)
  pumpUploadQueue()
}

function pumpUploadQueue() {
  while (activeUploadCount < IMAGE_UPLOAD_CONCURRENCY && uploadQueue.length) {
    const pending = uploadQueue.shift()
    pending.queued = false
    if (!uploads.value.some(item => item.id === pending.id)) continue
    activeUploadCount++
    runUpload(pending).finally(() => {
      activeUploadCount = Math.max(0, activeUploadCount - 1)
      pumpUploadQueue()
    })
  }
}

async function runUpload(pending) {
  pending.status = 'uploading'
  pending.error = ''
  try {
    const result = await uploadFile(pending.file, {
      name: pending.name,
      visibility: pending.visibility,
      teamId: pending.teamId,
    })
    pending.result = result
    pending.status = 'done'
    uploads.value = uploads.value.filter(item => item.id !== pending.id)
    if (!query.value.trim()) {
      images.value.unshift(result)
      total.value++
    } else {
      await loadGallery()
    }
    toast(`${pending.file.name} 上传成功`, 'success')
  } catch (error) {
    pending.error = error.message
    pending.status = 'error'
    toast(`${pending.file.name} 上传失败：${error.message}`, 'error')
  }
}

function retryUpload(pending) {
  if (pending.status === 'error' && pending.retryable !== false) enqueueUpload(pending)
}

function removeUpload(pending) {
  pending.queued = false
  uploads.value = uploads.value.filter(item => item.id !== pending.id)
}

function wrapped(item) {
  return { id: `image-${item.id || item.code}`, status: 'done', result: item, file: null }
}

async function onDelete(item) {
  const ok = await confirmAction({
    title: '删除图片',
    message: `确定删除「${item.name || item.original_filename || item.code}」${isGlobalAdmin.value ? `（属主：${item.owner_username || `用户 #${item.owner_id}`}）` : ''}？此操作不可恢复。`,
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteImage(item.code)
    images.value = images.value.filter(image => image.code !== item.code)
    total.value = Math.max(0, total.value - 1)
    toast('图片已删除', 'success')
  } catch (error) {
    toast(`删除失败：${error.message}`, 'error')
  }
}

async function onToggleVisibility(item) {
  const next = item.visibility === 'private' ? 'public' : 'private'
  if (next === 'public') {
    const ok = await confirmAction({
      title: '公开图片',
      message: `公开后，任何拿到链接的人都能访问这张图片。${isGlobalAdmin.value ? ` 属主：${item.owner_username || `用户 #${item.owner_id}`}。` : ''}`,
      confirmText: '设为公开',
    })
    if (!ok) return
  }
  try {
    const updated = await updateImage(item.code, { visibility: next })
    Object.assign(item, updated)
    toast(next === 'public' ? '图片已公开' : '图片已设为私密', 'success')
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
  loadGallery()
}

watch(() => props.teamId, () => {
  query.value = ''
  uploads.value = []
  loadGallery()
})

onMounted(async () => {
  loadGallery()
  try { await ensurePublicConfig() } catch { /* upload APIs remain usable when optional public config is unavailable */ }
})
onBeforeUnmount(() => clearTimeout(searchTimer))
</script>

<template>
    <section class="library-view">
    <div class="section-heading">
      <div>
        <p class="eyebrow">{{ isTeam ? '团队媒体库' : isGlobalAdmin ? '全站媒体库' : '个人媒体库' }}</p>
        <h2>{{ isTeam ? '团队图片' : isGlobalAdmin ? '全站图片' : '我的图片' }}</h2>
        <p>上传原图并获得可分享的短链接。</p>
      </div>
      <span class="total-badge">{{ total }} 张</span>
    </div>

    <div class="upload-panel">
      <div class="options">
        <input v-model="uploadName" class="name-input" type="text" placeholder="图片命名（可选，多张自动加序号）" maxlength="255" aria-label="图片显示名称" />
        <select v-model="uploadVisibility" class="vis-select" aria-label="图片可见性">
          <option value="private">私密 · 仅自己/团队可见</option>
          <option value="public">公开 · 任何人可访问</option>
        </select>
      </div>
      <UploadDropzone
        accept="image/*"
        label="选择图片，或拖拽到这里"
        :description="uploadDescription"
        aria-label="选择或拖拽图片上传"
        @files="handleFiles"
      />
    </div>

    <div class="library-toolbar">
      <div class="search-row">
        <input v-model="query" class="search" type="search" placeholder="搜索名称、文件名或短码" aria-label="搜索图片" @input="onQueryInput" />
        <button v-if="query" class="clear" aria-label="清除搜索" @click="clearSearch">×</button>
      </div>
    </div>

    <div v-if="uploads.length" class="media-grid pending-grid">
      <ImageResult v-for="item in uploads" :key="item.id" :item="item" @retry="retryUpload(item)" @remove-pending="removeUpload(item)" />
    </div>

    <p v-if="loading" class="status loading-state" aria-live="polite">正在加载图片…</p>
    <div v-else-if="loadError" class="status error" role="alert">加载失败：{{ loadError }} <button class="secondary" @click="loadGallery()">重试</button></div>
    <template v-else>
      <div v-if="images.length" class="media-grid">
        <ImageResult
          v-for="item in images"
          :key="item.id || item.code"
          :item="wrapped(item)"
          :deletable="canDelete(item)"
          :show-scope="isGlobalAdmin"
          :groupable="canGroup(item)"
          @add-to-group="groupTarget = item"
          @delete="onDelete(item)"
          @toggle-visibility="onToggleVisibility(item)"
        />
      </div>
      <div v-else class="empty-state">
        <div class="empty-icon">◇</div>
        <h3>{{ query ? '没有找到匹配图片' : '这里还没有图片' }}</h3>
        <p>{{ query ? '换个关键词试试看。' : '从上方上传第一张图片吧。' }}</p>
      </div>
      <div v-if="hasMore" class="load-more-wrap">
        <button class="secondary" :disabled="loadingMore" @click="loadGallery({ append: true })">
          {{ loadingMore ? '加载中…' : `加载更多（还有 ${total - images.length} 张）` }}
        </button>
      </div>
    </template>

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
