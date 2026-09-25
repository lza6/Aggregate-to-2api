<script setup>
/**
 * ToolCard — 工具卡片（Spec 009 门户）
 * 点击展开为在线体验面板（PortalXxx），符合 media.io「工具即入口」。
 * 每个卡片 = 图标 + 名称 + 一句话 + 状态徽章 + 展开面板。
 */
import { computed, ref } from 'vue'
import { t } from '../../composables/useI18n'

const props = defineProps({
  id: { type: String, required: true },
  icon: { type: String, required: true },
  nameKey: { type: String, required: true },
  descKey: { type: String, required: true },
  tagKey: { type: String, required: true },
  openKey: { type: String, required: true },
  accent: { type: String, default: 'blue' }, // blue | pink | green | purple | amber
})

const open = ref(false)
function toggle() { open.value = !open.value }

const accentClass = computed(() => `accent-${props.accent}`)
</script>

<template>
  <article class="tool-card" :class="[accentClass, { open }]">
    <button type="button" class="tool-head" :aria-expanded="open" @click="toggle">
      <span class="tool-icon" aria-hidden="true">{{ icon }}</span>
      <span class="tool-meta">
        <span class="tool-name">{{ t(nameKey) }}</span>
        <span class="tool-desc">{{ t(descKey) }}</span>
      </span>
      <span class="tool-badge" :class="tagKey.includes('Beta') || tagKey.includes('Agent') ? 'warn' : 'ok'">{{ t(tagKey) }}</span>
      <span class="tool-open" aria-hidden="true">{{ open ? '−' : '+' }}</span>
    </button>

    <!-- 体验面板：由父级用 slot 注入对应 PortalXxx -->
    <div v-if="open" class="tool-body" role="region">
      <slot name="panel" />
    </div>
  </article>
</template>

<style scoped>
.tool-card {
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--card);
  box-shadow: var(--shadow-card);
  backdrop-filter: blur(16px) saturate(140%);
  -webkit-backdrop-filter: blur(16px) saturate(140%);
  overflow: hidden;
  transition: border-color var(--dur) var(--ease-out), box-shadow var(--dur) var(--ease-out), transform var(--dur) var(--ease-spring);
}
.tool-card:hover {
  transform: translateY(-2px);
  border-color: var(--line-2);
}
.tool-card.open {
  border-color: rgba(96, 165, 250, 0.35);
  box-shadow: var(--shadow-glow);
}
.tool-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  text-align: left;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  border: none;
  min-height: 64px;
}
.tool-icon {
  font-size: 30px;
  line-height: 1;
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: var(--brand-soft);
}
.accent-pink .tool-icon { background: var(--accent-soft); }
.accent-green .tool-icon { background: var(--ok-soft); }
.accent-purple .tool-icon { background: rgba(192, 132, 252, 0.16); }
.accent-amber .tool-icon { background: var(--warn-soft); }
.tool-meta { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.tool-name { font-size: 17px; font-weight: 700; }
.tool-desc { font-size: 13px; color: var(--muted); }
.tool-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}
.tool-badge.ok { background: var(--ok-soft); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.22); }
.tool-badge.warn { background: var(--warn-soft); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.22); }
.tool-open { font-size: 20px; color: var(--muted-2); flex-shrink: 0; }
.tool-body { border-top: 1px solid var(--line); padding: var(--space-4); }
@media (max-width: 768px) {
  .tool-head { padding: var(--space-3); }
  .tool-icon { width: 44px; height: 44px; font-size: 24px; }
  .tool-badge { display: none; }
}
</style>
