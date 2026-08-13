<script setup>
import { ref } from 'vue'

const props = defineProps({
  accept: { type: String, default: 'image/*' },
  multiple: { type: Boolean, default: true },
  label: { type: String, default: '点击选择或拖拽文件到此处' },
  description: { type: String, default: '' },
  ariaLabel: { type: String, default: '选择或拖拽文件上传' },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['files'])
const input = ref(null)
const dragging = ref(false)

function openPicker() {
  input.value?.click()
}

function onInput(event) {
  // FileList is live: clearing the input also empties the object. Consumers
  // perform async validation before reading it, so always emit a stable copy.
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  emit('files', files)
}

function onDrop(event) {
  dragging.value = false
  // DataTransfer.files may become unavailable after the drop event returns.
  emit('files', Array.from(event.dataTransfer?.files || []))
}
</script>

<template>
  <div
    class="drop"
    :class="{ dragover: dragging, compact }"
    role="button"
    tabindex="0"
    :aria-label="ariaLabel"
    @click="openPicker"
    @keydown.enter.prevent="openPicker"
    @keydown.space.prevent="openPicker"
    @dragenter.prevent="dragging = true"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
  >
    <input ref="input" type="file" :accept="accept" :multiple="multiple" hidden @change="onInput" />
    <div class="drop-icon" aria-hidden="true">↑</div>
    <p class="hint">{{ label }}</p>
    <p v-if="description" class="sub">{{ description }}</p>
  </div>
</template>
