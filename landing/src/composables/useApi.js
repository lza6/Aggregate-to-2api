import { usePolling } from './usePolling'

// /v1/stats —— 状态胶囊条（总请求/出图/失败/耗时/并发/Worker/CF 求解）
export function useStats() {
  return usePolling('/v1/stats', 10000)
}

// /v1/providers —— 提供商网格
export function useProviders() {
  return usePolling('/v1/providers', 60000)
}

// /v1/models —— 模型列表
export function useModels() {
  return usePolling('/v1/models', 60000)
}

// /v1/meta —— 站台信息（aspect_ratios、supported_resolutions、api_key_mask）
export function useMeta() {
  return usePolling('/v1/meta', 60000)
}

// /v1/chat/usage — 对话 Token 用量
export function useChatUsage() {
  return usePolling('/v1/chat/usage?period=24h', 30000)
}
