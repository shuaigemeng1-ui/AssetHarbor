<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { acquireModalLock, releaseModalLock } from '../stores/modalLock'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  labelledBy: { type: String, default: 'modal-title' },
  describedBy: { type: String, default: '' },
  dialogRole: { type: String, default: 'dialog' },
  initialFocus: { type: String, default: '' },
  wide: { type: Boolean, default: false },
  fitViewport: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])
const panel = ref(null)
let previousFocus = null
let locked = false

function lockBody() {
  if (locked) return
  locked = true
  acquireModalLock()
}

function unlockBody() {
  if (!locked) return
  locked = false
  releaseModalLock()
}

function close() {
  emit('close')
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    close()
    return
  }
  if (event.key !== 'Tab' || !panel.value) return
  const focusable = [...panel.value.querySelectorAll(
    'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
  )]
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(async () => {
  previousFocus = document.activeElement
  lockBody()
  await nextTick()
  const explicit = props.initialFocus ? panel.value?.querySelector(props.initialFocus) : null
  const preferred = panel.value?.querySelector('[autofocus]')
  const first = panel.value?.querySelector('input, select, textarea, button')
  ;(explicit || preferred || first || panel.value)?.focus()
})

onBeforeUnmount(() => {
  unlockBody()
  previousFocus?.focus?.()
})
</script>

<template>
  <Teleport to="body">
    <div class="base-modal-backdrop" @mousedown.self="close">
      <section
        ref="panel"
        class="base-modal-panel"
        :class="{ wide, scrollable: !fitViewport, 'viewport-fit': fitViewport }"
        :role="dialogRole"
        aria-modal="true"
        :aria-labelledby="labelledBy"
        :aria-describedby="describedBy || (description ? `${labelledBy}-description` : undefined)"
        @keydown="onKeydown"
      >
        <header class="base-modal-head">
          <div>
            <h2 :id="labelledBy">{{ title }}</h2>
            <p v-if="description" :id="`${labelledBy}-description`">{{ description }}</p>
          </div>
          <button class="base-modal-close" type="button" aria-label="关闭" @click="close">×</button>
        </header>
        <div class="base-modal-content"><slot /></div>
        <footer v-if="$slots.footer" class="base-modal-footer"><slot name="footer" /></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.base-modal-backdrop {
  position: fixed;
  z-index: 1100;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgb(15 23 42 / 58%);
  backdrop-filter: blur(6px);
}

.base-modal-panel {
  width: min(520px, 100%);
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--panel);
  box-shadow: 0 30px 90px rgb(15 23 42 / 28%);
}

.base-modal-panel.scrollable {
  max-height: min(760px, calc(100vh - 40px));
  overflow: auto;
}

.base-modal-panel.viewport-fit {
  height: min(760px, calc(100vh - 40px));
  height: min(760px, calc(100dvh - 40px));
  max-height: none;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.base-modal-panel.viewport-fit .base-modal-head {
  position: static;
  border-radius: 19px 19px 0 0;
}

.base-modal-panel.viewport-fit .base-modal-content {
  min-height: 0;
  display: grid;
}

.base-modal-panel.wide {
  width: min(1050px, 100%);
}

.base-modal-head {
  position: sticky;
  z-index: 1;
  top: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 21px 22px 17px;
  border-bottom: 1px solid var(--border);
  background: rgb(255 255 255 / 96%);
  backdrop-filter: blur(10px);
}

.base-modal-head h2 {
  margin: 0;
  font-size: 18px;
  line-height: 1.35;
}

.base-modal-head p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
}

.base-modal-close {
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  color: var(--muted);
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
}

.base-modal-content {
  padding: 20px 22px;
}

.base-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 15px 22px 20px;
  border-top: 1px solid var(--border);
}

@media (max-width: 580px) {
  .base-modal-backdrop { padding: 8px; }
  .base-modal-panel { border-radius: 16px; }
  .base-modal-panel.scrollable { max-height: calc(100vh - 16px); }
  .base-modal-panel.viewport-fit {
    height: calc(100vh - 16px);
    height: calc(100dvh - 16px);
  }
  .base-modal-panel.viewport-fit .base-modal-head { border-radius: 15px 15px 0 0; }
  .base-modal-head, .base-modal-content { padding-inline: 17px; }
  .base-modal-footer { padding-inline: 17px; }
}
</style>
