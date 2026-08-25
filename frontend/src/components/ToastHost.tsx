import { useEffect, useState } from 'react';
import { onToast } from '../api';
import type { Toast } from '../api';

const MAX_TOASTS = 4;
const AUTO_DISMISS_MS = 3500;

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

  return (
    <div className="toast-host-container" aria-live="polite">
      {toasts.map(t => {
        const isSuccess = t.type === 'success';
        const isError = t.type === 'error';
        const icon = isSuccess ? '✅' : isError ? '❌' : 'ℹ️';
        const toastTypeClass = isSuccess ? 'toast-success' : isError ? 'toast-error' : 'toast-info';

        return (
          <div key={t.id} className={`toast-card-modern ${toastTypeClass}`}>
            <span className="toast-icon">{icon}</span>
            <span className="toast-msg">{t.message}</span>
            <button className="toast-close-btn" onClick={() => dismiss(t.id)} aria-label="关闭通知">
              ×
            </button>
          </div>
        );
      })}
      <style>{`
        .toast-host-container {
          position: fixed;
          top: 24px;
          right: 24px;
          z-index: 9999;
          display: flex;
          flex-direction: column;
          gap: 10px;
          max-width: 380px;
          pointer-events: none;
        }

        .toast-card-modern {
          pointer-events: auto;
          display: flex;
          align-items: center;
          gap: 12px;
          background: var(--bg-card);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-lg);
          padding: 12px 16px;
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
          box-shadow: var(--shadow-xl);
          backdrop-filter: blur(16px);
          animation: toast-slide-in 0.28s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .toast-success {
          border-left: 4px solid var(--success);
        }

        .toast-error {
          border-left: 4px solid var(--danger);
        }

        .toast-info {
          border-left: 4px solid var(--primary-500);
        }

        .toast-icon {
          font-size: 14px;
          flex-shrink: 0;
        }

        .toast-msg {
          flex: 1;
          line-height: 1.4;
          word-break: break-all;
        }

        .toast-close-btn {
          border: none;
          background: none;
          color: var(--text-muted);
          font-size: 18px;
          cursor: pointer;
          padding: 0 4px;
          line-height: 1;
          border-radius: 4px;
          transition: color var(--transition-fast);
        }

        .toast-close-btn:hover {
          color: var(--text-primary);
        }

        @keyframes toast-slide-in {
          from {
            opacity: 0;
            transform: translateX(24px) scale(0.96);
          }
          to {
            opacity: 1;
            transform: translateX(0) scale(1);
          }
        }
      `}</style>
    </div>
  );
}
