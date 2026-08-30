import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import {
  Skeleton,
  Empty,
  ErrorRetry,
  ActionableInline,
  classifyError,
  type ProviderOption,
} from '../components/Feedback';

// ── 纯展示组件：Skeleton / Empty ────────────────────────────────────
describe('Skeleton', () => {
  it('渲染指定行数的骨架条', () => {
    const { container } = render(<Skeleton lines={3} height={16} />);
    const bars = container.querySelectorAll('.fb-skeleton-shimmer');
    expect(bars).toHaveLength(3);
  });

  it('aria-busy=true 且有 aria-label', () => {
    render(<Skeleton lines={2} />);
    const wrapper = screen.getByLabelText('正在加载内容');
    expect(wrapper).toHaveAttribute('aria-busy', 'true');
  });

  it('默认 lines=3', () => {
    const { container } = render(<Skeleton />);
    expect(container.querySelectorAll('.fb-skeleton-shimmer')).toHaveLength(3);
  });
});

describe('Empty', () => {
  it('默认文案「暂无数据」', () => {
    render(<Empty />);
    expect(screen.getByText('暂无数据')).toBeInTheDocument();
  });

  it('自定义文案与提示', () => {
    render(<Empty text="还没有任务" hint="点击新建" />);
    expect(screen.getByText('还没有任务')).toBeInTheDocument();
    expect(screen.getByText('点击新建')).toBeInTheDocument();
  });

  it('无 hint 时不渲染提示', () => {
    const { container } = render(<Empty text="x" />);
    expect(container.querySelector('.fb-empty-sub')).toBeNull();
  });
});

// ── ErrorRetry：按 classifyError 分支渲染不同行动区 ─────────────────
const providers: ProviderOption[] = [
  { id: 'p1', label: 'Provider A', health: 'healthy' },
  { id: 'p2', label: 'Provider B', health: 'degraded' },
  { id: 'p3', label: 'Provider C', health: 'down' },
  { id: 'p4', label: 'Provider D', health: 'healthy' },
];

describe('ErrorRetry', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('rate_limit 错误：渲染「服务繁忙或触发限流」标题 + 备用 provider chips（排除 active 与 down）', () => {
    const onSwitch = vi.fn();
    render(
      <ErrorRetry
        message="HTTP 429 rate limited"
        onRetry={vi.fn()}
        availableProviders={providers}
        activeProvider="p1"
        onSwitchProvider={onSwitch}
      />,
    );
    expect(screen.getByText('服务繁忙或触发限流')).toBeInTheDocument();
    // p1 active 排除；p3 down 排除；p2/p4 渲染
    expect(screen.getByText('Provider B')).toBeInTheDocument();
    expect(screen.getByText('Provider D')).toBeInTheDocument();
    expect(screen.queryByText('Provider A')).not.toBeInTheDocument();
    expect(screen.queryByText('Provider C')).not.toBeInTheDocument();
  });

  it('rate_limit：点击 chip 触发 onSwitchProvider', () => {
    const onSwitch = vi.fn();
    render(
      <ErrorRetry
        message="429"
        onRetry={vi.fn()}
        availableProviders={providers}
        activeProvider="p1"
        onSwitchProvider={onSwitch}
      />,
    );
    fireEvent.click(screen.getByText('Provider B'));
    expect(onSwitch).toHaveBeenCalledWith('p2');
  });

  it('auth 错误：渲染 API Key 鉴权失败 + curl 示例 + 复制按钮', () => {
    render(<ErrorRetry message="401 unauthorized" onRetry={vi.fn()} />);
    expect(screen.getByText('API Key 鉴权失败或未配置')).toBeInTheDocument();
    // 复制按钮（CopyButton 文案「📋 一键复制」；ErrorRetry 自身重试按钮文案「🔄 重新请求」）
    const copyBtns = screen.getAllByRole('button', { name: /📋 一键复制/ });
    expect(copyBtns.length).toBe(1);
    // curl 示例存在
    expect(screen.getByText(/curl -X GET/)).toBeInTheDocument();
  });

  it('provider_down：渲染「上游提供商不可用」+ 仅列出 healthy 备用', () => {
    render(
      <ErrorRetry
        message="502 Bad Gateway"
        onRetry={vi.fn()}
        availableProviders={providers}
        activeProvider="p1"
        onSwitchProvider={vi.fn()}
      />,
    );
    expect(screen.getByText('上游提供商不可用')).toBeInTheDocument();
    // provider_down 仅列 healthy 备用：p4（p1 active 排除，p2 degraded 排除，p3 down 排除）
    expect(screen.getByText('Provider D')).toBeInTheDocument();
    expect(screen.queryByText('Provider B')).not.toBeInTheDocument();
  });

  it('generic 错误：渲染「数据获取异常」+ 原 message', () => {
    render(<ErrorRetry message="something weird" onRetry={vi.fn()} />);
    expect(screen.getByText('数据获取异常')).toBeInTheDocument();
    expect(screen.getByText('something weird')).toBeInTheDocument();
  });

  it('点击「重新请求」触发 onRetry', () => {
    const onRetry = vi.fn();
    render(<ErrorRetry message="boom" onRetry={onRetry} />);
    fireEvent.click(screen.getByText(/重新请求/));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('无 onSwitchProvider 时 rate_limit 不渲染切换块', () => {
    render(
      <ErrorRetry
        message="429"
        onRetry={vi.fn()}
        availableProviders={providers}
        activeProvider="p1"
      />,
    );
    // 切换块 fb-action-block 仅在 onSwitchProvider 存在时渲染
    expect(screen.queryByText(/繁忙降级/)).not.toBeInTheDocument();
  });

  it('无备用 provider 时不渲染切换块', () => {
    render(
      <ErrorRetry
        message="429"
        onRetry={vi.fn()}
        availableProviders={[{ id: 'p1', label: 'Only', health: 'healthy' }]}
        activeProvider="p1"
        onSwitchProvider={vi.fn()}
      />,
    );
    expect(screen.queryByText(/繁忙降级/)).not.toBeInTheDocument();
  });

  it('CopyButton：点击后调用 copyToClipboard（mock）并 notify', async () => {
    // mock clipboard 写成功
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    render(<ErrorRetry message="401" onRetry={vi.fn()} />);
    const copyBtn = screen.getByRole('button', { name: /📋 一键复制/ });
    fireEvent.click(copyBtn);
    await waitFor(() => {
      expect(writeText).toHaveBeenCalled();
    });
  });
});

// ── ActionableInline：内联错误块 ─────────────────────────────────────
describe('ActionableInline', () => {
  it('渲染 message', () => {
    render(<ActionableInline kind="generic" message="inline boom" />);
    expect(screen.getByText('inline boom')).toBeInTheDocument();
  });

  it('rate_limit + 备用 provider + onSwitch → 渲染 chip 并点击触发', () => {
    const onSwitch = vi.fn();
    render(
      <ActionableInline
        kind="rate_limit"
        message="429"
        availableProviders={providers}
        activeProvider="p1"
        onSwitchProvider={onSwitch}
      />,
    );
    expect(screen.getByText('切备用：')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Provider B'));
    expect(onSwitch).toHaveBeenCalledWith('p2');
  });

  it('provider_down → 渲染「切健康备用：」', () => {
    render(
      <ActionableInline
        kind="provider_down"
        message="502"
        availableProviders={providers}
        activeProvider="p1"
        onSwitchProvider={vi.fn()}
      />,
    );
    expect(screen.getByText('切健康备用：')).toBeInTheDocument();
  });

  it('generic 无 onSwitch 时不渲染 chip 行', () => {
    render(<ActionableInline kind="generic" message="x" />);
    expect(screen.queryByText('切备用：')).not.toBeInTheDocument();
    expect(screen.queryByText('切健康备用：')).not.toBeInTheDocument();
  });

  it('onRetry 存在时渲染重试按钮并触发', () => {
    const onRetry = vi.fn();
    render(<ActionableInline kind="generic" message="x" onRetry={onRetry} />);
    fireEvent.click(screen.getByText('🔄 重试'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('showSwitch：rate_limit 但备用 provider 全 down 时不渲染 chip 行', () => {
    render(
      <ActionableInline
        kind="rate_limit"
        message="429"
        availableProviders={[{ id: 'p3', label: 'Down', health: 'down' }]}
        activeProvider="p1"
        onSwitchProvider={vi.fn()}
      />,
    );
    expect(screen.queryByText('切备用：')).not.toBeInTheDocument();
  });
});

// ── classifyError 兜底（与纯逻辑测试互补，覆盖 Error 对象路径）─────
describe('classifyError 在组件边界的行为', () => {
  it('Error 对象 429 → rate_limit', () => {
    expect(classifyError(new Error('429'))).toBe('rate_limit');
  });
});
