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
