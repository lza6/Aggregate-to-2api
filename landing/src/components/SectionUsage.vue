<script setup>
import { computed } from 'vue'
import { motion } from 'motion-v'
import { fmtTokens, fmtInt, fmtFloat } from '../lib/fmt'
import { t } from '../composables/useI18n'

const props = defineProps({
  usage: { type: Object, default: null }, // {total_calls,ok_calls,fail_calls,prompt_tokens,completion_tokens,reasoning_tokens,tool_calls,avg_duration_ms,today_calls,today_tokens,by_model}
  loading: { type: Boolean, default: false },
  error: { type: String, default: null }
})

const u = computed(() => props.usage ?? {})

const totalTokens = computed(() => {
  const a = u.value.prompt_tokens ?? 0
  const b = u.value.completion_tokens ?? 0
  const c = u.value.reasoning_tokens ?? 0
  const s = a + b + c
  return [a, b, c].every(x => x === 0) ? 0 : s
})

const callRate = computed(() => {
  const t = u.value.total_calls ?? 0
  const ok = u.value.ok_calls ?? 0
  return t > 0 ? (ok / t) * 100 : null
})

const rows = computed(() => [
  { label: t('usage.col_calls'), value: fmtInt(u.value.total_calls), sub: `${t('usage.ok_calls_short')} ${fmtInt(u.value.ok_calls)} / ${t('usage.fail_calls_short')} ${fmtInt(u.value.fail_calls)}` },
  { label: t('usage.col_prompt'), value: fmtTokens(u.value.prompt_tokens), sub: 'prompt' },
  { label: t('usage.col_completion'), value: fmtTokens(u.value.completion_tokens), sub: 'completion' },
  { label: t('usage.col_reasoning'), value: fmtTokens(u.value.reasoning_tokens), sub: 'reasoning' },
  { label: t('usage.col_duration'), value: u.value.avg_duration_ms != null ? fmtFloat(u.value.avg_duration_ms, 0) + 'ms' : '—', sub: '' },
  { label: t('usage.col_tools'), value: fmtInt(u.value.tool_calls), sub: '' }
])
</script>

<template>
  <section class="section">
    <div class="section-head">
      <h2>{{ t('usage.title') }} <span class="unit">{{ t('usage.unit') }}</span></h2>
      <div class="section-sub muted">
        <span v-if="props.loading && !props.usage" class="muted-2">{{ t('status.loading') }}</span>
        <span v-else-if="props.error" class="degraded">{{ t('status.unavailable') }}</span>
        <span v-else-if="props.usage" class="pill ok">{{ t('usage.normal') }}</span>
      </div>
    </div>

    <motion.div class="use-card card"
      :initial="{ opacity: 0, y: 28, scale: 0.98 }"
      :whileInView="{ opacity: 1, y: 0, scale: 1 }"
      :viewport="{ once: true, margin: '-60px' }"
      :transition="{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }"
    >
      <div class="use-main">
        <div class="use-label">{{ t('usage.total_label') }}</div>
        <div class="use-total tnum">{{ fmtTokens(totalTokens) }}</div>
        <div class="use-meta muted-2">
          <span v-if="u.today_calls != null">{{ t('usage.today') }} {{ fmtInt(u.today_calls) }}{{ t('usage.calls') }}</span>
          <span v-if="u.today_tokens != null">/ {{ fmtTokens(u.today_tokens) }} {{ t('usage.tokens') }}</span>
          <span v-if="callRate != null">/ {{ t('usage.success_rate') }} {{ fmtFloat(callRate, 1) }}%</span>
        </div>
      </div>

      <div class="use-rows">
        <div v-for="r in rows" :key="r.label" class="use-row">
          <span class="use-row-label">{{ r.label }}</span>
          <div class="use-row-val">
            <span class="tnum">{{ r.value }}</span>
            <span v-if="r.sub" class="use-row-sub">{{ r.sub }}</span>
          </div>
        </div>
      </div>
    </motion.div>

    <!-- 分模型 -->
    <div v-if="Array.isArray(u.by_model) && u.by_model.length" class="models-table">
      <div class="table-head">
        <span>{{ t('usage.col_model') }}</span><span>{{ t('usage.col_call') }}</span><span>{{ t('usage.col_input') }}</span><span>{{ t('usage.col_output') }}</span>
      </div>
      <div v-for="m in u.by_model" :key="m.model" class="table-row">
        <code class="t-model">{{ m.model }}</code>
        <span class="tnum">{{ fmtInt(m.calls) }}</span>
        <span class="tnum">{{ fmtTokens(m.prompt_tokens) }}</span>
        <span class="tnum">{{ fmtTokens(m.completion_tokens) }}</span>
      </div>
    </div>

    <div v-if="!props.usage && props.error" class="use-card card empty">
      <span>{{ t('status.unavailable') }}</span>
    </div>
  </section>
</template>

<style scoped>
.section { display: flex; flex-direction: column; gap: var(--space-4); }
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.section-head h2 { font-size: 24px; letter-spacing: -0.01em; }
.unit {
  font-family: var(--mono);
  font-size: 14px;
  color: var(--muted);
  font-weight: 400;
  margin-left: 6px;
}

.use-card {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.use-main {
  text-align: center;
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--line);
}
.use-label {
  font-size: 13px;
  color: var(--muted);
  margin-bottom: 10px;
}
.use-total {
  font-size: clamp(44px, 7vw, 72px);
  font-weight: 800;
  letter-spacing: -0.03em;
  background: linear-gradient(120deg, var(--brand-2), var(--ok));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  line-height: 1.1;
}
.use-meta {
  margin-top: 10px;
  font-size: 13px;
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}

.use-rows {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
}
@media (max-width: 720px) {
  .use-rows { grid-template-columns: repeat(2, 1fr); }
}
.use-row {
  background: var(--bg-2);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.use-row-label { font-size: 12px; color: var(--muted); }
.use-row-val {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 22px;
  font-weight: 700;
}
.use-row-sub { font-size: 12px; color: var(--muted-2); font-weight: 400; }

.models-table {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.table-head, .table-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr;
  gap: var(--space-2);
  padding: 10px var(--space-3);
  align-items: center;
}
.table-head {
  color: var(--muted-2);
  font-size: 12px;
  background: var(--bg-2);
}
.table-row { border-top: 1px solid var(--line); }
.table-row code.t-model {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.table-row > span { text-align: right; font-size: 14px; }

.empty { text-align: center; color: var(--muted-2); padding: var(--space-5); }
</style>
