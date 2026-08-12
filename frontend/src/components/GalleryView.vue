<script setup>
import { onMounted, ref } from 'vue'
import { deleteImage, listImages, updateImage, uploadFile } from '../api'
import ImageResult from './ImageResult.vue'
import UploadDropzone from './UploadDropzone.vue'

const props = defineProps({ user: { type: Object, required: true } })

const items = ref([])
const loading = ref(true)
const loadError = ref('')
const query = ref('')
const uploadName = ref('')
const uploadVisibility = ref('private')

let nextId = 1
let searchTimer = null

async function loadGallery() {
  loading.value = true
  loadError.value = ''
  try {
    const { items: list } = await listImages({ q: query.value })
    items.value = list.map(info => ({ id: nextId++, status: 'done', result: info, file: null }))
  } catch (err) {
    loadError.value = err.message
  } finally {
    loading.value = false
  }
}

function onQueryInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadGallery, 300)
}

onMounted(loadGallery)

async function handleFiles(files) {
  const list = Array.from(files)
  if (!list.length) return

  const base = uploadName.value.trim()
  for (let i = 0; i < list.length; i++) {
    const file = list[i]
    const name = base ? (list.length > 1 ? `${base}-${i + 1}` : base) : ''
    const item = { id: nextId++, file, status: 'uploading', result: null, error: null }
    items.value.unshift(item)
    try {
      item.result = await uploadFile(file, { name, visibility: uploadVisibility.value })
      item.status = 'done'
    } catch (err) {
      item.error = err.message
      item.status = 'error'
    }
  }
}

async function onDelete(item) {
  if (!window.confirm(`确定删除图片「${item.result.name || item.result.code}」？此操作不可恢复。`)) return
  try {
    await deleteImage(item.result.code)
    items.value = items.value.filter(i => i.id !== item.id)
  } catch (err) {
    window.alert(`删除失败：${err.message}`)
  }
}

async function onToggleVisibility(item) {
  const next = item.result.visibility === 'private' ? 'public' : 'private'
  if (next === 'public' && !window.confirm('设为公开后，任何人拿到链接都能访问。确定？')) return
  try {
    item.result = await updateImage(item.result.code, { visibility: next })
  } catch (err) {
    window.alert(`操作失败：${err.message}`)
  }
}

function canDelete(item) {
  return props.user.role === 'admin' || item.result?.owner_id === props.user.id
}
</script>

<template>
  <section>
    <div class="options">
      <input v-model="uploadName" class="name-input" type="text"
             placeholder="图片命名（可选，多张自动加序号）" maxlength="255" />
      <select v-model="uploadVisibility" class="vis-select">
        <option value="private">私密 · 仅自己/团队可见</option>
        <option value="public">公开 · 任何人可访问</option>
      </select>
    </div>
    <UploadDropzone @files="handleFiles" />

    <div class="search-row">
      <input v-model="query" class="search" type="search"
             placeholder="搜索名称 / 文件名 / 短码…" @input="onQueryInput" />
      <span v-if="query" class="clear" @click="query = ''; loadGallery()">✕</span>
    </div>

    <p v-if="loading" class="status">加载中…</p>
    <p v-else-if="loadError" class="status error">加载失败：{{ loadError }}</p>
    <template v-else>
      <h2 class="section-title">
        我的图片
        <span class="count">{{ items.length }}</span>
      </h2>
      <p v-if="!items.length" class="status">
        {{ query ? '没有匹配的图片' : '还没有图片，拖拽上传第一张吧' }}
      </p>
      <ul class="results">
        <li v-for="item in items" :key="item.id">
          <ImageResult :item="item" :deletable="item.status === 'done' && canDelete(item)"
                       @delete="onDelete(item)" @toggle-visibility="onToggleVisibility(item)" />
        </li>
      </ul>
    </template>
  </section>
</template>
