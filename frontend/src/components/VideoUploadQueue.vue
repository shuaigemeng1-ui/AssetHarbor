<script setup>
import { computed, ref } from 'vue'
import {
  attachVideoFile,
  cancelVideoTask,
  dismissCompletedTask,
  pauseVideoTask,
  resumeVideoTask,
  retryVideoTask,
  taskProgress,
  taskTransferredBytes,
  uploadStatusLabel,
  VIDEO_ACCEPT,
  videoUploadState,
} from '../stores/videoUploads'
import { confirmAction, toast } from '../stores/feedback'
import { formatBytes, formatDuration } from '../utils/format'

const props = defineProps({
  teamId: { type: [Number, String], default: null },
})

const fileInput = ref(null)
const attachingTask = ref(null)

const tasks = computed(() => videoUploadState.tasks.filter(task => {
  if (props.teamId === null || props.teamId === undefined) return task.teamId === null || task.teamId === undefined
  return String(task.teamId) === String(props.teamId)
}))

function chooseOriginal(task) {
  attachingTask.value = task
  fileInput.value?.click()
}

async function onOriginalSelected(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || !attachingTask.value) return
  const task = attachingTask.value
  attachingTask.value = null
  try {
    await attachVideoFile(task, file)
    toast('文件校验通过，继续上传', 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}

async function cancel(task) {
  const ok = await confirmAction({
    title: '取消上传任务',
    message: `确定取消「${task.filename}」？已上传的分片也会被清理。`,
    confirmText: '取消上传',
    danger: true,
  })
  if (!ok) return
  try {
    await cancelVideoTask(task)
    toast('上传任务已取消', 'success')
  } catch (error) {
    toast(`取消失败：${error.message}`, 'error')
  }
}

function progressText(task) {
  return `${taskProgress(task).toFixed(1)}%`
}
</script>

<template>
  <section v-if="tasks.length" class="upload-queue" aria-labelledby="upload-queue-title">
    <div class="queue-heading">
      <div>
        <p class="eyebrow">后台上传</p>
        <h3 id="upload-queue-title">上传队列 <span>{{ tasks.length }}</span></h3>
      </div>
      <span v-if="!videoUploadState.online" class="offline-badge">网络已断开</span>
    </div>

    <input ref="fileInput" type="file" :accept="VIDEO_ACCEPT" hidden @change="onOriginalSelected" />

    <div class="queue-list">
      <article v-for="task in tasks" :key="task.localId" class="queue-item">
        <div class="file-mark" aria-hidden="true">▶</div>
        <div class="queue-main">
          <div class="queue-title-row">
            <div class="queue-filename" :title="task.filename">{{ task.name || task.filename }}</div>
            <strong>{{ progressText(task) }}</strong>
          </div>
          <div
            class="progress-track"
            role="progressbar"
            :aria-label="`${task.filename} 上传进度`"
            aria-valuemin="0"
            aria-valuemax="100"
            :aria-valuenow="Math.round(taskProgress(task))"
          >
            <span :style="{ width: `${taskProgress(task)}%` }"></span>
          </div>
          <div class="queue-meta">
            <span class="queue-status" :class="`status-${task.status}`">{{ uploadStatusLabel(task) }}</span>
            <span>{{ formatBytes(taskTransferredBytes(task)) }} / {{ formatBytes(task.size) }}</span>
            <template v-if="['uploading', 'retrying'].includes(task.status) && task.speed > 0">
              <span>{{ formatBytes(task.speed) }}/s</span>
              <span>剩余 {{ formatDuration(task.eta) }}</span>
            </template>
          </div>
          <p v-if="task.error" class="queue-error">{{ task.error }}</p>
          <p v-if="task.status === 'waiting_file'" class="queue-note">
            浏览器不会保存视频本体。请选择原文件，指纹一致后会从缺失分片继续。
          </p>
        </div>
        <div class="queue-actions">
          <button v-if="['uploading', 'retrying'].includes(task.status)" class="ghost" @click="pauseVideoTask(task)">暂停</button>
          <button v-else-if="['manual_paused', 'network_paused'].includes(task.status) && task.file" class="ghost" :disabled="!videoUploadState.online" @click="resumeVideoTask(task)">继续</button>
          <button v-if="task.status === 'waiting_file' || (task.status === 'failed' && !task.file)" class="ghost" @click="chooseOriginal(task)">重新选择</button>
          <button v-if="task.status === 'failed' && task.file" class="ghost" @click="retryVideoTask(task)">重试</button>
          <button v-if="task.status === 'completed'" class="ghost" @click="dismissCompletedTask(task)">收起</button>
          <button v-else-if="task.status !== 'cancelling'" class="ghost danger" @click="cancel(task)">取消</button>
        </div>
      </article>
    </div>
  </section>
</template>
