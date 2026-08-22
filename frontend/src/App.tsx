import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Skeleton } from './components/Feedback';
import { Dashboard } from './pages/Dashboard';

// P-UI-5: 非首屏路由懒加载（首屏只打包 Dashboard；recharts 等重依赖随懒加载页拆出）
const ProvidersPage = lazy(() => import('./pages/Providers').then(m => ({ default: m.ProvidersPage })));
const TasksPage = lazy(() => import('./pages/Tasks').then(m => ({ default: m.TasksPage })));
const AccountsPage = lazy(() => import('./pages/Accounts').then(m => ({ default: m.AccountsPage })));
const LogsPage = lazy(() => import('./pages/Logs').then(m => ({ default: m.LogsPage })));
const DLQPage = lazy(() => import('./pages/DLQ').then(m => ({ default: m.DLQPage })));

function PageFallback() {
  return <Skeleton lines={4} height={18} />;
}

export default function App() {
  // basename 与 vite base 一致：生产挂载于 /admin，路由需剥离该前缀才能匹配 path="/"
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
      <Layout>
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/providers" element={<ProvidersPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/accounts" element={<AccountsPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/dlq" element={<DLQPage />} />
          </Routes>
        </Suspense>
      </Layout>
    </BrowserRouter>
  );
}
