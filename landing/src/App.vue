<script setup>
// vite define 全局注入（landing/vite.config.js build-time 注入）
const appVersion = __APP_VERSION__
import { computed } from 'vue'
import { useStats, useMeta, useProviders, useModels, useChatUsage } from './composables/useApi'
import { fmtTokens, fmtInt, fmtFloat, fmtPct, orDash } from './lib/fmt'
import SectionStatus from './components/SectionStatus.vue'
import SectionProviders from './components/SectionProviders.vue'
import SectionUsage from './components/SectionUsage.vue'
import SectionCode from './components/SectionCode.vue'
import SectionFaq from './components/SectionFaq.vue'
import SectionChangelog from './components/SectionChangelog.vue'
import SectionCta from './components/SectionCta.vue'

const status = useStats()
const meta = useMeta()
const providers = useProviders()
const models = useModels()
const usage = useChatUsage()

const stats = computed(() => status.data.value ?? {})

// 由 /v1/stats 加工出的「实时状态胶囊」数字
const statChips = computed(() => {
  const s = stats.value
  const solver = s.solver ?? {}
  const cfOk = solver.status === 'ok' || solver.status === 'healthy' || solver.status === 'up'
  const cfRate = solver.window_success_rate != null
    ? (solver.window_success_rate * 100)
    : (solver.solve_total > 0
        ? (solver.solve_success_total / solver.solve_total) * 100
        : null)
  return [
    { label: '总请求', value: fmtInt(s.total_requests), sub: '', tone: 'text' },
    { label: '总出图', value: fmtInt(s.total_images), sub: '', tone: 'ok' },
    { label: '失败', value: fmtInt(s.total_errors), sub: '', tone: 'warn' },
    { label: '平均出图耗时', value: s.avg_duration_sec != null ? fmtFloat(s.avg_duration_sec, 1) + 's' : '—', sub: '', tone: 'text' },
    { label: '当前并发', value: fmtInt(s.processing), sub: s.queue_capacity != null ? `队列 ${s.queue_capacity}` : '', tone: 'text' },
    { label: 'Worker', value: fmtInt(s.workers), sub: '', tone: 'text' },
    {
      label: 'CF 求解',
      value: cfOk ? '正常' : (solver.status ? orDash(solver.status) : '—'),
      sub: cfRate != null ? `${fmtPct(cfRate)}` : '',
      tone: cfOk ? 'ok' : (solver.status ? 'warn' : 'muted'),
      dot: cfOk ? 'ok' : (solver.status ? 'warn' : 'muted')
    }
  ]
})

const metaInfo = computed(() => meta.data.value ?? {})
const providerItems = computed(() => providers.data.value?.items ?? null)
const modelList = computed(() => {
  const m = models.data.value
  if (!m || !Array.isArray(m.data)) return []
  return m.data
})
</script>

<template>
  <div class="landing">
    <div class="aura" aria-hidden="true"></div>

    <!-- 顶部品牌导航 -->
    <header class="nav">
      <div class="container nav-inner">
        <div class="brand">
          <span class="logo" aria-hidden="true">听</span>
          <div class="brand-text">
            <div class="brand-name">听风AI <span class="brand-tag">逆向号池</span></div>
            <div class="brand-sub">多提供商 AI 生成网关 · 高并发异步队列</div>
          </div>
        </div>
        <nav class="nav-actions">
          <a class="btn btn-ghost" href="/docs" target="_blank" rel="noopener">API 文档</a>
          <a class="btn btn-primary" href="/admin">进入管理台 <span aria-hidden="true">→</span></a>
        </nav>
      </div>
    </header>

    <!-- Hero -->
    <main class="main container">
      <section class="hero">
        <div class="hero-badge">
          <span class="dot ok"></span>
          <span>自动逆向 · 号池 / 邮箱池 / 代理池 · 自动过 Cloudflare Turnstile</span>
        </div>
        <h1>多提供商 AI 生成网关</h1>
        <p class="hero-sub">自动逆向 · 号池 / 邮箱池 / 代理池 · 高并发异步队列 · 自动过 Cloudflare Turnstile</p>

        <SectionStatus :stats="stats" :chips="statChips" :meta="metaInfo" :loading="status.loading.value" :error="status.error.value" />
      </section>

      <!-- 提供商与模型网格 -->
      <SectionProviders
        :provider-items="providerItems"
        :model-list="modelList"
        :loading="providers.loading.value"
        :error="providers.error.value"
      />

      <!-- 对话 Token 用量卡（M/B/K 大单位） -->
      <SectionUsage :usage="usage.data.value" :loading="usage.loading.value" :error="usage.error.value" />

      <!-- API 快速开始 -->
      <SectionCode />

      <!-- D4: FAQ 区 + 手到即用 curl -->
      <SectionFaq />

      <!-- D4: 更新日志区 + 实时状态 -->
      <SectionChangelog />

      <!-- CTA 区 + 页脚 -->
      <SectionCta />
    </main>

    <footer class="footer container">
      <div class="footer-inner">
        <span>负责人：听风</span>
        <span class="sep">·</span>
        <a href="https://github.com/lza6/" target="_blank" rel="noopener">GitHub github.com/lza6</a>
        <span class="sep">·</span>
        <a href="/v1/slow/view" target="_blank" rel="noopener">慢请求看板</a>
        <span class="sep">·</span>
        <a href="/v1/honor" target="_blank" rel="noopener">请我喝咖啡</a>
        <span class="sep">·</span>
        <span class="muted-2">v{{ appVersion }}</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.landing {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 导航 */
.nav {
  position: relative;
  z-index: 2;
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--line);
  background: rgba(15, 23, 42, 0.72);
  backdrop-filter: blur(10px);
}
.nav-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.logo {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--brand), #7c3aed);
  color: #fff;
  font-size: 20px;
  font-weight: 800;
  box-shadow: 0 4px 16px var(--brand-glow);
  flex-shrink: 0;
}
.brand-text { display: flex; flex-direction: column; gap: 2px; }
.brand-name {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0.01em;
  display: flex;
  align-items: center;
  gap: 8px;
}
.brand-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--brand-2);
  background: var(--brand-soft);
  padding: 2px 8px;
  border-radius: var(--radius-pill);
}
.brand-sub { font-size: 12.5px; color: var(--muted); }

.nav-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: var(--radius-pill);
  font-size: 14px;
  font-weight: 600;
  transition: transform 0.14s ease, box-shadow 0.2s ease, background 0.2s ease, border-color 0.2s ease;
  white-space: nowrap;
}
.btn-primary {
  background: var(--brand);
  color: #fff;
  box-shadow: 0 4px 18px var(--brand-glow);
}
.btn-primary:hover {
  background: var(--brand-2);
  transform: translateY(-1px);
  box-shadow: 0 8px 24px var(--brand-glow);
}
.btn-ghost {
  border: 1px solid var(--line-2);
  color: var(--text-2);
  background: transparent;
}
.btn-ghost:hover {
  border-color: var(--brand);
  color: var(--text);
  background: var(--brand-soft);
}

/* Hero */
.main {
  flex: 1;
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  padding-bottom: var(--space-7);
}
.hero {
  padding: var(--space-7) 0 var(--space-5);
  text-align: center;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--muted);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  padding: 6px 14px;
  margin-bottom: var(--space-4);
}
.hero h1 {
  font-size: clamp(32px, 5.5vw, 56px);
  font-weight: 800;
  letter-spacing: -0.02em;
  background: linear-gradient(120deg, #fff, var(--brand-2));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: var(--space-3);
}
.hero-sub {
  font-size: clamp(15px, 2.2vw, 18px);
  color: var(--muted);
  max-width: 720px;
  margin: 0 auto;
}
</style>
