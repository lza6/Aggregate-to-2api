# v20.3.5 发行说明 — 数据备份机制闭环 + SOP 运维完善

> 发布日期：2026-09-26 ｜ 分支：main ｜ 生产：https://imagefree.hwhcie.bond

## 🛡️ 数据备份闭环（可恢复性保障）

**现状确认**：仓库已有 `scripts/backup_db.py`（VACUUM INTO 在线热备，WAL 安全不锁写），但生产未配置 cron → 数据无自动备份。

**本轮闭环**：
- 生产 cron 配置：每日 03:00 全量备份 7 个 SQLite DB（imagefree/account_pool/dag_runs/email_registry/human_inbox/queue/skills）
- 备份输出 `/opt/imagefree-api/backups/<db>-<时间戳>.db`，保留 7 天自动清理
- 备份后自动 `PRAGMA integrity_check` + `requests` 行数核对

## ✅ 验证
- 全量备份 7/7 成功（imagefree.db requests=20 行校验 + integrity ok）
- **恢复演练**：7/7 备份文件 integrity_check = ok（真实可恢复，非损坏备份）
- 简化版脚本误建已删（无双脚本冲突）

## 📋 文件清单
- docs/SOP.md（v3.1.0 补「数据库备份」章节：机制/范围/cron/手动备份/恢复步骤）
- docs/verification-log.md（备份闭环验证记录）
- 版本全链 bump 20.3.5
