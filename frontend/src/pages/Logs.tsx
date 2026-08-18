import { useEffect, useRef, useState } from 'react';

interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

export function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState('');
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/v1/logs/ws`;
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        const entry = JSON.parse(event.data);
        setLogs(prev => [...prev.slice(-500), entry]);
      } catch { /* ignore */ }
    };
    return () => ws.close();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const filtered = filter
    ? logs.filter(l => l.message.toLowerCase().includes(filter.toLowerCase()))
    : logs;

  const levelColor = (lvl: string) => {
    switch (lvl) {
      case 'INFO': return '#38bdf8';
      case 'WARNING': case 'WARN': return '#fbbf24';
      case 'ERROR': case 'CRITICAL': case 'CRIT': return '#f87171';
      case 'DEBUG': return '#94a3b8';
      default: return '#cbd5e1';
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 16 }}>
        实时日志
        <span className="ws-status" style={{ color: connected ? '#10b981' : '#ef4444' }}>
          {connected ? ' ● 已连接' : ' ○ 已断开'}
        </span>
      </h1>
      <div style={{ marginBottom: 12 }}>
        <input
          type="text"
          placeholder="关键词过滤..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5e0', fontSize: 13 }}
        />
      </div>
      <div className="log-box">
        {filtered.map((l, i) => (
          <div key={i} className="log-line">
            <span className="log-ts">{l.timestamp}</span>
            <span className="log-lvl" style={{ color: levelColor(l.level) }}>{l.level}</span>
            <span className="log-logger">{l.logger}</span>
            <span className="log-msg">{l.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <style>{`
        .ws-status { font-size: 13px; margin-left: 12px; }
        .log-box { background: #0f1117; border-radius: 10px; padding: 12px; font-size: 12px; font-family: ui-monospace, Consolas, monospace; max-height: 600px; overflow-y: auto; line-height: 1.6; }
        .log-line { padding: 2px 4px; border-bottom: 1px solid rgba(255,255,255,.06); color: #cbd5e1; word-break: break-all; }
        .log-ts { color: #64748b; margin-right: 6px; }
        .log-lvl { display: inline-block; width: 48px; font-weight: 600; margin-right: 6px; }
        .log-logger { color: #a78bfa; margin-right: 6px; }
        .log-msg { color: #e2e8f0; }
        @media (prefers-color-scheme: dark) { input { background: #1e2132; color: #e1e4ed; border-color: #2d3050; } }
      `}</style>
    </div>
  );
}