<script setup>
// vite define 全局注入（landing/vite.config.js build-time 注入）
const appVersion = __APP_VERSION__
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useStats, useMeta, useProviders, useModels, useChatUsage } from './composables/useApi'
import { fmtTokens, fmtInt, fmtFloat, fmtPct, orDash } from './lib/fmt'
import { t, locale, setLocale, toggle } from './composables/useI18n'
import SectionStatus from './components/SectionStatus.vue'
import SectionProviders from './components/SectionProviders.vue'
import SectionUsage from './components/SectionUsage.vue'
import SectionCode from './components/SectionCode.vue'
import SectionFaq from './components/SectionFaq.vue'
import SectionChangelog from './components/SectionChangelog.vue'
import SectionCta from './components/SectionCta.vue'
import Privacy from './components/Privacy.vue'

const status = useStats()
const meta = useMeta()
const providers = useProviders()
const models = useModels()
const usage = useChatUsage()

const stats = computed(() => status.data.value ?? {})

// P3-7 hash 路由：#/privacy → 隐私页，其余 → 首页
const route = ref(typeof window !== 'undefined' ? window.location.hash : '')
function onHash() { route.value = window.location.hash }
onMounted(() => window.addEventListener('hashchange', onHash))
onBeforeUnmount(() => window.removeEventListener('hashchange', onHash))
const isPrivacy = computed(() => route.value.startsWith('#/privacy'))

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
    { label: t('chip.total_requests'), value: fmtInt(s.total_requests), sub: '', tone: 'text' },
    { label: t('chip.total_images'), value: fmtInt(s.total_images), sub: '', tone: 'ok' },
    { label: t('chip.total_errors'), value: fmtInt(s.total_errors), sub: '', tone: 'warn' },
    { label: t('chip.avg_duration'), value: s.avg_duration_sec != null ? fmtFloat(s.avg_duration_sec, 1) + 's' : '—', sub: '', tone: 'text' },
    { label: t('chip.processing'), value: fmtInt(s.processing), sub: s.queue_capacity != null ? `${t('chip.queue')} ${s.queue_capacity}` : '', tone: 'text' },
    { label: t('chip.workers'), value: fmtInt(s.workers), sub: '', tone: 'text' },
    {
      label: t('chip.cf_solver'),
      value: cfOk ? (locale.value === 'en' ? 'OK' : '正常') : (solver.status ? orDash(solver.status) : '—'),
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

function goPrivacy() { window.location.hash = '#/privacy' }
function goHome() { window.location.hash = '' }
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
            <div class="brand-name">听风AI <span class="brand-tag">{{ t('hero.badge') }}</span></div>
            <div class="brand-sub">{{ t('hero.sub') }}</div>
          </div>
        </div>
        <nav class="nav-actions">
          <button class="btn btn-ghost lang-btn" @click="toggle" :aria-label="locale === 'zh' ? 'Switch to English' : '切换到中文'">{{ t('nav.lang') }}</button>
          <a v-if="!isPrivacy" class="btn btn-ghost" href="/docs" target="_blank" rel="noopener">{{ t('nav.docs') }}</a>
          <a v-if="!isPrivacy" class="btn btn-primary" href="/admin">{{ t('nav.admin') }} <span aria-hidden="true">→</span></a>
          <a v-else class="btn btn-primary" href="/" @click.prevent="goHome">{{ t('privacy.back') }}</a>
        </nav>
      </div>
    </header>

    <!-- 隐私声明页（hash 路由 #/privacy） -->
    <Privacy v-if="isPrivacy" />

    <!-- 首页 -->
    <main v-else class="main container">
      <section class="hero">
        <div class="hero-badge">
          <span class="dot ok"></span>
          <span>{{ t('hero.badge') }}</span>
        </div>
        <h1>{{ t('hero.title') }}</h1>
        <p class="hero-sub">{{ t('hero.sub') }}</p>

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
        <span>{{ t('footer.owner') }}</span>
        <span class="sep">·</span>
        <a href="https://github.com/lza6/" target="_blank" rel="noopener">GitHub github.com/lza6</a>
        <span class="sep">·</span>
        <a href="#" @click.prevent="goPrivacy">{{ t('nav.privacy') }}</a>
        <span class="sep">·</span>
        <a href="/v1/slow/view" target="_blank" rel="noopener">{{ t('footer.slow') }}</a>
        <span class="sep">·</span>
        <a href="/v1/honor" target="_blank" rel="noopener">{{ t('footer.coffee') }}</a>
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
.lang-btn { cursor: pointer; font-family: var(--mono); min-width: 44px; }

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
