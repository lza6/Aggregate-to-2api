import { useEffect, useState } from 'react';
import { onToast } from '../api';
import type { Toast } from '../api';

const MAX_TOASTS = 4;
const AUTO_DISMISS_MS = 3000;

/** 全局 Toast 容器：挂载于 Layout，监听 api.ts notify() 广播。 */
export function ToastHost() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    return onToast((t: Toast) => {
      setToasts(prev => [...prev.slice(-(MAX_TOASTS - 1)), t]);
    });
  }, []);

  useEffect(() => {
    if (!toasts.length) return;
    const timer = setTimeout(() => {
      setToasts(prev => prev.slice(1));
    }, AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [toasts]);

  const dismiss = (id: number) => setToasts(prev => prev.filter(t => t.id !== id));

  if (!toasts.length) return null;

  const color = (type: Toast['type']) =>
    type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6';

  return (
    <div className="toast-host" aria-live="polite">
      {toasts.map(t => (
        <div key={t.id} className="toast-item" style={{ borderLeftColor: color(t.type) }}>
          <span className="toast-msg">{t.message}</span>
          <button className="toast-close" onClick={() => dismiss(t.id)} aria-label="关闭">×</button>
        </div>
      ))}
      <style>{`
        .toast-host { position: fixed; top: 16px; right: 16px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; max-width: 340px; }
        .toast-item { display: flex; align-items: center; gap: 10px; background: #fff; border: 1px solid #d1d5e0; border-left: 4px solid #3b82f6; border-radius: 10px; padding: 10px 12px; font-size: 13px; color: #1f2430; box-shadow: 0 4px 16px rgba(10,14,30,.10); animation: toast-in .22s ease-out; }
        .toast-msg { flex: 1; word-break: break-all; }
        .toast-close { border: none; background: none; color: #9aa1b2; font-size: 16px; cursor: pointer; padding: 0 2px; line-height: 1; }
        .toast-close:hover { color: #1f2430; }
        @keyframes toast-in { from { opacity: 0; transform: translateX(12px); } to { opacity: 1; transform: none; } }
        @media (prefers-color-scheme: dark) {
          .toast-item { background: #1e2132; border-color: #2d3050; color: #e1e4ed; }
          .toast-close:hover { color: #e1e4ed; }
        }
      `}</style>
    </div>
  );
}
