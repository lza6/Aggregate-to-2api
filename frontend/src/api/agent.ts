// v10.0.0：智能体 DAG 域 API 封装（/v1/agent/dag/* + /v1/agent/plan）。
// 复用 core.ts 的 apiFetch（统一超时/错误/ApiError 契约），零重复实现。
import { apiFetch } from './core';

// ── 类型（对齐后端 public_state 契约）────────────────────────
export interface DagNodePublic {
  id: string;
  kind: 'llm' | 'critic' | 'tool' | 'memory' | 'scene' | string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped' | string;
  depends_on: string[];
  prompt: string | null;
  model: string | null;
  condition: string | null;
  result: string | null;
  error: string | null;
  attempt: number;
  duration_ms: number;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
}

export interface DagRunPublic {
  run_id: string;
  name: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | string;
  fail_fast: boolean;
  max_parallel: number;
  error_summary: string | null;
  created_at: number;
  finished_at: number | null;
  nodes: DagNodePublic[];
}

export interface DagPlanMeta {
  scene: string;
  mock: boolean;
  llm_used: boolean;
  model: string;
  valid: boolean;
}

export interface DagPlanResult {
  nodes: DagNodePublic[];
  meta: DagPlanMeta;
}

export interface DagNodeInput {
  id: string;
  kind: string;
  depends_on?: string[];
  prompt?: string | null;
  model?: string | null;
  retry?: number;
}

export interface DagRunRequest {
  name: string;
  nodes: DagNodeInput[];
  fail_fast?: boolean;
  max_parallel?: number;
  retry?: number;
}

export interface DagRunListResponse {
  items: DagRunPublic[];
  count: number;
}

/** 提交 DAG run（返回 run_id；后台异步执行） */
export async function runDag(req: DagRunRequest): Promise<{ run_id: string; status: string }> {
  return apiFetch<{ run_id: string; status: string }>('/v1/agent/dag/run', {
    method: 'POST',
    body: JSON.stringify(req),
    caller: '提交 DAG 编排失败',
  });
}

/** 查询单个 run 终态/中间态（含每节点） */
export async function getDagRun(runId: string): Promise<DagRunPublic> {
  return apiFetch<DagRunPublic>(`/v1/agent/dag/${encodeURIComponent(runId)}`, {
    caller: '查询 DAG 运行状态失败',
  });
}

/** v13 P0-7：续跑非终态/failed/skipped 节点（幂等；开关 IF_DAG_RESUME_ENABLED=0 时后端 404） */
export async function resumeDag(
  runId: string,
): Promise<{ run_id: string; status: string; resumed: boolean }> {
  return apiFetch<{ run_id: string; status: string; resumed: boolean }>(
    `/v1/agent/dag/${encodeURIComponent(runId)}/resume`,
    { method: 'POST', caller: 'DAG 续跑触发失败' },
  );
}

/** 历史 run 列表（最近在前；可 status 过滤） */
export async function listDagRuns(params?: { limit?: number; status?: string }): Promise<DagRunListResponse> {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.status) q.set('status', params.status);
  const qs = q.toString();
  return apiFetch<DagRunListResponse>(`/v1/agent/dag${qs ? `?${qs}` : ''}`, { caller: '加载 DAG 历史失败' });
}

/** 自然语言 → DAG 节点（LLM 规划器，Mock 优先） */
export async function planDag(prompt: string, scene?: string): Promise<DagPlanResult> {
  return apiFetch<DagPlanResult>('/v1/agent/dag/plan', {
    method: 'POST',
    body: JSON.stringify({ prompt, scene: scene ?? undefined }),
    caller: '生成 DAG 计划失败',
  });
}

// ── B2/P0-1 技能沉淀（/v1/agent/skills/save-from-run + /v1/agent/my-skills）──
export interface SkillSaveRequest {
  run_id?: string;
  name: string;
  description?: string;
  prompt_template: string;
  params?: Record<string, unknown>;
  notes?: string;
}

export interface SkillPublic {
  id: string;
  name: string;
  description: string;
  status: 'draft' | 'approved' | 'rejected' | string;
  risk_score: number;
  created_at: number;
}

export async function saveSkillFromRun(payload: SkillSaveRequest): Promise<{ ok: boolean; skill: SkillPublic }> {
  return apiFetch('/v1/agent/skills/save-from-run', { method: 'POST', body: JSON.stringify(payload) });
}

export async function mySkills(): Promise<{ ok: boolean; count: number; items: SkillPublic[] }> {
  return apiFetch('/v1/agent/my-skills');
}
