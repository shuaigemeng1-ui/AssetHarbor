<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getSignedLink, revokeMediaLinks, updateImage } from '../api'
import { toast } from '../stores/feedback'
import { copyText } from '../utils/clipboard'
import { formatBytes, formatDate } from '../utils/format'
import AppIcon from './AppIcon.vue'
import BaseModal from './BaseModal.vue'
import CollectionPickerModal from './CollectionPickerModal.vue'

const props = defineProps({
  item: { type: Object, required: true },
  user: { type: Object, required: true },
  canManage: { type: Boolean, default: false },
  canManageGroups: { type: Boolean, default: false },
  isGlobalAdmin: { type: Boolean, default: false },
  teamId: { type: [Number, String], default: null },
  groupable: { type: Boolean, default: true },
})

const emit = defineEmits(['delete', 'toggle-visibility', 'updated'])

const signedUrl = ref('')
const signedLinkError = ref('')
const previewFailed = ref(false)
const signing = ref(false)
const copying = ref(false)
const copied = ref(false)
const linkTtl = ref(3600)
const linkExpiresAt = ref('')
const revoking = ref(false)
const editing = ref(false)
const editName = ref('')
const editSaving = ref(false)
const editError = ref('')
const localName = ref('')
const groupPickerOpen = ref(false)
const panel = ref(null)
let signedLinkGeneration = 0
let copiedTimer = null

defineExpose({
  focus: () => panel.value?.focus(),
  getElement: () => panel.value,
})

const isPrivate = computed(() => props.item.visibility === 'private')
const effectiveTeamId = computed(() => props.item.team_id ?? props.teamId)
const canEdit = computed(() => (
  props.isGlobalAdmin
  || props.canManage
  || String(props.item.owner_id) === String(props.user.id)
))
const displayName = computed(() => (
  localName.value.trim()
  || props.item.original_filename
  || (isPdf.value ? '未命名文档' : '未命名图片')
))
const isPdf = computed(() => (
  props.item.content_type === 'application/pdf'
  || String(localName.value || props.item.original_filename || '').toLowerCase().endsWith('.pdf')
))
const activeUrl = computed(() => (isPrivate.value ? signedUrl.value : props.item.url || ''))
const ownerLabel = computed(() => (
  props.item.owner_username
  || (props.item.owner_id !== null && props.item.owner_id !== undefined
    ? `用户 #${props.item.owner_id}`
    : '')
))
const scopeLabel = computed(() => {
  if (effectiveTeamId.value !== null && effectiveTeamId.value !== undefined) {
    return props.item.team_name || `团队空间 #${effectiveTeamId.value}`
  }
  return props.isGlobalAdmin ? '个人空间' : ''
})
const mediaForGrouping = computed(() => ({
  ...props.item,
  name: localName.value || props.item.name,
}))

watch(() => [props.item.code, props.item.name], ([code, name], previous = []) => {
  if (code !== previous[0] || name !== previous[1]) localName.value = name || ''
}, { immediate: true })

async function refreshSignedLink() {
  const generation = ++signedLinkGeneration
  signedUrl.value = ''
  signedLinkError.value = ''
  previewFailed.value = false
  if (!isPrivate.value || !props.item.code) return ''

  signing.value = true
  try {
    const response = await getSignedLink(props.item.code, linkTtl.value)
    if (generation !== signedLinkGeneration) return ''
    signedUrl.value = response.url || ''
    linkExpiresAt.value = response.expires_at ? formatDate(response.expires_at) : ''
    if (!signedUrl.value) signedLinkError.value = '签名链接暂不可用'
    return signedUrl.value
  } catch (error) {
    if (generation === signedLinkGeneration) {
      signedLinkError.value = error.message || '签名链接暂不可用'
    }
    return ''
  } finally {
    if (generation === signedLinkGeneration) signing.value = false
  }
}

async function retryPreview() {
  if (isPrivate.value) await refreshSignedLink()
  else previewFailed.value = false
}

watch(() => [props.item.code, props.item.visibility], () => {
  copied.value = false
  if (isPrivate.value) refreshSignedLink()
  else {
    signedLinkGeneration++
    signedUrl.value = ''
    signedLinkError.value = ''
    linkExpiresAt.value = ''
    previewFailed.value = false
    signing.value = false
  }
}, { immediate: true })

watch(linkTtl, () => {
  if (isPrivate.value && signedUrl.value) refreshSignedLink()
})

onBeforeUnmount(() => {
  signedLinkGeneration++
  if (copiedTimer) window.clearTimeout(copiedTimer)
})

async function revokeLinks() {
  if (revoking.value || !canEdit.value) return
  revoking.value = true
  try {
    await revokeMediaLinks(props.item.code)
    toast('已撤销全部历史分享链接', 'success')
    await refreshSignedLink()
  } catch (error) {
    toast(error.message || '撤销失败，请稍后重试', 'error')
  } finally {
    revoking.value = false
  }
}

async function copyUrl() {
  if (copying.value) return
  copying.value = true
  try {
    const target = isPrivate.value ? await refreshSignedLink() : props.item.url
    const ok = target && await copyText(target)
    if (!ok) {
      toast('复制失败，请稍后重试', 'error')
      return
    }
    copied.value = true
    toast(isPrivate.value ? '限时签名链接已复制' : (isPdf.value ? '文档链接已复制' : '图片链接已复制'), 'success')
    if (copiedTimer) window.clearTimeout(copiedTimer)
    copiedTimer = window.setTimeout(() => { copied.value = false }, 1400)
  } catch {
    toast('复制失败，请稍后重试', 'error')
  } finally {
    copying.value = false
  }
}

function openEditor() {
  editName.value = displayName.value
  editError.value = ''
  editing.value = true
}

async function saveName() {
  const name = editName.value.trim()
  if (!name) {
    editError.value = '名称不能为空'
    return
  }
  if (editSaving.value) return
  editSaving.value = true
  editError.value = ''
  try {
    const updated = await updateImage(props.item.code, { name })
    localName.value = updated.name || name
    editing.value = false
    emit('updated', updated)
    toast(isPdf.value ? '文档名称已更新' : '图片名称已更新', 'success')
  } catch (error) {
    editError.value = error.message || '保存失败，请稍后重试'
  } finally {
    editSaving.value = false
  }
}
</script>

<template>
  <aside ref="panel" class="image-inspector" :aria-label="isPdf ? 'PDF 文档详情' : '图片详情'">
    <header class="inspector-heading">
      <h2>{{ isPdf ? 'PDF 文档详情' : '图片详情' }}</h2>
    </header>

    <div class="inspector-preview" :class="{ 'is-pdf-inspector': isPdf }">
      <div v-if="isPdf && activeUrl && !previewFailed" class="pdf-container">
        <iframe
          :src="activeUrl"
          :title="displayName"
          class="pdf-preview-frame"
        />
        <div class="pdf-toolbar">
          <a :href="activeUrl" target="_blank" rel="noopener noreferrer" class="pdf-open-btn">
            <AppIcon name="external-link" size="13" />
            新窗口查看原件
          </a>
        </div>
      </div>
      <img
        v-else-if="!isPdf && activeUrl && !previewFailed"
        :src="activeUrl"
        :alt="displayName"
        decoding="async"
        referrerpolicy="no-referrer"
        @error="previewFailed = true"
      />
      <div v-else class="preview-empty" role="status">
        <AppIcon :name="isPdf ? 'pdf' : (isPrivate ? 'lock' : 'image')" size="26" />
        <strong>{{ signing ? '正在加载预览' : (isPdf ? 'PDF 文档' : '预览暂不可用') }}</strong>
        <small v-if="signedLinkError">{{ signedLinkError }}</small>
        <button v-if="!signing && !isPdf" type="button" @click="retryPreview">重试预览</button>
      </div>
    </div>

    <section class="inspector-section" aria-labelledby="image-inspector-info">
      <h3 id="image-inspector-info">文件信息</h3>
      <dl class="metadata-list">
        <div>
          <dt>显示名称</dt>
          <dd>{{ displayName }}</dd>
        </div>
        <div>
          <dt>原文件名</dt>
          <dd>{{ item.original_filename || '—' }}</dd>
        </div>
        <div>
          <dt>文件大小</dt>
          <dd>{{ formatBytes(item.size) }}</dd>
        </div>
        <div>
          <dt>文件类型</dt>
          <dd>{{ item.content_type || '—' }}</dd>
        </div>
        <div>
          <dt>短码</dt>
          <dd class="code-value">{{ item.code || '—' }}</dd>
        </div>
        <div>
          <dt>访问权限</dt>
          <dd>{{ isPrivate ? '私密访问' : '公开访问' }}</dd>
        </div>
        <div v-if="ownerLabel">
          <dt>属主</dt>
          <dd>{{ ownerLabel }}</dd>
        </div>
        <div v-if="scopeLabel">
          <dt>空间</dt>
          <dd>{{ scopeLabel }}</dd>
        </div>
      </dl>
    </section>

    <section class="inspector-section" aria-labelledby="image-inspector-link">
      <div class="section-title-row">
        <h3 id="image-inspector-link">{{ isPrivate ? '限时访问链接' : (isPdf ? '文档链接' : '图片链接') }}</h3>
        <span v-if="isPrivate">复制时自动刷新</span>
      </div>
      <div class="link-field" :title="activeUrl">
        {{ activeUrl || (signing ? '正在生成限时签名链接…' : '链接暂不可用') }}
      </div>
        <div v-if="isPrivate" class="link-settings">
          <label>
            <span>有效期</span>
            <select v-model="linkTtl" class="ttl-select" :disabled="signing" aria-label="签名链接有效期">
              <option :value="3600">1 小时</option>
              <option :value="86400">1 天</option>
              <option :value="604800">7 天</option>
            </select>
          </label>
          <small v-if="linkExpiresAt">到期时间：{{ linkExpiresAt }}</small>
        </div>
        <button
          v-if="isPrivate && canEdit"
          class="inspector-button danger-action"
          type="button"
          :disabled="revoking || signing"
          @click="revokeLinks"
        >
          <AppIcon name="delete" size="16" />
          {{ revoking ? '撤销中…' : '撤销全部历史分享链接' }}
        </button>

      <button
        class="inspector-button primary-action"
        type="button"
        :disabled="copying || signing || (!isPrivate && !item.url)"
        @click="copyUrl"
      >
        <AppIcon :name="copied ? 'check' : 'copy'" size="16" />
        {{ copying ? '复制中…' : copied ? '已复制' : (isPdf ? '复制文档链接' : '复制链接') }}
      </button>
    </section>

    <section v-if="canEdit || groupable" class="inspector-section inspector-actions" aria-labelledby="image-inspector-actions">
      <h3 id="image-inspector-actions">管理</h3>
      <div class="action-grid">
        <button v-if="canEdit" class="inspector-button" type="button" @click="emit('toggle-visibility', item)">
          <AppIcon :name="isPrivate ? 'public' : 'private'" size="16" />
          {{ isPrivate ? '设为公开' : '设为私密' }}
        </button>
        <button v-if="canEdit" class="inspector-button" type="button" @click="openEditor">
          <AppIcon name="edit" size="16" />
          重命名
        </button>
        <button v-if="groupable" class="inspector-button" type="button" @click="groupPickerOpen = true">
          <AppIcon name="collection" size="16" />
          加入分组
        </button>
        <button v-if="canEdit" class="inspector-button danger-action" type="button" @click="emit('delete', item)">
          <AppIcon name="delete" size="16" />
          {{ isPdf ? '删除文档' : '删除图片' }}
        </button>
      </div>
    </section>

    <BaseModal
      v-if="editing"
      :title="isPdf ? '重命名文档' : '重命名图片'"
      description="仅修改媒体库中的显示名称，原始文件名保持不变。"
      labelled-by="inspector-rename-image-title"
      @close="editing = false"
    >
      <form id="inspector-rename-image-form" class="rename-form" @submit.prevent="saveName">
        <label for="inspector-rename-image-input">显示名称</label>
        <input id="inspector-rename-image-input" v-model="editName" autofocus maxlength="255" />
        <p v-if="editError" class="form-error" role="alert">{{ editError }}</p>
      </form>
      <template #footer>
        <button class="ghost" type="button" :disabled="editSaving" @click="editing = false">取消</button>
        <button class="primary" type="submit" form="inspector-rename-image-form" :disabled="editSaving || !editName.trim()">
          {{ editSaving ? '保存中…' : '保存' }}
        </button>
      </template>
    </BaseModal>

    <CollectionPickerModal
      v-if="groupPickerOpen"
      :media="mediaForGrouping"
      :team-id="effectiveTeamId"
      :user-id="user.id"
      :can-manage="canManageGroups"
      @close="groupPickerOpen = false"
    />
  </aside>
</template>

<style scoped>
.image-inspector {
  position: sticky;
  top: 24px;
  width: min(380px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
  flex: 0 0 380px;
  align-self: flex-start;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
  color: var(--text);
}

.image-inspector:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.inspector-heading {
  padding: 18px;
  border-bottom: 1px solid var(--border);
}

.inspector-heading h2 {
  margin: 0;
  font-size: 16px;
  line-height: 1.35;
}

.heading-copy {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.heading-icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--muted);
}

.heading-copy p,
.heading-copy h2 {
  margin: 0;
}

.heading-copy p {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.3;
}

.heading-copy h2 {
  overflow: hidden;
  margin-top: 2px;
  font-size: 16px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.visibility-badge {
  flex: 0 0 auto;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 8px;
  color: var(--muted);
  background: var(--panel-soft);
  font-size: 12px;
  font-weight: 650;
}

.visibility-badge.public {
  border-color: #bbf7d0;
  color: #166534;
  background: #f0fdf4;
}

.inspector-preview {
  aspect-ratio: 4 / 3;
  margin: 18px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-soft);
}

.inspector-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.inspector-preview.is-pdf-inspector {
  min-height: 260px;
  height: 320px;
}

.pdf-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.pdf-preview-frame {
  width: 100%;
  flex: 1;
  border: 0;
}

.pdf-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 6px 10px;
  border-top: 1px solid var(--border);
  background: var(--panel-soft);
}

.pdf-open-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
}

.pdf-open-btn:hover {
  text-decoration: underline;
}

.preview-empty {
  max-width: 240px;
  display: grid;
  justify-items: center;
  gap: 7px;
  padding: 20px;
  color: var(--muted);
  text-align: center;
}

.preview-empty strong {
  color: var(--text);
  font-size: 14px;
}

.preview-empty small {
  font-size: 12px;
}

.preview-empty button {
  border: 0;
  padding: 3px 5px;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
  font: inherit;
  font-size: 14px;
}

.inspector-section {
  padding: 0 18px 18px;
}

.inspector-section + .inspector-section {
  padding-top: 18px;
  border-top: 1px solid var(--border);
}

.inspector-section h3 {
  margin: 0 0 11px;
  font-size: 16px;
  line-height: 1.4;
}

.metadata-list {
  margin: 0;
}

.metadata-list > div {
  min-height: 32px;
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  align-items: baseline;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  padding: 7px 0;
}

.metadata-list > div:last-child {
  border-bottom: 0;
}

.metadata-list dt {
  color: var(--muted);
  font-size: 12px;
}

.metadata-list dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 13px;
  text-align: right;
}

.code-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.section-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.section-title-row span {
  color: var(--muted);
  font-size: 11px;
}

.link-settings {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 9px;
  font-size: 12px;
}

.link-settings label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
}

.link-settings .ttl-select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 6px;
  background: #fff;
  color: var(--text);
}

.link-settings small {
  color: var(--muted);
}


.link-field {
  min-height: 42px;
  margin-bottom: 9px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  background: var(--panel-soft);
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inspector-button {
  min-height: 36px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 11px;
  background: var(--panel);
  color: var(--text);
  cursor: pointer;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
}

.inspector-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.inspector-button:hover:not(:disabled) {
  border-color: var(--border-strong);
  background: var(--panel-soft);
}

.inspector-button:disabled {
  cursor: not-allowed;
  opacity: .55;
}

.primary-action {
  width: 100%;
  border-color: var(--text);
  background: var(--text);
  color: var(--panel);
}

.primary-action:hover:not(:disabled) {
  border-color: var(--text);
  background: var(--text);
  opacity: .9;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.danger-action {
  border-color: #fecaca;
  color: var(--danger);
}

.rename-form {
  display: grid;
  gap: 7px;
}

.rename-form label {
  font-size: 14px;
  font-weight: 650;
}

.rename-form input {
  min-height: 42px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 11px;
  font-size: 14px;
  outline: 0;
}

.rename-form input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgb(37 99 235 / 10%);
}

.form-error {
  margin: 4px 0 0;
  color: var(--danger);
  font-size: 13px;
}

@media (max-width: 900px) {
  .image-inspector {
    position: static;
    width: 100%;
    max-height: none;
    flex-basis: auto;
  }
}

@media (max-width: 480px) {
  .image-inspector { border-radius: 0; }
  .inspector-heading,
  .inspector-section { padding-inline: 15px; }
  .inspector-preview { margin-inline: 15px; }
  .rename-form input { font-size: 16px; }
}
</style>
