// src/test/theme.test.ts — P1-7 主题优先级链（localStorage 手动覆盖 > 系统 prefers-color-scheme）。
// 验收：
// - 优先级链：未设置 → 跟随系统；手动 light/dark → 覆盖系统（含系统变化不回归）
// - 存储往返：system 清除存储、light/dark 持久化
// - applyTheme 幂等写 data-theme
// - jsdom 无 matchMedia → initTheme 只应用一次不抛错（浏览器/测试环境零回归）
import { describe, it, expect, afterEach } from 'vitest';
import {
  applyTheme,
  getStoredPreference,
  initTheme,
  resolveTheme,
  setThemePreference,
  THEME_KEY,
} from '../lib/theme';

afterEach(() => {
  try { localStorage.removeItem(THEME_KEY); } catch { /* 忽略 */ }
});

describe('resolveTheme 优先级链', () => {
  it('未设置（system）+ 系统深色 → dark', () => {
    expect(resolveTheme('system', true)).toBe('dark');
  });
  it('未设置（system）+ 系统浅色 → light', () => {
    expect(resolveTheme('system', false)).toBe('light');
  });
  it('手动 light 覆盖系统深色 → light', () => {
    expect(resolveTheme('light', true)).toBe('light');
  });
  it('手动 dark 覆盖系统浅色 → dark', () => {
    expect(resolveTheme('dark', false)).toBe('dark');
  });
});

describe('getStoredPreference / setThemePreference 存储往返', () => {
  it('默认 system（localStorage 未设置）', () => {
    expect(getStoredPreference()).toBe('system');
  });
  it('手动 dark 持久化并读回', () => {
    setThemePreference('dark');
    expect(getStoredPreference()).toBe('dark');
    expect(localStorage.getItem(THEME_KEY)).toBe('dark');
  });
  it('切回 system 清除存储（回到跟随系统）', () => {
    setThemePreference('dark');
    setThemePreference('system');
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
    expect(getStoredPreference()).toBe('system');
  });
  it('损坏的存储值视为 system（不崩）', () => {
    localStorage.setItem(THEME_KEY, 'banana');
    expect(getStoredPreference()).toBe('system');
  });
});

describe('applyTheme', () => {
  it('写 data-theme 属性（幂等）', () => {
    const el = document.createElement('html');
    expect(applyTheme(el, 'dark', false)).toBe('dark');
    expect(el.getAttribute('data-theme')).toBe('dark');
    expect(applyTheme(el, 'system', true)).toBe('dark');
    expect(el.getAttribute('data-theme')).toBe('dark');
    expect(applyTheme(el, 'light', true)).toBe('light');
    expect(el.getAttribute('data-theme')).toBe('light');
  });
});

describe('initTheme（jsdom 无 matchMedia）', () => {
  it('不抛错并写 data-theme；dispose 安全', () => {
    const el = document.createElement('html');
    const handle = initTheme(el);
    expect(el.getAttribute('data-theme')).toMatch(/^light|dark$/);
    expect(() => handle.dispose()).not.toThrow();
  });
  it('手动偏好写入后 initTheme 应用手动值', () => {
    const el = document.createElement('html');
    setThemePreference('dark');
    initTheme(el);
    expect(el.getAttribute('data-theme')).toBe('dark');
  });
});
