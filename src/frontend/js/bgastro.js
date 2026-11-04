// bgastro.js — (bg-dome 시험) 「바깥 보기」 천문 계산. 순수 함수(DOM 없음) — 검사 = bgastro.selfcheck.mjs.
// 시각 + 위도 · 경도 → 해 · 달의 고도 · 방위, 달 거리 · 밝은 면 비율, 별자리 회전(항성시).
// 공식은 천문 알마낙의 간략식(정밀도 약 1° 안쪽, 배경용으로 충분). 외부 라이브러리 없이 직접 계산한다.
//
// 방향 약속(장면 좌표와 같다): 방위(az) = 북 0 · 동 +π/2(시계 방향), 고도(alt) = 지평선 0 · 천정 +π/2.
// 장면 벡터 = [동(x), 위(y), 북(z)].

const RAD = Math.PI / 180;
const DAY_MS = 86400000, J1970 = 2440588, J2000 = 2451545;
const OBLIQ = 23.4397 * RAD;   // 황도 경사

const toDays = (ms) => ms / DAY_MS - 0.5 + J1970 - J2000;

const rightAscension = (l, b) => Math.atan2(Math.sin(l) * Math.cos(OBLIQ) - Math.tan(b) * Math.sin(OBLIQ), Math.cos(l));
const declination = (l, b) => Math.asin(Math.sin(b) * Math.cos(OBLIQ) + Math.cos(b) * Math.sin(OBLIQ) * Math.sin(l));
const siderealTime = (d, lw) => RAD * (280.16 + 360.9856235 * d) - lw;
// 남쪽 0 · 서쪽 + 로 재는 방위(알마낙 관례) — 아래에서 북 기준으로 바꾼다
const azimuthS = (H, phi, dec) => Math.atan2(Math.sin(H), Math.cos(H) * Math.sin(phi) - Math.tan(dec) * Math.cos(phi));
const altitude = (H, phi, dec) => Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(H));
/** 대기 굴절 보정(지평선 근처에서 실제보다 조금 높이 보인다). h < 0 이면 보정하지 않는다 */
export function refraction(h) {
  if (h < 0) h = 0;
  return 0.0002967 / Math.tan(h + 0.00312536 / (h + 0.08901179));
}
const toNorthAz = (azS) => { const a = azS + Math.PI; return a > Math.PI ? a - 2 * Math.PI : a; };   // (-π, π]

function sunCoords(d) {
  const M = RAD * (357.5291 + 0.98560028 * d);
  const C = RAD * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M));
  const L = M + C + RAD * 102.9372 + Math.PI;   // 황경
  return { dec: declination(L, 0), ra: rightAscension(L, 0) };
}

function moonCoords(d) {
  const L = RAD * (218.316 + 13.176396 * d);   // 평균 황경
  const M = RAD * (134.963 + 13.064993 * d);   // 평균 근점 이각
  const F = RAD * (93.272 + 13.229350 * d);    // 평균 승교점 이각
  const l = L + RAD * 6.289 * Math.sin(M);
  const b = RAD * 5.128 * Math.sin(F);
  return { ra: rightAscension(l, b), dec: declination(l, b), dist: 385001 - 20905 * Math.cos(M) };
}

/** 해 위치 { alt, az(북 기준), azS(남 기준 — 검사용) } (라디안) */
export function sunPosition(date, lat, lon) {
  const lw = RAD * -lon, phi = RAD * lat, d = toDays(+date);
  const c = sunCoords(d), H = siderealTime(d, lw) - c.ra;
  const azS = azimuthS(H, phi, c.dec);
  return { alt: altitude(H, phi, c.dec), az: toNorthAz(azS), azS };
}

/** 달 위치 { alt(굴절 보정), az(북 기준), azS, dist(km), parallactic } */
export function moonPosition(date, lat, lon) {
  const lw = RAD * -lon, phi = RAD * lat, d = toDays(+date);
  const c = moonCoords(d), H = siderealTime(d, lw) - c.ra;
  const geometricAlt = altitude(H, phi, c.dec);
  let h = geometricAlt;
  const parallactic = Math.atan2(Math.sin(H), Math.tan(phi) * Math.cos(c.dec) - Math.sin(c.dec) * Math.cos(H));
  h += refraction(h);
  const azS = azimuthS(H, phi, c.dec);
  return { alt: h, apparentAlt: h, geometricAlt, az: toNorthAz(azS), azS, dist: c.dist, parallactic };
}

/** 달 밝은 면 { fraction(0 ~ 1), phase(0 = 삭 · 0.5 = 망), angle(밝은 쪽 가장자리 방향) } — 위치와 무관(지구 어디서나 같다) */
export function moonIllumination(date) {
  const d = toDays(+date), s = sunCoords(d), m = moonCoords(d), sdist = 149598000;
  const phi = Math.acos(Math.sin(s.dec) * Math.sin(m.dec) + Math.cos(s.dec) * Math.cos(m.dec) * Math.cos(s.ra - m.ra));
  const inc = Math.atan2(sdist * Math.sin(phi), m.dist - sdist * Math.cos(phi));
  const angle = Math.atan2(Math.cos(s.dec) * Math.sin(s.ra - m.ra), Math.sin(s.dec) * Math.cos(m.dec) - Math.cos(s.dec) * Math.sin(m.dec) * Math.cos(s.ra - m.ra));
  return { fraction: (1 + Math.cos(inc)) / 2, phase: 0.5 + 0.5 * inc * (angle < 0 ? -1 : 1) / Math.PI, angle };
}

/** 고도 · 방위(북 기준) → 장면 벡터 [동, 위, 북] */
export function dirOf(alt, az) {
  return [Math.sin(az) * Math.cos(alt), Math.sin(alt), Math.cos(az) * Math.cos(alt)];
}

/** 장면(지평) 벡터 → 하늘에 고정된 적도 좌표 벡터로 바꾸는 3×3 행렬(행 우선). 별이 실제처럼 북극성 둘레로 돈다.
 *  적도 벡터 = (cos ra · cos dec, sin ra · cos dec, sin dec). 항성시 = 정남(시각 0)에 걸린 적경. */
export function horizonToEquatorial(date, lat, lon) {
  const phi = RAD * lat, lst = siderealTime(toDays(+date), RAD * -lon);
  const P = [0, Math.sin(phi), Math.cos(phi)];    // 천구 북극
  const Q = [0, Math.cos(phi), -Math.sin(phi)];   // 정남 자오선의 적도 점(시각 0)
  const Wd = [-1, 0, 0];                          // 서쪽 = 시각 +6h
  // 시각 좌표 (cos H cos δ, sin H cos δ, sin δ) = (d·Q, d·W, d·P), ra = lst - H → (x, -y) 를 lst 만큼 돌린다
  const c = Math.cos(lst), s = Math.sin(lst);
  const row = (k) => [c * Q[k] + s * Wd[k], s * Q[k] - c * Wd[k], P[k]];   // 열 k 를 모아 행 우선으로 바꾼다
  const cols = [row(0), row(1), row(2)];
  return [[cols[0][0], cols[1][0], cols[2][0]], [cols[0][1], cols[1][1], cols[2][1]], [cols[0][2], cols[1][2], cols[2][2]]];
}
