import { useCallback, useEffect, useState } from 'react';
import { fetchStats, fetchDiagnostics, fetchRoutingRecords } from '../api';
import { StatCard } from '../components/StatCard';
import { BarChart } from '../components/BarChart';
import { Gallery } from '../components/Gallery';
import { ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { Stats, Diagnostics, RoutingRecord, RoutingNode } from '../api';

const PWD_KEY = 'galleryPwd';

// 供 Gallery 组件通过 window 回调通知密码变更（跨组件层传递，避免 prop drilling 改动面扩大）
declare global { interface Window { __galleryChangePassword?: (pwd: string) => void } }

export function Dashboard() {
  const { data: stats, loading, error, reload } = useApi<Stats>(() => fetchStats(), { intervalMs: 5000 });
  const { data: diag, error: diagError } = useApi<Diagnostics>(() => fetchDiagnostics(), { intervalMs: 15000 });
  const { data: routingData } = useApi<{ records: RoutingRecord[]; nodes: Record<string, RoutingNode> }>(
    () => fetchRoutingRecords(50),
    { intervalMs: 15000 },
  );
  const [galleryPwd, setGalleryPwd] = useState<string | undefined>(undefined);

  // P-GALLERY: 刷新后从 sessionStorage 恢复画廊密码（不重输）
  useEffect(() => {
    const stored = sessionStorage.getItem(PWD_KEY);
    if (stored) setGalleryPwd(stored);
    const onChange = (pwd: string) => {
      sessionStorage.setItem(PWD_KEY, pwd);
      setGalleryPwd(pwd);
    };
    window.__galleryChangePassword = onChange;
    return () => { delete window.__galleryChangePassword; };
  }, []);

  const onGalleryFail = useCallback(() => sessionStorage.removeItem(PWD_KEY), []);

  const dailyChart = stats?.daily?.map(d => ({
    name: (d.day ?? '').slice(5),
    value: d.images,
  })) ?? [];

  if (error && !stats) {
    return <ErrorRetry message={error.message} onRetry={reload} />;
  }

  return (
    <div>
      <h1 style={{ margin: '0 0 20px', fontSize: 22 }}>仪表盘</h1>
      <div className="stats-grid">
        <StatCard label="总请求" value={loading && !stats ? '…' : stats?.total_requests ?? '-'} />
        <StatCard label="成功出图" value={stats?.total_images ?? '-'} color="#10b981" />
        <StatCard label="失败" value={stats?.total_errors ?? '-'} color="#ef4444" />
        <StatCard label="运行时长" value={stats?.uptime_human ?? '-'} />
        <StatCard label="当前处理中" value={stats?.processing ?? '-'} />
        <StatCard label="排队中" value={stats?.queued ?? '-'} sub={`容量 ${stats?.queue_capacity ?? '-'}`} />
        <StatCard label="Worker 数" value={diag?.workers?.total ?? stats?.workers ?? '-'} />
        <StatCard label="求解器状态" value={stats?.solver?.status ?? '-'} color={stats?.solver?.status === 'ok' ? '#10b981' : '#ef4444'} />
        {/* S-7: Worker 健康卡（stale 高亮红色）*/}
        <StatCard label="Worker 健康"
          value={diag ? `${diag.workers.alive}/${diag.workers.total}` : '…'}
          color={diag && diag.workers.stale_count > 0 ? '#ef4444' : '#10b981'}
          sub={diag && diag.workers.stale_count > 0 ? `⚠ ${diag.workers.stale_count} 个卡死` : '全部存活'} />
      </div>
      {diagError && (
        <div style={{ marginTop: 8, fontSize: 12, color: '#f59e0b' }}>
          诊断数据获取失败（不影响主面板）: {diagError.message}
        </div>
      )}
      {diag && diag.workers.stale_count > 0 && (
        <div style={{ marginTop: 10, padding: '10px 14px', borderRadius: 8, background: 'rgba(239,68,68,.12)', border: '1px solid rgba(239,68,68,.5)', color: '#ef4444', fontSize: 13 }}>
          ⚠️ {diag.workers.stale_count} 个 worker 超期未活跃（id: {diag.workers.stale_ids.join(', ')}）——请检查上游是否卡死
        </div>
      )}
      {dailyChart.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <BarChart data={dailyChart} title="近 14 日出图量" height={220} />
        </div>
      )}
      <div style={{ marginTop: 20 }} data-gallery-fail={onGalleryFail}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>最近作品</h2>
        <Gallery password={galleryPwd} />
      </div>
      {/* v3.2: 自适应路由记录（MAB-EWMA 引擎决策展示）*/}
      <div style={{ marginTop: 28 }}>
        <h2 style={{ fontSize: 18, marginBottom: 4 }}>🔄 智能路由</h2>
        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
          每次请求由 MAB-EWMA 引擎结合成功率、时延、负载实时打分路由到最优 provider
        </div>
        {routingData?.nodes && Object.keys(routingData.nodes).length > 0 && (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
            {Object.values(routingData.nodes).map(n => (
              <div key={n.provider_id} style={{ background: '#fff', border: '1px solid #d1d5e0', borderRadius: 10, padding: '8px 12px', fontSize: 12, minWidth: 140 }}>
                <div style={{ fontWeight: 600 }}>{n.provider_id}
                  <span style={{ marginLeft: 6, fontSize: 11, padding: '1px 6px', borderRadius: 999,
                    background: n.circuit_state === 'OPEN' ? '#fee2e2' : n.circuit_state === 'HALF_OPEN' ? '#fef3c7' : '#d1fae5',
                    color: n.circuit_state === 'OPEN' ? '#dc2626' : n.circuit_state === 'HALF_OPEN' ? '#b45309' : '#059669' }}>
                    {n.circuit_state}
                  </span>
                </div>
                <div style={{ color: '#6b7280', marginTop: 2 }}>EWMA {n.ewma_latency_ms}ms · 成功 {n.success_count}/失败 {n.failure_count} · 在途 {n.in_flight_requests}</div>
                <div style={{ color: '#6b8aff', fontWeight: 600 }}>评分 {n.score}</div>
              </div>
            ))}
          </div>
        )}
        <div className="table-wrap" style={{ overflowX: 'auto', background: '#fff', borderRadius: 12, border: '1px solid #d1d5e0' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr>
                <th>时间</th><th>请求</th><th>模型</th><th>请求源</th><th>路由到</th><th>评分</th><th>延迟</th><th>原因</th>
              </tr>
            </thead>
            <tbody>
              {(routingData?.records ?? []).map((r, i) => (
                <tr key={i}>
                  <td style={{ fontSize: 11, color: '#6b7280' }}>{new Date(r.ts * 1000).toLocaleTimeString()}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{r.request_id ? r.request_id.slice(0, 8) : '-'}</td>
                  <td>{r.model}</td>
                  <td>{r.requested_provider}</td>
                  <td>
                    <span style={{
                      padding: '1px 7px', borderRadius: 999, fontSize: 11, fontWeight: 600,
                      background: r.selected_provider === r.requested_provider ? '#d1fae5' : '#fef3c7',
                      color: r.selected_provider === r.requested_provider ? '#059669' : '#b45309',
                    }}>
                      {r.selected_provider}
                      {r.selected_provider !== r.requested_provider && ' ⚠'}
                    </span>
                  </td>
                  <td>{r.score}</td>
                  <td>{r.latency_ms ? `${r.latency_ms}ms` : '-'}</td>
                  <td style={{ fontSize: 11 }}>{r.reason}</td>
                </tr>
              ))}
              {!routingData?.records?.length && (
                <tr><td colSpan={8} style={{ color: '#9aa1b2', textAlign: 'center', padding: 14 }}>暂无路由记录 —— 有请求经路由引擎处理后显示在这里</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <style>{`
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
        @media (max-width: 600px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
        @media (prefers-color-scheme: dark) {
          .table-wrap { background: #1e2132; border-color: #2d3050; }
          tr { border-color: #2d3050; }
          td { border-color: #2d3050; }
        }
      `}</style>
    </div>
  );
}
