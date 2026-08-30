import { useMemo } from 'react';
import { fetchAiEcosystem } from '../api';
import type { AiEcosystemResponse, AiEcosystemModel, AiEcosystemProvider } from '../api';
import { StatCard } from '../components/StatCard';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';

/** 价格格式化：USD/百万 token → 紧凑展示（0 → "免费"，<1 → 4 位小数） */
function formatPrice(p: number | null | undefined): string {
  if (p == null) return '-';
  if (p === 0) return '免费';
  if (p < 1) return `$${p.toFixed(4)}`;
  return `$${p.toFixed(2)}`;
}

/** 上下文窗口格式化：128K / 1M / 200K */
function formatContext(cw: number | null | undefined): string {
  if (cw == null) return '-';
  if (cw >= 1_000_000) return `${(cw / 1_000_000).toFixed(cw % 1_000_000 === 0 ? 0 : 1)}M`;
  if (cw >= 1000) return `${Math.round(cw / 1000)}K`;
  return String(cw);
}

function statusColor(status: string): string {
  const s = status.toLowerCase();
  if (s === 'operational' || s === 'ok' || s === 'up') return 'var(--success)';
  if (s.includes('degraded') || s.includes('partial')) return 'var(--warning)';
  return 'var(--text-muted)';
}

export function EcosystemPage() {
  const { data, loading, error, reload } = useApi<AiEcosystemResponse>(
    () => fetchAiEcosystem(),
    { intervalMs: 60000 },
  );

  const flatModels = useMemo<{ model: AiEcosystemModel; providerName: string }[]>(() => {
    if (!data?.models?.providers) return [];
    const out: { model: AiEcosystemModel; providerName: string }[] = [];
    for (const p of data.models.providers as AiEcosystemProvider[]) {
      for (const m of p.models ?? []) {
        out.push({ model: m, providerName: p.name || p.id });
      }
    }
    return out;
  }, [data]);

  if (error && !data) return <ErrorRetry message={error.message} onRetry={reload} />;
  if (loading && !data) {
    return (
      <div className="ecosystem-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">AI 生态总览</h1>
            <p className="page-desc">聚合 TensorFeed 公开数据：模型定价、服务状态、今日 AI 简报</p>
          </div>
        </div>
        <div className="stats-grid">
          <Skeleton lines={2} height={90} />
          <Skeleton lines={2} height={90} />
          <Skeleton lines={2} height={90} />
          <Skeleton lines={2} height={90} />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="ecosystem-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">AI 生态总览</h1>
            <p className="page-desc">聚合 TensorFeed 公开数据：模型定价、服务状态、今日 AI 简报</p>
          </div>
        </div>
        <Empty text="暂无 AI 生态数据" hint="上游 TensorFeed 暂未返回数据，请稍后刷新" />
      </div>
    );
  }

  const m = data.models;
  const s = data.status;
  const t = data.today;
  const h = data.health;
  const newsCount = h.news_count ?? 0;

  return (
    <div className="ecosystem-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            AI 生态总览
            {data.stale && <span className="title-badge" style={{ background: 'var(--warning-bg)', color: 'var(--warning-text)', border: '1px solid var(--warning-border)' }}>stale 回退</span>}
          </h1>
          <p className="page-desc">聚合 TensorFeed 公开数据：模型定价、服务状态、今日 AI 简报 · TTL {data.cache.ttl_seconds}s · 每 60s 刷新</p>
        </div>
        <button onClick={reload} className="tf-btn tf-btn-secondary">
          <span>🔄</span> 刷新
        </button>
      </div>

      {/* 顶部 4 个 StatCard */}
      <div className="stats-grid">
        <StatCard
          label="模型总数"
          value={m.available ? m.count : '不可用'}
          sub={m.last_updated ? `上游更新于 ${m.last_updated}` : undefined}
          color="var(--primary-600)"
          icon="🧠"
        />
        <StatCard
          label="服务状态"
          value={s.available ? (s.all_operational ? '全部正常' : `${s.issues.length} 异常`) : '不可用'}
          sub={s.available ? `${s.service_count} 个服务` : undefined}
          color={s.available ? (s.all_operational ? 'var(--success)' : 'var(--warning)') : 'var(--danger)'}
          icon="📡"
        />
        <StatCard
          label="价格更新天数"
          value={m.available ? `${m.providers.length} 提供商` : '-'}
          sub={m.available ? `含 ${m.count} 个模型定价` : undefined}
          icon="💰"
        />
        <StatCard
          label="今日新闻数"
          value={h.available ? newsCount : '-'}
          sub={t.generated_at ? `生成于 ${t.generated_at}` : undefined}
          icon="📰"
        />
      </div>

      {/* 模型定价表 */}
      <div className="section-block">
        <div className="section-header">
          <div>
            <h2 className="section-title">💡 模型定价目录</h2>
            <span className="section-sub">价格单位：USD / 百万 token · 来自 TensorFeed /api/models</span>
          </div>
        </div>
        {m.available && flatModels.length > 0 ? (
          <div className="tf-table-container">
            <div style={{ overflowX: 'auto' }}>
              <table className="tf-table">
                <thead>
                  <tr>
                    <th>模型</th>
                    <th>提供商</th>
                    <th>输入价</th>
                    <th>输出价</th>
                    <th>上下文</th>
                    <th>Tier</th>
                  </tr>
                </thead>
                <tbody>
                  {flatModels.slice(0, 60).map(({ model, providerName }) => (
                    <tr key={`${providerName}/${model.id}`}>
                      <td style={{ fontWeight: 500 }}>{model.name || model.id}</td>
                      <td style={{ color: 'var(--text-secondary)' }}>{providerName}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{formatPrice(model.inputPrice)}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{formatPrice(model.outputPrice)}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary)' }}>{formatContext(model.contextWindow)}</td>
                      <td>
                        {model.tier ? (
                          <span className={`tf-badge ${model.tier?.toLowerCase().includes('free') ? 'tf-badge-success' : 'tf-badge-info'}`}>{model.tier}</span>
                        ) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {flatModels.length > 60 && (
              <div style={{ padding: '10px 16px', fontSize: 12, color: 'var(--text-muted)' }}>仅展示前 60 个模型，共 {flatModels.length} 个</div>
            )}
          </div>
        ) : (
          <div className="tf-card" style={{ padding: 24 }}>
            <Empty text="模型目录不可用" hint="上游 /api/models 暂未返回数据" />
          </div>
        )}
      </div>

      {/* 服务状态灯 */}
      <div className="section-block">
        <div className="section-header">
          <div>
            <h2 className="section-title">🚦 服务状态</h2>
            <span className="section-sub">TensorFeed 各服务实时运行状态 · 来自 /api/status/summary</span>
          </div>
        </div>
        {s.available ? (
          <div className="service-chips">
            {s.services.map((svc) => (
              <span key={svc.name} className="service-chip" style={{ borderColor: statusColor(svc.status) }}>
                <span className="service-dot" style={{ background: statusColor(svc.status) }} />
                {svc.name}
                <span className="service-provider">{svc.provider || '-'}</span>
              </span>
            ))}
          </div>
        ) : (
          <div className="tf-card" style={{ padding: 24 }}>
            <Empty text="服务状态不可用" hint="上游 /api/status/summary 暂未返回数据" />
          </div>
        )}
      </div>

      {/* 今日 AI 简报 */}
      <div className="section-block">
        <div className="section-header">
          <div>
            <h2 className="section-title">📌 今日 AI 简报</h2>
            <span className="section-sub">来自 /api/today · 新闻 / 推理成本 / 热门 namespace</span>
          </div>
        </div>
        {t.available ? (
          <div className="today-grid">
            <div className="tf-card today-card">
              <h3 className="today-card-title">📰 今日新闻（前 3）</h3>
              {t.news.length > 0 ? (
                <ul className="news-list">
                  {t.news.map((n, i) => (
                    <li key={i}>
                      {n.url ? (
                        <a href={n.url} target="_blank" rel="noopener noreferrer" className="news-link">
                          {n.title || '(无标题)'} <span className="news-source">{n.source ? `· ${n.source}` : ''}</span>
                        </a>
                      ) : (
                        <span>{n.title || '(无标题)'} <span className="news-source">{n.source ? `· ${n.source}` : ''}</span></span>
                      )}
                    </li>
                  ))}
                </ul>
              ) : <Empty text="暂无新闻" />}
            </div>
            <div className="tf-card today-card">
              <h3 className="today-card-title">🧮 推理成本</h3>
              <div className="inference-rows">
                <div className="metric-row"><span className="metric-k">最便宜输入</span><span className="metric-v">{formatPrice((t.inference as any)?.cheapest_input)}</span></div>
                <div className="metric-row"><span className="metric-k">最便宜输出</span><span className="metric-v">{formatPrice((t.inference as any)?.cheapest_output)}</span></div>
                <div className="metric-row"><span className="metric-k">最大上下文</span><span className="metric-v">{formatContext((t.inference as any)?.largest_context)}</span></div>
                <div className="metric-row"><span className="metric-k">免费层模型数</span><span className="metric-v">{(t.inference as any)?.free_tier_count ?? '-'}</span></div>
                <div className="metric-row"><span className="metric-k">总模型数</span><span className="metric-v">{(t.inference as any)?.total_models ?? '-'}</span></div>
              </div>
            </div>
            <div className="tf-card today-card">
              <h3 className="today-card-title">🏷️ 热门 Namespace</h3>
              {Array.isArray((t.inference as any)?.top_namespaces) && (t.inference as any).top_namespaces.length > 0 ? (
                <div className="ns-chips">
                  {((t.inference as any).top_namespaces as string[]).map((ns, i) => (
                    <span key={i} className="ns-chip">{ns}</span>
                  ))}
                </div>
              ) : <Empty text="暂无 namespace 数据" />}
            </div>
          </div>
        ) : (
          <div className="tf-card" style={{ padding: 24 }}>
            <Empty text="今日简报不可用" hint="上游 /api/today 暂未返回数据" />
          </div>
        )}
      </div>

      <style>{`
        .ecosystem-container { display: flex; flex-direction: column; gap: 26px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
        .section-block { display: flex; flex-direction: column; gap: 14px; }
        .section-header { display: flex; align-items: center; justify-content: space-between; }
        .section-title { font-size: 17px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.01em; }
        .section-sub { font-size: 12.5px; color: var(--text-muted); margin-top: 2px; display: block; }
        .service-chips { display: flex; flex-wrap: wrap; gap: 10px; }
        .service-chip { display: inline-flex; align-items: center; gap: 8px; background: var(--bg-card); border: 1px solid var(--border-default); padding: 8px 14px; border-radius: var(--radius-full); font-size: 12.5px; color: var(--text-primary); }
        .service-dot { width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 6px currentColor; }
        .service-provider { font-size: 11px; color: var(--text-muted); margin-left: 4px; }
        .today-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
        .today-card { padding: 18px 20px; display: flex; flex-direction: column; gap: 10px; }
        .today-card-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
        .news-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
        .news-list li { font-size: 12.5px; line-height: 1.5; }
        .news-link { color: var(--primary-600); text-decoration: none; }
        .news-link:hover { text-decoration: underline; }
        .news-source { color: var(--text-muted); font-size: 11.5px; }
        .inference-rows { display: flex; flex-direction: column; gap: 6px; border-top: 1px dashed var(--border-default); padding-top: 8px; }
        .metric-row { display: flex; justify-content: space-between; font-size: 12px; }
        .metric-k { color: var(--text-muted); }
        .metric-v { color: var(--text-secondary); font-weight: 500; font-variant-numeric: tabular-nums; }
        .ns-chips { display: flex; flex-wrap: wrap; gap: 8px; }
        .ns-chip { background: var(--primary-50); color: var(--primary-600); border: 1px solid var(--primary-200); padding: 4px 10px; border-radius: var(--radius-full); font-size: 11.5px; }
      `}</style>
    </div>
  );
}
