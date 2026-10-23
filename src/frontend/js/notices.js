// notices.js — 예고판 상단 「소식」 막대 (v2.7 → v4.6.4 개편). notices.json 을 읽어 표시한다.
// (v4.6.4) 디자인 = 운영자 승인 시안 — PC 는 날짜별 묶음, 모바일(≤767px)은 분류 칩 막대 + 카드. 제목은 둘 다 15.5px 한 줄(넘치면 …).
//   PC   접힘: [소식] [오늘 n · 7일 안 n] [5초마다 한 줄씩 넘어가는 티커] [▾] [테마] — 티커 제목을 누르면 목록을 펼치고 그 소식 팝업을 고정
//        펼침: 행사 배너 → [분류 칩 · 한글|원문] → 날짜별 묶음(날짜 칸 「10/24 (토) TODAY」 + 소식 줄)
//   모바일 접힘: [램프] [분류별 건수 칩 — 움직이지 않음, 누르면 그 분류로 펼침] [▾] [테마]
//        펼침: 행사 배너 → [「전체 n건」 · 한글|원문 / 밑줄 탭] → 카드 1열
// (v4.7.0) 분류 = 소식마다 categories(목록) — 한 소식은 자기 분류 탭 모두에. 라이브공연 탭은 [공연별 | 날짜순], 공연별 = 공연 이름으로 묶음(_liveGroupsHTML).
// 「소식 팝업 카드」 = 소식 하나의 자세한 내용(분류 · D-day · 날짜 · 시각 · 출처 / 전체 제목 / 번역 본문 / X 공식 카드 / 링크).
//   PC: 소식 줄 호버 = 잠깐 열림(팝업으로 옮겨도 유지), 클릭 = 고정(한 번에 1개), ✕ · Esc · 바깥 클릭으로 닫힘 — 트윗 말풍선과 같은 방식.
//   모바일: 카드를 누르면 아래 시트(배경 · ✕ · Esc 로 닫힘) — 트윗 시트와 같은 방식.
//   본문은 번역(body_ko)만 그린다. 원문 · 이미지는 X 공식 카드가 보여 준다(v3.8.0 법률 자문 — 원문 재조립 금지). 원문 모드에서도 본문 원문은 안 그림.
//
// renderNotices(section, data) 는 poll 마다 호출된다. 내용(+ 행사 배너 · 화면 모드 · 오늘 날짜)이 안 바뀌면 다시 그리지 않는다.
// 분류 탭 · 언어 전환은 막대를 다시 만들지 않고 목록(과 PC 티커)만 다시 그린다. 만료(expires_at 지남) 소식은 프론트에서도 숨긴다.
// 데이터 글자는 전부 _esc/_attr 로 이스케이프한 뒤 넣는다(아이콘 SVG 만 고정 문자열).

import { visibleBanners, bannerHTML, bannerSig, mountBannerMotion, stopBannerMotion } from "./banners.js";   // (v4a) 펼친 목록 맨 위 행사 배너
import { themeButton } from "./theme.js";   // (v4.6.0) 막대 마지막 칸 = 밝게/어둡게 전환 버튼 (다시 그려도 같은 버튼을 옮겨 붙인다)
import { makeXCard, loadXCards, stopXCards } from "./tweets.js";   // (v4.6.4) 팝업 카드의 X 공식 카드 — 트윗 말풍선과 같은 코드

// (v4.7.0) 분류 6개 — 백엔드가 소식마다 `categories`(목록)를 붙인다: 라이브공연 · 오프라인행사 · 음원·굿즈 · 방송은 여럿 함께,
//   Our Notes(게임 계정 글) · 기타는 단독. 한 소식은 자기 분류 탭 모두에 나온다.
//   `categories` 가 없는 줄(v4.7.0 이전 · 판정 실패)은 옛 `category`(정규식 4종)를 바꿔 읽는다:
//   live(옛 「라이브예고」 — 실제로는 대부분 방송) → broadcast, release → goods, platform · 모르는 값 → etc, 출처가 게임 계정이면 game.
const CATS = [
  { id: "live", name: "라이브공연" },
  { id: "event", name: "오프라인행사" },
  { id: "goods", name: "음원·굿즈" },
  { id: "broadcast", name: "방송·영상" },   // (test/notice-r5) 10-23 운영자 — 프리미어 · 영상 공개도
  { id: "game", name: "Our Notes" },
  { id: "etc", name: "기타" },
];
const CAT_IDS = CATS.map((c) => c.id);
const CAT_NAME = Object.fromEntries(CATS.map((c) => [c.id, c.name]));
const LEGACY_READ = { live: "broadcast", release: "goods", platform: "etc" };
const GAME_SRC_RE = /^@?bang_dream_on$/i;   // config/channels.json game_accounts 의 handle
function _cats(n) {   // 이 소식의 분류 목록(CATS 순서)
  const c = n && Array.isArray(n.categories) ? CAT_IDS.filter((id) => n.categories.includes(id)) : [];
  if (c.length) return c;
  if (n && GAME_SRC_RE.test(String(n.src_handle || "").trim())) return ["game"];
  const old = n && n.category;
  return [LEGACY_READ[old] || (CAT_IDS.includes(old) ? old : "etc")];
}
// 아이콘으로 보일 분류 하나 — 분류 탭 안이면 그 탭의 분류, 전체면 첫 분류
function _cat(n) { const cs = _cats(n); return _st.tab !== "all" && cs.includes(_st.tab) ? _st.tab : cs[0]; }
function _catNames(n) { return _cats(n).map((k) => CAT_NAME[k]).join(" · "); }

// 아이콘 — 고정 문자열(데이터 아님). 분류 아이콘은 선(stroke), X 로고만 채움(fill)
const ICON = {
  live: '<rect x="9" y="2.5" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/>',
  event: '<path d="M5 21V3.5M5 4h12.5l-2.5 4 2.5 4H5"/>',
  broadcast: '<rect x="2.5" y="5" width="19" height="12.5" rx="2"/><path d="M8 21h8"/><path d="M10 8.6v5.3l4.6-2.65z" fill="currentColor" stroke="none"/>',
  goods: '<path d="M4.5 8h15l-1.2 13H5.7z"/><path d="M8.8 8V6.5a3.2 3.2 0 0 1 6.4 0V8"/>',
  game: '<rect x="2" y="7" width="20" height="11" rx="5.5"/><path d="M7 10.5v4M5 12.5h4"/><circle cx="15.8" cy="11.3" r="1.1" fill="currentColor" stroke="none"/><circle cx="18" cy="13.9" r="1.1" fill="currentColor" stroke="none"/>',
  etc: '<circle cx="12" cy="12" r="9"/><circle cx="8" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="16" cy="12" r="1.2" fill="currentColor" stroke="none"/>',
  x: '<path d="M18.9 2.6h3.3l-7.2 8.2 8.5 11.3h-6.7l-5.2-6.8-6 6.8H1.3l7.7-8.8L.7 2.6h6.9l4.7 6.2 5.6-6.2Zm-1.2 17.7h1.9L7.2 4.4H5.2l12.5 15.9Z"/>',
};

const LANG_KEY = "mew.notice.lang";       // 제목 언어(ko = 한글, ja = 원문) — 트윗 번역 설정과 별개
const LIVE_VIEW_KEY = "mew.notice.liveview";   // (v4.7.0) 라이브공연 탭 보기 방식(group = 공연별, date = 날짜순)
const LIST_CAP = { pc: 420, m: 460 };     // 펼친 목록에서 분류 줄 아래 소식 영역의 최대 높이(px). 행사 배너 · 분류 줄 높이는 따로 더한다
const VIEWPORT_CAP = 0.7;                 // 펼친 목록 전체는 화면 높이의 70% 를 넘지 않는다 — 넘으면 목록 안에서 스크롤
const MOBILE_MQ = "(max-width: 767px)";   // notices.css 의 모바일 기준과 같다
const PEEK_CARD_MS = 500;                 // 호버 팝업은 이만큼 머물러야 X 카드를 불러온다(목록을 훑을 때 iframe 이 줄줄이 뜨지 않게)
const PEEK_CLOSE_MS = 160;                // 호버 팝업 닫기 유예 — 줄과 팝업 사이 틈을 지나는 동안 닫히지 않게
const POP_GAP = 8;                        // 줄과 팝업 사이(꼬리 자리)
const POP_MAX_H = 560;                    // 팝업 최대 높이 — 화면 안 남은 공간이 더 작으면 그만큼만(안에서 스크롤)

const _st = { built: false, sig: "", idx: 0, open: false, timer: null, paused: false,
              bn: [], bnSig: "", rawBanners: null, lastData: undefined,
              lang: _loadLang(), tab: "all", mode: "pc", list: [], section: null, listEl: null,
              liveView: _loadLiveView(), liveOpen: {} };   // (v4.7.0) 라이브공연 탭 [공연별 | 날짜순] · 묶음별 펼침(키 → bool)
// PC 팝업 카드 상태 — mode: null | "peek"(호버) | "pin"(클릭 고정)
const _pop = { el: null, id: null, mode: null, sig: "", cardTimer: null, closeTimer: null };
// 모바일 시트 상태
const _sheet = { el: null, scrim: null, id: null, sig: "" };

function _loadLang() {
  try { return localStorage.getItem(LANG_KEY) === "ja" ? "ja" : "ko"; } catch (e) { return "ko"; }
}
function _saveLang(v) {
  try { localStorage.setItem(LANG_KEY, v); } catch (e) { /* 저장 못 해도 지금 화면은 바꾼다 */ }
}
function _isMobile() {
  return !!(window.matchMedia && window.matchMedia(MOBILE_MQ).matches);
}
function _reduceMotion() {
  return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}

function _todayKST() {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Seoul" }); // YYYY-MM-DD
}

const _DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
function _date(n) { return n && typeof n.date === "string" && _DATE_RE.test(n.date) ? n.date : null; }

function _dday(dateIso) {
  if (!dateIso) return { cls: "d-none", text: "—", n: null };
  const t0 = new Date(_todayKST() + "T00:00:00+09:00").getTime();
  const t1 = new Date(dateIso + "T00:00:00+09:00").getTime();
  const n = Math.round((t1 - t0) / 86400000);
  if (n <= 0) return { cls: "d-today", text: "TODAY", n: 0 };
  if (n <= 7) return { cls: "d-soon", text: "D-" + n, n };
  return { cls: "d-far", text: "D-" + n, n };
}

const WD = ["일", "월", "화", "수", "목", "금", "토"];
const _md = (d) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;   // 10/24 (앞자리 0 없음)
const _wd = (d) => WD[new Date(d + "T00:00:00Z").getUTCDay()];
function _dateTxt(n) {   // 「〜10/24 (토)」 — 마감이면 〜, 날짜가 없으면 「날짜 미정」
  const d = _date(n);
  return d ? `${n.deadline ? "〜" : ""}${_md(d)} (${_wd(d)})` : "날짜 미정";
}

function _esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function _attr(s) { return _esc(s).replace(/'/g, "&#39;"); }
function _url(u) { return typeof u === "string" && /^https?:\/\//i.test(u) ? u : ""; }   // http(s) 주소만 링크로
function _tweetId(n) {   // tweet_url 의 status/숫자
  const m = /\/status(?:es)?\/(\d{5,25})/.exec(String((n && n.tweet_url) || ""));
  return m ? m[1] : null;
}

function _ic(name) {
  return `<svg class="ntc__ic${name === "x" ? " ntc__ic--fill" : ""}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICON[name] || ICON.etc}</svg>`;
}
function _catIc(cat, lg) {
  const nm = CAT_NAME[cat];
  return `<span class="ntc__cat${lg ? " ntc__cat--lg" : ""}" data-cat="${cat}" role="img" aria-label="${_attr(nm)}" title="${_attr(nm)}">${_ic(cat)}</span>`;
}
function _ddHTML(date) {
  const dd = _dday(date);
  return `<span class="ntc__dd ${dd.cls}">${dd.text}</span>`;
}

// 제목 = 고른 언어(한글 n.title_ko / 원문 n.title). 고른 언어가 비었으면 다른 쪽.
function _titleOf(n) {
  const ko = String(n.title_ko || "").trim(), ja = String(n.title || "").trim();
  if (_st.lang === "ja") return ja ? { t: ja, lang: "ja" } : ko ? { t: ko, lang: "ko" } : { t: "(제목 없음)", lang: "ko" };
  return ko ? { t: ko, lang: "ko" } : ja ? { t: ja, lang: "ja" } : { t: "(제목 없음)", lang: "ko" };
}
function _ttlSpan(n) {
  const tt = _titleOf(n);
  return `<span class="ntc__ttl" lang="${tt.lang}">${_esc(tt.t)}</span>`;
}
// 소식 줄 · 카드 공통 속성 — 링크가 아니라 팝업(시트)을 여는 버튼
function _hitAttrs(n) {
  return `data-nid="${_attr(n.id)}" role="button" tabindex="0" aria-haspopup="dialog" aria-label="${_attr(_titleOf(n).t)}"`;
}

function _visible(data) {
  const now = Date.now();
  const list = ((data && data.notices) || []).filter((n) => {
    if (!n) return false;
    if (!n.expires_at) return true;
    const e = Date.parse(n.expires_at);
    return isNaN(e) || e > now;
  });
  list.sort((a, b) =>
    (_date(a) || "9999-99-99").localeCompare(_date(b) || "9999-99-99") ||
    (a.time || "99:99").localeCompare(b.time || "99:99") ||
    String(a.id).localeCompare(String(b.id))
  );
  return list;
}
function _byId(id) { return id == null ? null : _st.list.find((n) => String(n.id) === String(id)) || null; }

function _counts(list) {
  const c = { all: list.length };
  CATS.forEach((k) => { c[k.id] = 0; });
  list.forEach((n) => { _cats(n).forEach((k) => { c[k]++; }); });   // 여러 분류인 소식은 각 분류에 하나씩
  return c;
}
function _filtered() {
  return _st.tab === "all" ? _st.list : _st.list.filter((n) => _cats(n).includes(_st.tab));
}

// ── PC 티커 한 줄: [D-day] [분류 아이콘] [제목] [날짜 (요일) 시각]. 제목을 누르면 펼침 + 그 소식 팝업 고정 ──
function _tickRow(n, clone) {
  const cat = _cats(n)[0], d = _date(n);
  const when = d ? `${_dateTxt(n)}${n.time ? " " + n.time : ""}` : (n.time || "");
  const tt = _titleOf(n);
  const ttl = clone
    ? `<span class="ntc__ttl" lang="${tt.lang}">${_esc(tt.t)}</span>`
    : `<span class="ntc__ttl" lang="${tt.lang}" data-pin="${_attr(n.id)}" role="button" tabindex="0" aria-haspopup="dialog" title="${_attr(tt.t)}">${_esc(tt.t)}</span>`;
  return `<div class="ntc__trow" data-cat="${cat}"${clone ? ' aria-hidden="true"' : ""}>` +
    _ddHTML(d) + _catIc(cat) + ttl + `<span class="ntc__when">${_esc(when)}</span></div>`;
}

// ── 언어 전환 [한글 | 원문] ──
function _segHTML() {
  const b = (code, label) => `<button type="button" data-lang="${code}" aria-pressed="${_st.lang === code}">${label}</button>`;
  return `<div class="ntc__seg" role="group" aria-label="제목 언어">${b("ko", "한글")}${b("ja", "원문")}</div>`;
}

// 탭 목록 = 전체(항상) + 건수가 있는 분류만
function _tabCats(c) { return [{ id: "all", name: "전체" }].concat(CATS.filter((k) => c[k.id] > 0)); }

// ── PC 분류 칩: [전체 n] [아이콘 이름 n] … (0건 분류는 숨김) ──
function _chipsHTML(c) {
  return `<div class="ntc__chips" role="tablist" aria-label="분류">` + _tabCats(c).map((k) =>
    `<button class="ntc__chip" role="tab" type="button" data-tab="${k.id}" data-cat="${k.id}" aria-selected="${_st.tab === k.id}"` +
      ` aria-label="${_attr(k.name)} ${c[k.id]}건" title="${_attr(k.name)}">` +
      (k.id === "all" ? "" : _ic(k.id)) + `<span>${_esc(k.name)}</span><span class="n">${c[k.id]}</span></button>`
  ).join("") + `</div>`;
}

// ── 모바일 밑줄 탭: 전체 / 분류 아이콘 + 건수 (0건 분류는 숨김) ──
function _utabsHTML(c) {
  return `<div class="ntc__utabs" role="tablist" aria-label="분류">` + _tabCats(c).map((k) =>
    `<button class="ntc__utab" role="tab" type="button" data-tab="${k.id}" data-cat="${k.id}" aria-selected="${_st.tab === k.id}"` +
      ` aria-label="${_attr(k.name)} ${c[k.id]}건" title="${_attr(k.name)}">` +
      (k.id === "all" ? `<span class="all">전체</span>` : _ic(k.id)) + `<span class="n">${c[k.id]}</span></button>`
  ).join("") + `</div>`;
}

// ── 모바일 접힌 막대: 분류별 건수 칩(0건 분류는 숨김) ──
function _cchipsHTML(c) {
  return CATS.filter((k) => c[k.id] > 0).map((k) =>
    `<button class="ntc__cchip" type="button" data-open-tab="${k.id}" data-cat="${k.id}"` +
      ` aria-label="${_attr(k.name)} ${c[k.id]}건 보기" title="${_attr(k.name)} ${c[k.id]}건 보기">${_ic(k.id)}<span>${c[k.id]}</span></button>`
  ).join("");
}

// ── PC 날짜별 묶음: 소식 줄 = 시각 · 분류 아이콘 · 제목(한 줄) / 분류 이름 · 이날까지 · 출처 ──
function _groupsHTML(list) {
  const groups = [];
  list.forEach((n) => {
    const d = _date(n);
    const g = groups[groups.length - 1];
    if (!g || g.date !== d) groups.push({ date: d, items: [n] });
    else g.items.push(n);
  });
  return groups.map((g) => {
    const head = g.date
      ? `<span class="d">${_md(g.date)}</span><span class="w">(${_wd(g.date)})</span>`
      : `<span class="d is-none">날짜 미정</span>`;
    const items = g.items.map((n) => {
      const cat = _cat(n);
      return `<div class="ntc__gi" data-cat="${cat}" ${_hitAttrs(n)}>` +
        `<span class="ntc__time${n.time ? "" : " is-none"}">${_esc(n.time || "—")}</span>` +
        _catIc(cat) +
        `<div class="ntc__gbody">${_ttlSpan(n)}` +
          `<div class="ntc__meta"><span class="ntc__cn">${_esc(_catNames(n))}</span>` + _lnameHTML(n) +
            (n.deadline ? `<span class="ntc__until">이날까지</span>` : "") +
            `<span class="ntc__src">${_ic("x")}<span class="nm">${_esc(n.src_handle || "@BDP_yumemita")}</span></span>` +
          `</div></div></div>`;
    }).join("");
    return `<div class="ntc__grp"><div class="ntc__gdate">${head}${g.date ? _ddHTML(g.date) : ""}</div>` +
      `<div class="ntc__gitems">${items}</div></div>`;
  }).join("");
}

// ── 모바일 카드: [분류 아이콘 36px] [제목 한 줄 / D-day · 분류 이름 · 날짜(요일) · 시각] ──
function _cardsHTML(list) {
  return `<div class="ntc__cards">` + list.map((n) => {
    const cat = _cat(n);
    return `<div class="ntc__card" data-cat="${cat}" ${_hitAttrs(n)}>${_catIc(cat, true)}` +
      `<div class="ntc__cbody">${_ttlSpan(n)}` +
        `<div class="ntc__meta">${_ddHTML(_date(n))}<span class="ntc__cn">${_esc(_catNames(n))}</span>` +
          `<span>${_esc(_dateTxt(n))}</span><span>${_esc(n.time || "—")}</span></div>` +
      `</div></div>`;
  }).join("") + `</div>`;
}

// ───────────── (v4.7.0) 라이브공연 탭 — 공연별 묶음 ─────────────
// 백엔드가 라이브공연 소식에 붙인 공연 이름(live_name, 원문 표기) · 공연일(live_date)로 같은 공연 소식을 모은다.
// 묶음 머리 = [공연일 타일] [공연 이름 / 소식 n건] [공연일 기준 D-day] [›] — 하위 소식 줄은 들여 쓴 어두운 칸에 작은 글자로(머리와 구분).
// 순서 = 다가오는 공연(공연일 순) → 공연일 미정 → 지난 공연(최근 순, 접힘) → 「그 밖의 공연 소식」(공연 이름 없음).
// [공연별 | 날짜순] 선택은 localStorage 에 남긴다. 날짜순 = 다른 탭과 같은 목록(줄마다 공연 이름 꼬리표).
function _loadLiveView() {
  try { return localStorage.getItem(LIVE_VIEW_KEY) === "date" ? "date" : "group"; } catch (e) { return "group"; }
}
function _saveLiveView(v) {
  try { localStorage.setItem(LIVE_VIEW_KEY, v); } catch (e) { /* 저장 못 해도 지금 화면은 바꾼다 */ }
}
function _liveKey(name) {   // 같은 공연 판정 — 전각/반각 · 대소문자 · 공백 · 괄호 · 구두점 차이는 무시
  return String(name || "").normalize("NFKC").toLowerCase().replace(/[\s「」『』“”"'’・·:：!！?？\-–—_.,、。☆★]/g, "");
}
function _lnameHTML(n) {   // 소식 줄의 공연 이름 꼬리표(라이브공연이고 이름이 있을 때)
  return n.live_name && _cats(n).includes("live") ? `<span class="ntc__lname" lang="ja">${_esc(n.live_name)}</span>` : "";
}
function _liveSegHTML() {
  const b = (v, label) => `<button type="button" data-lview="${v}" aria-pressed="${_st.liveView === v}">${label}</button>`;
  return `<div class="ntc__seg ntc__seg--lv" role="group" aria-label="라이브공연 보기 방식">${b("group", "공연별")}${b("date", "날짜순")}</div>`;
}
function _mostCommon(vals) {   // 가장 많이 나온 값(같으면 앞선 값 — 날짜는 이른 날)
  const cnt = new Map();
  vals.filter(Boolean).sort().forEach((v) => cnt.set(v, (cnt.get(v) || 0) + 1));
  let best = null, bn = 0;
  cnt.forEach((c, v) => { if (c > bn) { best = v; bn = c; } });
  return best;
}
function _liveGroups(list) {
  const today = _todayKST(), by = new Map();
  list.forEach((n) => {
    const k = _liveKey(n.live_name);
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(n);
  });
  const t0 = new Date(today + "T00:00:00+09:00").getTime();
  const groups = [...by.entries()].map(([key, items]) => {
    const name = key ? _mostCommon(items.map((n) => n.live_name)) : null;
    const date = key ? _mostCommon(items.map((n) => (_DATE_RE.test(n.live_date || "") ? n.live_date : null))) : null;
    const d = date ? Math.round((new Date(date + "T00:00:00+09:00").getTime() - t0) / 86400000) : null;
    const past = d != null && d < 0;
    const rank = !key ? 3 : past ? 2 : date ? 0 : 1;
    const last = items.map(_date).filter(Boolean).sort().pop() || null;
    return { key, name, date, d, past, rank, items, last };
  });
  groups.sort((a, b) => a.rank - b.rank ||
    (a.rank === 0 ? a.date.localeCompare(b.date) : a.rank === 2 ? b.date.localeCompare(a.date) : String(a.name).localeCompare(String(b.name))));
  return groups;
}
function _liveGroupsHTML(list, mode) {
  return `<div class="ntc__lgs">` + _liveGroups(list).map((g) => {
    const gid = g.key || "~other";
    const open = gid in _st.liveOpen ? _st.liveOpen[gid] : !g.past;
    const tile = !g.key
      ? `<span class="ntc__lgtile is-icon">${_ic("live")}</span>`
      : g.date
        ? `<span class="ntc__lgtile"><span class="m">${Number(g.date.slice(5, 7))}월</span><span class="d">${Number(g.date.slice(8, 10))}</span><span class="w">${_wd(g.date)}</span></span>`
        : `<span class="ntc__lgtile is-tbd"><span class="m">공연일</span><span class="d">미정</span></span>`;
    const dd = !g.key ? "" : g.d == null ? "공연일 미정" : g.d < 0 ? `종료 · D+${-g.d}` : g.d === 0 ? "TODAY" : `D-${g.d}`;
    const sub = `소식 ${g.items.length}건` + (g.past && g.last ? ` · 마지막 ${_md(g.last)}` : "");
    const rows = g.items.map((n) => {
      const chips = _cats(n).filter((k) => k !== "live")
        .map((k) => `<span class="ntc__lchip" data-cat="${k}">${_esc(CAT_NAME[k])}</span>`).join("");
      return mode === "pc"
        ? `<div class="ntc__gi ntc__lrow" data-cat="live" ${_hitAttrs(n)}><span class="ntc__ldot" aria-hidden="true"></span>` +
            `<span class="ntc__ldate">${_esc(_dateTxt(n))}</span><span class="ntc__ltime">${_esc(n.time || "—")}</span>` +
            _ttlSpan(n) + `<span class="ntc__lchips">${chips}</span></div>`
        : `<div class="ntc__card ntc__lrow" data-cat="live" ${_hitAttrs(n)}><span class="ntc__ldot" aria-hidden="true"></span>` +
            `<div class="ntc__cbody">${_ttlSpan(n)}<div class="ntc__meta"><span>${_esc(_dateTxt(n))}</span>` +
            `<span>${_esc(n.time || "—")}</span>${chips}</div></div></div>`;
    }).join("");
    const cls = "ntc__lg" + (g.past ? " is-past" : "") + (!g.key ? " is-other" : "") + (g.key && !g.date ? " is-tbd" : "");
    return `<section class="${cls}" data-cat="live">` +
      `<button class="ntc__lghd" type="button" data-lgrp="${_attr(gid)}" aria-expanded="${open}">` + tile +
        `<span class="ntc__lgtx"><span class="ntc__lgname"${g.key ? ' lang="ja"' : ""}>${_esc(g.name || "그 밖의 공연 소식")}</span>` +
          `<span class="ntc__lgsub">${_esc(sub)}</span></span>` +
        (dd ? `<span class="ntc__lgdd">${_esc(dd)}</span>` : "") +
        `<span class="ntc__lgchev" aria-hidden="true">›</span></button>` +
      `<div class="ntc__lgrows"${open ? "" : " hidden"}>${rows}</div></section>`;
  }).join("") + `</div>`;
}

// ── 소식 팝업 카드 내용 (PC 팝업 · 모바일 시트 공용) ──
// 머리(분류 · D-day · 날짜 · 시각 · 출처 · ✕) / 전체 제목 / [번역 본문 | X 카드] / 링크. X 카드는 DOM 으로 따로 붙인다(tweets.js makeXCard).
function _cardFill(box, n, device) {
  const cat = _cat(n), tt = _titleOf(n), tw = _url(n.tweet_url), more = _url(n.url);
  const when = _dateTxt(n) + (n.time ? " " + n.time : "");
  let body;
  if (_st.lang === "ja") {
    // 원문 모드에서도 본문 원문은 우리가 그리지 않는다 — X 공식 카드가 보여 준다
    const note = !tw ? "원문 트윗 정보가 없어요" : device === "m" ? "원문은 아래 X 카드에서 볼 수 있어요" : "원문은 옆 X 카드에서 볼 수 있어요";
    body = `<p class="ntc-card__body is-note">${note}</p>`;
  } else {
    const ko = String(n.body_ko || "").replace(/\r/g, "").replace(/\n{3,}/g, "\n\n").trim();
    body = ko ? `<p class="ntc-card__body" lang="ko">${_esc(ko)}</p>` : `<p class="ntc-card__body is-note">번역 준비 중…</p>`;
  }
  const links = (more ? `<a href="${_attr(more)}" target="_blank" rel="noopener">자세히 보기 ↗</a>` : "") +
                (tw ? `<a href="${_attr(tw)}" target="_blank" rel="noopener">원문 트윗 ↗</a>` : "");
  box.innerHTML =
    `<div class="ntc-card__hd" data-cat="${cat}">${_catIc(cat)}<span class="ntc-card__cn">${_esc(_catNames(n))}</span>` +
      (_date(n) ? _ddHTML(_date(n)) : "") +
      `<span class="ntc-card__when">${_esc(when)}</span>` +
      `<span class="ntc-card__h">${_esc(n.src_handle || "@BDP_yumemita")}</span>` +
      `<span class="ntc-card__sp"></span>` +
      `<button class="ntc-card__x" type="button" data-close aria-label="닫기">✕</button></div>` +
    `<h3 class="ntc-card__tt" lang="${tt.lang}">${_esc(tt.t)}</h3>` +
    `<div class="ntc-card__cols${tw ? "" : " no-x"}">${body}</div>` +
    (links ? `<div class="ntc-card__links">${links}</div>` : "");
  if (tw) box.querySelector(".ntc-card__cols").appendChild(makeXCard(_tweetId(n), tw));
}
function _cardSig(n) { return [n.id, n.last_updated, n.title, n.title_ko, n.body_ko, _cats(n).join(","), n.live_name, n.live_date, n.date, n.time, n.tweet_url, n.url, _st.lang].join("\u0001"); }

// ───────────── PC 팝업 (#notice 안 · 목록 밖, z-index 43) ─────────────
function _popRow() {
  if (!_st.listEl || _pop.id == null) return null;
  for (const r of _st.listEl.querySelectorAll(".ntc__gi")) if (r.dataset.nid === String(_pop.id)) return r;
  return null;
}
function _popEnsure(section) {
  if (!_pop.el) {
    const el = document.createElement("div");
    el.className = "ntc__pop";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", "소식 자세히");
    el.innerHTML = `<div class="ntc__pop-in"></div>`;
    _pop.el = el;
  }
  if (_pop.el.parentElement !== section) section.appendChild(_pop.el);   // 막대를 다시 그리면(innerHTML) 빠지므로 다시 붙인다
  return _pop.el;
}
function _popOpen(id, mode, focusIn) {
  const n = _byId(id), section = _st.section;
  if (!n || !section || _st.mode !== "pc" || !_st.listEl) { _popClose(); return; }
  clearTimeout(_pop.closeTimer);
  const el = _popEnsure(section), inner = el.firstElementChild;
  const fresh = String(_pop.id) !== String(id) || !el.classList.contains("is-open");
  if (fresh || _pop.sig !== _cardSig(n)) {
    stopXCards(el);
    _cardFill(inner, n, "pc");
    _pop.sig = _cardSig(n);
    inner.scrollTop = 0;
  }
  _pop.id = String(id);
  _pop.mode = mode;
  el.classList.toggle("is-pinned", mode === "pin");
  _st.listEl.querySelectorAll(".ntc__gi.is-on").forEach((r) => r.classList.remove("is-on"));
  const row = _popRow();
  if (row) row.classList.add("is-on");
  _popPlace();
  el.classList.add("is-open");
  clearTimeout(_pop.cardTimer);
  if (mode === "pin") loadXCards(el);
  else _pop.cardTimer = setTimeout(() => { if (_pop.mode && _pop.id === String(id)) loadXCards(el); }, PEEK_CARD_MS);
  if (focusIn) { const x = el.querySelector(".ntc-card__x"); if (x) x.focus({ preventScroll: true }); }
}
function _popClose(focusRow) {
  clearTimeout(_pop.cardTimer); clearTimeout(_pop.closeTimer);
  const row = _popRow();
  if (row) row.classList.remove("is-on");
  if (_pop.el) {
    _pop.el.classList.remove("is-open", "is-pinned");
    stopXCards(_pop.el);
  }
  if (focusRow && row) row.focus({ preventScroll: true });
  _pop.id = null; _pop.mode = null; _pop.sig = "";
}
// 줄 아래에 띄우되 화면 아래 공간이 모자라면 위로. 높이는 화면 안 남은 공간까지(안에서 스크롤). 좌우도 화면 밖으로 안 나가게.
function _popPlace() {
  const el = _pop.el, row = _popRow(), section = _st.section;
  if (!el || !section) return;
  if (!row) { _popClose(); return; }
  const sr = section.getBoundingClientRect(), rr = row.getBoundingClientRect();
  const tr = (row.querySelector(".ntc__ttl") || row).getBoundingClientRect();
  const vh = window.innerHeight, vw = document.documentElement.clientWidth;
  const below = vh - rr.bottom - POP_GAP - 8, above = rr.top - POP_GAP - 8;
  const up = below < Math.min(POP_MAX_H, 380) && above > below;
  el.style.setProperty("--pop-max", Math.max(160, Math.min(POP_MAX_H, up ? above : below)) + "px");
  el.classList.toggle("up", up);
  if (up) { el.style.top = "auto"; el.style.bottom = (sr.bottom - (rr.top - POP_GAP)) + "px"; }   // 위로 열면 아래 끝을 고정 — X 카드가 늦게 커져도 줄을 안 덮는다
  else { el.style.bottom = "auto"; el.style.top = (rr.bottom + POP_GAP - sr.top) + "px"; }
  const w = el.offsetWidth;
  const minL = Math.max(8, 8 - sr.left), maxL = Math.min(section.clientWidth, vw - sr.left) - w - 8;
  const left = Math.max(minL, Math.min(maxL, tr.left - sr.left - 18));
  el.style.left = left + "px";
  el.style.setProperty("--tail-x", Math.max(14, Math.min(w - 28, tr.left - sr.left - left + 10)) + "px");
}
// 목록을 다시 그린 뒤(폴링 · 탭 · 언어): 고정 팝업은 같은 소식이 남아 있으면 새 줄에 다시 붙이고, 없으면 닫는다. 호버 팝업은 닫는다.
function _popAfterRepaint() {
  if (!_pop.mode) return;
  if (_pop.mode === "peek" || _st.mode !== "pc" || !_st.open) { _popClose(); return; }
  if (!_byId(_pop.id) || !_popRow()) { _popClose(); return; }
  _popOpen(_pop.id, "pin");
}

// ───────────── 모바일 시트 (body 에 붙임, 배경 900 · 시트 901 = 트윗 시트와 같은 층) ─────────────
function _sheetEnsure() {
  if (_sheet.el) return;
  _sheet.scrim = document.createElement("div");
  _sheet.scrim.className = "ntc-scrim";
  _sheet.scrim.addEventListener("click", () => _sheetClose(true));
  _sheet.el = document.createElement("div");
  _sheet.el.className = "ntc-sheet";
  _sheet.el.setAttribute("role", "dialog");
  _sheet.el.setAttribute("aria-modal", "true");
  _sheet.el.setAttribute("aria-label", "소식 자세히");
  _sheet.el.innerHTML = `<div class="ntc-sheet__grab" aria-hidden="true"></div><div class="ntc-sheet__in"></div>`;
  _sheet.el.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) _sheetClose(true); });
  document.body.append(_sheet.scrim, _sheet.el);
}
function _sheetOpen(id) {
  const n = _byId(id);
  if (!n) return;
  _sheetEnsure();
  const inner = _sheet.el.querySelector(".ntc-sheet__in");
  const open = document.body.classList.contains("ntc-sheet-open");
  if (String(_sheet.id) !== String(id) || _sheet.sig !== _cardSig(n) || !open) {
    stopXCards(_sheet.el);
    _cardFill(inner, n, "m");
    _sheet.sig = _cardSig(n);
    _sheet.el.scrollTop = 0;
  }
  _sheet.id = String(id);
  document.body.classList.add("ntc-sheet-open");
  loadXCards(_sheet.el);
  if (!open) { const x = _sheet.el.querySelector(".ntc-card__x"); if (x) x.focus({ preventScroll: true }); }
}
function _sheetClose(restoreFocus) {
  if (!_sheet.el || _sheet.id == null) return;
  document.body.classList.remove("ntc-sheet-open");
  stopXCards(_sheet.el);
  const id = _sheet.id;
  _sheet.id = null; _sheet.sig = "";
  if (restoreFocus && _st.listEl) {
    for (const c of _st.listEl.querySelectorAll(".ntc__card")) if (c.dataset.nid === id) { c.focus({ preventScroll: true }); break; }
  }
}
// 목록을 다시 그린 뒤: 시트의 소식이 없어졌으면 닫고, 내용이 바뀌었으면 새로 채운다
function _sheetAfterRepaint() {
  if (_sheet.id == null) return;
  const n = _byId(_sheet.id);
  if (!n || _st.mode !== "m") { _sheetClose(false); return; }
  if (_sheet.sig !== _cardSig(n)) _sheetOpen(_sheet.id);
}

// (v4a) 행사 배너 데이터 반영 — 바뀌었을 때만 소식 영역을 다시 그린다. 소식이 0건이면 배너도 안 보인다(알려진 한계).
export function setBanners(section, data) {
  _st.rawBanners = data || null;
  const now = Date.now();
  const list = visibleBanners(_st.rawBanners, now);
  const sig = bannerSig(list, now);
  if (sig === _st.bnSig) return;
  _st.bn = list;
  _st.bnSig = sig;
  if (section && _st.lastData !== undefined) renderNotices(section, _st.lastData);
}
export function refreshBanners(section) { setBanners(section, _st.rawBanners); }

export function renderNotices(section, data) {
  if (!section) return;
  _st.section = section;
  _st.lastData = data;
  const list = _visible(data);
  _wireGlobal(section);

  if (!list.length) {
    // 숨기지 않는다 — 빈 막대만 두고 펼치기는 비활성. (요청: 소식 0건이어도 자리 유지)
    if (_st.timer) { clearInterval(_st.timer); _st.timer = null; }
    _popClose(); _sheetClose(false);
    _st.built = false; _st.sig = ""; _st.open = false; _st.idx = 0; _st.list = []; _st.listEl = null;
    if (section.dataset.empty !== "1") {
      stopBannerMotion();
      section.hidden = false;
      section.className = "ntc is-empty is-collapsed";
      section.innerHTML =
        `<div class="ntc__bar">` +
          `<span class="ntc__tag"><span class="ntc__lamp" aria-hidden="true"></span>` +
            `<span class="ntc__label">소식</span></span>` +
          `<div class="ntc__ticker"><span class="ntc__empty">새 소식이 없습니다</span></div>` +
          `<button class="ntc__tgl" type="button" disabled aria-disabled="true" aria-label="소식 없음">▾</button>` +
        `</div>`;
      section.querySelector(".ntc__bar").appendChild(themeButton());
      section.dataset.empty = "1";
    }
    return;
  }
  section.dataset.empty = "0";

  const mode = _isMobile() ? "m" : "pc";
  const today = _todayKST();
  const sig = list.map((n) => n.id + ":" + (n.last_updated || "") + ":" + _cats(n).join(",") + ":" + (n.live_name || "") + ":" + (n.live_date || "")).join("|") +
    "#" + _st.bnSig + "#" + mode + "#" + today;
  if (_st.built && sig === _st.sig) return;   // 변화 없음 → 계속 돌림
  _st.sig = sig;
  _st.mode = mode;
  _st.list = list;
  _build(section);
}

// 막대 + 펼친 목록 골격을 새로 만든다(데이터 · 배너 · 화면 모드 · 날짜가 바뀌었을 때)
function _build(section) {
  const list = _st.list, mode = _st.mode, c = _counts(list);
  if (_st.timer) { clearInterval(_st.timer); _st.timer = null; }
  if (_st.tab !== "all" && !c[_st.tab]) _st.tab = "all";   // 고른 분류가 0건이 되면(탭이 숨으므로) 전체로

  const ds = list.map((n) => _dday(_date(n)).n);
  const nToday = ds.filter((n) => n === 0).length;
  const nWeek = ds.filter((n) => n != null && n <= 7).length;

  const mid = mode === "pc"
    ? `<span class="ntc__sum">오늘 <b>${nToday}</b> · 7일 안 <b>${nWeek}</b></span>` +
      `<div class="ntc__ticker"><div class="ntc__track"></div></div>`
    : `<div class="ntc__chipbar">${_cchipsHTML(c)}</div>`;

  section.hidden = false;
  section.className = `ntc ntc--${mode}` + (nToday ? " has-today" : "") + (_st.open ? " is-open" : " is-collapsed");
  section.innerHTML =
    `<div class="ntc__bar">` +
      `<span class="ntc__tag"><span class="ntc__lamp" aria-hidden="true"></span>` +
        `<span class="ntc__label">소식</span>` +
        `<span class="ntc__all"${_st.open ? "" : " hidden"}>전체 ${list.length}건</span></span>` +
      mid +
      `<button class="ntc__tgl" type="button" aria-expanded="${_st.open}" aria-label="${_st.open ? "소식 접기" : "소식 전체 보기"}">` +
        `${_st.open ? "▴" : "▾"}</button>` +
    `</div>` +
    `<div class="ntc__list">` +
      (_st.bn.length ? `<div class="ntc__banners">${bannerHTML(_st.bn, Date.now())}</div>` : "") +
      `<div class="ntc__hd"></div><div class="ntc__body"></div>` +
    `</div>`;
  const barEl = section.querySelector(".ntc__bar");
  barEl.appendChild(themeButton());
  if (_pop.el) section.appendChild(_pop.el);   // 팝업은 목록 밖 · #notice 안(위치 기준)

  const listEl = section.querySelector(".ntc__list");
  _st.listEl = listEl;
  const tgl = section.querySelector(".ntc__tgl");
  if (_st.bn.length) mountBannerMotion(listEl); else stopBannerMotion();

  // ── PC 티커 (5초마다 한 줄, 마우스 · 포커스가 있으면 멈춤, 탭이 숨으면 멈춤) ──
  const track = section.querySelector(".ntc__track");
  const ticker = section.querySelector(".ntc__ticker");
  const N = list.length;
  _st.idx = Math.min(_st.idx, N - 1);
  let H = 35;
  const show = (i, animate) => {
    if (!track) return;
    track.style.transition = animate ? "" : "none";
    track.style.transform = `translateY(${-i * H}px)`;
  };
  const paintTicker = () => {
    if (!track) return;
    track.innerHTML = list.map((n) => _tickRow(n, false)).join("") + (N > 1 ? _tickRow(list[0], true) : "");
    H = track.firstElementChild ? track.firstElementChild.getBoundingClientRect().height || 35 : 35;
    show(_st.idx % N, false);
  };
  const advance = () => {
    _st.idx++;
    show(_st.idx, true);
    if (_st.idx === N) setTimeout(() => { _st.idx = 0; show(0, false); }, 520);
  };
  const play = () => {
    if (!track || _st.open || _st.paused || N < 2) return;
    if (_st.timer) clearInterval(_st.timer);
    track.classList.add("is-live");
    _st.timer = setInterval(advance, 5000);
  };
  const stop = () => {
    if (_st.timer) { clearInterval(_st.timer); _st.timer = null; }
    if (track) track.classList.remove("is-live");
  };
  _st.play = play; _st.stop = stop;   // 다시 만들 때 최신 클로저로 교체 (visibility 리스너가 참조)
  if (ticker) {
    ticker.addEventListener("mouseenter", () => { _st.paused = true; stop(); });
    ticker.addEventListener("mouseleave", () => { _st.paused = false; play(); });
    ticker.addEventListener("focusin", () => { _st.paused = true; stop(); });
    ticker.addEventListener("focusout", () => { _st.paused = false; play(); });
  } else {
    _st.paused = false;
  }

  // ── 펼친 목록 높이: 행사 배너 + 분류 줄 + 소식 영역(PC 420 · 모바일 460px 상한), 전체는 화면 높이 70% 상한 ──
  // 실측 px 을 max-height 로 넣어야 트랜지션이 딱 그 거리만큼 「스르륵」
  const applyListHeight = () => {
    if (_st.open) {
      const bnr = listEl.querySelector(".ntc__banners"), hd = listEl.querySelector(".ntc__hd");
      const fixed = (bnr ? bnr.getBoundingClientRect().height : 0) + (hd ? hd.getBoundingClientRect().height : 0);
      const cap = Math.round(fixed + LIST_CAP[_st.mode]);
      const capByViewport = Math.round(window.innerHeight * VIEWPORT_CAP);
      listEl.style.maxHeight = Math.min(listEl.scrollHeight, cap, capByViewport) + "px";
    } else {
      listEl.style.maxHeight = "0px";
    }
  };

  // ── 분류 줄 + 소식 목록 (탭 · 언어를 바꾸면 이것만 다시 그린다) ──
  const hdEl = listEl.querySelector(".ntc__hd"), bodyEl = listEl.querySelector(".ntc__body");
  const paintList = () => {
    const shown = _filtered();
    const liveTab = _st.tab === "live", lv = liveTab ? _liveSegHTML() : "";   // (v4.7.0) 라이브공연 탭 = [공연별 | 날짜순]
    if (mode === "pc") {
      hdEl.innerHTML = _chipsHTML(c) + lv + _segHTML();
    } else {
      const label = _st.tab === "all" ? "전체" : CAT_NAME[_st.tab];
      hdEl.innerHTML = `<div class="ntc__hd2"><span class="ntc__count">${_esc(label)} ${shown.length}건</span>${lv}${_segHTML()}</div>` + _utabsHTML(c);
    }
    hdEl.classList.toggle("has-lv", liveTab);
    bodyEl.innerHTML = !shown.length
      ? `<p class="ntc__none">이 분류의 소식이 없습니다.</p>`
      : liveTab && _st.liveView === "group" ? _liveGroupsHTML(shown, mode)
      : mode === "pc" ? _groupsHTML(shown) : _cardsHTML(shown);
    listEl.style.setProperty("--ntc-hd-h", hdEl.getBoundingClientRect().height + "px");   // PC 날짜 칸이 분류 줄 아래에 붙게
    if (_st.open) applyListHeight();
    _popAfterRepaint();
    _sheetAfterRepaint();
  };

  const setOpen = (open) => {
    _st.open = open;
    section.classList.toggle("is-open", open);
    section.classList.toggle("is-collapsed", !open);
    tgl.setAttribute("aria-expanded", String(open));
    tgl.setAttribute("aria-label", open ? "소식 접기" : "소식 전체 보기");
    tgl.textContent = open ? "▴" : "▾";
    const all = section.querySelector(".ntc__all");
    if (all) all.hidden = !open;
    applyListHeight();
    if (open) stop();
    else { _popClose(); show(_st.idx % N, false); play(); }
  };
  _st.setOpen = setOpen;

  // (PC 티커 제목) 목록을 펼친 뒤 그 소식 줄이 보이게 스크롤하고 팝업을 고정해 연다
  const openAndPin = (id, viaKey) => {
    const n = _byId(id);
    if (!n) return;
    if (_st.tab !== "all" && !_cats(n).includes(_st.tab)) { _st.tab = "all"; paintList(); }
    setOpen(true);
    const go = () => {
      const row = Array.from(listEl.querySelectorAll(".ntc__gi")).find((r) => r.dataset.nid === String(id));
      if (!row || !_st.open) return;
      const lr = listEl.getBoundingClientRect(), rr = row.getBoundingClientRect();
      listEl.scrollTop += rr.top - lr.top - hdEl.getBoundingClientRect().height - 8;
      _popOpen(id, "pin", viaKey);
      if (!viaKey) row.focus({ preventScroll: true });
    };
    setTimeout(go, _reduceMotion() ? 0 : 320);   // 펼침 트랜지션이 끝난 뒤 위치를 잰다
  };
  _st.openAndPin = openAndPin;

  tgl.addEventListener("click", () => setOpen(!_st.open));

  // 분류 탭 · 언어 전환 — 목록 안 이벤트 위임 (목록 요소는 다시 만들 때마다 새로 생기므로 리스너가 쌓이지 않는다)
  listEl.addEventListener("click", (e) => {
    const tab = e.target.closest("[data-tab]");
    if (tab) {
      if (_st.tab === tab.dataset.tab) return;
      _st.tab = tab.dataset.tab;
      paintList();
      const t = listEl.querySelector(`[data-tab="${_st.tab}"]`);
      if (t) t.focus({ preventScroll: true });
      return;
    }
    // (v4.7.0) 라이브공연 탭 — 보기 방식 · 공연 묶음 접기/펼치기
    const lview = e.target.closest("[data-lview]");
    if (lview) {
      const v = lview.dataset.lview === "date" ? "date" : "group";
      if (_st.liveView === v) return;
      _st.liveView = v;
      _saveLiveView(v);
      _popClose();
      paintList();
      const b = listEl.querySelector(`[data-lview="${v}"]`);
      if (b) b.focus({ preventScroll: true });
      return;
    }
    const lg = e.target.closest("[data-lgrp]");
    if (lg) {
      const open = lg.getAttribute("aria-expanded") !== "true";
      _st.liveOpen[lg.dataset.lgrp] = open;
      lg.setAttribute("aria-expanded", String(open));
      const rows = lg.parentElement.querySelector(".ntc__lgrows");
      if (rows) rows.hidden = !open;
      if (!open && _pop.mode && rows && _pop.id != null && rows.querySelector(`[data-nid="${CSS.escape(String(_pop.id))}"]`)) _popClose();
      if (_st.open) applyListHeight();
      return;
    }
    const lang = e.target.closest("[data-lang]");
    if (lang) {
      const v = lang.dataset.lang === "ja" ? "ja" : "ko";
      if (_st.lang === v) return;
      _st.lang = v;
      _saveLang(v);
      paintList();
      paintTicker();
      const b = listEl.querySelector(`[data-lang="${v}"]`);
      if (b) b.focus({ preventScroll: true });
    }
  });
  // (모바일) 접힌 막대의 분류 칩 → 그 분류 탭으로 펼침 / (PC) 티커 제목 → 펼침 + 팝업 고정
  barEl.addEventListener("click", (e) => {
    const pin = e.target.closest("[data-pin]");
    if (pin) { openAndPin(pin.dataset.pin, false); return; }
    const chip = e.target.closest("[data-open-tab]");
    if (!chip) return;
    _st.tab = chip.dataset.openTab;
    paintList();
    setOpen(true);
    // 행사 배너 아래 분류 줄이 목록 맨 위에 오게 — 고른 분류의 소식이 바로 보이도록
    const bnr = listEl.querySelector(".ntc__banners");
    listEl.scrollTop = bnr ? bnr.offsetHeight : 0;
  });

  // (v4.4) 행사 배너 탭을 바꾸면 카드 높이가 달라지므로 펼침 높이를 다시 잰다
  listEl.addEventListener("mew:banners-resize", () => { if (_st.open) applyListHeight(); });
  // 목록을 스크롤하면 팝업이 줄을 따라간다
  listEl.addEventListener("scroll", () => { if (_pop.mode) _popPlace(); }, { passive: true });
  listEl.addEventListener("transitionend", (e) => { if (e.target === listEl && _pop.mode) _popPlace(); });

  paintTicker();
  paintList();

  if (_st.open) {
    // 이미 펼친 채로 다시 만든 경우: 슬라이드 없이 바로 펼친 높이로
    listEl.style.transition = "none";
    applyListHeight();
    void listEl.offsetHeight;
    listEl.style.transition = "";
    _popAfterRepaint();
  } else {
    listEl.style.maxHeight = "0px";
  }
  play();
  _st.built = true;
}

// 문서 · #notice 리스너 — 한 번만 건다(#notice 노드는 다시 그려도 같다)
function _wireGlobal(section) {
  if (_st._wired) return;
  _st._wired = true;

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) _st.stop && _st.stop();
    else if (!_st.open && !_st.paused && _st.play) _st.play();
  });

  // PC ↔ 모바일 경계(767px)를 넘으면 막대 · 목록 구성이 달라지므로 다시 만든다(팝업 · 시트는 닫힘)
  if (window.matchMedia) {
    window.matchMedia(MOBILE_MQ).addEventListener("change", () => {
      _popClose(); _sheetClose(false);
      if (_st.lastData !== undefined) renderNotices(_st.section, _st.lastData);
    });
  }
  window.addEventListener("resize", () => { if (_pop.mode) _popPlace(); });

  // ── 소식 줄(PC) → 팝업 고정 / 카드(모바일) → 시트 ──
  const hit = (t) => (t instanceof Element ? t.closest(".ntc__gi, .ntc__card") : null);
  const activate = (el, viaKey) => {
    const id = el.dataset.nid;
    if (el.classList.contains("ntc__card")) { _sheetOpen(id); return; }
    if (_pop.mode === "pin" && _pop.id === String(id)) { _popClose(viaKey); return; }   // 고정된 줄을 다시 누르면 닫힘
    _popOpen(id, "pin", viaKey);
  };
  section.addEventListener("click", (e) => {
    if (_pop.el && _pop.el.contains(e.target)) {
      if (e.target.closest("[data-close]")) _popClose(true);
      return;
    }
    const el = hit(e.target);
    if (el && _st.listEl && _st.listEl.contains(el)) activate(el, false);
  });
  section.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const pin = e.target.closest("[data-pin]");
    if (pin) { e.preventDefault(); _st.openAndPin && _st.openAndPin(pin.dataset.pin, true); return; }
    const el = hit(e.target);
    if (el && el === e.target) { e.preventDefault(); activate(el, true); }
  });
  // PC 호버 — 고정 중에는 무시. 줄 → 팝업으로 옮겨 가도 유지(닫기를 잠깐 미뤄 틈을 지나는 동안 버틴다)
  section.addEventListener("pointerover", (e) => {
    if (_st.mode !== "pc" || e.pointerType === "touch") return;
    if (_pop.mode === "peek") {
      const h = hit(e.target);
      if (_pop.el.contains(e.target) || (h && h.dataset.nid === _pop.id)) { clearTimeout(_pop.closeTimer); return; }
    }
    const el = e.target.closest(".ntc__gi");
    if (!el || _pop.mode === "pin") return;
    _popOpen(el.dataset.nid, "peek");
  });
  section.addEventListener("pointerout", (e) => {
    if (_pop.mode !== "peek") return;
    const row = _popRow(), rt = e.relatedTarget;
    if (rt && ((row && row.contains(rt)) || _pop.el.contains(rt))) return;
    clearTimeout(_pop.closeTimer);
    _pop.closeTimer = setTimeout(() => { if (_pop.mode === "peek") _popClose(); }, PEEK_CLOSE_MS);
  });

  // Esc = 시트 / 팝업 닫기(목록은 그대로)
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (_sheet.id != null) { _sheetClose(true); return; }
    if (_pop.mode) _popClose(true);
  });
  // 고정 팝업 바깥 클릭 = 닫기 (소식 줄 · 팝업 · 티커 제목은 제외 — 그쪽은 위 click 이 처리. 테마 전환 버튼도 제외 — 바꾼 테마로 X 카드를 보게)
  document.addEventListener("click", (e) => {
    if (_pop.mode !== "pin") return;
    const t = e.target;
    if (!(t instanceof Element)) return;
    if ((_pop.el && _pop.el.contains(t)) || t.closest(".ntc__gi, [data-pin], .ntc__theme")) return;
    _popClose();
  });

  // 펼친 상태에서 영역 밖을 「탭」하면 목록 닫힘. 드래그(모바일 목록 스크롤 등)는 무시 —
  // pointerdown~up 이동량이 작을 때만 닫는다. 소식 시트 · 그 배경 안의 조작은 바깥으로 치지 않는다.
  let down = null;
  const outside = (t) => !section.contains(t) && !(t instanceof Element && t.closest(".ntc-sheet, .ntc-scrim"));
  document.addEventListener("pointerdown", (e) => {
    down = { x: e.clientX, y: e.clientY, outside: outside(e.target) };
  }, true);
  document.addEventListener("pointerup", (e) => {
    const d = down;
    down = null;
    if (!d || !_st.open || !d.outside) return;
    if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 10) return;   // 드래그
    if (!outside(e.target)) return;
    _st.setOpen && _st.setOpen(false);
  }, true);
}
