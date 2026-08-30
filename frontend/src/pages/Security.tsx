import { useState } from 'react';
import { fetchBlocklist, fetchBlockStatus, blockIp, unblockIp, notify, getStoredAdminKey, setStoredAdminKey } from '../api';
import { useApi } from '../hooks/useApi';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import type { BlockRule } from '../api';

const BLOCK_TYPE_META: Record<string, { label: string; tone: 'danger' | 'warning' }> = {
  block: { label: '全量封禁', tone: 'danger' },
  daily_limit: { label: '每日限流', tone: 'warning' },
};

function formatExpires(rule: BlockRule | null | undefined): string {
  if (!rule) return '—';
  const exp = rule.expire_at;
  if (!exp) return '永久';
  const now = Date.now() / 1000;
  if (exp <= now) return '已过期';
  const days = (exp - now) / 86400;
  if (days >= 1) return `${days.toFixed(1)} 天后`;
  return `${((exp - now) / 3600).toFixed(1)} 小时后`;
}

export function SecurityPage() {
  const { data, loading, error, reload } = useApi(() => fetchBlocklist(200), { intervalMs: 0 });
  const [adminKey, setAdminKey] = useState(getStoredAdminKey);
  const [ipInput, setIpInput] = useState('');
  const [blockType, setBlockType] = useState<'block' | 'daily_limit'>('block');
  const [dailyLimit, setDailyLimit] = useState(1);
  const [reason, setReason] = useState('');
  const [ttl, setTtl] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [unblockingIp, setUnblockingIp] = useState<string | null>(null);
  const [queryIp, setQueryIp] = useState('');
  const [queryResult, setQueryResult] = useState<{ ip: string; rule: BlockRule | null; blocked: boolean } | null>(null);

  const saveKey = () => {
    setStoredAdminKey(adminKey);
    notify(adminKey.trim() ? '管理 Key 已保存到本地' : '管理 Key 已清除（只读模式）', 'success');
    reload();
  };

  const handleBlock = async () => {
    if (submitting) return;
    const ip = ipInput.trim();
    if (!ip) { notify('请填写要封禁的 IP 地址', 'error'); return; }
    setSubmitting(true);
    try {
      const res = await blockIp({
        ip,
        block_type: blockType,
        daily_limit: blockType === 'daily_limit' ? dailyLimit : 0,
        reason: reason.trim(),
        ttl_seconds: ttl,
      });
      notify(`已封禁 ${ip}（${BLOCK_TYPE_META[res.record.block_type].label}）`, 'success');
      setIpInput(''); setReason(''); setTtl(0); setDailyLimit(1);
      reload();
    } catch (e) {
      notify('封禁失败: ' + (e instanceof Error ? e.message : String(e)), 'error');
    }
    setSubmitting(false);
  };

  const handleUnblock = async (ip: string) => {
    if (unblockingIp) return;
    if (!confirm(`确定解封 ${ip}？该 IP 将立即恢复访问。`)) return;
    setUnblockingIp(ip);
    try {
      const res = await unblockIp(ip);
      notify(res.removed ? `已解封 ${ip}` : (res.note ?? `${ip} 不在封禁表中`), 'success');
      reload();
    } catch (e) {
      notify('解封失败: ' + (e instanceof Error ? e.message : String(e)), 'error');
    }
    setUnblockingIp(null);
  };

  const handleQuery = async () => {
    const ip = queryIp.trim();
    if (!ip) { notify('请填写要查询的 IP 地址', 'error'); return; }
    try {
      const r = await fetchBlockStatus(ip);
      setQueryResult(r);
    } catch (e) {
      notify('查询失败: ' + (e instanceof Error ? e.message : String(e)), 'error');
    }
  };

  const items: BlockRule[] = data?.items ?? [];

  if (error && !data) {
    return (
      <div className="security-container">
        <div className="page-header"><h1 className="page-title">安全风控</h1></div>
        <ErrorRetry message={error.message} onRetry={reload} />
      </div>
    );
  }

  return (
    <div className="security-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            安全风控
            {items.length > 0 && <span className="title-badge">{items.length} 条生效规则</span>}
          </h1>
          <p className="page-desc">IP 动态封禁 / 解封 / 列表与状态查询（写操作需管理 Key 鉴权）</p>
        </div>
        <button onClick={reload} disabled={loading} className="tf-btn tf-btn-secondary">
          <span>🔄</span> 刷新
        </button>
      </div>

      <div className="admin-key-banner tf-card">
        <div className="akb-icon">🔑</div>
        <div className="akb-body">
          <div className="akb-title">管理 Key（Authorization: Bearer 头）</div>
          <div className="akb-desc">
            封禁 / 解封 / 列表 / 状态查询均需携带管理 Key（环境变量 <code>IF_ADMIN_KEYS</code>）。
            本面板仅将 Key 保存在本浏览器 localStorage，写操作随请求 Bearer 头发送；只读端点不携带。
          </div>
        </div>
        <div className="akb-input-wrap">
          <input
            type="password"
            placeholder="粘贴管理 Key（仅本地保存）"
            value={adminKey}
            onChange={e => setAdminKey(e.target.value)}
            className="tf-input akb-input"
          />
          <button onClick={saveKey} className="tf-btn tf-btn-primary tf-btn-sm">保存</button>
        </div>
      </div>

      <div className="sec-grid">
        {/* 封禁表单 */}
        <div className="sec-card tf-card">
          <div className="sec-card-title">⛔ 动态封禁 IP</div>
          <div className="sec-form">
            <label className="sec-field">
              <span>IP 地址 *</span>
              <input
                type="text"
                placeholder="如 1.2.3.4 或 2001:db8::1"
                value={ipInput}
                onChange={e => setIpInput(e.target.value)}
                className="tf-input"
              />
            </label>
            <div className="sec-field-row">
              <label className="sec-field">
                <span>封禁类型</span>
                <select value={blockType} onChange={e => setBlockType(e.target.value as 'block' | 'daily_limit')} className="tf-input">
                  <option value="block">全量封禁（永久拦截）</option>
                  <option value="daily_limit">每日限流（次数限制）</option>
                </select>
              </label>
              {blockType === 'daily_limit' && (
                <label className="sec-field">
                  <span>每日最大次数</span>
                  <input type="number" min={1} value={dailyLimit} onChange={e => setDailyLimit(Math.max(1, Number(e.target.value)))} className="tf-input" />
                </label>
              )}
            </div>
            <label className="sec-field">
              <span>封禁原因（可选，≤500 字）</span>
              <input type="text" placeholder="如 滥用刷接口" value={reason} onChange={e => setReason(e.target.value)} className="tf-input" />
            </label>
            <label className="sec-field">
              <span>有效时长秒数（0=永久）</span>
              <input type="number" min={0} value={ttl} onChange={e => setTtl(Math.max(0, Number(e.target.value)))} className="tf-input" />
            </label>
            <button onClick={handleBlock} disabled={submitting} className="tf-btn tf-btn-danger">
              {submitting ? '封禁中...' : '⛔ 确认封禁'}
            </button>
          </div>
        </div>

        {/* 状态查询 */}
        <div className="sec-card tf-card">
          <div className="sec-card-title">🔍 单 IP 状态查询</div>
          <div className="sec-form">
            <label className="sec-field">
              <span>IP 地址</span>
              <input
                type="text"
                placeholder="查询某 IP 当前生效规则"
                value={queryIp}
                onChange={e => setQueryIp(e.target.value)}
                className="tf-input"
              />
            </label>
            <button onClick={handleQuery} className="tf-btn tf-btn-secondary tf-btn-sm">查询</button>
            {queryResult && (
              <div className="sec-query-result">
                <div className="sec-query-ip">IP: <code>{queryResult.ip}</code></div>
                {queryResult.blocked ? (
                  <div className="sec-query-blocked">
                    <span className="tf-badge tf-badge-danger">{BLOCK_TYPE_META[queryResult.rule?.block_type ?? 'block']?.label ?? '已封禁'}</span>
                    {queryResult.rule?.reason && <div className="sec-query-reason">原因: {queryResult.rule.reason}</div>}
                    <div className="sec-query-meta">过期: {formatExpires(queryResult.rule)}</div>
                    <button onClick={() => handleUnblock(queryResult.ip)} className="tf-btn tf-btn-secondary tf-btn-sm">解封该 IP</button>
                  </div>
                ) : (
                  <div className="sec-query-clean">✅ 该 IP 未被封禁</div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 封禁列表 */}
      <div className="sec-list-section tf-card">
        <div className="sec-list-header">
          <h3 className="sec-list-title">📋 当前生效封禁规则</h3>
          <span className="tf-badge tf-badge-info">{items.length} 条</span>
        </div>

        {loading && !data ? (
          <div style={{ padding: '16px 20px' }}><Skeleton lines={4} height={20} /></div>
        ) : !items.length && !error ? (
          <Empty text="封禁表为空" hint="未配置任何 IP 封禁规则，所有请求正常通行" />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="tf-table">
              <thead>
                <tr>
                  <th>IP 地址</th>
                  <th>类型</th>
                  <th>每日上限</th>
                  <th>原因</th>
                  <th>过期</th>
                  <th style={{ textAlign: 'right' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => {
                  const meta = BLOCK_TYPE_META[r.block_type] ?? { label: r.block_type, tone: 'neutral' as const };
                  const busy = unblockingIp === r.ip;
                  return (
                    <tr key={r.ip}>
                      <td><code style={{ fontSize: 12, color: 'var(--primary-600)' }}>{r.ip}</code></td>
                      <td><span className={`tf-badge tf-badge-${meta.tone}`}>{meta.label}</span></td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {r.block_type === 'daily_limit' ? `${r.daily_limit ?? 1} 次/日` : '—'}
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 12.5, maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.reason || '—'}
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 12.5 }}>{formatExpires(r)}</td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          onClick={() => handleUnblock(r.ip)}
                          disabled={busy || unblockingIp !== null}
                          className="tf-btn tf-btn-secondary tf-btn-sm"
                        >
                          {busy ? '解封中...' : '🔓 解封'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <style>{`
        .security-container { display: flex; flex-direction: column; gap: 20px; }
        .admin-key-banner {
          display: flex; align-items: center; gap: 14px; padding: 16px 20px;
          background: var(--info-bg); border-color: var(--info-border);
        }
        .akb-icon { font-size: 22px; flex-shrink: 0; }
        .akb-body { flex: 1; min-width: 0; }
        .akb-title { font-size: 13.5px; font-weight: 600; color: var(--info-text); }
        .akb-desc { font-size: 12px; color: var(--info-text); opacity: 0.9; margin-top: 3px; line-height: 1.5; }
        .akb-desc code { font-family: ui-monospace, monospace; background: rgba(0,0,0,0.06); padding: 1px 4px; border-radius: 4px; }
        .akb-input-wrap { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .akb-input { width: 280px; font-size: 12px; }

        .sec-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }
        .sec-card { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
        .sec-card-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
        .sec-form { display: flex; flex-direction: column; gap: 12px; }
        .sec-field { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--text-secondary); }
        .sec-field-row { display: flex; gap: 12px; }
        .sec-field-row .sec-field { flex: 1; }
        .sec-query-result { margin-top: 6px; padding: 10px 12px; background: var(--bg-subtle); border: 1px solid var(--border-default); border-radius: var(--radius-md); display: flex; flex-direction: column; gap: 6px; }
        .sec-query-ip { font-size: 12px; color: var(--text-secondary); }
        .sec-query-blocked { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
        .sec-query-reason { font-size: 12px; color: var(--text-primary); }
        .sec-query-meta { font-size: 11.5px; color: var(--text-muted); }
        .sec-query-clean { font-size: 12.5px; color: var(--success-text); }

        .sec-list-section { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
        .sec-list-header { display: flex; align-items: center; justify-content: space-between; }
        .sec-list-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }

        @media (max-width: 768px) {
          .akb-input-wrap { flex-direction: column; align-items: stretch; }
          .akb-input { width: 100%; }
          .sec-field-row { flex-direction: column; }
        }
      `}</style>
    </div>
  );
}
