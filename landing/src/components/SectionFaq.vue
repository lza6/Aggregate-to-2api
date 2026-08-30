<script setup>
// D4: FAQ 区 —— 常见问题与"到手即用"curl 引导
import { ref } from 'vue'

const faqs = [
  {
    q: '如何获取 API Key？',
    a: '进入管理台 /admin → 在线聊天或在线生成页右上角「配置 Key」填入。Key 仅保存在你本地浏览器 localStorage，永不上传。匿名只读端点无需 Key；写接口（生成/聊天）需 Key。',
  },
  {
    q: '生成图像是同步还是异步？',
    a: '同步 /v1/generate 等待出图（典型 20~45s）；高并发推荐异步 /v1/generate/async 立即返回任务 ID，再轮询 /v1/tasks/{id} 或订阅每任务 SSE /v1/tasks/{id}/events。',
  },
  {
    q: '支持哪些客户端？',
    a: 'OpenAI 兼容（Codex / Cursor / Continue / 任意 OpenAI SDK）用 /v1/chat/completions；Anthropic 兼容（Claude Code）用 /v1/messages。在线聊天页右上角「API 接入」有一键 curl 模板。',
  },
  {
    q: '限流策略是什么？',
    a: '按出口代理数估算每小时额度，触发 429 时前端会提示切换备用引擎。健康检查 /v1/healthz 含实时并发/排队/worker 数。',
  },
]

const copied = ref(false)
let copyTimer = null
const quickstart = `# 1. 健康检查
curl https://imagefree.tingfengai.art/v1/healthz

# 2. 同步生成（替换 <KEY> 与提示词）
curl -X POST https://imagefree.tingfengai.art/v1/generate \\
  -H "Authorization: Bearer <KEY>" \\
  -H "Content-Type: application/json" \\
  -d '{"prompt":"a cute orange cat","aspect_ratio":"1:1"}'

# 3. 聊天（OpenAI 兼容）
curl -X POST https://imagefree.tingfengai.art/v1/chat/completions \\
  -H "Authorization: Bearer <KEY>" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"tryingopen/z-ai/glm-5.3-flash","messages":[{"role":"user","content":"hi"}]}'`

async function copyQuick() {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(quickstart)
    } else {
      const ta = document.createElement('textarea')
      ta.value = quickstart
      ta.style.position = 'fixed'; ta.style.opacity = '0'
      document.body.appendChild(ta); ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    copied.value = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => (copied.value = false), 1800)
  } catch {
    copied.value = false
  }
}

const openIdx = ref(0)
function toggle(i) { openIdx.value = openIdx.value === i ? -1 : i }
</script>

<template>
  <section class="section faq-section">
    <div class="section-head">
      <h2>常见问题 · 手到即用</h2>
      <div class="section-sub muted">一键复制 curl，立即开始</div>
    </div>

    <div class="faq-grid">
      <div class="faq-list">
        <div v-for="(f, i) in faqs" :key="i" class="faq-item">
          <button class="faq-q" @click="toggle(i)" :aria-expanded="openIdx === i">
            <span class="faq-q-text">{{ f.q }}</span>
            <span class="faq-caret" :class="{ open: openIdx === i }">▾</span>
          </button>
          <div v-if="openIdx === i" class="faq-a muted">{{ f.a }}</div>
        </div>
      </div>

      <div class="quick-card card">
        <div class="quick-head">
          <span class="quick-title">⚡ 手到即用 curl</span>
          <button class="copy-btn" @click="copyQuick">{{ copied ? '已复制 ✓' : '复制' }}</button>
        </div>
        <pre class="quick-code"><code>{{ quickstart }}</code></pre>
      </div>
    </div>
  </section>
</template>

<style scoped>
.section { display: flex; flex-direction: column; gap: var(--space-4); }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
.section-head h2 { font-size: 24px; letter-spacing: -0.01em; }

.faq-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); }
@media (max-width: 768px) { .faq-grid { grid-template-columns: 1fr; } }

.faq-list { display: flex; flex-direction: column; gap: var(--space-2); }
.faq-item { border-bottom: 1px solid var(--line); }
.faq-q {
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
  width: 100%; text-align: left;
  background: transparent; border: none; color: var(--text);
  padding: 12px 4px; cursor: pointer; font: inherit;
}
.faq-q:hover { color: var(--brand-2); }
.faq-q-text { font-size: 14px; font-weight: 600; }
.faq-caret { font-size: 12px; color: var(--muted); transition: transform 0.18s ease; }
.faq-caret.open { transform: rotate(180deg); }
.faq-a { padding: 4px 4px 14px; font-size: 13px; line-height: 1.6; }

.quick-card { padding: var(--space-3); display: flex; flex-direction: column; gap: var(--space-3); }
.quick-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.quick-title { font-size: 14px; font-weight: 700; color: var(--text); }
.copy-btn {
  background: var(--card-2); color: var(--text-2);
  border: 1px solid var(--line); padding: 6px 12px; border-radius: 8px;
  font-size: 13px; cursor: pointer;
}
.copy-btn:hover { border-color: var(--brand); color: var(--text); background: var(--brand-soft); }
.quick-code {
  margin: 0; padding: 12px; background: var(--bg-2); border: 1px solid var(--line);
  border-radius: 8px; font-family: var(--mono); font-size: 11.5px; line-height: 1.6;
  color: var(--text-2); overflow-x: auto; white-space: pre;
}
</style>
