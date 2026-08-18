interface ProviderCardProps {
  name: string;
  prefix: string;
  models: number;
  status: string;
  errorCount: number;
}

export function ProviderCard({ name, prefix, models, status, errorCount }: ProviderCardProps) {
  const statusColor = status === 'healthy' ? '#10b981' : status === 'degraded' ? '#f59e0b' : '#ef4444';
  return (
    <div className="prov-card">
      <div className="prov-head">
        <h3>{name}</h3>
        <span className="prov-prefix">{prefix}</span>
      </div>
      <div className="prov-meta">
        <span>模型: {models}</span>
        <span>错误: {errorCount}</span>
      </div>
      <div className="prov-status">
        <span className="status-dot" style={{ background: statusColor }} />
        {status}
      </div>
      <style>{`
        .prov-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 16px 18px; }
        .prov-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .prov-head h3 { margin: 0; font-size: 15px; }
        .prov-prefix { font-size: 11px; color: #6b7280; background: rgba(79,111,255,.08); padding: 2px 8px; border-radius: 6px; }
        .prov-meta { display: flex; gap: 12px; margin-bottom: 8px; }
        .prov-meta span { font-size: 12px; color: #6b7280; background: rgba(79,111,255,.08); padding: 2px 9px; border-radius: 999px; }
        .prov-status { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; }
        @media (prefers-color-scheme: dark) {
          .prov-card { background: #1e2132; border-color: #2d3050; }
          .prov-prefix { color: #8b8fa3; }
          .prov-meta span { color: #8b8fa3; }
        }
      `}</style>
    </div>
  );
}