import { useMemo } from 'react';
import { fetchDiagnostics, fetchAccountPool, fetchProxyPool } from '../api';
import { StatCard } from '../components/StatCard';
import { ProxyPoolGeo } from '../components/ProxyPoolGeo';
import { Skeleton, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';

interface PoolScore {
  label: string;
  detail: string;
  score: number;
  max: number;
  level: 'good' | 'warn' | 'bad';
}

function levelOf(score: number, max: number): PoolScore['level'] {
  const ratio = max > 0 ? score / max : 0;
  if (ratio >= 0.6) return 'good';
  if (ratio >= 0.3) return 'warn';
  return 'bad';
}

export function HealthPage() {
  const { data: diag, error: diagError, reload: reloadDiag } = useApi(
    () => fetchDiagnostics(),
    { intervalMs: 15000 },
  );
  const { data: accountData, error: accountError, reload: reloadAccount } = useApi(
    () => fetchAccountPool({ page: 1, pageSize: 1 }),
    { intervalMs: 15000 },
  );
  const { data: proxyData, error: proxyError, reload: reloadProxy } = useApi(
    () => fetchProxyPool({ page: 1, pageSize: 1 }),
    { intervalMs: 15000 },
  );

  // P3-4: 需要地理明细 → 用更大页拉取代理池条目（供 ProxyPoolGeo 聚合）。
  const { data: proxyDetail, error: proxyDetailError, reload: reloadProxyDetail } = useApi(
    () => fetchProxyPool({ page: 1, pageSize: 500 }),
    { intervalMs: 15000 },
  );

  const poolScores = useMemo<PoolScore[]>(() => {
    const scores: PoolScore[] = [];

    // ── Worker 存活（分值 20） ──
    if (diag) {
      const w = diag.workers;
      const workersScore = w.total > 0 ? Math.round((w.alive / w.total) * 20) : 0;
      scores.push({
        label: 'Worker 节点存活',
        detail: `${w.alive} / ${w.total} 存活${w.stale_ids.length ? ` · 失联: ${w.stale_ids.join(', ')}` : ''}`,
        score: workersScore,
        max: 20,
        level: levelOf(workersScore, 20),
      });
    }

    // ── 代理池（分值 20） ──
    if (proxyData) {
      const totalP = proxyData.total || 1;
      const proxyScore = Math.round((proxyData.available / totalP) * 20);
      scores.push({
        label: '出口代理可用',
        detail: `${proxyData.available} 可用 / ${totalP} 总量 · 冷却 ${proxyData.cooldown} · 住宅 ${proxyData.residential} / 免费 ${proxyData.free}`,
        score: proxyScore,
        max: 20,
        level: levelOf(proxyScore, 20),
      });
    }

    // ── 号池（分值 20） ──
    if (accountData) {
      const nb = accountData.accounts?.nanobanana;
      if (nb && nb.target > 0) {
        const accScore = Math.round(Math.min(1, nb.ok / nb.target) * 20);
        scores.push({
          label: '长效号池达标',
          detail: `${nb.ok} 可用 / 目标 ${nb.target} · 额度耗尽 ${nb.exhausted} · 积分池 ${nb.credits}`,
          score: accScore,
          max: 20,
          level: levelOf(accScore, 20),
        });
      } else {
        scores.push({ label: '长效号池', detail: '未配置账号池（不影响基础出图）', score: 0, max: 20, level: 'warn' });
      }
    }

    // ── 求解器（分值 20） ──
    if (diag) {
      const s = diag.solver;
      const band = s.circuit_open ? 0 : s.window_success_rate == null ? 8 : s.window_success_rate >= 0.95 ? 20 : s.window_success_rate >= 0.8 ? 14 : 6;
      scores.push({
        label: 'CF 求解器',
        detail: `${s.status} · 成功率 ${s.window_success_rate != null ? Math.round(s.window_success_rate * 100) + '%' : 'n/a'} · ${s.circuit_open ? '熔断已断开' : s.status === 'ok' ? '链路正常' : '待恢复'}`,
        score: band,
        max: 20,
        level: levelOf(band, 20),
      });
    }

    // ── 磁盘 / 队列 / DB 水位（分值 20） ──
    if (diag) {
      const diskPct = diag.disk.used_percent ?? 0;
      let diskScore = 20;
      if (diskPct > 95) diskScore = 0;
      else if (diskPct > 85) diskScore = 8;
      else if (diskPct > 70) diskScore = 14;
      scores.push({
        label: '磁盘水位',
        detail: `已用 ${diskPct}% · 空闲 ${diag.disk.free_gb ?? '-'}GB${diag.db.size_mb != null ? ` · DB ${diag.db.size_mb}MB` : ''}`,
        score: diskScore,
        max: 20,
        level: levelOf(diskScore, 20),
      });
    }

    return scores;
  }, [diag, proxyData, accountData]);

  const capability = useMemo(() => {
    if (!diag) return null;
    const total = poolScores.reduce((acc, s) => acc + s.max, 0);
    const got = poolScores.reduce((acc, s) => acc + s.score, 0);
    // 额外扣分：队列/慢日志异常
    const q = diag.queue;
    let penalty = 0;
    if (q && q.capacity > 0 && q.queued > q.capacity * 0.9) penalty += 8;
    if (diag.slow_log?.count > 50) penalty += 4;
    const final = Math.max(0, Math.min(100, Math.round((got / Math.max(1, total)) * 100) - penalty));
    return final;
  }, [diag, poolScores]);

  const capabilityLevel = capability == null ? 'bad' : capability >= 70 ? 'good' : capability >= 40 ? 'warn' : 'bad';
  const errors = [diagError, accountError, proxyError, proxyDetailError].filter(Boolean) as Error[];

  if (diagError && !diag) return <ErrorRetry message={diagError.message} onRetry={reloadDiag} />;

  return (
    <div className="health-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">系统健康体检</h1>
          <p className="page-desc">聚合诊断、号池与代理池状态，实时评估「可立即出图能力」</p>
        </div>
        <button className="tf-btn tf-btn-secondary" onClick={() => { reloadDiag(); reloadAccount(); reloadProxy(); reloadProxyDetail(); }}>
          <span>🔄</span> 重新体检
        </button>
      </div>

      {errors.length > 0 && (
        <div className="health-notice tf-card">
          <span>ℹ️</span> {errors.map(e => e.message).join(' · ')}
        </div>
      )}

      {/* 综合评分 */}
      <div className="health-score-card tf-card">
        <div className="score-ring" data-level={capabilityLevel}>
          <span className="score-ring-val">{capability == null ? '—' : capability}</span>
          <span className="score-ring-label">可立即出图能力</span>
        </div>
        <div className="score-summary">
          <h3 className="score-title">
            {capabilityLevel === 'good' ? '🟢 状态良好，可正常出图' : capabilityLevel === 'warn' ? '🟡 有降级项，建议关注' : '🔴 存在可用性风险，请优先处理'}
          </h3>
          <p className="score-sub">
            综合 5 项体检维度（Worker 存活、出口代理、长效号池、CF 求解器、磁盘水位）打分；
            {capability == null ? '数据加载中…' : `当前得分 ${capability}/100`}
          </p>
        </div>
      </div>

      {/* 维度明细 */}
      {!diag ? (
        <div className="health-grid"><Skeleton lines={3} height={90} /><Skeleton lines={3} height={90} /></div>
      ) : (
        <div className="health-grid">
          {poolScores.map((s) => (
            <div key={s.label} className="health-item tf-card">
              <div className="health-item-head">
                <span className="health-item-label">{s.label}</span>
                <span className={`health-item-level tf-badge ${s.level === 'good' ? 'tf-badge-success' : s.level === 'warn' ? 'tf-badge-warning' : 'tf-badge-danger'}`}>
                  {s.level === 'good' ? '正常' : s.level === 'warn' ? '降级' : '异常'}
                </span>
              </div>
              <div className="health-item-detail">{s.detail}</div>
              <div className="health-item-bar">
                <div className="health-item-bar-fill" data-level={s.level} style={{ width: `${Math.max(4, Math.round((s.score / Math.max(1, s.max)) * 100))}%` }} />
              </div>
              <div className="health-item-footer">
                <span>{s.score}/{s.max} 分</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* P3-4: 出口代理地理分布卡片（国家 emoji 分布 + 延迟/状态健康热力图） */}
      {proxyDetail && proxyDetail.items?.length > 0 && (
        <ProxyPoolGeo items={proxyDetail.items} />
      )}

      {/* 队列 / DB / 慢日志速览 */}
      {diag && (
        <div className="stats-grid">
          <StatCard label="队列堆积" value={diag.queue.queued} sub={`容量 ${diag.queue.capacity}`} color="var(--primary-500)" icon="⏳" />
          <StatCard label="处理中" value={diag.queue.processing} icon="⚡" />
          <StatCard label="DB 行数" value={diag.db.rows ?? '-'} sub={diag.db.size_mb != null ? `体积 ${diag.db.size_mb}MB` : undefined} icon="🗄️" />
          <StatCard label="慢请求(窗口内)" value={diag.slow_log?.count ?? '-'} sub={diag.slow_log?.avg_total_ms ? `平均 ${Math.round(diag.slow_log.avg_total_ms)}ms` : undefined} color="var(--warning)" icon="🐌" />
        </div>
      )}

      <style>{`
        .health-page { display: flex; flex-direction: column; gap: 22px; }
        .health-notice { padding: 10px 16px; font-size: 12.5px; color: var(--warning-text); background: var(--warning-bg); border-color: var(--warning-border); display: flex; align-items: center; gap: 8px; }

        .health-score-card { padding: 24px; display: flex; align-items: center; gap: 22px; background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-subtle) 100%); }
        .score-ring { width: 128px; height: 128px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; flex-shrink: 0; }
        .score-ring[data-level='good'] { background: radial-gradient(circle at 30% 30%, rgba(16,185,129,.25) 0%, rgba(16,185,129,.06) 60%), var(--bg-card); box-shadow: 0 0 0 3px var(--success); }
        .score-ring[data-level='warn'] { background: radial-gradient(circle at 30% 30%, rgba(245,158,11,.25) 0%, rgba(245,158,11,.06) 60%), var(--bg-card); box-shadow: 0 0 0 3px var(--warning); }
        .score-ring[data-level='bad'] { background: radial-gradient(circle at 30% 30%, rgba(239,68,68,.25) 0%, rgba(239,68,68,.06) 60%), var(--bg-card); box-shadow: 0 0 0 3px var(--danger); }
        .score-ring-val { font-size: 40px; font-weight: 800; letter-spacing: -0.03em; color: var(--text-primary); font-variant-numeric: tabular-nums; line-height: 1.1; }
        .score-ring-label { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
        .score-summary { display: flex; flex-direction: column; gap: 6px; }
        .score-title { font-size: 17px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.01em; }
        .score-sub { font-size: 12.5px; color: var(--text-muted); line-height: 1.6; }

        .health-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
        .health-item { padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; }
        .health-item-head { display: flex; align-items: center; justify-content: space-between; }
        .health-item-label { font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
        .health-item-detail { font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; word-break: break-all; }
        .health-item-bar { height: 7px; background: var(--bg-subtle); border-radius: var(--radius-full); overflow: hidden; }
        .health-item-bar-fill { height: 100%; border-radius: var(--radius-full); transition: width 0.5s cubic-bezier(0.16,1,0.3,1); }
        .health-item-bar-fill[data-level='good'] { background: linear-gradient(90deg, var(--success), #10b981); }
        .health-item-bar-fill[data-level='warn'] { background: linear-gradient(90deg, var(--warning), #f59e0b); }
        .health-item-bar-fill[data-level='bad'] { background: linear-gradient(90deg, var(--danger), #ef4444); }
        .health-item-footer { display: flex; justify-content: flex-end; font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums; }

        .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
        @media (max-width: 720px) { .health-score-card { flex-direction: column; text-align: center; } }
      `}</style>
    </div>
  );
}
