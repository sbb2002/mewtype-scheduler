// bghudlogic.selfcheck.mjs — node src/frontend/js/bghudlogic.selfcheck.mjs
import assert from "node:assert/strict";
import { dirFromAzAlt, azAltOf, sepDeg, toSpace, toDome, wrap180, pickHit, createDwell, stepDwell, beacons, FILL_S, rotFromTo, mulM, aimSpace } from "./bghudlogic.js";

const near = (a, b, e = 1e-6) => Math.abs(a - b) < e;
// 방향 ↔ 방위 · 고도
{
  const d = dirFromAzAlt(90, 0);
  assert.ok(near(d[0], 1) && near(d[2], 0), "방위 90° = 동(+x)");
  const [az, alt] = azAltOf(dirFromAzAlt(210, 35));
  assert.ok(near(az, 210, 1e-9) && near(alt, 35, 1e-9));
  assert.ok(near(sepDeg(dirFromAzAlt(10, 0), dirFromAzAlt(20, 0)), 10, 1e-9));
  assert.equal(wrap180(350), -10);
}
// 돔 ↔ 우주(돌림 행렬) 왕복
{
  const c = Math.cos(0.7), s = Math.sin(0.7);
  const m = [c, 0, -s, 0, 1, 0, s, 0, c];   // y 축 돌림(열 우선)
  const d = dirFromAzAlt(33, 21);
  const back = toDome(m, toSpace(m, d));
  assert.ok(back.every((v, i) => near(v, d[i])));
}
// 가장 가까운 대상
{
  const a = { id: "a", dir: dirFromAzAlt(0, 20), tol: 5 }, b = { id: "b", dir: dirFromAzAlt(3, 20), tol: 5 };
  assert.equal(pickHit(dirFromAzAlt(2.6, 20), [a, b]).id, "b");
  assert.equal(pickHit(dirFromAzAlt(40, 20), [a, b]), null);
  assert.equal(pickHit(dirFromAzAlt(0, 20), [{ ...a, hidden: true }]), null);
}
// 바라보기 → 잡힘 → 유지 → 풀림
{
  const t = { id: "t", dir: dirFromAzAlt(0, 0), tol: 5 };
  const st = createDwell();
  let got = null;
  for (let i = 0; i < FILL_S * 10 - 1; i++) got = stepDwell(st, t, 0, 0.1) || got;
  assert.equal(got, null, "2초 전엔 안 잡힘");
  got = stepDwell(st, t, 0, 0.1);
  assert.equal(got.id, "t");
  assert.equal(stepDwell(st, null, 10, 0.1), null);
  assert.ok(st.lock, "15° 안이면 유지");
  for (let i = 0; i < 29; i++) stepDwell(st, null, 30, 0.1);
  assert.ok(st.lock, "3초 전엔 유지");
  stepDwell(st, null, 30, 0.2);
  assert.equal(st.lock, null, "15° 밖 3초 넘으면 풀림");
  // 벗어나면 서서히 줄어 사라짐
  const s2 = createDwell();
  for (let i = 0; i < 10; i++) stepDwell(s2, t, 0, 0.1);
  assert.ok(s2.v > 0.49 && s2.v < 0.51);
  for (let i = 0; i < 16; i++) stepDwell(s2, null, 99, 0.1);
  assert.equal(s2.focus, null);
}
// 힌트 점
{
  const ts = [{ dir: dirFromAzAlt(100, 10) }, { dir: dirFromAzAlt(5, -10), below: true }, { dir: dirFromAzAlt(0, 10), found: true }];
  const bs = beacons(0, dirFromAzAlt(0, 10), ts, 22);
  assert.equal(bs.length, 2);
  assert.equal(bs[0].out, 1);
  assert.equal(bs[0].dx, 22);
  assert.ok(bs[1].below && bs[1].out === 0);
}
// 돌림 맞추기 — 아무 돌림에서도 사진 방향이 정한 자리에 맺힌다
{
  const ap = (m, v) => [m[0] * v[0] + m[3] * v[1] + m[6] * v[2], m[1] * v[0] + m[4] * v[1] + m[7] * v[2], m[2] * v[0] + m[5] * v[1] + m[8] * v[2]];
  const a = dirFromAzAlt(10, 5), b = dirFromAzAlt(200, 40);
  assert.ok(sepDeg(ap(rotFromTo(a, b), a), b) < 1e-4);
  assert.ok(sepDeg(ap(rotFromTo(a, a.map((x) => -x)), a), a.map((x) => -x)) < 1e-4, "정반대");
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 50; i++) {
    const m0 = mulM(rotFromTo(dirFromAzAlt(0, 90), dirFromAzAlt(rnd() * 360, rnd() * 180 - 90)), rotFromTo(dirFromAzAlt(0, 0), dirFromAzAlt(rnd() * 360, rnd() * 120 - 60)));
    const s = dirFromAzAlt(30, 25), t = dirFromAzAlt(rnd() * 360, 18 + rnd() * 22);
    assert.ok(sepDeg(toDome(aimSpace(m0, s, t), s), t) < 1e-4);
  }
}
console.log("bghudlogic self-check ok");
// 사진 속 점 · 달 궤도 지평선
{
  const { photoDir, moonFrame, levelSpace } = await import("./bghudlogic.js");
  const C = [0.42, 0.36, 0.83], l = Math.hypot(...C), Cn = C.map((x) => x / l);
  assert.ok(sepDeg(photoDir(Cn, 0.5, 0.5), Cn) < 1e-6, "사진 가운데 = C");
  assert.ok(sepDeg(photoDir(Cn, 0.5, 0.5), photoDir(Cn, 0.9, 0.5)) > 10, "옆으로 갈수록 떨어짐");
  const { N, T } = moonFrame(Cn);
  assert.ok(Math.abs(N[0] * T[0] + N[1] * T[1] + N[2] * T[2]) < 1e-9, "N ⟂ T");
  const m0 = [0.36, 0.48, -0.8, -0.8, 0.6, 0, 0.48, 0.64, 0.6];   // 직교 행렬(열 우선) 하나
  const m = levelSpace(m0, N, Cn, 123);
  const up = toDome(m, N), cd = toDome(m, Cn);
  assert.ok(near(up[1], 1, 1e-6), "지평선 위쪽 = 돔 위");
  assert.ok(near(azAltOf(cd)[0], 123, 1e-4), "사진 방위 = 요청값");
  assert.ok(azAltOf(cd)[1] > 5 && azAltOf(cd)[1] < 15, "사진 중심이 지평선 위 약 10°");
}
