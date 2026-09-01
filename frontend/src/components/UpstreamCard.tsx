import type { EmailSource, ProxyPoolEntry } from '../api';

// v6.9.1: 上游源卡片（邮箱池 / 代理池），复用 ProviderCard 同形态样式：
// name + 官网直达 + 状态徽标 + 计数芯片。与 ProviderCard 视觉一致以丰富 Providers 页。

interface UpstreamCardBaseProps {
  name: string;
  baseUrl?: string | null;
  available: boolean;
  statusLabel: string;
  chips: { icon: string; label: string; danger?: boolean }[];
  footerNote?: string;
}

function UpstreamCardBase({ name, baseUrl, available, statusLabel, chips, footerNote }: UpstreamCardBaseProps) {
  const badgeClass = available ? 'tf-badge-success' : 'tf-badge-neutral';
  const dotColor = available ? 'var(--success)' : 'var(--text-muted)';

  return (
    <div className="prov-card-modern tf-card upstream-card">
      <div className="prov-header">
        <div className="prov-title-area">
          <div className="prov-name-row">
            <h3 className="prov-name">{name}</h3>
            {baseUrl && (
              <a href={baseUrl} target="_blank" rel="noopener noreferrer" className="prov-link-badge" title="打开上游服务官网">
                ↗ 官网直达
              </a>
            )}
          </div>
          {baseUrl && <span className="prov-url" title={baseUrl}>{baseUrl}</span>}
        </div>
      </div>

      <div className="prov-chips-row">
        {chips.map((c, i) => (
          <div key={i} className={`prov-chip ${c.danger ? 'prov-chip-error' : ''}`}>
            <span className="chip-icon">{c.icon}</span>
            <span className="chip-label">{c.label}</span>
          </div>
        ))}
      </div>

      <div className="prov-footer">
        <span className={`tf-badge ${badgeClass}`}>
          <span className="tf-dot tf-dot-pulse" style={{ background: dotColor }} />
          {statusLabel}
        </span>
        {footerNote && <span className="prov-status-code">{footerNote}</span>}
      </div>

      <style>{`
        .upstream-card {
          padding: 20px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 16px;
        }
      `}</style>
    </div>
  );
}

export function EmailSourceCard({ source }: { source: EmailSource }) {
  const total = source.success_count + source.failure_count;
  const rate = total > 0 ? Math.round((source.success_count / total) * 100) : null;
  return (
    <UpstreamCardBase
      name={source.name}
      baseUrl={source.base_url}
      available={source.available}
      statusLabel={source.available ? '可用' : '冷却中'}
      chips={[
        { icon: '⭐', label: `优先级 ${source.priority}` },
        { icon: '✅', label: `成功 ${source.success_count}` },
        ...(source.failure_count > 0 ? [{ icon: '⚠️', label: `失败 ${source.failure_count}`, danger: true as const }] : []),
        ...(rate != null ? [{ icon: '📊', label: `成功率 ${rate}%` }] : []),
      ]}
      footerNote={source.last_error ? source.last_error.slice(0, 60) : undefined}
    />
  );
}

export function ProxyUpstreamCard({ entry }: { entry: ProxyPoolEntry }) {
  return (
    <UpstreamCardBase
      name={`${entry.country_emoji} ${entry.country}`}
      baseUrl={undefined}
      available={!entry.cooling}
      statusLabel={entry.cooling ? '冷却中' : '可用'}
      chips={[
        { icon: '🏷️', label: entry.source === 'residential' ? '住宅代理' : '免费代理' },
        { icon: '⚡', label: `${entry.latency_ms}ms` },
        { icon: '🔁', label: `日用 ${entry.daily_uses}` },
        ...(entry.fails > 0 ? [{ icon: '⚠️', label: `连续失败 ${entry.fails}`, danger: true as const }] : []),
      ]}
      footerNote={entry.country_code ? `国家码 ${entry.country_code}` : undefined}
    />
  );
}
