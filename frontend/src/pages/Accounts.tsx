import { useState } from 'react';
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
}

interface AccountPoolData {
  accounts: Record<string, ProviderPoolStats>;
  email_pool: { total_registered: number; by_provider: Record<string, number> };
  items?: AccountItem[];
}

const PROVIDER_META: Record<string, { name: string; note: string }> = {
  nanobanana: { name: 'NanoBanana Pro', note: '每日签到续额（长效号池）' },
};

function PoolCard({ prefix, stats }: { prefix: string; stats: ProviderPoolStats }) {
  const meta = PROVIDER_META[prefix] ?? { name: prefix, note: '' };
  const pct = stats.target > 0 ? Math.min(100, Math.round((stats.ok / stats.target) * 100)) : 0;
  return (
    <div className="pool-card">
      <div className="pool-head">
        <span className="pool-name">{meta.name}</span>
        {!stats.auto_register && <span className="pool-badge" title="自动补号已关闭">自动补号关</span>}
      </div>
      <div className="pool-note">{meta.note}</div>
      <div className="pool-progress-wrap">
        <div className="pool-progress"><div className="pool-progress-fill" style={{ width: `${pct}%` }} /></div>
        <span className="pool-progress-text">{stats.ok} / {stats.target} 可用（{pct}%）</span>
      </div>
      <div className="pool-metrics">
        <div><span className="pm-label">总账号</span><span className="pm-val">{stats.total}</span></div>
        <div><span className="pm-label">可用</span><span className="pm-val ok">{stats.ok}</span></div>
        <div><span className="pm-label">耗尽</span><span className="pm-val bad">{stats.exhausted}</span></div>
        <div><span className="pm-label">注册中</span><span className="pm-val">{stats.registering}</span></div>
        <div><span className="pm-label">总积分</span><span className="pm-val credits">{stats.credits}</span></div>
      </div>
    </div>
  );
}

export function AccountsPage() {
  const { data, loading, error, reload } = useApi<AccountPoolData>(() => fetchAccountPool(), { intervalMs: 10000 });
  const [filter, setFilter] = useState('');

  if (error && !data) return <ErrorRetry message={error.message} onRetry={reload} />;
  if (loading && !data) {
    return (
      <div>
        <h1 style={{ fontSize: 22, marginBottom: 20 }}>号池管理</h1>
        <div className="pool-grid"><Skeleton lines={2} height={130} /></div>
        <PoolStyle />
      </div>
    );
  }

  const entries = Object.entries(data?.accounts ?? {});
  const rawItems = data?.items ?? [];
  const items = filter ? rawItems.filter(i => i.email.toLowerCase().includes(filter.toLowerCase()) || i.status.includes(filter)) : rawItems;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>号池管理</h1>
        <button onClick={reload} className="refresh-btn">🔄 刷新数据</button>
      </div>

      {entries.length === 0 ? (
        <Empty text="号池为空" hint="IF_ACCOUNT_AUTO=1 时启动自动补号" />
      ) : (
        <div className="pool-grid">
          {entries.map(([prefix, stats]) => <PoolCard key={prefix} prefix={prefix} stats={stats} />)}
        </div>
      )}

      {/* ── 账号明细表格 ── */}
      <div className="accounts-detail-card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h3 style={{ fontSize: 16, margin: 0 }}>👤 入池账号活跃明细</h3>
            <span className="badge-count">{rawItems.length} 个账号</span>
          </div>
          <input
            type="text"
            placeholder="🔍 搜索脱敏邮箱/状态…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="search-input"
          />
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="accounts-table">
            <thead>
              <tr>
                <th>脱敏邮箱</th>
                <th>积分</th>
                <th>状态</th>
                <th>入池时间</th>
                <th>上次签到时间</th>
                <th>预计下次签到</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '30px 0', color: '#9aa1b2' }}>
                    📭 暂无入库账号明细（后台持续注册激活中…）
                  </td>
                </tr>
              ) : (
                items.map((it, idx) => {
                  const cTime = it.created_at ? new Date(it.created_at * 1000).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' }) : '—';
                  const chkTime = it.checkin_at ? new Date(it.checkin_at * 1000).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' }) : '尚未签到';
                  let nextChk = '今日已签';
                  if (!it.checkin_at || (Date.now() - it.checkin_at * 1000 > 20 * 3600 * 1000)) {
                    nextChk = '⚡ 待签到 (30分钟内自动触发)';
                  } else {
                    const nextDate = new Date(it.checkin_at * 1000 + 24 * 3600 * 1000);
                    nextChk = nextDate.toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit' }) + ' 之后';
                  }
                  return (
                    <tr key={idx}>
                      <td><code>{it.email}</code></td>
                      <td style={{ color: '#10b981', fontWeight: 600 }}>{it.credits} 分</td>
                      <td>
                        <span className={`status-pill ${it.status === 'ok' ? 'ok' : 'bad'}`}>
                          {it.status === 'ok' ? '正常' : it.status}
                        </span>
                      </td>
                      <td style={{ color: '#6b7280' }}>{cTime}</td>
                      <td style={{ color: '#6b7280' }}>{chkTime}</td>
                      <td style={{ color: nextChk.startsWith('⚡') ? '#10b981' : '#6b7280', fontWeight: nextChk.startsWith('⚡') ? 600 : 400 }}>{nextChk}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {data?.email_pool && (
        <div className="email-pool-card" style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 15, marginBottom: 10 }}>📮 邮箱分配统计</h3>
          <div style={{ fontSize: 13, color: '#4b5563', marginBottom: 8 }}>已向临时邮箱服务分配 <strong>{data.email_pool.total_registered}</strong> 个邮箱用于注册</div>
          {Object.entries(data.email_pool.by_provider ?? {}).map(([prov, n]) => (
            <div key={prov} className="email-row">
              <span>{PROVIDER_META[prov]?.name ?? prov}</span>
              <span>{n} 个</span>
            </div>
          ))}
        </div>
      )}
      <PoolStyle />
    </div>
  );
}

function PoolStyle() {
  return <style>{`
    .pool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; margin-bottom: 20px; }
    .pool-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .pool-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px; }
    .pool-name { font-size: 15px; font-weight: 600; color: #1f2430; }
    .pool-badge { font-size: 11px; background: #fef3c7; color: #b45309; border-radius: 999px; padding: 2px 8px; }
    .pool-note { font-size: 12px; color: #9aa1b2; margin-bottom: 12px; }
    .pool-progress-wrap { margin-bottom: 12px; }
    .pool-progress { height: 8px; background: #e8eaf1; border-radius: 999px; overflow: hidden; }
    .pool-progress-fill { height: 100%; background: linear-gradient(90deg, #6b8aff, #10b981); border-radius: 999px; transition: width .4s; }
    .pool-progress-text { font-size: 12px; color: #6b7280; margin-top: 4px; display: block; }
    .pool-metrics { display: flex; gap: 6px; flex-wrap: wrap; }
    .pool-metrics > div { flex: 1; min-width: 64px; background: #f8f9fc; border-radius: 8px; padding: 8px 10px; text-align: center; }
    .pm-label { display: block; font-size: 11px; color: #9aa1b2; margin-bottom: 2px; }
    .pm-val { font-size: 16px; font-weight: 600; color: #1f2430; }
    .pm-val.ok { color: #10b981; }
    .pm-val.bad { color: #ef4444; }
    .pm-val.credits { color: #6b8aff; }
    .refresh-btn { background: #fff; border: 1px solid #d1d5e0; padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 500; color: #374151; transition: all 0.2s; }
    .refresh-btn:hover { background: #f9fafb; border-color: #9ca3af; }
    .accounts-detail-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 20px; margin-top: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }
    .badge-count { font-size: 12px; background: #e0e7ff; color: #4338ca; padding: 2px 8px; border-radius: 999px; font-weight: 600; }
    .search-input { padding: 6px 12px; border: 1px solid #d1d5e0; border-radius: 8px; font-size: 13px; outline: none; width: 220px; }
    .search-input:focus { border-color: #6b8aff; }
    .accounts-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .accounts-table th { text-align: left; padding: 10px 8px; border-bottom: 1px solid #e5e7eb; color: #6b7280; font-weight: 500; }
    .accounts-table td { padding: 10px 8px; border-bottom: 1px solid #f3f4f6; color: #1f2430; }
    .accounts-table tr:last-child td { border-bottom: none; }
    .status-pill { font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 600; }
    .status-pill.ok { background: #d1fae5; color: #065f46; }
    .status-pill.bad { background: #fee2e2; color: #991b1b; }
    .email-pool-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 16px; }
    .email-row { display: flex; justify-content: space-between; font-size: 13px; padding: 6px 0; border-bottom: 1px dashed #e8eaf1; color: #374151; }
    .email-row:last-child { border-bottom: none; }
    @media (prefers-color-scheme: dark) {
      .pool-card, .accounts-detail-card, .email-pool-card { background: #1e2132; border-color: #2d3050; }
      .pool-progress { background: #2d3050; }
      .pool-metrics > div { background: #252840; }
      .pool-name, .pm-val, .card-header h3, .accounts-table td, .email-row { color: #e1e4ed; }
      .pool-note, .pool-progress-text, .pm-label, .accounts-table th { color: #8b8fa3; }
      .refresh-btn { background: #252840; border-color: #2d3050; color: #e1e4ed; }
      .search-input { background: #252840; border-color: #2d3050; color: #e1e4ed; }
      .accounts-table td { border-bottom-color: #2d3050; }
      .accounts-table th { border-bottom-color: #2d3050; }
    }
  `}</style>;
}

