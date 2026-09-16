import { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { ToastHost } from './ToastHost';
import { useT, useLang } from '../i18n';
import { useTheme } from '../hooks/useTheme';

export function Layout({ children }: { children: React.ReactNode }) {
  // P1-6 i18n：响应式 t() + 语言切换（zh/en，localStorage 持久化）
  const t = useT();
  const { lang, toggle } = useLang();
  // P1-7: 主题控制（跟随系统 → 浅色 → 深色 三态循环，localStorage 覆盖系统）
  const { preference, cycleTheme } = useTheme();
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
            <span className="brand-sub">{t('layout.brandSub')}</span>
          </div>
        </div>

        {/* Navigation */}
        <div className="nav-section-title">{t('nav.core')}</div>
        <nav className="sidebar-nav" aria-label="核心模块导航">
          <NavLink to="/" end className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">📊</span>
            <span className="nav-text">{t('nav.dashboard')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/providers" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🔌</span>
            <span className="nav-text">{t('nav.providers')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/tasks" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">📋</span>
            <span className="nav-text">{t('nav.tasks')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/accounts" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">👤</span>
            <span className="nav-text">{t('nav.accounts')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/logs" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">📝</span>
            <span className="nav-text">{t('nav.logs')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/dlq" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🗑️</span>
            <span className="nav-text">{t('nav.dlq')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/slow" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🐌</span>
            <span className="nav-text">{t('nav.slow')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/chat" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">💬</span>
            <span className="nav-text">{t('nav.chat')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/generate" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🖼️</span>
            <span className="nav-text">{t('nav.generate')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/agent" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🤖</span>
            <span className="nav-text">{t('nav.agent')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/api-guide" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">📖</span>
            <span className="nav-text">{t('nav.guide')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/health" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🩺</span>
            <span className="nav-text">{t('nav.health')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/ecosystem" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🌐</span>
            <span className="nav-text">{t('nav.ecosystem')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/costs" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">💰</span>
            <span className="nav-text">{t('nav.costs')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
          <NavLink to="/security" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'} onClick={() => setDrawerOpen(false)}>
            <span className="nav-icon" aria-hidden="true">🛡️</span>
            <span className="nav-text">{t('nav.security')}</span>
            <span className="nav-pip" aria-hidden="true" />
          </NavLink>
        </nav>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          <div className="system-pill">
            <span className="system-dot" aria-hidden="true" />
            <span className="system-status">{t('layout.systemOk')}</span>
          </div>
          <div className="system-version">v{__APP_VERSION__} SaaS Enterprise</div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="layout-body">
        <header className="layout-topbar">
          <div className="topbar-breadcrumb">
            <span className="breadcrumb-root">{t('layout.console')}</span>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">{t('layout.crumb')}</span>
          </div>
          <div className="topbar-actions">
            {/* P1-7：主题切换按钮（跟随系统 → 浅色 → 深色 三态循环） */}
            <button
              type="button"
              className="theme-toggle"
              onClick={cycleTheme}
              title={
                preference === 'dark'
                  ? '当前：深色（点击切到浅色）'
                  : preference === 'light'
                    ? '当前：浅色（点击切到跟随系统）'
                    : '当前：跟随系统（点击切到浅色）'
              }
              aria-label={`切换主题，当前${preference === 'dark' ? '深色' : preference === 'light' ? '浅色' : '跟随系统'}`}
            >
              <span className="theme-toggle-icon" aria-hidden="true">
                {preference === 'dark' ? '🌙' : preference === 'light' ? '☀️' : '🖥️'}
              </span>
            </button>
            {/* P1-6 i18n：中英切换按钮（显示目标语言，localStorage 持久化 + <html lang> 同步） */}
            <button
              type="button"
              className="tf-btn tf-btn-secondary tf-btn-sm"
              onClick={toggle}
              aria-label={lang === 'zh' ? 'Switch to English' : '切换到中文'}
            >
              {t('layout.langSwitch')}
            </button>
            {/* P3-1: 公开/受保护边界说明（不引入登录体系，写操作需管理 Key） */}
            <span className="boundary-pill" title="本面板公开只读展示；写操作（封禁/解封、DLQ 重试/清空）需管理 Key（Authorization: Bearer 头，环境变量 IF_ADMIN_KEYS）">
              <span className="boundary-dot" aria-hidden="true" />
              {t('layout.boundary')}
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

        /* P1-7：顶栏主题切换按钮（跟随系统 → 浅色 → 深色） */
        .theme-toggle {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 30px;
          height: 30px;
          border-radius: var(--radius-md);
          border: 1px solid var(--border-default);
          background: var(--bg-subtle);
          color: var(--text-secondary);
          cursor: pointer;
          font-size: 14px;
          transition: all var(--transition-fast, 0.15s ease);
        }
        .theme-toggle:hover {
          border-color: var(--primary-500);
          color: var(--text-primary);
        }
        .theme-toggle:focus-visible {
          outline: 2px solid var(--primary-500);
          outline-offset: 2px;
        }
        .theme-toggle-icon { line-height: 1; }

        @media (max-width: 480px) {
          .theme-toggle { width: 44px; height: 44px; }
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
