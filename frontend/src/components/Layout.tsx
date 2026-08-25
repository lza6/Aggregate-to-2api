import { NavLink } from 'react-router-dom';
import { ToastHost } from './ToastHost';

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="layout-root">
      <aside className="layout-sidebar">
        {/* Brand Section */}
        <div className="sidebar-brand">
          <div className="brand-logo-glow">
            <span className="brand-icon">⚡</span>
          </div>
          <div className="brand-info">
            <div className="brand-title">
              听风AI <span className="brand-tag">PRO</span>
            </div>
            <span className="brand-sub">高可用智能出图中心</span>
          </div>
        </div>

        {/* Navigation */}
        <div className="nav-section-title">核心模块</div>
        <nav className="sidebar-nav">
          <NavLink to="/" end className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span className="nav-icon">📊</span>
            <span className="nav-text">仪表盘</span>
            <span className="nav-pip" />
          </NavLink>
          <NavLink to="/providers" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span className="nav-icon">🔌</span>
            <span className="nav-text">提供商</span>
            <span className="nav-pip" />
          </NavLink>
          <NavLink to="/tasks" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span className="nav-icon">📋</span>
            <span className="nav-text">任务管理</span>
            <span className="nav-pip" />
          </NavLink>
          <NavLink to="/accounts" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span className="nav-icon">👤</span>
            <span className="nav-text">长效号池</span>
            <span className="nav-pip" />
          </NavLink>
          <NavLink to="/logs" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span className="nav-icon">📝</span>
            <span className="nav-text">实时日志</span>
            <span className="nav-pip" />
          </NavLink>
          <NavLink to="/dlq" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span className="nav-icon">🗑️</span>
            <span className="nav-text">死信队列</span>
            <span className="nav-pip" />
          </NavLink>
        </nav>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          <div className="system-pill">
            <span className="system-dot" />
            <span className="system-status">服务运行正常</span>
          </div>
          <div className="system-version">v4.3.3 SaaS Enterprise</div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="layout-body">
        <header className="layout-topbar">
          <div className="topbar-breadcrumb">
            <span className="breadcrumb-root">控制台</span>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">听风智能图像生成架构</span>
          </div>
          <div className="topbar-actions">
            <span className="topbar-badge">
              <span className="tf-dot tf-dot-pulse" style={{ background: '#10b981' }} />
              API Gateway
            </span>
          </div>
        </header>
        <main className="main-content">{children}</main>
      </div>

      <ToastHost />

      <style>{`
        .layout-root {
          display: flex;
          min-height: 100vh;
          background: var(--bg-canvas);
        }

        .layout-sidebar {
          width: 250px;
          background: var(--sidebar-bg);
          border-right: 1px solid var(--sidebar-border);
          color: var(--sidebar-text);
          padding: 24px 16px;
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          position: sticky;
          top: 0;
          height: 100vh;
          z-index: 40;
        }

        .sidebar-brand {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 0 6px 22px 6px;
          border-bottom: 1px solid var(--sidebar-border);
          margin-bottom: 20px;
        }

        .brand-logo-glow {
          width: 36px;
          height: 36px;
          border-radius: 10px;
          background: linear-gradient(135deg, #6366f1 0%, #3b82f6 100%);
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 0 16px rgba(99, 102, 241, 0.4);
        }

        .brand-icon {
          font-size: 18px;
        }

        .brand-info {
          display: flex;
          flex-direction: column;
        }

        .brand-title {
          font-size: 16px;
          font-weight: 700;
          color: #ffffff;
          letter-spacing: -0.02em;
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .brand-tag {
          font-size: 9px;
          font-weight: 700;
          background: linear-gradient(90deg, #6366f1, #a855f7);
          color: #ffffff;
          padding: 1px 5px;
          border-radius: 4px;
          letter-spacing: 0.05em;
        }

        .brand-sub {
          font-size: 11px;
          color: #64748b;
          margin-top: 1px;
        }

        .nav-section-title {
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: #475569;
          padding: 0 10px 8px;
        }

        .sidebar-nav {
          display: flex;
          flex-direction: column;
          gap: 4px;
          flex: 1;
        }

        .nav-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 14px;
          color: #94a3b8;
          text-decoration: none;
          border-radius: 10px;
          font-size: 13.5px;
          font-weight: 500;
          transition: all 0.18s ease;
          position: relative;
        }

        .nav-item:hover {
          color: #f1f5f9;
          background: var(--sidebar-item-hover);
        }

        .nav-item.active {
          color: #ffffff;
          background: var(--sidebar-item-active);
          font-weight: 600;
        }

        .nav-icon {
          font-size: 16px;
          opacity: 0.9;
        }

        .nav-text {
          flex: 1;
        }

        .nav-pip {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: #818cf8;
          opacity: 0;
          transform: scale(0.5);
          transition: all 0.2s ease;
        }

        .nav-item.active .nav-pip {
          opacity: 1;
          transform: scale(1);
          box-shadow: 0 0 8px #818cf8;
        }

        .sidebar-footer {
          padding-top: 16px;
          border-top: 1px solid var(--sidebar-border);
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .system-pill {
          display: flex;
          align-items: center;
          gap: 8px;
          background: rgba(16, 185, 129, 0.08);
          border: 1px solid rgba(16, 185, 129, 0.2);
          padding: 6px 10px;
          border-radius: 8px;
        }

        .system-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: #10b981;
          box-shadow: 0 0 6px rgba(16, 185, 129, 0.6);
        }

        .system-status {
          font-size: 11.5px;
          color: #34d399;
          font-weight: 500;
        }

        .system-version {
          font-size: 11px;
          color: #475569;
          padding-left: 2px;
          font-family: ui-monospace, monospace;
        }

        .layout-body {
          flex: 1;
          display: flex;
          flex-direction: column;
          min-width: 0;
        }

        .layout-topbar {
          height: 56px;
          background: var(--bg-card);
          border-bottom: 1px solid var(--border-default);
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 32px;
          position: sticky;
          top: 0;
          z-index: 30;
          backdrop-filter: blur(12px);
        }

        .topbar-breadcrumb {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
        }

        .breadcrumb-root {
          color: var(--text-muted);
        }

        .breadcrumb-sep {
          color: var(--border-strong);
        }

        .breadcrumb-current {
          color: var(--text-primary);
          font-weight: 600;
        }

        .topbar-actions {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .topbar-badge {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          font-weight: 500;
          color: var(--text-secondary);
          background: var(--bg-subtle);
          border: 1px solid var(--border-default);
          padding: 4px 10px;
          border-radius: var(--radius-full);
        }

        .main-content {
          flex: 1;
          padding: 28px 32px;
          overflow-y: auto;
        }

        @media (max-width: 860px) {
          .layout-root {
            flex-direction: column;
          }
          .layout-sidebar {
            width: 100%;
            height: auto;
            position: relative;
            padding: 14px 16px;
          }
          .sidebar-brand {
            margin-bottom: 10px;
            padding-bottom: 12px;
          }
          .nav-section-title, .sidebar-footer {
            display: none;
          }
          .sidebar-nav {
            flex-direction: row;
            overflow-x: auto;
            padding-bottom: 4px;
          }
          .nav-item {
            padding: 8px 12px;
            white-space: nowrap;
            font-size: 13px;
          }
          .layout-topbar {
            padding: 0 16px;
          }
          .main-content {
            padding: 16px;
          }
        }
      `}</style>
    </div>
  );
}
