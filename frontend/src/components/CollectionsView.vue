<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  createMediaGroup,
  deleteMediaGroup,
  listMediaGroupItems,
  listMediaGroups,
  removeMediaGroupItem,
  updateMediaGroup,
} from '../api'
import { confirmAction, toast } from '../stores/feedback'
import BaseModal from './BaseModal.vue'
import CollectionPickerModal from './CollectionPickerModal.vue'
import ImageResult from './ImageResult.vue'
import VideoCard from './VideoCard.vue'
import VideoPlayerModal from './VideoPlayerModal.vue'

const props = defineProps({
  user: { type: Object, required: true },
  teamId: { type: [Number, String], default: null },
  canManage: { type: Boolean, default: false },
})

const groups = ref([])
const groupTotal = ref(0)
const groupQuery = ref('')
const selected = ref(null)
const loadingGroups = ref(true)
const loadingMoreGroups = ref(false)
const groupError = ref('')
const items = ref([])
const itemTotal = ref(0)
const loadingItems = ref(false)
const loadingMore = ref(false)
const itemError = ref('')
const itemKind = ref('all')
const itemQuery = ref('')
const selectedVideo = ref(null)
const groupTarget = ref(null)
const editorMode = ref('')
const savingGroup = ref(false)
const editorError = ref('')
const groupForm = reactive({ name: '', description: '', color: '#2563eb', sortOrder: 0 })
const PAGE_SIZE = 18
let groupSearchTimer
let itemSearchTimer
let loadSequence = 0
let groupLoadGeneration = 0
const GROUP_PAGE_SIZE = 50

const isTeam = computed(() => props.teamId !== null && props.teamId !== undefined)
const hasMoreItems = computed(() => items.value.length < itemTotal.value)
const canEditSelected = computed(() => {
  if (!selected.value) return false
  return props.user.role === 'admin' || props.canManage || selected.value.owner_id === props.user.id
})

function canRemoveMedia() {
  return canEditSelected.value
}

function canEditMedia(item) {
  return props.user.role === 'admin' || props.canManage || item.owner_id === props.user.id
}

function sortGroups() {
  groups.value.sort((left, right) => (
    Number(left.sort_order || 0) - Number(right.sort_order || 0)
    || new Date(right.updated_at || 0) - new Date(left.updated_at || 0)
    || Number(right.id) - Number(left.id)
  ))
}

async function loadGroups({ preserveSelection = true, append = false } = {}) {
  const generation = ++groupLoadGeneration
  const scope = String(props.teamId ?? 'personal')
  const requestQuery = groupQuery.value.trim()
  if (append) loadingMoreGroups.value = true
  else loadingGroups.value = true
  groupError.value = ''
  const previousId = preserveSelection ? selected.value?.id : null
  try {
    const response = await listMediaGroups({
      teamId: props.teamId,
      q: requestQuery,
      limit: GROUP_PAGE_SIZE,
      offset: append ? groups.value.length : 0,
    })
    if (generation !== groupLoadGeneration || scope !== String(props.teamId ?? 'personal') || requestQuery !== groupQuery.value.trim()) return
    groups.value = append ? [...groups.value, ...(response.items || [])] : (response.items || [])
    groupTotal.value = Number(response.total || 0)
    const next = groups.value.find(group => group.id === previousId) || groups.value[0] || null
    if (next?.id !== selected.value?.id) await selectGroup(next)
    else if (next) selected.value = next
    else {
      selected.value = null
      items.value = []
      itemTotal.value = 0
    }
  } catch (error) {
    if (generation === groupLoadGeneration) groupError.value = error.message
  } finally {
    if (generation === groupLoadGeneration) {
      loadingGroups.value = false
      loadingMoreGroups.value = false
    }
  }
}

async function selectGroup(group) {
  selected.value = group
  selectedVideo.value = null
  itemQuery.value = ''
  itemKind.value = 'all'
  items.value = []
  itemTotal.value = 0
  if (group) await loadItems()
}

async function loadItems({ append = false } = {}) {
  if (!selected.value) return
  const sequence = ++loadSequence
  if (append) loadingMore.value = true
  else loadingItems.value = true
  itemError.value = ''
  try {
    const response = await listMediaGroupItems(selected.value.id, {
      kind: itemKind.value,
      q: itemQuery.value.trim(),
      limit: PAGE_SIZE,
      offset: append ? items.value.length : 0,
    })
    if (sequence !== loadSequence) return
    const incoming = response.items || []
    items.value = append ? [...items.value, ...incoming] : incoming
    itemTotal.value = Number(response.total || 0)
  } catch (error) {
    if (sequence === loadSequence) itemError.value = error.message
  } finally {
    if (sequence === loadSequence) {
      loadingItems.value = false
      loadingMore.value = false
    }
  }
}

function onGroupSearch() {
  groupLoadGeneration++
  clearTimeout(groupSearchTimer)
  groupSearchTimer = window.setTimeout(() => loadGroups({ preserveSelection: false }), 250)
}

function onItemSearch() {
  loadSequence++
  clearTimeout(itemSearchTimer)
  itemSearchTimer = window.setTimeout(() => loadItems(), 250)
}

function changeKind(kind) {
  if (itemKind.value === kind) return
  itemKind.value = kind
  loadItems()
}

function resetGroupForm(group = null) {
  Object.assign(groupForm, {
    name: group?.name || '',
    description: group?.description || '',
    color: group?.color || '#2563eb',
    sortOrder: Number(group?.sort_order || 0),
  })
  editorError.value = ''
}

function openCreate() {
  resetGroupForm()
  editorMode.value = 'create'
}

function openEdit() {
  if (!selected.value) return
  resetGroupForm(selected.value)
  editorMode.value = 'edit'
}

function closeEditor() {
  if (savingGroup.value) return
  editorMode.value = ''
  editorError.value = ''
}

async function saveGroup() {
  const name = groupForm.name.trim()
  if (!name) {
    editorError.value = '请输入分组名称'
    return
  }
  savingGroup.value = true
  editorError.value = ''
  try {
    let saved
    if (editorMode.value === 'create') {
      saved = await createMediaGroup({
        name,
        description: groupForm.description.trim(),
        color: groupForm.color,
        sortOrder: Number(groupForm.sortOrder || 0),
        teamId: props.teamId,
      })
      groups.value.unshift(saved)
      sortGroups()
      groupTotal.value++
      await selectGroup(saved)
      toast(`分组「${saved.name}」已创建`, 'success')
    } else {
      saved = await updateMediaGroup(selected.value.id, {
        name,
        description: groupForm.description.trim(),
        color: groupForm.color,
        sortOrder: Number(groupForm.sortOrder || 0),
      })
      const index = groups.value.findIndex(group => group.id === saved.id)
      if (index >= 0) groups.value[index] = saved
      sortGroups()
      selected.value = saved
      toast('分组信息已更新', 'success')
    }
    editorMode.value = ''
  } catch (error) {
    editorError.value = error.message
  } finally {
    savingGroup.value = false
  }
}

async function removeGroup() {
  if (!selected.value) return
  const group = selected.value
  const ok = await confirmAction({
    title: '删除分组',
    message: `删除「${group.name}」？分组内的媒体文件不会被删除。`,
    confirmText: '删除分组',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteMediaGroup(group.id)
    groups.value = groups.value.filter(item => item.id !== group.id)
    groupTotal.value = Math.max(0, groupTotal.value - 1)
    await selectGroup(groups.value[0] || null)
    toast('分组已删除，媒体文件已保留', 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}

async function removeItem(item) {
  const ok = await confirmAction({
    title: '移出分组',
    message: `将「${item.name || item.original_filename || item.code}」移出「${selected.value.name}」？原媒体文件会继续保留。`,
    confirmText: '移出分组',
    danger: true,
  })
  if (!ok) return
  try {
    await removeMediaGroupItem(selected.value.id, item.code)
    items.value = items.value.filter(media => media.code !== item.code)
    itemTotal.value = Math.max(0, itemTotal.value - 1)
    selected.value.item_count = Math.max(0, Number(selected.value.item_count || 0) - 1)
    toast('已移出分组', 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}

function imageItem(item) {
  return { id: `collection-${item.code}`, status: 'done', result: item, file: null }
}

watch(() => props.teamId, () => {
  groupLoadGeneration++
  loadSequence++
  groupQuery.value = ''
  selected.value = null
  items.value = []
  itemTotal.value = 0
  loadGroups({ preserveSelection: false })
})

onMounted(() => loadGroups({ preserveSelection: false }))
onBeforeUnmount(() => {
  clearTimeout(groupSearchTimer)
  clearTimeout(itemSearchTimer)
})
</script>

<template>
  <section class="collections-view">
    <div class="section-heading">
      <div>
        <p class="eyebrow">{{ isTeam ? '团队内容编排' : '媒体整理' }}</p>
        <h2>{{ isTeam ? '团队分组' : '我的分组' }}</h2>
        <p>用分组整理图片和视频，媒体仍保留在原始空间中。</p>
      </div>
      <button class="primary" type="button" @click="openCreate">新建分组</button>
    </div>

    <div class="collections-layout">
      <aside class="collections-sidebar">
        <div class="group-search">
          <input v-model="groupQuery" type="search" placeholder="搜索分组" aria-label="搜索分组" @input="onGroupSearch" />
          <span>{{ groupTotal }}</span>
        </div>
        <p v-if="loadingGroups" class="sidebar-status" aria-live="polite">正在加载分组…</p>
        <p v-else-if="groupError" class="sidebar-status error-text" role="alert">{{ groupError }}</p>
        <div v-else-if="groups.length" class="group-list">
          <button
            v-for="group in groups"
            :key="group.id"
            type="button"
            :class="{ active: selected?.id === group.id }"
            :style="{ '--group-color': group.color || '#2563eb' }"
            @click="selectGroup(group)"
          >
            <span class="folder-copy">
              <strong>{{ group.name }}</strong>
              <small>{{ group.item_count || 0 }} 项</small>
            </span>
          </button>
          <button v-if="groups.length < groupTotal" class="load-groups" type="button" :disabled="loadingMoreGroups" @click="loadGroups({ append: true })">
            {{ loadingMoreGroups ? '加载中…' : `加载更多（${groupTotal - groups.length}）` }}
          </button>
        </div>
        <div v-else class="sidebar-empty">
          <p>{{ groupQuery ? '没有匹配分组' : '还没有分组' }}</p>
          <button v-if="!groupQuery" class="ghost" type="button" @click="openCreate">新建第一个分组</button>
        </div>
      </aside>

      <main v-if="selected" class="collection-detail">
        <header class="collection-head">
          <div class="collection-title" :style="{ '--group-color': selected.color || '#2563eb' }">
            <div>
              <h3>{{ selected.name }}</h3>
              <p>{{ selected.description || '这个分组还没有说明。' }}</p>
              <small>{{ selected.owner_username ? `由 ${selected.owner_username} 创建 · ` : '' }}{{ selected.item_count || 0 }} 项媒体</small>
            </div>
          </div>
          <div v-if="canEditSelected" class="collection-actions">
            <button class="ghost" type="button" @click="openEdit">编辑</button>
            <button class="ghost danger" type="button" @click="removeGroup">删除</button>
          </div>
        </header>

        <div class="collection-toolbar">
          <div class="kind-tabs" role="tablist" aria-label="媒体类型">
            <button v-for="kind in ['all', 'image', 'video']" :key="kind" role="tab" :aria-selected="itemKind === kind" :class="{ active: itemKind === kind }" @click="changeKind(kind)">
              {{ { all: '全部', image: '图片', video: '视频' }[kind] }}
            </button>
          </div>
          <input v-model="itemQuery" class="item-search" type="search" placeholder="搜索组内媒体" aria-label="搜索组内媒体" @input="onItemSearch" />
        </div>

        <p v-if="loadingItems" class="detail-status" aria-live="polite">正在加载媒体…</p>
        <p v-else-if="itemError" class="detail-status error-text" role="alert">加载失败：{{ itemError }}</p>
        <template v-else>
          <div v-if="items.length" class="media-grid collection-media-grid">
            <template v-for="item in items" :key="item.code">
              <ImageResult
                v-if="item.media_kind === 'image'"
                :item="imageItem(item)"
                :editable="canEditMedia(item)"
                groupable
                :removable="canRemoveMedia(item)"
                @add-to-group="groupTarget = item"
                @remove="removeItem(item)"
              />
              <VideoCard
                v-else
                :item="item"
                :editable="canEditMedia(item)"
                groupable
                :removable="canRemoveMedia(item)"
                @add-to-group="groupTarget = item"
                @play="selectedVideo = item"
                @remove="removeItem(item)"
              />
            </template>
          </div>
          <div v-else class="collection-empty">
            <h3>{{ itemQuery ? '没有匹配媒体' : '这个分组还是空的' }}</h3>
            <p>{{ itemQuery ? '换个关键词或类型试试看。' : '在图片或视频卡片中点击“加入分组”。' }}</p>
          </div>
          <div v-if="hasMoreItems" class="load-more-wrap">
            <button class="secondary" :disabled="loadingMore" @click="loadItems({ append: true })">{{ loadingMore ? '加载中…' : `加载更多（还有 ${itemTotal - items.length} 项）` }}</button>
          </div>
        </template>
      </main>

      <main v-else class="collection-detail detail-placeholder">
        <h3>{{ loadingGroups ? '正在加载…' : '选择或创建一个分组' }}</h3>
        <p>将相关图片和视频集中到一起，查找更轻松。</p>
      </main>
    </div>

    <BaseModal
      v-if="editorMode"
      :title="editorMode === 'create' ? '新建分组' : '编辑分组'"
      description="分组只负责整理媒体，不会复制或移动原文件。"
      labelled-by="group-editor-title"
      @close="closeEditor"
    >
      <form id="group-editor-form" class="group-editor" @submit.prevent="saveGroup">
        <label>
          <span>分组名称</span>
          <input v-model="groupForm.name" autofocus maxlength="100" placeholder="例如：品牌视觉" />
        </label>
        <label>
          <span>说明</span>
          <textarea v-model="groupForm.description" rows="3" maxlength="500" placeholder="简要说明这个分组存放什么内容"></textarea>
        </label>
        <div class="editor-row">
          <label>
            <span>标识色</span>
            <input v-model="groupForm.color" type="color" aria-label="分组标识色" />
          </label>
          <label>
            <span>排序值</span>
            <input v-model.number="groupForm.sortOrder" type="number" min="-1000000" max="1000000" />
          </label>
        </div>
        <p v-if="editorError" class="error-text" role="alert">{{ editorError }}</p>
      </form>
      <template #footer>
        <button class="ghost" type="button" :disabled="savingGroup" @click="closeEditor">取消</button>
        <button class="primary" type="submit" form="group-editor-form" :disabled="savingGroup || !groupForm.name.trim()">{{ savingGroup ? '保存中…' : '保存分组' }}</button>
      </template>
    </BaseModal>

    <CollectionPickerModal
      v-if="groupTarget"
      :media="groupTarget"
      :team-id="teamId"
      :user-id="user.id"
      :can-manage="canManage || user.role === 'admin'"
      @close="groupTarget = null"
    />

    <VideoPlayerModal v-if="selectedVideo" :item="selectedVideo" @close="selectedVideo = null" />
  </section>
</template>

<style scoped>
.collections-view > .section-heading {
  margin-bottom: 20px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border);
}

.section-heading h2 {
  margin: 0 0 5px;
  font-size: 24px;
  font-weight: 680;
  letter-spacing: -.025em;
}

.section-heading .eyebrow {
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 10px;
  letter-spacing: .1em;
}

.section-heading p:not(.eyebrow) {
  color: var(--muted);
  font-size: 12px;
}

.section-heading > .primary {
  min-height: 38px;
  border-radius: 5px;
  padding: 0 13px;
  box-shadow: none;
  font-size: 12px;
}

.collections-layout {
  min-height: 560px;
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
}

.collections-sidebar {
  min-width: 0;
  border-right: 1px solid var(--border);
  background: #faf9f7;
}

.group-search {
  position: relative;
  padding: 14px;
  border-bottom: 1px solid var(--border);
}

.group-search input,
.item-search {
  min-height: 38px;
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 8px 10px;
  background: #fff;
  color: var(--text);
  box-shadow: none;
  font-size: 12px;
  outline: 0;
}

.group-search input:focus,
.item-search:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgb(11 99 229 / 10%);
}

.group-search input {
  width: 100%;
  padding-right: 42px;
}

.group-search > span {
  position: absolute;
  top: 50%;
  right: 24px;
  min-width: 18px;
  color: var(--muted);
  font-size: 10px;
  text-align: center;
  transform: translateY(-50%);
}

.group-list {
  display: grid;
  gap: 2px;
  padding: 8px;
}

.group-list button {
  --group-color: var(--accent);
  width: 100%;
  min-height: 46px;
  display: flex;
  align-items: center;
  border: 1px solid transparent;
  border-left: 3px solid transparent;
  border-radius: 4px;
  padding: 7px 9px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.group-list button:hover {
  background: #f2f0ec;
}

.group-list button.active {
  border-color: var(--border);
  border-left-color: var(--group-color);
  background: #fff;
}

.group-list .load-groups {
  justify-content: center;
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 11px;
}

.folder-copy {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 2px;
}

.folder-copy strong {
  overflow: hidden;
  color: var(--text);
  font-size: 12px;
  font-weight: 620;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.folder-copy small {
  color: var(--muted);
  font-size: 10px;
}

.sidebar-status,
.sidebar-empty {
  padding: 36px 14px;
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}

.sidebar-empty p {
  margin: 0 0 10px;
}

.collection-detail {
  min-width: 0;
  padding: 20px;
  background: #fff;
}

.collection-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 17px;
  border-bottom: 1px solid var(--border);
}

.collection-title {
  --group-color: var(--accent);
  min-width: 0;
  border-left: 3px solid var(--group-color);
  padding-left: 12px;
}

.collection-title h3 {
  margin: 0 0 3px;
  font-size: 18px;
  font-weight: 660;
}

.collection-title p {
  margin: 0 0 4px;
  color: var(--muted);
  font-size: 12px;
}

.collection-title small {
  color: var(--muted-light);
  font-size: 10px;
}

.collection-actions {
  display: flex;
  gap: 5px;
}

.collection-actions button,
.sidebar-empty button {
  border-radius: 4px;
}

.collection-toolbar {
  margin: 16px 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.kind-tabs {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid var(--border);
}

.kind-tabs button {
  margin-bottom: -1px;
  border: 0;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  padding: 7px 11px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 11px;
}

.kind-tabs button.active {
  border-bottom-color: var(--text);
  background: transparent;
  color: var(--text);
  font-weight: 650;
}

.item-search {
  width: min(260px, 100%);
}

.detail-status {
  min-height: 260px;
  display: grid;
  place-content: center;
  color: var(--muted);
  font-size: 12px;
}

.collection-media-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

:deep(.media-card) {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  box-shadow: none;
}

.collection-empty,
.detail-placeholder {
  min-height: 380px;
  display: grid;
  place-content: center;
  justify-items: center;
  padding: 24px;
  background: var(--panel-soft);
  text-align: center;
}

.collection-empty h3,
.detail-placeholder h3 {
  margin: 0 0 5px;
  font-size: 14px;
  font-weight: 630;
}

.collection-empty p,
.detail-placeholder p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}

.group-editor {
  display: grid;
  gap: 14px;
}

.group-editor label {
  display: grid;
  gap: 5px;
  color: var(--text);
  font-size: 11px;
  font-weight: 650;
}

.group-editor input,
.group-editor textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 9px 10px;
  background: #fff;
  color: var(--text);
  box-shadow: none;
  outline: 0;
  resize: vertical;
}

.group-editor input:focus,
.group-editor textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgb(11 99 229 / 10%);
}

.group-editor input {
  min-height: 40px;
}

.group-editor input[type='color'] {
  width: 58px;
  padding: 4px;
}

.editor-row {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 15px;
}

.group-editor .error-text {
  margin: 0;
  font-size: 12px;
}

@media (max-width: 1000px) {
  .collection-media-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 840px) {
  .collections-layout { grid-template-columns: 1fr; }
  .collections-sidebar { border-right: 0; border-bottom: 1px solid var(--border); }
  .group-list { grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); }
}

@media (max-width: 580px) {
  .section-heading,
  .collection-head,
  .collection-toolbar { flex-direction: column; }
  .section-heading > button { align-self: flex-start; }
  .collection-actions,
  .item-search { width: 100%; }
  .collection-media-grid { grid-template-columns: 1fr; }
}
</style>
