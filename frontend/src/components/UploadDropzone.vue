<script setup>
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'

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
    <div class="drop-icon" aria-hidden="true">
      <AppIcon name="upload" :size="18" />
    </div>
    <p class="hint">{{ label }}</p>
    <p v-if="description" class="sub">{{ description }}</p>
  </div>
</template>

<style scoped>
.drop {
  min-height: 148px;
  display: grid;
  place-content: center;
  justify-items: center;
  padding: 28px 20px;
  border: 1px dashed var(--border, #c9c5bd);
  border-radius: 8px;
  background: var(--panel, #fff);
  color: var(--text, #24211d);
  cursor: pointer;
  text-align: center;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.drop:hover,
.drop.dragover {
  border-color: var(--muted, #746f67);
  background: var(--soft, #f6f4ef);
  transform: none;
}

.drop:focus-visible {
  border-color: var(--text, #24211d);
  outline: 2px solid color-mix(in srgb, var(--text, #24211d) 18%, transparent);
  outline-offset: 2px;
  background: var(--soft, #f6f4ef);
  transform: none;
}

.drop.compact {
  min-height: 104px;
  padding: 20px 16px;
}

.drop-icon {
  width: 36px;
  height: 36px;
  margin-bottom: 10px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border, #dedbd4);
  border-radius: 6px;
  background: var(--soft, #f6f4ef);
  box-shadow: none;
  color: var(--text, #24211d);
}

.drop .hint {
  margin: 0 0 4px;
  color: var(--text, #24211d);
  font-size: 13px;
  font-weight: 620;
  line-height: 1.45;
}

.drop .sub {
  max-width: 660px;
  margin: 0;
  color: var(--muted, #746f67);
  font-size: 12px;
  line-height: 1.55;
}

@media (max-width: 580px) {
  .drop {
    min-height: 132px;
    padding: 22px 14px;
  }
}
</style>
