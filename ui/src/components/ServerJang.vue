<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { inject, ref } from 'vue'

const store = useConfigStore()
const axios = inject('axios')

const { server_push_enable, sendKey } = storeToRefs(store)

const test_result = ref('')
const testing = ref(false)
const test_error = ref(false)

async function test_push() {
  if (testing.value) return
  testing.value = true
  test_error.value = false
  test_result.value = '正在发送……'
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/test-serverJang-push`)
    test_result.value = response.data
    test_error.value = String(response.data).startsWith('发送失败')
  } catch (error) {
    test_error.value = true
    test_result.value =
      error.response?.data?.message || error.message || '发送失败，请检查 SENDKEY 后重试'
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <n-card
    title="Server酱推送通知"
    class="serverjang-settings"
    data-settings-keywords="Server酱 SENDKEY 推送 key 微信 通知 测试通知"
  >
    <div class="serverjang-enable-row" data-settings-label="启用 Server酱推送">
      <div class="serverjang-enable-copy">
        <span>启用 Server酱推送</span>
        <p>通过 Server酱接收任务汇总和异常提醒。该功能仍在建设中。</p>
      </div>
      <n-switch v-model:value="server_push_enable" aria-label="启用 Server酱推送" />
    </div>
    <n-form class="settings-form-stacked" label-placement="top" :show-feedback="false">
      <n-form-item label="SENDKEY">
        <template #label>
          <span class="serverjang-field-label">
            SENDKEY
            <help-text label="查看 Server酱 SENDKEY 获取方法">
              什么是 Server酱？参考：
              <n-button text tag="a" href="https://sct.ftqq.com" target="_blank" type="primary">
                https://sct.ftqq.com
              </n-button>
            </help-text>
          </span>
        </template>
        <n-input
          v-model:value="sendKey"
          type="password"
          show-password-on="click"
          placeholder="填写 Server酱推送 key"
          autocomplete="off"
          :input-props="{ 'aria-label': 'SENDKEY', spellcheck: false }"
        />
      </n-form-item>
    </n-form>
    <template v-if="server_push_enable">
      <div class="serverjang-test" data-settings-label="发送测试通知">
        <div class="serverjang-test-copy">
          <span>检查推送配置</span>
          <p>发送一条测试通知，确认 Server酱能够收到消息。</p>
        </div>
        <n-button :loading="testing" :disabled="testing" @click="test_push">发送测试通知</n-button>
      </div>
      <p
        v-if="test_result"
        class="serverjang-test-result"
        :class="{ 'is-error': test_error }"
        role="status"
      >
        {{ test_result }}
      </p>
    </template>
  </n-card>
</template>

<style scoped>
.serverjang-settings {
  container: serverjang-settings / inline-size;
}

.serverjang-enable-row,
.serverjang-test {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.serverjang-enable-row {
  padding-bottom: 20px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--settings-card-border, var(--mower-border));
}

.serverjang-enable-copy,
.serverjang-test-copy {
  flex: 1 1 220px;
  min-width: 0;
}

.serverjang-enable-copy > span,
.serverjang-test-copy > span {
  font-size: 14px;
}

.serverjang-enable-copy p,
.serverjang-test-copy p {
  margin: 4px 0 0;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.serverjang-field-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.serverjang-test {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--settings-card-border, var(--mower-border));
}

.serverjang-test-result {
  margin: 16px 0 0;
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--mower-control-surface);
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.serverjang-test-result.is-error {
  color: var(--mower-error);
}
</style>
