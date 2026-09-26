# v20.3.2 发行说明 — nginx 静态加速 + 图生图时长提示

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🚀 亮点

### P0 nginx 静态资源加速（CDN/缓存/压缩）
- `/assets/*` hash 文件：`Cache-Control: public, max-age=31536000, immutable` + `expires 1y`（浏览器/CDN 长期缓存，回源大减）
- gzip 压缩补全（js/css/json/svg）：JS 124KB→48KB（**-62%**）
- 首页 + `/index.html`：`no-cache, no-store`（防旧 hash chunk 引用）
- 配置备份 `/etc/nginx/sites-available/imagefree.bak-2031`

### UX 图生图时长提示
- PortalGenerate 图生图 busy 态显示「图生图生成约需 5-10 分钟，请耐心等待…」（双语 zh/en）
- 解决用户提交后无预期、困惑 pending 状态的问题

## ✅ 验证
- 静态资源响应头真实含 immutable + Content-Encoding: gzip
- 首页 no-cache 生效
- 生产全路由回归（/ /admin /v1/healthz /v1/gallery /v1/chat/models /docs）全 200

## 📋 文件清单
- landing/src/components/PortalGenerate.vue（img 时长提示 + 样式）
- landing/src/composables/useI18n.js（pgen.edit_hint 双语）
- 版本全链 bump 20.3.2（12 文件）
- nginx 配置（服务器，不入 git）
