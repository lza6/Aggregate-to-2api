import type { Dispatch, SetStateAction } from 'react';
import { classifyError } from '../Feedback';
import type { ChatModelInfo } from '../../api';

export type ChatRole = 'user' | 'assistant';
export type Effort = 'quick' | 'balanced' | 'deep';

export interface ChatMessage {
  role: ChatRole;
  content: string;
  reasoning?: string;
  toolCalls?: string[];
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
  durationMs?: number;
  error?: boolean;
  /** D2: 错误类别（用于错误气泡内联切备用 provider 行动） */
  errorKind?: ReturnType<typeof classifyError>;
}

export interface SseResult {
  content: string;
  reasoning: string;
  toolCalls: string[];
  usage?: ChatMessage['usage'];
}

export interface ChatErrorPayload {
  message: string;
  retryAfterMinutes?: number;
}

export class ChatRequestError extends Error {
  status: number;
  retryAfterMinutes?: number;

  constructor(message: string, status: number, retryAfterMinutes?: number) {
    super(message);
    this.name = 'ChatRequestError';
    this.status = status;
    this.retryAfterMinutes = retryAfterMinutes;
  }
}

export type ChatGroupKey = 'image' | 'chat' | 'tools' | 'multimodal';

export const CHAT_GROUP_ORDER: ChatGroupKey[] = ['image', 'chat', 'tools', 'multimodal'];
export const CHAT_GROUP_META: Record<ChatGroupKey, { label: string; hint: string }> = {
  image: { label: '🎨 生图模型', hint: '仅文本提示生成图像' },
  chat: { label: '💬 对话模型', hint: '纯文本对话' },
  tools: { label: '🔧 工具/智能体模型', hint: '支持函数调用' },
  multimodal: { label: '🖼️ 多模态模型', hint: '支持图片输入' },
};

export const HISTORY_KEY = 'chatPlaygroundHistory';
export const MAX_CONTEXT_MESSAGES = 30;
export const MAX_TEXTAREA_ROWS = 6;

/** P3-3: 模型能力分组 key（生图/对话/工具/多模态）——按 capabilities 集合匹配，避免重复计组。 */
export function capabilityGroupOf(caps: readonly string[] | undefined): ChatGroupKey | null {
  if (!caps || caps.length === 0) return null;
  const set = new Set(caps);
  if (set.has('chat_vision') || set.has('img2img') || set.has('img2vid')) return 'multimodal';
  if (set.has('chat_tools') || set.has('tools')) return 'tools';
  if (set.has('chat')) return 'chat';
  if (set.has('txt2img') || set.has('img2img')) return 'image';
  return null;
}

export function groupedModels(models: ChatModelInfo[]): { key: ChatGroupKey; label: string; models: ChatModelInfo[] }[] {
  const buckets = new Map<ChatGroupKey, ChatModelInfo[]>();
  const fallback: ChatModelInfo[] = [];
  for (const m of models) {
    const key = capabilityGroupOf(m.capabilities);
    if (!key) { fallback.push(m); continue; }
    const list = buckets.get(key) ?? [];
    list.push(m);
    buckets.set(key, list);
  }
  const groups = CHAT_GROUP_ORDER
    .filter(key => (buckets.get(key)?.length ?? 0) > 0)
    .map(key => ({ key, label: CHAT_GROUP_META[key].label, models: buckets.get(key) ?? [] }));
  if (fallback.length > 0) groups.push({ key: 'chat', label: '未分类模型', models: fallback });
  return groups;
}

export function loadHistory(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is ChatMessage => {
      if (!item || typeof item !== 'object') return false;
      const candidate = item as Partial<ChatMessage>;
      return (candidate.role === 'user' || candidate.role === 'assistant') && typeof candidate.content === 'string';
    });
  } catch {
    return [];
  }
}

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, character => {
    const entities: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    };
    return entities[character];
  });
}

/** 先转义全部文本，再只生成受控的粗体、代码块和换行标签。 */
export function renderMarkdown(text: string): { __html: string } {
  const escaped = escapeHtml(text);
  const chunks = escaped.split('```');
  const html = chunks.map((chunk, index) => {
    if (index % 2 === 1) {
      const code = chunk.replace(/^\w+\n/, '');
      return `<pre><code>${code}</code></pre>`;
    }
    return chunk.replace(/\*\*(.+?)\*\*/gs, '<strong>$1</strong>').replace(/\n/g, '<br />');
  }).join('');
  return { __html: html };
}

export function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString() : '-';
}

export function getUsageTotal(usage: ChatMessage['usage']): number | undefined {
  if (!usage) return undefined;
  if (typeof usage.total_tokens === 'number') return usage.total_tokens;
  const prompt = typeof usage.prompt_tokens === 'number' ? usage.prompt_tokens : 0;
  const completion = typeof usage.completion_tokens === 'number' ? usage.completion_tokens : 0;
  return prompt + completion > 0 ? prompt + completion : undefined;
}

export function getMessageContent(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    return value.map(part => {
      if (typeof part === 'string') return part;
      if (part && typeof part === 'object' && 'text' in part) {
        const text = (part as { text?: unknown }).text;
        return typeof text === 'string' ? text : '';
      }
      return '';
    }).join('');
  }
  return '';
}

export function getErrorPayload(payload: unknown, status: number): ChatErrorPayload {
  if (!payload || typeof payload !== 'object') {
    if (status === 429) return { message: '当前提供商繁忙，已为您自动切换至备用引擎' };
    if (status === 401) return { message: 'API Key 未配置或无效，请在右上角设置中填写有效 Key' };
    return { message: `请求失败（HTTP ${status}）` };
  }
  const body = payload as Record<string, unknown>;
  const nested = body.error && typeof body.error === 'object' ? body.error as Record<string, unknown> : undefined;
  let messageCandidate = typeof body.message === 'string'
    ? body.message
    : typeof body.error === 'string'
      ? body.error
      : nested?.message;

  if (status === 429 || (typeof messageCandidate === 'string' && (messageCandidate.includes('rate') || messageCandidate.includes('limit') || messageCandidate.includes('限流')))) {
    messageCandidate = '当前提供商繁忙，已为您自动切换至备用引擎';
  } else if (status === 401 || (typeof messageCandidate === 'string' && (messageCandidate.includes('key') || messageCandidate.includes('auth') || messageCandidate.includes('unauthorized')))) {
    messageCandidate = 'API Key 未配置或无效，请点击右上角【API 接入 & Key】进行配置';
  }

  const retryCandidate = body.retryAfterMinutes ?? body.retry_after_minutes ?? nested?.retryAfterMinutes ?? nested?.retry_after_minutes;
  return {
    message: typeof messageCandidate === 'string' ? messageCandidate : `请求失败（HTTP ${status}）`,
    retryAfterMinutes: typeof retryCandidate === 'number' ? retryCandidate : undefined,
  };
}

export async function readResponseJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export function appendAssistantMessage(setMessages: Dispatch<SetStateAction<ChatMessage[]>>, updater: (message: ChatMessage) => ChatMessage) {
  setMessages(previous => {
    if (!previous.length || previous[previous.length - 1].role !== 'assistant') return previous;
    const lastIndex = previous.length - 1;
    return previous.map((message, index) => index === lastIndex ? updater(message) : message);
  });
}
