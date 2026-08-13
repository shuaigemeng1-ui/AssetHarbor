<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
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
          <button class="base-modal-close" type="button" aria-label="关闭" @click="close">
            <AppIcon name="close" :size="17" />
          </button>
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
  padding: 24px;
  background: rgb(35 32 27 / 48%);
}

.base-modal-panel {
  width: min(520px, 100%);
  border: 1px solid var(--border, #dedbd4);
  border-radius: 8px;
  background: var(--panel, #fff);
  box-shadow: 0 6px 20px rgb(35 32 27 / 12%);
}

.base-modal-panel.scrollable {
  max-height: min(760px, calc(100vh - 40px));
  overflow: auto;
}

.base-modal-panel.viewport-fit {
  height: min(760px, calc(100vh - 48px));
  height: min(760px, calc(100dvh - 48px));
  max-height: none;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
}

.base-modal-panel.viewport-fit .base-modal-head {
  position: static;
}

.base-modal-panel.viewport-fit .base-modal-content {
  min-height: 0;
  display: grid;
  overflow: hidden;
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
  gap: 16px;
  padding: 18px 20px 15px;
  border-bottom: 1px solid var(--border, #dedbd4);
  background: var(--panel, #fff);
}

.base-modal-head h2 {
  margin: 0;
  color: var(--text, #24211d);
  font-size: 16px;
  font-weight: 650;
  line-height: 1.35;
}

.base-modal-head p {
  margin: 5px 0 0;
  color: var(--muted, #746f67);
  font-size: 12px;
  line-height: 1.55;
}

.base-modal-close {
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--muted, #746f67);
  cursor: pointer;
  transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease;
}

.base-modal-close:hover {
  border-color: var(--border, #dedbd4);
  background: var(--soft, #f5f3ef);
  color: var(--text, #24211d);
}

.base-modal-close:focus-visible {
  outline: 2px solid var(--accent, #36322d);
  outline-offset: 2px;
}

.base-modal-content {
  padding: 18px 20px;
}

.base-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px 18px;
  border-top: 1px solid var(--border, #dedbd4);
}

@media (max-width: 580px) {
  .base-modal-backdrop { padding: 8px; }
  .base-modal-panel { border-radius: 6px; }
  .base-modal-panel.scrollable { max-height: calc(100vh - 16px); }
  .base-modal-panel.viewport-fit {
    height: calc(100vh - 16px);
    height: calc(100dvh - 16px);
  }
  .base-modal-head, .base-modal-content { padding-inline: 16px; }
  .base-modal-footer { padding-inline: 16px; }
}
</style>
