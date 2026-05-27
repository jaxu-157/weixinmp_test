<template>
  <view class="page">
    <view class="header">
      <text class="title">待办清单</text>
      <text class="badge" v-if="completedCount === expectedCount && expectedCount > 0">全部完成</text>
    </view>

    <view class="card" v-for="(item, idx) in items" :key="idx">
      <text class="item-title">{{ item.title }}</text>
      <button class="toggle" @tap="toggleItem(idx)">
        {{ item.done ? '✅' : '⬜' }}
      </button>
    </view>

    <button class="add-btn" @tap="addItem">添加任务</button>

    <view class="footer">
      <text>已完成 {{ completedCount }} / {{ items.length }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

// ---------- Vision-Triage SDK 集成第 2 步 ----------
import { useTriageProbe } from 'vision-triage-sdk'
const probe = useTriageProbe('checklist_home')

interface Item { title: string; done: boolean }

const items = ref<Item[]>([
  { title: '写作业', done: false },
  { title: '复习概念', done: false },
  { title: '提交代码', done: false },
])

const completedCount = computed(() => items.value.filter(i => i.done).length)
const expectedCount = computed(() => items.value.length)

onMounted(() => {
  probe.markPageLoadEnd()
  syncProbe()
})

function toggleItem(idx: number) {
  probe.markInteractionStart()
  items.value[idx].done = !items.value[idx].done
  probe.markInteractionEnd()
  syncProbe()
}

function addItem() {
  probe.markInteractionStart()
  items.value.push({ title: `新任务 ${items.value.length + 1}`, done: false })
  probe.markInteractionEnd()
  syncProbe()
}

function syncProbe() {
  // 把"完成数 vs 总数"的语义告诉 SDK，方便后端做功能断言
  probe.setExpected(expectedCount.value)
  probe.setVisible(completedCount.value === expectedCount.value
    ? expectedCount.value
    : completedCount.value)
}
</script>

<style scoped>
.page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.header { display: flex; align-items: center; margin-bottom: 24rpx; }
.title { flex: 1; font-size: 36rpx; font-weight: bold; }
.badge { font-size: 22rpx; color: #fff; background: #27ae60; padding: 4rpx 16rpx; border-radius: 20rpx; }
.card { display: flex; align-items: center; background: #fff; padding: 24rpx; margin-bottom: 16rpx; border-radius: 12rpx; }
.item-title { flex: 1; font-size: 30rpx; }
.toggle { font-size: 36rpx; }
.add-btn { width: 100%; background: #4A90D9; color: #fff; padding: 24rpx; border-radius: 12rpx; margin: 24rpx 0; }
.footer { text-align: center; color: #999; font-size: 24rpx; }
</style>
