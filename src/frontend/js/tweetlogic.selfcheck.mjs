/**
 * tweetlogic.js 순수 로직 자동 테스트 (트윗 시트, V1-C 의 C1~C8). node tweetlogic.selfcheck.mjs 로 실행. 프레임워크 없음. DOM 을 쓰지 않는다.
 */
import {
  chains, attachments, inkFor, paperFor, paletteFor, contrast, parseRgb, kstParts,
  postedLabel, replyLabel, unpostedLabel, gapLabel, clockLabel, estimateCardH, firstUnread,
  faceOf, langOf, sigOf, shortName,
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

console.log(`\n✅ tweetlogic selfcheck 통과 (${n}건)`);
