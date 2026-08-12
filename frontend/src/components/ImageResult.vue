<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getSignedLink, updateImage } from '../api'
import { toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import { formatBytes } from '../utils/format'
import BaseModal from './BaseModal.vue'

const props = defineProps({
  item: { type: Object, required: true },
  deletable: { type: Boolean, default: false },
  editable: { type: Boolean, default: false },
  groupable: { type: Boolean, default: false },
  removable: { type: Boolean, default: false },
  showScope: { type: Boolean, default: false },
})

const emit = defineEmits(['delete', 'toggle-visibility', 'add-to-group', 'remove', 'retry', 'remove-pending'])
const copied = ref(false)
const signedUrl = ref(null)
const linkFailed = ref(false)
const localUrl = ref(null)
const signedRefreshAttempted = ref(false)
const editing = ref(false)
const editName = ref('')
const editSaving = ref(false)
const editError = ref('')

const result = computed(() => props.item.result)
const isPrivate = computed(() => result.value?.visibility === 'private')

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
})

const previewUrl = computed(() => {
  if (!result.value) return localUrl.value
  return isPrivate.value ? signedUrl.value : result.value.url
})

const copyTarget = computed(() => {
  if (!result.value) return ''
  return isPrivate.value ? signedUrl.value || result.value.url : result.value.url
})

async function copyUrl() {
  let target = copyTarget.value
  if (isPrivate.value) {
    try {
      signedUrl.value = (await getSignedLink(result.value.code)).url
      target = signedUrl.value
      linkFailed.value = false
    } catch {
      target = ''
    }
  }
  const ok = target && await copyText(target)
  if (!ok) {
    toast('复制失败，请手动复制链接', 'error')
    return
  }
  copied.value = true
  toast(isPrivate.value ? '限时签名链接已复制' : '图片链接已复制', 'success')
  window.setTimeout(() => (copied.value = false), 1200)
}

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

function openEditor() {
  editName.value = result.value?.name || result.value?.original_filename || ''
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
    const updated = await updateImage(result.value.code, { name })
    Object.assign(result.value, updated)
    editing.value = false
    toast('图片名称已更新', 'success')
  } catch (error) {
    editError.value = error.message
  } finally {
    editSaving.value = false
  }
}
</script>

<template>
  <article class="media-card image-card" :class="{ pending: item.status === 'uploading' }">
    <div class="media-preview image-preview">
      <img v-if="previewUrl && !linkFailed" :src="previewUrl" :alt="result?.name || result?.original_filename || item.file?.name || '图片预览'" loading="lazy" decoding="async" referrerpolicy="no-referrer" @error="onPreviewError" />
      <div v-else class="preview-placeholder">
        <span>{{ item.status === 'error' ? '!' : linkFailed ? '🔒' : '…' }}</span>
        <small>{{ item.status === 'error' ? '上传失败' : linkFailed ? '预览不可用' : '正在处理' }}</small>
      </div>
      <span v-if="result" class="visibility-pill" :class="result.visibility">
        {{ result.visibility === 'private' ? '私密' : '公开' }}
      </span>
    </div>

    <div class="media-card-body">
      <div class="media-card-heading">
        <div>
          <h3>{{ result?.name || result?.original_filename || item.file?.name || '未命名图片' }}</h3>
          <p v-if="result">{{ formatBytes(result.size) }} · {{ result.content_type }} · {{ result.code }}</p>
          <p v-if="showScope && result" class="card-scope">{{ result.team_id ? `团队 #${result.team_id}` : '个人空间' }} · {{ result.owner_username || `用户 #${result.owner_id}` }}</p>
          <p v-else-if="item.status === 'queued'">排队等待上传…</p>
          <p v-else-if="item.status === 'uploading'">正在上传…</p>
          <p v-else class="error-text">{{ item.error }}</p>
        </div>
      </div>

      <div v-if="result" class="card-actions">
        <button v-if="linkFailed" class="ghost" @click="retryPreview">重试预览</button>
        <button class="ghost" :disabled="copied || (isPrivate && !signedUrl)" @click="copyUrl">
          {{ copied ? '已复制' : '复制链接' }}
        </button>
        <button v-if="groupable" class="ghost" @click="emit('add-to-group')">加入分组</button>
        <button v-if="removable" class="ghost danger" @click="emit('remove')">移出分组</button>
        <button v-if="editable || deletable" class="ghost" @click="openEditor">重命名</button>
        <button v-if="deletable" class="ghost" @click="emit('toggle-visibility')">
          {{ result.visibility === 'private' ? '设为公开' : '设为私密' }}
        </button>
        <button v-if="deletable" class="ghost danger" @click="emit('delete')">删除</button>
      </div>
      <div v-else-if="item.status === 'error'" class="card-actions">
        <button v-if="item.retryable !== false" class="secondary" @click="emit('retry')">重试上传</button>
        <button class="ghost" @click="emit('remove-pending')">移除</button>
      </div>
    </div>

    <BaseModal v-if="editing" title="重命名图片" description="仅修改媒体库中的显示名称，原始文件名保持不变。" labelled-by="rename-image-title" @close="editing = false">
      <form id="rename-image-form" class="rename-form" @submit.prevent="saveName">
        <label for="rename-image-input">显示名称</label>
        <input id="rename-image-input" v-model="editName" autofocus maxlength="255" />
        <p v-if="editError" class="error-text" role="alert">{{ editError }}</p>
      </form>
      <template #footer>
        <button class="ghost" type="button" :disabled="editSaving" @click="editing = false">取消</button>
        <button class="primary" type="submit" form="rename-image-form" :disabled="editSaving || !editName.trim()">{{ editSaving ? '保存中…' : '保存' }}</button>
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
