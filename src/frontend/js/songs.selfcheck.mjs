/**
 * songs.js 순수 로직 자동 테스트 (v4.2.0).
 * node songs.selfcheck.mjs 로 실행. 프레임워크 없음.
 */
import { readFileSync } from "node:fs";
import { kanaToHangul, normalize, prepareSong, matches, viewSongs, matchRange } from "./songs.js";

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

// ── 정규화 ──
assert(normalize("ＺＥＡＬ of Proud") === "zeal of proud", "전각 → 반각 · 소문자");
assert(normalize("ユキトキ") === normalize("ゆきとき"), "가타카나 = 히라가나");
assert(normalize("유키") === normalize("유기"), "한글 초성 평음화 (ㅋ=ㄱ)");

// ── 검색 ──
const songs = JSON.parse(readFileSync(new URL("../assets/songs.json", import.meta.url), "utf8")).songs;
assert(songs.length === 65, "곡 65개");
assert(new Set(songs.map((s) => s.id)).size === 65, "video_id 중복 없음");
const prep = songs.map((s) => prepareSong(s, s.title === "ZEAL of proud" ? ["질오브"] : []));
const find = (q) => prep.filter((s) => matches(s, q)).map((s) => s.title);
assert(find("ゆきとき").includes("ユキトキ"), "가나 독음으로 검색");
assert(find("ユキトキ").includes("ユキトキ"), "곡명(가타카나)으로 검색");
assert(find("유키토키").includes("ユキトキ"), "한글 독음으로 검색");
assert(find("유기도기").includes("ユキトキ"), "한글 독음 표기 차이 흡수");
assert(find("마요나카").includes("真夜中遊園地"), "한글 독음 부분 일치");
assert(find("질오브").includes("ZEAL of proud"), "사용자 별칭으로 검색");
assert(find("zeal").includes("ZEAL of proud"), "영문 대소문자 무시");
assert(find("").length === 65, "빈 검색어 = 전부");
assert(find("zzzzqq").length === 0, "일치 없음");
assert(find("solo").length === 0 || !find("solo").some((t) => !t.toLowerCase().includes("solo")), "종류 텍스트는 검색 대상 아님");

// ── 필터 · 정렬 ──
const opts = { query: "", kind: "all", sortBy: "date", dir: "desc" };
const byDateDesc = viewSongs(prep, opts);
assert(byDateDesc[0].date >= byDateDesc[byDateDesc.length - 1].date, "날짜 내림차순");
assert(viewSongs(prep, { ...opts, dir: "asc" })[0].date === "2023-11-28", "날짜 오름차순 첫 곡 = 가장 오래된 곡");
assert(viewSongs(prep, { ...opts, kind: "cover" }).every((s) => s.kind === "cover"), "종류 필터");
const byName = viewSongs(prep, { ...opts, sortBy: "name", dir: "asc" });
assert(byName.length === 65, "이름순 정렬은 곡을 잃지 않음");
assert(prep.length === 65 && prep[0].date === "2023-11-28", "원본 배열은 건드리지 않음");

// ── 강조 구간 ──
assert(JSON.stringify(matchRange("ユキトキ", "きと")) === "[1,3]", "강조 구간 (가타카나 ↔ 히라가나)");
assert(matchRange("abc", "") === null && matchRange("abc", "zz") === null, "일치 없음이면 null");

console.log(`\n${n}개 통과`);
