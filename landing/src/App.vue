<script setup>
/**
 * App.vue — Spec 009 门户版（media.io 范式）
 * 一站式 AI 创意平台：HeroPortal + ToolsGrid（点击即用）+ GalleryWall（真实作品瀑布流）+ 简化页脚。
 * 移除：管理后台入口、SectionProviders/SectionCode/SectionUsage/SectionStatus、/v1/slow/view + /v1/honor 运维链接。
 * 保留：Hero3D 背景、隐私页（#/privacy）、i18n 语言切换。
 */
const appVersion = __APP_VERSION__
import { computed, ref, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { useScroll, useMediaQuery } from '@vueuse/core'
import { t, locale, toggle } from './composables/useI18n'
import HeroPortal from './components/HeroPortal.vue'
import ToolsGrid from './components/tools/ToolsGrid.vue'
import GalleryWall from './components/gallery/GalleryWall.vue'
import PortalChat from './components/PortalChat.vue'
import PortalGenerate from './components/PortalGenerate.vue'
import PortalVideo from './components/PortalVideo.vue'
import PortalPpt from './components/PortalPpt.vue'
import PortalAgent from './components/PortalAgent.vue'
import Privacy from './components/Privacy.vue'

const Hero3D = defineAsyncComponent(() => import('./components/Hero3D.vue'))

const { y: scrollY } = useScroll(window)
const navScrolled = computed(() => scrollY.value > 24)
const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
const small = useMediaQuery('(max-width: 768px)')

const route = ref(typeof window !== 'undefined' ? window.location.hash : '')
function onHash() { route.value = window.location.hash }
const isPrivacy = computed(() => route.value.startsWith('#/privacy'))

onMounted(() => { window.addEventListener('hashchange', onHash) })
onBeforeUnmount(() => { window.removeEventListener('hashchange', onHash) })

function goPrivacy() { window.location.hash = '#/privacy' }
function goHome() { window.location.hash = '' }
</script>

<template>
  <div class="landing">
    <!-- 3D 粒子流场背景（全屏固定，最底层） -->
    <div class="bg-field">
      <Hero3D v-if="!small || !reduced" />
    </div>
    <div class="aura" aria-hidden="true"></div>

    <!-- 顶部品牌导航（无管理后台入口） -->
    <header class="nav" :class="{ scrolled: navScrolled }">
      <div class="container nav-inner">
        <div class="brand">
          <span class="logo" aria-hidden="true">听</span>
          <div class="brand-text">
            <div class="brand-name">听风AI <span class="brand-tag">AI 创意平台</span></div>
            <div class="brand-sub">{{ t('portal.sub') }}</div>
          </div>
        </div>
        <nav class="nav-actions">
          <button class="btn btn-ghost lang-btn" @click="toggle" :aria-label="locale === 'zh' ? 'Switch to English' : '切换到中文'">{{ t('nav.lang') }}</button>
          <a v-if="!isPrivacy" class="btn btn-ghost" href="/docs" target="_blank" rel="noopener">{{ t('nav.docs') }}</a>
          <a v-else class="btn btn-primary" href="/" @click.prevent="goHome">{{ t('privacy.back') }}</a>
        </nav>
      </div>
    </header>

    <!-- 隐私声明页（hash 路由 #/privacy） -->
    <Privacy v-if="isPrivacy" />

    <!-- 首页：门户 -->
    <main v-else class="main container">
      <HeroPortal />

      <!-- 工具卡片网格 -->
      <section id="portal-tools" class="section-block" aria-labelledby="tools-title">
        <div class="section-head">
          <p class="kicker">{{ t('portal.tools_sub') }}</p>
          <h2 id="tools-title">{{ t('portal.tools_title') }}</h2>
        </div>
        <ToolsGrid>
          <template #panel:chat><PortalChat /></template>
          <template #panel:img><PortalGenerate mode="txt" /></template>
          <template #panel:edit><PortalGenerate mode="img" /></template>
          <template #panel:video><PortalVideo /></template>
          <template #panel:ppt><PortalPpt /></template>
          <template #panel:agent><PortalAgent /></template>
        </ToolsGrid>
      </section>

      <!-- 灵感画廊（真实作品瀑布流） -->
      <section class="section-block" aria-labelledby="gallery-sec-title">
        <GalleryWall :limit="60" />
      </section>
    </main>

    <!-- 简化页脚（无运维链接） -->
    <footer class="footer container">
      <div class="footer-inner">
        <span>{{ t('footer.note') }}</span>
        <span class="sep">·</span>
        <a href="https://github.com/lza6/" target="_blank" rel="noopener">GitHub github.com/lza6</a>
        <span class="sep">·</span>
        <a href="#" @click.prevent="goPrivacy">{{ t('nav.privacy') }}</a>
        <span class="sep">·</span>
        <span class="muted-2">v{{ appVersion }}</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.landing { position: relative; flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.nav { position: sticky; top: 0; z-index: 50; padding: var(--space-4) 0; border-bottom: 1px solid transparent; background: rgba(10, 14, 26, 0.4); backdrop-filter: blur(12px) saturate(140%); -webkit-backdrop-filter: blur(12px) saturate(140%); transition: padding var(--dur) var(--ease-out), background var(--dur) var(--ease-out), border-color var(--dur) var(--ease-out); }
.nav.scrolled { padding: var(--space-2) 0; background: rgba(10, 14, 26, 0.72); border-bottom-color: var(--line); backdrop-filter: blur(20px) saturate(160%); -webkit-backdrop-filter: blur(20px) saturate(160%); }
.nav-inner { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); flex-wrap: wrap; }
.brand { display: flex; align-items: center; gap: var(--space-3); }
.logo { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; background: linear-gradient(135deg, var(--brand), var(--accent)); color: #fff; font-size: 20px; font-weight: 800; box-shadow: 0 4px 16px var(--brand-glow), inset 0 1px 0 rgba(255, 255, 255, 0.25); flex-shrink: 0; }
.brand-text { display: flex; flex-direction: column; gap: 2px; }
.brand-name { font-size: 18px; font-weight: 800; letter-spacing: 0.01em; display: flex; align-items: center; gap: 8px; }
.brand-tag { font-size: 11px; font-weight: 600; color: var(--brand-2); background: var(--brand-soft); padding: 2px 8px; border-radius: var(--radius-pill); border: 1px solid rgba(96, 165, 250, 0.2); }
.brand-sub { font-size: 12.5px; color: var(--muted); max-width: 520px; }
.nav-actions { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.btn { display: inline-flex; align-items: center; gap: 8px; padding: 10px 18px; border-radius: var(--radius-pill); font-size: 14px; font-weight: 600; transition: transform var(--dur-fast) var(--ease-spring), box-shadow var(--dur) var(--ease-out), background var(--dur) var(--ease-out), border-color var(--dur) var(--ease-out); white-space: nowrap; }
.btn-primary { background: linear-gradient(135deg, var(--brand), var(--brand-2)); color: #fff; box-shadow: 0 4px 18px var(--brand-glow), inset 0 1px 0 rgba(255, 255, 255, 0.2); }
.btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 28px var(--brand-glow), inset 0 1px 0 rgba(255, 255, 255, 0.25); }
.btn-ghost { border: 1px solid var(--line-2); color: var(--text-2); background: var(--card); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); }
.btn-ghost:hover { border-color: var(--brand); color: var(--text); background: var(--brand-soft); transform: translateY(-1px); }
.lang-btn { cursor: pointer; font-family: var(--mono); min-width: 44px; }
.main { flex: 1; position: relative; z-index: 1; display: flex; flex-direction: column; gap: var(--space-6); padding-bottom: var(--space-7); }
.section-block { display: flex; flex-direction: column; gap: var(--space-4); }
.section-head { text-align: center; }
.section-head .kicker { margin: 0; color: var(--brand-2); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
.section-head h2 { font-size: clamp(24px, 3vw, 34px); }
.footer { padding: var(--space-4) 0 var(--space-6); }
.footer-inner { display: flex; align-items: center; justify-content: center; gap: 10px; flex-wrap: wrap; font-size: 13px; color: var(--muted); }
.sep { color: var(--muted-2); }
@media (max-width: 768px) {
  .brand-sub { max-width: 300px; }
  .main { gap: var(--space-5); }
}
</style>
