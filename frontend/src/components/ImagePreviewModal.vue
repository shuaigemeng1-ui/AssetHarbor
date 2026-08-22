<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getSignedLink } from '../api'
import { formatBytes } from '../utils/format'
import { downloadMediaFile } from '../utils/download'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  item: { type: Object, required: true },
  hasPrev: { type: Boolean, default: false },
  hasNext: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'prev', 'next'])

const zoom = ref(1)
const rotation = ref(0)
const posX = ref(0)
const posY = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const signedUrl = ref('')
const loading = ref(false)
const loadFailed = ref(false)

const isPrivate = computed(() => props.item.visibility === 'private')
const displayName = computed(() => (
  props.item.name
  || props.item.original_filename
  || (isPdf.value ? '未命名文档' : '未命名图片')
))
const isPdf = computed(() => (
  props.item.content_type === 'application/pdf'
  || String(props.item.name || props.item.original_filename || '').toLowerCase().endsWith('.pdf')
))

const activeUrl = computed(() => {
  if (isPrivate.value) return signedUrl.value
  return props.item.url || ''
})

async function loadSignedSource() {
  if (!isPrivate.value || !props.item.code) return
  loading.value = true
  loadFailed.value = false
  try {
    const res = await getSignedLink(props.item.code, 86400)
    signedUrl.value = res.url || ''
  } catch {
    loadFailed.value = true
  } finally {
    loading.value = false
  }
}

watch(() => props.item.code, () => {
  zoom.value = 1
  rotation.value = 0
  posX.value = 0
  posY.value = 0
  if (isPrivate.value) {
    loadSignedSource()
  } else {
    signedUrl.value = ''
  }
}, { immediate: true })

function zoomIn() {
  zoom.value = Math.min(5, Number((zoom.value + 0.25).toFixed(2)))
}

function zoomOut() {
  zoom.value = Math.max(0.2, Number((zoom.value - 0.25).toFixed(2)))
}

function resetZoom() {
  zoom.value = 1
  rotation.value = 0
  posX.value = 0
  posY.value = 0
}

function rotate() {
  rotation.value = (rotation.value + 90) % 360
}

function startDrag(e) {
  if (zoom.value <= 1 && rotation.value === 0) return
  isDragging.value = true
  dragStartX.value = e.clientX - posX.value
  dragStartY.value = e.clientY - posY.value
}

function onDrag(e) {
  if (!isDragging.value) return
  posX.value = e.clientX - dragStartX.value
  posY.value = e.clientY - dragStartY.value
}

function stopDrag() {
  isDragging.value = false
}

function onWheel(e) {
  if (isPdf.value) return
  e.preventDefault()
  if (e.deltaY < 0) zoomIn()
  else zoomOut()
}

function triggerDownload() {
  downloadMediaFile(activeUrl.value, displayName.value)
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  } else if (e.key === 'ArrowLeft' && props.hasPrev) {
    e.preventDefault()
    emit('prev')
  } else if (e.key === 'ArrowRight' && props.hasNext) {
    e.preventDefault()
    emit('next')
  } else if (e.key === '+' || e.key === '=') {
    e.preventDefault()
    zoomIn()
  } else if (e.key === '-' || e.key === '_') {
    e.preventDefault()
    zoomOut()
  } else if (e.key === '0') {
    e.preventDefault()
    resetZoom()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="image-preview-overlay" role="dialog" aria-modal="true" :aria-label="displayName" @click.self="emit('close')">
    <header class="preview-header">
      <div class="header-info">
        <AppIcon :name="isPdf ? 'pdf' : 'image'" size="20" class="header-icon" />
        <div class="header-text">
          <h2 :title="displayName">{{ displayName }}</h2>
          <span>{{ formatBytes(item.size) }} · {{ item.content_type }}</span>
        </div>
      </div>

      <div class="header-actions">
        <template v-if="!isPdf">
          <button class="action-btn" type="button" title="缩小 (-)" @click="zoomOut">
            <AppIcon name="zoomOut" size="18" />
          </button>
          <button class="action-btn zoom-indicator" type="button" title="重置缩放 (0)" @click="resetZoom">
            {{ Math.round(zoom * 100) }}%
          </button>
          <button class="action-btn" type="button" title="放大 (+)" @click="zoomIn">
            <AppIcon name="zoomIn" size="18" />
          </button>
          <button class="action-btn" type="button" title="旋转" @click="rotate">
            <AppIcon name="zoomReset" size="18" />
          </button>
        </template>
        <button class="action-btn download-btn" type="button" title="下载原文件" @click="triggerDownload">
          <AppIcon name="download" size="18" />
          <span>下载</span>
        </button>
        <button class="action-btn close-btn" type="button" title="关闭 (Esc)" @click="emit('close')">
          <AppIcon name="close" size="20" />
        </button>
      </div>
    </header>

    <div
      class="preview-stage"
      @wheel="onWheel"
      @mousedown="startDrag"
      @mousemove="onDrag"
      @mouseup="stopDrag"
      @mouseleave="stopDrag"
    >
      <div v-if="isPdf" class="pdf-stage">
        <iframe
          v-if="activeUrl && !loadFailed"
          :src="activeUrl"
          :title="displayName"
          class="pdf-frame"
        />
        <div v-else-if="loading" class="stage-status">
          <AppIcon name="retry" size="24" class="spin-icon" />
          <span>正在加载 PDF 文档…</span>
        </div>
        <div v-else class="stage-status">
          <AppIcon name="alert" size="24" />
          <span>无法加载 PDF 文档</span>
        </div>
      </div>

      <div v-else class="image-stage">
        <img
          v-if="activeUrl && !loadFailed"
          :src="activeUrl"
          :alt="displayName"
          class="preview-image"
          :style="{
            transform: `translate(${posX}px, ${posY}px) scale(${zoom}) rotate(${rotation}deg)`,
            cursor: zoom > 1 || rotation !== 0 ? (isDragging ? 'grabbing' : 'grab') : 'default',
          }"
          draggable="false"
          @error="loadFailed = true"
        />
        <div v-else-if="loading" class="stage-status">
          <AppIcon name="retry" size="24" class="spin-icon" />
          <span>正在加载图片…</span>
        </div>
        <div v-else class="stage-status">
          <AppIcon name="alert" size="24" />
          <span>图片预览加载失败</span>
        </div>
      </div>

      <button
        v-if="hasPrev"
        class="nav-btn prev-btn"
        type="button"
        title="上一项 (←)"
        @click.stop="emit('prev')"
      >
        <AppIcon name="chevron" size="24" class="rotate-180" />
      </button>
      <button
        v-if="hasNext"
        class="nav-btn next-btn"
        type="button"
        title="下一项 (→)"
        @click.stop="emit('next')"
      >
        <AppIcon name="chevron" size="24" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.image-preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  background: rgba(10, 10, 10, 0.92);
  backdrop-filter: blur(8px);
  color: #fff;
}

.preview-header {
  height: 56px;
  flex: 0 0 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: rgba(20, 20, 20, 0.85);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  z-index: 10;
}

.header-info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.header-icon {
  color: #a1a1aa;
}

.header-text {
  min-width: 0;
}

.header-text h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #fafafa;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-text span {
  font-size: 12px;
  color: #a1a1aa;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
  color: #e4e4e7;
  font-size: 13px;
  cursor: pointer;
  transition: all 120ms ease;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.3);
}

.zoom-indicator {
  min-width: 58px;
  font-family: ui-monospace, monospace;
}

.download-btn {
  background: #2563eb;
  border-color: #3b82f6;
  color: #fff;
}

.download-btn:hover {
  background: #1d4ed8;
  border-color: #2563eb;
}

.close-btn {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.4);
  color: #fca5a5;
}

.close-btn:hover {
  background: rgba(239, 68, 68, 0.4);
  color: #fff;
}

.preview-stage {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-stage {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-image {
  max-width: 90vw;
  max-height: 85vh;
  object-fit: contain;
  transition: transform 60ms linear;
  user-select: none;
}

.pdf-stage {
  width: 90vw;
  height: 88vh;
  max-width: 1200px;
  border-radius: 8px;
  overflow: hidden;
  background: #18181b;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border: 0;
}

.stage-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #a1a1aa;
  font-size: 14px;
}

.nav-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  cursor: pointer;
  transition: all 120ms ease;
  z-index: 20;
}

.nav-btn:hover {
  background: rgba(0, 0, 0, 0.85);
  border-color: rgba(255, 255, 255, 0.5);
  transform: translateY(-50%) scale(1.08);
}

.prev-btn { left: 24px; }
.next-btn { right: 24px; }

.rotate-180 { transform: rotate(180deg); }

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .header-actions span { display: none; }
  .pdf-stage { width: 98vw; height: 85vh; }
  .prev-btn { left: 8px; }
  .next-btn { right: 8px; }
}
</style>
