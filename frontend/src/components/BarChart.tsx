import { BarChart as RechartsBar, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

interface BarChartProps {
  data: { name: string; value: number }[];
  title: string;
  height?: number;
}

// 自定义高质感 Tooltip
function CustomTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip-date">{label}</div>
        <div className="chart-tooltip-val">
          <span className="chart-tooltip-dot" />
          出图量：<strong>{payload[0].value}</strong> 张
        </div>
      </div>
    );
  }
  return null;
}

export function BarChart({ data, title, height = 220 }: BarChartProps) {
  return (
    <div className="chart-card-modern tf-card">
      <div className="chart-header">
        <div className="chart-title-wrap">
          <h3 className="chart-title">{title}</h3>
          <span className="chart-sub">每日图片生成成功趋势</span>
        </div>
        <div className="chart-legend">
          <span className="legend-indicator" />
          <span className="legend-label">出图总量</span>
        </div>
      </div>

      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <RechartsBar data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#6366f1" stopOpacity={0.9} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.4} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
            <XAxis
              dataKey="name"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
              dy={6}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--bg-subtle)', opacity: 0.6 }} />
            <Bar
              dataKey="value"
              fill="url(#barGradient)"
              radius={[6, 6, 0, 0]}
              maxBarSize={32}
            />
          </RechartsBar>
        </ResponsiveContainer>
      </div>

      <style>{`
        .chart-card-modern {
          padding: 20px 24px;
        }

        .chart-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 20px;
        }

        .chart-title {
          font-size: 15px;
          font-weight: 600;
          color: var(--text-primary);
          letter-spacing: -0.01em;
        }

        .chart-sub {
          font-size: 12px;
          color: var(--text-muted);
          margin-top: 2px;
          display: block;
        }

        .chart-legend {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: var(--text-secondary);
        }

        .legend-indicator {
          width: 8px;
          height: 8px;
          border-radius: 2px;
          background: #6366f1;
        }

        .chart-tooltip {
          background: var(--bg-card);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          padding: 8px 12px;
          box-shadow: var(--shadow-lg);
          font-size: 12px;
        }

        .chart-tooltip-date {
          color: var(--text-muted);
          margin-bottom: 4px;
          font-weight: 500;
        }

        .chart-tooltip-val {
          color: var(--text-primary);
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .chart-tooltip-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #6366f1;
        }
      `}</style>
    </div>
  );
}
