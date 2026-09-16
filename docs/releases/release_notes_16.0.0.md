# v16.0.0 发行说明

> 发布时间：2026-09-16 | 基于 v15.1.1（`f0c5364`）| P0 破圈三件套：画廊管理端、MCP Streamable HTTP、聊天工具执行回路

## 主题：让「能力走出去 + 消费侧不空转」

### 新增（P0-3 画廊管理端 + 前端相册化）

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **画廊分页列表** | `GET /v1/gallery` 支持 page/page_size/status/model/search 过滤，返回 `{items,total,page,page_size,count}`（count/total 双字段兼容新旧消费者）；limit 参数向后兼容旧 `fetchGallery`；无过滤时命中 `gallery:{limit}` 缓存（warmup 预热） | `IF_GALLERY_PAGE_SIZE`(50) |
| **画廊搜索** | `GET /v1/gallery/search?q=` prompt 子串搜索 | — |
| **画廊详情** | `GET /v1/gallery/{task_id}` 单张详情 + similar 相似推荐 top_k（向量未启用时降级空列表不报错） | — |
| **画廊 ZIP 打包** | `POST /v1/gallery/zip` 多 task_id → 服务端临时文件流式 ZIP（StreamingResponse + 完成后清理），`IF_GALLERY_ZIP_BATCH=20` 分批防 512MB 容器 OOM，失败张跳过并回报 `X-Skipped`；修复 data-URI base64 前缀解码 | `IF_GALLERY_ZIP_BATCH`(20) |
| **画廊软删** | `DELETE /v1/gallery/{task_id}` status→deleted 可回滚（不物理删文件） | — |
| **防分页 OOM** | 画廊列表不投影 `image_base64`（ZIP 显式 `read_base64` 文件级读取） | — |
| **前端相册化** | Gallery.tsx 迁移分页端点 + 防抖搜索框 + IntersectionObserver 无限滚动（含「加载更多」按钮兜底）+ 多选操作条 + 删除确认弹窗 + 详情弹窗（大图+元信息+similar 横滑）+ 空/错/骨架三态 | — |

### 新增（P0-1 MCP Streamable HTTP）

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **Streamable HTTP Transport** | `/v1/mcp` 升级官方协议形态：`Accept: text/event-stream` 时 SSE 分帧、capabilities 声明 tools/resources/prompts、`resources/list`（`skills://index` 等）+ `prompts/list`（`image-from-prompt` 等）、`DELETE` 结束会话 | `IF_MCP_STREAMABLE`(1) |
| **异步生图任务契约** | `generate_image` 返回 `{task_id, status: queued}`，新 `task_status` 工具幂等轮询收敛，避免 MCP 单请求阻塞上游 6-30s | — |
| **外部客户端接入** | ApiGuide 新增 Claude Desktop / Cursor 一行配置卡片 + curl 验证示例（含 SSE 分帧） | — |

### 新增（P0-2 聊天工具真实执行回路）

| 项 | 内容 | 开关（缺省） |
|---|---|---|
| **网关侧工具执行** | 聊天 tools 命中白名单（skills_list/skills_get/dag_plan/generate_image + memory_search 只读）时网关侧执行并以 `role: tool` 回填续跑；复用 MCP 同一份 `find_tool`/`guard_and_run`，不复制实现 | `IF_CHAT_TOOL_LOOP`(0) |
| **护栏复用** | 破坏性命令黑名单（`is_destructive_command`）先行拒绝 + 预算门禁（enforce 超限 402 回填「无权限」文本） | `IF_CHAT_TOOL_MAX_TURNS`(2) |

### 修复

| 项 | 内容 |
|---|---|
| **旧 `/v1/gallery` 路由遮蔽** | 旧列表端点（admin/query.py）先注册遮蔽新分页列表 → 原位融合为权威实现（limit 兼容 + 缓存 + 双字段），并删除 gallery.py 重复列表路由避免双路由 |
| **ZIP 空包 bug** | 生产落库的 `image_base64` 是 data-URI（`data:image/png;base64,...`），zip 的 `b64decode` 直接解码失败 → 剥离前缀后解码，E2E 验证解出真实 PNG 内容 |
| **入口 sys.path** | E2E 脚本 `import api` 失败（sys.path[0]=scripts/）→ 注入仓库根 |

### 验证记录

| 项 | 命令 | 结果 |
|---|---|---|
| 后端单测 | `pytest -m "not integration and not chaos and not slow"` | **全量 exit 0**（含 `test_gallery_crud.py` 8 用例） |
| 前端单测 | `vitest run` | **263 passed / 24 files（+GalleryAlbum 6 用例、P2-1 适配 4 用例）** |
| 前端构建 | `tsc --noEmit` + `npm run build` | 0 error，dist 重建 |
| E2E | `scripts/e2e_v12.py` | **24/24 PASS**（含画廊段 13a-13f 6 断言：fixture 落库 → 搜索可见 → 详情 → ZIP 200+PK+PNG 内容 → 软删 → 列表不含） |
| 契约/版本 | E2E openapi + mcp serverInfo | 全链 **16.0.0** |
| 桌面 | 版本配置 16.0.0 | NSIS 真机自升级流**待验证**（无 Rust/真机环境，见 verification-log） |

付费红线：全程 `IF_MOCK_UPSTREAM=1`，零真实付费上游调用。

### 升级说明

- **API 16.0.0**：`/v1/gallery` 新增响应字段 `total/page/page_size`（`count` 保留向后兼容）；新增 search/detail/zip/delete 端点。旧 `fetchGallery(limit)` 客户端行为不变。
- **MCP**：`IF_MCP_STREAMABLE=1`（缺省）新增 SSE/能力分支；旧单端点 JSON-RPC 请求-响应路径完全保留（Content-Type 非 event-stream 时行为不变）。
- **聊天**：`IF_CHAT_TOOL_LOOP=0`（缺省）零行为变化；开启后工具 call 会被网关执行并回填。