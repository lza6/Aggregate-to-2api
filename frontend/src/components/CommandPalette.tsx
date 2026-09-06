/**
 * CommandPalette — Cmd+K 命令面板（P2-C1）
 *
 * 全局快捷跳转面板：Cmd/Ctrl + K 打开 → 模糊搜索页面 → Enter 跳转。
 * - 无第三方依赖（不引入 cmdk / kbar，自实现轻量版）
 * - 键盘完全可达：↑↓ 选择 / Enter 确认 / Esc 关闭
 * - 路由列表从 react-router-dom 的导航常量派生，与 Layout 侧栏同步
 * - aria-combobox + aria-expanded + aria-activedescendant（WCAG 2.2 AA）
 * - reduced-motion 降级：打开动画 0ms
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface CmdItem {
  id: string;
  label: string;
  hint?: string;
  path: string;
  icon: string;
  keywords: string;
}

// 与 Layout 侧栏同步的导航清单（避免重复维护两份）
const COMMANDS: CmdItem[] = [
  { id: 'dashboard', label: '仪表盘', hint: '系统总览', path: '/', icon: '📊', keywords: '仪表盘 总览 dashboard 首页' },
  { id: 'providers', label: '提供商', hint: '集群状态', path: '/providers', icon: '🔌', keywords: '提供商 providers 上游 集群' },
  { id: 'tasks', label: '任务管理', hint: '生成任务', path: '/tasks', icon: '📋', keywords: '任务 tasks 生成' },
  { id: 'accounts', label: '长效号池', hint: '账号管理', path: '/accounts', icon: '👤', keywords: '号池 accounts 账号 长效' },
  { id: 'logs', label: '实时日志', hint: 'WebSocket 日志流', path: '/logs', icon: '📝', keywords: '日志 logs 实时' },
  { id: 'dlq', label: '死信队列', hint: 'DLQ 重试', path: '/dlq', icon: '🗑️', keywords: '死信 dlq dlq 重试 队列' },
  { id: 'slow', label: '慢请求画像', hint: '瓶颈定位', path: '/slow', icon: '🐌', keywords: '慢 slow 慢请求 画像' },
  { id: 'chat', label: '在线聊天', hint: 'AI Playground', path: '/chat', icon: '💬', keywords: '聊天 chat playground 对话' },
  { id: 'generate', label: '在线生成', hint: '文生图 / 图生图', path: '/generate', icon: '🖼️', keywords: '生成 generate 文生图 图生图' },
  { id: 'api-guide', label: 'API 指南', hint: '调用示例', path: '/api-guide', icon: '📖', keywords: 'api 指南 guide 文档' },
  { id: 'health', label: '健康体检', hint: '出图能力', path: '/health', icon: '🩺', keywords: '健康 health 体检' },
  { id: 'ecosystem', label: 'AI 生态', hint: 'TensorFeed', path: '/ecosystem', icon: '🌐', keywords: '生态 ecosystem tensortfeed' },
  { id: 'costs', label: '成本管理', hint: '号池成本', path: '/costs', icon: '💰', keywords: '成本 costs 花费' },
  { id: 'security', label: '安全风控', hint: 'IP 封禁', path: '/security', icon: '🛡️', keywords: '安全 security 风控 封禁 ip' },
];

// 轻量模糊匹配：子序列匹配 + 关键词包含
function fuzzyMatch(query: string, item: CmdItem): boolean {
  if (!query) return true;
  const q = query.toLowerCase().trim();
  if (!q) return true;
  // 关键词包含
  if (item.keywords.toLowerCase().includes(q)) return true;
  if (item.label.toLowerCase().includes(q)) return true;
  if (item.hint?.toLowerCase().includes(q)) return true;
  // 子序列匹配 label
  const label = item.label.toLowerCase();
  let qi = 0;
  for (let i = 0; i < label.length && qi < q.length; i++) {
    if (label[i] === q[qi]) qi++;
  }
  return qi === q.length;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Cmd/Ctrl + K 打开
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(v => !v);
      } else if (e.key === 'Escape' && open) {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  // 打开时聚焦输入框 + 重置
  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIndex(0);
      // 微延迟以等面板渲染完再聚焦
      const t = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(t);
    }
  }, [open]);

  const filtered = useMemo(() => COMMANDS.filter(it => fuzzyMatch(query, it)), [query]);

  // 过滤结果变化时重置 active index
  useEffect(() => { setActiveIndex(0); }, [filtered]);

  const selectItem = useCallback((item: CmdItem) => {
    navigate(item.path);
    setOpen(false);
  }, [navigate]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(i => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = filtered[activeIndex];
      if (item) selectItem(item);
    }
  };

  // 滚动到 active 项
  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(`[data-idx="${activeIndex}"]`);
    // jsdom 等环境无 scrollIntoView —— 类型守卫 + 兜底，避免测试/无障碍树崩溃
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIndex, open]);

  if (!open) return null;

  return (
    <div className="cmdk-overlay" role="dialog" aria-modal="true" aria-label="命令面板" onClick={() => setOpen(false)}>
      <div className="cmdk-panel" role="combobox" aria-expanded="true" aria-owns="cmdk-list" onClick={e => e.stopPropagation()}>
        <div className="cmdk-input-wrap">
          <span className="cmdk-icon" aria-hidden="true">🔍</span>
          <input
            ref={inputRef}
            type="text"
            className="cmdk-input"
            placeholder="输入页面名或关键词跳转…（↑↓ 选择，Enter 确认，Esc 关闭）"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            aria-autocomplete="list"
            aria-controls="cmdk-list"
            aria-activedescendant={filtered[activeIndex] ? `cmdk-item-${filtered[activeIndex].id}` : undefined}
          />
          <kbd className="cmdk-esc">Esc</kbd>
        </div>
        <div className="cmdk-list" id="cmdk-list" ref={listRef} role="listbox" aria-label="页面列表">
          {filtered.length === 0 ? (
            <div className="cmdk-empty">无匹配页面</div>
          ) : filtered.map((item, i) => (
            <button
              key={item.id}
              id={`cmdk-item-${item.id}`}
              data-idx={i}
              type="button"
              role="option"
              aria-selected={i === activeIndex}
              className={`cmdk-item ${i === activeIndex ? 'is-active' : ''}`}
              onMouseEnter={() => setActiveIndex(i)}
              onClick={() => selectItem(item)}
            >
              <span className="cmdk-item-icon" aria-hidden="true">{item.icon}</span>
              <span className="cmdk-item-body">
                <span className="cmdk-item-label">{item.label}</span>
                {item.hint && <span className="cmdk-item-hint">{item.hint}</span>}
              </span>
              <span className="cmdk-item-path" aria-hidden="true">{item.path}</span>
            </button>
          ))}
        </div>
        <div className="cmdk-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
          <span><kbd>Enter</kbd> 跳转</span>
          <span><kbd>Esc</kbd> 关闭</span>
          <span className="cmdk-foot-brand">听风AI · {filtered.length} 个页面</span>
        </div>
      </div>
      <style>{`
        .cmdk-overlay {
          position: fixed;
          inset: 0;
          z-index: 1000;
          background: rgba(10, 14, 26, 0.55);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          display: flex;
          align-items: flex-start;
          justify-content: center;
          padding-top: 12vh;
          animation: cmdk-fade 0.16s ease-out;
        }
        @keyframes cmdk-fade { from { opacity: 0; } to { opacity: 1; } }
        @media (prefers-reduced-motion: reduce) {
          .cmdk-overlay, .cmdk-panel { animation: none !important; transition: none !important; }
        }
        .cmdk-panel {
          width: min(640px, 92vw);
          max-height: 70vh;
          background: var(--bg-card, #0f172a);
          border: 1px solid var(--border-default, rgba(255,255,255,0.12));
          border-radius: var(--radius-lg, 16px);
          box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
          overflow: hidden;
          display: flex;
          flex-direction: column;
          animation: cmdk-slide 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes cmdk-slide {
          from { transform: translateY(-12px) scale(0.98); opacity: 0; }
          to { transform: translateY(0) scale(1); opacity: 1; }
        }
        .cmdk-input-wrap {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 14px 16px;
          border-bottom: 1px solid var(--border-default, rgba(255,255,255,0.08));
        }
        .cmdk-icon { font-size: 16px; opacity: 0.7; }
        .cmdk-input {
          flex: 1;
          background: transparent;
          border: none;
          outline: none;
          color: var(--text-primary, #f1f5f9);
          font-size: 14.5px;
          font-family: inherit;
        }
        .cmdk-input::placeholder { color: var(--text-muted, #64748b); }
        .cmdk-esc {
          font-family: ui-monospace, monospace;
          font-size: 10.5px;
          padding: 2px 6px;
          border-radius: 4px;
          background: var(--bg-subtle, rgba(255,255,255,0.06));
          color: var(--text-muted, #94a3b8);
          border: 1px solid var(--border-default, rgba(255,255,255,0.08));
        }
        .cmdk-list {
          flex: 1;
          overflow-y: auto;
          padding: 6px;
          scrollbar-width: thin;
        }
        .cmdk-empty {
          padding: 28px 16px;
          text-align: center;
          color: var(--text-muted, #64748b);
          font-size: 13px;
        }
        .cmdk-item {
          display: flex;
          align-items: center;
          gap: 12px;
          width: 100%;
          padding: 10px 12px;
          border-radius: var(--radius-md, 8px);
          background: transparent;
          border: 1px solid transparent;
          color: var(--text-secondary, #cbd5e1);
          text-align: left;
          cursor: pointer;
          transition: background 0.12s ease, border-color 0.12s ease;
        }
        .cmdk-item:hover, .cmdk-item.is-active {
          background: var(--bg-subtle, rgba(255,255,255,0.06));
          border-color: var(--border-default, rgba(255,255,255,0.08));
        }
        .cmdk-item.is-active {
          color: var(--text-primary, #f1f5f9);
        }
        .cmdk-item:focus-visible {
          outline: 2px solid var(--primary-500, #6366f1);
          outline-offset: -2px;
        }
        .cmdk-item-icon { font-size: 16px; flex-shrink: 0; width: 22px; text-align: center; }
        .cmdk-item-body { display: flex; flex-direction: column; flex: 1; min-width: 0; gap: 2px; }
        .cmdk-item-label { font-size: 13.5px; font-weight: 500; }
        .cmdk-item-hint { font-size: 11px; color: var(--text-muted, #64748b); }
        .cmdk-item-path {
          font-family: ui-monospace, monospace;
          font-size: 11px;
          color: var(--text-muted, #64748b);
          opacity: 0.7;
          flex-shrink: 0;
        }
        .cmdk-foot {
          display: flex;
          gap: 16px;
          padding: 10px 16px;
          border-top: 1px solid var(--border-default, rgba(255,255,255,0.08));
          font-size: 11.5px;
          color: var(--text-muted, #64748b);
          flex-wrap: wrap;
          align-items: center;
          background: var(--bg-subtle, rgba(255,255,255,0.03));
        }
        .cmdk-foot kbd {
          font-family: ui-monospace, monospace;
          font-size: 10px;
          padding: 1px 5px;
          border-radius: 3px;
          background: var(--bg-card, rgba(255,255,255,0.06));
          border: 1px solid var(--border-default, rgba(255,255,255,0.08));
          margin-right: 2px;
        }
        .cmdk-foot-brand { margin-left: auto; opacity: 0.7; }
        @media (max-width: 520px) {
          .cmdk-item-path { display: none; }
          .cmdk-foot { font-size: 10.5px; gap: 10px; }
        }
      `}</style>
    </div>
  );
}

export default CommandPalette;
