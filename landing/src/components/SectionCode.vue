<script setup>
import { ref, computed } from 'vue'
import { motion } from 'motion-v'
import { t } from '../composables/useI18n'

const HOST = 'https://imagefree.tingfengai.art'

// curl 示例：同步/异步生成、聊天、健康检查
function computed_samples() {
  return [
    {
      title: t('code.sync.title'),
      desc: t('code.sync.desc'),
      code: `# ${t('code.sync.desc')}
curl -X POST ${HOST}/v1/generate \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $API_KEY" \\
  -d '{"prompt":"a cute orange cat","aspect_ratio":"1:1"}'`
    },
    {
      title: t('code.async.title'),
      desc: t('code.async.desc'),
      code: `# ${t('code.async.desc')}
curl -X POST ${HOST}/v1/generate/async \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $API_KEY" \\
  -d '{"prompt":"a cute orange cat","aspect_ratio":"1:1"}'`
    },
    {
      title: t('code.chat.title'),
      desc: t('code.chat.desc'),
      code: `# ${t('code.chat.desc')}
curl -X POST ${HOST}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $API_KEY" \\
  -d '{
    "model":"provider/model-id",
    "messages":[{"role":"user","content":"你好"}],
    "stream":false
  }'`
    },
    {
      title: t('code.health.title'),
      desc: t('code.health.desc'),
      code: `# ${t('code.health.desc')}
curl ${HOST}/v1/healthz`
    }
  ]
}

const samplesReactive = computed(() => computed_samples())

const active = ref(0)
const copied = ref(false)
let copyTimer = null

async function copyCode() {
  const text = samplesReactive.value[active.value].code
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    copied.value = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => (copied.value = false), 1500)
  } catch (e) {
    copied.value = false
  }
}
</script>

<template>
  <section class="section code-section">
    <div class="section-head">
      <h2>{{ t('code.title') }}</h2>
      <div class="section-sub muted">
        {{ t('code.sub') }} <code class="inline-code">API Key</code>{{ t('code.sub2') }}
      </div>
    </div>

    <motion.div class="code-card card"
      :initial="{ opacity: 0, y: 26 }"
      :whileInView="{ opacity: 1, y: 0 }"
      :viewport="{ once: true, margin: '-60px' }"
      :transition="{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }"
    >
      <div class="tabs">
        <motion.button
          v-for="(s, i) in samplesReactive"
          :key="s.title"
          class="tab"
          :class="{ on: i === active }"
          @click="active = i"
          :whileHover="{ y: -2 }"
          :whileTap="{ scale: 0.97 }"
        >
          {{ s.title }}
        </motion.button>
      </div>

      <div class="code-body">
        <div class="code-head">
          <span class="code-desc muted-2">{{ samplesReactive[active].desc }}</span>
          <button class="copy-btn" @click="copyCode">
            {{ copied ? t('code.copied') : t('code.copy') }}
          </button>
        </div>
        <div class="code-box">
          <pre><code v-pre>{{ samplesReactive[active].code }}</code></pre>
        </div>
      </div>
    </motion.div>
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
.inline-code {
  font-family: var(--mono);
  font-size: 13px;
  color: var(--brand-2);
  background: var(--brand-soft);
  padding: 1px 6px;
  border-radius: 5px;
}

.code-card { overflow: hidden; }
.tabs {
  display: flex;
  gap: 4px;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-2);
  border-bottom: 1px solid var(--line);
  overflow-x: auto;
}
.tab {
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  padding: 8px 14px;
  border-radius: 8px;
  white-space: nowrap;
  transition: color 0.2s ease, background 0.2s ease;
}
.tab:hover { color: var(--text-2); }
.tab.on {
  color: var(--text);
  background: var(--brand-soft);
}

.code-body { padding: var(--space-3); display: flex; flex-direction: column; gap: var(--space-3); }
.code-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.code-desc { font-size: 13px; }
.copy-btn {
  background: var(--card-2);
  color: var(--text-2);
  border: 1px solid var(--line);
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 13px;
  transition: all 0.2s ease;
  flex-shrink: 0;
}
.copy-btn:hover {
  border-color: var(--brand);
  color: var(--text);
  background: var(--brand-soft);
}
</style>
