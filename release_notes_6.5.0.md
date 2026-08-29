# 听风AI v6.5.0 发布说明

## 公开首页（/）迁 Vue3 落地页
- 从 3440 行单文件 `docs.html` 迁到独立 **Vue3 + Vite** 应用（`landing/`）
- 引导进 `/admin` 管理台与 Swagger `/docs`；不再在公开页暴露无需鉴权的出图生成器
- `/` 由 `api/main.py` 以 `base:'/'` 挂载 `landing/dist`；原 `health.py GET /` 路由移除

## 号池看板增强
- `/v1/account-pool` 新增 `live_registration`（注册阶段画像 + 每阶段耗时）
- 明细新增列：累计签到 / 本轮第几天 / 累计获得积分 / 存活天数

## 安全
- `task_to_public` 对私网/回环/链路本地 IP 打码（`client_ip=None`），只留「内网/本机」标签

## 版本
- 统一 6.5.0（frontend/package.json + pyproject + docker-compose tag + API version）

## 验证
- landing `npm run build` exit 0；Playwright 真实浏览器 7/0
- frontend tsc 0 + e2e-smoke 12/0
- 后端定向单测通过；`scripts/sync_deploy.py check` 一致
- 线上 `imagefree-api:6.5.0` / `imagefree-cfsolver:6.5.0` healthy

## v6.5.0 增补（2026-08-29）
- **admin 新增「在线生成」页**：文生图（/v1/generate）与图生图（/v1/edit）playground，
  带 API Key（localStorage），/v1/models 按 capability 过滤模型，画幅/分辨率选择，
  图生图最多 3 张参考图，异步任务轮询 + 结果预览。
- **部署要点**：改 `frontend/dist` 后须 `docker compose up -d --force-recreate api` 重新绑定挂载，
  否则容器仍挂旧目录（实测 /admin 404 SYS.003 的根因）。
