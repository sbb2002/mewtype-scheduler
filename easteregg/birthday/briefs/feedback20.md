# Claude → Codex: 라운드 20 (유노 생일 장면 — 시제품을 사이트용 모듈로 이식)

운영자가 시제품 v16(`C:\Users\User\Documents\pyworks\mewtype-scheduler-worktrees\v4\easteregg-birthday-skin\easteregg\birthday\birthday_bg_v16.html`)을 승인했고, **유노 생일(11-04)에 실제 사이트의 배경으로 쓴다.** 지금 작업 폴더는 사이트 저장소의 새 워크트리(`feat/birthday-easteregg`, main 최신)다. **사이트 통합(생일 판정 · 유리 패널 · 「온전히 보기」 버튼 · 문서)은 내가 한다.** 너는 **유노 장면을 독립 모듈로 뽑아 주는 것**만 해라. 디자인 · 모션은 v16 에서 **바꾸지 마라**(승인됨).

## 만들 파일 (모두 `src/frontend/` 아래, 빌드 없음 · ES 모듈 · 외부 요청 0)
- `js/bdayscene-yuno.js` — 장면 모듈. 아래 API.
- `css/bdayscene-yuno.css` — 장면 전용 CSS. v16 의 `<style>` 에서 **유노 장면에 실제 쓰이는 규칙만** 골라 정리(죽은 규칙 · 다른 캐릭터 규칙 · 시제품 UI(masthead/tabs/toolbar) 규칙 제외). 모든 선택자는 `.bdayscene` 아래로 스코프해 사이트 기존 CSS 와 충돌하지 않게. `prefers-reduced-motion` 처리 포함.
- `assets/birthday/yuno/*.webp` — v16 이 쓰는 유노 부위 이미지(data URI 가 아니라 **실제 파일**). 파일명 소문자 · 짧게(예: `head_open.webp`, `head_closed.webp`, `ear_l.webp`, `ear_r.webp`, `body.webp`, `tail.webp`, `arm_l.webp`, `arm_r.webp`, `headset.webp`, …). 리그 좌표(`RASTER_RIGS`, 최신 `assets5/rigs_v*.json` 중 v16 이 실제 쓰는 값)는 모듈에 상수로 둔다. 총 용량은 가능한 작게(필요하면 품질 약간 낮춤, 눈에 띄는 열화 금지).
- `js/bdayscene-yuno.selfcheck.mjs` — DOM 없는 순수 로직(박 위상 · 스윙 · EQ 스펙트럼 계산 등)이 있으면 분리해서 node 로 검증하는 self-check(저장소 관례: `node src/frontend/js/<이름>.selfcheck.mjs`, 실패 시 non-zero). 순수 로직 파일은 `js/bdaybeat.js` 로 분리해도 된다.

## 모듈 API (`js/bdayscene-yuno.js`)
```js
export function mountYunoScene(host, opts) // host: 장면을 그릴 빈 <div>. 반환: controller
// controller = { setStill(bool), celebrate(xRatio?, yRatio?), destroy(), whenReady: Promise }
```
- `host` 안에 `<div class="bdayscene">` 하나를 만들고 그 안에 SVG(또는 필요한 DOM)를 그린다. **host 를 꽉 채우고(`position:absolute; inset:0`) 비율 유지로 덮는다(slice)**. 사이트 쪽에서 host 를 `position:fixed; inset:0; z-index:-1` 로 둘 예정이라 모듈은 위치를 신경 쓰지 말고 host 100%×100% 만 채우면 된다.
- **PC(가로) / 모바일(세로) 구도 모두 지원**: 뷰포트 비율에 따라 viewBox/배치를 바꾼다(`resize` / `ResizeObserver`). v16 은 540px 이하에서 `viewBox '245 -300 850 1060'` 을 썼다 — 참고. 사이트에서는 **유노와 DJ 테이블이 화면 하단 중앙 쪽**에 오고, 위쪽 절반은 하늘(석양 · 별 · 산)과 이퀄라이저가 보이게 구도를 잡아라(위에 콘텐츠 패널이 얹히므로 화면 중앙~위쪽을 비워 두지 않아도 되지만, 유노 얼굴과 손은 하단 1/3~1/2 안에 있게). 세로 화면에서는 유노가 너무 작아지지 않게.
- `setStill(true)`: 모든 모션 정지(CSS 애니메이션 `animation-play-state:paused` + RAF 중단 + 폭죽 정리). `setStill(false)` 로 재개 시 **박 위상이 어긋나지 않게**(v18 방식 그대로: 하나의 시계). 사이트가 「움직임 멈춤」 · 탭 숨김(visibilitychange 는 모듈이 자체 처리해도 됨) · `prefers-reduced-motion` 에서 호출한다. 모션 줄이기면 모듈이 시작부터 정지 상태로 정적 장면만 그린다.
- `celebrate(xRatio, yRatio)`: 폭죽(v16 의 canvas burst). 인자 없으면 v16 의 기본 3발. 캔버스는 host 안에서 `pointer-events:none`.
- 포인터 패럴랙스는 **제외**(사이트 스크롤 · 패널과 충돌, 성능). 폰 흔들기 등 다른 상호작용도 제외.
- 장면 텍스트(「Happy Birthday.」 등) · 탭/툴바 UI 는 **모듈에 넣지 마라**(사이트가 따로 표시).
- 이미지는 상대 경로로 로드: 모듈 위치 기준 `new URL('../assets/birthday/yuno/xxx.webp', import.meta.url)`. 로드 실패해도 예외 없이 배경만 남게. `whenReady` 는 필수 이미지 디코딩 완료 시 resolve.
- **보안 규칙(저장소 규칙)**: 데이터를 `innerHTML` 로 넣지 마라. 정적 템플릿(내가 작성한 SVG 조각)은 `DOMParser` 또는 `createElementNS` 로 만든다. 외부 입력은 아예 받지 않는다.
- 성능: RAF 는 장면이 화면에 보일 때만(탭 숨김이면 중단), 장면이 `destroy()` 되면 리스너 · RAF · 타이머 전부 해제.

## 검증
- 시험용 페이지 `fixtures/bdayscene-yuno.html`(저장소 루트 `fixtures/`)을 만들어 모듈만 풀스크린으로 띄운다(로컬 `python -m http.server` 로 열었을 때 `/src/frontend/...` 상대 경로가 동작하게). Chrome 으로 **PC(1440×900) · 태블릿(768×1024) · 모바일(390×844, 360×740)** 4가지 뷰포트를 캡처(`fixtures/bdayscene-yuno-shots/`)해 직접 보고 구도(유노 위치 · 크기, 이퀄라이저 · 하늘 노출)를 평가하고, v16 과 모션이 같은지(박 위상 · 스크래치 · 고개)도 확인해라. 기존 사이트 CSS 와의 충돌은 내가 통합 후 확인한다.
- `setStill` 토글 · `destroy()` 후 누수 없음 · 콘솔 오류 0 확인.
- 마지막 보고에 파일 목록 · 용량(에셋 합계) · 아쉬운 점을 솔직히. `design_notes` 는 건드리지 마라(이 워크트리엔 없음).
