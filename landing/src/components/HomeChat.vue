<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { locale } from '../composables/useI18n'

const models = ref([])
const model = ref('')
const loadingModels = ref(true)
const modelError = ref('')
const input = ref('')
const sending = ref(false)
const messages = ref([])
const scroller = ref(null)

const copy = computed(() => {
  if (locale.value === 'en') {
    return {
      kicker: 'Try it',
      title: 'Chat on the homepage',
      sub: 'tryingopen is the live agent upstream. Pick a model and talk. Image providers stay on imagefree / aifreeforever.',
      placeholder: 'Ask something…',
      send: 'Send',
      empty: 'No messages yet. The reply streams in here.',
      loading: 'Loading models',
      retry: 'Retry',
      noModel: 'No tryingopen chat model is available.',
    }
  }
  return {
    kicker: '在线使用',
    title: '首页直接对话',
    sub: 'tryingopen 是 agent 和这里的真实上游。选模型就能聊。生图仍走 imagefree / aifreeforever。',
    placeholder: '输入你想问的…',
    send: '发送',
    empty: '还没有消息。回复会在这里逐字流出来。',
    loading: '正在加载模型',
    retry: '重试',
    noModel: '当前没有可用的 tryingopen 聊天模型。',
  }
})

const canSend = computed(() => input.value.trim().length > 0 && !sending.value && !!model.value)

async function loadModels() {
  loadingModels.value = true
  modelError.value = ''
  try {
    const response = await fetch('/v1/chat/models')
    if (!response.ok) throw new Error('HTTP ' + response.status)
    const data = await response.json()
    const items = (data.items || []).filter((item) => String(item.id || '').startsWith('tryingopen/'))
    models.value = items
    if (!items.some((item) => item.id === model.value)) model.value = items[0]?.id || ''
    if (!items.length) modelError.value = copy.value.noModel
  } catch (error) {
    modelError.value = error?.message || String(error)
  } finally {
    loadingModels.value = false
  }
}

watch(messages, async () => {
  await nextTick()
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
}, { deep: true })

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  if (!model.value) {
    modelError.value = copy.value.noModel
    return
  }
  input.value = ''
  const history = [...messages.value, { role: 'user', content: text }]
  const assistant = { role: 'assistant', content: '', pending: true, error: false }
  messages.value = [...history, assistant]
  sending.value = true
  try {
    const response = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: model.value,
        stream: true,
        messages: history.map((item) => ({ role: item.role, content: item.content })),
      }),
    })
    if (!response.ok || !response.body) {
      const errText = await response.text()
      throw new Error(errText.slice(0, 280) || ('HTTP ' + response.status))
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const data = line.slice(5).trim()
        if (!data || data === '[DONE]') continue
        let payload
        try { payload = JSON.parse(data) } catch { continue }
        if (payload.error) throw new Error(payload.error.message || 'stream error')
        const delta = payload.choices?.[0]?.delta || {}
        if (typeof delta.content === 'string' && delta.content) assistant.content += delta.content
      }
      messages.value = [...history, { ...assistant }]
      if (done) break
    }
    if (!assistant.content) assistant.content = locale.value === 'en' ? '(empty reply)' : '（空回复）'
  } catch (error) {
    assistant.error = true
    assistant.content = assistant.content || ((locale.value === 'en' ? 'Request failed: ' : '请求失败：') + (error?.message || error))
  } finally {
    assistant.pending = false
    messages.value = [...history, { ...assistant }]
    sending.value = false
  }
}

function onKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}

onMounted(loadModels)
</script>

<template>
  <section class="home-chat" aria-labelledby="home-chat-title">
    <div class="home-chat-head">
      <div>
        <p class="kicker">{{ copy.kicker }}</p>
        <h2 id="home-chat-title">{{ copy.title }}</h2>
        <p class="sub">{{ copy.sub }}</p>
      </div>
      <label class="model-pick">
        <span class="sr">model</span>
        <select v-model="model" :disabled="loadingModels || !models.length">
          <option v-if="!models.length" value="">tryingopen</option>
          <option v-for="item in models" :key="item.id" :value="item.id">{{ item.display_name || item.id }}</option>
        </select>
      </label>
    </div>

    <div v-if="loadingModels" class="skeleton" aria-busy="true" :aria-label="copy.loading">
      <span></span><span></span><span></span>
    </div>
    <p v-else-if="modelError" class="chat-error" role="alert">
      {{ modelError }}
      <button type="button" @click="loadModels">{{ copy.retry }}</button>
    </p>

    <div ref="scroller" class="thread" role="log" aria-live="polite">
      <p v-if="!messages.length" class="empty">{{ copy.empty }}</p>
      <article v-for="(item, index) in messages" :key="index" :class="['bubble', item.role, { err: item.error }]">
        <span class="who">{{ item.role === 'user' ? 'You' : 'tryingopen' }}</span>
        <p v-if="item.content">{{ item.content }}</p>
        <span v-else-if="item.pending" class="skeleton inline" aria-hidden="true"><i></i><i></i><i></i></span>
      </article>
    </div>

    <form class="composer" @submit.prevent="send">
      <textarea
        v-model="input"
        :placeholder="copy.placeholder"
        rows="2"
        :disabled="sending"
        @keydown="onKeydown"
      ></textarea>
      <button type="submit" :disabled="!canSend">{{ sending ? '…' : copy.send }}</button>
    </form>
  </section>
</template>

<style scoped>
.home-chat {
  margin-top: var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--card);
  box-shadow: var(--shadow-card);
}
.home-chat-head { display: flex; justify-content: space-between; gap: var(--space-3); align-items: flex-end; }
.kicker { margin: 0; color: var(--brand-2); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
h2 { margin: 4px 0; font-size: 28px; }
.sub { margin: 0; color: var(--muted); max-width: 62ch; }
.model-pick select, .composer textarea, .composer button, .chat-error button {
  min-height: 44px; border-radius: var(--radius-sm); border: 1px solid var(--line-2);
  background: var(--bg-2); color: var(--text); font: inherit;
}
.model-pick select { padding: 0 12px; }
.thread { min-height: 220px; max-height: 420px; overflow: auto; margin: var(--space-3) 0; display: flex; flex-direction: column; gap: 10px; }
.empty { color: var(--muted); }
.bubble { padding: 10px 12px; border-radius: 14px; background: var(--card-2); max-width: min(100%, 680px); }
.bubble.user { align-self: flex-end; background: var(--brand-soft); }
.bubble.err { border: 1px solid var(--err); }
.who { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.bubble p { margin: 0; white-space: pre-wrap; }
.composer { display: flex; gap: 10px; align-items: flex-end; }
.composer textarea { flex: 1; padding: 10px 12px; resize: vertical; }
.composer button { padding: 0 18px; background: var(--brand); color: #041018; font-weight: 700; cursor: pointer; }
.composer button:disabled { opacity: 0.5; cursor: not-allowed; }
.chat-error { color: var(--warn); }
.skeleton { display: grid; gap: 8px; margin-top: 16px; }
.skeleton span, .skeleton i { display: block; height: 14px; border-radius: 8px; background: linear-gradient(90deg, var(--card-2), var(--card-hover), var(--card-2)); background-size: 200% 100%; animation: shine 1.1s infinite; }
.skeleton span:nth-child(2), .skeleton i:nth-child(2) { width: 80%; }
.skeleton span:nth-child(3), .skeleton i:nth-child(3) { width: 55%; }
.skeleton.inline { display: flex; gap: 6px; margin: 0; }
.skeleton.inline i { width: 42px; height: 10px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
@keyframes shine { from { background-position: 100% 0; } to { background-position: -100% 0; } }
@media (max-width: 768px) {
  .home-chat-head, .composer { flex-direction: column; align-items: stretch; }
  h2 { font-size: 22px; }
  .composer button { width: 100%; }
}
</style>
