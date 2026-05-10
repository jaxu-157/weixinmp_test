<template>
  <view class="feed-page">
    <view class="filter-bar">
      <text class="filter-title">图片流</text>
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

onMounted(() => {
  resetMetrics()
  markPageLoadStart()
  loadFeed()
})

onShow(async () => {
  // 从服务器同步故障状态
  await syncFromServer()
  // 页面显示时如果有内存压力故障，模拟大量数据
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
  background: #f5f5f5;
}

.filter-bar {
  display: flex;
  align-items: center;
  padding: 20rpx 30rpx;
  background: #fff;
}

.filter-title {
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

.feed-scroll {
  flex: 1;
  height: 0;
}

.feed-list {
  display: flex;
  flex-wrap: wrap;
  padding: 10rpx;
}

.feed-card {
  width: calc(50% - 20rpx);
  margin: 10rpx;
  background: #fff;
  border-radius: 16rpx;
  overflow: hidden;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.08);
  transition: transform 0.2s;
}

.card-overlap {
  margin-top: -40rpx;
  z-index: 1;
}

.feed-image {
  width: 100%;
  height: 300rpx;
}

.image-blur {
  filter: blur(10px);
}

.feed-info {
  padding: 16rpx;
}

.feed-title {
  font-size: 28rpx;
  font-weight: bold;
  display: block;
  margin-bottom: 8rpx;
}

.feed-subtitle {
  font-size: 24rpx;
  color: #666;
  display: block;
  margin-bottom: 8rpx;
}

.feed-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
}

.tag {
  font-size: 20rpx;
  color: #4A90D9;
  background: #eef4fd;
  padding: 4rpx 12rpx;
  border-radius: 8rpx;
}

.loading-tip,
.empty-tip {
  text-align: center;
  padding: 40rpx;
  color: #999;
  font-size: 28rpx;
}
</style>
