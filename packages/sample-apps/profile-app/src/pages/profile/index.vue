<template>
  <view class="page">
    <view class="avatar-row">
      <image class="avatar" :src="user.avatar" mode="aspectFill" />
      <view class="info">
        <text class="name">{{ user.name || '未登录' }}</text>
        <text class="bio">{{ user.bio || '点击下方按钮加载资料' }}</text>
      </view>
    </view>

    <view class="stats">
      <view class="stat">
        <text class="num">{{ stats.followers }}</text>
        <text class="lbl">粉丝</text>
      </view>
      <view class="stat">
        <text class="num">{{ stats.following }}</text>
        <text class="lbl">关注</text>
      </view>
      <view class="stat">
        <text class="num">{{ stats.posts }}</text>
        <text class="lbl">发帖</text>
      </view>
    </view>

    <button class="btn" @tap="loadProfile" :disabled="loading">
      {{ loading ? '加载中…' : '刷新资料' }}
    </button>

    <view class="debug" v-if="showDebug">
      <text>profile: {{ probe ? 'attached' : 'none' }}</text>
      <text>expected name: {{ expectedName }}</text>
      <text>visible name: {{ user.name }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useTriageProbe } from 'vision-triage-sdk'

const probe = useTriageProbe('profile_main')

interface User { name: string; avatar: string; bio: string }
interface Stats { followers: number; following: number; posts: number }

const user = ref<User>({ name: '', avatar: '', bio: '' })
const stats = ref<Stats>({ followers: 0, following: 0, posts: 0 })
const expectedName = ref('')
const loading = ref(false)
const showDebug = ref(true)

async function loadProfile() {
  loading.value = true
  probe.markInteractionStart()

  // 模拟一个真实 API（实际项目里会是 wx.request / uni.request）
  await new Promise<void>((resolve) => setTimeout(resolve, 200))

  const serverData = {
    name: '张三',
    avatar: 'https://picsum.photos/100/100?random=99',
    bio: '小程序测试爱好者',
    followers: 128,
    following: 64,
    posts: 32,
  }
  user.value = {
    name: serverData.name,
    avatar: serverData.avatar,
    bio: serverData.bio,
  }
  stats.value = {
    followers: serverData.followers,
    following: serverData.following,
    posts: serverData.posts,
  }
  expectedName.value = serverData.name

  probe.markInteractionEnd()
  probe.setExpected(expectedName.value)
  probe.setVisible(user.value.name)
  loading.value = false
}
</script>

<style scoped>
.page { padding: 32rpx; background: #f5f5f5; min-height: 100vh; }
.avatar-row { display: flex; align-items: center; background: #fff; padding: 24rpx; border-radius: 16rpx; margin-bottom: 24rpx; }
.avatar { width: 100rpx; height: 100rpx; border-radius: 50rpx; background: #ddd; }
.info { margin-left: 24rpx; flex: 1; }
.name { font-size: 32rpx; font-weight: bold; display: block; }
.bio { font-size: 24rpx; color: #999; display: block; }
.stats { display: flex; background: #fff; padding: 32rpx 0; border-radius: 16rpx; margin-bottom: 24rpx; }
.stat { flex: 1; text-align: center; }
.num { font-size: 36rpx; font-weight: bold; display: block; }
.lbl { font-size: 22rpx; color: #999; display: block; }
.btn { width: 100%; background: #4A90D9; color: #fff; border-radius: 12rpx; padding: 24rpx; }
.debug { margin-top: 32rpx; padding: 16rpx; background: #2c3e50; border-radius: 12rpx; }
.debug text { display: block; color: #bdc3c7; font-size: 22rpx; }
</style>
