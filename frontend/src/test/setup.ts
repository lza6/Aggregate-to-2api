// Vitest 全局测试环境初始化。
// 引入 @testing-library/jest-dom 扩展 expect 断言（toBeInTheDocument 等）。
import '@testing-library/jest-dom';

// Node 22+ 通过 vitest 的 tinypool 注入「Node 内置全局」（localStorage/crypto 等）作为
// 普通对象，会遮蔽 jsdom 的 Storage 实现（导致 localStorage.clear is not a function）。
// 这里用真实 jsdom Storage 实例替换全局 localStorage，恢复 Storage 原型链。
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!DOCTYPE html>', { url: 'http://localhost/' });
const win = dom.window as unknown as {
  localStorage: Storage;
  Storage: typeof Storage;
};
if (typeof localStorage?.clear !== 'function') {
  Object.defineProperty(globalThis, 'localStorage', {
    value: win.localStorage,
    configurable: true,
    writable: true,
  });
  if (win.Storage) (globalThis as { Storage?: typeof Storage }).Storage = win.Storage;
}
