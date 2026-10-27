# 검증 명세 — 자기 답글 · 빠진 트윗 상시 조사 (핫픽스, 2026-10-27 작성)

구현 명세 = 같은 폴더 `patch_spec.md`(3차 개정). 이 문서는 **무엇을 · 어떻게 · 어떤 결과면 합격인지**를 적는다. 둘을 같이 고친다.

- 목표 두 가지 — **(가) 기존 기능이 그대로 동작하는가(회귀)** · **(나) 새 동작이 의도대로인가**. 거기에 (다) 부담 · 과금이 예상 안인가, (라) 장애 때 서비스를 해치지 않는가.
- 결과는 단계마다 이 폴더 `verify_result_<YYYYMMDD>.md` 에 남긴다 — 명령 · 출력 요지 · 합격/불합격 · 불합격이면 원인과 조치. **돌리지 않은 항목은 「안 함」 으로 적고 넘어가지 않는다.**
- 표기: **[필수]** = 하나라도 불합격이면 병합 · 배포하지 않는다. [권장] = 불합격이면 운영자에게 알리고 판단을 받는다.
- 단계: V0 기준선 → V1 단위(self-test) → V2 로컬 통합 → V3 스테이징 → V4 장애 주입 → V5 배포 직후 → V6 운영 관찰(1~3일). 앞 단계 [필수] 통과 전에 다음 단계로 가지 않는다.

## V0. 기준선 — 바꾸기 전 상태를 기록 (구현 시작 전)

| # | 항목 | 방법 | 기록할 것 |
|---|---|---|---|
| V0-1 [필수] | 기존 self-test 전부 | main `f69a7bc` 에서 `python -m src.backend.<모듈>`(src/backend 중 `app` · `local_runner` 를 뺀 전부 — 이 둘은 self-test 가 아니라 개발 서버 · 러너를 띄운다 + `collector.rss` · `collector.youtube` · `bus.conform` · `bus.publisher`), `node src/frontend/js/<이름>.selfcheck.mjs`(king · render · songs · time · timetable) | 통과 · 실패 목록. **이미 실패하던 것은 따로 표시**(이번 변경 탓이 아님을 구분) |
| V0-2 | Scheduler 잡 | `gcloud scheduler jobs list --location=asia-northeast1` | 4개(light · baseline · monitor · websub-renew) · 일정 · 대상 |
| V0-3 | Cloud Run 사용량 | Monitoring `run.googleapis.com/container/billable_instance_time` · `request_count` 최근 30일 · 최근 7일(서비스별) | 10-27 값: 30일 합계 약 54,900초 · backend 요청 7,941 · telegram 2,405 |
| V0-4 | 하루 일과 기준 | 최근 3일 monitoring 이벤트에서 06:00 baseline tick · 06:10 스냅샷 · 06:20 websub-renew 의 시각 · 결과, 운영자 DM(monitor) 횟수 | 하루 1번씩인지 |
| V0-5 | 트윗 데이터 모양 | data 브랜치 `tweets.json` · `tweet_archive.json` 크기 · 멤버별 건수, 일자 파일 개수 | v4.8.6 이전 직후 기준값(`ref/archive-split/followup_checks.md`)과 대조 |
| V0-6 | 빠진 트윗 보충 현황 | 최근 7일 모니터 `gap-fill` 이벤트 수 · 모드 | 변경 뒤 비교용 |

## V1. 단위 — self-test (네트워크 없음, 가짜 저장소 · 가짜 fxtwitter)

### V1-A. 회귀 [필수]
- V0-1 의 **모든 self-test 가 같은 결과**(기준선에서 통과하던 것은 전부 통과). 새 코드가 들어간 모듈(`xtweet` · `vxtwitter` · `tasks` · `oidc` · `telegram_app` · `app` · `enrich` · `local_runner`)은 특히 기존 assert 를 지우거나 느슨하게 바꾸지 않았는지 diff 로 확인.
- 기존 동작 고정 케이스(이미 있으면 그대로, 없으면 이번에 더함):
  1. `xtweet.merge_thread` — `reply_to_id` 없는 옛 항목 · 새 항목 섞여도 `added` · `rolled` · `dup` · `stale` 결과가 지금과 같다.
  2. `xtweet.sweep_expired` — 수명 규칙을 안 탄 항목(자기 답글 없음)의 만료 시각 · 보관 사유가 지금과 같다(게시 + 48h).
  3. `_maybe_personal_tweet(via="ingest")` 새 글 → 번역 · `_maybe_personal_schedule` · `_maybe_broadcast_change` · 새 트윗 DM 이 **지금처럼 한 번씩** 불린다.
  4. `_maybe_personal_tweet(via="ops")` 로 이미 있는 글(`dup`) → 판정이 **지금처럼 돈다**(관리 페이지 수동 경로 불변).
  5. `/ingest` 리트윗 → 지금처럼 `retweet skip`, 개인 트윗 · 보충 어디에도 안 감.
  6. `_build_task` — wake · tick · write 태스크 이름(분 버킷 붙음)이 지금과 **글자 하나 다르지 않다**.
  7. `tasks.from_env()` 인자 없이 부르면 대상 = 쓰기 서비스(지금 동작).
  8. `oidc.verify_request` — `ALLOW_UNAUTH=1` 이고 `force` 를 안 주면 지금처럼 건너뜀.
  9. 쓰기 서비스 `/tick` · `/monitor` · `/websub-renew` 응답 · 동작 불변(Flask 테스트 클라이언트).
  10. 프론트 `render` · `timetable` · `time` · `songs` · `king` selfcheck 통과. 트윗 말풍선: `reply_to_id` 가 하나도 없는 데이터 → 묶음 · 순서 · 시각 표시가 지금 `_groupMsgs` 결과와 같다.

### V1-B. 새 동작 [필수]
| # | 모듈 | 케이스 | 기대 |
|---|---|---|---|
| 1 | `vxtwitter` | 목록 응답(fixture: 실응답 1건)의 자기 답글 | `reply_to_id` = 원글 id, 남에게 단 답글은 `reply_to` 가 남 핸들 |
| 2 | `vxtwitter` | `since` 로 204 | 빈 목록(실패 `None` 과 구분) |
| 3 | `xtweet.gap_candidates` | 일반 글 게시 9분 / 10분 / 자기 답글 0분 | 9분 = 제외 · 10분 = 후보 · 자기 답글 = 후보 |
| 4 | `xtweet.gap_candidates` | 후보 5건 | 상한 없이 5건, 오래된 것부터 |
| 5 | `xtweet.gap_candidates` | 원글 48h 넘은 자기 답글 · 리트윗 · 남에게 단 답글 · 이미 아는 id | 자기 답글만 후보 |
| 6 | `xtweet` 수명 | 원글 10:00 · 답글 10:05 / 원글 10-01 · 답글 10-04 / 사슬 3단 | 원글 그대로 / 원글 10-05 / 뿌리까지 모두 늘어남, 답글 자신은 게시 + 48h |
| 7 | `xtweet` 되살리기 | 원글이 캐시(`expired`) / 일자 파일(`rolled`) / `deleted` | 캐시 → 되살림 + 캐시에서 지움 / 일자 파일 → 되살림 + 그 일자 파일에서 지움 / `deleted` → 안 되살림 · 답글도 안 올림 |
| 8 | `xtweet` 되살리기 | 되살린 뒤 `MAX_THREAD` 초과 | 가장 오래된 것이 `rolled`, 결과가 결정적(같은 입력 같은 출력) |
| 9 | `telegram_app` `/gap-check` | 5명 모두 204 | GitHub 읽기 0회 · 태스크 0 · 모니터 기록 0 |
| 10 | `/gap-check` | KST 분 = 0 | 5명 모두 `since` 없이 호출 |
| 11 | `/gap-check` | 후보 2건, 그중 1건 태스크 이름 이미 있음 | 1건 적재 · 1건 건너뜀, 오류 아님 |
| 12 | `/gap-check` | OIDC 없음 / 틀린 audience / 틀린 SA | 403, fxtwitter · GitHub 호출 0회 |
| 13 | `/gap-check` 쉬기 | 3회 연속 전부 실패 → 4번째 실행 / 429 1회 → 다음 실행 / 10분 뒤 | 4번째는 외부 호출 0 · 429 다음도 0 · 10분 뒤 재개, 모니터 warn 시작 1 · 재개 1 |
| 14 | `/gap-check` 시간 상한 | 가짜 fxtwitter 가 25초 지연 | 20초 안에 끝내고 200, 태스크 · 쓰기 없음 |
| 15 | `/gap-fill` | 이미 등록된 id | 200, 쓰기 0 · LLM 0 |
| 16 | `/gap-fill` | 자기 답글, 원글 미등록 · 보관함에도 없음 | 원글 먼저 개인 트윗 경로 → 답글, 커밋 2번, 원글 `expires_at` 이 규칙대로 |
| 17 | `/gap-fill` | 사슬 6단(상한 5) | 5단까지 올라가고 멈춤, 오류 없이 답글은 들어감(원글 연결 끊긴 단독) |
| 18 | `/gap-fill` | `/write` 실패 | 200 반환(재시도 폭주 없음), 모니터 `error` 1줄 |
| 19 | `_maybe_personal_tweet` | 같은 글이 보충 → 폰 순서 / 폰 → 보충 순서 | 두 순서 모두 예고 판정 · 변경 판정 · 새 트윗 DM 이 **딱 한 번** |
| 20 | `/ingest` | 개인 트윗 알림 | `_fill_member_gaps` 를 부르지 않는다(즉시 보충 제거) |
| 21 | 모니터 등급 | 자기 답글 보충 / 일반 글 보충 / 원글 함께 / 원글 되살림 | `ok` / `warn` / detail 「원글 함께」 / 「원글 되살림」 |
| 22 | 쓰기 서비스 `/daily` | 06:00 실행 | `/monitor` 06:10 · `/websub-renew` 06:20 태스크 2개 + baseline tick 1회 |
| 23 | `/daily` | 같은 날 두 번(재시도), 06:15 에 재시도 | 태스크 이름 같아 추가 생성 없음 · tick 은 재시도마다(지금 `/tick` 재시도와 같음) |
| 24 | `/daily` | 태스크 적재 실패 | baseline tick 은 그래도 실행, 응답 500 → Scheduler 재시도로 다시 적재 시도, 운영자 알림 1회 |
| 25 | `/daily` | 일시정지 | tick = paused 결과(지금과 같음), 태스크 2개는 예약(지금도 monitor · websub 는 가드 없음) |
| 26 | `tasks` | `gapfill-<id>`(버킷 없음) · `daily-monitor-<버킷>` · 대상 URL 인자 | 이름 · URL · OIDC audience 가 각각 맞다 |
| 27 | `enrich` · `local_runner` | 로컬 보충 작업 | 가공 큐 `q-enrich` 에 적재, 교착 없음 |
| 28 | 프론트 selfcheck(새 `tweets` selfcheck 또는 render 에 추가) | 원글 있음 · 없음 · 간격 11분 · 사슬 2단 · **5시간 뒤 답글** | 원글 바로 뒤 · 단독 · 붙음 · 순서대로 · **글타래가 맨 아래로 끌어올려짐** |
| 29 | 프론트 | 끌어올린 글타래 + 2분 묶음이 섞인 목록 | 글타래는 한 묶음, 다른 2분 묶음은 그대로, 시각 표시 = 각 묶음의 가장 늦은 글 |
| 30 | 프론트 | 읽음 기록 있는 원글 + 새 답글 | 원글 읽음 유지 · 안 읽은 개수 1 |

## V2. 로컬 통합 — 로컬 시험판(`python -m src.backend.local_runner`, `V4A_RUNTIME=local`)

데이터 = 로컬 파일(`myprojects/mewtype-scheduler-localdata/`). fxtwitter 는 **실제 호출**(분당 5회 — 한도 0.5%), LLM 은 Groq 공유 키라 **다른 시험과 동시에 돌리지 않는다**.

| # | 항목 | 방법 | 기대 |
|---|---|---|---|
| V2-1 [필수] | 상시 조사 실제 응답 | 러너 1분 타이머로 30분 이상 | 대부분 204 · 로그에 GitHub(로컬 파일) 읽기는 응답이 있을 때만 · 오류 0 |
| V2-2 [필수] | 실제 자기 답글 보충 | 로컬 데이터에서 최근 자기 답글 1건(48h 안)을 지우고 다음 정각 실행 대기(또는 `since` 없이 수동 실행) | 원글 뒤 `reply_to_id` 로 들어감 · 번역 · 원글 수명 규칙 · 모니터 `ok` |
| V2-3 [필수] | 원글 되살리기 | 로컬 데이터에서 원글을 보관함 캐시로 옮기고(V2-2 반복) / 일자 파일로 옮기고 | 되살아나 스레드에 있고 보관함 쪽에서 사라짐(양쪽에 없음 · 잃은 것 없음 — `scripts/split_archives.py --dry-run` 「잃은 항목 0 · 중복 0」) |
| V2-4 [필수] | 폰 경로 회귀 | 로컬 `/ingest` 에 fixture 개인 트윗 알림 · 리트윗 알림 · 공식 계정 글 · 게임 계정 글 | 개인 트윗 = 지금과 같은 결과(즉시 보충만 없음) · 리트윗 skip · 공식 → 소식 · 스케줄 판정 · 게임 → 행사 판정 그대로 |
| V2-5 [필수] | 화면 | 로컬 서버(`python -m http.server 8099`)로 V2-2 · V2-3 데이터 열기 — PC 폭 · 모바일 폭(≤640px) · 밝게/어둡게 · 번역 ON/OFF | 이어 붙이기 · 끌어올리기 · 기존 말풍선(X 카드 로딩 · 번역 토글 · 배지 · 토스트 끌어 닫기) 정상, 콘솔 오류 0. **화면 캡처를 운영자에게 보여 모양 확인(D11)** |
| V2-6 [권장] | 옛 데이터 | `reply_to_id` 없는 운영 `tweets.json` 사본으로 화면 | 지금 운영 화면과 같은 배치 |

## V3. 스테이징 — `STAGE=1` 배포(운영 무영향: 서비스 · 큐 · 데이터 브랜치 전부 따로, DM 없음)

| # | 항목 | 방법 | 기대 |
|---|---|---|---|
| V3-1 [필수] | Scheduler 를 안 만든다 | `STAGE=1 bash deploy/scheduler.sh` | 아무것도 안 하고 끝남, `gcloud scheduler jobs list` 4개(그대로) |
| V3-2 [필수] | 큐 | `STAGE=1 bash deploy/setup.sh` | `mewtype-gapfill-stage` · `mewtype-daily-stage` 생성 · 옵션(동시 1 · 시도 횟수) 확인. 운영 큐 옵션 불변 |
| V3-3 [필수] | 인증 | 토큰 없이 / 다른 SA 토큰 / `INVOKER_SA` 토큰으로 스테이징 `/gap-check` · `/gap-fill` 호출(`gcloud auth print-identity-token --impersonate-service-account=… --audiences=<URL>`) | 403 / 403 / 200 |
| V3-4 [필수] | 상시 조사 수동 | `INVOKER_SA` 토큰으로 스테이징 `/gap-check` 를 1분 간격 10회 + 정각 1회 | V2-1 과 같은 결과, 보충 태스크는 스테이징 큐로, 쓰기는 `data-stage` 로 |
| V3-5 [필수] | `/daily` 수동 | 스테이징 `/daily` 1회 | `mewtype-daily-stage` 에 태스크 2개(그날 06:10 · 06:20 — 이미 지난 시각이면 바로 실행) · baseline tick 결과, 다시 부르면 태스크 추가 없음 |
| V3-6 [필수] | 기존 경로 | 스테이징 `/ingest` · `/telegram`(`/status`) · `/websub/<이름>`(GET 허브 검증) · `/admin` 로그인 링크 | 지금과 같은 응답 |

## V4. 장애 주입 (V1 가짜 객체 + V3 스테이징)

| # | 주입 | 기대 | 단계 |
|---|---|---|---|
| V4-1 [필수] | fxtwitter 전부 타임아웃 30분 | 3회 시험 → 10분 쉼 반복, 실행당 외부 호출 시간 ≤ 20초, 모니터 warn 은 쉼/재개 쌍만 | V1-13 · V1-14 |
| V4-2 [필수] | fxtwitter 429 | 즉시 10분 쉼 | V1-13 |
| V4-3 [필수] | 1명만 실패 | 나머지 4명은 정상 처리, 쉼 아님 | V1 |
| V4-4 [필수] | GitHub 읽기 실패 | 그 실행 건너뜀 · 다음 실행 정상 · 쓰기 없음 | V1 |
| V4-5 [필수] | `/write` 503 · 429 | `writeclient` 백오프 그대로, 보충 작업 200 반환 · 다음 조사가 다시 찾음 | V1-18 |
| V4-6 [필수] | 같은 글이 폰 · 보충으로 1초 차 동시 도착 | 판정 · DM 한 번, 번역은 최대 두 번(허용) | V1-19 |
| V4-7 [권장] | 실행 겹침(앞 실행이 60초 넘음) | 같은 후보는 태스크 이름으로 한 번만 | V1-11 |
| V4-8 [필수] | `/monitor` 계속 실패 | `mewtype-daily` 큐 시도 4회에서 멈춤, 오류 DM ≤ 4회(지금 Scheduler 재시도와 같은 수준) | V3(스테이징 큐에서 실패하는 가짜 대상) |

## V5. 배포 직후 (운영, 배포 당일)

| # | 항목 | 방법 | 기대 |
|---|---|---|---|
| V5-1 [필수] | Scheduler | `gcloud scheduler jobs list` | **정확히 3개**(light · daily · gapcheck), 옛 3개 없음 |
| V5-2 [필수] | 상시 조사 첫 1시간 | 접수 서비스 로그 · 모니터 이벤트 | 분당 1회 실행 · 403 0 · 오류 0 · 대부분 204 |
| V5-3 [필수] | 폰 경로 | 배포 뒤 첫 멤버 트윗 알림 | 지금과 같이 들어옴 · 판정 · DM 한 번 · 보충 이벤트가 같은 id 로 또 안 생김 |
| V5-4 [필수] | 기존 정기 작업 | light tick(10분) · wake 태스크 | 전과 같은 주기 · 오류 없음(쓰기 서비스 로그) |
| V5-5 [필수] | 화면 | `https://mewtype-schduler.vercel.app/?va=claude`(Claude 가 열 때 `?va=claude` 필수) PC · 모바일 폭 | 기존 말풍선 정상 · 콘솔 오류 0 |

## V6. 운영 관찰 (배포 뒤 1~3일)

| # | 항목 | 기대 | 불합격이면 |
|---|---|---|---|
| V6-1 [필수] | **다음 날 06:00~06:20** | baseline tick 1회 → 06:10 스냅샷 · monitor DM **1번** → 06:20 websub-renew 1회(V0-4 와 같은 모양) | 옛 잡 3개 복구(patch_spec §8 되돌리기) |
| V6-2 [필수] | 첫 자기 답글 | 게시 후 1~2분 안에 들어옴(모니터 `gap-fill(자기 답글) · +N분`) · 원글 뒤에 붙음 · 늦은 답글이면 글타래가 맨 아래로 | 원인 조사 · 운영자 보고 |
| V6-3 [필수] | 중복 판정 | 폰과 보충이 겹친 글이 있으면 판정 · DM 한 번(모니터 · DM 기록) | §4-3 재점검 |
| V6-4 [필수] | 부담 | 하루 fxtwitter 호출 ≈ 7,200 · 204 비율 · 글 받은 실행 수(예상 하루 약 200) · GitHub 읽기 · Groq 호출 증가분 | 예상의 2배 넘으면 원인 보고 |
| V6-5 [필수] | 과금 | Cloud Run `billable_instance_time` 하루 증가분(예상 접수 서비스 하루 약 2,500초 이하) · 7일 뒤 월 환산이 무료 18만 vCPU-초 안 · Scheduler 잡 3개 유지 | 창 · 주기 재조정 제안 |
| V6-6 [권장] | 일반 글 보충 | 폰이 빠뜨린 일반 글이 다음 정각에 `warn` 으로 들어옴(게시 후 10~70분) | patch_spec §7-3 재논의 |
| V6-7 [권장] | 보관함 정리(v4.8.6)와 함께 | 매일 06:10 정리 뒤에도 되살린 원글이 캐시 · 일자 파일 양쪽에 없음 | 되살리기 로직 점검 |

## 결과 보고
- 단계마다 `verify_result_<날짜>.md` 를 devpapers 에 커밋 · 푸시하고, 운영자에게 [필수] 합격 · 불합격 요약을 알린다.
- 병합 · 배포는 운영자 결정 — V1 · V2 · V4(가짜) 합격 뒤 PR, V3 는 운영자 허락 후 스테이징 배포, V5 · V6 은 운영 배포 뒤.
