# v2.5 — 텔레그램 수동 관리 명령 (`/list` `/del` `/ingest` `/undo`)

작성 2026-09-05. v2.3(X 예고 릴레이)·v2.4(합동방송) 위에 얹는다. 배경: `docs/plan/v2_4_golive.md`
§1 에서 폰 웹푸시 캡처가 리트윗/원글 여부와 무관하게 **빈 텍스트나 엉뚱한 스택 알림 내용**으로
올 수 있음이 확인됨(`ref/ingest_try.md`). 이걸 완전 자동으로 감지·보정하려는 시도(`merge_scheduled`
잘림 가드, 다단 undo 스택)는 판단 로직이 급격히 복잡해져서, 대신 **운영자가 직접 보고(`/list`)
고치는(`/del`) 수동 경로**를 두고 `/undo` 는 "방금 한 작업 1건만 즉시 되돌리기"로 범위를 좁혔다.

## 0. 명령

| 명령 | 동작 |
|---|---|
| `/list [유닛]` | 현재 `schedule.json` 방송을 유닛별 idx 로 나열. 유닛 생략 시 5채널 전체. |
| `/del <유닛> <idx>` | 그 유닛의 idx번째 방송을 내림(삭제). **2단계 확인**(아래) 필요. |
| `/ingest <트윗 원문>` (별칭 `/add`) | 폰 자동 릴레이(`POST /ingest`)와 동일한 파싱·반영을 텔레그램에서 수동 실행. `INGEST_ECHO`/`INGEST_DRY_RUN` 스위치와 무관하게 항상 실제 반영 — 테스트 기간에도 트윗을 손으로 붙여넣어 백필하는 용도로 쓸 수 있다. |
| `/undo` | 이 봇을 통해 방금 반영된 변경(`/ingest` 또는 `/del`) **1건**을 되돌림. |

유닛 키: `arale` `yuno` `nonoka` `ritsu` `miyako` (`config/channels.json` `channel_order` 와 동일).

## 1. `/list` — idx 부여 규칙

`schedule.json` `broadcasts[]` 중 그 유닛이 당사자인 행(`channel_key == unit` 또는
`unit in collab_with` — 합동방송은 참여 멤버 전원 유닛에 노출, 프론트 팬아웃과 동일 규칙)을
**상태순(`live` → `upcoming` → `scheduled`) → `scheduled_start` 오름차순**으로 정렬해 1-based
idx 를 매긴다. `/list` 호출 시점 스냅샷이라, 그 사이 다른 변경(정기 `/tick`, 다른 명령)이 끼면
idx 가 밀릴 수 있다 — **`/del` 직전에 `/list` 로 재확인 권장**.

## 2. `/del` — 2단계 확인

1. `/del <유닛> <idx>` → 대상 행의 **전체 스냅샷**을 `admin_state.json` `pending_del` 에 저장하고
   경고 DM 전송(슬롯 1개 — 새 요청이 오면 이전 대기는 덮어써짐):
   - `warn_deltry`: `#{idx} {유닛명}의 {시작~종료} 방송예고를 내리시겠습니까?`
   - `warn_live` (대상이 `upcoming`/`live` 일 때만 추가): `해당 예고는 감지기능으로 다시 되살아날 수 있습니다.`
     — X 릴레이 유래 `scheduled`/`collab` 행(`video_id` 없음)은 지우면 끝이지만, 실제 YouTube
     `upcoming`/`live` 행은 근본 데이터가 YouTube 에 있어 다음 `/tick` 의 RSS/API 재조회로
     되살아날 수 있다. 임시로 숨기는 용도로만 유효.
   - 마지막 줄 고정: `그래도 지우시겠습니까? (y/N)`
2. 다음 메시지가 `y`/`yes`(대소문자 무관)면 삭제 실행, `n`/`no`/그 외/TTL(5분) 초과면 취소.
   이 y/N 판정은 **명령 디스패치보다 먼저** 가로챈다(`_telegram_webhook` 최상단).
3. 삭제 실행 시 **저장해둔 스냅샷과 지금 그 행이 정확히 일치하는지 재확인** 후 지운다(dict 동등
   비교). 그 사이 바뀌었거나 사라졌으면(다른 명령·정기 `/tick` 이 먼저 건드림) 삭제 안 하고
   "그 사이 바뀜 — `/list` 로 재확인" 안내.
4. 성공하면 `admin_state.json` `undo` 슬롯에 스냅샷(변경 직전 `schedule.json` 전체 + 변경 직후
   `sha`)을 남긴다.

## 3. `/ingest`(`/add`) — 폰 자동 경로 재사용

텔레그램 `/ingest` 텍스트 명령은 `POST /ingest`(폰 전용, `X-Ingest-Secret` 인증) 라우트와
**네임스페이스가 다르다**(하나는 URL 경로, 하나는 텔레그램 봇 채팅 명령) — 이름이 같아도 충돌
없음. `xrelay.parse` → `_merge_rows_into_schedule` 를 그대로 재사용하고, 큐(`ingest_queue.json`)
drain 도 동일하게 수행한다. 텔레그런 명령은 이미 `chat_id` 로 인증된 운영자 전용이라
`INGEST_ECHO`/`INGEST_DRY_RUN` 테스트 스위치를 안 거친다 — 붙여넣은 즉시 반영.

## 4. `/undo` — 슬롯 1개, SHA 가드

- `admin_state.json` `undo` 에는 **가장 최근 mutating 명령 1건**(`/ingest`, 폰 자동 `/ingest`,
  `/del`)의 정보만 있다. 그보다 오래된 건 `/undo` 로 못 돌아간다 — `/list`+`/del` 로 수동 처리.
- 판정: 지금 `schedule.json` 의 sha 가 그 작업이 **막 만들어낸 sha** 와 같은지 확인.
  - 같으면(그 사이 아무도 안 건드림) → 변경 직전 전체 내용(`prev_content`)으로 그대로 복원.
  - 다르면(정기 `/tick` 이 실물로 supersede 했거나 TTL 로 지웠거나, 다른 명령이 또 건드림) →
    **거부**. `prev_content` 로 무작정 되돌리면 그 사이의 정당한 변경까지 같이 날아가기 때문.
    "그 사이 갱신됨 — `/list`/`/del` 로 수동 처리" 안내.
- 이 설계는 3개 이상 `ingest`된 행이 각각 `none`/`live`/`scheduled` 로 갈린 혼재 상황(운영 중
  논의된 케이스)에서도 안전하게 동작한다: 그중 하나라도 `/tick` 이 건드렸으면 sha 가 달라져
  `/undo` 전체가 거부되고, 그 시점부터는 `/list` 로 실제 상태를 보고 `/del` 로 원하는 것만
  정밀하게 처리하면 된다 — `/undo` 가 상태를 추론하려 들지 않는다.

## 5. 관련 파일

- `src/backend/admin.py` — `admin_state.json` 스키마 + `pending_del`/`undo` 헬퍼 (순수 함수).
- `src/backend/telegram_app.py` — `/list` `/del` `/ingest` `/undo` 핸들러, y/N 가로채기,
  `_merge_rows_into_schedule`/`_remove_broadcast` 의 undo 스냅샷 기록(`_save_undo`).
- 계약: `admin_state.json` 스키마는 `src/backend/admin.py` 모듈 docstring 참고
  (`docs/SPEC.md` 계약 목록에도 추가 예정).
