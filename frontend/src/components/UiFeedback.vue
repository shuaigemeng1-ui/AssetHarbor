<script setup>
import { nextTick, ref, watch } from 'vue'
import { dismissToast, feedback, resolveConfirm } from '../stores/feedback'

const confirmButton = ref(null)

watch(() => feedback.confirm, async value => {
  if (value) {
    await nextTick()
    confirmButton.value?.focus()
  }
})
</script>

<template>
  <div class="toast-region" aria-live="polite" aria-atomic="true">
    <div v-for="item in feedback.toasts" :key="item.id" class="toast" :class="`toast-${item.type}`">
      <span>{{ item.message }}</span>
      <button aria-label="关闭提示" @click="dismissToast(item.id)">×</button>
    </div>
  </div>

  <div v-if="feedback.confirm" class="modal-backdrop" @click.self="resolveConfirm(false)">
    <section class="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message" @keydown.esc="resolveConfirm(false)">
      <div class="dialog-icon" :class="{ danger: feedback.confirm.danger }">{{ feedback.confirm.danger ? '!' : '?' }}</div>
      <h2 id="confirm-title">{{ feedback.confirm.title }}</h2>
      <p id="confirm-message">{{ feedback.confirm.message }}</p>
      <div class="dialog-actions">
        <button class="ghost" @click="resolveConfirm(false)">取消</button>
        <button ref="confirmButton" class="primary" :class="{ danger: feedback.confirm.danger }" @click="resolveConfirm(true)">
          {{ feedback.confirm.confirmText }}
        </button>
      </div>
    </section>
  </div>
</template>
