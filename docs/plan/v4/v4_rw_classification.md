# v3 업스트림/DM/tasks·scheduler 쓰기·읽기 분류 (v4 설계 기초자료)

`data` 레포지터리(계약 A~I 파일들)에 대한 READ/WRITE 여부를 기준으로, 현행 v3 요청 처리를 분류한 것. [`v4_improvi_plan.md`](./v4_improvi_plan.md)의 UP1/UP2/UP3 · Main Processor write/read 계열 설계 근거로 쓴다.

소스: [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md)(구조 개요) + [`docs/v3_pamphlet.html`](../../v3_pamphlet.html)(v3.6/v3.7 판정 트리 — `ARCHITECTURE.md`보다 최신이라 업스트림 자동 소식 판정 등은 이쪽이 근거).

분류 기준:
- **분류(읽기/쓰기/둘다)**: 해당 작업이 결과를 만들기 위해 기존 `data` 파일 내용을 **참조(READ)** 해야 하는지, `data` 파일을 **갱신(WRITE)** 하는지를 모두 본다. 병합(`merge_*`)·조회 후 삭제처럼 기존 값을 읽어야 쓸 수 있는 경우는 **둘다**로 분류한다.
- **대상**: [`v4_improvi_plan.md`](./v4_improvi_plan.md)의 메인 컨텐츠 구분(preview·notice·tweet)을 따르되, **실반영(해당 컨텐츠의 `data` 파일을 갱신)에 영향을 주는 작업만** 그 컨텐츠로 분류한다. 단순 조회처럼 실반영에 영향을 주지 않는 작업(=분류가 **읽기**인 작업)은 대상을 묻지 않고 전부 `etc`.

## 전체 분류표

| 구분 | 대상 | 작업 | `data` 레포 동작 | 분류 |
|---|---|---|---|---|
| 업스트림<br>(v4 UP1) | tweet | 개인 트윗 배지 반영 (`_maybe_personal_tweet`) | `tweets.json` 조회 후 병합(`merge_tweet`) | **둘다** |
| 업스트림 | preview | 개인 트윗 기반 예고 승격 (`parse_schedule`→`merge_personal_schedule`, 방송 예고 트윗일 때만) | `schedule.json` 조회 후 `status:"scheduled"` 행 승격 | **둘다** |
| 업스트림 | etc | 테스트 부계정 인입 (`force_echo`) | data 레포 미접근 (DM 회신만) | 해당없음 |
| 업스트림 | preview | 릴레이 트윗 인입 · 테스트 모드(ECHO/DRY-RUN) | `ingest_queue.json`에 원문 적재만 (조회 없이 append) | **쓰기** |
| 업스트림 | preview | 릴레이 트윗 인입 · 실배포 | `control.json` 조회(paused 확인) → `ingest_queue.json` drain(비움) → `schedule.json` 조회 후 병합(`merge_scheduled`) | **둘다** |
| 업스트림 | notice | 공식/미매칭 경로 자동 소식 판정 (`_maybe_auto_notice`→`xnotice.parse`, 크로스오버 계정 포함) | `notices.json` 조회 후 병합(`merge_notice`/`merge_into`, v3.7 LLM 의미중복 게이트) | **둘다** |
| 업스트림 | notice | 개인 5인 트윗 중 비스케줄 이벤트/비유튜브 라이브 링크 이관 | 위와 동일 파이프라인으로 `notices.json` 조회 후 병합 | **둘다** |
| DM<br>(v4 UP3) | etc | `/status` | schedule/control/pending 조회만 | **읽기** |
| DM | etc | `/list` | `schedule.json` 목록 조회만 | **읽기** |
| DM | etc | `/notice-list` | `notices.json` 조회만 | **읽기** |
| DM | etc | `/log` | 로그 조회만 | **읽기** |
| DM | etc | `/pause` | `control.json.paused=true` 설정 | **쓰기** |
| DM | etc | `/resume` | `control.json.paused=false` 설정 (별도로 `/tick` heal 유발 — 아래 `/tick` 항목 참조) | **쓰기** |
| DM | preview | `/del` | `admin_state.json.pending_del` 슬롯 기록 → 확정 시 `schedule.json` 조회 후 대상 삭제 | **둘다** |
| DM | preview | `/ingest`(DM 수동) | `pending_ingest` 슬롯 기록 → 원문 파싱 후 기존 `schedule.json` 조회·병합·저장 | **둘다** |
| DM | preview·notice | `/undo` | `pending_undo` 슬롯 기록 → 복원 대상·커밋 sha 조회 → `y` 확정 시 sha 재대조 후 `schedule.json`/`notices.json` 복원(`undo.path`로 대상 구분) | **둘다** |
| DM | notice | `/notice` | `pending_notice` 슬롯 기록 → 기존 `notices.json` 조회 후 병합(`merge_notice`) | **둘다** |
| DM | notice | `/notice-del` | `notices.json` 조회 후 대상 삭제 | **둘다** |
| Tasks/Scheduler<br>(v4 UP2) | preview | `POST /tick` (정상, Cloud Scheduler) | `control.json`·`tweets.json` 조회 → `schedule.json` 조회 후 재구성(`build_schedule`) → `pending.json` 갱신(`sync_pending`) | **둘다** |
| Tasks/Scheduler | preview | `POST /wake {video_id}` (정상, Cloud Tasks) | `pending.json` 조회 → 라이브 여부에 따라 `pending.json` 재예약 + `schedule.json` 상태 전이 + 종료/취소 시 `archive.json` append | **둘다** |
| Tasks/Scheduler | etc | `/tick`·`/wake` (`paused=true`일 때) | `control.json` 조회만 하고 no-op | **읽기** |

## 요약

- **대상별**: `preview`(예고/스케줄)가 가장 많은 경로를 차지 — 업스트림 릴레이 인입(테스트/실배포), `/del`·`/ingest`(DM), `/tick`·`/wake` 정상 동작. `notice`는 업스트림 자동 판정(공식/미매칭 경로, 개인 트윗 중 비스케줄 이벤트) + DM 쓰기 경로(`/notice`·`/notice-del`) + `/undo`의 일부 — 업스트림에도 존재한다는 점이 `docs/ARCHITECTURE.md`만 봐서는 누락되기 쉬우니 주의. `tweet`은 업스트림 개인 트윗 배지 반영 1건뿐. 나머지 전부(`/status`·`/list`·`/notice-list`·`/log`·`/pause`·`/resume`, paused 상태 no-op, force_echo)는 조회 전용이거나 컨텐츠 비특정이라 `etc`.
- **읽기만**: `/status`·`/list`·`/notice-list`·`/log`, 그리고 `paused` 상태의 `/tick`·`/wake`(no-op).
- **쓰기만**: `/pause`·`/resume`(단순 플래그 설정), 테스트 모드 릴레이 인입(큐 적재만).
- **둘다(조회+갱신)**: 나머지 대부분 — 개인 트윗/예고 인입, 실배포 릴레이 인입, `/del`·`/ingest`(DM)·`/undo`·`/notice`·`/notice-del`, 정상 동작 중인 `/tick`·`/wake`. `merge_*`류 병합 로직이 걸리는 작업은 거의 전부 여기 해당한다.
- **해당없음**: 테스트 부계정(`force_echo`) 인입 — data 레포에 아예 접근하지 않음.
