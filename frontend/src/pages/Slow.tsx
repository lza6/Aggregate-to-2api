import { useMemo } from 'react';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';

// ── 类型：/v1/slow 响应（后端 api/routes/admin.py L573-602）────
interface SlowItem {
  task_id: string;
  model: string;
  provider: string;
  queue_ms: number;
  wait_token_ms: number;
  solve_ms: number;
  upstream_ms: number;
  retry_ms: number;
  total_ms: number;
  slowest_stage: string;
  status: string;
  trace_id: string;
  submit_ms: number;
  poll_ms: number;
  created_at: number;
}

interface SlowStats {
  count: number;
  avg_total_ms: number;
  max_total_ms: number;
  slowest_stage: string | null;
}

interface SlowResponse {
  threshold_ms: number;
  enabled: boolean;
  stats: SlowStats;
  items: SlowItem[];
  count: number;
}

// ── 本地 fetchSlow：不写进 api.ts（该文件正由重构子代理处理，避免冲突）──
async function fetchSlow(limit = 50): Promise<SlowResponse> {
  const res = await fetch(`/v1/slow?limit=${limit}`);
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`慢日志获取失败 HTTP ${res.status}: ${detail.slice(0, 200)}`);
  }
  return res.json();
}

// 分段时间画像：queue/wait_token/solve/upstream/retry/submit/poll 各段的 count/avg/max
const STAGES: { key: keyof SlowItem; label: string; hint: string }[] = [
  { key: 'queue_ms', label: '排队', hint: '入队 → worker 取走' },
  { key: 'wait_token_ms', label: '等待 Token', hint: '取 turnstile token' },
  { key: 'solve_ms', label: 'CF 求解', hint: 'Turnstile 求解耗时' },
  { key: 'upstream_ms', label: '上游调用', hint: '上游提交 + 轮询' },
  { key: 'retry_ms', label: '重试累计', hint: '重试退避累计' },
  { key: 'submit_ms', label: '提交首字节', hint: '上游提交首字节' },
  { key: 'poll_ms', label: '轮询完成', hint: '上游轮询到完成' },
];

interface StageMetric {
  label: string;
  hint: string;
  count: number;
  avg: number;
  max: number;
}

function computeStageMetrics(items: SlowItem[]): StageMetric[] {
  return STAGES.map(({ key, label, hint }) => {
    const vals = items.map(i => Number(i[key]) || 0).filter(v => v > 0);
    const count = vals.length;
    const avg = count ? vals.reduce((a, b) => a + b, 0) / count : 0;
    const max = count ? Math.max(...vals) : 0;
    return { label, hint, count, avg, max };
  });
}

function staleLabel(stage: string | null): string {
  const map: Record<string, string> = {
    queue: '排队', wait_token: '等待 Token', solve: 'CF 求解',
    upstream: '上游调用', retry: '重试累计', submit: '提交首字节',
    poll: '轮询完成', total: '全程',
  };
  return stage ? (map[stage] ?? stage) : '—';
}

function formatMs(v: number): string {
  if (!Number.isFinite(v) || v <= 0) return '—';
  if (v >= 1000) return `${(v / 1000).toFixed(2)}s`;
  return `${Math.round(v)}ms`;
}

function fmtTime(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString();
}

export function SlowPage() {
  const { data, loading, error, reload } = useApi<SlowResponse>(() => fetchSlow(50), { intervalMs: 15000 });

  const stageMetrics = useMemo<StageMetric[]>(() => computeStageMetrics(data?.items ?? []), [data]);
  const items = data?.items ?? [];

  if (error && !data) {
    return (
      <div className="slow-container">
        <div className="page-header">
          <h1 className="page-title">慢请求画像</h1>
        </div>
        <ErrorRetry message={error.message} onRetry={reload} />
      </div>
    );
  }

  return (
    <div className="slow-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            慢请求画像
            <span className="title-badge">阈值 {data ? `${data.threshold_ms}ms` : '…'}</span>
            {data && !data.enabled && <span className="title-badge tf-badge-warning">已禁用</span>}
          </h1>
          <p className="page-desc">
            定位「出图慢在哪」—— 排队 / 等 token / CF 求解 / 上游 / 重试分段耗时（环形缓冲，进程重启即清零）
          </p>
        </div>
        <button onClick={reload} disabled={loading} className="tf-btn tf-btn-secondary">
          <span>🔄</span> 刷新
        </button>
      </div>

      {loading && !data ? (
        <div className="slow-stats-grid"><Skeleton lines={3} height={70} /><Skeleton lines={3} height={70} /><Skeleton lines={3} height={70} /><Skeleton lines={3} height={70} /></div>
      ) : (
        <>
          {/* 总体速览 */}
          <div className="slow-stats-grid">
            <div className="slow-stat tf-card">
              <div className="slow-stat-icon">🐌</div>
              <div className="slow-stat-body">
                <div className="slow-stat-label">窗口内慢请求</div>
                <div className="slow-stat-value">{data?.stats?.count ?? '-'}</div>
                <div className="slow-stat-sub">{data?.count ?? '-'} 条样本</div>
              </div>
            </div>
            <div className="slow-stat tf-card">
              <div className="slow-stat-icon">⏱️</div>
              <div className="slow-stat-body">
                <div className="slow-stat-label">平均总耗时</div>
                <div className="slow-stat-value">{data?.stats?.avg_total_ms ? formatMs(data.stats.avg_total_ms) : '—'}</div>
                <div className="slow-stat-sub">全程 avg</div>
              </div>
            </div>
            <div className="slow-stat tf-card">
              <div className="slow-stat-icon">📈</div>
              <div className="slow-stat-body">
                <div className="slow-stat-label">最慢总耗时</div>
                <div className="slow-stat-value">{data?.stats?.max_total_ms ? formatMs(data.stats.max_total_ms) : '—'}</div>
                <div className="slow-stat-sub">全程 max</div>
              </div>
            </div>
            <div className="slow-stat tf-card">
              <div className="slow-stat-icon">🎯</div>
              <div className="slow-stat-body">
                <div className="slow-stat-label">最慢阶段</div>
                <div className="slow-stat-value">{staleLabel(data?.stats?.slowest_stage ?? null)}</div>
                <div className="slow-stat-sub">瓶颈定位</div>
              </div>
            </div>
          </div>

          {/* 分段时间画像 */}
          <div className="tf-card relative-description">
            <div className="section-header">
              <div>
                <h2 className="section-title">分段时间画像</h2>
                <span className="section-sub">各阶段样本数 / 平均 / 最大（仅有量的阶段计数）</span>
              </div>
            </div>
            <div className="tf-table-container" style={{ border: 'none', boxShadow: 'none' }}>
              <div style={{ overflowX: 'auto' }}>
                <table className="tf-table">
                  <thead>
                    <tr>
                      <th>阶段</th>
                      <th>说明</th>
                      <th style={{ textAlign: 'right' }}>样本数</th>
                      <th style={{ textAlign: 'right' }}>平均 (avg)</th>
                      <th style={{ textAlign: 'right' }}>最大 (max)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stageMetrics.map(s => (
                      <tr key={s.label}>
                        <td style={{ fontWeight: 600 }}>{s.label}</td>
                        <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.hint}</td>
                        <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{s.count}</td>
                        <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{formatMs(s.avg)}</td>
                        <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{formatMs(s.max)}</td>
                      </tr>
                    ))}
                    {!items.length && (
                      <tr>
                        <td colSpan={5} style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
                          暂无慢请求样本
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* 最近慢请求明细 */}
          <div className="tf-card relative-description">
            <div className="section-header">
              <div>
                <h2 className="section-title">最近慢请求明细</h2>
                <span className="section-sub">逆序展示慢样本（最慢在前）</span>
              </div>
            </div>
            <div className="tf-table-container" style={{ border: 'none', boxShadow: 'none' }}>
              <div style={{ overflowX: 'auto' }}>
                <table className="tf-table">
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>任务 ID</th>
                      <th>模型</th>
                      <th>提供商</th>
                      <th style={{ textAlign: 'right' }}>总耗时</th>
                      <th>慢阶段</th>
                      <th>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => (
                      <tr key={it.task_id || it.trace_id || it.created_at}>
                        <td style={{ color: 'var(--text-muted)', fontSize: 11 }}>{fmtTime(it.created_at)}</td>
                        <td>
                          <code style={{ fontSize: 11.5, color: 'var(--primary-600)' }}>
                            {it.task_id ? it.task_id.slice(0, 8) : (it.trace_id ? it.trace_id.slice(0, 8) : '-')}
                          </code>
                        </td>
                        <td style={{ fontWeight: 500 }}>{it.model || '-'}</td>
                        <td style={{ color: 'var(--text-secondary)' }}>{it.provider || '-'}</td>
                        <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{formatMs(it.total_ms)}</td>
                        <td>
                          <span className="tf-badge tf-badge-warning">{staleLabel(it.slowest_stage)}</span>
                        </td>
                        <td>
                          <span className={`tf-badge ${it.status === 'error' ? 'tf-badge-danger' : 'tf-badge-success'}`}>
                            {it.status === 'error' ? '错误' : '成功'}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {!items.length && (
                      <tr>
                        <td colSpan={7} style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
                          📭 暂无慢请求 —— 发人生图请求后，超过阈值的样本将实时记录于此
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {!loading && !items.length && error && (
        <div className="slow-empty-wrap"><Empty text="慢日志暂不可用" hint={error.message} /></div>
      )}
      {!loading && !items.length && !error && data && (
        <div className="slow-empty-wrap"><Empty text="暂无慢请求数据" hint="配置了阈值后，超过阈值的出图请求会自动采样于此" /></div>
      )}

      <style>{`
        .slow-container { display: flex; flex-direction: column; gap: 20px; }
        .slow-stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
        .slow-stat { padding: 16px 18px; display: flex; align-items: center; gap: 14px; }
        .slow-stat-icon { font-size: 22px; flex-shrink: 0; }
        .slow-stat-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
        .slow-stat-label { font-size: 12px; color: var(--text-secondary); font-weight: 500; }
        .slow-stat-value { font-size: 20px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
        .slow-stat-sub { font-size: 11px; color: var(--text-muted); }
        .slow-empty-wrap { margin-top: 8px; }
        .section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
        .section-title { font-size: 15px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.01em; }
        .section-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; display: block; }
        .relative-description { padding: 20px 24px; }
      `}</style>
    </div>
  );
}
