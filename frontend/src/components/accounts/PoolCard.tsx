// P2-4 拆分：Accounts 页「单个号池卡片」子组件。
// 从原 Accounts.tsx 抽出，纯展示组件，无状态依赖（props 驱动）。

export interface PoolCardStats {
  total: number;
  ok: number;
  exhausted: number;
  registering: number;
  credits: number;
  target: number;
  auto_register: boolean;
}

export interface PoolCardMeta {
  name: string;
  note: string;
}

export function PoolCard({ prefix, stats, meta }: { prefix: string; stats: PoolCardStats; meta: PoolCardMeta }) {
  const pct = stats.target > 0 ? Math.min(100, Math.round((stats.ok / stats.target) * 100)) : 0;

  return (
    <div className="pool-card-modern tf-card">
      <div className="pool-head">
        <div>
          <span className="pool-name">{meta.name}</span>
          <span className="pool-prefix-tag">{prefix}</span>
        </div>
        {!stats.auto_register ? (
          <span className="tf-badge tf-badge-neutral">自动补号关</span>
        ) : (
          <span className="tf-badge tf-badge-success">
            <span className="tf-dot tf-dot-pulse" style={{ background: 'var(--success)' }} />
            自动补号中
          </span>
        )}
      </div>

      <div className="pool-note">{meta.note}</div>

      <div className="pool-progress-section">
        <div className="progress-info">
          <span className="progress-label">号池达标率</span>
          <span className="progress-value">{stats.ok} / {stats.target} 可用 ({pct}%)</span>
        </div>
        <div className="pool-progress-track">
          <div className="pool-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="pool-metrics-grid">
        <div className="pm-card">
          <span className="pm-label">总账号</span>
          <span className="pm-val">{stats.total}</span>
        </div>
        <div className="pm-card">
          <span className="pm-label">可用状态</span>
          <span className="pm-val text-success">{stats.ok}</span>
        </div>
        <div className="pm-card">
          <span className="pm-label">额度耗尽</span>
          <span className="pm-val text-danger">{stats.exhausted}</span>
        </div>
        <div className="pm-card">
          <span className="pm-label">正在注册</span>
          <span className="pm-val text-warning">{stats.registering}</span>
        </div>
        <div className="pm-card">
          <span className="pm-label">总积分池</span>
          <span className="pm-val text-primary">{stats.credits}</span>
        </div>
      </div>
    </div>
  );
}
