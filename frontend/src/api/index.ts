// P3 剩余风险治理：api.ts → api/ 子目录 barrel。
// `import { xxx } from '../api'` 解析到本文件（api/index.ts），聚合 re-export 全部子域。
// 拆分解决原 api.ts 857 行超 800 上限，且避免 api.ts 与 api/ 目录同名的路径歧义。

export * from './core';
export * from './providers';
export * from './tasks';
export * from './chat';
export * from './security';
export * from './misc';
