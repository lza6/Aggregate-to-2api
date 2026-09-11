// v12.0.1：Agent 页 DAG 轻量分层可视化（零依赖自绘 SVG）+ 推理轨迹（black-box）面板。
// 布局：按 depends_on 最长路径分层（拓扑分层；成环/未知依赖容错忽略），层内水平排列，
// 边为「父底 → 子顶」折线 + 按子节点状态着色的箭头。点击节点弹出该步完整推理轨迹。
// 复用 Agent 页 STATUS_META 状态色（pending/running/succeeded/failed/skipped）。
import { useMemo, useState } from 'react';
import type { DagNodePublic } from '../api/agent';

export const STATUS_META: Record<string, { label: string; color: string }> = {
  pending: { label: '排队中', color: '#94a3b8' },
  running: { label: '执行中', color: '#3b82f6' },
  succeeded: { label: '成功', color: '#10b981' },
  failed: { label: '失败', color: '#ef4444' },
  skipped: { label: '已跳过', color: '#64748b' },
};

export function statusLabel(status: string): string {
  return STATUS_META[status]?.label ?? status;
}

export function statusColor(status: string): string {
  return STATUS_META[status]?.color ?? '#94a3b8';
}

function fmtMs(v: number): string {
  if (!Number.isFinite(v) || v <= 0) return '—';
  if (v >= 1000) return `${(v / 1000).toFixed(2)}s`;
  return `${Math.round(v)}ms`;
}

/** SVG id/className 安全化（状态值来自固定枚举，兜底替换非法字符）。 */
function safeKey(v: string): string {
  return v.replace(/[^a-zA-Z0-9_-]/g, '_');
}

function truncate(v: string, max: number): string {
  return v.length > max ? `${v.slice(0, max - 1)}…` : v;
}

// ── 分层布局（最长路径法）────────────────────────────────────
const NODE_W = 150;
const NODE_H = 52;
const GAP_X = 28;
const GAP_Y = 64;
const PAD = 16;

interface LayoutResult {
  placed: { node: DagNodePublic; x: number; y: number }[];
  edges: { from: DagNodePublic; to: DagNodePublic; d: string; color: string }[];
  width: number;
  height: number;
}

function layoutDag(nodes: DagNodePublic[]): LayoutResult {
  const byId = new Map(nodes.map(n => [n.id, n]));
  const layerCache = new Map<string, number>();

  // 记忆化 DFS：layer(n) = max(layer(dep)) + 1；环边与未知依赖按 0 层兜底。
  function layerOf(id: string, path: Set<string>): number {
    const cached = layerCache.get(id);
    if (cached !== undefined) return cached;
    if (path.has(id)) return 0;
    path.add(id);
    const node = byId.get(id);
    let layer = 0;
    if (node) {
      for (const dep of node.depends_on) {
        if (dep !== id && byId.has(dep)) layer = Math.max(layer, layerOf(dep, path) + 1);
      }
    }
    path.delete(id);
    layerCache.set(id, layer);
    return layer;
  }

  const layers = new Map<number, DagNodePublic[]>();
  for (const n of nodes) {
    const layer = layerOf(n.id, new Set());
    const bucket = layers.get(layer);
    if (bucket) bucket.push(n);
    else layers.set(layer, [n]);
  }

  const maxCols = Math.max(...[...layers.values()].map(b => b.length), 1);
  const width = PAD * 2 + maxCols * NODE_W + (maxCols - 1) * GAP_X;
  const height = PAD * 2 + layers.size * NODE_H + (layers.size - 1) * GAP_Y;

  const pos = new Map<string, { x: number; y: number }>();
  for (const [layer, bucket] of layers) {
    const y = PAD + layer * (NODE_H + GAP_Y);
    const rowWidth = bucket.length * NODE_W + (bucket.length - 1) * GAP_X;
    const startX = Math.max(PAD, (width - rowWidth) / 2); // 层内居中
    bucket.forEach((n, i) => pos.set(n.id, { x: startX + i * (NODE_W + GAP_X), y }));
  }

  const edges: LayoutResult['edges'] = [];
  for (const n of nodes) {
    const to = pos.get(n.id);
    if (!to) continue;
    for (const depId of n.depends_on) {
      const dep = byId.get(depId);
      const from = pos.get(depId);
      if (!dep || !from) continue;
      const sx = from.x + NODE_W / 2;
      const sy = from.y + NODE_H;
      const tx = to.x + NODE_W / 2;
      const ty = to.y - 1; // 留 1px 给箭头尖端
      const midY = sy + (ty - sy) / 2;
      edges.push({ from: dep, to: n, d: `M ${sx} ${sy} V ${midY} H ${tx} V ${ty}`, color: statusColor(n.status) });
    }
  }

  return { placed: nodes.map(n => ({ node: n, ...(pos.get(n.id) ?? { x: PAD, y: PAD }) })), edges, width, height };
}

// ── 推理轨迹（black-box）面板 ────────────────────────────────
export function DagTrace({ node }: { node: DagNodePublic | null }) {
  if (!node) {
    return <div className="dag-trace-empty">点击上方节点，查看该步的完整推理轨迹（黑匣子）</div>;
  }
  const nothingYet = !node.prompt && !node.result && !node.error;
  return (
    <div className="dag-trace" role="region" aria-label={`节点 ${node.id} 推理轨迹`}>
      <div className="dag-trace-head">
        <span className="dag-node-kind">{node.kind}</span>
        <span className="dag-trace-id">{node.id}</span>
        <span className="dag-node-status" style={{ color: statusColor(node.status) }}>
          ● {statusLabel(node.status)}
        </span>
      </div>
      <div className="dag-trace-meta">
        <span>尝试 #{node.attempt}</span>
        <span>耗时 {fmtMs(node.duration_ms)}</span>
        {node.model && <span>模型 {node.model}</span>}
        {node.condition && <span>条件 {node.condition}</span>}
        {node.depends_on.length > 0 && <span>依赖 {node.depends_on.join(', ')}</span>}
      </div>
      {nothingYet && <div className="dag-trace-empty-inline">该节点尚未执行</div>}
      {node.prompt && (
        <section>
          <div className="dag-trace-label">输入 Prompt（该步被喂了什么）</div>
          <pre className="dag-trace-block">{node.prompt}</pre>
        </section>
      )}
      {node.result && (
        <section>
          <div className="dag-trace-label">输出 Result</div>
          <pre className="dag-trace-block">{node.result}</pre>
        </section>
      )}
      {node.error && (
        <section>
          <div className="dag-trace-label">错误 Error</div>
          <pre className="dag-trace-block is-error">{node.error}</pre>
        </section>
      )}
    </div>
  );
}

// ── DAG SVG 图（含选中态与轨迹面板联动）─────────────────────
interface DagGraphProps {
  nodes: DagNodePublic[];
  /** 额外选中回调（组件内部自持选中态，此回调用于外部联动，可选）。 */
  onSelect?: (id: string) => void;
}

export function DagGraph({ nodes, onSelect }: DagGraphProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const layout = useMemo(() => layoutDag(nodes), [nodes]);
  const selected = nodes.find(n => n.id === selectedId) ?? null;

  if (!nodes.length) return null;

  const arrowStatuses = [...new Set(nodes.map(n => n.status))];
  const pick = (id: string) => {
    setSelectedId(id);
    onSelect?.(id);
  };

  return (
    <div className="dag-graph">
      <div className="dag-graph-canvas">
        <svg
          className="dag-svg"
          width={layout.width}
          height={layout.height}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          role="img"
          aria-label={`DAG 节点图（${nodes.length} 节点）`}
        >
          <defs>
            {arrowStatuses.map(s => (
              <marker
                key={s}
                id={`dag-arrow-${safeKey(s)}`}
                viewBox="0 0 8 8"
                refX="8"
                refY="4"
                markerWidth="8"
                markerHeight="8"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 8 4 L 0 8 z" fill={statusColor(s)} />
              </marker>
            ))}
          </defs>
          {layout.edges.map((e, i) => (
            <path
              key={`${e.from.id}->${e.to.id}-${i}`}
              className="dag-svg-edge"
              d={e.d}
              stroke={e.color}
              markerEnd={`url(#dag-arrow-${safeKey(e.to.status)})`}
            />
          ))}
          {layout.placed.map(({ node, x, y }) => {
            const isSelected = node.id === selectedId;
            const classes = [
              'dag-svg-node',
              `st-${safeKey(node.status)}`,
              node.status === 'running' ? 'dag-node-running' : '',
              isSelected ? 'selected' : '',
            ]
              .filter(Boolean)
              .join(' ');
            return (
              <g
                key={node.id}
                className={classes}
                transform={`translate(${x}, ${y})`}
                onClick={() => pick(node.id)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    pick(node.id);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-pressed={isSelected}
                aria-label={`节点 ${node.id}（${statusLabel(node.status)}）`}
              >
                <rect
                  className="dag-svg-node-box"
                  width={NODE_W}
                  height={NODE_H}
                  rx={10}
                  style={{ stroke: statusColor(node.status) }}
                />
                <circle className="dag-svg-status-dot" cx={14} cy={17} r={4.5} fill={statusColor(node.status)} />
                <text className="dag-svg-kind" x={26} y={21}>
                  {node.kind}
                </text>
                <text className="dag-svg-id" x={14} y={41}>
                  {truncate(node.id, 16)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      {selected && <DagTrace node={selected} />}
    </div>
  );
}
