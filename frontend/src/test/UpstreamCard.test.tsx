import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmailSourceCard, ProxyUpstreamCard } from '../components/UpstreamCard';
import type { EmailSource, ProxyPoolEntry } from '../api';

function emailSource(partial: Partial<EmailSource>): EmailSource {
  return {
    name: 'mail.tm',
    base_url: 'https://mail.tm',
    priority: 80,
    available: true,
    success_count: 5,
    failure_count: 0,
    last_error: null,
    ...partial,
  };
}

function proxyEntry(partial: Partial<ProxyPoolEntry>): ProxyPoolEntry {
  return {
    url: '1.2.3.4:8080',
    source: 'residential',
    daily_uses: 2,
    use_count: 2,
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

describe('EmailSourceCard v6.9.1 邮箱池上游卡片', () => {
  it('渲染名称 / 官网直达 / 优先级 / 成功计数', () => {
    render(<EmailSourceCard source={emailSource({})} />);
    expect(screen.getByText('mail.tm')).toBeInTheDocument();
    expect(screen.getByText('↗ 官网直达')).toBeInTheDocument();
    expect(screen.getByText('优先级 80')).toBeInTheDocument();
    expect(screen.getByText('成功 5')).toBeInTheDocument();
    expect(screen.getByText('可用')).toBeInTheDocument();
  });

  it('冷却中（available=false）显示「冷却中」徽标且无成功率芯片（无样本）', () => {
    render(<EmailSourceCard source={emailSource({ available: false, success_count: 0, failure_count: 0 })} />);
    expect(screen.getByText('冷却中')).toBeInTheDocument();
    // 无失败 → 无失败芯片；无样本 → 无成功率芯片
    expect(screen.queryByText(/失败/)).not.toBeInTheDocument();
    expect(screen.queryByText(/成功率/)).not.toBeInTheDocument();
  });

  it('失败计数 > 0 渲染失败芯片；有样本渲染成功率', () => {
    render(<EmailSourceCard source={emailSource({ success_count: 8, failure_count: 2 })} />);
    // 8/10 = 80%
    expect(screen.getByText('成功率 80%')).toBeInTheDocument();
    expect(screen.getByText('失败 2')).toBeInTheDocument();
  });

  it('base_url 为 null 时不渲染官网直达链接', () => {
    render(<EmailSourceCard source={emailSource({ base_url: null })} />);
    expect(screen.queryByText('↗ 官网直达')).not.toBeInTheDocument();
  });
});

describe('ProxyUpstreamCard v6.9.1 代理池上游卡片', () => {
  it('渲染国家 emoji+名称 / 来源 / 延迟 / 日用次数', () => {
    render(<ProxyUpstreamCard entry={proxyEntry({})} />);
    expect(screen.getByText('🇺🇸 美国')).toBeInTheDocument();
    expect(screen.getByText('住宅代理')).toBeInTheDocument();
    expect(screen.getByText('80ms')).toBeInTheDocument();
    expect(screen.getByText('日用 2')).toBeInTheDocument();
    expect(screen.getByText('可用')).toBeInTheDocument();
  });

  it('免费代理 source=free 显示「免费代理」标签', () => {
    render(<ProxyUpstreamCard entry={proxyEntry({ source: 'free' })} />);
    expect(screen.getByText('免费代理')).toBeInTheDocument();
  });

  it('冷却中（cooling=true）显示「冷却中」徽标', () => {
    render(<ProxyUpstreamCard entry={proxyEntry({ cooling: true })} />);
    expect(screen.getByText('冷却中')).toBeInTheDocument();
  });

  it('连续失败 fails>0 渲染失败芯片', () => {
    render(<ProxyUpstreamCard entry={proxyEntry({ fails: 3 })} />);
    expect(screen.getByText('连续失败 3')).toBeInTheDocument();
  });
});
