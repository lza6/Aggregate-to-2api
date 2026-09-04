import { useEffect, useRef, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useVirtualList } from '../hooks/useVirtualList';
import { getStoredAdminKey } from '../api';
import { ADMIN_KEY_CHANGED_EVENT } from '../components/KeyBanner';

interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected';

// 4401 = 后端 /v1/logs/ws 鉴权失败时主动 close 的码（admin.py log_websocket）。
// 收到此码意味着 admin key 缺失/无效，重连只会再次 4401 → 必须停止重连并引导用户配置。
const AUTH_FAILED_CODE = 4401;
// 最大重连次数熔断：超过后转 disconnected，避免无限退避堆叠。
const MAX_RECONNECTS = 8;

export function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState('');
  const [connStatus, setConnStatus] = useState<ConnectionStatus>('disconnected');
  const [lastHeartbeat, setLastHeartbeat] = useState<Date | null>(null);
  const [reconnectCount, setReconnectCount] = useState(0);
  const [authFailed, setAuthFailed] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const unmountedRef = useRef(false);
  // 重连计数用 ref 累加，避免闭包快照旧值导致退避失效（原实现 reconnectCount 闭包陷阱）。
  const reconnectCountRef = useRef(0);
  // 鉴权失败标志：置位后 connectWs 直接返回，不再发起无意义重连。
  const authFailedRef = useRef(false);

  const connectWs = useCallback(() => {
    if (unmountedRef.current) return;
    // v7.7.8：实时日志公益只读开放，访客无需管理 Key 即可连接 WS。
    // 鉴权已失败 / 重连次数熔断 → 停在 disconnected（仅网络异常触发，非鉴权）。
    if (authFailedRef.current || reconnectCountRef.current >= MAX_RECONNECTS) {
      setConnStatus('disconnected');
      return;
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // v7.7.8：/v1/logs/ws 已对访客只读开放（日志内容脱敏，无 prompt/api_key 明文）。
    // 若本地存了管理 Key 仍透传（向后兼容 + 未来若恢复鉴权不破），但不强制。
    const adminKey = getStoredAdminKey();
    const wsUrl = adminKey
      ? `${protocol}//${window.location.host}/v1/logs/ws?api_key=${encodeURIComponent(adminKey)}`
      : `${protocol}//${window.location.host}/v1/logs/ws`;

    try {
      setConnStatus(prev => prev === 'connected' ? 'reconnecting' : prev);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (unmountedRef.current) { ws.close(); return; }
        setConnStatus('connected');
        reconnectCountRef.current = 0;
        setReconnectCount(0);
        setLastHeartbeat(new Date());
      };

      ws.onclose = (event) => {
        if (unmountedRef.current) return;
        // 4401 = 鉴权失败：停止重连，引导用户去安全风控页配置管理 Key。
        if (event.code === AUTH_FAILED_CODE) {
          authFailedRef.current = true;
          setAuthFailed(true);
          setConnStatus('disconnected');
          return;
        }
        const next = reconnectCountRef.current + 1;
        reconnectCountRef.current = next;
        setReconnectCount(next);
        // 指数退避：1s, 1.5s, 2.25s… 上限 10s；超过 MAX_RECONNECTS 熔断为 disconnected。
        if (next >= MAX_RECONNECTS) {
          setConnStatus('disconnected');
          return;
        }
        setConnStatus('reconnecting');
        const delay = Math.min(1000 * Math.pow(1.5, next - 1), 10000);
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connectWs();
        }, delay);
      };

      ws.onerror = () => {
        if (unmountedRef.current) return;
        setConnStatus('reconnecting');
      };

      ws.onmessage = (event) => {
        // v7.6 P1：后端收到 "ping" 回 "pong"（裸串）；收到 pong 或日志均刷新心跳保活时间
        if (event.data === 'pong') {
          setLastHeartbeat(new Date());
          return;
        }
        setLastHeartbeat(new Date());
        try {
          const entry = JSON.parse(event.data);
          setLogs(prev => [...prev.slice(-500), entry]);
        } catch { /* ignore */ }
      };
    } catch {
      setConnStatus('disconnected');
    }
  }, []);

  useEffect(() => {
    unmountedRef.current = false;
    connectWs();

    // 心跳保活定时器：每 10 秒发送心跳检测 ping（裸串，后端 admin.py 收到 "ping" 回 "pong"）
    const heartbeatTimer = window.setInterval(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        try {
          // v7.6 P1：原实现发 JSON.stringify({type:'ping'})，后端期望字面量 "ping"
          // → 永不回 pong；且发送后立即 setLastHeartbeat，连接死但无日志流入时仍显示「心跳正常」。
          // 现改为发裸串，heartbeat 仅在 onmessage 收到 pong/log 后更新。
          wsRef.current.send('ping');
        } catch { /* ignore */ }
      }
    }, 10000);

    return () => {
      unmountedRef.current = true;
      clearInterval(heartbeatTimer);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connectWs]);

  // v7.8：监听全局管理 Key 变更（KeyBanner 保存/清除时广播）。鉴权失败态下，
  // 用户在顶部横幅补 Key 后无需手动刷新——重置 authFailed 并自动重连。
  useEffect(() => {
    const onKeyChanged = () => {
      if (authFailedRef.current) {
        authFailedRef.current = false;
        setAuthFailed(false);
        reconnectCountRef.current = 0;
        setReconnectCount(0);
        connectWs();
      }
    };
    window.addEventListener(ADMIN_KEY_CHANGED_EVENT, onKeyChanged);
    return () => window.removeEventListener(ADMIN_KEY_CHANGED_EVENT, onKeyChanged);
  }, [connectWs]);

  const filtered = filter
    ? logs.filter(l => l.message.toLowerCase().includes(filter.toLowerCase()) || l.logger.toLowerCase().includes(filter.toLowerCase()))
    : logs;

  // P2-2: 日志流虚拟滚动 —— terminal-body 作为滚动容器，只渲染可见行（最多 500 行，固定行高切片）。
  const LOG_ROW_H = 22;
  const LOG_CONTAINER_H = 620;
  const vlist = useVirtualList(filtered, { itemHeight: LOG_ROW_H, containerHeight: LOG_CONTAINER_H, overscan: 12 });
  const topPad = vlist.startIndex * LOG_ROW_H;
  const bottomPad = (filtered.length - vlist.endIndex) * LOG_ROW_H;

  // 自动滚屏：新日志到达且 autoScroll 开启时，把滚动容器推到最底（虚拟化后用容器 scrollTop 而非 scrollIntoView）
  useEffect(() => {
    if (autoScroll && vlist.containerRef.current) {
      const el = vlist.containerRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [filtered.length, autoScroll, vlist.containerRef]);

  const getLevelBadgeClass = (lvl: string) => {
    switch (lvl?.toUpperCase()) {
      case 'INFO': return 'lvl-info';
      case 'WARNING': case 'WARN': return 'lvl-warn';
      case 'ERROR': case 'CRITICAL': case 'CRIT': return 'lvl-err';
      case 'DEBUG': return 'lvl-debug';
      default: return 'lvl-default';
    }
  };

  const getStatusBadge = () => {
    if (authFailed) {
      return (
        <span className="tf-badge tf-badge-danger">
          <span className="tf-dot" style={{ background: 'var(--danger)' }} />
          管理鉴权失败（请配置管理 Key）
        </span>
      );
    }
    if (connStatus === 'connected') {
      return (
        <span className="tf-badge tf-badge-success">
          <span className="tf-dot tf-dot-pulse" style={{ background: 'var(--success)' }} />
          WebSocket 实时连通
        </span>
      );
    }
    if (connStatus === 'reconnecting') {
      return (
        <span className="tf-badge tf-badge-warning ws-reconnecting-badge">
          <span className="tf-dot ws-spinner-dot" />
          正在重连中 (第 {reconnectCount} 次)...
          {reconnectCount >= 3 && (
            <Link to="/security" className="kb-link" style={{ marginLeft: 8, fontSize: 11.5 }}>持续重连？检查管理 Key →</Link>
          )}
        </span>
      );
    }
    return (
      <span className="tf-badge tf-badge-danger">
        <span className="tf-dot" style={{ background: 'var(--danger)' }} />
        连接中断
      </span>
    );
  };

  return (
    <div className="logs-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            实时集群日志
            {getStatusBadge()}
            {lastHeartbeat && (
              <span className="heartbeat-indicator" title={`心跳最后保活时间: ${lastHeartbeat.toLocaleTimeString()}`}>
                💓 心跳正常 ({lastHeartbeat.toLocaleTimeString()})
              </span>
            )}
          </h1>
          <p className="page-desc">实时跟踪服务端 Worker 处理、求解器调用、代理轮换及请求流日志（具备断线重连与心跳保活）</p>
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
          {(connStatus !== 'connected') && !authFailed && (
            <button onClick={() => connectWs()} className="tf-btn tf-btn-primary tf-btn-sm">
              ⚡ 立即重连
            </button>
          )}
          {authFailed && (
            <Link to="/security" className="tf-btn tf-btn-primary tf-btn-sm">🔑 前往配置管理 Key</Link>
          )}
        </div>
      </div>

      {/* 搜索过滤栏 */}
      <div className="logs-search-wrapper">
        <input
          type="text"
          aria-label="按关键词或模块过滤日志"
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

        <div className="terminal-body" ref={vlist.containerRef} onScroll={vlist.onScroll} role="log" aria-label="实时日志流">
          {filtered.length === 0 ? (
            <div className="terminal-empty">
              <span>{authFailed
                ? '⚠️ 管理鉴权失败：本地未配置管理 Key 或 Key 无效，请在「安全风控」页配置后重连。'
                : connStatus === 'reconnecting'
                  ? '正在尝试恢复 WebSocket 连接…'
                  : '等待服务端日志流推入中…'}</span>
            </div>
          ) : (
            <>
              {topPad > 0 && <div style={{ height: topPad }} aria-hidden="true" />}
              {vlist.visible.map((l) => (
                <div key={l.timestamp || l.logger || l.message.slice(0, 20)} className="terminal-line">
                  <span className="t-ts">{l.timestamp}</span>
                  <span className={`t-lvl ${getLevelBadgeClass(l.level)}`}>{l.level}</span>
                  <span className="t-logger">[{l.logger}]</span>
                  <span className="t-msg">{l.message}</span>
                </div>
              ))}
              {bottomPad > 0 && <div style={{ height: bottomPad }} aria-hidden="true" />}
            </>
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
