import { useEffect, useState } from 'react';
import { fetchDLQ, retryDLQTask, clearDLQ, notify } from '../api';

export function DLQPage() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const data = await fetchDLQ();
      setItems(data.items ?? []);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleRetry = async (taskId: string) => {
    setLoading(true);
    try {
      await retryDLQTask(taskId);
      notify('重试成功', 'success');
    } catch (e) {
      notify('重试失败: ' + (e as Error).message, 'error');
    }
    await load();
  };

  const handleClear = async () => {
    if (!confirm('确定清空死信队列？')) return;
    setLoading(true);
    try {
      await clearDLQ();
      notify('死信队列已清空', 'success');
    } catch (e) {
      notify('清空失败: ' + (e as Error).message, 'error');
    }
    await load();
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>死信队列</h1>
        {items.length > 0 && (
          <button onClick={handleClear} className="btn btn-danger">清空全部</button>
        )}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Task ID</th>
              <th>模型</th>
              <th>错误</th>
              <th>重试次数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item: any) => (
              <tr key={item.task_id}>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{item.task_id?.slice(0, 8)}</td>
                <td>{item.model ?? '-'}</td>
                <td style={{ color: '#ef4444', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.error ?? '-'}</td>
                <td>{item.attempts ?? '-'}</td>
                <td><button onClick={() => handleRetry(item.task_id)} className="btn btn-sm">重试</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">加载中...</div>}
        {!loading && !items.length && <div className="empty">死信队列为空</div>}
      </div>
      <style>{`
        .btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 13px; cursor: pointer; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-sm { background: #6b8aff; color: #fff; padding: 4px 12px; font-size: 12px; border-radius: 6px; border: none; cursor: pointer; }
        .table-wrap { overflow-x: auto; background: #fff; border-radius: 12px; border: 1px solid #d1d5e0; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 10px 12px; border-bottom: 1px solid #d1d5e0; color: #6b7280; font-weight: 600; font-size: 12px; background: #f8f9fc; }
        td { padding: 10px 12px; border-bottom: 1px solid #d1d5e0; }
        tr:last-child td { border-bottom: none; }
        .empty { text-align: center; color: #6b7280; padding: 40px; font-size: 13px; }
        @media (prefers-color-scheme: dark) {
          .table-wrap { background: #1e2132; border-color: #2d3050; }
          th { background: #252840; border-color: #2d3050; color: #8b8fa3; }
          td { border-color: #2d3050; }
        }
      `}</style>
    </div>
  );
}