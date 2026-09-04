import { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { ToastHost } from './ToastHost';

export function Layout({ children }: { children: React.ReactNode }) {
  // D3: 移动端侧栏抽屉开关；桌面端常驻，窄屏可折叠 + Esc/遮罩关闭 + 键盘可达
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Esc 关闭抽屉（键盘可达性 WCAG 2.1.1）：原 D3 注释承诺但未实现，补齐。
  // 仅在抽屉打开时挂监听，卸载即移除，避免污染全局 keydown。
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawerOpen]);
  return (
    <div className="layout-root">
      {/* 无障碍：skip-link，键盘 Tab 首焦点跳过侧栏直达主内容（WCAG 2.4.1 Bypass Blocks） */}
      <a href="#main-content" className="skip-link">跳到主内容</a>
      {/* D3: 移动端菜单按钮（窄屏可见），aria-label/焦点态。触控目标 ≥44px（WCAG 2.2.2） */}
      <button
        type="button"
        className="layout-menu-btn"
        aria-label={drawerOpen ? '关闭导航菜单' : '打开导航菜单'}
        aria-expanded={drawerOpen}
        aria-controls="layout-sidebar"
        onClick={() => setDrawerOpen(v => !v)}
      >
        <span className="layout-menu-icon" aria-hidden="true">{drawerOpen ? '✕' : '☰'}</span>
      </button>
      {drawerOpen && <div className="layout-overlay" onClick={() => setDrawerOpen(false)} role="button" aria-label="关闭导航" tabIndex={-1} />}
      <aside className={`layout-sidebar ${drawerOpen ? 'is-open' : ''}`} id="layout-sidebar" aria-label="主导航">
        {/* Brand Section */}
        <div className="sidebar-brand">
          <div className="brand-logo-glow">
            <span className="brand-icon" aria-hidden="true">⚡</span>
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
        <nav className="sidebar-nav" aria-label="核心模块导航">
          <NavLink to="/" end className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">📊</span>
            <span className="nav-text">仪表盘</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/providers" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🔌</span>
            <span className="nav-text">提供商</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/tasks" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">📋</span>
            <span className="nav-text">任务管理</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/accounts" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">👤</span>
            <span className="nav-text">长效号池</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/logs" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">📝</span>
            <span className="nav-text">实时日志</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/dlq" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🗑️</span>
            <span className="nav-text">死信队列</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/slow" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🐌</span>
            <span className="nav-text">慢请求画像</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/chat" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">💬</span>
            <span className="nav-text">在线聊天</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/generate" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🖼️</span>
            <span className="nav-text">在线生成</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/api-guide" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">📖</span>
            <span className="nav-text">API 指南</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/health" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🩺</span>
            <span className="nav-text">健康体检</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/ecosystem" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🌐</span>
            <span className="nav-text">AI 生态</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/costs" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">💰</span>
            <span className="nav-text">成本管理</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/security" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🛡️</span>
            <span className="nav-text">安全风控</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
        </nav>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          <div className="system-pill">
            <span className="system-dot" aria-hidden="true" />
            <span className="system-status">服务运行正常</span>
          </div>
          <div className="system-version">v{__APP_VERSION__} SaaS Enterprise</div>
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
            {/* P3-1: 公开/受保护边界说明（不引入登录体系，写操作需管理 Key） */}
            <span className="boundary-pill" title="本面板公开只读展示；写操作（封禁/解封、DLQ 重试/清空）需管理 Key（Authorization: Bearer 头，环境变量 IF_ADMIN_KEYS）">
              <span className="boundary-dot" aria-hidden="true" />
              公开只读 · 写操作需管理 Key
            </span>
            <span className="topbar-badge">
              <span className="tf-dot tf-dot-pulse" aria-hidden="true" style={{ background: '#10b981' }} />
              API Gateway
            </span>
          </div>
        </header>
        <main className="main-content" id="main-content" tabIndex={-1}>{children}</main>
      </div>

      <ToastHost />

      <style>{`
        .layout-root {
          display: flex;
          min-height: 100vh;
          background: var(--bg-canvas);
        }

        /* D3: 移动端菜单按钮 —— 仅窄屏可见，键盘可达 */
        .layout-menu-btn {
          display: none;
          position: fixed;
          top: 10px;
          left: 10px;
          z-index: var(--z-drawer, 60);
          width: 44px;
          height: 44px;
          border-radius: var(--radius-md);
          border: 1px solid var(--border-default);
          background: var(--bg-card);
          color: var(--text-primary);
          cursor: pointer;
          align-items: center;
          justify-content: center;
        }
        .layout-menu-btn:hover { border-color: var(--primary-500); }
        .layout-menu-btn:focus-visible { outline: 2px solid var(--primary-500); outline-offset: 2px; }
        .layout-menu-icon { font-size: 16px; line-height: 1; }
        .layout-overlay { display: none; }

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
          /* 100dvh：iOS Safari 地址栏伸缩时跟踪视口，旧浏览器回退 100vh */
          height: 100dvh;
          z-index: var(--z-drawer, 40);
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

        .nav-item:focus-visible {
          outline: 2px solid var(--primary-500);
          outline-offset: -2px;
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
          padding-top: calc(0px + var(--safe-top));
          position: sticky;
          top: 0;
          z-index: var(--z-sticky, 30);
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

        .boundary-pill {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11.5px;
          font-weight: 500;
          color: var(--warning-text);
          background: var(--warning-bg);
          border: 1px solid var(--warning-border);
          padding: 4px 10px;
          border-radius: var(--radius-full);
          cursor: help;
        }

        .boundary-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--warning);
          box-shadow: 0 0 6px rgba(245, 158, 11, 0.5);
        }

        @media (max-width: 860px) {
          .boundary-pill {
            display: none;
          }
        }

        .main-content {
          flex: 1;
          padding: 28px 32px;
          /* 焦点跳转到这里（skip-link）时不滚动到顶上而是留出 topbar 高度 */
          scroll-margin-top: 56px;
          overflow-y: auto;
        }

        @media (max-width: 860px) {
          .layout-root {
            flex-direction: column;
          }
          /* D3: 窄屏抽屉式侧栏，默认收起，is-open 时滑入 */
          .layout-menu-btn {
            display: flex;
          }
          .layout-sidebar {
            width: 240px;
            height: 100vh;
            height: 100dvh;
            position: fixed;
            top: 0;
            left: 0;
            transform: translateX(-100%);
            transition: transform 0.22s ease;
            box-shadow: var(--shadow-lg, 0 10px 30px rgba(0,0,0,0.3));
            z-index: var(--z-drawer, 55);
            padding: 60px 16px 16px;
          }
          .layout-sidebar.is-open {
            transform: translateX(0);
          }
          .layout-overlay {
            display: block;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.45);
            z-index: var(--z-overlay, 50);
          }
          .sidebar-brand {
            margin-bottom: 10px;
            padding-bottom: 12px;
          }
          .nav-section-title, .sidebar-footer {
            display: none;
          }
          .sidebar-nav {
            flex-direction: column;
            overflow-y: auto;
            padding-bottom: 4px;
          }
          .nav-item {
            padding: 10px 14px;
            font-size: 13px;
          }
          .layout-topbar {
            padding: 0 16px 0 56px;
          }
          .main-content {
            padding: 16px;
          }
        }

        /* D3: 375px 单列网格收紧 */
        @media (max-width: 480px) {
          .main-content { padding: 12px; scroll-margin-top: 50px; }
          .layout-topbar { height: 50px; }
          .topbar-breadcrumb { font-size: 12px; }
        }
      `}</style>
    </div>
  );
}
