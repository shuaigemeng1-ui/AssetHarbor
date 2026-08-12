<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  addTeamMember,
  changeTeamMemberRole,
  createTeam,
  deleteImage,
  deleteTeam,
  getTeam,
  listTeamImages,
  listTeams,
  removeTeamMember,
  updateImage,
  uploadFile,
} from '../api'
import ImageResult from './ImageResult.vue'
import UploadDropzone from './UploadDropzone.vue'

const props = defineProps({ user: { type: Object, required: true } })

const teams = ref([])
const selected = ref(null)
const createName = ref('')
const createDesc = ref('')
const addUsername = ref('')
const spaceItems = ref([])
const spaceLoading = ref(false)
const spaceQuery = ref('')
const uploadName = ref('')
const uploadVisibility = ref('private')

let nextId = 1
let searchTimer = null

const myRole = computed(() => selected.value?.role) // owner | admin | member（全局管理员显示 admin）
const canManage = computed(() =>
  myRole.value === 'owner' || myRole.value === 'admin' || props.user.role === 'admin',
)

function roleLabel(role) {
  return { owner: '拥有者', admin: '管理员', member: '成员' }[role] || role
}

async function loadTeams() {
  try {
    teams.value = await listTeams()
  } catch (err) {
    window.alert(err.message)
  }
}

async function openTeam(id) {
  try {
    selected.value = await getTeam(id)
    await loadSpace()
  } catch (err) {
    window.alert(err.message)
  }
}

async function loadSpace() {
  if (!selected.value) return
  spaceLoading.value = true
  try {
    const { items } = await listTeamImages(selected.value.id, { q: spaceQuery.value })
    spaceItems.value = items.map(info => ({ id: nextId++, status: 'done', result: info, file: null }))
  } catch (err) {
    window.alert(err.message)
  } finally {
    spaceLoading.value = false
  }
}

function onSpaceQuery() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadSpace, 300)
}

async function doCreate() {
  try {
    const team = await createTeam(createName.value.trim(), createDesc.value.trim())
    createName.value = ''
    createDesc.value = ''
    await loadTeams()
    await openTeam(team.id)
  } catch (err) {
    window.alert(`创建失败：${err.message}`)
  }
}

async function doAddMember() {
  try {
    await addTeamMember(selected.value.id, addUsername.value.trim())
    addUsername.value = ''
    selected.value = await getTeam(selected.value.id)
  } catch (err) {
    window.alert(err.message)
  }
}

async function doRemove(member) {
  if (!window.confirm(`确定把 ${member.username} 移出团队？`)) return
  try {
    await removeTeamMember(selected.value.id, member.id)
    selected.value = await getTeam(selected.value.id)
  } catch (err) {
    window.alert(err.message)
  }
}

async function doToggleRole(member) {
  const next = member.role === 'admin' ? 'member' : 'admin'
  if (!window.confirm(`把 ${member.username} ${next === 'admin' ? '设为管理员' : '降为成员'}？`)) return
  try {
    await changeTeamMemberRole(selected.value.id, member.id, next)
    selected.value = await getTeam(selected.value.id)
  } catch (err) {
    window.alert(err.message)
  }
}

async function doDeleteTeam() {
  if (!window.confirm(`确定解散团队「${selected.value.name}」？团队图片将回到上传者的个人空间。`)) return
  try {
    await deleteTeam(selected.value.id)
    selected.value = null
    await loadTeams()
  } catch (err) {
    window.alert(err.message)
  }
}

async function handleFiles(files) {
  const list = Array.from(files)
  if (!list.length || !selected.value) return

  const base = uploadName.value.trim()
  for (let i = 0; i < list.length; i++) {
    const name = base ? (list.length > 1 ? `${base}-${i + 1}` : base) : ''
    const item = { id: nextId++, file, status: 'uploading', result: null, error: null }
    spaceItems.value.unshift(item)
    try {
      item.result = await uploadFile(file, { name, visibility: uploadVisibility.value, teamId: selected.value.id })
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
    spaceItems.value = spaceItems.value.filter(i => i.id !== item.id)
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
  if (props.user.role === 'admin' || item.result?.owner_id === props.user.id) return true
  return selected.value && (selected.value.role === 'owner' || selected.value.role === 'admin')
}

onMounted(loadTeams)
</script>

<template>
  <section>
    <div class="teams-layout">
      <div class="team-panel">
        <h2 class="section-title">我的团队 <span class="count">{{ teams.length }}</span></h2>
        <ul v-if="teams.length" class="team-cards">
          <li v-for="t in teams" :key="t.id" :class="{ active: selected?.id === t.id }" @click="openTeam(t.id)">
            <div class="team-name">{{ t.name }}</div>
            <div class="team-meta">{{ t.member_count }} 人 · {{ roleLabel(t.role) }}</div>
          </li>
        </ul>
        <p v-else class="status">还没有加入任何团队</p>

        <div class="team-create-form">
          <input v-model="createName" placeholder="新团队名称" maxlength="64" />
          <input v-model="createDesc" placeholder="简介（可选）" maxlength="255" />
          <button class="primary" :disabled="!createName.trim()" @click="doCreate">创建团队</button>
        </div>
      </div>

      <div v-if="selected" class="team-detail">
        <div class="team-head">
          <h2>{{ selected.name }}</h2>
          <p v-if="selected.description" class="subtitle">{{ selected.description }}</p>
          <div class="team-actions">
            <span class="role-badge">{{ roleLabel(myRole) }}</span>
            <button v-if="canManage" class="ghost danger" @click="doDeleteTeam">解散团队</button>
          </div>
        </div>

        <h3 class="section-title">成员 <span class="count">{{ selected.members.length }}</span></h3>
        <div v-if="canManage" class="add-member">
          <input v-model="addUsername" placeholder="输入用户名邀请" @keyup.enter="doAddMember" />
          <button class="primary" :disabled="!addUsername.trim()" @click="doAddMember">邀请</button>
        </div>
        <ul class="member-list">
          <li v-for="m in selected.members" :key="m.id">
            <span class="username">{{ m.username }}</span>
            <span class="role-badge" :class="{ owner: m.role === 'owner', admin: m.role === 'admin' }">
              {{ roleLabel(m.role) }}
            </span>
            <span v-if="canManage && m.role !== 'owner'" class="member-actions">
              <button class="ghost" @click="doToggleRole(m)">
                {{ m.role === 'admin' ? '降为成员' : '设为管理员' }}
              </button>
              <button class="ghost danger" @click="doRemove(m)">移除</button>
            </span>
          </li>
        </ul>

        <h3 class="section-title">团队空间 <span class="count">{{ spaceItems.length }}</span></h3>
        <div class="options">
          <input v-model="uploadName" class="name-input" placeholder="图片命名（可选）" maxlength="255" />
          <select v-model="uploadVisibility" class="vis-select">
            <option value="private">私密 · 仅团队可见</option>
            <option value="public">公开 · 任何人可访问</option>
          </select>
        </div>
        <UploadDropzone @files="handleFiles" />
        <div class="search-row">
          <input v-model="spaceQuery" class="search" type="search" placeholder="搜索团队空间…" @input="onSpaceQuery" />
          <span v-if="spaceQuery" class="clear" @click="spaceQuery = ''; loadSpace()">✕</span>
        </div>
        <p v-if="spaceLoading" class="status">加载中…</p>
        <ul v-else class="results">
          <li v-for="item in spaceItems" :key="item.id">
            <ImageResult :item="item" :deletable="item.status === 'done' && canDelete(item)"
                         @delete="onDelete(item)" @toggle-visibility="onToggleVisibility(item)" />
          </li>
        </ul>
        <p v-if="!spaceLoading && !spaceItems.length" class="status">团队空间还没有图片</p>
      </div>

      <div v-else class="team-detail placeholder-panel">
        <p class="status">选择左侧团队查看成员与空间，或创建一个新团队</p>
      </div>
    </div>
  </section>
</template>
