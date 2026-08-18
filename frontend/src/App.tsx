import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<div><h1>仪表盘</h1><p>建设中...</p></div>} />
          <Route path="/providers" element={<div><h1>提供商</h1><p>建设中...</p></div>} />
          <Route path="/tasks" element={<div><h1>任务管理</h1><p>建设中...</p></div>} />
          <Route path="/accounts" element={<div><h1>号池</h1><p>建设中...</p></div>} />
          <Route path="/logs" element={<div><h1>日志</h1><p>建设中...</p></div>} />
          <Route path="/dlq" element={<div><h1>死信队列</h1><p>建设中...</p></div>} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}