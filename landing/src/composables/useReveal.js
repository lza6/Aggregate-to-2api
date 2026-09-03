/**
 * useReveal — 封装 motion-v 的 whileInView 滚动揭示预设
 * 用法：const reveal = useReveal(); <motion.div v-bind="reveal">…</motion.div>
 * 降级：reduced-motion 为真时退化为瞬时显示（opacity 1, 无位移）
 */
import { computed } from 'vue'
import { useMediaQuery } from '@vueuse/core'

export function useReveal(delay = 0) {
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  return computed(() =>
    reduced.value
      ? { initial: { opacity: 1, y: 0 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0 } }
      : {
          initial: { opacity: 0, y: 28 },
          whileInView: { opacity: 1, y: 0 },
          viewport: { once: true, margin: '-80px' },
          transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1], delay }
        }
  )
}
