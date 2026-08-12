<script setup>
import { onMounted, ref } from 'vue'
import UploadDropzone from './components/UploadDropzone.vue'
import ImageResult from './components/ImageResult.vue'
import { listImages, uploadFile } from './api'

const items = ref([])
const loading = ref(true)
const loadError = ref('')
let nextId = 1

onMounted(async () => {
  try {
    const { items: existing } = await listImages()
    items.value = existing.map(info => ({
      id: nextId++,
      status: 'done',
      result: info,
      file: null,
    }))
  } catch (err) {
    loadError.value = err.message
  } finally {
    loading.value = false
  }
})

async function handleFiles(files) {
  const list = Array.from(files)
  if (!list.length) return

  for (const file of list) {
    const item = { id: nextId++, file, status: 'uploading', result: null, error: null }
    items.value.unshift(item)
    try {
      item.result = await uploadFile(file)
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
    <header>
      <h1>oss<span>.</span></h1>
      <p class="subtitle">自托管图床 · 上传即得短码链接</p>
    </header>

    <UploadDropzone @files="handleFiles" />

    <p v-if="loading" class="status">加载已上传图片…</p>
    <p v-else-if="loadError" class="status error">加载失败：{{ loadError }}</p>
    <template v-else>
      <h2 class="section-title">
        已上传图片
        <span class="count">{{ items.length }}</span>
      </h2>
      <p v-if="!items.length" class="status">还没有图片，拖拽上传第一张吧</p>
      <ul class="results">
        <li v-for="item in items" :key="item.id">
          <ImageResult :item="item" />
        </li>
      </ul>
    </template>

    <footer>
      API 文档见 <a href="/docs">/docs</a> · 健康检查 <a href="/healthz">/healthz</a>
    </footer>
  </main>
</template>
