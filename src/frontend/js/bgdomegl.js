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
// 평소엔 폰을 돌린 양의 35% 만 따라 돈다(카드를 보는 중엔 배경이 크게 휘돌지 않게). 해상도는 기기 배율 1.5 까지만.

import { startGyro, gyroView, rebase, startAbsolute, gyroAbs, gyroDebug, gyroTilt } from "./bggyro.js";
import { BGVIEW_EVENT } from "./bgview.js";
import { outdoorSite } from "./bgsite.js";
import { sunPosition, moonPosition, moonIllumination, dirOf, horizonToEquatorial } from "./bgastro.js";

const DEG = Math.PI / 180;
// 돔(반지름 1) 안 눈 위치 [동, 위, 북] — bgdome.js 와 같다. 수평은 돔 중심(0, 0), 높이 0.24(11-04 운영자 결정 — 전엔 남쪽 0.42 에 있어
// 머리 위를 봐도 돔 꼭대기가 북쪽 29° 에 보였고 동 · 서 경도선이 23° 씩 북쪽으로 쏠렸다). 수평이 중심이면 경도선 = 실제 방위선, 돔 꼭대기 = 천정.
const EYE0 = [0, 0.24, 0];
// 줌(11-04 운영자 요청): 「배경 보기」(html.bg-peek) 중 두 손가락으로 오므리면 보는 방향의 반대쪽으로 r 만큼 물러서고(넓게), 벌리면 r 이 줄어 중심으로 돌아온다(크게).
// 눈 = EYE0 − r · (보는 방향의 수평 성분), 높이는 그대로. r 은 0 ~ ZOOM_R_MAX(돔 반지름 1). 새로고침하면 0(중심).
const ZOOM_R_MAX = 0.6;
const ZOOM_PER_SCREEN = 1.5;   // 두 손가락 거리가 화면 폭만큼 줄면 r 이 이만큼 는다
const EYE = EYE0.slice();      // 지금 눈 위치 — 프레임마다 갱신
const BASE_PITCH = 28 * DEG;
const GAIN_IDLE = 0.35, GAIN_PEEK = 1;
const PITCH_MIN = -55 * DEG, PITCH_MAX = 88 * DEG;
const CLOUD_MS = 160;                  // 카메라가 멈춰 있을 때 구름 흐름 다시 그리기 간격
const MAX_DPR = 1.5;
const QS = new URLSearchParams(window.location.search);
const DEBUG = QS.has("bgdebug");
// 확인용(?bgdebug 와 함께): bgtime = 시작 시각(ISO), bgspeed = 시간 배속 — 노을 · 밤을 기다리지 않고 본다
// ?bg=normal(운영자 명명) = 가속 없이 지금 시각 — 이 두 값을 주소에 같이 붙여도 무시한다
const NORMAL = QS.get("bg") === "normal";
const T_START = DEBUG && !NORMAL && QS.get("bgtime") ? Date.parse(QS.get("bgtime")) : NaN;
const T_SPEED = DEBUG && !NORMAL && QS.get("bgspeed") ? Number(QS.get("bgspeed")) || 1 : 1;
// 확인용(?bgdebug 와 함께): bgmoon = 달 위상 0 ~ 1(0 삭 · 0.25 상현 · 0.5 망 · 0.75 하현) — 달을 정남 고도 35° 에 두고 그 위상으로 비춘다(실제 해 위치는 그대로)
const MOON_TEST = DEBUG && QS.get("bgmoon") != null && Number.isFinite(Number(QS.get("bgmoon"))) ? ((Number(QS.get("bgmoon")) % 1) + 1) % 1 : null;
const T_REAL0 = Date.now();
const nowMs = () => (Number.isFinite(T_START) ? T_START + (Date.now() - T_REAL0) * T_SPEED : Date.now());

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

const VS = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

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
uniform vec3 uSunDir, uMoonDir, uMoonSun;   // uMoonSun = 달을 비추는 해 방향(평소 = uSunDir, 위상 시험 때만 다름)
uniform vec4 uSunShape, uMoonShape;   // 천체 접평면의 위쪽 방향(xyz), 지평선 눌림 세기(w)
// 고도 · 남중 · 위상에 따른 색과 세기는 JS 에서 초당 한 번만 계산한다
uniform vec3 uSunCol, uSunGlow, uSunHorizon, uMoonCol;
uniform vec4 uSunAir;   // 근접 번짐, 구름 산란, 저고도 온기, 원반 노출
uniform vec4 uSolar;   // 낮 산란, 지평 대기광, 해 가시성, 천정의 깊이
uniform vec4 uLunar;   // 달 가시성, 원반 불투명도, 빛 번짐 지수, 빛 번짐 세기
uniform float uMoonLight, uStarGain, uEarthshine;
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
vec4 skySet(sampler2D s, sampler2D cl, mat3 M, vec3 O, mat3 CM, vec3 CO, float u, float v, float el) {
  vec3 c = clamp(M * textureLod(s, vec2(u + uTime / 2844.444, v), 0.0).rgb + O, 0.0, 1.0);
  vec4 n = textureLod(cl, vec2(u + uTime / 1280.0, v), 0.0);
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
// 번짐은 원반보다 완만하게 눌리고 가로로 살짝 퍼진다. 원반 밖에서도 분모가 작아지지 않는다.
float discGlow(float facing, vec3 d, vec4 shape) {
  float y = dot(d, shape.xyz);
  return clamp(facing + shape.w * (0.06 * (1.0 - facing * facing) - 0.26 * y * y), 0.0, 1.0);
}

// 달: 장면에 맞춰 실제보다 크게(각반지름 1.6°). 복원한 구면에서 해 방향을 써 위상 · 표면도 함께 눌린다.
vec4 moon(vec3 t, float facing, float pxAng) {
  const float R = 1.6 * D;
  float rr = length(t) / R;
  float a = clamp((1.0 - rr) * R / pxAng + 0.5, 0.0, 1.0) * step(0.0, facing);
  if (a <= 0.0) return vec4(0.0);
  vec3 k = t / R;
  vec3 n = k - uMoonDir * sqrt(max(1.0 - dot(k, k), 0.0));   // 보이는 반구의 표면 법선(관측자 쪽)
  float lit = smoothstep(-0.03, 0.06, dot(n, uMoonSun));
  // 바다(어두운 무늬): 표면 위치로 만든 부드러운 얼룩 — 달 자체에 붙어 있다
  vec3 s = n * 3.1;
  float maria = h3(floor(s)) * 0.5 + h3(floor(s * 2.0)) * 0.3 + h3(floor(s * 4.0)) * 0.2;
  maria = smoothstep(0.35, 0.8, maria);
  float limb = 0.82 + 0.18 * sqrt(max(1.0 - rr * rr, 0.0));
  vec3 col = uMoonCol * (1.0 - 0.22 * maria) * limb;
  return vec4(col, a * lit);   // a = 밝은 면만. 어두운 면은 sky() 가 밤에만 옅게(지구 반사광) 칠한다
}
float moonDisc(vec3 t, float facing, float pxAng) {
  const float R = 1.6 * D;
  float rr = length(t) / R;
  return clamp((1.0 - rr) * R / pxAng + 0.5, 0.0, 1.0) * step(0.0, facing);
}

vec3 sky(vec3 d, float pxAng) {
  float el = asin(clamp(d.y, -1.0, 1.0));
  float u = atan(d.x, d.z) / TAU * 3.0;
  float v = clamp((70.0 * D - el) / (82.0 * D), 0.002, 0.998);
  if (uTex < 0.5) return uSkyBase;
  vec4 A = skySet(uSky, uCloud, uSkyM, uSkyO, uCldM, uCldO, u, v, el);
  vec4 B = uMix > 0.0 ? skySet(uSky2, uCloud2, uSkyM2, uSkyO2, uCldM2, uCldO2, u, v, el) : A;
  vec3 c = mix(A.rgb, B.rgb, uMix);
  if (uOut < 0.5) return c;
  float cloud = mix(A.a, B.a, uMix);
  float above = smoothstep(-0.004, 0.006, d.y);   // 지평선 아래(돔 벽 너머)에는 해 · 달 · 별이 없다

  float sd = dot(d, uSunDir), md = max(dot(d, uMoonDir), 0.0);
  float g = max(dot(vec3(d.x, 0.0, d.z) / max(length(d.xz), 1e-4), uSunHorizon), 0.0);
  float low = exp(-max(el, 0.0) / (14.0 * D));
  // 낮: 천정은 깊은 파랑, 해 쪽은 희푸른 산란광. 사진의 구름 결은 남긴다
  float clear = 1.0 - 0.7 * cloud;
  c *= 1.0 - uSolar.w * max(d.y, 0.0) * (1.0 - 0.5 * g) * clear;
  float forward = max(sd, 0.0);
  c += (vec3(0.72, 0.85, 1.0) - c) * uSolar.x * (0.04 + 0.22 * forward * forward + 0.1 * g * low) * clear;
  // 달 없는 밤의 사진 바탕은 더 어두운 남청색. 박명 이미지가 섞이는 -6° ~ -12°와 같은 곡선이다
  c = mix(c, c * vec3(0.42, 0.54, 0.82), uNight);
  // 달이 높고 보름에 가까울수록 밤하늘을 남청색으로 아주 조금 들어 올린다
  c += vec3(0.024, 0.041, 0.085) * uMoonLight * (0.45 + 0.55 * md * md) * (1.0 - 0.65 * cloud) * above;

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
      float moonGlare = 1.0 - uMoonLight * md * md * 0.65;
      c += vec3(0.95, 0.93, 1.0) * star * uStarGain * moonGlare * (1.0 - cloud) * above;
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
  vec3 mt = discTangent(d, uMoonDir, uMoonShape, 1.6 * D);
  float mf = dot(d, uMoonDir);
  vec4 m = moon(mt, mf, pxAng);
  float mvis = above * uLunar.x * (1.0 - 0.85 * cloud);
  c = mix(c, vec3(0.025, 0.034, 0.055), moonDisc(mt, mf, pxAng) * uEarthshine * mvis);   // 초승 · 그믐의 지구 반사광도 밤에만 보인다
  c = mix(c, m.rgb, m.a * uLunar.y * mvis);
  c += uMoonCol * pow(discGlow(md, d, uMoonShape), uLunar.z) * uLunar.w * mvis;

  // 각반지름 1.2°와 지평선 눌림 유지. 흰금색 핵 → 노란 테, 번짐은 원반 밖으로 이어진다.
  const float sunR = sin(1.2 * D);
  float sr;
  if (uSunShape.w > 0.0) sr = length(discTangent(d, uSunDir, uSunShape, sunR)) / sunR;
  else sr = sqrt(max(2.0 * (1.0 - sd), 0.0)) / sunR;
  float disc = clamp((1.0 - sr) * sunR / pxAng + 0.5, 0.0, 1.0) * step(0.0, sd);
  float limb = smoothstep(0.35, 1.0, sr);
  vec3 core = mix(mix(vec3(1.0, 0.985, 0.94), vec3(1.0, 0.975, 0.87), warm), uSunCol, limb);
  // 구름 알파는 합성 강도를 뺀 밀도로 복원한다. 짙은 구름은 직사광을 가리고 산란광은 남긴다.
  float density = clamp(cloud / max(uCldA, 0.001), 0.0, 1.0);
  float direct = (1.0 - density) * (1.0 - density);
  float sg = discGlow(max(sd, 0.0), d, uSunShape);
  float inner = pow(sg, mix(1800.0, 450.0, warm));
  float scatter = pow(sg, mix(180.0, 48.0, warm));
  float outer = pow(sg, mix(48.0, 12.0, warm));
  // 저고도에서 반치폭 약 3° / 10° / 20°. 얇은 구름 가장자리를 밝히고 짙은 구름은 직사만 가린다.
  float edge = 4.0 * density * (1.0 - density);
  float corona = inner * uSunAir.x * (1.0 - 0.75 * density) * uSolar.z;
  float halo = scatter * uSunAir.y * (0.65 + 0.55 * edge) * uSolar.z;
  float air = outer * (0.045 + 0.6 * warm) * max(uSolar.z, uSolar.y);
  vec3 light = core * mix(uSunAir.w, 1.8, limb) * disc * direct * uSolar.z * above
    + mix(uSunGlow, vec3(1.0, 0.92, 0.68), 0.72 * warm) * corona
    + uSunGlow * (halo + air);   // 대기 산란은 지평선 아래까지 연결하고 원반만 above로 가린다.
  // 공통 분모로 빛의 색 비율을 유지한다. 채널별 흰색 포화를 피하고 사진의 구름 계조도 남긴다.
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
  float sunFade = mix(1.0, 0.20, smoothstep(cos(6.0 * D), cos(2.0 * D), dot(ray, uSunDir)) * uSolar.z);
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
  vec3 col = sky(d, 1.0 / (uF * uDpr));   // 기기 픽셀 하나의 각도
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
  if (uOut > 0.5) col = compassHUD(col, d, asin(clamp(d.y, -1.0, 1.0)), atan(d.x, d.z), 1.0 / (uF * uDpr));

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

  let prog = null, U = {}, sets = {}, slotA = null, slotB = null, lastAstro = 0, astro = null;
  let W = 0, H = 0, dpr = 1, focal = 1, cx = 0, cy = 0, cyIndoor = 0, phone = true;
  let yaw = 0, pitch = BASE_PITCH, gain = GAIN_IDLE, drawnYaw = NaN, drawnPitch = NaN, lastGL = 0, lastFrame = 0, tPrev = 0;
  let zoomR = 0, zoomT = 0, drawnR = NaN, pinch = null;   // 줌(뒤로 물러선 거리) — 지금 값 · 목표 · 마지막으로 그린 값 · 두 손가락 시작 상태
  let raf = 0, stopped = true, settling = false, lastShake = 0, theme = null, t0 = performance.now();
  // 바깥 보기: 장면 +z = 북, +x = 동. 카메라 좌우 = 실제 방위, 위아래 = 실제 기울기(기준 자세 · 35% 축소 없음). 나침반이 없으면 남쪽을 본다
  let outdoor = false;
  const OUT_DEFAULT_YAW = Math.PI;
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
    gl.uniform1i(U.uSky, 0); gl.uniform1i(U.uCloud, 1); gl.uniform1i(U.uSky2, 2); gl.uniform1i(U.uCloud2, 3);
    gl.uniform1f(U.uMix, 0); gl.uniform1f(U.uOut, 0); gl.uniform1f(U.uNight, 0);
    gl.uniformMatrix3fv(U.uEqM, false, new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1]));
    sets = {}; slotA = slotB = null; astro = null;
    loadSet("day");
    theme = null;
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
        gl.activeTexture(gl.TEXTURE7);   // 올리는 동안만 빈 칸(7)을 쓴다 — 0 ~ 3 칸의 연결을 건드리지 않게
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
      const alt = astro.sunAlt / DEG;
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
    const earlier = sunPosition(new Date(+t - 5 * 60000), site.lat, site.lon).alt;
    const rising = later > sun.alt;   // 이미지 선택은 그대로, 5분 뒤가 더 높으면 아침
    const smooth = (a, b, x) => { const v = Math.min(1, Math.max(0, (x - a) / (b - a))); return v * v * (3 - 2 * v); };
    const blend = (a, b, v) => a.map((c, i) => c + (b[i] - c) * v);
    const alt = sun.alt / DEG;
    const night = 1 - smooth(-12, -6, alt);
    // 남중 전후에도 색을 매끄럽게 잇는다. 이미지의 아침 · 저녁 판정과 별개로 앞뒤 5분 고도차를 쓴다
    const dawn = smooth(-0.04, 0.04, (later - earlier) / DEG);
    const day = smooth(-2, 12, alt), warm = 1 - smooth(10, 28, alt);
    // 오늘 적위로 남중 고도를 구한다. 계절마다 달라지는 최고 고도에 맞춰 천정의 파랑을 깊게 한다
    const phi = site.lat * DEG;
    const dec = Math.asin(Math.max(-1, Math.min(1, Math.sin(phi) * Math.sin(sun.alt) + Math.cos(phi) * Math.cos(sun.alt) * Math.cos(sun.az))));
    const maxAlt = Math.PI / 2 - Math.abs(phi - dec);
    const noon = smooth(0.78, 0.995, Math.max(0, Math.sin(sun.alt)) / Math.max(0.05, Math.sin(maxAlt))) * day;
    const dusk = smooth(-12, -2, alt) * (1 - smooth(4, 16, alt));
    // 흰금색 핵을 둘러싼 노란 테. 여명은 복숭아 · 연금, 일몰은 짙은 금빛 산란광이다.
    const sunLow = blend([1, 0.81, 0.38], [1, 0.85, 0.59], dawn);
    const sunHigh = blend([1, 0.985, 0.955], [1, 0.96, 0.88], (1 - dawn) * (1 - noon) * 0.3);
    const sunCol = blend(sunHigh, sunLow, warm);
    const sunGlow = blend([1, 0.97, 0.9], blend([1, 0.74, 0.23], [1, 0.81, 0.52], dawn), warm);
    let moonSun = dirOf(sun.alt, sun.az), fraction = moonIllumination(t).fraction;
    if (MOON_TEST != null) {
      // 위상 p → 해-달 이각 ψ = 2πp. 차오르는 동안(p < 0.5) 해는 달의 서쪽 — 북반구에서 오른쪽이 밝다
      moon.alt = 35 * DEG; moon.az = Math.PI;
      const m = dirOf(moon.alt, moon.az), up = [0, 1, 0];
      const w = [up[1] * m[2] - up[2] * m[1], up[2] * m[0] - up[0] * m[2], up[0] * m[1] - up[1] * m[0]];   // up × m = 달 자리의 서쪽
      const wl = Math.hypot(...w), psi = 2 * Math.PI * MOON_TEST;
      moonSun = m.map((c, i) => Math.cos(psi) * c + Math.sin(psi) * w[i] / wl);
      fraction = (1 - Math.cos(psi)) / 2;
    }
    const moonAlt = moon.alt / DEG;
    const moonUp = smooth(-2, 0.3, moonAlt), moonLow = 1 - smooth(0, 24, moonAlt);
    const moonContrast = 1 - smooth(-8, 10, alt);
    const moonLight = night * fraction * fraction * moonUp * smooth(0, 50, moonAlt);
    const moonCol = blend(blend([0.94, 0.965, 1], [1, 0.62, 0.28], moonLow), [0.89, 0.945, 1], day * 0.8);
    astro = { sunAlt: sun.alt, sunAz: sun.az, moonAlt: moon.alt, moonAz: moon.az, rising, fraction, noon, moonLight, time: t.toISOString() };
    gl.uniform1f(U.uOut, 1);
    gl.uniform1f(U.uNight, night);
    gl.uniform3fv(U.uSunCol, sunCol);
    gl.uniform3fv(U.uSunGlow, sunGlow);
    gl.uniform4f(U.uSunAir, 0.5 + 1.9 * warm, 0.12 + 0.8 * warm * (1 - 0.18 * dawn), warm, 18 + 8 * warm);
    gl.uniform3fv(U.uSunHorizon, [Math.sin(sun.az), 0, Math.cos(sun.az)]);
    gl.uniform4f(U.uSolar, day, dusk, smooth(-1.5, 0.5, alt), day * (0.045 + 0.055 * noon));
    gl.uniform3fv(U.uMoonCol, moonCol);
    gl.uniform4f(U.uLunar, moonUp, 0.22 + 0.78 * moonContrast, 900 - 660 * moonLow,
      Math.pow(fraction, 0.7) * moonContrast * (0.055 + 0.085 * moonLow));
    gl.uniform1f(U.uMoonLight, moonLight);
    gl.uniform1f(U.uStarGain, night * (1 - 0.68 * moonLight));
    gl.uniform1f(U.uEarthshine, night * (0.72 + 0.12 * (1 - fraction)));
    gl.uniform3fv(U.uSunDir, dirOf(sun.alt, sun.az));
    gl.uniform3fv(U.uMoonDir, dirOf(moon.alt, moon.az));
    gl.uniform3fv(U.uMoonSun, moonSun);
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

  function applyTheme() {
    const name = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    if (name === theme) return;
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
    if (gl.isContextLost() || !W) return;
    applyTheme();
    updateAstro(false);
    chooseSets();
    const B = basis();
    gl.uniform3fv(U.uFwd, B.fwd); gl.uniform3fv(U.uRight, B.right); gl.uniform3fv(U.uUp, B.up);
    gl.uniform3fv(U.E, EYE); drawnR = zoomR;
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
    gain += ((peek || outdoor ? GAIN_PEEK : GAIN_IDLE) - gain) * (1 - Math.exp(-dt / 0.35));
    let tYaw, tPitch;
    if (outdoor) {
      const a = gyroAbs();
      const target = a ? a.yaw : OUT_DEFAULT_YAW;
      tYaw = yaw + Math.atan2(Math.sin(target - yaw), Math.cos(target - yaw));   // 북쪽(±180°)을 넘을 때 한 바퀴 돌지 않게
      tPitch = Math.max(PITCH_MIN, Math.min(PITCH_MAX, a ? a.pitch : BASE_PITCH));
    } else {
      if (settling) rebase();   // 섞이는 동안은 매번 지금 자세를 정면으로 → 화면이 천천히 정면으로 돌아온다
      const g = gyroView();
      tYaw = g ? g.yaw * gain : 0;
      tPitch = Math.max(PITCH_MIN, Math.min(PITCH_MAX, BASE_PITCH + (g ? g.pitch * gain : 0)));
    }
    const k = 1 - Math.exp(-dt / (settling ? 0.55 : 0.08));
    yaw += (tYaw - yaw) * k;
    pitch += (tPitch - pitch) * k;
    if (!peek && !pinch) zoomT = 0;   // 배경 보기를 닫으면 중심으로 돌아온다
    zoomR += (zoomT - zoomR) * (1 - Math.exp(-dt / 0.12));
    if (Math.abs(zoomT - zoomR) < 1e-4) zoomR = zoomT;
    EYE[0] = EYE0[0] - zoomR * Math.sin(yaw);
    EYE[2] = EYE0[2] - zoomR * Math.cos(yaw);
    return peek;
  }

  // 두 손가락 줌 — 배경 보기 중에만(그 밖엔 카드 · 페이지 조작이 우선). 브라우저 확대를 막으려 passive: false
  const touchDist = (e) => Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
  const pinchMark = (on) => { if (on) document.documentElement.dataset.bgPinch = "1"; else delete document.documentElement.dataset.bgPinch; };
  let pinchEndT = 0;
  window.addEventListener("touchstart", (e) => {
    if (e.touches.length !== 2 || !document.documentElement.classList.contains("bg-peek")) return;
    pinch = { d0: Math.max(1, touchDist(e)), r0: zoomT };
    clearTimeout(pinchEndT);
    pinchMark(true);   // bgpeek.js 가 이 표시가 있는 동안 「누르면 되돌아가기」를 하지 않는다
  }, { passive: true });
  window.addEventListener("touchmove", (e) => {
    if (!pinch || e.touches.length !== 2) return;
    e.preventDefault();
    const r = pinch.r0 + (pinch.d0 - touchDist(e)) / Math.max(1, W) * ZOOM_PER_SCREEN;
    zoomT = Math.max(0, Math.min(ZOOM_R_MAX, r));
  }, { passive: false });
  const endPinch = (e) => {
    if (!pinch || e.touches.length >= 2) return;
    pinch = null;
    pinchEndT = setTimeout(() => pinchMark(false), 450);   // 손을 뗄 때 따라오는 click 까지 막는다
  };
  window.addEventListener("touchend", endPinch, { passive: true });
  window.addEventListener("touchcancel", endPinch, { passive: true });

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
    if (settling && !moving && t - lastShake > 400) settling = false;   // 다 가라앉았다 — 이 자세가 새 기준으로 남는다
    placePieces();
    if (Math.abs(yaw - drawnYaw) + Math.abs(pitch - drawnPitch) + Math.abs(zoomR - drawnR) > 2e-4 || t - lastGL > CLOUD_MS || (T_SPEED > 1 && outdoor)) draw();
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
  document.addEventListener(BGVIEW_EVENT, (e) => {
    outdoor = e.detail === "outdoor";
    // 기준점(폰 뒷면 방향이 맺히는 자리): 실내 = 테두리가 화면 아래에 오도록 위쪽 40% 쯤, 바깥 = 화면 정가운데
    // — 바깥 보기는 실제 기울기를 그대로 쓰므로(AR 처럼) 폰을 해 쪽으로 겨누면 해가 한가운데 와야 한다(2026-11-04 운영자 지시)
    cy = outdoor ? H / 2 : cyIndoor;
    if (W) gl.uniform2f(U.uC, cx, cy);
    settling = false;
    if (outdoor) startAbsolute();
    else { yaw = Math.atan2(Math.sin(yaw), Math.cos(yaw)); rebase(); }   // 실내로 돌아오면 지금 자세가 정면
    updateAstro(true);
    draw();
  });
  new MutationObserver(() => draw()).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  function resize(w, h) {
    W = w; H = h; phone = W <= 767;
    dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    // 기존 SVG 투영(bgdome.js domeGeometry)과 같은 초점 · 중심 — 정면에서 보면 테두리가 같은 자리
    focal = phone ? W * 1.25 : W * 0.76;
    const c = Math.cos(BASE_PITCH), s = Math.sin(BASE_PITCH), eyeY = EYE0[1], eyeZ = EYE0[2];   // 실내 구도는 줌 0(중심) 기준
    const rimY = H - (phone ? 68 : 130);
    cx = W / 2;
    cyIndoor = rimY - focal * (eyeY * c + (1 - eyeZ) * s) / (-eyeY * s + (1 - eyeZ) * c);
    cy = outdoor ? H / 2 : cyIndoor;
    gl.uniform2f(U.uRes, canvas.width, canvas.height); gl.uniform1f(U.uDpr, dpr);
    gl.uniform2f(U.uC, cx, cy); gl.uniform1f(U.uF, focal);
    draw();
    placePieces();
  }

  /** 흔들기 — 조각마다 제각각 튀어 나가고, 다 가라앉을 때까지 보는 방향을 새 정면으로 옮긴다 */
  function shake(power = 1) {
    if (stopped) return;
    lastShake = performance.now();
    settling = !outdoor;   // 바깥 보기는 정면이 실제 방위라 기준을 옮기지 않는다(무늬만 섞인다)
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
    window.__bgdome = { get state() { return { astro, sets: slotA + (slotB ? "→" + slotB : ""), outdoor, yaw: yaw / DEG, pitch: pitch / DEG, zoom: zoomR, eye: EYE.slice(), gain, settling, stopped, gyro: gyroView(), abs: gyroAbs(), speed: Math.max(...pieces.map((p) => len3(p.v))) }; } };
  }

  return {
    resize,
    shake,
    setPaused(stop_) { if (stop_) stop(); else start(); },
    destroy() { stop(); canvas.remove(); air.remove(); },
  };
}
