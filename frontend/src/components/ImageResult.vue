<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getSignedLink } from '../api'
import { toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import { formatBytes } from '../utils/format'

const props = defineProps({
  item: { type: Object, required: true },
  deletable: { type: Boolean, default: false },
})

const emit = defineEmits(['delete', 'toggle-visibility'])
const copied = ref(false)
const signedUrl = ref(null)
const linkFailed = ref(false)
const localUrl = ref(null)

const result = computed(() => props.item.result)
const isPrivate = computed(() => result.value?.visibility === 'private')

watch(() => props.item.file, file => {
  if (localUrl.value) URL.revokeObjectURL(localUrl.value)
  localUrl.value = file?.type?.startsWith('image/') ? URL.createObjectURL(file) : null
}, { immediate: true })

watch(() => [result.value?.code, result.value?.visibility], async () => {
  signedUrl.value = null
  linkFailed.value = false
  if (!result.value || !isPrivate.value) return
  try {
    signedUrl.value = (await getSignedLink(result.value.code)).url
  } catch {
    linkFailed.value = true
  }
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
  const ok = await copyText(copyTarget.value)
  if (!ok) {
    toast('复制失败，请手动复制链接', 'error')
    return
  }
  copied.value = true
  toast(isPrivate.value ? '限时签名链接已复制' : '图片链接已复制', 'success')
  window.setTimeout(() => (copied.value = false), 1200)
}
</script>

<template>
  <article class="media-card image-card" :class="{ pending: item.status === 'uploading' }">
    <div class="media-preview image-preview">
      <img v-if="previewUrl" :src="previewUrl" :alt="result?.name || result?.original_filename || item.file?.name || '图片预览'" referrerpolicy="no-referrer" />
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
          <p v-else-if="item.status === 'uploading'">正在上传…</p>
          <p v-else class="error-text">{{ item.error }}</p>
        </div>
      </div>

      <div v-if="result" class="card-actions">
        <button class="ghost" :disabled="copied || (isPrivate && !signedUrl)" @click="copyUrl">
          {{ copied ? '已复制' : '复制链接' }}
        </button>
        <button v-if="deletable" class="ghost" @click="emit('toggle-visibility')">
          {{ result.visibility === 'private' ? '设为公开' : '设为私密' }}
        </button>
        <button v-if="deletable" class="ghost danger" @click="emit('delete')">删除</button>
      </div>
    </div>
  </article>
</template>
