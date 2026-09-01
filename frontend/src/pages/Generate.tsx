import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchImageModels, generateImage, editImage, fetchTask, fetchEditTask, fetchProviders, getStoredApiKey, setStoredApiKey, notify } from '../api';
import { ErrorRetry, type ProviderOption } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { ImageModelInfo, Task } from '../api';

type GenMode = 'txt' | 'img';
type TaskStatus = 'idle' | 'running' | 'done' | 'error';

interface GenState {
  status: TaskStatus;
  task?: Task;
  error?: string;
}

/** 生成错误分级/可行动化提示（P2-4）：把后端高频错误映射成可读 + 可行动文案。 */
function friendlierGenError(raw: unknown): string {
  const msg = (typeof raw === 'string' ? raw : raw instanceof Error ? raw.message : String(raw ?? '')).trim();
  const low = msg.toLowerCase();
  if (low.includes('401') || low.includes('unauthorized') || low.includes('api key')) {
    return 'API Key 未配置或无效 — 请点击右上角「配置 API Key」填入有效 Key（写接口需 Key）。';
  }
  if (low.includes('429') || low.includes('queue_full') || low.includes('queue full') || low.includes('繁忙')) {
    return '当前上游繁忙或队列已满 — 已自动切换备用引擎，请稍后重试或调大调小并发。';
  }
  if (low.includes('限流') || low.includes('rate')) {
    return '触发限流 — 请降低请求频率后重试。';
  }
  if (low.includes('403') || low.includes('forbidden')) {
    return '请求被拒绝（403）— 请检查 API Key 权限或调用频率。';
  }
  if (low.includes('timeout') || low.includes('超时')) {
    return '上游超时 — 已自动切换备用引擎，请稍后重试。';
  }
  return msg || '生成失败，请稍后重试。';
}

const ASPECT_OPTIONS = ['1:1', '3:4', '4:3', '9:16', '16:9', '3:2', '2:3', '21:9'];
const RES_OPTIONS = ['1K', '2K', '4K', '480p', '720p'];

/** 把 DataURL / 文件转成 base64 data URI（图生图输入） */
function fileToDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export function GeneratePage() {
  const { data: modelsData, loading, error, reload } = useApi<{ items: Record<string, ImageModelInfo[]>; count: number }>(fetchImageModels);
  // D1: 拉取 providers 列表，429/502 错误时渲染「一键切备用 provider」行动。
  const { data: providersData } = useApi(() => fetchProviders());
  const [mode, setMode] = useState<GenMode>('txt');
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('');
  const [aspect, setAspect] = useState('1:1');
  const [resolution, setResolution] = useState('1K');
  const [apiKey, setApiKey] = useState(getStoredApiKey);
  const [showKeyPanel, setShowKeyPanel] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [genState, setGenState] = useState<GenState>({ status: 'idle' });
  const [editImages, setEditImages] = useState<{ name: string; data: string }[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  // 生图模型（含 txt2img）/ 图生图模型（含 img2img）
  const txtModels = useMemo(() => flatModels(modelsData?.items, 'txt2img'), [modelsData]);
  const imgModels = useMemo(() => flatModels(modelsData?.items, 'img2img'), [modelsData]);
  const activeModels = mode === 'txt' ? txtModels : imgModels;

  const clearPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
  }, []);

  useEffect(() => clearPoll, [clearPoll]);

  // 默认选中第一个可用模型
  useEffect(() => {
    if (!model && activeModels.length > 0) setModel(activeModels[0].id);
    if (model && !activeModels.some(m => m.id === model)) setModel(activeModels[0]?.id ?? '');
  }, [activeModels, model]);

  const startPoll = useCallback((taskId: string, edit: boolean) => {
    clearPoll();
    const poll = async () => {
      try {
        let t: Task;
        if (edit) t = await fetchEditTask(taskId);
        else t = await fetchTask(taskId);
        if (t.status === 'completed' || t.status === 'error') {
          clearPoll();
          if (t.status === 'completed') {
            notify('生成完成', 'success');
            setGenState({ status: 'done', task: t });
          } else {
            notify('生成失败', 'error');
            setGenState({ status: 'error', error: t.error ?? undefined, task: t });
          }
        } else {
          setGenState({ status: 'running', task: t });
        }
      } catch (e) {
        // 轮询失败不中断，等下一轮
      }
    };
    void poll();
    pollRef.current = setInterval(poll, 4000);
  }, [clearPoll]);

  /** 文生图走每任务 SSE（/v1/tasks/{id}/events，无鉴权，浏览器可直接 EventSource）。
   *  终态 result/error 到达后拉一次完整任务（补 model/duration_sec/image_url 字段展示）再关流。
   *  若流意外断开且任务仍未终态 → 回退 4s 轮询兜底（保持既有能力）。
   */
  const startTxtSse = useCallback((taskId: string) => {
    clearPoll();
    const es = new EventSource(`/v1/tasks/${taskId}/events`);
    sseRef.current = es;
    const close = () => { es.close(); if (sseRef.current === es) sseRef.current = null; };
    es.onmessage = () => {/* ping/保活事件忽略 */};
    es.addEventListener('result', () => {
      void fetchTask(taskId).then((t) => {
        clearPoll();
        setGenState({ status: 'done', task: t });
        notify('生成完成', 'success');
      }).catch(() => { clearPoll(); }).finally(close);
    });
    es.addEventListener('error', (ev) => {
      const raw = (ev as MessageEvent).data ?? '';
      void fetchTask(taskId).then((t) => {
        clearPoll();
        const msg = friendlierGenError(t.error || raw);
        setGenState({ status: 'error', error: msg, task: t });
        notify(msg, 'error');
      }).catch(() => {
        clearPoll();
        setGenState({ status: 'error', error: friendlierGenError(raw) });
      }).finally(close);
    });
    es.onerror = () => {
      // P2-2: SSE 断线显式提示（网络抖动/服务端关流），并主动查一次任务状态：
      // 已终态则收尾，未终态则转轮询兜底（保持既有能力）。
      notify('任务事件流已断开，正在恢复…', 'info');
      void fetchTask(taskId).then((t) => {
        clearPoll();
        if (t.status === 'completed' || t.status === 'error') {
          if (t.status === 'completed') { setGenState({ status: 'done', task: t }); notify('生成完成', 'success'); }
          else { setGenState({ status: 'error', error: t.error ?? undefined, task: t }); notify(t.error ?? '生成失败', 'error'); }
          close();
        } else {
          // 未终态：回退轮询（startPoll 内部会 clearPoll）
          notify('已切换为轮询查询任务进度', 'info');
          startPoll(taskId, false);
        }
      }).catch(() => { close(); });
    };
  }, [clearPoll, startPoll]);

  const handleGenerate = useCallback(async () => {
    const text = prompt.trim();
    if (!text) { notify('请输入提示词', 'error'); return; }
    if (!model) { notify('请选择模型', 'error'); return; }
    if (genState.status === 'running') { notify('任务进行中，请等待完成', 'info'); return; }
    if (mode === 'img' && editImages.length === 0) { notify('图生图需先上传/粘贴一张或多张参考图', 'error'); return; }

    setGenState({ status: 'running' });
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      if (mode === 'txt') {
        const t = await generateImage({ prompt: text, aspect_ratio: aspect, model, resolution, download: false }, controller.signal);
        if (t.status === 'completed') {
          notify('生成完成', 'success');
          setGenState({ status: 'done', task: t });
        } else {
          // v6.6.0: 文生图优先走每任务 SSE；若事件流未消费到终态，es.onerror 会回退到轮询。
          setGenState({ status: 'running', task: t });
          startTxtSse(t.id);
        }
      } else {
        const images = editImages.map(im => im.data);
        const t = await editImage({ images, prompt: text, model, download: false }, controller.signal);
        setGenState({ status: 'running', task: t });
        startPoll(t.id, true);
      }
    } catch (e) {
      const msg = friendlierGenError(e);
      setGenState({ status: 'error', error: msg });
      notify(msg, 'error');
    }
  }, [prompt, model, mode, aspect, resolution, editImages, genState.status, startTxtSse, startPoll]);

  const handleReset = useCallback(() => {
    abortRef.current?.abort();
    clearPoll();
    setPrompt('');
    setGenState({ status: 'idle' });
    setEditImages([]);
  }, [clearPoll]);

  const onPickFiles = useCallback(async (fileList: FileList | null) => {
    if (!fileList) return;
    const items: { name: string; data: string }[] = [];
    for (const f of Array.from(fileList).slice(0, 3)) {
      try {
        items.push({ name: f.name, data: await fileToDataUri(f) });
      } catch { /* ignore */ }
    }
    if (items.length) setEditImages(prev => [...prev, ...items].slice(0, 3));
  }, []);

  const task = genState.task;
  const resultUrl = task?.image_url;

  // D1: providers → ProviderOption[]（用于错误态一键切备用引擎）
  const providerOptions: ProviderOption[] = useMemo(() => {
    const items = providersData?.items;
    if (!items) return [];
    return Object.entries(items).map(([id, p]) => ({ id, label: p.display_name || id, health: p.health_status }));
  }, [providersData]);
  const activeProvider = useMemo(() => model?.split("/")[0] ?? "", [model]);
  const switchProvider = useCallback((providerId: string) => {
    const groups = modelsData?.items;
    if (!groups || !groups[providerId]) return;
    const candidates = groups[providerId].filter(m => Array.isArray(m.capabilities) && m.capabilities.includes(mode === "txt" ? "txt2img" : "img2img"));
    if (candidates.length > 0) {
      setModel(candidates[0].id);
      notify(`已切换到备用引擎：${candidates[0].name || candidates[0].id}`, "success");
    } else {
      notify(`该 provider 暂无${mode === "txt" ? "文生图" : "图生图"}可用模型`, "info");
    }
  }, [modelsData, mode]);

  if (error && !modelsData) return <ErrorRetry message={error.message} onRetry={reload} availableProviders={providerOptions} activeProvider={activeProvider} onSwitchProvider={switchProvider} />;

  return (
    <div className="gen-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            在线生成
            <span className="title-badge">文生图 · 图生图</span>
          </h1>
          <p className="page-desc">带 API Key 生成图像（写接口需 Key，未配置时后端返回 401）</p>
        </div>
        <div className="gen-header-actions">
          <button
            className="tf-btn tf-btn-secondary"
            onClick={() => setShowKeyPanel(v => !v)}
          >
            🔑 {apiKey ? '已配置 Key' : '配置 API Key'}
          </button>
          <button className="tf-btn tf-btn-secondary" onClick={reload}>
            <span>🔄</span> 刷新模型
          </button>
        </div>
      </div>

      {showKeyPanel && (
        <div className="gen-key-panel tf-card">
          <label className="chat-control-field">
            <span>API Key（仅存浏览器 localStorage，永不上传；勿在公共电脑保存）</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                placeholder="sk-tfai-..."
                onChange={e => setApiKey(e.target.value)}
                className="tf-input"
                style={{ flex: 1 }}
                autoComplete="off"
              />
              <button
                type="button"
                className="tf-btn tf-btn-secondary"
                aria-label="切换 Key 明文/掩码"
                onClick={() => setShowKey(v => !v)}
              >
                {showKey ? '🙈 掩码' : '👁 显示'}
              </button>
            </div>
            <small style={{ color: 'var(--text-muted)' }}>🔒 仅保存在本机浏览器 localStorage，关闭页面即离开；公共电脑请勿保存。</small>
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="tf-btn tf-btn-primary"
              onClick={() => { setStoredApiKey(apiKey); notify('API Key 已保存', 'success'); }}
            >
              保存 Key
            </button>
            <button
              className="tf-btn tf-btn-secondary"
              onClick={() => { setApiKey(''); setStoredApiKey(''); notify('已清除 Key', 'info'); }}
            >
              清除
            </button>
          </div>
        </div>
      )}

      <div className="gen-panel tf-card">
        {/* 模式切换 */}
        <div className="gen-tabs">
          <button className={`gen-tab ${mode === 'txt' ? 'on' : ''}`} onClick={() => { setMode('txt'); setGenState({ status: 'idle' }); }}>
            🖼️ 文生图
          </button>
          <button className={`gen-tab ${mode === 'img' ? 'on' : ''}`} onClick={() => { setMode('img'); setGenState({ status: 'idle' }); }}>
            🎨 图生图
          </button>
        </div>

        {/* 图生图：上传参考图 */}
        {mode === 'img' && (
          <div className="gen-img-input">
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              multiple
              style={{ display: 'none' }}
              onChange={e => { void onPickFiles(e.target.files); e.target.value = ''; }}
            />
            <button className="tf-btn tf-btn-secondary" onClick={() => fileRef.current?.click()}>
              📎 上传参考图（最多 3 张）
            </button>
            {editImages.length > 0 && (
              <div className="gen-img-previews">
                {editImages.map((im, i) => (
                  <div key={i} className="gen-img-preview">
                    <img src={im.data} alt={im.name} />
                    <button
                      type="button"
                      className="gen-img-remove"
                      aria-label={`移除 ${im.name}`}
                      onClick={() => setEditImages(prev => prev.filter((_, x) => x !== i))}
                    >×</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 提示词 */}
        <label className="chat-control-field">
          <span>{mode === 'txt' ? '提示词（Prompt）' : '编辑指令（Prompt）'}</span>
          <textarea
            className="tf-input gen-prompt"
            rows={4}
            placeholder={mode === 'txt' ? 'a cute orange cat with blue eyes, soft lighting' : 'make it a watercolor painting'}
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
          />
        </label>

        {/* 模型 / 画幅 / 分辨率 */}
        <div className="gen-row">
          <label className="chat-control-field">
            <span>模型</span>
            <select value={model} onChange={e => setModel(e.target.value)} disabled={loading || activeModels.length === 0}>
              {activeModels.length === 0 && <option value="">{loading ? '加载模型…' : '无可用模型'}</option>}
              {activeModels.map(m => (
                <option key={m.id} value={m.id}>{m.name || m.id}</option>
              ))}
            </select>
          </label>
          {mode === 'txt' && (
            <label className="chat-control-field">
              <span>画幅</span>
              <select value={aspect} onChange={e => setAspect(e.target.value)}>
                {ASPECT_OPTIONS.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
            </label>
          )}
          {mode === 'txt' && (
            <label className="chat-control-field">
              <span>分辨率</span>
              <select value={resolution} onChange={e => setResolution(e.target.value)}>
                {RES_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
          )}
        </div>

        {/* 操作 */}
        <div className="gen-actions">
          <button className="tf-btn tf-btn-primary" onClick={() => void handleGenerate()} disabled={genState.status === 'running'}>
            {genState.status === 'running' ? '⏳ 生成中…' : mode === 'txt' ? '🚀 生成图片' : '🎨 生成变体'}
          </button>
          <button className="tf-btn tf-btn-secondary" onClick={handleReset}>重置</button>
        </div>

        {/* 结果 */}
        {genState.status !== 'idle' && (
          <div className="gen-result">
            {genState.status === 'running' && (
              <div className="gen-loading">
                <span className="gen-spinner" />
                任务处理中（任务 ID: {task?.id ? task.id.slice(0, 12) + '…' : '—'}）…
              </div>
            )}
            {genState.status === 'error' && (
              <div className="gen-error">❌ {genState.error || '生成失败'}</div>
            )}
            {genState.status === 'done' && resultUrl && (
              <div className="gen-done">
                <img src={resultUrl} alt="生成结果" />
                <div className="gen-done-meta">
                  <span>模型 {task?.model}</span>
                  <span>耗时 {task?.duration_sec != null ? `${task.duration_sec.toFixed(1)}s` : '—'}</span>
                  <a href={resultUrl} target="_blank" rel="noopener noreferrer">打开原图 ↗</a>
                  <button type="button" className="tf-btn tf-btn-secondary tf-btn-sm" onClick={() => void handleGenerate()}>
                    🔁 重新生成相同 Prompt
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <style>{`
        .gen-page { display: flex; flex-direction: column; gap: 20px; }
        .gen-header-actions { display: flex; align-items: center; gap: 10px; }
        .gen-key-panel { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
        .gen-panel { padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
        .gen-tabs { display: flex; gap: 8px; }
        .gen-tab { background: var(--bg-subtle); border: 1px solid var(--border-default); color: var(--text-secondary); padding: 8px 14px; border-radius: var(--radius-sm); font-size: 13px; cursor: pointer; transition: all 0.15s ease; }
        .gen-tab:hover { border-color: var(--primary-500); color: var(--text-primary); }
        .gen-tab.on { background: var(--primary-50); border-color: var(--primary-500); color: var(--primary-600); font-weight: 600; }
        .gen-prompt { resize: vertical; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
        .gen-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }
        .gen-actions { display: flex; gap: 10px; }
        .gen-img-input { display: flex; flex-direction: column; gap: 10px; }
        .gen-img-previews { display: flex; flex-wrap: wrap; gap: 10px; }
        .gen-img-preview { position: relative; width: 96px; height: 96px; border-radius: var(--radius-sm); overflow: hidden; border: 1px solid var(--border-default); }
        .gen-img-preview img { width: 100%; height: 100%; object-fit: cover; }
        .gen-img-remove { position: absolute; top: 2px; right: 2px; width: 20px; height: 20px; border-radius: 50%; background: rgba(0,0,0,.65); color: #fff; border: none; cursor: pointer; font-size: 13px; line-height: 1; }
        .gen-result { padding-top: 8px; border-top: 1px solid var(--border-default); display: flex; flex-direction: column; gap: 12px; }
        .gen-loading { display: flex; align-items: center; gap: 10px; color: var(--text-secondary); font-size: 13.5px; }
        .gen-spinner { width: 16px; height: 16px; border: 2px solid var(--border-default); border-top-color: var(--primary-500); border-radius: 50%; animation: gen-spin .8s linear infinite; }
        @keyframes gen-spin { to { transform: rotate(360deg); } }
        .gen-error { color: var(--danger); font-size: 13px; padding: 10px 12px; background: var(--danger-bg); border: 1px solid var(--danger-border); border-radius: var(--radius-sm); display: flex; flex-direction: column; gap: 8px; }
        .gen-error-actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .gen-done { display: flex; flex-direction: column; gap: 10px; }
        .gen-done img { max-width: 100%; border-radius: var(--radius-md); border: 1px solid var(--border-default); }
        .gen-done-meta { display: flex; align-items: center; gap: 12px; font-size: 12.5px; color: var(--text-muted); flex-wrap: wrap; }
      `}</style>
    </div>
  );
}

/** 拍平 /v1/models 分组，按 capability 过滤出可用模型 */
function flatModels(groups: Record<string, ImageModelInfo[]> | undefined, cap: string): ImageModelInfo[] {
  if (!groups) return [];
  return Object.values(groups).flat().filter(m => Array.isArray(m.capabilities) && m.capabilities.includes(cap));
}
