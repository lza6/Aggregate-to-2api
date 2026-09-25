<script setup>
/**
 * ToolsGrid — 工具卡片网格（Spec 009 门户）
 * 6 张工具卡：AI 对话 / 文生图 / 图生图 / AI 视频 / AI PPT / AI 智能体
 * 面板通过具名 slot 注入（panel:chat / panel:img / panel:edit / panel:video / panel:ppt / panel:agent）
 */
import { ref, computed } from 'vue'
import { t } from '../../composables/useI18n'
import ToolCard from './ToolCard.vue'

const props = defineProps({
  available: { type: Object, default: () => ({}) }, // { chat, img, edit, video, ppt, agent } 布尔可用性
})

const cards = computed(() => [
  { id: 'chat', icon: '💬', nameKey: 'tool.chat.name', descKey: 'tool.chat.desc', tagKey: 'tool.chat.tag', openKey: 'tool.chat.open', accent: 'blue' },
  { id: 'img', icon: '🎨', nameKey: 'tool.img.name', descKey: 'tool.img.desc', tagKey: 'tool.img.tag', openKey: 'tool.img.open', accent: 'pink' },
  { id: 'edit', icon: '🖌️', nameKey: 'tool.edit.name', descKey: 'tool.edit.desc', tagKey: 'tool.edit.tag', openKey: 'tool.edit.open', accent: 'green' },
  { id: 'video', icon: '🎬', nameKey: 'tool.video.name', descKey: 'tool.video.desc', tagKey: 'tool.video.tag', openKey: 'tool.video.open', accent: 'purple' },
  { id: 'ppt', icon: '📊', nameKey: 'tool.ppt.name', descKey: 'tool.ppt.desc', tagKey: 'tool.ppt.tag', openKey: 'tool.ppt.open', accent: 'amber' },
  { id: 'agent', icon: '🤖', nameKey: 'tool.agent.name', descKey: 'tool.agent.desc', tagKey: 'tool.agent.tag', openKey: 'tool.agent.open', accent: 'blue' },
])

const active = ref('')
function onOpen(id) { active.value = active.value === id ? '' : id }

const panelSlot = computed(() => ({
  chat: 'panel:chat', img: 'panel:img', edit: 'panel:edit', video: 'panel:video', ppt: 'panel:ppt', agent: 'panel:agent',
}))
</script>

<template>
  <div class="tools-grid">
    <ToolCard
      v-for="card in cards"
      :key="card.id"
      :id="card.id"
      :icon="card.icon"
      :name-key="card.nameKey"
      :desc-key="card.descKey"
      :tag-key="card.tagKey"
      :open-key="card.openKey"
      :accent="card.accent"
    >
      <template #panel>
        <slot :name="panelSlot[card.id]" :available="available[card.id]" />
      </template>
    </ToolCard>
  </div>
</template>

<style scoped>
.tools-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}
@media (max-width: 900px) {
  .tools-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .tools-grid { grid-template-columns: 1fr; }
}
</style>
