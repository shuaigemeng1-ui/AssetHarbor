<script setup>
import { ref } from 'vue'
import UploadDropzone from './components/UploadDropzone.vue'
import ImageResult from './components/ImageResult.vue'
import { uploadFile } from './api'

const items = ref([])
let nextId = 1

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

    <ul class="results">
      <li v-for="item in items" :key="item.id">
        <ImageResult :item="item" />
      </li>
    </ul>

    <footer>
      API 文档见 <a href="/docs">/docs</a> · 健康检查 <a href="/healthz">/healthz</a>
    </footer>
  </main>
</template>
