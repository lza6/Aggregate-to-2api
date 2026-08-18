import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { TasksPage } from './pages/Tasks';
import { AccountsPage } from './pages/Accounts';
import { LogsPage } from './pages/Logs';
import { DLQPage } from './pages/DLQ';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/providers" element={<div><h1>提供商</h1><p>建设中...</p></div>} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/dlq" element={<DLQPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}