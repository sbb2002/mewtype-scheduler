// bglevel.js — (bg-dome, 11-06 운영자 「폰을 기울여도 배경 자체는 눈으로 보기에 기울지 않게 — 모든 테마」)
// 폰을 옆으로 기울이면(roll) 배경을 그만큼 반대로 돌려 세상 기준 수평을 지킨다.
//   · UFO 돔(WebGL) = bgdomegl.js 가 카메라 축을 직접 돌린다(여기선 건드리지 않음 — #bgdeco[data-variant="d"])
//   · 기본(#bgdeco, main 의 배경) · 생일(#bday-bg) = 배경 층을 CSS 로 돌리고, 돌려도 모서리가 비지 않게 그만큼 키운다
// 기울기 = bggyro.js gyroTilt(화면 평면 안의 중력 방향). 눕혀 들면(upright 작음) 의미가 없어 0 쪽으로, 0.15초 저역 통과로 손떨림을 거른다. 움직임 줄이기면 끈다.

import { gyroTilt } from "./bggyro.js";

let raf = 0, roll = 0, last = 0;
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

function layers() {
  const out = [];
  const deco = document.getElementById("bgdeco");
  if (deco && deco.dataset.variant !== "d") out.push(deco);
  const bday = document.getElementById("bday-bg");
  if (bday) out.push(bday);
  return out;
}

function loop(t) {
  raf = requestAnimationFrame(loop);
  const dt = Math.min(0.1, (t - (last || t)) / 1000); last = t;
  const tl = reduce.matches ? null : gyroTilt();
  const want = tl ? tl.roll * Math.max(0, Math.min(1, (tl.upright - 0.25) / 0.45)) : 0;
  roll += (want - roll) * (1 - Math.exp(-dt / 0.15));
  const W = window.innerWidth, H = window.innerHeight, c = Math.abs(Math.cos(roll)), s = Math.abs(Math.sin(roll));
  const k = Math.max((W * c + H * s) / W, (W * s + H * c) / H);   // 돌린 화면을 다 덮는 확대 배율
  const tf = Math.abs(roll) < 0.002 ? "" : `rotate(${(-roll).toFixed(4)}rad) scale(${k.toFixed(4)})`;
  for (const el of layers()) if (el.style.transform !== tf) el.style.transform = tf;
  // 돔으로 바뀌었으면 남은 CSS 회전을 지운다
  const deco = document.getElementById("bgdeco");
  if (deco && deco.dataset.variant === "d" && deco.style.transform) deco.style.transform = "";
}

/** 기울기 맞추기 시작(한 번만). 센서 값이 없으면 아무것도 돌리지 않는다 */
export function startLevel() { if (!raf) raf = requestAnimationFrame(loop); }
