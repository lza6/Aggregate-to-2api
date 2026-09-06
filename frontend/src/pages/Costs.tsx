import { Suspense, lazy } from 'react';
import { fetchCost, fetchCostForecast } from '../api';
import { StatCard } from '../components/StatCard';
import { Skeleton, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { CostForecast, CostOverview } from '../api';

// recharts 重依赖懒加载（与 Dashboard 一致，主包不静态携带）
const LazyBarChart = lazy(() => import('../components/BarChart').then(m => ({ default: m.BarChart })));

/** USD 金额短格式化（$123.4567 -> $123.46；避免过长） */
function formatUsd(n: number | undefined | null): string {
  if (n == null || !Number.isFinite(Number(n))) return '-';
  return `$${Number(n).toFixed(2)}`;
}

export function CostsPage() {
  const { data: cost, loading, error, reload } = useApi<CostOverview>(() => fetchCost(), { intervalMs: 15000 });
  // P3-D3: 预算燃烧预测（管理 Key 鉴权；预算=0 时后端返回 disabled=true，前端降级）
  const { data: forecast } = useApi<CostForecast>(() => fetchCostForecast(), { intervalMs: 60000 });

  if (error && !cost) return <ErrorRetry message={error.message} onRetry={reload} />;
  if (loading && !cost) {
    return (
      <div className="costs-container">
        <div className="page-header">
          <h1 className="page-title">成本可视化</h1>
        </div>
        <div className="stats-grid">
          <Skeleton lines={2} height={80} />
          <Skeleton lines={2} height={80} />
          <Skeleton lines={2} height={80} />
          <Skeleton lines={2} height={80} />
        </div>
        <Skeleton lines={5} height={200} />
      </div>
    );
  }

  const monthlyChart = (cost?.monthly ?? []).map(m => ({
    name: m.month,
    value: m.cost_usd,
  }));

  const budget = cost?.budget_usd ?? 0;
  const overBudget = cost?.over_budget ?? false;
  const burnRate = cost?.burn_rate_warning ?? false;

  // P3-2: 日/月累积 vs 预算 —— 用月度趋势做「累积瀑布」：每月柱 = 该月成本，覆盖层 = 预算累计线。
  // 数据仅 month_to_date（月度累积口径），此处用 monthly 数组做逐月累积对比预算。
  const cumulative = (() => {
    const arr = (cost?.monthly ?? []).map(m => m.cost_usd);
    let acc = 0;
    return arr.map(v => (acc += v));
  })();
  const cumMax = Math.max(1, ...cumulative, budget);

  // 全屏预警（P3-2）：over_budget 时置顶红条；是否超 80% 燃烧率给出次级提示
  const warningText = overBudget
    ? `已超出本月预算 $${budget.toFixed(2)}（当前 ${formatUsd(cost?.month_to_date_usd)}）`
    : burnRate
      ? `本月已消耗预算 ${cost?.budget_remaining_pct != null ? (100 - cost.budget_remaining_pct).toFixed(1) : '?'}%，建议关注燃烧率`
      : null;

  return (
    <div className="costs-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            成本可视化
            <span className="title-badge">{budget > 0 ? `预算 $${budget.toFixed(2)}` : '未设预算'}</span>
          </h1>
          <p className="page-desc">token 成本（chat_usage）与图片成本（号池积分折算）月度口径一览</p>
        </div>
        <button onClick={reload} className="tf-btn tf-btn-secondary">
          <span>🔄</span> 刷新
        </button>
      </div>

      {/* P3-2: 全屏预算预警横幅（over_budget / burn_rate_warning） */}
      {warningText && (
        <div className="cost-budget-alert" role="alert">
          <span className="cba-icon">🚨</span>
          <div className="cba-body">
            <div className="cba-title">{overBudget ? '本月预算已超支' : '预算燃烧率告警'}</div>
            <div className="cba-msg">{warningText}</div>
          </div>
          <span className="cba-pct">{cost?.budget_remaining_pct != null ? `${cost.budget_remaining_pct.toFixed(0)}% 余量` : ''}</span>
        </div>
      )}

      {/* 顶部 4 张 StatCard */}
      <div className="stats-grid">
        <StatCard
          label="本月成本"
          value={formatUsd(cost?.month_to_date_usd)}
          sub={cost ? `图片 ${formatUsd(cost.image_cost_usd_mtd)}` : undefined}
          icon="💰"
        />
        <StatCard
          label="今日成本"
          value={formatUsd(cost?.today_usd)}
          icon="📆"
        />
        <StatCard
          label="预算余量"
          value={cost ? `${cost.budget_remaining_pct?.toFixed(1) ?? '-'}%` : '-'}
          sub={budget > 0 ? `剩余 $${(budget - (cost?.month_to_date_usd ?? 0)).toFixed(2)}` : '未启用成本预算'}
          color={budget > 0 ? (overBudget ? 'var(--danger)' : 'var(--success)') : undefined}
          icon="📊"
        />
        <StatCard
          label="燃烧率告警"
          value={burnRate ? '超 80%' : '正常'}
          sub={burnRate ? '月度已消耗预算 80% 以上' : overBudget ? '已超预算' : '预算内'}
          color={overBudget || burnRate ? 'var(--danger)' : 'var(--success)'}
          icon="🔥"
        />
      </div>

      {/* 月度趋势 */}
      {monthlyChart.length > 0 ? (
        <div className="section-block">
          <Suspense fallback={<div className="chart-fallback">图表加载中…</div>}>
            <LazyBarChart data={monthlyChart} title="月度成本趋势" sub="近 12 个月成本（USD）" height={230} />
          </Suspense>
        </div>
      ) : (
        <div className="section-block tf-card empty-chart-placeholder">
          <div className="empty-state">
            <span className="empty-icon">📊</span>
            <p className="empty-text">暂无成本趋势数据</p>
            <span className="empty-hint">产生调用后，月度成本趋势将在此展示</span>
          </div>
        </div>
      )}

      {/* P3-2: 日/月累积 vs 预算 —— 瀑布对比（纯 CSS bar，无重依赖） */}
      {budget > 0 && cumulative.length > 0 && (
        <div className="section-block tf-card cost-cumulative-card">
          <div className="section-header">
            <div>
              <h2 className="section-title">⛰️ 累积成本 vs 预算</h2>
              <span className="section-sub">逐月累积（USD）与预算线对比 — 超出即触发全屏预警</span>
            </div>
            <span className="tf-badge tf-badge-info">预算 ${budget.toFixed(2)}</span>
          </div>
          <div className="cum-rows">
            {cumulative.map((v, i) => {
              const pct = Math.min(100, (v / cumMax) * 100);
              const budgetPct = budget > 0 ? Math.min(100, (budget / cumMax) * 100) : 0;
              const over = budget > 0 && v > budget;
              return (
                <div className="cum-row" key={i}>
                  <span className="cum-label">{cost?.monthly?.[i]?.month ?? `M${i + 1}`}</span>
                  <div className="cum-track">
                    <div
                      className={`cum-fill ${over ? 'cum-over' : ''}`}
                      style={{ width: `${pct}%`, position: 'relative' }}
                    >
                      {budget > 0 && v > budget && <span className="cum-budget-cut" style={{ left: `${Math.min(100, budgetPct * (cumMax / v))}%` }} title="预算线" />}
                    </div>
                  </div>
                  <span className="cum-val">${v.toFixed(2)}{over ? ' ⚠' : ''}</span>
                </div>
              );
            })}
            {/* 预算参考线 */}
            <div className="cum-budget-line" style={{ width: `${Math.min(100, (budget / cumMax) * 100)}%` }}>
              <span className="cum-budget-label">预算 ${budget.toFixed(2)}</span>
            </div>
          </div>
          <style>{`
            .cost-cumulative-card { padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
            .cum-rows { display: flex; flex-direction: column; gap: 8px; position: relative; }
            .cum-row { display: grid; grid-template-columns: 64px 1fr 84px; align-items: center; gap: 10px; }
            .cum-label { font-size: 11.5px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
            .cum-track { height: 14px; background: var(--bg-subtle); border-radius: var(--radius-full); overflow: hidden; position: relative; }
            .cum-fill { height: 100%; background: linear-gradient(90deg, #6366f1 0%, #818cf8 100%); border-radius: var(--radius-full); transition: width 0.5s cubic-bezier(0.16, 1, 0.3, 1); }
            .cum-fill.cum-over { background: linear-gradient(90deg, #ef4444 0%, #f59e0b 100%); }
            .cum-val { font-size: 11.5px; color: var(--text-primary); font-variant-numeric: tabular-nums; text-align: right; font-weight: 600; }
            .cum-budget-line { position: relative; height: 1px; background: var(--warning); margin-top: 4px; pointer-events: none; }
            .cum-budget-label { position: absolute; right: 0; top: -16px; font-size: 10.5px; color: var(--warning-text); font-weight: 600; white-space: nowrap; }
          `}</style>
        </div>
      )}

      {/* P3-D3: 预算燃烧预测（管理 Key 鉴权；预算=0 时降级为"未设预算"） */}
      <div className="section-block tf-card cost-forecast-card">
        <div className="section-header">
          <div>
            <h2 className="section-title">🔮 预算燃烧预测</h2>
            <span className="section-sub">
              {forecast?.disabled
                ? '未设预算（IF_COST_BUDGET_USD=0），不启用燃烧预测'
                : '基于近 30 天日均消耗速率预测何时超预算'}
            </span>
          </div>
          {!forecast?.disabled && forecast?.projected_exceed_date && (
            <span
              className="tf-badge"
              style={{
                background: (forecast.days_remaining ?? 0) <= 7 ? 'var(--danger-bg)' : 'var(--warning-bg)',
                color: (forecast.days_remaining ?? 0) <= 7 ? 'var(--danger-text)' : 'var(--warning-text)',
              }}
            >
              预计 {forecast.projected_exceed_date} 超预算
            </span>
          )}
        </div>

        {forecast?.disabled ? (
          <div className="cost-forecast-disabled">
            <span className="cf-disabled-icon">⚠️</span>
            <div className="cf-disabled-body">
              <div className="cf-disabled-title">未设预算阈值</div>
              <div className="cf-disabled-msg">
                设置环境变量 <code>IF_COST_BUDGET_USD</code>（美元，&gt;0）后重启服务即可启用燃烧预测。
                当前仅展示近 30 天日均消耗参考值。
              </div>
            </div>
            <span className="cf-disabled-avg">日均 {formatUsd(forecast?.daily_avg_30d)}</span>
          </div>
        ) : forecast ? (
          <>
            <div className="cf-stats-row">
              <div className="cf-stat">
                <span className="cf-stat-label">日均消耗（30d）</span>
                <span className="cf-stat-value">{formatUsd(forecast.daily_avg_30d)}</span>
              </div>
              <div className="cf-stat">
                <span className="cf-stat-label">近 30 天累计</span>
                <span className="cf-stat-value">{formatUsd(forecast.current_spent_30d)}</span>
              </div>
              <div className="cf-stat">
                <span className="cf-stat-label">预算阈值</span>
                <span className="cf-stat-value">{formatUsd(forecast.budget_usd)}</span>
              </div>
              <div className="cf-stat">
                <span className="cf-stat-label">预计超预算</span>
                <span className="cf-stat-value">
                  {forecast.projected_exceed_date ?? '无法预测'}
                </span>
              </div>
              <div className="cf-stat">
                <span className="cf-stat-label">剩余天数</span>
                <span
                  className="cf-stat-value"
                  style={{
                    color:
                      forecast.days_remaining == null
                        ? 'var(--text-muted)'
                        : forecast.days_remaining <= 7
                          ? 'var(--danger-text)'
                          : forecast.days_remaining <= 14
                            ? 'var(--warning-text)'
                            : 'var(--success-text)',
                  }}
                >
                  {forecast.days_remaining == null ? '-' : `${forecast.days_remaining} 天`}
                </span>
              </div>
            </div>

            {/* 燃烧进度条：当前累计 vs 预算阈值 */}
            {forecast.budget_usd > 0 && (
              <div className="cf-burn-bar">
                {(() => {
                  const spentPct = Math.min(
                    100,
                    (forecast.current_spent_30d / forecast.budget_usd) * 100,
                  );
                  const over = forecast.current_spent_30d >= forecast.budget_usd;
                  return (
                    <>
                      <div className="cf-burn-track">
                        <div
                          className={`cf-burn-fill ${over ? 'cf-burn-over' : ''}`}
                          style={{ width: `${Math.max(2, spentPct)}%` }}
                        />
                        {/* 预算警戒线（100% 处） */}
                        <div className="cf-burn-budget-line" title="预算阈值" />
                      </div>
                      <div className="cf-burn-legend">
                        <span>累计 {formatUsd(forecast.current_spent_30d)}</span>
                        <span>预算 {formatUsd(forecast.budget_usd)}</span>
                        <span style={{ color: over ? 'var(--danger-text)' : 'var(--text-muted)' }}>
                          {over ? '已超支' : `${spentPct.toFixed(1)}%`}
                        </span>
                      </div>
                    </>
                  );
                })()}
              </div>
            )}

            {forecast.note && (
              <div className="cf-note">{forecast.note}</div>
            )}
          </>
        ) : (
          <Skeleton lines={3} height={40} />
        )}
      </div>

      {/* by_provider 表格 */}
      <div className="section-block">
        <div className="section-header">
          <div>
            <h2 className="section-title">按提供商成本</h2>
            <span className="section-sub">provider / 调用数 / cost_usd / tokens</span>
          </div>
        </div>
        <div className="tf-table-container">
          <div style={{ overflowX: 'auto' }}>
            <table className="tf-table">
              <thead>
                <tr>
                  <th>提供商</th>
                  <th>调用数</th>
                  <th>成本 (USD)</th>
                  <th>Tokens</th>
                  <th>消耗积分</th>
                  <th>出图数</th>
                </tr>
              </thead>
              <tbody>
                {(cost?.by_provider ?? []).map(row => (
                  <tr key={row.provider}>
                    <td style={{ fontWeight: 600 }}>{row.provider}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{row.calls ?? 0}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--primary-600)' }}>{formatUsd(row.cost_usd)}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary)' }}>{(row.tokens ?? 0).toLocaleString()}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary)' }}>{row.credits_used ?? '-'}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary)' }}>{row.images ?? '-'}</td>
                  </tr>
                ))}
                {!cost?.by_provider?.length && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: '36px 0', color: 'var(--text-muted)' }}>
                      📭 暂无按提供商成本数据
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 口径说明 */}
      {(cost?.note || budget === 0) && (
        <div className="cost-note tf-card">
          <span>ℹ️</span>
          <span>{cost?.note ?? '预算未配置（IF_COST_BUDGET_USD=0），不启用成本告警。'}</span>
        </div>
      )}

      <style>{`
        .costs-container { display: flex; flex-direction: column; gap: 24px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
        .section-block { display: flex; flex-direction: column; gap: 14px; }
        .section-header { display: flex; align-items: center; justify-content: space-between; }
        .section-title { font-size: 17px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.01em; }
        .section-sub { font-size: 12.5px; color: var(--text-muted); margin-top: 2px; display: block; }
        .chart-fallback { padding: 40px 0; text-align: center; color: var(--text-muted); font-size: 12.5px; }
        .cost-note { padding: 10px 16px; font-size: 12.5px; color: var(--warning-text); background: var(--warning-bg); border-color: var(--warning-border); display: flex; align-items: center; gap: 8px; }
        .cost-budget-alert { display: flex; align-items: center; gap: 12px; padding: 14px 18px; background: var(--danger-bg); border: 1px solid var(--danger-border); border-radius: var(--radius-lg); color: var(--danger-text); }
        .cba-icon { font-size: 22px; flex-shrink: 0; }
        .cba-body { flex: 1; min-width: 0; }
        .cba-title { font-size: 14px; font-weight: 700; }
        .cba-msg { font-size: 12.5px; opacity: 0.92; margin-top: 2px; }
        .cba-pct { font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
        .cost-forecast-card { padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
        .cost-forecast-disabled { display: flex; align-items: center; gap: 12px; padding: 14px 16px; background: var(--bg-subtle); border-radius: var(--radius-lg); }
        .cf-disabled-icon { font-size: 22px; flex-shrink: 0; }
        .cf-disabled-body { flex: 1; min-width: 0; }
        .cf-disabled-title { font-size: 14px; font-weight: 700; color: var(--text-primary); }
        .cf-disabled-msg { font-size: 12.5px; color: var(--text-muted); margin-top: 2px; }
        .cf-disabled-msg code { background: var(--bg-card); padding: 1px 6px; border-radius: 4px; font-size: 11.5px; }
        .cf-disabled-avg { font-size: 13px; font-weight: 600; color: var(--primary-600); font-variant-numeric: tabular-nums; white-space: nowrap; }
        .cf-stats-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
        .cf-stat { display: flex; flex-direction: column; gap: 4px; padding: 10px 14px; background: var(--bg-subtle); border-radius: var(--radius-md); }
        .cf-stat-label { font-size: 11px; color: var(--text-muted); }
        .cf-stat-value { font-size: 14px; font-weight: 600; color: var(--text-primary); font-variant-numeric: tabular-nums; }
        .cf-burn-bar { display: flex; flex-direction: column; gap: 6px; }
        .cf-burn-track { position: relative; height: 12px; background: var(--bg-subtle); border-radius: var(--radius-full); overflow: hidden; }
        .cf-burn-fill { height: 100%; background: linear-gradient(90deg, #6366f1 0%, #818cf8 100%); border-radius: var(--radius-full); transition: width 0.5s cubic-bezier(0.16, 1, 0.3, 1); }
        .cf-burn-fill.cf-burn-over { background: linear-gradient(90deg, #ef4444 0%, #f59e0b 100%); }
        .cf-burn-budget-line { position: absolute; right: 0; top: 0; bottom: 0; width: 2px; background: var(--warning); pointer-events: none; }
        .cf-burn-legend { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
        .cf-note { font-size: 11.5px; color: var(--text-muted); line-height: 1.5; }
      `}</style>
    </div>
  );
}
