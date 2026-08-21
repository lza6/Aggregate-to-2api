/** 三态反馈组件：Skeleton（骨架）/ Empty（空态）/ ErrorRetry（错误+重试）。 */

export function Skeleton({ lines = 3, height = 16 }: { lines?: number; height?: number }) {
  return (
    <div className="fb-skeleton" aria-busy="true" aria-label="加载中">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="fb-skeleton-line"
          style={{ height, width: `${88 - i * (60 / Math.max(1, lines - 1) || 0)}%`, animationDelay: `${i * 0.12}s` }}
        />
      ))}
      <style>{`
        .fb-skeleton { padding: 8px 0; }
        .fb-skeleton-line { border-radius: 6px; margin-bottom: 10px; background: linear-gradient(90deg, #e8eaf1 25%, #f3f4f9 50%, #e8eaf1 75%); background-size: 200% 100%; animation: fb-shimmer 1.3s infinite; }
        @keyframes fb-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        @media (prefers-color-scheme: dark) {
          .fb-skeleton-line { background: linear-gradient(90deg, #232743 25%, #2d3155 50%, #232743 75%); background-size: 200% 100%; }
        }
      `}</style>
    </div>
  );
}

export function Empty({ text = '暂无数据', hint }: { text?: string; hint?: string }) {
  return (
    <div className="fb-empty">
      <div className="fb-empty-icon" aria-hidden>◌</div>
      <div className="fb-empty-text">{text}</div>
      {hint && <div className="fb-empty-hint">{hint}</div>}
      <style>{`
        .fb-empty { text-align: center; color: #6b7280; padding: 48px 20px; font-size: 13px; }
        .fb-empty-icon { font-size: 28px; color: #b6bccb; margin-bottom: 8px; }
        .fb-empty-hint { margin-top: 6px; font-size: 12px; color: #9aa1b2; }
      `}</style>
    </div>
  );
}

export function ErrorRetry({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="fb-error">
      <div className="fb-error-text" role="alert">加载失败：{message}</div>
      <button onClick={onRetry} className="fb-retry-btn">重试</button>
      <style>{`
        .fb-error { text-align: center; color: #b91c1c; padding: 40px 20px; font-size: 13px; }
        .fb-retry-btn { margin-top: 10px; padding: 6px 18px; border: none; border-radius: 8px; background: #ef4444; color: #fff; font-size: 13px; cursor: pointer; }
        .fb-retry-btn:hover { background: #dc2626; }
      `}</style>
    </div>
  );
}
