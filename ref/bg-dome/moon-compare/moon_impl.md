# 달 궤도 「지구돋이」 직접 구현 — 3자 비교 작업 (Claude · Codex · agy 가 각자 따로)

먼저 같은 폴더의 `moon_brief.md`(배경 · 문제 · 제약)를 읽어라. 이번에는 **설계가 아니라 구현**이다.
세 모델이 각자 독립된 워크트리에서 작업하고, 운영자가 결과물을 눈으로 비교한다. 서로의 작업을 보거나 베끼지 말 것.

## 작업 위치 (각자 하나만 — 다른 사람 것 건드리지 말 것)
- Codex : `C:\Users\User\Documents\pyworks\mewtype-scheduler-worktrees\v4\test-bg-moon-codex` (브랜치 test/bg-moon-codex), 서버 포트 8112
- agy   : `C:\Users\User\Documents\pyworks\mewtype-scheduler-worktrees\v4\test-bg-moon-agy`   (브랜치 test/bg-moon-agy),   서버 포트 8113
- (Claude는 test-bg-moon-claude · 8111)
이 워크트리는 feat/bg-dome 의 최신 커밋에서 갈라졌다. **그 밖의 경로 · 다른 브랜치는 수정 금지. 푸시 · 병합 금지**(자기 브랜치에 로컬 커밋만).

## 목표
달 궤도(`__bgplace('moon')`)의 지표면과 지구돋이를 **자연스럽게** — 반복 패턴 · 평평한 회색 바닥 · 직선 지평선을 없애고, 지구돋이 사진의 지구와 이어지는 하나의 장면으로. 지표면이 화면 아래를 가득 채우고 그 위로 지구가 뜬다. 구체적 방법(구면 지평선 · 절차적 크레이터 · 낮은 태양각 그림자 · 지구빛 · 줌 LOD 등)은 당신의 판단. 디자인 품질이 최우선이고, 성능(폰 30fps 이상)은 그다음.
수정 범위는 주로 `src/frontend/js/bgdomegl.js` 의 `spaceBase` 달 부분(`uMoon*`) · `placePhoto` · `draw` 의 달 유니폼. 에셋을 추가하면 `src/frontend/assets/bg/README.md` 에 출처(퍼블릭 도메인만)를 적을 것.

## 확인 방법
1. 자기 워크트리 루트에서 `python scripts/serve_local.py <자기 포트>` 를 백그라운드로 띄운다(이미 쓰는 포트면 다른 걸로 옮기지 말고 알려라).
2. 브라우저(가능하면)로 `http://localhost:<포트>/src/frontend/?bgdebug&bgunlock=all&bgindoor=space&va=claude` 를 열고 콘솔에서
   `document.documentElement.classList.add('bg-peek'); for (const e of document.querySelectorAll('body > *')) { const k=(e.id+' '+e.className); if(!/bg|ufo|hud|deco/i.test(k) && e.tagName!=='SCRIPT') e.style.visibility='hidden'; } for (const e of document.querySelectorAll('.bghud,.ufo-hint,.bg-starlight,.bgfx')) e.style.display='none'; __bgplace('moon');`
   2.5초 뒤 `__bgview(__bgplaceAz(), 38)`, 6초 뒤 스크린샷. 고도 15 · 38 · 60, 그리고 `__bgview` 로 지평선 쪽을 볼 때도 확인.
3. 비교용 스크린샷을 `C:\Users\User\AppData\Local\Temp\claude\190db50d1f62be64\3fc3a647-5a04-4d2d-82d5-7c7dac928dda\scratchpad\shots\<자기이름>_alt15.png`, `_alt38.png`, `_alt60.png` 로 저장(브라우저를 못 쓰면 저장 못 한 사유를 적어라).
4. `node src/frontend/js/bg*.selfcheck.mjs` 가 모두 통과해야 한다.

## 끝나면
`C:\Users\User\AppData\Local\Temp\claude\190db50d1f62be64\3fc3a647-5a04-4d2d-82d5-7c7dac928dda\scratchpad\moon_<자기이름>_report.md` 에 (1) 무엇을 어떻게 만들었는지 (2) 알려진 한계 · 못 한 것 (3) 성능 우려, 를 짧게 쓰고 채팅에 「완료」라고만 남겨라. 이름은 codex / agy / claude.
