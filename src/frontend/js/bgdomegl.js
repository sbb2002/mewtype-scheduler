// bgdomegl.js — (bg-dome, 기본 배경 — 옛 배경은 ?bg=classic) UFO 돔 실내를 WebGL2 한 장으로 그린다. 폰을 돌리면(bggyro.js) 보는 방향이 따라 돈다.
//
// 그리는 것(셰이더 = 픽셀마다 「그 방향으로 무엇이 보이나」를 계산):
//   · 돔 유리 — 구면 격자(위도 18 · 40 · 62°, 경도 30° 간격, 경도선은 천정까지). 선 굵기는 화면 픽셀 기준이라 각도가 바뀌어도 같다.
//   · 하늘 — 기존 구름 사진 두 장(가로로 이음매 없이 반복되는 이미지)을 한 바퀴에 3번 감는다. 천정 쪽은 하늘 평균색으로 녹인다.
//   · 바닥 — 남보라 반광택 공연 무대, 오각형 매립 조명 5개와 따뜻한 빛기둥. 밝게 테마도 어두운 재질에 주변광만 더 받는다.
// 공중 무늬(고리 · 별 · 지그재그 · 점 · 물결 · 반짝이)는 SVG 조각을 3D 위치에서 화면으로 투영해 transform 만 바꾼다(합성만 일어나 싸다).
// 평소엔 천천히 떠다니고(관성 있는 무작위 표류), 흔들면 튀어 나가 벽 · 바닥 · 서로에 부딪히며 섞인다. 다 가라앉으면 그때 폰 자세를 새 정면으로 삼는다.
//
// 비용: 카메라가 안 움직이면 구름 흐름만 초당 6번 다시 그린다. 화면 갱신은 평소 30fps · 레인을 걷은 「배경 보기」(html.bg-peek) 중 60fps.
// 시선은 실내 · 바깥 모두 폰이 실제로 향한 방향 그대로(updateView). 해상도는 기기 배율 1.5 까지만.

import { gyroView, startAbsolute, gyroAbs, gyroDebug, gyroTilt } from "./bggyro.js";
import { BGVIEW_EVENT, BGINDOOR_EVENT, indoorBg, setIndoorBg, setBgView, chooseBgView } from "./bgview.js";
import { outdoorSite } from "./bgsite.js";
import { sunPosition, moonPosition, moonIllumination, dirOf, horizonToEquatorial, refraction } from "./bgastro.js";

import { groundWorld, createGroundTextures, groundShader } from "./bgground.js";
import { createConsole } from "./bgconsole.js";
import { createUfoPanel } from "./bgpanel.js";

const DEG = Math.PI / 180;
// 돔(반지름 1) 안 눈 위치 [동, 위, 북] — bgdome.js 와 같다. 수평은 돔 중심(0, 0), 높이 0.24(11-04 운영자 결정 — 전엔 남쪽 0.42 에 있어
// 머리 위를 봐도 돔 꼭대기가 북쪽 29° 에 보였고 동 · 서 경도선이 23° 씩 북쪽으로 쏠렸다). 수평이 중심이면 경도선 = 실제 방위선, 돔 꼭대기 = 천정.
const EYE0 = [0, 0.24, 0];
// 줌(11-04 운영자 요청): 「배경 보기」(html.bg-peek) 중 두 손가락으로 오므리면 보는 방향의 반대쪽으로 r 만큼 물러서고(넓게), 벌리면 r 이 줄어 중심으로 돌아온다(크게).
// 눈 = EYE0 − r · (보는 방향의 수평 성분), 높이는 그대로. r 은 0 ~ ZOOM_R_MAX(돔 반지름 1). 새로고침하면 0(중심).
// Signed pinch path: 0..0.6 = retreat; -1..0 = logarithmic 30x..1x telephoto.
const ZOOM_R_MAX = 0.6;
const ZOOM_PER_SCREEN = 1.5;   // 두 손가락 거리가 화면 폭만큼 줄면 r 이 이만큼 는다
// (11-06 운영자 「제안대로」) UFO 조작 패널 — 배경 보기는 뒤로 물러난 자리에서 시작하고, 가운데 콘솔로 다가가면 패널이 뜬다.
// 문턱은 히스테리시스(나타남 · 사라짐 값이 다름), 망원(×1 초과)이면 숨김. 값은 폰에서 만져 보고 조정.
// 11-06 운영자 「인식 범위가 너무 좁다 — 2배로」: 0.12 · 0.18 → 0.24 · 0.36(시작 0.4 보다 안쪽이라 열자마자 뜨지는 않는다).
const PEEK_START_R = 0.4, PANEL_ON_R = 0.24, PANEL_OFF_R = 0.36;
const EYE = EYE0.slice();      // 지금 눈 위치 — 프레임마다 갱신
const BASE_PITCH = 28 * DEG;
const PITCH_MIN = -55 * DEG, PITCH_MAX = 88 * DEG;
const CLOUD_MS = 160;                  // 카메라가 멈춰 있을 때 구름 흐름 다시 그리기 간격
const MAX_DPR = 1.5;
const QS = new URLSearchParams(window.location.search);
const DEBUG = QS.has("bgdebug");
const GROUND = groundWorld(QS, DEBUG);
// 확인용(?bgdebug 와 함께): bgtime = 시작 시각(ISO), bgspeed = 시간 배속 — 노을 · 밤을 기다리지 않고 본다
// ?bg=normal(운영자 명명) = 가속 없이 지금 시각 — 이 두 값을 주소에 같이 붙여도 무시한다
const NORMAL = QS.get("bg") === "normal";
const T_START = DEBUG && !NORMAL && QS.get("bgtime") ? Date.parse(QS.get("bgtime")) : NaN;
// bgspeed = 0 이면 bgtime 시각에 멈춘다(장면 고정 확인용)
// (11-05) 방문마다 구름 배치 무작위(저장 안 함). ?bgdebug&bgcloudseed=0 이면 예전 그대로, 정수면 고정 배치(캡처 비교용).
const CLOUD_SEED = (() => {
  const q = DEBUG ? QS.get("bgcloudseed") : null;
  if (q === "0") return [0, 0, 0];
  let s = q != null && /^\d+$/.test(q) ? Number(q) >>> 0 : (crypto.getRandomValues(new Uint32Array(1))[0] || 1);
  const r = () => { s = Math.imul(s ^ (s >>> 15), 0x2c1b3c6d) >>> 0; s ^= s >>> 12; return (s >>> 0) / 4294967296; };
  return [r(), r(), 0.35 + 0.45 * r()];
})();
// (11-05 운영자) 실내 배경 무작위 — 분홍 구름이 기본(이 사이트의 얼굴), 가끔 「우주」(성간 이동 1분 뒤 일반 우주).
// 방문마다 뽑는다(저장 안 함). ?bgdebug&bgindoor=pink|space 로 고정, bgwarp=<초> 로 워프 진행 시점 고정(캡처용).
// (11-06 운영자) 방문마다 무작위는 없앴다 — UFO 조작 패널에서 고른 값을 기기에 기억(bgview.js indoorBg), 처음은 분홍. 디버그 bgindoor 가 우선.
let INDOOR_BG = (() => { const q = DEBUG ? QS.get("bgindoor") : null; return q === "space" || q === "pink" ? q : indoorBg(); })();
const WARP_FIXED = DEBUG && QS.get("bgwarp") != null && Number.isFinite(Number(QS.get("bgwarp"))) ? Number(QS.get("bgwarp")) : null;
// (11-05 3차 운영자) 항해 시나리오 — 우주 배경이 뽑히면 일반 우주 · 성간 이동 중 하나로 시작(반반).
//   일반 우주로 시작: 20% 「출발」 = 20초 머문 뒤 1분에 걸쳐 0 → 0.99c 가속(그 뒤 0.99c 유지), 80% = 계속 정지.
//   성간 이동으로 시작: 20% 「도착」 = 0.99c 로 20초 뒤 1분에 걸쳐 0.99c → 0 감속(그 뒤 정지), 80% 「등속」 = 0.7c.
// ?bgdebug&bgvoyage=rest|depart|cruise|arrive 로 고정, bgwarp=<초> 로 진행 시점 고정.
const VOYAGE = (() => {
  const q = DEBUG ? QS.get("bgvoyage") : null;
  if (["rest", "depart", "cruise", "arrive"].includes(q)) return q;
  // (11-06 운영자) 무작위 항해 시나리오는 없앤다 — 평소 우주는 정지. 성간 이동(10% · 길게 누르기 · 워프 기어)은 조작 패널 3단계에서.
  return "rest";
})();
function voyageBeta(sec) {
  const ss = (x) => { const v = Math.min(1, Math.max(0, x)); return v * v * (3 - 2 * v); };
  if (VOYAGE === "rest") return 0;
  if (VOYAGE === "cruise") return 0.7;
  if (VOYAGE === "depart") return 0.99 * ss((sec - 20) / 60);
  return 0.99 * (1 - ss((sec - 20) / 60));   // arrive
}
const VOYAGE_END = VOYAGE === "depart" || VOYAGE === "arrive" ? 83 : 0;   // 이 뒤로는 속도가 그대로
// (11-05 2차, 비교용) 우주 바탕: map = NASA SVS Deep Star Maps 2020(가) · eso = ESO/S. Brunier 은하수 파노라마(대안) · shader = 그려 만든 우주(나).
// 딥필드 = 웹 망원경 SMACS 0723(NASA, ESA, CSA, STScI). 평가용 이미지는 assets/bg/eval/(저장소에 올리지 않음). ?bgdebug&bgspace=map|eso|shader&bgdeep=0|1
// (11-05 운영자) 가 · 나 · 대안 모두 쓴다 — 방문마다 셋 중 하나(같은 확률).
const SPACE_MODE = (() => { const q = DEBUG ? QS.get("bgspace") : null; return ["map", "eso", "shader"].includes(q) ? q : ["map", "eso", "shader"][Math.floor(Math.random() * 3)]; })();
const SPACE_DEEP = !(DEBUG && QS.get("bgdeep") === "0");   // 워프 60초, 마지막 10초 감속하며 일반 우주로
const T_SPEED = (() => { const v = DEBUG && !NORMAL && QS.get("bgspeed") != null ? Number(QS.get("bgspeed")) : NaN; return Number.isFinite(v) && v >= 0 ? v : 1; })();
// 확인용(?bgdebug 와 함께): bgmoon = 달 위상 0 ~ 1(0 삭 · 0.25 상현 · 0.5 망 · 0.75 하현) — 달을 정남 고도 35° 에 두고 그 위상으로 비춘다(실제 해 위치는 그대로)
// 달 기본 = CSS reference pixel 기준 육안 크기 × 배율(11-05). 해는 기존 투영 그대로.
// 확인용(?bgdebug 와 함께): bgsize = 옛 크기 비교 — now(옛 기본: 지름 해 2.4° · 달 3.2°) | real(실제, 기본) | double(실제의 2배 1.06°)
//   | window(실제 0.53° + 바깥 보기 화면 폭을 폰이 눈에 차지하는 각도 약 12.4° 로 — 폰이 「창문」처럼 실제 하늘과 1:1)
const SIZE_MODE = DEBUG && ["now", "real", "double", "window"].includes(QS.get("bgsize")) ? QS.get("bgsize") : "eye";
// CSS reference pixel: 0.0213 degrees. Optical sun and debug comparisons stay unchanged.
const MOON_CSS_DIAMETER = 0.53 / 0.0213;
const THEME_MS = 840;
const SUN_MOON_R = { eye: [0.2665, 0.265], now: [1.2, 1.6], real: [0.2665, 0.2590], double: [0.533, 0.518], window: [0.2665, 0.2590] }[SIZE_MODE];   // 각반지름(도) [해, 달]
const WINDOW_HFOV = 12.4;   // 도 — 폭 약 6.5cm 화면을 30cm 에서 볼 때(추정값, 기기 · 습관마다 다르다)
const MOON_TEST = DEBUG && QS.get("bgmoon") != null && Number.isFinite(Number(QS.get("bgmoon"))) ? ((Number(QS.get("bgmoon")) % 1) + 1) % 1 : null;
// Debug (bgdebug): bgsunalt/bgmoonalt = apparent degrees; bgsunaz/bgmoonaz = azimuth degrees clockwise from north.
// bgcloud = fixed density 0..1; bglight=disc|bloom|rays|full isolates stages. bgspeed=0 freezes clouds too.
const debugNumber = (key) => DEBUG && !NORMAL && QS.has(key) && Number.isFinite(Number(QS.get(key))) ? Number(QS.get(key)) : null;
const AIR = { pressure: 1, aerosol: 0.05, alpha: 1.3 }; // Design atmosphere, not measured weather.
const EXPOSURE = { sun: 40, moon: 1 }; // Separate from optical depth.
const airMass = (h) => { h = Math.max(0, Math.min(90, h)); return 1 / (Math.sin(h * DEG) + 0.50572 * Math.pow(h + 6.07995, -1.6364)); };
// Relative linear-light RGB at 60 degrees; preserve attenuation as well as channel ratios.
const transmission = (h) => [650, 550, 450].map(w => Math.exp(-(airMass(h) - airMass(60)) *
  (0.10 * AIR.pressure * Math.pow(550 / w, 4) + AIR.aerosol * Math.pow(550 / w, AIR.alpha))));
// Artistic exposure compensation preserves extinction hue without losing low luminaries.
const exposedHue = (rgb) => rgb.map(v => v / Math.max(...rgb, 1e-6));
const T_REAL0 = Date.now();
const nowMs = () => (Number.isFinite(T_START) ? T_START : T_REAL0) + (Date.now() - T_REAL0) * T_SPEED;

// 바깥 보기 하늘 단계 — 해 고도(도)가 이 값일 때 그 이미지 한 벌. 사이 값은 이웃 두 벌을 섞는다. 노을 한 벌을 해 뜰 때도 같이 쓴다
// 해가 올라가는 중이면 노을(twilight) 자리에 여명(dawn)을 쓴다(2026-11-04 운영자 지시 — 해 뜰 때 · 질 때 색감이 다르다).
// 바깥 보기의 낮 = 실제 낮 하늘(daylight). 분홍 하늘(day)은 실내 보기 전용(2026-11-04 운영자 지시)
const SKY_KEYS = [{ name: "daylight", alt: 12 }, { name: "twilight", alt: 0 }, { name: "bluehour", alt: -6 }, { name: "night", alt: -12 }];
const SKY_FILES = {
  day: ["../assets/bg/dome-sky.webp", "../assets/bg/dome-clouds.webp"],
  daylight: ["../assets/bg/sky-daylight.webp", "../assets/bg/clouds-daylight.webp"],
  twilight: ["../assets/bg/sky-twilight.webp", "../assets/bg/clouds-twilight.webp"],   // 해 질 때
  dawn: ["../assets/bg/sky-dawn.webp", "../assets/bg/clouds-dawn.webp"],               // 해 뜰 때 — 노을보다 맑고 차가운 색
  bluehour: ["../assets/bg/sky-bluehour.webp", "../assets/bg/clouds-bluehour.webp"],
  night: ["../assets/bg/sky-night.webp", "../assets/bg/clouds-night.webp"],
};
const ASTRO_MS = T_SPEED > 1 ? 0 : 1000;   // 해 · 달 위치 다시 계산 간격(실제 속도면 1초 — 해는 1분에 0.25°쯤만 움직인다. 배속 확인 중엔 매 프레임)
// World kind is fixed until navigation. Specialize away the other two materials
// and their texture/BRDF paths instead of carrying uniform branches per pixel.
const GROUND_SHADER = groundShader.replace("uniform float uGroundKind, uGroundAlt,",
  `const float uGroundKind = ${GROUND.index}.0, uGroundAlt = ${GROUND.altitude}.0;\nuniform float`);

const VS = `#version 300 es
precision highp float;
in vec2 aPos;
uniform sampler2D uCloud, uCloud2;
uniform vec3 uSunDir, uMoonDir;
uniform float uTime, uMix, uCloudTest;
flat out vec2 vSourceClear;
// (11-05 운영자) 구름이 항상 같은 무늬 → 방문마다 무작위: 같은 구름 사진을 두 번(한 번은 좌우 뒤집어) 다른 자리 · 속도로 읽어 겹친다.
// uCloudSeed = (첫 겹 자리, 둘째 겹 자리, 둘째 겹 세기). 둘째 겹 세기 0 이면 예전과 같다.
uniform vec3 uCloudSeed;
vec4 cloudAt(sampler2D cl, float u, float v) {
  vec4 a = textureLod(cl, vec2(u + uCloudSeed.x * 3.0 + uTime / 1280.0, v), 0.0);
  if (uCloudSeed.z <= 0.0) return a;
  vec4 b = textureLod(cl, vec2(-u + uCloudSeed.x * 7.0 + uTime / 1730.0, v), 0.0);
  float wb = b.a * uCloudSeed.z, w = a.a + wb;
  return vec4(w > 1e-4 ? (a.rgb * a.a + b.rgb * wb) / w : a.rgb, 1.0 - (1.0 - a.a) * (1.0 - wb));
}
float sourceClear(vec3 dir) {
  if (uCloudTest >= 0.0) return 1.0 - uCloudTest;
  float cu = atan(dir.x, dir.z) / 6.2831853 * 3.0,
    cv = clamp((70.0 * .01745329 - asin(clamp(dir.y,-1.0,1.0))) / (82.0 * .01745329), .002, .998);
  float a = cloudAt(uCloud, cu, cv).a;
  if (uMix > 0.0) a = mix(a, cloudAt(uCloud2, cu, cv).a, uMix);
  return 1.0 - a;
}
void main() {
  gl_Position = vec4(aPos, 0.0, 1.0);
  // Only three vertices sample each source's cloud, independently of the view.
  vSourceClear = vec2(sourceClear(uSunDir), sourceClear(uMoonDir));
}`;

const FS = `#version 300 es
precision highp float;
uniform vec2 uRes; uniform float uDpr; uniform vec2 uC; uniform float uF;
uniform vec3 uFwd, uRight, uUp;
uniform float uTime, uTex;
// 하늘 이미지 두 벌(A · B)을 uMix 로 섞는다 — 실내 = 낮 한 벌. 바깥 보기 = 해 고도에 따라 낮 · 노을 · 박명 · 밤 중 이웃한 두 벌
uniform sampler2D uSky, uCloud, uSky2, uCloud2;
uniform mat3 uSkyM; uniform vec3 uSkyO; uniform mat3 uCldM; uniform vec3 uCldO;
uniform mat3 uSkyM2; uniform vec3 uSkyO2; uniform mat3 uCldM2; uniform vec3 uCldO2;
uniform float uCldA, uMix;
// 바깥 보기: 해 · 달 방향(장면 벡터 [동, 위, 북]), 밤 정도(별), 지평 → 적도 회전(별이 실제처럼 돈다)
uniform float uOut, uNight;
uniform vec3 uSunDir, uMoonDir, uMoonSun;
uniform float uSunR, uMoonR;   // 각반지름(라디안)
uniform sampler2D uMoonTex; uniform float uMoonTexOn; uniform vec2 uMoonRot;   // 달 앞면 사진(NASA LRO) · 받았는지 · 북쪽 기울기(cos, sin)   // uMoonSun = 달을 비추는 해 방향(평소 = uSunDir, 위상 시험 때만 다름)
uniform vec4 uSunShape, uMoonShape;   // 천체 접평면의 위쪽 방향(xyz), 지평선 눌림 세기(w)
// 고도 · 남중 · 위상에 따른 색과 세기는 JS 에서 초당 한 번만 계산한다
uniform vec3 uSunCol, uSunGlow, uSunHorizon, uMoonCol;
uniform vec4 uSunAir;   // 근접 번짐, 구름 산란, 저고도 온기, 원반 노출
uniform vec4 uSolar;   // 낮 산란, 지평 대기광, 해 가시성, 천정의 깊이
uniform vec4 uFlare;
uniform vec3 uSunTrans; uniform vec4 uOptics; uniform float uCloudTest;
uniform vec4 uLunar;   // 달 가시성, 원반 불투명도, 빛 번짐 지수, 빛 번짐 세기
uniform float uMoonLight, uStarGain, uEarthshine;
// (11-05) 달빛 하늘 밝기 — Krisciunas & Schaefer 1991(PASP 103, 1033). uMoonKS.x = I*·10^(−0.4kX(Z달))·(달 떠 있음)/B어두운하늘(59.2 nL = 21.9 mag/arcsec²),
// .y = V 소광 계수 k. 픽셀마다 산란 f(ρ) · 시선 공기질량을 곱하면 「어두운 하늘 대비 달빛」 배율 − 1. 조사 · 계획 = devpapers ref/bg-dome/moonlight_plan.md.
uniform vec2 uMoonKS;
float moonSkyGain(vec3 d) {   // = B달 / B어두운하늘
  if (uMoonKS.x <= 0.0) return 0.0;
  float rho = max(degrees(acos(clamp(dot(d, uMoonDir), -1.0, 1.0))), 10.0);   // 10° 안은 모형 범위 밖 — 원반 · 광륜이 맡는다
  float cr = cos(radians(rho));
  float f = 229086.8 * (1.06 + cr * cr) + pow(10.0, 6.15 - rho / 40.0);
  float cz = max(d.y, 0.02), X = inversesqrt(1.0 - 0.96 * (1.0 - cz * cz));
  return f * uMoonKS.x * (1.0 - pow(10.0, -0.4 * uMoonKS.y * X));
}
uniform vec2 uTele; // background exposure, solar exposure
// (11-05) 확대 시 주변이 어두워지는 실제 광학 — 가상 쌍안경 · 망원경(구경 70mm)의 사출동 = 구경 / 배율.
// 사출동이 눈동자보다 작아지면 넓게 퍼진 대상(하늘 · 땅)의 표면 밝기 = (사출동 / 눈동자)², 별(점광원)은 밝기 유지 · 오히려 더 많이 보인다.
// uPupil.x = 표면 밝기 배율(≤ 1), .y = 별이 더 보이는 등급(2.5 log10 min(배율², (구경/눈동자)²)).
uniform vec2 uPupil;
uniform float uMoonCue;
uniform vec2 uMoonAxis;
uniform vec4 uMoonScreen; // CSS center, radius, screen-size mode (front hemisphere only)
uniform sampler2D uThemeFrame;
uniform float uThemeProgress; // 1 = inactive; no snapshot lookup at rest

flat in vec2 vSourceClear;
uniform mat3 uEqM;
uniform vec3 uSkyBase; uniform float uGridA, uReflA;
uniform vec3 uFloorIn, uFloorOut, uPad, uGlow, uRim;
uniform float uFloorRefl, uLightK;
out vec4 outColor;
const float TAU = 6.2831853, D = 0.01745329;
uniform vec3 E;   // 눈 위치 = EYE(줌으로 움직인다)
float h1(float n) { return fract(sin(n * 127.1) * 43758.5453); }
float h2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float h3(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
// 거리 d(세계 단위)인 선의 덮임 — pw = 픽셀 하나의 세계 크기, halfPx = 선 반폭(기기 픽셀)
float cover(float d, float pw, float halfPx) { return clamp(halfPx - d / pw + 0.5, 0.0, 1.0); }

// 하늘 한 벌: 먼 하늘(불투명) + 가까운 구름(투명) 합성. 이미지 위 끝 위는 하늘 평균색, 아래 끝 아래는 지평선 평균색
// (11-05 운영자) 구름이 항상 같은 무늬 → 방문마다 무작위: 같은 구름 사진을 두 번(한 번은 좌우 뒤집어) 다른 자리 · 속도로 읽어 겹친다.
// uCloudSeed = (첫 겹 자리, 둘째 겹 자리, 둘째 겹 세기). 둘째 겹 세기 0 이면 예전과 같다.
uniform vec3 uCloudSeed;
vec4 cloudAt(sampler2D cl, float u, float v) {
  vec4 a = textureLod(cl, vec2(u + uCloudSeed.x * 3.0 + uTime / 1280.0, v), 0.0);
  if (uCloudSeed.z <= 0.0) return a;
  vec4 b = textureLod(cl, vec2(-u + uCloudSeed.x * 7.0 + uTime / 1730.0, v), 0.0);
  float wb = b.a * uCloudSeed.z, w = a.a + wb;
  return vec4(w > 1e-4 ? (a.rgb * a.a + b.rgb * wb) / w : a.rgb, 1.0 - (1.0 - a.a) * (1.0 - wb));
}
vec4 skySet(sampler2D s, sampler2D cl, mat3 M, vec3 O, mat3 CM, vec3 CO, float u, float v, float el) {
  // 하늘 사진에도 구름 결이 들어 있어 같은 무작위 자리만큼 돌린다(둘째 겹 세기 > 0 일 때만 — 0 이면 예전 그대로).
  vec3 c = clamp(M * textureLod(s, vec2(u + (uCloudSeed.z > 0.0 ? uCloudSeed.y * 3.0 : 0.0) + uTime / 2844.444, v), 0.0).rgb + O, 0.0, 1.0);
  vec4 n = cloudAt(cl, u, v);
  c = mix(c, clamp(CM * n.rgb + CO, 0.0, 1.0), n.a * uCldA);
  vec3 z = clamp(M * textureLod(s, vec2(0.5, 0.03), 7.0).rgb + O, 0.0, 1.0);
  vec3 hz = clamp(M * textureLod(s, vec2(u, 0.97), 6.0).rgb + O, 0.0, 1.0);
  c = mix(c, hz, smoothstep(-2.0 * D, -11.0 * D, el));
  return vec4(mix(c, z, smoothstep(50.0 * D, 84.0 * D, el)), n.a * uCldA);   // a = 가까운 구름이 가린 정도(별 · 달을 가린다)
}

// 눌린 접평면 좌표를 원래 원반으로 되돌린다. 아래쪽은 조금 더 들고, 중심과 가로 지름은 유지한다.
vec3 discTangent(vec3 d, vec3 center, vec4 shape, float radius) {
  vec3 t = d - center * dot(d, center);
  float y = dot(t, shape.xyz);
  float scale = 1.0 - 0.175 * shape.w + 0.04 * shape.w * clamp(y / radius, -1.0, 1.0);
  return t + shape.xyz * (y / scale - y);
}
// Gaussian sigma in radians, using chord squared (stable near a tiny disc).
float angularBloom(float facing, float sigma) {
  return exp(-max(2.0 * (1.0 - facing), 0.0) / (2.0 * sigma * sigma));
}
float cloudAtSun() {
  return 1.0 - vSourceClear.x;
}
${GROUND_SHADER}

// Lens layer after foreground, before HUD/dither. Occlusion is sampled at the source.
vec3 solarOptics(vec3 col, vec2 p) {
  if (uFlare.z <= 0.0 || uOptics.w < 0.5) return col;
  vec2 source = uFlare.xy, offset = source - uC;
  float clear = 1.0 - cloudAtSun();
  float gain = uFlare.z * clear * clear * uGroundSourceVisibility.x;
  float view = uFlare.w;
  vec2 v = (p - source) / uF;
  float rho = length(v), pixel = 1.0 / (uF * uDpr);
  float rays = 0.0;
  if (rho > 0.45 * D && rho < 18.0 * D) {
    float phi = atan(v.y, v.x);
    // cos(8 phi) has eight positive lobes; fixed phase, no temporal noise.
    float exponent = min(3.0, pow(rho / (4.0 * pixel), 2.0));
    float lobe = pow(max(0.0, cos(8.0 * (phi - 0.13))), exponent);
    rays = lobe * exp(-pow(rho / (uOptics.y * D), 2.0)) * smoothstep(0.45 * D, 0.9 * D, rho);
  }
  vec3 light = uSunTrans * (rays * uOptics.z * view);
  if (uOptics.w > 1.5) {
    light += uSunTrans * (0.025 * exp(-pow(rho / (6.0 * D), 2.0)) * view);
    float separation = smoothstep(0.0, 5.0 * D, length(offset) / uF);
    for (int j = 0; j < 3; j++) {
      float k = j == 0 ? -0.25 : (j == 1 ? -0.65 : -1.1);
      float radius = (j == 0 ? 0.65 : (j == 1 ? 1.0 : 1.5)) * D;
      vec2 g = (p - uC - k * offset) / uF;
      float r2 = dot(g, g) / (radius * radius);
      if (r2 > 18.0) continue;
      float ghost = exp(-0.5 * r2);
      vec3 tint = j == 0 ? vec3(0.55, 0.8, 0.45) : (j == 1 ? vec3(0.35, 0.65, 0.85) : vec3(0.65, 0.8, 0.4));
      light += tint * uSunTrans * ghost * 0.025 * separation;
    }
  }
  return (col + light * gain) / (1.0 + max(light.r, max(light.g, light.b)) * gain);
}

// Screen-size moon keeps its astronomical center; only its disc footprint is distorted.
vec3 moonTangent(vec3 d, vec2 p) {
  if (uMoonScreen.w < .5) return discTangent(d, uMoonDir, uMoonShape, uMoonR);
  vec2 k = (p - uMoonScreen.xy) * vec2(1,-1) / max(uMoonScreen.z, .001);
  vec3 up = uMoonShape.xyz, right = cross(up,uMoonDir);
  vec2 axis = uMoonAxis;
  vec2 sp = vec2(dot(k,axis),dot(k,vec2(-axis.y,axis.x)));
  float scale = 1.0 - .175 * uMoonShape.w + .04 * uMoonShape.w * clamp(sp.y,-1.0,1.0);
  return uMoonR * (right * sp.x + up * sp.y / scale);
}
// 달: 각반지름 uMoonR. 복원한 구면에서 해 방향을 써 위상 · 표면도 함께 눌린다.
// 표면 = NASA LRO 컬러 지도로 만든 앞면 사진(assets/bg/moon-near.webp, 북쪽 위). 달의 북쪽은 하늘의 북극 쪽으로 기울인다(시각각).
vec4 moon(vec3 t, float facing, float pxAng) {
  float R = uMoonR;
  float rr = length(t) / R;
  float a = clamp((1.0 - rr) * R / pxAng + 0.5, 0.0, 1.0) * step(0.0, facing);
  if (a <= 0.0) return vec4(0.0);
  vec3 k = t / R;
  vec3 n = k - uMoonDir * sqrt(max(1.0 - dot(k, k), 0.0));   // 보이는 반구의 표면 법선(관측자 쪽)
  // 명암 경계: 실제 달처럼 부드럽게(경계 폭 약 ±8°) — 밝은 면이 하늘색으로 서서히 사라진다
  float ns = dot(n, uMoonSun);
  float lit = smoothstep(-0.10, 0.16, ns) * (0.55 + 0.45 * smoothstep(0.0, 0.5, ns));
  vec3 up = uMoonShape.xyz, right = cross(up, uMoonDir);
  vec2 sp = vec2(dot(k, right), dot(k, up));
  vec2 lu = vec2(sp.x * uMoonRot.x - sp.y * uMoonRot.y, sp.x * uMoonRot.y + sp.y * uMoonRot.x);   // 화면 → 달 좌표(북쪽 위)
  float alb = uMoonTexOn > 0.5 ? texture(uMoonTex, vec2(0.5 + 0.5 * lu.x, 0.5 - 0.5 * lu.y)).r / 0.4875 : 1.0;   // 평균 1 로 맞춤
  float limb = 0.82 + 0.18 * sqrt(max(1.0 - rr * rr, 0.0));
  vec3 col = uMoonCol * mix(1.0, alb, 0.85) * limb;
  return vec4(col, a * lit);   // a = 밝은 면만. 어두운 면은 sky() 가 하늘색을 살짝 어둡게(지구 반사광) 한다
}
float moonDisc(vec3 t, float facing, float pxAng) {
  float R = uMoonR;
  float rr = length(t) / R;
  return clamp((1.0 - rr) * R / pxAng + 0.5, 0.0, 1.0) * step(0.0, facing);
}


// (11-05 운영자) 실내 무작위 배경 「우주」 — 성간 이동(워프) 1분 뒤 일반 우주로. 이미지 없이 셰이더만.
// uSpace.x = 우주 배경 켬, .y = 속도 β(v/c), .z = 지나가는 별 스크롤 누적 거리, .w = 지금 스크롤 속도. 진행 방향 uWarpDir = 돔 정면 지평선.
// 색 = 상대론적 도플러: 진행 방향(축 가까이)은 푸르게, 옆은 흰색, 뒤쪽일수록 붉게. 광행차로 별이 앞쪽에 몰린다.
uniform vec4 uSpace; uniform vec3 uWarpDir;
// (11-05 2차) 우주 배경 비교용: uSpaceTex = (하늘 지도 켬, 딥필드 켬, 지도 종류 1 = NASA 별 지도 · 2 = ESO 은하수, 지도 노출).
// 지도는 등장방형(equirect) — 13번 칸, 딥필드 사진 — 14번 칸(실내에서는 지형 확대 조각 칸이 비어 있다).
uniform sampler2D uSpaceMap, uSpaceDeep; uniform vec4 uSpaceTex; uniform vec2 uSpaceMapSize;
float vnoise(vec3 p) {
  vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(h3(i), h3(i + vec3(1,0,0)), f.x), mix(h3(i + vec3(0,1,0)), h3(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(h3(i + vec3(0,0,1)), h3(i + vec3(1,0,1)), f.x), mix(h3(i + vec3(0,1,1)), h3(i + vec3(1,1,1)), f.x), f.y), f.z);
}
vec3 spaceStars(vec3 d, float pxAng, float gain) {
  vec3 c = vec3(0);
  for (int k = 0; k < 2; k++) {
    float sc = k == 0 ? 60.0 : 140.0;
    vec3 e = d * sc, cell = floor(e);
    float h = h3(cell + float(k) * 19.7);
    if (h > (k == 0 ? 0.93 : 0.965)) {
      vec3 sp = normalize(cell + 0.5 + (vec3(h3(cell + 1.7), h3(cell + 3.1), h3(cell + 5.3)) - 0.5) * 0.6) * sc;
      float mag = (h - 0.93) * 14.0;
      float s = clamp(0.9 - length(e - sp) / (sc * pxAng), 0.0, 1.0) * (0.25 + 0.75 * mag);
      vec3 tint = mix(vec3(1.0, 0.78, 0.6), vec3(0.7, 0.82, 1.0), h3(cell + 9.1));
      c += tint * s * (k == 0 ? 1.4 : 0.8);
    }
  }
  return c * gain;
}
// 몽환적인 은하 무리 — 허블 딥필드처럼 여기저기 작은 은하(타원 · 나선, 주황 핵 · 푸른 팔). 실제 크기와 무관한 연출.
vec3 galaxies(vec3 d, float pxAng) {
  vec3 c = vec3(0);
  for (int k = 0; k < 2; k++) {
    float sc = k == 0 ? 22.0 : 55.0;
    vec3 e = d * sc, cell = floor(e);
    float h = h3(cell + 7.3 + float(k) * 3.1);
    if (h < (k == 0 ? 0.62 : 0.72)) continue;
    vec3 sp = normalize(cell + 0.5 + (vec3(h3(cell + 2.1), h3(cell + 4.7), h3(cell + 6.9)) - 0.5) * 0.5);
    vec3 A = normalize(cross(abs(sp.y) < 0.9 ? vec3(0, 1, 0) : vec3(1, 0, 0), sp)), B = cross(sp, A);
    vec3 q = d - sp * dot(d, sp);
    float rot = h3(cell + 8.8) * TAU, cr = cos(rot), sr = sin(rot);
    vec2 uv = vec2(dot(q, A), dot(q, B)); uv = vec2(cr * uv.x - sr * uv.y, sr * uv.x + cr * uv.y);
    float size = (k == 0 ? 0.0045 : 0.0022) * (0.5 + 1.2 * h3(cell + 1.1)), ell = 0.25 + 0.75 * h3(cell + 5.5);
    uv /= max(size, pxAng * 0.7);
    vec2 w = vec2(uv.x, uv.y / ell);
    float r = length(w);
    if (r > 6.0) continue;
    float core = exp(-r * r * 3.0), halo = exp(-r * 1.3) * 0.45;
    float spiral = h3(cell + 3.3) > 0.45 ? 1.0 : 0.0;
    float arm = spiral * pow(0.5 + 0.5 * sin(2.0 * atan(w.y, w.x) - 3.2 * log(r + 0.05)), 3.0) * exp(-r * 0.9) * 0.9;
    vec3 warm = mix(vec3(1.0, 0.72, 0.45), vec3(1.0, 0.9, 0.75), h3(cell + 9.9));
    vec3 cool = mix(vec3(0.55, 0.7, 1.0), vec3(0.85, 0.6, 1.0), h3(cell + 4.4));
    float bright = (k == 0 ? 0.5 : 0.3) * (0.4 + 0.6 * h);
    c += (warm * core + mix(warm, cool, 0.6) * halo + cool * arm) * bright;
  }
  return c;
}
vec3 nebula(vec3 d) {
  float n = vnoise(d * 2.2) * 0.55 + vnoise(d * 5.1 + 3.0) * 0.3 + vnoise(d * 11.0 + 7.0) * 0.15;
  float m = vnoise(d * 1.7 + 11.0);
  return mix(vec3(0.18, 0.06, 0.28), vec3(0.04, 0.12, 0.26), m) * pow(max(n - 0.42, 0.0) * 2.2, 2.0) * 0.35;
}
vec3 spaceBase(vec3 d, float pxAng) {
  vec3 c = vec3(0.004, 0.005, 0.010);
  if (uSpaceTex.x > 0.5) {
    // 등장방형 지도. 경계선(경도 ±180°)에서 밉맵이 튀지 않게 픽셀 크기로 직접 고른다.
    float lon = atan(d.x, d.z), lat = asin(clamp(d.y, -1.0, 1.0));
    float lod = max(0.0, log2(pxAng * uSpaceMapSize.x / TAU));
    vec3 m = textureLod(uSpaceMap, vec2(0.5 - lon / TAU, 0.5 - lat / 3.14159265), lod).rgb;
    c += pow(m, vec3(2.2)) * uSpaceTex.w;
  } else {
    c += nebula(d) + vec3(0.010, 0.006, 0.016) * pow(max(1.0 - abs(d.y - 0.15), 0.0), 6.0);
  }
  c += spaceStars(d, pxAng, uSpaceTex.x > 0.5 ? 0.6 : 1.0) + galaxies(d, pxAng);
  if (uSpaceTex.y > 0.5) {
    // 딥필드 사진 한 장 — 정면 오른쪽 위에 크게(가로 약 34°), 가장자리는 서서히 녹아든다. 검은 바탕이라 더한다.
    vec3 C = normalize(vec3(0.42, 0.36, 0.83)), A = normalize(cross(vec3(0, 1, 0), C)), B = cross(C, A);
    float cz = dot(d, C);
    if (cz > 0.5) {
      vec2 tp = vec2(dot(d, A), dot(d, B)) / cz;
      float half_ = tan(17.0 * D);
      vec2 uv = 0.5 + tp / (2.0 * half_);
      if (all(greaterThan(uv, vec2(0))) && all(lessThan(uv, vec2(1)))) {
        float lod = max(0.0, log2(pxAng * 1960.0 / (2.0 * half_)));
        vec3 g = pow(textureLod(uSpaceDeep, vec2(uv.x, 1.0 - uv.y), lod).rgb, vec3(2.2));
        vec2 e = min(uv, 1.0 - uv);
        c += g * smoothstep(0.0, 0.18, min(e.x, e.y)) * 0.9;
      }
    }
  }
  return c;
}
// (11-05 3차) 상대론적 성간 이동 — 운영자 시나리오(출발 가속 · 0.7c 등속 · 도착 감속)의 속도 β 로 하늘 전체를 바꾼다.
// 광행차: 정지 좌표계 방향 θ' 의 별이 cosθ = (cosθ' + β)/(1 + β cosθ') 로 앞쪽에 몰린다(픽셀마다 역변환해 정지 좌표계 하늘을 읽음).
// 도플러: D = 1/(γ(1 − β cosθ)) — 앞은 푸르고 밝게, 뒤는 붉고 어둡게. 색은 흑체 온도 T → D·T 로 옮기고, 밝기는 D³(빛 몰림)를 톤 매핑.
// 가까이 지나가는 별의 궤적 = 유노 생일 장면 UFO 궤적처럼 밝은 머리 + 9초에 걸쳐 선형으로 옅어지는 꼬리 + 넓은 번짐.
vec3 bbColor(float T) {   // 흑체 색(Tanner Helland 근사, 1000 ~ 40000K), 최대 성분 1
  float x = clamp(T, 1000.0, 40000.0) / 100.0;
  float r = x <= 66.0 ? 1.0 : clamp(1.29293618606 * pow(x - 60.0, -0.1332047592), 0.0, 1.0);
  float g = x <= 66.0 ? clamp(0.39008157876 * log(x) - 0.63184144378, 0.0, 1.0) : clamp(1.12989086089 * pow(x - 60.0, -0.0755148492), 0.0, 1.0);
  float b = x >= 66.0 ? 1.0 : (x <= 19.0 ? 0.0 : clamp(0.54320678911 * log(x - 10.0) - 1.19625408914, 0.0, 1.0));
  return vec3(r, g, b) * smoothstep(400.0, 1400.0, T);   // 1000K 아래는 사실상 안 보인다
}
vec3 passingStars(vec3 F, float cr, float ph, float pxRest, float D, float beta, float dist) {
  float s = log(tan(max(acos(cr), 1e-3) * 0.5));
  float lanes = 64.0, fi = (ph / TAU + 0.5) * lanes, lane = floor(fi), fx = fract(fi) - 0.5;
  float hl = h1(lane * 1.37 + 3.0);
  if (hl < 0.68) return vec3(0);   // 궤적은 적게(약 20줄)
  float speed = 0.8 + 0.8 * h1(lane * 7.1);                    // 별마다 거리가 달라 지나가는 빠르기가 다르다
  float P = 12.0, head = mod(dist * speed + hl * 97.0, P) - 6.0; // 머리 위치(로그 극좌표 s), 앞(−)에서 뒤(+)로
  float behind = mod(head - s + P, P);                           // 머리에서 꼬리 쪽으로 떨어진 거리
  float age = behind / max(uSpace.w * speed, 1e-3);              // uSpace.w = 지금 s 스크롤 속도(1/초)
  float k = 1.0 - age / 9.0;                                     // UFO 궤적과 같은 9초 선형 감쇠
  if (k <= 0.0) return vec3(0);
  float lw = max(pxRest / max(sqrt(max(1.0 - cr * cr, 1e-6)) * TAU / lanes, 1e-4), 0.025);
  float core = exp(-fx * fx / (lw * lw)), glow = exp(-fx * fx / (14.0 * lw * lw)) * 0.3;
  float headDot = exp(-behind * behind / 0.002) * 1.5;
  float T = 5200.0 + 6000.0 * h1(lane * 3.3);
  // 궤적 밝기는 D^1.5 로만 — 앞쪽이 하얗게 포화되지 않고 도플러 색(앞 파랑 · 뒤 빨강)이 남게. 축 바로 앞은 옅게(바퀴살처럼 모이지 않게).
  return bbColor(T * D) * (k * k * (core + glow) + headDot * core) * min(pow(D, 1.5), 12.0) * 0.5 * smoothstep(0.03, 0.2, beta) * smoothstep(0.995, 0.93, cr);
}
vec3 spaceSky(vec3 d, float pxAng) {
  float beta = uSpace.y;
  if (beta < 1e-4) return spaceBase(d, pxAng);
  vec3 F = uWarpDir, A = normalize(cross(abs(F.y) < 0.9 ? vec3(0, 1, 0) : vec3(1, 0, 0), F)), B = cross(F, A);
  float g = inversesqrt(1.0 - beta * beta);
  float co = clamp(dot(d, F), -1.0, 1.0);
  float cr = (co - beta) / (1.0 - beta * co);                     // 정지 좌표계에서의 cosθ'
  vec3 perp = d - F * co; float pl = length(perp); vec3 pn = pl > 1e-6 ? perp / pl : A;
  vec3 dr = F * cr + pn * sqrt(max(0.0, 1.0 - cr * cr));
  float D = 1.0 / (g * (1.0 - beta * co));                        // 도플러 인자(관측 방향 기준)
  float pxRest = pxAng * D;                                       // 앞쪽은 정지 좌표계 하늘이 압축돼 한 픽셀이 더 넓은 하늘을 덮는다
  vec3 base = spaceBase(dr, pxRest);
  vec3 shift = bbColor(6500.0 * D) / bbColor(6500.0);
  vec3 c = base * shift * min(D * D * D, 60.0);
  float ph = atan(dot(d, B), dot(d, A));
  c += passingStars(F, cr, ph, pxRest, D, beta, uSpace.z);
  float m = max(c.r, max(c.g, c.b));
  c = mix(c, c * (1.0 - exp(-m * 1.15)) / max(m, 1e-4), smoothstep(0.0, 0.1, beta));  // 색을 지키는 톤 매핑 — 앞쪽 몰린 빛이 하얗게 날아가지 않게
  return c;
}
vec3 sky(vec3 d, float pxAng, vec2 discPx, vec2 p) {
  float el = asin(clamp(d.y, -1.0, 1.0));
  float u = atan(d.x, d.z) / TAU * 3.0;
  float v = clamp((70.0 * D - el) / (82.0 * D), 0.002, 0.998);
  if (uTex < 0.5) return uSkyBase;
  vec4 A = skySet(uSky, uCloud, uSkyM, uSkyO, uCldM, uCldO, u, v, el);
  vec4 B = uMix > 0.0 ? skySet(uSky2, uCloud2, uSkyM2, uSkyO2, uCldM2, uCldO2, u, v, el) : A;
  vec3 c = mix(A.rgb, B.rgb, uMix);
#if GROUND_OUTDOOR
  if (uOut < 0.5) return c * uPupil.x;   // 바깥 프로그램에는 우주 표본기를 넣지 않는다(표본기 16개 한도 — 아래 makeProgram 주석)
#else
  if (uOut < 0.5) return (uSpace.x > 0.5 ? spaceSky(d, pxAng) : c) * uPupil.x;
#endif
  float cloud = uCloudTest >= 0.0 ? uCloudTest * uCldA : mix(A.a, B.a, uMix);
  float above = smoothstep(-0.004, 0.006, d.y);   // 지평선 아래(돔 벽 너머)에는 해 · 달 · 별이 없다
#if GROUND_OUTDOOR
  // At altitude the true horizon is below zero. The baked terrain/sphere masks
  // the source; the old zero-degree cutoff would erase the sun before sunset.
  if (uGroundKind > .5 && uGroundKind < 1.5 && uTerrainOn > .5) above = 1.0;
#endif

  float sd = dot(d, uSunDir), md = max(dot(d, uMoonDir), 0.0);
  float g = max(dot(vec3(d.x, 0.0, d.z) / max(length(d.xz), 1e-4), uSunHorizon), 0.0);
  float low = exp(-max(el, 0.0) / (14.0 * D));
  // 낮: 천정은 깊은 파랑, 해 쪽은 희푸른 산란광. 사진의 구름 결은 남긴다
  float clear = 1.0 - 0.7 * cloud;
  c *= 1.0 - uSolar.w * max(d.y, 0.0) * (1.0 - 0.5 * g) * clear;
  float forward = max(sd, 0.0);
  c += (vec3(0.72, 0.85, 1.0) - c) * uSolar.x * (0.04 + 0.22 * forward * forward + 0.1 * g * low) * clear;
  // 달 없는 밤의 사진 바탕은 더 어두운 남청색. 박명 이미지가 섞이는 -6° ~ -12°와 같은 곡선이다
  // (11-05 운영자) 밤하늘 발색이 너무 짙다 → 실제 밤처럼 어둡게, 색감은 약간만: 채도를 크게 줄이고 남색으로 어둡게,
  // 지평선 근처만 옅은 도시 불빛 번짐(따뜻한 회색)을 남긴다.
  float nl = dot(c, vec3(0.2126, 0.7152, 0.0722));
  vec3 nightC = mix(vec3(nl), c, 0.45) * vec3(0.30, 0.36, 0.58) + vec3(0.020, 0.017, 0.015) * exp(-max(el, 0.0) / (9.0 * D));
  c = mix(c, nightC, uNight);
  // 달이 높고 보름에 가까울수록 밤하늘을 남청색으로 아주 조금 들어 올린다
  // 달빛: 밝기 배율 M = 1 + B달/B어두운하늘(보름 · 고도 45° 천정 ≈ 31배, 달 쪽 ≈ 63배, 반달 ≈ 4배, 초승 ≈ 1.3배).
  // 눈은 로그로 느끼므로 등급 차 Δm = 2.5 log10 M(0 ~ 약 4.5)만큼 삭 하늘에서 「달빛 회청색」 쪽으로(구름 결은 남기고 같이 밝힘).
  float moonDm = 2.5 * log(1.0 + moonSkyGain(d)) / 2.302585;
  float moonLift = clamp(moonDm / 4.5, 0.0, 1.0) * uNight * above;
  c = c * (1.0 + 0.9 * moonLift) + vec3(0.12, 0.15, 0.21) * 0.7 * moonLift * (1.0 - 0.4 * cloud);

  // 별: 하늘에 고정된 적도 좌표의 3D 격자에 하나씩. 밤 정도 · 구름으로 흐려진다
  if (uNight > 0.0) {
    vec3 e = uEqM * d * 70.0;
    vec3 cell = floor(e);
    float h = h3(cell);
    if (h > 0.9) {
      vec3 sp = normalize(cell + 0.5 + (vec3(h3(cell + 1.7), h3(cell + 3.1), h3(cell + 5.3)) - 0.5) * 0.6) * 70.0;
      float px = 70.0 * pxAng;
      float mag = (h - 0.9) * 10.0;
      float tw = 0.8 + 0.2 * sin(uTime * (1.5 + 3.0 * h) + h * 60.0);
      float star = clamp((0.7 + 0.6 * mag) - length(e - sp) / px, 0.0, 1.0) * (0.35 + 0.65 * mag) * tw;
      // 하늘이 밝아진 만큼 어두운 별부터 사라진다(한계 등급이 Δm 만큼 올라감). mag 0 = 가장 어두운 별 · 1 = 가장 밝은 별.
      float limit = clamp(moonDm / 4.5, 0.0, 1.0) * 0.92 - uPupil.y / 5.0 * 0.5;   // 확대하면(망원) 더 어두운 별까지 보인다
      c += vec3(0.95, 0.93, 1.0) * star * uStarGain * smoothstep(limit - 0.08, limit + 0.06, mag) * (1.0 + 0.12 * uPupil.y) * (1.0 - cloud) * above;
    }
  }

  // 해 쪽 사진의 라벤더를 호박빛으로 물들인다. 지평선 양쪽으로 이어져 수평 띠가 생기지 않는다.
  float warm = uSunAir.z;
  float horizonAir = g * g * g * g * exp(-el * el / (22.0 * D * 22.0 * D));
  float golden = horizonAir * uSolar.y * warm;
  float skyLuma = dot(c, vec3(0.2126, 0.7152, 0.0722));
  vec3 amber = mix(uSunGlow, uSunCol, 0.32);
  c = mix(c, amber * (0.72 + 0.3 * skyLuma), golden * 0.64);

  // 달(구름 뒤) — 낮엔 옅게, 밤엔 또렷하게 + 둘레 빛
  c *= uTele.x * uPupil.x;   // 광원 노출(확대해 달 · 해가 화면을 채울 때) × 사출동 표면 밝기
  vec3 mt = moonTangent(d, p);
  float mf = dot(d, uMoonDir);
  vec4 m = moon(mt, mf, discPx.y);
  float mvis = (uMoonScreen.w > .5 ? 1.0 : above) * uLunar.x * (1.0 - clamp(cloud / max(uCldA, 0.001), 0.0, 1.0));
  c = mix(c, c * 0.62, moonDisc(mt, mf, discPx.y) * uEarthshine * mvis);   // 어두운 면 = 그 자리 하늘색을 살짝 어둡게(고정색이 아니라 하늘에 맞춘다) — 밤에만
  // Contrast only inside the existing disc coverage. No extra angular extent;
  // fades out when the physical disc already resolves in the telephoto view.
  c = mix(c, m.rgb * (1.0 + 1.1 * uMoonCue), m.a * uLunar.y * mvis);
  float moonFacing = uMoonScreen.w > .5 ? max(0.0, 1.0 - dot(mt,mt) * .5) : md;
  c += uMoonCol * angularBloom(moonFacing, uLunar.z * D) * uLunar.w * mvis;
  // Broad halo remains subtle at high altitude; near the horizon its gain falls to 0.003.
  c += uMoonCol * angularBloom(moonFacing, uLunar.z * 3.0 * D) * uLunar.w * 0.32 * mvis;

  // Physical angular radius is unchanged by the camera focal length.
  float sunR = sin(uSunR);
  float sr = length(discTangent(d, uSunDir, uSunShape, sunR)) / sunR;
  float disc = clamp((1.0 - sr) * sunR / discPx.x + 0.5, 0.0, 1.0) * step(0.0, sd);

  // 구름 알파는 합성 강도를 뺀 밀도로 복원한다. 짙은 구름은 직사광을 가리고 산란광은 남긴다.
  float density = clamp(cloud / max(uCldA, 0.001), 0.0, 1.0);
  float direct = (1.0 - density) * (1.0 - density);
  // Weak low-altitude width correction is artistic, independent of extinction and disc radius.
  float inner = angularBloom(sd, mix(1.4, 1.9, warm) * D);
  float scatter = angularBloom(sd, mix(3.6, 4.8, warm) * D);
  float outer = angularBloom(sd, mix(7.0, 8.5, warm) * D);
  float edge = 4.0 * density * (1.0 - density);
  float corona = inner * uSunAir.x * (1.0 - 0.92 * density);
  float halo = scatter * uSunAir.y * (0.65 + 0.55 * edge) * (1.0 - 0.55 * density);
  vec3 light = mix(uSunTrans, vec3(1.0), mix(0.90, 0.15, 1.0 - uTele.y)) * uSunAir.w * disc * direct * above * uSolar.z
    + (mix(uSunTrans, vec3(1.0), 0.88) * corona
    + mix(uSunTrans, vec3(1.0), 0.70 - 0.35 * warm) * halo
    + uSunTrans * outer * 0.10 * step(0.001, uSunAir.x)) * uSolar.z * smoothstep(-.06, -.04, uSunDir.y);
  light *= uTele.y;
  c = (c + light) / (1.0 + max(light.r, max(light.g, light.b)));
  return c;
}

// Thin monoline glyphs on the glass, in an inward-readable east/up chart.
float hudSegment(vec2 p, vec2 a, vec2 b) {
  vec2 v = b - a;
  return length(p - a - v * clamp(dot(p - a, v) / dot(v, v), 0.0, 1.0));
}
vec3 compassHUD(vec3 col, vec3 ray, float lat, float lon, float glassPx) {
  // Select only the closest cardinal meridian; no four-glyph pixel loop.
  float cardinal = floor(lon / (90.0 * D) + 0.5);
  float a = cardinal * (90.0 * D);
  // 시선 방향(하늘) 기준 고도 8° · 방위 0/90/180/270° 에 둔다 — 눈 높이 때문에 생기는 돔 유리의 고도 시차 없이 실제 방위 · 고도에 놓인다.
  // 글자 높이 0.0615 rad(약 3.5°) = 390px 폰에서 약 30 CSS px.
  float size = 0.0615;
  vec2 p = vec2((lon - a) * cos(8.0 * D), lat - 8.0 * D) / size;
  // Use continuous sphere derivatives: the nearest-meridian chart jumps at 45 degrees.
  float px = max(glassPx / size, 1e-5);
  if (abs(p.x) > 0.68 + 40.0 * uDpr * px || abs(p.y) > 0.66 + 40.0 * uDpr * px) return col;   // 블룸이 다 사그라드는 거리까지(잘린 네모 테두리 방지)
  float id = mod(cardinal + 4.0, 4.0);
  vec2 bl = vec2(-0.30, -0.5), tl = vec2(-0.30, 0.5);
  vec2 br = vec2(0.30, -0.5), tr = vec2(0.30, 0.5);
  float ink;
  if (id < 0.5) { // N
    ink = min(hudSegment(p, bl, tl), min(hudSegment(p, tl, br), hudSegment(p, br, tr)));
  } else if (id < 1.5) { // E
    ink = min(hudSegment(p, bl, tl), min(hudSegment(p, tl, tr),
      min(hudSegment(p, vec2(-0.30, 0.0), vec2(0.22, 0.0)), hudSegment(p, bl, br))));
  } else if (id < 2.5) { // S: clipped corners keep the stencil light and readable.
    ink = min(hudSegment(p, tr, vec2(-0.20, 0.5)), hudSegment(p, vec2(-0.20, 0.5), vec2(-0.30, 0.35)));
    ink = min(ink, hudSegment(p, vec2(-0.30, 0.35), vec2(-0.30, 0.10)));
    ink = min(ink, hudSegment(p, vec2(-0.30, 0.10), vec2(0.30, -0.10)));
    ink = min(ink, hudSegment(p, vec2(0.30, -0.10), vec2(0.30, -0.35)));
    ink = min(ink, hudSegment(p, vec2(0.30, -0.35), vec2(0.20, -0.5)));
    ink = min(ink, hudSegment(p, vec2(0.20, -0.5), bl));
  } else { // W
    ink = min(hudSegment(p, tl, vec2(-0.19, -0.5)), hudSegment(p, vec2(-0.19, -0.5), vec2(0.0, 0.12)));
    ink = min(ink, min(hudSegment(p, vec2(0.0, 0.12), vec2(0.19, -0.5)), hudSegment(p, vec2(0.19, -0.5), tr)));
  }
  float ticks = hudSegment(vec2(abs(p.x), p.y), vec2(0.48, -0.10), vec2(0.48, 0.10));
  ink = min(ink, ticks);
  float distPx = ink / px;
  // 획 반폭(기기 픽셀) — 11-04 0.65 → 0.9 → 1.4(「더 두껍게」)
  float core = cover(ink, px, 1.4 * uDpr);
  // 글로우(11-04 운영자): 글자 색 그대로, 테두리처럼 보이지 않게 경계 없는 넓은 번짐만 — 가우스 번짐(σ ≈ 4px) + 더 넓은 블룸(꼬리 ≈ 10px).
  // 어두운 테는 「테두리 같다」 해서 뺐다. 대신 아주 넓고 옅은 그늘(σ ≈ 12px)로 밝은 낮 하늘에서 글자가 묻히지 않게 한다(경계가 생기지 않는다).
  float e = max(distPx - 1.4 * uDpr, 0.0) / uDpr;   // 획 바깥으로부터의 거리(CSS 픽셀)
  float halo = exp(-e * e / 32.0);
  float bloom = exp(-e / 10.0);
  float shade = exp(-e * e / 288.0);
  // Project the glyph center and bodies into the camera plane: fade the whole glyph,
  // including its shadow and glow, before they can cover a nearby luminary.
  vec3 glyph = vec3(sin(a) * cos(8.0 * D), sin(8.0 * D), cos(a) * cos(8.0 * D));
  vec2 gp = vec2(dot(glyph, uRight), dot(glyph, uUp)) / max(dot(glyph, uFwd), 0.01);
  vec2 sp = vec2(dot(uSunDir, uRight), dot(uSunDir, uUp)) / max(dot(uSunDir, uFwd), 0.01);
  vec2 mp = vec2(dot(uMoonDir, uRight), dot(uMoonDir, uUp)) / max(dot(uMoonDir, uFwd), 0.01);
  float sunFade = mix(1.0, smoothstep(55.0, 140.0, length(gp - sp) * uF), uSolar.z * step(0.0, dot(uSunDir, uFwd)));
  sunFade *= mix(1.0, smoothstep(45.0 + uMoonScreen.z, 100.0 + uMoonScreen.z, length(gp - mp) * uF), uLunar.x * step(0.0, dot(uMoonDir, uFwd)));
  float flick = 0.95 + 0.05 * sin(uTime * 7.3 + cardinal * 1.7) * sin(uTime * 2.1);   // 아주 옅은 네온 떨림
  vec3 hue = id < 0.5 ? vec3(1.0, 0.055, 0.075) : vec3(0.53, 0.94, 1.0);
  float dayK = uSolar.x;   // 낮일수록 그늘을 조금 더
  col = mix(col, col * 0.55, shade * (0.12 + 0.18 * dayK) * sunFade);
  col += hue * (halo * 0.38 + bloom * 0.16) * sunFade * flick;
  return mix(col, hue, core * 0.95 * sunFade);
}

void main() {
  vec2 p = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y) / uDpr;
  vec3 d = normalize(uFwd + uRight * (p.x - uC.x) / uF + uUp * (uC.y - p.y) / uF);

  // 돔(단위 구) 안쪽에서 나가는 점
  float b = dot(E, d), c = dot(E, E) - 1.0;
  vec3 q = E + (-b + sqrt(max(b * b - c, 0.0))) * d;
  float pwq = length(fwidth(q)) * 0.75;
  // 바닥 원판(돔 아래쪽) 덮임 비율 — q.y 는 바닥 가장자리(q.y = 0)를 지나며 연속이라 픽셀 폭으로 나눠 경계를 섞는다(계단 현상 방지).
  // 분기 밖에서 fwidth 를 구해 둔다(분기 안 도함수는 정의되지 않음).
  float floorK = clamp(0.5 - q.y / max(fwidth(q.y), 1e-6), 0.0, 1.0);

  // ── 유리 + 하늘
  // Directional distance derivatives before any non-uniform branch; stable tangent lengths for small discs.
  vec2 discDistance = vec2(length(discTangent(d, uSunDir, uSunShape, sin(uSunR))),
    length(moonTangent(d, p)));
  vec2 discPx = max(fwidth(discDistance), vec2(1e-6));
  float groundPixel = 1.0 / (uF * uDpr);
  groundDx=dFdx(d); groundDy=dFdy(d);
#if GROUND_OUTDOOR
  vec3 col = vec3(0);
  if (floorK < 1.0) {
    vec4 geometry = groundGeometry(d, groundPixel);
    if (geometry.x >= 1.0) col = groundSurface(d, geometry, groundPixel) * uPupil.x;
    else {
      col = sky(d, groundPixel, discPx, p);
      if (geometry.x > 0.0) col = mix(col, groundSurface(d, geometry, groundPixel) * uPupil.x, geometry.x);
    }
  }
#else
  vec4 geometry = groundGeometry(d, groundPixel);
  vec3 col = sky(d, groundPixel, discPx, p);
  // 우주 배경에는 땅이 없다 — 지평선 아래도 별.
  if (geometry.x > 0.0 && uSpace.x < 0.5) col = mix(col, groundSurface(d, geometry, groundPixel) * uPupil.x, geometry.x);
#endif
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
  if (floorK > 0.0) {
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
    if (floorK > 0.0) {
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

  vec3 outc = mix(col, fc, floorK);
  outc += (vec3(1.0) - outc) * (vec3(1.0) - exp(-beam));   // 하늘/돔 앞에도 빛기둥을 합성한다
  if (uOut > 0.5) {
    outc = mix(outc, solarOptics(outc, p), uTele.y);
    vec3 hud = compassHUD(outc, d, asin(clamp(d.y, -1.0, 1.0)), atan(d.x, d.z), 1.0 / (uF * uDpr));
    outc = mix(hud, outc, floorK);
  }
  outc += (h2(gl_FragCoord.xy) - 0.5) / 255.0;   // 그라데이션 띠 방지
  // One captured frame, no extra render pass. Quantized glass faces sweep from
  // the crown, counterclockwise in the visible screen, with a narrow neon scan.
  if (uThemeProgress < 1.0) {
    float row = lat > 62.0*D ? 0.0 : (lat > 40.0*D ? 1.0 : (lat > 18.0*D ? 2.0 : 3.0));
    float faceLon = (floor(lon/(30.0*D)) + .5) * 30.0*D;
    float faceLat = (row < .5 ? 76.0 : (row < 1.5 ? 51.0 : (row < 2.5 ? 29.0 : 9.0))) * D;
    vec3 face = vec3(sin(faceLon)*cos(faceLat),sin(faceLat),cos(faceLon)*cos(faceLat)) - E;
    vec2 faceP = uC + uF * vec2(dot(face,uRight),-dot(face,uUp)) / max(dot(face,uFwd),.01);
    vec3 zenith = vec3(0,1,0)-E;
    vec2 crown = uC + uF * vec2(dot(zenith,uRight),-dot(zenith,uUp)) / max(dot(zenith,uFwd),.01);
    crown = clamp(crown,vec2(0),uRes/uDpr);
    vec2 v = faceP-crown;
    float sector = floor(mod(atan(-v.x,-v.y)+TAU,TAU)/TAU*12.0)/12.0;
    float delay = row*.105 + sector*.49;
    float local = (uThemeProgress-delay)/.17;
    float reveal = smoothstep(0.0,1.0,local);
    vec3 old = texture(uThemeFrame,gl_FragCoord.xy/uRes).rgb;
    outc = mix(old,outc,reveal);
    float edge = max(0.0,1.0-abs(local-.5)*2.0);
    float scan = step(.91,fract(p.y*.125 + uThemeProgress*9.0));
    outc += mix(vec3(.12,.85,1),vec3(1,.16,.64),sector) * edge * (.08 + 2.4*grid + .16*scan) * (1.0-floorK);
  }
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
// UFO 기울임(11-04 운영자 요청): 폰을 세워 정면을 볼 때 핸들 돌리듯 옆으로 기울이면 하늘(카메라)은 그대로, 무늬만 낮아진 쪽으로 살살 쓸려 내려온다.
// 가속도 = TILT_G · (sin|roll| − sin 3°) · 세움 정도 — 화면 오른쪽(수평) 방향 + 그 1/4 만큼 아래. 3° 안쪽 손떨림은 무시.
// 빠르면 DRAG_FAST 가 걸려 쓸려 가는 속도는 초당 0.04 ~ 0.06(돔 반지름 1 기준) 언저리에서 멈춘다 — 「살살」.
const TILT_G = 0.1, TILT_DEAD = Math.sin(3 * Math.PI / 180), TILT_DOWN = 0.25;

function stepPieces(ps, dt, tiltA) {
  let moving = false;
  for (const p of ps) {
    if (tiltA) for (let i = 0; i < 3; i++) p.v[i] += tiltA[i] * dt;
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

  let prog = null, U = {}, programs = {}, sets = {}, slotA = null, slotB = null, lastAstro = 0, astro = null;
  let W = 0, H = 0, dpr = 1, focal = 1, focalOut = 1, cx = 0, cy = 0, cyIndoor = 0, phone = true;
  let yaw = 0, pitch = BASE_PITCH, drawnYaw = NaN, drawnPitch = NaN, lastGL = 0, lastFrame = 0, tPrev = 0;
  let zoomR = 0, zoomT = 0, zoomPath = 0, tele = 1, drawnTele = NaN, drawnR = NaN, pinch = null, moonTex = null;   // 줌(뒤로 물러선 거리) — 지금 값 · 목표 · 마지막으로 그린 값 · 두 손가락 시작 상태
  let raf = 0, stopped = true, lastShake = 0, theme = null, t0 = performance.now();
  // 장면 +z = 북, +x = 동. 바깥 보기 = 실제 시각 · 위치의 하늘(해 · 달 · 별 · 방위 글자). 시선은 두 보기가 같다
  let outdoor = false;
  let releaseGround = null, albedoLoading = false, albedoOn = false, textureEpoch = 0;
  let themeFrame = null, themeStart = -Infinity;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let spaceT0 = null, warpLast = 0, warpDist = 0;
  const spaceTex = { map: null, deep: null, blank: null, mapW: 1, loading: false };
  function loadSpaceTex() {
    if (spaceTex.loading) return; spaceTex.loading = true;
    const load = (name, key, unit) => {
      const img = new Image(); img.decoding = "async";
      img.onload = () => {
        if (gl.isContextLost()) return;
        const tex = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img); gl.generateMipmap(gl.TEXTURE_2D);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, key === "map" ? gl.REPEAT : gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        spaceTex[key] = tex; if (key === "map") spaceTex.mapW = img.width;
        if (outdoor) releaseGround?.terrain?.rebind?.();   // 그사이 바깥(지형)으로 바뀌었으면 13 · 14번 칸을 지형 것으로 되돌린다
        gl.activeTexture(gl.TEXTURE0); draw();
      };
      img.onerror = () => console.warn("[bgdome] 우주 사진을 못 받음", name);
      img.src = new URL("../assets/bg/eval/" + name, import.meta.url).href;
    };
    if (SPACE_MODE !== "shader") load(SPACE_MODE === "eso" ? "space-eso.jpg" : "space-starmap.jpg", "map", 13);
    if (SPACE_DEEP) load("space-deep.jpg", "deep", 14);
  }   // 실내 우주 배경의 워프 시작 · 적분 거리
  try { init(); } catch (err) { console.warn("[bgdome] WebGL 초기화 실패 — SVG 로 그린다", err); return null; }

  const air = document.createElement("div");
  air.className = "bgdm-air";
  const defs = GRADS.map((g, i) => `<linearGradient id="bgdm-pg${i}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${g[0]}"/><stop offset="1" stop-color="${g[1]}"/></linearGradient>`).join("");
  air.innerHTML = `<svg style="position:absolute;width:0;height:0" aria-hidden="true"><defs>${defs}</defs></svg>`;   // 고정 문자열(데이터 아님)
  host.appendChild(canvas);
  host.appendChild(air);
  const magnification = document.createElement("span");
  magnification.setAttribute("aria-hidden", "true");
  magnification.style.cssText = "position:absolute;right:18px;top:calc(env(safe-area-inset-top, 0px) + 22px);pointer-events:none;color:rgba(190,224,239,.65);font:12px ui-monospace,monospace;letter-spacing:.08em;text-shadow:0 0 8px #9ac6df;display:none";
  host.appendChild(magnification);
  const viewFocal = () => (outdoor ? focalOut : focal) * tele;
  const ufoConsole = createConsole(air);   // 공중 무늬보다 먼저 붙여 무늬가 콘솔 앞을 지나가게
  const ufoPanel = createUfoPanel();
  const life = new AbortController();   // 테마를 바꿔 장면을 없앨 때(destroy) 문서 · 창 리스너를 한꺼번에 뗀다
  // 패널에서 고르기(2단계): 버츄얼 스페이스 · 초행성X = 실내 배경, 지구 = 바깥 보기(위치 권한 — 거절 · 실패면 지금 배경에 남는다)
  ufoPanel.onPick((key) => {
    if (key === "earth") { if (!outdoor) chooseBgView("outdoor"); return; }
    if (key !== INDOOR_BG) setIndoorBg(key);
    if (outdoor) setBgView("indoor");
  });
  document.addEventListener(BGINDOOR_EVENT, (e) => {
    const v = e.detail === "space" ? "space" : "pink";
    if (v === INDOOR_BG) return;
    INDOOR_BG = v;
    spaceT0 = null; warpDist = 0;   // 우주에 새로 들어간다
    draw();
  }, { signal: life.signal });
  let wasPeek = false, ufoArmed = false;   // 열린 직후 물러나는 동안(r 0 → 0.4)엔 패널이 번쩍 뜨지 않게 — 다 물러났거나 손가락으로 줌하면 켠다

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
    programs = {};
    makeProgram(false); makeProgram(true);
    if (GROUND.kind === "mountain") makeProgram(true, true);
    prog = programs[outdoor ? "outdoor" : "indoor"].program;
    U = programs[outdoor ? "outdoor" : "indoor"].uniforms;
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    moonTex = null; albedoLoading = albedoOn = false; textureEpoch++;
    themeFrame = null; themeStart = -Infinity;
    if (releaseGround) releaseGround();
    releaseGround = createGroundTextures(gl, GROUND, () => { lastGL = 0; draw(); });
    sets = {}; slotA = slotB = null; astro = null;
    loadSet("day");
    theme = null;
  }

  function makeProgram(outside, terrain = false) {
    prog = gl.createProgram();
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VS));
    // Each program carries only its ground material. Switching copies uniforms
    // once per view change, never per frame; textures and vertex storage are shared.
    let fragment = FS.replace("if (uOut < .5) return groundSurfaceIndoor(ray, geometry, pixel);",
      outside ? "" : "return groundSurfaceIndoor(ray, geometry, pixel);");
    fragment = fragment.replace("precision highp float;", `precision highp float;\n#define GROUND_OUTDOOR ${outside ? 1 : 0}`);
    if (terrain) {
      // Compile away the fallback ridge/material path. Keeping both in one
      // fragment program increases register pressure even after the bake.
      fragment = fragment.replace("uniform float uTerrainOn;", "const float uTerrainOn = 1.0;");
    } else {
      // (11-06 수정) 실내 · 지형 없는 바깥 프로그램은 지형을 쓰지 않는다(terrain.view 는 지형 프로그램에서만 1) — 상수 0 으로 지형 경로와
      // 표본기 6개를 컴파일에서 빼낸다. 안 빼면 산 장소 기기에서 실내 = 하늘 4 · 달 · 테마 · 우주 2 · 바닥 4 · 지형 6 = 18 개로
      // 폰 · PC 흔한 한도(MAX_TEXTURE_IMAGE_UNITS 16)를 넘어 WebGL 이 통째로 실패했다(11-05 우주 배경 추가 뒤부터).
      fragment = fragment.replace("uniform float uTerrainOn;", "const float uTerrainOn = 0.0;");
    }
    // Keep the indoor arithmetic identical to the original uniform path;
    // constant-folded sphere geometry can move a final 8-bit rounding boundary.
    if (!outside) fragment = fragment.replace(
      `const float uGroundKind = ${GROUND.index}.0, uGroundAlt = ${GROUND.altitude}.0;`,
      "uniform float uGroundKind, uGroundAlt;");
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, fragment));
    gl.bindAttribLocation(prog, 0, "aPos");
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) || "link");
    gl.useProgram(prog);
    const n = gl.getProgramParameter(prog, gl.ACTIVE_UNIFORMS);
    U = {};
    for (let i = 0; i < n; i++) { const name = gl.getActiveUniform(prog, i).name; U[name] = gl.getUniformLocation(prog, name); }
    gl.uniform1i(U.uSky, 0); gl.uniform1i(U.uCloud, 1); gl.uniform1i(U.uSky2, 2); gl.uniform1i(U.uCloud2, 3);
    gl.uniform1f(U.uMix, 0); gl.uniform1f(U.uOut, 0); gl.uniform1f(U.uNight, 0); gl.uniform2f(U.uPupil, 1, 0);
    // 우주 사진 표본기: 실내만 13 · 14번 칸. 바깥 프로그램에서는 지형 정수 표본기(13번)와 겹치면 그리기가 통째로 실패하므로 0번(같은 float 종류)에.
    gl.uniform1i(U.uSpaceMap, outside ? 0 : 13); gl.uniform1i(U.uSpaceDeep, outside ? 0 : 14);
    gl.uniform3f(U.uCloudSeed, ...CLOUD_SEED);
    gl.uniformMatrix3fv(U.uEqM, false, new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1]));
    gl.uniform1f(U.uSunR, SUN_MOON_R[0] * DEG); gl.uniform1f(U.uMoonR, SUN_MOON_R[1] * DEG);
    gl.uniform1i(U.uMoonTex, 4); gl.uniform1f(U.uMoonTexOn, 0);
    gl.uniform1i(U.uGroundTile, 5); gl.uniform1i(U.uGroundRidge, 6); gl.uniform1i(U.uGroundAlbedo, 7);
    gl.uniform1i(U.uThemeFrame, 9); gl.uniform1f(U.uThemeProgress, 1);
    gl.uniform1i(U.uGroundIndoorTile, 10);
    gl.uniform1i(U.uTerrainSkyline, 8); gl.uniform1i(U.uTerrainGeometry, 11); gl.uniform1i(U.uTerrainNormal, 12);
    gl.uniform1i(U.uTerrainDetail, 13); gl.uniform1i(U.uTerrainDetailNormal, 14); gl.uniform1i(U.uTerrainShadow, 15);
    gl.uniform1f(U.uTerrainOn, 0); gl.uniform1f(U.uTerrainDetailOn, 0);
    if (!outside) { gl.uniform1f(U.uGroundKind, GROUND.index); gl.uniform1f(U.uGroundAlt, GROUND.altitude); }
    gl.uniform1f(U.uGroundAlbedoOn, 0);
    programs[terrain ? "terrain" : outside ? "outdoor" : "indoor"] = { program: prog, uniforms: U };
  }

  function useViewProgram() {
    const target = programs[outdoor ? (releaseGround?.terrain?.ready ? "terrain" : "outdoor") : "indoor"];
    if (target === programs.terrain) releaseGround?.terrain?.rebind?.();   // 실내가 13 · 14번 칸에 꽂은 우주 · 검정 질감을 지형 것으로
    if (target.program === prog) return;
    gl.useProgram(target.program);
    for (let i = 0; i < gl.getProgramParameter(target.program, gl.ACTIVE_UNIFORMS); i++) {
      const { name, type } = gl.getActiveUniform(target.program, i);
      if (U[name] == null) continue;
      // 우주 사진 표본기의 칸은 프로그램마다 다르다(실내 13 · 14, 바깥 0) — 옮겨 쓰면 바깥에서 지형 정수 표본기와 겹쳐 그리기가 실패한다.
      if (name === "uSpaceMap" || name === "uSpaceDeep") continue;
      const value = gl.getUniform(prog, U[name]), location = target.uniforms[name];
      if (type === gl.FLOAT) gl.uniform1f(location, value);
      else if (type === gl.FLOAT_VEC2) gl.uniform2fv(location, value);
      else if (type === gl.FLOAT_VEC3) gl.uniform3fv(location, value);
      else if (type === gl.FLOAT_VEC4) gl.uniform4fv(location, value);
      else if (type === gl.FLOAT_MAT3) gl.uniformMatrix3fv(location, false, value);
      else if (type === gl.SAMPLER_2D || type === gl.INT) gl.uniform1i(location, value);
    }
    prog = target.program; U = target.uniforms;
    slotA = slotB = null;
  }

  /** 달 앞면 사진(바깥 보기에서 처음 쓸 때 한 번) — 4번 칸. 못 받으면 무늬 없는 달로 그린다 */
  function loadMoonTex() {
    if (moonTex) return;
    moonTex = gl.createTexture();
    const img = new Image();
    img.decoding = "async";
    img.onload = () => {
      if (gl.isContextLost()) return;
      gl.activeTexture(gl.TEXTURE4);
      gl.bindTexture(gl.TEXTURE_2D, moonTex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
      gl.generateMipmap(gl.TEXTURE_2D);   // 달이 몇 픽셀일 때 반짝이지 않게
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.uniform1f(U.uMoonTexOn, 1);
      draw();
    };
    img.onerror = () => console.warn("[bgdome] 달 사진을 못 받음");
    img.src = new URL("../assets/bg/moon-near.webp", import.meta.url).href;
  }

  /** 하늘 한 벌(하늘 · 구름 두 장)을 받아 GPU 에 올린다. 다 받으면 ready */
  function loadSet(name) {
    if (sets[name]) return sets[name];
    const set = sets[name] = { name, sky: gl.createTexture(), cloud: gl.createTexture(), left: 2, ready: false };
    const [skyRel, cloudRel] = SKY_FILES[name];
    for (const [tex, rel] of [[set.sky, skyRel], [set.cloud, cloudRel]]) {
      const img = new Image();
      img.decoding = "async";
      img.onload = () => {
        if (gl.isContextLost()) return;
        gl.activeTexture(gl.TEXTURE9);   // Temporary upload unit; preserve ground/albedo units 5..8.
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
        gl.generateMipmap(gl.TEXTURE_2D);   // 천정 · 지평선 평균색(작은 단계)용. 본 샘플은 0단계만 써서 경도 이음매에 줄이 안 생긴다
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        const err = gl.getError();
        if (err || DEBUG) console.warn(`[bgdome] 하늘 이미지 ${rel} ${img.naturalWidth}x${img.naturalHeight} glError=${err}`);
        if (--set.left === 0) {
          set.ready = true;
          slotA = slotB = null;   // 다음 그리기에서 다시 고른다
          if (name === "day") gl.uniform1f(U.uTex, 1);
          draw();
        }
      };
      img.onerror = () => console.warn(`[bgdome] 하늘 이미지를 못 받음 ${rel}`);
      img.src = new URL(rel, import.meta.url).href;
    }
    return set;
  }

  /** 낮 한 벌만 테마 색 보정(실내와 같은 분홍 톤)을 받고, 노을 · 박명 · 밤은 그린 색 그대로 */
  function setUniforms(set, slot) {
    const t = THEMES[theme || "dark"];
    const m3 = (M) => new Float32Array([M[0][0], M[1][0], M[2][0], M[0][1], M[1][1], M[2][1], M[0][2], M[1][2], M[2][2]]);   // 열 우선
    const I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], Z = [0, 0, 0];
    const day = set.name === "day";
    const sfx = slot === 0 ? "" : "2";
    gl.uniformMatrix3fv(U["uSkyM" + sfx], false, m3(day ? t.skyM : I)); gl.uniform3fv(U["uSkyO" + sfx], day ? t.skyO : Z);
    gl.uniformMatrix3fv(U["uCldM" + sfx], false, m3(day ? t.cldM : I)); gl.uniform3fv(U["uCldO" + sfx], day ? t.cldO : Z);
    gl.activeTexture(gl.TEXTURE0 + slot * 2); gl.bindTexture(gl.TEXTURE_2D, set.sky);
    gl.activeTexture(gl.TEXTURE1 + slot * 2); gl.bindTexture(gl.TEXTURE_2D, set.cloud);
  }

  /** 지금 그릴 두 벌(A · B)과 섞는 비율. 아직 안 받은 벌은 받는 동안 받아 둔 쪽으로 대신한다 */
  function chooseSets() {
    let a = "day", b = null, mix = 0;
    if (astro) {
      const alt = astro.sunGeometricAlt / DEG;
      a = SKY_KEYS[0].name;
      if (alt <= SKY_KEYS[3].alt) a = "night";
      else if (alt < SKY_KEYS[0].alt) {
        for (let i = 0; i < 3; i++) {
          const k0 = SKY_KEYS[i], k1 = SKY_KEYS[i + 1];
          if (alt <= k0.alt && alt > k1.alt) { a = k0.name; b = k1.name; mix = (k0.alt - alt) / (k0.alt - k1.alt); break; }
        }
      }
    }
    if (astro && astro.rising) { if (a === "twilight") a = "dawn"; if (b === "twilight") b = "dawn"; }
    for (const n of [a, b]) if (n) loadSet(n);
    const ready = (n) => n && sets[n] && sets[n].ready;
    if (!ready(a)) { a = ready(b) ? b : "day"; b = null; mix = 0; }
    if (b && !ready(b)) { b = null; mix = 0; }
    if (a !== slotA) setUniforms(sets[a], 0);
    if (b && b !== slotB) setUniforms(sets[b], 1);
    slotA = a; slotB = b;
    gl.uniform1f(U.uMix, b ? mix : 0);
  }

  /** 바깥 보기: 실제 시각 · 위치로 해 · 달 · 별 방향을 다시 구한다 */
  function updateAstro(force) {
    const site = outdoorSite();
    if (!outdoor || !site) {
      if (astro) { astro = null; gl.uniform1f(U.uOut, 0); gl.uniform1f(U.uNight, 0); lastGL = 0; }
      return;
    }
    const now = performance.now();
    if (!force && now - lastAstro < ASTRO_MS) return;
    lastAstro = now;
    const t = new Date(nowMs());
    const sun = sunPosition(t, site.lat, site.lon), moon = moonPosition(t, site.lat, site.lon);
    const later = sunPosition(new Date(+t + 5 * 60000), site.lat, site.lon).alt;
    const rising = later > sun.alt;   // 이미지 선택은 그대로, 5분 뒤가 더 높으면 아침
    const smooth = (a, b, x) => { const v = Math.min(1, Math.max(0, (x - a) / (b - a))); return v * v * (3 - 2 * v); };
    // Twilight uses geometric sun altitude; disc position, airmass and empirical squash use apparent altitude.
    sun.geometricAlt = sun.alt;
    sun.apparentAlt = sun.alt + refraction(sun.alt);
    moon.apparentAlt = moon.alt; // Already refracted by moonPosition, never add twice.
    for (const [name, body] of [["sun", sun], ["moon", moon]]) {
      const h = debugNumber("bg" + name + "alt"), az = debugNumber("bg" + name + "az");
      if (h != null) body.apparentAlt = Math.max(-90, Math.min(90, h)) * DEG;
      if (az != null) body.az = az * DEG;
    }
    if (debugNumber("bgsunalt") != null) sun.geometricAlt = sun.apparentAlt - refraction(sun.apparentAlt);
    const alt = sun.geometricAlt / DEG;
    const night = 1 - smooth(-12, -6, alt);
    // 남중 전후에도 색을 매끄럽게 잇는다. 이미지의 아침 · 저녁 판정과 별개로 앞뒤 5분 고도차를 쓴다
    const day = smooth(-2, 12, alt), warm = 1 - smooth(10, 28, alt);
    // 오늘 적위로 남중 고도를 구한다. 계절마다 달라지는 최고 고도에 맞춰 천정의 파랑을 깊게 한다
    const phi = site.lat * DEG;
    const dec = Math.asin(Math.max(-1, Math.min(1, Math.sin(phi) * Math.sin(sun.alt) + Math.cos(phi) * Math.cos(sun.alt) * Math.cos(sun.az))));
    const maxAlt = Math.PI / 2 - Math.abs(phi - dec);
    const noon = smooth(0.78, 0.995, Math.max(0, Math.sin(sun.alt)) / Math.max(0.05, Math.sin(maxAlt))) * day;
    const dusk = smooth(-12, -2, alt) * (1 - smooth(4, 16, alt));
    // 흰금색 핵을 둘러싼 노란 테. 여명은 복숭아 · 연금, 일몰은 짙은 금빛 산란광이다.
    const sunTrans = transmission(sun.apparentAlt / DEG);
    const sunCol = exposedHue(sunTrans), sunGlow = sunCol;
    let moonSun = dirOf(sun.alt, sun.az), fraction = moonIllumination(t).fraction;
    if (MOON_TEST != null) {
      // 위상 p → 해-달 이각 ψ = 2πp. 차오르는 동안(p < 0.5) 해는 달의 서쪽 — 북반구에서 오른쪽이 밝다
      moon.apparentAlt = (debugNumber("bgmoonalt") ?? 35) * DEG; moon.az = (debugNumber("bgmoonaz") ?? 180) * DEG;
      moon.alt = moon.apparentAlt;
      const m = dirOf(moon.alt, moon.az), up = [0, 1, 0];
      const w = [up[1] * m[2] - up[2] * m[1], up[2] * m[0] - up[0] * m[2], up[0] * m[1] - up[1] * m[0]];   // up × m = 달 자리의 서쪽
      const wl = Math.hypot(...w), psi = 2 * Math.PI * MOON_TEST;
      moonSun = m.map((c, i) => Math.cos(psi) * c + Math.sin(psi) * w[i] / Math.max(wl, 1e-6));
      fraction = (1 - Math.cos(psi)) / 2;
    }
    sun.alt = sun.apparentAlt; moon.alt = moon.apparentAlt;
    const moonAlt = moon.apparentAlt / DEG;
    const moonUp = smooth(-4, -3, moonAlt);
    const moonContrast = 1 - smooth(-8, 10, alt);
    const moonLight = night * fraction * fraction * moonUp * smooth(0, 50, moonAlt);
    const moonWarm = 1 - smooth(0, 20, moonAlt);
    const moonHue = exposedHue(transmission(moonAlt));
    const moonCol = moonHue.map((v, i) =>
      (v * (1 - moonWarm * 0.62) + [1, 0.29, 0.025][i] * moonWarm * 0.62) *
      [0.94, 0.965, 1][i] * EXPOSURE.moon);
    astro = { night, sunGeometricAlt: sun.geometricAlt, moonGeometricAlt: moon.geometricAlt, sunAlt: sun.alt, sunAz: sun.az, moonAlt: moon.alt, moonAz: moon.az, rising, fraction, noon, moonLight, time: t.toISOString() };
    gl.uniform1f(U.uOut, 1);
    gl.uniform1f(U.uNight, night);
    gl.uniform3fv(U.uSunCol, sunCol);
    gl.uniform3fv(U.uSunGlow, sunGlow);
    const stage = DEBUG && !NORMAL ? QS.get("bglight") : null;
    gl.uniform3fv(U.uSunTrans, sunCol);
    gl.uniform1f(U.uCloudTest, debugNumber("bgcloud") == null ? -1 : Math.max(0, Math.min(1, debugNumber("bgcloud"))));
    gl.uniform4f(U.uSunAir, stage === "disc" ? 0 : 18 + 8 * warm, stage === "disc" ? 0 : 4.5 + 2 * warm, warm, EXPOSURE.sun);
    gl.uniform4f(U.uOptics, smooth(-4, -3, sun.alt / DEG),
      2 + 3 * smooth(0, 30, sun.alt / DEG), 0.1 + 0.9 * smooth(0, 30, sun.alt / DEG),
      stage === "disc" || stage === "bloom" ? 0 : stage === "rays" ? 1 : 2);
    gl.uniform3fv(U.uSunHorizon, [Math.sin(sun.az), 0, Math.cos(sun.az)]);
    gl.uniform4f(U.uSolar, day, dusk, smooth(-4, -3, sun.alt / DEG), day * (0.045 + 0.055 * noon));
    gl.uniform3fv(U.uMoonCol, moonCol);
    gl.uniform4f(U.uLunar, moonUp, 0.22 + 0.78 * moonContrast,
      0.22 + 0.23 * (1 - moonWarm),
      Math.pow(fraction, 0.7) * moonContrast * (0.003 + 0.047 * (1 - moonWarm)));
    gl.uniform1f(U.uMoonLight, moonLight);
    // 달빛 모형 입력: 위상각 α(fraction = (1 + cos α)/2), 달 V 등급(K&S 식 9), 대기 밖 조도(식 8), 달까지 소광(식 3 공기질량).
    {
      const K = 0.20, alpha = Math.acos(Math.max(-1, Math.min(1, 2 * fraction - 1))) / DEG;
      const m = -12.73 + 0.026 * alpha + 4e-9 * alpha ** 4, Istar = 10 ** (-0.4 * (m + 16.57));
      const air = (altDeg) => { const z = (90 - Math.max(altDeg, 0)) * DEG; return 1 / Math.sqrt(1 - 0.96 * Math.sin(z) ** 2); };
      const up = smooth(-2, 0, moonAlt), ext = 10 ** (-0.4 * K * air(moonAlt));
      gl.uniform2f(U.uMoonKS, Istar * ext * up / 59.2, K);
      // 지형 달빛 = 지면 조도 비율(달 등급 · 소광 · sin 고도), 보름 · 고도 45° = 1(반달 ≈ 0.12, 지평선 보름 ≈ 0.01 — Seidelmann 1992 표와 같은 꼴).
      const full45 = 10 ** (-0.4 * (-12.73 + 16.57)) * 10 ** (-0.4 * K * air(45)) * Math.sin(45 * DEG);
      gl.uniform1f(U.uGroundMoonLight, night * Math.min(1.4, Istar * ext * Math.sin(Math.max(moonAlt, 0) * DEG) / full45) * up);
    }
    gl.uniform1f(U.uStarGain, night);   // 달빛에 따른 별 줄임은 셰이더가 픽셀마다(한계 등급)
    gl.uniform1f(U.uEarthshine, night * (0.72 + 0.12 * (1 - fraction)));
    gl.uniform3fv(U.uSunDir, dirOf(sun.alt, sun.az));
    gl.uniform3fv(U.uMoonDir, dirOf(moon.alt, moon.az));
    gl.uniform3fv(U.uMoonSun, moonSun);
    gl.uniform2f(U.uMoonRot, Math.cos(moon.parallactic), Math.sin(moon.parallactic));
    loadMoonTex();
    // 고도 5° 이상은 원, 지평선에서는 세로/가로 약 0.83. 방향 · 세기는 픽셀마다가 아니라 초당 한 번 구한다.
    const shape = (key, body) => {
      const sa = Math.sin(body.alt), ca = Math.cos(body.alt);
      gl.uniform4f(U[key], -sa * Math.sin(body.az), ca, -sa * Math.cos(body.az), 1 - smooth(0, 5, body.alt / DEG));
    };
    shape("uSunShape", sun);
    shape("uMoonShape", moon);
    const M = horizonToEquatorial(t, site.lat, site.lon);
    gl.uniformMatrix3fv(U.uEqM, false, new Float32Array([M[0][0], M[1][0], M[2][0], M[0][1], M[1][1], M[2][1], M[0][2], M[1][2], M[2][2]]));
    lastGL = 0;
  }

  // Fetch only the selected outdoor material. A failed upload keeps procedural ground.
  function loadGroundAlbedo() {
    if (!outdoor || GROUND.kind === "sea" || albedoLoading) return;
    albedoLoading = true;
    const epoch = textureEpoch;
    if (releaseGround.terrain) {
      releaseGround.terrain.start().then(() => {
        if (epoch !== textureEpoch || gl.isContextLost()) return;
        albedoOn = true; lastGL = 0; draw();
      }).catch(() => { /* failed DEM/Worker keeps the original mountain */ });
      return;
    }
    const img = new Image(); img.decoding = "async";
    img.onload = () => {
      if (epoch !== textureEpoch || gl.isContextLost()) return;
      try {
        releaseGround.setAlbedo(img);
        albedoOn = true; lastGL = 0; draw();
      } catch (_) { albedoOn = false; }
    };
    img.onerror = () => { /* procedural material remains available */ };
    img.src = new URL("../assets/bg/ground-" + GROUND.kind + "-albedo.webp", import.meta.url).href;
  }

  function applyTheme() {
    const name = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    if (name === theme) return;
    if (theme && !reducedMotion.matches && W && !isPaused()) {
      gl.drawArrays(gl.TRIANGLES, 0, 3); // refresh the non-preserved backbuffer before copying
      // Repeated toggles capture the currently visible mixture, avoiding a jump.
      if (!themeFrame) themeFrame = gl.createTexture();
      gl.activeTexture(gl.TEXTURE9); gl.bindTexture(gl.TEXTURE_2D, themeFrame);
      gl.copyTexImage2D(gl.TEXTURE_2D, 0, gl.RGB, 0, 0, canvas.width, canvas.height, 0);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      themeStart = performance.now();
      gl.activeTexture(gl.TEXTURE0);
    } else themeStart = -Infinity;
    theme = name;
    const t = THEMES[name];
    gl.uniform1f(U.uCldA, 0.5);
    slotA = slotB = null;   // 낮 한 벌의 색 보정이 테마마다 달라 다시 건다
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
    if (gl.isContextLost() || !W || releaseGround?.terrain?.uploading) return;
    useViewProgram();
    applyTheme();
    updateAstro(false);
    chooseSets();
    loadGroundAlbedo();
    gl.uniform1f(U.uGroundAlbedoOn, outdoor && albedoOn ? 1 : 0);
    gl.uniform1f(U.uThemeProgress, reducedMotion.matches ? 1 : Math.min(1, (performance.now()-themeStart)/THEME_MS));
    const B = basis();
    gl.uniform3fv(U.uFwd, B.fwd); gl.uniform3fv(U.uRight, B.right); gl.uniform3fv(U.uUp, B.up);
    gl.uniform3fv(U.E, EYE); drawnR = zoomR; drawnTele = tele;
    gl.uniform1f(U.uF, viewFocal());
    // 실내 우주가 13 · 14번 칸에 float 질감을 꽂았다면 바깥 지형(정수 표본기) 전에 비운다 — 확대 조각이 있으면 view() 가 다시 꽂는다.
    if (outdoor && spaceTex.blank) { gl.activeTexture(gl.TEXTURE13); gl.bindTexture(gl.TEXTURE_2D, null); gl.activeTexture(gl.TEXTURE14); gl.bindTexture(gl.TEXTURE_2D, null); }
    if (outdoor && releaseGround.terrain) releaseGround.terrain.view(U, yaw, pitch,
      2 * Math.atan(W / (2 * viewFocal())), 2 * Math.atan(H / (2 * viewFocal())), tele, W, H);
    gl.uniform2f(U.uTele, 1, 1);
    {
      // 사출동 광학: 구경 70mm, 눈동자 = 밝은 곳 3mm ~ 어둠 적응 7mm(바깥 = 밤 정도, 실내 = 우주면 어둠 · 분홍이면 밝음).
      const APERTURE = 70, dark = outdoor ? (astro ? astro.night ?? 0 : 0) : (INDOOR_BG === "space" ? 1 : 0);
      const pupil = 3 + 4 * dark, exitPupil = APERTURE / Math.max(tele, 1);
      const surface = tele <= 1 ? 1 : Math.min(1, (exitPupil / pupil) ** 2);
      const starGain = Math.min(tele * tele, (APERTURE / pupil) ** 2);
      gl.uniform2f(U.uPupil, surface, tele <= 1 ? 0 : 2.5 * Math.log10(starGain));
    }
    gl.uniform1f(U.uTime, T_SPEED === 0 ? 0 : (performance.now() - t0) / 1000);
    if (INDOOR_BG === "space" && !outdoor) {
      const now = performance.now();
      if (spaceT0 === null) { spaceT0 = now; warpLast = now; }
      const el = WARP_FIXED != null ? WARP_FIXED : (now - spaceT0) / 1000;
      // 모션 줄이기: 별이 흐르지 않는 정지 우주(속도 0)로만.
      const beta = reducedMotion.matches ? 0 : voyageBeta(el);
      const scroll = 0.45 + 1.6 * beta;                       // 지나가는 별의 흐름 빠르기(로그 극좌표 s / 초)
      if (WARP_FIXED != null) warpDist = el * scroll; else { warpDist += Math.min(0.1, (now - warpLast) / 1000) * scroll * (beta > 0 ? 1 : 0); warpLast = now; }
      gl.uniform4f(U.uSpace, 1, beta, warpDist, scroll);
      loadSpaceTex();
      gl.uniform4f(U.uSpaceTex, spaceTex.map ? 1 : 0, spaceTex.deep ? 1 : 0, SPACE_MODE === "eso" ? 2 : 1, SPACE_MODE === "eso" ? 1.8 : 1.5);
      gl.uniform2f(U.uSpaceMapSize, spaceTex.mapW, spaceTex.mapW / 2);
      gl.uniform3f(U.uWarpDir, 0, 0.05, 0.99875);
    } else gl.uniform4f(U.uSpace, 0, 0, 0, 0);
    // (11-06 수정) 실내 프로그램의 우주 표본기(13 · 14번, float)는 분홍 하늘일 때도 활성이다. 산 장소 기기는 그 칸에 지형의 정수 질감(RGBA16UI)이
    // 꽂혀 있어 float 표본기와 종류가 어긋나면 그리기가 통째로 실패(하늘 · 바닥 검정)하므로, 실내는 매번 우주 사진 또는 1×1 검정을 꽂는다.
    // 지형 프로그램으로 돌아갈 때는 useViewProgram 이 terrain.rebind() 로 되돌린다.
    if (!outdoor) {
      if (!spaceTex.blank) { spaceTex.blank = gl.createTexture(); gl.activeTexture(gl.TEXTURE13); gl.bindTexture(gl.TEXTURE_2D, spaceTex.blank); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([0, 0, 0, 255])); }
      gl.activeTexture(gl.TEXTURE13); gl.bindTexture(gl.TEXTURE_2D, spaceTex.map || spaceTex.blank);
      gl.activeTexture(gl.TEXTURE14); gl.bindTexture(gl.TEXTURE_2D, spaceTex.deep || spaceTex.blank);
      gl.activeTexture(gl.TEXTURE0);
    }
    gl.uniform1f(U.uMoonCue, 0);
    let moonRadius = SUN_MOON_R[1] * DEG;
    if (astro && SIZE_MODE === "eye") {
      const m = dirOf(astro.moonAlt,astro.moonAz), z = dot3(m,B.fwd);
      const radius = MOON_CSS_DIAMETER * tele / 2;
      const right = [Math.cos(astro.moonAz),0,-Math.sin(astro.moonAz)];
      const ax = dot3(right,B.right), ay = dot3(right,B.up), len = Math.hypot(ax,ay) || 1;
      gl.uniform2f(U.uMoonAxis,ax/len,ay/len);
      moonRadius = Math.atan(radius/viewFocal());
      gl.uniform4f(U.uMoonScreen, cx+viewFocal()*dot3(m,B.right)/Math.max(z,.001),
        cy-viewFocal()*dot3(m,B.up)/Math.max(z,.001), radius, z > 0 ? 1 : 0);
    } else gl.uniform4f(U.uMoonScreen,0,0,0,0);
    gl.uniform2f(U.uGroundSourceVisibility, 1, 1);
    // Camera/source-only optics terms computed once per draw, rather than once per fragment.
    if (astro) {
      const s = dirOf(astro.sunAlt, astro.sunAz), z = dot3(s, B.fwd);
      const smooth = (a, b, x) => { const v = Math.max(0, Math.min(1, (x - a) / (b - a))); return v * v * (3 - 2 * v); };
      if (outdoor) {
        const pixel = 1 / (viewFocal() * dpr);
        gl.uniform2f(U.uGroundSourceVisibility,
          releaseGround.sourceVisibility(s, SUN_MOON_R[0] * DEG, pixel),
          releaseGround.sourceVisibility(dirOf(astro.moonAlt, astro.moonAz), moonRadius, pixel));
        const cue = DEBUG && QS.get("bgmooncues") === "0" ? 0 :
          (1 - smooth(6, 12, 2 * viewFocal() * moonRadius)) *
          (1 - smooth(8, 14, astro.moonAlt / DEG));
        gl.uniform1f(U.uMoonCue, cue);
      }
      let sx = cx, sy = cy, gain = 0, view = 0;
      if (z > 0.05) {
        const F = viewFocal();
        sx += F * dot3(s, B.right) / z; sy -= F * dot3(s, B.up) / z;
        const outside = Math.hypot(Math.max(-sx, sx - W, 0), Math.max(-sy, sy - H, 0));
        gain = (1 - smooth(0, 8 * DEG, Math.atan(outside / F))) * smooth(0.05, 0.3, z)
          * smooth(-4 * DEG, -3 * DEG, s[1]);
        view = 0.75 + 0.25 * Math.exp(-Math.pow(Math.acos(Math.max(0, Math.min(1, z))) / (12 * DEG), 2));
      }
      gl.uniform4f(U.uFlare, sx, sy, gain, view);
      // Meter only a visible source inside the frame; fading at its edges avoids exposure jumps.
      const meter = (alt, az, radius) => {
        const v = dirOf(alt, az), z = dot3(v, B.fwd);
        if (z <= 0 || (!releaseGround.terrain?.ready && alt < -radius)) return 0;
        const F = viewFocal(), x = cx + F * dot3(v, B.right) / z, y = cy - F * dot3(v, B.up) / z;
        const edge = Math.min(x, W - x, y, H - y);
        return smooth(-F * radius, F * radius + 20, edge) * smooth(3, 24, F * radius * 2);
      };
      if (outdoor && tele > 1) {
        const sunMeter = meter(astro.sunAlt, astro.sunAz, SUN_MOON_R[0] * DEG);
        const moonMeter = meter(astro.moonAlt, astro.moonAz, moonRadius) * Math.sqrt(astro.fraction);
        gl.uniform2f(U.uTele, 1 - 0.94 * Math.max(sunMeter, moonMeter), 1 / (1 + 28 * sunMeter));
      }
    }
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
        const F = viewFocal();
        sx = cx + F * dot3(q, B.right) / z;
        sy = cy - F * dot3(q, B.up) / z;
        s = F * base * p.size / z / BOX;
        const m = BOX * s;
        show = sx > -m && sx < W + m && sy > -m && sy < H + m;
      }
      if (show !== p.shown) { p.el.style.visibility = show ? "" : "hidden"; p.shown = show; }
      if (show) p.el.style.transform = `translate3d(${(sx - BOX / 2).toFixed(1)}px,${(sy - BOX / 2).toFixed(1)}px,0) scale(${s.toFixed(3)}) rotate(${(p.th / DEG).toFixed(1)}deg)`;
    }
  }

  // 시선(11-05 운영자 「바깥 · 실내 시선 통일 — 바꿀 때마다 돌아가서 어색」): 두 보기 모두 폰이 실제로 향한 방향 그대로(AR 방식).
  //   방위 = 나침반 절대 방위(bggyro.gyroAbs — 진북 보정(편각)은 위치가 있을 때, 두 보기 공통), 나침반이 없으면 자이로 상대 방위. 기울기 = 중력으로 잰 실제 기울기.
  //   기준점 = 화면 정가운데. 센서가 하나도 없으면(PC 등) 옛 실내 구도(위로 28° · 테두리가 화면 아래)로 고정.
  //   그래서 보기를 바꿔도 화면이 돌지 않는다. 옛 실내 보기의 「35% 만 따라 돌기 · 흔들면 지금 방향이 정면」은 없앴다(흔들면 무늬만 섞인다).
  function updateView(dt, now) {
    const peek = document.documentElement.classList.contains("bg-peek");
    const a = gyroAbs(), g = gyroView();
    let target = yaw, tPitch = BASE_PITCH;
    if (a) { target = a.yaw; tPitch = a.pitch; }
    else if (g) { target = g.yaw; tPitch = g.rawPitch; }
    const sensed = !!(a || g), wantCy = sensed ? H / 2 : cyIndoor;
    if (W && Math.abs(wantCy - cy) > 0.5) { cy = wantCy; gl.uniform2f(U.uC, cx, cy); drawnYaw = NaN; }
    const tYaw = yaw + Math.atan2(Math.sin(target - yaw), Math.cos(target - yaw));   // 북쪽(±180°)을 넘을 때 한 바퀴 돌지 않게
    tPitch = Math.max(PITCH_MIN, Math.min(PITCH_MAX, tPitch));
    // Stronger damping at telephoto, with a bounded response time (0.08..0.44 s).
    const k = 1 - Math.exp(-dt / (0.08 + 0.36 * Math.log(tele) / Math.log(30)));
    yaw += (tYaw - yaw) * k;
    pitch += (tPitch - pitch) * k;
    if (!peek) { zoomT = 0; pinch = null; }   // 배경 보기를 닫으면 중심으로 돌아온다
    else if (!wasPeek) { zoomT = PEEK_START_R; ufoArmed = false; }  // 열 때는 뒤로 물러난 자리에서(가운데 콘솔이 앞에 보이게) — 부드럽게 물러난다
    wasPeek = peek;
    zoomPath += (zoomT - zoomPath) * (1 - Math.exp(-dt / 0.12));
    if (Math.abs(zoomT - zoomPath) < 1e-5) zoomPath = zoomT;
    zoomR = Math.max(0, zoomPath);
    tele = Math.pow(30, Math.max(0, -zoomPath));
    magnification.style.display = peek && tele > 1.02 ? "" : "none";
    const label = `\u00d7${tele < 10 ? tele.toFixed(1).replace(/\.0$/, "") : Math.round(tele)}`;
    if (magnification.textContent !== label) magnification.textContent = label;
    EYE[0] = EYE0[0] - zoomR * Math.sin(yaw);
    EYE[2] = EYE0[2] - zoomR * Math.cos(yaw);
    return peek;
  }

  // 조작 콘솔(바닥) · 패널(화면) — 콘솔은 배경 보기 중에만 그리고, 패널은 문턱을 넘을 때만 클래스를 바꾼다(매 프레임 DOM 갱신 없음)
  function updateUfo(peek) {
    ufoConsole.setVisible(peek);
    if (peek) {
      const B = basis(), F = viewFocal();
      ufoConsole.place((w) => {
        const q = sub(w, EYE), z = dot3(q, B.fwd);
        return z < 0.03 ? null : [cx + F * dot3(q, B.right) / z, cy - F * dot3(q, B.up) / z, z];
      }, B);
    }
    if (peek && !ufoArmed && zoomR >= PANEL_OFF_R) ufoArmed = true;
    const want = peek && ufoArmed && (ufoPanel.on ? zoomR <= PANEL_OFF_R && tele <= 1.02 : zoomR < PANEL_ON_R && tele <= 1.001);
    if (want) {
      ufoPanel.setCurrent(outdoor ? "earth" : INDOOR_BG === "space" ? "space" : "pink");   // 바뀔 때만 DOM 을 건드린다(bgpanel.js)
      // 우주 사진은 처음 고를 때 받는다 — 받는 동안 칸에 표시(그려 만든 우주 모드는 사진이 없다)
      const loading = INDOOR_BG === "space" && !outdoor && SPACE_MODE !== "shader" && !spaceTex.map;
      ufoPanel.setChip("space", loading ? "불러오는 중…" : "길게 누르면 워프");
    }
    ufoPanel.set(want);
    ufoPanel.setHint(peek ? Math.max(0, Math.min(1, 1 - 2.5 * (1 - zoomR / PEEK_START_R))) : 0);
  }
  function hideUfo() { ufoPanel.set(false); ufoPanel.setHint(0); ufoConsole.setVisible(false); }

  // 두 손가락 줌 — 배경 보기 중에만(그 밖엔 카드 · 페이지 조작이 우선). 브라우저 확대를 막으려 passive: false
  const touchDist = (e) => Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
  const pinchMark = (on) => { if (on) document.documentElement.dataset.bgPinch = "1"; else delete document.documentElement.dataset.bgPinch; };
  let pinchEndT = 0;
  window.addEventListener("touchstart", (e) => {
    if (e.touches.length !== 2 || !document.documentElement.classList.contains("bg-peek")) return;
    pinch = { distance: touchDist(e) };
    ufoArmed = true;   // 손가락으로 줌을 시작하면 그때부터는 문턱대로 패널을 띄운다
    clearTimeout(pinchEndT);
    pinchMark(true);   // bgpeek.js 가 이 표시가 있는 동안 「누르면 되돌아가기」를 하지 않는다
  }, { passive: true, signal: life.signal });
  window.addEventListener("touchmove", (e) => {
    if (!pinch || e.touches.length !== 2) return;
    e.preventDefault();
    const distance = touchDist(e);
    zoomT = Math.max(-1, Math.min(ZOOM_R_MAX, zoomT + (pinch.distance - distance) / Math.max(1, W) * ZOOM_PER_SCREEN));
    pinch.distance = distance;
  }, { passive: false, signal: life.signal });
  const endPinch = (e) => {
    if (!pinch || e.touches.length >= 2) return;
    pinch = null;
    pinchEndT = setTimeout(() => pinchMark(false), 450);   // 손을 뗄 때 따라오는 click 까지 막는다
  };
  window.addEventListener("touchend", endPinch, { passive: true, signal: life.signal });
  window.addEventListener("touchcancel", endPinch, { passive: true, signal: life.signal });

  // 기울임 → 무늬에 줄 가속도(세계 좌표). roll 은 0.15초 저역 통과로 손떨림을 거른다
  let rollS = 0;
  function tiltAccel(dt) {
    const tl = gyroTilt();
    const target = tl ? tl.roll * tl.upright : 0;
    rollS += (target - rollS) * (1 - Math.exp(-dt / 0.15));
    const s = Math.sign(rollS) * Math.max(0, Math.abs(Math.sin(rollS)) - TILT_DEAD) * TILT_G;
    if (!s) return null;
    const B = basis();   // right = 화면 오른쪽의 수평 방향(카메라는 기울지 않는다)
    return [B.right[0] * s, -Math.abs(s) * TILT_DOWN, B.right[2] * s];
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
    const moving = stepPieces(pieces, dt, tiltAccel(dt));
    placePieces();
    updateUfo(peek);
    if ((!reducedMotion.matches && t - themeStart < THEME_MS) || (Math.abs(yaw - drawnYaw) + Math.abs(pitch - drawnPitch)) * tele + Math.abs(zoomR - drawnR) + Math.abs(tele - drawnTele) > 2e-4 || (pitch - Math.atan((H - cy) / viewFocal()) < (GROUND.kind === "mountain" ? 12 * DEG : 0) && t - lastGL > 1000 / (peek ? 60 : 30) - 2) || t - lastGL > CLOUD_MS || (T_SPEED > 1 && outdoor) || (INDOOR_BG === "space" && !outdoor && WARP_FIXED == null && !reducedMotion.matches && spaceT0 !== null && (voyageBeta((performance.now() - spaceT0) / 1000) > 0 || performance.now() - spaceT0 < VOYAGE_END * 1000) && t - lastGL > 1000 / (peek ? 60 : 30) - 2)) draw();
    raf = requestAnimationFrame(frame);
  }

  function start() {
    if (!stopped) return;
    stopped = false;
    startAbsolute();   // 두 보기 모두 실제 방위를 쓴다(자이로 듣기도 같이 시작)
    tPrev = lastFrame = performance.now();
    raf = requestAnimationFrame(frame);
  }
  function stop() { stopped = true; cancelAnimationFrame(raf); raf = 0; hideUfo(); }

  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); stop(); });
  canvas.addEventListener("webglcontextrestored", () => {
    try { init(); resize(window.innerWidth, window.innerHeight); if (!isPaused()) start(); } catch { /* 복구 실패 — 마지막 화면 없이 바탕색만 */ }
  });
  document.addEventListener(BGVIEW_EVENT, (e) => {
    outdoor = e.detail === "outdoor";
    useViewProgram();
    // 시선 · 기준점은 두 보기가 같다(updateView) — 여기서는 화면 폭 각도만(시안 bgsize=window 일 때만 바깥이 다르다)
    if (W) gl.uniform1f(U.uF, viewFocal());
    updateAstro(true);
    draw();
  }, { signal: life.signal });
  const themeObs = new MutationObserver(() => draw()); themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  function finishThemeMotion() { themeStart = -Infinity; draw(); }
  reducedMotion.addEventListener("change", finishThemeMotion);

  function resize(w, h) {
    themeStart = -Infinity;
    W = w; H = h; phone = W <= 767;
    dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    // 기존 SVG 투영(bgdome.js domeGeometry)과 같은 초점 · 중심 — 정면에서 보면 테두리가 같은 자리
    focal = phone ? W * 1.25 : W * 0.76;
    focalOut = SIZE_MODE === "window" ? (W / 2) / Math.tan(WINDOW_HFOV / 2 * DEG) : focal;
    const c = Math.cos(BASE_PITCH), s = Math.sin(BASE_PITCH), eyeY = EYE0[1], eyeZ = EYE0[2];   // 실내 구도는 줌 0(중심) 기준
    const rimY = H - (phone ? 68 : 130);
    cx = W / 2;
    cyIndoor = rimY - focal * (eyeY * c + (1 - eyeZ) * s) / (-eyeY * s + (1 - eyeZ) * c);
    cy = gyroAbs() || gyroView() ? H / 2 : cyIndoor;
    gl.uniform2f(U.uRes, canvas.width, canvas.height); gl.uniform1f(U.uDpr, dpr);
    gl.uniform2f(U.uC, cx, cy); gl.uniform1f(U.uF, viewFocal());
    draw();
    placePieces();
  }

  /** 흔들기 — 조각마다 제각각 튀어 나가고, 다 가라앉을 때까지 보는 방향을 새 정면으로 옮긴다 */
  function shake(power = 1) {
    if (stopped) return;
    lastShake = performance.now();
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
    // 폰에서 3초마다 상태를 경고 로그로 남긴다(확인용 서버의 오류 비콘이 PC 로 넘긴다)
    setInterval(() => {
      const r = (v) => (v == null ? null : Math.round(v / DEG));
      const site = outdoorSite();
      console.warn("[bgdome] 상태 " + JSON.stringify({
        outdoor, site: !!site, view: [r(yaw), r(pitch)],
        abs: gyroAbs() && [r(gyroAbs().yaw), r(gyroAbs().pitch)],
        sun: astro && [r(astro.sunAz), r(astro.sunAlt)], moon: astro && [r(astro.moonAz), r(astro.moonAlt)],
        sets: slotA + (slotB ? ">" + slotB : ""), ev: gyroDebug, scr: (screen.orientation && screen.orientation.angle) ?? window.orientation ?? null,
      }));
    }, 3000);
    window.__bgdome = { get state() { return { ground: GROUND, astro, sets: slotA + (slotB ? "→" + slotB : ""), outdoor, yaw: yaw / DEG, pitch: pitch / DEG, zoom: zoomR, magnification: tele, moonDiameterCSS: SIZE_MODE === "eye" ? MOON_CSS_DIAMETER * tele : 2 * viewFocal() * SUN_MOON_R[1] * DEG, themeProgress: Math.min(1,(performance.now()-themeStart)/THEME_MS), albedoOn, terrain: releaseGround.terrain?.metrics, zoomTarget: zoomT, eye: EYE.slice(), cy, stopped, gyro: gyroView(), abs: gyroAbs(), speed: Math.max(...pieces.map((p) => len3(p.v))) }; } };
  }

  return {
    resize,
    shake,
    setPaused(stop_) { if (stop_) stop(); else start(); },
    destroy() { stop(); reducedMotion.removeEventListener("change", finishThemeMotion); textureEpoch++; if (themeFrame) gl.deleteTexture(themeFrame); if (releaseGround) releaseGround(); canvas.remove(); air.remove(); magnification.remove(); ufoPanel.remove(); life.abort(); themeObs.disconnect(); try { gl.getExtension("WEBGL_lose_context")?.loseContext(); } catch { /* 이미 잃음 */ } },
  };
}
