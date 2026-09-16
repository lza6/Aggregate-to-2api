// P1-6 i18n 测试：
// (a) en/zh 字典 key 集完全一致（无缺失/多余）
// (b) t() 对已知 key 返回对应文案（含 {n} 占位插值）
// (c) 未知 key 回退 key 本身（不崩）
// (d) useLang 切换后 localStorage 持久化 + <html lang> 属性同步
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { t, setLang, getLang, useLang, isLangComplete } from '../i18n';
import { messagesZh } from '../i18n/messages.zh';
import { messagesEn } from '../i18n/messages.en';

describe('i18n 模块 P1-6', () => {
  beforeEach(() => {
    // 每例前复位为默认 zh，避免用例间语言状态污染
    setLang('zh');
    localStorage.removeItem('if-lang');
  });

  afterEach(() => {
    setLang('zh');
  });

  it('(a) en 与 zh 的 key 集完全一致：无缺失、无多余', () => {
    const { missingInEn, missingInZh, extraInEn } = isLangComplete();
    expect(missingInEn).toEqual([]);
    expect(missingInZh).toEqual([]);
    expect(extraInEn).toEqual([]);
  });

  it('(a) 两个字典 key 数量一致且非空', () => {
    const zhKeys = Object.keys(messagesZh);
    const enKeys = Object.keys(messagesEn);
    expect(zhKeys.length).toBeGreaterThan(0);
    expect(zhKeys.length).toBe(enKeys.length);
  });

  it('(b) t() 对已知 key 返回对应语言文案（默认 zh）', () => {
    expect(t('nav.generate')).toBe('在线生成');
    expect(t('tasks.statusProcessing')).toBe('处理中');
    expect(t('gallery.zip')).toBe('打包下载 ZIP');
    // 切换 en 后取英文
    setLang('en');
    expect(t('nav.generate')).toBe('Generate');
    expect(t('tasks.statusProcessing')).toBe('Processing');
    expect(t('gallery.zip')).toBe('Download ZIP');
  });

  it('(b) t() 支持 {n} 占位符插值', () => {
    expect(t('tasks.total', { n: 42 })).toBe('共 42 条记录');
    expect(t('gallery.selected', { n: 3 })).toBe('已选 3 张');
    setLang('en');
    expect(t('tasks.total', { n: 42 })).toBe('42 records in total');
    expect(t('gallery.selected', { n: 3 })).toBe('3 selected');
  });

  it('(c) 未知 key 回退 key 本身（不崩）', () => {
    const unknown = 'some.unknown.key';
    expect(t(unknown)).toBe(unknown);
    setLang('en');
    expect(t(unknown)).toBe(unknown);
  });

  it('(d) useLang 切换后持久化到 localStorage + 同步 <html lang> 属性', () => {
    // 初始：默认 zh → lang 属性 zh-CN，localStorage 无值
    expect(document.documentElement.lang).toBe('zh-CN');
    expect(getLang()).toBe('zh');

    const { result } = renderHook(() => useLang());
    expect(result.current.lang).toBe('zh');

    act(() => result.current.setLang('en'));
    expect(result.current.lang).toBe('en');
    expect(localStorage.getItem('if-lang')).toBe('en');
    expect(document.documentElement.lang).toBe('en');

    // 切换后 t() 立即返回英文（模块级 currentLang 同步更新）
    expect(t('nav.dashboard')).toBe('Dashboard');
  });

  it('(d) 语言切换后 useLang hook 响应式更新 lang', () => {
    const { result } = renderHook(() => useLang());
    expect(result.current.lang).toBe('zh');
    act(() => result.current.toggle());
    expect(result.current.lang).toBe('en');
    expect(localStorage.getItem('if-lang')).toBe('en');
    act(() => result.current.toggle());
    expect(result.current.lang).toBe('zh');
  });

  it('(d) setLang 持久化后 getLang 与 localStorage 一致（冷启动检测来源）', () => {
    setLang('en');
    expect(getLang()).toBe('en');
    expect(localStorage.getItem('if-lang')).toBe('en');
  });
});