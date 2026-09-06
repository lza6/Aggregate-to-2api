/** P1-5: React 错误边界 —— 任一页面渲染期抛异常不再卸载整棵树（白屏）。

设计要点（对照 CLAUDE.md 反伪实现 / 甲方 P1-5 验收）：
- 类组件：getDerivedStateFromError 兜底重渲染 + componentDidCatch 侧效应（上报 + 钩子）。
- 上报：复用现有 FrontendError 遥测 `reportFrontendError`（POST /v1/errors/frontend），
  新 code 命名空间 FE.BOUNDARY，与 main.tsx 的 window.onerror/unhandledrejection 的
  FE.RUNTIME / FE.PROMISE 区分，便于在 error_tracker 聚合出「UI 崩溃」类别。
- 隔离：根边界包住 <Layout>；每个懒加载页面再包一层嵌套边界 —— 单页抛错不连坐整站。
- 可定制：fallback 渲染函数 `(error, onReset) => ReactNode`，onError 回调可用于独立审查。
- 重试：reset 会重新渲染 children（若仍抛错则再次捕获）；「回到总览」用 useNavigate 跳 "/"。
 */
import { Component, useState, type ReactNode, type ErrorInfo } from 'react';
import { useNavigate } from 'react-router-dom';
import { reportFrontendError } from '../lib/telemetry';

export type FallbackRenderer = (error: Error, onReset: () => void) => ReactNode;

interface ErrorBoundaryProps {
  children: ReactNode;
  /** 自定义 fallback；缺省用内置 fallback（含重试/回到总览）。 */
  fallback?: FallbackRenderer;
  /** 错误捕获回调（componentDidCatch 侧），不改变默认上报行为。 */
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** 内置 fallback：警告横幅 + 「重试 / 回到总览 / 复制错误」按钮（依赖 Router 上下文）。
 * P2-C1 增强：增加「复制错误栈」按钮（便于用户反馈 bug），重试计数显示（多次重试仍失败时提示）。
 */
function DefaultFallback({ error, onReset }: { error: Error; onReset: () => void }) {
  const navigate = useNavigate();
  const goHome = () => navigate('/', { replace: true });
  const msg = error?.message || '未知渲染错误';
  const stack = error?.stack || '';
  const [retryCount, setRetryCount] = useState(0);
  const handleReset = () => {
    setRetryCount(c => c + 1);
    onReset();
  };
  const copyStack = async () => {
    try {
      const text = `${msg}\n\n${stack}`;
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
    } catch {
      /* 静默 */
    }
  };
  return (
    <div className="eb-fallback tf-card" role="alert">
      <div className="eb-fallback-icon">🧯</div>
      <div className="eb-fallback-body">
        <div className="eb-fallback-title">页面渲染异常</div>
        <div className="eb-fallback-msg">{msg}</div>
        <div className="eb-fallback-hint">
          已自动上报该错误，任务队列与其它页面不受影响。
          {retryCount >= 2 && ' 多次重试仍失败，建议刷新整页或回到总览。'}
        </div>
        {stack && (
          <details className="eb-fallback-details">
            <summary>查看错误栈</summary>
            {/* 去掉首行（与 msg 重复的错误消息），仅展示调用栈 */}
            <pre className="eb-fallback-stack">{stack.split('\n').slice(1).join('\n').trim() || stack}</pre>
          </details>
        )}
      </div>
      <div className="eb-fallback-actions">
        <button type="button" className="tf-btn tf-btn-primary" onClick={handleReset}>🔄 重试</button>
        <button type="button" className="tf-btn tf-btn-secondary" onClick={copyStack} title="复制错误栈以便反馈">📋 复制错误</button>
        <button type="button" className="tf-btn tf-btn-secondary" onClick={goHome}>🏠 回到总览</button>
      </div>
      <style>{`
        .eb-fallback { display: flex; align-items: flex-start; gap: 14px; padding: 24px 28px; background: var(--danger-bg); border-color: var(--danger-border); margin: 8px 0; flex-wrap: wrap; }
        .eb-fallback-icon { font-size: 26px; flex-shrink: 0; }
        .eb-fallback-body { flex: 1; min-width: 200px; }
        .eb-fallback-title { font-size: 15px; font-weight: 700; color: var(--danger-text); letter-spacing: -0.01em; }
        .eb-fallback-msg { font-size: 12.5px; color: var(--danger-text); opacity: 0.92; margin-top: 4px; word-break: break-word; }
        .eb-fallback-hint { font-size: 11.5px; color: var(--danger-text); opacity: 0.75; margin-top: 6px; }
        .eb-fallback-details { margin-top: 10px; }
        .eb-fallback-details summary { cursor: pointer; font-size: 11.5px; color: var(--danger-text); opacity: 0.8; user-select: none; }
        .eb-fallback-stack { margin: 8px 0 0; padding: 10px 12px; background: rgba(0,0,0,0.18); border-radius: 6px; font-size: 11px; font-family: ui-monospace, monospace; color: var(--danger-text); overflow-x: auto; max-height: 180px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
        .eb-fallback-actions { display: flex; gap: 8px; flex-shrink: 0; align-items: center; }
        @media (max-width: 520px) { .eb-fallback-actions { width: 100%; } .eb-fallback-actions .tf-btn { flex: 1; justify-content: center; } }
      `}</style>
    </div>
  );
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 默认上报到后端 frontend error tracker（遥测自身必须静默，不能成为新错误源）。
    try {
      reportFrontendError(
        'FE.BOUNDARY',
        error?.message ?? '未知渲染错误',
        [error?.stack, info?.componentStack].filter(Boolean).join('\n\n'),
      );
    } catch {
      /* 遥测失败不影响用户 */
    }
    this.props.onError?.(error, info);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      return this.props.fallback
        ? this.props.fallback(error, this.reset)
        : <DefaultFallback error={error} onReset={this.reset} />;
    }
    return this.props.children;
  }
}
