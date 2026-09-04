import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { chatCompletions, fetchChatModels, fetchChatRemaining, fetchChatUsage, fetchProviders, getStoredApiKey, setStoredApiKey, notify } from '../api';
import type { ChatModelInfo, ChatRemaining, ChatUsageStats } from '../api';
import { useApi } from '../hooks/useApi';
import { classifyError, type ProviderOption } from '../components/Feedback';
import {
  ChatRequestError, appendAssistantMessage, getErrorPayload, readResponseJson,
  groupedModels, loadHistory, HISTORY_KEY, MAX_CONTEXT_MESSAGES, MAX_TEXTAREA_ROWS,
  formatNumber,
  type ChatMessage, type Effort,
} from '../components/chat/chat-utils';
import { MessageBubble, ModelPicker } from '../components/chat/ChatComponents';
import { useChatStream } from '../components/chat/useChatStream';

export function ChatPlayground() {
  const { data: modelsData, loading: modelsLoading, error: modelsError, reload: reloadModels } = useApi<{ items: ChatModelInfo[]; count: number; auth_required?: boolean }>(fetchChatModels);
  const { data: remaining } = useApi<ChatRemaining>(fetchChatRemaining, { intervalMs: 30000 });
  const { data: providersData } = useApi(() => fetchProviders());
  const { data: usage } = useApi<ChatUsageStats>(() => fetchChatUsage('1h'), { intervalMs: 60000 });
  const [model, setModel] = useState('');
  const [effort, setEffort] = useState<Effort>('balanced');
  const [messages, setMessages] = useState<ChatMessage[]>(loadHistory);
  const [input, setInput] = useState('');
  const [stream, setStream] = useState(true);
  const [sending, setSending] = useState(false);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [apiKey, setApiKey] = useState(getStoredApiKey);
  const [showApiPanel, setShowApiPanel] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const consumeSse = useChatStream();
  const models = modelsData?.items ?? [];

  useEffect(() => {
    if (!model && models.length > 0) setModel(models[0].id);
  }, [model, models]);

  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(messages));
    } catch {
      // 本地存储不可用时仍保留当前会话，不阻断聊天。
    }
  }, [messages]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const lineHeight = Number.parseFloat(getComputedStyle(textarea).lineHeight) || 22;
    textarea.style.height = `${Math.min(textarea.scrollHeight, lineHeight * MAX_TEXTAREA_ROWS + 20)}px`;
  }, [input]);

  useEffect(() => {
    const container = messagesRef.current;
    if (!container || !isNearBottom) return;
    container.scrollTop = container.scrollHeight;
  }, [messages, isNearBottom]);

  const updateScrollPosition = useCallback(() => {
    const container = messagesRef.current;
    if (!container) return;
    setIsNearBottom(container.scrollHeight - container.scrollTop - container.clientHeight < 80);
  }, []);

  const clearConversation = useCallback(() => {
    setMessages([]);
    localStorage.removeItem(HISTORY_KEY);
  }, []);

  const exportMarkdown = useCallback(() => {
    if (messages.length === 0) {
      notify('当前没有可导出的对话', 'info');
      return;
    }
    const markdown = messages.map(message => {
      const title = message.role === 'user' ? '## 你' : '## 助手';
      const reasoning = message.reasoning ? `\n\n<details>\n<summary>思考过程</summary>\n\n${message.reasoning}\n\n</details>` : '';
      return `${title}\n\n${message.content}${reasoning}`;
    }).join('\n\n---\n\n');
    const blob = new Blob([`# AI 聊天记录\n\n${markdown}\n`], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `chat-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }, [messages]);

  const exportJson = useCallback(() => {
    if (messages.length === 0) {
      notify('当前没有可导出的对话', 'info');
      return;
    }
    const payload = { exported_at: new Date().toISOString(), model, effort, messages };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `chat-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }, [messages, model, effort]);

  const modelGroups = useMemo(() => groupedModels(models), [models]);
  const modelPickerHint = useMemo(() => {
    const current = models.find(m => m.id === model);
    if (!current) return undefined;
    const parts: string[] = [];
    if (current.context_window) parts.push(`上下文 ${(current.context_window / 1024).toFixed(0)}K`);
    if (current.price_per_mtok) parts.push(`约 $${current.price_per_mtok}/M tokens`);
    return parts.length ? parts.join(' · ') : undefined;
  }, [models, model]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || !model || sending) return;
    const userMessage: ChatMessage = { role: 'user', content: text };
    const nextMessages = [...messages, userMessage];
    const requestMessages = nextMessages.slice(-MAX_CONTEXT_MESSAGES).map(({ role, content }) => ({ role, content }));
    setMessages([...nextMessages, { role: 'assistant', content: '' }]);
    setInput('');
    setSending(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const startedAt = performance.now();

    try {
      const response = await chatCompletions({ model, messages: requestMessages, stream, reasoning_effort: effort }, controller.signal);
      if (!response.ok) {
        const payload = getErrorPayload(await readResponseJson(response), response.status);
        throw new ChatRequestError(payload.message, response.status, payload.retryAfterMinutes);
      }

      let result: import('../components/chat/chat-utils').SseResult;
      if (stream) {
        result = await consumeSse({ response, onDelta: delta => {
          appendAssistantMessage(setMessages, current => ({
            ...current,
            content: `${current.content}${delta.content ?? ''}`,
            reasoning: `${current.reasoning ?? ''}${delta.reasoning ?? ''}`,
            toolCalls: delta.toolCall ? [...(current.toolCalls ?? []), delta.toolCall] : current.toolCalls,
          }));
        } });
      } else {
        const payload = await readResponseJson(response) as Record<string, unknown> | null;
        const choices = payload && Array.isArray(payload.choices) ? payload.choices : [];
        const choice = choices[0] && typeof choices[0] === 'object' ? choices[0] as Record<string, unknown> : {};
        const message = choice.message && typeof choice.message === 'object' ? choice.message as Record<string, unknown> : choice;
        const content = (message.content as unknown) as string | undefined;
        const reasoning = (message.reasoning_content ?? message.reasoning) as unknown as string | undefined;
        const rawTools = Array.isArray(message.tool_calls) ? message.tool_calls : [];
        result = {
          content: typeof content === 'string' ? content : '',
          reasoning: typeof reasoning === 'string' ? reasoning : '',
          toolCalls: rawTools.map(item => typeof item === 'string' ? item : JSON.stringify(item)),
          usage: payload?.usage && typeof payload.usage === 'object' ? payload.usage as ChatMessage['usage'] : undefined,
        };
      }
      appendAssistantMessage(setMessages, current => ({
        ...current,
        content: result.content || current.content,
        reasoning: result.reasoning || current.reasoning,
        toolCalls: result.toolCalls.length > 0 ? result.toolCalls : current.toolCalls,
        usage: result.usage,
        durationMs: Math.round(performance.now() - startedAt),
      }));
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        appendAssistantMessage(setMessages, current => ({ ...current, content: current.content || '已停止生成。', durationMs: Math.round(performance.now() - startedAt) }));
      } else {
        const message = error instanceof ChatRequestError
          ? error.message
          : error instanceof Error ? error.message : '聊天请求失败';
        const retryAfterMinutes = error instanceof ChatRequestError ? error.retryAfterMinutes : undefined;
        const retryHint = retryAfterMinutes !== undefined ? `，请约 ${retryAfterMinutes} 分钟后重试` : '';
        notify(`${message}${retryHint}`, 'error');
        appendAssistantMessage(setMessages, () => ({ role: 'assistant', content: `${message}${retryHint}`, error: true, errorKind: classifyError(`${message}${retryHint}`) as ChatMessage['errorKind'], durationMs: Math.round(performance.now() - startedAt) }));
      }
    } finally {
      setSending(false);
      abortRef.current = null;
    }
  }, [consumeSse, effort, input, messages, model, sending, stream]);

  const stopGenerating = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const effortHint = useMemo(() => ({ quick: 'Thinks little', balanced: 'Default', deep: 'Deep thinking' }[effort]), [effort]);
  const remainingClass = remaining && remaining.remaining < 5 ? 'is-low' : '';

  const providerOptions: ProviderOption[] = useMemo(() => {
    const items = providersData?.items;
    if (!items) return [];
    return Object.entries(items).map(([id, p]) => ({ id, label: p.display_name || id, health: p.health_status }));
  }, [providersData]);
  const activeProvider = useMemo(() => model?.split('/')[0] ?? '', [model]);
  const switchChatProvider = useCallback((providerId: string) => {
    const candidates = models.filter(m => m.id.startsWith(`${providerId}/`));
    if (candidates.length > 0) {
      setModel(candidates[0].id);
      notify(`已切换到备用引擎：${candidates[0].display_name || candidates[0].id}`, 'success');
    } else {
      notify(`provider ${providerId} 暂无对话模型`, 'info');
    }
  }, [models]);

  return (
    <div className="chat-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">在线聊天 <span className="title-badge">AI Playground</span></h1>
          <p className="page-desc">选择模型，直接体验统一 AI 聊天服务与流式响应能力</p>
        </div>
        {/* v7.7 UX：模型列表加载失败不再静默锁死，给出可见错误与重试 */}
        {modelsError && (
          <div className="tf-card" style={{ padding: '12px 16px', fontSize: 12.5, color: 'var(--danger-text)', background: 'var(--danger-bg)', borderColor: 'var(--danger-border)' }}>
            模型目录加载失败：{modelsError.message}
            <button className="tf-btn tf-btn-secondary tf-btn-sm" style={{ marginLeft: 8 }} onClick={reloadModels}>🔄 重试</button>
          </div>
        )}
        <div className="chat-header-actions">
          <button className="tf-btn tf-btn-secondary tf-btn-sm" onClick={() => setShowApiPanel(v => !v)}>
            🔑 API 接入
          </button>
          <div className={`chat-remaining-pill ${remainingClass}`}>
            <span className="remaining-dot" />
            剩余额度 <strong>{remaining ? formatNumber(remaining.remaining) : '-'}</strong>
          </div>
        </div>
      </div>

      {showApiPanel && (
        <section className="tf-card chat-api-panel">
          <h3 className="chat-api-title">API 接入指南（OpenAI / Anthropic 兼容）</h3>
          {modelsData?.auth_required !== false && (
            <div className="chat-key-row">
              <label htmlFor="chat-api-key-input">API Key（仅保存在本浏览器 localStorage，随请求 Bearer 头发送）</label>
              <div className="chat-key-controls">
                <input
                  id="chat-api-key-input"
                  type="password"
                  value={apiKey}
                  placeholder={modelsData?.auth_required ? '必填：sk-…' : '可选：未启用鉴权可留空'}
                  onChange={event => setApiKey(event.target.value)}
                />
                <button
                  className="tf-btn tf-btn-primary tf-btn-sm"
                  onClick={() => {
                    setStoredApiKey(apiKey);
                    notify(apiKey.trim() ? 'API Key 已保存到本地' : 'API Key 已清除', 'success');
                  }}
                  disabled={!modelsData?.auth_required}
                >保存 Key</button>
              </div>
            </div>
          )}
          <p className="chat-api-note">以下示例把 <code>&lt;key&gt;</code> 换成你的 Key；<code>BASE</code> 换成本站地址。</p>
          <pre className="chat-api-code">{`# OpenAI 兼容（Codex / Cursor / Continue / 任意 OpenAI SDK）
curl -X POST ${window.location.origin}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  ${apiKey.trim() ? '-H "Authorization: Bearer ' + apiKey.trim() + '" \\\n  ' : ''}-d '{"model":"${model || 'tryingopen/z-ai/glm-5.3-flash'}","messages":[{"role":"user","content":"你好"}],"stream":true}'

# Anthropic 兼容（Claude Code）
export ANTHROPIC_BASE_URL=${window.location.origin}/v1
curl -X POST ${window.location.origin}/v1/messages \\
  -H "Content-Type: application/json" \\
  ${apiKey.trim() ? '-H "X-API-Key: ' + apiKey.trim() + '" \\\n  ' : ''}-d '{"model":"${model || 'tryingopen/qwen/qwen3.8-27b'}","max_tokens":1024,"messages":[{"role":"user","content":"hi"}]}'`}
          </pre>
          <div className="chat-api-models">
            <strong>可用模型 ID：</strong>
            <code>{models.map(m => m.id).join(' · ')}</code>
          </div>
        </section>
      )}

      <section className="tf-card chat-controls">
        <ModelPicker groups={modelGroups} value={model} loading={modelsLoading} hint={modelPickerHint} onChange={setModel} />
        <label className="chat-control-field">
          <span>思考深度</span>
          <select value={effort} onChange={event => setEffort(event.target.value as Effort)}>
            <option value="quick">Quick · Thinks little</option>
            <option value="balanced">Balanced · Default</option>
            <option value="deep">Deep · Deep thinking</option>
          </select>
          <small>{effortHint}</small>
        </label>
        <label className="chat-stream-toggle">
          <input type="checkbox" checked={stream} onChange={event => setStream(event.target.checked)} />
          <span>流式响应</span>
        </label>
        <div className="chat-control-actions">
          <button className="tf-btn tf-btn-secondary tf-btn-sm" onClick={clearConversation} disabled={messages.length === 0}>清空对话</button>
          <button className="tf-btn tf-btn-secondary tf-btn-sm" onClick={exportMarkdown} disabled={messages.length === 0}>导出 Markdown</button>
          <button className="tf-btn tf-btn-secondary tf-btn-sm" onClick={exportJson} disabled={messages.length === 0}>导出 JSON</button>
        </div>
      </section>

      <section className="tf-card chat-workspace">
        <div className="chat-quota-line">
          <span>本小时调用额度</span>
          <span>{remaining ? `${formatNumber(remaining.used_last_hour)} / ${formatNumber(remaining.hourly_limit)}` : '加载中…'}</span>
        </div>
        <div className="chat-messages" ref={messagesRef} onScroll={updateScrollPosition}>
          {messages.length === 0 ? (
            <div className="chat-empty">
              <div className="chat-empty-icon">💬</div>
              <strong>开始一段新对话</strong>
              <span>输入问题后按 Enter 发送，Shift + Enter 换行</span>
            </div>
          ) : messages.map((message, index) => (
            <MessageBubble
              key={`${message.role}-${index}`}
              message={message}
              backupProviders={providerOptions}
              activeProvider={activeProvider}
              onSwitchProvider={switchChatProvider}
            />
          ))}
        </div>
        {usage && (
          <div className="chat-usage-line">
            <span>近 1h 用量</span>
            <span>
              {formatNumber(usage.total_calls)} 调用 · 成功 {formatNumber(usage.ok_calls)}
              {usage.avg_duration_ms != null ? ` · 均 ${usage.avg_duration_ms}ms` : ''}
              {usage.cost_usd != null ? ` · $${usage.cost_usd}` : ''}
              {' · '}今日 {formatNumber(usage.today_tokens)} tokens
            </span>
          </div>
        )}
        <div className="chat-input-area">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={event => setInput(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void sendMessage();
              }
            }}
            placeholder={model ? '输入消息…' : '请先等待聊天模型加载'}
            disabled={sending || !model}
            rows={1}
            aria-label="聊天消息"
          />
          {sending ? (
            <button className="tf-btn tf-btn-danger chat-send-button" onClick={stopGenerating}>停止</button>
          ) : (
            <button className="tf-btn tf-btn-primary chat-send-button" onClick={() => void sendMessage()} disabled={!input.trim() || !model}>发送</button>
          )}
        </div>
      </section>

      <style>{`
        .chat-page { display: flex; flex-direction: column; gap: 20px; min-height: calc(100vh - 112px); }
        .chat-page .page-header { margin-bottom: 0; }
        .chat-header-actions { display: flex; align-items: center; gap: 12px; }
        .chat-api-panel { padding: 20px 22px; display: flex; flex-direction: column; gap: 14px; }
        .chat-api-title { font-size: 15px; font-weight: 700; color: var(--text-primary); }
        .chat-key-row { display: flex; flex-direction: column; gap: 8px; }
        .chat-key-row > label { font-size: 12px; color: var(--text-secondary); }
        .chat-key-controls { display: flex; gap: 8px; }
        .chat-key-controls input { flex: 1; max-width: 380px; font-family: ui-monospace, monospace; }
        .chat-api-note { font-size: 12px; color: var(--text-muted); }
        .chat-api-code { margin: 0; padding: 14px 16px; overflow-x: auto; border: 1px solid var(--border-default); border-radius: 10px; background: var(--bg-subtle); color: var(--text-primary); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; line-height: 1.6; white-space: pre; }
        .chat-api-models { font-size: 11.5px; color: var(--text-secondary); line-height: 1.7; word-break: break-all; }
        .chat-api-models code { color: var(--primary-500); }
        .chat-remaining-pill { display: flex; align-items: center; gap: 8px; border: 1px solid var(--success-border); background: var(--success-bg); color: var(--success-text); padding: 8px 13px; border-radius: var(--radius-full); font-size: 12px; white-space: nowrap; }
        .chat-remaining-pill.is-low { border-color: var(--danger-border); background: var(--danger-bg); color: var(--danger-text); }
        .remaining-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); box-shadow: 0 0 8px var(--success); }
        .is-low .remaining-dot { background: var(--danger); box-shadow: 0 0 8px var(--danger); }
        .chat-controls { display: flex; align-items: flex-end; gap: 14px; padding: 16px 18px; flex-wrap: wrap; }
        .chat-control-field { display: flex; flex-direction: column; gap: 6px; min-width: 210px; }
        .chat-control-field > span { font-size: 11.5px; color: var(--text-muted); }
        .chat-control-field select { min-width: 210px; }
        .chat-control-field small { color: var(--text-muted); font-size: 10.5px; margin-top: -2px; }
        .chat-stream-toggle { display: flex; align-items: center; gap: 7px; height: 36px; color: var(--text-secondary); font-size: 12px; white-space: nowrap; }
        .chat-stream-toggle input { accent-color: var(--primary-500); }
        .chat-control-actions { display: flex; gap: 8px; margin-left: auto; }
        .chat-workspace { display: flex; flex-direction: column; min-height: 480px; overflow: hidden; }
        .chat-quota-line { display: flex; justify-content: space-between; padding: 12px 18px; border-bottom: 1px solid var(--border-default); color: var(--text-muted); font-size: 11.5px; }
        .chat-messages { display: flex; flex: 1; flex-direction: column; gap: 18px; max-height: calc(100vh - 320px); min-height: 330px; overflow-y: auto; padding: 22px clamp(14px, 4vw, 50px); scroll-behavior: smooth; }
        .chat-empty { display: flex; flex: 1; align-items: center; justify-content: center; flex-direction: column; gap: 8px; color: var(--text-muted); min-height: 270px; }
        .chat-empty strong { color: var(--text-primary); font-size: 15px; }
        .chat-empty span { font-size: 12px; }
        .chat-empty-icon { font-size: 40px; opacity: .8; margin-bottom: 4px; }
        .chat-message-row { display: flex; gap: 10px; align-items: flex-start; max-width: 86%; }
        .chat-message-row.is-user { align-self: flex-end; flex-direction: row-reverse; }
        .chat-avatar { display: flex; flex: 0 0 30px; width: 30px; height: 30px; align-items: center; justify-content: center; border-radius: 10px; font-size: 10px; font-weight: 700; }
        .user-avatar { color: #fff; background: linear-gradient(135deg, var(--primary-500), #3b82f6); }
        .assistant-avatar { color: var(--primary-500); background: var(--bg-subtle); border: 1px solid var(--border-default); }
        .chat-bubble { min-width: 80px; padding: 11px 14px; border: 1px solid var(--border-default); border-radius: 4px 14px 14px 14px; background: var(--bg-card); color: var(--text-primary); box-shadow: var(--shadow-sm); line-height: 1.65; font-size: 13px; overflow-wrap: anywhere; }
        .is-user .chat-bubble { border: 0; border-radius: 14px 4px 14px 14px; color: #fff; background: linear-gradient(135deg, var(--primary-600), #2563eb); }
        .chat-role-label { color: var(--text-muted); font-size: 10px; font-weight: 600; margin-bottom: 3px; }
        .is-user .chat-role-label { color: rgba(255,255,255,.72); text-align: right; }
        .chat-content pre { margin: 8px 0; padding: 10px 12px; overflow-x: auto; border: 1px solid var(--border-default); border-radius: 8px; background: var(--bg-subtle); color: var(--text-primary); line-height: 1.5; }
        .chat-content code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
        .chat-content strong { font-weight: 700; }
        .chat-reasoning { margin-bottom: 9px; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--bg-subtle); color: var(--text-muted); font-size: 11px; }
        .chat-reasoning summary { cursor: pointer; padding: 6px 9px; user-select: none; }
        .chat-reasoning-content { padding: 0 9px 8px; white-space: pre-wrap; line-height: 1.5; }
        .chat-message-meta, .chat-tool-calls { margin-top: 7px; color: var(--text-muted); font-size: 10.5px; }
        .is-user .chat-message-meta { color: rgba(255,255,255,.68); }
        .chat-inline-error { color: var(--danger-text); background: var(--danger-bg); border: 1px solid var(--danger-border); border-radius: 7px; padding: 8px 10px; font-size: 12px; }
        .chat-error-action { margin-top: 8px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
        .chat-error-hint { font-size: 11px; color: var(--danger-text); opacity: 0.85; }
        .chat-provider-chip { display: inline-flex; align-items: center; gap: 5px; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-default); padding: 4px 10px; border-radius: var(--radius-full); font-size: 11.5px; cursor: pointer; }
        .chat-provider-chip:hover:not(:disabled) { border-color: var(--primary-500); }
        .chat-provider-chip:disabled { opacity: 0.5; cursor: not-allowed; }
        .chat-chip-dot { width: 5px; height: 5px; border-radius: 50%; }
        .chat-chip-dot.ok { background: var(--success); box-shadow: 0 0 5px var(--success); }
        .chat-usage-line { display: flex; justify-content: space-between; padding: 8px 18px; border-top: 1px solid var(--border-default); background: var(--bg-subtle); color: var(--text-muted); font-size: 11.5px; }
        .chat-input-area { display: flex; align-items: flex-end; gap: 10px; padding: 14px 18px 16px; border-top: 1px solid var(--border-default); background: var(--bg-subtle); }
        .chat-input-area textarea { flex: 1; min-height: 38px; max-height: 152px; resize: none; border: 1px solid var(--border-default); border-radius: 10px; background: var(--bg-card); color: var(--text-primary); padding: 9px 12px; font: inherit; font-size: 13px; line-height: 22px; outline: none; }
        .chat-input-area textarea:focus { border-color: var(--primary-500); box-shadow: 0 0 0 3px rgba(99,102,241,.14); }
        .chat-send-button { min-width: 58px; height: 38px; }
        @media (max-width: 680px) {
          .chat-control-field, .chat-control-field select { min-width: min(100%, 220px); width: 100%; }
          .chat-control-actions { margin-left: 0; width: 100%; }
          .chat-control-actions button { flex: 1; }
          .chat-message-row { max-width: 96%; }
          .chat-messages { padding: 16px 10px; }
        }
      `}</style>
    </div>
  );
}
