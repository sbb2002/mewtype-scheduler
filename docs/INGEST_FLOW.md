# ingest 신호 처리 경로 (현행)

업스트림 시스템(운영자 폰의 Automate 플로우)은 팔로우한 계정의 푸시 알림이 일정 양식(`android.bigText` 등)이면
**무조건** `POST /ingest`(`mewtype-telegram` 공개 서비스)로 중계한다. 로직 수정이나 새 POST
신설은 없다. 그 뒤 `_ingest()`(`src/backend/telegram_app.py`)가 들어온 텍스트를 **소식**·**스케줄**·
**버림**으로 분기한다.

> v2.8(개인 트윗)에서 3↔4 노드 사이에 `android.title` 분기가 추가됨 → `docs/plan/v2_8_personal_tweets.md`.
> v2.8.1: 개인 5인 분기가 배지(`tweets.json`) + **`parse_schedule` → `scheduled` 승격**(`schedule.json`) 둘 다 수행 → `docs/plan/v2_8_1_personal_schedule.md`.

## 들어오는 것 — `request.form` (또는 JSON)

| 필드 | 출처 | 뜻 |
|---|---|---|
| `text` | `nx.android.bigText` (없으면 `android.text`/`nmsg`/`nticker`) | 트윗 본문 |
| `title` | `nx.android.title` | 게시자 표시 이름 (리포스트·외부계정·계정 판별) |
| `template` | `nx.android.template` | `BigTextStyle` 등 — 폰 게이트가 사용 |
| `tag` | `nx.pde_noti_tag` | 트윗 태그 → `x.com/i/status/<id>` · 중복제거 키 |

## 흐름

```mermaid
flowchart TD
    N1["1 · POST /ingest — 업스트림 시스템 중계 · X-Ingest-Secret"]
    D2{"2 · secret 검증"}
    N3["3 · 본문 파싱 (text · title · template · tag)"]
    N4["4 · _maybe_auto_notice — 항상 실행 · ECHO/DRY-RUN 무관"]
    D5{"5 · INGEST_ECHO?"}
    D6{"6 · text 비었나?"}
    D7{"7 · INGEST_DRY_RUN?"}
    D8{"8 · control.paused?"}
    N9["9 · 큐 drain 후 xrelay.parse → rows"]
    D10{"10 · rows 있나?"}
    N11["11 · merge_scheduled → schedule.json scheduled 행 + undo + DM"]

    T2["403 · 종료"]
    T4["xnotice.parse → 소식이면 notices.json 커밋 · added/updated DM"]
    T5["raw body 전문 DM · looks_relayable 이면 큐 적재 · 종료"]
    T6["400 · 종료 (empty text)"]
    T7["파싱 결과만 DM · 저장 안 함 · 큐 적재 · 종료"]
    T8["무시 + silent DM · 종료"]
    T12["스케줄·소식 형식 아님 DM · 소식은 4에서 이미 처리됨"]

    N1 --> D2
    D2 -->|실패| T2
    D2 -->|통과| N3
    N3 --> N4
    N4 -->|소식| T4
    N4 -->|계속| D5
    D5 -->|yes| T5
    D5 -->|no| D6
    D6 -->|yes| T6
    D6 -->|no| D7
    D7 -->|yes| T7
    D7 -->|no| D8
    D8 -->|yes| T8
    D8 -->|no| N9
    N9 --> D10
    D10 -->|예| N11
    D10 -->|아니오| T12
```

세로 척추 = "계속 진행" 경로, 옆으로 빠지면 그 단계에서 응답하고 **종료**.
4번(`_maybe_auto_notice`)만 게이트보다 앞이고 ECHO/DRY-RUN·paused 와 무관하게 항상 돈다.

## 단계 상세

1. **`POST /ingest`** — 업스트림 시스템이 팔로우 계정 푸시 알림을 양식만 맞으면 무조건 중계. 헤더 `X-Ingest-Secret`.
2. **시크릿 검증** — `X-Ingest-Secret == INGEST_SECRET` 아니면 `403`, 그 외 통과.
3. **본문 파싱** — raw body 를 form 파싱 전에 캐시 → `text/title/template/tag` 추출 + 폰 Automate 의
   `urlEncode` 딕셔너리 버그 우회(본문이 폼 키로 새는 경우 복구).
4. **`_maybe_auto_notice()`** — ECHO/DRY-RUN·paused 와 **무관하게 여기서 항상**. 순수 `xnotice.parse`
   가 소식이 아니면 GitHub 는 안 건드림. 소식이면 `notices.merge_notice` → `notices.json` 커밋,
   `added`/`updated` 만 DM.
5. **`INGEST_ECHO`** on → raw body 전문을 청크로 DM + `xrelay.looks_relayable` 이면
   `ingest_queue.json` 적재 → 즉시 종료(파싱·저장 없음).
6. **`text` 비었으면** `400` + 계측 로그.
7. **`INGEST_DRY_RUN`** on → `xrelay.parse` 결과·인식실패 줄만 DM + 큐 적재 → **저장 없이** 종료.
8. **`control.json` 의 `paused`** → 무시 + silent DM → 종료.
9. **`_ingest_queue_drain()`**(테스트 기간에 쌓인 큐 반영) 후 `xrelay.parse(raw)` → `rows`
   (일일 `配信スケジュール` 또는 `出演情報`).
10. **`rows` 유무 분기.**
11. 예 → `merge_scheduled` → `schedule.json` 의 `status:"scheduled"` 행을 같은 날짜 기준 교체 +
    `admin_state.json` undo 스냅샷 + `xrelay.summary_text` DM.
12. 아니오 → "스케줄·소식 형식 아님" 안내 DM (소식은 4에서 이미 처리 — 여기선 아무 것도 저장 안 함).

## 별개 경로

- **`/telegram` 웹훅** — 운영자 명령(`/status /pause /resume /log /list /del /ingest /notice
  /notice-del /notice-list /undo`). 대부분 트윗 인입과 무관하지만 **`/ingest`(무인자 →
  다음 메시지/파일로 원문)** 는 예외로 트윗을 받는다. `_handle_manual_ingest` 가
  `xrelay.parse`(@BDP 일일 스케줄 / `出演情報`)를 먼저 시도하고, 행이 안 나오고 인식
  실패 줄도 없으면 **`_try_personal_ingest`** 로 폴백한다 (멤버 개인 예고 트윗):
  - 본문에 **온전한 YouTube URL 이 있으면** `videos.list`(quota 1) 로 `channelId`
    → 5인 `channel_key` 판별.
  - URL 이 없거나 채널을 못 정하면(영상 비공개 · 링크 잘림 · `YOUTUBE_API_KEY` 미설정
    · 5인 채널 아님) `admin_state.pending_member` 슬롯에 원문을 넣고 **유닛을 되묻는다**
    (`[1]아라레 … [5]미야코`, 취소 `aNoneTokyo`, TTL 5분). 운영자가 `1~5`/이름으로
    답하면 `_handle_member_followup` 이 그 `channel_key` 로 재처리.
  - 채널이 정해지면 `xtweet.parse_schedule`(게이트 = `配信` 계열 + 날짜/URL) →
    `merge_personal_schedule` 로 `schedule.json` 의 `scheduled`(`source:"personal"`) 행
    + undo 스냅샷 + DM. 업스트림 시스템의 `_maybe_personal_schedule`(android.title 로 채널을
    아는 경로)와 결과가 같다.
- **현재 플래그 전제** — v2.7 소식 자동 인입이 운영 중이므로 `INGEST_ECHO=0` · `INGEST_DRY_RUN=0`
  (실배포) 상태. 즉 5·7번 게이트는 통과, 4번과 9~12번이 실제 경로.
