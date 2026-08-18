interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}

export function StatCard({ label, value, sub, color }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
      <style>{`
        .stat-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
        .stat-label { font-size: 12px; color: #6b7280; }
        .stat-value { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; margin-top: 4px; }
        .stat-sub { font-size: 11px; color: #6b7280; margin-top: 2px; }
        @media (prefers-color-scheme: dark) {
          .stat-card { background: #1e2132; border-color: #2d3050; }
          .stat-label { color: #8b8fa3; }
          .stat-sub { color: #8b8fa3; }
        }
      `}</style>
    </div>
  );
}