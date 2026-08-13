<script setup>
import { dismissToast, feedback, resolveConfirm } from '../stores/feedback'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'
</script>

<template>
  <div class="toast-region" aria-live="polite" aria-atomic="true">
    <div v-for="item in feedback.toasts" :key="item.id" class="toast" :class="`toast-${item.type}`">
      <span>{{ item.message }}</span>
      <button aria-label="关闭提示" @click="dismissToast(item.id)"><AppIcon name="close" size="15" /></button>
    </div>
  </div>

  <BaseModal
    v-if="feedback.confirm"
    :title="feedback.confirm.title"
    labelled-by="confirm-title"
    described-by="confirm-message"
    dialog-role="alertdialog"
    initial-focus="[data-confirm-cancel]"
    @close="resolveConfirm(false)"
  >
    <div class="confirm-body">
      <div class="dialog-icon" :class="{ danger: feedback.confirm.danger }"><AppIcon name="alert" size="19" /></div>
      <p id="confirm-message">{{ feedback.confirm.message }}</p>
      <div class="dialog-actions">
        <button data-confirm-cancel class="ghost" @click="resolveConfirm(false)">取消</button>
        <button class="primary" :class="{ danger: feedback.confirm.danger }" @click="resolveConfirm(true)">
          {{ feedback.confirm.confirmText }}
        </button>
      </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.confirm-body { text-align: center; }
.confirm-body > p { margin: 0 0 20px; color: var(--muted); font-size: 13px; }
</style>
