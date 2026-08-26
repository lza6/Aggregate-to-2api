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
  const [autoScroll, setAutoScroll] = useState(true);
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
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  const filtered = filter
    ? logs.filter(l => l.message.toLowerCase().includes(filter.toLowerCase()) || l.logger.toLowerCase().includes(filter.toLowerCase()))
    : logs;

  const getLevelBadgeClass = (lvl: string) => {
    switch (lvl?.toUpperCase()) {
      case 'INFO': return 'lvl-info';
      case 'WARNING': case 'WARN': return 'lvl-warn';
      case 'ERROR': case 'CRITICAL': case 'CRIT': return 'lvl-err';
      case 'DEBUG': return 'lvl-debug';
      default: return 'lvl-default';
    }
  };

  return (
    <div className="logs-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            实时集群日志
            <span className={`tf-badge ${connected ? 'tf-badge-success' : 'tf-badge-danger'}`}>
              <span className={`tf-dot ${connected ? 'tf-dot-pulse' : ''}`} style={{ background: connected ? 'var(--success)' : 'var(--danger)' }} />
              {connected ? 'WebSocket 已连通' : '连接中断'}
            </span>
          </h1>
          <p className="page-desc">实时跟踪服务端 Worker 处理、求解器调用、代理轮换及请求流日志</p>
        </div>
        <div className="logs-action-bar">
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`tf-btn tf-btn-sm ${autoScroll ? 'tf-btn-primary' : 'tf-btn-secondary'}`}
          >
            {autoScroll ? '⬇️ 自动滚屏开启' : '⏹️ 自动滚屏已暂停'}
          </button>
          <button onClick={() => setLogs([])} className="tf-btn tf-btn-secondary tf-btn-sm">
            🗑️ 清屏
          </button>
        </div>
      </div>

      {/* 搜索过滤栏 */}
      <div className="logs-search-wrapper">
        <input
          type="text"
          placeholder="🔍 按关键词、模块名称过滤日志条目…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="tf-input logs-search-input"
        />
        <span className="logs-count-hint">已捕获 {filtered.length} 行</span>
      </div>

      {/* 极客风终端风格展示框 */}
      <div className="terminal-log-box">
        <div className="terminal-header">
          <div className="terminal-dots">
            <span className="t-dot dot-red" />
            <span className="t-dot dot-yellow" />
            <span className="t-dot dot-green" />
          </div>
          <div className="terminal-title">live-stream.stdout — /v1/logs/ws</div>
          <div className="terminal-badge">{filtered.length} lines</div>
        </div>

        <div className="terminal-body">
          {filtered.length === 0 ? (
            <div className="terminal-empty">
              <span>⚡ 等待服务端日志流推入中…</span>
            </div>
          ) : (
            filtered.map((l) => (
              <div key={l.timestamp || l.logger || l.message.slice(0, 20)} className="terminal-line">
                <span className="t-ts">{l.timestamp}</span>
                <span className={`t-lvl ${getLevelBadgeClass(l.level)}`}>{l.level}</span>
                <span className="t-logger">[{l.logger}]</span>
                <span className="t-msg">{l.message}</span>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <style>{`
        .logs-container {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .logs-action-bar {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .logs-search-wrapper {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .logs-search-input {
          flex: 1;
        }

        .logs-count-hint {
          font-size: 12px;
          color: var(--text-muted);
          white-space: nowrap;
        }

        .terminal-log-box {
          background: #080c14;
          border: 1px solid #1e293b;
          border-radius: var(--radius-lg);
          overflow: hidden;
          box-shadow: var(--shadow-xl);
          display: flex;
          flex-direction: column;
        }

        .terminal-header {
          background: #0d1321;
          border-bottom: 1px solid #1e293b;
          padding: 10px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .terminal-dots {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .t-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
        }
        .dot-red { background: #ef4444; }
        .dot-yellow { background: #f59e0b; }
        .dot-green { background: #10b981; }

        .terminal-title {
          font-size: 11.5px;
          font-family: ui-monospace, monospace;
          color: #64748b;
        }

        .terminal-badge {
          font-size: 11px;
          color: #94a3b8;
          background: rgba(255, 255, 255, 0.06);
          padding: 2px 8px;
          border-radius: 4px;
        }

        .terminal-body {
          padding: 14px 16px;
          font-size: 12px;
          font-family: "JetBrains Mono", ui-monospace, Consolas, monospace;
          max-height: 620px;
          overflow-y: auto;
          line-height: 1.65;
        }

        .terminal-empty {
          color: #64748b;
          text-align: center;
          padding: 60px 0;
          font-size: 13px;
        }

        .terminal-line {
          padding: 2px 0;
          color: #e2e8f0;
          word-break: break-all;
          display: flex;
          gap: 8px;
        }

        .t-ts {
          color: #64748b;
          flex-shrink: 0;
        }

        .t-lvl {
          font-weight: 600;
          flex-shrink: 0;
          width: 52px;
        }

        .lvl-info { color: #38bdf8; }
        .lvl-warn { color: #fbbf24; }
        .lvl-err { color: #f87171; }
        .lvl-debug { color: #94a3b8; }
        .lvl-default { color: #cbd5e1; }

        .t-logger {
          color: #a78bfa;
          flex-shrink: 0;
        }

        .t-msg {
          color: #f1f5f9;
          flex: 1;
        }
      `}</style>
    </div>
  );
}
