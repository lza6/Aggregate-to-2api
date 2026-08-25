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
  const isHealthy = status === 'healthy';
  const isDegraded = status === 'degraded';
  const badgeClass = isHealthy ? 'tf-badge-success' : isDegraded ? 'tf-badge-warning' : 'tf-badge-danger';
  const statusLabel = isHealthy ? '正常运行' : isDegraded ? '降级运行' : '服务不可用';
  const dotColor = isHealthy ? 'var(--success)' : isDegraded ? 'var(--warning)' : 'var(--danger)';

  return (
    <div className="prov-card-modern tf-card">
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
        <span className="prov-prefix-tag">{prefix}</span>
      </div>

      <div className="prov-chips-row">
        <div className="prov-chip">
          <span className="chip-icon">📦</span>
          <span className="chip-label">{models} 个模型</span>
        </div>
        <div className="prov-chip">
          <span className="chip-icon">💎</span>
          <span className="chip-label">余额: {credits != null ? `${credits} 分` : '理论无限'}</span>
        </div>
        {errorCount > 0 && (
          <div className="prov-chip prov-chip-error">
            <span className="chip-icon">⚠️</span>
            <span className="chip-label">错误 {errorCount}</span>
          </div>
        )}
      </div>

      <div className="prov-footer">
        <span className={`tf-badge ${badgeClass}`}>
          <span className="tf-dot tf-dot-pulse" style={{ background: dotColor }} />
          {statusLabel}
        </span>
        <span className="prov-status-code">{status}</span>
      </div>

      <style>{`
        .prov-card-modern {
          padding: 20px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 16px;
        }

        .prov-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 10px;
        }

        .prov-title-area {
          flex: 1;
          min-width: 0;
        }

        .prov-name-row {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }

        .prov-name {
          font-size: 15.5px;
          font-weight: 600;
          color: var(--text-primary);
          letter-spacing: -0.01em;
        }

        .prov-link-badge {
          font-size: 11px;
          color: var(--primary-500);
          text-decoration: none;
          padding: 2px 7px;
          border-radius: var(--radius-sm);
          background: var(--primary-50);
          border: 1px solid var(--primary-100);
          font-weight: 500;
          transition: all var(--transition-fast);
        }

        .prov-link-badge:hover {
          background: var(--primary-100);
          border-color: var(--primary-200);
        }

        .prov-url {
          display: block;
          font-size: 11.5px;
          color: var(--text-muted);
          margin-top: 3px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .prov-prefix-tag {
          font-family: ui-monospace, monospace;
          font-size: 11px;
          font-weight: 600;
          color: var(--primary-600);
          background: var(--primary-50);
          border: 1px solid var(--primary-100);
          padding: 3px 8px;
          border-radius: var(--radius-md);
        }

        .prov-chips-row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        .prov-chip {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          font-size: 12px;
          color: var(--text-secondary);
          background: var(--bg-subtle);
          border: 1px solid var(--border-default);
          padding: 4px 10px;
          border-radius: var(--radius-full);
          font-weight: 500;
        }

        .prov-chip-error {
          background: var(--danger-bg);
          border-color: var(--danger-border);
          color: var(--danger-text);
        }

        .prov-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-top: 1px solid var(--border-subtle);
          padding-top: 12px;
        }

        .prov-status-code {
          font-size: 11px;
          font-family: ui-monospace, monospace;
          color: var(--text-muted);
        }
      `}</style>
    </div>
  );
}
