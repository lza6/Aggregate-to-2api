// src/lib/theme.ts — P1-7 主题优先级链（localStorage 手动覆盖 > 系统 prefers-color-scheme）。
//
// 原实现：theme 完全由 CSS `@media (prefers-color-scheme: dark)` 驱动，无手动覆盖。
// 本模块引入 `data-theme` 属性（挂在 <html>）作为唯一权威来源：
//   1. localStorage['tf-theme'] 有值（用户手动选 light/dark）→ 以该值覆盖系统，且系统变化不再跟随；
//   2. 未设置 → 跟随系统（matchMedia change 时更新）；
//   3. 跨标签页修改（storage 事件）→ 同步。
// 浏览器/B 端部署与 Tauri 桌面一致；桌面端 index.html 内联脚本被 CSP 拦截时由 main.tsx 的 initTheme() 兜底，
// 且桌面窗口 visible:false 直到后端就绪，无 FOUC（见 desktop/README.md）。
//
// CSS 侧配套：index.css 的 `@media (prefers-color-scheme: dark)` 增加 `:not([data-theme])` 守卫（无 JS/隐私模式
// 兜底），并新增 `:root[data-theme='dark']` 手动深色；浅色即 `:root` 默认，无需额外规则。

export type ThemePreference = 'system' | 'light' | 'dark';

export const THEME_KEY = 'tf-theme';

const isDarkQuery = () =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null;

/** 读取用户偏好：localStorage 仅接受 light/dark，其余（含缺失/损坏）视为 system。 */
export function getStoredPreference(storage: Storage = window.localStorage): ThemePreference {
  const v = storage.getItem(THEME_KEY);
  return v === 'light' || v === 'dark' ? v : 'system';
}

/** 解析最终主题：system 跟随系统，手动值直接返回（覆盖系统）。 */
export function resolveTheme(pref: ThemePreference, systemDark: boolean): 'light' | 'dark' {
  return pref === 'system' ? (systemDark ? 'dark' : 'light') : pref;
}

/** 把解析结果写入 <html data-theme>（幂等，可反复调用）。 */
export function applyTheme(root: HTMLElement, pref: ThemePreference, systemDark: boolean): 'light' | 'dark' {
  const theme = resolveTheme(pref, systemDark);
  root.setAttribute('data-theme', theme);
  return theme;
}

/** 写入用户偏好：'system' 清除存储（回到跟随系统），light/dark 持久化。 */
export function setThemePreference(pref: ThemePreference, storage: Storage = window.localStorage): void {
  if (pref === 'system') storage.removeItem(THEME_KEY);
  else storage.setItem(THEME_KEY, pref);
}

export interface ThemeControllerHandle {
  /** 当前生效主题（light/dark） */
  current: 'light' | 'dark';
  /** 解除 matchMedia/storage 监听 */
  dispose: () => void;
}

/**
 * 初始化主题控制器：立即应用一次 + 挂系统偏好变化与跨标签 storage 监听。
 * 在 main.tsx（React 渲染前）调用一次；返回 dispose（应用生命周期内不需要）。
 * matchMedia 缺省守卫：jsdom 无 matchMedia 时仅做一次应用，不挂系统监听。
 */
export function initTheme(
  root: HTMLElement = document.documentElement,
  storage: Storage = window.localStorage,
): ThemeControllerHandle {
  const mq = isDarkQuery();
  const apply = () => applyTheme(root, getStoredPreference(storage), mq?.matches ?? false);

  apply();
  let disposed = false;

  const onSystemChange = () => {
    if (disposed) return;
    // 用户手动选择后不再跟随系统
    if (getStoredPreference(storage) !== 'system') return;
    apply();
  };
  const onStorage = (e: StorageEvent) => {
    if (disposed) return;
    if (e.key === null || e.key === THEME_KEY) apply();
  };

  mq?.addEventListener('change', onSystemChange);
  window.addEventListener('storage', onStorage);

  return {
    current: applyTheme(root, getStoredPreference(storage), mq?.matches ?? false),
    dispose: () => {
      disposed = true;
      mq?.removeEventListener('change', onSystemChange);
      window.removeEventListener('storage', onStorage);
    },
  };
}