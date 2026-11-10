// bglive.js — (bg-dome, 11-10) 돔 바닥 「라이브 조명」 순수 로직 + 마지막 값 보관.
// 돔 바닥의 매립 조명 5개 = 멤버 5명(preview.channel_order 순서). 멤버가 라이브 중이면 그 조명만 멤버 색으로 맥동한다.
// 이 파일은 DOM 을 건드리지 않는다(발행 함수 publishLive 만 document 이벤트를 쏜다 — node 에서는 건너뜀).
import { FALLBACK_CHANNEL_ORDER } from "./config.js";

/** 맥동 주기(ms). 평소 색 → 멤버 색 → 평소 색을 한 바퀴 — 2.8초 = 부드러운 사인(약 2.5 ~ 3초 범위). */
export const LIVE_PERIOD_MS = 2800;

/** channel_order 가 비었거나 없으면 config.js 의 대체 순서 */
export function orderOf(preview) {
  const o = preview && Array.isArray(preview.channel_order) ? preview.channel_order.filter((k) => typeof k === "string" && k) : [];
  return o.length ? o : FALLBACK_CHANNEL_ORDER;
}

/**
 * 조명 0 ~ 4번 = channel_order 앞 5명. 5명 미만이면 빈 칸은 key null.
 * 라이브 판정: state === "live" 인 항목(end · 예고 · assumed_live 제외). 참여 멤버 = channel_key(주 레인) + collab_with(합동 · 그룹 영상, 배열).
 * 반환: [{ key, live }] 길이 5.
 */
export function liveLightKeys(preview) {
  const order = orderOf(preview).slice(0, 5);
  const live = new Set();
  for (const it of preview && Array.isArray(preview.items) ? preview.items : []) {
    if (!it || it.state !== "live" || it.assumed_live) continue;   // 지각 추정(assumed_live)은 라이브가 아니다
    if (typeof it.channel_key === "string") live.add(it.channel_key);
    if (Array.isArray(it.collab_with)) for (const k of it.collab_with) if (typeof k === "string") live.add(k);
  }
  return Array.from({ length: 5 }, (_, i) => {
    const key = order[i] || null;
    return { key, live: !!key && live.has(key) };
  });
}

/**
 * 맥동값 0 ~ 1 (0 = 평소 색, 1 = 멤버 색). reduce 면 점멸 없이 1(멤버 색으로 켜 둠).
 * 사인이라 0 에서 시작해 부드럽게 오간다.
 */
export function pulse(tMs, reduce) {
  if (reduce) return 1;
  return 0.5 - 0.5 * Math.cos((2 * Math.PI * tMs) / LIVE_PERIOD_MS);
}

// ── 마지막 값 보관(돔이 나중에 만들어져도 읽을 수 있게) ──
let current = null;      // 실제 데이터로 계산한 [{ key, live }] 5칸
let currentOrder = FALLBACK_CHANNEL_ORDER;
let forced = null;       // 확인용(?bgdebug) window.__bglive 가 준 키 목록 → 같은 모양으로 바꾼 값

/** main.js 가 preview 를 받을 때 부른다 — 값을 보관하고 문서 이벤트 bg:live 를 낸다(detail = 5칸 배열). */
export function publishLive(preview) {
  current = liveLightKeys(preview);
  currentOrder = orderOf(preview);
  if (typeof document !== "undefined") document.dispatchEvent(new CustomEvent("bg:live", { detail: current }));
}

/** 지금 쓸 5칸 배열 — 확인용 강제 값이 있으면 그것, 없으면 마지막 실제 값. 아직 아무것도 없으면 null. */
export function lastLive() {
  return forced || current;
}

/** 확인용(?bgdebug): keys 를 라이브로 강제. null 이면 실제 데이터로 되돌린다. */
export function forceLive(keys) {
  if (keys == null) { forced = null; return; }
  const set = new Set(Array.isArray(keys) ? keys : []);
  forced = currentOrder.slice(0, 5).map((key) => ({ key, live: set.has(key) }));
  while (forced.length < 5) forced.push({ key: null, live: false });
}
