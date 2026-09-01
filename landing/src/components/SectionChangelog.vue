<script setup>
// D4: 更新日志区 —— 读 /v1/healthz 实时状态 + 读静态 release notes 摘要
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { usePolling } from '../composables/usePolling'
import { t, locale } from '../composables/useI18n'

// /v1/healthz —— 实时状态胶囊（status/cf_solver/workers/queue）
const health = usePolling('/v1/healthz', 15000)
const healthChips = computed(() => {
  const h = health.data.value ?? {}
  const ok = h.status === 'ok'
  const cfUp = locale.value === 'en' ? 'online' : '在线'
  return [
    { label: t('changelog.service'), value: ok ? (locale.value === 'en' ? 'OK' : '正常') : (h.status || '—'), tone: ok ? 'ok' : 'warn' },
    { label: t('changelog.cf'), value: h.cf_solver === 'up' ? cfUp : (h.cf_solver || '—'), tone: h.cf_solver === 'up' ? 'ok' : 'warn' },
    { label: t('changelog.worker'), value: h.workers ?? '—', tone: 'text' },
    { label: t('changelog.concurrent'), value: h.processing ?? '—', tone: 'text' },
    { label: t('changelog.queue'), value: h.queued ?? '—', tone: 'text' },
    { label: t('changelog.dbrows'), value: h.db_rows ?? '—', tone: 'text' },
  ]
})

// 静态 release notes 摘要（构建时复制进 /public/release/，运行时 fetch 列表）
const notes = ref([])
const notesError = ref(null)
async function loadNotes() {
  try {
    const res = await fetch('/release/index.json')
    if (!res.ok) throw new Error('HTTP ' + res.status)
    notes.value = await res.json()
  } catch (e) {
    notesError.value = e instanceof Error ? e.message : String(e)
  }
}
onMounted(() => loadNotes())
onBeforeUnmount(() => health.stop())

const expanded = ref(0)
function toggle(i) { expanded.value = expanded.value === i ? -1 : i }
</script>

<template>
  <section class="section changelog-section">
    <div class="section-head">
      <h2>{{ t('changelog.title') }}</h2>
      <div class="section-sub muted">{{ t('changelog.sub') }} <code class="inline-code">/v1/healthz</code> {{ t('changelog.sub2') }}</div>
    </div>

    <!-- 实时状态胶囊 -->
    <div class="health-chips">
      <div v-for="c in healthChips" :key="c.label" class="health-chip" :class="'tone-' + c.tone">
        <span class="hc-label">{{ c.label }}</span>
        <span class="hc-value">{{ c.value }}</span>
      </div>
    </div>

    <!-- 更新日志列表 -->
    <div class="notes-list card">
      <div v-if="notes.length === 0 && !notesError" class="notes-empty muted">{{ t('changelog.loading') }}</div>
      <div v-else-if="notesError" class="notes-empty muted">{{ t('changelog.fail_prefix') }}{{ notesError }}）</div>
      <div v-else>
        <div v-for="(n, i) in notes" :key="n.version" class="note-item">
          <button class="note-head" @click="toggle(i)" :aria-expanded="expanded === i">
            <span class="note-version">{{ n.version }}</span>
            <span class="note-title">{{ n.title }}</span>
            <span class="note-caret" :class="{ open: expanded === i }">▾</span>
          </button>
          <div v-if="expanded === i" class="note-body">
            <pre class="note-pre"><code>{{ n.preview }}</code></pre>
            <a class="note-link" :href="n.url" target="_blank" rel="noopener">{{ t('changelog.full') }} {{ n.version }} {{ t('changelog.notes') }}</a>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.section { display: flex; flex-direction: column; gap: var(--space-4); }
.section-head {
  display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap;
}
.section-head h2 { font-size: 24px; letter-spacing: -0.01em; }
.inline-code {
  font-family: var(--mono); font-size: 13px; color: var(--brand-2);
  background: var(--brand-soft); padding: 1px 6px; border-radius: 5px;
}

.health-chips { display: flex; flex-wrap: wrap; gap: 10px; }
.health-chip {
  display: flex; flex-direction: column; gap: 2px;
  background: var(--card); border: 1px solid var(--line);
  padding: 10px 14px; border-radius: var(--radius-sm); min-width: 100px;
}
.hc-label { font-size: 11px; color: var(--muted); }
.hc-value { font-size: 15px; font-weight: 700; color: var(--text); }
.tone-ok .hc-value { color: var(--ok); }
.tone-warn .hc-value { color: var(--warn); }

.notes-list { padding: var(--space-3); display: flex; flex-direction: column; gap: var(--space-2); }
.notes-empty { padding: var(--space-3); text-align: center; }
.note-item { border-bottom: 1px solid var(--line); }
.note-item:last-child { border-bottom: none; }
.note-head {
  display: flex; align-items: center; gap: var(--space-3);
  width: 100%; text-align: left;
  background: transparent; border: none; color: var(--text);
  padding: 10px 4px; cursor: pointer; font: inherit;
}
.note-head:hover { color: var(--brand-2); }
.note-version {
  font-family: var(--mono); font-size: 13px; font-weight: 700;
  color: var(--brand-2); background: var(--brand-soft);
  padding: 2px 8px; border-radius: var(--radius-pill); flex-shrink: 0;
}
.note-title { flex: 1; font-size: 13.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.note-caret { font-size: 12px; color: var(--muted); transition: transform 0.18s ease; }
.note-caret.open { transform: rotate(180deg); }
.note-body { padding: 0 4px 12px; display: flex; flex-direction: column; gap: 8px; }
.note-pre {
  margin: 0; padding: 10px 12px; background: var(--bg-2); border: 1px solid var(--line);
  border-radius: 8px; font-family: var(--mono); font-size: 11.5px; line-height: 1.6;
  color: var(--text-2); overflow-x: auto; white-space: pre-wrap; max-height: 240px;
}
.note-link { font-size: 12px; color: var(--brand-2); }
</style>
