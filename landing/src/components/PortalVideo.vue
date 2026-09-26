<script setup>
/**
 * PortalVideo — 门户 AI 视频（Spec 009，Beta）
 * v20.3.1 P1（审计）：请求 /v1/meta 检测 video_enabled；未启用显示 Beta 说明（不渲染可点表单）。
 * 真实视频上游（falai 已下线）待新 provider 接入后替换。
 */
import { onMounted, ref } from 'vue'
import { t } from '../composables/useI18n'

const enabled = ref(false)
const checking = ref(true)

onMounted(async () => {
  try {
    const r = await fetch('/v1/meta', { headers: { accept: 'application/json' } })
    if (r.ok) {
      const m = await r.json()
      enabled.value = m.video_enabled === true
    }
  } catch { /* 探测失败视为未启用（Beta 保守） */ }
  finally { checking.value = false }
})
</script>

<template>
  <div class="portal-video">
    <p class="kicker">{{ t('pvideo.kicker') }}</p>
    <h3>{{ t('tool.video.name') }}</h3>
    <p v-if="checking" class="beta-note" role="status"><span class="dot ok"></span> {{ t('pchat.loading') }}</p>
    <template v-else>
      <p class="beta-note">🎬 {{ t('pvideo.beta') }}</p>
      <p v-if="!enabled" class="off-note">{{ t('pvideo.off') }}</p>
    </template>
  </div>
</template>

<style scoped>
.portal-video { display: flex; flex-direction: column; gap: 8px; }
.kicker { margin: 0; color: var(--brand-2); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
h3 { margin: 0; font-size: 20px; }
.beta-note { color: var(--warn); font-size: 14px; display: inline-flex; align-items: center; gap: 8px; }
.off-note { color: var(--muted); font-size: 13px; }
</style>
