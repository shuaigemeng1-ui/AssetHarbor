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
        <div v-if="spaceTab === 'images'" id="team-panel-images" role="tabpanel" aria-labelledby="team-tab-images"><GalleryView :key="`images-${selected.id}`" :user="user" :team-id="selected.id" :can-manage="canManageMembers" embedded /></div>
        <div v-else-if="spaceTab === 'videos'" id="team-panel-videos" role="tabpanel" aria-labelledby="team-tab-videos"><VideoView :key="`videos-${selected.id}`" :user="user" :team-id="selected.id" :can-manage="canManageMembers" /></div>
        <div v-else id="team-panel-groups" role="tabpanel" aria-labelledby="team-tab-groups"><CollectionsView :key="`groups-${selected.id}`" :user="user" :team-id="selected.id" :can-manage="canManageMembers" /></div>
      </div>

      <div v-else class="team-detail placeholder-panel">
        <h3>{{ loadingTeam ? '正在加载团队…' : '选择一个团队' }}</h3>
        <p>从左侧进入团队空间，或创建一个新团队。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.teams-view > .section-heading {
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

.teams-layout {
  min-height: 560px;
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
}

.team-panel {
  position: static;
  min-width: 0;
  border: 0;
  border-right: 1px solid var(--border);
  border-radius: 0;
  padding: 14px;
  background: #faf9f7;
  box-shadow: none;
}

.aside-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 2px 11px;
}

.aside-title h3 {
  margin: 0;
  font-size: 12px;
  font-weight: 660;
}

.aside-title span {
  border: 0;
  border-radius: 4px;
  padding: 2px 5px;
  background: #eeece8;
  color: var(--muted);
  font-size: 10px;
  font-weight: 550;
}

.team-cards,
.member-list {
  margin: 0;
  padding: 0;
  display: grid;
  gap: 2px;
  list-style: none;
}

.team-cards button {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 7px 8px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.team-cards button:hover {
  background: #f2f0ec;
}

.team-cards button.active {
  border-color: var(--border);
  background: #fff;
}

.team-avatar,
.member-avatar {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: #eeece8;
  color: var(--text);
  font-weight: 650;
}

.team-avatar {
  width: 32px;
  height: 32px;
  font-size: 11px;
}

.team-avatar.large {
  width: 42px;
  height: 42px;
  border-radius: 5px;
  font-size: 16px;
}

.team-cards strong,
.team-cards small {
  max-width: 150px;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.team-cards strong {
  font-size: 12px;
  font-weight: 620;
}

.team-cards small {
  margin-top: 2px;
  color: var(--muted);
  font-size: 10px;
}

.team-panel > .status {
  min-height: auto;
  padding: 26px 4px;
  color: var(--muted);
  font-size: 11px;
  text-align: center;
}

.team-create-form {
  margin-top: 14px;
  padding-top: 14px;
  display: grid;
  gap: 8px;
  border-top: 1px solid var(--border);
}

.team-create-form h4 {
  margin: 0 0 1px;
  font-size: 11px;
  font-weight: 650;
}

.team-create-form input,
.add-member input {
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

.team-create-form input:focus,
.add-member input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgb(11 99 229 / 10%);
}

.team-create-form .primary,
.add-member .secondary {
  min-height: 36px;
  border-radius: 5px;
  box-shadow: none;
  font-size: 11px;
}

.team-detail {
  min-width: 0;
  padding: 20px;
  background: #fff;
}

.team-head {
  margin: 0 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 0;
  border-bottom: 1px solid var(--border);
  border-radius: 0;
  padding: 0 0 18px;
  background: #fff;
  box-shadow: none;
}

.team-title-group {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 11px;
}

.team-head h2 {
  margin: 0 0 3px;
  font-size: 19px;
  font-weight: 670;
}

.team-head p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}

.team-actions,
.member-actions,
.add-member {
  display: flex;
  align-items: center;
  gap: 5px;
}

.team-actions button,
.member-actions button {
  border-radius: 4px;
}

.role-badge {
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 6px;
  background: var(--panel-soft);
  color: var(--muted);
  font-size: 10px;
  white-space: nowrap;
}

.role-badge.owner,
.role-badge.admin {
  border-color: var(--border);
  background: var(--panel-soft);
  color: var(--text);
}

.members-panel {
  margin-bottom: 18px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 14px;
  background: #fff;
  box-shadow: none;
}

.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-title-row h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 660;
}

.panel-title-row h3 span {
  margin-left: 3px;
  border-radius: 3px;
  padding: 1px 4px;
  background: var(--panel-soft);
  color: var(--muted);
  font-size: 10px;
}

.add-member input {
  width: 180px;
}

.member-list {
  margin-top: 12px;
}

.member-list li {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 2px;
  border-top: 1px solid var(--border);
}

.member-avatar {
  width: 28px;
  height: 28px;
  font-size: 10px;
}

.member-list .username {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  font-size: 12px;
  font-weight: 620;
  text-overflow: ellipsis;
}

.space-tabs {
  width: fit-content;
  margin: 0 0 18px;
  display: flex;
  gap: 2px;
  border: 0;
  border-bottom: 1px solid var(--border);
  border-radius: 0;
  padding: 0;
  background: transparent;
}

.space-tabs button {
  margin-bottom: -1px;
  border: 0;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  padding: 8px 14px;
  background: transparent;
  color: var(--muted);
  box-shadow: none;
  cursor: pointer;
  font-size: 11px;
}

.space-tabs button.active {
  border-bottom-color: var(--text);
  background: transparent;
  color: var(--text);
}

.placeholder-panel {
  min-height: 558px;
  display: grid;
  place-content: center;
  justify-items: center;
  border: 0;
  border-radius: 0;
  background: var(--panel-soft);
  box-shadow: none;
  text-align: center;
}

.placeholder-panel h3 {
  margin: 0 0 5px;
  font-size: 14px;
  font-weight: 630;
}

.placeholder-panel p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}

@media (max-width: 940px) {
  .teams-layout { grid-template-columns: 210px minmax(0, 1fr); }
  .panel-title-row { align-items: flex-start; flex-direction: column; }
}

@media (max-width: 760px) {
  .teams-layout { grid-template-columns: 1fr; }
  .team-panel { border-right: 0; border-bottom: 1px solid var(--border); }
  .team-cards { grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); }
}

@media (max-width: 580px) {
  .team-head { align-items: flex-start; flex-direction: column; }
  .team-actions { width: 100%; justify-content: space-between; }
  .add-member { width: 100%; }
  .add-member input { min-width: 0; flex: 1; }
  .member-list li { align-items: flex-start; flex-wrap: wrap; }
  .member-actions { width: 100%; justify-content: flex-end; }
}
</style>
