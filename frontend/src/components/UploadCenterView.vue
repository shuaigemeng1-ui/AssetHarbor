<script setup>
import { computed, onMounted, ref } from 'vue'
import { activeVideoUploadCount, videoUploadState } from '../stores/videoUploads'
import AppIcon from './AppIcon.vue'
import VideoUploadQueue from './VideoUploadQueue.vue'

const heading = ref(null)

const activeTaskDescription = computed(() => {
  if (!videoUploadState.restored) return '正在恢复本地保存的视频上传任务…'
  return activeVideoUploadCount.value
    ? `当前有 ${activeVideoUploadCount.value} 个未完成的视频上传任务。`
    : '当前没有未完成的视频上传任务。'
})

const hasTasks = computed(() => videoUploadState.tasks.length > 0)

onMounted(() => {
  heading.value?.focus({ preventScroll: true })
})
</script>

<template>
  <section class="upload-center-view" aria-labelledby="upload-center-title">
    <header class="upload-center-header">
      <div class="upload-center-heading">
        <span class="upload-center-kicker">视频上传</span>
        <h1 id="upload-center-title" ref="heading" tabindex="-1">视频上传中心</h1>
        <p>集中管理个人空间与团队空间的视频上传任务。</p>
      </div>

      <div
        class="upload-status-summary"
        role="status"
        aria-live="polite"
        :aria-busy="!videoUploadState.restored ? 'true' : undefined"
      >
        <span class="status-indicator" :class="{ active: activeVideoUploadCount > 0 }" aria-hidden="true"></span>
        <span class="status-copy">
          <span>未完成任务</span>
          <strong>{{ activeVideoUploadCount }}</strong>
        </span>
        <p>{{ activeTaskDescription }}</p>
      </div>
    </header>

    <div class="upload-center-content">
      <div class="upload-center-section-heading">
        <div>
          <span>任务管理</span>
          <h2>全部视频上传任务</h2>
        </div>
        <p>个人与团队空间的上传进度统一显示在这里。</p>
      </div>

      <div v-if="!videoUploadState.restored" class="upload-center-state">
        <AppIcon name="upload" aria-hidden="true" />
        <strong>正在恢复上传任务</strong>
        <p>正在读取此前保留的视频上传进度，请稍候。</p>
      </div>
      <div v-else-if="!hasTasks" class="upload-center-state">
        <AppIcon name="video" aria-hidden="true" />
        <strong>暂无视频上传任务</strong>
        <p>从“我的视频”、团队视频或全站视频页面开始上传后，任务会显示在这里。</p>
      </div>
      <VideoUploadQueue v-else all-scopes />
    </div>
  </section>
</template>

<style scoped>
.upload-center-view {
  display: grid;
  gap: 20px;
  color: var(--text, #1c1917);
}

.upload-center-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
  align-items: end;
  gap: 32px;
}

.upload-center-heading {
  min-width: 0;
}

.upload-center-kicker,
.upload-center-section-heading > div > span {
  color: var(--muted, #737373);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
}

.upload-center-heading h1 {
  margin: 6px 0 7px;
  font-size: clamp(26px, 1.1vw, 30px);
  line-height: 1.2;
  letter-spacing: -.025em;
}

.upload-center-heading p,
.upload-center-section-heading p,
.upload-status-summary p {
  margin: 0;
  color: var(--muted, #737373);
  font-size: 14px;
  line-height: 1.65;
}

.upload-status-summary {
  min-height: 82px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-content: center;
  align-items: center;
  column-gap: 10px;
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 8px;
  padding: 14px 16px;
  background: #fff;
}

.status-indicator {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #a3a3a3;
}

.status-indicator.active {
  background: var(--accent, #0b63e5);
  box-shadow: 0 0 0 4px rgb(11 99 229 / 10%);
}

.status-copy {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 14px;
  font-weight: 650;
}

.status-copy strong {
  font-size: 22px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.upload-status-summary p {
  grid-column: 2;
  margin-top: 4px;
  font-size: 13px;
}

.upload-center-content {
  min-height: 260px;
  border: 1px solid var(--border, #e5e5e3);
  border-radius: 8px;
  padding: 20px;
  background: #fff;
}

.upload-center-section-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border, #e5e5e3);
  padding-bottom: 16px;
}

.upload-center-section-heading h2 {
  margin: 5px 0 0;
  font-size: 20px;
  line-height: 1.3;
}

.upload-center-section-heading > p {
  max-width: 420px;
  text-align: right;
}

.upload-center-state {
  min-height: 180px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  color: var(--muted, #737373);
  text-align: center;
}

.upload-center-state :deep(svg) {
  width: 24px;
  height: 24px;
}

.upload-center-state strong {
  color: var(--text, #1c1917);
  font-size: 16px;
}

.upload-center-state p {
  max-width: 520px;
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
}

:deep(.upload-queue) {
  margin: 0;
  border: 0 !important;
  padding: 0;
}

:deep(.queue-heading .eyebrow),
:deep(.queue-meta),
:deep(.queue-note),
:deep(.queue-error) {
  font-size: 12px;
}

:deep(.queue-heading h3) {
  font-size: 16px;
}

:deep(.queue-filename) {
  font-size: 14px;
}

:deep(.queue-title-row strong),
:deep(.queue-actions button) {
  font-size: 13px;
}

@media (max-width: 760px) {
  .upload-center-header {
    grid-template-columns: minmax(0, 1fr);
    align-items: stretch;
    gap: 16px;
  }

  .upload-center-section-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 7px;
  }

  .upload-center-section-heading > p {
    text-align: left;
  }
}

@media (max-width: 560px) {
  .upload-center-content {
    min-height: 220px;
    padding: 16px;
  }

  :deep(.queue-actions) {
    grid-column: 1 / -1;
  }
}
</style>
