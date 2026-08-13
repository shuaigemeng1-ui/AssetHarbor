import { describe, expect, it } from 'vitest'
import { formatApiErrorDetail } from '../api'

describe('API error detail formatting', () => {
  it('formats FastAPI/Pydantic validation arrays into a readable message', () => {
    expect(formatApiErrorDetail([
      { loc: ['body', 'filename'], msg: 'Field required', type: 'missing' },
      { loc: ['body', 'size'], msg: 'Input should be greater than 0', type: 'greater_than' },
    ], 422)).toBe('filename：Field required；size：Input should be greater than 0')
  })

  it('keeps string details and falls back to the HTTP status', () => {
    expect(formatApiErrorDetail('存储配额不足', 413)).toBe('存储配额不足')
    expect(formatApiErrorDetail(null, 503)).toBe('HTTP 503')
  })

  it('localizes stable storage admission errors', () => {
    expect(formatApiErrorDetail('user storage quota exceeded', 413)).toBe('用户累计存储额度不足')
    expect(formatApiErrorDetail('team storage quota exceeded', 413)).toBe('团队累计存储额度不足')
    expect(formatApiErrorDetail('insufficient storage space', 507)).toBe('服务器可用存储空间不足')
  })

  it('localizes stable password change errors', () => {
    expect(formatApiErrorDetail('current password is incorrect', 400)).toBe('当前密码不正确')
    expect(formatApiErrorDetail('new password must differ from the current one', 400)).toBe('新密码不能与当前密码相同')
    expect(formatApiErrorDetail('credentials changed concurrently; sign in again', 409)).toBe('账户凭据已发生变化，请重新登录')
  })
})
