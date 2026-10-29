# 구현 지시서 — v4.9.6 (오늘 · 내일 예고 넘기기 · 알림 뱃지 · 라이브 아바타 · 탭 제목 · 예고 보관함 일자 분리)

- 기능 명세 = 같은 폴더 `SPEC_DRAFT.md`(3판 보완). 이 문서는 그 명세를 **작업 묶음별 코드 지시**로 옮긴 것이다. 둘이 어긋나면 이 문서를 따르고 Claude(검증 담당)에게 알린다.
- 번호 = **v4.9.6 하나**(운영자 확정 10-29 — 보관함 분리도 같은 번호. 사용자 입장에서 보관함 분리만 따로 번호를 받는 것은 납득할 만한 번호가 아님).
- 브랜치 `hotfix/day-nav-live`(일반 패치). 작업 묶음은 임시 로컬 브랜치 `tmp/dn-a` · `tmp/dn-b` 에서 하고 Claude 가 합친다(임시 브랜치는 푸시하지 않고 합친 뒤 지운다).
- 분담: 프론트 작업 묶음 A1 · A2(→ `tmp/dn-a`, A1 끝난 뒤 A2) · B(→ `tmp/dn-b`, A 와 동시) = Haiku 서브에이전트. 백엔드 C(예고 보관함 일자 분리) · 문서 · 버전 · 검증 = Claude.

## 공통 규칙 (모든 작업 묶음)

- 코드 주석은 **한국어**, 주변 코드의 주석 밀도 · 이름 · 문체(「— 」 대시, 짧은 이유 설명)를 따른다. 새 주석에는 `(v4.9.6)` 표시를 앞에 붙인다(기존 `(v4.5.8)` 같은 방식).
- 데이터는 `textContent` / `createElement` 로만 넣는다. **`innerHTML` 금지**(빈 문자열로 비우는 기존 코드는 그대로 둔다).
- 지정된 파일 밖은 고치지 않는다. **커밋하지 않는다**(Claude 가 검토 후 커밋). 파일을 만들거나 지우지 않는다(지시된 것 제외).
- 끝나면 `node src/frontend/js/timetable.selfcheck.mjs` · `node src/frontend/js/render.selfcheck.mjs` · `node src/frontend/js/king.selfcheck.mjs` 를 돌려(저장소 루트에서) 모두 통과하는지 확인하고, 바꾼 내용 · 판단한 것 · 확인 못 한 것을 짧게 보고한다.
- 「움직임 줄이기」 = `matchMedia("(prefers-reduced-motion: reduce)").matches`. 이 설정이면 애니메이션 · 트랜지션 없이 즉시 바꾼다.

---

## 작업 묶음 A1 — 하루 04:00 · 내일 구간 분류 · 카드 보기 · 문구 (worktree `../mewtype-scheduler-worktrees/v4/tmp-dn-a`)

파일: `src/frontend/js/timetable.js` · `src/frontend/js/timetable.selfcheck.mjs` · `src/frontend/js/main.js`(주석 1줄) · `src/frontend/js/render.js`(주석 1줄) · `src/frontend/css/timetable.css`(내일 구분선 스타일만).

### A1-1. `timetable.js` 상수 · 구간 함수
- 21행 `const DAY_START_HOUR = 6;  // monitor_log…` → `export const DAY_START_HOUR = 4;   // (v4.9.6) 예고보드의 하루 = 04:00 ~ 익일 04:00 (프론트 전용 — 모니터링 하루 경계 06:00 과 별개)`.
- `dayWindow(nowMs)` → `dayWindow(nowMs, offset = 0)`: 지금 계산 그대로 `ds` 를 구한 뒤 `ds += offset * DAY_MS`. 반환 `{ ds, de: ds + DAY_MS }`. 위 주석 「오늘 구간」 → 「오늘 구간(offset 0 = 오늘 예고, 1 = 내일 예고)」.
- 머리 주석(1~13행): 3행 「오늘 = KST 06:00 ~ 익일 06:00 (모니터링 하루 경계와 같음)」 → 「오늘 = KST 04:00 ~ 익일 04:00(오늘 예고), 그다음 하루 = 내일 예고. 그 밖의 예고는 "이후 예고"로 펼친다.」 · 6행 `dayWindow(nowMs, offset)` · 7행 반환에 `tomorrow` 추가.

### A1-2. `classify`
- 반환을 `{ ds, de, live, ended, upcoming, tomorrow, later }` 로.
- announced/upcoming/watching 분기:
  ```js
  const s = itemMs(item.scheduled_start);
  if (item.time_tbd || !isFinite(s) || s >= de + DAY_MS) later.push(item);
  else if (s >= de) tomorrow.push({ item, start: s, end: null });
  else upcoming.push({ item, start: s, end: null });
  ```
- `tomorrow.sort(byStart)` 추가. `live` · `ended` 규칙은 그대로.
- 76행 주석 「오늘 06:00 이후 시작해」 → 「오늘 04:00 이후 시작해」, 「later = 이후 예고(구간 밖·시각 미정)」 → 「tomorrow = 내일 예고(다음 04:00 하루)의 예정 { item, start }, later = 이후 예고(그다음 04:00 이후 · 시각 미정)」.

### A1-3. 머리줄 문구 (두 곳)
- `buildBoardHead` 377행 `06:00 ~ 익일 06:00` → `04:00 ~ 익일 04:00`. (그 밖의 구조는 A2 가 바꾼다 — A1 은 글자만.)
- 435행 시간축 주석의 06:00 은 A2 가 고친다 — A1 은 손대지 않는다.

### A1-4. `buildTodayCards(ctx, key, opts)` — 카드 보기(모바일 · PC 카드 보기 공용)
- `mT = (ctx.tomorrow || []).filter(has)` 추가.
- 메타: `(opts.compact ? "" : `${mdw(ctx.ds)} 04:00 ~ 익일 04:00 · `) + `예정 ${mU.length}` + (방송 중) + (종료) + (mT.length ? ` · 내일 ${mT.length}` : "")`.
- 순서 = 종료 → 방송 중 → 오늘 예정 → **내일 구분선** → 내일 예정.
  - 오늘 것(`all`)도 내일 것(`mT`)도 0건 → 지금처럼 「오늘 남은 예고가 없습니다.」만.
  - 오늘 것이 0건이고 내일이 있으면 → `.tt-today__none`(「오늘 남은 예고가 없습니다.」) 다음에 스택.
  - 스택(`.tt-today__stack`) 안: 오늘 카드들 → (mT 가 있으면) 구분선 `div.tt-today__div` 글자 `내일 예고 · ${mdw(ctx.de)} 04:00 ~` → 내일 카드들(`todayCard(entry, "upcoming", ctx, big, key)`).
  - `bigIdx` = 오늘 것 중 종료가 아닌 첫 카드. 없으면 내일 첫 카드가 big.
- `timetable.css` 의 `.tt-today__stack` 규칙(487행) 바로 아래에 구분선 스타일:
  ```css
  /* (v4.9.6) 카드 보기의 내일 구분선 — 오늘 예정 다음, 내일 예고(다음 04:00 하루)의 예정 앞 */
  .tt-today__div {
    display: flex; align-items: center; gap: 8px;
    font-size: 0.72rem; font-weight: 600; color: var(--color-text-muted);
    white-space: nowrap;
  }
  .tt-today__div::after { content: ""; flex: 1; border-top: 1px dashed var(--color-border); }
  ```
  `.tt-today__none` 다음에 스택이 올 때 사이 간격: `.tt-today__none + .tt-today__stack { margin-top: 12px; }`.

### A1-5. 「이후 예고」 문구 (`buildFoldButton`)
- `오늘 이후 예고 ${total}건 펼치기` → `이후 예고 ${total}건 펼치기`, `오늘 이후 예고 접기` → `이후 예고 접기`.
- 666행 주석은 그대로.

### A1-6. 주석의 06:00
- `main.js` 358행 「오늘 구간(KST 06:00)이 바뀌었으면」 → 「오늘 구간(KST 04:00)이 바뀌었으면」.
- `render.js` 972행 「오늘 구간(06:00)이 바뀌었으면」 → 「오늘 구간(04:00)이 바뀌었으면」.
- `src/frontend/monitor.html` 의 06:00 은 모니터링 하루 경계라 **고치지 않는다**.

### A1-7. `timetable.selfcheck.mjs`
- 17~23행 06:00 단언을 04:00 로: `21:35 → 당일 04:00 ~ 익일 04:00`, `03:59 는 아직 전날 구간`, `04:00 정각부터 새 구간`.
- 추가 단언(시각은 KST, `kst()` 헬퍼 사용):
  1. `dayWindow(kst("2026-10-30T01:00:00"))` 의 ds = `2026-10-29T04:00`, `dayWindow(같은 시각, 1)` 의 ds = `2026-10-30T04:00`, de = `2026-10-31T04:00`.
  2. now = `2026-10-29T23:00` 에서 announced 3건(채널 다르게): `2026-10-30T03:59` → `upcoming`, `2026-10-30T04:00` → `tomorrow`, `2026-10-31T04:00` → `later`. 시각 미정(`time_tbd: true`) → `later`.
  3. `tomorrow` 는 시작순 정렬, 각 항목에 `start` 가 있고 `end === null`.
  4. 종료분 넘어가기: preview `end` 항목(actual_start `2026-10-29T23:00` KST, state_since `2026-10-30T01:00` KST)이 now = `2026-10-30T03:59` 에서는 `ended` 에 있고, now = `2026-10-30T04:00` 에서는 없다.
  5. 기존 「오늘 예정 = 아라레 23:30」 · 「이후 예고 2건」 단언: 기존 fixture 의 ritsu `2026-10-06T12:00:00Z`(= 10-06 21:00 KST)는 이제 **내일 예고**다(now 10-05 21:35 → 내일 = 10-06 04:00 ~ 10-07 04:00). 단언을 `r.tomorrow` 1건(ritsu) · `r.later` 1건(nonoka 시각 미정)으로 고친다.
- 기존 메시지 형식(`assert(cond, "설명")`)을 따른다.

---

## 작업 묶음 A2 — PC 표: 4시간 축 · 익일 새벽 칸 · 두 화면 레일 · 일 이동 버튼 · 넘기기 (같은 worktree `tmp-dn-a`, **A1 이 끝난 뒤**)

파일: `src/frontend/js/timetable.js` · `src/frontend/js/timetable.selfcheck.mjs` · `src/frontend/css/timetable.css` · `src/frontend/css/layout.css`(토큰 1줄) · `src/frontend/css/theme.css`(토큰 1줄). **`render.js` 는 고치지 않는다**(보고 있는 화면 상태는 `timetable.js` 안에 둔다 — 아래 A2-1).

### A2-1. 상태 (`timetable.js` 모듈 변수, `ttRO` · `ttNudged` 옆)
```js
// (v4.9.6) 표가 보여 주는 하루 — 0 = 오늘 예고, 1 = 내일 예고. 저장하지 않는다(새로고침 · 첫 입장은 언제나 오늘 예고).
// 75초 재렌더 · 보기 방식 전환 · 창 크기 변화에도 유지하고, 04:00(tickTimetable 이 true)에 0 으로 돌아간다.
let ttDay = 0, ttSliding = false, dayNudged = false, lastTomN = null;
```
- `tickTimetable` 끝: `const roll = typeof de === "number" && nowMs >= de; if (roll) ttDay = 0; return roll;`.
- `buildTimetable` 시작에서 `const nTom = ctx.tomorrow.length; if (!nTom) ttDay = 0;` (내일 예정이 0건이 되면 오늘로).

### A2-2. DOM 구조 (SPEC §9 에 올릴 구조 — 이 모양 그대로)
```
section.tt
  div.tt__head                          ← buildBoardHead(ctx, { day: ttDay, pager: true })
    h2.tt__title  「오늘 예고」|「내일 예고」
    span.tt__pg (aria-hidden) > i + i   ← 두 점 표시 (표 보기에만)
    span.tt__meta
    div.vt                              ← 보기 방식 탭(있으면)
  div.tt__body                          ← (새) flex 가로: 표 + 일 이동 버튼
    div.tt__sw                          ← 기존(넘침 흐림 · 화살표). flex: 1; min-width: 0
      div.tt__scroll
        div.tt__grid                    ← grid-template-columns: 124px 1fr (행 정의 없음)
          div.tt__side                  ← (새) 1열: 머리 칸 + 멤버 칸 5줄 — 넘기는 동안 움직이지 않음
            div.tt__corner              ← 시간축 높이만큼 빈 칸
            section.lane.tt__lane[data-channel] × 5   (기존 그대로: header.lane__header.tt__who > span.lane__avatar + span.tt__nm > b + small)
          div.tt__rail                  ← (새) 2열, overflow: hidden, position: relative
            div.tt__strip               ← (새) width: 200%; display: flex; transform: translateX(-50% × ttDay)
              div.tt__pane[data-day="0"]  ← width: 50%; position: relative
                div.tt__axis
                div.tt__track[data-channel] × 5
                div.tt__ov > .tt__past + .tt__now + .tt__nowtag     ← 오늘 화면에만 (.tt__mid 는 없앰)
              div.tt__pane[data-day="1"]
                div.tt__axis
                div.tt__track[data-channel] × 5
      button.tt__arr--l / --r          ← 기존
    button.tt__day                      ← (새) 일 이동 버튼
      span.tt__day-ic > svg(chevron)
      span.tt__day-n                    ← 내일 예정 건수 알약
  div.tt__legend                        ← 기존
```
- `grid.__tt = { ds: ctx.ds, de: ctx.de }` 는 그대로(지금 선 위치 = 오늘 화면 기준). `positionNow` 는 그대로 동작한다(`.tt__now` 가 grid 안 하나뿐).
- `grid.style.setProperty("--dawn-l", `${((24 - DAY_START_HOUR) / 24) * 100}%`)`.
- 줄 맞춤: `.tt__corner` 와 `.tt__axis` 는 같은 높이(36px + 아래 테두리 1px), 멤버 칸 · 칸은 둘 다 78px + 아래 점선 1px — 지금 값 그대로라 두 열의 줄이 맞는다. `.tt__corner { height: 36px; border-bottom: 1px solid transparent; }`.

### A2-3. 한 화면(pane) 그리기 — `buildPane(ctx, day)` 함수로 분리
- `day` 0: `pctx = ctx`, 항목 = `ended`(state "ended") + `live`("live") + `upcoming`("upcoming") — 지금 `all` 과 같다.
- `day` 1: `pctx = { ...ctx, ds: ctx.de, de: ctx.de + DAY_MS }`, 항목 = `ctx.tomorrow` 를 전부 state "upcoming".
- 시간축(지금 `for (h = 0; h <= 24; h += 3)` 를 바꿈) — 주석 「시간축: 04:00 부터 4시간마다. 자정은 강조 + 익일 날짜」:
  ```js
  const MID = 24 - DAY_START_HOUR;              // 자정 눈금 (= 20)
  for (let h = 0; h <= 24; h += 4) { …is-first(h===0) · is-last(h===24) · is-midnight(h===MID)…
    sub = h === 0 ? mdw(t) : h === MID ? `자정 · 익일 ${mdw(t)}` : h === 24 ? `익일 ${mdw(t)}` : "" }
  ```
  `t = pctx.ds + h * HOUR_MS`.
- 멤버별 칸: `mine = items.filter(...itemKeys...includes(key))`, 빈 칸 문구 = day 0 「오늘 예정 없음」 / day 1 「내일 예정 없음」. 블록 = `layoutRow(mine, pctx)` · `blockEl(g.entry, g.state, pctx, g, key)`.
- `.tt__ov` 는 day 0 에만 붙인다(`.tt__mid` 는 만들지 않는다).
- 멤버 칸(`.tt__nm small`)의 건수: day 0 개수 · day 1 개수를 둘 다 구해 `small.dataset.n0` · `small.dataset.n1` 에 두고 `textContent = `${ttDay ? n1 : n0}건``. → `buildTimetable` 에서 멤버 칸을 만들 때 두 화면의 항목 목록이 필요하니, 항목 목록을 먼저 만들고(`items0`, `items1`) 멤버 칸 · 두 pane 에 같이 쓴다.

### A2-4. 머리줄 `buildBoardHead(ctx, opts = {})`
- `opts.day`(0|1, 기본 0) · `opts.pager`(true 면 두 점 표시).
- 제목 = day 0 「오늘 예고」 · day 1 「내일 예고」.
- 메타 = `headMeta(ctx, day)` 함수로 빼서:
  - day 0: `${mdw(ctx.ds)} 04:00 ~ 익일 04:00 · 예정 ${ctx.upcoming.length}건` + 방송 중 · 종료(지금 그대로).
  - day 1: `${mdw(ctx.de)} 04:00 ~ 익일 04:00 · 예정 ${ctx.tomorrow.length}건`.
- 두 점: `span.tt__pg` 에 `i` 두 개, `aria-hidden="true"`, `style --pg` = day(0|1). 제목 다음 · 메타 앞.
- 카드 보기(render.js 가 `buildBoardHead(ctx)` 로 부름)는 인자 없이 부르므로 지금처럼 오늘 예고 · 점 없음.

### A2-5. 일 이동 버튼 `button.tt__day`
- `type="button"`. 안: `span.tt__day-ic` > SVG(viewBox `0 0 12 12`, path `M4 2l4 4-4 4` — `overflowArrow("r")` 와 같은 모양, 공용 헬퍼로 빼도 됨) · `span.tt__day-n`(글자 = 내일 건수).
- 상태 맞추기 `syncDayBtn(btn, nTom)`:
  - `btn.classList.toggle("is-back", ttDay === 1)` — 화살표 180° 회전(CSS).
  - `btn.disabled = ttDay === 0 && nTom === 0`.
  - `aria-label` = 비활성 「내일 예정 없음」 / day 0 「내일 예고 보기 (예정 N건)」 / day 1 「오늘 예고 보기」.
  - 알약: `n.textContent = String(nTom)`, `n.hidden = nTom === 0 || ttDay === 1`.
- 건수 튐: 렌더 때 `if (lastTomN !== null && nTom !== lastTomN && nTom > 0 && !calm)` → 알약에 `is-pop` 을 붙였다 `animationend` 에 뗀다. 그 뒤 `lastTomN = nTom`.
- 처음 한 번 까딱임: `if (!dayNudged && !calm && ttDay === 0 && ctx.upcoming.length === 0 && nTom > 0) { dayNudged = true; btn.classList.add("is-nudge"); nudgeBusy = true; }` — 이 렌더에서 까딱였으면 `wireOverflow` 의 넘침 화살표 까딱임은 건너뛴다(`ttNudged` 를 그대로 둬서 다음 렌더에 한다). `wireOverflow(scroll)` 의 조건에 `&& !nudgeBusy` 를 더하고, `nudgeBusy` 는 `buildTimetable` 시작에서 false 로 둔다. (`wireOverflow` 의 `upd` 는 rAF · ResizeObserver 로 나중에도 불리므로, 까딱임 판정을 한 렌더 동안의 플래그로 막는다.)
- 클릭 = `switchDay(ttDay ? 0 : 1)`.

### A2-6. 넘기기 `switchDay(to)` (버튼 · 끌기 공용, `buildTimetable` 안 클로저)
1. `if (to === ttDay) { 제자리로 되돌리기(끌기에서 온 경우); return; }`. `closeCardPop()`.
2. `const dir = to > ttDay ? 1 : -1; ttDay = to;`
3. 띠: 움직임 줄이기면 `strip.style.transition = "none"`, 아니면 `strip.style.transition = "transform 280ms cubic-bezier(0.2, 0.8, 0.2, 1)"`(남은 거리가 짧으면 그대로 280ms — 단순하게). `strip.style.transform = `translateX(${-50 * ttDay}%)``. `ttSliding = true`; `transitionend`(또는 300ms 시간 제한 중 먼저) 에 `ttSliding = false`.
4. 머리줄: 제목 · 메타 글자 바꾸기 — 움직임 줄이기면 바로 `textContent` 교체. 아니면 각 요소에 `el.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: `translateX(${-6 * dir}px)` }], { duration: 80, easing: "ease-in" })` → `onfinish` 에 글자 교체 후 `el.animate([{ opacity: 0, transform: `translateX(${6 * dir}px)` }, { opacity: 1, transform: "none" }], { duration: 80, easing: "ease-out" })`. (`.tt__title` · `.tt__meta` 는 `display: inline-block` 이어야 transform 이 먹는다 — CSS 에서.)
5. 두 점: `pg.style.setProperty("--pg", String(ttDay))`.
6. 멤버 칸 건수: 각 `.tt__nm small` 의 글자를 `dataset.n0|n1` 로. 움직임 줄이기가 아니면 `small.animate([{ opacity: 0.2 }, { opacity: 1 }], { duration: 160 })`.
7. `syncDayBtn(btn, nTom)`.

### A2-7. 마우스 끌기 (레일 `.tt__rail` 에 pointer 이벤트)
- 순수 함수 2개를 **export** 해서 selfcheck 에 넣는다:
  ```js
  /* (v4.9.6) 넘기기 판정 — dx = 끈 거리(px, 왼쪽 = 음수 = 내일 쪽), vx = 놓기 직전 속도(px/ms), w = 레일 폭, day = 지금 화면, canNext = 내일 예정이 1건 이상 */
  export function swipeDecision(dx, vx, w, day, canNext) {
    if (day === 0 && canNext && dx < 0 && (-dx >= w * 0.25 || vx <= -0.5)) return "next";
    if (day === 1 && dx > 0 && (dx >= w * 0.25 || vx >= 0.5)) return "prev";
    return "stay";
  }
  /* 끄는 동안 띠가 따라오는 거리 — 더 갈 화면이 없는 쪽은 고무줄(30%, 최대 48px), 갈 수 있는 쪽은 1:1(레일 폭까지) */
  export function dragFollow(dx, w, day, canNext) {
    const open = (day === 0 && dx < 0 && canNext) || (day === 1 && dx > 0);
    if (open) return Math.max(-w, Math.min(w, dx));
    return Math.sign(dx) * Math.min(48, Math.abs(dx) * 0.3);
  }
  ```
- 시작(`pointerdown`): `e.pointerType === "mouse" && e.button === 0` 이고, 표가 넘치지 않을 때(`!sw.classList.contains("is-over")`), 누른 곳이 블록 · 버튼이 아닐 때(`!e.target.closest(".tt-blk, button")`)만. `drag = { x: e.clientX, w: rail.clientWidth, pts: [{ x, t: e.timeStamp }], moved: false }`.
- 움직임(`pointermove`, window 에): `dx = e.clientX - drag.x`. `|dx| > 5` 가 처음 넘으면 `drag.moved = true`, `rail.classList.add("is-dragging")`, `closeCardPop()`, `ttSliding = true`, `strip.style.transition = "none"`. moved 면 `e.preventDefault()`, 띠 = `translateX(calc(${-50 * ttDay}% + ${dragFollow(dx, w, ttDay, nTom > 0)}px))`, 두 점 `--pg` = `ttDay - follow / w`(0~1 로 자름). `pts` 는 최근 5개만.
- 놓기(`pointerup` · `pointercancel`, window 에): moved 가 아니면 끝. 속도 `vx` = 렌더 캐러셀(`render.js` onUp)과 같은 방식(`pts` 처음 · 끝, 놓기 직전 80ms 안에 움직였을 때만, 아니면 0). `rail.classList.remove("is-dragging")`. 판정 결과:
  - `"next"` → `switchDay(1)`, `"prev"` → `switchDay(0)`.
  - `"stay"` → 제자리로: 움직임 줄이기면 즉시, 아니면 `transition: transform 200ms cubic-bezier(0.2, 0.8, 0.2, 1)` 로 `translateX(${-50 * ttDay}%)`, `--pg` = ttDay. 끝나면 `ttSliding = false`.
  - 그리고 이어지는 click 한 번을 막는다: `suppress = true; setTimeout(() => suppress = false, 0)` + 레일에 capture click 리스너(`if (suppress) { e.preventDefault(); e.stopPropagation(); }`).
- 움직임 줄이기: 끄는 동안 띠를 움직이지 않고(follow 반영 안 함), 놓을 때 판정만 해 즉시 바꾼다.
- 리스너 누수 방지: window 리스너는 렌더마다 새로 걸리므로, `ttRO` 처럼 모듈 변수 `ttDragOff`(이전 렌더의 해제 함수)를 두고 `buildTimetable` 에서 먼저 부른다.
- 블록 마우스 올림 팝업: `blockEl` 의 `mouseenter` 처리 첫 줄에 `if (ttSliding) return;`.

### A2-8. CSS (`timetable.css`)
- 토큰: `layout.css` `:root` 의 `--color-grid` 줄 아래 `--color-dawn: rgba(255, 255, 255, 0.045);    /* (v4.9.6) 타임테이블 익일 새벽 칸(실제 다음 날 00:00~04:00) */` · `--color-dawn-edge: rgba(255, 255, 255, 0.12);`. `theme.css` 의 `--color-grid` 줄 아래 `--color-dawn: rgba(107, 91, 196, 0.05);` · `--color-dawn-edge: rgba(107, 91, 196, 0.16);`. (최종 톤은 화면 보고 Claude 가 정한다.)
- `.tt__grid` 는 그대로(`grid-template-columns: 124px 1fr`). 추가:
  ```css
  .tt__side { grid-column: 1; }
  .tt__corner { height: 36px; border-bottom: 1px solid transparent; }
  .tt__rail { grid-column: 2; position: relative; overflow: hidden; }
  .tt__strip { display: flex; width: 200%; will-change: transform; }
  .tt__pane { position: relative; width: 50%; flex: none; }
  ```
- `.tt__axis` 의 `grid-column: 2;` 줄 삭제(이제 pane 안).
- `.tt__track` 배경: 세로 눈금 4시간(`calc(100% / 6)`) + 익일 새벽 칸:
  ```css
  background-image:
    repeating-linear-gradient(to right, var(--color-grid) 0 1px, transparent 1px calc(100% / 6)),
    linear-gradient(to right, transparent var(--dawn-l, 83.333%), var(--color-dawn-edge) var(--dawn-l, 83.333%) calc(var(--dawn-l, 83.333%) + 1px), var(--color-dawn) calc(var(--dawn-l, 83.333%) + 1px));
  ```
  주석 「(v4.9.6) 4시간 눈금 + 익일 새벽 칸(실제 다음 날 00:00~04:00 — 블록 아래 층이라 블록 색이 바래지 않는다)」. `layout.css` 25행 `--color-grid` 주석 「3시간 눈금」 → 「4시간 눈금」.
- `.tt__ov` 의 `inset: 0 0 0 124px;` → `inset: 0;`(pane 기준). 주석 「지금 선 · 지난 구간 음영 · 자정 점선」 → 「지금 선 · 지난 구간 음영 (오늘 화면에만)」.
- `.tt__mid` 규칙 삭제.
- 끌기 커서: `.tt__sw:not(.is-over) .tt__rail { cursor: grab; }` · `.tt__rail.is-dragging { cursor: grabbing; user-select: none; }` · `.tt__rail.is-dragging .tt-blk { pointer-events: none; }`.
- 머리줄: `.tt__title, .tt__meta { display: inline-block; }`.
- 두 점:
  ```css
  /* (v4.9.6) 두 점 표시 — 오늘 · 내일 중 어디인지. --pg = 0(오늘) ~ 1(내일), 끄는 동안 끈 거리만큼 옮겨 간다 */
  .tt__pg { align-self: center; display: inline-flex; gap: 4px; --pg: 0; }
  .tt__pg i { height: 6px; border-radius: 3px; background: var(--color-text-muted); transition: width 0.28s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.28s; }
  .tt__pg i:first-child { width: calc(6px + 10px * (1 - var(--pg))); opacity: calc(0.35 + 0.65 * (1 - var(--pg))); }
  .tt__pg i:last-child { width: calc(6px + 10px * var(--pg)); opacity: calc(0.35 + 0.65 * var(--pg)); }
  .tt__pg.is-live i { transition: none; }   /* 끄는 동안(JS 가 --pg 를 매 프레임 넣음)은 바로 따라오게 */
  ```
  JS: 끌기 시작 때 `pg.classList.add("is-live")`, 놓을 때 `remove`.
- 일 이동 버튼 · 몸통:
  ```css
  /* (v4.9.6) 표 + 일 이동 버튼(오른쪽 세로 띠) */
  .tt__body { display: flex; gap: 10px; align-items: stretch; }
  .tt__body > .tt__sw { flex: 1; min-width: 0; }
  .tt__day {
    flex: none; width: 36px; padding: 0;
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
    border-radius: 10px; border: 1px solid var(--color-border); background: var(--color-bg-secondary); color: var(--color-text);
    cursor: pointer; transition: background 0.15s, opacity 0.2s, transform 80ms;
  }
  .tt__day:hover:not(:disabled) { background: var(--color-hover); }
  .tt__day:active:not(:disabled) { transform: scale(0.94); }
  .tt__day:focus-visible { outline: 2px solid var(--color-text-muted); outline-offset: 1px; }
  .tt__day:disabled { opacity: 0.35; cursor: default; }
  .tt__day-ic { display: grid; place-items: center; transition: transform 280ms cubic-bezier(0.2, 0.8, 0.2, 1), translate 0.15s; }
  .tt__day-ic svg { width: 12px; height: 12px; fill: none; stroke: currentColor; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }
  .tt__day.is-back .tt__day-ic { transform: rotate(180deg); }
  .tt__day:hover:not(:disabled) .tt__day-ic { translate: 2px 0; }
  .tt__day.is-back:hover .tt__day-ic { translate: -2px 0; }
  .tt__day-n {
    min-width: 18px; padding: 1px 5px; border-radius: 9px; box-sizing: border-box; text-align: center;
    font-size: 0.66rem; font-weight: 700; font-variant-numeric: tabular-nums;
    background: var(--color-raised); box-shadow: inset 0 0 0 1px var(--color-raised-edge);
  }
  .tt__day-n.is-pop { animation: dot-pop 0.38s cubic-bezier(0.25, 1.55, 0.45, 1); }
  .tt__day.is-nudge { animation: tt-arr-nudge 0.7s ease-in-out 3; }
  @media (prefers-reduced-motion: reduce) {
    .tt__day, .tt__day-ic, .tt__pg i { transition: none; }
    .tt__day.is-nudge, .tt__day-n.is-pop { animation: none; }
  }
  ```
  `dot-pop` 키프레임은 이미 `timetable.css` 끝(모바일 블록 밖)에 있다 — 그대로 쓴다.

### A2-9. selfcheck 추가 (`timetable.selfcheck.mjs`)
- `swipeDecision`: w=800 기준 — (-200, 0, 800, 0, true) = next(25% 경계 포함) · (-199, 0, …) = stay · (-50, -0.6, …, 0, true) = next(빠른 튕김) · (-400, 0, 800, 0, **false**) = stay(내일 0건) · (+300, 0, 800, 0, true) = stay(오늘에서 오른쪽) · (+200, 0, 800, 1, true) = prev · (-300, 0, 800, 1, true) = stay(내일에서 왼쪽) · (+50, 0.6, 800, 1, true) = prev.
- `dragFollow`: (-100, 800, 0, true) = -100 · (-100, 800, 0, false) = -30 · (+500, 800, 0, true) = 48(최대) · (+100, 800, 1, true) = 100 · (-1000, 800, 0, true) = -800.

---

## 작업 묶음 B — 알림 뱃지 · 라이브 아바타 · 탭 제목 (worktree `../mewtype-scheduler-worktrees/v4/tmp-dn-b`, A 와 동시)

파일: `src/frontend/js/tweets.js` · `src/frontend/css/tweets.css` · `src/frontend/css/theme.css` · `src/frontend/js/render.js` · `src/frontend/css/timetable.css`(맨 끝에 덧붙이기만). **`timetable.js` 는 고치지 않는다.**

### B-1. 청록 링 삭제 + 뱃지 빨강
- `tweets.js` 297행 주석 「배지(.lane__tw) · 아바타 링(.has-tweet) 을 …」 → 「배지(.lane__tw) 를 …」. 308행 `avatar.classList.toggle("has-tweet", …)` 줄 삭제. (`avatar` 변수는 바로 위 `if (!avatar) continue;` 에서만 쓰이게 되는데, 그 검사는 그대로 둔다 — 아바타 없는 레인 건너뛰기.)
- `tweets.css` 123~126행(`/* 트윗이 있는 멤버의 아바타 = 얇은 링… */` 주석 + `.lane__avatar.has-tweet { … }`) 삭제.
- `tweets.css` 10~11행: `--tw-badge-bg: var(--color-live);   /* 안 읽은 트윗 배지 (v4.9.6 청록 → 빨강) */` · `--tw-badge-fg: #ffffff;`.
- `tweets.css` 112행 펄스 글로우 `drop-shadow(0 0 5px rgba(204, 251, 250, 0.8))` → `drop-shadow(0 0 5px color-mix(in srgb, var(--tw-badge-bg) 80%, transparent))`.
- `theme.css` 105행 근처 밝게 값의 `--tw-badge-bg: #12a4a9` → `var(--color-live)`, 같은 블록에 `--tw-badge-fg` 가 있으면 `#ffffff`.
- 다른 `has-tweet` 사용처가 없는지 `src/frontend` 전체를 다시 검색해 확인.

### B-2. 라이브 아바타 효과
- `render.js` `renderBoard` 에서 `for (const key of order) sampleLaneColor(…)` 줄 **바로 다음**, `wireFold(boardEl)` 앞에:
  ```js
  // (v4.9.6) 라이브 아바타 효과 — 지금 방송 중인 멤버(합동 참여자 포함)의 레인에 lane--live. 모바일 캐러셀 클론이 같이 복제하도록 initMobileCarousel 전에
  for (const e of cls.live) for (const k of itemKeys(e.item, order)) {
    boardEl.querySelectorAll(`.lane[data-channel="${CSS.escape(k)}"]`).forEach((l) => l.classList.add("lane--live"));
  }
  ```
  (`itemKeys` 는 이미 `timetable.js` 에서 import 되어 있는지 확인, 없으면 import 에 추가.)
- `render.js` `initMobileCarousel` 의 점 만드는 반복문(`btn.className = "dot";` 다음 근처): `if (lane.classList.contains("lane--live")) btn.classList.add("dot--live");`.
- `timetable.css` **맨 끝**에 덧붙임:
  ```css
  /* (v4.9.6) 라이브 아바타 효과 — 방송 중인 멤버의 프로필 이미지에 빨간 테두리 + 은은한 글로우(느린 호흡). render.js renderBoard 가 .lane--live 를 켠다 */
  .lane--live .lane__avatar {
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35), 0 0 0 3px var(--color-live), 0 0 10px 3px color-mix(in srgb, var(--color-live) 55%, transparent);
    animation: live-breathe 2.4s ease-in-out infinite;
  }
  @keyframes live-breathe {
    50% { box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35), 0 0 0 3px var(--color-live), 0 0 16px 5px color-mix(in srgb, var(--color-live) 35%, transparent); }
  }
  /* 모바일 하단 멤버 전환 점 — 방송 중인 멤버는 흐리지 않고 빨간 링 */
  #pager-dots .dot.dot--live {
    opacity: 1;
    box-shadow: 0 0 0 2px var(--color-live), 0 0 8px 1px color-mix(in srgb, var(--color-live) 55%, transparent);
  }
  @media (prefers-reduced-motion: reduce) {
    .lane--live .lane__avatar { animation: none; }
  }
  ```
  (맨 앞 `0 0 0 1px rgba(0, 0, 0, 0.35)` = `layout.css` `.lane__avatar` 의 원래 그림자 — 덮어쓰지 않게 이어 붙였다.)

### B-3. 탭 제목 라이브 표시
- `render.js` 에 함수 추가(`renderBoard` 위):
  ```js
  /* (v4.9.6) 탭 제목 라이브 표시 — 라이브가 1건 이상이면 「🔴 LIVE n · 원래 제목」. n = 방송 수(합동 1건 = 1). 같은 값이면 쓰지 않는다 */
  let baseTitle = null;
  function applyLiveTitle(n) {
    if (baseTitle === null) baseTitle = document.title;
    const t = n > 0 ? `🔴 LIVE ${n} · ${baseTitle}` : baseTitle;
    if (document.title !== t) document.title = t;
  }
  ```
- `renderBoard` 끝(`__focusTab` 처리 다음)에 `applyLiveTitle(cls.live.length);`.

### B-4. 확인
- `node src/frontend/js/render.selfcheck.mjs` 통과(이 파일이 `document` 없이 render.js 를 import 하면 `document.title` 이 모듈 로드 때 불리지 않는지 확인 — 함수 안에서만 읽으므로 괜찮아야 한다).
