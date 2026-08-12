<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getVideoSignedLink, updateVideo } from '../api'
import { toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import { formatBytes, formatDate } from '../utils/format'
import BaseModal from './BaseModal.vue'

const props = defineProps({
  item: { type: Object, required: true },
  deletable: { type: Boolean, default: false },
  editable: { type: Boolean, default: false },
  groupable: { type: Boolean, default: false },
  removable: { type: Boolean, default: false },
  showScope: { type: Boolean, default: false },
})

const emit = defineEmits(['play', 'delete', 'toggle-visibility', 'add-to-group', 'remove'])
const root = ref(null)
const video = ref(null)
const inView = ref(false)
const signedUrl = ref('')
const loadingLink = ref(false)
const previewFailed = ref(false)
const copied = ref(false)
const signedRefreshAttempted = ref(false)
const editing = ref(false)
const editName = ref('')
const editSaving = ref(false)
const editError = ref('')
let observer

const isPrivate = computed(() => props.item.visibility === 'private')
const streamUrl = computed(() => isPrivate.value ? signedUrl.value : props.item.url)
const downloadUrl = computed(() => {
  if (!streamUrl.value) return ''
  return `${streamUrl.value}${streamUrl.value.includes('?') ? '&' : '?'}download=1`
})

async function resolveLink(force = false) {
  if (!isPrivate.value) return props.item.url
  if (!force && (signedUrl.value || loadingLink.value)) return signedUrl.value
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
  signedRefreshAttempted.value = false
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

async function onPreviewError() {
  if (isPrivate.value && !signedRefreshAttempted.value) {
    signedRefreshAttempted.value = true
    previewFailed.value = false
    await resolveLink(true)
    video.value?.load?.()
    return
  }
  previewFailed.value = true
}

async function retryPreview() {
  previewFailed.value = false
  signedRefreshAttempted.value = false
  if (isPrivate.value) await resolveLink(true)
  await nextTick()
  video.value?.load?.()
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

function openEditor() {
  editName.value = props.item.name || props.item.original_filename || ''
  editError.value = ''
  editing.value = true
}

async function saveName() {
  const name = editName.value.trim()
  if (!name) {
    editError.value = '名称不能为空'
    return
  }
  editSaving.value = true
  editError.value = ''
  try {
    const updated = await updateVideo(props.item.code, { name })
    Object.assign(props.item, updated)
    editing.value = false
    toast('视频名称已更新', 'success')
  } catch (error) {
    editError.value = error.message
  } finally {
    editSaving.value = false
  }
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
        @error="onPreviewError"
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
          <p v-if="showScope" class="card-scope">{{ item.team_id ? `团队 #${item.team_id}` : '个人空间' }} · {{ item.owner_username || `用户 #${item.owner_id}` }}</p>
          <p class="card-date">{{ formatDate(item.created_at) }}</p>
        </div>
      </div>
      <p v-if="previewFailed" class="codec-hint">当前浏览器无法解码此格式，可直接下载原文件。</p>
      <div class="card-actions">
        <button v-if="previewFailed" class="ghost" :disabled="loadingLink" @click="retryPreview">重试预览</button>
        <button class="ghost" :disabled="loadingLink" @click="copyLink">{{ copied ? '已复制' : '复制链接' }}</button>
        <a v-if="previewFailed && downloadUrl" class="ghost button-link" :href="downloadUrl">下载</a>
        <button v-if="groupable" class="ghost" @click="emit('add-to-group')">加入分组</button>
        <button v-if="removable" class="ghost danger" @click="emit('remove')">移出分组</button>
        <button v-if="editable || deletable" class="ghost" @click="openEditor">重命名</button>
        <button v-if="deletable" class="ghost" @click="emit('toggle-visibility')">{{ isPrivate ? '设为公开' : '设为私密' }}</button>
        <button v-if="deletable" class="ghost danger" @click="emit('delete')">删除</button>
      </div>
    </div>

    <BaseModal v-if="editing" title="重命名视频" description="仅修改媒体库中的显示名称，原始文件名保持不变。" labelled-by="rename-video-title" @close="editing = false">
      <form id="rename-video-form" class="rename-form" @submit.prevent="saveName">
        <label for="rename-video-input">显示名称</label>
        <input id="rename-video-input" v-model="editName" autofocus maxlength="255" />
        <p v-if="editError" class="error-text" role="alert">{{ editError }}</p>
      </form>
      <template #footer>
        <button class="ghost" type="button" :disabled="editSaving" @click="editing = false">取消</button>
        <button class="primary" type="submit" form="rename-video-form" :disabled="editSaving || !editName.trim()">{{ editSaving ? '保存中…' : '保存' }}</button>
      </template>
    </BaseModal>
  </article>
</template>

<style scoped>
.rename-form { display: grid; gap: 7px; }
.rename-form label { font-size: 12px; font-weight: 650; }
.rename-form input { min-height: 42px; border: 1px solid var(--border); border-radius: 10px; padding: 8px 11px; outline: 0; }
.rename-form input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgb(37 99 235 / 10%); }
.rename-form p { margin: 4px 0 0; font-size: 12px; }
</style>
