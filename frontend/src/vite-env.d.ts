/// <reference types="vite/client" />

/** build-time 由 vite.config.ts 从 package.json 注入（*不*从跨会话读取） */
declare const __APP_VERSION__: string;