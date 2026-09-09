# 현행 아키텍처 — 전체 흐름

현재 배포돼 있는 시스템의 구성요소와 데이터 흐름. 그림의 각 박스를 그대로 설명한다.

![현행 전체 흐름](v2_4_flow.png)

*(생성기 `docs/plan/gen_v2_4.py` — `python docs/plan/gen_v2_4.py`)*

- 인터페이스 계약·모듈 명세: `docs/SPEC.md`
- 스케줄 타이밍(운영자 시점): `docs/SCHEDULE.md`
- 세부 설계: `docs/plan/v2_3_x_relay.md`(X 릴레이), `docs/plan/v2_4_collab.md`(합동방송),
  실배포 전환 런북 `docs/plan/v2_4_golive.md`

---

## 구성요소

### 외부 · 운영자 폰

- **Android · Automate** — 운영자가 `@BDP_yumemita` 를 팔로우. 삼성 브라우저 웹푸시 알림이 뜨면
  "HTTP Request" 블록이 `POST /ingest` (`X-Ingest-Secret` 헤더). 폰이 릴레이하는 건 **신호+본문**
  뿐이고, 판정·저장은 전부 백엔드가 한다.
  - Content body 식(이 폰 Automate 빌드 기준, 커밋 `1c21d9a`):
    `urlEncode({"text": coalesce(nx["android.bigText"], nx["android.text"], nmsg, nticker, "")})`
  - 이 빌드는 `urlEncode({"text": expr})` 의 값을 폼 **키** 자리로 흘린다 → 백엔드 `_ingest` 가
    폼 키에서 원문을 복구한다(`# ponytail:`). 상세: `docs/plan/v2_4_golive.md`.
  - `Expression true?` 필터: 본문에 `配信スケジュール` 또는 `出演情報` 포함 (백엔드
    `xrelay.looks_relayable` 과 동일). 테스트 기간엔 생략하고 전부 relay.
  - X **원글**(팔로우 계정 새 글) 알림은 `InboxStyle` 이라 트리거 시점 본문이 비는 경우가 있다.
    **리트윗·인용** 알림은 본문이 extra 에 실려 관통.
- **운영자 Telegram DM** — 아웃바운드 알림(A~F) 수신처. `/status /pause /resume /log` 명령 발신.

### 백엔드 · Cloud Run (`asia-northeast1`)

두 서비스가 **같은 컨테이너 이미지**를 공유하고 엔트리포인트만 다르다.

- **`mewtype-backend`** (비공개, `--no-allow-unauthenticated` + OIDC)
  - `POST /tick` — Cloud Scheduler 2잡(baseline JST 06:00 / light 3h)이 호출. RSS +
    `videos.list` 배치 1회 → `reconcile.build_schedule` 로 `schedule.json` 재구성 +
    `statemachine.sync_pending` 으로 `pending.json` 갱신 + 필요한 wake 태스크 enqueue.
  - `POST /wake {video_id}` — Cloud Tasks 가 방송별로 도달시킴. 그 방송 하나만 조회 →
    라이브 여부 확인 → 다음 체크 재예약(pre-live 3분 / live-watch 시작~+60분 10분 · 이후 3분).
    720h 상한 → `now+696h` 클램프 롱폴링.
  - `paused`(control.json) 면 `/tick`·`/wake` 는 healthcheck 핑만 하고 no-op.
  - 상태 전이(upcoming/live 시작·종료, fallback, 오류)를 Telegram DM 으로 직접 알림.
  - 성공 끝에 `HEALTHCHECK_URL`(healthchecks.io) GET 1발 → grace 초과 시 다운 알림.
- **`mewtype-telegram`** (공개, `--allow-unauthenticated`, `ALLOW_UNAUTH=1`)
  - `POST /telegram` — Telegram webhook. `X-Telegram-Bot-Api-Secret-Token` + `chat.id`
    허용목록. `/status`·`/pause`·`/resume`·`/log`·`/list`·`/del`·`/ingest`·`/undo` 처리.
    `/resume` 은 메인 `/tick` 을 OIDC 발급해 호출(heal).
    - **(v2.5.1)** `/ingest` = 2단계. 무인자로 보내면 `admin_state.json` `pending_ingest` 슬롯
      (TTL 180s) + 안내문 → 이어 보낸 텍스트/첨부파일(`getFile`, UTF-8·256KB)을 원문으로 소진.
      `aNoneTokyo` 취소 · `/`명령이면 대기 접고 통과 · 180s 초과면 만료. (인라인 `/ingest <원문>` 제거)
    - **(v2.5.2)** `/undo` = 2단계. `/undo` → 복원/제거 요약 + 되돌아갈 KST 시각·커밋 sha +
      `pending_undo` 슬롯(y/N, TTL 60s). `y` 시 2중 가드(undo 슬롯 미교체 + 대상 파일 sha 일치).
      **(v2.7)** `undo.path` 로 `schedule.json` ↔ `notices.json` 구분해 복원.
    - **(v2.7)** `/notice` = 2단계(`/ingest` 와 동일) → `xnotice.parse` → `notices.merge_notice`.
      `/notice-list` · `/notice-del <id|번호>`. 상세: `docs/plan/v2_7_notice_board.md`.
  - `POST /ingest` — 업스트림 시스템 인입 (X 예고 릴레이).
    - form 필드: `text`(필수 본문) · `title`(`android.title` 게시자 표시 이름) · `template`
      (`android.template`) · `tag`(`pde_noti_tag`). `tag` → `x.com/i/status/<id>` 링크·중복제거 키.
      폰 Automate `@12` 게이트가 `contains(template,"BigTextStyle")` 로 다운로드/그룹요약/미디어
      재생 알림을 차단. 상세: `docs/plan/v2_3_x_relay.md`.
    - 원본 바디는 `request.form` 접근 전에 `get_data(cache=True, parse_form_data=False)` 로 캐시
      (Werkzeug form 파싱이 스트림을 소비 → 이후 `get_data()` 가 빈 문자열이 되던 버그).
      - **(v2.8) `android.title` 라우팅** — 본문 파싱 직후 `xtweet.route_by_title`. 개인 5인 표시명이면
      `_maybe_personal_tweet` → `tweets.json`(계약 I) 반영 후 즉시 200 (소식/스케줄 파이프라인 안 탐).
      테스트 부계정(`INGEST_TEST_TITLES`, 기본 `jehy`)이면 `force_echo` — 5번에서 무조건 ECHO(헬스체크).
      공식(`夢限大みゅーたいぷ`)·미매칭은 기존 경로. 전체 그림: `docs/INGEST_FLOW.md`.
    - **(v2.8.1)** 개인 5인 분기는 배지 처리 후 `xtweet.parse_schedule` 도 돌린다 — 트윗이 방송
      예고(`配信` 계열 + 날짜[+시각] 또는 온전한 YT URL)면 `merge_personal_schedule` 로
      `schedule.json` 의 `status:"scheduled"`(`source:"personal"`) 행 승격. 정기 `/tick` 은
      `reconcile` 직후 `xtweet.apply_overrides` 로 트윗이 정한 시각을 API 재구성이 안 덮게 한다.
  - **테스트** (`INGEST_ECHO=1` 또는 `INGEST_DRY_RUN=1`): 파싱·저장 안 함. 받은 텍스트 DM 회신
      (ECHO 는 raw body 전문, 4096자 초과 시 청크 분할) + `ingest ECHO: len=.. blen=.. tail_ok=..`
      로그. 스케줄/출연 트윗(`xrelay.looks_relayable`)만 `ingest_queue.json` 에 원문 적재.
    - **실배포** (`INGEST_ECHO=0` · `INGEST_DRY_RUN=0`): `control.json` `paused` 확인 →
      `_ingest_queue_drain` 이 큐 원문을 `received_at` 순서로 `xrelay.parse` → `merge_scheduled`
      → `schedule.json` 커밋, 큐 비움. 이번 요청 본문도 파싱·머지. 결과 DM 에 인식 실패 줄 수 표기.

### 저장 · GitHub `data` 브랜치

Cloud Run 이 GitHub Contents API(fine-grained PAT, Secret Manager)로 변경분만 커밋. 코드 없음.

| 파일 | 내용 |
|---|---|
| `schedule.json` | 계약 A. `status:"upcoming"/"live"` 실물 + `status:"scheduled"`(video_id 없음, X 릴레이 유래) + `host:"group"`(5인 공동명의 채널) |
| `archive.json` | 계약 B. 종료·취소·삭제된 방송 append-only |
| `pending.json` | 계약 E. wake 폴링 FSM 상태 (pre-live / live-watch) |
| `control.json` | 계약 F. `paused` / `log_level` |
| `ingest_queue.json` | 테스트 모드(ECHO/DRY-RUN) 중 온 스케줄 트윗 원문 버퍼. 실배포 전환 후 첫 `/ingest` 에서 drain |
| `admin_state.json` | 계약 G (v2.5). 텔레그램 명령 슬롯 각 1개 — `pending_del`(TTL 300s) · `pending_ingest`(180s) · `pending_notice`(180s) · `pending_undo`(60s) · `undo`(sha 판정, `path` 로 대상 파일 구분) |
| `notices.json` | 계약 H (v2.7). 방송 외 소식(`live`/`release`/`platform`/`etc`). `xnotice.parse` → `notices.merge_notice` 로 중복제거·필드 병합. `expires_at` 지나면 sweep |
| `notice_archive.json` | 계약 H. 만료된 소식 append-only. recap/공연 후 트윗이 과거 소식을 되살리지 않도록 `seen_ids` 대조에 사용 |
| `tweets.json` | 계약 I (v2.8). 멤버 5인 개인 트윗, 채널당 1건 맵. `xtweet.parse` → `merge_tweet`(더 최신 Snowflake id 면 교체). `expires_at`(=received_at+24h) 지나면 sweep. 프론트 편지 배지 |
| `tweet_archive.json` | 계약 I. 만료·교체로 내려간 개인 트윗 로그 append-only (`archived_reason`). 프론트 안 읽음 |

### 프론트엔드 · Vercel

`schedule.json` 을 `raw.githubusercontent.com/.../data/schedule.json` 에서 75초마다 fetch.
빌드 없음, ES 모듈 직접 로드.

- `.card--live` / `.card--upcoming` — 실물 방송 카드.
- `.card--scheduled` — 예고(점선·감광), 썸네일 대신 `icon`, "예고" 배지, 링크는 채널 URL.
  `assumed_live` 면 `.card--sched-live`(실선·빨강기, "방송 중 (추정)").
- `.card--collab` — 합동(`kind=="collab"`). `render.js` 가 참여 멤버 전원(`channel_key` ∪
  `collab_with`) 레인에 같은 카드로 팬아웃. 링크는 `url`(그룹 영상). PC 5열 그리드·모바일
  캐러셀 레이아웃 무변경.
- **(v2.7)** `js/notices.js` + `css/notices.css` 가 예고판 상단 `#notice` 티커를 그린다.
  `NOTICES_URL`(= `data/notices.json`) 을 `schedule.json` 과 같은 75초 주기로 폴링. 기본 1줄만
  표시·5초 회전·무한 순환, `▾`/`▴` 로 전체 펼침. 당일(TODAY) 소식이 있으면 좌측 램프가 빨강
  저속 점멸. 만료 소식은 프론트에서도 숨김(백엔드 sweep 지연 대비). 아래 방송 카드와 중복 없음.
- **(v2.8)** `js/tweets.js` + `css/tweets.css` — `TWEETS_URL`(= `data/tweets.json`, 계약 I) 을 75초
  주기로 폴링. 트윗이 있는 유닛 아바타 우상단에 파란 편지 배지(안 읽음=꽉 참·콩콩 점프, 읽음=외곽선).
  PC: 아바타/배지 호버=말풍선 펼침, 클릭=고정(X/Esc/바깥클릭 닫힘), 여러 유닛 동시 열림.
  모바일: 배지 탭=상단 토스트(메신저 알림풍)+백드롭. 배경색은 유닛 `--lane-color` 재사용, 글자색은
  대비로 자동. 읽음 상태는 뷰어별 `localStorage`. 만료·404 면 배지 안 뜸.

---

## 화살표 (데이터 이동)

| | |
|---|---|
| 알림 본문 | Automate → `mewtype-telegram` `POST /ingest` — form `text`(본문) + `title`(게시자 이름) + `template` + `tag`(트윗 태그) |
| ECHO / 결과 / 알림 DM | Telegram `sendMessage` (양 서비스 → 운영자) |
| 정기 트리거 | Cloud Scheduler → `mewtype-backend` `POST /tick` (OIDC) |
| 방송별 wake | Cloud Tasks → `mewtype-backend` `POST /wake` (OIDC) |
| heal | `mewtype-telegram` `/resume` → `mewtype-backend` `/tick` (OIDC) |
| 커밋 / 큐 | Cloud Run → GitHub Contents API (`schedule.json` 등 커밋 / `ingest_queue.json` 적재·drain) |
| reconcile | 정기 `/tick` 이 `data` 브랜치 읽기·쓰기 |
| raw fetch | `raw.githubusercontent.com/.../data/{schedule,notices}.json` (프론트 75초 폴링) |
| 다운 감지 | `mewtype-backend` `/tick` 성공 → healthchecks.io GET → (grace 초과) Telegram |

---

## `scheduled` 행의 일생 (X 릴레이 유래)

```
@BDP_yumemita 일일 스케줄/出演情報 트윗
        │  폰 Automate → POST /ingest
        ▼
xrelay.parse → merge_scheduled → schedule.json 에 status:"scheduled" 행 (video_id 없음)
        │
        ├─ 정기 /tick 의 reconcile 이 매번 보존
        ├─ 같은 채널 실물 upcoming/live 가 ±4h 안에 뜸 → supersede(제거)
        ├─ scheduled_start 경과 → assumed_live=true (회원전용은 API 로 실물 못 봄)
        ├─ host:"group" 행은 멤버 개인 실물로 supersede 안 함 (그룹 채널은 추적 5채널 아님)
        └─ expires_at (start + 공개 3h / 회원전용 5h) 도달 → 제거
```

Cloud Tasks/`pending.json` 은 안 탄다. 대신 `handlers._scheduled_wake_times` 가
`scheduled_start`(지금~+3h)마다 `light /tick` 1개를 예약해 공개 방송의 정시 시작을 RSS 로 줍는다.
