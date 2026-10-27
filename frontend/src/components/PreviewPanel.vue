<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NInput, NInputGroup, NSpace, NText, useDialog, useMessage } from 'naive-ui'
import { api } from '../api'
import type { Preview, ProfileDetail } from '../api/types'
import { copyText } from '../lib/clipboard'
import { subscriptionUrl } from '../lib/profile'

const props = defineProps<{ profileId: number; token: string; dirty: boolean; version: number }>()
const emit = defineEmits<{ rotated: [detail: ProfileDetail] }>()
const message = useMessage()
const dialog = useDialog()

const preview = ref<Preview | null>(null)
const loading = ref(false)
const url = computed(() => subscriptionUrl(window.location.origin, props.token))

let seq = 0
async function load() {
  const mine = ++seq
  loading.value = true
  try {
    const r = await api.preview(props.profileId)
    if (mine === seq) preview.value = r
  } catch (e) {
    if (mine === seq) message.error((e as Error).message)
  } finally {
    if (mine === seq) loading.value = false
  }
}
onMounted(load)
watch(() => props.version, load)

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
    <NCard title="订阅链接" size="small">
      <NSpace vertical>
        <NInputGroup>
          <NInput :value="url" readonly />
          <NButton @click="copy">复制</NButton>
          <NButton type="warning" ghost @click="rotate">重置</NButton>
        </NInputGroup>
        <NText depth="3">在 Clash Verge Rev 等使用 Mihomo 内核的客户端中添加此订阅链接。</NText>
      </NSpace>
    </NCard>

    <NAlert v-if="dirty" type="warning">有未保存的修改：预览和订阅链接使用的是已保存的版本。</NAlert>
    <NButton :loading="loading" @click="load">重新生成预览</NButton>

    <template v-if="preview">
      <NAlert v-if="preview.errors.length" type="error" title="方案有错误，无法生成配置（订阅链接会继续返回上次成功的版本）">
        <ul class="list"><li v-for="(e, i) in preview.errors" :key="i">{{ e }}</li></ul>
      </NAlert>
      <NAlert v-if="preview.warnings.length" type="warning" title="警告">
        <ul class="list"><li v-for="(w, i) in preview.warnings" :key="i">{{ w }}</li></ul>
      </NAlert>
      <pre v-if="preview.content" class="yaml">{{ preview.content }}</pre>
    </template>
  </NSpace>
</template>

<style scoped>
.list {
  margin: 0;
  padding-left: 20px;
}
.yaml {
  background: #f6f8fa;
  border-radius: 6px;
  font-size: 12px;
  max-height: 600px;
  overflow: auto;
  padding: 12px;
}
</style>
