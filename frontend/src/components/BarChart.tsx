import { BarChart as RechartsBar, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

interface BarChartProps {
  data: { name: string; value: number }[];
  title: string;
  height?: number;
}

export function BarChart({ data, title, height = 200 }: BarChartProps) {
  return (
    <div className="chart-card">
      <h3>{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBar data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#d1d5e0" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#6b8aff" radius={[4, 4, 0, 0]} />
        </RechartsBar>
      </ResponsiveContainer>
      <style>{`
        .chart-card { background: #fff; border: 1px solid #d1d5e0; border-radius: 12px; padding: 18px 20px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
        .chart-card h3 { font-size: 14px; margin: 0 0 12px; }
        @media (prefers-color-scheme: dark) {
          .chart-card { background: #1e2132; border-color: #2d3050; }
        }
      `}</style>
    </div>
  );
}