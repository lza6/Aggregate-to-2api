<script setup>
// CTA 区 —— 引导进入 /admin 管理台 + Swagger 文档
import { motion } from 'motion-v'
import { t } from '../composables/useI18n'
</script>

<template>
  <section class="cta-section">
    <motion.div class="cta card"
      :initial="{ opacity: 0, y: 30, scale: 0.97 }"
      :whileInView="{ opacity: 1, y: 0, scale: 1 }"
      :viewport="{ once: true, margin: '-60px' }"
      :transition="{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }"
    >
      <h2>{{ t('cta.title') }}</h2>
      <p class="cta-sub muted">
        {{ t('cta.sub') }}
      </p>
      <div class="cta-actions">
        <motion.a class="btn btn-primary btn-lg" href="/admin"
          :whileHover="{ y: -3, scale: 1.03 }"
          :whileTap="{ scale: 0.98 }"
          :transition="{ type: 'spring', stiffness: 400, damping: 17 }"
        >{{ t('cta.admin') }} <span aria-hidden="true">→</span></motion.a>
        <motion.a class="btn btn-ghost btn-lg" href="/docs" target="_blank" rel="noopener"
          :whileHover="{ y: -2 }"
          :whileTap="{ scale: 0.98 }"
        >{{ t('cta.swagger') }}</motion.a>
      </div>
    </motion.div>
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
  background: linear-gradient(120deg, var(--text), var(--brand-2));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
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
  transition: box-shadow var(--dur) var(--ease-out), background var(--dur) var(--ease-out), border-color var(--dur) var(--ease-out);
  position: relative;
  z-index: 1;
}
.btn-primary {
  background: linear-gradient(135deg, var(--brand), var(--brand-2));
  color: #fff;
  box-shadow: 0 4px 18px var(--brand-glow), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}
.btn-primary:hover {
  box-shadow: 0 8px 28px var(--brand-glow), 0 0 0 4px var(--brand-soft), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}
.btn-ghost {
  border: 1px solid var(--line-2);
  color: var(--text-2);
  background: var(--card);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.btn-ghost:hover {
  border-color: var(--brand);
  color: var(--text);
  background: var(--brand-soft);
}
.btn-lg { padding: 14px 26px; font-size: 16px; }
</style>
