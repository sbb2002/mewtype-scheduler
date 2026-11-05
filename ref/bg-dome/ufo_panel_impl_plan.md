# UFO 조작 패널 — 구현 계획서 (2026-11-06 작성, 착수 전)

대상 브랜치 `feat/bg-dome`(워크트리 `mewtype-scheduler-worktrees/v4/feat-bg-dome`, 작성 시점 끝 `47c91c5`). 모바일 기준(PC 는 `HANDOFF.md` 「PC 버전」 — 이번 범위 밖).
디자인 · 동작 정본 = 시안 `ufo-panel/*.dc.html` + `HANDOFF.md` 「조작 패널」 절. 이 문서는 **그걸 실제 코드에 어떻게 붙일지**만 적는다.
코드 위치 · 이름은 작성 시점 코드를 읽고 적었다(줄 번호는 바뀔 수 있어 함수 · 변수 이름으로 적는다).

## 0. 착수 전에 운영자에게 받을 답 (아직 미정)

1. 고른 배경을 기기에 기억할지(시안 기본 = 기억, `localStorage`). 지금은 실내/바깥만 `bgview` 키로 기억하고 핑크/우주는 방문마다 무작위(`bgdomegl.js` `INDOOR_BG`).
2. 우주를 고르면 지금의 무작위 항해 시나리오(`VOYAGE` = rest · depart · cruise · arrive, `voyageBeta()`)를 없애고 길게 누르기 → 기어로만 할지(시안 기본 = 기어로만).
3. 모바일에서 테마 버튼 길게 누르기 팝업(`bgview.js` `initBgView` · `buildPop`)을 없앨지. 없애면 PC 버전 전까지 PC 에서 배경을 못 고른다.
4. 「띵」이 곡 플레이어 · 생일 배경음과 겹칠 때 — 울릴지, 음소거를 따를지(`musicpriority.js` 와의 관계).

## 1. 지금 코드에서 붙일 자리

| 할 일 | 지금 코드 |
|---|---|
| 배경 보기(전체 보기) 켜고 끄기 | `bgpeek.js` — `html.bg-peek` 클래스, 화면 전체를 덮는 투명 버튼 `#bg-peek-catch` 를 누르면 `show()` 로 닫힘. `data-bg-pinch` 가 있으면 닫지 않음 |
| 줌(뒤로 물러서기 r · 망원) | `bgdomegl.js` `zoomT`(목표) · `zoomPath` · `zoomR` · `tele`, `updateView()` 안에서 `if (!peek) { zoomT = 0; ... }` — 배경 보기를 닫으면 r 0. 두 손가락 = `touchstart/move/end` 리스너, `ZOOM_R_MAX = 0.6` |
| 3D → 화면 투영 | `basis()`(카메라 축) · `placePieces()`(공중 무늬 SVG 조각을 `translate3d … scale` 로 배치) · `viewFocal()` · `cx/cy` |
| 실내 핑크 / 우주 | 방문마다 뽑는 상수 `INDOOR_BG`(`"pink"` · `"space"`), 우주 그리기 = `draw()` 의 `if (INDOOR_BG === "space" && !outdoor)` 블록 → `uSpace = (1, β, 누적 거리, 스크롤 속도)`, 사진은 `loadSpaceTex()` 가 처음 쓸 때 받음 |
| 실내 / 바깥 전환 | `bgview.js` `setBgView()` → `BGVIEW_EVENT` → `bgdomegl.js` 리스너가 `outdoor` 를 바꾸고 `useViewProgram()`(이미 컴파일된 프로그램 교체) |
| 바깥 보기 위치 권한 | `bgview.js` `choose("outdoor")` → `bgsite.js` `acquireSite()`, 거절 · 실패 시 실내로 되돌리고 토스트 |
| 시선 · 흔들기 | `updateView()` 가 `gyroAbs()` · `gyroView()` 로 `yaw` · `pitch` 를 부드럽게 따라감 |

## 2. 단계 (단계마다 폰 확인 → 운영자 승인 → 다음)

### 1단계 — 콘솔 · 패널이 나타나고 사라지기 (배경 전환 없음)
- 새 모듈 `js/bgconsole.js`(바닥 콘솔) · `js/bgpanel.js`(화면 패널) + `css/bgpanel.css`. 데이터는 `textContent` · `createElement` 로만(innerHTML 금지 — 저장소 규칙).
- 배경 보기를 열 때 r 을 0.4 에서 시작: `updateView()` 의 「닫으면 0」 옆에 「열리는 순간 `zoomT = zoomPath = 0.4`」 추가(`bgpeek.js` 가 클래스를 붙이는 순간을 `updateView()` 가 `peek` 변화로 감지).
- 바닥 콘솔 = SVG 한 장을 무대 중심 `[0, 바닥 높이, 0]` 에 두고 `placePieces()` 와 같은 투영으로 배치. 비스듬히 보는 원근은 CSS `matrix3d`(basis 로 계산). 셰이더는 건드리지 않는다.
  콘솔 자체 애니메이션(홀로그램 깜빡 · 주사선 · 빛기둥 맥동 · 받침 파동 · 상태등) = 시안 `Approach.dc.html` CSS · SMIL 그대로.
- 문턱: `zoomR < 0.12` 이면 패널 등장, `> 0.18` 이면 퇴장(히스테리시스), `tele > 1` 이면 퇴장. 문턱을 넘을 때만 클래스 전환(`hud on/off`), 매 프레임 DOM 갱신 없음.
- 패널 등장 · 퇴장 효과 = 시안 `Approach.dc.html` 의 `hudIn/hudOut` · `lineIn/lineOut` · `chroma*` · `itemIn` · `typeIn` · `brkIn` 그대로. 움직임 줄이기 = 페이드만.
- **패널 누름이 배경 보기 닫기로 새지 않게**: 패널을 `#bg-peek-catch` 보다 위(z-index)에 두고, 패널 안 `pointerdown` 때 `data-bg-pinch` 처럼 표시를 달아 `show()` 가 무시하게 한다(지금 핀치가 쓰는 방식과 같음).
- 이 단계의 패널 버튼은 아직 아무 일도 안 한다(모양 · 등장만 확인).

### 2단계 — 배경 고르기(버츄얼 스페이스 · 지구)
- `INDOOR_BG` 를 상수에서 바꿀 수 있는 값으로(예: `let indoorBg`, `setIndoorBg()`), `draw()` 의 분기는 그대로 그 값을 읽게. 우주 사진은 처음 고를 때 `loadSpaceTex()` — 받는 동안 버튼에 「불러오는 중」.
- 「지구」 = `bgview.js` 의 바깥 보기 흐름(`choose("outdoor")`) 재사용 — 위치 권한 묻기 · 거절 시 지금 배경 유지 · 안내 토스트. 장소(도시 · 산 · 바다)는 지금처럼 방문마다 한 번(`groundWorld()`), 고를 때마다 다시 뽑지 않는다(산 지형 셰이더 즉석 컴파일로 끊김 방지).
- 0번 질문 1 · 3 의 답에 따라 기억 · 테마 버튼 팝업 처리.

### 3단계 — 초행성X · 워프 기어
- 칸 길게 누르기 = 1초 충전(왼쪽 → 오른쪽, 칩에 %) → 100% 면 성간 이동. 떼면 0.25초에 빠짐. 발동 중 설명 「메롱이다, 그럼 바이바이!」(시안 `Main.dc.html` `chargeLoop`).
  포인터 캡처(`setPointerCapture`)로 떼기를 놓치지 않는다. 길게 누를 때 폰 기본 메뉴(`contextmenu`) 막기.
- 워프 기어 패널(시안 `Gear.dc.html`) — 속도 모형을 순수 함수로 떼어 `js/bgwarp.js`(+ `bgwarp.selfcheck.mjs`: N→3 이 1 · 2 를 거치는지, 중간 단 등속 · 목표 단 지수 접근, 레드존 τ, 흔들림 포락선 값).
  그 β 를 `draw()` 의 `uSpace.y` 에 넣는다 — 지금 `voyageBeta(el)` 자리. 스크롤 속도 `0.45 + 1.6β` · 누적 거리 계산은 그대로.
- 0번 질문 2 의 답이 「기어로만」이면 `VOYAGE` · `voyageBeta()` · 관련 디버그(`bgvoyage` · `bgwarp`)를 정리.
- 기어 패널은 조작 패널 문턱과 별개로 워프 중엔 계속 보인다(시안 가정 — 운영자 미확인이면 1단계 확인 때 같이 물을 것).

### 4단계 — 흔들림 · 좌석벨트 표시등 · 띵 · 진동
- 흔들림 = 돔 시점(`yaw` · `pitch`)에 작은 무작위 오프셋을 더한다(`updateView()` 끝). 패널은 흔들지 않는다. 세기 포락선 = 시안 그대로(가속 τ 0.7 · 끝나면 τ 0.9 잔진동 · 급제동 즉시).
  흔들림이 있는 동안은 `frame()` 의 「다시 그릴지」 조건이 참이 되게(지금은 시점이 움직이면 그린다 — 오프셋도 시점 변화라 그대로 걸릴 것, 확인).
- 좌석벨트 표시등 = 시안 `Gear.dc.html` 의 `.belt` 마크업 · CSS 그대로(실물 따라 그린 SVG, `<use>` 로 꺼짐 · 켜짐 두 겹).
- 「띵」 = Web Audio 합성(시안 `ding()`), 오디오 컨텍스트는 첫 누름 때 만들거나 깨운다. 0번 질문 4 의 답 반영.
- 진동 = `navigator.vibrate`(안드로이드만, iOS 사파리 없음) — 0.12초마다 떨림 세기 비례 길이. 움직임 줄이기 설정이면 진동도 끈다.

## 3. 성능 · 안전 원칙
- 셰이더(`bgdomegl.js` 프래그먼트)는 3단계의 β 연결 말고는 손대지 않는다 — 화면 전체 픽셀 비용이 늘지 않게.
- 새 DOM 은 배경 보기 중에만 붙이거나 보이고, 닫히면 `hidden` · 애니메이션 정지. 탭 숨김 · 생일 장면 · 움직임 줄이기에서 돔이 멈출 때 콘솔 · 패널 애니메이션도 멈춘다.
- 애니메이션은 `transform` · `opacity` · `clip-path` 위주(시안과 같음). 레드존 표시등의 `filter: drop-shadow` 는 작은 요소라 허용.

## 4. 확인 방법
- 단계마다: 순수 로직 self-check(`node src/frontend/js/*.selfcheck.mjs`) → 로컬 서버 + Tailscale HTTPS 로 S23 · 삼성 인터넷 확인(`HANDOFF.md` 「확인 방법」 — 폰 센서 · 진동은 HTTPS 에서만).
- 문턱 값(0.12 / 0.18) · 시작 r(0.4) · 충전 1초는 폰에서 만져 보고 조정.
- 운영자가 확인하기 전 「동작한다」고 보고하지 않는다 — 캡처 · 폰 확인으로 본 범위만 적는다.
