// src/hooks/useTheme.ts — P1-7 主题控制 React 钩子（顶栏主题切换按钮用）。
// 三态循环：跟随系统 → 浅色 → 深色 → 跟随系统。状态与 localStorage 双向同步，
// 外部（跨标签页/手动改 localStorage）变化经 storage 事件回同步到 React state。
import { useCallback, useEffect, useState } from 'react';
import {
  applyTheme,
  getStoredPreference,
  initTheme,
  setThemePreference,
  THEME_KEY,
  type ThemePreference,
} from '../lib/theme';

const CYCLE: ThemePreference[] = ['system', 'light', 'dark'];

export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(() => getStoredPreference());

  // 挂主题控制器：应用一次 + 系统偏好变化跟随 + storage 事件回同步
  useEffect(() => {
    const handle = initTheme();
    return handle.dispose;
  }, []);

  // 跨标签页/外部写入 localStorage 时同步按钮态
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === null || e.key === THEME_KEY) setPreference(getStoredPreference());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const cycleTheme = useCallback(() => {
    const next: ThemePreference = CYCLE[(CYCLE.indexOf(preference) + 1) % CYCLE.length];
    setThemePreference(next);
    setPreference(next);
    // L6 修复（审查）：jsdom 无 matchMedia → 可选链守卫（与 initTheme 一致），浏览器不受影响
    const dark = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-color-scheme: dark)').matches : false;
    applyTheme(document.documentElement, next, dark);
  }, [preference]);

  return { preference, cycleTheme };
}
