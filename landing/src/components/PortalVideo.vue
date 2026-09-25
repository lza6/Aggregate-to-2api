<script setup>
/**
 * PortalVideo — 门户 AI 视频（Spec 009，Beta 占位）
 * 真实视频上游（falai 已下线）待新 provider 接入后替换；当前展示 Beta 说明。
 * 避免误导：明确标注 Mock 演示。
 */
import { t } from '../composables/useI18n'
</script>

<template>
  <div class="portal-video">
    <p class="kicker">{{ t('pvideo.kicker') }}</p>
    <h3>{{ t('tool.video.name') }}</h3>
    <p class="beta-note">🎬 {{ t('pvideo.beta') }}</p>
    <p class="off-note">{{ t('pvideo.off') }}</p>
  </div>
</template>

<style scoped>
.portal-video { display: flex; flex-direction: column; gap: 8px; }
.kicker { margin: 0; color: var(--brand-2); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
h3 { margin: 0; font-size: 20px; }
.beta-note { color: var(--warn); font-size: 14px; }
.off-note { color: var(--muted); font-size: 13px; }
</style>
