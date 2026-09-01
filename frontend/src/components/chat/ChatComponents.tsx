import type { ProviderOption } from '../Feedback';
import type { ChatMessage, ChatGroupKey } from './chat-utils';
import { renderMarkdown, getUsageTotal, formatNumber } from './chat-utils';

interface ReasoningBlockProps {
  content?: string;
}

export function ReasoningBlock({ content }: ReasoningBlockProps) {
  if (!content) return null;
  return (
    <details className="chat-reasoning">
      <summary>🧠 思考过程 ({content.length} 字)</summary>
      <div className="chat-reasoning-content">{content}</div>
    </details>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
  backupProviders?: ProviderOption[];
  activeProvider?: string;
  onSwitchProvider?: (id: string) => void;
}

export function MessageBubble({ message, backupProviders, activeProvider, onSwitchProvider }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  return (
    <div className={`chat-message-row ${isUser ? 'is-user' : 'is-assistant'}`}>
      <div className={`chat-avatar ${isUser ? 'user-avatar' : 'assistant-avatar'}`}>{isUser ? '我' : 'AI'}</div>
      <div className={`chat-bubble ${message.error ? 'chat-bubble-error' : ''}`}>
        <div className="chat-role-label">{isUser ? '你' : '助手'}</div>
        {message.error ? (
          <div className="chat-inline-error" role="alert">
            {message.content}
            {(message.errorKind === 'rate_limit' || message.errorKind === 'provider_down') && onSwitchProvider && (backupProviders ?? []).length > 0 && (
              <div className="chat-error-action">
                <span className="chat-error-hint">{message.errorKind === 'provider_down' ? '上游宕机，切健康备用：' : '繁忙降级，切备用：'}</span>
                {(backupProviders ?? []).slice(0, 5).map(p => (
                  <button key={p.id} type="button" className="chat-provider-chip" onClick={() => onSwitchProvider(p.id)} disabled={p.id === activeProvider}>
                    {p.label}
                    {p.health === 'healthy' && <span className="chat-chip-dot ok" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <>
            {!isUser && <ReasoningBlock content={message.reasoning} />}
            <div className="chat-content" dangerouslySetInnerHTML={renderMarkdown(message.content || (message.reasoning ? '' : '正在思考…'))} />
            {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
              <div className="chat-tool-calls">🔧 工具调用：{message.toolCalls.join(' · ')}</div>
            )}
            {!isUser && (message.usage || message.durationMs !== undefined) && (
              <div className="chat-message-meta">
                {getUsageTotal(message.usage) !== undefined && `${formatNumber(getUsageTotal(message.usage) ?? 0)} tokens`}
                {getUsageTotal(message.usage) !== undefined && message.durationMs !== undefined && ' · '}
                {message.durationMs !== undefined && `${message.durationMs}ms`}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

interface ModelPickerProps {
  groups: { key: ChatGroupKey; label: string; models: import('../../api').ChatModelInfo[] }[];
  value: string;
  loading: boolean;
  hint?: string;
  onChange: (value: string) => void;
}

export function ModelPicker({ groups, value, loading, hint, onChange }: ModelPickerProps) {
  const flatCount = groups.reduce((acc, g) => acc + g.models.length, 0);
  return (
    <label className="chat-control-field">
      <span>模型</span>
      <select value={value} onChange={event => onChange(event.target.value)} disabled={loading || flatCount === 0}>
        {flatCount === 0 && <option value="">{loading ? '加载模型中…' : '暂无可用模型'}</option>}
        {groups.map(group => (
          <optgroup key={group.key} label={group.label}>
            {group.models.map(model => (
              <option key={model.id} value={model.id}>{model.display_name || model.id}</option>
            ))}
          </optgroup>
        ))}
      </select>
      {hint && <small>{hint}</small>}
    </label>
  );
}
