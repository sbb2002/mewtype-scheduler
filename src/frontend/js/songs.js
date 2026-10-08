// songs.js — (v4.2.0) 플레이어 곡 목록의 순수 로직: 검색 정규화 · 가나→한글 독음 변환 · 필터/정렬. DOM · 네트워크 접근 없음.
// 곡 데이터는 assets/songs.json (원본: ref/player/songs_release.json). 사용자 별칭은 player.js 가 localStorage 로 관리해 여기에 넘긴다.

export const KIND_LABEL = { original: "오리지널", cover: "커버" };   // 솔로 구분 없음 — 솔로도 커버(운영자 결정 2026-10-06)

// ── 독음(가나) → 한글 ────────────────────────────────────────────────
// 외래어 표기법을 단순화한 것: 어두 か·た행은 가·다, 어중은 카·타. ん=ㄴ 받침, っ=ㅅ 받침,
// 장음(ー · お/ゆ단 뒤의 う)은 생략. 조사 は 도 글자 그대로 하 로 바뀐다.
const H_BASE = {
  あ: "아", い: "이", う: "우", え: "에", お: "오", か: "카", き: "키", く: "쿠", け: "케", こ: "코",
  さ: "사", し: "시", す: "스", せ: "세", そ: "소", た: "타", ち: "치", つ: "츠", て: "테", と: "토",
  な: "나", に: "니", ぬ: "누", ね: "네", の: "노", は: "하", ひ: "히", ふ: "후", へ: "헤", ほ: "호",
  ま: "마", み: "미", む: "무", め: "메", も: "모", や: "야", ゆ: "유", よ: "요",
  ら: "라", り: "리", る: "루", れ: "레", ろ: "로", わ: "와", を: "오",
  が: "가", ぎ: "기", ぐ: "구", げ: "게", ご: "고", ざ: "자", じ: "지", ず: "즈", ぜ: "제", ぞ: "조",
  だ: "다", ぢ: "지", づ: "즈", で: "데", ど: "도", ば: "바", び: "비", ぶ: "부", べ: "베", ぼ: "보",
  ぱ: "파", ぴ: "피", ぷ: "푸", ぺ: "페", ぽ: "포",
};
const H_COMBO = {
  き: ["캬", "큐", "쿄"], し: ["샤", "슈", "쇼"], ち: ["차", "추", "초"], に: ["냐", "뉴", "뇨"],
  ひ: ["햐", "휴", "효"], み: ["먀", "뮤", "묘"], り: ["랴", "류", "료"], ぎ: ["갸", "규", "교"],
  じ: ["자", "주", "조"], び: ["뱌", "뷰", "뵤"], ぴ: ["퍄", "퓨", "표"],
};
const H_INIT = { 카: "가", 키: "기", 쿠: "구", 케: "게", 코: "고", 타: "다", 치: "지", 츠: "즈", 테: "데", 토: "도" };
const VOWEL_O_U = new Set([8, 12, 13, 17]);   // ㅗ ㅛ ㅜ ㅠ — 뒤따르는 う 는 장음이라 생략

const isHangul = (c) => c >= 0xac00 && c <= 0xd7a3;
const hasNoBatchim = (c) => isHangul(c) && (c - 0xac00) % 28 === 0;

/** 가나(히라가나·가타카나) 독음 → 한글. 가나가 아닌 글자(영문 등)는 그대로 둔다. */
export function kanaToHangul(src) {
  const t = String(src || "").replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 96));
  let out = "";
  let atStart = true;
  const last = () => out.charCodeAt(out.length - 1);
  for (let i = 0; i < t.length; ) {
    const c = t[i];
    const n = t[i + 1];
    if (H_COMBO[c] && n && "ゃゅょ".includes(n)) { out += H_COMBO[c]["ゃゅょ".indexOf(n)]; i += 2; atStart = false; continue; }
    if ("ぁぃぅぇぉ".includes(c)) { i++; continue; }   // 작은 모음(トゥ · フェ …) — 앞 글자 모음을 바꾸는 글자라 한글에선 지운다(ト+ゥ → 토)
    if (c === "ん") { if (hasNoBatchim(last())) out = out.slice(0, -1) + String.fromCharCode(last() + 4); i++; continue; }
    if (c === "っ") { if (hasNoBatchim(last())) out = out.slice(0, -1) + String.fromCharCode(last() + 19); i++; continue; }
    if (c === "ー") { i++; continue; }
    if (c === "う" && isHangul(last()) && VOWEL_O_U.has(Math.floor(((last() - 0xac00) % 588) / 28))) { i++; continue; }
    if (H_BASE[c]) {
      let s = H_BASE[c];
      if (atStart && H_INIT[s]) s = H_INIT[s];
      out += s; atStart = false; i++; continue;
    }
    out += c;
    atStart = /\s/.test(c);
    i++;
  }
  return out;
}

// ── 검색 정규화 ──────────────────────────────────────────────────────
// 대소문자 · 전각/반각(NFKC) 무시, 가타카나 → 히라가나, 한글 초성 평음화(ㅋ→ㄱ ㅌ→ㄷ ㅍ→ㅂ ㅊ→ㅈ, 된소리→평음).
// 평음화는 독음 변환의 표기 차이(키/기, 타/다)를 흡수하려는 것. 글자 수가 그대로라 강조 위치가 어긋나지 않는다.
const FOLD_INITIAL = { 1: 0, 15: 0, 4: 3, 16: 3, 8: 7, 17: 7, 10: 9, 13: 12, 14: 12 };
function foldHangul(x) {
  return x.replace(/[가-힣]/g, (c) => {
    const n = c.charCodeAt(0) - 0xac00;
    const ini = Math.floor(n / 588);
    return String.fromCharCode(0xac00 + (FOLD_INITIAL[ini] ?? ini) * 588 + (n % 588));
  });
}
export function normalize(x) {
  const t = String(x || "").normalize("NFKC").toLowerCase().replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 96));
  return foldHangul(t);
}

/** 곡 하나에 검색용 필드(독음 한글 · 정규화 문자열)를 붙인다. aliases = 사용자 별칭 배열. */
export function prepareSong(raw, aliases = []) {
  const reading = raw.reading || "";
  const readingKo = reading ? kanaToHangul(reading) : "";
  return {
    ...raw,
    reading,
    readingKo,
    aliases: aliases.slice(),
    _n: { title: normalize(raw.title), reading: normalize(reading), readingKo: normalize(readingKo), aliases: aliases.map(normalize) },
  };
}

/** 화면에 보여 줄 한글 음차 — 곡명에 일본어(가나·한자)가 있고 독음이 있는 곡만. 영문 곡명 · 독음 없는 곡은 빈 문자열. */
export function displayKo(song) {
  return /[぀-ヿ㐀-鿿]/.test(song.title || "") ? song.readingKo || "" : "";
}

/** 신곡인가(곡 하나) / 있는가(목록). — 곡의 **발매일(`date`)** 부터 `days`일(기본 14일) 뒤까지(그날 포함, KST 기준) true.
 *  발매일 전(미래 날짜)은 신곡이 아니다. 이전(~2026-10-08)엔 등록 시각 `added_at` 기준 7일이었으나 발매일 +14일로 바꿨다(운영자 결정 2026-10-08). */
export function isNewSong(song, nowMs = Date.now(), days = 14) {
  const t = Date.parse(`${song && song.date}T00:00:00+09:00`);
  return Number.isFinite(t) && nowMs >= t - 300000 && nowMs < t + (days + 1) * 86400000;   // 시계 오차 5분까지 허용
}
export function hasNewSong(songs, nowMs = Date.now(), days = 14) {
  return (songs || []).some((s) => isNewSong(s, nowMs, days));
}

/** 검색어가 곡명 · 독음(가나/한글) · 별칭 중 하나라도 부분 일치하는가. 빈 검색어는 전부 통과. */
export function matches(song, query) {
  const q = normalize(String(query || "").trim());
  if (!q) return true;
  const n = song._n;
  return n.title.includes(q) || n.reading.includes(q) || n.readingKo.includes(q) || n.aliases.some((a) => a.includes(q));
}

/** 종류 필터 + 검색 + 정렬. sortBy: "date" | "name", dir: "asc" | "desc". 원본 배열은 건드리지 않는다.
 *  **신곡(발매일 +14일 안의 곡)은 어떤 정렬이든 항상 맨 위에, 최신 순**(발매일 내림차순 → 등록 시각 → 곡명)으로 나온다. 나머지는 고른 정렬대로. */
export function viewSongs(songs, { query = "", kind = "all", sortBy = "date", dir = "desc" } = {}) {
  const sign = dir === "asc" ? 1 : -1;
  const now = Date.now();
  const byKind = (s) => kind === "all" || (kind === "new" ? isNewSong(s, now) : s.kind === kind);   // "new" = 발매일 +14일 안의 신곡
  const list = songs.filter((s) => byKind(s) && matches(s, query));
  const newest = (a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0)
    || String(b.added_at || "").localeCompare(String(a.added_at || ""))
    || a.title.localeCompare(b.title, "ja");
  const fresh = list.filter((s) => isNewSong(s, now)).sort(newest);
  const rest = list.filter((s) => !isNewSong(s, now)).sort((a, b) => {
    const byName = (a.reading || a.title).localeCompare(b.reading || b.title, "ja");
    if (sortBy === "name") return sign * byName;
    const byDate = a.date < b.date ? -1 : a.date > b.date ? 1 : 0;
    return byDate !== 0 ? sign * byDate : a.title.localeCompare(b.title, "ja");   // 같은 날 공개된 곡은 곡명순으로 고정
  });
  return [...fresh, ...rest];
}

/** text 안에서 query 가 일치하는 구간 [start, end) 를 돌려준다. 정규화로 글자 수가 달라지는 텍스트는 null (강조 생략). */
export function matchRange(text, query) {
  const q = normalize(String(query || "").trim());
  if (!q || !text) return null;
  const t = normalize(text);
  if (t.length !== text.length) return null;
  const i = t.indexOf(q);
  return i < 0 ? null : [i, i + q.length];
}
