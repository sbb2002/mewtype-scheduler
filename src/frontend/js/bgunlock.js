// bgunlock.js — (bg-dome) 배경 보기 해금 상태 · 규칙. DOM · WebGL 없음(순수 계산 + 기기 저장 하나, self-check = bgunlock.selfcheck.mjs).
// 정본 = devpapers docs/plan/bg-dome/hud_implementation.md(운영자 11-09 확정 해금 시나리오).
//
// 해금(unlock) = 하늘이나 기능이 처음 쓸 수 있게 열리는 것. 이 기기에만 저장(localStorage "bgunlock") — 기기를 바꾸면 사라진다.
//   space   초행성X(기본 우주)         ← 버츄얼 스페이스에서 토성 표식 발견
//   hold    초행성X 길게 누르기 = 성간 이동 ← 기본 우주에서 성운 발견
//   moon    달 궤도(지구돋이 사진 하늘)    ← 딥필드 다섯 곳을 다 가 본 뒤 무작위 워프 한 번
//   earth   지구(바깥 보기)              ← 달 궤도에서 지구 발견 — 마지막 해금
//   light   별빛 조명                    ← 기본 우주의 멤버 탄생 별자리 5개
//   ymmt · freenav  마지막 보상(YMMT 별자리 · 자유 항해) ← 지구와 함께
// 딥필드 = 우주 사진이 크게 보이는 우주 하늘(DEEP_SET 의 지구돋이를 뺀 다섯). 무작위 워프로 도착할 때마다 하나씩 「가 본 곳(vis)」에 들어가 워프 목적지에 추가된다.

import { emptyStory, parseStory } from "./bgstorylogic.js";

export const KEY = "bgunlock";
export const UNLOCKS = ["space", "hold", "moon", "earth", "light", "ymmt", "freenav"];

/** 딥필드 다섯(키 · 사진 번호 = bgdomegl.js DEEP_SET 순서 · 이름). 달 궤도는 따로 */
export const DEEP_FIELDS = [
  { key: "smacs", idx: 0, name: "SMACS 0723 DEEP FIELD", feat: { u: 0.43, v: 0.37, n: "DIFFRACTION STAR" } },
  { key: "crab", idx: 2, name: "CRAB NEBULA", feat: { u: 0.62, v: 0.5, n: "CRAB PULSAR" } },
  { key: "orion", idx: 3, name: "ORION NEBULA", feat: { u: 0.52, v: 0.45, n: "TRAPEZIUM" } },
  { key: "pillars", idx: 4, name: "PILLARS OF CREATION", feat: { u: 0.4, v: 0.17, n: "PILLAR TIP" } },
  { key: "tara", idx: 5, name: "TARANTULA NEBULA", feat: { u: 0.25, v: 0.42, n: "R136 CLUSTER" } },
];
// feat = 그 딥필드 사진에서만 찾을 수 있는 표식 하나(그림 좌표 u 왼 → 오 · v 위 → 아래). 이걸 찾으면 그 딥필드를 「탐험한」 것으로 친다(운영자 11-09)
export const MOON = { key: "moon", idx: 1, name: "LUNAR ORBIT", feat: { u: 0.57, v: 0.515, n: "EARTH" } };
const BY_KEY = Object.fromEntries([...DEEP_FIELDS, MOON].map((d) => [d.key, d]));
export const placeInfo = (key) => BY_KEY[key] || null;
/** 사진 번호 → 장소 키(없으면 null = 사진 없는 기본 우주) */
export const keyOfIdx = (idx) => ([...DEEP_FIELDS, MOON].find((d) => d.idx === idx) || {}).key || null;

/** 빈 상태 */
export function emptyState() { return { v: 1, unl: [], vis: [], found: [], seen: {}, story: emptyStory() }; }   // story = 「다시, 이 하늘」 진행(bgstorylogic.js)

/** 저장된 글을 상태로(틀린 값은 버린다) */
export function parseState(text) {
  const s = emptyState();
  if (!text) return s;
  let o;
  try { o = JSON.parse(text); } catch { return s; }
  if (!o || typeof o !== "object") return s;
  if (Array.isArray(o.unl)) s.unl = o.unl.filter((k) => UNLOCKS.includes(k));
  if (Array.isArray(o.vis)) s.vis = o.vis.filter((k, i, a) => DEEP_FIELDS.some((d) => d.key === k) && a.indexOf(k) === i);
  if (Array.isArray(o.found)) s.found = o.found.filter((k) => typeof k === "string").slice(0, 64);
  s.story = parseStory(o.story);
  if (o.seen && typeof o.seen === "object") for (const k of ["holdNotice", "locAsked", "ymmtShown", "lightOff", "pinchHint"]) if (o.seen[k] === true) s.seen[k] = true;   // lightOff = 별빛 조명을 끔(3단계) · pinchHint = 「벌려 다가가기」 안내를 본 기기(11-20 검토 — 전엔 복원 목록에서 빠져 새로고침마다 다시 떴다)
  return s;
}

/** 옛 사용자(해금 이전부터 조작 패널로 하늘을 골라 쓰던 기기) — 다시 잠그지 않는다(운영자 원칙). 근거 = 패널이 남긴 기억(bgindoor · bgview) */
export function legacyUnlocks(storedIndoor, storedView) {
  return storedIndoor != null || storedView != null ? ["space", "hold", "earth"] : [];
}

export const has = (s, k) => s.unl.includes(k);
/** 해금. 새로 열렸으면 true */
export function unlock(s, k) { if (!UNLOCKS.includes(k) || has(s, k)) return false; s.unl.push(k); return true; }
/** 찾은 대상 기록. 새로 찾았으면 true */
export function find(s, id) { if (s.found.includes(id)) return false; s.found.push(id); return true; }

/** 워프로 어딘가에 도착 — 달 궤도에 처음이면 "moon"(해금), 그 밖 null. 딥필드는 도착만으로는 「가 본 곳」이 되지 않는다(explore — 사진 속 표식을 찾아야) */
export function arrive(s, key) {
  if (key === "moon") return unlock(s, "moon") ? "moon" : null;
  return null;
}
/** 딥필드 탐험 완료(그 사진의 표식을 찾음) — 처음이면 true, 워프 목적지에 추가된다 */
export function explore(s, key) {
  if (!DEEP_FIELDS.some((d) => d.key === key) || s.vis.includes(key)) return false;
  s.vis.push(key);
  return true;
}

/** 딥필드를 다 가 봤나 */
export const allDeepVisited = (s) => DEEP_FIELDS.every((d) => s.vis.includes(d.key));

/**
 * 무작위 워프의 도착지. cur = 지금 있는 곳 키("space" 기본 우주 · 딥필드 키 · "moon").
 * 딥필드를 다 가 봤고 달 궤도가 아직이면 달 궤도. 아니면 지금 있는 곳을 뺀 딥필드 가운데 균등 무작위 — 이미 가 본 곳도 나온다(운영자 11-09).
 */
export function randomDest(s, cur, rand = Math.random) {
  if (allDeepVisited(s) && !has(s, "moon")) return "moon";
  const pool = DEEP_FIELDS.map((d) => d.key).filter((k) => k !== cur);
  return pool[Math.min(pool.length - 1, Math.floor(rand() * pool.length))];
}

/**
 * WARP 를 누를 때 고르기 창에 보일 것. 고를 곳이 하나도 없으면(가 본 딥필드 0 · 달 궤도 잠김) null — 창 없이 바로 무작위.
 * 항목 = { key: "random" | 딥필드 키 | "moon" | "space", name, here } — here = 지금 있는 곳(누를 수 없음).
 */
export function chooserItems(s, cur) {
  if (!s.vis.length && !has(s, "moon")) return null;
  // 딥필드 다섯을 다 탐험했고 달 궤도가 아직이면 무작위 자리를 달 궤도가 대신한다(운영자 11-09 — 무작위를 잠깐 없애고 달 궤도로)
  const items = [allDeepVisited(s) && !has(s, "moon") ? { key: "moon", name: MOON.name, here: false, signal: true } : { key: "random", name: "RANDOM", here: false }];
  for (const k of s.vis) items.push({ key: k, name: BY_KEY[k].name, here: k === cur });
  if (has(s, "moon")) items.push({ key: "moon", name: MOON.name, here: cur === "moon" });
  if (cur !== "space") items.push({ key: "space", name: "BACK TO OPEN SPACE", here: false });
  return items;
}

/** 확인용 · 모두 열기(모니터링 페이지 지뢰찾기 성공과 같은 결과) */
export function unlockAll(s, findIds = []) {
  for (const k of UNLOCKS) unlock(s, k);
  for (const d of DEEP_FIELDS) if (!s.vis.includes(d.key)) s.vis.push(d.key);
  for (const id of findIds) find(s, id);
  return s;
}

/** 기기 저장 상태 — 읽고 쓰기 실패해도 이번 방문 동안은 메모리로 계속 */
export function loadUnlock(storage) {
  let text = null, indoor = null, view = null;
  try { text = storage.getItem(KEY); indoor = storage.getItem("bgindoor"); view = storage.getItem("bgview"); } catch { /* 저장소 막힘 */ }
  const s = parseState(text);
  if (text == null) for (const k of legacyUnlocks(indoor, view)) unlock(s, k);
  return s;
}
export function saveUnlock(storage, s) {
  try { storage.setItem(KEY, JSON.stringify({ v: 1, unl: s.unl, vis: s.vis, found: s.found, seen: s.seen, story: s.story || emptyStory() })); return true; } catch { return false; }
}

// ── 찾기(2단계, 시선 HUD bghud.js) ────────────────────────────────────────────
/** 멤버 탄생 별자리 다섯(config.js BIRTHDAYS 의 생일 → 황도 12궁, 운영자 11-09). 모양은 단순화한 예시 — 별 오프셋 [방위°, 고도°] · 선 [i, j]. key = 멤버 키(곡 힌트 bgmusic.js) */
export const ZODIAC = [
  { id: "z_arale", key: "arale", n: "LEO", who: "ARARE", S: [[0, 0], [1, 4], [3, 7], [6, 7], [7, 4], [-7, 2], [-13, 0], [-8, -2]], L: [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 0]] },
  { id: "z_yuno", key: "yuno", n: "SCORPIO", who: "YUNO", S: [[-8, 6], [-7, 3], [-6, 0], [-3, -2], [0, -3], [3, -4], [6, -3], [8, -1], [7, 2]], L: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8]] },
  { id: "z_nonoka", key: "nonoka", n: "ARIES", who: "NONOKA", S: [[-6, -1], [-1, 1], [2, 2], [5, 4]], L: [[0, 1], [1, 2], [2, 3]] },
  { id: "z_ritsu", key: "ritsu", n: "AQUARIUS", who: "RITSU", S: [[-8, 4], [-4, 5], [0, 3], [2, 0], [1, -4], [4, -6], [-2, -2], [-5, -5]], L: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [3, 6], [6, 7]] },
  { id: "z_miyako", key: "miyako", n: "VIRGO", who: "MIYAKO", S: [[0, 0], [-4, 3], [-8, 5], [3, 4], [6, 8], [-1, -4], [2, -8], [-5, -1]], L: [[0, 1], [1, 2], [0, 3], [3, 4], [0, 5], [5, 6], [1, 7]] },
];
const UNLOCK_MSG = {
  space: { to: "→ PLANET X UNLOCKED IN UFO CONTROL", toast: "PLANET X UNLOCKED" },
  hold: { to: "→ HOLD PLANET X TO JUMP", toast: "INTERSTELLAR JUMP UNLOCKED" },
  earth: { to: "→ EARTH UNLOCKED IN UFO CONTROL", toast: "EARTH UNLOCKED · YMMT SIGN · FREE ROAM" },
};
/**
 * 해금 종류 표지. bgdomegl.js unlockFx 가 이 객체로 어느 칸을 빛낼지(FX_TILE) 고르고, bghud.js 는 있으면 불꽃 연출을 터뜨린다.
 * (11-09 엔 「해금 2초 뒤 자동 이동 + 이 글로 안내 카드」 였으나 11-13 시나리오에서 자동 이동 · 안내 카드를 없앴다 — title · go · how 글은 지금 화면에 쓰이지 않는다)
 */
export const GUIDE = {
  space: { title: "PLANET X UNLOCKED", go: "space", how: "Approach the UFO console to open UFO CONTROL, then tap VOYAGE TO PLANET X." },
  hold: { title: "INTERSTELLAR JUMP UNLOCKED", go: "hold", how: "Hold PLANET X for 1 second to jump. Shift up to gear 5 below, then press WARP." },
  earth: { title: "EARTH UNLOCKED", go: "earth", how: "Tap EARTH in UFO CONTROL. Allow location to see your real sky." },
  moon: { title: "LUNAR ORBIT UNLOCKED", go: null, how: "Pick LUNAR ORBIT as a warp destination to return." },
  light: { title: "STARLIGHT UNLOCKED", go: null, how: "Toggle STARLIGHT in UFO CONTROL." },
  explore: { title: "DEEP FIELD SURVEYED", go: null, how: "This deep field is now listed under WARP destinations." },
};
/**
 * 대상을 잡았다(시선 링 100%). t = { id, unlock?("space" | "hold" | "earth"), zod?(별자리면 true), who? }.
 * 돌려줌 = { fresh(처음 찾음), k(카드 위 작은 글 — "NEW" · "SURVEYED" · "SIGN" · ""), to(카드 아래 줄 — 없으면 ""), toast(알림 — 없으면 ""), changed(저장 필요) }.
 * 지구를 찾으면 지구와 함께 마지막 보상(ymmt · freenav)도 열린다. 별자리 다섯을 다 찾으면 별빛 조명.
 */
export function onFound(s, t) {
  const fresh = find(s, t.id);
  const r = { fresh, k: "", to: "", toast: "", changed: fresh, guide: null };
  if (t.unlock) {
    const opened = unlock(s, t.unlock);
    if (t.unlock === "earth") { unlock(s, "ymmt"); unlock(s, "freenav"); }
    if (opened) { r.k = "NEW"; r.to = UNLOCK_MSG[t.unlock].to; r.toast = UNLOCK_MSG[t.unlock].toast; r.changed = true; r.guide = GUIDE[t.unlock]; }
  } else if (t.explore) {
    if (explore(s, t.explore)) { r.k = "SURVEYED"; r.to = "→ ADDED TO WARP DESTINATIONS"; r.toast = `SURVEYED · ${placeInfo(t.explore).name}`; r.changed = true; r.guide = GUIDE.explore; }
  } else if (t.zod && fresh) {
    r.k = "SIGN"; r.to = `${t.who} · BIRTH SIGN`;
    if (ZODIAC.every((z) => s.found.includes(z.id)) && unlock(s, "light")) { r.to += " · STARLIGHT UNLOCKED"; r.toast = "STARLIGHT UNLOCKED"; r.guide = GUIDE.light; }
  }
  return r;
}

/** 찾을 수 있는 대상 id 전부 — 모두 열기(모니터링 페이지 지뢰찾기)가 found 를 채울 때 */
export const ALL_FIND_IDS = ["saturn", "neb", "earthT", ...DEEP_FIELDS.map((d) => "x_" + d.key), ...ZODIAC.map((z) => z.id)];
/** 모두 열기 — 기기 저장까지(모니터링 페이지에서 부른다). 돌려줌 = 저장 성공 */
export function unlockAllStored(storage) { const s = loadUnlock(storage); unlockAll(s, ALL_FIND_IDS); return saveUnlock(storage, s); }
