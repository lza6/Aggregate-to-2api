import { NavLink } from 'react-router-dom';
import { ToastHost } from './ToastHost';

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h2>听风AI</h2>
          <span className="sub">管理面板</span>
        </div>
        <nav>
          <NavLink to="/" end className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>📊 仪表盘</NavLink>
          <NavLink to="/providers" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>🔌 提供商</NavLink>
          <NavLink to="/tasks" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>📋 任务</NavLink>
          <NavLink to="/accounts" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>👤 号池</NavLink>
          <NavLink to="/logs" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>📝 日志</NavLink>
          <NavLink to="/dlq" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>🗑️ 死信队列</NavLink>
        </nav>
      </aside>
      <main className="main-content">{children}</main>
      <ToastHost />
      <style>{`
        * { margin: 0; padding: 0; box-sizing: border-box; }
        .layout { display: flex; min-height: 100vh; }
        .sidebar { width: 220px; background: #1a1e2e; color: #e1e4ed; padding: 20px; display: flex; flex-direction: column; flex-shrink: 0; }
        .sidebar-brand { margin-bottom: 24px; }
        .sidebar-brand h2 { margin: 0; font-size: 20px; }
        .sidebar-brand .sub { font-size: 12px; color: #8b8fa3; }
        .nav-link { display: block; padding: 10px 14px; color: #8b8fa3; text-decoration: none; border-radius: 8px; margin-bottom: 2px; font-size: 14px; }
        .nav-link:hover { color: #e1e4ed; background: rgba(255,255,255,.05); }
        .nav-link.active { color: #6b8aff; background: rgba(107,138,255,.12); font-weight: 600; }
        .main-content { flex: 1; padding: 24px; background: #f4f6fa; overflow-y: auto; }
        @media (max-width: 768px) {
          .layout { flex-direction: column; }
          .sidebar { width: 100%; padding: 12px; flex-direction: row; overflow-x: auto; }
          .sidebar-brand { display: none; }
          .nav-link { white-space: nowrap; }
          .main-content { padding: 12px; }
        }
      `}</style>
    </div>
  );
}
