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
        {icon && <span className="stat-icon-wrapper">{icon}</span>}
      </div>
      <div className="stat-value" style={color ? { color } : undefined}>
        {value}
      </div>
      {sub && <div className="stat-sub">{sub}</div>}
      <style>{`
        .stat-card-modern {
          padding: 18px 20px;
          display: flex;
          flex-direction: column;
          position: relative;
          overflow: hidden;
        }

        .stat-card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 8px;
        }

        .stat-label {
          font-size: 12.5px;
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
          font-size: 11.5px;
          color: var(--text-muted);
          margin-top: 6px;
          display: flex;
          align-items: center;
          gap: 4px;
        }
      `}</style>
    </div>
  );
}
