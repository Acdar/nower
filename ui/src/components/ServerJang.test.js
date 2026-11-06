import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, effectScope, ref } from 'vue'
import { createPinia } from 'pinia'
import ServerJang from './ServerJang.vue'
import { useConfigStore } from '@/stores/config'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

let scope
let store
let component
let http

beforeEach(() => {
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', ref(false))
  http = { get: vi.fn() }
  app.provide('axios', http)
  store = app.runWithContext(() => useConfigStore())
  scope = effectScope()
  component = scope.run(() => app.runWithContext(() => ServerJang.setup({}, { expose: vi.fn() })))
})

afterEach(() => {
  scope.stop()
  store.$dispose()
})

describe('test server酱 push feedback', () => {
  it('reports a successful test push', async () => {
    http.get.mockResolvedValue({ data: '发送成功' })

    await component.test_push()

    expect(http.get).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/test-serverJang-push')
    )
    expect(component.test_result.value).toBe('发送成功')
    expect(component.test_error.value).toBe(false)
    expect(component.testing.value).toBe(false)
  })

  it('keeps the backend send failure visible even when the request succeeds', async () => {
    http.get.mockResolvedValue({ data: '发送失败 : pushkey 无效' })

    await component.test_push()

    expect(component.test_result.value).toBe('发送失败 : pushkey 无效')
    expect(component.test_error.value).toBe(true)
    expect(component.testing.value).toBe(false)
  })

  it('shows a request failure and permits a later retry', async () => {
    http.get.mockRejectedValueOnce(new Error('连接中断'))
    await component.test_push()
    expect(component.test_result.value).toBe('连接中断')
    expect(component.test_error.value).toBe(true)
    expect(component.testing.value).toBe(false)

    http.get.mockResolvedValueOnce({ data: '发送成功' })
    await component.test_push()
    expect(component.test_result.value).toBe('发送成功')
    expect(component.test_error.value).toBe(false)
    expect(http.get).toHaveBeenCalledTimes(2)
  })

  it('prevents repeated sends until the active send finishes', async () => {
    let finish
    http.get.mockReturnValue(new Promise((resolve) => (finish = resolve)))

    const sending = component.test_push()
    await component.test_push()

    expect(component.testing.value).toBe(true)
    expect(component.test_result.value).toBe('正在发送……')
    expect(http.get).toHaveBeenCalledTimes(1)
    finish({ data: '发送成功' })
    await sending
    expect(component.testing.value).toBe(false)
  })
})
