<template>
  <view class="counter-page">
    <view class="counter-header">
      <text class="page-title">💎 我的积分</text>
      <text class="fault-badge" v-if="faultState.currentProfile !== 'normal'">
        {{ faultState.currentProfile }}
      </text>
    </view>

    <view class="counter-card">
      <text class="counter-label">积分余额</text>
      <text class="counter-value">{{ displayValue }}</text>
      <text class="counter-version">版本: {{ version }}</text>
      <text class="counter-time">更新时间: {{ updatedAtStr }}</text>
    </view>

    <view class="status-section">
      <view class="status-row">
        <text class="status-label">状态</text>
        <text class="status-value" :class="statusClass">{{ statusText }}</text>
      </view>
      <view class="status-row">
        <text class="status-label">交互延迟</text>
        <text class="status-value">{{ interactionMs }}ms</text>
      </view>
    </view>

    <view class="action-section">
      <button class="refresh-btn" @tap="onRefresh" :disabled="refreshing">
        {{ refreshing ? '同步中...' : '🔄 同步积分' }}
      </button>
      <button class="reset-btn" @tap="onReset">重置</button>
    </view>

    <view class="debug-section" v-if="showDebug">
      <text class="debug-title">调试信息</text>
      <text class="debug-text">expected: {{ expectedValue }}</text>
      <text class="debug-text">visible: {{ displayValue }}</text>
      <text class="debug-text">match: {{ expectedValue === displayValue }}</text>
      <text class="debug-text">profile: {{ faultState.currentProfile }}</text>
    </view>

    <FaultPanel />
  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { refreshCounter, fetchCounterValue } from '@/services/api'
import { getFaultState, syncFromServer } from '@/services/fault'
import {
  markInteractionStart,
  markInteractionEnd,
  getInteractionDuration,
  markPageLoadStart,
  markPageLoadEnd,
  resetMetrics
} from '@/services/perf'
import { exportPageState } from '@/services/oracle'
import FaultPanel from '@/components/FaultPanel.vue'

const faultState = getFaultState()
const displayValue = ref(0)
const expectedValue = ref(0)
const version = ref('v0')
const updatedAt = ref(0)
const refreshing = ref(false)
const interactionMs = ref(0)
const showDebug = ref(true)
const statusText = ref('就绪')

const updatedAtStr = computed(() => {
  if (!updatedAt.value) return '--'
  return new Date(updatedAt.value).toLocaleTimeString()
})

const statusClass = computed(() => {
  if (statusText.value === '成功') return 'status-success'
  if (statusText.value === '数据不一致') return 'status-error'
  return ''
})

onMounted(async () => {
  resetMetrics()
  markPageLoadStart()
  await syncFromServer()
  loadCounter()
})

onShow(async () => {
  await syncFromServer()
  loadCounter()
})

async function loadCounter() {
  try {
    const res = await fetchCounterValue()
    if (res.code === 0) {
      const serverValue = res.data.value
      const serverVersion = res.data.version
      const serverTime = res.data.updatedAt

      // wrong_mapping故障：服务端返回字段名不对，value可能是undefined
      if (serverValue === undefined || serverValue === null) {
        expectedValue.value = -1
        displayValue.value = -1
        statusText.value = '字段映射错误'
        version.value = 'ERROR'
        updatedAt.value = 0
      } else {
        expectedValue.value = serverValue
        // stale_ui故障：不更新显示值（保持旧值）
        if (faultState.staleEnabled) {
          statusText.value = '数据不一致'
        } else {
          displayValue.value = serverValue
          statusText.value = '成功'
        }
        version.value = serverVersion || 'v?'
        updatedAt.value = serverTime || 0
      }
    }
    markPageLoadEnd()
  } catch (e) {
    console.error('[Counter] Load failed:', e)
    statusText.value = '加载失败'
  }
}

async function onRefresh() {
  refreshing.value = true
  statusText.value = '刷新中...'
  markInteractionStart()

  try {
    const res = await refreshCounter()
    if (res.code === 0) {
      expectedValue.value = res.data.value

      // stale_ui故障：不更新显示值
      if (faultState.staleEnabled) {
        statusText.value = '数据不一致'
      } else if (faultState.currentProfile === 'wrong_mapping') {
        // wrong_mapping故障：错误映射
        displayValue.value = res.data.value + 100
        statusText.value = '数据不一致'
      } else {
        displayValue.value = res.data.value
        statusText.value = '成功'
      }

      version.value = res.data.version
      updatedAt.value = res.data.updatedAt
    }
  } catch (e) {
    console.error('[Counter] Refresh failed:', e)
    statusText.value = '刷新失败'
  } finally {
    markInteractionEnd()
    interactionMs.value = getInteractionDuration()
    refreshing.value = false
  }
}

function onReset() {
  displayValue.value = 0
  expectedValue.value = 0
  version.value = 'v0'
  updatedAt.value = 0
  interactionMs.value = 0
  statusText.value = '就绪'
  resetMetrics()
}

function getPageStateExport() {
  return exportPageState('counter', displayValue.value, expectedValue.value, {
    hasOverlap: false,
    imageLoaded: true,
    isBlank: false
  })
}

defineExpose({ getPageStateExport })
</script>

<style scoped>
.counter-page {
  min-height: 100vh;
  background: linear-gradient(180deg, #FFF6F6 0%, #FFE4E4 100%);
  padding: 30rpx;
}

.counter-header {
  display: flex;
  align-items: center;
  margin-bottom: 30rpx;
}

.page-title {
  font-size: 36rpx;
  font-weight: bold;
  flex: 1;
}

.fault-badge {
  font-size: 22rpx;
  color: #fff;
  background: #e74c3c;
  padding: 4rpx 16rpx;
  border-radius: 20rpx;
}

.counter-card {
  background: linear-gradient(135deg, #FFFFFF 0%, #FFF0F2 100%);
  border-radius: 32rpx;
  padding: 80rpx 40rpx;
  text-align: center;
  margin-bottom: 30rpx;
  box-shadow: 0 8rpx 32rpx rgba(233, 77, 95, 0.15);
  border: 2rpx solid #FFD4D9;
}

.counter-label {
  font-size: 28rpx;
  color: #666;
  display: block;
  margin-bottom: 20rpx;
}

.counter-value {
  font-size: 96rpx;
  font-weight: bold;
  color: #E94D5F;
  display: block;
  margin-bottom: 20rpx;
}

.counter-version {
  font-size: 24rpx;
  color: #999;
  display: block;
  margin-bottom: 8rpx;
}

.counter-time {
  font-size: 24rpx;
  color: #999;
  display: block;
}

.status-section {
  background: #fff;
  border-radius: 16rpx;
  padding: 30rpx;
  margin-bottom: 30rpx;
}

.status-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16rpx 0;
}

.status-label {
  font-size: 28rpx;
  color: #333;
}

.status-value {
  font-size: 28rpx;
  color: #666;
}

.status-success {
  color: #27ae60;
}

.status-error {
  color: #e74c3c;
}

.action-section {
  display: flex;
  gap: 20rpx;
  margin-bottom: 30rpx;
}

.refresh-btn {
  flex: 1;
  background: #E94D5F;
  color: #fff;
  border-radius: 12rpx;
  font-size: 30rpx;
  height: 88rpx;
  line-height: 88rpx;
}

.reset-btn {
  flex: 1;
  background: #ecf0f1;
  color: #333;
  border-radius: 12rpx;
  font-size: 30rpx;
  height: 88rpx;
  line-height: 88rpx;
}

.debug-section {
  background: #2c3e50;
  border-radius: 12rpx;
  padding: 20rpx;
}

.debug-title {
  font-size: 24rpx;
  color: #27ae60;
  display: block;
  margin-bottom: 12rpx;
}

.debug-text {
  font-size: 22rpx;
  color: #bdc3c7;
  display: block;
  margin-bottom: 6rpx;
  font-family: monospace;
}
</style>
