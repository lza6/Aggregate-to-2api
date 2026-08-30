import { describe, it, expect } from 'vitest';

// Dashboard 内部 formatTokens 为局部函数（未导出）。
// 这里在测试文件内镜像复制一份实现，仅用于锁定其格式化口径（82548 -> 82.5K 等）。
// 若 Dashboard 的 formatTokens 实现变化，此镜像需同步——故此文件同时是回归锚点。
function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0';
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

describe('formatTokens 口径锁定', () => {
  it('0 → 0', () => {
    expect(formatTokens(0)).toBe('0');
  });
  it('负数 → 0', () => {
    expect(formatTokens(-5)).toBe('0');
  });
  it('NaN → 0', () => {
    expect(formatTokens(Number.NaN)).toBe('0');
  });
  it('Infinity → 0（Number.isFinite=false）', () => {
    expect(formatTokens(Number.POSITIVE_INFINITY)).toBe('0');
  });
  it('999 → 999（< 1000 原样）', () => {
    expect(formatTokens(999)).toBe('999');
  });
  it('1000 → 1.0K', () => {
    expect(formatTokens(1000)).toBe('1.0K');
  });
  it('82548 → 82.5K', () => {
    expect(formatTokens(82548)).toBe('82.5K');
  });
  it('999999 → 1000.0K（< 1M 走 K 分支）', () => {
    expect(formatTokens(999999)).toBe('1000.0K');
  });
  it('1000000 → 1.00M', () => {
    expect(formatTokens(1_000_000)).toBe('1.00M');
  });
  it('1234567 → 1.23M', () => {
    expect(formatTokens(1_234_567)).toBe('1.23M');
  });
  it('1000000000 → 1.00B', () => {
    expect(formatTokens(1_000_000_000)).toBe('1.00B');
  });
  it('1234567890 → 1.23B', () => {
    expect(formatTokens(1_234_567_890)).toBe('1.23B');
  });
});
