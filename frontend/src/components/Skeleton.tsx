/**
 * Skeleton — 骨架屏组件（P2-C1）
 *
 * 现有 `Feedback.tsx` 中的 Skeleton 是基础 shimmer 行，适合文本块；
 * 本组件提供结构化骨架屏（表格行 / 卡片 / 列表项），让列表页加载态
 * 有"内容形状"的占位，而非泛化 spinner，降低用户感知等待。
 *
 * 设计：
 * - 三种 variant：`rows`（表格行）/ `cards`（卡片网格）/ `lines`（文本行，等价旧 Skeleton）
 * - 复用全局 shimmer 动画（与 Feedback.Skeleton 同一 keyframes，避免双份）
 * - aria-busy + aria-label，屏幕阅读器宣告"加载中"
 * - 无第三方依赖，纯 CSS shimmer
 */
import type { CSSProperties } from 'react';

export type SkeletonVariant = 'rows' | 'cards' | 'lines';

export interface SkeletonProps {
  variant?: SkeletonVariant;
  /** variant=rows / lines 时的行数 */
  count?: number;
  /** variant=cards 时的卡片数 */
  cards?: number;
  /** 单行高度 px（仅 lines / rows 生效） */
  height?: number;
  /** 卡片高度 px（仅 cards 生效） */
  cardHeight?: number;
  /** 表格列数（variant=rows 时用以模拟列分布） */
  columns?: number;
  className?: string;
  style?: CSSProperties;
}

/** 单行 shimmer 基础块 */
function ShimmerBar({ height, widthPct, delay }: { height: number; widthPct: number; delay: number }) {
  return (
    <div
      className="sk-bar"
      style={{ height, width: `${widthPct}%`, animationDelay: `${delay}s` }}
    />
  );
}

/** 表格行骨架（模拟列分布：短-中-长-中-短） */
function RowSkeleton({ columns, height }: { columns: number; height: number }) {
  // 预设列宽模式，循环取用，避免每行完全相同
  const PATTERNS = [
    [18, 32, 50, 24, 16],
    [22, 28, 60, 20, 14],
    [16, 40, 38, 30, 18],
  ];
  const cols = Math.max(1, columns);
  return (
    <div className="sk-row">
      {Array.from({ length: cols }, (_, i) => {
        const pattern = PATTERNS[i % PATTERNS.length];
        const w = pattern[i % pattern.length];
        return <ShimmerBar key={i} height={height} widthPct={w} delay={i * 0.08} />;
      })}
      <style>{`
        .sk-row { display: flex; gap: 16px; align-items: center; padding: 12px 4px; border-bottom: 1px solid var(--border-subtle, rgba(0,0,0,0.04)); }
      `}</style>
    </div>
  );
}

/** 卡片骨架 */
function CardSkeleton({ height }: { height: number }) {
  return (
    <div className="sk-card" style={{ height }}>
      <div className="sk-card-head">
        <ShimmerBar height={28} widthPct={45} delay={0} />
        <div className="sk-card-pill" />
      </div>
      <div className="sk-card-body">
        <ShimmerBar height={14} widthPct={70} delay={0.1} />
        <ShimmerBar height={14} widthPct={55} delay={0.15} />
        <ShimmerBar height={14} widthPct={65} delay={0.2} />
      </div>
      <div className="sk-card-foot">
        <ShimmerBar height={18} widthPct={30} delay={0.25} />
        <ShimmerBar height={18} widthPct={20} delay={0.3} />
      </div>
      <style>{`
        .sk-card { padding: 18px 20px; display: flex; flex-direction: column; gap: 14px; background: var(--bg-card); border: 1px solid var(--border-default); border-radius: var(--radius-md); }
        .sk-card-head { display: flex; align-items: center; justify-content: space-between; }
        .sk-card-pill { width: 56px; height: 18px; border-radius: var(--radius-full); background: var(--bg-subtle); }
        .sk-card-body { display: flex; flex-direction: column; gap: 8px; }
        .sk-card-foot { display: flex; gap: 12px; margin-top: 4px; }
      `}</style>
    </div>
  );
}

export function Skeleton({
  variant = 'lines',
  count = 5,
  cards = 3,
  height = 16,
  cardHeight = 160,
  columns = 5,
  className,
  style,
}: SkeletonProps) {
  return (
    <div
      className={`sk-wrapper ${className ?? ''}`}
      role="status"
      aria-busy="true"
      aria-label="内容加载中"
      style={style}
    >
      {variant === 'lines' && (
        Array.from({ length: count }, (_, i) => (
          <ShimmerBar
            key={i}
            height={height}
            widthPct={Math.max(40, 92 - i * (50 / Math.max(1, count - 1) || 0))}
            delay={i * 0.1}
          />
        ))
      )}
      {variant === 'rows' && (
        <div className="sk-rows-wrap">
          {Array.from({ length: count }, (_, i) => (
            <RowSkeleton key={i} columns={columns} height={height} />
          ))}
          <style>{`
            .sk-rows-wrap { padding: 4px 0; }
          `}</style>
        </div>
      )}
      {variant === 'cards' && (
        <div className="sk-cards-wrap">
          {Array.from({ length: cards }, (_, i) => (
            <CardSkeleton key={i} height={cardHeight} />
          ))}
          <style>{`
            .sk-cards-wrap { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
          `}</style>
        </div>
      )}
      <style>{`
        .sk-wrapper { padding: 12px 0; width: 100%; }
        .sk-bar {
          border-radius: var(--radius-md);
          margin-bottom: 12px;
          background: linear-gradient(90deg, var(--bg-subtle) 0%, var(--border-default) 50%, var(--bg-subtle) 100%);
          background-size: 200% 100%;
          animation: sk-shimmer 1.5s infinite ease-in-out;
        }
        @keyframes sk-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
      `}</style>
    </div>
  );
}

export default Skeleton;
