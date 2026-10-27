<script setup lang="ts">
import { computed } from 'vue'
import { NAlert, NButton, NInput, NInputGroup, NSpace, useDialog, useMessage } from 'naive-ui'
import { api } from '../api'
import type { IssueSection, Preview, ProfileDetail } from '../api/types'
import { copyText } from '../lib/clipboard'
import { subscriptionUrl } from '../lib/profile'
import IssueList from './IssueList.vue'

const props = defineProps<{
  profileId: number
  token: string
  dirty: boolean
  preview: Preview | null
  loading: boolean
}>()
const emit = defineEmits<{ rotated: [detail: ProfileDetail]; reload: []; goto: [section: IssueSection] }>()
const message = useMessage()
const dialog = useDialog()

const url = computed(() => subscriptionUrl(window.location.origin, props.token))

async function copy() {
  if (await copyText(url.value)) message.success('已复制订阅链接')
  else message.warning('无法访问剪贴板，请手动复制')
}

function rotate() {
  dialog.warning({
    title: '重置订阅链接',
    content: '旧链接会立即失效，所有客户端都需要改用新链接。确定继续？',
    positiveText: '重置',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        emit('rotated', await api.rotateToken(props.profileId))
        message.success('订阅链接已重置')
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}
</script>

<template>
  <NSpace vertical size="large">
    <section class="sub">
      <h3>订阅链接</h3>
      <p>在 Clash Verge Rev 等使用 Mihomo 内核的客户端中添加此链接。</p>
      <NInputGroup>
        <NInput :value="url" readonly class="mono" />
        <NButton type="primary" @click="copy">复制</NButton>
        <NButton secondary type="warning" @click="rotate">重置</NButton>
      </NInputGroup>
    </section>

    <NAlert v-if="dirty" type="warning">有未保存的修改：预览和订阅链接使用的是已保存的版本。</NAlert>

    <template v-if="preview">
      <NAlert v-if="preview.errors.length" type="error" title="方案有错误，无法生成配置（订阅链接会继续返回上次成功的版本）">
        <IssueList :issues="preview.issues" @goto="emit('goto', $event)" />
      </NAlert>
      <NAlert v-if="preview.warnings.length" type="warning" title="警告">
        <ul class="list"><li v-for="(w, i) in preview.warnings" :key="i">{{ w }}</li></ul>
      </NAlert>
    </template>

    <section class="code">
      <div class="code__bar">
        <span>生成的 Mihomo 配置</span>
        <NButton size="tiny" quaternary class="code__btn" :loading="loading" @click="emit('reload')">重新生成</NButton>
      </div>
      <pre v-if="preview?.content" class="yaml">{{ preview.content }}</pre>
      <p v-else class="code__empty">{{ loading ? '正在生成…' : preview?.errors.length ? '修正上面的错误并保存后，这里会显示生成的配置。' : '没有可显示的配置。' }}</p>
    </section>
  </NSpace>
</template>

<style scoped>
.sub h3 {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}
.sub p {
  color: var(--rf-muted);
  font-size: 13px;
  margin: 4px 0 10px;
}
.list {
  margin: 0;
  padding-left: 20px;
}
.code {
  background: #10263c;
  border-radius: 10px;
  overflow: hidden;
}
.code__bar {
  align-items: center;
  border-bottom: 1px solid #22405e;
  color: #9fb4c8;
  display: flex;
  font-size: 12px;
  justify-content: space-between;
  padding: 6px 8px 6px 14px;
}
.code__btn {
  color: #c4d2df;
}
.yaml {
  color: #dbe6ef;
  font-family: var(--rf-mono);
  font-size: 12.5px;
  line-height: 1.6;
  margin: 0;
  max-height: 600px;
  overflow: auto;
  padding: 14px 16px;
  tab-size: 2;
}
.code__empty {
  color: #9fb4c8;
  font-size: 13px;
  margin: 0;
  padding: 16px;
}
</style>
