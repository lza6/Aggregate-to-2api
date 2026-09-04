// LogsPage WebSocket 鉴权分支与重连熔断测试。
// Bug 1 根因：原实现 WS 不携带管理 Key → 后端 check_admin_key close(4401) → 前端无脑重连风暴。
// 本测试覆盖：无 Key/有 Key 的 URL 拼装、4401 鉴权失败停止重连、普通断线退避重连。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LogsPage } from '../pages/Logs';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  readyState = 0; // 0=CONNECTING
  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  send() { /* noop */ }
  close() { this.readyState = 3; }
}

function renderLogs() {
  return render(
    <MemoryRouter>
      <LogsPage />
    </MemoryRouter>,
  );
}

describe('LogsPage WebSocket 鉴权与重连', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', FakeWebSocket);
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('无管理 Key 时 WS URL 不带 ?api_key=（走开放模式/401 由后端决定）', () => {
    renderLogs();
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).not.toContain('api_key=');
  });

  it('有管理 Key 时 WS URL 带 ?api_key=（encodeURIComponent 编码）', () => {
    localStorage.setItem('imagefreeAdminApiKey', 'sk-admin-abc 123');
    renderLogs();
    expect(FakeWebSocket.instances[0].url).toContain('api_key=sk-admin-abc%20123');
  });

  it('onclose 4401（鉴权失败）→ 进入鉴权失败态且不再发起重连', () => {
    renderLogs();
    const ws = FakeWebSocket.instances[0];
    act(() => {
      ws.onclose?.(new CloseEvent('close', { code: 4401 }));
    });
    expect(screen.getByText('管理鉴权失败（请配置管理 Key）')).toBeInTheDocument();
    // 推进退避定时器（远超最大退避 10s），不应发起新连接
    act(() => { vi.advanceTimersByTime(30000); });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('onclose 普通码（1006）→ reconnecting 态 + 退避后发起新 WS 连接', () => {
    renderLogs();
    const ws = FakeWebSocket.instances[0];
    act(() => {
      ws.onclose?.(new CloseEvent('close', { code: 1006 }));
    });
    expect(screen.getByText(/正在重连中/)).toBeInTheDocument();
    // 第 1 次退避约 1s；推进后应新建第 2 个连接
    act(() => { vi.advanceTimersByTime(2000); });
    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2);
  });
});
