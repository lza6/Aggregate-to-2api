# g07 记忆/RAG 组扫描报告（17 目录）

> 主项目锚点：`api/agent/memory.py`（L0-L3 分层记忆 + supersede(superseded_by) + apply_decay + 巩固管道）+ `api/agent/vector/`（embed.py/store.py）。
> 关注方向：①agent 深度优化（记忆深化/黑匣子教学化/小白易用）；②扩展场景（图片/视频/电商/PPT/多模态）；③工程规范/交互/安全/性能。

---

## DeusData__codebase-memory-mcp
- 定位：纯 C 编写的「代码智能引擎」MCP——tree-sitter AST 全量索引 + Hybrid LSP 语义类型解析，产出持久化代码知识图谱，15 个 MCP 工具，原生二进制即装即用（Linux 内核 28M LOC / 75K 文件 3 分钟索引完）。
- 技术栈：纯 C（无语言运行时）/ tree-sitter(162 语言) / 内存 SQLite / LZ4 压缩 / Aho-Corasick 匹配 / MCP 协议 / 内嵌 3D 图谱可视化(localhost:9749)。
- 亮点：
  1. **RAM-first 索引管线**：LZ4 压缩 + 内存 SQLite + 融合 Aho-Corasick 模式匹配，索引完释放内存；5 条结构查询约 3.4K token vs 文件级搜索 412K（120x 省 token）——对"代码记忆"类检索做了极致工程化（`internal/cbm/`）。
  2. **结构化图谱而非文本记忆**：函数/类/调用链/HTTP 路由/跨服务链接 + Infrastructure-as-Code（Dockerfile/K8s manifest 也进图），15 MCP 工具覆盖 search/trace/architecture/impact/Cypher/dead-code。
  3. **供应链安全范式**：每个 release 三个行为一致候选二进制先送 VirusTotal 再打包 + SLSA3 + OpenSSF Scorecard（SECURITY.md）。
- 对主项目价值：扩展方向参考（代码图谱方向）。主项目已有 codegraph/graft，此项目是同类更工程化的外部参照，非核心记忆/RAG 借鉴。
- 借鉴点：若深化"代码记忆/代码问答"，可参考其 MCP 工具面（impact analysis/dead code 检测）与索引管线思想；其 RAM-first + 压缩索引思路可用于 graft 图谱加速。
- 评分：2（与主项目 memory 关联弱，但为"代码记忆"扩展提供蓝本；与 codebase-memory-mcp 为同一项目）

---

## ai-memory
- 定位：Rust 编写的**跨 agent / 跨机器 / 跨团队**长期记忆服务器——用 git 托管的 Markdown wiki 作为唯一事实源，数据库只是可重建的派生索引；Claude Code/Codex/Cursor 等 20+ harness 共享同一记忆，支持 typed handoff（交接协议）。
- 技术栈：Rust（多 crate）/ SQLite(FTS5) / 可选向量（零 LLM 默认路径）/ git 原子提交 / MCP / lifecycle hooks / 多用户 auth + 审计日志。
- 亮点：
  1. **git-backed Markdown wiki 作为真相源**（`crates/ai-memory-wiki/`：git.rs/atomic.rs/ledger.rs）——可 grep、可 Obsidian 打开、可手改、可 rsync；数据库（`ai-memory-store/`）永远可由文件重建，不绑架于二进制 blob；wiki 层有 ledger（账本）保证每条 mutation 可审计。
  2. **遗忘/保留数学是纯函数**（`crates/ai-memory-store/src/decay.rs`）：`salience·exp(−λΔt) + σ·log(1+access_count)·exp(−μ·days_since_access)`——**不必物化整个访问历史表**，只靠 `access_count + last_accessed_at` 两列（V03 迁移），热读路径零 join；参数化 lambda/sigma/mu/cold_threshold/hard_delete_after_days（墓碑+版本祖先保留 180 天后硬删）；还有 `retention_score_with_breadth` 统计"多少不同 operator 强化过"，防单人重复阅读刷分。
  3. **混合检索 RRF 融合**（`reader.rs`）：FTS5 全文 + 实体 + 链接 + 可选向量多流融合 `1/(k+rank), k=60`；`fts_query.rs` 对 FTS5 查询做智能 token 处理（stopword/裸列/引号陷阱规避）；page authority tag 重排。
- 对主项目价值：**直接借鉴**。主项目 `memory.py` 的 apply_decay 目前是简单三档阈值，ai-memory 的 retention 公式是可直接落地的升级版；其"wiki 为源 + 数据库为派生索引"思想也适配主项目记忆可解释性（黑匣子教学化）。
- 借鉴点：
  - 把 `_DECAY_THRESHOLDS` 简单阈值替换为 retention_score 纯函数（仅需给 SQLite 表加 access_count/last_accessed_at 两列，与主项目 MemoryRecord 兼容）。
  - 记忆变更 ledger/审计（history 表已有雏形，可对齐 wiki.ledger 的"每 mutation 可审计"）。
  - FTS5 + 向量 RRF 融合检索（主项目 query 目前以向量为主，可补 FTS5 关键词流）。
- 评分：5

---

## awesome-ai-memory
- 定位：AI 记忆领域**精选清单**（curated list）——按开源/闭源、图/向量/两者、Memory/Framework/Optimizer/Storage 四维分类的记忆工具全景图（mem0/cognee/MemGPT/Zep/GraphRAG/VectorStore 等）。
- 技术栈：纯 README/表格，无代码。
- 亮点：
  1. 给出记忆工具全景分类维度（Graph/Vector/Both × Memory/Framework/Optimizer/Storage）——用于选型时的坐标系。
  2. 主推 cognee（semantic memory，graph+vector）。
- 对主项目价值：扩展方向参考（选型索引，非实现）。
- 借鉴点：主项目做记忆/检索技术选型时作为清单核对；无代码可迁移。
- 评分：1（信息索引，非可执行代码）

---

## claude-supermemory
- 定位：Claude Code 插件（Node hooks）——把 Supermemory 平台接进 Claude Code，实现跨会话持久记忆；团队记忆(team)与个人记忆分离。
- 技术栈：Node/TypeScript 插件（hooks + commands + agents）/ Supermemory 云 API / statusline。
- 亮点：
  1. **Reasoned recall（按需召回）**：每轮由模型自主判断"当前消息是否需要召回记忆"，需要才搜（每次/偶尔/从不三档）——既省 token 又不打扰（`plugin/hooks/`）。
  2. **容器命名 hash 化**：`repo_<project>__<remote-hash>` 由规范化 git remote 派生——同名仓库不碰撞、克隆共享记忆；`sm_scope` 元数据在同一容器内分隔个人/项目记忆。
  3. 自动捕获（session-end）+ 显式保存双通道，回退兼容旧容器名。
- 对主项目价值：局部借鉴（agent 记忆"小白易用/省 token"方向）。Reasoned recall 思路可移植到主项目 memory.query 触发策略。
- 借鉴点：在主项目 agent 记忆检索前加"是否需要检索"的意图门（结合现有意图识别三路：规则+embedding+LLM），避免每轮无条件灌记忆；用 (user_key, scope) 元数据做个人/项目/会话三域隔离（主项目现有 user_key+scene 已是雏形，可加 scope 域）。
- 评分：3

---

## codebase-memory-mcp
- 定位：与 `DeusData__codebase-memory-mcp` **同一项目**（DeusData 为原作者命名空间，差异仅在 .git 内部元数据）。纯 C 代码智能引擎 MCP，15 工具 + 3D 图谱可视化。
- 技术栈：同 DeusData__codebase-memory-mcp（tree-sitter / Hybrid LSP / 内存 SQLite / LZ4 / Aho-Corasick / MCP / C）。
- 亮点：同 DeusData__codebase-memory-mcp；另有 arXiv:2603.27277 论文背书（31 仓库实测：83% 回答质量、10x 少 token、2.1x 少工具调用 vs 逐文件探索）。
- 对主项目价值：扩展方向参考（与 DeusData 条目合并看待，不重复计分）。
- 借鉴点：同 DeusData 条目。
- 评分：2

---

## hermes-zvec-memory
- 定位：Hermes Agent 的**本地优先记忆 provider**——基于 zvec-grep(`zg`，Hybrid BM25+向量 + RRF 融合) 对 Markdown vault 做检索；无云、无账号、数据不出机器。
- 技术栈：Python(plugin) + Node(zvec-grep) / Markdown vault(facts/ + sessions/) / SQLite(FTS/向量) / 后台 debounce 重索引(默认 600s) / 可选共享 daemon。
- 亮点：
  1. **每轮 prefetch 限 5 条压缩注入**：`zg query --preview short --limit 5`，平凡 prompt 跳过（`plugin.yaml` 描述）——检索成本恒定、上下文最小。
  2. **写路径与索引解耦**：`sync_turn` 后台追加每日 session 日志，重索引 debounce（600s）绝不每轮触发；facts/sessions 分离（耐久事实 vs 逐日流水）。
  3. **session-end 提取偏好/决策**（compaction handoff 排除）——会话收尾时从日志蒸馏出可复用记忆。
- 对主项目价值：局部借鉴（检索成本控制 + 写读解耦 + 会话收尾蒸馏）。与主项目"黑匣子教学化"方向契合（vault 是明文的）。
- 借鉴点：主项目 memory query 增加"恒定量检索预算 + 平凡输入跳过"；consolidate 与 query 的调度解耦（已有后台 worker，可对齐 debounce）；会话收尾时用 LLM 蒸馏"偏好/决策"进 L2/L3（主项目 _consolidate_with_llm 已有雏形）。
- 评分：4

---

## mem0
- 定位：**AI 记忆层**行业标杆（mem-zero）——为 assistant/agent 提供持久个性化记忆；Multi-Level（User/Session/Agent）记忆 + 向量存储 + 实体链接 + 多信号检索。
- 技术栈：Python(OSS SDK) + 自托管 server(docker) + 云平台 / 30+ 向量后端（pgvector/qdrant/chroma/redis/valkey/milvus…）/ 多种 embedding 与 LLM / SQLite(本地元数据与历史) / spaCy 实体抽取。
- 亮点（尤其 2026.04 新版记忆算法，README 已公开）：
  1. **单次遍历 ADD-only 提取**：一次 LLM 调用完成事实抽取，不做 UPDATE/DELETE，记忆只累积不覆盖——从根上消除"覆盖丢信息"，LoCoMo 71.4→92.5、LongMemEval 67.8→94.4、BEAM(1M) 64.1，top_200 预算下单遍检索（`memory/main.py: _add_to_vector_store`、`_create_memory`）。
  2. **三信号融合检索**（`utils/scoring.py: score_and_rank`）：语义(向量) + BM25(关键词) + 实体 boost 三流并行打分后**自适应归一化**（分母按激活信号数取 1.0/2.0/1.5/2.5），threshold 先闸语义分再融合；BM25 用**查询长度自适应 sigmoid 归一化**（midpoint/steepness 随 term 数分级，`get_bm25_params`）；超量取回 over-fetch 4x/min60。
  3. **实体链接**（`utils/entity_extraction.py`）：spaCy 抽取 PROPER/QUOTED/TOPIC/IDENTIFIER 四类实体（优先级 + 重叠消解 + 归一化去重），实体被嵌入并跨记忆链接，检索时实体 boost（`_compute_entity_boosts`）。
  4. **时间感知**：检索按"当前/过去/计划"时间维度排序正确日期实例；expiration_date 过期记忆默认隐藏（`_payload_is_expired`）；`history` 表 + `SQLiteManager`（check_same_thread + 线程锁 + 迁移）做变更审计。
  5. **元数据过滤算子完备**（search filters）：eq/ne/in/nin/gt/gte/lt/lte/contains/icontains/wildcard/AND/OR/NOT——检索能力下放到存储层。
- 对主项目价值：**直接借鉴**（记忆/检索设计的核心参照系，与主项目 L0-L3 + supersede 同赛道）。
- 借鉴点：
  - 把主项目 query() 的向量单检索升级为"语义+BM25+实体"三信号融合 + 自适应归一化（SQLite 已有，可给记忆表加 FTS5 + text_lemmatized 列；实体 boost 可复用主项目现有 intent 规则路抽取）。
  - ADD-only 语义：主项目 supersede 目前是"先插新行再回填旧行"（`_consolidate_mock`），可对齐 mem0"只增不覆盖 + 版本链"，把 supersede 从"标记"升为"版本历史"。
  - 巩固触发：`_should_use_agent_memory_extraction` 判断何时用 agent 记忆抽取，值得移植到主项目 consolidate 调度。
  - 检索结果 explain（score_details 分解三信号）——直接服务主项目"黑匣子教学化"。
- 评分：5

---

## memorizz
- 定位：Python 记忆优先 agent 框架（"intelligence plane"）——持久记忆 + 模型 + 提示 + 推理整合，让 agent 跨会话复用经验。
- 技术栈：Python / 多存储 provider（filesystem/Mongo/Oracle 同契约）/ embeddings+混合检索 / MCP server / CLI / 本地 web UI / MemAgent/MemAgentBuilder / MetaHarness。
- 亮点：
  1. **五类记忆分类法**：Episodic(对话史) / Semantic(知识/偏好/人格) / Procedural(工具/工作流/技能) / Short-term(工作上下文+语义缓存) / Shared(agent 协调与交接共享空间)——比主项目 L0-L3 多出 procedural 与 shared 两个正交维度。
  2. **上下文效率工程**：检索去重 + 历史总结压缩 + **召回决策可检视**（inspect recall decisions）+ 保留/遗忘控制（docs/guides/context-efficiency.md）。
  3. **MetaHarness**：任务穿 Codex/Claude Code/OpenHands 执行，记忆 scope 与学习证据跨 harness 携带，统一权限/审批/工作区隔离/预算/取消/宿主侧验证——与主项目"跨会话记忆 + 审批持久化"思路高度同构。
- 对主项目价值：局部借鉴（记忆分类维度 + 上下文效率 + 召回可解释）。
- 借鉴点：为主项目记忆补 procedural（工具/技能记忆）与 shared（agent 协作共享）层；recall 决策记录 + 检视 UI（主项目管理面板可加"本次检索为何返回这些"视图）。
- 评分：4

---

## supermemory
- 定位：**记忆与上下文引擎**（研究实验室产品，宣称 LongMemEval/LoCoMo/ConvoMem 三榜第一）——自动从对话学事实、建用户画像、处理知识更新与矛盾、过期自动遗忘，按时给出正确上下文；Hybrid RAG+Memory 单查询融合。
- 技术栈：TypeScript monorepo（apps/web + apps/mcp + packages/）+ SDK(npm/pypi) + 云平台 / 多模态抽取（PDF OCR、视频转录、AST-aware 代码切块）/ connectors（Gmail/Drive/Notion…）。
- 亮点：
  1. **用户画像 ~50ms、95% Recall@15 且 99.4% 上下文缩减**（README 研究数据）——"稳定事实 + 近期活动"双通道画像，单次调用即得。
  2. **时间/矛盾处理**：知识更新与矛盾处理、过期信息自动遗忘、temporal changes——记忆不是静态快照而是带时序演化的状态机。
  3. **单记忆结构 + 本体（ontology）统一 RAG 与 memory**：知识库文档与个性化上下文一次查询融合（README.zh-CN）。
- 对主项目价值：扩展方向参考（大部分能力在闭源平台侧；OSS 仓库以插件/MCP/web 为主，核心引擎不完整开放）。
- 借鉴点：用户画像"稳定事实+近期活动"双通道（主项目 L3 persona 可加"近期活跃"热通道）；多模态抽取器（PDF OCR/视频转录/AST 切块）对齐主项目扩展场景方向。
- 评分：3（方向参考为主，核心不可直接搬运）

---

## LightRAG-main
- 定位：HKUDS 的**轻量图 RAG**——文本切块 + LLM 抽取实体/关系构建知识图谱，支持 6 种检索模式；单文件存储后端极简（也可全托管化）。
- 技术栈：Python / 图存储多后端（neo4j/memgraph/networkx/mongo/postgres/opensearch/redis/qdrant…）/ 向量存储多后端 / 可选 reranker / OpenSearch 一体化 / RAGAS 评估 + Langfuse 追踪。
- 亮点：
  1. **六检索模式统一 QueryParam**（`base.py`）：local(实体邻域) / global(全局社区) / hybrid / naive(纯向量) / mix(KG+向量) / bypass——一套参数覆盖图检索到朴素检索，`operate.py: kg_query` + `_build_query_context` 统一编排。
  2. **双层关键词**：LLM 抽取 high-level/low-level 关键词分别喂 global/local 检索（`operate.py: get_keywords_from_query`），配合 `_apply_token_truncation` 统一 token 预算——上下文可控。
  3. **增量维护**：文档删除触发 KG 自动再生（`_merge_nodes_then_upsert`/`_merge_edges_then_upsert` 幂等合并），断点续跑有缓存层（`_get_cached_extraction_results`）；OpenSearch 一体化存储（2026.03）。
- 对主项目价值：扩展方向参考（主项目暂无图记忆；若做"关联知识问答"可引入图 RAG）。
- 借鉴点：主项目 DAG/RAG 扩展时参考"双层关键词→分层检索→统一 token 预算"的编排；实体/关系/文本块三层存储 + 增量合并的幂等思想可用于主项目 L2 场景聚合。
- 评分：4

---

## PixelRAG
- 定位：伯克利 SkyLab/BAIR 的**视觉 RAG**——把网页/PDF/图片渲染成截图再按"外观"检索（视觉结构如图表/表格/布局不丢失），支持以图查图；预构建 828 万维基百科索引。
- 技术栈：Python(pip)/TypeScript(前端)/chromium 渲染/embed/向量索引/serve 管线（render→tile→index→search）。
- 亮点：
  1. **视觉优先检索范式**：HTML 解析会丢的表格/图表/版式信息，截图像素层完整保留，reader model 直接看图回答（arxiv:2606.28344）。
  2. 通用 render→index→search 管线，演示/部署开箱即用（pixelrag.ai 在线 demo）。
- 对主项目价值：扩展方向参考（主项目扩展场景含"图片/多模态"，此为其检索侧蓝本）。
- 借鉴点：若主项目做"电商主图/PPT/网页截图"检索问答，可移植 render→tile→向量索引管线（chromium 截图 + 图 embedding）；与主项目已有图片上游结合成本低。
- 评分：3

---

## SuperAGI-main
- 定位：老牌（2023）**开源自主 agent 框架**——构建/管理/运行自治 agent，DAG 工作流 + 工具市场 + GUI；官方已基本停止开发（维护模式）。
- 技术栈：Python(FastAPI) / Celery+Redis / PostgreSQL(alembic) / Next.js GUI / 向量存储抽象（chroma/pinecone，VectorFactory）。
- 亮点：
  1. **Agent 执行器 + 工作流步骤注入记忆**（`jobs/agent_executor.py`）：`VectorFactory.get_vector_storage(...)` 抽象向量后端，agent 执行时按工作流步骤注入 memory——清晰的"存储抽象 + 步骤级记忆注入"。
  2. 完整工具体系（resource/tool/toolkit + 审批 permission，`models/tool*.py`）+ 知识库（knowledges）。
- 对主项目价值：无价值/低（架构旧、已停维护；主项目 DAG+工具+审批已更现代）。
- 借鉴点：VectorFactory 式存储抽象（主项目 vector/store.py 已内聚，无需拆分）；其余不迁移。
- 评分：1

---

## context-engineering-intro-main
- 定位：**Context Engineering 模板**——把"给 AI 助手的上下文"当作工程学科：CLAUDE.md 规则 + examples + INITIAL.md 需求 → `/generate-prp` 生成 PRP（Product Requirements Prompt）→ `/execute-prp` 执行 + validation 自纠。
- 技术栈：Claude Code 命令/模板（slash commands + PRP 文档格式）/ use-cases 案例集。
- 亮点：
  1. **PRP 工作流**：需求文档(INITIAL.md)→结构化 PRP→执行→校验循环（validation loops 让 AI 自纠）——"上下文工程 > prompt engineering"的完整方法论 + 模板落地（`PRPs/templates/`）。
  2. 强调"多数 agent 失败是上下文失败而非模型失败"；examples 目录作为上下文资产被显式引用。
- 对主项目价值：扩展方向参考（主项目"黑匣子教学化/小白易用"——把记忆与上下文沉淀成可读文档/模板）。
- 借鉴点：主项目 agent 记忆的"教学化"可借鉴 PRP 格式（把 L1-L3 记忆导出为结构化 PRP/简报喂给子任务）；docs 规范已类似 CLAUDE.md 化。
- 评分：2

---

## dragonfly
- 定位：**DragonflyDB**——Redis/Memcached 兼容的极致性能内存数据存储（宣称 25x 吞吐、同负载省 80% 资源），非记忆算法项目，属基础设施（可能因"可作记忆/向量缓存后端"被分入本组）。
- 技术栈：C++ / 无共享架构 + thread-per-core 分片 / Redis+Memcached 协议兼容 / 纵向扩展。
- 亮点：
  1. 无共享多线程架构，单实例纵向扩展即达高吞吐（`docs/design`），协议零改迁移。
  2. 低尾延迟 + 高缓存命中率（作为缓存/KV 层）。
- 对主项目价值：扩展方向参考（基础设施可选件；主项目用 SQLite/aiosqlite + 内存缓存，暂无引入此类存储的需求与授权）。
- 借鉴点：仅当主项目记忆/SSE 状态需超高频 KV 时才考虑替换；现阶段不迁移。其"无共享分片"思想对主项目 worker 并发模型（semaphore/队列）有启发但非记忆范畴。
- 评分：1（与记忆/RAG 算法无直接关联，属基础设施）

---

## graphrag
- 定位：微软**图 RAG**（研究性质，2024 首发，现维护模式）——LLM 从非结构化文本抽取实体/关系构建知识图谱 + Leiden 社区分层 + 社区摘要，实现全局/局部/DRIFT 多路检索。
- 技术栈：Python / graphrag-llm / 图+向量存储 / asyncio / 工作流引擎（index workflows）/ prompt tuning 工具。
- 亮点：
  1. **社区分层 + 动态社区选择**（`query/context_builder/dynamic_community_selection.py`）：LLM 对社区报告逐条评分（rate_relevancy），按阈值+max_level 选相关社区，keep_parent 保留父级——避免全量灌社区摘要。
  2. **DRIFT 检索**（`query/structured_search/drift_search/`：primer/state/action）：循环、动态、树状查询扩展——一次检索不够就沿证据链继续探索，是"agentic 检索"的成熟实现。
  3. Local/Global/DRIFT 三种检索器 + `rate_relevancy` 相关性评分 + 对话历史上下文构建器（`context_builder/`）。
- 对主项目价值：局部借鉴（DRIFT 循环检索 + 动态社区选择思想可移植到主项目 DAG/RAG，尤其"检索不够→继续探索"与主项目 DAG 断点续跑同构）。
- 借鉴点：主项目 RAG 检索可加"评分阈值→决定是否第二轮扩展"的循环门；社区/主题分组可类比主项目 L2 场景聚合（用 LLM 评分而非固定规则选场景）。
- 评分：4

---

## infiniflow__ragflow
- 定位：**深度文档理解 RAG 平台**（DeepDoc 文档解析 + RAG 全栈 + GraphRAG-light + Agentic RAG）——面向企业知识库，多类型文档（论文/表格/PPT/简历/法律/邮件…）开箱即用。
- 技术栈：Python / 前后端全栈 / DeepDoc 深度文档解析 / redis / 多模型接入 / LangGraph(agentic RAG 图) / GraphRAG-light。
- 亮点：
  1. **Agentic RAG 图**（`rag/advanced_rag/agentic_rag_graph.py`，LangGraph）：fanout 查询扩展 + evidence 评分（`_is_evidence`/`_score`）+ SCA gaps 重写 + think-stream 分割——检索-验证-重写的闭环图。
  2. **断点续跑检查点**（`rag/graphrag/checkpoints.py`）：`stable_checkpoint_key` 用内容哈希生成幂等 checkpoint 键，社区/实体解析处理进度持久化到 Redis（TTL 7 天，page size 1000）——大索引可断点续跑。
  3. **场景化文档 app**（`rag/app/`：book/laws/paper/email/picture/presentation/resume/table…）——把解析/切块/检索按文档类型工程化。
- 对主项目价值：局部借鉴（主项目扩展场景"PPT/电商/多模态" + DAG 断点续跑的工程范本）。
- 借鉴点：主项目 DAG 续跑对齐"内容哈希幂等 checkpoint"（把断点从"步骤 id"升级为"内容哈希"，天然幂等防重复）；agentic RAG 的"扩展→评分→重写"循环可并入主项目 DAG；场景化解析目录组织对齐主项目扩展场景规划。
- 评分：4

---

## mirage-cortex
- 定位：RealmForge——**生成式 agent 群模拟世界引擎**（living novel）：每个角色有真实记忆/学习/关系，结构化世界模型跨会话持久，涌现叙事/经济/社会。
- 技术栈：原型级（README + 单文件 index.html 演示 + preview.svg）/ 概念文档完整（index/world/llm 分层）。
- 亮点：
  1. **分层持久化**：World Graph(邻接表实体关系) + Chronicle(事件时序库：每个动作带 ID/来源/location/epoch) + Memory Store(向量库：事实 + 情感摘要)——事件日志与事实记忆分离，RAG 检索"像真实回忆而非文本注入"。
  2. **关系图随时间衰减**：不强化就淡化，模拟人类记忆褪色——与主项目 apply_decay 呼应（但用图结构实现）。
  3. **Persona Script + State Vector**（人格脚本 + 状态向量：心情/健康/库存/关系）+ Cortex Router 跨模型负载均衡 + Prompt Compression（小模型摘要保持叙事一致）。
- 对主项目价值：扩展方向参考（agent 记忆深化——情感/关系/世界模型维度，主项目当前为纯文本事实记忆）。
- 借鉴点：把主项目 L1/L2 记忆与"关系/情感/事件流"分离（L2 场景聚合可扩展为带时间的 Chronicle）；关系衰减用图实现可留作 L2 强化方向。
- 评分：3

---

## 本组汇总：Top3 最值得主项目借鉴项

1. **mem0 多信号融合检索 + ADD-only 记忆算法**（直接借鉴，评分 5）
   - 迁移目标：主项目 `MemoryStore.query()`。把当前向量单检索升级为「语义 + FTS5/BM25 + 实体」三流并行 + 自适应归一化打分（`score_and_rank` 分母随激活信号数取 1.0/2.0/1.5/2.5，阈值先闸语义分）；BM25 用查询长度自适应 sigmoid（`get_bm25_params` 的 midpoint/steepness 分级）；实体 boost 可复用主项目已有意图规则路抽取实体。同时把 supersede 从"标记被取代"升级为"只增不覆盖的版本链"，并开启检索 explain（score_details 分解三信号），直接支撑主项目"黑匣子教学化"。

2. **ai-memory 保留/遗忘数学 + wiki 派生索引 + RRF 融合**（直接借鉴，评分 5）
   - 迁移目标：主项目 `memory.py` 的 `apply_decay`（现为 L0 7 天/L1 30 天/L2 90 天的简单阈值）。替换为纯函数 `salience·exp(−λΔt) + σ·log(1+access_count)·exp(−μ·days_since_access)`，只需给表加 `access_count + last_accessed_at` 两列（免物化访问历史表，热读路径零 join），配 cold_threshold 淘汰 + hard_delete_after_days 墓碑期；`retention_score_with_breadth` 防单人刷分。检索侧补 FTS5 与向量 RRF 融合（`1/(k+rank), k=60`），并借鉴 fts_query 的智能 token 处理。

3. **LightRAG / GraphRAG 图检索编排 + 动态社区/DRIFT 循环检索**（局部借鉴，评分 4）
   - 迁移目标：主项目 DAG/RAG 扩展。LightRAG 的「双层关键词(high/low) → local/global/hybrid/mix 分层检索 → 统一 token 预算」编排，与 GraphRAG 的「LLM 评分动态社区选择 + DRIFT 循环检索（不够就沿证据链继续探索）」结合——作为主项目 L2 场景聚合与 RAG 检索的升级路线；其"内容哈希幂等 checkpoint"（ragflow checkpoints.py）可直接对齐主项目 DAG 断点续跑。

> 其余可圈点：hermes-zvec-memory（检索预算恒定 + 写读解耦 + 会话收尾蒸馏，评分 4）、memorizz（procedural/shared 记忆维度 + recall 决策可检视，评分 4）、ragflow（agentic RAG 扩展→评分→重写循环，评分 4）、PixelRAG（视觉 RAG 为"图片/多模态"扩展场景的检索侧蓝本，评分 3）、claude-supermemory（reasoned recall 按需召回省 token，评分 3）。
