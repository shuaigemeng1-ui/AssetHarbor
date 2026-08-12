<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getVideoSignedLink } from '../api'
import { toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import { formatBytes, formatDate } from '../utils/format'

const props = defineProps({
  item: { type: Object, required: true },
  deletable: { type: Boolean, default: false },
})

const emit = defineEmits(['play', 'delete', 'toggle-visibility'])
const root = ref(null)
const video = ref(null)
const inView = ref(false)
const signedUrl = ref('')
const loadingLink = ref(false)
const previewFailed = ref(false)
const copied = ref(false)
let observer

const isPrivate = computed(() => props.item.visibility === 'private')
const streamUrl = computed(() => isPrivate.value ? signedUrl.value : props.item.url)
const downloadUrl = computed(() => {
  if (!streamUrl.value) return ''
  return `${streamUrl.value}${streamUrl.value.includes('?') ? '&' : '?'}download=1`
})

async function resolveLink() {
  if (!isPrivate.value) return props.item.url
  if (signedUrl.value || loadingLink.value) return signedUrl.value
  loadingLink.value = true
  try {
    signedUrl.value = (await getVideoSignedLink(props.item.code)).url
  } catch {
    previewFailed.value = true
  } finally {
    loadingLink.value = false
  }
  return signedUrl.value
}

watch(() => [props.item.code, props.item.visibility], () => {
  signedUrl.value = ''
  previewFailed.value = false
  if (inView.value) resolveLink()
})

onMounted(() => {
  if (!('IntersectionObserver' in window)) {
    inView.value = true
    resolveLink()
    return
  }
  observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      inView.value = true
      resolveLink()
      observer?.disconnect()
    }
  }, { rootMargin: '160px' })
  observer.observe(root.value)
})

onBeforeUnmount(() => observer?.disconnect())

function revealFirstFrame() {
  if (!video.value || !Number.isFinite(video.value.duration) || video.value.duration <= 0) return
  try { video.value.currentTime = Math.min(0.1, video.value.duration / 10) } catch { /* codec may reject seeking */ }
}

async function copyLink() {
  let url = streamUrl.value
  if (isPrivate.value) {
    try {
      signedUrl.value = (await getVideoSignedLink(props.item.code)).url
      url = signedUrl.value
    } catch {
      url = ''
    }
  } else if (!url) {
    url = await resolveLink()
  }
  if (!url || !await copyText(url)) {
    toast('复制失败，请稍后重试', 'error')
    return
  }
  copied.value = true
  toast(isPrivate.value ? '限时签名链接已复制' : '视频链接已复制', 'success')
  window.setTimeout(() => (copied.value = false), 1200)
}
</script>

<template>
  <article ref="root" class="media-card video-card">
    <button class="media-preview video-preview" :disabled="previewFailed || !streamUrl" :aria-label="`播放 ${item.name || item.original_filename}`" @click="emit('play', item)">
      <video
        v-if="inView && streamUrl && !previewFailed"
        ref="video"
        :src="streamUrl"
        muted
        playsinline
        preload="metadata"
        @loadedmetadata="revealFirstFrame"
        @error="previewFailed = true"
      ></video>
      <div v-else class="preview-placeholder video-placeholder">
        <span>{{ previewFailed ? '↓' : '▶' }}</span>
        <small>{{ previewFailed ? '浏览器无法预览' : loadingLink ? '正在获取预览' : '视频' }}</small>
      </div>
      <span v-if="!previewFailed && streamUrl" class="play-badge" aria-hidden="true">▶</span>
      <span class="visibility-pill" :class="item.visibility">{{ isPrivate ? '私密' : '公开' }}</span>
    </button>

    <div class="media-card-body">
      <div class="media-card-heading">
        <div>
          <h3>{{ item.name || item.original_filename || '未命名视频' }}</h3>
          <p>{{ formatBytes(item.size) }} · {{ item.content_type }} · {{ item.code }}</p>
          <p class="card-date">{{ formatDate(item.created_at) }}</p>
        </div>
      </div>
      <p v-if="previewFailed" class="codec-hint">当前浏览器无法解码此格式，可直接下载原文件。</p>
      <div class="card-actions">
        <button class="ghost" :disabled="loadingLink" @click="copyLink">{{ copied ? '已复制' : '复制链接' }}</button>
        <a v-if="previewFailed && downloadUrl" class="ghost button-link" :href="downloadUrl">下载</a>
        <button v-if="deletable" class="ghost" @click="emit('toggle-visibility')">{{ isPrivate ? '设为公开' : '设为私密' }}</button>
        <button v-if="deletable" class="ghost danger" @click="emit('delete')">删除</button>
      </div>
    </div>
  </article>
</template>
