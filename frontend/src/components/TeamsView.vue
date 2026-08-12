<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  addTeamMember,
  changeTeamMemberRole,
  createTeam,
  deleteTeam,
  getTeam,
  listTeams,
  removeTeamMember,
} from '../api'
import { confirmAction, toast } from '../stores/feedback'
import GalleryView from './GalleryView.vue'
import CollectionsView from './CollectionsView.vue'
import VideoView from './VideoView.vue'

const props = defineProps({ user: { type: Object, required: true } })

const teams = ref([])
const selected = ref(null)
const createName = ref('')
const createDesc = ref('')
const addUsername = ref('')
const spaceTab = ref('images')
const loadingTeam = ref(false)
let openTeamGeneration = 0

const myRole = computed(() => selected.value?.role)
const canManageMembers = computed(() => (
  ['owner', 'admin'].includes(myRole.value) || props.user.role === 'admin'
))
const canChangeRoles = computed(() => myRole.value === 'owner' || props.user.role === 'admin')
const canDissolve = computed(() => myRole.value === 'owner' || props.user.role === 'admin')

function roleLabel(role) {
  return { owner: '拥有者', admin: '管理员', member: '成员' }[role] || role
}

async function loadTeams() {
  try {
    teams.value = await listTeams()
  } catch (error) {
    toast(`团队加载失败：${error.message}`, 'error')
  }
}

async function openTeam(id) {
  const generation = ++openTeamGeneration
  loadingTeam.value = true
  try {
    const team = await getTeam(id)
    if (generation !== openTeamGeneration) return
    selected.value = team
    spaceTab.value = 'images'
  } catch (error) {
    if (generation === openTeamGeneration) toast(`团队加载失败：${error.message}`, 'error')
  } finally {
    if (generation === openTeamGeneration) loadingTeam.value = false
  }
}

async function doCreate() {
  try {
    const team = await createTeam(createName.value.trim(), createDesc.value.trim())
    createName.value = ''
    createDesc.value = ''
    await loadTeams()
    await openTeam(team.id)
    toast('团队创建成功', 'success')
  } catch (error) {
    toast(`创建失败：${error.message}`, 'error')
  }
}

async function doAddMember() {
  if (!addUsername.value.trim()) return
  try {
    await addTeamMember(selected.value.id, addUsername.value.trim())
    addUsername.value = ''
    selected.value = await getTeam(selected.value.id)
    toast('成员已加入团队', 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}

async function doRemove(member) {
  const removingSelf = member.id === selected.value.members.find(item => item.username === props.user.username)?.id
  const ok = await confirmAction({
    title: removingSelf ? '退出团队' : '移除团队成员',
    message: removingSelf ? `确定退出「${selected.value.name}」？你的团队分组会转交给团队拥有者。` : `确定把 ${member.username} 移出团队？`,
    confirmText: removingSelf ? '退出团队' : '移除',
    danger: true,
  })
  if (!ok) return
  try {
    await removeTeamMember(selected.value.id, member.id)
    if (removingSelf) {
      openTeamGeneration++
      selected.value = null
      await loadTeams()
      toast('已退出团队', 'success')
    } else {
      selected.value = await getTeam(selected.value.id)
      toast('成员已移除', 'success')
    }
  } catch (error) {
    toast(error.message, 'error')
  }
}

async function doToggleRole(member) {
  const next = member.role === 'admin' ? 'member' : 'admin'
  const ok = await confirmAction({
    title: next === 'admin' ? '设为管理员' : '取消管理员权限',
    message: `确定将 ${member.username} ${next === 'admin' ? '设为团队管理员' : '降为普通成员'}？`,
    confirmText: '确认变更',
  })
  if (!ok) return
  try {
    await changeTeamMemberRole(selected.value.id, member.id, next)
    selected.value = await getTeam(selected.value.id)
    toast('成员角色已更新', 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}

async function doDeleteTeam() {
  const ok = await confirmAction({
    title: '解散团队',
    message: `确定解散「${selected.value.name}」？团队图片和视频会回到各上传者的个人空间。`,
    confirmText: '解散团队',
    danger: true,
  })
  if (!ok) return
  try {
    await deleteTeam(selected.value.id)
    openTeamGeneration++
    selected.value = null
    await loadTeams()
    toast('团队已解散', 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}

onMounted(loadTeams)
</script>

<template>
  <section class="teams-view">
    <div class="section-heading page-heading">
      <div>
        <p class="eyebrow">协作空间</p>
        <h2>团队</h2>
        <p>邀请成员，在同一个空间管理图片和视频。</p>
      </div>
    </div>

    <div class="teams-layout">
      <aside class="team-panel">
        <div class="aside-title">
          <h3>我的团队</h3>
          <span>{{ teams.length }}</span>
        </div>
        <ul v-if="teams.length" class="team-cards">
          <li v-for="team in teams" :key="team.id">
            <button :class="{ active: selected?.id === team.id }" @click="openTeam(team.id)">
              <span class="team-avatar">{{ team.name.slice(0, 1).toUpperCase() }}</span>
              <span>
                <strong>{{ team.name }}</strong>
                <small>{{ team.member_count }} 人 · {{ roleLabel(team.role) }}</small>
              </span>
            </button>
          </li>
        </ul>
        <p v-else class="status">还没有加入任何团队</p>

        <form class="team-create-form" @submit.prevent="doCreate">
          <h4>创建新团队</h4>
          <input v-model="createName" placeholder="团队名称" maxlength="64" aria-label="新团队名称" required />
          <input v-model="createDesc" placeholder="简介（可选）" maxlength="255" aria-label="新团队简介" />
          <button class="primary" :disabled="!createName.trim()">创建团队</button>
        </form>
      </aside>

      <div v-if="selected" class="team-detail">
        <div class="team-head surface-card">
          <div class="team-title-group">
            <span class="team-avatar large">{{ selected.name.slice(0, 1).toUpperCase() }}</span>
            <div>
              <h2>{{ selected.name }}</h2>
              <p>{{ selected.description || '这个团队还没有简介。' }}</p>
            </div>
          </div>
          <div class="team-actions">
            <span class="role-badge">{{ roleLabel(myRole) }}</span>
            <button v-if="canDissolve" class="ghost danger" @click="doDeleteTeam">解散团队</button>
          </div>
        </div>

        <section class="members-panel surface-card">
          <div class="panel-title-row">
            <h3>成员 <span>{{ selected.members.length }}</span></h3>
            <form v-if="canManageMembers" class="add-member" @submit.prevent="doAddMember">
              <input v-model="addUsername" placeholder="输入用户名邀请" aria-label="要邀请的用户名" />
              <button class="secondary" :disabled="!addUsername.trim()">邀请</button>
            </form>
          </div>
          <ul class="member-list">
            <li v-for="member in selected.members" :key="member.id">
              <span class="member-avatar">{{ member.username.slice(0, 1).toUpperCase() }}</span>
              <span class="username">{{ member.username }}</span>
              <span class="role-badge" :class="{ owner: member.role === 'owner', admin: member.role === 'admin' }">{{ roleLabel(member.role) }}</span>
              <span v-if="member.role !== 'owner' && (canManageMembers || member.username === user.username)" class="member-actions">
                <button v-if="canChangeRoles" class="ghost" @click="doToggleRole(member)">{{ member.role === 'admin' ? '降为成员' : '设为管理员' }}</button>
                <button v-if="canManageMembers || member.username === user.username" class="ghost danger" @click="doRemove(member)">{{ member.username === user.username ? '退出团队' : '移除' }}</button>
              </span>
            </li>
          </ul>
        </section>

        <div class="space-tabs" role="tablist" aria-label="团队空间类型">
          <button id="team-tab-images" role="tab" aria-controls="team-panel-images" :aria-selected="spaceTab === 'images'" :class="{ active: spaceTab === 'images' }" @click="spaceTab = 'images'">图片</button>
          <button id="team-tab-videos" role="tab" aria-controls="team-panel-videos" :aria-selected="spaceTab === 'videos'" :class="{ active: spaceTab === 'videos' }" @click="spaceTab = 'videos'">视频</button>
          <button id="team-tab-groups" role="tab" aria-controls="team-panel-groups" :aria-selected="spaceTab === 'groups'" :class="{ active: spaceTab === 'groups' }" @click="spaceTab = 'groups'">分组</button>
        </div>
        <div v-if="spaceTab === 'images'" id="team-panel-images" role="tabpanel" aria-labelledby="team-tab-images"><GalleryView :key="`images-${selected.id}`" :user="user" :team-id="selected.id" :can-manage="canManageMembers" /></div>
        <div v-else-if="spaceTab === 'videos'" id="team-panel-videos" role="tabpanel" aria-labelledby="team-tab-videos"><VideoView :key="`videos-${selected.id}`" :user="user" :team-id="selected.id" :can-manage="canManageMembers" /></div>
        <div v-else id="team-panel-groups" role="tabpanel" aria-labelledby="team-tab-groups"><CollectionsView :key="`groups-${selected.id}`" :user="user" :team-id="selected.id" :can-manage="canManageMembers" /></div>
      </div>

      <div v-else class="team-detail placeholder-panel">
        <div class="empty-icon">◎</div>
        <h3>{{ loadingTeam ? '正在加载团队…' : '选择一个团队' }}</h3>
        <p>从左侧进入团队空间，或创建一个新团队。</p>
      </div>
    </div>
  </section>
</template>
