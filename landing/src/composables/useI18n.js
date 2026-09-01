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
