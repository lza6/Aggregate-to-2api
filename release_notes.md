## v4.3.0 config/db/worker 三文件拆分 + CI修复 + 号池补号脚本

### 架构拆分（P0 大文件）
- config.py(1026行) → `api/config/` 12 文件包（base/db/http/solver/cache/provider/pool/queue/observability/edit/security/settings）
- db.py(1087行) → `api/db/` 3 文件包（core 连接池+批量写+查询/清理 + queries QueueDB + __init__ 聚合导出）
- worker.py(993行) → `api/worker/` 3 文件包（engine 核心引擎 + token_pool 预取池 + __init__ 聚合导出）
- 全部向后兼容：`from api.config import config` / `from api.db import DB` / `from api.worker import Engine` 零改动可用
- 旧单体文件 `api/{config,db,worker}.py` 已 git rm

### 验证
- 42 路由全部注册正常
- test_adaptive_router 14 passed / test_main_validation / test_edit_mutex / test_imagefree_client / test_db_* 全绿
- 生产重建后端 `healthz: ok | workers: 10` / `/v1/models: 33 模型 3 提供商`

### CI 修复
- liint 去掉 `|| true`（真实拦截）
- 单元/集成测试分 `-m` 标记区分运行
- Docker 构建前加 `sync_deploy.py check`

### 号池补号
- `scripts/batch_register_nb.py`：断点续跑 + 错误分类退避 + 并发 2 + checkpoint + SIGTERM 优雅退出
- `scripts/supervise_reg.sh` wrapper 崩溃自动重启
- nanobanana 返回名额定位目标 10000

### 其他
- docs.html 提供商数 4→3 / 版本 v4.2.1（上次已上）
- docker-compose 版本号 v4.2.1