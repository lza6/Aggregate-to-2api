import { useEffect, useState } from 'react';
import { fetchStats } from '../api';
import { StatCard } from '../components/StatCard';
import { BarChart } from '../components/BarChart';
import { Gallery } from '../components/Gallery';
import type { Stats } from '../api';

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    const load = async () => {
      try { setStats(await fetchStats()); } catch { /* ignore */ }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const dailyChart = stats?.daily?.map(d => ({
    name: d.date.slice(5),
    value: d.images,
  })) ?? [];

  return (
    <div>
      <h1 style={{ margin: '0 0 20px', fontSize: 22 }}>仪表盘</h1>
      <div className="stats-grid">
        <StatCard label="总请求" value={stats?.total_requests ?? '-'} />
        <StatCard label="成功出图" value={stats?.total_images ?? '-'} color="#10b981" />
        <StatCard label="失败" value={stats?.total_errors ?? '-'} color="#ef4444" />
        <StatCard label="运行时长" value={stats?.uptime_human ?? '-'} />
        <StatCard label="当前处理中" value={stats?.processing ?? '-'} />
        <StatCard label="排队中" value={stats?.queued ?? '-'} sub={`容量 ${stats?.queue_capacity ?? '-'}`} />
        <StatCard label="Worker 数" value={stats?.workers ?? '-'} />
        <StatCard label="求解器状态" value={stats?.solver?.status ?? '-'} color={stats?.solver?.status === 'ok' ? '#10b981' : '#ef4444'} />
      </div>
      {dailyChart.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <BarChart data={dailyChart} title="近 14 日出图量" height={220} />
        </div>
      )}
      <div style={{ marginTop: 20 }}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>最近作品</h2>
        <Gallery />
      </div>
      <style>{`
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
        @media (max-width: 600px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
      `}</style>
    </div>
  );
}