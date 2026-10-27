# 검증 결과 — 2026-10-27 (V0 기준선 일부)

대상: main `f69a7bc`(v4.8.6) = `hotfix/self-reply-fill` 분기점. 코드 변경 전.

## V0-1 기존 self-test — 합격
- 실행: 워크트리 `v4/hotfix-self-reply-fill` 에서 `python -m src.backend.<모듈>` 전부(모듈당 300초 상한) + `collector.rss` · `collector.youtube` · `bus.conform` · `bus.publisher`,
  `node src/frontend/js/<이름>.selfcheck.mjs` 5개.
- 결과: 백엔드 · 수집 · 버스 **46개 통과**, 프론트 5개(king · render · songs · time · timetable) 통과.
- 「실패」 2개는 self-test 가 아님(이번 변경과 무관):
  - `app` — `__main__` 이 Flask 개발 서버(127.0.0.1:8080)를 띄워 300초 상한에 걸려 끝남(종료 코드 124). 끝난 뒤 8080 에 남은 프로세스 없음 확인.
  - `local_runner` — 로컬 러너 자체. 필수 설정(`YOUTUBE_API_KEY` · `INGEST_SECRET` · `ADMIN_SECRET`) 없는 워크트리라 기동 거부(종료 코드 2).
  - 참고: CLAUDE.md 「명령」 의 「self-test 있는 모듈: src/backend 전부」 는 이 둘이 빠진다 — 구현 때 CLAUDE.md 를 같이 고친다.

## V0-2 Scheduler 잡 — 기록
- `mewtype-scheduler` 프로젝트(asia-northeast1) 4개: `mewtype-light` `*/10 * * * *` UTC → backend `/tick` · `mewtype-baseline` `0 6 * * *` Asia/Tokyo → `/tick` ·
  `mewtype-monitor` `10 6 * * *` Asia/Seoul → `/monitor` · `mewtype-websub-renew` `20 6 * * *` Asia/Seoul → `/websub-renew`. 모두 ENABLED.
- 결제 계정의 다른 프로젝트 3개(bandori-song-sorter · bandori-playlist-maker · my-idea-wiki)는 Scheduler API 를 안 씀.

## V0-3 Cloud Run 사용량 — 기록 (최근 30일, Monitoring)
- `billable_instance_time`: mewtype-backend 38,077초 · mewtype-telegram 16,339초 · backend-stage 287초 · telegram-stage 187초(합계 약 54,900초).
- `request_count`: backend 7,941 · telegram 2,405 · backend-stage 92 · telegram-stage 79.
- 두 서비스 모두 1 vCPU · 512Mi · CPU 상시 할당 없음(요청 기반 과금). backend 동시 1 · 최대 1, telegram 동시 80 · 최대 20.

## 안 함
- V0-4(하루 일과 기준) · V0-5(트윗 데이터 모양) · V0-6(보충 현황) — 구현 시작 때 기록.

---

# V1 · V2-5 일부 — 2026-10-27 오후 (구현 뒤)

대상: `hotfix/self-reply-fill` 로컬 커밋 10개(백엔드 5 · 트윗 시트 3 · 점검 수정 2: `5c1c4ec` · `33cad24`). push 전.

## V1-A · V1-B 백엔드 self-test — 합격
- Claude 가 직접 다시 실행: src/backend 전부(app · local_runner 제외) + collector · bus 4개 = **46/46 통과**(기준선과 같음). app · local_runner 는 import 만 확인.
- Haiku 보고상 V1-B 1~27 중 22~25(`/daily`)는 저장소 self-test 가 아니라 별도 Flask 스크립트로만 확인, 7a 는 간접 확인(16 · 16b). 일시정지(25)는 안 함.

## V1-C 트윗 시트 순수 로직 — 합격
- `node src/frontend/js/tweetlogic.selfcheck.mjs` 47건 통과(C1~C8, 운영 레인 색 5개 대비 4.5:1 이상 포함). 기존 프론트 selfcheck 5종(king · render · songs · time · timetable) 통과.

## V2-5 · V2-5a 화면 · 프론트 회귀 — 대부분 합격 (Chrome, 로컬 http.server + 운영 데이터 사본 `data/` 임시, 리츠 글 1건에 `reply_to_id` 예시 주입)
- PC(1920): 가운데 540px 팝업 보드 · 실제 리츠 레인 색(193 201 214) · 검은 글자 · 6글 중 글타래 1개(2글) · 첨부 줄 6 · 사진 버튼 · 「여기부터 새 글」. 머리 줄 탭으로 6글 전체 전환 + `mew:tllang` 저장 · 두 면 같은 높이 · 사진 버튼 / 마우스 끌기로 그 글만 전환 · 멤버 칩 전환 · 닫으면 읽음 처리(배지 숨김, 읽은 트윗 안내) · 폴링 재그림(`renderTweets` 다시 호출) 때 열린 X 카드 iframe 4개 그대로 · 닫으면 iframe 0.
- 폰(같은 페이지를 폭 390 · 360 틀(iframe)에 띄움 — 창 크기 조절이 안 먹어서): 아래 시트 · 손잡이 표시 · 머리 줄 한 줄(360 은 핸들 말줄임) · **번역 글자 폭 322 · 292px**(지금 110px) · 칩 줄 가로 스크롤(`touch-action: pan-x`) · 손잡이 아래로 끌기(터치 흉내) → 닫힘선 표시 후 닫힘 · 첨부 줄 → 원문 · ← 키 → 번역 · 칩으로 멤버 전환.
- 소식 팝업 X 카드 계약: `makeXCard` · `loadXCards` · `stopXCards` 를 직접 불러 확인 — 카드 클래스 · `data-id` · `data-href` · 쉬머, 실제 X 임베드 iframe 생성 + 높이 신호(592px) 수신, 제거. **소식판을 화면에서 열어 본 것은 안 함**(소식판이 접힌 상태라 클릭으로 못 염).
- 콘솔 오류 0(모든 단계).
- 점검 중 찾아 고친 것: ① 배지 최종 상태가 애니메이션 끝에만 기댐(가려진 탭에서 어중간한 상태) → `5c1c4ec` ② `reset.css` 터치 선택 목록이 옛 클래스 → `5c1c4ec` ③ 닫은 뒤 포커스 → `5c1c4ec` · `33cad24`.
- **남은 것(개선 후보, 회귀 아님)**: 닫은 뒤 포커스가 body 로 간다 — 레인 안에 키보드로 갈 수 있는 요소가 배지뿐이고 배지는 읽으면 숨겨짐(아바타 · 이름은 링크 요소가 아님). 지금 운영 코드도 포커스를 돌려주지 않는다. 고치려면 아바타에 `tabindex="-1"` 을 주고 그리로 돌려주는 방식 등.
- 주의: 점검 때 브라우저가 옛 `tweets.js` · `reset.css` 를 캐시로 읽어 「안 고쳐짐」으로 보인 적이 있음 — 포트를 바꿔(8099 → 8098 → 8097) 새로 받아 확인.

## 안 함
- V2-5b(실제 색 대비 화면 측정 — selfcheck 계산으로만) · V2-5c(움직임 줄이기) · 밝게 테마 · 원문 면 안내 문구 표시 · 실제 손가락 터치.
- V2-1~V2-4(로컬 시험판 + 실제 fxtwitter 로 자기 답글 보충), V3(스테이징), V4(장애 주입 — V1 가짜 객체분은 Haiku self-test 에 포함), V5 · V6.
