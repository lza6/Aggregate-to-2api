import { useCallback, useEffect, useState, lazy, Suspense } from 'react';
import { fetchStats, fetchDiagnostics, fetchRoutingRecords, fetchSystemSpec, fetchChatUsage, fetchChatRemaining, fetchChatAuthStatus, getStoredApiKey, fetchAccountPool, notify } from '../api';
import { StatCard } from '../components/StatCard';
import { ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { Stats, Diagnostics, RoutingRecord, RoutingNode, SystemSpec, ChatUsageStats, ChatRemaining, ChatAuthStatus, AccountPoolResponse } from '../api';

const PWD_KEY = 'galleryPwd';

declare global { interface Window { __galleryChangePassword?: (pwd: string) => void } }

// P3-6: Gallery 亦为懒加载（图片列表较重），与 recharts 一并拆出主包
const LazyGallery = lazy(() => import('../components/Gallery').then(m => ({ default: m.Gallery })));

// P3-6: recharts 重依赖懒加载 —— 图表仅在数据就绪后按需加载，主包不再静态携带 recharts
const LazyBarChart = lazy(() => import('../components/BarChart').then(m => ({ default: m.BarChart })));

/** Token 数短格式化（82548 -> 82.5K / 1234567 -> 1.2M / 1234567890 -> 1.23B） */
function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0';
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export function Dashboard() {
  const { data: stats, loading, error, reload } = useApi<Stats>(() => fetchStats(), { intervalMs: 5000 });
  const { data: diag, error: diagError } = useApi<Diagnostics>(() => fetchDiagnostics(), { intervalMs: 15000 });
  const { data: routingData } = useApi<{ records: RoutingRecord[]; nodes: Record<string, RoutingNode> }>(
    () => fetchRoutingRecords(50),
    { intervalMs: 15000 },
  );
  const { data: sys } = useApi<SystemSpec>(() => fetchSystemSpec(), { intervalMs: 60000 });
  const { data: chatUsage } = useApi<ChatUsageStats>(() => fetchChatUsage('24h'), { intervalMs: 15000 });
  const { data: chatRemaining } = useApi<ChatRemaining>(() => fetchChatRemaining(), { intervalMs: 15000 });
  const { data: authStatus } = useApi<ChatAuthStatus>(() => fetchChatAuthStatus(getStoredApiKey() ? { adminKey: getStoredApiKey() } : undefined), { intervalMs: 30000 });
  // v6.6.0: 号池成本口径（累计消耗获取每张平均成本）——供「成本口径」主卡
  const { data: accountPool } = useApi<AccountPoolResponse>(() => fetchAccountPool({ page: 1, pageSize: 1 }), { intervalMs: 30000 });
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
  const chatModelChart = chatUsage?.by_model?.map(item => ({
    name: item.model.split('/').pop() || item.model,
    value: item.calls,
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
        <div className="dashboard-header-actions">
          {authStatus?.enabled && (
            <span className="tf-badge tf-badge-warning api-key-badge" title="全站写操作需携带此 Key">
              🔑 API Key: <code>{authStatus.key_mask ?? '…'}</code>
              {/* 完整 Key 仅当请求携带管理面 Key（auth/status 被鉴权通过）才返回；匿名只拿 mask */}
              {authStatus.key ? (
                <button
                  type="button"
                  className="api-key-copy"
                  aria-label="复制完整 API Key"
                  onClick={async () => {
                    const full = authStatus.key ?? '';
                    if (!full) { notify('未获取到 Key', 'error'); return; }
                    try {
                      await navigator.clipboard.writeText(full);
                      notify('API Key 已复制到剪贴板', 'success');
                    } catch {
                      notify('复制失败，请手动复制', 'error');
                    }
                  }}
                >📋 复制</button>
              ) : null}
            </span>
          )}
          <button onClick={reload} className="tf-btn tf-btn-secondary">
            <span>🔄</span> 刷新数据
          </button>
        </div>
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
          label="base64 缓存"
          value={stats?.base64_gc ? `${stats.base64_gc.total_files} 文件 / ${stats.base64_gc.total_gb.toFixed(2)} GB` : '-'}
          sub={stats?.base64_gc ? `热 ${stats.base64_gc.hot_files} · 冷 ${stats.base64_gc.cold_files} · 配额 ${stats.base64_gc.usage_pct}%` : undefined}
          icon="🧊"
        />
        <StatCard
          label="待清理"
          value={stats?.base64_gc ? `${stats.base64_gc.pending_cleanup_count} 个` : '-'}
          sub={stats?.base64_gc ? `预计释放 ${stats.base64_gc.pending_cleanup_gb.toFixed(2)} GB` : undefined}
          color={stats?.base64_gc && stats.base64_gc.pending_cleanup_count > 0 ? 'var(--warning, #e0a800)' : 'var(--success)'}
          icon="🗑️"
        />
        <StatCard
          label="Worker 集群健康"
          value={diag ? `${diag.workers.alive} / ${diag.workers.total}` : '…'}
          color={diag && diag.workers.stale_count > 0 ? 'var(--danger)' : 'var(--success)'}
          sub={diag && diag.workers.stale_count > 0 ? `⚠ ${diag.workers.stale_count} 个节点失联` : '所有 Worker 存活'}
          icon="🩺"
        />
        <StatCard
          label="出图成本口径"
          value={accountPool?.cost_summary ? `${accountPool.cost_summary.total_credits_used} 分` : '-'}
          sub={accountPool?.cost_summary
            ? `累计 ${accountPool.cost_summary.total_images_used} 张 · 均 ${accountPool.cost_summary.avg_cost_per_image != null ? accountPool.cost_summary.avg_cost_per_image + ' 分/张' : '—'} · ${accountPool.cost_summary.accounts_with_usage}/${accountPool.cost_summary.total_accounts} 账号出图`
            : '号池无出图数据'}
          color="var(--primary-600)"
          icon="💰"
        />
      </div>

      {/* AI 聊天服务 */}
      <div className="section-block">
        <div className="section-header">
          <div>
            <h2 className="section-title">💬 AI 聊天服务</h2>
            <span className="section-sub">聊天调用、Token 消耗与实时额度概览</span>
          </div>
        </div>
        <div className="stats-grid">
          <StatCard label="聊天调用（24h）" value={chatUsage?.total_calls ?? '-'} icon="💬" />
          <StatCard
            label="Token 消耗（24h）"
            value={chatUsage ? formatTokens(chatUsage.prompt_tokens + chatUsage.completion_tokens + chatUsage.reasoning_tokens) : '-'}
            sub={chatUsage ? `推理 ${formatTokens(chatUsage.reasoning_tokens)}` : undefined}
            icon="📝"
          />
          <StatCard
            label="当前可用额度"
            value={chatRemaining?.remaining ?? '-'}
            sub={chatRemaining ? `${chatRemaining.available_proxies} 个出口 × ${chatRemaining.calls_per_proxy_per_hour}/时` : undefined}
            color={chatRemaining ? (chatRemaining.remaining > 0 ? 'var(--success)' : 'var(--danger)') : undefined}
            icon="🔋"
          />
          <StatCard label="工具调用（24h）" value={chatUsage?.tool_calls ?? '-'} icon="🔧" />
          <StatCard
            label="成本（24h）"
            value={chatUsage ? `$${(chatUsage.cost_usd ?? 0).toFixed(4)}` : '-'}
            sub={chatUsage ? `今日 $${(chatUsage.today_cost_usd ?? 0).toFixed(4)}` : undefined}
            icon="💰"
          />
        </div>
      </div>
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
      {dailyChart.length > 0 ? (
        <div className="section-block">
          <Suspense fallback={<div className="chart-fallback">图表加载中…</div>}>
            <LazyBarChart data={dailyChart} title="近 14 日出图总量趋势" height={230} />
          </Suspense>
        </div>
      ) : (
        <div className="section-block tf-card empty-chart-placeholder">
          <div className="empty-state">
            <span className="empty-icon">📊</span>
            <p className="empty-text">暂无趋势数据</p>
            <span className="empty-hint">生成作品后，出图趋势将在此展示</span>
          </div>
        </div>
      )}

      {chatModelChart.length > 0 && (
        <div className="section-block">
          <Suspense fallback={<div className="chart-fallback">图表加载中…</div>}>
            <LazyBarChart
              data={chatModelChart}
              title="近 24h 各模型调用分布"
              sub="按聊天模型统计调用次数"
              unit="次"
              metricLabel="调用量"
              height={170}
            />
          </Suspense>
        </div>
      )}

      {/* 服务器规格卡片 (自适应并发) */}
      {sys && (
        <div className="section-block">
          <div className="section-header">
            <div>
              <h2 className="section-title">🖥️ 服务器配置</h2>
              <span className="section-sub">按 CPU/内存自适应算力 —— 高配服务器自动提升并发</span>
            </div>
          </div>
          <div className="sys-grid">
            <div className="sys-card tf-card">
              <div className="sys-head">
                <span className="sys-icon">🧠</span>
                <span className="sys-name">CPU 核心</span>
                <span className="sys-val">{sys.cpu.cores} 核</span>
              </div>
              <div className="sys-sub">架构 · 自动检测</div>
            </div>
            <div className="sys-card tf-card">
              <div className="sys-head">
                <span className="sys-icon">💾</span>
                <span className="sys-name">内存</span>
                <span className="sys-val">{sys.memory.total_gb} GB</span>
              </div>
              <div className="sys-sub">{sys.memory.total_mb} MB</div>
            </div>
            <div className="sys-card tf-card">
              <div className="sys-head">
                <span className="sys-icon">💿</span>
                <span className="sys-name">磁盘</span>
                <span className="sys-val">{sys.disk.free_gb} GB 可用</span>
              </div>
              <div className="sys-sub">共 {sys.disk.total_gb} GB · 已用 {sys.disk.used_gb} GB</div>
            </div>
            <div className="sys-card tf-card">
              <div className="sys-head">
                <span className="sys-icon">⚙️</span>
                <span className="sys-name">并行 Worker</span>
                <span className="sys-val">{sys.adaptive.workers}</span>
              </div>
              <div className="sys-sub">每个 Worker 独立生成通道</div>
            </div>
            <div className="sys-card tf-card">
              <div className="sys-head">
                <span className="sys-icon">🌐</span>
                <span className="sys-name">上游并发上限</span>
                <span className="sys-val">{sys.adaptive.upstream_inflight}</span>
              </div>
              <div className="sys-sub">Upstream max inflight</div>
            </div>
            <div className="sys-card tf-card">
              <div className="sys-head">
                <span className="sys-icon">🪙</span>
                <span className="sys-name">Token 池水位</span>
                <span className="sys-val">{sys.adaptive.token_pool_size}</span>
              </div>
              <div className="sys-sub">预取 turnstile token</div>
            </div>
            <div className="sys-card tf-card">
              <div className="sys-head">
                <span className="sys-icon">🧮</span>
                <span className="sys-name">队列上限</span>
                <span className="sys-val">{sys.adaptive.max_queue.toLocaleString()}</span>
              </div>
              <div className="sys-sub">有界队列最大容量</div>
            </div>
          </div>
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
        <Suspense fallback={<div className="gallery-fallback">作品加载中…</div>}>
          <LazyGallery password={galleryPwd} />
        </Suspense>
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
                {(routingData?.records ?? []).map((r) => {
                  const isRedirected = r.selected_provider !== r.requested_provider;
                  return (
                    <tr key={r.request_id || r.ts}>
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
        .chart-fallback { padding: 40px 0; text-align: center; color: var(--text-muted); font-size: 12.5px; }
        .gallery-fallback { padding: 32px 0; text-align: center; color: var(--text-muted); font-size: 12.5px; }
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

        /* 服务器规格卡片 */
        .sys-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
          gap: 12px;
        }

        .sys-card {
          padding: 14px 16px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-subtle) 100%);
        }

        .sys-head {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .sys-icon { font-size: 16px; }
        .sys-name { font-size: 12.5px; color: var(--text-muted); flex: 1; }
        .sys-val { font-size: 16px; font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }
        .sys-sub { font-size: 11.5px; color: var(--text-muted); }
      `}</style>
    </div>
  );
}
