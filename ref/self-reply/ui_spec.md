# 구현 명세 — 트윗 시트(멤버 트윗 보기 새 화면) (2026-10-27 · 미구현)

같은 핫픽스(`hotfix/self-reply-fill`)에 들어간다. 백엔드 · 데이터 = `patch_spec.md`, 검증 = `verify_spec.md`(V1-C · V2-5 · V5-5 · V6-9). 이 문서는 프론트만.
**운영자가 확정한 시안 = 같은 폴더 `ui_prototype.html`**(아티팩트 https://claude.ai/artifact/56DyWE8n6fh49zZ9Zg6zCA 버전 6). 동작 · 모양 · 수치가 이 문서와 시안이 다르면 **시안을 따르고** 다른 점을 보고한다.
번호: 운영자 결정 = **마이너**(10-27 — 새 등급 규칙: 메이저 · 마이너 · 일반 패치, 새 요소가 들어가면 마이너). 번호는 병합 때(지금 main v4.8.6 이면 v4.9.0).

- 용어(새로 씀 — 구현하면 `docs/TERMINOLOGY.md` 에 올린다):
  - **트윗 시트*** — * 트윗 시트 = 보드에서 멤버 아바타 · 이름 · 트윗 배지를 누르면 뜨는 멤버 트윗 보기 창. 폰 = 아래에서 올라오는 시트, PC = 가운데 뜨는 팝업 보드. 지금의 PC 말풍선(`.lane__bubble`) · 모바일 토스트(`.tw-toast`)를 대신한다.
  - **면*** — * 면 = 트윗 한 건의 두 보기 — 번역 면(우리 번역) · 원문 면(X 공식 카드). 한 번에 한 면만 칸 전체 폭으로 보인다.
  - 글타래 · 이어 붙이기 · 글타래 끌어올리기 = `patch_spec.md` 용어.

## 1. 결정 (운영자, 10-27)

| # | 내용 |
|---|---|
| U1 | 글 하나에 **한 면씩 전체 폭**. 번역 ↔ 원문은 그 글을 **옆으로 밀어서**(폰 플릭 · 마우스 끌기 · 트랙패드). 글마다 붙은 탭 버튼은 **없음** |
| U2 | 머리 줄의 **「번역 · 원문」 탭 = 모든 글 한꺼번에** 전환(선택 기억). ✕ 왼쪽에 둔다 |
| U3 | 두 면은 **같은 높이**(큰 쪽) — 전환해도 목록이 들썩이지 않음 |
| U4 | 번역 면엔 사진 · 영상을 안 그리므로 **첨부 줄**(「사진 1장 · 인용 글 사진 1장 — 원문에서 보기 ›」)과 시각 줄의 **사진 · 영상 버튼(아이콘 + 수, 누르면 그 글만 원문)** 으로 알린다 |
| U5 | 시트 바탕 = **멤버 색**(운영 레인 색 `--lane-color` = 아바타 평균색), 멤버를 바꾸면 색이 부드럽게 넘어간다 |
| U6 | 폰 = 아래 시트(끌어 닫기), **PC = 가운데 팝업 보드**(토스트 · 말풍선 아님). 속 구성 · 조작은 같다 |
| U7 | 시트 안 **멤버 칩**(순서 = `channel_order`: 아라레 · 유노 · 노노카 · 리츠 · 미야코)으로 멤버 이동, 칩 줄은 끌어서 넘김 |
| U8 | 마이크로인터랙션 A1~C4(§6) |
| U9 | 글자색 = 검정 · 흰색 중 **대비 큰 쪽**(지금 「밝기 0.42 기준」 대신), 번역 칸 바탕은 글자 반대쪽으로 섞음 |

## 2. 범위

- 고침: `src/frontend/js/tweets.js`(시트 부분 다시 씀) · `src/frontend/css/tweets.css`(시트 부분 다시 씀) · `src/frontend/css/theme.css`(밝게 값 필요한 토큰만).
- 새로: `src/frontend/js/tweetlogic.js`(DOM 없는 순수 함수) + `src/frontend/js/tweetlogic.selfcheck.mjs`(node 로 import 해 검사 — `king.selfcheck.mjs` 와 같은 방식). `tweets.js` 는 import 할 때 document 를 만지므로 node 에서 못 읽는다 → 순수 로직은 반드시 `tweetlogic.js` 로.
- 손대지 않음: `render.js`(보드 · 레인 · `--lane-color`), `notices.js`, `main.js`(`renderTweets` · `reapplyTweets` 호출 그대로), `sheetdrag.js`(재사용만), `index.html`(시트는 JS 가 만든다).

## 3. 반드시 지킬 것 (기존 기능 · 계약)

1. **소식 팝업이 쓰는 X 카드 공용 코드 유지** — `export makeXCard / loadXCards / stopXCards`, 클래스 `.lane__thread__xcard`(`data-id` · `data-href`) · `iframe.lane__thread__embed` · `.lane__thread__xskel` · `.lane__thread__xlink`, 높이 신호(`_wireEmbedResize`, `twttr.private.resize`) · 15초 실패 링크 · 테마 전환 시 다시 부르기(`THEME_EVENT`). 트윗 시트도 원문 면에 이 카드를 그대로 쓴다. `notices.css` 의 `.ntc-card__cols .lane__thread__xcard` 도 그대로 동작해야 한다.
2. **보드 쪽 그대로**: 트윗 배지 `.lane__tw`(빈 원 · 숫자 원 · 읽음이면 없음, `aria-label`, `data-sig` 로 다시 안 그림) · 아바타 링 `.lane__avatar.has-tweet` · 트윗 없는 네임플레이트를 누르면 흔들기 + 「OO의 새 트윗이 아직 없어요」(`_noTweet`) · 클릭 대상(`.lane__tw, .lane__avatar, .lane__link, .tt__nm`, `data-no-badge` 레인 제외, 캡처 단계에서 앵커 기본 이동 막기).
3. **데이터 규칙 그대로**: `_visible`(만료 `expires_at` 지난 것 빼기 · 게시 시각순 · `MAX_THREAD` 50) · `_postedIso`(posted_at → Snowflake → 받은 시각 「HH:MM 등록」) · 원문 앵커 `_setSrc`(url → x.com/handle → 비활성) · v2.8 단건 하위호환 `_list`.
4. **법률 자문 원칙**: 원문 텍스트 · 사진 · 영상 · 인용 글 미디어는 **우리가 그리지 않는다** — 번역 면엔 번역 텍스트만, 첨부는 「사진 N장」 같은 **개수 글자**만. 데이터의 `media` · `quote.media` 는 개수 · 종류를 세는 데만 쓴다.
5. 데이터는 **`textContent` · `createElement` 로만**(innerHTML 금지 — 지금 `_bubble` · `_ensureToast` 의 고정 마크업 innerHTML 도 새 코드에선 쓰지 않는다).
6. **75초 폴링마다 다시 그려도 X 카드가 다시 불러와지지 않게** — 열린 시트의 목록은 표시 내용 서명(id · 번역 · 인용 번역 · reply_to_id)이 바뀐 때만 다시 그린다(지금 `_fillBubble` 의 `__sig` 방식). 다시 그릴 때 각 글의 지금 면 · 피드 스크롤 위치를 유지.
7. **저장값 이어받기**: 읽음 = `mew:twread`(형식 · 4일 보존 그대로). 전체 면 = 기존 `mew:tllang`("ko" = 번역, "orig" = 원문) 을 그대로 읽고 쓴다(사용자의 지금 설정이 이어지게). 엿보기 횟수 = 새 키 `mew:twpeek`. 모든 읽기 · 쓰기 try/catch.
8. 시트를 닫으면 X 카드 iframe 을 지운다(`_stopCards` — 재생 중 영상 멈춤).
9. Esc 로 닫힘, 바깥(스크림) 클릭으로 닫힘, 포커스는 열 때 시트로 · 닫을 때 누른 자리로.

## 4. 구조

```
body
 ├ .tws-scrim                        바깥 어둠(클릭 = 닫기)
 └ section.tws[role=dialog][aria-modal=true][aria-labelledby=tws-nm]   ← 시트 하나(멤버마다 따로 만들지 않음)
    ├ .tws__grab                     폰 손잡이(PC 숨김)
    ├ .tws__head                     [아바타 · 이름 · 「@핸들 · 최근 48시간」(한 줄 말줄임)] [.tws__seg 번역|원문 + 미끄러지는 알약] [✕]
    ├ nav.tws__members               멤버 칩 줄(.tws__chip ×5 + .tws__mpill 알약), 가로 스크롤 · 끌기, 넘치면 양 끝 흐림
    ├ .tws__feed                     세로 스크롤 목록(위 · 아래 끝 흐림)
    │   ├ .tws__new                  「여기부터 새 글」 구분선(첫 안 읽은 글 앞, 하나)
    │   ├ article.tws-tw             글 하나 (글타래면 .tws-chain[role=group] 안에)
    │   │   ├ .tws-tw__meta          시각 · 「이어서 · N 뒤」 · 새 글 꼬리표 · [사진·영상 버튼 .tws-tw__media] · [X 링크 .tws-tw__open]
    │   │   ├ .tws-tw__track         가로 스냅 스크롤(두 면, align-items: stretch = 같은 높이)
    │   │   │   ├ .tws-tw__face 번역 면 → .tws-ko(.tws-ko__txt · .tws-ko__q 인용 번역 · button.tws-att 첨부 줄)
    │   │   │   └ .tws-tw__face 원문 면 → .lane__thread__xcard(공용 X 카드)
    │   │   └ .tws-tw__dots          면 점 2개(끌기 손잡이 겸)
    └ button.tws__newchip            「새 글 N개 ↓」(새 글 자리가 화면 아래 밖일 때)
```
클래스 이름은 이대로(프론트 DOM 계약 — `docs/SPEC.md` §9 에 올린다). 시안의 이름(`.sheet` · `.tw` · `.ko` …)을 위처럼 `tws` 접두로 바꿔 옮긴다.

## 5. 동작

### 5-1. 열기 · 닫기 · 폭
- 열기: 보드 클릭 위임(§3-2 대상). 트윗이 있으면 그 멤버로 시트를 연다. **PC 호버로 열리는 미리보기(`peek`) · 여러 개 고정(`pinned`)은 없앤다.**
- 폭 판단은 지금 `_mobile()`(`max-width: 767px`) 그대로: 폰 = 아래 시트(폭 전체, 높이 86%, 위 모서리 22px), PC = 가운데 팝업 보드(폭 540px · 최대 높이 660px · 화면 높이 86% 이하). 폭 경계를 창 크기 조절로 넘나들면 닫지 말고 모양만 바뀐다.
- 폰 끌어 닫기: `wireSheetDrag({ dir: "down", handles: [.tws__grab, .tws__head], setScrim, … })` 재사용. 머리 줄의 버튼 · 탭(`.tws__seg`) 위에서는 끌기를 시작하지 않는다. PC 는 끌어 닫기 없음.
- `body.tw-modal-open`(스크롤 잠금) 유지.

### 5-2. 멤버 · 색
- 칩 순서 = `FALLBACK_CHANNEL_ORDER`. 칩 = 아바타 점(레인 색) + 이름(`name_ko` 의 이름 부분 — 지금 `_noTweet` 처럼 마지막 낱말) + 안 읽은 수(현재 멤버 제외). **트윗 없는 멤버 칩은 흐리게 · 누를 수 없게**(`aria-disabled`).
- 색: `_palette(lane)` 를 고친다 — 바탕 = `--lane-color`(없으면 `#3a3a3e`), 글자 = 검정(`#17171b`) · 흰색 중 대비 큰 쪽(시안 `ink()`), 번역 칸 `--paper` = 검정 글자면 `rgba(255,255,255,.38)`, 흰 글자면 `rgba(0,0,0,.2)`. 계산은 `tweetlogic.js` 의 순수 함수.
- 색 전환: `@property --m · --mi`(`<color>`) 등록 + `transition` 500ms. 바탕은 시안처럼 172° 옅은 그라데이션.
- 멤버를 바꾸면: 그 전 멤버 읽음 처리 → 목록 다시 그림 → 칩 방향(오른쪽 칩이면 오른쪽에서) 24px 미끄러져 들어옴 → 칩 알약 이동 → 칩 줄이 현재 칩을 보이게(페이지 전체는 스크롤하지 않게 `scrollLeft` 직접 계산).

### 5-3. 목록 · 글타래 · 새 글
- 묶기 · 순서는 `tweetlogic.js`:
  - `chains(list)` — `reply_to_id` 가 목록 안 글이면 같은 글타래(뿌리까지), 글타래 안은 게시 시각순, **글타래 자리 = 가장 늦은 글 시각**(끌어올리기). 원글이 목록에 없으면 답글은 혼자.
  - 시안 `units()` 와 같은 결과여야 한다.
- 시각 줄: 오늘(KST) 글 = `HH:MM · N분 전`, 아니면 `M/D HH:MM · N시간 전`. 글타래의 답글 = 화살표 + 「이어서 · 시각 · N분/N시간 M분/N일 뒤」(바로 위 글과의 간격). 게시 시각을 모르면 「HH:MM 등록」(지금 규칙).
- 새 글: 첫 안 읽은 글 앞에 「여기부터 새 글」. 열면 그 자리로, 없으면 맨 아래(최신)로 스크롤. 읽음 처리는 **시트를 닫을 때 · 멤버를 바꿀 때**(지금은 열 때 바로 — 바뀜. 보드 배지는 그때 줄어든다).
- 2분 안 글 묶음(`GROUP_GAP_MS` · `.lane__thread__grp`)은 **없앤다** — 글마다 시각 줄이 있다.

### 5-4. 면 전환
- 한 글: `.tws-tw__track` = `overflow-x: auto; scroll-snap-type: x mandatory` 두 면. 손가락은 번역 면 위에서 브라우저 스크롤 그대로. 시각 줄 · 점 줄은 모든 포인터로 끌기(원문 면의 X 카드 iframe 위는 우리가 못 받으므로), 마우스는 글 어디서나 끌기. 8px · 가로가 더 크면 끌기 시작, **놓을 때 스냅을 되돌리기 전에 위치를 읽어**(시안 버그 수정분) 25% 넘으면 넘어감. ←/→ 키(글에 포커스).
- 전체: 머리 줄 탭 → 모든 글. 화면에 보이는 글만 40ms 간격 차례, 나머지 즉시. 선택은 `mew:tllang` 에.
- 첨부 줄 · 사진 버튼: 그 글만 원문 면 + 280ms 뒤 사진 자리 한 번 빛남(이미 원문이면 빛남만).
- 원문 면으로 처음 넘어갈 때 한 번(세션당) 안내: 「X 카드 위에서는 밀기가 X 화면으로 가요. 글 위 시각 줄이나 아래 점 줄을 밀면 번역으로 돌아와요.」
- 면 판정은 `scrollend`(없으면 140ms 디바운스) + 프로그램 스크롤 중 600ms 보호(시안 `settle`).

### 5-5. X 카드 · 높이
- 원문 면의 X 카드는 **글(article)이 피드 화면 근처(위아래 한 화면)에 들어오면** 불러온다 — 원문 면은 가로로 화면 밖이라 카드 자체를 관찰하면 안 불린다. 관찰 대상 = `article.tws-tw`, root = `.tws__feed`.
- 불러오기 전 자리 높이 = 사진 수 · 인용 여부로 어림(`tweetlogic.estimateCardH(m)` — 기본 `CARD_EST_H` 230 + 사진 1장 ~180 · 2장 이상 ~200 · 인용 +90 · 인용 사진 +150 정도, 시안 `xcard()` 비율 참고). 높이 신호가 오면 그 값.
- 두 면 같은 높이는 CSS(`align-items: stretch`)로. 번역이 짧으면 첨부 줄이 아래에 붙고(`margin-top: auto`), 카드가 짧으면 아래 빈 자리.

### 5-6. 첨부 세기 (`tweetlogic.attachments(m)`)
- 사진 = `media` · `quote.media` 의 URL 중 영상 썸네일이 아닌 것, 영상 = URL 에 `video_thumb` 또는 `amplify` 포함(10-27 실측 — 영상은 썸네일 URL 로만 저장됨, `vxtwitter._media_urls`).
- 반환 `{ text: "사진 1장 · 인용 글 사진 1장", photo, video }`. 둘 다 0 이면 첨부 줄 · 사진 버튼 없음.

## 6. 마이크로인터랙션 (시안 그대로 옮김)
| # | 내용 | 시안 함수/선택자 |
|---|---|---|
| A1 | 처음 두 번(`mew:twpeek`) 열 때 보이는 첫 글을 24px 밀었다 돌아옴(260ms, 열고 360ms 뒤). 조작하면 취소 | `peek` · `cancelPeek` |
| A2 | 끄는 동안 점 폭 연속 변화, 25% 선 넘으면 점 톡 + 진동 10ms | `setDots` · `onTrackScroll` · `pulseDot` |
| A3 | 끝 방향 고무줄(1/3, 최대 24px) → 스프링 복귀 | `setRub` · `springBack` |
| A4 | 머리 줄 탭 알약 미끄러짐 + 차례 전환 | `placePill` · `syncPills` · `applyAll` |
| A5 | 멤버 칩 알약 미끄러짐 · 칩 줄 끌기 · 양 끝 흐림 | `members` · `keepChip` · `fadeMembers` |
| B1 | 첨부 줄 · 사진 버튼 → 원문 + 사진 자리 빛남 | `pulseX` |
| B2 | PC 보드는 누른 아바타 쪽에서 커지며 나옴(transform-origin), 열기 320ms · 닫기 210ms | `open` |
| B3 | 폰 끌어 닫기: 스크림 옅어짐 · 닫힘 선 넘으면 손잡이 넓어짐 + 진동 | `wireSheetDrag` 의 `setScrim` · `onMove` |
| B4 | 「여기부터 새 글」 선 그어짐 · 닫으면 보드 배지 줄어들며 사라짐 | `.newline.draw` · `refreshBadges` |
| B5 | X 카드 자리 쉬머(처음 보일 때 280ms) — 실제로는 `.lane__thread__xskel` 쉬머를 높이 신호 올 때까지 | `xcard` |
| C1 | 글타래 세로줄이 처음 보일 때 위→아래로 그어짐 | `.chain.draw` |
| C2 | 「새 글 N개 ↓」 칩 | `#newChip` · `watchFeed` |
| C3 | 피드 위 · 아래 끝 흐림 | `fadeEdges` |
| C4 | 글 포커스 테두리(글자색 2px) · ←/→ | `.tw:focus-visible` |
- 토큰: `--t-fast 120ms · --t-face 260ms · --t-open 320ms · --t-close 210ms · --t-color 500ms`, 곡선 `--ease`, 스프링은 놓을 때만.
- 움직임 줄이기: 이동 · 크기 끔(색 · 투명도만), A1 · A3 안 함. 진동은 `sheetdrag.js` 의 `vibrate()` 재사용.
- 진행 중 애니메이션은 새 조작이 즉시 취소, 필수 상태를 animationend 에 기대지 않음.

## 7. 지우는 것
- `.lane__bubble*` · `.tw-toast*` · `.tw-backdrop` · `.lane__thread__grp/__unit/__msg/__t/__quote` 와 그 코드(`_bubble` · `_fillBubble` · `_positionBubble` · `_repositionAll` · `_showBubble` · `_closeBubble` · `_togglePin` · `_closeAllPins` · `_ensureToast` · `_openToast` · `_closeToast` · `_renderThread` · `_groupMsgs` · `_tlBubble` · `_syncTl` · `_flipLang` · PC 호버 `pointerover/out`).
- **남기는 것**: `.lane__thread__xcard` · `__embed` · `__xskel` · `__xlink` 와 X 카드 코드(§3-1), `.lane__tw` · `.has-tweet` · `.is-nope` · `.tw-nope` 와 그 코드.

## 8. 같이 고칠 문서
- `docs/SPEC.md` §9 트윗(1348줄 부근 「js/tweets.js + css/tweets.css」 · 1407줄 「트윗 토스트」) 을 트윗 시트로 다시 씀 — DOM 구조(§4) · 동작(§5) · 저장 키 · 지우는 것. 소식 팝업 문단(1384~1390)의 「트윗 말풍선과 같은 방식」 문구는 「트윗 시트와 같은 X 카드」로.
- `docs/TERMINOLOGY.md`: 트윗 시트 · 면. `CLAUDE.md` 저장소 구조의 tweets.js 한 줄(「멤버 트윗 말풍선」 → 「멤버 트윗 시트」) · tweetlogic.js 추가.
