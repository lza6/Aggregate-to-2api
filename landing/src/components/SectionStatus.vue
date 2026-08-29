<script setup>
// 实时状态胶囊条 —— 从 /v1/stats + /v1/meta 拉取
// 数字用 tabular-nums（.tnum），单位/小字弱化
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
        <span>实时状态</span>
        <span v-if="props.loading && !props.chips.length" class="muted-2">加载中…</span>
      </div>
      <div v-if="props.error" class="degraded">
        ⚠ 数据暂不可用
      </div>
    </div>

    <div class="chips" role="group" aria-label="实时状态指标">
      <div
        v-for="(c, i) in props.chips"
        :key="c.label"
        class="chip"
        :class="toneClass(c.tone)"
      >
        <div class="chip-label">
          <span v-if="c.dot" class="dot" :class="c.dot"></span>
          {{ c.label }}
        </div>
        <div class="chip-value tnum">
          {{ c.value }}
          <span v-if="c.sub" class="chip-sub">{{ c.sub }}</span>
        </div>
      </div>
    </div>

    <div v-if="Object.keys(props.meta).length" class="meta-line degraded">
      支持画幅：
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
  transition: border-color 0.2s ease, transform 0.2s ease;
  position: relative;
}
.chip:hover {
  border-color: var(--line-2);
  transform: translateY(-2px);
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
