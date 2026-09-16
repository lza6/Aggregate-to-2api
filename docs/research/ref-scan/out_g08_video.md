# g08 组扫描结果：视频/媒体生成类（42 目录）

> 扫描对象：`D:/参考项目/` 下 42 个视频/媒体目录。主项目「听风AI」当前只做 txt2img/img2img，未做 txt2vid/短视频编排——本组重点回答「往 txt2vid/短视频扩展能迁移什么设计」。
> 行开始对齐：全部目录已逐一访问，无遗漏；无目录不可访问。

---

## AI-Youtube-Shorts-Generator
- 定位：长视频→9:16 短视频的「切片裁剪」器，Opus Clip 类开源替代，LLM 高光打分 + 竖屏重裁
- 技术栈：Python 3.10+ / yt-dlp / faster-whisper / ffmpeg / OpenCV / OpenAI·Gemini LLM；双模式 API(MuAPI)/本地
- 亮点：
  1. **可插拔 LLM 后端**：`get_highlights(transcript, llm_fn=...)` 把同一条 virality 提示词同时驱动云 API 与本地 LLM 客户端（`shorts_generator/highlights.py`）——与主项目 registry 思路同构
  2. **激活性打分 schema 化**：每个 clip 带 `{title,start_time,end_time,score(0-100),hook_sentence,virality_reason}`，LLM 返回强约束 JSON（`HIGHLIGHT_SYSTEM_PROMPT`），后续纯排序裁剪不依赖 LLM 再解读
  3. **长视频分块 + overlap 去重**：>30min 自动 20min 分块带 60s 重叠，score 排序去重（`CHUNK_SIZE_SECONDS` 等常量）——短视频素材切分的工程化模板
- 对主项目价值：**直接借鉴**
- 借鉴点：txt2vid 扩展若做「高光裁剪」产品线，可直接移植「LLM 打分 JSON schema + score 排序 + 分块去重」三段式；主项目已有 SSE 进度，把打分/裁剪步骤发事件即可
- 评分：4

## ATH-MaaS__Pixelle-Video
- 定位：Pixelle-Video 的 MaaS 化实现（与 Pixelle-Video 同源，见下）
- 技术栈：Python / FastAPI / yaml 配置
- 亮点：与 Pixelle-Video 互补呈现「MaaS 私服化」视角，`packaging/` + `docker` 完整
- 对主项目价值：局部借鉴（其主体已并入 Pixelle-Video 条目）
- 借鉴点：MaaS 化的配置与打包思路（config.example.yaml / docker-start / packaging/）
- 评分：3

## Ai-movie-clip
- 定位：智能自动视频剪辑系统——上传素材→CV/ML 分析→LLM 生成剪辑方案→FFmpeg/moviepy 执行→出片
- 技术栈：Python 3.8+ / FastAPI / FFmpeg / moviepy / Whisper / YOLO / DashScope / Coze / MCP
- 亮点：
  1. **可编排工作流管道**：`workflow_orchestrator.py` 把「识别→分类→策略→执行→输出」定义成 `[(step_name, step_func)]` 表驱动，步骤可插拔、可中间校验——主项目 DAG 编排的轻量参照
  2. **内容双分类决策**：人声剧情类 vs 场景风景类，按 4 维度（人声/字幕/场景切换频率/人脸）分流剪辑策略（`docs/ARCHITECTURE.md`）——按内容类型路由生产管线
  3. **模板 + 随机转场/特效**：`cliptemplate/{smart_clip_with_vocals,coze,random_effects,random_transition}.py`——把「转场/特效」做成可组合随机模块
- 对主项目价值：**直接借鉴**
- 借鉴点：短视频编排的「分析→方案→执行」三步引擎 + 内容分类分流策略 + 模板系统；若主项目做「上传素材→自动成片」，这套 step_func 表驱动编排几乎照搬
- 评分：4

## Anil-matcha__Awesome-GPT-Image-2.5-API-Prompts
- 定位：GPT-Image-2.5 提示词 + API 调用的集合库（Flare/Sunburst）
- 技术栈：纯 Markdown 集合
- 亮点：按「2.5 新能力」组织提示词技巧（编辑精度、多轮一致性），含 API 示例
- 对主项目价值：扩展方向参考
- 借鉴点：可作为主项目生图 prompts 资产库的补充来源；与视频生成关系弱
- 评分：2

## AtlasCloudAI__awesome-gpt-image-2.5-prompts
- 定位：GPT Image 2.5 官方示例反向工程提示词库（407+）
- 技术栈：TypeScript / 多语言 i18n / 静态站
- 亮点：提示词→实际成图配对整理，i18n 全语种；`data/` 结构化
- 对主项目价值：扩展方向参考
- 借鉴点：prompt 数据「结构化 + 可检索 + 多语言」的组织方式，可用于主项目 prompt 模板库
- 评分：2

## CosyVoice
- 定位：阿里 FunAudioLLM 的 LLM-based TTS 系列（高性能/流式/音色克隆）
- 技术栈：Python / PyTorch / 2.5B LLM / flow-matching / vLLM / Triton
- 亮点：
  1. **Bi-Streaming TTS**：文本边入边出 + 音频边出边出，低至 150ms 延迟（README Highlights）
  2. **零样本多语言音色克隆 + 发音修补 + Instruct 控制**（语种/方言/情绪/语速/音量）
  3. **统一前端库**（tokenizer/llm/flow/hifigan）分层清晰，vLLM/Triton runtime 多种部署
- 对主项目价值：**局部借鉴**（自托管 TTS 引擎候选，重；作为上游文本→语音能力接入需大改动）
- 借鉴点：短视频文案配音若要求自托管，CosyVoice 是首选引擎；主项目可先以「外部 TTS provider 抽象」接入（edge-tts 轻/ CosyVoice 重由 provider 层切换）
- 评分：3

## Eirias__omnivoice-studio
- 定位：开源 ElevenLabs 替代——实时听写/零样本音色克隆/视频配音，全本地 646 语言
- 技术栈：Python(FastAPI) + 前端 + MCP server / alembic 迁移 / pyproject
- 亮点：
  1. **MCP server 内置**：`omnivoice/mcp_server.py`——把 TTS 能力暴露成 MCP 工具，主项目 agent 层可直接对接
  2. **CLI 族齐整**：`cli/{infer,infer_batch,dub,train,demo}.py`——推理/批处理/视频配音/训练全 CLI 化，方便脚本编排
  3. **Dubbing 管线**：dub 子命令面向「给视频配音」场景，与短视频编排的语音轨步骤直接对口
- 对主项目价值：**直接借鉴**（能力形态）——主项目扩展 txt2vid 的配音链路可参考
- 借鉴点：MCP server 暴露 TTS 的形态 + 批处理 CLI + dub 管线；主项目 agent 体系可加「配音」MCP 工具
- 评分：4

## LuxTTS
- 定位：轻量 zipvoice 系 TTS，音色克隆 + 150x 实时速度
- 技术栈：Python / pytorch（模型 ~small）
- 亮点：小模型高性能（150x realtime、48kHz、CPU 可跑）——自托管成本极低
- 对主项目价值：扩展方向参考
- 借鉴点：作为轻量自托管 TTS 备选（比 CosyVoice 轻得多），同样接入 provider 抽象
- 评分：3

## Pixelle-Video
- 定位：**AI 全自动短视频引擎**——输主题 → 文案→配图→配音→BGM→合成，全自动；本组最贴合主项目扩展目标的项目
- 技术栈：Python(FastAPI) + ComfyUI/RunningHub 工作流 + 直连 API 多模型 + Edge-TTS/Index-TTS + pg(半持久化)
- 亮点：
  1. **Storyboard 数据模型 schema 化**：`models/storyboard.py`——`StoryboardConfig`（含 task_id 文件隔离、分镜数、讲解词字数上下限、image prompt 字数上下限、fps、TTS 模式、frame_template 带尺寸路径）+ `StoryboardFrame`（narration + image_prompt + 生成资源路径链 audio/media/composed/video_segment + duration）+ `Storyboard.is_completed` 完成判定——**分镜→素材→成品全链数据模型，主项目 txt2vid 可直接照抄**
  2. **结构化进度事件**：`models/progress.py` 的 `ProgressEvent`（event_type + 0-1 progress + frame_current/frame_total + step 1-4 + action audio/image/compose/video）——正好对齐主项目已有 SSE 事件流，逐帧进度可 1:1 映射
  3. **任务队列管理**：`api/tasks/manager.py`——内存任务 + asyncio task + 生命周期（create/poll/cleanup_loop），TaskStatus 枚举 + TaskProgress
  4. **多供应商视频客户端族**：`services/api_services/{video_kling,video_seedance,video_dashscope,image_*,vlm_*}.py`——每个供应商独立 client（Kling 含 JWT 鉴权、TLS 适配器、重试 session），上层统一 list_workflows/调用——与主项目 providers/registry 完全同构，直接可扩展为 txt2vid 供应商抽象
  5. **管线分层**：`pipelines/{base,standard,linear,asset_based,custom}.py`——标准/线性/素材态/自定义多管线
- 对主项目价值：**★★★★★ 最高价值，直接借鉴**
- 借鉴点：Storyboard 模型 + ProgressEvent + 任务队列三件套 + 视频供应商 client 族。主项目做 txt2vid 时：`StoryboardFrame` 拆成 DB 表 + SSE 事件按 `ProgressEvent` 结构发布；新增 txt2vid provider 直接按现有 `providers/base.py` 接口扩展 `image-to-video` 动作即可
- 评分：5

## VideoCaptioner
- 定位：LLM 驱动的视频字幕工具（ASR→优化→翻译→合成），也可做配音
- 技术栈：Python / faster-whisper·bcut·剪映 etc ASR 多引擎 / pydub / CLI + GUI(Tkinter) / claude-code skill
- 亮点：
  1. **ASR 引擎抽象 + 模板方法**：`core/asr/base.py`——BaseASR 统一音频加载/CRC32 缓存 key/限流(`RATE_LIMIT_MAX_CALLS=100/12h`)/模板方法，子类实现不同引擎——公益引擎限流与缓存设计值得照抄
  2. **分块并发转写**：`core/asr/chunked_asr.py`——480s 块、10s overlap、3 并发，`ChunkMerger` 合并——与 AI-Youtube-Shorts 的分块思路同构
  3. **配置优先级链**：命令行 > 环境变量(VIDEOCAPTIONER_*) > 配置文件 > 默认值——主项目 IF_* 配置的增强参照
  4. **全流程 process 命令**：transcribe→optimize→translate→synthesize 一条命令
- 对主项目价值：**直接借鉴**（字幕/配音链路）
- 借鉴点：ASR 抽象 + 缓存/限流 + 分块并发 + 字幕 burn-in；短视频编排的字幕生成、以及主项目 chat 端点限流实现可参照 BaseASR 的窗口限流
- 评分：4

## VideoHub
- 定位：长视频内容理解 Agent 平台（DoVideoAI）——结构化知识、可检索可追问（Java/Spring）
- 技术栈：Java 21 / Spring Boot 3.5 / MySQL / Redis / RocketMQ / LangChain4j / Vue3
- 亮点：
  1. **Agent 自动选分析模式**：手动选 vs Agent 自动判断 + 工作台展示结构化结论/时间戳证据/执行计划/阶段轨迹/质量评估
  2. 消息队列驱动任务（RocketMQ）——长任务异步的强实现
- 对主项目价值：扩展方向参考（视频理解，非生成；技术栈异构）
- 借鉴点：「结构化结论 + 时间戳证据 + 阶段轨迹」的展示结构可借鉴到主项目任务详情页；但 MQ/MySQL/Java 与主项目栈差异大，仅思想借鉴
- 评分：2

## VideoPipe
- 定位：模块化视频管道框架（C++），节点/对象拖拽式流程
- 技术栈：C++ / CMake / 节点图
- 亮点：节点式 DAG 数据流框架（nodes/objects），抽象「任意算子组合成视频流水线」
- 对主项目价值：扩展方向参考（概念层面）
- 借鉴点：「算子节点图」思想——主项目 DAG 编排已具备，可确认 video 算子（下载/裁剪/合成/字幕）是否按节点化设计
- 评分：2

## VideoRAG
- 定位：视频可对话框架（Vimo）——超长视频理解、chat with videos（桌面端）
- 技术栈：VideoRAG 算法 + 桌面应用
- 亮点：VideoRAG 检索增强思想（视频→多模态 embedding→问答）；万字长视频能力
- 对主项目价值：扩展方向参考（视频理解/问答，非生成）
- 借鉴点：若主项目做「对已生成视频提问/回顾」，VideoRAG 是参照；短视频场景价值有限
- 评分：2

## Vincentwei1021__video-shotcraft
- 定位：video-shotcraft 同源码站（见 video-shotcraft 条目，同一作者镜像仓）
- 技术栈：TypeScript / Remotion
- 亮点：同 video-shotcraft
- 对主项目价值：同 video-shotcraft（不重复计）
- 借鉴点：—
- 评分：3

## VoiceMem
- 定位：语音记忆 Agent——语音侧记忆系统（清华团队）
- 技术栈：Python / finetune / web / 评估
- 亮点：把「记忆」做进语音模型（ChatMem-400K 数据集 + VoiceMem 记忆空间），语音交互带记忆
- 对主项目价值：扩展方向参考（agent 记忆方向与语音结合，前瞻）
- 借鉴点：主项目 agent 记忆若扩展到语音输入场景可参考；短视频编排价值低
- 评分：2

## ZeroLu__awesome-gpt-image
- 定位：GPT Image 2 社区提示词精选（趋势榜项目）
- 技术栈：纯 Markdown/静态
- 亮点：多语言 README + 高保真提示词集合
- 对主项目价值：扩展方向参考
- 借鉴点：prompt 资产库补充
- 评分：2

## anhao__gpt-image-2.5-orange-book
- 定位：GPT Image 2.5 官方提示词指南的「橙皮书」重编（77 页 PDF + MD）
- 技术栈：Markdown/PDF
- 亮点：逐句解析官方 24 条提示词（这句为什么写/不写会怎样），Flare/Sunburst 对照
- 对主项目价值：扩展方向参考
- 借鉴点：可作为主项目生图 prompt「教学/资产」参考；与视频无关
- 评分：2

## autoshorts
- 定位：本地优先（Tauri2）桌面应用——长视频→竖屏短视频候选 + AI 激活性打分
- 技术栈：Tauri 2 + React + TSX + Rust + SQLite + ffmpeg + Deepgram + DeepSeek/Claude
- 亮点：
  1. **动态多 LLM 支持**：DeepSeek(默认)/Claude 切换做病毒时刻检测——与 AI-Youtube-Shorts 的 hook 打分同思路，桌面落地形态
  2. **本地 SQLite + 项目制**：transcript/candidates/渲染数据全本地，项目管理器（新建/打开/重命名/删除）
  3. **竖屏自动裁切**：ffmpeg 中心裁切 9:16 H.264 原生集成
- 对主项目价值：**直接借鉴**（主项目桌面端 Tauri2 已有；短切片能力可作桌面功能）
- 借鉴点：Tauri 桌面 + SQLite 的本地项目制管理（主项目桌面 Tauri2 sidecar 已有相似基础）；竖屏裁切 ffmpeg 命令
- 评分：4

## bradautomates__claude-video
- 定位：同名 claude-video（/watch）的另一仓库呈现（本组列了两次，内容同）
- 技术栈：Python / yt-dlp / ffmpeg / Whisper
- 亮点：同 claude-video
- 对主项目价值：同 claude-video（不重复计）
- 借鉴点：—
- 评分：3

## cf12436__gptimage_prompts
- 定位：AISaasGo 图片提示词库（541 案例，Next.js 站点 + Agent skill）
- 技术栈：Next.js / TypeScript / wrangler(CF) / Playwright 测试
- 亮点：从图出发找提示词 + 占位符([TEXT]/[PRODUCT])替换方法论 + 图片提示词技能
- 对主项目价值：扩展方向参考
- 借鉴点：prompt 库「图→词」检索 + 占位符模板化设计——可用于主项目 prompts 模块
- 评分：2

## claude-video
- 定位：让 Claude 能「看视频」——/watch skill，下载+抽帧+字幕/Whisper 转写+交给 LLM 理解
- 技术栈：Python / yt-dlp / ffmpeg / Whisper API / Claude Code skill
- 亮点：
  1. **感知层设计**：`SKILL.md` 声称「plugin is a perception layer, not an interpretation layer」——把视频转成「帧图片 + 带时间戳字幕」交给 LLM，主项目 agent 若需理解/审核生成结果可照此
  2. **自动缩放抽帧**：scene-aware 抽帧 vs 快 keyframes(efficient)，按问题自适应 fps/时间段/分辨率（claude-video-vision）
  3. **结构化 preflight**：`setup.py --json` 返回 can_proceed/first_run/missing_binaries 供 first-run 分支——Agent skill 的健壮初始化范式
- 对主项目价值：**直接借鉴**（视频理解的感知层 + 主项目生成结果质检/自反思可选）
- 借鉴点：抽帧(ffmpeg) + 字幕时间戳 → LLM 即「生成视频质检」，可挂到主项目 critic 自反思节点做 vid2text 复核
- 评分：4

## claude-video-vision
- 定位：claude-video 的增强版（多后端 Whisper/OpenAI/Gemini、自适应抽帧、MCP 化）
- 技术栈：Python / ffmpeg / Whisper / MCP / Claude Code plugin
- 亮点：自适应抽取（fps/时间范围/分辨率按问题调整）+ MCP server 形态
- 对主项目价值：直接借鉴（MCP 感知工具 + 自适应参数）
- 借鉴点：MCP server 暴露「看视频」工具的形态；自适应抽帧参数策略，供主项目视频质检 agent 使用
- 评分：4

## doesVideoContain
- 定位：浏览器端（WebGPU/WebAI）本地视频内容匹配工具——用自然语言找出视频中含某物的片段
- 技术栈：JavaScript / WebGPU / Transformers.js(WebAI)
- 亮点：纯前端本地跑模型、隐私友好、100GB 本地文件即时分析不上传——实时匹配截图
- 对主项目价值：扩展方向参考（前端能力，与主项目服务端架构差异大）
- 借鉴点：「自然语言查询→视频片段定位」可作为主项目素材库语义检索的前瞻参考；当前架构不符
- 评分：2

## duuhuang-ai__xhs-product-image-design-report
- 定位：小红书商品图竞品分析→商品图设计决策报告 Skill
- 技术栈：Agent skill / HTML 报告
- 亮点：采集→逐图拆解→给拍摄清单→证据边界管理（强表达必须有证据才能写）
- 对主项目价值：扩展方向参考（电商生图场景的决策报告模式）
- 借鉴点：「决策报告」输出形态 + 证据边界管理，可用于主项目生图场景的报告类 agent
- 评分：2

## freestylefly__awesome-gpt-image-2
- 定位：GPT Image 2 工业级提示词引擎 + 模板库（544 cases、20+ 模板、「Prompt as Code」）
- 技术栈：Vite / JS 前端 + supabase + agents/ skills
- 亮点：500+ 逆向案例 + 模板库 + design-qa 检验；「Prompt as Code」口号
- 对主项目价值：扩展方向参考
- 借鉴点：Prompt-as-Code 模板系统设计思想——主项目生图 provider 的 prompt 模板可工程化
- 评分：3

## gnipbao__openai-image-prompt-writer
- 定位：GPT Image 2.5 提示词写作 Skill（只写词不生成）
- 技术栈：Agent skill / 中文
- 亮点：默认只写 prompt 的边界 + 离线 settings validator + 参考图分工/编辑约束写法
- 对主项目价值：扩展方向参考
- 借鉴点：prompt writer 的「只写词」工具化拆分——主项目 agent 可拆独立 prompt-writing 工具
- 评分：2

## gpt-img-2__awesome-gpt-image-2-5
- 定位：GPT Image 2.5 中文提示词图鉴（1962 条可搜索、577 创作者署名、开放数据）
- 技术栈：静态站 + JSON/CSV open data + Agent skill
- 亮点：开放数据（JSON/CSV 可下载）+ 署名 + 社区认证——提示词数据的开放治理
- 对主项目价值：扩展方向参考
- 借鉴点：prompt 开放数据集（CC 认证）可作为主项目 prompts 库数据源
- 评分：2

## hand-drawn-explainer-video-nikola
- 定位：中文知识讲解「边说边画 / 程序动画」手绘视频 Skill（两个制作路线）
- 技术栈：Agent skill / HTML/SVG/GSAP/Remotion / ffmpeg / 火山 TTS
- 亮点：
  1. **明确不冒充**：源码明确「手绘风静图平移 ≠ 逐笔绘制」——交付前检查真实视频/音轨/字幕/场景边界/末帧（finalize_stroke_video.py）
  2. **双路线 + 可组合画面结构/风格**：逐笔故事动画（单场景/多幕/左右双语义岛 × Q版/小黑）与程序动画（HTML/SVG + GSAP/HyperFrames）正交组合
  3. **真实生产验证**：交付真实 MP4 + 可编辑工程包 + 末帧/手速验收
- 对主项目价值：**直接借鉴**（程序动画→HTML/SVG→渲染成视频的轻量叙事路线）
- 借鉴点：若主项目做「图文/知识讲解短视频」，可走 HTML/SVG+GSAP 动画→mp4（Remotion/ffmpeg）而非依赖昂贵的 txt2vid；"验收贯穿"纪律（真实文件/末帧检查）与主项目真实闭环原则高度一致
- 评分：4

## hermes-live-voice
- 定位：Hermes Agent 的实时语音网关 + Dashboard 插件（长任务可断开重连收结果）
- 技术栈：Node.js / TS / OpenAI Realtime / Gemini Live / 本地 HF
- 亮点：
  1. **网关 + 任务监督 + 进度流 + 客户端协议分离**：语音交互与 agent 脑分离
  2. **断线重连安全**：start task→keep talking→disconnect→reconnect→still get result——长任务可靠交付模型
- 对主项目价值：扩展方向参考（语音交互网关，主项目有桌面端/聊天端点，可作为语音化前瞻）
- 借鉴点：「进度流 + 断线补偿」模式与主项目 SSE 断线补偿同构，双向印证；实时语音为远期方向
- 评分：2

## html-video
- 定位：HTML→MP4 渲染引擎 + 可插拔 adapter + 模板画廊（21 模板）+ AI 配乐
- 技术栈：TypeScript monorepo / Remotion & HyperFrames adapters / CLI / content-graph
- 亮点：
  1. **EngineRegistry 可插拔渲染引擎**：`packages/core/src/registry.ts`——EngineAdapter 注册表，remotion/hyperframes 各自适配，模板统一扫描注册——与主项目 provider registry 完全同构
  2. **ContentGraph + topoSort**：`@html-video/content-graph` 以图驱动多帧视频编排（validate + topoSort + 默认帧时长）
  3. **ProjectOrchestrator**：createProject→setTemplate/setVariables→renderPreviewHtml→exportMp4 的工程化状态机（status draft…）
- 对主项目价值：**★★★★★ 最高价值（架构层）**
- 借鉴点：Multi-frame 视频编排 = content-graph + 渲染引擎注册表 + 模板系统。主项目若走「模板化短视频」（非逐帧付费生成），可用 EngineAdapter 抽象承接 Remotion/HyperFrames 渲染；ContentGraph 与主项目 DAG 编排可对照进化
- 评分：5

## kids-blessing-video-wizard
- 定位：儿童祝福短视频分步向导 Skill（不是一键，每次只推一步、记住前选）
- 技术栈：Agent skill
- 亮点：「分步向导 + 关键节点人工确认（生成参考图→确认→图生视频）」——可交互的渐进式生成流程
- 对主项目价值：局部借鉴
- 借鉴点：分步推进 + 中间确认的设计，与主项目任务「审核节点」（如生图前确认）可结合；面向场景化（节日祝福）的模板化
- 评分：2

## sanoTTS
- 定位：极小型神经 TTS（294k-2.3M 参数）——跑 $3 单片机或浏览器 WASM
- 技术栈：Python/C/Arduino/WASM/16 语言 30 音色
- 亮点：极致轻量 + 无云端（RTF 0.383 on ESP32-S3）、零依赖音素化
- 对主项目价值：扩展方向参考（极端轻量 TTS，与后端生成场景匹配度低）
- 借鉴点：极端小模型思路可作为嵌入式/离线 TTS 前瞻；短视频编排用不上
- 评分：1

## video-analyzer
- 定位：视频分析工具——关键帧喂视觉模型 + Whisper 转写 → 生成视频描述
- 技术栈：Python / Llama3.2 Vision(Ollama) / Whisper / OpenAI 兼容 API
- 亮点：可全本地（无需 API key）或任意 OpenAI 兼容服务；关键帧提取 + 双模态融合描述；完整 DESIGN 文档 + prompt 调优章节
- 对主项目价值：局部借鉴
- 借鉴点：关键帧→VLM 描述（vid2text）可复用为成品视频质检；「本地/云端双模式」与主项目 provider 双模式一致
- 评分：3

## video-search-and-summarization
- 定位：NVIDIA 视频搜索与摘要 AI Blueprint（实时/留存视频的自然语言搜索、摘要、Q&A、告警验证）
- 技术栈：NVIDIA NIM / VLM / RAG / Clips 检索 / MCP
- 亮点：
  1. **Agent 工作流族**：Q&A/告警验证/实时告警/视频搜索/长视频摘要 5 个 reference workflow 分离清晰
  2. **三区处理**：实时视频智能（特征+embedding+流理解→消息代理发布）→下游分析（轨迹/事件/告警增强）→agentic 离线处理（工具化搜索/Q&A/检索）
  3. 引入 MCP 做 agent 编排入口
- 对主项目价值：扩展方向参考（视频理解/RAG；NVIDIA 依赖重）
- 借鉴点：视频 embedding 检索（VSS 的 video embedding 检索）可作为主项目视频素材库/质检的前瞻；架构参考价值 > 直接移植
- 评分：2

## video-shotcraft
- 定位：AI agent skill——产品宣传片/演示视频制作（Remotion 渲染），157 镜头配方卡 + 214 风格动效
- 技术栈：TypeScript / Remotion / workbench + template 工程化
- 亮点：
  1. **镜头配方卡（Shot Recipe Card）schema**：`references/shots/**/*.md` 每卡 YAML front-matter（name/一句话/适用/时长/能量/标签）+ 意图/动效核心/**参数表(典型值+调节手感)**/已知坑/参考实现——**动效参数工程化的绝佳模板，参数可调不是黑盒**
  2. **八阶段流水线**：`references/pipeline.md`——产品理解→视觉方向/styleframe→功能到镜头映射→分镜放行→素材采集→逐镜头→声音设计→独立终检；**每个镜头以 `npx remotion still` 静帧肉眼验收**，方向性问题不进昂贵逐镜头阶段
  3. **workbench + template 分离**：开发用的 workbench 与交付模板分离；jianying-export 导出剪映
- 对主项目价值：**★★★★★ 最高价值（内容生产方法论）**
- 借鉴点：现成短视频编排骨架——「recipe card(lens/shot) + pipeline 阶段门(gate) + remotion 渲染」。主项目 txt2vid 若做「产品宣传/讲解片」，shot 卡与阶段门是现成蓝本；「参数表典型值+手感」式文档组织也值得纳入主项目生图参数文档
- 评分：5

## video-talkcraft
- 定位：video-shotcraft 系列口播篇——口播稿 + 成品配音 → Remotion 解说成片（字级配音同步）
- 技术栈：TypeScript / Remotion / 字级时间戳对齐 / SHOTBOOK 分镜
- 亮点：
  1. **字级配音同步**：字幕、动效、镜头全部锁「人声」时间轴（word-level timestamp alignment）——口播视频的核心工程
  2. **七层反 PPT 镜头系统** + 108 动效卡 + 三重验收（review-protocol.md）
  3. references 文档体系完整（broll-sources/cinematography/shot-design/layout/design-language）
- 对主项目价值：**直接借鉴**（口播/讲解短视频是 txt2vid 主力场景）
- 借鉴点：字级时间戳对齐（Whisper word timestamps → 动效/字幕排布）——主项目做口播视频最值钱的一条；与 VideoCaptioner 的 word-level timestamp 呼应
- 评分：4

## video-use
- 定位：用 Claude Code 剪视频——丢原始素材进文件夹，对话拿 final.mp4（去填充词/调色/淡入淡出/烧字幕/动画覆盖层/自评/会话记忆）
- 技术栈：Python / ffmpeg / HyperFrames·Remotion·Manim·PIL / 并行子 agent
- 亮点：
  1. **并行子 agent 生成动画覆盖层**：每个动画 spawn 独立子 agent——多 agent 编排的素材产线
  2. **每个剪切边界自评渲染输出**（self-evaluates）+ `project.md` 会话记忆——持续自省 + 跨会话续接
  3. 去填充词（umm/uh）+ 30ms 淡入避免爆音——后期工程细节
- 对主项目价值：**直接借鉴**（剪辑/后期编排 + 自评 + 会话记忆，与主项目 agent 体系契合）
- 借鉴点：并行子 agent 素材产线 + 生成后自评门槛 + project.md 记忆模式——主项目 DAG 已具备类似机制，可确认视频剪辑算子（去词/调色/烧字）并入
- 评分：4

## wangge-dev__wangge-gpt-image-2-5
- 定位：旺哥 GPT Image 2.5 中文提示词库（104 基础 + 117 变体 + 电商专区）
- 技术栈：静态画廊 GitHub Pages / 数据目录组织
- 亮点：可筛选画廊 + 电商场景变体体系（30 套场景 86 变体）
- 对主项目价值：扩展方向参考
- 借鉴点：电商场景变体组织，可补主项目生图场景模板
- 评分：2

## xianyu110__awesome-gpt-image2.5
- 定位：GPT Image 2.5 社区玩法精选（173 条，偏一人团队/营销/可抄工作流）
- 技术栈：静态站 + skills.html + docs/playbooks
- 亮点：按「可抄工作流」组织；型号选型表（Flare 快便宜 vs Sunburst 高质量）与官方 playbook
- 对主项目价值：扩展方向参考
- 借鉴点：模型选型手册 + 可抄工作流整理法——主项目 provider 选型文档可借鉴
- 评分：2

## xianyu110__awesome-gptimage2
- 定位：GPT-Image-2 中文实战手册（770+ 可检索提示词、10+ 场景、方法论）
- 技术栈：静态站 schema/scripts + GitHub Pages
- 亮点：`schema/` 结构化数据 + 实测经验整合
- 对主项目价值：扩展方向参考
- 借鉴点：prompt 数据 schema 化组织
- 评分：2

## yangbishang__gpt-image-2.5-prompt
- 定位：GPT Image 2.5 提示词归档（124 examples、Flare/Sunburst 对照、可复现）
- 技术栈：静态站 + GitHub Actions 校验 + schemas/templates/tests
- 亮点：**CI 校验 catalog**（examples 结构校验 workflow）+ 参数/输入/对照齐全——数据资产工程化
- 对主项目价值：扩展方向参考
- 借鉴点：prompt archive 的 CI 校验（结构校验 workflow）——主项目 prompt 资产可加 schema 校验
- 评分：2

## zack-d-films-ai-video-generator
- 定位：Zack D Films 风格 3D 动画短视频全管线——一个主题→成片（脚本→角色三视图→keyframe→图生视频→配音克隆→ffmpeg 合成）
- 技术栈：Python / MuAPI(veo3.1 img2vid) / ffmpeg / Agent skill (SKILL.md)
- 亮点：
  1. **beats.json 项目 schema（核心！）**：`examples/swallow_gum_beats.json`——project_name/topic/aspect_ratio/style_preset/narrator_voice/character_sheets_required + beats[]（beat_id/narration/title/hook）+ shots[]（shot_id/type/duration_sec/scene_description/camera_move/character_refs/zoom_impact）——**从叙事拍(beat)到镜头(shot)到场景描述/运镜/时长/角色引用的完整结构化项目文件，主项目 txt2vid 项目模型的最佳模板**
  2. **GATE 人工确认点**：SKILL.md 流程明确「GATE 1: 审脚本 beats.json」「GATE 2: 选 keyframe 风格」——花钱生成（图生视频）前先以廉价产物(脚本/静帧)过审
  3. **MuAPIClient 提交-轮询封装**：`scripts/provider.py` 的 `_submit_and_poll(endpoint, payload, max_wait, poll_interval)`（POST→poll GET predictions/{id}/result）+ `_upload_file` 资产上传 + JSON 容错提取——供应商异步任务封装范式
  4. **ffmpeg 合成引擎**：`assemble.py`——统一 720x1280 画布/30fps/切点转场(长 0.35s 枚举 fade/wipeleft/slideleft/circleopen)/impact zoom/CRF23/音频 96k + ffprobe 时长/音频探测防错——竖屏视频装配的完整参数集
- 对主项目价值：**★★★★★ 最高价值（端到端视频项目模型）**
- 借鉴点：beats.json 项目模型（拍→镜→景）+ GATE 审点 + img2vid 异步封装 + ffmpeg 装配参数。主项目做 txt2vid 最直接路径 = 把「beats.json」建模成 DB 表/路由请求 + 复用主项目现有 provider 轮询 + 新增 assemble 阶段
- 评分：5

---

# 本组汇总：Top3 最值得主项目借鉴项（视频扩展方向）

**Top1 — Pixelle-Video / zack-d-films 的项目-分镜-镜头数据模型（Storyboard / beats.json）**
- 证据：`Pixelle-Video/pixelle_video/models/storyboard.py`（StoryboardConfig/StoryboardFrame 含 task_id 隔离、narration+prompt+资源路径链+duration、is_completed 判定）、`zack-d-films-ai-video-generator/examples/swallow_gum_beats.json`（beats[]→shots[] 含 scene_description/camera_move/duration/character_refs）
- 迁移：主项目新增 txt2vid 时先定义「项目 Storyboard→拍(beat)→镜头(shot)」三层 schema（DB 表 + pydantic 并存），配 task_id 文件隔离；SSE 进度按 `ProgressEvent`（event_type+0-1 progress+frame_current/total+step+action）逐帧发布——主项目 SSE 事件流直接适配，前端进度条/任务详情页近零改造。

**Top2 — html-video / video-shotcraft 的渲染引擎注册表 + 镜头配方卡 + 阶段门流水线**
- 证据：`html-video/packages/core/src/registry.ts`（EngineRegistry 可插拔 EngineAdapter + TemplateRegistry 模板目录扫描）、`video-shotcraft/references/pipeline.md`（八阶段 + 「方向性问题不进昂贵逐镜头阶段」+ 每镜头 remotion still 静帧验收）、`references/shots/**`（YAML front-matter 配方卡：适用/时长/能量/参数表典型值+手感/已知坑）
- 迁移：主项目扩展「模板化短视频」（不强依赖单次付费 txt2vid）时，用 EngineAdapter 抽象承接 Remotion/HyperFrames 渲染后端；镜头/模板做成配方卡资产（参数表化、非黑盒）；流水线加「廉价产物过审 gate」（脚本/静帧确认后再花钱生成，呼应 zack-d GATE1/2）；每镜头静帧验收呼应主项目真实闭环铁则。

**Top3 — Pixelle-Video 多供应商视频客户端族 + zack-d 异步提交-轮询封装**
- 证据：`Pixelle-Video/pixelle_video/services/api_services/{video_kling,video_seedance,video_dashscope,vlm_*}.py`（每家独立 client：Kling 含 JWT 鉴权/TLS1.2 适配器/Retry session，上层统一 list_workflows）、`zack-d-films-ai-video-generator/scripts/provider.py::_submit_and_poll`（POST→轮询 /predictions/{id}/result、_upload_file 资产上传、JSON 容错提取）
- 迁移：主项目 providers 已按 base.py+registry 分家，新增 txt2vid 能力 = 在既有抽象上加 `image_to_video` 动作族（kling/seedance/veo/fal 等），复用现有 MAB-EWMA 路由 + 熔断 + 预算门禁；轮询/上传/JSON 容错直接对照 zack-d 实现。这是三条中最「低成本高确定性」的一条——主项目架构已为此预备好。

附加跨组洞察（供主项目参考，不占名额）：
- TTS/配音链：CosyVoice（重、自托管 LLM-TTS）+ LuxTTS/sanoTTS（轻）二态接入 provider 抽象；Eirias omnivoice 提供「MCP server 暴露 TTS + dub CLI」形态，正好接主项目 agent 体系。
- 口播/字幕链路：video-talkcraft 的「字级时间戳对齐驱动动效/字幕」+ VideoCaptioner 的「ASR 多引擎抽象 + 分块并发 + 窗口限流」是短视频文案到画面的两条关键工程。
- 视频理解/质检：claude-video(-vision)「感知层：帧图 + 带时间戳字幕 → LLM」可用于主项目 critic 节点对生成视频做 vid2text 自反思复核；video-search-and-summarization/VideoRAG/VoiceMem 属远期视频理解/检索方向。
- 提示词/资产类仓库（10+ 个 gpt-image 集合）对主项目生图 prompt 资产库价值为「数据源/模板化/CI 校验」三方面，与视频扩展方向弱相关，评分均在 2 分档。