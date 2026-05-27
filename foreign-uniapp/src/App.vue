<script setup lang="ts">
import { onLaunch, onShow, onHide } from "@dcloudio/uni-app";
import { initPerfObserver } from "@/services/perf";

onLaunch(() => {
  console.log("[Vision-Triage] App Launch");
  initPerfObserver();
});
onShow(() => {
  console.log("[Vision-Triage] App Show");
});
onHide(() => {
  console.log("[Vision-Triage] App Hide");
});
</script>

<style>
page {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 28rpx;
  color: #333;
  background: #f5f5f5;
}
</style>
