<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { deleteImage, listImages, listTeamImages, updateImage, uploadFile } from '../api'
import { confirmAction, toast } from '../stores/feedback'
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
const uploadVisibility = ref('private')
const PAGE_SIZE = 12
let nextId = 1
let searchTimer = null

const isTeam = computed(() => props.teamId !== null && props.teamId !== undefined)
const hasMore = computed(() => images.value.length < total.value)

async function fetchPage(offset) {
  const options = { limit: PAGE_SIZE, offset, q: query.value.trim() }
  return isTeam.value ? listTeamImages(props.teamId, options) : listImages(options)
}

async function loadGallery({ append = false } = {}) {
  if (append) loadingMore.value = true
  else loading.value = true
  loadError.value = ''
  try {
    const response = await fetchPage(append ? images.value.length : 0)
    const incoming = response.items || []
    images.value = append ? [...images.value, ...incoming] : incoming
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
  searchTimer = window.setTimeout(() => loadGallery(), 300)
}

async function handleFiles(files) {
  const list = Array.from(files || [])
  const base = uploadName.value.trim()
  for (let index = 0; index < list.length; index++) {
    const file = list[index]
    const name = base ? (list.length > 1 ? `${base}-${index + 1}` : base) : ''
    const pending = { id: nextId++, file, status: 'uploading', result: null, error: '' }
    uploads.value.unshift(pending)
    try {
      pending.result = await uploadFile(file, {
        name,
        visibility: uploadVisibility.value,
        teamId: props.teamId,
      })
      pending.status = 'done'
      uploads.value = uploads.value.filter(item => item !== pending)
      if (!query.value.trim()) {
        images.value.unshift(pending.result)
        total.value++
      } else {
        await loadGallery()
      }
      toast(`${file.name} 上传成功`, 'success')
    } catch (error) {
      pending.error = error.message
      pending.status = 'error'
      toast(`${file.name} 上传失败：${error.message}`, 'error')
    }
  }
}

function wrapped(item) {
  return { id: `image-${item.id || item.code}`, status: 'done', result: item, file: null }
}

async function onDelete(item) {
  const ok = await confirmAction({
    title: '删除图片',
    message: `确定删除「${item.name || item.original_filename || item.code}」？此操作不可恢复。`,
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
      message: '公开后，任何拿到链接的人都能访问这张图片。',
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

function clearSearch() {
  query.value = ''
  loadGallery()
}

watch(() => props.teamId, () => {
  query.value = ''
  uploads.value = []
  loadGallery()
})

onMounted(loadGallery)
onBeforeUnmount(() => clearTimeout(searchTimer))
</script>

<template>
  <section class="library-view">
    <div class="section-heading">
      <div>
        <p class="eyebrow">{{ isTeam ? '团队媒体库' : '个人媒体库' }}</p>
        <h2>{{ isTeam ? '团队图片' : '我的图片' }}</h2>
        <p>上传原图并获得可分享的短链接。</p>
      </div>
      <span class="total-badge">{{ total }} 张</span>
    </div>

    <div class="upload-panel">
      <div class="options">
        <input v-model="uploadName" class="name-input" type="text" placeholder="图片命名（可选，多张自动加序号）" maxlength="255" />
        <select v-model="uploadVisibility" class="vis-select" aria-label="图片可见性">
          <option value="private">私密 · 仅自己/团队可见</option>
          <option value="public">公开 · 任何人可访问</option>
        </select>
      </div>
      <UploadDropzone
        accept="image/*"
        label="选择图片，或拖拽到这里"
        description="支持 JPG、PNG、GIF、WebP、SVG、AVIF 等常用格式"
        aria-label="选择或拖拽图片上传"
        @files="handleFiles"
      />
    </div>

    <div class="library-toolbar">
      <div class="search-row">
        <input v-model="query" class="search" type="search" placeholder="搜索名称、文件名或短码" @input="onQueryInput" />
        <button v-if="query" class="clear" aria-label="清除搜索" @click="clearSearch">×</button>
      </div>
    </div>

    <div v-if="uploads.length" class="media-grid pending-grid">
      <ImageResult v-for="item in uploads" :key="item.id" :item="item" />
    </div>

    <p v-if="loading" class="status loading-state">正在加载图片…</p>
    <p v-else-if="loadError" class="status error">加载失败：{{ loadError }}</p>
    <template v-else>
      <div v-if="images.length" class="media-grid">
        <ImageResult
          v-for="item in images"
          :key="item.id || item.code"
          :item="wrapped(item)"
          :deletable="canDelete(item)"
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
  </section>
</template>
