<script setup>
/**
 * PortalAgent — 门户在线 AI 智能体（Spec 009）
 * 自然语言 → POST /v1/agent/dag/plan → POST /v1/agent/dag/run → 轮询结果
 * tryingopen 真实 LLM 规划（mock=False 已核验）；运行 DAG 是真实任务编排。
 */
import { computed, ref } from 'vue'
import { t } from '../composables/useI18n'

const prompt = ref('')
const busy = ref(false)
const err = ref('')
const plan = ref(null)
const runId = ref('')
const status = ref('')
const result = ref('')
const pollRef = ref(null)

const canPlan = computed(() => prompt.value.trim().length > 0 && !busy.value)

async function buildPlan() {
  if (!canPlan.value) return
  busy.value = true; err.value = ''; plan.value = null; result.value = ''
  try {
    const response = await fetch('/v1/agent/dag/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt.value.trim() }),
    })
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail || body.error || ('HTTP ' + response.status))
    if (!body.nodes || !body.nodes.length) throw new Error(t('pagent.noPlan'))
    plan.value = body.nodes
  } catch (error) {
    err.value = (error?.message || String(error)).slice(0, 240)
  } finally {
    busy.value = false
  }
}

function clearPoll() {
  if (pollRef.value) { clearInterval(pollRef.value); pollRef.value = null }
}

async function runPlan() {
  if (!plan.value || busy.value) return
  busy.value = true; err.value = ''; result.value = ''; status.value = 'running'
  try {
    const response = await fetch('/v1/agent/dag/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: prompt.value.trim().slice(0, 64) || 'portal-agent',
        nodes: plan.value.map((n, i) => ({
          id: String(n.id || 'node-' + i),
          kind: n.kind || 'llm',
          depends_on: Array.isArray(n.depends_on) ? n.depends_on : [],
          prompt: n.prompt || undefined,
          model: n.model || undefined,
        })),
        fail_fast: true,
        max_parallel: 2,
      }),
    })
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail || body.error || ('HTTP ' + response.status))
    runId.value = body.run_id
    await pollRun(runId.value)
  } catch (error) {
    err.value = (error?.message || String(error)).slice(0, 240)
  } finally {
    busy.value = false
  }
}

function pollRun(id) {
  return new Promise((resolve) => {
    let fails = 0
    const poll = async () => {
      try {
        const r = await fetch(`/v1/agent/dag/${id}`)
        const body = await r.json()
        if (body.status === 'succeeded' || body.status === 'completed') {
          status.value = 'succeeded'
          result.value = (body.nodes || []).map((n) => (n.result || '')).filter(Boolean).join('\n').slice(0, 600)
          clearPoll(); resolve()
        } else if (body.status === 'failed' || body.status === 'error') {
          err.value = body.error_summary || '执行失败'
          status.value = 'failed'
          clearPoll(); resolve()
        } else {
          status.value = body.status || 'running'
          fails = 0
        }
      } catch (e) {
        fails += 1
        if (fails >= 8) { err.value = '任务查询失败'; clearPoll(); resolve() }
      }
    }
    void poll()
    pollRef.value = setInterval(poll, 2000)
  })
}
</script>

<template>
  <div class="portal-agent">
    <p class="kicker">{{ t('pagent.kicker') }}</p>
    <h3>{{ t('pagent.title') }}</h3>

    <textarea
      v-model="prompt"
      :placeholder="t('pagent.prompt')"
      rows="2"
      :disabled="busy"
    ></textarea>

    <div class="agent-actions">
      <button type="button" class="btn btn-ghost btn-sm" :disabled="!canPlan" @click="buildPlan">{{ t('pagent.plan') }}</button>
      <button v-if="plan" type="button" class="btn btn-primary" :disabled="busy" @click="runPlan">
        {{ busy ? t('pagent.running') : t('pagent.run') }}
      </button>
    </div>

    <div v-if="plan" class="plan-list">
      <span v-for="(n, i) in plan" :key="i" class="plan-node">
        <span class="node-kind">{{ n.kind }}</span>
        {{ n.prompt || n.id }}
      </span>
    </div>

    <p v-if="err" class="agent-err" role="alert">⚠ {{ err }}</p>
    <p v-if="status === 'succeeded'" class="agent-ok" role="status">{{ t('pagent.done') }}</p>
    <pre v-if="result" class="agent-result">{{ result }}</pre>
  </div>
</template>

<style scoped>
.portal-agent { display: flex; flex-direction: column; gap: var(--space-3); }
.kicker { margin: 0; color: var(--brand-2); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
h3 { margin: 0; font-size: 20px; }
.portal-agent textarea { min-height: 60px; border-radius: var(--radius-sm); border: 1px solid var(--line-2); background: var(--bg-2); color: var(--text); font: inherit; padding: 10px 12px; resize: vertical; }
.agent-actions { display: flex; gap: 10px; }
.btn-sm { padding: 8px 14px; font-size: 13px; min-height: 40px; }
.plan-list { display: flex; flex-direction: column; gap: 6px; }
.plan-node { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-2); background: var(--card); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 8px 12px; }
.node-kind { font-size: 11px; font-weight: 700; color: var(--brand-2); background: var(--brand-soft); border-radius: var(--radius-pill); padding: 2px 8px; }
.agent-err { color: var(--warn); font-size: 13px; }
.agent-ok { color: var(--ok); font-size: 13px; }
.agent-result { max-height: 200px; overflow: auto; font-family: var(--mono); font-size: 12px; color: var(--text-2); background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 10px 12px; white-space: pre-wrap; }
@media (max-width: 768px) { .agent-actions { flex-direction: column; align-items: stretch; } .agent-actions .btn { width: 100%; } }
</style>
