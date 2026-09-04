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
import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { notify } from '../api';
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
  // v7.7.11: 移除业务 Key 输入——生图/聊天公益开放不限 Key，示例不再填充业务 Key
  // （管理 Key 仅用于面板写操作，不在本页输入；用户自行去 Security 页存管理 Key）
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : 'https://imagefree.tingfengai.art';

  const examples = useMemo(() => ({
    // v7.7.4：生图公益开放不限 Key（guard_generate_request 已移除 check_api_key），
    // 故生图 curl 不带 -H Authorization；用户填的业务 Key 仅用于可选鉴权场景。
    curlSync: `# 生图公益开放无需 Key（仅 per-IP 限流防刷）
curl -X POST ${baseUrl}/v1/generate \\
  -H "Content-Type: application/json" \\
  -d '{"model":"imagefree/default","prompt":"a cute cat","aspect_ratio":"1:1"}'`,
    curlAsync: `# 1. 异步提交（立即返回 task_id）——生图无需 Key
curl -X POST ${baseUrl}/v1/generate/async \\
  -H "Content-Type: application/json" \\
  -d '{"model":"imagefree/default","prompt":"a cute cat","aspect_ratio":"1:1"}'

# 返回: {"id":"<task_id>","status":"queued", ...}

# 2. 轮询任务状态直到 completed（/v1/tasks/{id} 公开端点，无需 Key）
curl ${baseUrl}/v1/tasks/<task_id>`,
    curlChat: `# 聊天公益开放不限 Key（仅 per-IP 限流防刷）；无需 Authorization 头
curl -X POST ${baseUrl}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"tryingopen/z-ai/glm-5.3-flash","messages":[{"role":"user","content":"你好"}]}'`,
    pyRequests: `import requests

BASE = "${baseUrl}"

# 同步生图（生图公益开放无需 Key）
r = requests.post(
    f"{BASE}/v1/generate",
    headers={"Content-Type": "application/json"},
    json={"model": "imagefree/default", "prompt": "a cute cat", "aspect_ratio": "1:1"},
    timeout=120,
)
task = r.json()
print(task["id"], task["status"])
if task.get("image_url"):
    print("图片:", task["image_url"])`,
    pyOpenai: `# 用 openai 库（兼容 OpenAI 风格的 /v1/chat/completions）
# 聊天公益开放不限 Key；api_key 可填任意占位（openai 库要求非空）
from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="any-placeholder",
)

resp = client.chat.completions.create(
    model="tryingopen/z-ai/glm-5.3-flash",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)`,
    jsFetch: `// 浏览器 / Node.js fetch —— 异步生图无需 Key
const BASE = "${baseUrl}";

const res = await fetch(\`\${BASE}/v1/generate/async\`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ model: "imagefree/default", prompt: "a cute cat", aspect_ratio: "1:1" }),
});
const task = await res.json();
console.log(task.id, task.status);`,
  }), [baseUrl]);

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

      {/* v7.7.11: 移除业务 Key 输入框——生图/聊天公益开放不限 Key，无需用户填业务 Key */}
      <div className="tf-card ag-card">
        <div className="ag-card-title">🆓 公益开放说明</div>
        <div className="ag-card-desc">
          <b>生图 / 聊天均公益开放不限 Key</b>（仅 per-IP 限流防刷），直接用下方 curl 调用即可，无需任何 Key。
          <br/>管理面<b>写操作</b>（封禁 / DLQ 清空重试 / 日志）需独立<b>管理 Key</b>（<code>IF_ADMIN_KEYS</code>），详见 <Link to="/security" className="ag-link">安全风控页</Link>。
        </div>
      </div>

      {/* 鉴权方式 */}
      <div className="tf-card ag-card">
        <div className="ag-card-title">🛡️ 鉴权方式（生图/聊天无需，管理写操作需）</div>
        <div className="ag-auth-grid">
          <div className="ag-auth-item">
            <code>Authorization: Bearer &lt;管理Key&gt;</code>
            <div className="ag-auth-note">管理写操作推荐，标准 HTTP 头。</div>
          </div>
          <div className="ag-auth-item">
            <code>X-API-Key: &lt;管理Key&gt;</code>
            <div className="ag-auth-note">自定义头，与 Bearer 等价。</div>
          </div>
          <div className="ag-auth-item">
            <code>?api_key=&lt;管理Key&gt;</code>
            <div className="ag-auth-note">⚠️ 会进 referer/访问日志，仅 WebSocket 等无法设头的场景用。</div>
          </div>
        </div>
        <div className="ag-card-hint">生图/聊天公益开放无需 Key；管理 Key 仅用于面板写操作（封禁/DLQ/日志）。</div>
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
          查看当前可用模型列表：<code>GET {baseUrl}/v1/models</code>（公益开放，无需 Key）。
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
