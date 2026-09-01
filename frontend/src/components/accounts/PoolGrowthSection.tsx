// P2-4 拆分：Accounts 页「号池补满速率 + 成本口径」子组件（号池展开时显示）。
// 从原 Accounts.tsx 抽出，纯展示。

interface GrowthStats {
  total: number;
  new_in_24h: number;
  new_in_7d: number;
  avg_daily_7d: number;
  ok: number;
  target: number;
  gap: number;
  eta_days: number | null;
}

interface CostSummary {
  total_credits_used: number;
  total_images_used: number;
  total_credits_earned: number;
  accounts_with_usage: number;
  total_accounts: number;
  avg_cost_per_image: number | null;
}

export function PoolGrowthSection({ growthStats, costSummary }: { growthStats?: GrowthStats; costSummary?: CostSummary }) {
  return (
    <>
      {growthStats ? (
        <div className="pool-growth-section tf-card">
          <div className="detail-header">
            <div className="detail-title-group">
              <h3 className="detail-title">📈 号池补满速率</h3>
              <span className="tf-badge tf-badge-info">刷新即估</span>
            </div>
            <span className="pool-growth-target">
              目标 {growthStats.ok} / {growthStats.target} 可用
            </span>
          </div>
          <div className="pool-growth-grid">
            <div className="pg-card">
              <span className="pm-label">今日新增</span>
              <span className="pg-val text-primary">{growthStats.new_in_24h}</span>
              <span className="pg-sub">24h 入池账号</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">日均新增</span>
              <span className="pg-val text-primary">{growthStats.avg_daily_7d}</span>
              <span className="pg-sub">近 7 天平均</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">距目标还差</span>
              <span className="pg-val text-warning">{growthStats.gap}</span>
              <span className="pg-sub">还差这么多可用</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">预计达标</span>
              <span className="pg-val">{growthStats.eta_days != null ? `${growthStats.eta_days} 天` : '—'}</span>
              <span className="pg-sub">
                {growthStats.new_in_24h > 0 ? '按今日速率估算' : '新增为 0，暂无法估算'}
              </span>
            </div>
          </div>
          {growthStats.new_in_24h > 0 && growthStats.eta_days != null && growthStats.eta_days > 30 && (
            <div className="pool-growth-hint">
              ⚠ 按当前速率约需 {growthStats.eta_days} 天，久未达标建议调小 IF_REGISTER_COOLDOWN 或补代理池。
            </div>
          )}
        </div>
      ) : null}

      {costSummary ? (
        <div className="pool-growth-section tf-card">
          <div className="detail-header">
            <div className="detail-title-group">
              <h3 className="detail-title">💰 成本口径</h3>
              <span className="tf-badge tf-badge-info">号池聚合</span>
            </div>
            <span className="pool-growth-target">
              {costSummary.accounts_with_usage} / {costSummary.total_accounts} 账号有出图
            </span>
          </div>
          <div className="pool-growth-grid">
            <div className="pg-card">
              <span className="pm-label">累计消耗积分</span>
              <span className="pg-val text-danger">{costSummary.total_credits_used}</span>
              <span className="pg-sub">全部账号累计扣减</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">累计出图次数</span>
              <span className="pg-val text-primary">{costSummary.total_images_used}</span>
              <span className="pg-sub">实际生成结果数</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">平均每张成本</span>
              <span className="pg-val">{costSummary.avg_cost_per_image != null ? `${costSummary.avg_cost_per_image} 分/张` : '—'}</span>
              <span className="pg-sub">有出图口径下估算</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">累计获得积分</span>
              <span className="pg-val text-success">{costSummary.total_credits_earned}</span>
              <span className="pg-sub">签到累计入账</span>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
