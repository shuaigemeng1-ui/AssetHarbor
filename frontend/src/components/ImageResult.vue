<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  item: { type: Object, required: true },
})

const copied = ref(false)

const previewUrl = computed(() =>
  props.item.result ? `/i/${props.item.result.code}` : null,
)

const infoText = computed(() => {
  if (props.item.status === 'uploading') return '上传中…'
  const r = props.item.result
  if (!r) return ''
  return `${(r.size / 1024).toFixed(1)} KB · ${r.content_type} · ${r.code}`
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

      <button v-if="item.result" class="copy" :disabled="copied" @click="copyUrl">
        {{ copied ? '已复制 ✓' : '复制' }}
      </button>
    </template>
  </div>
</template>
