import { useEffect, useState } from 'react';
import { fetchAccountPool } from '../api';

export function AccountsPage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const load = async () => {
      try { setData(await fetchAccountPool()); } catch { /* ignore */ }
    };
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  if (!data) return <div className="empty">加载中...</div>;

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>号池管理</h1>
      <pre style={{ background: '#f0f2f6', padding: 16, borderRadius: 10, fontSize: 12, overflow: 'auto' }}>
        {JSON.stringify(data, null, 2)}
      </pre>
      <style>{`.empty { text-align: center; color: #6b7280; padding: 40px; font-size: 13px; }`}</style>
    </div>
  );
}