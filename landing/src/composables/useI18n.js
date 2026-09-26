/**
 * P3-7 landing i18n —— 轻量中/英切换（不引 vue-i18n 重依赖）。
 * - 字典 zh / en 平行；t(key) 按当前 locale 取值，缺失回退到 key 本身。
 * - locale 持久化：localStorage 'landing-lang' > URL ?lang= > 浏览器语言 > 默认 zh。
 * - 提供 setLocale(lang) 与 toggle()，供语言切换按钮调用。
 * - 响应式：用 Vue ref，组件内 import { t, locale, setLocale, toggle } 即可。
 */
import { ref, computed } from 'vue'

/** locale 取值：'zh' | 'en'（JS 无 type alias，用 JSDoc 标注）。 */

/** 从 URL ?lang= 或 localStorage 或浏览器语言推断初始 locale。 */
/** @returns {'zh' | 'en'} */
function detectInitial() {
  if (typeof window === 'undefined') return 'zh'
  // 1. URL ?lang=
  const params = new URLSearchParams(window.location.search)
  const fromUrl = params.get('lang')
  if (fromUrl === 'en' || fromUrl === 'zh') return fromUrl
  // 2. localStorage
  const saved = localStorage.getItem('landing-lang')
  if (saved === 'en' || saved === 'zh') return saved
  // 3. 浏览器语言
  const nav = (navigator.language || 'zh').toLowerCase()
  if (nav.startsWith('en')) return 'en'
  return 'zh'
}

/** @type {import('vue').Ref<'zh' | 'en'>} */
export const locale = ref(detectInitial())

/** 持久化 + 同步 URL（去掉 ?lang= 让默认语言不污染 URL，非默认语言保留）。 */
/** @param {'zh' | 'en'} lang */
export function setLocale(lang) {
  locale.value = lang
  try {
    localStorage.setItem('landing-lang', lang)
  } catch {
    /* localStorage 不可用（隐私模式）静默忽略 */
  }
  // 同步 <html lang>（无障碍 + SEO）
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN'
  }
}

export function toggle() {
  setLocale(locale.value === 'zh' ? 'en' : 'zh')
}

/** 中/英字典。键名扁平，按页面分区分组（nav/hero/status/providers/usage/code/faq/changelog/cta/privacy/footer）。 */
/** @type {Record<'zh' | 'en', Record<string, string>>} */
const dict = {
  zh: {
    // nav
    'nav.docs': 'API 文档',
    'nav.admin': '进入管理台',
    'nav.privacy': '隐私',
    'nav.lang': 'EN',
    // hero
    'hero.badge': '自动逆向 · 号池 / 邮箱池 / 代理池 · 自动过 Cloudflare Turnstile',
    'hero.title': '多提供商 AI 生成网关',
    'hero.sub': '自动逆向 · 号池 / 邮箱池 / 代理池 · 高并发异步队列 · 自动过 Cloudflare Turnstile',
    // status
    'status.title': '实时状态',
    'status.loading': '加载中…',
    'status.unavailable': '⚠ 数据暂不可用',
    'status.aspect': '支持画幅：',
    'chip.total_requests': '总请求',
    'chip.total_images': '总出图',
    'chip.total_errors': '失败',
    'chip.avg_duration': '平均出图耗时',
    'chip.processing': '当前并发',
    'chip.queue': '队列',
    'chip.workers': 'Worker',
    'chip.cf_solver': 'CF 求解',
    // providers
    'providers.title': '提供商与模型',
    'providers.sync': '实时同步',
    'providers.models_count': '个模型',
    'providers.errors': '次错误',
    'providers.models_label': '模型',
    'providers.no_models': '未返回模型',
    'providers.empty': '暂无提供商数据',
    // usage
    'usage.title': '对话 Token 用量',
    'usage.unit': '24h',
    'usage.normal': '正常',
    'usage.total_label': '总 Tokens（prompt + completion + reasoning）',
    'usage.today': '今日',
    'usage.calls': '次',
    'usage.tokens': 'tokens',
    'usage.success_rate': '成功率',
    'usage.col_calls': '调用次数',
    'usage.col_prompt': '输入 tokens',
    'usage.col_completion': '输出 tokens',
    'usage.col_reasoning': '推理 tokens',
    'usage.col_duration': '平均耗时',
    'usage.col_tools': '工具调用',
    'usage.col_model': '模型',
    'usage.col_call': '调用',
    'usage.col_input': '输入',
    'usage.col_output': '输出',
    'usage.sub_calls_ok_fail': 'prompt',
    'usage.ok_calls_short': '成功',
    'usage.fail_calls_short': '失败',
    // code
    'code.title': 'API 快速开始',
    'code.sub': '写接口需',
    'code.sub2': '（聊天 / 生成 / 图生图）· 请合理使用',
    'code.sync.title': '同步生成 /v1/generate',
    'code.sync.desc': '等待出图，典型 20~45 秒',
    'code.async.title': '异步生成 /v1/generate/async',
    'code.async.desc': '立即返回任务 ID，高并发推荐',
    'code.chat.title': '聊天 /v1/chat/completions',
    'code.chat.desc': 'OpenAI 标准协议，流式/非流式',
    'code.health.title': '健康检查 /v1/healthz',
    'code.health.desc': '含实时并发/排队',
    'code.copy': '复制',
    'code.copied': '已复制 ✓',
    // faq
    'faq.title': '常见问题 · 手到即用',
    'faq.sub': '一键复制 curl，立即开始',
    'faq.q1': '如何获取 API Key？',
    'faq.a1': '进入管理台 /admin → 在线聊天或在线生成页右上角「配置 Key」填入。Key 仅保存在你本地浏览器 localStorage，永不上传。匿名只读端点无需 Key；写接口（生成/聊天）需 Key。',
    'faq.q2': '生成图像是同步还是异步？',
    'faq.a2': '同步 /v1/generate 等待出图（典型 20~45s）；高并发推荐异步 /v1/generate/async 立即返回任务 ID，再轮询 /v1/tasks/{id} 或订阅每任务 SSE /v1/tasks/{id}/events。',
    'faq.q3': '支持哪些客户端？',
    'faq.a3': 'OpenAI 兼容（Codex / Cursor / Continue / 任意 OpenAI SDK）用 /v1/chat/completions；Anthropic 兼容（Claude Code）用 /v1/messages。在线聊天页右上角「API 接入」有一键 curl 模板。',
    'faq.q4': '限流策略是什么？',
    'faq.a4': '按出口代理数估算每小时额度，触发 429 时前端会提示切换备用引擎。健康检查 /v1/healthz 含实时并发/排队/worker 数。',
    'faq.quick_title': '⚡ 手到即用 curl',
    // changelog
    'changelog.title': '更新日志 · 实时状态',
    'changelog.sub': '读',
    'changelog.sub2': '与最近 release notes',
    'changelog.loading': '加载中…',
    'changelog.fail_prefix': '更新日志暂不可用（',
    'changelog.full': '查看完整',
    'changelog.notes': '说明 ↗',
    'changelog.service': '服务状态',
    'changelog.cf': 'CF 求解',
    'changelog.worker': 'Worker',
    'changelog.concurrent': '并发',
    'changelog.queue': '排队',
    'changelog.dbrows': 'DB 行数',
    // cta
    'cta.title': '开始使用听风AI 生成网关',
    'cta.sub': '进入管理台管理号池、任务与账单 · 或查看完整 Swagger 接口文档',
    'cta.admin': '进入管理台',
    'cta.swagger': '查看 Swagger /docs',
    // footer
    'footer.owner': '负责人：听风',
    'footer.slow': '慢请求看板',
    'footer.coffee': '请我喝咖啡',
    // privacy
    'privacy.back': '← 返回首页',
    'privacy.updated': '最后更新',
    'privacy.disclaimer': '本声明为公益服务合规基础摘要，非完整法律文本。如有疑问请联系负责人。',
    // portal (Spec 009)
    'portal.badge': '免费 · 免登录 · 即刻创作',
    'portal.title': '一站式 AI 创意平台',
    'portal.sub': 'AI 对话 · 文生图 · 图生图 · AI 视频 · AI PPT · 智能体编排 —— 灵感画廊每日更新，全部免登录免费使用',
    'portal.cta': '立即开始创作',
    'portal.cta_sub': '下拉选择工具，点开即用',
    'portal.trust1': '真实出图 · R2 存储',
    'portal.trust2': '公益免费 · 无限畅用',
    'portal.trust3': '免登录 · 秒级上手',
    'portal.tools_title': '创作工具',
    'portal.tools_sub': '点开卡片，在线直接使用',
    'portal.gallery_title': '灵感画廊',
    'portal.gallery_sub': '社区最新创作的 AI 作品',
    'portal.gallery_empty': '画廊还没有作品，快去创作第一张吧',
    'portal.gallery_open': '前往管理台管理画廊',
    'portal.footer_note': '免登录 · 免费 · 公益 AI 创意平台',
    'tool.chat.name': 'AI 对话',
    'tool.chat.desc': '与前沿大模型实时对话，流式回复',
    'tool.chat.tag': '在线',
    'tool.chat.open': '开始对话',
    'tool.img.name': '文生图',
    'tool.img.desc': '一句话生成高清图片，多画幅可选',
    'tool.img.tag': '免费',
    'tool.img.open': '立即生成',
    'tool.edit.name': '图生图',
    'tool.edit.desc': '上传参考图，AI 帮你改写风格与内容',
    'tool.edit.tag': '免费',
    'tool.edit.open': '上传编辑',
    'tool.video.name': 'AI 视频',
    'tool.video.desc': '文生视频 / 图生视频，动态创意',
    'tool.video.tag': 'Beta',
    'tool.video.open': '生成视频',
    'tool.ppt.name': 'AI PPT',
    'tool.ppt.desc': '输入大纲，一键生成可编辑 PPTX',
    'tool.ppt.tag': '免费',
    'tool.ppt.open': '生成 PPT',
    'tool.agent.name': 'AI 智能体',
    'tool.agent.desc': '自然语言编排多步任务，自动执行',
    'tool.agent.tag': 'Agent',
    'tool.agent.open': '启动智能体',
    'pchat.kicker': '在线使用',
    'pchat.title': 'AI 对话',
    'pchat.sub': '选择模型即可开始聊天，回复实时流出',
    'pchat.placeholder': '输入你想问的…',
    'pchat.send': '发送',
    'pchat.empty': '还没有消息。回复会在这里逐字流出来。',
    'pchat.loading': '正在加载模型',
    'pchat.retry': '重试',
    'pchat.noModel': '当前没有可用的聊天模型。',
    'pgen.kicker': '在线生成',
    'pgen.title': '文生图 / 图生图',
    'pgen.prompt': '描述你想生成的画面…',
    'pgen.aspect': '画幅',
    'pgen.generate': '生成',
    'pgen.busy': '生成中…',
    'pgen.done': '生成完成 ✓',
    'pgen.error': '生成失败',
    'pgen.upload': '上传参考图（图生图）',
    'pgen.mode_txt': '文生图',
    'pgen.mode_img': '图生图',
    'pgen.noModel': '当前没有可用的生图模型。',
    'pgen.edit_hint': '图生图生成约需 5-10 分钟，请耐心等待…',
    'pvideo.kicker': 'AI 视频',
    'pvideo.prompt': '描述你想生成的视频…',
    'pvideo.submit': '生成视频',
    'pvideo.beta': 'Beta · Mock 演示',
    'pvideo.off': '视频生成暂未开放（敬请期待）',
    'pppt.kicker': 'AI PPT',
    'pppt.title': '一键生成 PPTX',
    'pppt.title_ph': '演示文稿标题',
    'pppt.page_headline': '页面主题',
    'pppt.page_points': '要点（每行一条）',
    'pppt.add_page': '+ 添加一页',
    'pppt.gen': '生成 PPTX',
    'pppt.downloading': '生成中…',
    'pppt.done': '下载成功 ✓',
    'pppt.err': 'PPT 生成失败',
    'pppt.off': 'PPT 生成暂未开放（敬请期待）',
    'pagent.kicker': 'AI 智能体',
    'pagent.title': '自然语言编排任务',
    'pagent.prompt': '描述你想让智能体完成的任务…',
    'pagent.plan': '生成执行计划',
    'pagent.run': '执行',
    'pagent.running': '执行中…',
    'pagent.done': '执行完成 ✓',
    'pagent.err': '智能体执行失败',
    'pagent.noPlan': '无法生成执行计划，请换个说法试试',
    'footer.note': '听风AI · 公益免费 · 免登录',
  },
  en: {
    // nav
    'nav.docs': 'API Docs',
    'nav.admin': 'Open Console',
    'nav.privacy': 'Privacy',
    'nav.lang': '中',
    // hero
    'hero.badge': 'Auto reverse-engineering · account/email/proxy pools · auto-solve Cloudflare Turnstile',
    'hero.title': 'Multi-Provider AI Generation Gateway',
    'hero.sub': 'Auto reverse-engineering · account/email/proxy pools · high-concurrency async queue · auto-solve Cloudflare Turnstile',
    // status
    'status.title': 'Live Status',
    'status.loading': 'Loading…',
    'status.unavailable': '⚠ Data unavailable',
    'status.aspect': 'Aspect ratios: ',
    'chip.total_requests': 'Requests',
    'chip.total_images': 'Images',
    'chip.total_errors': 'Errors',
    'chip.avg_duration': 'Avg time',
    'chip.processing': 'Concurrent',
    'chip.queue': 'Queue',
    'chip.workers': 'Workers',
    'chip.cf_solver': 'CF solver',
    // providers
    'providers.title': 'Providers & Models',
    'providers.sync': 'live sync',
    'providers.models_count': ' models',
    'providers.errors': ' errors',
    'providers.models_label': 'Models',
    'providers.no_models': 'no models',
    'providers.empty': 'No provider data',
    // usage
    'usage.title': 'Chat Token Usage',
    'usage.unit': '24h',
    'usage.normal': 'OK',
    'usage.total_label': 'Total Tokens (prompt + completion + reasoning)',
    'usage.today': 'Today',
    'usage.calls': ' calls',
    'usage.tokens': 'tokens',
    'usage.success_rate': 'success',
    'usage.col_calls': 'Calls',
    'usage.col_prompt': 'Prompt tokens',
    'usage.col_completion': 'Completion tokens',
    'usage.col_reasoning': 'Reasoning tokens',
    'usage.col_duration': 'Avg duration',
    'usage.col_tools': 'Tool calls',
    'usage.col_model': 'Model',
    'usage.col_call': 'Calls',
    'usage.col_input': 'Input',
    'usage.col_output': 'Output',
    'usage.sub_calls_ok_fail': 'prompt',
    'usage.ok_calls_short': 'ok',
    'usage.fail_calls_short': 'fail',
    // code
    'code.title': 'Quick Start',
    'code.sub': 'Write endpoints need',
    'code.sub2': ' (chat / generate / img2img) · use responsibly',
    'code.sync.title': 'Sync /v1/generate',
    'code.sync.desc': 'Wait for image, typically 20~45s',
    'code.async.title': 'Async /v1/generate/async',
    'code.async.desc': 'Returns task id immediately, recommended for high concurrency',
    'code.chat.title': 'Chat /v1/chat/completions',
    'code.chat.desc': 'OpenAI-compatible, streaming/non-streaming',
    'code.health.title': 'Health /v1/healthz',
    'code.health.desc': 'Includes live concurrency/queue',
    'code.copy': 'Copy',
    'code.copied': 'Copied ✓',
    // faq
    'faq.title': 'FAQ · Ready to Use',
    'faq.sub': 'One-click copy curl, start now',
    'faq.q1': 'How do I get an API key?',
    'faq.a1': 'Open the console /admin → enter the key via "Configure Key" in the top-right of the chat or generate page. The key is stored only in your browser localStorage and never uploaded. Anonymous read-only endpoints need no key; write endpoints (generate/chat) require one.',
    'faq.q2': 'Is image generation sync or async?',
    'faq.a2': 'Sync /v1/generate waits for the image (typically 20~45s); for high concurrency use async /v1/generate/async which returns a task id immediately, then poll /v1/tasks/{id} or subscribe to per-task SSE /v1/tasks/{id}/events.',
    'faq.q3': 'Which clients are supported?',
    'faq.a3': 'OpenAI-compatible (Codex / Cursor / Continue / any OpenAI SDK) via /v1/chat/completions; Anthropic-compatible (Claude Code) via /v1/messages. The chat page top-right "API Access" has one-click curl templates.',
    'faq.q4': 'What is the rate-limit policy?',
    'faq.a4': 'Hourly quota is estimated by the number of exit proxies; on 429 the frontend suggests switching to a backup engine. Health check /v1/healthz shows live concurrency/queue/worker counts.',
    'faq.quick_title': '⚡ Ready-to-use curl',
    // changelog
    'changelog.title': 'Changelog · Live Status',
    'changelog.sub': 'reads',
    'changelog.sub2': ' and recent release notes',
    'changelog.loading': 'Loading…',
    'changelog.fail_prefix': 'Changelog unavailable (',
    'changelog.full': 'View full',
    'changelog.notes': 'notes ↗',
    'changelog.service': 'Service',
    'changelog.cf': 'CF solver',
    'changelog.worker': 'Worker',
    'changelog.concurrent': 'Concurrent',
    'changelog.queue': 'Queue',
    'changelog.dbrows': 'DB rows',
    // cta
    'cta.title': 'Start Using the Generation Gateway',
    'cta.sub': 'Open the console to manage account pools, tasks and billing · or read the full Swagger docs',
    'cta.admin': 'Open Console',
    'cta.swagger': 'Swagger /docs',
    // footer
    'footer.owner': 'Maintainer: Tingfeng',
    'footer.slow': 'Slow requests',
    'footer.coffee': 'Buy me a coffee',
    // privacy
    'privacy.back': '← Back to home',
    'privacy.updated': 'Last updated',
    'privacy.disclaimer': 'This statement is a compliance summary for a public-interest service, not a full legal text. Contact the maintainer with any questions.',
    // portal (Spec 009)
    'portal.badge': 'Free · No login · Create now',
    'portal.title': 'All-in-one AI Creative Platform',
    'portal.sub': 'AI Chat · Text to Image · Image to Image · AI Video · AI PPT · Agent Orchestration — inspiration gallery updated daily, free & no login',
    'portal.cta': 'Start Creating',
    'portal.cta_sub': 'Scroll down, pick a tool, use it instantly',
    'portal.trust1': 'Real images · R2 storage',
    'portal.trust2': 'Public welfare · Free',
    'portal.trust3': 'No login · Instant',
    'portal.tools_title': 'Create',
    'portal.tools_sub': 'Click a card to use it online',
    'portal.gallery_title': 'Inspiration Gallery',
    'portal.gallery_sub': 'Latest AI artworks from the community',
    'portal.gallery_empty': 'No artworks yet — create the first one!',
    'portal.gallery_open': 'Open gallery manager',
    'portal.footer_note': 'No login · Free · Public AI creative platform',
    'tool.chat.name': 'AI Chat',
    'tool.chat.desc': 'Talk to frontier models with streaming replies',
    'tool.chat.tag': 'Live',
    'tool.chat.open': 'Start chatting',
    'tool.img.name': 'Text to Image',
    'tool.img.desc': 'One sentence to HD images, multiple ratios',
    'tool.img.tag': 'Free',
    'tool.img.open': 'Generate now',
    'tool.edit.name': 'Image to Image',
    'tool.edit.desc': 'Upload a reference, let AI restyle it',
    'tool.edit.tag': 'Free',
    'tool.edit.open': 'Upload & edit',
    'tool.video.name': 'AI Video',
    'tool.video.desc': 'Text/Image to video, dynamic creativity',
    'tool.video.tag': 'Beta',
    'tool.video.open': 'Generate video',
    'tool.ppt.name': 'AI PPT',
    'tool.ppt.desc': 'Outline in, editable PPTX out',
    'tool.ppt.tag': 'Free',
    'tool.ppt.open': 'Generate PPT',
    'tool.agent.name': 'AI Agent',
    'tool.agent.desc': 'Orchestrate multi-step tasks from natural language',
    'tool.agent.tag': 'Agent',
    'tool.agent.open': 'Launch agent',
    'pchat.kicker': 'Try it',
    'pchat.title': 'AI Chat',
    'pchat.sub': 'Pick a model and start talking — replies stream in live',
    'pchat.placeholder': 'Ask something…',
    'pchat.send': 'Send',
    'pchat.empty': 'No messages yet. Replies stream in here.',
    'pchat.loading': 'Loading models',
    'pchat.retry': 'Retry',
    'pchat.noModel': 'No chat model available right now.',
    'pgen.kicker': 'Generate online',
    'pgen.title': 'Text / Image to Image',
    'pgen.prompt': 'Describe the image you want…',
    'pgen.aspect': 'Ratio',
    'pgen.generate': 'Generate',
    'pgen.busy': 'Generating…',
    'pgen.done': 'Done ✓',
    'pgen.error': 'Generation failed',
    'pgen.upload': 'Upload reference (img2img)',
    'pgen.mode_txt': 'Text to Image',
    'pgen.mode_img': 'Image to Image',
    'pgen.noModel': 'No image model available right now.',
    'pgen.edit_hint': 'Image-to-image takes about 5-10 minutes, please wait…',
    'pvideo.kicker': 'AI Video',
    'pvideo.prompt': 'Describe the video you want…',
    'pvideo.submit': 'Generate video',
    'pvideo.beta': 'Beta · Mock demo',
    'pvideo.off': 'Video generation is not available yet (coming soon)',
    'pppt.kicker': 'AI PPT',
    'pppt.title': 'Generate PPTX in one click',
    'pppt.title_ph': 'Presentation title',
    'pppt.page_headline': 'Page headline',
    'pppt.page_points': 'Bullet points (one per line)',
    'pppt.add_page': '+ Add page',
    'pppt.gen': 'Generate PPTX',
    'pppt.downloading': 'Generating…',
    'pppt.done': 'Downloaded ✓',
    'pppt.err': 'PPT generation failed',
    'pppt.off': 'PPT generation is not available yet (coming soon)',
    'pagent.kicker': 'AI Agent',
    'pagent.title': 'Orchestrate tasks from natural language',
    'pagent.prompt': 'Describe the task you want the agent to complete…',
    'pagent.plan': 'Build execution plan',
    'pagent.run': 'Execute',
    'pagent.running': 'Running…',
    'pagent.done': 'Done ✓',
    'pagent.err': 'Agent execution failed',
    'pagent.noPlan': 'Could not build a plan — try a different description',
    'footer.note': 'TingfengAI · Public welfare · No login',
  },
}

/** 翻译函数：t('key') → 当前 locale 对应字符串；缺失回退 key 本身。 */
/** @param {string} key @returns {string} */
export function t(key) {
  const m = dict[locale.value] || dict.zh
  return m[key] ?? dict.zh[key] ?? key
}

/** 供模板内响应式使用（computed 包一层，locale 切换自动重算）。 */
export const tComputed = computed(() => (key) => t(key))

/** 初始化 <html lang>。 */
if (typeof document !== 'undefined') {
  document.documentElement.lang = locale.value === 'en' ? 'en' : 'zh-CN'
}
