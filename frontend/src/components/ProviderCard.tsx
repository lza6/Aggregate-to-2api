interface ProviderCardProps {
  name: string;
  prefix: string;
  baseUrl?: string;
  models: number;
  status: string;
  errorCount: number;
  credits?: number | null;
}

export function ProviderCard({ name, prefix, baseUrl, models, status, errorCount, credits }: ProviderCardProps) {
  const statusColor = status === 'healthy' ? '#10b981' : status === 'degraded' ? '#f59e0b' : '#ef4444';
  const statusLabel = status === 'healthy' ? '健康' : status === 'degraded' ? '降级' : '不可用';
  return (
    <div className="prov-card">
      <div className="prov-head">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>{name}</h3>
            {baseUrl && (
              <a href={baseUrl} target="_blank" rel="noopener noreferrer" className="official-link" title="打开官方网站">
                ↗ 官网
              </a>
            )}
          </div>
          {baseUrl && <span className="prov-url">{baseUrl}</span>}
        </div>
        <span className="prov-prefix">{prefix}</span>
      </div>
      <div className="prov-meta">
        <span>📦 {models} 个模型</span>
        <span>余额: {credits != null ? `${credits}分` : '理论无限'}</span>
        {errorCount > 0 && <span style={{ color: '#ef4444' }}>⚠️ 错误: {errorCount}</span>}
      </div>
      <div className="prov-status">
        <span className="status-dot" style={{ background: statusColor }} />
        <span>{statusLabel} ({status})</span>
      </div>
      <style>{`
        .prov-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .prov-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
        .official-link { font-size: 11px; color: #6b8aff; text-decoration: none; padding: 2px 6px; border-radius: 4px; background: rgba(107,138,255,.1); font-weight: 500; }
        .official-link:hover { text-decoration: underline; background: rgba(107,138,255,.2); }
        .prov-url { display: block; font-size: 11px; color: #9aa1b2; margin-top: 2px; }
        .prov-prefix { font-size: 11px; color: #6b7280; background: rgba(79,111,255,.08); padding: 2px 8px; border-radius: 6px; font-weight: 600; }
        .prov-meta { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
        .prov-meta span { font-size: 12px; color: #4b5563; background: #f3f4f6; padding: 3px 10px; border-radius: 999px; }
        .prov-status { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #374151; border-top: 1px dashed #e5e7eb; padding-top: 10px; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; }
        @media (prefers-color-scheme: dark) {
          .prov-card { background: #1e2132; border-color: #2d3050; }
          .prov-prefix { color: #8b8fa3; }
          .prov-meta span { color: #e1e4ed; background: #252840; }
          .prov-status { color: #e1e4ed; border-top-color: #2d3050; }
          .prov-head h3 { color: #e1e4ed; }
        }
      `}</style>
    </div>
  );
}