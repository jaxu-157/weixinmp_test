import { getFaultState } from './fault'

const BASE_URL = 'http://localhost:8900'

interface ApiResponse<T = any> {
  code: number
  data: T
  profile: string
  latency?: number
}

async function request<T>(path: string, options?: { method?: string; data?: any }): Promise<ApiResponse<T>> {
  const fault = getFaultState()
  const url = `${BASE_URL}${path}`
  const header = {
    'Content-Type': 'application/json',
    'X-Fault-Profile': fault.currentProfile
  }

  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method: options?.method || 'GET',
      data: options?.data,
      header,
      success: (res) => {
        resolve(res.data as ApiResponse<T>)
      },
      fail: (err) => {
        reject(err)
      }
    })
  })
}

export interface FeedItem {
  id: number
  title: string
  subtitle: string
  imageUrl: string
  tags: string[]
}

export interface CounterData {
  value: number
  updatedAt: number
  version: string
}

export interface LayoutCard {
  id: number
  title: string
  description: string
  imageUrl: string
  width: number
  height: number
  tags: string[]
}

export async function fetchFeedList(page: number = 1, pageSize: number = 10): Promise<ApiResponse<FeedItem[]>> {
  return request<FeedItem[]>(`/api/feed?page=${page}&pageSize=${pageSize}`)
}

export async function fetchCounterValue(): Promise<ApiResponse<CounterData>> {
  return request<CounterData>('/api/counter')
}

export async function refreshCounter(): Promise<ApiResponse<CounterData>> {
  return request<CounterData>('/api/counter/refresh', { method: 'POST' } as any)
}

export async function fetchLayoutCards(): Promise<ApiResponse<LayoutCard[]>> {
  return request<LayoutCard[]>('/api/layout')
}

export async function activateFaultOnServer(profile: string): Promise<ApiResponse<void>> {
  return request<void>('/fault/activate', {
    method: 'POST',
    data: { profile }
  } as any)
}

export async function getFaultStatus(): Promise<ApiResponse<{ profile: string }>> {
  return request<{ profile: string }>('/fault/status')
}
