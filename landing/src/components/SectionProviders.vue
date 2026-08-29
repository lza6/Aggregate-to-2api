<script setup>
import { computed } from 'vue'
import { orDash } from '../lib/fmt'

const props = defineProps({
  providerItems: { type: Object, default: null }, // backend: {items:{<provider>:{display_name,capabilities,model_count,health_status,degraded,error_count}},count}
  modelList: { type: Array, default: () => [] },   // backend: {data:[{id:"<provider>/<model>",...}]}
  loading: { type: Boolean, default: false },
  error: { type: String, default: null }
})

// 把后端 items 对象转成有序数组
const providers = computed(() => {
  const items = props.providerItems
  if (!items || typeof items !== 'object') return []
  return Object.entries(items)
    .map(([id, v]) => ({ id, ...v }))
    .filter(p => p.id !== 'count')
})

// 按 provider 归组模型 id（models 的 id 形如 "<provider>/<model>"）
const modelsByProvider = computed(() => {
  const map = {}
  for (const m of props.modelList) {
    const id = String(m.id || '')
    const slash = id.indexOf('/')
    const provider = slash === -1 ? 'default' : id.slice(0, slash)
    const model = slash === -1 ? id : id.slice(slash + 1)
    ;(map[provider] = map[provider] || []).push(model)
  }
  return map
})

const healthTone = (h) => {
  const s = String(h || '').toLowerCase()
  if (s.includes('ok') || s.includes('healthy') || s.includes('up') || s === 'green') return 'ok'
  if (s.includes('degraded') || s.includes('warn') || s.includes('yellow')) return 'warn'
  if (s.includes('down') || s.includes('error') || s.includes('red') || s.includes('fail')) return 'err'
  return 'muted'
}

const capTone = (cap) => {
  const c = String(cap || '').toLowerCase()
  if (c.includes('txt') || c.includes('text') || c.includes('chat')) return 'info'
  if (c.includes('img') || c.includes('image') || c.includes('vision')) return 'ok'
  return 'muted'
}

function displayName(p) {
  return orDash(p.display_name || p.id)
}
</script>

<template>
  <section class="section">
    <div class="section-head">
      <h2>提供商与模型</h2>
      <div class="section-sub muted">
        <span v-if="props.loading && !providers.length" class="muted-2">加载中…</span>
        <span v-else-if="props.error" class="degraded">数据暂不可用</span>
        <span v-else-if="providers.length || modelList.length">实时同步</span>
      </div>
    </div>

    <div v-if="providers.length" class="grid">
      <article
        v-for="p in providers"
        :key="p.id"
        class="provider card"
      >
        <div class="provider-head">
          <div class="provider-title">
            <span class="dot" :class="healthTone(p.health_status)"></span>
            <h3>{{ displayName(p) }}</h3>
          </div>
          <span class="pill" :class="healthTone(p.health_status)">
            {{ p.health_status ? orDash(p.health_status) : (p.degraded ? 'degraded' : 'active') }}
          </span>
        </div>

        <div class="provider-meta muted-2">
          <span>{{ p.model_count != null ? p.model_count : '—' }} 个模型</span>
          <span v-if="p.error_count">· {{ p.error_count }} 次错误</span>
        </div>

        <div v-if="Array.isArray(p.capabilities) && p.capabilities.length" class="caps">
          <span v-for="cap in p.capabilities" :key="cap" class="pill" :class="capTone(cap)">{{ cap }}</span>
        </div>

        <div class="models ov">
          <span class="models-label muted-2">模型</span>
          <template v-if="(modelsByProvider[p.id] || []).length">
            <code v-for="m in modelsByProvider[p.id]" :key="m" class="model-id">#{{ m }}</code>
          </template>
          <span v-else class="degraded">未返回模型</span>
        </div>
      </article>
    </div>

    <div v-else class="empty card">
      <span>{{ props.loading ? '加载中…' : (props.error ? '数据暂不可用' : '暂无提供商数据') }}</span>
    </div>
  </section>
</template>

<style scoped>
.section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.section-head h2 {
  font-size: 24px;
  letter-spacing: -0.01em;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--space-4);
}

.provider {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}
.provider:hover {
  border-color: var(--line-2);
  transform: translateY(-3px);
  box-shadow: var(--shadow-glow);
}
.provider-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.provider-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.provider-title h3 {
  font-size: 17px;
}
.provider-meta {
  font-size: 13px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.caps {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.models {
  border-top: 1px solid var(--line);
  padding-top: var(--space-3);
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.models-label {
  font-size: 12px;
  margin-right: 4px;
}
.model-id {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--text-2);
  background: var(--card-2);
  padding: 3px 8px;
  border-radius: 6px;
  white-space: nowrap;
}

.empty {
  padding: var(--space-5);
  text-align: center;
  color: var(--muted-2);
}
</style>
