<script setup>
import { computed, onMounted, ref } from 'vue'
import { getSignedLink } from '../api'

const props = defineProps({
  item: { type: Object, required: true },
})

const copied = ref(false)
const signedUrl = ref(null)
const linkFailed = ref(false)

const isPrivate = computed(() => props.item.result?.visibility === 'private')

// 私密图：<img> 标签无法携带 Authorization 头，必须通过过期签名链接预览；
// 链接由 /api/images/{code}/link 生成，默认 24h 有效。
onMounted(async () => {
  if (isPrivate.value && props.item.result) {
    try {
      signedUrl.value = (await getSignedLink(props.item.result.code)).url
    } catch {
      linkFailed.value = true
    }
  }
})

const previewUrl = computed(() => {
  if (isPrivate.value) return signedUrl.value || null
  return props.item.result?.url ?? null
})

const copyTarget = computed(() => {
  if (!props.item.result) return ''
  return isPrivate.value ? signedUrl.value || props.item.result.url : props.item.result.url
})

const infoText = computed(() => {
  if (props.item.status === 'uploading') return '上传中…'
  const r = props.item.result
  if (!r) return ''
  const parts = []
  if (r.name) parts.push(r.name)
  parts.push(`${(r.size / 1024).toFixed(1)} KB`)
  if (r.visibility === 'private') parts.push('🔒 私密')
  parts.push(r.content_type)
  parts.push(r.code)
  if (r.owner_username) parts.push(`@${r.owner_username}`)
  return parts.join(' · ')
})

async function copyUrl() {
  const text = copyTarget.value
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  copied.value = true
  setTimeout(() => (copied.value = false), 1200)
}
</script>

<template>
  <div class="row">
    <template v-if="item.status === 'error'">
      <div class="error-box">❌ {{ item.file.name }}：{{ item.error }}</div>
    </template>

    <template v-else>
      <img v-if="previewUrl" :src="previewUrl" class="thumb" alt="" referrerpolicy="no-referrer" />
      <div v-else class="thumb placeholder" :title="linkFailed ? '无法生成预览链接' : ''">
        {{ linkFailed ? '🔒' : '⏳' }}
      </div>

      <div class="meta">
        <span class="url">{{ item.result?.url || '上传中…' }}</span>
        <span class="info">{{ infoText }}</span>
        <span v-if="isPrivate && signedUrl" class="info link-hint">复制的是限时签名链接</span>
      </div>

      <button v-if="item.result" class="copy" :disabled="copied" :title="copyTarget" @click="copyUrl">
        {{ copied ? '已复制 ✓' : '复制链接' }}
      </button>
    </template>
  </div>
</template>
