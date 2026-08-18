import { useEffect, useState } from 'react';
import { fetchTasks } from '../api';
import type { Task } from '../api';

export function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchTasks({ limit: 50, status: status || undefined });
        setTasks(data.items);
        setTotal(data.total);
      } catch { /* ignore */ }
    };
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [status]);

  const statusColor = (s: string) => {
    switch (s) {
      case 'completed': return '#10b981';
      case 'processing': return '#f59e0b';
      case 'error': return '#ef4444';
      default: return '#6b7280';
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 16 }}>任务管理 <span style={{ fontSize: 13, color: '#6b7280' }}>共 {total} 条</span></h1>
      <div style={{ marginBottom: 12 }}>
        <select value={status} onChange={e => setStatus(e.target.value)} style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #d1d5e0', fontSize: 13 }}>
          <option value="">全部状态</option>
          <option value="pending">排队中</option>
          <option value="processing">处理中</option>
          <option value="completed">已完成</option>
          <option value="error">失败</option>
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>状态</th>
              <th>模型</th>
              <th>提示词</th>
              <th>耗时</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map(t => (
              <tr key={t.id}>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.id.slice(0, 8)}</td>
                <td><span className="status-pill" style={{ background: statusColor(t.status) }}>{t.status}</span></td>
                <td>{t.model}</td>
                <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.prompt?.slice(0, 40)}</td>
                <td>{t.duration_sec != null ? `${t.duration_sec.toFixed(1)}s` : '-'}</td>
                <td style={{ fontSize: 12, color: '#6b7280' }}>{t.created_at ? new Date(t.created_at * 1000).toLocaleString() : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!tasks.length && <div className="empty">暂无任务</div>}
      </div>
      <style>{`
        .table-wrap { overflow-x: auto; background: #fff; border-radius: 12px; border: 1px solid #d1d5e0; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 10px 12px; border-bottom: 1px solid #d1d5e0; color: #6b7280; font-weight: 600; font-size: 12px; background: #f8f9fc; }
        td { padding: 10px 12px; border-bottom: 1px solid #d1d5e0; }
        tr:last-child td { border-bottom: none; }
        .status-pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; color: #fff; }
        .empty { text-align: center; color: #6b7280; padding: 40px; font-size: 13px; }
        @media (prefers-color-scheme: dark) {
          .table-wrap { background: #1e2132; border-color: #2d3050; }
          th { border-color: #2d3050; color: #8b8fa3; background: #252840; }
          td { border-color: #2d3050; }
        }
      `}</style>
    </div>
  );
}