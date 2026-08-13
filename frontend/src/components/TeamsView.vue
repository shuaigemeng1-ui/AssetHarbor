<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
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
import AppIcon from './AppIcon.vue'

const props = defineProps({ user: { type: Object, required: true } })

const teams = ref([])
const selected = ref(null)
const createName = ref('')
const createDesc = ref('')
const addUsername = ref('')
const spaceTab = ref('images')
const loadingTeam = ref(false)
const createOpen = ref(false)
const membersOpen = ref(false)
const teamMenuOpen = ref(false)
const inviteOpen = ref(false)
const settingsOpen = ref(false)
const addMemberInput = ref(null)
const memberPanel = ref(null)
const teamSwitcher = ref(null)
const teamSwitcherButton = ref(null)
const teamOptionButtons = ref([])
const memberDrawerQuery = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(max-width: 1160px)')
  : null
const isMemberDrawer = ref(memberDrawerQuery?.matches || false)
let panelReturnFocus = null
let openTeamGeneration = 0

const myRole = computed(() => selected.value?.role)
const canManageMembers = computed(() => (
  ['owner', 'admin'].includes(myRole.value) || props.user.role === 'admin'
))
const canChangeRoles = computed(() => myRole.value === 'owner' || props.user.role === 'admin')
const canDissolve = computed(() => myRole.value === 'owner' || props.user.role === 'admin')
const memberPanelHidden = computed(() => isMemberDrawer.value && !membersOpen.value)
const orderedMembers = computed(() => {
  const rank = { owner: 0, admin: 1, member: 2 }
  return [...(selected.value?.members || [])].sort((left, right) => (
    (rank[left.role] ?? 3) - (rank[right.role] ?? 3)
      || left.username.localeCompare(right.username, 'zh-CN')
  ))
})

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
    membersOpen.value = false
    inviteOpen.value = false
    settingsOpen.value = false
  } catch (error) {
    if (generation === openTeamGeneration) toast(`团队加载失败：${error.message}`, 'error')
  } finally {
    if (generation === openTeamGeneration) loadingTeam.value = false
  }
}

function selectTeam(id) {
  teamMenuOpen.value = false
  teamSwitcherButton.value?.focus()
  openTeam(id)
}

function toggleTeamMenu() {
  createOpen.value = false
  teamMenuOpen.value = !teamMenuOpen.value
}

async function focusTeamOption(position) {
  teamMenuOpen.value = true
  createOpen.value = false
  await nextTick()
  const options = teamOptionButtons.value
  const target = position < 0 ? options.at(-1) : options[position]
  target?.focus()
}

function onTeamMenuKeydown(event) {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const options = teamOptionButtons.value
  if (!options.length) return
  if (event.key === 'Home') return options[0].focus()
  if (event.key === 'End') return options.at(-1).focus()
  const current = Math.max(0, options.indexOf(document.activeElement))
  const delta = event.key === 'ArrowDown' ? 1 : -1
  options[(current + delta + options.length) % options.length].focus()
}

function onOutsidePointerDown(event) {
  if (teamMenuOpen.value && !teamSwitcher.value?.contains(event.target)) teamMenuOpen.value = false
}

function onMemberDrawerChange(event) {
  isMemberDrawer.value = event.matches
  if (!event.matches) membersOpen.value = false
}

function openCreatePanel() {
  teamMenuOpen.value = false
  createOpen.value = !createOpen.value
}

function closeMemberPanel() {
  membersOpen.value = false
  inviteOpen.value = false
  settingsOpen.value = false
  nextTick(() => panelReturnFocus?.focus?.())
}

async function doCreate() {
  try {
    const team = await createTeam(createName.value.trim(), createDesc.value.trim())
    createName.value = ''
    createDesc.value = ''
    createOpen.value = false
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
    inviteOpen.value = false
    selected.value = await getTeam(selected.value.id)
    await loadTeams()
    toast('成员已加入团队', 'success')
  } catch (error) {
    toast(error.message, 'error')
  }
}

async function openMemberPanel(event) {
  panelReturnFocus = event?.currentTarget || document.activeElement
  membersOpen.value = true
  inviteOpen.value = true
  settingsOpen.value = false
  await nextTick()
  addMemberInput.value?.focus()
}

async function openMemberList(event) {
  panelReturnFocus = event?.currentTarget || document.activeElement
  membersOpen.value = true
  inviteOpen.value = false
  settingsOpen.value = false
  await nextTick()
  memberPanel.value?.focus({ preventScroll: true })
}

async function openSettingsPanel(event) {
  panelReturnFocus = event?.currentTarget || document.activeElement
  membersOpen.value = true
  inviteOpen.value = false
  settingsOpen.value = true
  await nextTick()
  memberPanel.value?.focus({ preventScroll: true })
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
      await loadTeams()
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

function onPageKeydown(event) {
  if (event.key === 'Tab' && isMemberDrawer.value && membersOpen.value && memberPanel.value) {
    const focusable = [...memberPanel.value.querySelectorAll('button:not([disabled]), input:not([disabled])')]
    if (!focusable.length) return
    const first = focusable[0]
    const last = focusable.at(-1)
    if (event.shiftKey && [memberPanel.value, first].includes(document.activeElement)) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
    return
  }
  if (event.key !== 'Escape') return
  if (membersOpen.value) {
    event.preventDefault()
    closeMemberPanel()
    return
  }
  if (teamMenuOpen.value) {
    event.preventDefault()
    teamMenuOpen.value = false
    nextTick(() => teamSwitcherButton.value?.focus())
  }
}

onMounted(() => {
  loadTeams()
  window.addEventListener('keydown', onPageKeydown)
  document.addEventListener('pointerdown', onOutsidePointerDown)
  memberDrawerQuery?.addEventListener?.('change', onMemberDrawerChange)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onPageKeydown)
  document.removeEventListener('pointerdown', onOutsidePointerDown)
  memberDrawerQuery?.removeEventListener?.('change', onMemberDrawerChange)
})
</script>

<template>
  <section class="teams-view">
    <header class="teams-header">
      <h2>团队</h2>
    </header>

    <div class="team-topbar">
      <div class="team-switcher-wrap">
        <div v-if="teams.length" ref="teamSwitcher" class="team-switcher">
          <button
            ref="teamSwitcherButton"
            class="team-switcher-button"
            type="button"
            :aria-expanded="teamMenuOpen"
            aria-controls="team-switcher-menu"
            @click="toggleTeamMenu"
            @keydown.down.prevent="focusTeamOption(0)"
            @keydown.up.prevent="focusTeamOption(-1)"
          >
            <span v-if="selected" class="team-avatar">{{ selected.name.slice(0, 1).toUpperCase() }}</span>
            <span v-else class="team-avatar"><AppIcon name="teams" size="16" /></span>
            <strong>{{ selected?.name || (loadingTeam ? '正在加载团队…' : '选择团队') }}</strong>
            <AppIcon name="down" size="16" />
          </button>
          <ul id="team-switcher-menu" class="team-cards" :class="{ open: teamMenuOpen }" aria-label="我的团队" :aria-hidden="!teamMenuOpen" @keydown="onTeamMenuKeydown">
            <li v-for="team in teams" :key="team.id">
              <button ref="teamOptionButtons" :aria-pressed="selected?.id === team.id" :tabindex="teamMenuOpen ? 0 : -1" :class="{ active: selected?.id === team.id }" type="button" @click="selectTeam(team.id)">
                <span class="team-avatar">{{ team.name.slice(0, 1).toUpperCase() }}</span>
                <span>
                  <strong>{{ team.name }}</strong>
                  <small>{{ team.member_count }} 人 · {{ roleLabel(team.role) }}</small>
                </span>
              </button>
            </li>
          </ul>
        </div>
        <p v-else class="team-empty-copy">还没有加入任何团队</p>

        <button class="secondary create-team-trigger" type="button" :aria-expanded="createOpen" aria-controls="team-create-panel" @click="openCreatePanel">
          <AppIcon name="plus" size="16" />
          新建团队
        </button>
      </div>

      <div v-if="selected" class="team-actions">
        <button class="team-summary" type="button" aria-label="查看团队成员" @click="openMemberList">
          <AppIcon name="teams" size="19" />
          <span><small>{{ roleLabel(myRole) }}</small><strong>{{ selected.members.length }} 名成员</strong></span>
        </button>
        <button v-if="canManageMembers" class="primary invite-trigger" type="button" @click="openMemberPanel">
          <AppIcon name="plus" size="16" />
          邀请成员
        </button>
        <button v-if="canDissolve" class="secondary settings-trigger" type="button" aria-label="团队设置" @click="openSettingsPanel">
          <AppIcon name="settings" size="17" />
          <span>团队设置</span>
        </button>
      </div>
    </div>

    <form v-if="createOpen" id="team-create-panel" class="team-create-form" @submit.prevent="doCreate">
      <div>
        <strong>创建新团队</strong>
        <span>设置名称和可选简介，创建后自动进入团队空间。</span>
      </div>
      <input v-model="createName" placeholder="团队名称" minlength="2" maxlength="64" aria-label="新团队名称" required />
      <input v-model="createDesc" placeholder="简介（可选）" maxlength="255" aria-label="新团队简介" />
      <div class="create-form-actions">
        <button class="ghost" type="button" @click="createOpen = false">取消</button>
        <button class="primary" :disabled="createName.trim().length < 2">创建团队</button>
      </div>
    </form>

    <template v-if="selected">
      <div class="space-tabs" role="tablist" aria-label="团队空间类型">
        <button id="team-tab-images" role="tab" aria-controls="team-panel-images" :aria-selected="spaceTab === 'images'" :class="{ active: spaceTab === 'images' }" @click="spaceTab = 'images'">图片</button>
        <button id="team-tab-videos" role="tab" aria-controls="team-panel-videos" :aria-selected="spaceTab === 'videos'" :class="{ active: spaceTab === 'videos' }" @click="spaceTab = 'videos'">视频</button>
        <button id="team-tab-groups" role="tab" aria-controls="team-panel-groups" :aria-selected="spaceTab === 'groups'" :class="{ active: spaceTab === 'groups' }" @click="spaceTab = 'groups'">分组</button>
      </div>

      <div class="teams-layout" :class="{ 'members-open': membersOpen }">
        <section class="team-detail">
          <h2 class="visually-hidden">{{ selected.name }}</h2>

          <div v-if="spaceTab === 'images'" id="team-panel-images" role="tabpanel" aria-labelledby="team-tab-images"><GalleryView :key="`images-${selected.id}`" :user="user" :team-id="selected.id" :can-manage="canManageMembers" embedded /></div>
          <div v-else-if="spaceTab === 'videos'" id="team-panel-videos" role="tabpanel" aria-labelledby="team-tab-videos"><VideoView :key="`videos-${selected.id}`" :user="user" :team-id="selected.id" :can-manage="canManageMembers" embedded /></div>
          <div v-else id="team-panel-groups" role="tabpanel" aria-labelledby="team-tab-groups"><CollectionsView :key="`groups-${selected.id}`" :user="user" :team-id="selected.id" :can-manage="canManageMembers" embedded /></div>
        </section>

        <section
          ref="memberPanel"
          class="members-panel"
          :class="{ open: membersOpen }"
          aria-label="团队成员"
          :role="isMemberDrawer ? 'dialog' : undefined"
          :aria-modal="isMemberDrawer && membersOpen ? 'true' : undefined"
          :aria-hidden="memberPanelHidden ? 'true' : undefined"
          :inert="memberPanelHidden ? '' : undefined"
          tabindex="-1"
        >
          <div class="panel-title-row">
            <h3>成员 <span>{{ selected.members.length }}</span></h3>
            <button class="member-panel-close" type="button" aria-label="关闭成员面板" @click="closeMemberPanel"><AppIcon name="close" size="17" /></button>
          </div>
          <form v-if="canManageMembers && inviteOpen" class="add-member" @submit.prevent="doAddMember">
            <input ref="addMemberInput" v-model="addUsername" placeholder="输入用户名邀请" aria-label="要邀请的用户名" minlength="3" />
            <button class="secondary" :disabled="!addUsername.trim()">邀请</button>
          </form>
          <ul class="member-list">
            <li v-for="member in orderedMembers" :key="member.id">
              <span class="member-avatar">{{ member.username.slice(0, 1).toUpperCase() }}</span>
              <span class="member-copy"><strong class="username">{{ member.username }}</strong></span>
              <div class="member-role-row">
                <span class="role-badge" :class="{ owner: member.role === 'owner', admin: member.role === 'admin' }">{{ roleLabel(member.role) }}</span>
                <span v-if="member.role !== 'owner' && (canManageMembers || member.username === user.username)" class="member-actions">
                  <button v-if="canChangeRoles" class="ghost" type="button" @click="doToggleRole(member)">{{ member.role === 'admin' ? '降为成员' : '设为管理员' }}</button>
                  <button v-if="canManageMembers || member.username === user.username" class="ghost danger" type="button" @click="doRemove(member)">{{ member.username === user.username ? '退出团队' : '移除' }}</button>
                </span>
              </div>
            </li>
          </ul>
          <button v-if="canDissolve && settingsOpen" class="ghost danger dissolve-team" type="button" @click="doDeleteTeam">解散团队</button>
        </section>
        <button v-if="membersOpen" class="members-backdrop" type="button" aria-label="关闭成员面板" @click="closeMemberPanel" />
      </div>
    </template>

    <div v-else class="team-detail placeholder-panel">
      <span class="placeholder-icon"><AppIcon name="teams" size="22" /></span>
      <div>
        <h3>{{ loadingTeam ? '正在加载团队…' : '选择一个团队' }}</h3>
        <p>从上方进入团队空间，或创建一个新团队。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.teams-view {
  min-width: 0;
  min-height: 100vh;
  padding: 30px clamp(24px, 2.2vw, 36px) 48px;
  background: #fff;
}

.teams-header { margin-bottom: 24px; }

.teams-header h2 {
  margin: 0 0 5px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -.025em;
}

.team-topbar {
  min-height: 74px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.team-switcher-wrap,
.team-actions,
.team-switcher,
.team-summary,
.create-team-trigger,
.invite-trigger,
.settings-trigger {
  display: flex;
  align-items: center;
}

.team-switcher-wrap { min-width: 0; gap: 10px; }

.team-switcher {
  position: relative;
  min-width: 194px;
}

.team-switcher-button {
  width: 100%;
  min-height: 48px;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  padding: 5px 10px 5px 7px;
  background: #fff;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.team-switcher-button:hover,
.team-switcher-button:focus-visible { border-color: var(--accent); }
.team-switcher-button strong { overflow: hidden; font-size: 15px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }

.team-switcher > .team-cards {
  position: absolute;
  z-index: 20;
  top: calc(100% + 6px);
  left: 0;
  width: min(280px, calc(100vw - 32px));
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px;
  background: #fff;
  box-shadow: var(--shadow-md);
  opacity: 0;
  pointer-events: none;
  transform: translateY(-4px);
  transition: opacity 120ms ease, transform 120ms ease;
}

.team-switcher > .team-cards.open { opacity: 1; pointer-events: auto; transform: translateY(0); }

.team-empty-copy { margin: 0; color: var(--muted); font-size: 14px; }

.create-team-trigger,
.invite-trigger,
.settings-trigger { min-height: 44px; gap: 7px; padding: 0 14px; font-size: 14px; }

.team-actions { flex: 0 0 auto; gap: 10px; }

.team-summary {
  gap: 10px;
  border: 0;
  padding: 5px 8px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.team-summary > span { min-width: 84px; display: grid; gap: 1px; }
.team-summary small { color: var(--muted); font-size: 12px; }
.team-summary strong { font-size: 14px; font-weight: 620; }

.team-create-form {
  margin-bottom: 18px;
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(180px, .8fr) minmax(220px, 1fr) auto;
  align-items: end;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 14px;
  background: var(--panel-soft);
}

.team-create-form > div:first-child { align-self: center; display: grid; gap: 3px; }
.team-create-form strong { font-size: 14px; }
.team-create-form span { color: var(--muted); font-size: 12px; }
.create-form-actions { display: flex; gap: 6px; }

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
  width: 34px;
  height: 34px;
  font-size: 13px;
}

.team-avatar.large {
  width: 46px;
  height: 46px;
  border-radius: 6px;
  font-size: 17px;
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
  font-size: 14px;
  font-weight: 620;
}

.team-cards small {
  margin-top: 2px;
  color: var(--muted);
  font-size: 12px;
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
  font-size: 14px;
  outline: 0;
}

.team-create-form input:focus,
.add-member input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgb(11 99 229 / 10%);
}

.team-create-form button,
.add-member .secondary {
  min-height: 36px;
  border-radius: 5px;
  box-shadow: none;
  font-size: 14px;
}

.teams-layout {
  position: relative;
  min-height: 600px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(310px, 27vw, 380px);
}

.team-detail { min-width: 0; padding: 28px 28px 42px 0; background: #fff; }

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

.member-actions,
.add-member {
  display: flex;
  align-items: center;
  gap: 5px;
}

.role-badge {
  border: 0;
  padding: 3px 0;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}

.role-badge.owner { color: var(--accent); font-weight: 650; }

.members-panel {
  min-width: 0;
  border-left: 1px solid var(--border);
  padding: 30px 0 36px 24px;
  background: #fff;
  outline: 0;
}

.members-panel:focus-visible { box-shadow: inset 2px 0 var(--accent); }

.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-title-row h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 660;
}

.member-panel-close { display: none; }

.add-member { margin-top: 18px; }

.panel-title-row h3 span {
  margin-left: 3px;
  border-radius: 3px;
  padding: 1px 4px;
  background: var(--panel-soft);
  color: var(--muted);
  font-size: 11px;
}

.add-member input {
  min-width: 0;
  flex: 1;
}

.member-list {
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 6px;
}

.member-list li {
  position: relative;
  min-width: 0;
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 14px 12px;
  border-top: 1px solid var(--border);
}

.member-list li:first-child { border-top: 0; }

.member-avatar {
  width: 36px;
  height: 36px;
  font-size: 12px;
}

.member-copy { min-width: 0; display: grid; align-content: center; gap: 1px; }

.member-list .username {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  font-size: 14px;
  font-weight: 620;
  text-overflow: ellipsis;
}

.member-role-row {
  position: relative;
  min-width: 64px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.member-actions {
  position: absolute;
  right: 0;
  top: 50%;
  width: max-content;
  flex-wrap: nowrap;
  justify-content: flex-end;
  padding-left: 8px;
  background: #fff;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-50%);
  transition: opacity 120ms ease;
  white-space: nowrap;
}

.member-list li:hover .member-actions,
.member-list li:focus-within .member-actions { opacity: 1; pointer-events: auto; }

.member-actions button {
  min-height: 30px;
  flex: 0 0 auto;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  white-space: nowrap;
}

.dissolve-team { width: 100%; min-height: 38px; margin-top: 20px; white-space: nowrap; }

.space-tabs {
  width: 100%;
  margin: 4px 0 0;
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
  font-size: 14px;
}

.space-tabs button.active {
  border-bottom-color: var(--accent);
  background: transparent;
  color: var(--accent);
  font-weight: 650;
}

.placeholder-panel {
  min-height: 420px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-top: 1px solid var(--border);
  background: #fff;
  text-align: left;
}

.placeholder-icon { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 6px; background: var(--panel-soft); color: var(--muted); }

.placeholder-panel h3 {
  margin: 0 0 5px;
  font-size: 16px;
  font-weight: 630;
}

.placeholder-panel p {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
}

.members-backdrop { display: none; }

@media (max-width: 1260px) {
  .team-topbar { align-items: flex-start; }
  .team-actions { flex-wrap: wrap; justify-content: flex-end; }
  .team-create-form { grid-template-columns: 1fr 1fr; }
  .create-form-actions { justify-content: flex-end; }
}

@media (max-width: 1160px) {
  .teams-layout { grid-template-columns: minmax(0, 1fr); }
  .team-detail { padding-right: 0; }
  .members-panel {
    position: fixed;
    z-index: 81;
    inset: 0 0 0 auto;
    width: min(360px, calc(100vw - 32px));
    padding: 26px 20px;
    border-left: 1px solid var(--border);
    overflow-y: auto;
    box-shadow: -12px 0 32px rgb(0 0 0 / 10%);
    transform: translateX(102%);
    transition: transform 160ms ease;
  }
  .members-panel[aria-hidden='true'] { visibility: hidden; }
  .members-panel.open { transform: translateX(0); }
  .member-list li { grid-template-columns: 36px minmax(0, 1fr); }
  .member-role-row { grid-column: 1 / -1; margin-top: 8px; justify-content: space-between; }
  .member-actions { position: static; padding-left: 0; opacity: 1; pointer-events: auto; transform: none; }
  .member-panel-close { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid var(--border); border-radius: 5px; background: #fff; color: var(--muted); cursor: pointer; }
  .members-backdrop { position: fixed; z-index: 80; inset: 0; display: block; border: 0; padding: 0; background: rgb(20 20 20 / 28%); }
}

@media (max-width: 760px) {
  .teams-header { margin-bottom: 18px; }
  .team-topbar { flex-direction: column; }
  .team-switcher-wrap,
  .team-actions { width: 100%; }
  .team-actions { justify-content: flex-start; }
  .team-summary { margin-right: auto; }
  .settings-trigger { width: 44px; justify-content: center; padding: 0; }
  .settings-trigger span { display: none; }
  .team-create-form { grid-template-columns: 1fr; }
  .space-tabs button { flex: 1; }
}

@media (max-width: 580px) {
  .team-switcher-wrap { align-items: stretch; flex-direction: column; }
  .team-switcher { width: 100%; }
  .create-team-trigger { justify-content: center; }
  .team-actions { display: grid; grid-template-columns: 1fr auto; }
  .team-summary { grid-column: 1 / -1; }
  .invite-trigger { justify-content: center; }
  .add-member { width: 100%; }
  .team-detail { padding-top: 24px; }
  .team-create-form input,
  .add-member input { font-size: 16px; }
}

@media (prefers-reduced-motion: reduce) {
  .team-switcher > .team-cards,
  .members-panel { transition: none; }
}
</style>
