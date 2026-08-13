<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getVideoSignedLink, updateVideo } from '../api'
import { toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import { formatBytes, formatDate } from '../utils/format'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'

const props = defineProps({
  item: { type: Object, required: true },
  deletable: { type: Boolean, default: false },
  editable: { type: Boolean, default: false },
  groupable: { type: Boolean, default: false },
  removable: { type: Boolean, default: false },
  showScope: { type: Boolean, default: false },
  selectable: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
})

const emit = defineEmits(['play', 'delete', 'toggle-visibility', 'add-to-group', 'remove', 'select'])
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
const displayName = computed(() => props.item.name || props.item.original_filename || '未命名视频')
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

function selectCard() {
  if (!props.selectable) return
  emit('select', props.item)
}

function activatePreview() {
  if (props.selectable) selectCard()
  else emit('play', props.item)
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
  <article
    ref="root"
    class="media-card video-card"
    :class="{ selectable, selected: selectable && selected }"
    :role="selectable ? 'button' : undefined"
    :tabindex="selectable ? 0 : undefined"
    :aria-label="selectable ? `查看视频详情：${displayName}` : undefined"
    :aria-pressed="selectable ? selected : undefined"
    @click="selectCard"
    @keydown.enter.prevent="selectCard"
    @keydown.space.prevent="selectCard"
  >
    <div
      class="media-preview video-preview"
      :role="selectable ? undefined : 'button'"
      :tabindex="selectable ? undefined : 0"
      :aria-label="selectable ? undefined : `播放 ${displayName}`"
      @click.stop="activatePreview"
      @keydown.enter.prevent.stop="activatePreview"
      @keydown.space.prevent.stop="activatePreview"
    >
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
        <AppIcon :name="previewFailed ? 'alert' : 'video'" size="22" />
        <small>{{ previewFailed ? '浏览器无法预览' : loadingLink ? '正在获取预览' : '视频' }}</small>
      </div>
      <span v-if="!selectable && !previewFailed && streamUrl" class="play-badge" aria-hidden="true"><AppIcon name="play" size="14" /></span>
      <span class="visibility-marker" :class="item.visibility">
        <AppIcon v-if="isPrivate" name="lock" size="10" />
        {{ isPrivate ? '私密' : '公开' }}
      </span>
    </div>

    <div class="media-card-body">
      <h3 v-if="selectable" :title="displayName">{{ displayName }}</h3>
      <template v-else>
      <div class="media-card-heading">
        <div>
          <h3 :title="displayName">{{ displayName }}</h3>
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
      </template>
      <button v-if="selectable && previewFailed" class="preview-retry" type="button" @click.stop="retryPreview">重试预览</button>
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
.video-card {
  overflow: visible;
}

.video-card.selectable {
  padding: 5px;
  border: 2px solid transparent;
  border-radius: 8px;
  background: transparent;
  box-shadow: none;
  cursor: pointer;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.video-card.selectable:hover {
  border-color: #e4e4e7;
  background: #fafafa;
  box-shadow: none;
  transform: none;
}

.video-card.selectable:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.video-card.selectable.selected,
.video-card.selectable.selected:hover {
  border-color: #2563eb;
  background: #fff;
}

.video-preview {
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border: 0;
  border-radius: 5px;
  background: #05080f;
  cursor: pointer;
}

.video-preview video {
  width: 100%;
  height: 100%;
  border-radius: inherit;
  background: #05080f;
  object-fit: contain;
}

.video-placeholder {
  gap: 7px;
  border-radius: inherit;
  background: #f4f4f5;
  color: #71717a;
}

.video-placeholder small { font-size: 11px; }

.play-badge {
  width: 34px;
  height: 34px;
  border: 0;
  background: rgb(9 9 11 / 64%);
  box-shadow: none;
  backdrop-filter: none;
}

.visibility-marker {
  position: absolute;
  top: 7px;
  right: 7px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 5px;
  border: 1px solid rgb(228 228 231 / 90%);
  border-radius: 4px;
  background: rgb(255 255 255 / 90%);
  color: #52525b;
  font-size: 10px;
  font-weight: 500;
  line-height: 1.3;
}

.video-card.selectable .media-card-body { padding: 7px 1px 1px; }

.video-card.selectable .media-card-body h3 {
  margin: 0;
  overflow: hidden;
  color: #27272a;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.video-card.selectable.selected .media-card-body h3 { color: #2563eb; }

.preview-retry {
  margin-top: 5px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #2563eb;
  font-size: 11px;
  cursor: pointer;
}

.rename-form { display: grid; gap: 7px; }
.rename-form label { font-size: 12px; font-weight: 650; }
.rename-form input { min-height: 42px; border: 1px solid var(--border); border-radius: 10px; padding: 8px 11px; outline: 0; }
.rename-form input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgb(37 99 235 / 10%); }
.rename-form p { margin: 4px 0 0; font-size: 12px; }
</style>
