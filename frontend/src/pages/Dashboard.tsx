import { useCallback, useEffect, useState } from 'react';
import { fetchStats, fetchDiagnostics, fetchRoutingRecords } from '../api';
import { StatCard } from '../components/StatCard';
import { BarChart } from '../components/BarChart';
import { Gallery } from '../components/Gallery';
import { ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { Stats, Diagnostics, RoutingRecord, RoutingNode } from '../api';

const PWD_KEY = 'galleryPwd';

declare global { interface Window { __galleryChangePassword?: (pwd: string) => void } }

export function Dashboard() {
  const { data: stats, loading, error, reload } = useApi<Stats>(() => fetchStats(), { intervalMs: 5000 });
  const { data: diag, error: diagError } = useApi<Diagnostics>(() => fetchDiagnostics(), { intervalMs: 15000 });
  const { data: routingData } = useApi<{ records: RoutingRecord[]; nodes: Record<string, RoutingNode> }>(
    () => fetchRoutingRecords(50),
    { intervalMs: 15000 },
  );
  const [galleryPwd, setGalleryPwd] = useState<string | undefined>(undefined);

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
    <div className="dashboard-container">
      {/* 顶部标题栏 */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            系统总览仪表盘
            <span className="title-badge">实时监控中</span>
          </h1>
          <p className="page-desc">全节点图像生成任务调度、集群负载与核心业务指标一览</p>
        </div>
        <button onClick={reload} className="tf-btn tf-btn-secondary">
          <span>🔄</span> 刷新数据
        </button>
      </div>

      {/* 核心指标卡片矩阵 */}
      <div className="stats-grid">
        <StatCard
          label="总请求数"
          value={loading && !stats ? '…' : stats?.total_requests ?? '-'}
          icon="📈"
        />
        <StatCard
          label="成功出图"
          value={stats?.total_images ?? '-'}
          color="var(--success)"
          icon="🎨"
        />
        <StatCard
          label="生成失败"
          value={stats?.total_errors ?? '-'}
          color="var(--danger)"
          icon="⚠️"
        />
        <StatCard
          label="系统运行时长"
          value={stats?.uptime_human ?? '-'}
          icon="⏱️"
        />
        <StatCard
          label="当前处理中"
          value={stats?.processing ?? '-'}
          icon="⚡"
        />
        <StatCard
          label="队列等待中"
          value={stats?.queued ?? '-'}
          sub={`队列最大容量: ${stats?.queue_capacity ?? '-'}`}
          icon="⏳"
        />
        <StatCard
          label="Worker 总数"
          value={diag?.workers?.total ?? stats?.workers ?? '-'}
          icon="🤖"
        />
        <StatCard
          label="CF 求解器状态"
          value={stats?.solver?.status ?? '-'}
          color={stats?.solver?.status === 'ok' ? 'var(--success)' : 'var(--danger)'}
          icon="🛡️"
        />
        <StatCard
          label="Worker 集群健康"
          value={diag ? `${diag.workers.alive} / ${diag.workers.total}` : '…'}
          color={diag && diag.workers.stale_count > 0 ? 'var(--danger)' : 'var(--success)'}
          sub={diag && diag.workers.stale_count > 0 ? `⚠ ${diag.workers.stale_count} 个节点失联` : '所有 Worker 存活'}
          icon="🩺"
        />
      </div>

      {/* 诊断提示 */}
      {diagError && (
        <div className="diag-notice tf-card">
          <span>ℹ️</span> 诊断指标轮询降级（不影响核心生成）: {diagError.message}
        </div>
      )}

      {diag && diag.workers.stale_count > 0 && (
        <div className="stale-alert tf-card">
          <span className="alert-icon">🚨</span>
          <div className="alert-body">
            <strong>集群异常警告：</strong> 检测到 {diag.workers.stale_count} 个 Worker 节点超过心跳阈值未响应（ID: {diag.workers.stale_ids.join(', ')}），请检查对应上游提供商连接。
          </div>
        </div>
      )}

      {/* 趋势图表区 */}
      {dailyChart.length > 0 && (
        <div className="section-block">
          <BarChart data={dailyChart} title="近 14 日出图总量趋势" height={230} />
        </div>
      )}

      {/* 最近作品预览 */}
      <div className="section-block" data-gallery-fail={onGalleryFail}>
        <div className="section-header">
          <div>
            <h2 className="section-title">🖼️ 最近生成作品</h2>
            <span className="section-sub">实时生成的图片缩略图及耗时元数据</span>
          </div>
        </div>
        <Gallery password={galleryPwd} />
      </div>

      {/* MAB-EWMA 自适应智能路由 */}
      <div className="section-block">
        <div className="section-header">
          <div>
            <h2 className="section-title">🔄 智能调度引擎 (MAB-EWMA)</h2>
            <span className="section-sub">结合各 Provider 实时成功率、滑动时延及在途并发实时权衡打分</span>
          </div>
        </div>

        {routingData?.nodes && Object.keys(routingData.nodes).length > 0 && (
          <div className="router-nodes-grid">
            {Object.values(routingData.nodes).map(n => {
              const isOpen = n.circuit_state === 'OPEN';
              const isHalf = n.circuit_state === 'HALF_OPEN';
              const badgeClass = isOpen ? 'tf-badge-danger' : isHalf ? 'tf-badge-warning' : 'tf-badge-success';

              return (
                <div key={n.provider_id} className="router-node-card tf-card">
                  <div className="node-head">
                    <span className="node-name">{n.provider_id}</span>
                    <span className={`tf-badge ${badgeClass}`}>{n.circuit_state}</span>
                  </div>
                  <div className="node-metrics">
                    <div className="metric-row">
                      <span className="metric-k">滑动时延 (EWMA)</span>
                      <span className="metric-v">{n.ewma_latency_ms}ms</span>
                    </div>
                    <div className="metric-row">
                      <span className="metric-k">成功 / 失败</span>
                      <span className="metric-v">{n.success_count} / {n.failure_count}</span>
                    </div>
                    <div className="metric-row">
                      <span className="metric-k">在途并发 (In-flight)</span>
                      <span className="metric-v">{n.in_flight_requests}</span>
                    </div>
                  </div>
                  <div className="node-score-footer">
                    <span className="score-label">调度综合评分</span>
                    <span className="score-val">{n.score}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="tf-table-container">
          <div style={{ overflowX: 'auto' }}>
            <table className="tf-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>请求 ID</th>
                  <th>请求模型</th>
                  <th>请求源</th>
                  <th>路由分配</th>
                  <th>评分</th>
                  <th>时延</th>
                  <th>路由原因</th>
                </tr>
              </thead>
              <tbody>
                {(routingData?.records ?? []).map((r, i) => {
                  const isRedirected = r.selected_provider !== r.requested_provider;
                  return (
                    <tr key={i}>
                      <td style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                        {new Date(r.ts * 1000).toLocaleTimeString()}
                      </td>
                      <td>
                        <code style={{ fontSize: 11.5, color: 'var(--primary-600)' }}>
                          {r.request_id ? r.request_id.slice(0, 8) : '-'}
                        </code>
                      </td>
                      <td style={{ fontWeight: 500 }}>{r.model}</td>
                      <td style={{ color: 'var(--text-secondary)' }}>{r.requested_provider}</td>
                      <td>
                        <span className={`tf-badge ${isRedirected ? 'tf-badge-warning' : 'tf-badge-success'}`}>
                          {r.selected_provider}
                          {isRedirected && ' ⚡ 智能降级'}
                        </span>
                      </td>
                      <td style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{r.score}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary)' }}>
                        {r.latency_ms ? `${r.latency_ms}ms` : '-'}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.reason}</td>
                    </tr>
                  );
                })}
                {!routingData?.records?.length && (
                  <tr>
                    <td colSpan={8} style={{ textAlign: 'center', padding: '36px 0', color: 'var(--text-muted)' }}>
                      📭 暂无路由记录 —— 发起生图请求后，调度决策流将实时记录于此
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <style>{`
        .dashboard-container {
          display: flex;
          flex-direction: column;
          gap: 28px;
        }

        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
          gap: 14px;
        }

        .diag-notice {
          padding: 10px 16px;
          font-size: 12.5px;
          color: var(--warning-text);
          background: var(--warning-bg);
          border-color: var(--warning-border);
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .stale-alert {
          padding: 14px 18px;
          background: var(--danger-bg);
          border-color: var(--danger-border);
          color: var(--danger-text);
          font-size: 13px;
          display: flex;
          align-items: flex-start;
          gap: 12px;
        }

        .section-block {
          display: flex;
          flex-direction: column;
          gap: 14px;
        }

        .section-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .section-title {
          font-size: 17px;
          font-weight: 600;
          color: var(--text-primary);
          letter-spacing: -0.01em;
        }

        .section-sub {
          font-size: 12.5px;
          color: var(--text-muted);
          margin-top: 2px;
          display: block;
        }

        .router-nodes-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 12px;
        }

        .router-node-card {
          padding: 14px 16px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .node-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .node-name {
          font-size: 13.5px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .node-metrics {
          display: flex;
          flex-direction: column;
          gap: 4px;
          border-top: 1px dashed var(--border-default);
          padding-top: 8px;
        }

        .metric-row {
          display: flex;
          justify-content: space-between;
          font-size: 11.5px;
        }

        .metric-k {
          color: var(--text-muted);
        }

        .metric-v {
          color: var(--text-secondary);
          font-weight: 500;
        }

        .node-score-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding-top: 6px;
          border-top: 1px solid var(--border-subtle);
        }

        .score-label {
          font-size: 11px;
          color: var(--text-muted);
        }

        .score-val {
          font-size: 14px;
          font-weight: 700;
          color: var(--primary-600);
        }
      `}</style>
    </div>
  );
}
