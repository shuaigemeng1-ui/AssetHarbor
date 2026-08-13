// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

function mountView() {
  return mount(TeamsView, {
    props: { user: { id: 7, username: 'alice', role: 'user' } },
    global: { stubs: { GalleryView: true, VideoView: true, CollectionsView: true } },
  })
}

describe('TeamsView permissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listTeams.mockResolvedValue([team])
    api.getTeam.mockResolvedValue(detail)
    feedback.confirmAction.mockResolvedValue(true)
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
})
