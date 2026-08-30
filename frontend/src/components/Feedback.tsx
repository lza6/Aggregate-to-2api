/** 三态反馈组件：Skeleton（骨架屏）/ Empty（空态）/ ErrorRetry（错误+重试）。
 *
 * D1（动作化错误提示）：ErrorRetry 从「文案」升级为「行动」——
 *  - 429 限流 → 内联「切备用 provider」按钮（调 onSwitchProvider 回调）；
 *  - 401/未配置 Key → 自动生成 curl 命令 + 一键复制（navigator.clipboard + execCommand 兜底）；
 *  - 502/provider down → 列出可用备用 provider，一键切换。
 */
import type { ReactNode } from 'react';

export function Skeleton({ lines = 3, height = 16 }: { lines?: number; height?: number }) {
  return (
    <div className="fb-skeleton-wrapper" aria-busy="true" aria-label="正在加载内容">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="fb-skeleton-shimmer"
          style={{
            height,
            width: `${92 - i * (50 / Math.max(1, lines - 1) || 0)}%`,
            animationDelay: `${i * 0.1}s`,
          }}
        />
      ))}
      <style>{`
        .fb-skeleton-wrapper { padding: 12px 0; width: 100%; }
        .fb-skeleton-shimmer {
          border-radius: var(--radius-md); margin-bottom: 12px;
          background: linear-gradient(90deg, var(--bg-subtle) 0%, var(--border-default) 50%, var(--bg-subtle) 100%);
          background-size: 200% 100%; animation: fb-shimmer 1.5s infinite ease-in-out;
        }
        @keyframes fb-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
      `}</style>
    </div>
  );
}

export function Empty({ text = '暂无数据', hint }: { text?: string; hint?: string }) {
  return (
    <div className="fb-empty-state">
      <div className="fb-empty-visual">
        <span className="empty-sparkle">✨</span>
        <div className="empty-box-icon">📦</div>
      </div>
      <div className="fb-empty-title">{text}</div>
      {hint && <div className="fb-empty-sub">{hint}</div>}
      <style>{`
        .fb-empty-state { text-align: center; padding: 56px 24px; display: flex; flex-direction: column; align-items: center; justify-content: center; margin: 0 auto; }
        .fb-empty-visual { position: relative; margin-bottom: 14px; }
        .empty-box-icon { font-size: 38px; opacity: 0.85; filter: grayscale(0.2); }
        .empty-sparkle { position: absolute; top: -6px; right: -8px; font-size: 16px; animation: fb-sparkle 2.5s infinite ease-in-out; }
        @keyframes fb-sparkle { 0%, 100% { transform: scale(0.8) rotate(0deg); opacity: 0.5; } 50% { transform: scale(1.15) rotate(15deg); opacity: 1; } }
        .fb-empty-title { font-size: 14.5px; font-weight: 600; color: var(--text-primary); }
        .fb-empty-sub { margin-top: 5px; font-size: 12.5px; color: var(--text-muted); max-width: 320px; line-height: 1.5; }
      `}</style>
    </div>
  );
}

/** D1: 错误类别推断 —— 根据原始错误文本归类，决定渲染哪种行动区。 */
export type ErrorKind = 'rate_limit' | 'auth' | 'provider_down' | 'generic';

export function classifyError(raw: unknown): ErrorKind {
  const msg = (typeof raw === 'string' ? raw : raw instanceof Error ? raw.message : String(raw ?? '')).toLowerCase();
  if (msg.includes('429') || msg.includes('rate') || msg.includes('limit') || msg.includes('限流') || msg.includes('繁忙') || msg.includes('queue_full') || msg.includes('queue full')) {
    return 'rate_limit';
  }
  if (msg.includes('401') || msg.includes('unauthorized') || msg.includes('api key') || msg.includes('未授权') || msg.includes('未配置')) {
    return 'auth';
  }
  if (msg.includes('502') || msg.includes('503') || msg.includes('504') || (msg.includes('provider') && msg.includes('down')) || (msg.includes('上游') && msg.includes('不可用'))) {
    return 'provider_down';
  }
  return 'generic';
}

/** D1-2: 一键复制 —— navigator.clipboard 优先，HTTP/非安全上下文降级 execCommand。 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // 走兜底
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export interface ProviderOption {
  id: string;
  label: string;
  health?: string;
}

interface ErrorRetryProps {
  message: string;
  onRetry: () => void;
  /** D1: 备用 provider 列表（429/502 时供一键切换）。 */
  availableProviders?: ProviderOption[];
  /** D1: 当前已选 provider id（避免列出自己）。 */
  activeProvider?: string;
  /** D1: 切换到某备用 provider。 */
  onSwitchProvider?: (id: string) => void;
}

export function ErrorRetry({ message, onRetry, availableProviders, activeProvider, onSwitchProvider }: ErrorRetryProps) {
  const kind = classifyError(message);
  const isKeyError = kind === 'auth';
  const isRateLimit = kind === 'rate_limit';
  const isProviderDown = kind === 'provider_down';

  const displayHeading = isKeyError ? 'API Key 鉴权失败或未配置' : (isRateLimit ? '服务繁忙或触发限流' : (isProviderDown ? '上游提供商不可用' : '数据获取异常'));
  const displayMsg = isRateLimit
    ? '当前提供商繁忙，已为您自动切换至备用引擎'
    : (isKeyError ? '检测到未配置有效 API Key，请携带 Authorization 凭据访问。' : message);

  const sampleCurl = `curl -X GET ${window.location.origin}/v1/stats \\
  -H "Authorization: Bearer <YOUR_API_KEY>"`;

  const backupProviders = (availableProviders ?? [])
    .filter(p => p.id !== activeProvider && p.health !== 'down');

  return (
    <div className="fb-error-banner tf-card" role="alert">
      <div className="fb-error-icon">{isKeyError ? '🔑' : '⚠️'}</div>
      <div className="fb-error-content">
        <div className="fb-error-heading">{displayHeading}</div>
        <div className="fb-error-msg">{displayMsg}</div>

        {isRateLimit && onSwitchProvider && backupProviders.length > 0 && (
          <div className="fb-action-block">
            <div className="fb-action-label">⚠️ 繁忙降级 · 可一键切到备用引擎：</div>
            <div className="fb-provider-chips">
              {backupProviders.slice(0, 6).map(p => (
                <button key={p.id} type="button" className="fb-provider-chip" onClick={() => onSwitchProvider(p.id)} title={p.health ? `健康状态：${p.health}` : undefined}>
                  {p.label}
                  {p.health === 'healthy' && <span className="fb-chip-dot ok" />}
                  {p.health === 'degraded' && <span className="fb-chip-dot warn" />}
                </button>
              ))}
            </div>
          </div>
        )}

        {isProviderDown && onSwitchProvider && backupProviders.length > 0 && (
          <div className="fb-action-block">
            <div className="fb-action-label">🔌 上游宕机 · 切到健康备用提供商：</div>
            <div className="fb-provider-chips">
              {backupProviders.filter(p => p.health === 'healthy').slice(0, 6).map(p => (
                <button key={p.id} type="button" className="fb-provider-chip primary" onClick={() => onSwitchProvider(p.id)}>
                  {p.label} <span className="fb-chip-dot ok" />
                </button>
              ))}
            </div>
          </div>
        )}

        {isKeyError && (
          <div className="fb-action-block">
            <div className="fb-action-label">📋 一键复制调用命令示例：</div>
            <pre className="fb-action-code">{sampleCurl}</pre>
            <CopyButton text={sampleCurl} />
          </div>
        )}
      </div>
      <button onClick={onRetry} className="tf-btn tf-btn-danger tf-btn-sm fb-error-btn">
        🔄 重新请求
      </button>
      <style>{`
        .fb-error-banner { display: flex; align-items: center; gap: 14px; padding: 16px 20px; background: var(--danger-bg); border-color: var(--danger-border); margin-bottom: 16px; }
        .fb-error-icon { font-size: 22px; flex-shrink: 0; }
        .fb-error-content { flex: 1; min-width: 0; }
        .fb-error-heading { font-size: 13.5px; font-weight: 600; color: var(--danger-text); }
        .fb-error-msg { font-size: 12px; color: var(--danger-text); opacity: 0.9; margin-top: 2px; word-break: break-all; }
        .fb-action-block { margin-top: 10px; }
        .fb-action-label { font-size: 11.5px; color: var(--danger-text); opacity: 0.85; margin-bottom: 6px; }
        .fb-provider-chips { display: flex; flex-wrap: wrap; gap: 8px; }
        .fb-provider-chip { display: inline-flex; align-items: center; gap: 6px; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-default); padding: 6px 12px; border-radius: var(--radius-full); font-size: 12px; cursor: pointer; transition: border-color 0.15s ease, background 0.15s ease; }
        .fb-provider-chip:hover { border-color: var(--primary-500); background: var(--primary-50); }
        .fb-provider-chip.primary { border-color: var(--success); color: var(--success-text); }
        .fb-chip-dot { width: 6px; height: 6px; border-radius: 50%; }
        .fb-chip-dot.ok { background: var(--success); box-shadow: 0 0 6px var(--success); }
        .fb-chip-dot.warn { background: var(--warning); }
        .fb-action-code { margin: 0 0 8px 0; padding: 8px 10px; background: rgba(0,0,0,0.1); border-radius: 6px; font-size: 11px; font-family: ui-monospace, monospace; overflow-x: auto; color: inherit; }
        .fb-copy-btn { background: var(--danger-border); color: var(--danger-text); border: 1px solid var(--danger-border); padding: 4px 10px; border-radius: 6px; font-size: 11px; cursor: pointer; }
        .fb-copy-btn:hover { background: var(--danger-bg); }
        .fb-error-btn { flex-shrink: 0; }
      `}</style>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const handle = async () => {
    const ok = await copyToClipboard(text);
    const { notify } = await import('../api');
    notify(ok ? '📋 已复制到剪贴板' : '复制失败，请手动复制', ok ? 'success' : 'error');
  };
  return (
    <button type="button" className="fb-copy-btn" onClick={() => void handle()}>📋 一键复制</button>
  );
}

/** D1: 内联动作化错误块 —— 用于 ChatPlayground/Generate 卡片内联（非全屏 banner）。 */
export interface ActionableInlineProps {
  kind: ErrorKind;
  message: string;
  availableProviders?: ProviderOption[];
  activeProvider?: string;
  onSwitchProvider?: (id: string) => void;
  onRetry?: () => void;
}

export function ActionableInline({ kind, message, availableProviders, activeProvider, onSwitchProvider, onRetry }: ActionableInlineProps): ReactNode {
  const backupProviders = (availableProviders ?? [])
    .filter(p => p.id !== activeProvider && p.health !== 'down');
  const showSwitch = (kind === 'rate_limit' || kind === 'provider_down') && onSwitchProvider && backupProviders.length > 0;
  return (
    <div className="ai-inline-action">
      <div className="ai-inline-msg">{message}</div>
      {showSwitch && (
        <div className="ai-provider-row">
          <span className="ai-switch-hint">{kind === 'provider_down' ? '切健康备用：' : '切备用：'}</span>
          {backupProviders.slice(0, 5).map(p => (
            <button key={p.id} type="button" className="ai-provider-chip" onClick={() => onSwitchProvider!(p.id)}>
              {p.label}
              {p.health === 'healthy' && <span className="ai-dot ok" />}
            </button>
          ))}
        </div>
      )}
      {onRetry && (
        <button type="button" className="ai-retry-btn" onClick={onRetry}>🔄 重试</button>
      )}
      <style>{`
        .ai-inline-action { display: flex; flex-direction: column; gap: 8px; padding: 8px 4px 0; }
        .ai-inline-msg { font-size: 12px; }
        .ai-provider-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
        .ai-switch-hint { font-size: 11px; color: var(--text-muted); }
        .ai-provider-chip { display: inline-flex; align-items: center; gap: 5px; background: var(--bg-subtle); color: var(--text-primary); border: 1px solid var(--border-default); padding: 4px 10px; border-radius: var(--radius-full); font-size: 11.5px; cursor: pointer; }
        .ai-provider-chip:hover { border-color: var(--primary-500); }
        .ai-dot { width: 5px; height: 5px; border-radius: 50%; }
        .ai-dot.ok { background: var(--success); box-shadow: 0 0 5px var(--success); }
        .ai-retry-btn { align-self: flex-start; background: var(--bg-subtle); color: var(--text-primary); border: 1px solid var(--border-default); padding: 4px 12px; border-radius: 6px; font-size: 11.5px; cursor: pointer; }
      `}</style>
    </div>
  );
}
