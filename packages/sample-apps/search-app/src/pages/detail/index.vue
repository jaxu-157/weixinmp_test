<template>
  <view class="page">
    <text class="title">{{ title }}</text>
    <text class="body">{{ body }}</text>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { useTriageProbe } from 'vision-triage-sdk'

const probe = useTriageProbe('search_detail')

const title = ref('')
const body = ref('')

onLoad((options) => {
  const id = options?.id || '0'
  title.value = `详情 #${id}`
  body.value = `这是一篇关于 #${id} 的详细内容，用于验证页面跳转后 probe 能否正常工作。`
  probe.setExpected(`详情 #${id}`)
  probe.setVisible(title.value)
})

onMounted(() => { probe.markPageLoadEnd() })
</script>

<style scoped>
.page { padding: 32rpx; background: #f5f5f5; min-height: 100vh; }
.title { font-size: 36rpx; font-weight: bold; display: block; margin-bottom: 24rpx; }
.body { font-size: 28rpx; color: #444; line-height: 1.6; }
</style>
