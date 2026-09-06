<script setup lang="ts">
/**
 * Hero3D — 抽象粒子流场背景（裸 Three.js，懒加载）
 * 语义：AI 生成 · 数据流转汇聚（呼应网关聚合多提供商）
 * - 粒子沿流场漂移，颜色在天蓝 ↔ 粉珊瑚间渐变
 * - 鼠标 parallax 相机微移
 * - 三档降级：reduced-motion / WebGL 不可用 → CSS aura
 * - three 动态 import 不进 LCP 关键路径；forceContextLoss 防 GL 句柄累积
 *
 * P2-C2: 粒子数按视口断点细化 —— 小屏 800 / 中屏 1400 / 大屏 2200
 * （原固定 2200 在手机上 GPU 压力大，掉帧明显；按断点降级）
 */
import { ref, onMounted, onBeforeUnmount, shallowRef, computed } from 'vue'
import { useMediaQuery } from '@vueuse/core'

const props = withDefaults(defineProps<{
  count?: number
  area?: number
}>(), {
  count: 0,  // 0 = 按断点自适应
  area: 18
})

const canvasHost = ref<HTMLElement | null>(null)
const ok = ref(true)
const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
// P2-C2: 断点细化粒子数
const small = useMediaQuery('(max-width: 768px)')
const medium = useMediaQuery('(max-width: 1280px)')
const adaptiveCount = computed(() => {
  if (props.count > 0) return props.count  // 显式传入则用之
  if (small.value) return 800
  if (medium.value) return 1400
  return 2200
})

// ctx 持有不可代理的 three 对象；phase 与 build/loop 共享同一份引用
interface Ctx { THREE: any; scene: any; camera: any; renderer: any; points: any; phase: Float32Array }
const ctx = shallowRef<Ctx | null>(null)

let raf = 0
let mouseX = 0, mouseY = 0, tX = 0, tY = 0
let onMove: ((e: MouseEvent) => void) | null = null
let onResize: (() => void) | null = null

function onMoveFn(e: MouseEvent) {
  tX = (e.clientX / window.innerWidth - 0.5) * 2
  tY = (e.clientY / window.innerHeight - 0.5) * 2
}

function loop() {
  const c = ctx.value
  if (!c) return
  const { scene, camera, renderer, points, phase } = c
  const time = performance.now() * 0.0002

  points.rotation.y = time * 0.6
  points.rotation.x = Math.sin(time * 0.4) * 0.15

  const attr = points.geometry.attributes.position
  const arr = attr.array as Float32Array
  const n = Math.floor(arr.length / 3) // 缓存上界，避免每帧除法
  for (let i = 0; i < n; i++) {
    arr[i * 3 + 1] += Math.sin(time * 2 + phase[i]) * 0.004
  }
  attr.needsUpdate = true

  mouseX += (tX - mouseX) * 0.04
  mouseY += (tY - mouseY) * 0.04
  camera.position.x = mouseX * 0.8
  camera.position.y = -mouseY * 0.5
  camera.lookAt(0, 0, 0)

  renderer.render(scene, camera)
  raf = requestAnimationFrame(loop)
}

onMounted(async () => {
  try {
    const THREE = await import('three')
    const host = canvasHost.value
    if (!host) return
    const w = host.clientWidth || window.innerWidth
    const h = host.clientHeight || window.innerHeight

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 100)
    camera.position.set(0, 0, 8)

    // 直接创建 renderer；失败即降级，省掉探测用的 GL context
    let renderer: any
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' })
    } catch {
      ok.value = false
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6))
    renderer.setSize(w, h)
    renderer.setClearColor(0x000000, 0)
    host.appendChild(renderer.domElement)

    const n = adaptiveCount.value
    const positions = new Float32Array(n * 3)
    const colors = new Float32Array(n * 3)
    const phase = new Float32Array(n)
    const cBlue = new THREE.Color('#60a5fa')
    const cPink = new THREE.Color('#f472b6')
    const tmp = new THREE.Color()

    for (let i = 0; i < n; i++) {
      const i3 = i * 3
      const r = (Math.random() ** 0.5) * props.area
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      positions[i3] = r * Math.sin(phi) * Math.cos(theta)
      positions[i3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.7
      positions[i3 + 2] = r * Math.cos(phi)

      tmp.copy(cBlue).lerp(cPink, Math.random())
      colors[i3] = tmp.r
      colors[i3 + 1] = tmp.g
      colors[i3 + 2] = tmp.b
      phase[i] = Math.random() * Math.PI * 2
    }

    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))

    const mat = new THREE.PointsMaterial({
      size: 0.06,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true
    })

    const points = new THREE.Points(geo, mat)
    scene.add(points)

    ctx.value = { THREE, scene, camera, renderer, points, phase }

    onMove = onMoveFn
    window.addEventListener('mousemove', onMove, { passive: true })
    onResize = () => {
      if (!canvasHost.value || !renderer || !camera) return
      const w = canvasHost.value.clientWidth
      const h = canvasHost.value.clientHeight
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    window.addEventListener('resize', onResize)

    if (!reduced.value) {
      raf = requestAnimationFrame(loop)
    } else {
      renderer.render(scene, camera)
    }
  } catch (e) {
    console.warn('[Hero3D] init failed, fallback to CSS', e)
    ok.value = false
  }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  if (onMove) window.removeEventListener('mousemove', onMove)
  if (onResize) window.removeEventListener('resize', onResize)
  const c = ctx.value
  if (c) {
    // forceContextLoss 先于 dispose：强制释放底层 GL context，防小屏↔大屏切换累积句柄
    c.renderer?.forceContextLoss?.()
    c.renderer?.dispose?.()
    c.renderer?.domElement?.remove()
    c.points?.geometry?.dispose()
    c.points?.material?.dispose()
  }
  ctx.value = null
})
</script>

<template>
  <div class="hero3d" ref="canvasHost" aria-hidden="true">
    <div v-if="!ok" class="hero3d-fallback"></div>
  </div>
</template>

<style scoped>
.hero3d {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: hidden;
}
.hero3d :deep(canvas) {
  display: block;
}
.hero3d-fallback {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(closest-side at 50% 40%, rgba(96, 165, 250, 0.22), transparent 65%),
    radial-gradient(closest-side at 20% 70%, rgba(244, 114, 182, 0.14), transparent 60%),
    radial-gradient(closest-side at 80% 30%, rgba(96, 165, 250, 0.12), transparent 60%);
  filter: blur(10px);
}
</style>
