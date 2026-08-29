<script setup>
import { ref } from 'vue'

const HOST = 'https://imagefree.tingfengai.art'

// curl 示例：同步/异步生成、聊天、健康检查
const samples = [
  {
    title: '同步生成 /v1/generate',
    desc: '等待出图，典型 20~45 秒',
    code: `# 同步生成（等待出图）
curl -X POST ${HOST}/v1/generate \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $API_KEY" \\
  -d '{"prompt":"a cute orange cat","aspect_ratio":"1:1"}'`
  },
  {
    title: '异步生成 /v1/generate/async',
    desc: '立即返回任务 ID，高并发推荐',
    code: `# 异步生成（立即返回任务 ID）
curl -X POST ${HOST}/v1/generate/async \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $API_KEY" \\
  -d '{"prompt":"a cute orange cat","aspect_ratio":"1:1"}'`
  },
  {
    title: '聊天 /v1/chat/completions',
    desc: 'OpenAI 标准协议，流式/非流式',
    code: `# 聊天（OpenAI 兼容）
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
    title: '健康检查 /v1/healthz',
    desc: '含实时并发/排队',
    code: `# 健康检查
curl ${HOST}/v1/healthz`
  }
]

const active = ref(0)
const copied = ref(false)
let copyTimer = null

async function copyCode() {
  const text = samples[active.value].code
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
      <h2>API 快速开始</h2>
      <div class="section-sub muted">
        写接口需 <code class="inline-code">API Key</code>（聊天 / 生成 / 图生图）· 请合理使用
      </div>
    </div>

    <div class="code-card card">
      <div class="tabs">
        <button
          v-for="(s, i) in samples"
          :key="s.title"
          class="tab"
          :class="{ on: i === active }"
          @click="active = i"
        >
          {{ s.title }}
        </button>
      </div>

      <div class="code-body">
        <div class="code-head">
          <span class="code-desc muted-2">{{ samples[active].desc }}</span>
          <button class="copy-btn" @click="copyCode">
            {{ copied ? '已复制 ✓' : '复制' }}
          </button>
        </div>
        <div class="code-box">
          <pre><code v-pre>{{ samples[active].code }}</code></pre>
        </div>
      </div>
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
