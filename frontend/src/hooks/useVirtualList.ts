import { useCallback, useRef, useState } from 'react';

export interface UseVirtualListOptions {
  /** 每条渲染高度（px），用于计算可见窗口。 */
  itemHeight: number;
  /** 视口高度（px）。 */
  containerHeight?: number;
  /** 视口外预渲染条数，减少滚到边界时的白屏。默认 8。 */
  overscan?: number;
}

export interface UseVirtualListResult<T> {
  /** 当前应渲染的切片（含 overscan）。 */
  visible: T[];
  /** 可见切片的起始索引（用以计算顶部 spacer）。 */
  startIndex: number;
  /** 可见切片的结束索引（不含）。 */
  endIndex: number;
  /** 绑定到滚动容器的 ref。 */
  containerRef: React.RefObject<HTMLDivElement | null>;
  /** 绑定到滚动容器的 onScroll。 */
  onScroll: () => void;
  /** 整表高度（items.length * itemHeight），用于撑出滚动条。 */
  totalHeight: number;
  itemHeight: number;
}

/**
 * 轻量虚拟滚动 hook（无第三方依赖）。
 *
 * 只渲染视口附近的一小段列表项，用 paddingTop/paddingBottom 撑出整表高度，
 * 从而在超长列表（日志 500+ 行、账号表格等）上大幅减少 DOM 节点。
 * 适用于固定行高（height 恒定、单行截断）的列表。
 */
export function useVirtualList<T>(items: T[], options: UseVirtualListOptions): UseVirtualListResult<T> {
  const { itemHeight, containerHeight = 600, overscan = 8 } = options;
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const totalCount = items.length;
  const totalHeight = totalCount * itemHeight;

  let startIndex = 0;
  let endIndex = 0;
  if (totalCount > 0 && itemHeight > 0) {
    startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
    // 避免滚动位置超出总数时切片为空
    startIndex = Math.min(startIndex, Math.max(0, totalCount - 1));
    endIndex = Math.min(totalCount, Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan);
  }
  const visible = totalCount === 0 ? [] : items.slice(startIndex, endIndex);

  const onScroll = useCallback(() => {
    const el = containerRef.current;
    if (el) setScrollTop(el.scrollTop);
  }, []);

  return { visible, startIndex, endIndex, containerRef, onScroll, totalHeight, itemHeight };
}
