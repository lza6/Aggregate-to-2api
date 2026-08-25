/** 三态反馈组件：Skeleton（骨架屏）/ Empty（空态）/ ErrorRetry（错误+重试） */

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
        .fb-skeleton-wrapper {
          padding: 12px 0;
          width: 100%;
        }
        .fb-skeleton-shimmer {
          border-radius: var(--radius-md);
          margin-bottom: 12px;
          background: linear-gradient(
            90deg,
            var(--bg-subtle) 0%,
            var(--border-default) 50%,
            var(--bg-subtle) 100%
          );
          background-size: 200% 100%;
          animation: fb-shimmer 1.5s infinite ease-in-out;
        }
        @keyframes fb-shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
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
        .fb-empty-state {
          text-align: center;
          padding: 56px 24px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          margin: 0 auto;
        }
        .fb-empty-visual {
          position: relative;
          margin-bottom: 14px;
        }
        .empty-box-icon {
          font-size: 38px;
          opacity: 0.85;
          filter: grayscale(0.2);
        }
        .empty-sparkle {
          position: absolute;
          top: -6px;
          right: -8px;
          font-size: 16px;
          animation: fb-sparkle 2.5s infinite ease-in-out;
        }
        @keyframes fb-sparkle {
          0%, 100% { transform: scale(0.8) rotate(0deg); opacity: 0.5; }
          50% { transform: scale(1.15) rotate(15deg); opacity: 1; }
        }
        .fb-empty-title {
          font-size: 14.5px;
          font-weight: 600;
          color: var(--text-primary);
        }
        .fb-empty-sub {
          margin-top: 5px;
          font-size: 12.5px;
          color: var(--text-muted);
          max-width: 320px;
          line-height: 1.5;
        }
      `}</style>
    </div>
  );
}

export function ErrorRetry({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="fb-error-banner tf-card">
      <div className="fb-error-icon">⚠️</div>
      <div className="fb-error-content">
        <div className="fb-error-heading">数据获取异常</div>
        <div className="fb-error-msg" role="alert">{message}</div>
      </div>
      <button onClick={onRetry} className="tf-btn tf-btn-danger tf-btn-sm fb-error-btn">
        🔄 重新请求
      </button>
      <style>{`
        .fb-error-banner {
          display: flex;
          align-items: center;
          gap: 14px;
          padding: 16px 20px;
          background: var(--danger-bg);
          border-color: var(--danger-border);
          margin-bottom: 16px;
        }
        .fb-error-icon {
          font-size: 22px;
          flex-shrink: 0;
        }
        .fb-error-content {
          flex: 1;
          min-width: 0;
        }
        .fb-error-heading {
          font-size: 13.5px;
          font-weight: 600;
          color: var(--danger-text);
        }
        .fb-error-msg {
          font-size: 12px;
          color: var(--danger-text);
          opacity: 0.9;
          margin-top: 2px;
          word-break: break-all;
        }
        .fb-error-btn {
          flex-shrink: 0;
        }
      `}</style>
    </div>
  );
}
