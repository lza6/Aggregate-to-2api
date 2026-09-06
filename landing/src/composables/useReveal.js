/**
 * useReveal — 滚动揭示预设（P2-C2 优化版：原生 IntersectionObserver + CSS）
 *
 * 旧版：封装 motion-v 的 whileInView，每个 section 包一层 <motion.div>，
 *   会让 motion-v（~30kb gz）进入首屏关键路径。
 * 新版：返回 CSS class + 原生 IntersectionObserver 切换 class。
 *   - 触发前：.reveal-init（opacity 0, translateY 28px）
 *   - 视口内：.reveal-in（opacity 1, translateY 0，CSS transition 接管）
 *   - reduced-motion：直接 opacity 1，无位移
 *
 * 用法：
 *   const { ref, shown } = useReveal(0.3)
 *   <section ref="ref" :class="['reveal', shown ? 'reveal-in' : 'reveal-init']">…</section>
 *
 * 保留 motion-v 的 App.vue 仍可工作（向后兼容），但新代码应改用此 hook。
 * 后续可逐步把 App.vue 的 <motion.section v-bind="revealN"> 替换为原生 <section>。
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useMediaQuery } from '@vueuse/core'

export function useReveal(delay = 0) {
  const el = ref<HTMLElement | null>(null)
  const shown = ref(false)
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')

  /** @type {IntersectionObserver | null} */
  let io = null

  onMounted(() => {
    // reduced-motion：直接显示，不观察
    if (reduced.value) {
      shown.value = true
      return
    }
    if (!el.value || typeof IntersectionObserver === 'undefined') {
      // 环境降级：无 IO 支持 → 直接显示
      shown.value = true
      return
    }
    io = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          // 延迟应用（模拟 motion-v 的 delay）
          if (delay > 0) {
            setTimeout(() => { shown.value = true }, delay * 1000)
          } else {
            shown.value = true
          }
          // once: true —— 触发一次后停止观察
          if (io && el.value) io.unobserve(el.value)
          break
        }
      }
    }, { rootMargin: '-80px 0px', threshold: 0.1 })
    io.observe(el.value)
  })

  onBeforeUnmount(() => {
    if (io) { io.disconnect(); io = null }
  })

  return { ref: el, shown }
}

/**
 * 全局 CSS 类（需在 base.css 或组件 <style> 中定义）：
 *   .reveal { transition: opacity var(--dur-slow) var(--ease-spring), transform var(--dur-slow) var(--ease-spring); will-change: opacity, transform; }
 *   .reveal-init { opacity: 0; transform: translateY(28px); }
 *   .reveal-in { opacity: 1; transform: translateY(0); }
 *   @media (prefers-reduced-motion: reduce) { .reveal, .reveal-init, .reveal-in { transition: none; opacity: 1; transform: none; } }
 *
 * 这些类已追加到 base.css（P2-C2 同步改动）。
 */

export default useReveal
