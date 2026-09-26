# imagefree API 标准操作程序（SOP）

> 版本: 3.1.0 | 最后更新: 2026-09-26
> 适用: 本机（Windows 开发）+ 线上服务器（Azure 20.204.27.154，systemd + nginx）
> 公网入口: `https://imagefree.hwhcie.bond`（nginx 443 → FastAPI 8100）
> 当前代码版本: v20.3.x（发版前先核对 pyproject.toml/README 版本徽章）

---

## 1. 生产架构（真实现状）

| 组件 | 说明 |
|------|------|
| API 服务 | `systemd imagefree-api.service`，WorkingDirectory=/opt/imagefree-api，uvicorn :8100 |
| CF 求解 | `systemd imagefree-cfsolver.service`（camoufox，:8001） |
| Web 入口 | nginx 443（sites-available/imagefree）→ 代理 :8100 |
| 域名 | `*.hwhcie.bond` → 20.204.27.154（泛解析） |
| 数据库 | `/opt/imagefree-api/data/imagefree.db`（SQLite，WAL） |
| 前端 | landing（Vue3 门户，挂载 /）+ frontend（React 管理台，挂载 /admin） |
| 静态缓存 | nginx /assets immutable 1y + gzip（v20.3.2 起） |

**服务管理**：
```bash
systemctl status imagefree-api        # 状态
systemctl restart imagefree-api       # 重启（改代码/配置后）
journalctl -u imagefree-api -n 100    # 看日志
systemctl reload nginx                # nginx 配置热重载
```

---

## 2. 部署流程（发版）

### 2.1 本地构建（Windows）
```powershell
# 后端（无构建，git 直接部署）
cd C:\Users\Administrator.DESKTOP-EGNE9ND\Desktop\imagefree-2ai
git add -A && git commit -m "..." && git push origin main

# 前端 dist（服务器无 node，需本地构建后上传）
cd landing && npm.cmd run build       # → landing/dist
cd frontend && npm.cmd run build      # → frontend/dist（/admin）
```

### 2.2 服务器部署
```bash
# 1. 拉代码
cd /opt/imagefree-api && git pull --ff-only origin main

# 2. 上传 dist（SFTP）
#    landing/dist → /opt/imagefree-api/landing/dist（先备份 dist.bak-<版本>）
#    frontend/dist → /opt/imagefree-api/frontend/dist

# 3. 重启
systemctl restart imagefree-api && systemctl is-active imagefree-api

# 4. 验证
curl -s http://127.0.0.1:8100/v1/healthz | head -c 200
curl -s -o /dev/null -w "home=%{http_code} admin=%{http_code}\n" http://127.0.0.1:8100/ http://127.0.0.1:8100/admin/
```

### 2.3 nginx 配置改动
```bash
cp /etc/nginx/sites-available/imagefree /etc/nginx/sites-available/imagefree.bak-<日期>
# 编辑后:
nginx -t && systemctl reload nginx
```

---

## 3. 数据库备份（可恢复性保障，v20.3.5 确认配置）

**机制**：`scripts/backup_db.py`（VACUUM INTO 在线热备，WAL 安全不锁写）
- 备份范围：data/ 下全部 7 个 SQLite DB（imagefree/account_pool/dag_runs/email_registry/human_inbox/queue/skills）
- 输出：`/opt/imagefree-api/backups/<db>-<时间戳>.db`
- 校验：备份后自动 `PRAGMA integrity_check` + `requests` 行数核对
- 保留：`--keep-days 7`（超期自动清理）

**cron 调度**（已在生产配置）：
```bash
0 3 * * * cd /opt/imagefree-api && /opt/imagefree-api/.venv/bin/python scripts/backup_db.py --all --out-dir /opt/imagefree-api/backups --keep-days 7 >> /opt/imagefree-api/backups/backup.log 2>&1
```

**手动备份 / 恢复演练**：
```bash
# 手动全量备份
cd /opt/imagefree-api && .venv/bin/python scripts/backup_db.py --all --out-dir /opt/imagefree-api/backups --keep-days 7

# 恢复（用备份文件替换 data/ 下对应 db，先停服务避免写冲突）
systemctl stop imagefree-api
cp backups/imagefree-<时间戳>.db data/imagefree.db
systemctl start imagefree-api
```

---

## 3. 功能开关（systemd 环境变量）

| 开关 | 值 | 作用 |
|------|-----|------|
| IF_PPT_GENERATE | 1 | PPT 生成（python-pptx） |
| IF_VIDEO_ENABLED | 0 | 视频 Mock（上游待接入） |
| IF_FREE_PROXY | 1 | 免费代理池（高并发换 IP） |
| IF_MOCK_UPSTREAM | (缺省) | 0=真实上游，1=Mock |
| IF_API_KEYS | 空 | 匿名开放（配 Key 则启用鉴权） |

改开关：编辑 `/etc/systemd/system/imagefree-api.service` → `systemctl daemon-reload && systemctl restart imagefree-api`

---

## 4. 常见排障

| 症状 | 排查 | 修复 |
|------|------|------|
| 图生图 500 TLS | journalctl 查 SSLV3 | 已修复（R2 SNI）v20.3.1 |
| 页面旧 chunk 404 | index.html 缓存 | nginx no-cache 已配 /assets immutable |
| 上游瞬时 429 | 重试即成功 | 代理池自动换 IP |
| cf_solver 熔断 | healthz solver_status | 重启 cfsolver 服务 |

---

## 5. 验证记录约定（防重复优化）

已闭环项记录在 `docs/verification-log.md` + workflow_status「已验证勿重做」——
新任务先查该清单，避免重复跑同一测试/优化。
