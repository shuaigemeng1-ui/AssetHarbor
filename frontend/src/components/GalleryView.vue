<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { deleteImage, fetchPublicConfig, listImages, listTeamImages, updateImage, uploadFile } from '../api'
import { confirmAction, toast } from '../stores/feedback'
import { acquireModalLock, releaseModalLock } from '../stores/modalLock'
import { formatBytes } from '../utils/format'
import { WORKSPACE_DRAWER_MAX_WIDTH, WORKSPACE_DRAWER_MEDIA_QUERY } from '../utils/layout'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'
import ImageInspector from './ImageInspector.vue'
import ImagePreviewModal from './ImagePreviewModal.vue'
import ImageResult from './ImageResult.vue'
import UploadDropzone from './UploadDropzone.vue'

const props = defineProps({
  user: { type: Object, required: true },
  teamId: { type: [Number, String], default: null },
  canManage: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
  openUpload: { type: Boolean, default: false },
  scope: {
    type: String,
    default: 'mine',
    validator: value => ['mine', 'all'].includes(value),
  },
})

const emit = defineEmits(['upload-request-consumed'])

const images = ref([])
const uploads = ref([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const loadError = ref('')
const query = ref('')
const uploadName = ref('')
const uploadOpen = ref(props.openUpload)
const selectedImage = ref(null)
const inspectorOpen = ref(false)
const inspectorPanel = ref(null)
const isNarrowLayout = ref(typeof window !== 'undefined' && window.innerWidth <= WORKSPACE_DRAWER_MAX_WIDTH)
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
const publicConfig = ref(null)
const PAGE_SIZE = 12
let nextId = 1
let searchTimer = null
let loadGeneration = 0
let publicConfigPromise = null
let layoutMedia = null
let drawerLocked = false
let previousInspectorFocus = null
const uploadQueue = []
const IMAGE_UPLOAD_CONCURRENCY = 3
let activeUploadCount = 0

const isTeam = computed(() => props.teamId !== null && props.teamId !== undefined)
const hasMore = computed(() => images.value.length < total.value)
const isGlobalAdmin = computed(() => props.user.role === 'admin' && !isTeam.value && props.scope === 'all')
const inspectorDrawerMode = computed(() => props.embedded || isNarrowLayout.value)
const drawerActive = computed(() => inspectorOpen.value && inspectorDrawerMode.value)
const inspectorHidden = computed(() => inspectorDrawerMode.value && !inspectorOpen.value)
const uploadButtonLabel = computed(() => (
  props.user.role === 'admin' && !isTeam.value ? '上传到我的个人空间' : '上传'
))
const uploadModalTitle = computed(() => (
  props.user.role === 'admin' && !isTeam.value ? '上传图片与文档到我的个人空间' : '上传图片与文档'
))
const uploadModalDescription = computed(() => (
  isTeam.value
    ? '图片与文档会保存到当前团队空间，并生成可分享的短链接。'
    : '图片与文档会保存到当前账号的个人空间，并生成可分享的短链接。'
))
const uploadDescription = computed(() => {
  const parts = ['支持 JPG、PNG、GIF、WebP、SVG、AVIF、PDF 等常用格式']
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
  const requestScope = isTeam.value ? `team:${props.teamId}` : props.scope
  const requestQuery = query.value.trim()
  const offset = append ? images.value.length : 0
  if (append) loadingMore.value = true
  else loading.value = true
  loadError.value = ''
  try {
    const response = isTeam.value
      ? await listTeamImages(props.teamId, { limit: PAGE_SIZE, offset, q: requestQuery })
      : await listImages({ limit: PAGE_SIZE, offset, q: requestQuery, scope: props.scope })
    const currentScope = isTeam.value ? `team:${props.teamId}` : props.scope
    if (generation !== loadGeneration || requestScope !== currentScope || requestQuery !== query.value.trim()) return
    const incoming = response.items || []
    images.value = append ? [...images.value, ...incoming] : incoming
    total.value = Number(response.total || 0)
    if (!append || !selectedImage.value) {
      selectedImage.value = props.embedded ? null : (incoming[0] || null)
      if (!selectedImage.value) inspectorOpen.value = false
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
    const response = await uploadFile(pending.file, {
      name: pending.name,
      visibility: pending.visibility,
      teamId: pending.teamId,
    })
    const result = {
      ...response,
      original_filename: response.original_filename || pending.file.name,
    }
    pending.result = result
    pending.status = 'done'
    uploads.value = uploads.value.filter(item => item.id !== pending.id)
    if (!query.value.trim()) {
      images.value.unshift(result)
      total.value++
      selectedImage.value = props.embedded ? null : result
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

async function selectImage(item) {
  selectedImage.value = item
  inspectorOpen.value = true
}

function closeInspector() {
  inspectorOpen.value = false
}

const previewModalOpen = ref(false)
const previewTargetItem = ref(null)

const previewIndex = computed(() => {
  if (!previewTargetItem.value) return -1
  return images.value.findIndex(img => img.code === previewTargetItem.value.code)
})
const hasPrevPreview = computed(() => previewIndex.value > 0)
const hasNextPreview = computed(() => previewIndex.value !== -1 && previewIndex.value < images.value.length - 1)

function openPreview(item) {
  previewTargetItem.value = item
  previewModalOpen.value = true
}

function closePreview() {
  previewModalOpen.value = false
  previewTargetItem.value = null
}

function onPrevPreview() {
  if (hasPrevPreview.value) {
    previewTargetItem.value = images.value[previewIndex.value - 1]
  }
}

function onNextPreview() {
  if (hasNextPreview.value) {
    previewTargetItem.value = images.value[previewIndex.value + 1]
  }
}

function isPdfItem(item) {
  return item?.content_type === 'application/pdf'
    || String(item?.name || item?.original_filename || '').toLowerCase().endsWith('.pdf')
}

function onGlobalPaste(event) {
  const target = event.target
  const isInput = target && (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT' ||
    target.isContentEditable
  )
  const clipboardFiles = Array.from(event.clipboardData?.files || [])
  if (!clipboardFiles.length) {
    const items = Array.from(event.clipboardData?.items || [])
    for (const item of items) {
      if (item.kind === 'file') {
        const file = item.getAsFile()
        if (file) clipboardFiles.push(file)
      }
    }
  }
  if (!clipboardFiles.length) return
  if (isInput && !clipboardFiles.some(f => f.type.startsWith('image/') || f.type === 'application/pdf')) {
    return
  }
  event.preventDefault()
  handleFiles(clipboardFiles)
  toast(`已从剪贴板接收 ${clipboardFiles.length} 个文件并开始上传`, 'info')
}

function onGalleryKeydown(event) {
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

  // Handle arrow navigation between media cards when not typing and no modal is blocking
  if (!hasModal && !isTyping && images.value.length > 1 && selectedImage.value) {
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      const currentIndex = images.value.findIndex(img => img.code === selectedImage.value?.code)
      if (currentIndex !== -1 && currentIndex < images.value.length - 1) {
        event.preventDefault()
        selectImage(images.value[currentIndex + 1])
        return
      }
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      const currentIndex = images.value.findIndex(img => img.code === selectedImage.value?.code)
      if (currentIndex > 0) {
        event.preventDefault()
        selectImage(images.value[currentIndex - 1])
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

async function onDelete(item) {
  const isPdf = isPdfItem(item)
  const kindLabel = isPdf ? '文档' : '图片'
  const ok = await confirmAction({
    title: `删除${kindLabel}`,
    message: `确定删除「${item.name || item.original_filename || item.code}」${isGlobalAdmin.value ? `（属主：${item.owner_username || `用户 #${item.owner_id}`}）` : ''}？此操作不可恢复。`,
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteImage(item.code)
    const deletedIndex = images.value.findIndex(image => image.code === item.code)
    images.value = images.value.filter(image => image.code !== item.code)
    total.value = Math.max(0, total.value - 1)
    if (selectedImage.value?.code === item.code) {
      selectedImage.value = images.value[deletedIndex] || images.value[deletedIndex - 1] || null
      if (!selectedImage.value) inspectorOpen.value = false
    }
    toast(`${kindLabel}已删除`, 'success')
  } catch (error) {
    toast(`删除失败：${error.message}`, 'error')
  }
}

async function onToggleVisibility(item) {
  const isPdf = isPdfItem(item)
  const kindLabel = isPdf ? '文档' : '图片'
  const next = item.visibility === 'private' ? 'public' : 'private'
  if (next === 'public') {
    const ok = await confirmAction({
      title: `公开${kindLabel}`,
      message: `公开后，任何拿到链接的人都能访问这份${kindLabel}。${isGlobalAdmin.value ? ` 属主：${item.owner_username || `用户 #${item.owner_id}`}。` : ''}`,
      confirmText: '设为公开',
    })
    if (!ok) return
  }
  try {
    const updated = await updateImage(item.code, { visibility: next })
    Object.assign(item, updated)
    toast(next === 'public' ? `${kindLabel}已公开` : `${kindLabel}已设为私密`, 'success')
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

watch(() => [props.teamId, props.scope], () => {
  query.value = ''
  uploads.value = []
  selectedImage.value = null
  inspectorOpen.value = false
  uploadOpen.value = false
  loadGallery()
})

watch(() => props.openUpload, next => {
  if (next) {
    uploadOpen.value = true
    emit('upload-request-consumed')
  }
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

onMounted(async () => {
  window.addEventListener('keydown', onGalleryKeydown)
  window.addEventListener('paste', onGlobalPaste)
  if (window.matchMedia) {
    layoutMedia = window.matchMedia(WORKSPACE_DRAWER_MEDIA_QUERY)
    isNarrowLayout.value = layoutMedia.matches
    layoutMedia.onchange = event => { isNarrowLayout.value = event.matches }
  }
  if (props.openUpload) emit('upload-request-consumed')
  loadGallery()
  try { await ensurePublicConfig() } catch { /* upload APIs remain usable when optional public config is unavailable */ }
})
onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  window.removeEventListener('keydown', onGalleryKeydown)
  window.removeEventListener('paste', onGlobalPaste)
  if (layoutMedia) layoutMedia.onchange = null
  if (drawerLocked) {
    releaseModalLock()
    drawerLocked = false
  }
})
</script>

<template>
  <section class="asset-library" :class="{ 'asset-library-embedded': embedded, 'inspector-open': inspectorOpen }">
    <div class="asset-library-main" :inert="drawerActive ? '' : undefined">
      <header v-if="!embedded" class="library-heading">
        <div class="library-title">
          <p>{{ isTeam ? '团队媒体库' : isGlobalAdmin ? '全站媒体库' : '个人媒体库' }}</p>
          <div>
            <h1>{{ isTeam ? '团队图片' : isGlobalAdmin ? '全站图片' : '我的图片' }}</h1>
            <span>{{ total }} 张</span>
          </div>
        </div>
      </header>

      <div class="library-toolbar">
        <div class="search-row">
          <AppIcon name="search" size="17" />
          <input v-model="query" class="search" type="search" placeholder="搜索名称、文件名或短码" aria-label="搜索图片" @input="onQueryInput" />
          <button v-if="query" class="clear" type="button" aria-label="清除搜索" @click="clearSearch">
            <AppIcon name="close" size="15" />
          </button>
        </div>
        <button v-if="uploads.length" class="upload-activity" type="button" @click="uploadOpen = true">
          {{ uploads.length }} 个上传任务
        </button>
        <button class="primary library-upload-button" type="button" @click="uploadOpen = true">
          <AppIcon name="upload" size="16" />
          {{ uploadButtonLabel }}
        </button>
      </div>

      <p v-if="loading" class="status loading-state" aria-live="polite">正在加载图片…</p>
      <div v-else-if="loadError" class="status error" role="alert">
        <span>加载失败：{{ loadError }}</span>
        <button class="secondary" @click="loadGallery()">重试</button>
      </div>
      <template v-else>
        <div v-if="images.length" class="media-grid asset-grid" role="list" aria-label="图片列表">
          <ImageResult
            v-for="item in images"
            :key="item.id || item.code"
            :item="wrapped(item)"
            selectable
            :selected="selectedImage?.code === item.code"
            @select="selectImage(item)"
            @preview="openPreview(item)"
          />
        </div>
        <div v-else class="empty-state">
          <div class="empty-icon"><AppIcon name="image" size="22" /></div>
          <h3>{{ query ? '没有找到匹配图片' : '这里还没有图片' }}</h3>
          <p>{{ query ? '换个关键词试试看。' : '上传第一张图片，开始建立媒体库。' }}</p>
          <button v-if="!query && !embedded" class="primary" type="button" @click="uploadOpen = true">{{ uploadButtonLabel }}</button>
        </div>
        <div v-if="hasMore" class="load-more-wrap">
          <button class="secondary" :disabled="loadingMore" @click="loadGallery({ append: true })">
            {{ loadingMore ? '加载中…' : `加载更多（还有 ${total - images.length} 张）` }}
          </button>
        </div>
      </template>
    </div>

    <ImageInspector
      v-if="selectedImage"
      ref="inspectorPanel"
      tabindex="-1"
      :role="drawerActive ? 'dialog' : undefined"
      :aria-modal="drawerActive ? 'true' : undefined"
      :aria-hidden="inspectorHidden ? 'true' : undefined"
      :inert="inspectorHidden ? '' : undefined"
      :item="selectedImage"
      :user="user"
      :can-manage="canDelete(selectedImage)"
      :can-manage-groups="canManage || user.role === 'admin'"
      :is-global-admin="isGlobalAdmin"
      :team-id="selectedImage.team_id ?? teamId"
      :groupable="canGroup(selectedImage)"
      @delete="onDelete(selectedImage)"
      @toggle-visibility="onToggleVisibility(selectedImage)"
      @updated="Object.assign(selectedImage, $event)"
      @preview="openPreview(selectedImage)"
    />
    <aside
      v-else
      class="image-inspector image-inspector-empty"
      aria-label="图片详情"
      :aria-hidden="inspectorHidden ? 'true' : undefined"
      :inert="inspectorHidden ? '' : undefined"
    >
      <AppIcon name="image" size="24" />
      <strong>图片详情</strong>
      <p>{{ loading ? '正在加载媒体库…' : '选择一张图片查看详情' }}</p>
    </aside>
    <button v-if="inspectorOpen" class="inspector-mobile-backdrop" type="button" tabindex="-1" aria-label="关闭图片详情" @click="closeInspector" />
    <button v-if="inspectorOpen" class="inspector-mobile-close" type="button" aria-label="关闭图片详情" @click="closeInspector">
      <AppIcon name="close" size="17" />
    </button>

    <BaseModal
      v-if="uploadOpen"
      :title="uploadModalTitle"
      :description="uploadModalDescription"
      labelled-by="image-upload-title"
      wide
      @close="uploadOpen = false"
    >
      <div class="image-upload-dialog">
        <div class="upload-settings">
          <label>
            <span>图片命名</span>
            <input v-model="uploadName" class="name-input" type="text" placeholder="可选，多张图片会自动添加序号" maxlength="255" />
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
          accept="image/*,application/pdf,.pdf"
          label="选择图片或 PDF，或拖拽到这里"
          :description="uploadDescription"
          aria-label="选择或拖拽图片或 PDF 上传"
          @files="handleFiles"
        />
        <section v-if="uploads.length" class="upload-task-section" aria-label="上传任务">
          <header><strong>上传任务</strong><span>{{ uploads.length }} 个</span></header>
          <div class="media-grid pending-grid">
            <ImageResult
              v-for="item in uploads"
              :key="item.id"
              :item="item"
              @retry="retryUpload(item)"
              @remove-pending="removeUpload(item)"
            />
          </div>
        </section>
      </div>
      <template #footer>
        <button class="ghost" type="button" @click="uploadOpen = false">关闭</button>
      </template>
    </BaseModal>

    <ImagePreviewModal
      v-if="previewModalOpen && previewTargetItem"
      :item="previewTargetItem"
      :has-prev="hasPrevPreview"
      :has-next="hasNextPreview"
      @close="closePreview"
      @prev="onPrevPreview"
      @next="onNextPreview"
    />
  </section>
</template>
