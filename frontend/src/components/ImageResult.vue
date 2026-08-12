<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  item: { type: Object, required: true },
})

const copied = ref(false)

// 预览/复制一律使用后端返回的绝对 URL（受 OSS_PUBLIC_URL 环境变量控制），
// 前端不自行拼 base，保证 PUBLIC_URL 配置的域名全局生效。
const previewUrl = computed(() => props.item.result?.url ?? null)

const infoText = computed(() => {
  if (props.item.status === 'uploading') return '上传中…'
  const r = props.item.result
  if (!r) return ''
  const parts = []
  if (r.name) parts.push(r.name)
  parts.push(`${(r.size / 1024).toFixed(1)} KB`)
  parts.push(r.content_type)
  parts.push(r.code)
  if (r.owner_username) parts.push(`@${r.owner_username}`)
  return parts.join(' · ')
})

async function copyUrl() {
  const text = props.item.result.url
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
      <div v-else class="thumb placeholder">⏳</div>

      <div class="meta">
        <span class="url">{{ item.result?.url || '上传中…' }}</span>
        <span class="info">{{ infoText }}</span>
      </div>

      <button v-if="item.result" class="copy" :disabled="copied" :title="item.result.url" @click="copyUrl">
        {{ copied ? '已复制 ✓' : '复制链接' }}
      </button>
    </template>
  </div>
</template>
