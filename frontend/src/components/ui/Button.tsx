/**
 * Button — 页面级统一按钮组件（P1-13）
 *
 * 定位：管理面板提交路径的统一按钮抽象，解决「部分提交按钮无 loading / disabled
 * 防重复反馈」问题；本项目已有全局 tf-btn 视觉体系（index.css）与 a11y 地基
 * （focus-visible / reduced-motion / 44px 触控目标），此处不再新建全局样式，
 * 仅复用现有 tf-btn-* 类并配套横向 spinner。
 *
 * 行为：
 * - `loading`：渲染 spinner + aria-busy=true；同时置 disabled（防重复点击），
 *   点击不触发 onClick。文案应自行替换（如 "提交中…"），组件不覆盖 children。
 * - `disabled`：原生禁用，点击不触发 onClick。
 * - 保留原生 `<button>` 语义与类名透传，未引入任何第三方依赖。
 */
import { type ButtonHTMLAttributes, type ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: 'tf-btn-primary',
  secondary: 'tf-btn-secondary',
  ghost: 'tf-btn-ghost',
  danger: 'tf-btn-danger',
};

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: 'tf-btn-sm',
  md: '',
  lg: 'tf-btn-lg',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** 提交中态：显示 spinner + aria-busy，同时置 disabled 防重复点击 */
  loading?: boolean;
  /** asChild：占位选项，始终渲染原生 <button>（可访问性优先），调用方传入的 onLoadingText 等由 children 自行处理 */
  asChild?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  asChild = false,
  className,
  children,
  ...rest
}: ButtonProps) {
  const classes = [
    'tf-btn',
    VARIANT_CLASS[variant],
    SIZE_CLASS[size],
    loading ? 'tf-btn-loading' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      className={classes}
      aria-busy={loading ? 'true' : undefined}
      disabled={rest.disabled || loading}
      {...rest}
    >
      {loading && <span className="tf-btn-spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

export default Button;