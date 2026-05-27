<template>
  <view class="layout-page">
    <view class="layout-header">
      <text class="page-title">🎁 活动专区</text>
      <text class="fault-badge" v-if="faultState.currentProfile !== 'normal'">
        {{ faultState.currentProfile }}
      </text>
    </view>

    <scroll-view scroll-y class="layout-scroll">
      <view class="overlap-warning" v-if="faultState.overlapEnabled">
        <text class="warning-text">⚠ 布局错位故障已激活</text>
      </view>
      <view class="memory-warning" v-if="faultState.memoryPressure">
        <text class="warning-text">⚠ 内存压力模拟中</text>
      </view>
      <view class="card-grid">
        <view
          class="layout-card"
          v-for="card in layoutCards"
          :key="card.id"
          :class="{
            'card-shifted': faultState.overlapEnabled && card.id % 2 === 0,
            'card-collide': faultState.overlapEnabled && card.id % 3 === 0,
            'card-large': card.height > 200
          }"
          :style="getCardStyle(card)"
        >
          <image
            class="card-image"
            :src="card.imageUrl"
            mode="aspectFill"
            :style="{ height: card.height + 'rpx' }"
          />
          <view class="card-body">
            <text class="card-title" :class="{ 'title-overflow': card.title.length > 20 }">
              {{ card.title }}
            </text>
            <text class="card-desc">{{ card.description }}</text>
            <view class="card-tags">
              <text class="card-tag" v-for="tag in card.tags" :key="tag">{{ tag }}</text>
            </view>
            <button class="card-btn" size="mini" @tap="onCardAction(card)">操作</button>
          </view>
        </view>
      </view>

      <view class="loading-tip" v-if="loading">
        <text>加载中...</text>
      </view>
    </scroll-view>

    <FaultPanel />
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { fetchLayoutCards, type LayoutCard } from '@/services/api'
import { getFaultState, syncFromServer } from '@/services/fault'
import { markPageLoadStart, markPageLoadEnd, resetMetrics } from '@/services/perf'
import { exportPageState } from '@/services/oracle'
import FaultPanel from '@/components/FaultPanel.vue'

const faultState = getFaultState()
const layoutCards = ref<LayoutCard[]>([])
const loading = ref(false)

onMounted(async () => {
  resetMetrics()
  markPageLoadStart()
  await syncFromServer()
  loadCards()
})

onShow(async () => {
  await syncFromServer()
  loadCards()
})

async function loadCards() {
  loading.value = true
  try {
    const res = await fetchLayoutCards()
    if (res.code === 0) {
      layoutCards.value = res.data
    }
  } catch (e) {
    console.error('[Layout] Load failed:', e)
  } finally {
    loading.value = false
    markPageLoadEnd()
  }
}

function getCardStyle(card: LayoutCard) {
  if (faultState.overlapEnabled && card.id % 3 === 0) {
    return { transform: 'translateY(-20rpx)', marginLeft: '-10rpx' }
  }
  return {}
}

function onCardAction(card: LayoutCard) {
  console.log('[Layout] Card action:', card.id)
  uni.showToast({ title: `操作: ${card.title}`, icon: 'none' })
}

function getPageStateExport() {
  return exportPageState('layout', layoutCards.value.length, undefined, {
    hasOverlap: faultState.overlapEnabled,
    imageLoaded: true,
    isBlank: layoutCards.value.length === 0 && !loading.value
  })
}

defineExpose({ getPageStateExport })
</script>

<style scoped>
.layout-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

.layout-header {
  display: flex;
  align-items: center;
  padding: 20rpx 30rpx;
  background: #fff;
}

.page-title {
  font-size: 32rpx;
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

.layout-scroll {
  flex: 1;
  height: 0;
}

.card-grid {
  display: flex;
  flex-wrap: wrap;
  padding: 20rpx;
  gap: 20rpx;
}

.layout-card {
  width: calc(50% - 30rpx);
  background: #fff;
  border-radius: 16rpx;
  overflow: hidden;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.06);
  transition: all 0.3s;
}

.card-shifted {
  transform: translateX(80rpx) rotate(5deg);
  z-index: 2;
  border: 4rpx solid #e74c3c;
  margin-top: -60rpx;
}

.card-collide {
  transform: translateY(-80rpx) translateX(-30rpx) rotate(-3deg);
  z-index: 3;
  border: 4rpx solid #e67e22;
  opacity: 0.85;
}

.overlap-warning,
.memory-warning {
  background: #e74c3c;
  padding: 16rpx 30rpx;
  margin: 0 20rpx 10rpx;
  border-radius: 8rpx;
}

.memory-warning {
  background: #e67e22;
}

.warning-text {
  color: #fff;
  font-size: 26rpx;
}

.card-large {
  width: 100%;
}

.card-image {
  width: 100%;
  min-height: 200rpx;
}

.card-body {
  padding: 16rpx;
}

.card-title {
  font-size: 28rpx;
  font-weight: bold;
  display: block;
  margin-bottom: 8rpx;
}

.title-overflow {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-desc {
  font-size: 24rpx;
  color: #666;
  display: block;
  margin-bottom: 12rpx;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
  margin-bottom: 12rpx;
}

.card-tag {
  font-size: 20rpx;
  color: #8e44ad;
  background: #f4ecf7;
  padding: 4rpx 12rpx;
  border-radius: 8rpx;
}

.card-btn {
  font-size: 24rpx;
  background: #E94D5F;
  color: #fff;
  border-radius: 8rpx;
}

.loading-tip {
  text-align: center;
  padding: 40rpx;
  color: #999;
}
</style>
