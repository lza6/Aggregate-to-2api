# Litestream 异地备份恢复流程

> 配套：`deploy/litestream.yml` + `docker-compose.yml` 的 `backup` profile。
> 适用场景：本地 SQLite 损坏 / 误删 / 整机故障，从 R2/S3 异地副本恢复。

## 前置条件

1. 已按 `deploy/litestream.yml` 启用 backup profile 跑过一段时间，WAL 已复制到对象存储。
2. 取得 R2/S3 凭证：`LITESTREAM_ACCESS_KEY_ID` / `LITESTREAM_SECRET_ACCESS_KEY` / endpoint / bucket。
3. 在恢复机准备空目录（避免与现有库冲突），如 `./restore-data/`。

## 恢复流程（按库逐个执行）

### 1. 临时恢复容器（不挂业务卷，只跑 litestream restore）

在 `deploy/` 目录新建临时 compose 配置 `docker-compose.restore.yml`：

```yaml
services:
  litestream-restore:
    image: litestream/litestream:latest
    container_name: imagefree-litestream-restore
    volumes:
      - ./restore-data:/data
      - ./litestream.yml:/etc/litestream.yml:ro
    environment:
      - LITESTREAM_ACCESS_KEY_ID=${LITESTREAM_ACCESS_KEY_ID}
      - LITESTREAM_SECRET_ACCESS_KEY=${LITESTREAM_SECRET_ACCESS_KEY}
    entrypoint: ["litestream"]
    command: ["restore", "-config", "/etc/litestream.yml", "/data/imagefree.db"]
    profiles: ["restore"]
```

执行：

```bash
cd deploy
# 设凭证（与备份侧一致）
export LITESTREAM_ACCESS_KEY_ID=<填>
export LITESTREAM_SECRET_ACCESS_KEY=<填>
export LITESTREAM_S3_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
export LITESTREAM_S3_BUCKET=imagefree-backups

# 恢复主库（也可加 -o <目标路径> 覆盖默认位置）
docker compose -f docker-compose.yml -f docker-compose.restore.yml --profile restore run --rm litestream-restore

# 重复恢复号池 / 邮箱池：把 command 的 /data/imagefree.db 改成
# /data/account_pool.db / /data/email_registry.db 各跑一次
```

### 2. 数据一致性校验

恢复完成后，对每个 db 跑 SQLite 完整性检查：

```bash
cd deploy/restore-data
sqlite3 imagefree.db "PRAGMA integrity_check;"
sqlite3 account_pool.db "PRAGMA integrity_check;"
sqlite3 email_registry.db "PRAGMA integrity_check;"
```

期望输出 `ok`。若非 ok：

- WAL 残留损坏：`sqlite3 imagefree.db ".recover" > recovered.sql` 后重建库。
- 副本不完整：换更早时间点的 snapshot（litestream restore `-timestamp` 参数，见官方文档）。

### 3. 切换回业务

1. 停业务容器：`docker compose down`
2. 替换业务 db：`cp restore-data/imagefree.db data/imagefree.db`（保留原损坏库为 `.broken` 以备分析）
3. 重启：`docker compose up -d api`
4. 验证：`curl http://localhost:8100/v1/healthz | jq .db_rows`（应有行数）
5. 重启 backup profile：`docker compose --profile backup up -d litestream`

## RPO 与保留策略

| 项 | 默认值 | 含义 |
|----|--------|------|
| `sync-interval` | 1s | WAL 复制间隔（RPO ≤ 1s） |
| `retention` | 72h | 副本保留窗口 |
| `retention-check-interval` | 1h | 清理过期副本扫描间隔 |
| `snapshot-interval` | 1h | 全量快照间隔（WAL 链太长时加速恢复） |

调整位置：`deploy/litestream.yml` 每个 `replicas` 块。

## 故障演练（推荐每月一次）

1. 模拟损坏：`echo "corrupt" >> data/imagefree.db`
2. 停 api：`docker compose stop api`
3. 跑上述恢复流程。
4. 验证恢复后 db 完整 + api 正常起。
5. 删演练数据：`rm restore-data/*.db*`。

## 已知限制

- Litestream 不复制未持久化的内存状态（worker 队列 / LRU 缓存 / token 池）—— 这些是运行时状态，恢复后由 api 重新构建。
- `edit_leases.db` 未纳入备份（短时租约，恢复后重新建立即可）。
- 对象存储凭证泄露风险：R2/S3 token 建议用受限 scope（只读写 imagefree-backups bucket）。
