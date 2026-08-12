<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AuthView from './components/AuthView.vue'
import ImageResult from './components/ImageResult.vue'
import UploadDropzone from './components/UploadDropzone.vue'
import { fetchMe, getToken, listImages, setToken, uploadFile } from './api'

const user = ref(null)
const items = ref([])
const loading = ref(true)
const loadError = ref('')
const query = ref('')
const uploadName = ref('')
const uploadVisibility = ref('public')

let nextId = 1
let searchTimer = null

const isAdmin = computed(() => user.value?.role === 'admin')

function onUnauthorized() {
  user.value = null
  items.value = []
}

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

onMounted(async () => {
  window.addEventListener('oss:unauthorized', onUnauthorized)
  if (getToken()) {
    try {
      user.value = await fetchMe()
      await loadGallery()
    } catch {
      // invalid token — api.js already cleared it
    }
  }
  loading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('oss:unauthorized', onUnauthorized)
  clearTimeout(searchTimer)
})

async function handleAuthed(u) {
  user.value = u
  await loadGallery()
}

function logout() {
  setToken(null)
  user.value = null
  items.value = []
  query.value = ''
}

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
</script>

<template>
  <main>
    <template v-if="!user">
      <AuthView @authed="handleAuthed" />
    </template>

    <template v-else>
      <header>
        <div>
          <h1>oss<span>.</span></h1>
          <p class="subtitle">自托管图床 · 上传即得短码链接</p>
        </div>
        <div class="userbox">
          <span class="username">{{ user.username }}</span>
          <span class="role-badge" :class="{ admin: isAdmin }">
            {{ isAdmin ? '管理员' : '用户' }}
          </span>
          <button class="ghost" @click="logout">退出</button>
        </div>
      </header>

      <div class="options">
        <input v-model="uploadName" class="name-input" type="text"
               placeholder="图片命名（可选，多张自动加序号）" maxlength="255" />
        <select v-model="uploadVisibility" class="vis-select">
          <option value="public">公开 · 任何人可访问</option>
          <option value="private">私密 · 仅自己可见</option>
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
          已上传图片
          <span class="count">{{ items.length }}</span>
        </h2>
        <p v-if="!items.length" class="status">
          {{ query ? '没有匹配的图片' : '还没有图片，拖拽上传第一张吧' }}
        </p>
        <ul class="results">
          <li v-for="item in items" :key="item.id">
            <ImageResult :item="item" />
          </li>
        </ul>
      </template>

      <footer>
        API 文档见 <a href="/docs">/docs</a> · 健康检查 <a href="/healthz">/healthz</a>
      </footer>
    </template>
  </main>
</template>
