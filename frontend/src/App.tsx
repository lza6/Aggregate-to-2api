import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Skeleton, Empty } from './components/Feedback';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Dashboard } from './pages/Dashboard';

// P-UI-5: 非首屏路由懒加载（首屏只打包 Dashboard；recharts 等重依赖随懒加载页拆出）
const ProvidersPage = lazy(() => import('./pages/Providers').then(m => ({ default: m.ProvidersPage })));
const TasksPage = lazy(() => import('./pages/Tasks').then(m => ({ default: m.TasksPage })));
const AccountsPage = lazy(() => import('./pages/Accounts').then(m => ({ default: m.AccountsPage })));
const LogsPage = lazy(() => import('./pages/Logs').then(m => ({ default: m.LogsPage })));
const DLQPage = lazy(() => import('./pages/DLQ').then(m => ({ default: m.DLQPage })));
const ChatPlayground = lazy(() => import('./pages/ChatPlayground').then(m => ({ default: m.ChatPlayground })));
const GeneratePage = lazy(() => import('./pages/Generate').then(m => ({ default: m.GeneratePage })));
const HealthPage = lazy(() => import('./pages/Health').then(m => ({ default: m.HealthPage })));
const SecurityPage = lazy(() => import('./pages/Security').then(m => ({ default: m.SecurityPage })));
const EcosystemPage = lazy(() => import('./pages/Ecosystem').then(m => ({ default: m.EcosystemPage })));
const CostsPage = lazy(() => import('./pages/Costs').then(m => ({ default: m.CostsPage })));
const SlowPage = lazy(() => import('./pages/Slow').then(m => ({ default: m.SlowPage })));

function PageFallback() {
  return <Skeleton lines={4} height={18} />;
}

export default function App() {
  // basename 与 vite base 一致：生产挂载于 /admin，路由需剥离该前缀才能匹配 path="/"
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
      {/* P1-5: 根错误边界 —— 包住 <Layout> 与整棵路由树；任一页面崩坏时仍保持侧栏/Topbar 存活 */}
      <ErrorBoundary>
        <Layout>
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              {/* P1-5: 每个懒加载页面再包一层嵌套边界 —— 单页渲染异常只降级该页，不连坐整站 */}
              <Route path="/providers" element={<ErrorBoundary><ProvidersPage /></ErrorBoundary>} />
              <Route path="/tasks" element={<ErrorBoundary><TasksPage /></ErrorBoundary>} />
              <Route path="/accounts" element={<ErrorBoundary><AccountsPage /></ErrorBoundary>} />
              <Route path="/logs" element={<ErrorBoundary><LogsPage /></ErrorBoundary>} />
              <Route path="/dlq" element={<ErrorBoundary><DLQPage /></ErrorBoundary>} />
              <Route path="/chat" element={<ErrorBoundary><ChatPlayground /></ErrorBoundary>} />
              <Route path="/generate" element={<ErrorBoundary><GeneratePage /></ErrorBoundary>} />
              <Route path="/health" element={<ErrorBoundary><HealthPage /></ErrorBoundary>} />
              <Route path="/security" element={<ErrorBoundary><SecurityPage /></ErrorBoundary>} />
              <Route path="/ecosystem" element={<ErrorBoundary><EcosystemPage /></ErrorBoundary>} />
              <Route path="/costs" element={<ErrorBoundary><CostsPage /></ErrorBoundary>} />
              <Route path="/slow" element={<ErrorBoundary><SlowPage /></ErrorBoundary>} />
              {/* v7.7 UX：catch-all 404——未知路径不再渲染空白主区 */}
              <Route path="*" element={<Empty text="页面不存在" hint="请使用左侧导航访问有效页面" />} />
            </Routes>
          </Suspense>
        </Layout>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
