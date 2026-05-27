<template>
  <view class="feed-page">
    <view class="filter-bar">
      <text class="filter-title">🛍 今日推荐</text>
      <text class="fault-badge" v-if="faultState.currentProfile !== 'normal'">
        {{ faultState.currentProfile }}
      </text>
    </view>

    <scroll-view
      scroll-y
      class="feed-scroll"
      @scrolltolower="loadMore"
      :refresher-enabled="true"
      @refresherrefresh="onRefresh"
      :refresher-triggered="refreshing"
    >
      <view class="memory-warning" v-if="faultState.memoryPressure">
        <text class="warning-text">⚠ 内存压力模拟中</text>
      </view>
      <view class="feed-list">
        <view
          class="feed-card"
          v-for="item in feedList"
          :key="item.id"
          :class="{ 'card-overlap': faultState.overlapEnabled }"
          @tap="onCardTap(item)"
        >
          <image
            class="feed-image"
            :src="item.imageUrl"
            mode="aspectFill"
            :class="{ 'image-blur': faultState.blurLevel > 0 }"
            @load="onImageLoad(item.id)"
            @error="onImageError(item.id)"
          />
          <view class="feed-info">
            <text class="feed-title">{{ item.title }}</text>
            <text class="feed-subtitle">{{ item.subtitle }}</text>
            <view class="feed-tags">
              <text class="tag" v-for="tag in item.tags" :key="tag">{{ tag }}</text>
            </view>
          </view>
        </view>
      </view>

      <view class="loading-tip" v-if="loading">
        <text>加载中...</text>
      </view>
      <view class="empty-tip" v-if="!loading && feedList.length === 0">
        <text>暂无数据</text>
      </view>
    </scroll-view>

    <FaultPanel />
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { fetchFeedList, type FeedItem } from '@/services/api'
import { getFaultState, syncFromServer } from '@/services/fault'
import { markPageLoadStart, markPageLoadEnd, resetMetrics } from '@/services/perf'
import { exportPageState } from '@/services/oracle'
import FaultPanel from '@/components/FaultPanel.vue'

const faultState = getFaultState()
const feedList = ref<FeedItem[]>([])
const loading = ref(false)
const refreshing = ref(false)
const currentPage = ref(1)
const imageLoadedMap = ref<Record<number, boolean>>({})

onMounted(async () => {
  resetMetrics()
  markPageLoadStart()
  await syncFromServer()
  loadFeed()
  if (faultState.memoryPressure) {
    simulateMemoryPressure()
  }
})

onShow(async () => {
  await syncFromServer()
  currentPage.value = 1
  loadFeed()
  if (faultState.memoryPressure) {
    simulateMemoryPressure()
  }
})

async function loadFeed() {
  loading.value = true
  try {
    const res = await fetchFeedList(currentPage.value)
    if (res.code === 0) {
      if (currentPage.value === 1) {
        feedList.value = res.data
      } else {
        feedList.value.push(...res.data)
      }
    }
  } catch (e) {
    console.error('[Feed] Load failed:', e)
  } finally {
    loading.value = false
    refreshing.value = false
    markPageLoadEnd()
  }
}

function loadMore() {
  currentPage.value++
  loadFeed()
}

function onRefresh() {
  refreshing.value = true
  currentPage.value = 1
  resetMetrics()
  markPageLoadStart()
  loadFeed()
}

function onCardTap(item: FeedItem) {
  console.log('[Feed] Card tapped:', item.id)
}

function onImageLoad(id: number) {
  imageLoadedMap.value[id] = true
}

function onImageError(id: number) {
  imageLoadedMap.value[id] = false
  console.warn('[Feed] Image load failed:', id)
}

function simulateMemoryPressure() {
  const bigArray: number[][] = []
  for (let i = 0; i < 1000; i++) {
    bigArray.push(new Array(1000).fill(Math.random()))
  }
  console.warn('[Feed] Memory pressure simulated, array size:', bigArray.length)
}

function getPageStateExport() {
  return exportPageState('feed', feedList.value.length, undefined, {
    hasOverlap: faultState.overlapEnabled,
    imageLoaded: Object.values(imageLoadedMap.value).every(Boolean),
    isBlank: feedList.value.length === 0 && !loading.value
  })
}

defineExpose({ getPageStateExport })
</script>

<style scoped>
.feed-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #FFF6F6 0%, #FFE4E4 100%);
}

.filter-bar {
  display: flex;
  align-items: center;
  padding: 28rpx 40rpx;
  background: linear-gradient(90deg, #E94D5F 0%, #FF7A8B 100%);
  box-shadow: 0 4rpx 20rpx rgba(233, 77, 95, 0.3);
}

.filter-title {
  font-size: 38rpx;
  font-weight: 900;
  flex: 1;
  color: #fff;
  letter-spacing: 2rpx;
}

.fault-badge {
  font-size: 22rpx;
  color: #E94D5F;
  background: #FFF;
  padding: 6rpx 20rpx;
  border-radius: 30rpx;
  font-weight: bold;
}

.feed-scroll {
  flex: 1;
  height: 0;
}

.feed-list {
  display: flex;
  flex-direction: column;
  padding: 20rpx;
}

.feed-card {
  width: 100%;
  margin: 16rpx 0;
  background: #FFF;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: 0 6rpx 24rpx rgba(233, 77, 95, 0.12);
  border-left: 8rpx solid #E94D5F;
}

.card-overlap {
  margin-top: -50rpx;
  z-index: 1;
}

.feed-image {
  width: 100%;
  height: 360rpx;
}

.image-blur {
  filter: blur(10px);
}

.feed-info {
  padding: 24rpx;
}

.feed-title {
  font-size: 32rpx;
  font-weight: bold;
  display: block;
  margin-bottom: 10rpx;
  color: #2C2C2C;
}

.feed-subtitle {
  font-size: 26rpx;
  color: #888;
  display: block;
  margin-bottom: 12rpx;
}

.feed-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
}

.tag {
  font-size: 22rpx;
  color: #FFF;
  background: linear-gradient(90deg, #FF7A8B 0%, #E94D5F 100%);
  padding: 6rpx 16rpx;
  border-radius: 16rpx;
  font-weight: bold;
}

.memory-warning {
  background: #FFB000;
  padding: 20rpx 32rpx;
  margin: 16rpx 20rpx;
  border-radius: 16rpx;
}

.warning-text {
  color: #FFF;
  font-size: 28rpx;
  font-weight: bold;
}

.loading-tip,
.empty-tip {
  text-align: center;
  padding: 50rpx;
  color: #E94D5F;
  font-size: 30rpx;
}
</style>
