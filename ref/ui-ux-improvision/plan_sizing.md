# 기능 요소 크기 정리 구현 명세 (v4.11.7 에 포함 · 프론트만)

작업 폴더: `C:\Users\user\Documents\myprojects\mewtype-scheduler-worktrees\v4\patch-ui-ux-improvision` (브랜치 `patch/ui-ux-improvision`).

공통 규칙
- CSS 만 고친다. JS · `docs/` · `README.md` · `CLAUDE.md` · `scripts/` · `birthday*` · `bday*` · `king*` · `monitor*` · `src/backend/` 금지. 커밋 · 푸시 금지.
- 주석은 한국어, 변경 자리에 `(v4.11.7)`.
- 아래 값 외의 크기 · 색 · 구성은 바꾸지 않는다. 폰 = `@media (max-width: 767px)`, PC = 그 밖. 폰 전용 값은 그 파일의 기존 폰 미디어쿼리 안에 둔다.
- 높이는 `height` 대신 `min-height` 를 쓰고 세로 패딩을 0 으로 해 글자가 가운데 오게 한다(줄바꿈되는 요소가 잘리지 않게). 가운데 정렬이 안 되면 `display: inline-flex; align-items: center; justify-content: center`.
- 기존 규칙을 찾아 값을 고친다. 뒤에 덮어쓰는 규칙을 새로 쌓지 않는다.

## 1. 어둡게 패널 색 (`css/layout.css` `:root`)
`--color-bg: #0f0f0f` → `#101015`, `--color-bg-secondary: #1a1a1a` → `#1b1b22`, `--color-border: #333333` → `#34343f`, `--color-hover: #232323` → `#25252e`. `theme.css` 의 밝게 값은 그대로.

## 2. 상단 소식 막대
- `css/notices.css`: `--ntc-item-h: 2.2rem` → `36px`, 폰은 `44px`(같은 파일 폰 미디어쿼리에서 그 토큰이 정의된 선택자로 덮는다). 주석 갱신.
- `.ntc__cchip` `height: 26px` → `28px`. 좌우 패딩 · 글자 · 아이콘 그대로.
- `.ntc__bar` `border-radius: 6px` → `8px`.
- `css/layout.css` `--m-notice: calc(3.4rem - 3.6px)` → `calc(3.4rem + 5.2px)`. 주석의 「막대 2.2rem」을 「막대 44px」로.
- `css/theme.css` 폰 미디어쿼리: 테마 아이콘 `.ntc__theme svg` 18px(폰만). PC `.ntc__tgl` · `.ntc__theme` 폭은 `2.5rem`(40px)로.
- 막대 높이에 묶인 다른 값(펼침 목록 위치, sticky top 등)이 2.2rem 을 직접 쓰면 찾아서 맞춘다. 찾은 내용을 보고한다.

## 3. 플레이어 (`css/playerpop.css`)
- `.mp-search`: PC `min-height: 40px`, 폰 `44px`, `padding: 0 12px`. 폰의 `.mp-search input { padding: 6px 0; }` 는 `padding: 0`. 입력 글자 16px 유지.
- `.mp-chips button, .mp-sort button`: `min-height: 32px`(폰 36px), `padding: 0 10px`, `font-size: 13px`. 정렬 버튼(`.mp-sort__opt` · `.mp-sort__cycle`) 은 `padding: 0 8px`, `border-radius: 8px`.
- `.mp-pop .mp-tab`: `min-height: 40px`(폰 44px), 세로 패딩 0, 글자 14px.
- 폰 `.mp-lib .mp-tools`: `gap: 4px; padding: 6px 12px;` (도구 줄이 커진 만큼 곡 줄 자리를 지킨다).
- 곡 줄 `.mp-item__main` 은 건드리지 않는다.

## 4. 전환 버튼
- `css/notices.css` `.ntc__seg button`: `padding: 0 12px; min-height: 32px`(폰 36px).
- `css/tweets.css` `.tws__seg-b`: `min-height: 28px` → `32px`(폰 36px), 세로 패딩 0. 글자 · 좌우 패딩은 그대로(칩 줄 폭이 빠듯하다). `.tws__seg-pill` 위치 계산이 CSS 에 묶여 있으면 맞춘다.
- `css/timetable.css` `.vt__btn`: `padding: 0 13px; min-height: 32px; border-radius: 8px`. `.vt` `border-radius: 9px` → `11px`.

## 5. 폰 YouTube · X
`.lane__nav-btn` 의 폰 크기 26px → `32px`, `border-radius: 8px`, 아이콘 `18px`, `.lane__nav` 폰 `gap: 4px`.
`css/layout.css` 터치 영역: `.lane__nav-yt::after, .lane__nav-x::after` 를 `top: -2px; bottom: -2px; left: -6px; right: -6px;`(44×36). 주석 갱신.

## 6. 이후 예고 펼치기 (`css/timetable.css`)
`.tt-fold`: `padding: 0 14px; min-height: 40px`(폰 44px), `border-radius: 8px`, `gap: 8px`, `font-size: 14px`. 펼친 상태에서 `.tt-later` 와 이어지는 모서리 반경이 10px 로 적힌 곳도 8px 로 맞춘다.

## 7. 행사 배너 탭 (`css/banners.css`)
`.bnr__tab`: `min-height: 56px; padding: 8px 12px; border-radius: 12px; align-content: center`. 폰의 `min-height: 44px` 는 삭제. `.bnr__tabtop`: `font-size: 12px; line-height: 16px`. `.bnr__tabname`: `font-size: 14px; line-height: 20px`. `.bnr__arrow`: `border-radius: 12px`.

## 8. 소식 칩 터치 영역 (`css/layout.css`)
막대가 44px 가 되어 잘리지 않는다. 주석의 「세로 34」를 「세로 44」로만 고친다.

## 완료 보고
파일별 변경, 2번에서 찾은 값, 명세와 달라진 점, 막힌 점. `node src/frontend/js/*.selfcheck.mjs` 중 render · timetable · tweetlogic · longcopy 실행 결과.
