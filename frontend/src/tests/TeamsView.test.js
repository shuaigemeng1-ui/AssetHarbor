// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  addTeamMember: vi.fn(),
  changeTeamMemberRole: vi.fn(),
  createTeam: vi.fn(),
  deleteTeam: vi.fn(),
  getTeam: vi.fn(),
  listTeams: vi.fn(),
  removeTeamMember: vi.fn(),
}))
const feedback = vi.hoisted(() => ({ confirmAction: vi.fn(), toast: vi.fn() }))

vi.mock('../api', () => api)
vi.mock('../stores/feedback', () => feedback)

import TeamsView from '../components/TeamsView.vue'

const team = { id: 3, name: '设计团队', description: '', role: 'admin', member_count: 3 }
const detail = {
  ...team,
  members: [
    { id: 10, username: 'owner', role: 'owner' },
    { id: 11, username: 'alice', role: 'admin' },
    { id: 12, username: 'bob', role: 'member' },
  ],
}

function mountView({ user = { id: 7, username: 'alice', role: 'user' } } = {}) {
  const wrapper = mount(TeamsView, {
    props: { user },
    global: { stubs: { GalleryView: true, VideoView: true, CollectionsView: true } },
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

const mountedWrappers = []

describe('TeamsView permissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listTeams.mockResolvedValue([team])
    api.getTeam.mockResolvedValue(detail)
    feedback.confirmAction.mockResolvedValue(true)
  })

  afterEach(() => {
    mountedWrappers.splice(0).forEach(wrapper => wrapper.unmount())
    document.body.classList.remove('modal-open')
  })

  it('lets a team admin manage members but not roles or team dissolution', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('.team-cards button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('解散团队')
    expect(wrapper.text()).not.toContain('设为管理员')
    expect(wrapper.text()).not.toContain('团队设置')
    const bobRow = wrapper.findAll('.member-list li').find(row => row.text().includes('bob'))
    expect(bobRow.text()).toContain('移除')
    expect(wrapper.text()).toContain('退出团队')
  })

  it('clears the selected team and refreshes membership after leaving', async () => {
    api.removeTeamMember.mockResolvedValue(undefined)
    api.listTeams.mockResolvedValueOnce([team]).mockResolvedValueOnce([])
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('.team-cards button').trigger('click')
    await flushPromises()
    const selfRow = wrapper.findAll('.member-list li').find(row => row.text().includes('alice'))
    await selfRow.findAll('button').find(button => button.text() === '退出团队').trigger('click')
    await flushPromises()

    expect(api.removeTeamMember).toHaveBeenCalledWith(3, 11)
    expect(feedback.confirmAction).toHaveBeenCalledWith(expect.objectContaining({ title: '退出团队' }))
    expect(wrapper.text()).toContain('选择一个团队')
    expect(wrapper.text()).toContain('还没有加入任何团队')
  })

  it('ignores a slower team detail response after the user opens another team', async () => {
    const secondTeam = { ...team, id: 4, name: '研发团队' }
    api.listTeams.mockResolvedValue([team, secondTeam])
    let resolveFirst
    let resolveSecond
    api.getTeam.mockImplementation(id => new Promise(resolve => {
      if (id === 3) resolveFirst = resolve
      else resolveSecond = resolve
    }))
    const wrapper = mountView()
    await flushPromises()

    const buttons = wrapper.findAll('.team-cards button')
    buttons[0].trigger('click')
    buttons[1].trigger('click')
    await flushPromises()
    resolveSecond({ ...detail, id: 4, name: '研发团队' })
    await flushPromises()
    resolveFirst(detail)
    await flushPromises()

    expect(wrapper.get('.team-detail h2').text()).toBe('研发团队')
  })

  it('uses the member drawer at 1366px after accounting for the sidebar', async () => {
    api.removeTeamMember.mockResolvedValue(undefined)
    api.listTeams.mockResolvedValueOnce([team]).mockResolvedValueOnce([])
    const originalMatchMedia = window.matchMedia
    const mediaQuery = {
      matches: true,
      media: '(max-width: 1408px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }
    window.matchMedia = vi.fn(() => mediaQuery)
    let wrapper
    try {
      wrapper = mountView()
      await flushPromises()
      await wrapper.get('.team-cards button').trigger('click')
      await flushPromises()
      await wrapper.get('.team-summary').trigger('click')
      await flushPromises()

      expect(window.matchMedia).toHaveBeenCalledWith('(max-width: 1408px)')
      expect(wrapper.get('.members-panel').attributes('role')).toBe('dialog')
      expect(wrapper.get('.members-panel').attributes('aria-modal')).toBe('true')
      expect(wrapper.get('.members-panel').attributes('aria-hidden')).toBeUndefined()
      expect(document.body.classList.contains('modal-open')).toBe(true)
      expect(wrapper.get('.team-detail').attributes('inert')).toBe('')
      const selfRow = wrapper.findAll('.member-list li').find(row => row.text().includes('alice'))
      await selfRow.findAll('button').find(button => button.text() === '退出团队').trigger('click')
      await flushPromises()

      expect(api.removeTeamMember).toHaveBeenCalledWith(3, 11)
      expect(wrapper.text()).toContain('选择一个团队')
      expect(document.body.classList.contains('modal-open')).toBe(false)
      expect(wrapper.get('.team-topbar').attributes('inert')).toBeUndefined()
    } finally {
      window.matchMedia = originalMatchMedia
    }
  })

  it('toggles team settings with the trigger and returns to members from the panel', async () => {
    const wrapper = mountView({ user: { id: 7, username: 'alice', role: 'admin' } })
    await flushPromises()
    await wrapper.get('.team-cards button').trigger('click')
    await flushPromises()

    const trigger = wrapper.get('.settings-trigger')
    expect(trigger.attributes('aria-pressed')).toBe('false')

    await trigger.trigger('click')
    expect(trigger.attributes('aria-pressed')).toBe('true')
    expect(wrapper.text()).toContain('解散团队')
    expect(wrapper.text()).toContain('返回成员列表')

    // Clicking the trigger again leaves the settings view (the wide-layout
    // cancel path, where no drawer close affordance exists).
    await trigger.trigger('click')
    expect(trigger.attributes('aria-pressed')).toBe('false')
    expect(wrapper.text()).not.toContain('解散团队')
    expect(wrapper.text()).not.toContain('返回成员列表')

    // Re-open and leave via the explicit panel action.
    await trigger.trigger('click')
    expect(wrapper.text()).toContain('解散团队')
    const back = wrapper.findAll('button').find(button => button.text() === '返回成员列表')
    expect(back).toBeTruthy()
    await back.trigger('click')
    expect(wrapper.text()).not.toContain('解散团队')
    expect(trigger.attributes('aria-pressed')).toBe('false')
  })
})
