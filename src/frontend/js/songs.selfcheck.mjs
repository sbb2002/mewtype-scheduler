/**
 * songs.js 순수 로직 자동 테스트 (v4.2.0).
 * node songs.selfcheck.mjs 로 실행. 프레임워크 없음.
 */
import { readFileSync } from "node:fs";
import { isNewSong, hasNewSong, displayKo, kanaToHangul, normalize, prepareSong, matches, viewSongs, matchRange } from "./songs.js";

let n = 0;
function assert(cond, msg) {
  n++;
  if (!cond) { console.error(`❌ FAIL (${n}): ${msg}`); process.exit(1); }
  console.log(`✓ ${msg}`);
}

// ── 가나 → 한글 ──
assert(kanaToHangul("ゆきとき") === "유키토키", "ゆきとき → 유키토키 (어두 ゆ, 어중 き·と·き)");
assert(kanaToHangul("きみが") === "기미가", "어두 き 는 기, 어중은 카행 유지");
assert(kanaToHangul("ちょうわくせいXへのたび") === "초와쿠세이X헤노타비", "ちょう 장음 생략 · 영문 X 유지");
assert(kanaToHangul("まよなかゆうえんち") === "마요나카유엔치", "ゆう 장음 생략");
assert(kanaToHangul("ジレンマ").length > 0 && kanaToHangul("ジレンマ") === "지렌마", "가타카나 입력 · ん 은 ㄴ 받침");
assert(kanaToHangul("てれぱしー") === "데레파시", "ー 생략 · 어두 て 는 데");
assert(kanaToHangul("いっぱい") === "잇파이", "っ 는 ㅅ 받침");

assert(kanaToHangul("ゆめはトゥルーエンド") === "유메하토루엔도" && kanaToHangul("フェイス") === "후이스", "작은 모음(ゥ ェ)은 지운다");

// ── 정규화 ──
assert(normalize("ＺＥＡＬ of Proud") === "zeal of proud", "전각 → 반각 · 소문자");
assert(normalize("ユキトキ") === normalize("ゆきとき"), "가타카나 = 히라가나");
assert(normalize("유키") === normalize("유기"), "한글 초성 평음화 (ㅋ=ㄱ)");

// ── 검색 ──
const songs = JSON.parse(readFileSync(new URL("../assets/songs.json", import.meta.url), "utf8")).songs;
assert(songs.length === 64, "곡 64개");
assert(new Set(songs.map((s) => s.id)).size === 64, "video_id 중복 없음");
const prep = songs.map((s) => prepareSong(s, s.title === "ZEAL of proud" ? ["질오브"] : []));
const find = (q) => prep.filter((s) => matches(s, q)).map((s) => s.title);
assert(find("ゆきとき").includes("ユキトキ"), "가나 독음으로 검색");
assert(find("ユキトキ").includes("ユキトキ"), "곡명(가타카나)으로 검색");
assert(find("유키토키").includes("ユキトキ"), "한글 독음으로 검색");
assert(find("유기도기").includes("ユキトキ"), "한글 독음 표기 차이 흡수");
assert(find("마요나카").includes("真夜中遊園地"), "한글 독음 부분 일치");
assert(find("질오브").includes("ZEAL of proud"), "사용자 별칭으로 검색");
assert(find("zeal").includes("ZEAL of proud"), "영문 대소문자 무시");
assert(find("").length === 64, "빈 검색어 = 전부");
assert(find("zzzzqq").length === 0, "일치 없음");
assert(find("solo").length === 0 || !find("solo").some((t) => !t.toLowerCase().includes("solo")), "종류 텍스트는 검색 대상 아님");

// ── 한글 음차 표시 ──
assert(displayKo(prepareSong({ title: "愛は衝動", reading: "あいはしょうどう" })) === "아이하쇼도", "일본어 곡명 → 한글 음차 표시 (조사 は 도 하 로 바뀐다 — 알려진 단순화)");
assert(displayKo(prepareSong({ title: "TearJerker", reading: "てあじゃーかー" })) === "", "영문 곡명은 음차 표시 안 함");
assert(displayKo(prepareSong({ title: "夢我夢中", reading: "" })) === "", "독음 없으면 표시 안 함");

// ── NEW 배지 (발매일 +14일, 그날 포함 · KST) ──
const NOW = Date.parse("2026-10-10T00:00:00Z");   // = KST 10-10 09:00
assert(hasNewSong([{ date: "2026-10-05" }], NOW), "발매 5일 뒤 → NEW");
assert(hasNewSong([{ date: "2026-09-26" }], NOW), "발매일 +14일째(KST 10-10) → 아직 NEW");
assert(!hasNewSong([{ date: "2026-09-25" }], NOW), "발매일 +15일째 → NEW 없음");
assert(!hasNewSong([{ date: "2026-10-12" }], NOW), "발매일 전(미래 날짜) → NEW 아님");
assert(!hasNewSong([{ title: "날짜 없음" }, { date: "" }, { date: "x" }], NOW) && !hasNewSong([], NOW) && !hasNewSong(null, NOW), "date 없음 · 이상한 값 · 빈 목록 → NEW 없음");
assert(isNewSong({ date: "2026-10-05" }, NOW) && !isNewSong({ title: "시드" }, NOW), "곡 하나 단위 NEW 판정");
assert(!isNewSong({ date: "2026-10-05", added_at: "2026-10-09T00:00:00Z" }, Date.parse("2026-10-30T00:00:00Z")), "기준은 added_at 이 아니라 발매일");

// ── 필터 · 정렬 ──
const opts = { query: "", kind: "all", sortBy: "date", dir: "desc" };
const byDateDesc = viewSongs(prep, opts);
assert(byDateDesc[0].date >= byDateDesc[byDateDesc.length - 1].date, "날짜 내림차순");
assert(viewSongs(prep, { ...opts, dir: "asc" })[0].date === "2023-11-28", "날짜 오름차순 첫 곡 = 가장 오래된 곡");
assert(viewSongs(prep, { ...opts, kind: "cover" }).every((s) => s.kind === "cover"), "종류 필터");
assert(prep.every((s) => s.kind === "cover" || s.kind === "original"), "종류는 original / cover 둘뿐(solo 없음)");
const byName = viewSongs(prep, { ...opts, sortBy: "name", dir: "asc" });
assert(byName.length === 64, "이름순 정렬은 곡을 잃지 않음");
assert(prep.length === 64 && prep[0].date === "2023-11-28", "원본 배열은 건드리지 않음");

// ── 신곡 필터 ──
const ymd = (daysAgo) => new Date(Date.now() + 9 * 3600e3 - daysAgo * 86400e3).toISOString().slice(0, 10);   // KST 날짜
const baseNew = viewSongs(prep, { ...opts, kind: "new" }).length;   // 시드 곡 중 최근 14일 발매가 이미 있을 수 있다
const withNew = [{ ...prep[0], date: ymd(0) }, ...prep.slice(1)];
assert(viewSongs(withNew, { ...opts, kind: "new" }).length === baseNew + 1, "신곡 필터 = 발매일 +14일 안의 곡만");
assert(viewSongs([{ ...prep[0], date: ymd(15) }], { ...opts, kind: "new" }).length === 0, "발매 15일 전 곡은 신곡 아님");

// ── 신곡은 항상 맨 위 · 최신순 ──
const mixed = prep.map((s) => (s.title === "ユキトキ" ? { ...s, date: ymd(4) } : s.title === "ジレンマ" ? { ...s, date: ymd(1) } : s));
for (const o of [{ sortBy: "date", dir: "desc" }, { sortBy: "date", dir: "asc" }, { sortBy: "name", dir: "asc" }]) {
  const v = viewSongs(mixed, { query: "", kind: "all", ...o });
  const k = v.filter((s) => isNewSong(s)).length;
  assert(v.slice(0, k).every((s) => isNewSong(s)) && v.slice(k).every((s) => !isNewSong(s)), `신곡은 정렬(${o.sortBy} ${o.dir})과 무관하게 맨 위`);
  assert(v.findIndex((s) => s.title === "ジレンマ") < v.findIndex((s) => s.title === "ユキトキ") && v.findIndex((s) => s.title === "ユキトキ") < k, `신곡끼리는 최신순 (${o.sortBy} ${o.dir})`);
}
const nv = viewSongs(mixed, { ...opts, kind: "new" }).map((s) => s.title);
assert(nv.indexOf("ジレンマ") < nv.indexOf("ユキトキ") && nv.includes("ユキトキ"), "신곡 필터도 최신순");

// ── 강조 구간 ──
assert(JSON.stringify(matchRange("ユキトキ", "きと")) === "[1,3]", "강조 구간 (가타카나 ↔ 히라가나)");
assert(matchRange("abc", "") === null && matchRange("abc", "zz") === null, "일치 없음이면 null");

console.log(`\n${n}개 통과`);
