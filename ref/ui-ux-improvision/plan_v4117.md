# v4.11.7 구현 명세 (일반 패치 · 프론트만)

작업 폴더: `C:\Users\user\Documents\myprojects\mewtype-scheduler-worktrees\v4\hotfix-ui-refine` (브랜치 `patch/ui-ux-improvision`). 메인 폴더는 건드리지 않는다.
기준 문서: 이 폴더의 `docs/SPEC.md`(이번 변경 반영됨), `PRODUCT.md` 는 메인 폴더에만 있다.

공통 규칙
- 빌드 없음 · ES 모듈 · 새 의존성 금지. 데이터 주입은 `textContent` / `createElement` (`innerHTML` 금지).
- 코드 주석은 한국어, 각 변경 주석에 `(v4.11.7)`.
- 건드리지 말 것: `birthday*` · `bday*` · `king*` · `monitor*` · `src/backend/` · `docs/` · `README.md` · `CLAUDE.md` · `config.js` 의 `APP_VERSION` · `APP_DATE`.
- 커밋 · 푸시 금지. 작업 트리에 변경만 남긴다.
- `prefers-reduced-motion` 을 지킨다. 밝게 · 어둡게 모두 CSS 토큰으로 처리한다.
- 명세에 없는 개선 · 리팩터링 금지. 막히면 임의로 넘겨짚지 말고 보고서에 적는다.

## 1. 네트워크 실패 처리

### 1-1. `js/api.js`
`fetchPreview` 실패 결과에 `status` 를 담는다. HTTP 오류 = `{ok:false, status:response.status, error}`. 응답은 받았는데 JSON 파싱 실패도 그 `status`. 연결 실패 · 시간 초과는 `status` 없음.

### 1-2. 새 파일 `js/netrecover.js` — 순수 상태 기계 (DOM · window 접근 금지)
```js
export const RETRY_DELAYS_MS = [3000, 8000];
export const ONLINE_DELAY_MS = 5000;
export function createNetRecovery({ retry, show, hide, setTimer, clearTimer, isVisible }) { return { onSuccess, onFailure, onOnline }; }
```
상태: `idle` · `retrying`(attempt) · `alert`. 타이머는 하나만 둔다.
- `onSuccess()`: 타이머 해제, `alert` 였으면 `hide()`, `idle` 로.
- `onFailure(kind)` (`kind` = `"network"` | `"server"`):
  - `isVisible()` 가 false 이고 `alert` 가 아니면: 타이머 해제 후 `idle`. 안내 안 띄움(복귀 때 재조회가 돈다).
  - `alert`: `show(kind)` 만 다시 부름(문구 갱신). 재시도 예약 없음.
  - 타이머가 이미 대기 중: 아무것도 안 함(정기 조회가 겹친 경우).
  - 그 밖: 다음 재시도가 남았으면 `RETRY_DELAYS_MS[attempt]` 뒤 타이머. 타이머가 울리면 `attempt+1` · `isVisible()` 이 false 면 `idle` 로 끝, 아니면 `retry()`. 재시도가 다 떨어졌으면 `alert` 로 가서 `show(kind)`.
- `onOnline()`: `idle` 이면 무시. 아니면 기존 타이머 해제 후 `ONLINE_DELAY_MS` 뒤 `retry()`. 이 재시도가 실패하면 상태는 그대로이며(`alert` 는 `show` 만) `retrying` 은 위 규칙을 따른다.

새 파일 `js/netrecover.selfcheck.mjs`: 가짜 타이머로 다음을 전부 검사하고 실패 시 `process.exit(1)`.
(1) 1회 실패 뒤 재시도 성공 → `show` 0회 (2) 3회 연속 실패 → `show` 1회, 2회째까지 안 뜸 (3) 간격 3000 · 8000 (4) `alert` 뒤 성공 → `hide` 1회 (5) 숨김 상태 실패 → `show` · 재시도 0회 (6) 대기 중 실패 겹침 → 타이머 1개 (7) `alert` 에서 `onOnline` → 5000 뒤 `retry` (8) `idle` 의 `onOnline` 무시 (9) `alert` 중 kind 변경 시 `show` 재호출.

### 1-3. `js/main.js`
- `createNetRecovery` 연결: `retry` = 기존 `refetchAll`(함수를 모듈 위쪽으로 올려 재사용), `isVisible` = `document.visibilityState === "visible"`, `setTimer`/`clearTimer` = `setTimeout`/`clearTimeout`.
- `poll()`: 성공 끝에 `recovery.onSuccess()`. 실패면 `lastSchedule` 없을 때만 기존 「불러오는 중 문제가 발생했어요」 처리, 공통으로 `recovery.onFailure(result.status ? "server" : "network")`.
- `renderFooter` 호출에서 `stale` 인자 삭제.
- `pollTweets` · `pollBanners`: `if (!r.ok) return;` 지난 데이터 유지.
- `pollNotices`: 한 번이라도 성공했으면(`noticesLoaded`) 실패를 무시한다. 아직 성공한 적이 없으면 지금처럼 `renderNotices(notice, null)`.
- `window.addEventListener("online", recovery.onOnline)`.
- 안내 DOM: `document.body` 끝에 `div#net-alert[role=status][aria-live=polite][hidden]` 을 한 번만 만든다. 안에 `span.net-alert__ic`(글자 `!`, `aria-hidden`) + `span.net-alert__tx`.
  - `network` 문구 = `네트워크가 불안정하여 최신정보를 업데이트하지 못했어요.`
  - `server` 문구 = `최신정보를 업데이트하지 못했어요.`

### 1-4. `js/notices.js`
`renderNotices(section, null)`(한 번도 못 불러옴)은 빈 막대 문구를 `소식을 불러오지 못했어요` 로, 데이터가 있고 0건이면 지금처럼 `새 소식이 없습니다`.
빈 막대는 `section.dataset.empty` 로 한 번만 그리므로 두 문구가 바뀌는 경우에도 글자가 갱신되게 한다.

### 1-5. 「업데이트 지연」 삭제
`index.html` 의 `#foot-status`, `render.js renderFooter` 의 `stale` · `statusSpan`, `layout.css` 의 `#foot-status` 규칙 삭제.

### 1-6. `css/layout.css` 안내 스타일
`#net-alert`: `position:fixed; left:50%; top:50%; transform:translate(-50%,-50%); z-index:960; pointer-events:none; max-width:min(320px, calc(100vw - 32px)); width:max-content; display:flex; align-items:flex-start; gap:10px; padding:12px 14px; border-radius:12px; border:1px solid var(--color-border); background:var(--color-bg-secondary); color:var(--color-text); font-size:0.875rem; line-height:1.45; word-break:keep-all; box-shadow:0 8px 24px rgba(0,0,0,.35);`
`[hidden]` 은 `display:none`. `.net-alert__ic`: 20px 동그라미, `background:var(--color-late)`, 글자색 `#1a1a1a`, 굵게, 가운데. 빨강 쓰지 말 것(LIVE 전용). 움직임은 넣지 않는다.

## 2. 이후 예고 점 색

`js/config.js` 에 추가(시안 값, 운영자 확인 전):
```js
export const MEMBER_DOT_COLORS = {
  arale:  { dark: "#E9A23B", darkEnded: "#8C5E17", light: "#BA7500", lightEnded: "#E3B883" },
  yuno:   { dark: "#C2345E", darkEnded: "#751634", light: "#B82554", lightEnded: "#E08999" },
  nonoka: { dark: "#E883B4", darkEnded: "#8C4A6A", light: "#C35F91", lightEnded: "#E6A8C4" },
  ritsu:  { dark: "#4FA3E0", darkEnded: "#275F87", light: "#358ECA", lightEnded: "#8FBDE3" },
  miyako: { dark: "#8A63D2", darkEnded: "#50367F", light: "#8057C8", lightEnded: "#B29EE2" },
};
```
`timetable.js fillDot`: 각 `.wk2__seg` 에 `--dot-d` · `--dot-de` · `--dot-l` · `--dot-le` 를 `style.setProperty` 로 넣는다(키가 표에 없으면 넣지 않음).
`css/timetable.css`:
```css
.wk2__seg { background: var(--dot-d, var(--lane-color, var(--color-text-muted))); }
html[data-theme="light"] .wk2__seg { background: var(--dot-l, var(--lane-color, var(--color-text-muted))); }
.wk2__dot.is-ended .wk2__seg { background: var(--dot-de, var(--lane-color, var(--color-text-muted))); }
html[data-theme="light"] .wk2__dot.is-ended .wk2__seg { background: var(--dot-le, var(--lane-color, var(--color-text-muted))); }
```
`.wk2__dot.is-ended { opacity: 0.5; }` 를 삭제하고 주석을 갱신한다. 합동 알약 · 라이브 링 · 자물쇠 · 시각 미정 표시는 유지. `--lane-color` 는 레인 헤더 · 멤버 점에서 그대로 쓴다. `weekpop.js` 의 `--lane-color` 복사는 그대로 둔다(대체값).

## 3. 보던 멤버 기억 (`js/render.js`)

키 `mew.lane.last`, 값 = 채널 키. `try/catch` 로 감싼다.
- `initMobileCarousel` 에서 `activeIdx = ((activeIdx % n) + n) % n;` 바로 앞: 페이지당 첫 호출에서만(`laneRestored` 플래그) 저장값을 읽어 `reals` 의 같은 `dataset.channel` 위치로 `activeIdx` 설정. 없거나 못 찾으면 그대로.
- 사용자가 멤버를 바꾸는 지점 `if (real !== activeIdx) { activeIdx = real; ...` 안에서 저장한다.

## 4. 폰 시트 닫기 중복 제거

손잡이가 없는 PC 는 그대로다.
- `js/weekpop.js`: 「닫기」 버튼(`x`)을 만들지 않는다. `ui.x` 삭제. 시트에 `tabindex="-1"`, 열릴 때 시트에 `focus({preventScroll:true})`. `.wk-sheet__x` CSS 삭제.
- `css/playerpop.css` 의 `@media (max-width: 767px)` 안에 `.mp-x { display: none; }`. 기존 `.mp-x { padding... }` 줄 대체. `player.js:1651` 은 버튼이 안 보이면 `el.pop` 에 포커스(`el.pop` 에 `tabindex="-1"`).
- `css/notices.css`: `.ntc-sheet .ntc-card__x { display: none; }`. `notices.js:560` 포커스는 `_sheet.el`(`tabindex="-1"`)로. PC 팝업 ✕ 유지.
- 포커스 때 윤곽선이 시트 전체에 보이면 `outline: none` 으로 막는다.

## 5. 터치 영역 (`@media (max-width: 767px)` 안에서만)

보이는 크기 · 배치는 바꾸지 않는다. 각 요소에 `position:relative`(이미 있으면 생략)와 투명 `::after { content:""; position:absolute; ... }` 로 넓힌다. `::after` 를 이미 쓰는 요소는 `::before`, 둘 다 쓰면 보고한다.
- `#pager-dots .dot`: 세로 44px · 가로 40px(간격 14px 의 절반씩), 이웃과 겹치지 않음.
- `#pager-dots .player-btn` · `.week-btn`: 세로 44px.
- `.lane__nav-yt` · `.lane__nav-x`: 가로 44px, 세로는 두 버튼이 겹치지 않는 최대.
- `.lane__tw`: 사방 8px(아바타와 겹쳐도 됨 — 둘 다 트윗 시트를 연다).
- `.ntc__cchip`: 세로 44px(가로 확장 없음).
- `.ntc__tgl` · 소식 막대 테마 버튼: 세로 44px.

## 6. 글자 크기 근접값 묶기

대상: `css/layout.css card.css timetable.css notices.css banners.css player.css playerpop.css longcopy.css` 의 `rem` 값만. `tweets.css` · 모든 `px` 값은 제외(X 카드 맞춤 · 소식 제목 15.5px 등 결정값).
- `0.74rem`, `0.76rem` → `0.75rem`
- `0.82rem`, `0.84rem`, `.84rem`, `0.86rem` → `0.85rem`
- `0.66rem` → `0.68rem`
- `.72rem` → `0.72rem`, `.8rem` → `0.8rem`

그리고 PC 제목 위계: `@media (min-width: 768px)` 에서 `.tt__title { font-size: 1rem; }` (폰 값은 그대로).

## 완료 보고에 쓸 것
파일별 변경 요약, 실행한 점검 명령 결과, 명세와 달라진 점, 막힌 점.

점검:
`node src/frontend/js/netrecover.selfcheck.mjs`
`node src/frontend/js/render.selfcheck.mjs`, `timetable.selfcheck.mjs`, `tweetlogic.selfcheck.mjs`, `longcopy.selfcheck.mjs`, `songs.selfcheck.mjs`, `time.selfcheck.mjs`, `king.selfcheck.mjs`
