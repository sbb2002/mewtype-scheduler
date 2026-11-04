// bgdomegl.js — (bg-dome 시험, ?bg=d) UFO 돔 실내를 WebGL2 한 장으로 그린다. 폰을 돌리면(bggyro.js) 보는 방향이 따라 돈다.
//
// 그리는 것(셰이더 = 픽셀마다 「그 방향으로 무엇이 보이나」를 계산):
//   · 돔 유리 — 구면 격자(위도 18 · 40 · 62°, 경도 30° 간격, 경도선은 천정까지). 선 굵기는 화면 픽셀 기준이라 각도가 바뀌어도 같다.
//   · 하늘 — 기존 구름 사진 두 장(가로로 이음매 없이 반복되는 이미지)을 한 바퀴에 3번 감는다. 천정 쪽은 하늘 평균색으로 녹인다.
//   · 바닥 — 남보라 반광택 공연 무대, 오각형 매립 조명 5개와 따뜻한 빛기둥. 밝게 테마도 어두운 재질에 주변광만 더 받는다.
// 공중 무늬(고리 · 별 · 지그재그 · 점 · 물결 · 반짝이)는 SVG 조각을 3D 위치에서 화면으로 투영해 transform 만 바꾼다(합성만 일어나 싸다).
// 평소엔 천천히 떠다니고(관성 있는 무작위 표류), 흔들면 튀어 나가 벽 · 바닥 · 서로에 부딪히며 섞인다. 다 가라앉으면 그때 폰 자세를 새 정면으로 삼는다.
//
// 비용: 카메라가 안 움직이면 구름 흐름만 초당 6번 다시 그린다. 화면 갱신은 평소 30fps · 레인을 걷은 「배경 보기」(html.bg-peek) 중 60fps.
// 평소엔 폰을 돌린 양의 35% 만 따라 돈다(카드를 보는 중엔 배경이 크게 휘돌지 않게). 해상도는 기기 배율 1.5 까지만.

import { startGyro, gyroView, rebase } from "./bggyro.js";

const DEG = Math.PI / 180;
const EYE = [0, 0.24, -0.42];          // 돔(반지름 1) 안 눈 위치 — bgdome.js 와 같다
const BASE_PITCH = 28 * DEG;
const GAIN_IDLE = 0.35, GAIN_PEEK = 1;
const PITCH_MIN = -55 * DEG, PITCH_MAX = 88 * DEG;
const CLOUD_MS = 160;                  // 카메라가 멈춰 있을 때 구름 흐름 다시 그리기 간격
const MAX_DPR = 1.5;
const DEBUG = new URLSearchParams(window.location.search).has("bgdebug");

const VS = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

const FS = `#version 300 es
precision highp float;
uniform vec2 uRes; uniform float uDpr; uniform vec2 uC; uniform float uF;
uniform vec3 uFwd, uRight, uUp;
uniform float uTime, uTex;
uniform sampler2D uSky, uCloud;
uniform mat3 uSkyM; uniform vec3 uSkyO; uniform mat3 uCldM; uniform vec3 uCldO; uniform float uCldA;
uniform vec3 uSkyBase; uniform float uGridA, uReflA;
uniform vec3 uFloorIn, uFloorOut, uPad, uGlow, uRim;
uniform float uFloorRefl, uLightK;
out vec4 outColor;
const float TAU = 6.2831853, D = 0.01745329;
const vec3 E = vec3(0.0, 0.24, -0.42);
float h1(float n) { return fract(sin(n * 127.1) * 43758.5453); }
float h2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
// 거리 d(세계 단위)인 선의 덮임 — pw = 픽셀 하나의 세계 크기, halfPx = 선 반폭(기기 픽셀)
float cover(float d, float pw, float halfPx) { return clamp(halfPx - d / pw + 0.5, 0.0, 1.0); }

vec3 sky(vec3 d) {
  float el = asin(clamp(d.y, -1.0, 1.0));
  float u = atan(d.x, d.z) / TAU * 3.0;
  float v = clamp((70.0 * D - el) / (82.0 * D), 0.002, 0.998);
  if (uTex < 0.5) return uSkyBase;
  vec3 c = clamp(uSkyM * textureLod(uSky, vec2(u + uTime / 2844.444, v), 0.0).rgb + uSkyO, 0.0, 1.0);
  vec4 n = textureLod(uCloud, vec2(u + uTime / 1280.0, v), 0.0);
  c = mix(c, clamp(uCldM * n.rgb + uCldO, 0.0, 1.0), n.a * uCldA);
  vec3 z = clamp(uSkyM * textureLod(uSky, vec2(0.5, 0.03), 7.0).rgb + uSkyO, 0.0, 1.0);
  vec3 hz = clamp(uSkyM * textureLod(uSky, vec2(u, 0.97), 6.0).rgb + uSkyO, 0.0, 1.0);   // 이미지 아래끝보다 낮은 쪽 = 지평선 평균색(끝줄이 세로로 늘어나 보이지 않게)
  c = mix(c, hz, smoothstep(-2.0 * D, -11.0 * D, el));
  return mix(c, z, smoothstep(50.0 * D, 84.0 * D, el));
}

void main() {
  vec2 p = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y) / uDpr;
  vec3 d = normalize(uFwd + uRight * (p.x - uC.x) / uF + uUp * (uC.y - p.y) / uF);

  // 돔(단위 구) 안쪽에서 나가는 점
  float b = dot(E, d), c = dot(E, E) - 1.0;
  vec3 q = E + (-b + sqrt(max(b * b - c, 0.0))) * d;
  float pwq = length(fwidth(q)) * 0.75;

  // ── 유리 + 하늘
  vec3 col = sky(d);
  float lat = asin(clamp(q.y, -1.0, 1.0)), cl = cos(lat);
  float lon = atan(q.x, q.z);
  float dLat = min(min(abs(lat - 18.0 * D), abs(lat - 40.0 * D)), abs(lat - 62.0 * D));
  float dLon = abs(mod(lon + 15.0 * D, 30.0 * D) - 15.0 * D) * cl;
  float hw = 0.525 * uDpr;
  float meridian = cover(dLon, pwq, hw) * smoothstep(2.0, 6.0, 30.0 * D * cl / max(pwq, 1e-6));   // 천정에서 선 간격이 몇 픽셀 안 되면 흰 덩어리 대신 흐리게 모인다
  float grid = max(cover(dLat, pwq, hw), meridian) * uGridA;
  col = mix(col, vec3(1.0), grid);
  float r1 = abs(lon + 71.0 * D) * cl, r2 = abs(lon - 69.0 * D) * cl;
  float refl = (exp(-pow(r1 / 0.045, 2.0)) + exp(-pow(r2 / 0.045, 2.0))) * smoothstep(8.0 * D, 20.0 * D, lat) * (1.0 - smoothstep(70.0 * D, 84.0 * D, lat));
  col = mix(col, vec3(1.0), refl * uReflA);

  // ── 바닥(공연 무대 원판)
  float tf = E.y / max(-d.y, 1e-3);
  vec2 P = E.xz + tf * d.xz;
  float pw = max(length(fwidth(P)) * 0.75, 1e-5);
  float r = length(P);
  vec3 fc = mix(uFloorIn, uFloorOut, smoothstep(0.0, 1.0, r));

  // 반광택 코팅: 넓은 하늘 반사와 미세한 표면 결. 픽셀보다 작은 결은 소거한다.
  float grazing = 1.0 - max(-d.y, 0.0);
  float fresnel = 0.035 + 0.24 * grazing * grazing * grazing * grazing * grazing;
  if (q.y < 0.0) {
    fc += uSkyBase * fresnel * uFloorRefl;
    float grain = sin(dot(P, vec2(213.0, 147.0))) + sin(dot(P, vec2(-157.0, 241.0)));
    fc *= 1.0 + 0.009 * grain * (1.0 - smoothstep(0.4, 1.1, pw * 300.0));
    fc *= 0.98 + 0.02 * sin(P.x * 19.0 + sin(P.y * 13.0));
  }

  // 빛기둥은 시선과 유한 원통의 교차 구간만 계산한다. 바닥/돔 뒤쪽은 잘라 낸다.
  const float beamH = 0.58, beamR = 0.105;
  float dy = (d.y < 0.0 ? -1.0 : 1.0) * max(abs(d.y), 1e-4);
  vec2 slab = vec2(-E.y, beamH - E.y) / dy;
  float sceneT = q.y < 0.0 ? tf : length(q - E);
  float tNear = max(0.0, min(slab.x, slab.y)), tFar = min(sceneT, max(slab.x, slab.y));
  float dxz2 = max(dot(d.xz, d.xz), 1e-5);
  float dxz = sqrt(dxz2);
  vec3 beam = vec3(0.0);

  // 반지름 0.42의 오각형 배치와 매립 조명 5개는 그대로 유지한다.
  for (int i = 0; i < 5; i++) {
    float a = float(i) * TAU / 5.0 + 0.31;
    vec2 cc = vec2(sin(a), cos(a)) * 0.42;
    vec2 o = E.xz - cc;
    float tAxis = -dot(o, d.xz) / dxz2;

    // 도함수는 위에서 구해 두므로 하늘 픽셀의 바닥 재질 계산은 생략해도 안전하다.
    if (q.y < 0.0) {
      vec2 v = P - cc;
      float dd = length(v);

      // 조명 웅덩이와 하우징 바깥쪽의 짧은 접촉 그림자.
      float pool = 1.0 / (1.0 + dot(v, v) / 0.014);
      fc += uGlow * pool * pool * 0.52 * uLightK;
      float shadow = 1.0 - smoothstep(0.079, 0.105 + pw, length(v - vec2(0.003, -0.005)));
      fc *= 1.0 - shadow * 0.42;

      // 바닥 아래 가상 빛기둥에 시선을 연장해 흐린 반사상을 얻는다.
      float tr = clamp(tAxis, tf, tf + 0.44 / max(-d.y, 1e-3));
      float rh = clamp(-(E.y + tr * d.y) / 0.44, 0.0, 1.0);
      vec2 rv = E.xz + tr * d.xz - cc;
      float rw = 0.048 + 0.08 * rh;
      float reflection = exp(-dot(rv, rv) / (rw * rw + pw * pw));
      fc += uPad * reflection * (1.0 - rh) * (0.07 + fresnel) * uFloorRefl;

      // 티타늄 외곽 턱 → 짙은 안쪽 벽 → 발광 렌즈. 모든 경계는 픽셀 면적으로 덮는다.
      float body = cover(dd - 0.087, pw, 0.5);
      float well = cover(dd - 0.068, pw, 0.5);
      float lens = cover(dd - 0.056, pw, 0.5);
      float facing = 0.5 + 0.5 * dot(v, vec2(-0.6, 0.8)) / max(dd, 1e-4);
      vec3 metal = mix(uFloorOut * 0.65, uRim * 0.8, facing * facing);
      fc = mix(fc, metal, body);
      fc = mix(fc, uFloorOut * 0.38, well);
      float glass = clamp(1.0 - dd * dd / (0.056 * 0.056), 0.0, 1.0);
      fc = mix(fc, mix(uGlow * 0.65, uPad * 2.8, 0.28 + 0.72 * glass) * uLightK, lens);
      float lip = max(body - cover(dd - 0.084, pw, 0.5), 0.0);
      fc += uRim * lip * (0.15 + 0.65 * facing);

      // 둘레의 작은 조명 8개: 대칭을 접어 최근접 점을 구하므로 추가 반복/각도 계산이 없다.
      vec2 av = abs(v), axial = vec2(max(av.x, av.y) - 0.075, min(av.x, av.y));
      vec2 diagonal = av - vec2(0.053033);
      float dl = sqrt(min(dot(axial, axial), dot(diagonal, diagonal)));
      float lights = cover(dl - 0.003, pw, 0.5) * smoothstep(1.0, 3.0, 0.025 / pw);
      fc += uPad * lights * 1.2 * uLightK;
    }

    // 원통 교차 길이와 최근접 거리로 볼륨을 근사한다. 레이마칭/텍스처 샘플은 없다.
    float closest2 = max(dot(o, o) - tAxis * tAxis * dxz2, 0.0);
    float chord = sqrt(max(beamR * beamR - closest2, 0.0) / dxz2);
    float lo = max(tNear, tAxis - chord), hi = min(tFar, tAxis + chord);
    if (hi > lo) {
      float span = hi - lo, tb = clamp(tAxis, lo, hi);
      float bh = clamp((E.y + (lo + span * 0.5) * d.y) / beamH, 0.0, 1.0);
      vec2 bv = E.xz + tb * d.xz - cc;
      float bw = 0.043 + 0.038 * bh;
      float radial = dot(bv, bv) / (bw * bw);
      float path = min(span, 1.77245 * bw / dxz);
      float fade = (1.0 - bh) * (1.0 - bh);
      float dust = 0.98 + 0.02 * sin(bh * 57.0 + float(i) * 2.0 + uTime * 0.35);
      beam += (uGlow * exp(-radial) * 0.75 + uPad * exp(-radial * 4.0) * 1.6) * path * fade * dust * 7.0 * uLightK;
    }
  }

  // 원판의 둥근 모서리: 안쪽의 은은한 빛과 바깥쪽의 어두운 턱.
  fc += uRim * (1.0 - smoothstep(0.0, 0.045, abs(r - 0.965))) * 0.12;
  fc *= 1.0 - smoothstep(0.975, 1.0, r) * 0.6;
  fc += uRim * cover(abs(r - 0.975), pw, 0.45 * uDpr) * 0.25;
  fc = fc / (vec3(1.0) + fc);   // 렌즈와 금속의 밝기 차를 남기는 바닥 전용 톤 매핑

  vec3 outc = q.y < 0.0 ? fc : col;
  outc += (vec3(1.0) - outc) * (vec3(1.0) - exp(-beam));   // 하늘/돔 앞에도 빛기둥을 합성한다
  outc += (h2(gl_FragCoord.xy) - 0.5) / 255.0;   // 그라데이션 띠 방지
  outColor = vec4(outc, 1.0);
}`;

// ── 색 · 필터(기존 CSS 의 테마별 구름 필터를 그대로 행렬로 옮긴다) ──
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
const mul = (A, B) => A.map((row) => [0, 1, 2].map((j) => row[0] * B[0][j] + row[1] * B[1][j] + row[2] * B[2][j]));
const sat = (s) => [
  [0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s],
  [0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s],
  [0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s],
];
const hue = (deg) => {
  const c = Math.cos(deg * DEG), s = Math.sin(deg * DEG);
  return [
    [0.213 + c * 0.787 - s * 0.213, 0.715 - c * 0.715 - s * 0.715, 0.072 - c * 0.072 + s * 0.928],
    [0.213 - c * 0.213 + s * 0.143, 0.715 + c * 0.285 + s * 0.140, 0.072 - c * 0.072 - s * 0.283],
    [0.213 - c * 0.213 - s * 0.787, 0.715 - c * 0.715 + s * 0.715, 0.072 + c * 0.928 + s * 0.072],
  ];
};
const bright = (k) => [[k, 0, 0], [0, k, 0], [0, 0, k]];

const THEMES = {
  dark: {
    skyM: [[0.204, 0.408, 0.068], [0.084, 0.168, 0.028], [0.132, 0.264, 0.044]], skyO: [0.04, 0.02, 0.04],
    cldM: [[0.27, 0.54, 0.09], [0.15, 0.30, 0.05], [0.204, 0.408, 0.068]], cldO: [0.06, 0.02, 0.04],
    skyBase: hex("#702747"), gridA: 0.23, reflA: 0.045,
    floorIn: hex("#262337"), floorOut: hex("#101320"),
    pad: hex("#fff0d7"), glow: hex("#b39ce8"), rim: hex("#a5a1bf"), floorRefl: 0.75, lightK: 0.9,
  },
  light: {
    skyM: mul(bright(1.12), mul(hue(344), sat(0.9))), skyO: [0, 0, 0],
    cldM: mul(bright(1.1), sat(0.85)), cldO: [0, 0, 0],
    skyBase: hex("#f6a8c4"), gridA: 0.54, reflA: 0.09,
    floorIn: hex("#3a344e"), floorOut: hex("#202334"),
    pad: hex("#fff3df"), glow: hex("#c4adee"), rim: hex("#c4b6cf"), floorRefl: 1.0, lightK: 1,
  },
};

// ── 공중 무늬(콘의 파스텔 외곽선 장식에서 모양 규칙만 따왔다) ──
const NS = "http://www.w3.org/2000/svg";
const GRADS = [["#ff8fbf", "#ffc38a"], ["#ffd36e", "#9ee6a8"], ["#8fe0d4", "#8fb5ff"], ["#a99bff", "#ff9ed2"], ["#ffa3a3", "#c59bff"], ["#7fd6ff", "#d79bff"]];
const BOX = 40;   // 조각 SVG 한 변(px, 확대 전)
const starPts = Array.from({ length: 10 }, (_, i) => {
  const a = i * Math.PI / 5 - Math.PI / 2, rad = i % 2 ? 4.8 : 11;
  return `${(Math.cos(a) * rad).toFixed(2)},${(Math.sin(a) * rad).toFixed(2)}`;
}).join(" ");
const SHAPES = {
  ring: (g) => `<circle r="9" fill="none" stroke="url(#${g})" stroke-width="3.4"/>`,
  star: (g) => `<polygon points="${starPts}" fill="none" stroke="url(#${g})" stroke-width="3" stroke-linejoin="round"/>`,
  zig: (g) => `<polyline points="-13,4 -6.5,-4 0,4 6.5,-4 13,4" fill="none" stroke="url(#${g})" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>`,
  dot: (g) => `<circle r="4.6" fill="url(#${g})"/>`,
  wave: (g) => `<path d="M-12 2 q6 -9 12 0 t12 0" fill="none" stroke="url(#${g})" stroke-width="3.2" stroke-linecap="round"/>`,
  spark: (g) => `<path d="M0 -11 Q2 -2 11 0 Q2 2 0 11 Q-2 2 -11 0 Q-2 -2 0 -11Z" fill="url(#${g})"/>`,
};
const KINDS = ["ring", "star", "dot", "zig", "spark", "ring", "star", "dot", "wave", "spark", "zig", "dot", "ring"];
const N_PIECES = 26;

const rnd = (a, b) => a + Math.random() * (b - a);
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const len3 = (a) => Math.hypot(a[0], a[1], a[2]);

function randUnit() {
  const z = rnd(-1, 1), a = rnd(0, Math.PI * 2), s = Math.sqrt(1 - z * z);
  return [s * Math.cos(a), z, s * Math.sin(a)];
}

/** 눈에서 (yaw, el) 방향 dist 거리 — 돔 안(반지름 0.88, 바닥 위 0.08)에 들어올 때까지 줄인다 */
function placeFromEye(yaw, el, dist) {
  const dir = [Math.sin(yaw) * Math.cos(el), Math.sin(el), Math.cos(yaw) * Math.cos(el)];
  for (let k = 0; k < 20; k++, dist *= 0.9) {
    const p = [EYE[0] + dir[0] * dist, EYE[1] + dir[1] * dist, EYE[2] + dir[2] * dist];
    if (len3(p) < 0.88 && p[1] > 0.08) return p;
  }
  return [EYE[0] + dir[0] * 0.3, Math.max(0.1, EYE[1] + dir[1] * 0.3), EYE[2] + dir[2] * 0.3];
}

// 물리 상수(세계 단위 = 돔 반지름 1, 초)
const WANDER = 0.012, WANDER_PULL = 0.35, DRAG_IDLE = 0.6, DRAG_FAST = 1.5, FAST = 0.06;
const R_DOME = 0.9, Y_MIN = 0.06, EYE_GAP = 0.28, PIECE_R = 0.035, BOUNCE = 0.8;

function stepPieces(ps, dt) {
  let moving = false;
  for (const p of ps) {
    // 무작위 표류: 가속도 자체가 천천히 바뀐다(관성 있는 떠다님)
    // (가속도 표준편차 ≈ WANDER → 평소 속도 ≈ 0.02/s, 폰 화면에서 초당 십여 px)
    const sd = WANDER * Math.sqrt(2 * WANDER_PULL * dt) * 3.46;   // 균등 난수(-.5~.5)의 표준편차 1/√12 보정
    for (let i = 0; i < 3; i++) p.a[i] += -p.a[i] * WANDER_PULL * dt + (Math.random() - 0.5) * sd;
    const sp = len3(p.v);
    const f = Math.exp(-(sp > FAST ? DRAG_FAST : DRAG_IDLE) * dt);
    for (let i = 0; i < 3; i++) { p.v[i] = (p.v[i] + p.a[i] * dt) * f; p.x[i] += p.v[i] * dt; }
    p.w *= Math.exp(-1.2 * dt);
    p.th += (p.w + p.spin) * dt;
    // 돔 벽
    const r = len3(p.x);
    if (r > R_DOME) {
      const n = p.x.map((c) => c / r), vn = dot3(p.v, n);
      for (let i = 0; i < 3; i++) p.x[i] = n[i] * R_DOME;
      if (vn > 0) { for (let i = 0; i < 3; i++) p.v[i] -= (1 + BOUNCE) * vn * n[i]; p.w += rnd(-3, 3) * Math.min(1, vn * 3); }
    }
    // 바닥
    if (p.x[1] < Y_MIN) { p.x[1] = Y_MIN; if (p.v[1] < 0) { p.w += rnd(-3, 3) * Math.min(1, -p.v[1] * 3); p.v[1] = -p.v[1] * BOUNCE; } }
    // 눈 앞을 가리지 않게
    const e = sub(p.x, EYE), de = len3(e);
    if (de < EYE_GAP && de > 1e-6) {
      const n = e.map((c) => c / de), vn = dot3(p.v, n);
      for (let i = 0; i < 3; i++) p.x[i] = EYE[i] + n[i] * EYE_GAP;
      if (vn < 0) for (let i = 0; i < 3; i++) p.v[i] -= (1 + BOUNCE) * vn * n[i];
    }
    if (len3(p.v) > FAST) moving = true;
  }
  // 조각끼리 부딪힘
  for (let i = 0; i < ps.length; i++) for (let j = i + 1; j < ps.length; j++) {
    const a = ps[i], b = ps[j], dv = sub(b.x, a.x), dd = len3(dv), min = 2 * PIECE_R;
    if (dd >= min || dd < 1e-6) continue;
    const n = dv.map((c) => c / dd), push = (min - dd) / 2;
    for (let k = 0; k < 3; k++) { a.x[k] -= n[k] * push; b.x[k] += n[k] * push; }
    const vn = dot3(sub(b.v, a.v), n);
    if (vn < 0) {
      const jn = -(1 + BOUNCE) * vn / 2;
      for (let k = 0; k < 3; k++) { a.v[k] -= jn * n[k]; b.v[k] += jn * n[k]; }
      const spin = Math.min(4, Math.abs(vn) * 30);
      a.w += rnd(-spin, spin); b.w += rnd(-spin, spin);
    }
  }
  return moving;
}

function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "shader");
  return s;
}

/** WebGL2 돔 장면. 못 만들면 null(부르는 쪽이 SVG 장면으로 대신한다). */
export function createDomeGL(host, isPaused) {
  const canvas = document.createElement("canvas");
  canvas.className = "bgdm-gl";
  const gl = canvas.getContext("webgl2", { alpha: false, antialias: false, depth: false, stencil: false, premultipliedAlpha: false, powerPreference: "low-power" });
  if (!gl) return null;

  let prog = null, U = {}, texSky = null, texCloud = null, texReady = 0;
  let W = 0, H = 0, dpr = 1, focal = 1, cx = 0, cy = 0, phone = true;
  let yaw = 0, pitch = BASE_PITCH, gain = GAIN_IDLE, drawnYaw = NaN, drawnPitch = NaN, lastGL = 0, lastFrame = 0, tPrev = 0;
  let raf = 0, stopped = true, settling = false, lastShake = 0, theme = null, t0 = performance.now();
  try { init(); } catch (err) { console.warn("[bgdome] WebGL 초기화 실패 — SVG 로 그린다", err); return null; }

  const air = document.createElement("div");
  air.className = "bgdm-air";
  const defs = GRADS.map((g, i) => `<linearGradient id="bgdm-pg${i}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${g[0]}"/><stop offset="1" stop-color="${g[1]}"/></linearGradient>`).join("");
  air.innerHTML = `<svg style="position:absolute;width:0;height:0" aria-hidden="true"><defs>${defs}</defs></svg>`;   // 고정 문자열(데이터 아님)
  host.appendChild(canvas);
  host.appendChild(air);

  // 조각 배치 — 처음 보는 정면에 몇 개는 꼭 보이게
  const pieces = Array.from({ length: N_PIECES }, (_, i) => {
    const front = i < 7;
    const x = placeFromEye(front ? rnd(-0.45, 0.45) : rnd(-Math.PI, Math.PI), rnd(front ? 0.12 : 0.05, front ? 1.0 : 1.2), rnd(0.4, 0.9));
    const kind = KINDS[i % KINDS.length];
    const el = document.createElementNS(NS, "svg");
    el.setAttribute("viewBox", `${-BOX / 2} ${-BOX / 2} ${BOX} ${BOX}`);
    el.setAttribute("class", "bgdm-air__piece");
    el.innerHTML = SHAPES[kind](`bgdm-pg${i % GRADS.length}`);   // 고정 문자열(데이터 아님)
    air.appendChild(el);
    return { x, v: [0, 0, 0], a: [0, 0, 0], th: rnd(0, Math.PI * 2), w: 0, spin: rnd(-0.25, 0.25), size: rnd(0.8, 1.25), el, shown: true };
  });


  function init() {
    prog = gl.createProgram();
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VS));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FS));
    gl.bindAttribLocation(prog, 0, "aPos");
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) || "link");
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    const n = gl.getProgramParameter(prog, gl.ACTIVE_UNIFORMS);
    U = {};
    for (let i = 0; i < n; i++) { const name = gl.getActiveUniform(prog, i).name; U[name] = gl.getUniformLocation(prog, name); }
    gl.uniform1i(U.uSky, 0);
    gl.uniform1i(U.uCloud, 1);
    texReady = 0;
    texSky = loadTex(0, "../assets/bg/dome-sky.webp");
    texCloud = loadTex(1, "../assets/bg/dome-clouds.webp");
    theme = null;
  }

  function loadTex(unit, rel) {
    const tex = gl.createTexture();
    const img = new Image();
    img.decoding = "async";
    img.onload = () => {
      if (gl.isContextLost()) return;
      gl.activeTexture(gl.TEXTURE0 + unit);
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
      gl.generateMipmap(gl.TEXTURE_2D);   // 천정 평균색(가장 작은 단계)용. 본 샘플은 0단계만 써서 경도 이음매에 줄이 안 생긴다
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      const err = gl.getError();
      if (err || DEBUG) console.warn(`[bgdome] 구름 이미지 ${rel} ${img.naturalWidth}x${img.naturalHeight} glError=${err} max=${gl.getParameter(gl.MAX_TEXTURE_SIZE)}`);
      if (++texReady === 2) { gl.uniform1f(U.uTex, 1); draw(); if (DEBUG) console.warn(`[bgdome] 구름 준비 끝 glError=${gl.getError()}`); }
    };
    img.onerror = () => console.warn(`[bgdome] 구름 이미지를 못 받음 ${rel}`);
    img.src = new URL(rel, import.meta.url).href;
    return tex;
  }

  function applyTheme() {
    const name = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    if (name === theme) return;
    theme = name;
    const t = THEMES[name];
    const m3 = (M) => new Float32Array([M[0][0], M[1][0], M[2][0], M[0][1], M[1][1], M[2][1], M[0][2], M[1][2], M[2][2]]);   // 열 우선
    gl.uniformMatrix3fv(U.uSkyM, false, m3(t.skyM)); gl.uniform3fv(U.uSkyO, t.skyO);
    gl.uniformMatrix3fv(U.uCldM, false, m3(t.cldM)); gl.uniform3fv(U.uCldO, t.cldO); gl.uniform1f(U.uCldA, 0.5);
    gl.uniform3fv(U.uSkyBase, t.skyBase); gl.uniform1f(U.uGridA, t.gridA); gl.uniform1f(U.uReflA, t.reflA);
    for (const k of ["floorIn", "floorOut", "pad", "glow", "rim"]) gl.uniform3fv(U["u" + k[0].toUpperCase() + k.slice(1)], t[k]);
    gl.uniform1f(U.uFloorRefl, t.floorRefl); gl.uniform1f(U.uLightK, t.lightK);
    lastGL = 0;
  }

  function basis() {
    const cy_ = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    return { fwd: [sy * cp, sp, cy_ * cp], right: [cy_, 0, -sy], up: [-sy * sp, cp, -cy_ * sp] };
  }

  function draw() {
    if (gl.isContextLost() || !W) return;
    applyTheme();
    const B = basis();
    gl.uniform3fv(U.uFwd, B.fwd); gl.uniform3fv(U.uRight, B.right); gl.uniform3fv(U.uUp, B.up);
    gl.uniform1f(U.uTime, (performance.now() - t0) / 1000);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    drawnYaw = yaw; drawnPitch = pitch; lastGL = performance.now();
  }

  function placePieces() {
    const B = basis(), base = phone ? 0.075 : 0.045;
    for (const p of pieces) {
      const q = sub(p.x, EYE), z = dot3(q, B.fwd);
      let show = z > 0.05;
      let sx = 0, sy = 0, s = 0;
      if (show) {
        sx = cx + focal * dot3(q, B.right) / z;
        sy = cy - focal * dot3(q, B.up) / z;
        s = focal * base * p.size / z / BOX;
        const m = BOX * s;
        show = sx > -m && sx < W + m && sy > -m && sy < H + m;
      }
      if (show !== p.shown) { p.el.style.visibility = show ? "" : "hidden"; p.shown = show; }
      if (show) p.el.style.transform = `translate3d(${(sx - BOX / 2).toFixed(1)}px,${(sy - BOX / 2).toFixed(1)}px,0) scale(${s.toFixed(3)}) rotate(${(p.th / DEG).toFixed(1)}deg)`;
    }
  }

  function updateView(dt, now) {
    const peek = document.documentElement.classList.contains("bg-peek");
    gain += ((peek ? GAIN_PEEK : GAIN_IDLE) - gain) * (1 - Math.exp(-dt / 0.35));
    if (settling) rebase();   // 섞이는 동안은 매번 지금 자세를 정면으로 → 화면이 천천히 정면으로 돌아온다
    const g = gyroView();
    const tYaw = g ? g.yaw * gain : 0;
    const tPitch = Math.max(PITCH_MIN, Math.min(PITCH_MAX, BASE_PITCH + (g ? g.pitch * gain : 0)));
    const k = 1 - Math.exp(-dt / (settling ? 0.55 : 0.08));
    yaw += (tYaw - yaw) * k;
    pitch += (tPitch - pitch) * k;
    return peek;
  }

  function frame(t) {
    raf = 0;
    if (stopped) return;
    const peek = document.documentElement.classList.contains("bg-peek");
    if (t - lastFrame < 1000 / (peek ? 60 : 30) - 2) { raf = requestAnimationFrame(frame); return; }
    lastFrame = t;
    const dt = Math.min(0.05, (t - tPrev) / 1000 || 0.016);
    tPrev = t;
    updateView(dt, t);
    const moving = stepPieces(pieces, dt);
    if (settling && !moving && t - lastShake > 400) settling = false;   // 다 가라앉았다 — 이 자세가 새 기준으로 남는다
    placePieces();
    if (Math.abs(yaw - drawnYaw) + Math.abs(pitch - drawnPitch) > 2e-4 || t - lastGL > CLOUD_MS) draw();
    raf = requestAnimationFrame(frame);
  }

  function start() {
    if (!stopped) return;
    stopped = false;
    startGyro();
    tPrev = lastFrame = performance.now();
    raf = requestAnimationFrame(frame);
  }
  function stop() { stopped = true; cancelAnimationFrame(raf); raf = 0; }

  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); stop(); });
  canvas.addEventListener("webglcontextrestored", () => {
    try { init(); resize(window.innerWidth, window.innerHeight); if (!isPaused()) start(); } catch { /* 복구 실패 — 마지막 화면 없이 바탕색만 */ }
  });
  new MutationObserver(() => draw()).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  function resize(w, h) {
    W = w; H = h; phone = W <= 767;
    dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    // 기존 SVG 투영(bgdome.js domeGeometry)과 같은 초점 · 중심 — 정면에서 보면 테두리가 같은 자리
    focal = phone ? W * 1.25 : W * 0.76;
    const c = Math.cos(BASE_PITCH), s = Math.sin(BASE_PITCH), eyeY = EYE[1], eyeZ = EYE[2];
    const rimY = H - (phone ? 68 : 130);
    cx = W / 2;
    cy = rimY - focal * (eyeY * c + (1 - eyeZ) * s) / (-eyeY * s + (1 - eyeZ) * c);
    gl.uniform2f(U.uRes, canvas.width, canvas.height); gl.uniform1f(U.uDpr, dpr);
    gl.uniform2f(U.uC, cx, cy); gl.uniform1f(U.uF, focal);
    draw();
    placePieces();
  }

  /** 흔들기 — 조각마다 제각각 튀어 나가고, 다 가라앉을 때까지 보는 방향을 새 정면으로 옮긴다 */
  function shake(power = 1) {
    if (stopped) return;
    lastShake = performance.now();
    settling = true;
    for (const p of pieces) {
      const u = randUnit(), sp = rnd(0.35, 0.95) * power;
      for (let i = 0; i < 3; i++) p.v[i] += u[i] * sp;
      const v = len3(p.v);
      if (v > 1.6) for (let i = 0; i < 3; i++) p.v[i] *= 1.6 / v;
      p.w += rnd(-6, 6) * power;
    }
  }

  // 확인용(?bgdebug) — 콘솔에서 보는 방향 · 섞임 상태를 읽는다
  if (new URLSearchParams(window.location.search).has("bgdebug")) {
    window.__bgdome = { get state() { return { yaw: yaw / DEG, pitch: pitch / DEG, gain, settling, stopped, gyro: gyroView(), speed: Math.max(...pieces.map((p) => len3(p.v))) }; } };
  }

  return {
    resize,
    shake,
    setPaused(stop_) { if (stop_) stop(); else start(); },
    destroy() { stop(); canvas.remove(); air.remove(); },
  };
}
