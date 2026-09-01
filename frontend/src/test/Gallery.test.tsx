import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { Gallery } from '../components/Gallery';
import type { GalleryItem } from '../api';
import { fetchGallery, signGallery } from '../api';

// ── P2-1 画廊签名 URL 自动过期刷新 ──────────────────────────────────────
// 后端 /v1/gallery 返回 image_url（当前不含 exp；待后端补）。
// 前端做两层防护：
//   1) 若 image_url 带 exp（单图直链签名）→ 到期前 5s 用 signGallery 重签并刷新列表；
//   2) 无 exp 时由 <img onError> 防御路径兜底：加载失败重签一次 → 仍失败走 onGalleryFail。
//
// 注意：useFakeTimers 与 @testing-library 的 waitFor/findBy* 冲突（后者内部 setTimeout 也被假化），
// 因此在假定时器下统一用 `await act(async () => {})` 冲刷微任务队列，再手动推进定时器。

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    fetchGallery: vi.fn(),
    signGallery: vi.fn(),
    getStoredAdminKey: vi.fn(() => ''),
  };
});

const nowSec = () => Math.floor(Date.now() / 1000);

function item(url: string, prompt = 'test prompt'): GalleryItem {
  return { image_url: url, image_mime: 'image/png', prompt, aspect_ratio: '1:1', duration_sec: 1.2 };
}

/** 冲刷微任务队列（await act 空体）——配合假定时器推进 React 状态变更。 */
async function flush() {
  await act(async () => {});
}

function renderGallery(overrides: { password?: string; onGalleryFail?: () => void } = {}) {
  return render(<Gallery limit={20} password={overrides.password} onGalleryFail={overrides.onGalleryFail} />);
}

describe('Gallery P2-1 签名 URL 自动过期刷新', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('带即将到期 exp 的 image_url → 到期前触发 signGallery 重签并按新 password 刷新列表', async () => {
    // exp 距今 12s：与 5s lead 配合 → 定时器 7s 后触发。remainSec <= 60 满足。
    const exp = nowSec() + 12;
    const expiringUrl = `https://img.example/x.png?exp=${exp}`;
    (fetchGallery as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [item(expiringUrl)], count: 1 })
      .mockResolvedValueOnce({ items: [item('https://img.example/refreshed.png')], count: 1 });
    (signGallery as ReturnType<typeof vi.fn>).mockResolvedValue({ url: '/v1/gallery?limit=20&password=999999:abc', expires_in: 600 });
    const resignMock = signGallery as ReturnType<typeof vi.fn>;

    renderGallery();
    await flush();
    expect(screen.getByAltText('test prompt')).toBeInTheDocument();
    expect(resignMock).not.toHaveBeenCalled();

    // 推进 7s（exp-5s），应触发重签 setTimeout
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
    });
    // 冲刷 refreshSigned 异步（signGallery.resolve → fetchGallery.resolve → setItems）
    await flush();
    expect(resignMock).toHaveBeenCalledTimes(1);
    // 新列表落地（仍渲染 test prompt 单图）
    expect(screen.getByAltText('test prompt')).toBeInTheDocument();
  });

  it('已过期 URL（img onError 防御路径）→ 静默重拉列表，不触发 onGalleryFail（C2）', async () => {
    // 后端 /v1/gallery 返回的 image_url 是 R2 直链（无签名），单图 404/过期 ≠ 画廊 token 失效。
    // C2 修复：坏图 onError 只静默重拉一次列表，绝不走 signGallery → 清密码 → 弹密码框。
    const expiredUrl = `https://img.example/expired.png?exp=${nowSec() - 100}`;
    (fetchGallery as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [item(expiredUrl)], count: 1 })
      .mockResolvedValueOnce({ items: [item('https://img.example/refreshed.png')], count: 1 });
    // signGallery 应完全不被调用（开放画廊无 admin key 必 403，但这里不应触发它）
    const resignMock = signGallery as ReturnType<typeof vi.fn>;
    const onGalleryFail = vi.fn();

    renderGallery({ onGalleryFail });
    await flush();
    const img = screen.getByAltText('test prompt');

    // 模拟 <img> 加载失败（单图失效，非凭据问题）
    fireEvent.error(img);
    await flush();

    // 关键断言：不触发 signGallery、不触发 onGalleryFail、不进入密码态（坏图不锁死画廊）
    expect(resignMock).not.toHaveBeenCalled();
    expect(onGalleryFail).not.toHaveBeenCalled();
    expect(screen.queryByText('画廊访问受保护')).not.toBeInTheDocument();
  });

  it('无 exp 的普通 image_url → 不挂长定时器，正常渲染', async () => {
    (fetchGallery as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ items: [item('https://img.example/plain.png')], count: 1 });
    const resignMock = signGallery as ReturnType<typeof vi.fn>;

    renderGallery();
    await flush();
    expect(screen.getByAltText('test prompt')).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(resignMock).not.toHaveBeenCalled();
  });

  it('C2: 单图网络抖动（onError）→ 静默重拉列表，不触发 signGallery/密码重置', async () => {
    // 开放画廊（无 password、无 admin key）加载成功
    (fetchGallery as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [item('https://img.example/plain.png')], count: 1 })
      .mockResolvedValueOnce({ items: [item('https://img.example/plain2.png')], count: 1 });
    const resignMock = signGallery as ReturnType<typeof vi.fn>;
    const onGalleryFail = vi.fn();

    renderGallery({ onGalleryFail });
    await flush();
    const img = screen.getByAltText('test prompt');

    // 模拟单个 <img> 加载失败（网络抖动/R2 失效，非凭据问题）
    fireEvent.error(img);
    await flush();

    // 关键断言：不走 signGallery（开放画廊无 key 必 403），不触发 onGalleryFail，不进入密码态
    expect(resignMock).not.toHaveBeenCalled();
    expect(onGalleryFail).not.toHaveBeenCalled();
    expect(screen.queryByText('画廊访问受保护')).not.toBeInTheDocument();
  });
});
