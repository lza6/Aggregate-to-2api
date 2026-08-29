import { useEffect, useState } from 'react';
import { fetchAccountPool } from '../api';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';

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
  // v6.3.4/v6.5.0: 签到画像与存活天数
  checkin_total?: number;
  checkin_cycle_day?: number;
  credits_earned_total?: number;
  next_claim_at?: number | null;
  age_days?: number | null;
  // v6.5.1: 每账号出图消耗画像
  credits_used_total?: number;
  images_used?: number;
  last_used_at?: number | null;
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

interface AccountPoolData {
  accounts: Record<string, ProviderPoolStats>;
  // v6.6.0: 号池补满速率画像（后端字段 growth_stats）
  growth_stats?: {
    total: number;
    new_in_24h: number;
    new_in_7d: number;
    avg_daily_7d: number;
    ok: number;
    target: number;
    gap: number;
    eta_days: number | null;
  };
  // v6.6.0: 成本口径聚合（配合 Dashboard「成本口径」主卡）
  cost_summary?: {
    total_credits_used: number;
    total_images_used: number;
    total_credits_earned: number;
    accounts_with_usage: number;
    total_accounts: number;
    avg_cost_per_image: number | null;
  };
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
// minimaxh3 提供商已下线：前端只展示当前活跃提供商卡片
const ACTIVE_PROVIDERS = new Set(['nanobanana']);

// v6.5.0: 注册阶段中文名（与后端 STAGE_LABELS 对齐）
const STAGE_LABELS_ZH: Record<string, string> = {
  init: '初始化',
  email_allocated: '分配邮箱',
  captcha_solved: '求解验证码',
  verification_sent: '发送验证',
  code_or_link_received: '收取验证链接',
  logged_in: '登录换会话',
  completed: '注册完成',
  failed: '注册失败',
};

function PoolCard({ prefix, stats }: { prefix: string; stats: ProviderPoolStats }) {
  const meta = PROVIDER_META[prefix] ?? { name: prefix, note: '账号生命周期池' };
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

export function AccountsPage() {
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const { data, loading, error, reload } = useApi<AccountPoolData>(
    () => fetchAccountPool({ page, pageSize, search: filter }),
    { intervalMs: 10000 },
  );

  // Hooks 必须在条件 return 之前调用；筛选/页大小变化后回到第一页并刷新
  useEffect(() => {
    setPage(1);
  }, [filter, pageSize]);
  useEffect(() => {
    void reload();
  }, [page, filter, pageSize, reload]);

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
  const pagedItems = data?.items ?? [];

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

      {entries.length === 0 ? (
        <Empty text="号池暂未初始化" hint="开启 IF_ACCOUNT_AUTO=1 后将自动开始账号注册与巡检" />
      ) : (
        <div className="pool-grid">
          {entries.map(([prefix, stats]) => <PoolCard key={prefix} prefix={prefix} stats={stats} />)}
        </div>
      )}

      {/* v6.6.0: 号池补满速率监控（每日新增账号数 + 预计达标天数） */}
      {data?.growth_stats ? (
        <div className="pool-growth-section tf-card">
          <div className="detail-header">
            <div className="detail-title-group">
              <h3 className="detail-title">📈 号池补满速率</h3>
              <span className="tf-badge tf-badge-info">刷新即估</span>
            </div>
            <span className="pool-growth-target">
              目标 {data.growth_stats.ok} / {data.growth_stats.target} 可用
            </span>
          </div>
          <div className="pool-growth-grid">
            <div className="pg-card">
              <span className="pm-label">今日新增</span>
              <span className="pg-val text-primary">{data.growth_stats.new_in_24h}</span>
              <span className="pg-sub">24h 入池账号</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">日均新增</span>
              <span className="pg-val text-primary">{data.growth_stats.avg_daily_7d}</span>
              <span className="pg-sub">近 7 天平均</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">距目标还差</span>
              <span className="pg-val text-warning">{data.growth_stats.gap}</span>
              <span className="pg-sub">还差这么多可用</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">预计达标</span>
              <span className="pg-val">{data.growth_stats.eta_days != null ? `${data.growth_stats.eta_days} 天` : '—'}</span>
              <span className="pg-sub">
                {data.growth_stats.new_in_24h > 0 ? '按今日速率估算' : '新增为 0，暂无法估算'}
              </span>
            </div>
          </div>
          {data.growth_stats.new_in_24h > 0 && data.growth_stats.eta_days != null && data.growth_stats.eta_days > 30 && (
            <div className="pool-growth-hint">
              ⚠ 按当前速率约需 {data.growth_stats.eta_days} 天，久未达标建议调小 IF_REGISTER_COOLDOWN 或补代理池。
            </div>
          )}
        </div>
      ) : null}

      {/* v6.6.0: 成本口径聚合（累计消耗出图 + 平均每张成本） */}
      {data?.cost_summary ? (
        <div className="pool-growth-section tf-card">
          <div className="detail-header">
            <div className="detail-title-group">
              <h3 className="detail-title">💰 成本口径</h3>
              <span className="tf-badge tf-badge-info">号池聚合</span>
            </div>
            <span className="pool-growth-target">
              {data.cost_summary.accounts_with_usage} / {data.cost_summary.total_accounts} 账号有出图
            </span>
          </div>
          <div className="pool-growth-grid">
            <div className="pg-card">
              <span className="pm-label">累计消耗积分</span>
              <span className="pg-val text-danger">{data.cost_summary.total_credits_used}</span>
              <span className="pg-sub">全部账号累计扣减</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">累计出图次数</span>
              <span className="pg-val text-primary">{data.cost_summary.total_images_used}</span>
              <span className="pg-sub">实际生成结果数</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">平均每张成本</span>
              <span className="pg-val">{data.cost_summary.avg_cost_per_image != null ? `${data.cost_summary.avg_cost_per_image} 分/张` : '—'}</span>
              <span className="pg-sub">有出图口径下估算</span>
            </div>
            <div className="pg-card">
              <span className="pm-label">累计获得积分</span>
              <span className="pg-val text-success">{data.cost_summary.total_credits_earned}</span>
              <span className="pg-sub">签到累计入账</span>
            </div>
          </div>
        </div>
      ) : null}

      {/* v6.5.0: 最近一次注册会话阶段画像 + 每阶段耗时 */}
      {data?.live_registration ? (
        <div className="accounts-detail-section tf-card">
          <div className="detail-header">
            <div className="detail-title-group">
              <h3 className="detail-title">🚀 最近一次注册会话（阶段与耗时）</h3>
              <span className="tf-badge tf-badge-info">实时</span>
            </div>
          </div>
          <div className="reg-stage-body">
            <div className="reg-stage-meta">
              <span className="reg-stage-email">{data.live_registration.email || '—'}</span>
              <span className="tf-badge tf-badge-neutral">{data.live_registration.email_source || '来源未知'}</span>
              <span
                className={`tf-badge ${
                  data.live_registration.stage === 'completed'
                    ? 'tf-badge-success'
                    : data.live_registration.stage === 'failed'
                      ? 'tf-badge-danger'
                      : 'tf-badge-warning'
                }`}
              >
                {data.live_registration.stage_label || data.live_registration.stage}
              </span>
            </div>
            {data.live_registration.last_error && (
              <div className="reg-stage-error">⚠ {data.live_registration.last_error.slice(0, 160)}</div>
            )}
            <div className="reg-stage-flow">
              {Object.entries(data.live_registration.stage_durations ?? {}).map(([stage, dur]) => (
                <div key={stage} className="reg-stage-node">
                  <div className="reg-stage-name">{STAGE_LABELS_ZH[stage] ?? stage}</div>
                  <div className="reg-stage-dur">{Number(dur) >= 1 ? `${Number(dur).toFixed(1)}s` : `${(Number(dur) * 1000).toFixed(0)}ms`}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {/* 账号活跃明细 */}
      <div className="accounts-detail-section tf-card">
        <div className="detail-header">
          <div className="detail-title-group">
            <h3 className="detail-title">👤 入池账号活跃明细</h3>
            <span className="tf-badge tf-badge-info">{totalItems} 个账号总数</span>
          </div>
          <div className="detail-search-wrap">
            <input
              type="text"
              placeholder="🔍 搜索脱敏邮箱 / 状态…"
              value={filter}
              onChange={e => setFilter(e.target.value)}
              className="tf-input search-input-styled"
            />
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="tf-table">
            <thead>
              <tr>
                <th>脱敏账号邮箱</th>
                <th>剩余可用积分</th>
                <th>状态</th>
                <th>累计签到</th>
                <th>本轮第几天</th>
                <th>累计获得积分</th>
                <th>累计消耗积分</th>
                <th>出图次数</th>
                <th>存活天数</th>
                <th>入池时间</th>
                <th>上次签到时间</th>
                <th>注册IP</th>
                <th>下次签到窗口</th>
              </tr>
            </thead>
            <tbody>
              {pagedItems.length === 0 ? (
                <tr>
                  <td colSpan={13} style={{ textAlign: 'center', padding: '36px 0', color: 'var(--text-muted)' }}>
                    📭 暂无入库账号明细（后台持续注册激活中…）
                  </td>
                </tr>
              ) : (
                pagedItems.map((it) => {
                  const cTime = it.created_at
                    ? new Date(it.created_at * 1000).toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    : '—';
                  const chkTime = it.checkin_at
                    ? new Date(it.checkin_at * 1000).toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    : '尚未签到';

                  let nextChk = '今日已签';
                  const isPendingCheckin = !it.checkin_at || (Date.now() - (it.checkin_at ?? 0) * 1000 > 20 * 3600 * 1000);
                  if (isPendingCheckin) {
                    nextChk = '⚡ 待签到 (30分钟内自动触发)';
                  } else if (it.checkin_at) {
                    const nextDate = new Date(it.checkin_at * 1000 + 24 * 3600 * 1000);
                    nextChk = nextDate.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) + ' 之后';
                  }

                  return (
                    <tr key={it.email}>
                      <td>
                        <code style={{ fontSize: 12, color: 'var(--primary-600)' }}>{it.email}</code>
                      </td>
                      <td>
                        <span style={{ color: 'var(--success)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                          {it.credits} 分
                        </span>
                      </td>
                      <td>
                        <span className={`tf-badge ${it.status === 'ok' ? 'tf-badge-success' : 'tf-badge-danger'}`}>
                          {it.status === 'ok' ? '正常运行' : it.status}
                        </span>
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}>{it.checkin_total ?? 0} 次</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-muted)' }}>
                        {it.checkin_total && it.checkin_total > 0 ? `${it.checkin_cycle_day ?? 0} / 7` : '—'}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--primary-600)', fontWeight: 500 }}>
                        {it.credits_earned_total ?? 0} 分
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--danger)', fontWeight: 500 }}>
                        {it.credits_used_total ?? 0} 分
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary)' }}>
                        {it.images_used ?? 0} 次
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-muted)' }}>
                        {it.age_days != null ? `${it.age_days} 天` : '—'}
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 11.5 }}>{cTime}</td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 11.5 }}>{chkTime}</td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 11.5 }}>
                        {it.register_ip ? it.register_ip : '—'}
                      </td>
                      <td>
                        <span style={{
                          color: isPendingCheckin ? 'var(--warning-text)' : 'var(--text-secondary)',
                          fontWeight: isPendingCheckin ? 600 : 400,
                          fontSize: 12
                        }}>
                          {nextChk}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 分页控件 */}
        {totalItems > pageSize && (
          <div className="pagination-bar">
            <span className="pagination-info">
              共 {totalItems} 条，第 {safePage}/{totalPages} 页
            </span>
            <div className="pagination-controls">
              <button
                className="tf-btn tf-btn-sm"
                disabled={safePage <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                ◀ 上一页
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter(p => p === 1 || p === totalPages || Math.abs(p - safePage) <= 2)
                .map((p, idx, arr) => (
                  <span key={p} style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
                    {idx > 0 && arr[idx - 1] !== p - 1 ? <span className="pagination-ellipsis">…</span> : null}
                    <button
                      className={`tf-btn tf-btn-sm ${p === safePage ? 'tf-btn-primary' : ''}`}
                      onClick={() => setPage(p)}
                    >
                      {p}
                    </button>
                  </span>
                ))}
              <button
                className="tf-btn tf-btn-sm"
                disabled={safePage >= totalPages}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              >
                下一页 ▶
              </button>
            </div>
            <select
              className="tf-input page-size-select"
              value={pageSize}
              onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
            >
              <option value={10}>10条/页</option>
              <option value={20}>20条/页</option>
              <option value={50}>50条/页</option>
              <option value={100}>100条/页</option>
            </select>
          </div>
        )}

      {/* 临时邮箱池分配统计 */}
      {data?.email_pool && (
        <div className="email-pool-section tf-card">
          <div className="email-pool-header">
            <h3 className="email-pool-title">📮 临时邮箱池分配统计</h3>
            <span className="email-total-tag">注册尝试: {data.email_pool.total_registered} · 成功入池: {data.email_pool.successful_registrations ?? 0} · 失败: {data.email_pool.failed_registrations ?? 0}</span>
          </div>
          <div className="email-providers-list">
            {Object.entries(data.email_pool.by_provider ?? {}).map(([prov, n]) => (
              <div key={prov} className="email-provider-row">
                <span className="ep-name">{PROVIDER_META[prov]?.name ?? prov}</span>
                <span className="ep-count">{n} 个邮箱</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <style>{`
        .accounts-page-container {
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        .pool-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
          gap: 16px;
        }

        .pool-card-modern {
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 14px;
        }

        .pool-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .pool-name {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .pool-prefix-tag {
          font-size: 11px;
          font-family: ui-monospace, monospace;
          color: var(--text-muted);
          margin-left: 6px;
        }

        .pool-note {
          font-size: 12px;
          color: var(--text-muted);
        }

        .pool-progress-section {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .progress-info {
          display: flex;
          justify-content: space-between;
          font-size: 12px;
        }

        .progress-label {
          color: var(--text-secondary);
        }

        .progress-value {
          color: var(--text-primary);
          font-weight: 600;
        }

        .pool-progress-track {
          height: 8px;
          background: var(--bg-subtle);
          border-radius: var(--radius-full);
          overflow: hidden;
        }

        .pool-progress-fill {
          height: 100%;
          background: linear-gradient(90deg, #6366f1 0%, #10b981 100%);
          border-radius: var(--radius-full);
          transition: width 0.5s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .pool-metrics-grid {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 8px;
        }

        .pm-card {
          background: var(--bg-subtle);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          padding: 8px 6px;
          text-align: center;
          display: flex;
          flex-direction: column;
          gap: 3px;
        }

        .pm-label {
          font-size: 10.5px;
          color: var(--text-muted);
        }

        .pm-val {
          font-size: 15px;
          font-weight: 700;
          font-variant-numeric: tabular-nums;
          color: var(--text-primary);
        }

        .text-success { color: var(--success); }
        .text-danger { color: var(--danger); }
        .text-warning { color: var(--warning); }
        .text-primary { color: var(--primary-600); }

        .pool-growth-section {
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 14px;
        }
        .pool-growth-target {
          font-size: 12px;
          color: var(--text-muted);
          font-variant-numeric: tabular-nums;
        }
        .pool-growth-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 8px;
        }
        .pg-card {
          background: var(--bg-subtle);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          padding: 10px 12px;
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .pg-val {
          font-size: 20px;
          font-weight: 700;
          font-variant-numeric: tabular-nums;
          color: var(--text-primary);
        }
        .pg-sub {
          font-size: 10.5px;
          color: var(--text-muted);
        }
        .pool-growth-hint {
          font-size: 12px;
          color: var(--warning-text);
          background: var(--bg-subtle);
          border: 1px dashed var(--warning);
          border-radius: var(--radius-sm);
          padding: 8px 10px;
        }

        .accounts-detail-section {
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .reg-stage-body {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .reg-stage-meta {
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          gap: 10px;
        }
        .reg-stage-email {
          font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
          font-size: 12.5px;
          color: var(--primary-600);
        }
        .reg-stage-error {
          font-size: 12px;
          color: var(--danger);
          background: var(--bg-subtle);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-sm);
          padding: 8px 10px;
          font-family: ui-monospace, monospace;
        }
        .reg-stage-flow {
          display: flex;
          flex-wrap: wrap;
          align-items: stretch;
          gap: 8px;
        }
        .reg-stage-node {
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
          gap: 4px;
          background: var(--bg-subtle);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-sm);
          padding: 8px 12px;
          min-width: 92px;
        }
        .reg-stage-name {
          font-size: 11.5px;
          color: var(--text-secondary);
        }
        .reg-stage-dur {
          font-size: 14px;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
          color: var(--primary-600);
        }

        .detail-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 12px;
        }

        .detail-title-group {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .detail-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .search-input-styled {
          width: 240px;
        }

        .pagination-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 12px;
          margin-top: 4px;
        }

        .pagination-info {
          font-size: 12px;
          color: var(--text-muted);
        }

        .pagination-controls {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .pagination-ellipsis {
          color: var(--text-muted);
          font-size: 13px;
          padding: 0 2px;
        }

        .page-size-select {          width: auto;
          min-width: 100px;
          font-size: 12px;
        }

        .email-pool-section {
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 14px;
        }

        .email-pool-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .email-pool-title {
          font-size: 15px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .email-total-tag {
          font-size: 12px;
          color: var(--text-muted);
        }

        .email-providers-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .email-provider-row {
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          padding: 8px 12px;
          background: var(--bg-subtle);
          border-radius: var(--radius-md);
          color: var(--text-primary);
        }

        @media (max-width: 768px) {
          .pool-metrics-grid {
            grid-template-columns: repeat(2, 1fr);
          }
          .pool-growth-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }
      `}</style>
    </div>
  );
}
