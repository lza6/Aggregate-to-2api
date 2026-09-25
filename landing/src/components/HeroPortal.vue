<script setup>
/**
 * HeroPortal — 门户 Hero（Spec 009）
 * 大标题 + 副标题 + 主 CTA（滚动到工具区）+ 轻量信任元素（三枚胶囊）
 */
import { t } from '../composables/useI18n'

function scrollToTools() {
  const el = document.getElementById('portal-tools')
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <section class="hero portal-hero">
    <span class="hero-badge fade-up">{{ t('portal.badge') }}</span>
    <h1 class="hero-title text-grad fade-up" style="animation-delay: 0.1s">{{ t('portal.title') }}</h1>
    <p class="hero-sub fade-up" style="animation-delay: 0.2s">{{ t('portal.sub') }}</p>
    <div class="hero-cta fade-up" style="animation-delay: 0.3s">
      <button type="button" class="btn btn-primary btn-lg" @click="scrollToTools">
        {{ t('portal.cta') }} <span aria-hidden="true">↓</span>
      </button>
    </div>
    <div class="hero-trust fade-up" style="animation-delay: 0.4s">
      <span class="pill ok"><span class="dot ok"></span>{{ t('portal.trust1') }}</span>
      <span class="pill info">{{ t('portal.trust2') }}</span>
      <span class="pill">{{ t('portal.trust3') }}</span>
    </div>
  </section>
</template>

<style scoped>
.portal-hero { padding: var(--space-7) 0 var(--space-6); text-align: center; }
.hero-cta { margin-top: var(--space-5); }
.btn-lg { padding: 14px 30px; font-size: 16px; }
.hero-trust { margin-top: var(--space-4); display: flex; justify-content: center; gap: var(--space-3); flex-wrap: wrap; }
@media (max-width: 768px) {
  .portal-hero { padding: var(--space-6) 0 var(--space-5); }
  .hero-trust { gap: var(--space-2); }
}
</style>
