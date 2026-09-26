<script setup>
/**
 * PortalPpt — 门户在线 AI PPT（Spec 009）
 * 大纲 → POST /v1/skills/ppt/generate → PPTX 下载
 * v20.3.1 P1（审计）：请求 /v1/meta 检测 ppt_enabled，未启用时显示「敬请期待」而非渲染可点按钮（杜绝 404）。
 */
import { computed, onMounted, ref } from 'vue'
import { t } from '../composables/useI18n'

const title = ref('')
const pages = ref([{ headline: '', points: '' }])
const busy = ref(false)
const err = ref('')
const done = ref(false)
const enabled = ref(true)
const checking = ref(true)

const canSubmit = computed(() => title.value.trim().length > 0 && pages.value.some((p) => p.headline.trim()))

onMounted(async () => {
  try {
    const r = await fetch('/v1/meta', { headers: { accept: 'application/json' } })
    if (r.ok) {
      const m = await r.json()
      enabled.value = m.ppt_enabled !== false
    }
  } catch { /* 探测失败视为可用（后端可达性由请求自身暴露） */ }
  finally { checking.value = false }
})

function addPage() { pages.value.push({ headline: '', points: '' }) }

async function submit() {
  if (!canSubmit.value || busy.value) return
  busy.value = true; err.value = ''; done.value = false
  try {
    const body = {
      title: title.value.trim(),
      pages: pages.value
        .filter((p) => p.headline.trim())
        .map((p) => ({
          headline: p.headline.trim(),
          points: p.points.split(/\n/).map((s) => s.trim()).filter(Boolean),
        })),
    }
    const response = await fetch('/v1/skills/ppt/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text.slice(0, 200) || ('HTTP ' + response.status))
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'outline.pptx'
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 10000)
    done.value = true
  } catch (error) {
    err.value = (error?.message || String(error)).slice(0, 240)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="portal-ppt">
    <p class="kicker">{{ t('pppt.kicker') }}</p>
    <h3>{{ t('pppt.title') }}</h3>

    <div v-if="checking" class="ppt-checking" role="status">
      <span class="dot ok"></span> {{ t('pchat.loading') }}
    </div>
    <div v-else-if="!enabled" class="ppt-off" role="status">
      🎴 {{ t('pppt.off') }}
    </div>

    <template v-else>
      <label class="field">
        <span>{{ t('pppt.title_ph') }}</span>
        <input v-model="title" type="text" :placeholder="t('pppt.title_ph')" :disabled="busy" />
      </label>

      <div v-for="(page, i) in pages" :key="i" class="page-card">
        <input v-model="page.headline" type="text" :placeholder="t('pppt.page_headline')" :disabled="busy" />
        <textarea v-model="page.points" rows="3" :placeholder="t('pppt.page_points')" :disabled="busy"></textarea>
      </div>

      <div class="ppt-actions">
        <button type="button" class="btn btn-ghost btn-sm" :disabled="busy" @click="addPage">{{ t('pppt.add_page') }}</button>
        <button type="button" class="btn btn-primary" :disabled="!canSubmit || busy" @click="submit">
          {{ busy ? t('pppt.downloading') : t('pppt.gen') }}
        </button>
      </div>

      <p v-if="err" class="ppt-err" role="alert">⚠ {{ err }}</p>
      <p v-else-if="done" class="ppt-ok" role="status">{{ t('pppt.done') }}</p>
    </template>
  </div>
</template>

<style scoped>
.portal-ppt { display: flex; flex-direction: column; gap: var(--space-3); }
.kicker { margin: 0; color: var(--brand-2); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
h3 { margin: 0; font-size: 20px; }
.field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
.field input, .page-card input, .page-card textarea {
  min-height: 44px; border-radius: var(--radius-sm); border: 1px solid var(--line-2);
  background: var(--bg-2); color: var(--text); font: inherit; padding: 10px 12px;
}
.page-card { display: flex; flex-direction: column; gap: 8px; padding: var(--space-3); border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--card); }
.page-card textarea { min-height: 72px; resize: vertical; }
.ppt-actions { display: flex; justify-content: space-between; gap: 10px; }
.btn-sm { padding: 8px 14px; font-size: 13px; min-height: 40px; }
.ppt-err { color: var(--warn); font-size: 13px; }
.ppt-ok { color: var(--ok); font-size: 13px; }
.ppt-off { color: var(--muted); font-size: 14px; padding: var(--space-2) 0; }
.ppt-checking { color: var(--muted); font-size: 13px; display: inline-flex; align-items: center; gap: 8px; }
@media (max-width: 768px) { .ppt-actions { flex-direction: column; align-items: stretch; } .ppt-actions .btn { width: 100%; } }
</style>
