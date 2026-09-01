import { describe, it, expect } from 'vitest';
import type { ProviderSummary } from '../api';

// v6.9.1: Providers 页排序逻辑 —— 不需要账号的提供商排前，需要账号的（nanobanana）排末尾。
// 复刻 Providers.tsx 中的 useMemo 排序逻辑做纯函数测试（不渲染组件，避免轮询 hook 污染）。

interface ProviderEntry { prefix: string; summary: ProviderSummary; }

function splitByAccount(providers: ProviderEntry[]) {
  const noAccount = providers.filter(({ summary }) => !summary.needs_account);
  const withAccount = providers.filter(({ summary }) => summary.needs_account);
  return { noAccount, withAccount };
}

const base = (over: Partial<ProviderSummary>): ProviderSummary => ({
  display_name: 'x',
  base_url: '',
  capabilities: [],
  model_count: 0,
  health_status: 'healthy',
  credits: null,
  error_count: 0,
  degraded: false,
  ...over,
});

describe('Providers 页 v6.9.1 排序逻辑', () => {
  it('needs_account=False（imagefree/aifreeforever）排到「无需账号」组', () => {
    const entries: ProviderEntry[] = [
      { prefix: 'nanobanana', summary: base({ needs_account: true }) },
      { prefix: 'imagefree', summary: base({ needs_account: false }) },
      { prefix: 'aifreeforever', summary: base({ needs_account: false }) },
    ];
    const { noAccount, withAccount } = splitByAccount(entries);
    expect(noAccount.map(e => e.prefix)).toEqual(['imagefree', 'aifreeforever']);
    expect(withAccount.map(e => e.prefix)).toEqual(['nanobanana']);
  });

  it('needs_account 未定义时按 false 处理（向后兼容，归入无需账号组）', () => {
    const entries: ProviderEntry[] = [
      { prefix: 'imagefree', summary: base({ needs_account: undefined as unknown as boolean }) },
      { prefix: 'nanobanana', summary: base({ needs_account: true }) },
    ];
    const { noAccount, withAccount } = splitByAccount(entries);
    expect(noAccount.map(e => e.prefix)).toEqual(['imagefree']);
    expect(withAccount.map(e => e.prefix)).toEqual(['nanobanana']);
  });

  it('全都需要账号 → 无需账号组为空，不崩溃', () => {
    const entries: ProviderEntry[] = [
      { prefix: 'nanobanana', summary: base({ needs_account: true }) },
    ];
    const { noAccount, withAccount } = splitByAccount(entries);
    expect(noAccount).toHaveLength(0);
    expect(withAccount.map(e => e.prefix)).toEqual(['nanobanana']);
  });

  it('全都不需要账号 → 需要账号组为空', () => {
    const entries: ProviderEntry[] = [
      { prefix: 'imagefree', summary: base({ needs_account: false }) },
      { prefix: 'aifreeforever', summary: base({ needs_account: false }) },
    ];
    const { noAccount, withAccount } = splitByAccount(entries);
    expect(noAccount).toHaveLength(2);
    expect(withAccount).toHaveLength(0);
  });
});
