# 생일 이스터에그 화면 음악 연동 — 작업 인수 문서 (Codex 이어받기용)

작성 2026-10-31. 정본 명세 = `docs/BIRTHDAY_MUSIC_SCENE_SPEC.md`(커밋 `78f3e70`). 이 문서는 **지금 어디까지 됐고, 무엇이 남았고, 어떻게 이어가는지**만 적는다. 이 문서와 명세가 어긋나면 명세가 정본이다.

## 1. 현재 상태 (한눈에)

- 브랜치 `feat/birthday-music-scene`, 워크트리 `C:\Users\User\Documents\pyworks\mewtype-scheduler-worktrees\v4\feat-birthday-music-scene`, 기준 `origin/main`(`fc6f8ca`).
- 커밋: `78f3e70`(명세) + 이 문서. **구현 변경은 아직 모두 커밋되지 않은 수정 상태**다(1차 작업 환경에서 Git 쓰기 권한이 막혀 커밋 0개). 이어받는 쪽이 먼저 `git status` 로 확인하고 의미 단위로 커밋할 것.
- 구현 범위(명세 §1~§8 + 추가 지시 1)는 **들어가 있다**: Canvas 장면 이식, 음악 재생·플레이어 UI, 인트로(밝기 곡선 · 17.14초 점등), 기기별 배치, 복사 억제, 정리, 유노 스포트라이트, 태양 일출 + 태양 중심 점등 전파.
- **완료 아님.** Codex 자체 판정도 「출시 가능 미통과」(아래 §2).

### 통과한 검증 (Codex 가 실제 실행, 결과 파일은 §5)
- 기존 `*.selfcheck.mjs` 10개 + 새 검사(박 지도 · 시계 · 17.14초 · 밝기 곡선 · 사인 디코드 · 화면 비율 5종) 전부 통과.
- 평일(생일 아님) 접속에서 장면 · 음원 · 사인 요청 0. `?bday=yuno` 에서만 요청.
- 정본 시안과 PC 픽셀 비교: 의도된 차이(유노 x 이동 · 사인 폭 440 · 드롭 시각)를 보정하면 7개 시점 차이 0.
- 모바일 390×844 · 412×915 · 360×800 캡처 확인(유노 정중앙 · 큰 태양 · 상단 사인 · 연장 하늘/바닥, 제목/컨트롤/안내 겹침 없음).
- 인트로 밝기 곡선 실측(0.03 · 0.17 · 0.30 · 0.30 · 0.30 · 2.4 · 1.7 · 1.45 · 1.0).
- 자동재생 허용/차단 경로, iPhone UA 에서 슬라이더 숨김 · 음소거, 저장 볼륨 복원, 키보드(Chromium 에뮬레이션).
- 추가 지시 1: 태양 y(0~9.9초 지평선 아래 → 10초 상승 → 16.8~17.0초 도착) · 점등 파면 반지름 진행 · 모션 감소 대체 확인.

## 2. 남은 작업 (우선순위 순)

1. **프레임 비용 (가장 큼, 출시 차단)**: 목표 장면 프레임 CPU **8ms 이하**. 현재 추가 효과 구간에서 평균 44~72ms, p95 80~108ms, 최대 115ms(보고서 표: 7.5초 평균 44.08 · 14초 54.97 · 17.3초 72.09). 이미 한 개선: 캐릭터를 개별 필터 대신 **별도 캐릭터 캔버스 1회 합성**으로 바꿈. 아직 큰 곳(Codex 추정): 바닥 격자 + 발광 띠 합성, 스포트라이트 · 점등 전파 합성. 방향 제안:
   - 바닥 발광 띠는 시안(프로토타입 `floorWave`)이 이미 열별 그라데이션 최적화를 거쳤다. 이식본이 그 최적화를 유지하는지 확인.
   - 정적 레이어(하늘 그라데이션 · 별 · 격자선 · 바닥 기본)는 **오프스크린 캔버스에 1회만 렌더**해서 `drawImage` 로 합성, 매 프레임 재계산 금지. 해상도(DPR)는 장면에 한해 낮추는 것도 허용(`Math.min(dpr, 1.5)`).
   - 점등 전파 · 스포트라이트는 radial/linear gradient 객체 재생성을 피하고 `globalCompositeOperation` 횟수를 줄인다.
   - `Chromium headless` 측정은 CPU 렌더링(SwiftShader)이라 실제 GPU 기기보다 훨씬 느릴 수 있다. **측정 환경을 보고서에 명시**하고, 가능하면 GPU 가속 켠 헤디드 Chrome 에서도 재측정. 판정 기준은 「GPU 가속 환경에서 8ms 이하」이면서 「소프트웨어 렌더링에서도 극단적으로 느리지 않음」.
2. **곡 전환 무공백(§7, §9)**: 곡 끝 → 다음 곡 사이 공백 제거. 다음 곡 blob 선로딩 + 곡 끝 직전(예: 남은 0.3초) 두 번째 `Audio`/`AudioBufferSource` 를 예약 재생(Web Audio `start(when)`)하는 방식 검토. 장면 박 지도 · 제목 교체 시점도 맞춘다.
3. **실제 iPhone Safari 검증**: GainNode 볼륨 · 음소거 토글 · 안전영역 · 주소창 높이 변화 · 자동재생 차단 시 탭 시작. 이 PC 에서는 불가하므로 운영자 실기기 확인 항목으로 남기고 보고서에 「미확인」으로 적는다.
4. **커밋**: 구현 변경을 한국어 메시지로 의미 단위 분할 커밋(트레일러 `Co-Authored-By: Codex <noreply@openai.com>`). 예정 제목(1차): `생일 인트로에 유노 조명과 태양 일출·점등 전파 추가` 등. 푸시 · PR 은 운영자 지시 후.
5. **마무리 문서**: `docs/SPEC.md` 「생일 스킨」 · `docs/BIRTHDAY_SKIN.md` · `docs/VERSION.md`(버전 등급 = 새 요소 추가 → **마이너 v4.11.0 제안**, 번호는 운영자 확정 후) · `src/frontend/js/config.js` 의 `APP_VERSION`/`APP_DATE` 는 **운영자 확정 후**에만 바꾼다. `CLAUDE.md` 「현재 버전」 줄도 마찬가지.

## 3. 운영자 확정 사항 (바꾸지 말 것)

- 디자인(프로토타입 v12) 확정. 효과는 **시간에 따라 나오는 방식**(랜덤은 초기 요청이었으나 확정은 곡 진행 기준 스케줄). 유성 개수 · UFO 경로 · 별 각도의 해시 랜덤은 시안대로 유지.
- 유노는 **모든 기기에서 화면 가로 정중앙**. 모바일: 하늘을 위로 늘려 사인을 하늘에 크게, 태양 **1.45배**(1.9 이상 1.6배), 태양 중심을 유노 쪽으로 약 75 단위. 상단 여백은 하늘과 이음새 없이.
- 인트로(곡 1 시계): 0.03 → 3초에 0.30, 17초까지 유지, **17.14초 2.4배 → 1.5초 복귀**, 태양 중심에서 퍼지는 동심원 링. **7초경 유노 스포트라이트**, **10초부터 태양 일출 → 17.14초 직전 도착**, 17.14초에 태양에서 번지는 점등. 17.14초는 저음 에너지 +40dB 점프로 측정한 첫 킥 시각.
- 플레이어: 이전/다음 · 재생/정지 · 볼륨(PC) / 음소거(모바일), 우하단 `♪BGM [mp3 제목]`, 하단 디스클레이머 `듣고 계시는 이 음악은 SUNO로 제작되었습니다.`, 볼륨 기본 30%, 곡은 Noctural Run ↔ Midnight Groove 번갈아 연속.
- 복사 방지는 「우연한 가져가기를 어렵게 하는 장벽」으로만 기록(완벽 불가 명시). 사인은 이미지 파일 없이 벡터 + Canvas.
- 아직 운영자 답을 못 받은 4가지는 **기본값 적용 중**(명세 §8): ① 일반 화면에서도 음악 재생 + 🎂 옆 작은 아이콘 ② 자동재생 차단 시 「탭하여 시작」 ③ 제목은 파일명 그대로(`Noctural Run` 철자 교정은 운영자 확인 대기) ④ 음원 원본 유지(약 10MB).
- **하지 않는 것**: 병합 · 배포 · `APP_VERSION` 변경 · 푸시(지시 전) · `main` 직접 수정.

## 4. 알려진 이슈 · 주의

- Codex 1차 보고에서 인트로 표(밝기 값)와 「ease-out」 설명이 충돌했다고 기록돼 있음(보고서 「인트로 곡선」 절). 값은 표(0.03→0.30@3s, 2.4→1.0@1.5s)를 정본으로 하고 곡선 모양만 ease-out 으로 통일.
- 예전 SVG 장면 검증(`fixtures/validate-bdayscene-yuno.cjs` 등 v16 계산 검사)은 **회귀 자료로 보존**돼 있다. 새 Canvas 검증은 `scripts/verify_birthday_*.py` · `scripts/compare_birthday_pixels.py`.
- 테스트에서만 모듈 응답에 내부 상태 접근 코드를 덧붙여 읽는다(제품 소스에 전역 디버그 훅 없음 — 유지).
- 시안(정본) 프레임 비용은 2카드 합 22ms 정도였다. 이식본이 시안보다 느리다면 이식 과정의 회귀일 가능성이 높으니 **시안 `floorWave`/`visual`/`skyProps` 와 이식본을 같은 시각에서 구간별 시간(`performance.now`)으로 비교**하라.

## 5. 자료 위치

| 자료 | 위치 |
|---|---|
| 정본 시안 · 데이터 · UI 시안 | `C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Documents-pyworks-mewtype-scheduler\cd557148-9ec6-47cb-b90f-a459b94aa233\scratchpad\handoff\` (`prototype_v12.html` · `beatdata.json` · `plan_mockup.html` · `ufo.png` · `pc_sign.jpg` · `m2_sign.jpg`) |
| 1차 · 추가 지시 원문 | 같은 폴더 `brief.md` · `ADDENDUM_1.md` · `brief2.md` |
| **Codex 1차 보고서(상세 표 · 수치)** | 같은 폴더 `REPORT.md` |
| 검증 산출물(캡처 · JSON) | 같은 폴더 `verify\` (`results.json` · `pixels.json` · `lifecycle.json` · `addendum.json` · `mobile-*.png` · `intro-*.png` · `addendum-sheet-1440.jpg` · `addendum-sheet-390.jpg` 등) |
| UI 시안(운영자에게 공유한 아티팩트) | `https://claude.ai/artifact/55aoDLTeARY34pU5mB8Czh` |
| 음원 원본 | `C:\Users\User\Documents\pyworks\mewtype-scheduler-worktrees\devpapers\ref\bgm_easteregg_birthday\` |
| 재실행 | `python scripts/verify_birthday_addendum.py` · `python scripts/compare_birthday_pixels.py` · `python scripts/verify_birthday_lifecycle.py` · `node src/frontend/js/*.selfcheck.mjs` |

## 6. 이어받기 지시문 (Codex 에 그대로 붙여 넣을 것)

> 워크트리 `C:\Users\User\Documents\pyworks\mewtype-scheduler-worktrees\v4\feat-birthday-music-scene` (브랜치 `feat/birthday-music-scene`)에서 이어서 작업하라. 먼저 `CLAUDE.md`, `docs/BIRTHDAY_MUSIC_SCENE_SPEC.md`, `docs/BIRTHDAY_MUSIC_SCENE_HANDOFF.md`, 그리고 `…\scratchpad\handoff\REPORT.md` 를 읽어라. 구현은 이미 들어가 있고 **커밋되지 않았다**. 해야 할 일은 인수 문서 §2 의 순서대로: (1) 장면 프레임 비용을 8ms 이하로(정적 레이어 오프스크린 캐시 · 바닥/조명/점등 합성 최적화 · 시안과 구간별 시간 비교, 측정 환경 명시) (2) 곡 전환 무공백 (3) 가능한 범위의 모바일 재검증, 실기기 필요 항목은 미확인으로 기록 (4) 의미 단위 한국어 커밋(트레일러 `Co-Authored-By: Codex <noreply@openai.com>`) (5) 문서 갱신(버전 상수는 건드리지 말고 제안만). 푸시 · 병합 · 배포 금지. 검증은 직접 실행하고 통과/미통과/미확인을 근거와 함께 `…\scratchpad\handoff\REPORT.md` 끝에 「3차 결과」 절로 덧붙여라. 통과하지 못한 것은 못 했다고 써라. 끝나면 같은 폴더에 `DONE3.flag` 를 만들어라.

## 7. 후속 완료 (2026-11-01)

위 미커밋·배포 금지 상태는 인계 당시 기록이다. 후속 구현·검증과 모니터 방향 입력/가장자리 표시를 완료했고, 2026-11-01 운영자 지시로 PR #127(`6969df5`)을 병합하고 v4.11.0을 프로덕션에 배포했다. 태그는 같은 코드 병합 커밋을 가리킨다. Vercel `dpl_HPj2rF2fAeJ8XMN5L8ootsZUKqLm` READY와 운영 파일 일치·음원 Range를 확인했다.

최신 근거는 `docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md`와 `docs/VERSION.md`다. GPU 가속 CPU 8ms와 스테레오 무공백 검사는 통과했고 소프트웨어 렌더링은 8ms를 넘는다. 실제 삼성 브라우저·iPhone 확인은 운영자가 진행한다. 소스 버전 표기는 v4.11.0/2026-11-01로 갱신했다.
