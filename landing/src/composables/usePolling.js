import { ref, onMounted, onBeforeUnmount } from 'vue'

/**
 * 轮询数据源 hook。
 * - 同源相对路径 /v1/...（base 空字符串）
 * - 每次请求都在 try/catch 中，失败不抛错，写入 error 并保留上次 data
 * - 卸载时清空定时器
 * @param {string} url 相对路径，如 '/v1/stats'
 * @param {number} intervalMs 轮询间隔
 * @param {object} options
 * @param {function} [options.transform] 对响应做可选归一化
 * @param {boolean} [options.immediate=true] 是否挂载后立即拉取
 */
export function usePolling(url, intervalMs, options = {}) {
  const { transform, immediate = true } = options
  const data = ref(null)
  const error = ref(null)
  const loading = ref(!!immediate)
  let timer = null

  async function fetchOnce() {
    try {
      const res = await fetch(url, { headers: { Accept: 'application/json' } })
      if (!res.ok) {
        const body = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status}${body ? ': ' + body.slice(0, 120) : ''}`)
      }
      const json = await res.json()
      data.value = transform ? transform(json) : json
      error.value = null
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  function start() {
    if (timer) clearInterval(timer)
    if (intervalMs > 0) timer = setInterval(fetchOnce, intervalMs)
  }

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  onMounted(() => {
    if (immediate) fetchOnce()
    start()
  })
  onBeforeUnmount(stop)

  return { data, error, loading, fetchOnce, start, stop }
}
