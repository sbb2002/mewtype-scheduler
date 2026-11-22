// bgstorylogic.js — (bg-dome-mgcyan) UFO 돔 스토리 「다시, 이 하늘」(AGAIN, THIS SKY) 의 상태 · 규칙. DOM 없음(self-check = bgstorylogic.selfcheck.mjs).
// 저장은 해금 상태(bgunlock.js, localStorage "bgunlock")의 story 칸에 같이 둔다 — 해금 기록과 따로 지우거나 잠그지 않는다.
//
// 흐름(운영자 제작 요청 11-23):
//   1 출발  배경 보기에 처음 들어올 때 한 번 — 제목 카드 + (곡이 흐르면) NOW PLAYING · 실제 곡 제목. intro = true 로 바로 저장(새로고침해도 다시 안 뜸)
//   2 추적  딥필드마다 고유 표식을 찾으면 좌하단 레이더에 방위선 하나(장소마다 한 번 · 순서 · 재방문 무관). 다섯 개가 다 모이면 한 점에서 겹친다
//          (그 뒤 LUNAR ORBIT 가 워프 목적지에 뜨는 건 기존 해금 흐름 그대로 — 이 모듈은 건드리지 않는다)
//   3 발견  달 궤도에서 지구를 잡으면(시선 링 100%) 방위선이 지구 위로 겹치고 SIGNAL ORIGIN · EARTH. 이 순간 done = true 로 저장 — 스토리 끝
//   4 귀환  같은 항해(배경 보기에서 나가기 전, 같은 페이지) 안에서만 첫 귀환 YMMT 한 번(메모리 — 저장하지 않는다. bgdomegl.js storyReturn)
// done 뒤에는 스토리 전용 연출(제목 카드 · 방위선 적립 · 발견 장면 · 첫 귀환 YMMT)을 어떤 경로로도 다시 켜지 않는다.

// bgunlock.js 가 이 모듈을 불러 저장값을 다루므로 여기선 bgunlock 을 부르지 않는다(순환 방지). self-check 가 DEEP_FIELDS 와 같은지 확인한다
export const LINE_KEYS = ["smacs", "crab", "orion", "pillars", "tara"];   // 방위선 자리 순서(레이더 각도) = 딥필드 순서
export const STORY_TITLE = "AGAIN, THIS SKY";

/** 빈 스토리 상태 */
export function emptyStory() { return { intro: false, lines: [], done: false, song: null }; }

/** 저장된 값 → 상태(틀린 값은 버린다) */
export function parseStory(o) {
  const s = emptyStory();
  if (!o || typeof o !== "object") return s;
  if (o.intro === true) s.intro = true;
  if (o.done === true) { s.done = true; s.intro = true; }
  if (Array.isArray(o.lines)) s.lines = o.lines.filter((k, i, a) => LINE_KEYS.includes(k) && a.indexOf(k) === i);
  if (o.song && typeof o.song === "object" && typeof o.song.id === "string") s.song = { id: o.song.id, title: typeof o.song.title === "string" ? o.song.title.slice(0, 120) : "" };
  return s;
}

/** 지금 곡 정보(플레이어 이벤트 detail 또는 그 사본) → { on, id, title } */
export function songOf(detail) {
  const d = detail && typeof detail === "object" ? detail : {};
  const on = d.state === "playing" || d.state === "buffering";
  return { on: on && typeof d.id === "string", id: typeof d.id === "string" ? d.id : null, title: typeof d.title === "string" ? d.title : "" };
}

/**
 * 배경 보기에 들어옴. 처음이면 출발 장면을 보여 줄 것을 돌려준다({ title: 곡 제목 | null }), 아니면 null.
 * 처음 들어올 때 이미 탐험한 딥필드(vis)는 방위선으로 조용히 채운다(스토리 이전부터 탐험한 이용자 — 다시 시키지 않는다). 상태를 바꾸면 저장해야 한다.
 */
export function beginStory(st, vis, song) {
  if (st.done || st.intro) return null;
  st.intro = true;
  for (const k of vis || []) if (LINE_KEYS.includes(k) && !st.lines.includes(k)) st.lines.push(k);
  st.song = song && song.on && song.id ? { id: song.id, title: song.title || "" } : null;
  return { title: st.song ? st.song.title : null };
}

/** 딥필드 표식을 찾음 → 방위선 하나. 새로 쌓였으면 true(끝난 스토리 · 이미 쌓인 장소 · 딥필드 아님 = false) */
export function addLine(st, key) {
  if (st.done || !LINE_KEYS.includes(key) || st.lines.includes(key)) return false;
  st.lines.push(key);
  return true;
}

/** 방위선이 다 모였나(다섯 개가 한 점에서 겹침) */
export const converged = (st) => LINE_KEYS.every((k) => st.lines.includes(k));

/**
 * 달 궤도에서 지구를 잡음 → 발견 장면. 처음이면 { title(지금 곡 제목 | null), same(출발 곡과 같은 곡) } 을 돌려주고 done = true(저장 필요), 이미 끝났으면 null.
 * 무음이어도 장면은 그대로(title = null).
 */
export function discover(st, song) {
  if (st.done) return null;
  st.done = true; st.intro = true;
  for (const k of LINE_KEYS) if (!st.lines.includes(k)) st.lines.push(k);   // 발견 = 신호의 근원 확정. 레이더는 끝나면 숨으므로 기록만 맞춘다
  const now = song && song.on && song.id ? song : null;
  return { title: now ? now.title || null : null, same: !!(now && st.song && now.id === st.song.id) };
}

/** 레이더 · 발견 장면의 방위선 각도(도, 화면 기준 0 = 오른쪽 · 시계 방향) — 딥필드 순서대로 72° 간격 */
export const lineAngle = (key) => -90 + 18 + LINE_KEYS.indexOf(key) * 72;
