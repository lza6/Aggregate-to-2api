import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { classifyError, copyToClipboard } from '../components/Feedback';

// ── classifyError：错误类别推断 ──────────────────────────────────────
// 429/rate/limit/限流/繁忙/queue_full → rate_limit
// 401/unauthorized/api key/未授权/未配置 → auth
// 502/503/504/provider down/上游不可用 → provider_down
// 其他 → generic

describe('classifyError', () => {
  const rateLimitCases: Array<[unknown, string]> = [
    ['HTTP 429 Too Many Requests', '429'],
    ['rate limit exceeded', 'rate'],
    ['you reached the limit', 'limit'],
    ['当前繁忙，请稍后', '繁忙'],
    ['触发限流', '限流'],
    ['queue_full', 'queue_full'],
    ['queue full', 'queue full'],
    [new Error('429 rate limited'), 'Error+429'],
  ];
  for (const [raw, label] of rateLimitCases) {
    it(`rate_limit ← ${label}`, () => {
      expect(classifyError(raw)).toBe('rate_limit');
    });
  }

  const authCases: Array<[unknown, string]> = [
    ['401 Unauthorized', '401'],
    ['unauthorized access', 'unauthorized'],
    ['invalid api key', 'api key'],
    ['未授权访问', '未授权'],
    ['未配置 Key', '未配置'],
  ];
  for (const [raw, label] of authCases) {
    it(`auth ← ${label}`, () => {
      expect(classifyError(raw)).toBe('auth');
    });
  }

  const providerDownCases: Array<[unknown, string]> = [
    ['502 Bad Gateway', '502'],
    ['503 Service Unavailable', '503'],
    ['504 Gateway Timeout', '504'],
    ['provider is down', 'provider down'],
    ['上游不可用', '上游不可用'],
  ];
  for (const [raw, label] of providerDownCases) {
    it(`provider_down ← ${label}`, () => {
      expect(classifyError(raw)).toBe('provider_down');
    });
  }

  it('generic ← 其他文案', () => {
    expect(classifyError('something went wrong')).toBe('generic');
  });

  it('generic ← 空串', () => {
    expect(classifyError('')).toBe('generic');
  });

  it('generic ← null/undefined', () => {
    expect(classifyError(null)).toBe('generic');
    expect(classifyError(undefined)).toBe('generic');
  });

  it('大小写不敏感：UNAUTHORIZED 与 unauthorized 等价', () => {
    expect(classifyError('UNAUTHORIZED')).toBe('auth');
  });

  it('Error 对象走 message 字段', () => {
    expect(classifyError(new Error('HTTP 429'))).toBe('rate_limit');
    expect(classifyError(new Error('502 Bad Gateway'))).toBe('provider_down');
  });

  it('数字/对象走 String() 转换', () => {
    // 429 数字 → '429' → rate_limit
    expect(classifyError(429)).toBe('rate_limit');
    // 对象 String 化后不含任何关键词 → generic
    expect(classifyError({ foo: 'bar' })).toBe('generic');
  });

  it('优先级：同时含 429 与 502 时按 rate_limit 优先（先匹配先返回）', () => {
    // 实现按顺序匹配：rate_limit 分支在前，故 429 命中即返回。
    expect(classifyError('429 then 502')).toBe('rate_limit');
  });

  it('provider_down 需要 provider 与 down 同时出现', () => {
    expect(classifyError('provider ok')).toBe('generic');
    expect(classifyError('system down')).toBe('generic');
    expect(classifyError('provider down')).toBe('provider_down');
  });

  it('provider_down 需要上游 与 不可用 同时出现', () => {
    expect(classifyError('上游可用')).toBe('generic');
    expect(classifyError('下游不可用')).toBe('generic');
    expect(classifyError('上游不可用')).toBe('provider_down');
  });
});

// ── copyToClipboard：navigator.clipboard + execCommand 兜底 ─────────
// jsdom 不实现 document.execCommand，需先在 document 上定义该方法，再用 vi.spyOn 接管。
function ensureExecCommand(returnValue: boolean = true) {
  // 若已存在则不覆盖（保留可被 spyOn 的真实实现）
  if (typeof (document as unknown as { execCommand?: unknown }).execCommand !== 'function') {
    Object.defineProperty(document, 'execCommand', {
      value: vi.fn().mockReturnValue(returnValue),
      configurable: true,
      writable: true,
    });
  }
}

describe('copyToClipboard', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('安全上下文 + clipboard 可用 → 调 navigator.clipboard.writeText 并返回 true', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const ok = await copyToClipboard('hello');
    expect(ok).toBe(true);
    expect(writeText).toHaveBeenCalledWith('hello');
  });

  it('非安全上下文 → 走 execCommand 兜底路径', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    ensureExecCommand(true);
    const execSpy = vi.spyOn(document, 'execCommand').mockReturnValue(true);
    const ok = await copyToClipboard('hello');
    expect(ok).toBe(true);
    expect(execSpy).toHaveBeenCalledWith('copy');
  });

  it('navigator.clipboard.writeText 抛异常 → 走 execCommand 兜底', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    });
    ensureExecCommand(true);
    const execSpy = vi.spyOn(document, 'execCommand').mockReturnValue(true);
    const ok = await copyToClipboard('hello');
    expect(ok).toBe(true);
    expect(execSpy).toHaveBeenCalledWith('copy');
  });

  it('execCommand 返回 false → copyToClipboard 返回 false', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    ensureExecCommand(false);
    vi.spyOn(document, 'execCommand').mockReturnValue(false);
    const ok = await copyToClipboard('hello');
    expect(ok).toBe(false);
  });

  it('execCommand 抛异常 → copyToClipboard 返回 false（不向上抛）', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    ensureExecCommand(true);
    vi.spyOn(document, 'execCommand').mockImplementation(() => {
      throw new Error('not supported');
    });
    const ok = await copyToClipboard('hello');
    expect(ok).toBe(false);
  });

  it('兜底路径创建 textarea 并 append/remove 到 body', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    ensureExecCommand(true);
    const execSpy = vi.spyOn(document, 'execCommand').mockReturnValue(true);
    const appendSpy = vi.spyOn(document.body, 'appendChild');
    const removeSpy = vi.spyOn(document.body, 'removeChild');
    await copyToClipboard('payload');
    expect(execSpy).toHaveBeenCalledWith('copy');
    expect(appendSpy).toHaveBeenCalledTimes(1);
    expect(removeSpy).toHaveBeenCalledTimes(1);
    const ta = appendSpy.mock.calls[0][0] as HTMLTextAreaElement;
    expect(ta.value).toBe('payload');
  });
});
