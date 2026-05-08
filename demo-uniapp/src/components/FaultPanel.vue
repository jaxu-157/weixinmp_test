<template>
  <view class="fault-panel" v-if="visible">
    <view class="panel-mask" @tap="togglePanel" />
    <view class="panel-content">
      <view class="panel-header">
        <text class="panel-title">故障面板</text>
        <text class="panel-close" @tap="togglePanel">×</text>
      </view>

      <view class="panel-body">
        <view class="current-profile">
          <text class="label">当前 Profile:</text>
          <text class="value" :class="profileClass">{{ faultState.currentProfile }}</text>
        </view>

        <view class="profile-list">
          <view
            class="profile-item"
            v-for="p in profiles"
            :key="p.value"
            :class="{ active: faultState.currentProfile === p.value }"
            @tap="switchProfile(p.value)"
          >
            <text class="profile-name">{{ p.label }}</text>
            <text class="profile-desc">{{ p.desc }}</text>
          </view>
        </view>

        <view class="panel-actions">
          <button class="btn-reset" size="mini" @tap="onReset">恢复 Normal</button>
        </view>
      </view>
    </view>
  </view>

  <view class="panel-trigger" @tap="togglePanel" v-if="!visible">
    <text class="trigger-icon">⚙</text>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { getFaultState, activateFault, resetFault, type FaultProfile } from '@/services/fault'
import { activateFaultOnServer } from '@/services/api'

const faultState = getFaultState()
const visible = ref(false)

const profiles = [
  { value: 'normal' as FaultProfile, label: 'Normal', desc: '无故障' },
  { value: 'slow_api' as FaultProfile, label: 'Slow API', desc: '接口慢但结果正确' },
  { value: 'blur_image' as FaultProfile, label: 'Blur Image', desc: '图像模糊' },
  { value: 'stale_ui' as FaultProfile, label: 'Stale UI', desc: '页面显示旧值' },
  { value: 'wrong_mapping' as FaultProfile, label: 'Wrong Mapping', desc: '数据映射错误' },
  { value: 'layout_overlap' as FaultProfile, label: 'Layout Overlap', desc: '布局错位重叠' },
  { value: 'memory_pressure' as FaultProfile, label: 'Memory Pressure', desc: '内存压力' },
  { value: 'mixed_fault' as FaultProfile, label: 'Mixed Fault', desc: '混合故障' }
]

const profileClass = computed(() => {
  if (faultState.currentProfile === 'normal') return 'profile-normal'
  return 'profile-fault'
})

function togglePanel() {
  visible.value = !visible.value
}

async function switchProfile(profile: FaultProfile) {
  activateFault(profile)
  try {
    await activateFaultOnServer(profile)
  } catch (e) {
    console.warn('[FaultPanel] Server sync failed:', e)
  }
}

async function onReset() {
  resetFault()
  try {
    await activateFaultOnServer('normal')
  } catch (e) {
    console.warn('[FaultPanel] Server reset failed:', e)
  }
}
</script>

<style scoped>
.panel-trigger {
  position: fixed;
  right: 20rpx;
  bottom: 200rpx;
  width: 80rpx;
  height: 80rpx;
  background: rgba(74, 144, 217, 0.9);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4rpx 20rpx rgba(0, 0, 0, 0.2);
  z-index: 9999;
}

.trigger-icon {
  font-size: 40rpx;
  color: #fff;
}

.fault-panel {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 10000;
}

.panel-mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
}

.panel-content {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: #fff;
  border-radius: 24rpx 24rpx 0 0;
  max-height: 80vh;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  padding: 30rpx;
  border-bottom: 1rpx solid #eee;
}

.panel-title {
  flex: 1;
  font-size: 32rpx;
  font-weight: bold;
}

.panel-close {
  font-size: 48rpx;
  color: #999;
  padding: 0 10rpx;
}

.panel-body {
  padding: 30rpx;
}

.current-profile {
  display: flex;
  align-items: center;
  margin-bottom: 30rpx;
  padding: 20rpx;
  background: #f8f9fa;
  border-radius: 12rpx;
}

.label {
  font-size: 28rpx;
  color: #666;
  margin-right: 16rpx;
}

.value {
  font-size: 28rpx;
  font-weight: bold;
}

.profile-normal {
  color: #27ae60;
}

.profile-fault {
  color: #e74c3c;
}

.profile-list {
  margin-bottom: 30rpx;
}

.profile-item {
  padding: 20rpx;
  border: 2rpx solid #eee;
  border-radius: 12rpx;
  margin-bottom: 16rpx;
  transition: all 0.2s;
}

.profile-item.active {
  border-color: #4A90D9;
  background: #eef4fd;
}

.profile-name {
  font-size: 28rpx;
  font-weight: bold;
  display: block;
  margin-bottom: 4rpx;
}

.profile-desc {
  font-size: 24rpx;
  color: #999;
}

.panel-actions {
  text-align: center;
}

.btn-reset {
  background: #27ae60;
  color: #fff;
  border-radius: 8rpx;
  font-size: 28rpx;
}
</style>
