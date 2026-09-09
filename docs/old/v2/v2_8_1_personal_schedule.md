# v2.8.1 — 개인 트윗 예고 → `scheduled` 승격 + 최신 트윗 시각 override

작성 2026-09-07. v2.8(개인 트윗 편지 배지) 위에 얹는다.
현재 상태: **설계 (확정)**. 현행 ingest 경로: `docs/INGEST_FLOW.md`, v2.8: `docs/plan/v2_8_personal_tweets.md`

---

## 0. 목표

개인 유닛도 본인 계정에서 방송 예고를 올린다 (공식 `@BDP_yumemita` 스케줄보다 **더 빠른 경우가 잦음**).
4명은 `配信 + 날짜 + 시간` 패턴이 확실, 1명(宮永ののか)은 패턴 없음. **5명 전부 같은 규칙**을 적용해
잡히면 `scheduled` 승격, 안 잡히면(노노카 등) 배지로만 두고 공식 스케줄/영상 감지에 의존한다 —
운영에 지장 없음.

v2.8 의 개인 트윗 배지는 그대로. 이 문서는 그 위에 **schedule.json 반영**을 추가한다.

---

## 1. 단계 모델 (계약 A 정식화)

| 단계 | **필수 필드** | 선택 | 만들어지는 곳 |
|---|---|---|---|
| `scheduled` | `date` | `time`, `url`, `video_id`, `kind`, `members_only` | X릴레이(`bdp_schedule`) · 개인 트윗(`personal`) · `出演情報`(`appearance`) |
| `upcoming` | `date` + `time`(→`scheduled_start`) + `url` + `thumbnail` + `video_id` | `collab_with` 등 | **오직** `videos.list` (`liveBroadcastContent=="upcoming"`) |
| `live` | `upcoming` 전부 + `actual_start` | — | `videos.list` / wake |
| (종료) | — | — | → `archive.json` (`ended`/`canceled`/`removed`) |

`assumed_live` = `scheduled` 행의 플래그(시작 지났는데 실물 미확인). 별도 단계 아님.

### 전이 규칙 — "기존 행을 바꾸려면 그 행의 현재 단계 필수조건을 새 정보가 충족해야"

- **`scheduled` 생성**: 새 정보에 `date` 필요.
- **`scheduled` 수정**: 새 정보에 `date` 필요. time/url/kind 는 있으면 병합.
- **`scheduled` → `upcoming`**: `videos.list` 가 `date+time+url+thumbnail+video_id` 전부 제공할 때만.
- **`upcoming` 수정**: 새 정보에 `date`+`time` 필요. 기존 url·thumbnail·video_id 는 유지.
- **`upcoming` → `live` / 종료**: `videos.list` / wake. 무변경.
- 역행(`upcoming`→`scheduled`) 없음. `none` 이면 곧장 archive.

---

## 2. 계약 A 추가 필드

기존 `scheduled` 행(`docs/SPEC.md §1-1`)에 더한다:

| 필드 | 타입 | 뜻 |
|---|---|---|
| `source` | `"bdp_schedule"` \| `"personal"` \| `"appearance"` | 이 행을 낸 트윗 파이프라인. `merge_scheduled` 의 replace-by-date 가 source 별로 격리되게. (기존엔 암묵적으로 `bdp_schedule` 뿐) |
| `time_tbd` | bool (기본 false) | `scheduled` 에서만. true = `scheduled_start` 가 `"<date>T00:00:00Z"` 자리표시자, 시각 미정. `time` 채워지면 해제 |
| `info_source` | `"bdp_schedule"` \| `"personal"` \| `"appearance"` \| `"api"` | 현재 표시 중인 **날짜·시각**을 마지막으로 정한 출처 |
| `info_at` | ISO-Z | 그 정보의 **유효 시각**. 트윗 = Snowflake id 에서 뽑은 작성 시각(없으면 `received_at`). API = 그 `/tick` 실행 시각 |
| `api_start_seen` | ISO-Z \| null | 트윗이 API-확정 행의 시각을 override 한 시점에 **API 가 말하던 `scheduled_start`**. API 가 이 값과 달라지면(스트림 실제 수정) API 가 다시 이김. override 없으면 null |

프론트 계약(계약 C)은 `time_tbd` 만 신경 씀 — 나머지는 백엔드 전용.

---

## 3. 파서 — `xtweet.parse_schedule(text, *, channel_key, tag, now_iso) -> dict | None`

`xnotice._pick_event_date` · `_first_time` · `xrelay.YT_VIDEO_RE` 재사용. 순수. self-test 는 `xtweet.__main__`.

### 게이트 (전부 통과해야 행을 냄 — precision 우선)

1. `配信` 계열 키워드: `配信 | 生配信 | 生放送 | プレミア公開 | 歌枠 | 放送 | ライブ配信 | 同時配信`
2. 그리고 다음 중 하나:
   - **구체 미래 날짜** (`M/D` · `○月○日` · `本日`/`今夜`/`これから` + 시각) — 시각은 있으면 쓰고 없으면 `time_tbd`
   - 또는 **온전한 스트림 URL** (`youtube.com/(watch?v=|live/)<11>` — `xrelay.YT_VIDEO_RE`)

### 오탐 가드 (하나라도 걸리면 None — 배지만)

- 후기: `ありがとう(ございました)` / `お疲れ(様)` / `無事終了` / `見てくれて` + 파싱된 시각이 **과거 30분+** + 미래 마커(`本日`/`今夜`/`これから`/`まもなく`) 없음
- 본문이 `RT @…` / `@handle:` 로 시작 (남의 예고 리트윗)
- 구체 날짜·시각·URL 셋 다 없음

### 행 구성

```jsonc
{
  "channel_key": "<유닛>",
  "status": "scheduled",
  "source": "personal",
  "date": "2026-09-13",                     // 필수
  "scheduled_start": "2026-09-13T12:00:00Z",// date+time(JST→UTC). time 없으면 "<date>T00:00:00Z"
  "time_tbd": false,                        // time 없었으면 true
  "start_approx": false,                    // 본문에 "頃" 있으면 true
  "url": "https://youtube.com/live/<id>",   // 본문 URL 있으면. 없으면 채널 URL
  "video_id": "<id>",                       // 온전한 YT URL 에서 추출. 없으면 없음
  "members_only": false,                    // メン限/メンバー限定/会員限定/🔒
  "kind": "song",                           // 歌枠→song, 그 외 키워드 매핑, 기본 "unknown"
  "icon": null,
  "info_source": "personal",
  "info_at": "<트윗 Snowflake 작성 시각 or received_at>",
  "api_start_seen": null,
  "expires_at": "<§5 규칙>"
}
```

### 특례 — 날짜 없이 URL만

`date` 가 없으면 `scheduled` **불가** (단계 필수조건 위반). 대신 `video_id` 를 정규 파이프라인
후보로 넘긴다 — 실무상 YouTube RSS 가 몇 분 안에 그 영상을 잡으므로 **v2.8.1 에서는 별도 처리 없이
RSS 에 의존**한다(기존 `/tick` 후보 = RSS ∪ 미해결 videoId). 갭: 트윗~다음 `light /tick`(3h) 사이.
필요해지면 후속에서 `pending_videos` 주입. → 이 케이스는 `parse_schedule` 이 **None** 반환(배지만).

---

## 4. 병합 · 중복 붕괴 — `xtweet.merge_schedule_row(prev_schedule, row, now_iso)`

`_merge_rows_into_schedule`(telegram_app, `/undo` 스냅샷·충돌재시도 포함)를 통해 `schedule.json` 반영.
그 안에서 아래 "같은 방송" 판정으로 기존 행과 합친다.

### "같은 방송" 판정 (Q3)

1. **양쪽 `video_id`(또는 온전한 스트림 URL) 있고 값이 같음** → 동일 방송.
   다르면 → **다른 방송** (같은 채널·시각이어도 흡수 안 함 — 재시작 방송 등).
2. 아니면 폴백: 같은 `channel_key` **그리고**
   - 둘 다 시각 있음 → `scheduled_start` **±90분**
   - 한쪽이 `time_tbd` → **같은 날짜(JST)**

### 생존 우선순위 (붕괴 시 어느 행을 남기나)

`video_id` 있는 행 > 상위 단계(`live`>`upcoming`>`scheduled`) > `info_at` 최신 > `bdp_schedule` > `personal`

생존 행에 없는 필드는 소멸 행에서 승계(예: 개인 행의 `scheduled_start` 를 공식 행이 아직 `time_tbd`
면 이관). `scheduled_start`(날짜·시각)만은 **§6 최신-정보-우선** 규칙으로 정한다.

---

## 5. `expires_at` (개인 `scheduled` 행)

- 시각 있음 · 공개 → `scheduled_start + 3h`
- 시각 있음 · `members_only`(`メン限`/`メンバー限定`/`会員限定`/`🔒`) → `scheduled_start + 5h`
- `time_tbd` (시각 없음) → **그 날짜의 JST 자정** (그 날 하루 종일 보이고 자정에 제거)

X릴레이 `scheduled` 행과 동일 정책. 도달 시 제거 (`assumed_live` 를 거쳐).

---

## 6. 최신 트윗이 날짜·시각의 정본 (Q1) — `handlers.py` 후처리 패스

**배경**: 유닛이 불가피하게 지각할 때 YouTube 예고 스트림을 수정하지 않고 **트윗으로만** "22:30〜로
늦어집니다" 를 알릴 수 있다. 그러면 다음 `/tick` 의 `videos.list` 가 (수정 안 된) 원래 22:00 을
돌려줘도 트윗값 22:30 이 유지돼야 한다.

### 규칙

- 시각 정보의 **유효 시각** = 트윗은 Snowflake 작성 시각, API 는 그 `/tick` 실행 시각.
- **트윗 override 는 다음 둘 중 하나가 오기 전까지 유지**:
  1. **더 나중 트윗** (Snowflake > 행의 `info_at`) — 날짜+시각 갖추면 새 값으로.
  2. **API 값 자체의 변화** — `videos.list` 의 `scheduledStartTime` 이 행의 `api_start_seen` 과
     **달라짐** = 스트리머가 실제로 스트림을 수정함 → API 가 다시 이김
     (`scheduled_start`=API값, `info_source="api"`, `api_start_seen=null`).
  - API 가 계속 같은 값(`== api_start_seen`)을 돌려주면 → 트윗값 유지.

### 구현 위치 — `handlers.py` (reconcile 은 수정 금지 모듈)

`src/collector/reconcile.py` = v1부터 검증된 순수 상태 판정 함수, 실물 `upcoming`/`live`/`none` 만
안다. `scheduled` 티어·트윗 override 는 v1이 모르는 개념 → **reconcile 바깥**에서 처리
(v2.3/2.4/2.7 도 전부 이 방식).

`handlers.tick()` 흐름:
```
prev = gh.read schedule.json
... rss + videos.list ...
new = reconcile.build_schedule(candidates, prev, video_infos)   # 기존 그대로
new = xtweet.apply_overrides(new, prev, now_iso)                 # ← 추가
... statemachine.sync_pending ...
gh.write schedule.json = new
```

`xtweet.apply_overrides(new_schedule, prev_schedule, now_iso) -> new_schedule` (순수):
- `new` 의 각 행에 대해 `prev` 에서 같은 방송 행을 찾는다(§4 판정).
- `prev` 행 `info_source in (personal|bdp_schedule|appearance)` 이고 `time_tbd` 아님:
  - `new` 행이 이번 tick 에 API 로 `scheduled_start` 를 얻었으면 →
    - `api_start == prev.api_start_seen` (또는 prev 에 override 없고 `api_start == prev.scheduled_start`)
      → **prev 의 `scheduled_start`·`info_source`·`info_at`·`api_start_seen` 유지**, 나머지(status,
      thumbnail, video_id …)는 `new` 값.
    - `api_start != …` → API 가 이김: `new` 그대로 + `info_source="api"`, `info_at=now`, `api_start_seen=null`.
  - `new` 행이 여전히 `scheduled`(API 미해결) → prev 의 시각 필드 그대로 이관.
- reconcile 이 API 로 새로 만든/갱신한 행에는 `info_source="api"`, `info_at=now` 를 스탬프(override 없을 때).

### 지각 트윗 → 어느 행에 붙나 (R1) — `parse_schedule` + `merge_schedule_row` 단계에서

- 트윗에 스트림 URL 있음 → 그 `video_id` 를 가진 행에 확정.
- URL 없음 → 같은 `channel_key` + 트윗 파싱 `date` == 행 `date`.
- 같은 유닛·같은 날 2행이면 → 트윗 시각에 **가장 가까운** 행.
- 아무 행에도 안 붙음 (R2) → `date` 있으니 **새 `scheduled` 행 생성** (별도 처리 없음).

override 트윗이 붙는 행이 `upcoming` 이면: 그 행에 `date`+`time` 이 갖춰져 있어야 수정 가능
(전이 규칙). 갖추면 `scheduled_start` 갱신 + `info_source="personal"` + `info_at`=Snowflake +
`api_start_seen`=그 행의 직전 `scheduled_start`. 단계는 `upcoming` 유지(url·thumbnail 그대로).

---

## 7. 백엔드 배선

- `xtweet.py` 추가: `parse_schedule`, `merge_schedule_row`(같은 방송 판정 + 붕괴), `apply_overrides`,
  `_same_broadcast(a, b)` (§4). self-test 확장.
- `telegram_app._maybe_personal_tweet`: 배지 처리(v2.8) 후 `xtweet.parse_schedule` 도 호출 →
  행 나오면 `_merge_rows_into_schedule` 로 반영(`/undo` 스냅샷 자동). 그 후 `return`(notice 안 탐).
  - **관측 DM** (초반 튜닝용): 행 생성/갱신되면 `📅 <유닛> 본인 예고 감지 → <시각|미정> <url>` 한 줄.
    precision 안정되면 제거.
- `telegram_app._handle_manual_ingest`(수동 `/ingest`): `xrelay.parse` 가 행을 안 내고
  인식 실패 줄도 없으면 `_try_personal_ingest` 로 폴백. 본문 YouTube URL →
  `_channel_key_by_video`(`collector.youtube.YouTubeClient.videos_list`, quota 1)로 채널
  판별 → `_ingest_personal_row`(= `parse_schedule` + `merge_personal_schedule`). URL 없음/
  판별 실패면 `admin.pending_member` 슬롯(raw 저장)으로 유닛 되묻기(`[1~5]`/이름, 취소
  `aNoneTokyo`, TTL 5분) → `_handle_member_followup` 이 응답받아 재처리. `mewtype-telegram`
  서비스에 `YOUTUBE_API_KEY` Secret 추가 필요(`deploy/deploy_telegram.sh`).
- `handlers.tick()`: `reconcile.build_schedule` 직후 `xtweet.apply_overrides(new, prev, now_iso)`.
- `handlers._scheduled_wake_times`: 개인 `personal` 시각 있는 행도 X릴레이 행과 같이 `light /tick`
  1개 예약. `time_tbd` 행은 정밀 시작 없음 → 예약 안 함(3h 주기에 의존).
- Cloud Tasks / `pending.json` 은 `personal` `scheduled` 행 자체는 안 탐 (video_id 확정 후 정규
  파이프라인이 태움 — X릴레이와 동일).

## 8. 프론트

- `render.js`: `time_tbd` 면 시각 자리에 "시간 미정" (기존 `scheduled_start` 없을 때 분기 재사용),
  카운트다운(`updateCountdowns`)은 `time_tbd` 행 스킵.
- `source == "personal"` 표식(작은 "본인 예고" 칩)은 **선택** — 필요하면 후속. v2.8.1 기본은 무표식
  (X릴레이 `scheduled` 카드와 동일 렌더).

## 9. 문서

`docs/SPEC.md` §1-1(계약 A 필드 5개) · §8.4(handlers apply_overrides) · §8.7(/ingest 라우팅에
parse_schedule 추가), `docs/INGEST_FLOW.md`(개인 분기에 "+ parse_schedule → scheduled" 표기),
`docs/ARCHITECTURE.md`, `docs/VERSION.md`, `CLAUDE.md`.

## 10. 비목표 (v2.8.1)

- 날짜 없는 URL-only 트윗의 즉시 후보 주입(`pending_videos`) — RSS 의존, 필요 시 후속.
- 宮永ののか 전용 파서 — 없음. 공통 규칙 통과 못 하면 배지만.
- `source:"personal"` 프론트 표식 — 선택.
- 개인 트윗의 취소/삭제 감지 — 불가(API 없음). `expires_at` 로만 정리.
