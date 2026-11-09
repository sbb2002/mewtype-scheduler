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

export const KEY = "bgunlock";
export const UNLOCKS = ["space", "hold", "moon", "earth", "light", "ymmt", "freenav"];

/** 딥필드 다섯(키 · 사진 번호 = bgdomegl.js DEEP_SET 순서 · 이름). 달 궤도는 따로 */
export const DEEP_FIELDS = [
  { key: "smacs", idx: 0, name: "SMACS 0723 딥필드" },
  { key: "crab", idx: 2, name: "게 성운" },
  { key: "orion", idx: 3, name: "오리온 성운" },
  { key: "pillars", idx: 4, name: "창조의 기둥" },
  { key: "tara", idx: 5, name: "타란툴라 성운" },
];
export const MOON = { key: "moon", idx: 1, name: "달 궤도" };
const BY_KEY = Object.fromEntries([...DEEP_FIELDS, MOON].map((d) => [d.key, d]));
export const placeInfo = (key) => BY_KEY[key] || null;
/** 사진 번호 → 장소 키(없으면 null = 사진 없는 기본 우주) */
export const keyOfIdx = (idx) => ([...DEEP_FIELDS, MOON].find((d) => d.idx === idx) || {}).key || null;

/** 빈 상태 */
export function emptyState() { return { v: 1, unl: [], vis: [], found: [], seen: {} }; }

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
  if (o.seen && typeof o.seen === "object") for (const k of ["holdNotice", "locAsked", "ymmtShown"]) if (o.seen[k] === true) s.seen[k] = true;
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

/** 워프로 어딘가에 도착 — 처음 가 본 딥필드면 "deep", 달 궤도에 처음이면 "moon"(해금), 그 밖 null */
export function arrive(s, key) {
  if (DEEP_FIELDS.some((d) => d.key === key)) { if (s.vis.includes(key)) return null; s.vis.push(key); return "deep"; }
  if (key === "moon") return unlock(s, "moon") ? "moon" : null;
  return null;
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
  const items = [{ key: "random", name: "무작위", here: false }];
  for (const k of s.vis) items.push({ key: k, name: BY_KEY[k].name, here: k === cur });
  if (has(s, "moon")) items.push({ key: "moon", name: MOON.name, here: cur === "moon" });
  if (cur !== "space") items.push({ key: "space", name: "기본 우주로", here: false });
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
  try { storage.setItem(KEY, JSON.stringify({ v: 1, unl: s.unl, vis: s.vis, found: s.found, seen: s.seen })); return true; } catch { return false; }
}
