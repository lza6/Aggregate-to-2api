import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProxyPoolGeo } from '../components/ProxyPoolGeo';
import type { ProxyPoolEntry } from '../api';

function entry(partial: Partial<ProxyPoolEntry>): ProxyPoolEntry {
  return {
    url: 'user:pass@1.2.3.4:8080',
    source: 'free',
    daily_uses: 1,
    use_count: 1,
    cooling: false,
    cooldown_seconds: 0,
    fails: 0,
    country: '美国',
    country_code: 'US',
    country_emoji: '🇺🇸',
    latency_ms: 80,
    checked_ago_seconds: 10,
    protocols: {},
    ...partial,
  };
}

describe('ProxyPoolGeo P3-4 地理分布', () => {
  it('按国家聚合 emoji 分布，并给延迟分档', () => {
    const items: ProxyPoolEntry[] = [
      entry({ country: '美国', country_emoji: '🇺🇸', latency_ms: 60 }),
      entry({ country: '美国', country_emoji: '🇺🇸', latency_ms: 150 }),
      entry({ country: '日本', country_emoji: '🇯🇵', latency_ms: 220, cooling: true }),
    ];
    render(<ProxyPoolGeo items={items} />);

    // 标题与总数
    expect(screen.getByText('🌍 出口代理地理分布')).toBeInTheDocument();
    expect(screen.getByText('3 条出口')).toBeInTheDocument();

    // 国家聚合：美国 2 条（平均延迟 105ms），日本 1 条
    expect(screen.getByText('美国')).toBeInTheDocument();
    expect(screen.getByText('日本')).toBeInTheDocument();
    expect(screen.getByText('2 条')).toBeInTheDocument();
    expect(screen.getByText('1 条')).toBeInTheDocument();
    // 平均延迟（(60+150)/2 = 105）
    expect(screen.getByText('105ms')).toBeInTheDocument();
    expect(screen.getByText('220ms')).toBeInTheDocument();
  });

  it('健康热力：健康 slow/moderate/healthy 与冷却计数（fails>2 计入连续失败）', () => {
    const items: ProxyPoolEntry[] = [
      entry({ country: 'A', country_emoji: '🇦', latency_ms: 40, cooling: false, fails: 0 }),   // healthy
      entry({ country: 'A', country_emoji: '🇦', latency_ms: 120, cooling: false, fails: 0 }),  // moderate
      entry({ country: 'A', country_emoji: '🇦', latency_ms: 400, cooling: false, fails: 3 }),  // slow + fails>2
      entry({ country: 'A', country_emoji: '🇦', latency_ms: 400, cooling: true, fails: 0 }),   // cooling
    ];
    render(<ProxyPoolGeo items={items} />);

    expect(screen.getByText(/健康 1/)).toBeInTheDocument();
    expect(screen.getByText(/中速 1/)).toBeInTheDocument();
    expect(screen.getByText(/慢速 1/)).toBeInTheDocument();
    expect(screen.getByText(/冷却 1/)).toBeInTheDocument();
    expect(screen.getByText(/连续失败 1/)).toBeInTheDocument();
  });

  it('空列表 → 渲染默认标题与总数 0，不崩溃', () => {
    render(<ProxyPoolGeo items={[]} />);
    expect(screen.getByText('🌍 出口代理地理分布')).toBeInTheDocument();
    expect(screen.getByText('0 条出口')).toBeInTheDocument();
  });
});
