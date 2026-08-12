<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  labelledBy: { type: String, default: 'modal-title' },
})

const emit = defineEmits(['close'])
const panel = ref(null)
let previousFocus = null

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
  document.body.classList.add('modal-open')
  await nextTick()
  const preferred = panel.value?.querySelector('[autofocus]')
  const first = panel.value?.querySelector('input, select, textarea, button')
  ;(preferred || first || panel.value)?.focus()
})

onBeforeUnmount(() => {
  document.body.classList.remove('modal-open')
  previousFocus?.focus?.()
})
</script>

<template>
  <Teleport to="body">
    <div class="base-modal-backdrop" @mousedown.self="close">
      <section
        ref="panel"
        class="base-modal-panel"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="labelledBy"
        @keydown="onKeydown"
      >
        <header class="base-modal-head">
          <div>
            <h2 :id="labelledBy">{{ title }}</h2>
            <p v-if="description">{{ description }}</p>
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
  max-height: min(760px, calc(100vh - 40px));
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--panel);
  box-shadow: 0 30px 90px rgb(15 23 42 / 28%);
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
  .base-modal-panel { max-height: calc(100vh - 16px); border-radius: 16px; }
  .base-modal-head, .base-modal-content { padding-inline: 17px; }
  .base-modal-footer { padding-inline: 17px; }
}
</style>
