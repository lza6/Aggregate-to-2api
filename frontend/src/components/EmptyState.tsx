/**
 * EmptyState — 空态插画 + CTA（P2-C1）
 *
 * 现有 `Feedback.Empty` 是基础空态（emoji + 文案 + 提示），不带行动按钮。
 * 本组件升级为可带 CTA 的空态：
 * - 插画区：保留 emoji 风格（与现有设计一致，不引入新插画库）
 * - 主文案 + 辅助提示
 * - 可选 CTA 按钮（如「刷新」「提交首个任务」）
 * - 可选次级链接
 *
 * 与 Feedback.Empty 共存：Feedback.Empty 用在简单内联场景；
 * EmptyState 用在整页/整区块空态，需要引导用户行动时。
 */
import type { ReactNode } from 'react';

export interface EmptyStateProps {
  /** 主图标 emoji（与现有风格一致，不引入新插画库） */
  icon?: string;
  /** 主标题 */
  text: string;
  /** 辅助说明 */
  hint?: string;
  /** 主 CTA 按钮文案 */
  ctaLabel?: string;
  /** 主 CTA 点击回调 */
  onCta?: () => void;
  /** 次级链接文案 */
  secondaryLabel?: string;
  /** 次级链接 href 或 onClick */
  onSecondary?: () => void;
  /** 次级链接跳转（用 react-router Link 时由外层包） */
  secondaryHref?: string;
  /** 自定义底部内容（如多个按钮） */
  children?: ReactNode;
}

export function EmptyState({
  icon = '📦',
  text,
  hint,
  ctaLabel,
  onCta,
  secondaryLabel,
  onSecondary,
  secondaryHref,
  children,
}: EmptyStateProps) {
  return (
    <div className="es-root" role="status">
      <div className="es-visual">
        <span className="es-sparkle" aria-hidden="true">✨</span>
        <div className="es-icon" aria-hidden="true">{icon}</div>
      </div>
      <div className="es-title">{text}</div>
      {hint && <div className="es-sub">{hint}</div>}
      {(ctaLabel || children || secondaryLabel) && (
        <div className="es-actions">
          {ctaLabel && onCta && (
            <button type="button" className="tf-btn tf-btn-primary tf-btn-sm" onClick={onCta}>
              {ctaLabel}
            </button>
          )}
          {secondaryLabel && (
            secondaryHref ? (
              <a className="tf-btn tf-btn-secondary tf-btn-sm" href={secondaryHref}>
                {secondaryLabel}
              </a>
            ) : onSecondary ? (
              <button type="button" className="tf-btn tf-btn-secondary tf-btn-sm" onClick={onSecondary}>
                {secondaryLabel}
              </button>
            ) : null
          )}
          {children}
        </div>
      )}
      <style>{`
        .es-root {
          text-align: center;
          padding: 64px 24px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          margin: 0 auto;
          gap: 8px;
        }
        .es-visual { position: relative; margin-bottom: 10px; }
        .es-icon {
          font-size: 44px;
          opacity: 0.88;
          filter: grayscale(0.15);
        }
        .es-sparkle {
          position: absolute;
          top: -8px;
          right: -10px;
          font-size: 18px;
          animation: es-sparkle 2.5s infinite ease-in-out;
        }
        @keyframes es-sparkle {
          0%, 100% { transform: scale(0.8) rotate(0deg); opacity: 0.5; }
          50% { transform: scale(1.15) rotate(15deg); opacity: 1; }
        }
        .es-title {
          font-size: 15px;
          font-weight: 600;
          color: var(--text-primary);
        }
        .es-sub {
          margin-top: 4px;
          font-size: 12.5px;
          color: var(--text-muted);
          max-width: 360px;
          line-height: 1.6;
        }
        .es-actions {
          margin-top: 16px;
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          justify-content: center;
        }
      `}</style>
    </div>
  );
}

export default EmptyState;
