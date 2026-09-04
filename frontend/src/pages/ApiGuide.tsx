/**
 * API 调用指南页（v7.8）。
 *
 * 目标：让用户一眼看懂如何用 curl/Python/JS 调用听风AI 的生图与聊天接口，
 * 并能一键复制示例。用户在页面输入自己的业务 API Key（IF_API_KEYS）后，
 * 所有示例自动填充真实 Key，免去手抠。
 *
 * 注意：业务 Key（IF_API_KEYS，生图/聊天用）与管理 Key（IF_ADMIN_KEYS，写操作用）
 * 是两把不同的 Key，页面明确区分。
 */
import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { getStoredApiKey, setStoredApiKey, notify } from '../api';
import { copyToClipboard } from '../components/Feedback';

function CopyButton({ text }: { text: string }) {
  const handle = async () => {
    const ok = await copyToClipboard(text);
    notify(ok ? '📋 已复制到剪贴板' : '复制失败，请手动复制', ok ? 'success' : 'error');
  };
  return <button type="button" className="tf-btn tf-btn-secondary tf-btn-sm" onClick={() => void handle()}>📋 一键复制</button>;
}

function CodeBlock({ code, title }: { code: string; title?: string }) {
  return (
    <div className="ag-code-block">
      {title && <div className="ag-code-title">{title}</div>}
      <pre className="ag-code-pre">{code}</pre>
      <CopyButton text={code} />
    </div>
  );
}

export function ApiGuidePage() {
  const [apiKey, setApiKey] = useState<string>(() => getStoredApiKey());
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : 'https://imagefree.tingfengai.art';
  // 占位 Key：用户未填则用 <YOUR_API_KEY> 提示，避免暴露空值。
  const key = apiKey.trim() || '<YOUR_API_KEY>';

  const saveKey = () => {
    setStoredApiKey(apiKey.trim());
    notify(apiKey.trim() ? '✅ 业务 API Key 已保存到本地' : '业务 API Key 已清除', apiKey.trim() ? 'success' : 'info');
  };

  const onKeyKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); saveKey(); }
  };

  const examples = useMemo(() => ({
    curlSync: `curl -X POST ${baseUrl}/v1/generate \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"imagefree/default","prompt":"a cute cat","aspect_ratio":"1:1"}'`,
    curlAsync: `# 1. 异步提交（立即返回 task_id）
curl -X POST ${baseUrl}/v1/generate/async \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"imagefree/default","prompt":"a cute cat","aspect_ratio":"1:1"}'

# 返回: {"id":"<task_id>","status":"queued", ...}

# 2. 轮询任务状态直到 completed
curl ${baseUrl}/v1/tasks/<task_id> -H "Authorization: Bearer ${key}"`,
    curlChat: `curl -X POST ${baseUrl}/v1/chat/completions \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"tryingopen/gpt-4o","messages":[{"role":"user","content":"你好"}]}'`,
    pyRequests: `import requests

BASE = "${baseUrl}"
KEY = "${key}"

# 同步生图（阻塞到出图完成）
r = requests.post(
    f"{BASE}/v1/generate",
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    json={"model": "imagefree/default", "prompt": "a cute cat", "aspect_ratio": "1:1"},
    timeout=120,
)
task = r.json()
print(task["id"], task["status"])
if task.get("image_url"):
    print("图片:", task["image_url"])`,
    pyOpenai: `# 用 openai 库（兼容 OpenAI 风格的 /v1/chat/completions）
from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="${key}",
)

resp = client.chat.completions.create(
    model="tryingopen/gpt-4o",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)`,
    jsFetch: `// 浏览器 / Node.js fetch
const BASE = "${baseUrl}";
const KEY = "${key}";

const res = await fetch(\`\${BASE}/v1/generate/async\`, {
  method: "POST",
  headers: { "Authorization": \`Bearer \${KEY}\`, "Content-Type": "application/json" },
  body: JSON.stringify({ model: "imagefree/default", prompt: "a cute cat", aspect_ratio: "1:1" }),
});
const task = await res.json();
console.log(task.id, task.status);`,
  }), [baseUrl, key]);

  return (
    <div className="ag-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">📖 API 调用指南</h1>
          <p className="page-desc">如何用 curl / Python / JavaScript 调用听风AI 出图与聊天接口（OpenAI 风格 /v1/*）</p>
        </div>
      </div>

      {/* Base URL */}
      <div className="tf-card ag-card">
        <div className="ag-card-title">🌐 Base URL</div>
        <div className="ag-card-desc">所有请求都以此为前缀。生产环境即本页面所在域名。</div>
        <div className="ag-base-row">
          <code className="ag-base-url">{baseUrl}</code>
          <CopyButton text={baseUrl} />
        </div>
      </div>

      {/* 我的业务 API Key */}
      <div className="tf-card ag-card">
        <div className="ag-card-title">🔑 我的业务 API Key</div>
        <div className="ag-card-desc">
          业务 Key（环境变量 <code>IF_API_KEYS</code>）用于调用 <b>生图 / 聊天</b> 接口；
          与<b>管理 Key</b>（<code>IF_ADMIN_KEYS</code>，用于面板封禁/DLQ 写操作）不同。
          填入后下方所有示例自动替换 <code>&lt;YOUR_API_KEY&gt;</code>。仅保存在本浏览器 localStorage。
        </div>
        <div className="ag-key-row">
          <input
            type="text"
            aria-label="业务 API Key（仅本地保存）"
            placeholder="粘贴你的业务 API Key（IF_API_KEYS）"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            onKeyDown={onKeyKeyDown}
            className="tf-input ag-key-input"
            autoComplete="off"
          />
          <button type="button" onClick={saveKey} className="tf-btn tf-btn-primary tf-btn-sm">保存</button>
          <CopyButton text={key} />
        </div>
        <div className="ag-card-hint">未配置业务 Key 的端点（公益生图 <code>/v1/generate</code>）保持开放，但建议配置以启用限流配额归属。</div>
      </div>

      {/* 鉴权方式 */}
      <div className="tf-card ag-card">
        <div className="ag-card-title">🛡️ 鉴权方式（三选一）</div>
        <div className="ag-auth-grid">
          <div className="ag-auth-item">
            <code>Authorization: Bearer &lt;key&gt;</code>
            <div className="ag-auth-note">推荐，标准 HTTP 头，不进 URL。</div>
          </div>
          <div className="ag-auth-item">
            <code>X-API-Key: &lt;key&gt;</code>
            <div className="ag-auth-note">自定义头，与 Bearer 等价。</div>
          </div>
          <div className="ag-auth-item">
            <code>?api_key=&lt;key&gt;</code>
            <div className="ag-auth-note">⚠️ 会进 referer/访问日志，仅 WebSocket 等无法设头的场景用。</div>
          </div>
        </div>
        <div className="ag-card-hint">管理 Key 用于面板写操作（封禁/DLQ/日志），详见 <Link to="/security" className="ag-link">安全风控页</Link>。</div>
      </div>

      {/* curl 示例 */}
      <div className="tf-card ag-card">
        <div className="ag-card-title">💻 curl 示例</div>
        <CodeBlock code={examples.curlSync} title="① 同步生图（阻塞到出图完成）" />
        <CodeBlock code={examples.curlAsync} title="② 异步生图（提交 + 轮询）" />
        <CodeBlock code={examples.curlChat} title="③ 聊天补全（OpenAI 兼容）" />
      </div>

      {/* Python 示例 */}
      <div className="tf-card ag-card">
        <div className="ag-card-title">🐍 Python 示例</div>
        <CodeBlock code={examples.pyRequests} title="① requests 库（同步生图）" />
        <CodeBlock code={examples.pyOpenai} title="② openai 库（聊天，OpenAI 兼容）" />
      </div>

      {/* JS 示例 */}
      <div className="tf-card ag-card">
        <div className="ag-card-title">⚡ JavaScript 示例</div>
        <CodeBlock code={examples.jsFetch} title="fetch（异步生图）" />
      </div>

      {/* 模型列表提示 */}
      <div className="tf-card ag-card">
        <div className="ag-card-title">📋 可用模型</div>
        <div className="ag-card-desc">
          查看当前可用模型列表：<code>GET {baseUrl}/v1/models</code>（带业务 Key）。
          模型 id 命名：<code>&lt;提供商前缀&gt;/&lt;上游真实模型名&gt;</code>，如 <code>imagefree/default</code>、<code>tryingopen/gpt-4o</code>。
        </div>
      </div>

      <style>{`
        .ag-container { display: flex; flex-direction: column; gap: 20px; max-width: 920px; }
        .ag-card { padding: 20px 24px; display: flex; flex-direction: column; gap: 14px; }
        .ag-card-title { font-size: 15px; font-weight: 700; color: var(--text-primary); }
        .ag-card-desc { font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; }
        .ag-card-desc code, .ag-auth-item code, .ag-card-hint code { font-family: ui-monospace, monospace; background: rgba(0,0,0,.06); padding: 1px 5px; border-radius: 4px; font-size: 11.5px; }
        .ag-card-hint { font-size: 11.5px; color: var(--text-muted); line-height: 1.5; }
        .ag-base-row { display: flex; align-items: center; gap: 10px; }
        .ag-base-url { flex: 1; font-family: ui-monospace, monospace; font-size: 13px; color: var(--primary-600); background: var(--bg-subtle); padding: 8px 12px; border-radius: var(--radius-md); overflow-x: auto; }
        .ag-key-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .ag-key-input { flex: 1; min-width: 240px; font-size: 12.5px; }
        .ag-auth-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
        .ag-auth-item { padding: 10px 12px; background: var(--bg-subtle); border: 1px solid var(--border-default); border-radius: var(--radius-md); }
        .ag-auth-item code { display: block; font-family: ui-monospace, monospace; font-size: 12px; color: var(--primary-600); margin-bottom: 4px; word-break: break-all; }
        .ag-auth-note { font-size: 11px; color: var(--text-muted); }
        .ag-code-block { background: var(--bg-subtle); border: 1px solid var(--border-default); border-radius: var(--radius-md); padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
        .ag-code-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
        .ag-code-pre { margin: 0; font-family: ui-monospace, monospace; font-size: 11.5px; color: var(--text-primary); line-height: 1.6; white-space: pre-wrap; word-break: break-all; overflow-x: auto; }
        .ag-code-block button { align-self: flex-start; }
        .ag-link { color: var(--primary-500); text-decoration: none; }
        .ag-link:hover { text-decoration: underline; }
        @media (max-width: 640px) {
          .ag-key-input { min-width: 100%; }
          .ag-base-row { flex-direction: column; align-items: stretch; }
        }
      `}</style>
    </div>
  );
}
