<script setup>
/**
 * P3-7 隐私声明 / DPA 页 —— 公益服务合规基础摘要。
 * 通过 hash 路由 #/privacy 渲染（避免后端 StaticFiles 深链 404）。
 * 中/英双语（locale 切换自动重算）。
 */
import { computed } from 'vue'
import { t, locale } from '../composables/useI18n'

const isEn = computed(() => locale.value === 'en')

const sections = computed(() => isEn.value ? [
  {
    h: '1. Data We Collect',
    p: 'When you call the generation / chat API, we log the minimum data needed to operate and debug the service:',
    items: [
      'Request metadata: timestamp, endpoint, model id, prompt text (for generation), aspect ratio / resolution.',
      'Result metadata: status (success/fail), latency, error code, upstream provider used.',
      'Network: your IP address (for rate-limiting and abuse protection), User-Agent.',
      'Auth: a masked form of your API key (e.g. sk-tfai-12***), never the full key.',
      'Account pool: for providers that need accounts, we store the registration email / cookie / password locally to keep the pool running; these are reverse-engineered test accounts, not real user accounts.',
    ],
  },
  {
    h: '2. Retention',
    p: 'Logs and request records are kept in SQLite for operational observability:',
    items: [
      'Request history and metrics: ~30 days rolling, then auto-pruned.',
      'Error / dead-letter queue: ~30 days for debugging.',
      'Account pool state: persistent (needed for the service to function).',
      'Backups: daily snapshots retained 7 days (see docs/SOP.md).',
    ],
  },
  {
    h: '3. Third-Party Upstream Providers',
    p: 'Your prompts and images are forwarded to one of these upstream providers based on routing. We do not control their privacy practices — review their terms if relevant:',
    items: [
      'imagefree — main site, no account needed.',
      'aifreeforever — free, per-IP daily quota, uses free proxy rotation.',
      'nanobanana-pro — credit-based, uses self-managed test accounts with daily check-in.',
      'falai — optional provider (toggle-gated).',
      'tryingopen — chat provider, per-IP hourly limit.',
    ],
  },
  {
    h: '4. Your Rights (GDPR / CCPA basics)',
    p: 'As a public-interest service we honor the spirit of GDPR / CCPA:',
    items: [
      'Access: you can request a summary of what we logged for your API key.',
      'Deletion: you can request deletion of your request history tied to your key.',
      'No profiling: we do not build behavioral profiles or sell data.',
      'No cookies: the landing page stores only your language preference in localStorage; no tracking cookies.',
    ],
  },
  {
    h: '5. Security',
    p: 'Basic safeguards in place:',
    items: [
      'API keys are stored as environment variables, never in source.',
      'Admin endpoints require a separate admin key (IF_ADMIN_KEYS).',
      'Security headers (HSTS / X-Content-Type-Options / Referrer-Policy) injected when enabled.',
      'Rate limiting per IP and per key to prevent abuse.',
    ],
  },
  {
    h: '6. Contact',
    p: 'This is a personal public-interest project. Contact the maintainer via GitHub for any privacy request:',
    items: [
      'GitHub: github.com/lza6',
      'For data-access / deletion requests, include your masked API key for verification.',
    ],
  },
] : [
  {
    h: '1. 我们收集的数据',
    p: '当你调用生成 / 聊天 API 时，我们会记录运行与排查所需的最少数据：',
    items: [
      '请求元数据：时间戳、端点、模型 id、提示词（生成用）、画幅/分辨率。',
      '结果元数据：状态（成功/失败）、耗时、错误码、所用上游提供商。',
      '网络：你的 IP 地址（用于限流与防滥用）、User-Agent。',
      '鉴权：API Key 的脱敏形式（如 sk-tfai-12***），绝不存全 Key。',
      '号池：对需要账号的提供商，本地存注册邮箱 / cookie / 密码以维持号池运转；这些是逆向测试账号，非真实用户账号。',
    ],
  },
  {
    h: '2. 保留期',
    p: '日志与请求记录存于 SQLite 用于运维可观测：',
    items: [
      '请求历史与指标：~30 天滚动，到期自动清理。',
      '错误 / 死信队列：~30 天用于排查。',
      '号池状态：持久化（服务运行必需）。',
      '备份：每日快照保留 7 天（见 docs/SOP.md）。',
    ],
  },
  {
    h: '3. 第三方上游提供商',
    p: '你的提示词与图像会按路由转发到以下上游之一。我们无法控制其隐私实践——必要时请查阅其条款：',
    items: [
      'imagefree —— 主站，无需账号。',
      'aifreeforever —— 免费，每 IP 每日限额，使用免费代理轮换。',
      'nanobanana-pro —— 积分制，使用自管测试账号每日签到续额。',
      'falai —— 可选提供商（开关控制）。',
      'tryingopen —— 聊天提供商，每 IP 每时限额。',
    ],
  },
  {
    h: '4. 你的权利（GDPR / CCPA 基础）',
    p: '作为公益服务，我们遵循 GDPR / CCPA 的精神：',
    items: [
      '访问：你可请求我们针对你的 API Key 记录的数据摘要。',
      '删除：你可请求删除与你的 Key 关联的请求历史。',
      '不做画像：我们不构建行为画像，不售卖数据。',
      '无 Cookie：落地页仅在 localStorage 存语言偏好，无追踪 Cookie。',
    ],
  },
  {
    h: '5. 安全',
    p: '已落实的基础防护：',
    items: [
      'API Key 以环境变量存储，绝不入源码。',
      '管理端点需独立管理 Key（IF_ADMIN_KEYS）鉴权。',
      '安全响应头（HSTS / X-Content-Type-Options / Referrer-Policy）开启时注入。',
      '按 IP 与按 Key 限流防滥用。',
    ],
  },
  {
    h: '6. 联系方式',
    p: '这是个人公益项目。如需隐私请求，通过 GitHub 联系负责人：',
    items: [
      'GitHub：github.com/lza6',
      '数据访问 / 删除请求请附上你的脱敏 API Key 以便核验。',
    ],
  },
])
</script>

<template>
  <main class="privacy container">
    <a class="back" href="/#/" @click.prevent="$router && $router.push('/') ? null : (window.location.hash = '')">{{ t('privacy.back') }}</a>
    <h1>{{ isEn ? 'Privacy Statement & DPA Summary' : '隐私声明 / DPA 摘要' }}</h1>
    <p class="meta muted-2">
      <span>{{ t('privacy.updated') }}：2026-09-01</span>
      <span class="sep">·</span>
      <span>{{ t('privacy.disclaimer') }}</span>
    </p>

    <section v-for="(s, i) in sections" :key="i" class="psec">
      <h2>{{ s.h }}</h2>
      <p class="muted">{{ s.p }}</p>
      <ul>
        <li v-for="(it, j) in s.items" :key="j" class="muted">{{ it }}</li>
      </ul>
    </section>
  </main>
</template>

<style scoped>
.privacy {
  max-width: 820px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4) var(--space-7);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.back {
  font-size: 13px;
  color: var(--brand-2);
  align-self: flex-start;
}
.back:hover { text-decoration: underline; }
h1 {
  font-size: clamp(26px, 4vw, 38px);
  font-weight: 800;
  letter-spacing: -0.02em;
  background: linear-gradient(120deg, #fff, var(--brand-2));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.meta {
  font-size: 13px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.meta .sep { color: var(--muted-2); }
.psec {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: var(--space-4);
  background: var(--card);
}
.psec h2 {
  font-size: 18px;
  margin-bottom: var(--space-2);
}
.psec p { font-size: 14px; line-height: 1.6; margin-bottom: var(--space-2); }
.psec ul { margin: 0; padding-left: 1.2em; display: flex; flex-direction: column; gap: 6px; }
.psec li { font-size: 13.5px; line-height: 1.6; }
</style>
