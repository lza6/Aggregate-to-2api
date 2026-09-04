/**
 * 全局管理 Key 横幅（v7.8）。
 *
 * 背景：管理面板写操作（DLQ 清空/重试、IP 封禁、Logs WS）走 adminHeaders()，
 * Key 存 localStorage（core.ts: ADMIN_KEY_STORAGE）。用户此前需专门去「安全风控」页
 * 才能配置 → 在其它页点写操作必然 401。此横幅在所有页顶部常驻：
 * - 未配置：黄色提示 + 输入框 + 保存 + 前往安全风控页
 * - 已配置：绿色小条 + 清除 + 前往安全风控页
 *
 * 保存/清除后广播自定义事件 `admin-key-changed`，让 Logs WS 等监听方重连/刷新。
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getStoredAdminKey, setStoredAdminKey, notify } from '../api';

export const ADMIN_KEY_CHANGED_EVENT = 'admin-key-changed';

export function KeyBanner() {
  const [stored, setStored] = useState<string>(() => getStoredAdminKey());
  const [input, setInput] = useState('');
  // 已配置态折叠为小条；未配置态展开。用户可手动展开/收起。
  const [expanded, setExpanded] = useState<boolean>(() => !getStoredAdminKey());

  const broadcast = () => {
    window.dispatchEvent(new CustomEvent(ADMIN_KEY_CHANGED_EVENT));
  };

  const save = () => {
    const key = input.trim();
    setStoredAdminKey(key);
    setStored(key);
    setInput('');
    notify(key ? '✅ 管理 Key 已保存到本地（全站写操作生效）' : '管理 Key 已清除（写操作将回到未授权态）', key ? 'success' : 'info');
    broadcast();
    if (key) setExpanded(false);
  };

  const clear = () => {
    setStoredAdminKey('');
    setStored('');
    notify('管理 Key 已清除（写操作将回到未授权态）', 'info');
    broadcast();
    setExpanded(true);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      save();
    }
  };

  if (stored && !expanded) {
    // 已配置折叠态：绿色小条
    return (
      <div className="kb-banner kb-banner-ok" role="status">
        <span className="kb-icon" aria-hidden="true">✅</span>
        <span className="kb-text">管理 Key 已配置（仅本地保存，写操作全站生效）</span>
        <div className="kb-actions">
          <Link to="/security" className="kb-link">前往安全风控页 →</Link>
          <button type="button" className="tf-btn tf-btn-secondary tf-btn-sm" onClick={() => setExpanded(true)}>更换</button>
          <button type="button" className="tf-btn tf-btn-secondary tf-btn-sm" onClick={clear}>清除</button>
        </div>
        <style>{kbStyles}</style>
      </div>
    );
  }

  // 未配置 / 展开态：黄色提示条 + 输入
  return (
    <div className="kb-banner kb-banner-warn" role="alert">
      <span className="kb-icon" aria-hidden="true">🔑</span>
      <div className="kb-body">
        <div className="kb-title">未配置管理 Key — 写操作（封禁 / DLQ 清空重试 / 日志）将返回 401</div>
        <div className="kb-desc">管理 Key 来自环境变量 <code>IF_ADMIN_KEYS</code>，仅保存在本浏览器 localStorage。保存后全站写操作自动携带。</div>
      </div>
      <div className="kb-input-wrap">
        <input
          type="password"
          aria-label="管理 Key（仅本地保存）"
          placeholder="粘贴管理 Key（仅本地保存）"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          className="tf-input kb-input"
          autoComplete="off"
        />
        <button type="button" onClick={save} className="tf-btn tf-btn-primary tf-btn-sm">保存</button>
        {stored && (
          <button type="button" onClick={() => setExpanded(false)} className="tf-btn tf-btn-secondary tf-btn-sm">收起</button>
        )}
      </div>
      <Link to="/security" className="kb-link">前往安全风控页 →</Link>
      <style>{kbStyles}</style>
    </div>
  );
}

const kbStyles = `
  .kb-banner {
    display: flex; align-items: center; gap: 12px; padding: 10px 16px;
    border: 1px solid var(--border-default); border-radius: var(--radius-md);
    margin-bottom: 16px; flex-wrap: wrap;
  }
  .kb-banner-ok { background: var(--success-bg, rgba(16,185,129,.08)); border-color: var(--success-border, rgba(16,185,129,.25)); color: var(--success-text, #065f46); }
  .kb-banner-warn { background: var(--warning-bg); border-color: var(--warning-border); color: var(--warning-text); }
  .kb-icon { font-size: 18px; flex-shrink: 0; }
  .kb-text { font-size: 12.5px; font-weight: 600; flex: 1; min-width: 120px; }
  .kb-body { flex: 1; min-width: 240px; }
  .kb-title { font-size: 13px; font-weight: 600; }
  .kb-desc { font-size: 11.5px; opacity: .9; margin-top: 2px; line-height: 1.5; }
  .kb-desc code { font-family: ui-monospace, monospace; background: rgba(0,0,0,.06); padding: 1px 4px; border-radius: 4px; }
  .kb-input-wrap { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .kb-input { width: 260px; font-size: 12px; }
  .kb-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .kb-link { font-size: 11.5px; color: var(--primary-500); text-decoration: none; white-space: nowrap; }
  .kb-link:hover { text-decoration: underline; }
  @media (max-width: 768px) {
    .kb-input-wrap { width: 100%; }
    .kb-input { width: 100%; }
  }
`;
