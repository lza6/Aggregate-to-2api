// v12.0.1：节点展示升级为 SVG 分层 DAG 图 + 推理轨迹面板（components/DagGraph.tsx）。
// 复用现有轮子：useApi（轮询/竞态/防抖）+ EmptyState/ErrorRetry/Skeleton + Toast。
import { useState } from 'react';
import { DagGraph, statusColor, statusLabel } from '../components/DagGraph';
import { EmptyState } from '../components/EmptyState';
import { Skeleton, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import { notify } from '../api/core';
import {
  getDagRun,
  listDagRuns,
  planDag,
  runDag,
  type DagPlanResult,
  type DagRunPublic,
} from '../api/agent';

function fmtTime(ts: number | null): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

function RunCard({ run }: { run: DagRunPublic }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={`dag-run-card ${run.status}`}>
      <button
        type="button"
        className="dag-run-head"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
      >
        <span className="dag-run-name">{run.name}</span>
        <span className="dag-run-status" style={{ color: statusColor(run.status) }}>
          {statusLabel(run.status)}
        </span>
        <span className="dag-run-time">{fmtTime(run.created_at)}</span>
        <span className="dag-run-toggle" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
      </button>
      {expanded && (
        <div className="dag-run-detail">
          {run.error_summary && <div className="dag-run-error">run 异常：{run.error_summary.slice(0, 300)}</div>}
          <DagGraph nodes={run.nodes} />
        </div>
      )}
    </div>
  );
}

export function AgentPage() {
  const [prompt, setPrompt] = useState('');
  const [planning, setPlanning] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [plan, setPlan] = useState<DagPlanResult | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  // 轮询当前 run 状态（5s；终态后停止由 useApi 仅在有 run 时开启 intervalMs=0 → 手动 reload）
  const run = useApi<DagRunPublic | null>(
    () => (activeRunId ? getDagRun(activeRunId) : Promise.resolve(null)),
    { intervalMs: activeRunId ? 3000 : 0, immediate: !!activeRunId },
  );
  // 历史列表（15s 轮询，刷新不丢）
  const history = useApi(() => listDagRuns({ limit: 10 }), { intervalMs: 15000 });

  const currentRun = run.data;
  const isTerminal = currentRun ? ['succeeded', 'failed'].includes(currentRun.status) : true;

  async function handlePlan() {
    if (!prompt.trim()) {
      notify('请先输入任务描述', 'error');
      return;
    }
    setPlanning(true);
    try {
      const p = await planDag(prompt.trim());
      setPlan(p);
      if (!p.meta.valid) notify('规划器返回了不合法节点，仍可手动提交', 'info');
      else notify(`规划完成：${p.nodes.length} 个节点（${p.meta.mock ? '规则规划' : 'LLM 规划'}）`, 'success');
    } catch (e) {
      notify(e instanceof Error ? e.message : '规划失败', 'error');
    } finally {
      setPlanning(false);
    }
  }

  async function handleSubmit() {
    if (!plan || !plan.nodes.length) {
      notify('请先规划出节点再提交', 'error');
      return;
    }
    setSubmitting(true);
    try {
      const res = await runDag({ name: prompt.trim().slice(0, 64) || 'DAG 任务', nodes: plan.nodes });
      setActiveRunId(res.run_id);
      setPlan(null);
      notify(`已提交 DAG（${res.run_id}），后台执行中`, 'success');
      run.reload();
    } catch (e) {
      notify(e instanceof Error ? e.message : '提交失败', 'error');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="agent-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">智能体 DAG 编排</h1>
          <p className="page-subtitle">用一句话描述任务，自动拆解为多步节点并串行/并行执行</p>
        </div>
        <span className="boundary-pill" title="DAG 编排公益开放；写操作（清空历史等）需管理 Key">
          <span className="boundary-dot" aria-hidden="true" />
          公益开放
        </span>
      </div>

      <div className="dag-composer">
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="例如：画一张电商主图，并对成品做质量终检"
          rows={3}
          aria-label="任务描述"
        />
        <div className="dag-composer-actions">
          <button type="button" className="tf-btn tf-btn-primary" onClick={handlePlan} disabled={planning || submitting}>
            {planning ? '规划中…' : '生成计划'}
          </button>
          <button type="button" className="tf-btn tf-btn-secondary" onClick={handleSubmit} disabled={!plan || submitting}>
            {submitting ? '提交中…' : '提交执行'}
          </button>
        </div>
      </div>

      {plan && (
        <div className="dag-plan-preview">
          <div className="dag-section-title">
            计划预览（{plan.nodes.length} 节点，{plan.meta.valid ? '✓ 合法' : '✗ 需检查'}，{plan.meta.mock ? '规则规划' : `LLM 规划(${plan.meta.model})`}）
          </div>
          <DagGraph nodes={plan.nodes.map(n => ({ ...n, status: 'pending' }))} />
        </div>
      )}

      {activeRunId && (
        <div className="dag-current-run">
          <div className="dag-section-title">
            当前运行：{activeRunId}{' '}
            {currentRun && <span style={{ color: statusColor(currentRun.status) }}>{statusLabel(currentRun.status)}</span>}
            {!isTerminal && <span className="dag-polling-hint">（每 3s 自动刷新）</span>}
          </div>
          {run.error && !currentRun && <ErrorRetry message={run.error.message} onRetry={run.reload} />}
          {run.loading && !currentRun && <Skeleton lines={3} height={16} />}
          {currentRun && (
            <div className="dag-run-detail">
              {currentRun.error_summary && <div className="dag-run-error">{currentRun.error_summary.slice(0, 300)}</div>}
              <DagGraph nodes={currentRun.nodes} />
            </div>
          )}
        </div>
      )}

      <div className="dag-history">
        <div className="dag-section-title">历史运行</div>
        {history.error && !history.data && <ErrorRetry message={history.error.message} onRetry={history.reload} />}
        {history.loading && !history.data && <Skeleton lines={3} height={16} />}
        {history.data && history.data.items.length === 0 && (
          <EmptyState text="还没有 DAG 运行记录" hint="在上方输入任务并提交第一个编排" />
        )}
        {history.data?.items.map(run => <RunCard key={run.run_id} run={run} />)}
      </div>
    </div>
  );
}
