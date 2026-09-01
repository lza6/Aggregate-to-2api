# 听风AI v7.1.0 发布说明

## 概述

v7.1.0 是**数据安全 + 资源治理 + 代码整洁度**版本。基于 v7.0.0 已上线基线，本版系统性落地《下一步改进指南.md》P2 全档（P2-1~P2-6）：

- **P2-1 DB 自动备份+恢复**（VACUUM INTO 在线热备 + cron 调度 + 恢复演练 SOP）
- **P2-2 封禁表分页**（list_all 改 page/page_size/since_ts + 前端分页 UI，防 OOM）
- **P2-3 同步 sqlite3 评估**（to_thread 在当前流量下非瓶颈，留 v7.3 专项，本轮仅记录）
- **P2-4 大文件拆分**（Accounts.tsx 987→276 行，拆 6 子组件；api.ts 保留聚合口）
- **P2-5 config 模块级实例化测试钩子**（get_settings/reset_settings + conftest autouse 防污染）
- **P2-6 worker 缩容判定简化 + 硬编码评估**（早返回简化；nanobanana/tryingopen 已是动态嗅探自愈，不抽 config）

**向后兼容，无破坏性变更，不改变现有 API 契约。**

---

## P2-1 DB 自动备份+恢复

### 实现
- `scripts/backup_db.py`（新建）：sqlite3 `VACUUM INTO` 在线热备（WAL 模式安全）+ `wal_checkpoint(TRUNCATE)` + `integrity_check` + 行数校验 + 滚动清理（`--keep-days 7`）+ `--all` 批量备份所有 data/*.db
- `scripts/restore_db.py`（新建）：备份预检 → 自动 pre-restore 当前 target（防覆盖）→ 复制恢复 → 清理残留 WAL/SHM → integrity_check + 行数对照
- `deploy/docker-compose.yml`：api volumes 加 `./data/backups:/app/data/backups` 持久化 + 顶部注释加 crontab 调度说明
- `docs/SOP.md`：追加「DB 备份与恢复」章节（备份策略/命令/恢复/演练步骤/异地副本/注意事项）

### 验证
- 造测试 DB（requests=3）→ `backup_db.py` → 备份成功 + integrity=ok + 行数=3 ✓
- `restore_db.py` → 恢复成功 + pre-restore 机制验证通过 ✓
- `ruff check scripts/backup_db.py scripts/restore_db.py` → All checks passed!

---

## P2-2 封禁表分页（防 OOM）

### 实现
- `api/db/ip_blocklist_store.py`：`list_all` 改分页（`limit/offset/since_ts`，limit 钳到 [1,10000]）+ 新增 `count(since_ts)` 单 SELECT COUNT（不加载全部数据）
- `api/routes/security.py`：`blocklist` 端点改 `page/page_size/since_ts` 参数 + 旧 `limit` 兼容 + 信封 `{items,count,total,page,page_size,has_more}`；`stats` 端点用 `count()` 替代全量加载
- `api/bg_tasks.py:99`：`blocked_ip_count` 改用 `count()` 替代 `len(list_all(2000))`
- `api/request_guard.py:275`：`_sync_blocklist_cache` 改分页累加（page_size=1000 分批拉取聚合），防 OOM
- `frontend/src/api.ts`：`fetchBlocklist` 改 `{page,pageSize,limit}` 签名 + `BlocklistPage` 类型
- `frontend/src/pages/Security.tsx`：分页 UI（page state + 首页/上页/下页按钮 + 总页数 + has_more 禁用）

### 验证
- `tests/test_ip_blocklist.py` 新增 `TestPaginationAndCount` 6 用例 → **28 passed**
- 向后兼容：旧 `list_all(limit=N)` 仍工作；端点旧 `?limit=N` 仍兼容
- `ruff check` → All checks passed!

---

## P2-3 同步 sqlite3 评估（不迁移，记录结论）

- v6.9.0 P0-3 已用 `asyncio.to_thread` 包裹 account_pool/email_pool 同步 sqlite3（缓解事件循环阻塞）
- **评估结论**：to_thread 在当前流量下非瓶颈（线上 P95 时延分解未显示线程池饱和），迁移到 aiosqlite 是 L3 大工程（跨 account_pool/email_pool/registerer/nanobanana 多文件 async 传染），**留 v7.3 专项**，本轮不迁移。

---

## P2-4 大文件拆分

### 实现
- `frontend/src/pages/Accounts.tsx` 987 → **276 行**，拆 6 子组件到 `frontend/src/components/accounts/`：
  - `PoolCard.tsx`（60行）单个号池卡片
  - `PoolPausedBanner.tsx`（44行）号池停用横幅
  - `PoolGrowthSection.tsx`（100行）号池补满速率+成本
  - `LiveRegistrationCard.tsx`（65行）最近注册会话画像
  - `AccountTable.tsx`（200行）账号活跃明细表（虚拟滚动 slice）
  - `PaginationBar.tsx`（100行）分页控件+邮箱池分配
- `frontend/src/api.ts` 保留为单一聚合口（857 行，含大量类型定义非逻辑；拆 `api/` 子目录会与 api.ts 同名路径歧义，决策保留聚合口）
- **向后兼容**：`AccountsPage` 导出名不变；`import { fetchAccountPool, ... } from '../api'` 仍可用；`useVirtualList` 仍在顶层（hooks 顺序恒定）

### 验证
- `npx tsc --noEmit` → 0 error
- `npx vitest run` → 193 passed (12 files)
- `npm run build` → ✓ built in 2.71s

---

## P2-5 config 模块级实例化测试钩子

### 实现
- `api/config/__init__.py`：新增 `get_settings()`（lru_cache 风格单例）+ `reset_settings()`（测试重置钩子），保留 `settings = Settings()` 模块级变量向后兼容
- `tests/conftest.py`：新增 autouse fixture `_reset_settings_singleton`，每用例前调 `reset_settings()` 重建单例（读当前 env），防跨文件单例污染（v6.9.0 P0-1 根因）

### 验证
- `pytest tests/test_config_validate.py` → 20 passed
- `pytest tests/test_account_pool.py` → 30 passed（reset 不破现有测试）
- `pytest tests/test_token_pool.py` → 14 passed（排除预存 Windows 卡死 2 用例）
- `ruff check` → All checks passed!

---

## P2-6 worker 缩容判定简化 + 硬编码评估

### 实现
- `api/worker/engine.py` `_auto_scale_once`：缩容判定用早返回简化（消除 `should_shrink` 布尔变量 + `idle_count >= 1` 重复判定冗余），**行为等价**（扩容/缩容条件不变）
- **硬编码评估结论**（不抽 config）：
  - `nanobanana.py` Action ID：已是 `ActionSniffer` 动态嗅探 + `STATIC_ACTION_IDS` 静态兜底，站点改版自动嗅探更新。抽 config 会破坏自愈链路。
  - `tryingopen.py` `_FALLBACK_CATALOG`：已是模块级类常量（站点目录不可访问时兜底），运行时走 `_MODEL_RE` 动态嗅探。抽 config 无意义（目录是上游动态的）。

### 验证
- `pytest tests/test_worker_auto_scale.py` → 14 passed
- `pytest tests/test_worker_health.py` → 8 passed
- `pytest tests/test_tryingopen.py` → 7 passed
- `ruff check` → All checks passed!

---

## 测试

- 后端核心套件逐个跑全绿：
  - test_ip_blocklist **28** / test_config_validate **20** / test_worker_auto_scale **14** / test_worker_health **8** / test_tryingopen **7** / test_security_headers **7** / test_account_pool **30** / test_token_pool **14**（排除预存 Windows 卡死 2）
- 前端：`npx vitest run` → 193 passed (12 files) + `npm run build` ✓ + `npx tsc --noEmit` 0 error
- `ruff check` 全改动文件 → All checks passed!

## 已知限制 / 剩余风险

- **P2-3 同步 sqlite3 未迁移**：to_thread 当前非瓶颈，留 v7.3 专项（L3 大工程，需单独批次评估）。
- **预存卡死用例**：`TestMainObservability::test_healthz_has_solver_fields` / `test_metrics_keeps_legacy_lines` 在 Windows Python 3.14 本地卡死（预存，非本版引入），CI ubuntu+3.11 不受影响。
- **api.ts 857 行略超 800**：含大量类型定义非逻辑，拆 `api/` 子目录会与 api.ts 同名路径歧义，决策保留聚合口（可接受）。
- **未 commit/push/部署**：所有改动留工作区，需用户授权后 commit + 发版 + 部署。

## 部署

- P2-1 DB 备份卷随部署生效；生产 crontab 需在宿主机配置（见 compose 顶部注释）。
- P2-2/P2-5/P2-6 代码改动随镜像构建生效。
