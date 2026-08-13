<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { getVideoSignedLink } from '../api'
import { formatBytes } from '../utils/format'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'

const props = defineProps({ item: { type: Object, required: true } })
const emit = defineEmits(['close'])

const player = ref(null)
const sourceUrl = ref('')
const loading = ref(true)
const failed = ref(false)
const refreshed = ref(false)

const isPrivate = computed(() => props.item.visibility === 'private')
const downloadUrl = computed(() => sourceUrl.value
  ? `${sourceUrl.value}${sourceUrl.value.includes('?') ? '&' : '?'}download=1`
  : '')

async function loadSource(force = false) {
  loading.value = true
  failed.value = false
  try {
    sourceUrl.value = isPrivate.value
      ? (await getVideoSignedLink(props.item.code, force ? undefined : null)).url
      : props.item.url
    await nextTick()
    player.value?.load()
    player.value?.play().catch(() => {})
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

async function onPlayerError() {
  if (isPrivate.value && !refreshed.value) {
    refreshed.value = true
    await loadSource(true)
    return
  }
  failed.value = true
}

watch(() => props.item.visibility, () => {
  refreshed.value = false
  loadSource()
})

onMounted(() => {
  loadSource()
})
</script>

<template>
  <BaseModal
    :title="item.name || item.original_filename || '视频播放器'"
    :description="`${formatBytes(item.size)} · ${item.content_type}`"
    labelled-by="player-title"
    wide
    fit-viewport
    @close="emit('close')"
  >
    <section class="player-content">
      <div class="player-stage">
        <video
          v-if="sourceUrl && !failed"
          ref="player"
          class="player-media"
          :src="sourceUrl"
          controls
          playsinline
          preload="metadata"
          @error="onPlayerError"
        ></video>
        <div v-else class="player-fallback">
          <div class="empty-icon"><AppIcon name="video" size="20" /></div>
          <h3>{{ loading ? '正在加载视频…' : '当前浏览器无法播放此视频' }}</h3>
          <p v-if="!loading">文件会保持原格式存储，你仍然可以下载后使用本地播放器打开。</p>
          <button v-if="!loading" class="secondary" type="button" @click="loadSource(true)">重试播放</button>
          <a v-if="downloadUrl && !loading" class="primary button-link" :href="downloadUrl">下载原文件</a>
        </div>
      </div>
    </section>
  </BaseModal>
</template>

<style scoped>
.player-content {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: grid;
  place-items: center;
  overflow: hidden;
  color: #fff;
}

.player-stage {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid #20242b;
  border-radius: 6px;
  background: #05080f;
  isolation: isolate;
}

.player-stage .player-media {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  max-height: 100%;
  display: block;
  background: #05080f;
  object-fit: contain;
  object-position: center;
}

.player-fallback {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  min-height: 0;
  max-width: none;
  display: grid;
  align-content: center;
  justify-items: center;
  padding: clamp(24px, 6vh, 70px) 25px;
  text-align: center;
}

.player-fallback p {
  color: #98a2b3;
}

@media (max-width: 580px) {
  .player-stage {
    border-radius: 5px;
  }
}
</style>
