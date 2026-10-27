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

---

# 실제 API · V3 스테이징 — 2026-10-27 저녁 (다른 세션 인계용)

브랜치 `hotfix/self-reply-fill` 은 **푸시됨**(`33cad24`, 커밋 10개). **PR · 병합 · 운영 배포는 안 함** — 아래 막힘 때문. 버전 = 마이너(v4.9.0 예정, 운영자 결정).

## 실제 API(이 PC, 시크릿 불필요) — 합격
- `vxtwitter.fetch_profile_statuses` 5명 1.3~1.9초, 유노 · 노노카 · 리츠 자기 답글의 `reply_to_id` 정확. `since=지금` → `[]`(204).
- 단건 조회 답글 필드: vxtwitter `replyingTo` · `replyingToID` 실재(Haiku 「추정」 해소), fxtwitter 폴백도 같은 값. `extract()` → `reply_to` · `reply_to_id` 맞음.
- 로컬 시험판(V2-1~4)은 이 PC 에 `.env.local` 이 없어 못 돌림(시험판 PC 는 따로) — 스테이징으로 대체.

## V3 스테이징 — 결과
- 배포: `mewtype-backend-stage` · `mewtype-telegram-stage` (`STAGE=1 bash deploy/deploy.sh` · `deploy_telegram.sh`, 웹훅 스크립트는 안 돌림 — 운영 봇 연결 보호). 큐 `mewtype-gapfill-stage`(동시 1 · 3회) · `mewtype-daily-stage`(동시 1 · 4회 · 30~300초)는 `setup.sh` 대신 gcloud 로 직접 생성(`setup.sh` 는 시크릿 프롬프트까지 돎). 운영 큐 옵션 불변.
- V3-1: `STAGE=1 scheduler.sh` 는 시험 안 함(코드상 즉시 종료) · 운영 Scheduler 잡 4개 그대로.
- V3-3 인증: 토큰 없음 · 잘못된 형식 · 내 계정 토큰(audience 다름) → 403. Cloud Tasks 가 `INVOKER_SA` OIDC 로 부르면 200. (내 계정은 `INVOKER_SA` 토큰 직접 발급 권한 없음 — IAM 은 안 바꿈. 시험 호출은 `gcloud tasks create-http-task --oidc-service-account-email` 로.)
- V3-5 `/daily`: 큐를 멈춘 채 두 번 호출 → 예약 2개뿐(`daily-monitor-29884150` = 06:10 KST · `daily-websub-renew-29884160` = 06:20 KST, 두 번째는 「Task already exists」), baseline tick 두 번 정상(200, 16~24초). 스테이징에서 monitor · websub 구독이 실제로 돌지 않게 두 작업을 지우고 큐 재개.
- V3-4 보충 작업: 스테이징 data-stage 에 운영 `tweets.json` · `tweet_archive.json` 을 복사하고 유노 글 `2114544324147089633` 만 뺀 뒤 `/gap-fill` 직접 적재 → 단건 조회 + Groq 120b 번역(0.8초) + data-stage 반영(번역 있음) — **합격**. (같은 커밋에서 만료된 유노 글 2건은 정상 sweep.)
- **V3-4 상시 조사 — 막힘**: Cloud Run(스테이징 접수 서비스)에서 `GET https://api.fxtwitter.com/2/profile/<핸들>/statuses` 가 **404**(17:00 정각 전체 조회 = 5명 전부, 17:02 `since` 조회 = 미야코 404 확인). 같은 시각 이 PC(가정 회선)에서는 같은 코드 · 같은 주소가 200. 404 = fxtwitter 명세상 「사용자 없음 또는 빈 목록」(한도 초과면 429) — 우리 사용량(분당 수 회)은 한도 1,000/분에 한참 못 미침. 추정: 구글 데이터센터(공유) IP 대역에서만 막힘 · 또는 X 가 데이터센터 요청에 빈 목록을 줌 · 또는 일시 장애. **확인 안 됨.**
  - 운영 `mewtype-telegram` 은 10-25 같은 호출로 보충 성공 기록(모니터 gap-fill 1건), 그 뒤 404 경고 로그 없음(UserWarning 은 메시지가 같으면 인스턴스당 한 번만 찍히므로 「없음」이 성공을 뜻하진 않음).
  - 17:26 재시도(`since` 조회): 200 · 404 경고 없음 → 아마 5명 모두 204(새 글 없음) — 목록 접근이 됐다는 뜻일 수 있으나 전체 조회가 아니라 결론 못 냄. **18:00 KST 정각 전체 조회 예약(`gapcheck-hour18-…`)** — 결과는 아래 추가.
  - 구글 쪽 다른 경로(Cloud Tasks 로 fxtwitter 직접 GET) 시도 — 큐 기록(log-sampling)을 켰지만 기록이 안 남아 결론 못 냄(기록은 다시 끔).

## 스테이징 상태(남겨 둠 — 운영과 분리)
- 서비스 2개 새 코드로 배포된 상태, 큐 2개 생성됨(`mewtype-gapfill-stage` · `mewtype-daily-stage`), data-stage `tweets.json` · `tweet_archive.json` = 10-27 운영 복사본 + 시험 보충 1건. Scheduler 잡은 만들지 않음.

## 다음 세션이 할 일
1. fxtwitter 404 원인: 스테이징에서 정각 전체 조회 반복 · 큰 다른 계정 목록도 404 인지(시험 경로 필요) · 운영 서버의 지금 즉시 보충(멤버 트윗 때 `_fill_member_gaps`)이 성공하는지 로그 · 계속 막히면 대안(fxtwitter 자체 호스팅 등 — 무료 조건 · X 인증 조건 조사, 유료 경로 제외 — 메모리 「유료 서비스 반려」).
2. 막힘이 풀리면: 남은 V3-4(정각 상시 조사 → 후보 적재 → 보충) · V4 장애 주입 일부 · 그 뒤 PR → 병합(마이너 v4.9.0, 「버전 올릴 때 할 일」 0~6) → 배포 순서(`deploy/README.md` self-reply 절 — `scheduler.sh` 는 KST 05:50~06:30 피해서).
3. 대안으로 갈 경우: 이번 변경이 `/ingest` 의 즉시 보충을 없앴으므로 상시 조사 없이 내보내려면 즉시 보충을 되살리는 수정이 필요.
4. 보류: 트윗 시트 키보드 접근성(메모리 「키보드 접근성 보류」).

---

# 배포 (2026-10-27 KST 17:43~17:50, 운영자 승인 — 「배포, 머지하고 지켜볼 사항을 devpapers 에」)
- 운영자 판단: fxtwitter 404 가 나도 다음 회차가 다시 찾고, 그 간격에 글이 만료 · 밀릴 일은 없으므로 적용. Claude 도 동의(실패 = 지연일 뿐 손실 없음, 지금 운영의 즉시 보충도 같은 호출을 써 나빠지지 않음).
- 운영 큐 2개 → `deploy.sh`(backend 00188) → `deploy_telegram.sh`(telegram 00127) → `telegram_webhook.sh`(텔레그램 API 404 — 이 PC env.sh 토큰 문제, 주소 불변이라 기존 등록 유지로 판단) → `scheduler.sh`(3잡, 옛 3잡 삭제) → PR #101 병합 `2cad9f5` · 태그 `v4.9.0` · 문서 커밋 `67993b0` · `bdb3f11` → Vercel 반영 확인.
- V5 결과 · 지켜볼 것 · 되돌리기 = 같은 폴더 **`watch_after_deploy.md`**.
