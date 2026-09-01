<script setup>
// CTA 区 —— 引导进入 /admin 管理台 + Swagger 文档
import { t } from '../composables/useI18n'
</script>

<template>
  <section class="cta-section">
    <div class="cta card">
      <h2>{{ t('cta.title') }}</h2>
      <p class="cta-sub muted">
        {{ t('cta.sub') }}
      </p>
      <div class="cta-actions">
        <a class="btn btn-primary btn-lg" href="/admin">{{ t('cta.admin') }} <span aria-hidden="true">→</span></a>
        <a class="btn btn-ghost btn-lg" href="/docs" target="_blank" rel="noopener">{{ t('cta.swagger') }}</a>
      </div>
    </div>
  </section>
</template>

<style scoped>
.cta-section { padding: var(--space-6) 0 0; }
.cta {
  text-align: center;
  padding: var(--space-6) var(--space-4);
  position: relative;
  overflow: hidden;
}
.cta::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(closest-side at 50% 120%, var(--brand-glow), transparent 70%),
    radial-gradient(closest-side at 15% 0%, rgba(16, 185, 129, 0.12), transparent 60%);
  pointer-events: none;
}
.cta h2 {
  font-size: clamp(24px, 3.5vw, 34px);
  letter-spacing: -0.01em;
  margin-bottom: var(--space-2);
}
.cta-sub { margin-bottom: var(--space-4); }
.cta-actions {
  display: flex;
  justify-content: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 22px;
  border-radius: var(--radius-pill);
  font-size: 15px;
  font-weight: 600;
  transition: transform 0.14s ease, box-shadow 0.2s ease, background 0.2s ease, border-color 0.2s ease;
  position: relative;
  z-index: 1;
}
.btn-primary {
  background: var(--brand);
  color: #fff;
  box-shadow: 0 4px 18px var(--brand-glow);
}
.btn-primary:hover {
  background: var(--brand-2);
  transform: translateY(-1px);
  box-shadow: 0 8px 24px var(--brand-glow);
}
.btn-ghost {
  border: 1px solid var(--line-2);
  color: var(--text-2);
  background: transparent;
}
.btn-ghost:hover {
  border-color: var(--brand);
  color: var(--text);
  background: var(--brand-soft);
}
.btn-lg { padding: 14px 26px; font-size: 16px; }
</style>
