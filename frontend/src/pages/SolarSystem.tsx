import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { notify } from '../api';

interface BodyInfo {
  name?: string;
  type?: string;
  dia?: string;
  period?: string;
  day?: string;
  kind?: string;
  year?: string;
  fact?: string;
}

interface PlanetSpec {
  name: string;
  color: number;
  darker?: string;
  bands?: boolean;
  radius: number;
  dist: number;
  period: number;
  day: number;
  dia: string;
  kind: string;
  year: string;
  fact: string;
}

interface SystemSpec {
  id: string;
  name: string;
  pos: [number, number, number];
  tiltX?: number;
  tiltZ?: number;
  star: {
    name: string;
    type: string;
    color: number;
    glow: string;
    radius: number;
    fact: string;
    kind: string;
    year: string;
  };
  planets: PlanetSpec[];
}

const reduceMotion =
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const STAR_COLORS = [
  '#cdd8ff', '#fff6e0', '#9fd4ff', '#d9c9ff',
];

function textureBands(base: string, darker: string): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 64;
  const g = c.getContext('2d')!;
  const b = new THREE.Color(base);
  const d = new THREE.Color(darker);
  for (let y = 0; y < 64; y++) {
    const f = Math.sin(y / 3.2) * 0.5 + 0.5;
    const col = b.clone().lerp(d, f * 0.7 + Math.random() * 0.12);
    g.fillStyle = `#${col.getHexString()}`;
    g.fillRect(0, y, 512, 1);
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.RepeatWrapping;
  t.repeat.x = 4;
  return t;
}

function textureGlow(r: number, g: number, b: number): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const x = c.getContext('2d')!;
  for (let y = 0; y < 64; y++) {
    for (let px = 0; px < 64; px++) {
      const dx = px - 32;
      const dy = y - 32;
      const d = Math.sqrt(dx * dx + dy * dy) / 32;
      const a = Math.max(0, 1 - d);
      x.fillStyle = `rgba(${r},${g},${b},${Math.pow(a, 2.2)})`;
      x.fillRect(px, y, 1, 1);
    }
  }
  return new THREE.CanvasTexture(c);
}

function spriteGlow(color: string, scale: number): THREE.Sprite {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d')!;
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, '#ffffff');
  grad.addColorStop(0.18, color);
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  const s = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: t,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
  );
  s.scale.set(scale, scale, 1);
  return s;
}

function starField(scene: THREE.Scene): void {
  const N = 9000;
  const pos = new Float32Array(N * 3);
  const col = new Float32Array(N * 3);
  const size = new Float32Array(N);
  const palette = STAR_COLORS.map(c => new THREE.Color(c));
  for (let i = 0; i < N; i++) {
    const r = 900 + Math.random() * 1500;
    const t = Math.random() * Math.PI * 2;
    const p = Math.acos(Math.random() * 2 - 1);
    pos[i * 3] = r * Math.sin(p) * Math.cos(t);
    pos[i * 3 + 1] = r * Math.cos(p);
    pos[i * 3 + 2] = r * Math.sin(p) * Math.sin(t);
    const c = palette[Math.floor(Math.random() * palette.length)];
    col[i * 3] = c.r;
    col[i * 3 + 1] = c.g;
    col[i * 3 + 2] = c.b;
    size[i] = Math.random() < 0.03 ? 2.2 : 0.8 + Math.random() * 1.1;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  g.setAttribute('size', new THREE.BufferAttribute(size, 1));
  const m = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    vertexColors: true,
    vertexShader: `
      attribute float size;
      varying vec3 vC;
      void main() {
        vC = color;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = size * (340.0 / -mv.z);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: `
      varying vec3 vC;
      void main() {
        float d = distance(gl_PointCoord, vec2(0.5));
        float a = smoothstep(0.5, 0.05, d);
        gl_FragColor = vec4(vC, a);
      }
    `,
  });
  scene.add(new THREE.Points(g, m));
}

const SYSTEMS: SystemSpec[] = [
  {
    id: 'solar',
    name: '太阳系',
    pos: [0, 0, 0],
    star: {
      name: '太阳',
      type: '恒星 · G 型主序',
      color: 0xffcf70,
      glow: '#ffcf70',
      radius: 8,
      fact: '占太阳系总质量 99.86%，核心每秒将 6 亿吨氢聚变为氦。',
      kind: 'G 型主序星',
      year: '自古已知',
    },
    planets: [
      { name: '水星', color: 0x9c8f86, radius: 1.1, dist: 18, period: 4.2, day: 58.6, dia: '4,879 km', kind: '岩石行星', year: '自古已知', fact: '昼夜温差近 600°C，是一颗几乎无大气的铁核行星。' },
      { name: '金星', color: 0xe8c66a, radius: 1.6, dist: 26, period: 6.4, day: 243, dia: '12,104 km', kind: '岩石行星', year: '自古已知', fact: '硫酸云层下地表 460°C，温室效应失控的极端案例。' },
      { name: '地球', color: 0x3f6fd0, darker: '#1c3b86', radius: 1.7, dist: 36, period: 8.6, day: 1, dia: '12,742 km', kind: '岩石 · 宜居', year: '自古已知', fact: '已知唯一存在生命的天体。' },
      { name: '火星', color: 0xc0552e, radius: 1.3, dist: 47, period: 11.4, day: 1.03, dia: '6,779 km', kind: '岩石 · 沙漠', year: '自古已知', fact: '拥有太阳系最高火山奥林帕斯山。' },
      { name: '木星', color: 0xd8b28a, darker: '#8a6a45', bands: true, radius: 3.4, dist: 60, period: 16.2, day: 0.41, dia: '139,820 km', kind: '气态巨行星', year: '自古已知', fact: '红色大风暴已持续数百年。' },
      { name: '土星', color: 0xe2c587, darker: '#a2844f', bands: true, radius: 2.9, dist: 74, period: 20.6, day: 0.44, dia: '116,460 km', kind: '气态巨行星', year: '自古已知', fact: '环宽达 28 万 km，厚度却仅约 1 km。' },
      { name: '天王星', color: 0x8fd0d8, radius: 2.0, dist: 86, period: 26, day: 0.72, dia: '50,724 km', kind: '冰巨行星', year: '1781', fact: '自转轴近乎横躺。' },
      { name: '海王星', color: 0x3a60c8, radius: 1.9, dist: 96, period: 31, day: 0.67, dia: '49,244 km', kind: '冰巨行星', year: '1846', fact: '赤道风速可达 2,100 km/h。' },
    ],
  },
  {
    id: 'proxima',
    name: '比邻星',
    pos: [430, -60, 360],
    tiltX: 0.35,
    tiltZ: 0.5,
    star: {
      name: '比邻星', type: '恒星 · M 型红矮星', color: 0xff6a45, glow: '#ff6a45', radius: 3,
      fact: '距太阳 4.24 光年，是离我们最近的恒星邻居。', kind: '红矮星', year: '1915',
    },
    planets: [
      { name: '比邻星 b', color: 0x8a5a3a, radius: 1.15, dist: 14, period: 11.2, day: 11.2, dia: '约 1.07 R⊕', kind: '岩质 · 宜居带', year: '2016', fact: '位于宜居带内，但可能受耀斑潮汐锁定。' },
      { name: '比邻星 d', color: 0x9aa0b0, radius: 0.85, dist: 9, period: 5.1, day: 5.1, dia: '约 0.26 M⊕', kind: '岩质候选', year: '2020', fact: '疑似超短周期岩质候选行星。' },
    ],
  },
  {
    id: 'trappist',
    name: 'TRAPPIST-1',
    pos: [-520, 40, 320],
    tiltX: -0.2,
    tiltZ: 0.7,
    star: {
      name: 'TRAPPIST-1', type: '恒星 · M 型红矮星', color: 0xff7a55, glow: '#ff7a55', radius: 2.4,
      fact: '7 颗岩质行星挤在比水星更近的轨道上，3 颗在宜居带。', kind: '红矮星', year: '2015',
    },
    planets: Array.from('bcdefgh').map((l, i) => ({
      name: `TRAPPIST-1${l}`,
      color: [0x9c8f86, 0xb58a6a, 0x8a6a3a, 0x79b5a0, 0x7fb0d8, 0xa0b0c8, 0x6a7a90][i],
      radius: 0.9,
      dist: 10 + i * 4.4,
      period: 1.5 + i * 5.2,
      day: 0.5,
      dia: '约 0.77–1.15 R⊕',
      kind: '岩质行星',
      year: '2017',
      fact: '一套行星几乎等间隔公转。',
    })),
  },
  {
    id: 'kepler',
    name: '开普勒-22',
    pos: [0, 200, -520],
    tiltX: 0.3,
    tiltZ: -0.35,
    star: {
      name: '开普勒-22', type: '恒星 · G 型主序', color: 0xf5d76e, glow: '#f5d76e', radius: 6,
      fact: '一颗与太阳非常相似的恒星，拥有一枚早期宜居候选行星。', kind: 'G 型主序星', year: '2011',
    },
    planets: [
      { name: '开普勒-22b', color: 0x6fb0a8, radius: 2.3, dist: 40, period: 289.9, day: 0.79, dia: '约 2.4 R⊕', kind: '超级地球 · 宜居', year: '2011', fact: '第一颗确认位于类太阳恒星宜居带的系外行星。' },
    ],
  },
];

interface Pickable {
  mesh: THREE.Object3D;
  data: BodyInfo;
}

export function SolarSystem() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<BodyInfo | null>(null);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [fps, setFps] = useState(0);
  const pausedRef = useRef(paused);
  const speedRef = useRef(speed);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);
  useEffect(() => {
    speedRef.current = speed;
  }, [speed]);

  useEffect(() => {
    const host = containerRef.current;
    if (!host) return;
    let disposed = false;
    let raf = 0;

    try {
      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      const width = host.clientWidth || window.innerWidth;
      const height = host.clientHeight || window.innerHeight;
      renderer.setSize(width, height);
      host.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(55, width / height, 0.5, 8000);
      camera.position.set(65, 45, 120);

      scene.add(new THREE.HemisphereLight(0xbdd6ff, 0x0a0714, 0.5));
      starField(scene);

      const bg = new THREE.Mesh(
        new THREE.SphereGeometry(2600, 48, 32),
        new THREE.ShaderMaterial({
          side: THREE.BackSide,
          depthWrite: false,
          fog: false,
          uniforms: {
            c1: { value: new THREE.Color('#0a0f20') },
            c2: { value: new THREE.Color('#04060d') },
          },
          vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
          fragmentShader: 'varying vec3 vP; uniform vec3 c1; uniform vec3 c2; void main(){ float h = normalize(vP).y*0.5+0.5; gl_FragColor = vec4(mix(c2, c1, h), 1.0); }',
        })
      );
      scene.add(bg);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.07;
      controls.minDistance = 6;
      controls.maxDistance = 3000;
      controls.autoRotate = !reduceMotion;
      controls.autoRotateSpeed = 0.24;

      const pickables: Pickable[] = [];
      const labels: { el: HTMLDivElement; mesh: THREE.Object3D }[] = [];

      const labelBox = document.createElement('div');
      labelBox.style.cssText = 'position:absolute;inset:0;pointer-events:none;overflow:hidden;font-family:ui-monospace,monospace;font-size:11px;';
      host.style.position = 'relative';
      host.appendChild(labelBox);

      SYSTEMS.forEach(sys => {
        const pos = new THREE.Vector3(sys.pos[0], sys.pos[1], sys.pos[2]);
        const star = new THREE.Mesh(
          new THREE.SphereGeometry(sys.star.radius, 32, 32),
          new THREE.MeshStandardMaterial({
            color: sys.star.color,
            emissive: sys.star.color,
            emissiveIntensity: 1.6,
            roughness: 0.4,
          })
        );
        star.position.copy(pos);
        scene.add(star);
        pickables.push({
          mesh: star,
          data: { name: sys.star.name, type: sys.star.type, kind: sys.star.kind, year: sys.star.year, dia: `约 ${(sys.star.radius * 174000).toFixed(0)} km`, fact: sys.star.fact },
        });

        const glow = spriteGlow(sys.star.glow, sys.star.radius * 9.5);
        glow.position.copy(pos);
        glow.material.opacity = 0.35;
        scene.add(glow);

        const light = new THREE.PointLight(sys.star.color, 2600, 900, 1.6);
        light.position.copy(pos);
        scene.add(light);

        sys.planets.forEach(p => {
          const ringPts: THREE.Vector3[] = [];
          for (let i = 0; i <= 96; i++) {
            const a = (i / 96) * Math.PI * 2;
            ringPts.push(new THREE.Vector3(Math.cos(a) * p.dist, 0, Math.sin(a) * p.dist));
          }
          const ringGeo = new THREE.BufferGeometry().setFromPoints(ringPts);
          const ring = new THREE.Line(ringGeo, new THREE.LineBasicMaterial({ color: 0x8fb8ff, transparent: true, opacity: 0.28 }));
          ring.rotation.x = sys.tiltX || 0;
          ring.rotation.z = sys.tiltZ || 0;
          scene.add(ring);

          const mat = p.bands
            ? new THREE.MeshStandardMaterial({ map: textureBands(p.color.toString(16), p.darker || '#333'), roughness: 0.85 })
            : new THREE.MeshStandardMaterial({ color: p.color, roughness: p.name === '地球' ? 0.6 : 0.9 });
          const mesh = new THREE.Mesh(new THREE.SphereGeometry(p.radius, 24, 24), mat);
          const group = new THREE.Group();
          group.add(mesh);
          mesh.position.x = p.dist;
          group.position.copy(pos);
          group.rotation.x = sys.tiltX || 0;
          group.rotation.z = sys.tiltZ || 0;
          scene.add(group);

          if (p.name === '土星') {
            const satRing = new THREE.Mesh(
              new THREE.RingGeometry(p.radius * 1.4, p.radius * 2.3, 48),
              new THREE.MeshBasicMaterial({ color: 0xd9c9a0, transparent: true, opacity: 0.55, side: THREE.DoubleSide })
            );
            satRing.rotation.x = Math.PI / 2.4;
            mesh.add(satRing);
          }
          if (p.name === '地球') {
            const atm = new THREE.Mesh(
              new THREE.SphereGeometry(p.radius * 1.06, 24, 24),
              new THREE.MeshBasicMaterial({ map: textureGlow(120, 190, 255), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })
            );
            mesh.add(atm);
          }

          pickables.push({
            mesh,
            data: {
              name: p.name,
              type: p.kind,
              kind: p.kind,
              year: p.year,
              dia: p.dia,
              period: `${p.period} 天（缩放）`,
              day: `${p.day} 天`,
              fact: p.fact,
            },
          });
          mesh.userData = { period: p.period, radius: p.dist, angle: Math.random() * Math.PI * 2 };

          labels.push({
            el: makeLabel(`${p.name} · ${p.kind}`),
            mesh,
          });
        });
      });

      labels.push(...pickables
        .filter(el => el.data.name === '太阳' || el.data.name === '比邻星' || el.data.name === 'TRAPPIST-1' || el.data.name === '开普勒-22')
        .map(el => ({ el: makeLabel(el.data.name || ''), mesh: el.mesh })));

      function makeLabel(text: string): HTMLDivElement {
        const el = document.createElement('div');
        el.textContent = text;
        el.style.cssText = 'position:absolute;left:0;top:0;transform:translate(-50%,-160%);color:#93a1bd;text-shadow:0 1px 6px #000;transition:opacity .2s;white-space:nowrap;';
        labelBox.appendChild(el);
        return el;
      }

      const raycaster = new THREE.Raycaster();
      const ndc = new THREE.Vector2();
      const v = new THREE.Vector3();

      const onClick = (e: MouseEvent) => {
        ndc.x = (e.clientX / width) * 2 - 1;
        ndc.y = -(e.clientY / height) * 2 + 1;
        raycaster.setFromCamera(ndc, camera);
        const allMeshes = pickables.map(p => p.mesh);
        const hits = raycaster.intersectObjects(allMeshes, true);
        if (hits.length > 0) {
          const hit = hits[0];
          const found = pickables.find(p => p.mesh === hit.object || (hit.object.parent && p.mesh === hit.object.parent));
          if (found) setSelected(found.data);
        } else {
          setSelected(null);
        }
      };
      renderer.domElement.addEventListener('click', onClick);

      const onResize = () => {
        const w = host.clientWidth || window.innerWidth;
        const h = host.clientHeight || window.innerHeight;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      };
      window.addEventListener('resize', onResize);

      const allPlanets: THREE.Mesh[] = [];
      scene.traverse((o: THREE.Object3D) => {
        if (o.userData && o.userData.period !== undefined) allPlanets.push(o as THREE.Mesh);
      });

      let last = performance.now();
      let fpsAcc = 0;
      let fpsN = 0;
      function animate(now: number) {
        raf = requestAnimationFrame(animate);
        const dt = Math.min(0.08, (now - last) / 1000);
        last = now;
        fpsAcc += 1000 / Math.max(1, dt);
        fpsN++;
        if (fpsN >= 20) {
          if (!disposed) setFps(Math.round(fpsAcc / fpsN));
          fpsAcc = 0;
          fpsN = 0;
        }
        if (!pausedRef.current) {
          const k = speedRef.current;
          allPlanets.forEach(mesh => {
            mesh.userData.angle += ((Math.PI * 2) / Math.max(0.5, mesh.userData.period)) * dt * k * 0.06;
            mesh.position.x = Math.cos(mesh.userData.angle) * mesh.userData.radius;
            mesh.position.z = Math.sin(mesh.userData.angle) * mesh.userData.radius;
            mesh.rotation.y += dt * 0.4 * k;
          });
        }
        controls.update();
        labels.forEach(l => {
          l.mesh.getWorldPosition(v);
          const d = v.distanceTo(camera.position);
          const look = v.clone().sub(camera.position).normalize().dot(camera.getWorldDirection(new THREE.Vector3()));
          if (look < -0.1 || d > 480 || d < 2) {
            l.el.style.opacity = '0';
            return;
          }
          v.project(camera);
          l.el.style.left = `${(v.x * 0.5 + 0.5) * width}px`;
          l.el.style.top = `${(-v.y * 0.5 + 0.5) * height}px`;
          l.el.style.opacity = '1';
        });
        renderer.render(scene, camera);
      }
      raf = requestAnimationFrame(animate);

      return () => {
        disposed = true;
        cancelAnimationFrame(raf);
        window.removeEventListener('resize', onResize);
        renderer.domElement.removeEventListener('click', onClick);
        controls.dispose();
        renderer.dispose();
        if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement);
        if (labelBox.parentNode === host) host.removeChild(labelBox);
      };
    } catch (err) {
      notify(`3D 场景初始化失败: ${err instanceof Error ? err.message : String(err)}`, 'error');
      return () => {
        disposed = true;
      };
    }
  }, []);

  return (
    <div className="solar-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">宇宙星图 <span className="title-badge">3D WebGL</span></h1>
          <p className="page-desc">交互式 3D 行星系地图：左键旋转 · 滚轮缩放 · 点击天体查看详情 · 支持多星系切换与时间流速</p>
        </div>
        <div className="solar-actions">
          <button className="tf-btn tf-btn-secondary tf-btn-sm" onClick={() => setPaused(v => !v)}>
            {paused ? '▶ 播放' : '⏸ 暂停'}
          </button>
          <button className="tf-btn tf-btn-secondary tf-btn-sm" onClick={() => setSpeed(v => (v >= 20 ? 0.25 : v * 2))}>
            倍速 {speed}×
          </button>
        </div>
      </div>

      <div className="tf-card solar-card">
        <div className="solar-canvas" ref={containerRef} />
        <div className="solar-fps fade">{fps} FPS</div>
        {selected && (
          <div className="solar-info card-pop" role="dialog" aria-label="天体详情">
            <button className="solar-close" onClick={() => setSelected(null)} aria-label="关闭">×</button>
            <div className="solar-info-name">{selected.name || '未知'}</div>
            <div className="solar-info-tag">{selected.type || selected.kind || ''}</div>
            <div className="solar-info-kv">
              <span>直径</span><b>{selected.dia || '—'}</b>
              <span>发现</span><b>{selected.year || '—'}</b>
              <span>自转</span><b>{selected.day || '—'}</b>
              <span>公转</span><b>{selected.period || '—'}</b>
            </div>
            <div className="solar-info-fact">{selected.fact || ''}</div>
          </div>
        )}
      </div>

      <style>{`
        .solar-page { display: flex; flex-direction: column; gap: 20px; }
        .solar-actions { display: flex; gap: 10px; }
        .solar-card { position: relative; height: calc(100vh - 160px); min-height: 480px; overflow: hidden; border-radius: 14px; }
        .solar-canvas { position: absolute; inset: 0; }
        .solar-canvas canvas { display: block; width: 100%; height: 100%; cursor: grab; }
        .solar-canvas canvas:active { cursor: grabbing; }
        .solar-fps { position: absolute; right: 14px; top: 12px; z-index: 6; font-family: ui-monospace, monospace; font-size: 12px; color: rgba(148,163,184,.85); background: rgba(15,23,42,.6); border: 1px solid rgba(99,102,241,.3); padding: 4px 9px; border-radius: 8px; backdrop-filter: blur(6px); }
        .solar-info { position: absolute; left: 16px; bottom: 16px; z-index: 7; width: min(340px, calc(100% - 32px)); background: rgba(10,15,30,.86); border: 1px solid rgba(148,163,184,.25); border-radius: 14px; padding: 16px 18px; backdrop-filter: blur(14px); box-shadow: 0 18px 44px rgba(0,0,0,.5); }
        .solar-info-name { font-size: 19px; font-weight: 700; color: #f1f5f9; }
        .solar-info-tag { display: inline-block; margin-top: 5px; font-size: 11px; letter-spacing: .08em; color: #fbbf24; border: 1px solid rgba(251,191,36,.4); padding: 2px 8px; border-radius: 6px; }
        .solar-info-kv { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 14px; margin-top: 12px; font-size: 12px; }
        .solar-info-kv span { color: #94a3b8; }
        .solar-info-kv b { color: #e2e8f0; font-variant-numeric: tabular-nums; }
        .solar-info-fact { margin-top: 11px; padding-top: 10px; border-top: 1px solid rgba(148,163,184,.18); color: #94a3b8; font-size: 12.5px; line-height: 1.6; }
        .solar-close { position: absolute; right: 8px; top: 6px; background: none; border: 0; color: #94a3b8; font-size: 20px; cursor: pointer; }
        .solar-close:hover { color: #fff; }
        .card-pop { animation: cardPop .25s ease; }
        @keyframes cardPop { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
      `}</style>
    </div>
  );
}