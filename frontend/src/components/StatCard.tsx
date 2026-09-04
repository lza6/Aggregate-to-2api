interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  icon?: string;
}

export function StatCard({ label, value, sub, color, icon }: StatCardProps) {
  return (
    <div className="stat-card-modern tf-card">
      <div className="stat-card-header">
        <span className="stat-label">{label}</span>
        {/* 装饰性 emoji 图标：屏幕阅读器跳过，避免朗读 "chart icon" 干扰（WCAG 1.3.1） */}
        {icon && <span className="stat-icon-wrapper" aria-hidden="true">{icon}</span>}
      </div>
      <div className="stat-value" style={color ? { color } : undefined}>
        {value}
      </div>
      {sub && <div className="stat-sub">{sub}</div>}
      <style>{`
        .stat-card-modern {
          padding: var(--space-5, 20px) var(--space-5, 20px);
          display: flex;
          flex-direction: column;
          position: relative;
          overflow: hidden;
          contain: layout style paint;
        }

        .stat-card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: var(--space-2, 8px);
        }

        .stat-label {
          font-size: var(--text-sm, 12.5px);
          font-weight: 500;
          color: var(--text-secondary);
          letter-spacing: 0.01em;
        }

        .stat-icon-wrapper {
          font-size: 15px;
          opacity: 0.8;
        }

        .stat-value {
          font-size: 26px;
          font-weight: 700;
          letter-spacing: -0.03em;
          font-variant-numeric: tabular-nums;
          color: var(--text-primary);
          line-height: 1.2;
        }

        .stat-sub {
          font-size: var(--text-xs, 11.5px);
          color: var(--text-muted);
          margin-top: var(--space-2, 6px);
          display: flex;
          align-items: center;
          gap: var(--space-1, 4px);
        }
      `}</style>
    </div>
  );
}
