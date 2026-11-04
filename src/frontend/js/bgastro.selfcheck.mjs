// bgastro.selfcheck.mjs — node src/frontend/js/bgastro.selfcheck.mjs
// 기준값 ① 같은 간략식을 쓰는 공개 라이브러리(SunCalc)의 시험값(2013-03-05 00:00 UTC, 북위 50.5 · 동경 30.5)
//        ② 상식으로 확인되는 값(춘분 정오 해 고도 ≈ 90° - 위도, 보름 · 그믐의 밝은 면 비율, 해 뜨는 방향 ≈ 동쪽)

import { sunPosition, moonPosition, moonIllumination, dirOf, horizonToEquatorial } from "./bgastro.js";

let fail = 0;
const DEG = 180 / Math.PI;
function near(name, got, want, tol) {
  const ok = Math.abs(got - want) <= tol;
  if (!ok) fail++;
  console.log(`${ok ? "ok  " : "FAIL"} ${name}: ${got.toFixed(6)} (기대 ${want.toFixed(6)} ± ${tol})`);
}

// ① 기준 라이브러리 시험값(라디안, 방위는 남 기준)
const t = new Date(Date.UTC(2013, 2, 5)), lat = 50.5, lon = 30.5;
const sun = sunPosition(t, lat, lon);
near("해 방위(남 기준)", sun.azS, -2.5003175907168385, 1e-9);
near("해 고도", sun.alt, -0.7000406838781611, 1e-9);
const moon = moonPosition(t, lat, lon);
near("달 방위(남 기준)", moon.azS, -0.9783999522438226, 1e-9);
near("달 고도", moon.alt, 0.014551482243892251, 1e-9);
near("달 거리(km)", moon.dist, 364121.37256256194, 1e-6);
const ill = moonIllumination(t);
near("달 밝은 면 비율", ill.fraction, 0.4848068202456373, 1e-9);
near("달 위상", ill.phase, 0.7548368838538762, 1e-9);
near("달 밝은 쪽 각도", ill.angle, 1.6732942678578346, 1e-9);

// ② 상식 확인
// 서울(37.57, 126.98) 2026-03-20 춘분 무렵 남중 = 12:40 KST(03:40 UTC — 경도 차 +32분, 균시차 +7분) → 고도 ≈ 52.3°, 방위 ≈ 남(180°)
const noon = sunPosition(new Date(Date.UTC(2026, 2, 20, 3, 40)), 37.57, 126.98);
near("서울 춘분 남중 고도(도)", noon.alt * DEG, 52.3, 1.0);
near("서울 춘분 남중 방위(도, |az|)", Math.abs(noon.az * DEG), 180, 1.5);
// 같은 날 해 뜰 무렵(06:35 KST = 21:35 UTC 전날) → 고도 ≈ 0, 방위 ≈ 동(90°)
const rise = sunPosition(new Date(Date.UTC(2026, 2, 19, 21, 35)), 37.57, 126.98);
near("서울 춘분 일출 고도(도)", rise.alt * DEG, 0, 1.5);
near("서울 춘분 일출 방위(도)", rise.az * DEG, 90, 3.0);
// 2026-01-03 10:03 UTC 보름 → 밝은 면 ≈ 1, 2026-01-18 19:52 UTC 그믐(삭) → ≈ 0
near("2026-01-03 보름 밝은 면", moonIllumination(new Date(Date.UTC(2026, 0, 3, 10, 3))).fraction, 1, 0.01);
near("2026-01-18 삭 밝은 면", moonIllumination(new Date(Date.UTC(2026, 0, 18, 19, 52))).fraction, 0, 0.01);

// 방향 벡터: 동쪽 지평선 = [1, 0, 0], 천정 = [0, 1, 0]
const e = dirOf(0, Math.PI / 2), z = dirOf(Math.PI / 2, 0);
near("동쪽 벡터 x", e[0], 1, 1e-12);
near("천정 벡터 y", z[1], 1, 1e-12);

// 적도 회전 행렬: 회전 행렬이어야 하고(길이 보존), 천구 북극 방향은 적도 z 축(1)로 간다
const M = horizonToEquatorial(t, lat, lon);
const mul = (v) => M.map((r) => r[0] * v[0] + r[1] * v[1] + r[2] * v[2]);
const pole = mul([0, Math.sin(lat / DEG), Math.cos(lat / DEG)]);
near("천구 북극 → 적도 z", pole[2], 1, 1e-9);
const v = mul([0.3, 0.5, -0.81]);
near("길이 보존", Math.hypot(...v), Math.hypot(0.3, 0.5, -0.81), 1e-9);
// 해 방향을 적도로 보냈다가 천정과 내적하면 해 고도가 그대로 나와야 한다
const sv = mul(dirOf(sun.alt, sun.az));
const altBack = Math.asin(mul([0, 1, 0]).reduce((s, c, i) => s + c * sv[i], 0));   // 천정의 적도 벡터 · 해 적도 벡터 = sin(해 고도)
near("행렬로 되돌린 해 고도", altBack, sun.alt, 1e-9);

console.log(fail ? `\n${fail}개 실패` : "\n전부 통과");
process.exit(fail ? 1 : 0);
