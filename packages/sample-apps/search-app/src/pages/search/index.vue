<template>
  <view class="page">
    <view class="search-bar">
      <input class="input" v-model="keyword" placeholder="输入关键词搜索" />
      <button class="btn" @tap="onSearch" :disabled="searching">{{ searching ? '搜索中…' : '搜索' }}</button>
    </view>

    <view v-if="results.length === 0 && !searching" class="empty">
      <text>{{ keyword ? '无结果' : '请输入关键词' }}</text>
    </view>

    <view class="result" v-for="r in results" :key="r.id" @tap="goDetail(r.id)">
      <text class="r-title">{{ r.title }}</text>
      <text class="r-summary">{{ r.summary }}</text>
    </view>

    <view class="meta">
      <text>结果数: {{ results.length }} | 期望: {{ expectedCount }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useTriageProbe } from 'vision-triage-sdk'

const probe = useTriageProbe('search_main')

interface Result { id: number; title: string; summary: string }

const keyword = ref('')
const results = ref<Result[]>([])
const expectedCount = ref(0)
const searching = ref(false)

async function onSearch() {
  if (!keyword.value.trim()) return
  searching.value = true
  probe.markInteractionStart()

  await new Promise<void>(r => setTimeout(r, 150))

  const count = (keyword.value.length * 2) % 8 + 1
  expectedCount.value = count
  results.value = Array.from({ length: count }).map((_, i) => ({
    id: i + 1,
    title: `${keyword.value} 结果 ${i + 1}`,
    summary: `这是 "${keyword.value}" 的第 ${i + 1} 条搜索结果说明`,
  }))

  probe.markInteractionEnd()
  probe.setExpected(expectedCount.value)
  probe.setVisible(results.value.length)
  searching.value = false
}

function goDetail(id: number) {
  uni.navigateTo({ url: `/pages/detail/index?id=${id}` })
}
</script>

<style scoped>
.page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.search-bar { display: flex; margin-bottom: 24rpx; }
.input { flex: 1; background: #fff; padding: 18rpx 24rpx; border-radius: 12rpx; margin-right: 16rpx; font-size: 28rpx; }
.btn { background: #4A90D9; color: #fff; padding: 0 32rpx; border-radius: 12rpx; }
.empty { text-align: center; padding: 80rpx 0; color: #999; }
.result { background: #fff; padding: 24rpx; border-radius: 12rpx; margin-bottom: 16rpx; }
.r-title { font-size: 30rpx; font-weight: bold; display: block; margin-bottom: 8rpx; }
.r-summary { font-size: 24rpx; color: #666; display: block; }
.meta { margin-top: 32rpx; text-align: center; color: #999; font-size: 22rpx; }
</style>
