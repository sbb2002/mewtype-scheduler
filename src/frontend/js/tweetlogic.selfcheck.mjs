/**
 * tweetlogic.js 순수 로직 자동 테스트 (트윗 시트, V1-C 의 C1~C8 + v4.9.1 C9 새 글만 끼우기 계획 + v4.9.3 C10~C15 미디어 · X 카드 치수 · 스크롤 · 밀기). node tweetlogic.selfcheck.mjs 로 실행. 프레임워크 없음. DOM 을 쓰지 않는다.
 */
import {
  chains, attachments, inkFor, paperFor, paletteFor, contrast, parseRgb, kstParts,
  postedLabel, replyLabel, unpostedLabel, gapLabel, clockLabel, estimateCardH, firstUnread,
  faceOf, langOf, sigOf, shortName, reconcileUnits,
  mediaItems, smallUrl, gridOf, singleRatio, mediaBoxH, predictCardH, xTextH, restoreTarget, fabMode, swipeTo, dayLabel, fullLabel,
} from "./tweetlogic.js";

let n = 0;
function assert(cond, msg) {
  n++;
  if (!cond) { console.error(`❌ FAIL (${n}): ${msg}`); process.exit(1); }
  console.log(`✓ ${msg}`);
}
const ids = (units) => units.map((u) => u.map((m) => m.id).join("+"));
const flat = (units) => units.flat().map((m) => m.id);
const H = 3600e3, MIN = 60e3;
const t0 = Date.parse("2026-10-27T01:00:00Z");
const at = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const msg = (id, ms, extra) => ({ id, posted_at: at(ms), ...extra });
const NOW = Date.parse("2026-10-26T22:05:00Z");   // 10/27 07:05 KST

// ── C1 · chains: 글타래 묶기 · 순서
{
  const r1 = msg("r1", t0), r2 = msg("r2", t0 + 5 * MIN, { reply_to_id: "r1" });
  assert(JSON.stringify(flat(chains([r2, r1]))) === JSON.stringify(["r1", "r2"]), "C1 원글 있음: 답글은 원글 바로 뒤");
  const x1 = msg("x1", t0 + H, { reply_to_id: "nope" });
  const u = chains([x1]);
  assert(u.length === 1 && u[0].length === 1, "C1 원글 없음: 답글은 혼자");
  const a = msg("a", t0), b = msg("b", t0 + 11 * MIN, { reply_to_id: "a" });
  assert(ids(chains([a, b])).join(",") === "a+b", "C1 간격 11분: 그래도 붙음");
  const c2a = msg("ca", t0), c2b = msg("cb", t0 + MIN, { reply_to_id: "ca" }), c2c = msg("cc", t0 + 2 * MIN, { reply_to_id: "cb" });
  assert(ids(chains([c2c, c2a, c2b])).join(",") === "ca+cb+cc", "C1 사슬 2단: 뿌리까지 한 덩어리, 순서대로");
  const e = msg("e", t0 + 2 * H), p = msg("p", t0), d = msg("d", t0 + 5 * H, { reply_to_id: "p" });
  const r = chains([d, e, p]);
  assert(ids(r).join(",") === "e,p+d", "C1 5시간 뒤 답글: 글타래가 맨 아래로 끌어올려짐");
  const o1 = msg("o1", t0 + 3 * H), o2 = msg("o2", t0 + 4 * H);
  assert(flat(chains([o2, o1])).join(",") === "o1,o2", "C1 옛 데이터(reply_to_id 없음): 게시 시각순 그대로");
}

// ── C2 · chains: 남의 글 가리킴 · 순환
{
  const A = msg("A", t0, { reply_to_id: "someone-else" }), B = msg("B", t0 + MIN, { reply_to_id: "A" });
  assert(ids(chains([A])).join(",") === "A", "C2 남의 글 id 를 가리킴(원글 목록에 없음): 단독");
  assert(ids(chains([A, B])).join(",") === "A+B", "C2 단독이 된 글에 붙은 답글은 그 글 아래 글타래로");
  const Z = msg("Z", t0, { reply_to_id: "outside" });
  assert(ids(chains([Z, msg("W", t0 + MIN)])).join(",") === "Z,W", "C2 남의 글 답글 + 무관한 글: 각자 단독 · 시각순");
  const X = msg("X", t0, { reply_to_id: "Y" }), Y = msg("Y", t0 + MIN, { reply_to_id: "X" });
  const cyc = chains([X, Y]);
  assert(cyc.length === 2 && cyc.every((u) => u.length === 1), "C2 순환(서로 가리킴): 단독 처리 · 무한 반복 없음");
  const S = msg("S", t0, { reply_to_id: "S" });
  assert(chains([S]).length === 1 && chains([S])[0].length === 1, "C2 자기 자신을 가리킴: 단독 · 무한 반복 없음");
}

// ── C3 · attachments
{
  const P = "https://pbs.twimg.com/media/aaa.jpg", Q = "https://pbs.twimg.com/media/bbb.jpg";
  const V = "https://pbs.twimg.com/amplify_video_thumb/1/img/x.jpg", TV = "https://pbs.twimg.com/tweet_video_thumb/y.jpg";
  assert(attachments({ media: [P] }).text === "사진 1장", "C3 사진 1 → 「사진 1장」");
  assert(attachments({ media: [P, Q], quote: { media: [P] } }).text === "사진 2장 · 인용 글 사진 1장", "C3 사진 2 + 인용 사진 1");
  assert(attachments({ media: [V] }).text === "영상 1개" && attachments({ media: [TV] }).video === 1, "C3 영상 썸네일(amplify · video_thumb) → 「영상 1개」");
  const none = attachments({});
  assert(none.text === "" && none.photo === 0 && none.video === 0, "C3 아무것도 없음 → 빈 결과");
}

// ── C4 · 글자색 · 번역 칸 바탕 (운영 레인 색 5개)
{
  const lanes = [["아라레", [225, 187, 139], "#17171b"], ["유노", [151, 84, 103], "#ffffff"], ["노노카", [197, 179, 197], "#17171b"],
    ["리츠", [193, 201, 214], "#17171b"], ["미야코", [169, 151, 190], "#17171b"]];
  // 번역 칸은 --paper 를 바탕 위에 섞은 색 — 그 위에서 글자 대비를 잰다
  const blend = (rgb, paper) => {
    const c = parseRgb(rgb), m = paper.match(/rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)/);
    const a = +m[4]; return [0, 1, 2].map((i) => c[i] * (1 - a) + (+m[i + 1]) * a);
  };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  for (const [name, c, want] of lanes) {
    const rgb = `rgb(${c[0]} ${c[1]} ${c[2]})`;
    const ink = inkFor(rgb);
    assert(ink === want, `C4 ${name}(${c.join("/")}) 글자색 = ${want === "#ffffff" ? "흰색" : "검정"}`);
    const p = paletteFor(rgb);
    const hex = [1, 3, 5].map((i) => parseInt(ink.slice(i, i + 2), 16));
    const ratio = contrast(lum(blend(rgb, p.paper)), lum(hex));
    assert(ratio >= 4.5, `C4 ${name} 번역 칸 위 대비 ${ratio.toFixed(2)}:1 ≥ 4.5`);
  }
  const fb = paletteFor("");
  assert(fb.bg === "#3a3a3e" && fb.ink === "#ffffff" && fb.paper === paperFor("#ffffff"), "C4 색 없음 → 폴백 바탕 · 흰 글자");
  assert(paperFor("#17171b") === "rgba(255, 255, 255, 0.38)" && paperFor("#ffffff") === "rgba(0, 0, 0, 0.2)", "C4 번역 칸 바탕은 글자 반대쪽");
}

// ── C5 · 시각 표기 (KST)
{
  const now = Date.parse("2026-10-27T07:05:00+09:00");           // 10/27 07:05 KST
  const today = Date.parse("2026-10-27T07:00:00+09:00");           // 같은 날 · 5분 전
  assert(postedLabel(today, now) === "07:00 · 5분 전", "C5 오늘 글 = HH:MM · N분 전");
  const yest = Date.parse("2026-10-26T22:30:00+09:00");
  assert(postedLabel(yest, now).startsWith("10/26 22:30"), "C5 어제 글 = M/D HH:MM");
  const prev = Date.parse("2026-10-27T07:00:00+09:00");
  assert(replyLabel(prev + 30 * MIN, prev, now) === "이어서 · 07:30 · 30분 뒤", "C5 간격 30분 → 「30분 뒤」");
  assert(gapLabel(7 * H + 31 * MIN) === "7시간 31분 뒤", "C5 간격 7시간 31분");
  assert(gapLabel(2 * 24 * H) === "2일 뒤", "C5 간격 2일");
  assert(unpostedLabel(today) === "07:00 등록", "C5 게시 시각 모름 → 「HH:MM 등록」");
  assert(clockLabel(today, now) === "07:00", "C5 clockLabel 오늘");
  const k = kstParts(Date.parse("2026-10-26T15:00:00Z"));
  assert(k.d === 27 && k.h === 0, "C5 KST 날짜 경계(UTC 15:00 = KST 다음날 00시)");
}

// ── C6 · estimateCardH
{
  const plain = estimateCardH({});
  const one = estimateCardH({ media: ["https://x/a.jpg"] });
  const two = estimateCardH({ media: ["https://x/a.jpg", "https://x/b.jpg"] });
  const quoteP = estimateCardH({ quote: { media: ["https://x/q.jpg"] } });
  assert(plain >= 230 && plain < one && one < two && two < quoteP, `C6 늘어나는 순서: ${plain} < ${one} < ${two} < ${quoteP}`);
}

// ── C7 · 새 글 자리
{
  const a = msg("a", 1), b = msg("b", 2, { reply_to_id: "a" }), c = msg("c", 3), d = msg("d", 4);
  const units = chains([a, b, c, d]);
  const readSet = new Set(["a", "c", "d"]);
  const partial = firstUnread(units, (m) => readSet.has(m.id));
  assert(partial && partial.id === "b" && partial.inChain === true, "C7 읽음 일부: 글타래 안 답글 b 앞");
  const all = firstUnread(units, () => true);
  assert(all === null, "C7 전부 읽음 → 자리 없음");
  const onlyReplyUnread = firstUnread(units, (m) => m.id !== "b");
  assert(onlyReplyUnread && onlyReplyUnread.id === "b" && onlyReplyUnread.inChain, "C7 글타래 중간 답글만 안 읽음 → 그 답글 앞(글타래 안)");
  const firstRoot = firstUnread(units, (m) => m.id !== "c");
  assert(firstRoot && firstRoot.id === "c" && !firstRoot.inChain, "C7 단독 글이 첫 안 읽은 글 → 글타래 밖");
}

// ── C8 · 면 저장값 (mew:tllang)
{
  assert(faceOf("ko") === 0 && langOf(0) === "ko", "C8 \"ko\" → 번역(0)");
  assert(faceOf("orig") === 1 && langOf(1) === "orig", "C8 \"orig\" → 원문(1)");
  assert(faceOf(null) === 0 && faceOf(undefined) === 0, "C8 저장값 없음 → 번역");
  assert(faceOf("weird") === 0 && faceOf("1") === 0, "C8 이상한 값 → 번역");
}

// ── 보조: 서명 · 이름
{
  const l1 = [{ id: "1", text_ko: "가" }], l2 = [{ id: "1", text_ko: "가", reply_to_id: "9" }];
  assert(sigOf(l1) !== sigOf(l2), "서명: 답글 연결이 바뀌면 다름");
  assert(sigOf(l1) === sigOf([{ id: "1", text_ko: "가" }]), "서명: 같은 내용이면 같음");
  assert(shortName("나카마치 아라레") === "아라레" && shortName("") === "", "이름: 마지막 낱말");
}

// ── C9 · 열린 시트 갱신 계획 (v4.9.1, reconcileUnits)
{
  const js = (v) => JSON.stringify(v);
  const same = reconcileUnits([["a"], ["b", "c"]], [["a"], ["b", "c"]]);
  assert(js(same) === js([{ from: 0, add: [], keep: true }, { from: 1, add: [], keep: true }]), "C9 그대로 → 붙일 것 없음 · 모두 제자리");
  const tail = reconcileUnits([["a"], ["b"]], [["a"], ["b"], ["d"]]);
  assert(tail && tail[2].from === -1 && js(tail[2].add) === js(["d"]) && tail[0].keep && tail[1].keep, "C9 맨 뒤 새 글 → 새 글타래만 덧붙임");
  const grow = reconcileUnits([["a"], ["b"]], [["a"], ["b", "e"]]);
  assert(grow && grow[1].from === 1 && js(grow[1].add) === js(["e"]) && grow[1].keep, "C9 마지막 글에 자기 답글 → 그 글타래 뒤에 붙임");
  const lift = reconcileUnits([["a"], ["b"], ["c"]], [["b"], ["c"], ["a", "f"]]);
  assert(lift && lift[2].from === 0 && js(lift[2].add) === js(["f"]) && !lift[2].keep && lift[0].keep && lift[1].keep,
    "C9 옛 글에 답글 → 그 글타래가 끝으로(끌어올리기) — 그 하나만 옮김");
  assert(reconcileUnits([["a"], ["b"]], [["b"]]) === null, "C9 글이 빠짐(만료) → 다시 그림");
  assert(reconcileUnits([["a", "c"]], [["a", "b", "c"]]) === null, "C9 글타래 중간에 끼어듦 → 다시 그림");
  assert(reconcileUnits([["b"]], [["a", "b"]]) === null, "C9 원글이 뒤늦게 와서 뿌리가 바뀜 → 다시 그림");
  const older = reconcileUnits([["b"]], [["a"], ["b"]]);
  assert(older && older[0].from === -1 && older[1].keep, "C9 더 이른 시각의 새 글 → 앞에 끼움(옛 글은 제자리)");
  const real = reconcileUnits(chains([msg("a", t0), msg("b", t0 + MIN)]).map((u) => u.map((m) => m.id)),
    chains([msg("a", t0), msg("b", t0 + MIN), msg("c", t0 + 2 * MIN, { reply_to_id: "b" })]).map((u) => u.map((m) => m.id)));
  assert(real && real.length === 2 && js(real[1].add) === js(["c"]), "C9 chains 결과와 맞물림");
}

// ── C10 · 미디어 목록 · 작은 그림 주소 · 격자 (v4.9.3)
{
  const P = "https://pbs.twimg.com/media/aaa.jpg", V = "https://pbs.twimg.com/amplify_video_thumb/1/img/x.jpg";
  const items = mediaItems([P, V, "", null]);
  assert(items.length === 2 && !items[0].video && items[1].video, "C10 mediaItems: 빈 값 빼고 영상 썸네일 구분");
  assert(smallUrl(P) === P + "?name=small", "C10 smallUrl: name=small 붙임");
  assert(smallUrl("https://pbs.twimg.com/media/x.png?name=orig") === "https://pbs.twimg.com/media/x.png?name=small", "C10 smallUrl: name=orig → small");
  assert(smallUrl("https://pbs.twimg.com/media/x?format=jpg&name=large") === "https://pbs.twimg.com/media/x?format=jpg&name=small", "C10 smallUrl: 다른 인자는 그대로");
  assert(smallUrl("https://example.com/a.jpg") === "https://example.com/a.jpg", "C10 smallUrl: pbs 가 아니면 그대로");
  const g = [0, 1, 2, 3, 4, 6].map(gridOf);
  assert(g[0].cls === "" && g[1].cls === "g1" && g[3].cls === "g3" && g[4].shown === 4 && g[4].more === 0, "C10 gridOf: 0~4칸");
  assert(g[5].cls === "g4" && g[5].shown === 4 && g[5].more === 2, "C10 gridOf: 6개 → 4칸 + 「+2」");
}

// ── C11 · X 카드 치수 (2026-10-28 운영 X 카드 실측값 그대로)
{
  assert(singleRatio(526, 900) === 1 && singleRatio(1200, 675) === 1200 / 675 && singleRatio(0, 0) === 16 / 9, "C11 singleRatio: 세로 → 1:1 · 가로 → 원래 비율 · 모름 → 16:9");
  // 카드 폭 505 → 묶음 폭 471: 2~4칸 266(16:9) · 세로 사진 1칸 471 · 인용 안(폭 469, 테두리 없음) 264
  assert(mediaBoxH(4, 471, 0, 1) === 266 && mediaBoxH(2, 371, 0, 1) === 210 && mediaBoxH(3, 311, 0, 1) === 176, "C11 2~4칸 = 16:9 (471→266 · 371→210 · 311→176)");
  assert(mediaBoxH(1, 471, singleRatio(526, 900), 1) === 471, "C11 세로 사진 1칸 = 정사각형 471");
  assert(mediaBoxH(2, 469, 0, 0) === 264, "C11 인용 안 2칸(테두리 없음) 469→264");
  assert(mediaBoxH(0, 471, 0, 1) === 0, "C11 미디어 없음 → 0");
  // 실측 카드 높이: 영상3+사진1(본문 192) 671 · 세로 사진 1장(본문 266) 950 · 사진 2 + 인용(본문 120 · 사진 2)(본문 73) 1000 · 자기 답글(본문 50) 275
  const mix = { w: 505, reply: false, n: 4, ratio: 0, quote: null };
  assert(predictCardH({ ...mix, textH: 192 }) === 671 && xTextH(671, mix) === 192, "C11 영상3+사진1: 671 ↔ 본문 192");
  const one = { w: 505, reply: false, n: 1, ratio: singleRatio(526, 900), quote: null };
  assert(predictCardH({ ...one, textH: 266 }) === 950, "C11 세로 사진 1장: 950");
  const q = { w: 505, reply: false, n: 2, ratio: 0, quote: { textH: 120, n: 2, ratio: 0 } };
  assert(predictCardH({ ...q, textH: 73 }) === 1000 && xTextH(1000, q) === 73, "C11 사진 2 + 인용 사진 2: 1000 ↔ 본문 73");
  const re = { w: 505, reply: true, n: 0, ratio: 0, quote: null };
  assert(predictCardH({ ...re, textH: 50 }) === 275 && xTextH(275, re) === 50, "C11 자기 답글(「님에게 보내는 답글」 줄): 275 ↔ 본문 50");
  assert(xTextH(100, re) === 0, "C11 카드가 고정 치수보다 작으면 본문 0");
}

// ── C12 · 스크롤 자리 되돌리기
{
  assert(restoreTarget(undefined, ["a"]) === null && restoreTarget({ bottom: true }, ["a"]) === null, "C12 기록 없음 · 맨 아래였음 → 맨 아래");
  const t = restoreTarget({ id: "b", off: 37 }, ["a", "b"]);
  assert(t && t.id === "b" && t.off === 37, "C12 보던 글이 있으면 그 글 + 어긋남");
  assert(restoreTarget({ id: "z", off: 5 }, ["a", "b"]) === null, "C12 보던 글이 사라졌으면 맨 아래");
}

// ── C13 · ↓ 동그라미
{
  assert(fabMode(0, 0) === "off" && fabMode(160, 0) === "off", "C13 맨 아래 160px 안 · 새 글 없음 → 안 뜸");
  assert(fabMode(161, 0) === "plain", "C13 160px 넘게 올림 → 「맨 아래로」(숫자 없음)");
  assert(fabMode(0, 2) === "count" && fabMode(500, 1) === "count", "C13 기다리는 새 글 → 숫자 · 흔들기");
}

// ── C14 · 밀기 판정
{
  assert(swipeTo(0, -0.26) === 1 && swipeTo(0, -0.25) === 0, "C14 번역 → 원문: 왼쪽으로 25% 를 넘겨야");
  assert(swipeTo(0, 0.9) === 0, "C14 번역에서 오른쪽(갈 면 없음) → 그대로");
  assert(swipeTo(1, 0.3) === 0 && swipeTo(1, -0.9) === 1, "C14 원문 → 번역은 오른쪽, 반대쪽은 그대로");
}

// ── C15 · 날짜 구분선 · 시각 title
{
  assert(dayLabel(Date.parse("2026-10-28T12:00:00+09:00")) === "10월 28일 (수)", "C15 10/28 → 「10월 28일 (수)」");
  assert(dayLabel(Date.parse("2026-10-27T15:30:00Z")) === "10월 28일 (수)", "C15 UTC 15:30 = KST 다음날 00:30");
  const now = Date.parse("2026-10-28T21:05:00+09:00");
  assert(fullLabel(Date.parse("2026-10-28T21:02:00+09:00"), now) === "10/28 21:02 · 3분 전", "C15 fullLabel");
}

console.log(`\n✅ tweetlogic selfcheck 통과 (${n}건)`);
