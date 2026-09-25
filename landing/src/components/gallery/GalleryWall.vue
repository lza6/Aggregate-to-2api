<script setup>
/**
 * GalleryWall — 灵感画廊（Spec 009 门户）
 * 真实 /v1/gallery 数据，瀑布流 + 懒加载 + 空态 + 错误态。
 * 点图可打开原图（新窗口）；hover 显示 prompt。
 */
import { computed, onMounted, ref } from 'vue'
import { t } from '../../composables/useI18n'
import { useGallery } from '../../composables/useApi'

const props = defineProps({ limit: { type: Number, default: 60 } })

const gallery = useGallery(props.limit)
const items = computed(() => {
  const raw = gallery.data.value?.items
  if (!Array.isArray(raw)) return []
  return raw.filter((it) => it && it.image_url && it.status === 'completed')
})
const loading = gallery.loading
const error = gallery.error

function src(item) { return item.image_url }
function prompt(item) { return (item.prompt || '').slice(0, 80) || (item.model || 'AI') }
</script>

<template>
  <section class="gallery-wall" aria-labelledby="gallery-title">
    <div class="wall-head">
      <div>
        <p class="kicker">{{ t('portal.gallery_sub') }}</p>
        <h2 id="gallery-title">{{ t('portal.gallery_title') }}</h2>
      </div>
      <span class="pill info">{{ gallery.data.value?.count ?? 0 }} 张</span>
    </div>

    <div v-if="loading" class="wall-skeleton" aria-busy="true">
      <span v-for="n in 6" :key="n" class="sk"></span>
    </div>
    <p v-else-if="error" class="wall-error" role="alert">{{ error }}</p>
    <p v-else-if="!items.length" class="wall-empty">{{ t('portal.gallery_empty') }}</p>

    <div v-else class="wall-grid">
      <a
        v-for="(item, i) in items"
        :key="item.id || i"
        class="wall-item"
        :href="src(item)"
        target="_blank"
        rel="noopener"
        :title="prompt(item)"
      >
        <img :src="src(item)" :alt="prompt(item)" loading="lazy" decoding="async" />
        <span class="wall-cap">{{ prompt(item) }}</span>
      </a>
    </div>
  </section>
</template>

<style scoped>
.gallery-wall { margin-top: var(--space-6); }
.wall-head { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-3); margin-bottom: var(--space-4); }
.kicker { margin: 0; color: var(--brand-2); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
h2 { margin: 4px 0; font-size: 28px; }
.wall-grid { columns: 3; column-gap: var(--space-3); }
.wall-item {
  position: relative;
  display: block;
  margin-bottom: var(--space-3);
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--line);
  break-inside: avoid;
  background: var(--card-2);
}
.wall-item img { width: 100%; display: block; aspect-ratio: auto; }
.wall-cap {
  position: absolute;
  inset: auto 0 0 0;
  padding: 10px 12px;
  font-size: 12px;
  color: #fff;
  background: linear-gradient(transparent, rgba(5, 8, 17, 0.85));
  opacity: 0;
  transition: opacity var(--dur) var(--ease-out);
}
.wall-item:hover .wall-cap, .wall-item:focus-visible .wall-cap { opacity: 1; }
.wall-skeleton { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-3); }
.sk { height: 180px; border-radius: var(--radius-sm); background: linear-gradient(90deg, var(--card-2), var(--card-hover), var(--card-2)); background-size: 200% 100%; animation: shine 1.1s infinite; }
.wall-empty, .wall-error { color: var(--muted); padding: var(--space-4); }
.wall-error { color: var(--warn); }
@keyframes shine { from { background-position: 100% 0; } to { background-position: -100% 0; } }
@media (max-width: 768px) {
  .wall-grid { columns: 2; }
  .wall-skeleton { grid-template-columns: repeat(2, 1fr); }
  h2 { font-size: 22px; }
}
</style>
