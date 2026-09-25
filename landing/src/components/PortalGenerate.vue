<script setup>
/**
 * PortalGenerate — 门户在线文生图 / 图生图（Spec 009）
 * - 文生图：POST /v1/generate（同步等待）→ 任务 SSE /v1/tasks/{id}/events 更快反馈
 * - 图生图：POST /v1/edit（异步）→ 轮询 /v1/edit/tasks/{id}
 * 免登录免费（生产鉴权放开）；真实 imagefree/aifreeforever 上游。
 */
import { computed, onMounted, ref } from 'vue'
import { t } from '../composables/useI18n'

const props = defineProps({
  mode: { type: String, default: 'txt' }, // 'txt' | 'img'
})

const models = ref([])
const model = ref('')
const loadingModels = ref(true)
const modelError = ref('')
const prompt = ref('')
const aspect = ref('1:1')
const busy = ref(false)
const resultUrl = ref('')
const resultError = ref('')
const uploadData = ref('')
const fileInput = ref(null)
const pollRef = ref(null)

const ASPECTS = ['1:1', '3:4', '4:3', '9:16', '16:9', '3:2', '2:3', '21:9']
const isImg = computed(() => props.mode === 'img')
const canSubmit = computed(() => {
  if (busy.value) return false
  if (isImg.value) return !!uploadData.value && prompt.value.trim().length > 0
  return prompt.value.trim().length > 0
})

async function loadModels() {
  loadingModels.value = true
  modelError.value = ''
  try {
    const response = await fetch('/v1/models')
    if (!response.ok) throw new Error('HTTP ' + response.status)
    const data = await response.json()
    const all = []
    for (const list of Object.values(data.items || {})) {
      if (!Array.isArray(list)) continue
      for (const m of list) {
        const caps = Array.isArray(m.capabilities) ? m.capabilities : []
        const kind = isImg.value ? (caps.includes('img2img') ? 'img2img' : caps.includes('txt2img') ? 'txt2img' : '') : 'txt2img'
        if (kind && !all.some((x) => x.id === m.id)) all.push({ ...m, kind })
      }
    }
    models.value = all.filter((m) => m.kind === (isImg.value ? 'img2img' : 'txt2img'))
    if (!models.value.some((m) => m.id === model.value)) model.value = models.value[0]?.id || ''
    if (!models.value.length) modelError.value = t('pgen.noModel')
  } catch (error) {
    modelError.value = error?.message || String(error)
  } finally {
    loadingModels.value = false
  }
}

function onFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => { uploadData.value = String(reader.result) }
  reader.readAsDataURL(file)
}

function clearPoll() {
  if (pollRef.value) { clearInterval(pollRef.value); pollRef.value = null }
}

async function submit() {
  if (!canSubmit.value) return
  resultUrl.value = ''
  resultError.value = ''
  busy.value = true
  try {
    if (isImg.value) {
      // 图生图（异步编辑）
      const response = await fetch('/v1/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: uploadData.value, prompt: prompt.value.trim(), model: model.value || undefined }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || body.error || ('HTTP ' + response.status))
      const taskId = body.task_id || body.id
      if (!taskId) throw new Error('no task id')
      await pollEdit(taskId)
    } else {
      // 文生图：同步 /v1/generate（真实出图等待）
      const response = await fetch('/v1/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt.value.trim(), aspect_ratio: aspect.value, model: model.value || undefined }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || body.error || ('HTTP ' + response.status))
      if (body.status === 'completed' && body.image_url) {
        resultUrl.value = body.image_url
      } else if (body.status === 'completed' && body.image_base64) {
        resultUrl.value = body.image_base64
      } else if (body.task_id || body.id) {
        await pollTask(body.task_id || body.id)
      } else {
        throw new Error('生成未返回结果')
      }
    }
  } catch (error) {
    resultError.value = (error?.message || String(error)).slice(0, 280)
  } finally {
    busy.value = false
  }
}

function pollTask(taskId) {
  return new Promise((resolve) => {
    const es = new EventSource(`/v1/tasks/${taskId}/events`)
    const timer = setTimeout(() => { es.close(); resolve() }, 90000)
    es.addEventListener('result', () => {
      void fetch(`/v1/tasks/${taskId}`).then((r) => r.json()).then((task) => {
        if (task.image_url) resultUrl.value = task.image_url
        else if (task.image_base64) resultUrl.value = task.image_base64
      }).catch(() => {}).finally(() => { es.close(); clearTimeout(timer); resolve() })
    })
    es.addEventListener('error', (ev) => {
      const raw = (ev && ev.data) || ''
      const data = JSON.parse(raw || '{}')
      if (data && data.error) resultError.value = (data.error.message || data.error).slice(0, 200)
      es.close(); clearTimeout(timer); resolve()
    })
  })
}

function pollEdit(taskId) {
  return new Promise((resolve) => {
    let fails = 0
    const poll = async () => {
      try {
        const r = await fetch(`/v1/edit/tasks/${taskId}`)
        const task = await r.json()
        if (task.status === 'completed') {
          if (task.image_url) resultUrl.value = task.image_url
          else if (task.image_base64) resultUrl.value = task.image_base64
          clearPoll(); resolve()
        } else if (task.status === 'error') {
          resultError.value = task.error || '图生图失败'
          clearPoll(); resolve()
        } else {
          fails = 0
        }
      } catch (e) {
        fails += 1
        if (fails >= 5) { resultError.value = '任务查询失败'; clearPoll(); resolve() }
      }
    }
    void poll()
    pollRef.value = setInterval(poll, 3000)
  })
}

onMounted(loadModels)
</script>

<template>
  <div class="portal-gen">
    <div class="pgen-head">
      <p class="kicker">{{ t('pgen.kicker') }}</p>
      <h3>{{ isImg ? t('pgen.mode_img') : t('pgen.mode_txt') }}</h3>
    </div>

    <div v-if="loadingModels" class="skeleton" aria-busy="true"><span></span><span></span></div>
    <p v-else-if="modelError" class="gen-error" role="alert">{{ modelError }}</p>

    <template v-else>
      <div v-if="isImg" class="upload-row">
        <input ref="fileInput" type="file" accept="image/*" class="sr-file" @change="onFile" />
        <button type="button" class="btn btn-ghost btn-sm" @click="fileInput?.click()">
          {{ t('pgen.upload') }}
        </button>
        <span v-if="uploadData" class="upload-ok">✓</span>
        <img v-if="uploadData" :src="uploadData" alt="reference" class="thumb" />
      </div>

      <div class="gen-form">
        <textarea
          v-model="prompt"
          :placeholder="t('pgen.prompt')"
          rows="2"
          :disabled="busy"
        ></textarea>
        <div class="gen-row">
          <label v-if="!isImg" class="aspect-pick">
            <span>{{ t('pgen.aspect') }}</span>
            <select v-model="aspect" :disabled="busy">
              <option v-for="a in ASPECTS" :key="a" :value="a">{{ a }}</option>
            </select>
          </label>
          <button type="button" class="btn btn-primary" :disabled="!canSubmit" @click="submit">
            {{ busy ? t('pgen.busy') : t('pgen.generate') }}
          </button>
        </div>
      </div>

      <div v-if="busy" class="gen-busy" role="status">
        <span class="dot ok"></span> {{ t('pgen.busy') }}
      </div>
      <p v-else-if="resultError" class="gen-error" role="alert">⚠ {{ resultError }}</p>
      <div v-else-if="resultUrl" class="gen-result">
        <img :src="resultUrl" :alt="prompt" loading="lazy" />
        <a :href="resultUrl" target="_blank" rel="noopener" class="btn btn-ghost btn-sm">{{ t('pgen.done') }} ↗</a>
      </div>
    </template>
  </div>
</template>

<style scoped>
.portal-gen { display: flex; flex-direction: column; gap: var(--space-3); }
.pgen-head { display: flex; align-items: baseline; gap: var(--space-3); }
.kicker { margin: 0; color: var(--brand-2); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
h3 { margin: 0; font-size: 20px; }
.gen-form textarea, .aspect-pick select, .composer button, .gen-error button {
  min-height: 44px; border-radius: var(--radius-sm); border: 1px solid var(--line-2);
  background: var(--bg-2); color: var(--text); font: inherit;
}
.gen-form textarea { width: 100%; padding: 10px 12px; resize: vertical; }
.gen-row { display: flex; gap: 10px; align-items: center; justify-content: space-between; margin-top: 10px; }
.aspect-pick { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
.aspect-pick select { padding: 0 10px; min-height: 40px; }
.btn-sm { padding: 8px 14px; font-size: 13px; min-height: 40px; }
.upload-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sr-file { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.upload-ok { color: var(--ok); font-weight: 700; }
.thumb { width: 72px; height: 72px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--line-2); }
.gen-busy { color: var(--muted); font-size: 13px; display: inline-flex; align-items: center; gap: 8px; }
.gen-error { color: var(--warn); font-size: 13px; }
.gen-result img { max-width: 100%; max-height: 360px; border-radius: var(--radius); border: 1px solid var(--line-2); }
.gen-result { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
.skeleton { display: grid; gap: 8px; }
.skeleton span { display: block; height: 14px; border-radius: 8px; background: linear-gradient(90deg, var(--card-2), var(--card-hover), var(--card-2)); background-size: 200% 100%; animation: shine 1.1s infinite; }
.skeleton span:nth-child(2) { width: 80%; }
@keyframes shine { from { background-position: 100% 0; } to { background-position: -100% 0; } }
@media (max-width: 768px) {
  .gen-row { flex-direction: column; align-items: stretch; }
  .btn-primary { width: 100%; }
}
</style>
