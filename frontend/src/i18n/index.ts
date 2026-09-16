// 轻量 i18n（P1-6）：约 0 依赖 —— 不引入 i18next / react-i18next。
// - t(key) 按当前语言取值，缺失回退 key 本身（不崩，未接入页面保持中文渐进式）。
// - 支持 {n} 占位符插值：t('tasks.total', { n: total })。
// - useLang() / useT()：React hook（useSyncExternalStore），切换语言全组件响应式重渲染。
// - localStorage 持久化（'if-lang'）+ <html lang> 属性同步（无障碍 + SEO）。
// - 默认语言 zh；en 与 zh key 集一致性由 isLangComplete() 断言（src/test/i18n.test.ts）。
import { useCallback, useSyncExternalStore } from 'react';
import { messagesZh } from './messages.zh';
import { messagesEn } from './messages.en';

export type Lang = 'zh' | 'en';
export type MessageKey = keyof typeof messagesZh;

export const messages: Record<Lang, Record<string, string>> = {
  zh: messagesZh,
  en: messagesEn,
};

const STORAGE_KEY = 'if-lang';
const DEFAULT_LANG: Lang = 'zh';

function detectInitialLang(): Lang {
  if (typeof window === 'undefined') return DEFAULT_LANG;
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === 'zh' || saved === 'en') return saved;
  } catch {
    /* localStorage 不可用（隐私模式）静默忽略 */
  }
  return DEFAULT_LANG;
}

let currentLang: Lang = detectInitialLang();
const listeners = new Set<() => void>();

function applyLangAttr(lang: Lang): void {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
  }
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function getSnapshot(): Lang {
  return currentLang;
}

// 模块加载即同步一次 <html lang>（首帧无障碍/SEO），不写 localStorage。
applyLangAttr(currentLang);

/** 切换语言：持久化 localStorage + 同步 <html lang> + 通知所有订阅组件。 */
export function setLang(lang: Lang): void {
  if (lang !== 'zh' && lang !== 'en') return;
  currentLang = lang;
  try {
    window.localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* 忽略 */
  }
  applyLangAttr(lang);
  listeners.forEach(cb => cb());
}

/** 当前语言（非响应式读取；组件内请用 useLang/useT）。 */
export function getLang(): Lang {
  return currentLang;
}

/** 中英往返切换，返回切换后的语言。 */
export function toggleLang(): Lang {
  const next: Lang = currentLang === 'zh' ? 'en' : 'zh';
  setLang(next);
  return next;
}

function tIn(lang: Lang, key: string, params?: Record<string, string | number>): string {
  const dict = messages[lang] ?? messages.zh;
  let str = dict[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      str = str.split(`{${k}}`).join(String(v));
    }
  }
  return str;
}

/** 纯函数翻译：按指定语言取文案，缺失回退 key，{n} 占位插值。 */
export function t(key: MessageKey | string, params?: Record<string, string | number>): string {
  return tIn(currentLang, key, params);
}

/** en/zh 字典 key 集一致性检查（测试断言用）。 */
export function isLangComplete(): { missingInEn: string[]; missingInZh: string[]; extraInEn: string[] } {
  const zhKeys = Object.keys(messagesZh) as MessageKey[];
  const enKeys = Object.keys(messagesEn);
  const zhSet = new Set<string>(zhKeys);
  const enSet = new Set<string>(enKeys);
  return {
    missingInEn: zhKeys.filter(k => !enSet.has(k)),
    missingInZh: enKeys.filter(k => !zhSet.has(k)),
    extraInEn: enKeys.filter(k => !zhSet.has(k)),
  };
}

/** React hook：响应式读取当前语言 + 切换函数。 */
export function useLang(): { lang: Lang; setLang: (lang: Lang) => void; toggle: () => void } {
  const lang = useSyncExternalStore(subscribe, getSnapshot);
  return { lang, setLang, toggle: toggleLang };
}

/** React hook：响应式 t() —— 语言切换后自动重渲染并返回最新文案。 */
export function useT(): (key: MessageKey | string, params?: Record<string, string | number>) => string {
  const lang = useSyncExternalStore(subscribe, getSnapshot);
  return useCallback((key, params) => tIn(lang, key, params), [lang]);
}
