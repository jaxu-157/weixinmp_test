import { createSSRApp } from 'vue'
import App from './App.vue'
import { installTriage } from 'vision-triage-sdk'

export function createApp() {
  const app = createSSRApp(App)
  installTriage(app, { backendUrl: 'http://localhost:8900' })
  return { app }
}
