import { useEffect, useMemo, useState } from 'react';
import { fetchProviders, fetchEmailSources, fetchProxyPool } from '../api';
import { ProviderCard } from '../components/ProviderCard';
import { EmailSourceCard, ProxyUpstreamCard } from '../components/UpstreamCard';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { ProviderSummary, EmailSource, ProxyPoolEntry } from '../api';

// v6.9.1: nanobanana 号池已停用（用户「把这个号池停一下」）。
// 纯前端折叠：needs_account=True 的提供商排末尾且默认折叠，保留后端能力，可通过开关恢复。
const NANOBANANA_HIDDEN_KEY = 'imagefreeHideNanobananaPool';

export function ProvidersPage() {
  const { data, loading, error, reload } = useApi(() => fetchProviders(), { intervalMs: 10000 });
  const [providers, setProviders] = useState<{ prefix: string; summary: ProviderSummary }[]>([]);

  // 邮箱池上游源（独立请求，不阻塞主看板）
  const emailApi = useApi(() => fetchEmailSources(), { intervalMs: 30000 });
  const [emailSources, setEmailSources] = useState<EmailSource[]>([]);
  useEffect(() => {
    if (emailApi.data) setEmailSources(emailApi.data.items ?? []);
  }, [emailApi.data]);

  // 代理池上游（复用 /v1/proxy-pool，取首页 + 住宅/免费各取若干）
  const proxyApi = useApi(() => fetchProxyPool({ page: 1, pageSize: 24 }), { intervalMs: 30000 });
  const [proxyEntries, setProxyEntries] = useState<ProxyPoolEntry[]>([]);
  useEffect(() => {
    if (proxyApi.data) setProxyEntries(proxyApi.data.items ?? []);
  }, [proxyApi.data]);

  // nanobanana 折叠开关（localStorage 持久化，默认隐藏 = 用户「停一下」意图）
  const [nbHidden, setNbHidden] = useState<boolean>(() => {
    try { return localStorage.getItem(NANOBANANA_HIDDEN_KEY) !== '0'; } catch { return true; }
  });
  useEffect(() => {
    try { localStorage.setItem(NANOBANANA_HIDDEN_KEY, nbHidden ? '1' : '0'); } catch { /* ignore */ }
  }, [nbHidden]);

  useEffect(() => {
    if (data) {
      setProviders(Object.entries(data.items ?? {}).map(([prefix, summary]) => ({ prefix, summary })));
    }
  }, [data]);

  // 排序：needs_account=False（不需要账号）在前；needs_account=True（nanobanana）排末尾。
  const sorted = useMemo(() => {
    const noAccount = providers.filter(({ summary }) => !summary.needs_account);
    const withAccount = providers.filter(({ summary }) => summary.needs_account);
    return { noAccount, withAccount };
  }, [providers]);

  if (error && !data) return <ErrorRetry message={error.message} onRetry={reload} />;
  if (loading && !data) {
    return (
      <div className="providers-container">
        <div className="page-header">
          <h1 className="page-title">提供商集群状态</h1>
        </div>
        <div className="prov-grid">
          <Skeleton lines={3} height={140} />
          <Skeleton lines={3} height={140} />
          <Skeleton lines={3} height={140} />
        </div>
      </div>
    );
  }

  return (
    <div className="providers-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            提供商集群状态
            <span className="title-badge">{providers.length} 个上游</span>
          </h1>
          <p className="page-desc">各上游 AI 生图提供商健康度、模型目录、额度余额及官网快捷直达；邮箱池与代理池上游同卡片展示</p>
        </div>
        <button onClick={reload} className="tf-btn tf-btn-secondary">
          <span>🔄</span> 刷新状态
        </button>
      </div>

      {/* 不需要账号的提供商（imagefree / aifreeforever）—— 排前突出 */}
      <section className="prov-section">
        <h2 className="prov-section-title">
          🆓 无需账号即可生图
          <span className="prov-section-sub">匿名 / 验证码模式，开箱即用</span>
        </h2>
        <div className="prov-grid">
          {sorted.noAccount.map(({ prefix, summary }) => (
            <ProviderCard
              key={prefix}
              name={summary.display_name ?? prefix}
              prefix={prefix}
              baseUrl={summary.base_url}
              models={summary.model_count ?? 0}
              status={summary.health_status ?? 'unknown'}
              errorCount={summary.error_count ?? 0}
              credits={summary.credits}
            />
          ))}
          {!sorted.noAccount.length && !loading && (
            <div style={{ gridColumn: '1 / -1' }}>
              <Empty text="未检测到无需账号的提供商" hint="后端暂未加载 imagefree / aifreeforever 适配器" />
            </div>
          )}
        </div>
      </section>

      {/* 需要账号的提供商（nanobanana）—— 排末尾，可折叠（号池已停用） */}
      {sorted.withAccount.length > 0 && (
        <section className="prov-section">
          <div className="prov-section-head-row">
            <h2 className="prov-section-title">
              🔐 需要账号（号池）
              <span className="prov-section-sub prov-section-sub-warn">号池自动补号已暂停 · 每日签到停用</span>
            </h2>
            <button
              className="tf-btn tf-btn-sm"
              onClick={() => setNbHidden(v => !v)}
              aria-expanded={!nbHidden}
              title="切换号池区块显示"
            >
              {nbHidden ? '▸ 展开查看' : '▾ 折叠隐藏'}
            </button>
          </div>
          {!nbHidden && (
            <div className="prov-grid">
              {sorted.withAccount.map(({ prefix, summary }) => (
                <div key={prefix} className="prov-card-disabled-wrap">
                  <ProviderCard
                    name={summary.display_name ?? prefix}
                    prefix={prefix}
                    baseUrl={summary.base_url}
                    models={summary.model_count ?? 0}
                    status={summary.health_status ?? 'unknown'}
                    errorCount={summary.error_count ?? 0}
                    credits={summary.credits}
                  />
                  <div className="prov-disabled-banner">
                    ⏸ NanoBanana Pro 每日签到号池已停用（自动补号/签到会话卡片不展示，后端能力保留）
                  </div>
                </div>
              ))}
            </div>
          )}
          {nbHidden && (
            <div className="prov-hidden-placeholder tf-card">
              <span className="prov-hidden-icon">⏸</span>
              <div>
                <div className="prov-hidden-title">号池管理已停用</div>
                <div className="prov-hidden-desc">NanoBanana Pro（每日签到）自动补号已暂停，可在 Accounts 页查看历史号池或在此展开恢复查看</div>
              </div>
            </div>
          )}
        </section>
      )}

      {/* 邮箱池上游 */}
      <section className="prov-section">
        <h2 className="prov-section-title">
          📮 邮箱池上游
          <span className="prov-section-sub">临时邮箱多源弹性调度 · 各源官网直达</span>
        </h2>
        {emailApi.error && !emailSources.length ? (
          <Empty text="邮箱池上游加载失败" hint={emailApi.error.message} />
        ) : emailApi.loading && !emailSources.length ? (
          <div className="prov-grid"><Skeleton lines={3} height={140} /><Skeleton lines={3} height={140} /></div>
        ) : (
          <div className="prov-grid">
            {emailSources.map(s => <EmailSourceCard key={s.name} source={s} />)}
            {!emailSources.length && (
              <div style={{ gridColumn: '1 / -1' }}><Empty text="邮箱池暂无源" hint="后端 email_pool 未初始化" /></div>
            )}
          </div>
        )}
      </section>

      {/* 代理池上游 */}
      <section className="prov-section">
        <h2 className="prov-section-title">
          🌐 代理池上游
          <span className="prov-section-sub">住宅代理 + 免费代理双源 · 国家/延迟/冷却状态</span>
        </h2>
        {proxyApi.error && !proxyEntries.length ? (
          <Empty text="代理池上游加载失败" hint={proxyApi.error.message} />
        ) : proxyApi.loading && !proxyEntries.length ? (
          <div className="prov-grid"><Skeleton lines={3} height={140} /><Skeleton lines={3} height={140} /></div>
        ) : (
          <div className="prov-grid">
            {proxyEntries.map((e, i) => <ProxyUpstreamCard key={`${e.url}-${i}`} entry={e} />)}
            {!proxyEntries.length && (
              <div style={{ gridColumn: '1 / -1' }}><Empty text="代理池暂无条目" hint="后端 proxy_pool 未加载" /></div>
            )}
          </div>
        )}
      </section>

      <style>{`
        .providers-container {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .prov-section {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .prov-section-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
          display: flex;
          align-items: baseline;
          gap: 10px;
        }

        .prov-section-sub {
          font-size: 12px;
          color: var(--text-muted);
          font-weight: 400;
        }

        .prov-section-sub-warn {
          color: var(--warning-text);
        }

        .prov-section-head-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
        }

        .prov-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 16px;
        }

        .prov-card-disabled-wrap {
          display: flex;
          flex-direction: column;
          gap: 8px;
          opacity: 0.78;
        }

        .prov-disabled-banner {
          font-size: 11.5px;
          color: var(--warning-text);
          background: var(--bg-subtle);
          border: 1px dashed var(--warning);
          border-radius: var(--radius-sm);
          padding: 6px 10px;
        }

        .prov-hidden-placeholder {
          display: flex;
          align-items: center;
          gap: 14px;
          padding: 18px 20px;
          border: 1px dashed var(--border-default);
          background: var(--bg-subtle);
        }

        .prov-hidden-icon {
          font-size: 24px;
          color: var(--text-muted);
        }

        .prov-hidden-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .prov-hidden-desc {
          font-size: 12px;
          color: var(--text-muted);
          margin-top: 2px;
        }
      `}</style>
    </div>
  );
}
