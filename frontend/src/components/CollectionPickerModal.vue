<script setup>
import { computed, onMounted, ref } from 'vue'
import { addMediaGroupItems, createMediaGroup, listMediaGroups } from '../api'
import { toast } from '../stores/feedback'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'

const props = defineProps({
  media: { type: Object, required: true },
  teamId: { type: [Number, String], default: null },
  userId: { type: [Number, String], required: true },
  canManage: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'added'])
const groups = ref([])
const selectedId = ref(null)
const loading = ref(true)
const loadingMore = ref(false)
const total = ref(0)
const fetchedCount = ref(0)
const query = ref('')
const saving = ref(false)
const error = ref('')
const creating = ref(false)
const newName = ref('')
const newColor = ref('#2563eb')
let loadGeneration = 0

const title = computed(() => props.media.name || props.media.original_filename || props.media.code)

async function loadGroups({ append = false } = {}) {
  const generation = ++loadGeneration
  const requestQuery = query.value.trim()
  if (append) loadingMore.value = true
  else loading.value = true
  error.value = ''
  try {
    const response = await listMediaGroups({ teamId: props.teamId, q: requestQuery, limit: 50, offset: append ? fetchedCount.value : 0 })
    if (generation !== loadGeneration || requestQuery !== query.value.trim()) return
    const incoming = (response.items || []).filter(group => (
      props.canManage || String(group.owner_id) === String(props.userId)
    ))
    groups.value = append ? [...groups.value, ...incoming] : incoming
    total.value = Number(response.total || 0)
    fetchedCount.value = (append ? fetchedCount.value : 0) + (response.items || []).length
    if (!groups.value.some(group => group.id === selectedId.value)) selectedId.value = groups.value[0]?.id ?? null
  } catch (cause) {
    if (generation === loadGeneration) error.value = cause.message
  } finally {
    if (generation === loadGeneration) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

onMounted(loadGroups)

async function addToSelected() {
  if (!selectedId.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const result = await addMediaGroupItems(selectedId.value, [props.media.code])
    const group = groups.value.find(item => item.id === selectedId.value)
    if (result.added) {
      if (group) group.item_count = Number(group.item_count || 0) + 1
      toast(`已加入「${group?.name || '分组'}」`, 'success')
      emit('added', { groupId: selectedId.value, group: result.group || group })
    } else {
      toast('这个媒体已在所选分组中', 'info')
    }
    emit('close')
  } catch (cause) {
    error.value = cause.message
  } finally {
    saving.value = false
  }
}

async function createAndAdd() {
  const name = newName.value.trim()
  if (!name || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const group = await createMediaGroup({
      name,
      color: newColor.value,
      teamId: props.teamId,
      codes: [props.media.code],
    })
    groups.value.unshift(group)
    selectedId.value = group.id
    toast(`已新建「${group.name}」并加入媒体`, 'success')
    emit('added', { groupId: group.id, group })
    emit('close')
  } catch (cause) {
    error.value = cause.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <BaseModal
    title="加入分组"
    :description="`选择要收纳「${title}」的分组。`"
    labelled-by="collection-picker-title"
    @close="emit('close')"
  >
    <div v-if="loading" class="picker-status" aria-live="polite">正在加载分组…</div>
    <template v-else>
      <form class="picker-search" @submit.prevent="loadGroups()">
        <input v-model="query" type="search" placeholder="搜索分组" aria-label="搜索可加入的分组" />
        <button class="ghost" type="submit">搜索</button>
      </form>
      <div v-if="groups.length" class="picker-groups" role="radiogroup" aria-label="选择分组">
        <label v-for="group in groups" :key="group.id" :class="{ selected: selectedId === group.id }">
          <input v-model="selectedId" type="radio" name="media-group" :value="group.id" />
          <span class="group-color" :style="{ background: group.color || '#2563eb' }"></span>
          <span class="group-copy">
            <strong>{{ group.name }}</strong>
            <small>{{ group.item_count || 0 }} 项{{ group.description ? ` · ${group.description}` : '' }}</small>
          </span>
          <span class="check">✓</span>
        </label>
        <button v-if="fetchedCount < total" class="load-more-groups" type="button" :disabled="loadingMore" @click="loadGroups({ append: true })">
          {{ loadingMore ? '加载中…' : `继续查找分组（还有 ${total - fetchedCount} 个）` }}
        </button>
      </div>
      <div v-else-if="!creating" class="picker-empty">
        <span>◇</span>
        <strong>{{ fetchedCount < total ? '这一页没有可管理的分组' : '还没有分组' }}</strong>
        <small>{{ fetchedCount < total ? '继续查找你创建或有权管理的分组。' : '新建一个分组，之后就能快速归档媒体。' }}</small>
        <button v-if="fetchedCount < total" class="ghost" type="button" :disabled="loadingMore" @click="loadGroups({ append: true })">
          {{ loadingMore ? '查找中…' : `继续查找（还有 ${total - fetchedCount} 个）` }}
        </button>
      </div>

      <form v-if="creating" class="quick-create" @submit.prevent="createAndAdd">
        <label>
          <span>分组名称</span>
          <input v-model="newName" autofocus maxlength="100" placeholder="例如：产品素材" />
        </label>
        <label class="color-field">
          <span>标识色</span>
          <input v-model="newColor" type="color" aria-label="分组标识色" />
        </label>
        <div class="quick-actions">
          <button class="ghost" type="button" :disabled="saving" @click="creating = false">取消</button>
          <button class="primary" :disabled="!newName.trim() || saving">{{ saving ? '创建中…' : '新建并加入' }}</button>
        </div>
      </form>

      <p v-if="error" class="picker-error" role="alert">{{ error }}</p>
    </template>

    <template #footer>
      <button v-if="!creating" class="ghost" type="button" @click="creating = true">
        <AppIcon name="plus" size="14" />
        新建分组
      </button>
      <span class="footer-spacer"></span>
      <button class="ghost" type="button" :disabled="saving" @click="emit('close')">取消</button>
      <button v-if="!creating" class="primary" type="button" :disabled="!selectedId || saving" @click="addToSelected">
        {{ saving ? '正在加入…' : '加入所选分组' }}
      </button>
    </template>
  </BaseModal>
</template>

<style scoped>
.picker-status,
.picker-empty {
  min-height: 180px;
  display: grid;
  place-content: center;
  justify-items: center;
  color: var(--muted);
  text-align: center;
}

.picker-empty span { margin-bottom: 7px; color: var(--accent); font-size: 28px; }
.picker-empty strong { color: var(--text); }
.picker-empty small { margin-top: 4px; }
.picker-empty button { margin-top: 12px; }
.picker-groups { display: grid; gap: 8px; }
.picker-search { margin-bottom: 12px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 7px; }
.picker-search input { min-height: 38px; border: 1px solid var(--border); border-radius: 9px; padding: 7px 10px; outline: 0; }
.picker-search input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgb(37 99 235 / 10%); }
.picker-groups label {
  display: flex;
  align-items: center;
  gap: 11px;
  min-height: 58px;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 9px 11px;
  background: var(--panel);
  cursor: pointer;
  transition: 150ms ease;
}
.picker-groups label:hover { border-color: var(--border-strong); background: var(--panel-soft); }
.picker-groups label.selected { border-color: #a7c1fc; background: var(--accent-soft); }
.picker-groups input { position: absolute; opacity: 0; pointer-events: none; }
.group-color { width: 10px; height: 32px; flex: 0 0 auto; border-radius: 999px; }
.group-copy { min-width: 0; flex: 1; display: grid; }
.group-copy strong { overflow: hidden; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.group-copy small { overflow: hidden; color: var(--muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.check {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 50%;
  color: transparent;
  font-size: 12px;
}
.selected .check { border-color: var(--accent); background: var(--accent); color: #fff; }
.picker-groups .load-more-groups { min-height: 40px; border: 1px solid var(--border); border-radius: 10px; background: var(--panel-soft); color: var(--accent); cursor: pointer; font-size: 13px; }
.quick-create { display: grid; grid-template-columns: 1fr auto; gap: 13px; }
.quick-create label { display: grid; gap: 5px; color: var(--text); font-size: 13px; font-weight: 650; }
.quick-create input[type='text'],
.quick-create input:not([type]) {
  min-height: 42px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 11px;
}
.color-field input { width: 52px; height: 42px; border: 1px solid var(--border); border-radius: 10px; padding: 4px; background: #fff; }
.quick-actions { grid-column: 1 / -1; display: flex; justify-content: flex-end; gap: 8px; }
.picker-error { margin: 13px 0 0; color: var(--danger); font-size: 13px; }
.footer-spacer { flex: 1; }

@media (max-width: 480px) {
  .quick-create { grid-template-columns: 1fr; }
  .color-field { grid-row: 2; }
  .quick-actions { grid-column: 1; }
}
</style>
