import { useEffect, useState } from 'react';
import { fetchAccountPool } from '../api';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import { useVirtualList } from '../hooks/useVirtualList';
import { PoolCard } from '../components/accounts/PoolCard';
import { PoolPausedBanner } from '../components/accounts/PoolPausedBanner';
import { PoolGrowthSection } from '../components/accounts/PoolGrowthSection';
import { LiveRegistrationCard } from '../components/accounts/LiveRegistrationCard';
import { AccountTable } from '../components/accounts/AccountTable';
import { PaginationBar, EmailPoolSection } from '../components/accounts/PaginationBar';

interface ProviderPoolStats {
  total: number;
  ok: number;
  exhausted: number;
  registering: number;
  credits: number;
  target: number;
  auto_register: boolean;
}

interface AccountItem {
  email: string;
  credits: number;
  status: string;
  created_at: number | null;
  checkin_at: number | null;
  register_ip?: string | null;
  checkin_total?: number;
  checkin_cycle_day?: number;
  credits_earned_total?: number;
  credits_used_total?: number;
  images_used?: number;
  last_used_at?: number | null;
  next_claim_at?: number | null;
  age_days?: number | null;
}

interface LiveRegistration {
  stage: string;
  stage_label: string;
  email: string;
  email_source: string;
  created_at: number;
  updated_at: number;
  last_error: string | null;
  error_category: string | null;
  stage_durations: Record<string, number>;
}

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

interface AccountPoolData {
  accounts: Record<string, ProviderPoolStats>;
  growth_stats?: GrowthStats;
  cost_summary?: CostSummary;
  email_pool: {
    total_registered: number;
    by_provider: Record<string, number>;
    successful_registrations?: number;
    failed_registrations?: number;
  };
  live_registration?: LiveRegistration | null;
  items?: AccountItem[];
  items_total?: number;
  total_pages?: number;
  page?: number;
  page_size?: number;
}

const PROVIDER_META: Record<string, { name: string; note: string }> = {
  nanobanana: { name: 'NanoBanana Pro', note: '每日签到自动续额（长效号池管理）' },
};
const ACTIVE_PROVIDERS = new Set(['nanobanana']);

const ACCOUNT_ROW_H = 48;
const ACCOUNT_CONTAINER_H = 560;

export function AccountsPage() {
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [poolPaused, setPoolPaused] = useState<boolean>(() => {
    try { return localStorage.getItem('imagefreeNanobananaPoolPaused') !== '0'; } catch { return true; }
  });
  useEffect(() => {
    try { localStorage.setItem('imagefreeNanobananaPoolPaused', poolPaused ? '1' : '0'); } catch { /* ignore */ }
  }, [poolPaused]);
  const { data, loading, error, reload } = useApi<AccountPoolData>(
    () => fetchAccountPool({ page, pageSize, search: filter }),
    { intervalMs: 10000, debounceMs: 300 },  // v7.7 UX：搜索防抖——快速输入不再每键一请求
  );

  useEffect(() => { setPage(1); }, [filter, pageSize]);
  useEffect(() => { void reload(); }, [page, filter, pageSize, reload]);

  // P2-2: useVirtualList 必须在任何条件 return 之前调用（hooks 顺序恒定，防 React #310）
  const pagedItems = data?.items ?? [];
  const vlist = useVirtualList(pagedItems, { itemHeight: ACCOUNT_ROW_H, containerHeight: ACCOUNT_CONTAINER_H, overscan: 10 });
  const topPad = vlist.startIndex * ACCOUNT_ROW_H;
  const bottomPad = (pagedItems.length - vlist.endIndex) * ACCOUNT_ROW_H;

  if (error && !data) return <ErrorRetry message={error.message} onRetry={reload} />;
  if (loading && !data) {
    return (
      <div className="accounts-page-container">
        <div className="page-header">
          <h1 className="page-title">长效号池管理</h1>
        </div>
        <div className="pool-grid">
          <Skeleton lines={4} height={160} />
        </div>
      </div>
    );
  }

  const entries = Object.entries(data?.accounts ?? {}).filter(([prefix]) => ACTIVE_PROVIDERS.has(prefix));
  const totalItems = data?.items_total ?? 0;
  const totalPages = Math.max(1, data?.total_pages ?? 1);
  const safePage = Math.min(page, totalPages);

  return (
    <div className="accounts-page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            长效号池管理
            <span className="title-badge">{totalItems} 个活跃账号</span>
          </h1>
          <p className="page-desc">各平台长效账号自动注册、每日签到续额调度、脱敏活跃明细及邮箱分配</p>
        </div>
        <button onClick={reload} className="tf-btn tf-btn-secondary">
          <span>🔄</span> 刷新号池
        </button>
      </div>

      <PoolPausedBanner poolPaused={poolPaused} onToggle={() => setPoolPaused(v => !v)} />

      {poolPaused ? null : entries.length === 0 ? (
        <Empty text="号池暂未初始化" hint="开启 IF_ACCOUNT_AUTO=1 后将自动开始账号注册与巡检" />
      ) : (
        <div className="pool-grid">
          {entries.map(([prefix, stats]) => (
            <PoolCard key={prefix} prefix={prefix} stats={stats} meta={PROVIDER_META[prefix] ?? { name: prefix, note: '账号生命周期池' }} />
          ))}
        </div>
      )}

      {!poolPaused && (data?.growth_stats || data?.cost_summary) ? (
        <PoolGrowthSection growthStats={data?.growth_stats} costSummary={data?.cost_summary} />
      ) : null}

      {!poolPaused && data?.live_registration ? (
        <LiveRegistrationCard reg={data.live_registration} />
      ) : null}

      {!poolPaused && (
        <>
          <div className="detail-search-wrap" style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <input
              type="text"
              aria-label="搜索脱敏邮箱或状态"
              placeholder="🔍 搜索脱敏邮箱 / 状态…"
              value={filter}
              onChange={e => setFilter(e.target.value)}
              className="tf-input search-input-styled"
              style={{ width: 240 }}
            />
          </div>
          <AccountTable
            pagedItems={pagedItems}
            virtualSlice={vlist}
            rowHeight={ACCOUNT_ROW_H}
            containerHeight={ACCOUNT_CONTAINER_H}
            topPad={topPad}
            bottomPad={bottomPad}
          />
          {totalItems > pageSize && (
            <PaginationBar
              totalItems={totalItems}
              safePage={safePage}
              totalPages={totalPages}
              pageSize={pageSize}
              onPageChange={setPage}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
            />
          )}
        </>
      )}

      {!poolPaused && data?.email_pool && (
        <EmailPoolSection emailPool={data.email_pool} providerMeta={PROVIDER_META} />
      )}

      <style>{`
        .accounts-page-container { display: flex; flex-direction: column; gap: 24px; }
        .pool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }
        .pool-card-modern { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
        .pool-head { display: flex; align-items: center; justify-content: space-between; }
        .pool-name { font-size: 16px; font-weight: 600; color: var(--text-primary); }
        .pool-prefix-tag { font-size: 11px; font-family: ui-monospace, monospace; color: var(--text-muted); margin-left: 6px; }
        .pool-note { font-size: 12px; color: var(--text-muted); }
        .pool-progress-section { display: flex; flex-direction: column; gap: 6px; }
        .progress-info { display: flex; justify-content: space-between; font-size: 12px; }
        .progress-label { color: var(--text-secondary); }
        .progress-value { color: var(--text-primary); font-weight: 600; }
        .pool-progress-track { height: 8px; background: var(--bg-subtle); border-radius: var(--radius-full); overflow: hidden; }
        .pool-progress-fill { height: 100%; background: linear-gradient(90deg, #6366f1 0%, #10b981 100%); border-radius: var(--radius-full); transition: width 0.5s cubic-bezier(0.16, 1, 0.3, 1); }
        .pool-metrics-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
        .pm-card { background: var(--bg-subtle); border: 1px solid var(--border-default); border-radius: var(--radius-md); padding: 8px 6px; text-align: center; display: flex; flex-direction: column; gap: 3px; }
        .pm-label { font-size: 10.5px; color: var(--text-muted); }
        .pm-val { font-size: 15px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text-primary); }
        .text-success { color: var(--success); } .text-danger { color: var(--danger); } .text-warning { color: var(--warning); } .text-primary { color: var(--primary-600); }
        .pool-growth-section { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
        .pool-growth-target { font-size: 12px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
        .pool-growth-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
        .pg-card { background: var(--bg-subtle); border: 1px solid var(--border-default); border-radius: var(--radius-md); padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; }
        .pg-val { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text-primary); }
        .pg-sub { font-size: 10.5px; color: var(--text-muted); }
        .pool-growth-hint { font-size: 12px; color: var(--warning-text); background: var(--bg-subtle); border: 1px dashed var(--warning); border-radius: var(--radius-sm); padding: 8px 10px; }
        .accounts-detail-section { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
        .reg-stage-body { display: flex; flex-direction: column; gap: 12px; }
        .reg-stage-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
        .reg-stage-email { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12.5px; color: var(--primary-600); }
        .reg-stage-error { font-size: 12px; color: var(--danger); background: var(--bg-subtle); border: 1px solid var(--border-default); border-radius: var(--radius-sm); padding: 8px 10px; font-family: ui-monospace, monospace; }
        .reg-stage-flow { display: flex; flex-wrap: wrap; align-items: stretch; gap: 8px; }
        .reg-stage-node { display: flex; flex-direction: column; justify-content: flex-end; gap: 4px; background: var(--bg-subtle); border: 1px solid var(--border-default); border-radius: var(--radius-sm); padding: 8px 12px; min-width: 92px; }
        .reg-stage-name { font-size: 11.5px; color: var(--text-secondary); }
        .reg-stage-dur { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--primary-600); }
        .detail-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
        .detail-title-group { display: flex; align-items: center; gap: 10px; }
        .detail-title { font-size: 16px; font-weight: 600; color: var(--text-primary); }
        .pagination-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-top: 4px; }
        .pagination-info { font-size: 12px; color: var(--text-muted); }
        .pagination-controls { display: flex; align-items: center; gap: 4px; }
        .pagination-ellipsis { color: var(--text-muted); font-size: 13px; padding: 0 2px; }
        .page-size-select { width: auto; min-width: 100px; font-size: 12px; }
        .email-pool-section { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
        .email-pool-header { display: flex; align-items: center; justify-content: space-between; }
        .email-pool-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
        .email-total-tag { font-size: 12px; color: var(--text-muted); }
        .email-providers-list { display: flex; flex-direction: column; gap: 8px; }
        .email-provider-row { display: flex; justify-content: space-between; font-size: 13px; padding: 8px 12px; background: var(--bg-subtle); border-radius: var(--radius-md); color: var(--text-primary); }
        .pool-paused-banner { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 18px; border-radius: var(--radius-md); border: 1px solid var(--border-default); background: var(--bg-subtle); flex-wrap: wrap; }
        .pool-paused-banner.is-paused { border-color: var(--warning); background: var(--warning-bg, var(--bg-subtle)); }
        .pool-paused-main { display: flex; align-items: center; gap: 12px; }
        .pool-paused-icon { font-size: 22px; color: var(--warning); }
        .pool-paused-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
        .pool-paused-desc { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
        .pool-disabled-placeholder { display: flex; align-items: center; gap: 14px; padding: 28px 24px; border: 1px dashed var(--warning); background: var(--bg-subtle); grid-column: 1 / -1; }
        .pool-disabled-icon { font-size: 32px; color: var(--text-muted); }
        .pool-disabled-title { font-size: 16px; font-weight: 600; color: var(--text-primary); }
        .pool-disabled-desc { font-size: 12.5px; color: var(--text-muted); margin-top: 4px; max-width: 540px; }
        @media (max-width: 768px) { .pool-metrics-grid { grid-template-columns: repeat(2, 1fr); } .pool-growth-grid { grid-template-columns: repeat(2, 1fr); } }
      `}</style>
    </div>
  );
}
