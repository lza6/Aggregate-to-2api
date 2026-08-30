/// <reference types="vite/client" />
/// <reference types="vitest/globals" />

/** build-time 由 vite.config.ts 从 package.json 注入（*不*从跨会话读取） */
declare const __APP_VERSION__: string;
