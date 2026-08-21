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

interface AccountPoolData {
  accounts: Record<string, ProviderPoolStats>;
  email_pool: { total_registered: number; by_provider: Record<string, number> };
}

const PROVIDER_META: Record<string, { name: string; note: string }> = {
  minimaxh3: { name: 'MiniMax H3', note: '用完即弃 · 自动注册补号' },
  nanobanana: { name: 'NanoBanana Pro', note: '每日签到续额' },
};

function PoolCard({ prefix, stats }: { prefix: string; stats: ProviderPoolStats }) {
  const meta = PROVIDER_META[prefix] ?? { name: prefix, note: '' };
  const pct = stats.target > 0 ? Math.min(100, Math.round((stats.ok / stats.target) * 100)) : 0;
  return (
    <div className="pool-card">
      <div className="pool-head">
        <span className="pool-name">{meta.name}</span>
        {!stats.auto_register && <span className="pool-badge" title="自动补号已关闭（IF_*_AUTOREG=0）">自动补号关</span>}
      </div>
      <div className="pool-note">{meta.note}</div>
      <div className="pool-progress-wrap">
        <div className="pool-progress"><div className="pool-progress-fill" style={{ width: `${pct}%` }} /></div>
        <span className="pool-progress-text">{stats.ok} / {stats.target} 可用（{pct}%）</span>
      </div>
      <div className="pool-metrics">
        <div><span className="pm-label">总数</span><span className="pm-val">{stats.total}</span></div>
        <div><span className="pm-label">可用</span><span className="pm-val ok">{stats.ok}</span></div>
        <div><span className="pm-label">耗尽</span><span className="pm-val bad">{stats.exhausted}</span></div>
        <div><span className="pm-label">注册中</span><span className="pm-val">{stats.registering}</span></div>
        <div><span className="pm-label">总积分</span><span className="pm-val credits">{stats.credits}</span></div>
      </div>
    </div>
  );
}

export function AccountsPage() {
  const { data, loading, error, reload } = useApi<AccountPoolData>(() => fetchAccountPool(), { intervalMs: 15000 });

  if (error && !data) return <ErrorRetry message={error.message} onRetry={reload} />;
  if (loading && !data) {
    return (
      <div>
        <h1 style={{ fontSize: 22, marginBottom: 20 }}>号池管理</h1>
        <div className="pool-grid"><Skeleton lines={2} height={130} /><Skeleton lines={2} height={130} /></div>
        <PoolStyle />
      </div>
    );
  }

  const entries = Object.entries(data?.accounts ?? {});

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>号池管理</h1>
      {entries.length === 0 ? (
        <Empty text="号池为空" hint="IF_ACCOUNT_AUTO=1 时启动自动补号" />
      ) : (
        <div className="pool-grid">
          {entries.map(([prefix, stats]) => <PoolCard key={prefix} prefix={prefix} stats={stats} />)}
        </div>
      )}
      {data?.email_pool && (
        <div className="email-pool-card">
          <h3 style={{ fontSize: 15, marginBottom: 10 }}>📮 邮箱池</h3>
          <div style={{ fontSize: 13, color: '#4b5563', marginBottom: 8 }}>累计注册邮箱 <strong>{data.email_pool.total_registered}</strong> 个</div>
          {Object.entries(data.email_pool.by_provider ?? {}).map(([prov, n]) => (
            <div key={prov} className="email-row">
              <span>{PROVIDER_META[prov]?.name ?? prov}</span>
              <span>{n}</span>
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
    .pool-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 16px; }
    .pool-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px; }
    .pool-name { font-size: 15px; font-weight: 600; }
    .pool-badge { font-size: 11px; background: #fef3c7; color: #b45309; border-radius: 999px; padding: 2px 8px; }
    .pool-note { font-size: 12px; color: #9aa1b2; margin-bottom: 12px; }
    .pool-progress-wrap { margin-bottom: 12px; }
    .pool-progress { height: 8px; background: #e8eaf1; border-radius: 999px; overflow: hidden; }
    .pool-progress-fill { height: 100%; background: linear-gradient(90deg, #6b8aff, #10b981); border-radius: 999px; transition: width .4s; }
    .pool-progress-text { font-size: 12px; color: #6b7280; margin-top: 4px; display: block; }
    .pool-metrics { display: flex; gap: 6px; flex-wrap: wrap; }
    .pool-metrics > div { flex: 1; min-width: 64px; background: #f8f9fc; border-radius: 8px; padding: 8px 10px; text-align: center; }
    .pm-label { display: block; font-size: 11px; color: #9aa1b2; margin-bottom: 2px; }
    .pm-val { font-size: 16px; font-weight: 600; }
    .pm-val.ok { color: #10b981; }
    .pm-val.bad { color: #ef4444; }
    .pm-val.credits { color: #6b8aff; }
    .email-pool-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 16px; }
    .email-row { display: flex; justify-content: space-between; font-size: 13px; padding: 6px 0; border-bottom: 1px dashed #e8eaf1; }
    .email-row:last-child { border-bottom: none; }
    @media (prefers-color-scheme: dark) {
      .pool-card, .email-pool-card { background: #1e2132; border-color: #2d3050; }
      .pool-progress { background: #2d3050; }
      .pool-metrics > div { background: #252840; }
      .pool-note, .pool-progress-text, .pm-label { color: #8b8fa3; }
    }
  `}</style>;
}
