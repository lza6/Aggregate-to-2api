<script setup>
// 实时状态胶囊条 —— 从 /v1/stats + /v1/meta 拉取
// 数字用 tabular-nums（.tnum），单位/小字弱化
import { motion } from 'motion-v'
import { t } from '../composables/useI18n'

const props = defineProps({
  chips: { type: Array, default: () => [] },
  meta: { type: Object, default: () => ({}) },
  stats: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null }
})

const toneClass = (tone) => ({
  '--tone': tone,
  ok: tone === 'ok',
  warn: tone === 'warn',
  muted: tone === 'muted'
})
</script>

<template>
  <section class="status-wrap">
    <div class="status-head">
      <div class="status-title">
        <span class="dot ok"></span>
        <span>{{ t('status.title') }}</span>
        <span v-if="props.loading && !props.chips.length" class="muted-2">{{ t('status.loading') }}</span>
      </div>
      <div v-if="props.error" class="degraded">
        {{ t('status.unavailable') }}
      </div>
    </div>

    <div class="chips" role="group" aria-label="实时状态指标">
      <motion.div
        v-for="(c, i) in props.chips"
        :key="c.label"
        class="chip"
        :class="toneClass(c.tone)"
        :initial="{ opacity: 0, y: 20, scale: 0.96 }"
        :whileInView="{ opacity: 1, y: 0, scale: 1 }"
        :viewport="{ once: true }"
        :transition="{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: i * 0.06 }"
        :whileHover="{ y: -4, scale: 1.02 }"
      >
        <div class="chip-label">
          <span v-if="c.dot" class="dot" :class="c.dot"></span>
          {{ c.label }}
        </div>
        <div class="chip-value tnum">
          {{ c.value }}
          <span v-if="c.sub" class="chip-sub">{{ c.sub }}</span>
        </div>
      </motion.div>
    </div>

    <div v-if="Object.keys(props.meta).length" class="meta-line degraded">
      {{ t('status.aspect') }}
      <span v-for="(res, ratio) in props.meta.aspect_ratios" :key="ratio" class="meta-item">{{ ratio }} · {{ res }}</span>
    </div>
  </section>
</template>

<style scoped>
.status-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  text-align: left;
}
.status-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.status-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-2);
  letter-spacing: 0.02em;
}

.chips {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
}
@media (max-width: 860px) {
  .chips { grid-template-columns: repeat(2, 1fr); }
}

.chip {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: var(--space-3) var(--space-4);
  box-shadow: var(--shadow-card);
  backdrop-filter: blur(16px) saturate(140%);
  -webkit-backdrop-filter: blur(16px) saturate(140%);
  transition: border-color var(--dur) var(--ease-out);
  position: relative;
  overflow: hidden;
}
.chip::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: linear-gradient(180deg, rgba(255,255,255,0.14), transparent 50%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}
.chip:hover {
  border-color: var(--line-2);
}
.chip-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}
.chip-value {
  font-size: clamp(24px, 3.4vw, 34px);
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--text);
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
}
.chip-sub {
  font-size: 13px;
  font-weight: 500;
  color: var(--muted-2);
}
.chip.ok .chip-value { color: #34d399; }
.chip.warn .chip-value { color: #fbbf24; }
.chip.muted .chip-value { color: var(--muted); }

.meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}
.meta-item {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--muted-2);
}
</style>
