<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getSignedLink, updateImage } from '../api'
import { toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import { downloadMediaFile } from '../utils/download'
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
  checked: { type: Boolean, default: false },
  multiSelectMode: { type: Boolean, default: false },
})

const emit = defineEmits(['delete', 'toggle-visibility', 'add-to-group', 'remove', 'retry', 'remove-pending', 'select', 'preview', 'check'])
const signedUrl = ref(null)
const linkFailed = ref(false)
const localUrl = ref(null)
const signedRefreshAttempted = ref(false)
const copied = ref(false)
const editing = ref(false)
const editName = ref('')
const editSaving = ref(false)
const editError = ref('')
let copiedTimer = null

const result = computed(() => props.item.result)
const isPrivate = computed(() => result.value?.visibility === 'private')
const isPending = computed(() => ['queued', 'uploading'].includes(props.item.status))
const hasContextActions = computed(() => Boolean(
  props.editable || props.deletable || props.groupable || props.removable,
))
const displayName = computed(() => (
  result.value?.name
  || result.value?.original_filename
  || props.item.file?.name
  || (isPdf.value ? '未命名文档' : '未命名图片')
))
const isPdf = computed(() => (
  result.value?.content_type === 'application/pdf'
  || props.item.file?.type === 'application/pdf'
  || String(result.value?.name || result.value?.original_filename || props.item.file?.name || '').toLowerCase().endsWith('.pdf')
))
const placeholderIcon = computed(() => {
  if (props.item.status === 'error') return 'alert'
  if (isPdf.value) return 'pdf'
  if (linkFailed.value) return 'lock'
  if (isPending.value) return 'upload'
  return 'image'
})
const placeholderText = computed(() => {
  if (props.item.status === 'error') return '上传失败'
  if (isPdf.value) return 'PDF 文档'
  if (linkFailed.value) return '预览不可用'
  if (props.item.status === 'queued') return '等待上传'
  return '正在处理'
})

watch(() => props.item.file, file => {
  if (localUrl.value) URL.revokeObjectURL(localUrl.value)
  localUrl.value = file?.type?.startsWith('image/') ? URL.createObjectURL(file) : null
}, { immediate: true })

async function loadSignedLink() {
  signedUrl.value = null
  linkFailed.value = false
  if (!result.value || !isPrivate.value) return
  try {
    signedUrl.value = (await getSignedLink(result.value.code)).url
  } catch {
    linkFailed.value = true
  }
}

watch(() => [result.value?.code, result.value?.visibility], async () => {
  signedRefreshAttempted.value = false
  await loadSignedLink()
}, { immediate: true })

onBeforeUnmount(() => {
  if (localUrl.value) URL.revokeObjectURL(localUrl.value)
  if (copiedTimer) window.clearTimeout(copiedTimer)
})

const previewUrl = computed(() => {
  if (!result.value) return localUrl.value
  return isPrivate.value ? signedUrl.value : result.value.url
})

async function onPreviewError() {
  if (isPrivate.value && !signedRefreshAttempted.value) {
    signedRefreshAttempted.value = true
    await loadSignedLink()
    return
  }
  linkFailed.value = true
}

async function retryPreview() {
  signedRefreshAttempted.value = false
  if (isPrivate.value) await loadSignedLink()
  else linkFailed.value = false
}

function selectCard(event) {
  if (!props.selectable || !result.value) return
  if (props.multiSelectMode || event?.shiftKey || event?.ctrlKey || event?.metaKey) {
    emit('check', { item: result.value, event })
    return
  }
  emit('select', result.value)
}

function toggleCheck(event) {
  if (!result.value) return
  emit('check', { item: result.value, event })
}

async function copyUrl() {
  let target = result.value?.url || ''
  if (isPrivate.value) {
    try {
      target = (await getSignedLink(result.value.code)).url || ''
      signedUrl.value = target
      linkFailed.value = false
    } catch {
      target = ''
    }
  }
  if (!target || !(await copyText(target))) {
    toast('复制失败，请稍后重试', 'error')
    return
  }
  copied.value = true
  toast(isPrivate.value ? '限时签名链接已复制' : (isPdf.value ? '文档链接已复制' : '图片链接已复制'), 'success')
  if (copiedTimer) window.clearTimeout(copiedTimer)
  copiedTimer = window.setTimeout(() => { copied.value = false }, 1200)
}

function openEditor() {
  editName.value = displayName.value
  editError.value = ''
  editing.value = true
}

async function saveName() {
  const name = editName.value.trim()
  if (!name) {
    editError.value = '名称不能为空'
    return
  }
  if (editSaving.value) return
  editSaving.value = true
  editError.value = ''
  try {
    const updated = await updateImage(result.value.code, { name })
    Object.assign(result.value, updated)
    editing.value = false
    toast(isPdf.value ? '文档名称已更新' : '图片名称已更新', 'success')
  } catch (error) {
    editError.value = error.message || '保存失败，请稍后重试'
  } finally {
    editSaving.value = false
  }
}

function triggerDownload() {
  if (!result.value) return
  const target = previewUrl.value || result.value.url
  downloadMediaFile(target, displayName.value)
}
</script>

<template>
  <article
    class="media-card image-card"
    :class="{
      pending: isPending,
      error: item.status === 'error',
      selectable: selectable && result,
      selected: selected && selectable && result,
      'is-checked': checked,
      'multi-selecting': multiSelectMode,
    }"
    :role="selectable && result ? 'button' : undefined"
    :tabindex="selectable && result ? 0 : undefined"
    :aria-label="selectable && result ? `查看${isPdf ? '文档' : '图片'}详情：${displayName}` : undefined"
    :aria-pressed="selectable && result ? selected : undefined"
    @click="selectCard($event)"
    @keydown.enter.prevent="selectCard($event)"
    @keydown.space.prevent="selectCard($event)"
  >
    <div class="media-preview image-preview" :class="{ 'is-pdf-card': isPdf }">
      <button
        v-if="result && (selectable || multiSelectMode)"
        type="button"
        class="card-checkbox"
        :class="{ checked }"
        :aria-label="checked ? `取消勾选 ${displayName}` : `勾选 ${displayName}`"
        :aria-checked="checked"
        @click.stop="toggleCheck($event)"
      >
        <AppIcon :name="checked ? 'checkSquare' : 'square'" size="16" />
      </button>
      <div v-if="isPdf && !['queued', 'uploading', 'error'].includes(item.status)" class="pdf-card-preview">
        <AppIcon name="pdf" :size="30" />
        <span class="pdf-tag">PDF</span>
      </div>
      <img v-else-if="previewUrl && !linkFailed" :src="previewUrl" :alt="displayName" loading="lazy" decoding="async" referrerpolicy="no-referrer" @error="onPreviewError" />
      <div v-else class="preview-placeholder">
        <AppIcon :name="placeholderIcon" :size="22" />
        <small>{{ placeholderText }}</small>
      </div>
      <span v-if="result" class="visibility-marker" :class="result.visibility">
        <AppIcon v-if="isPrivate" name="lock" :size="10" />
        {{ result.visibility === 'private' ? '私密' : '公开' }}
      </span>
    </div>

    <div class="media-card-body">
      <h3 :title="displayName">{{ displayName }}</h3>
      <p v-if="item.status === 'queued'" class="task-status">排队等待上传</p>
      <p v-else-if="item.status === 'uploading'" class="task-status">正在上传</p>
      <div v-else-if="item.status === 'error'" class="upload-error">
        <p class="error-text" role="alert">{{ item.error || '上传失败，请重试' }}</p>
        <div class="card-actions">
          <button v-if="item.retryable !== false" class="secondary" type="button" @click.stop="emit('retry')">重试上传</button>
          <button class="ghost" type="button" @click.stop="emit('remove-pending')">移除</button>
        </div>
      </div>
      <button v-else-if="linkFailed" class="preview-retry" type="button" @click.stop="retryPreview">重试预览</button>
      <div v-if="result && hasContextActions" class="context-card-actions">
        <button class="ghost" type="button" @click.stop="triggerDownload">
          <AppIcon name="download" size="13" />
          下载
        </button>
        <button class="ghost" type="button" @click.stop="copyUrl">
          <AppIcon :name="copied ? 'check' : 'copy'" size="13" />
          {{ copied ? '已复制' : (isPdf ? '复制文档链接' : '复制链接') }}
        </button>
        <button v-if="groupable" class="ghost" type="button" @click.stop="emit('add-to-group')">加入分组</button>
        <button v-if="removable" class="ghost danger" type="button" @click.stop="emit('remove')">移出分组</button>
        <button v-if="editable || deletable" class="ghost" type="button" @click.stop="openEditor">重命名</button>
        <button v-if="deletable" class="ghost" type="button" @click.stop="emit('toggle-visibility')">
          {{ isPrivate ? '设为公开' : '设为私密' }}
        </button>
        <button v-if="deletable" class="ghost danger" type="button" @click.stop="emit('delete')">删除</button>
      </div>
    </div>

    <BaseModal
      v-if="editing"
      :title="isPdf ? '重命名文档' : '重命名图片'"
      description="仅修改媒体库中的显示名称，原始文件名保持不变。"
      labelled-by="rename-image-title"
      @close="editing = false"
    >
      <form id="rename-image-form" class="rename-form" @submit.prevent="saveName">
        <label for="rename-image-input">显示名称</label>
        <input id="rename-image-input" v-model="editName" autofocus maxlength="255" />
        <p v-if="editError" class="error-text" role="alert">{{ editError }}</p>
      </form>
      <template #footer>
        <button class="ghost" type="button" :disabled="editSaving" @click="editing = false">取消</button>
        <button class="primary" type="submit" form="rename-image-form" :disabled="editSaving || !editName.trim()">
          {{ editSaving ? '保存中…' : '保存' }}
        </button>
      </template>
    </BaseModal>
  </article>
</template>

<style scoped>
.image-card {
  overflow: visible;
  padding: 5px;
  border: 2px solid transparent;
  border-radius: 8px;
  background: transparent;
  box-shadow: none;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.image-card:hover {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
  transform: none;
}

.image-card.selectable { cursor: pointer; }
.image-card.selectable:hover {
  border-color: #e4e4e7;
  background: #fafafa;
}

.image-card.selectable:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.image-card.selected,
.image-card.selected:hover {
  border-color: #2563eb;
  background: #fff;
}

.image-card.pending { border-style: dashed; border-color: #d4d4d8; }
.image-card.error { border-color: #fecaca; background: #fffafa; }

.image-preview {
  aspect-ratio: 4 / 3;
  border: 0;
  border-radius: 5px;
  background: #f4f4f5;
}

.pdf-card-preview {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #71717a;
  background: #f4f4f5;
}

.pdf-tag {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.preview-placeholder {
  gap: 7px;
  background: #f4f4f5;
  color: #71717a;
}

.preview-placeholder small { font-size: 12px; }

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
  font-size: 11px;
  font-weight: 500;
  line-height: 1.3;
}

.visibility-marker.public { color: #3f3f46; }

.media-card-body { padding: 7px 1px 1px; }

.media-card-body h3 {
  margin: 0;
  overflow: hidden;
  color: #27272a;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selected .media-card-body h3 { color: #2563eb; }

.task-status,
.upload-error p {
  margin: 4px 0 0;
  overflow: hidden;
  color: #71717a;
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-error p { color: #b91c1c; }

.card-actions {
  margin-top: 8px;
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
}

.card-actions button {
  min-height: 30px;
  flex: 1;
  padding: 5px 8px;
  font-size: 14px;
}

.preview-retry {
  margin-top: 5px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #2563eb;
  font-size: 14px;
  cursor: pointer;
}

.context-card-actions {
  margin-top: 9px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.context-card-actions button {
  min-height: 28px;
  gap: 4px;
  padding: 4px 7px;
  font-size: 14px;
}

.rename-form {
  display: grid;
  gap: 7px;
}

.rename-form label {
  font-size: 14px;
  font-weight: 650;
}

.rename-form input {
  min-height: 40px;
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 8px 10px;
  font-size: 14px;
  outline: 0;
}

.rename-form input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgb(11 99 229 / 10%);
}

.rename-form p {
  margin: 3px 0 0;
  font-size: 13px;
}

@media (max-width: 580px) {
  .rename-form input { font-size: 16px; }
}

.card-checkbox {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 28px;
  height: 28px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.72);
  backdrop-filter: blur(4px);
  color: #cbd5e1;
  border: 1px solid rgba(255, 255, 255, 0.35);
  cursor: pointer;
  z-index: 5;
  opacity: 0;
  transition: opacity 140ms ease, background-color 140ms ease, transform 140ms ease, border-color 140ms ease;
}

.image-card:hover .card-checkbox,
.card-checkbox:focus-visible,
.card-checkbox.checked,
.image-card.multi-selecting .card-checkbox {
  opacity: 1;
}

.card-checkbox.checked {
  background: #2563eb;
  border-color: #3b82f6;
  color: #fff;
}

.card-checkbox:hover {
  transform: scale(1.08);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.8);
}

.image-card.is-checked {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.35);
}
</style>
