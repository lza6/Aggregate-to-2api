# 六维独立审查报告 — 《参考的结果计划指南.md》

- 生成日期：2026-09-16
- 审查者：独立 Critic（只读，未修改任何文件）
- 审查对象：`C:\Users\Administrator.DESKTOP-EGNE9ND\Desktop\imagefree-2ai\参考的结果计划指南.md`
- 验证依据：主项目代码实际读取（api/、frontend/）+ `docs/verification-log.md` + `.ref_scan/` 23 份 out + 23 份 list 报告

---

## 逐维评分

| 维度 | 评分 | 一句话依据 |
|---|:---:|---|
| 1. 需求完整性 | **4/5** | 用户五项诉求全覆盖（技能沉淀 P0-1/P0-4、黑匣子教学化 P0-3、小白易用 P0-3、视频/电商/PPT 扩展 P1-8/P1-9、参考全量扫描 §1.2），但「视频」诉求定位到"新增"基于错误现状诊断；电商/PPT 仅技能级方案、未给完整产品闭环 |
| 2. 逻辑正确性 | **4/5** | P0=体验/安全、P1=场景、P2=效率分级合理；"先安全扫描再开放技能"批次链路正确；但 P0-1 自述"前置依赖无"与批次表 B2→B1 冲突，B4→B3 依赖理由牵强 |
| 3. 边界与失败场景 | **4/5** | 付费红线/Mock 铁律贯穿（P1-8 注明 IF_MOCK_UPSTREAM=1）、兼容性/P0-1 不破坏 5 预设技能、P1-6 双传输降级、P1-5 SQLite 加列可回滚、回滚开关均有；缺：沉淀内容注入与扫描的强制顺序、admin 审批无人值守、既有 falai 视频的付费红线状态 |
| 4. 代码质量与仓库规范一致性 | **3/5** | 大部分路径/行数与实测吻合，但含 2 处事实性错误（视频现状、agent 技术债表述）+ 1 个无证据数字 |
| 5. 测试与覆盖 | **4/5** | 全部建议可执行且真实（Mock LLM/上游、E2E、cargo check、真机待验证），无一过度宣称；缺 skill 沉淀"重放验证"的通过判据（GATE 阈值由谁定） |
| 6. 实际运行结果 | **4/5** | 核心测试基线（2141/49/5/14-14/257/20）在 verification-log v15.1.1 有条目；23 份 out + 23 份 list + 4 份 .ref-scout 存在；但"1167 目录"与"181 版本门禁"无法复算 |

**总体 3.8/5 → CONDITIONAL PASS**

---

## 发现清单

### BLOCKER（0）— 无

报告为 ANALYSIS_ONLY 纯文档，未破坏任何源码/数据，无阻断项。

### MAJOR（2）

**M1. 「主项目只有 txt2img/img2img、无视频」（§2.3/§4.1/§1.2、P1-8、B7）为事实错误**
- 证据：
  - `api/providers/base.py:34-37` 已定义 `CAP_TXT2IMG/CAP_IMG2IMG/CAP_TXT2VID/CAP_IMG2VID` 能力常量，头部注释"统一能力面：txt2img / img2img / txt2vid（支持哪些由 capability 声明）"。
  - `api/providers/falai.py`（580 行）docstring 明确"fal.ai 免费 minimax-H3-max **视频生成** Provider（纯算版）"，`:79-84` 声明 `(CAP_TXT2VID,)`/`(CAP_IMG2VID,)` 双视频能力，`:330` 区分 img2vid，`:369-391` 含 `_fetch_result`/`_download` 视频下载链路（completed + asset_url=video_url）。
  - `api/providers/registry.py:446` 注册 FalaiProvider；`:375` 装配时已将 `"txt2vid","img2vid"` 纳入 capability 列表。
  - `tests/test_falai.py` 有 `test_generate_txt2vid_success`、`test_generate_img2vid_with_upload`、poll-timeout/rate_limited/no_request_id 等视频路径测试。
  - git: `213e517 feat(v8.1.0): …P1-A agent 化能力跃迁` 起落地。
- 连带影响：P1-8"在 `providers/base.py` 加 `image_to_video` 动作族"与 B7"视频扩展（Mock）"被定位成"从零新增"，实际应为"既有 falai 视频能力的抽象统一 + 供应商扩展 + 编排/SDAG 集成"。
- 根因链：扫描子代理 `out_g08_video.md` 头部同样误称"主项目当前只做 txt2img/img2img，未做 txt2vid"——汇总层未对主项目代码复核即继承。**风险**：23 份 out 报告可能存在更多同类失真引用。
- 建议：Phase B 开工前先跑一次"out 报告引用主项目现状的事实复核"（只读 grep 主项目），并修正 §1.2/§2.3/§4.1/P1-8/B7 表述；视频功能定位需重新与用户对齐（既有免费视频 vs 扩展编排管线）。

**M2. 「工程规范高：181 处版本门禁、60+ 契约测试」（§2.2）无法复现**
- 证据：全仓排除 node_modules/.venv/dist/.git 后匹配 `15.1.1` 仅 44 处（含 .md/.vue/.rs/.yaml 文档）；`verification-log.md` v15.1.1 记录"契约 20"，与"60+ 契约"不符。
- 结论：**UNVERIFIED**（找不到"181"的计算路径，属措施级说法，不影响路线图方向，但违反报告自身 Evidence Ledger 纪律）。
- 建议：删除或改为可复现口径（如"版本一致性门禁 8 处 + 契约 20"）。

### MINOR（4）

**m1. 「agent 模块未拆分（api/agent/*.py 2802 行一行到底）」（§2.5-P0 技术债）与事实不符**
- 证据：`api/agent/` 已拆 **11 个文件**（budget_guard 179 / critic 178 / dag 546 / guard 137 / human_inbox 290 / intent 326 / memory 521 / metrics 113 / planner 295 / routes 180 / __init__ 37），总量 2802 正确，但最大文件 dag.py 546 行、memory.py 521 行，全部 < 800 行门禁，无"一行到底"。
- 建议：技术债表述改为"agent 域整体 2802 行分散 11 文件，多文件逼近 600 行仍需关注"，P0 分级依据需修正。

**m2. 「记忆检索单一：向量单检索」（§4.4）不准确**
- 证据：`api/agent/memory.py:186-232` `query()` 为纯 SQL `SELECT * FROM {table} WHERE user_key=? AND scene=? … ORDER BY importance DESC, last_accessed_at DESC LIMIT ?`，全文件无 embed/vector 引用（rg 无命中）。实际是"SQL 排序检索、无任何语义/向量检索"——差距比报告所述更大。
- 建议：P1-5 现状描述改为"纯 SQL 排序，无向量/全文检索"，差距论证反而更强。

**m3. P0-1 依赖描述自相矛盾**
- P0-1 表写"前置依赖：无"，但批次表 `B2(P0-1) 依赖 B1(P0-2 技能扫描)`。安全上 B1 前置正确，但 P0-1 自述需改。
- 建议：P0-1 前置依赖改为"B1 技能安全扫描"。

**m4. 批次依赖 B3→B4 牵强、B2→B3 仅属营销逻辑**
- B4（P1-5 记忆升级）依赖 B3（教学化）理由不足——记忆三流检索独立可交付；B3 依赖 B2"技能沉淀能展示才教"非技术依赖。
- 建议：P1-5 改为独立或依赖 B2 即可，教学化可视用户优先级提前。

### NOTE（5）

- **n1（UNVERIFIED）**："1167 独立目录"与 23 份 list_gXX 合计 1144 行无法复算（差 23）。因 g05 补扫 + `.ref-scout` 复用物可能未计入 list，不排除成立；需在账本补充复算路径。
- **n2**：`out_g08_video.md` 已证实含主项目现状失真 → Phase B 对 23 份 out 报告中被当作"主项目现状"的断言需抽样复核，否则 M1 类错误会继续扩散。
- **n3**："24 个 agent 开关"（§2.4）实测相关 `IF_` 开关约 22 个，方向属实、数字精度存疑（NOTE 级）。
- **n4**：技能沉淀"历史 DAG 重放验证（复用意图评测）"缺通过判据——SkillClaw 用 GATE 分数，报告未说明 GATE 阈值由谁定、如何定。
- **n5**：已核验一致的项（供 Phase B 放心引用）：
  - `api/config/__init__.py` **821 行** ✓（实测 wc -l = 821）
  - `IF_*` 开关 **188 个** ✓（rg -c validation_alias="IF_）
  - `api/skills/` 5 技能（critic/ecommerce/image_quality/ppt/prompt_refine）仅 SKILL.md、无 schema/validate/expected_results ✓
  - `api/mcp/server.py` `PROTOCOL_VERSION = "2025-06-18"` 单 JSON-RPC 端点 + 五工具（skills_list/skills_get/dag_plan/dag_status/generate_image）✓
  - `frontend/src/pages/Agent.tsx` 263 行 + `DagGraph.tsx` "推理轨迹（black-box）面板"（代码注释自认 black-box）✓ → P0-3 教学化方向成立
  - `frontend/src/pages/Dashboard.tsx` **714 行** ✓；前端 **15 页** ✓；`frontend/src/` 无 i18n ✓
  - 测试基线：单测 **2141/0F**（verification-log:22 行 2026-09-15）、集成 **49**+混沌 **5**（:26）、E2E **14/14**（:8/:26/:55）、vitest **257/0**（:8）、契约 **20**（:8）✓
  - `.ref_scan/` 23 份 out_gXX + 23 份 list_gXX 均存在 ✓、`.ref-scout-*.md` ×4 存在 ✓

---

## 结论

**CONDITIONAL PASS** — 报告大方向正确、证据链总体扎实、付费红线与 Mock 铁律贯穿、路线图 P0/P1/P2 分级及"安全前置 → 技能沉淀 → 教学化"批次链路合理，**满足进入 Phase B 的标准**（尤其 B1 技能安全扫描 → B2 技能沉淀 → B3 教学化不受任何发现影响）。

进入 Phase B 前的**条件**（均为文档级修订，不阻塞 B1 类代码实施）：
1. 修正 **M1**（视频现状事实错误，重定位 P1-8/B7 与用户视频诉求表述），并对 23 份 out 报告的主项目引用做只读事实复核；
2. 取消或复现 **M2**"181 版本门禁/60+ 契约"数字；
3. 修正 **m1**（agent 技术债）、**m2**（记忆检索现状）、**m3**（P0-1 依赖）三处表述；
4. Evidence Ledger 补充 **n1**"1167 目录数"复算路径。