<script setup>
import { ref } from 'vue'

const emit = defineEmits(['files'])
const input = ref(null)
const dragging = ref(false)

function openPicker() {
  input.value?.click()
}

function onInput(e) {
  emit('files', e.target.files)
  e.target.value = ''
}

function onDrop(e) {
  dragging.value = false
  emit('files', e.dataTransfer.files)
}
</script>

<template>
  <div
    class="drop"
    :class="{ dragover: dragging }"
    role="button"
    tabindex="0"
    aria-label="选择或拖拽图片上传"
    @click="openPicker"
    @keydown.enter.prevent="openPicker"
    @keydown.space.prevent="openPicker"
    @dragenter.prevent="dragging = true"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
  >
    <input ref="input" type="file" accept="image/*" multiple hidden @change="onInput" />
    <p class="hint">点击选择 或 拖拽图片到此处</p>
    <p class="sub">支持 jpg / png / gif / webp / svg / bmp / ico / avif / tiff</p>
  </div>
</template>
