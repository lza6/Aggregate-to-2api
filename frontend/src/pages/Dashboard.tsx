import { useCallback, useEffect, useState } from 'react';
import { fetchStats } from '../api';
import { StatCard } from '../components/StatCard';
import { BarChart } from '../components/BarChart';
import { Gallery } from '../components/Gallery';
import { ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { Stats } from '../api';

const PWD_KEY = 'galleryPwd';

// 供 Gallery 组件通过 window 回调通知密码变更（跨组件层传递，避免 prop drilling 改动面扩大）
declare global { interface Window { __galleryChangePassword?: (pwd: string) => void } }

export function Dashboard() {
  const { data: stats, loading, error, reload } = useApi<Stats>(() => fetchStats(), { intervalMs: 5000 });
  const [galleryPwd, setGalleryPwd] = useState<string | undefined>(undefined);

  // P-GALLERY: 刷新后从 sessionStorage 恢复画廊密码（不重输）
  useEffect(() => {
    const stored = sessionStorage.getItem(PWD_KEY);
    if (stored) setGalleryPwd(stored);
    const onChange = (pwd: string) => {
      sessionStorage.setItem(PWD_KEY, pwd);
      setGalleryPwd(pwd);
    };
    window.__galleryChangePassword = onChange;
    return () => { delete window.__galleryChangePassword; };
  }, []);

  const onGalleryFail = useCallback(() => sessionStorage.removeItem(PWD_KEY), []);

  const dailyChart = stats?.daily?.map(d => ({
    name: d.date.slice(5),
    value: d.images,
  })) ?? [];

  if (error && !stats) {
    return <ErrorRetry message={error.message} onRetry={reload} />;
  }

  return (
    <div>
      <h1 style={{ margin: '0 0 20px', fontSize: 22 }}>仪表盘</h1>
      <div className="stats-grid">
        <StatCard label="总请求" value={loading && !stats ? '…' : stats?.total_requests ?? '-'} />
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
      <div style={{ marginTop: 20 }} data-gallery-fail={onGalleryFail}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>最近作品</h2>
        <Gallery password={galleryPwd} />
      </div>
      <style>{`
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
        @media (max-width: 600px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
      `}</style>
    </div>
  );
}
