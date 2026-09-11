# 구현 명세 (SPEC) — v3.0

현행 구현 계약. v2 원문은 `docs/old/v2/`, v1 은 `docs/old/v1/`.
설계 배경: `docs/plan/v3_backend_surgery.md`(기능 상세) · `docs/plan/v3_draft.md`(결정 로그) ·
`docs/plan/v3_telegram_controller.md`(제어 채널) · `docs/plan/v3_impl_spec.md`(구현 명세·진행) ·
`docs/plan/v3_golive.md`(전환·롤백 런북).

> **배포 상태**: **v3.0 배포됨 (2026-09-09)** — `main` 이 현행. `data` 브랜치는 콜드 스타트
> (v2 파일은 `data:.old/`, 마이그레이션 스크립트 없음).

**인터페이스 계약(§1~§7)을 벗어나는 변경은 이 문서를 먼저 고친다.**

---

## 0. 아키텍처 / 저장소 구조

서버 상시 가동 없음. 무료 인프라만 사용.

| 역할 | 수단 |
|---|---|
| 수집·판정 | **Cloud Run**(scale-to-zero, `src/backend/`, Flask+gunicorn). 리전 `asia-northeast1` |
| 정기 트리거 | **Cloud Scheduler** 2잡 — baseline JST 06:00 / light 3h → `POST /tick` (OIDC) |
| 방송별 정밀 wake | **Cloud Tasks** — `POST /wake {video_id}` (OIDC). 720h 상한 → `now+696h` 클램프 롱폴링 |
| 저장 | **GitHub `data` 브랜치** — Cloud Run 이 GitHub Contents API(fine-grained PAT, Secret Manager)로 커밋 |
| 프론트 | **Vercel** 정적 호스팅 (빌드 없음). `raw.githubusercontent.com/.../data/preview.json` 75초 폴링 |
| 모니터링·제어 | 공개 서비스 **`mewtype-telegram`**(같은 이미지, 다른 엔트리포인트) — Telegram webhook + `/ingest` |
| 외부 LLM | **Groq**(선택) — notice 제목 추출 + notice/개인트윗 번역. 키 없으면 원문 노출 폴백 |
| 업스트림 시스템 | 운영자 폰 Automate — X·YouTube 푸시알림을 `POST /ingest` 로 중계(코드베이스 밖) |

```
src/
  frontend/            # Vercel Root Directory = src/frontend, 빌드 없음
    index.html         # #notice + #board + #foot 스켈레톤, <script type="module">
    css/{reset,layout,card,notices,tweets}.css
    js/
      config.js        # 상수 (PREVIEW_URL, NOTICES_URL, TWEETS_URL, 폴링 주기, 폴백 채널)
      time.js          # UTC→KST 포맷 · 상대시간(D-n·절대표기) · elapsedLabel — 순수
      api.js           # fetchPreview(url): AbortController 타임아웃, {ok,data|error}
      render.js        # renderBoard / renderFooter / updateCountdowns — preview.items(state) 기반
      notices.js       # 소식 티커 (title_ko 있으면 [번역]—[원문] 순 marquee)
      tweets.js        # 유닛 아바타 편지 배지 (+ text_ko 원문↔번역 토글 버튼)
      main.js          # DOMContentLoaded → poll(preview) + pollNotices + pollTweets + 카운트다운 틱
  collector/           # v1 순수 모듈 — rss/youtube 는 v3 백엔드가 import 재사용.
    rss.py youtube.py  #   (reconcile.py·store.py·main.py 는 v1 break-glass 전용, v3 무의존)
    config.py reconcile.py store.py main.py
  backend/             # v3 Cloud Run 서비스
    app.py             # /tick(Scheduler) /wake(Cloud Tasks) /healthz
    handlers.py        # tick/wake 오케스트레이션 — preview.json 1파일 커밋 + LLM 번역 sweep
    preview.py         # (신규) preview.json 스키마 헬퍼 (id·매칭·정렬·승격·아카이브) — 순수
    preview_build.py   # (신규) reconcile 포크 → build_preview(6상태 + FSM 파생 + ytnotif 머지) — 순수
    statemachine.py    # (v3 재작성) derive(item, now) → 상태 전이·다음 wake 시각. 저장 타이머 없음 — 순수
    llm.py             # (신규) Groq 클라이언트 — notice_title / translate, 백오프·환각가드 — 순수 로직
    ytnotif.py         # (신규) YouTube 앱 푸시알림 payload 파서 (TUNEIN/REMINDER/SUB_START) — 순수
    vxtwitter.py       # (신규) api.vxtwitter.com unfurl — 본문·미디어·YT video_id 추출
    gh_store.py        # GitHub Contents API read/write (낙관적 동시성, ConflictError)
    tasks.py           # Cloud Tasks enqueue (OIDC 타깃, 720h 클램프)
    oidc.py            # Scheduler/Tasks OIDC bearer 검증
    config.py          # 환경변수 → Config
    notify.py          # Telegram sendMessage + diff_events(6상태 전이) + allows(레벨 게이팅)
    control.py         # control.json 스키마 (paused / log_level)
    admin.py           # admin_state.json 스키마 — v3 pending_op / edit_lock / suppress + v2 호환 슬롯
    telegram_app.py    # 공개 webhook — {cmd}×{contents} 격자 + POST /ingest (X 릴레이)
    xrelay.py          # @BDP 일일 스케줄 트윗 파서 → announced 아이템 (merge_announced) — 순수
    xnotice.py         # 방송 외 이벤트 트윗 → notices 항목 파서 (+ body_for_llm) — 순수
    notices.py         # notices.json 계약 + 중복판정(url∥title)·머지·sweep·edit — 순수
    xtweet.py          # 개인 5인 트윗 — route_by_title / parse / merge_tweet / parse_schedule
                       #   / merge_personal_schedule / apply_overrides. 리트윗(^@handle:) 필터 — 순수
Dockerfile             # python:3.12-slim + gunicorn. 두 서비스가 이 이미지 공유(엔트리포인트만 다름)
deploy/                # gcloud 배포 스크립트. env.sh 는 루트 .env 매핑(gitignore)
config/channels.json   # 5채널 단일 소스 (channel_order, channel_id, handle, name, name_ko, x_names)
data 브랜치             # preview.json + preview_archive.json + control.json + admin_state.json
                       #   + notices.json / notice_archive.json + tweets.json / tweet_archive.json
                       #   + ingest_queue.json (ECHO/DRY-RUN 버퍼). 코드 없음.
                       #   ※ v2 의 schedule.json / archive.json / pending.json 은 폐지.
```

- 파이썬 3.12. 시각은 전부 UTC ISO(`Z`) 저장, KST 변환은 프론트 `time.js` 전담.
- v2→v3 핵심 변화: `schedule.json`→`preview.json`(6상태), `pending.json` 폐지(FSM 파생),
  `reconcile.build_schedule`→`preview_build.build_preview`, 외부 LLM(번역) 도입.

---

## 1. 계약 A — `preview.json` 스키마 (data 브랜치 루트)

`schedule.json` 대체. 프론트가 `raw.githubusercontent.com` 에서 직접 fetch.
`none` 상태 = 파일에 없음(삭제). 상세 배경: `docs/plan/v3_backend_surgery.md` "v3 데이터 스키마".

```jsonc
{
  "generated_at": "2026-09-09T12:00:00Z",       // ISO UTC 'Z'. 매 tick/wake 실행시각
  "channel_order": ["arale","yuno","nonoka","ritsu","miyako"],
  "channels": {
    "arale": { "name","name_ko","channel_id","handle","channel_url","avatar" }
    // channel_url = https://www.youtube.com/@{handle} (코드 파생). avatar 는 baseline 스캔이 취득
  },
  "items": [
    {
      "id": "pv_a1b2c3d4",                  // "pv_" + sha1(f"{channel_key}|{first_seen}")[:8]. 생애주기 내내 고정
      "state": "watching",                  // announced | upcoming | watching | live | end
      "state_since": "2026-09-09T11:57:00Z",// 현재 state 진입 시각 (end 30분창·강등 판정 앵커)

      "channel_key": "ritsu",               // 주 레인
      "collab_with": null,                  // 합동이면 참여 channel_key 배열(주 레인 제외). 렌더가 union 레인 팬아웃
      "host": null,                         // "group" = 5인 전원 합동(出演情報 텍스트 또는 그룹 채널 API 감지) → supersede 면제
      "kind": null,                         // "collab" | 카테고리(game/song/talk/…) | null
      "membership": false,                  // true = 회원전용. watching 스킵, 시작 신호→live 직행, API 확인 안 함

      "title": "【チラズアート】…",           // JP 원문. announced 단계엔 null 가능. 번역 안 함(번역은 notice/tweet 만)
      "url": "https://www.youtube.com/watch?v=bgzve7Y7S50",   // 없으면 채널 URL
      "video_id": "bgzve7Y7S50",            // null 가능 (announced / 회원전용)
      "thumbnail": "https://i.ytimg.com/vi/bgzve7Y7S50/mqdefault.jpg",  // video_id 유래 or vxtwitter 미디어. null 가능

      "scheduled_start": "2026-09-09T12:00:00Z",  // JST→UTC. 파싱 실패 null. time_tbd 면 "<date>T00:00:00Z"
      "time_tbd": false,                    // true = 날짜만, 시각 미정
      "actual_start": null,                 // live 확정 시각. live-cadence(60분 분기) 앵커
      "concurrent_viewers": null,           // live 한정. 변동 필드 → 커밋 diff 트리거에서 제외

      "source": "personal",                // x-relay | personal | yt-notif | api | manual
      "info_source": "personal",           // 마지막으로 타이밍/정보를 갱신한 신호 종류
      "info_at": "2026-09-08T09:00:00Z",   // 그 신호 시각(트윗 snowflake 유래 등)
      "api_start_seen": null,              // 마지막 API scheduled_start. 이 값이 바뀌면(스트림 실수정) 트윗값 대신 API 승

      "assumed_live": false,               // video_id 없이 scheduled_start 지남 → 프론트 "방송 중(추정)"
      "first_seen": "2026-09-08T09:00:00Z",
      "last_updated": "2026-09-09T11:57:00Z",
      "expires_at": "2026-09-09T15:00:00Z" // 하드 TTL 안전망. 공개 start+3h / membership +5h / time_tbd 예정일의 다음 JST 자정
    }
  ]
}
```

규칙:
- **정렬** (`preview.sort_items`): state 우선순위(`live` > `watching` > `upcoming` > `announced`) →
  `scheduled_start` asc(null 뒤) → `id`. `end` 는 우선순위 밖(뒤).
- 파일 없을 때 기본형(`preview.default_preview`): `{"generated_at": null, "channel_order": [], "channels": {}, "items": []}`.
  프론트는 `channel_order`/`channels` 가 비면 `config.js` 폴백을 쓴다.
- `generated_at` heartbeat: 실질 변화가 없어도 `_HEARTBEAT_MIN_SEC`(20분) 간격으로 전진 커밋
  (`handlers._heartbeat_generated_at` + `_stable_view` 로 volatile 필드 `last_updated`/`concurrent_viewers` 동결).

### 1-1. 아이템 매칭 (`preview.match_item`)

같은 `channel_key` + (`video_id` 일치 ∥ `url` 일치 ∥ `scheduled_start` ±4h(`superscede_sec`)).
매칭되면 같은 `id` 유지·필드 갱신. 안 되면 새 `id`. `none` 으로 사라진 뒤 오는 예고는 무조건 새 아이템.

### 1-2. 상태 승격 (`preview.promote_state`)

`upcoming` = `scheduled_start` && !`time_tbd` && `title` && `thumbnail` && `url` && `video_id` 전부.
아니면 `announced`. 승격 판정은 `preview_build` 가 매 tick 수행 (FSM 은 승격을 되돌리지 않음 — 지각 강등만).

### 1-3. 합동방송 (collab)

`xrelay`/`xtweet` 가 `collab_with` 채운 `announced` 아이템을 참여 유닛 전부에 fan-out.
url(video_id) 확정 시 일반 방송 추적과 동일 — 상태머신은 레인이 아니라 url 추적. `preview_build` 가
참여자(`channel_key` ∪ `collab_with`) 중 아무 채널에나 실물 ±4h 안에 뜨면 supersede 하고
`_carry_collab` 로 실물 행에 `collab_with` + `kind="collab"` 이관. `host=="group"` 은 supersede 면제.
프론트 `render.js` 가 union 레인에 `.card--collab` 팬아웃. 상세: `docs/old/v2/v2_4_collab.md` §8.

### 1-3-1. 그룹 공식 채널(`@BDP_yumemita`) 폴링 — v3.1.4

`config/channels.json` `channels.group`(channel_order 밖, 전용 레인 없음)은 5인 합동 전용
공식 채널. RSS/`videos.list` 로 이 채널에 영상이 뜨면 `preview_build.build_preview` 가
`channel_key=channel_order[0]` + `collab_with=channel_order[1:]` + `host="group"` +
`kind="collab"` 로 즉시 5인 레인에 팬아웃한다(`GROUP_CHANNEL_KEY`). `出演情報` 텍스트 유래
`host="group"` 과 동일하게 취급되어 supersede 면제. 이 채널은 RSS 폴링 대상일 뿐 —
5개 개인 레인과 달리 자체 카드/레인을 갖지 않는다.

### 1-3-2. 즉시개시 트윗 릴레이 (`xrelay.parse_live_now`) — v3.1.4

일일 스케줄(`配信スケジュール`)도 出演情報도 아닌, "지금 막 시작" 계열 공지
(`配信開始`/`同時視聴配信`/`生配信中` 등 + **온전한** YouTube 영상 URL)를 감지해
`video_id` 를 이미 채운 `announced` 아이템으로 즉시 반영한다. RSS/API 폴링(최대 light tick
3h 간격)을 기다리지 않고 `/ingest` 시점에 바로 preview 에 올라가는 것이 목적 — 그룹 채널
폴링(1-3-1)과 상호보완적 이중 경로(둘 중 먼저 도착하는 쪽이 반영, 이후 `video_id` 매칭으로
합류). 텍스트에 개인 이름이 있으면 그 멤버(+동석자), 없고 그룹 명의(`夢限大みゅーたいぷ`/
`ゆめみた`)만 있으면 5인 전원(`host="group"`). 둘 다 없으면 채널 특정 불가로 무시. 잘린 URL
(`…`)은 `video_id` 를 못 얻으므로 노이즈 방지 차 무시.

---

## 2. 계약 B — `preview_archive.json` 스키마

```jsonc
{
  "generated_at": "2026-09-09T12:00:00Z",
  "items": [ { /* preview 아이템 원본 + "archived_at" */ } ]
}
```

- `end→none` 또는 removed/expired 시 `build_archive_appends` 가 append. `(video_id, id)` 로 dedupe.
- 프론트는 안 읽음 — 디버그 + 회원전용 사후확정(RSS 로 뒤늦게 뜨는 아카이브)용.

---

## 3. 계약 C — 프론트 DOM 구조

`render.js` 가 생성하고 `css/` 가 스타일링. class 이름 변경은 이 문서 수정 후에만.
`#board` 골격(`<section class="lane">` × `channel_order`, `lane__header`/`lane__live`/`lane__buckets`)은
v2 와 동일 — `docs/old/v2/IMPLEMENTATION_v2.md` §3 참조. v3 변경분:

### 레인 헤더 (`lane__header`) — v3.0.2

`<a class="lane__link">`(아바타 `lane__avatar` + `lane__meta`) **+** `<nav class="lane__nav">`
(우측 세로 레일: `lane__nav-btn lane__nav-yt` = `channel_url`, `lane__nav-btn lane__nav-x` =
`https://x.com/<handle>`). 헤더는 `display:flex` (tweets.css 가 layout.css override).
아바타는 트윗 있으면 `tweets.js` 가 말풍선 토글로 가로채고, 없으면 `.lane__link` 대로 YouTube.
이름 글자·레일은 항상 채널 이동. SVG 아이콘은 `render.js svgIcon()`(`createElementNS`).

### 카드 클래스 매핑 (state → class)

| state | 최상위 class | 썸네일 자리 | `.card__rel` |
|---|---|---|---|
| `announced` | `card card--announced` | 아이콘 `📺` (`card__icon`) | `relativeLabel`, 배지 "예고"(`card__badge--announced`), href = 채널 URL |
| `upcoming` | `card card--upcoming` | 썸네일 `<img>` | `relativeLabel` (+ `card__rel--late` 토글) |
| `watching` | `card card--watching` | 썸네일 `<img>` | `relativeLabel` (+late), 배지 "대기 중"(`card__badge--watching`) |
| `live` | `card card--live` | 썸네일 + `LIVE` 배지 | `elapsedLabel(actual_start)` = `"방송 중 (n분)"` |
| `end` | `card card--end` | 썸네일 유지, 배지 없음 | `"방송 종료"`. 빨강 테두리 없음(OFF-AIR 소등) |

- `membership` true → `card--membership` 추가. 썸네일 자리 자물쇠 `🔒`(`card__icon`), body 에 `card__chip` "🔒 회원 전용 방송".
- `assumed_live` && state ∈ (announced, upcoming) → `card--sched-live` 추가, `.card__rel` = `"방송 중 (추정)"`(빨강), 테두리 실선.
- `kind=="collab"` (또는 `collab_with` 존재) → `card--collab` 추가, 배지 "합동"(`card__badge--collab`), href = `url`.
- `time_tbd` → `<time>` 자리에 `M/D` 만 + `.card__rel` = "시간 미정", 카운트다운 스킵.

### 라이브 존 (`lane__live`)

`buildLive(liveItems, endedItems, …)`: `data-state="on"` 은 **실제 `live` 아이템이 있을 때만**.
`end` 아이템은 존에 남기되 소등(`data-state="off"`). 둘 다 없으면 `<span class="lane__live-off">OFF-AIR</span>`.

### 버킷 분류 (`bucketKey`)

`scheduled_start − now`: `<24h`=`today` / `<7일`=`week` / 그 외·null=`rest`. PC·모바일 동일 3분할
(v3.0.0 까진 PC 만 `<30일`=`month` / 그 외=`later` 4분할이었음). 대상 = state ∈ (announced, upcoming, watching).

### 렌더 규칙

- 전체 재렌더(폴링마다 `#board` 재구성). `updateCountdowns()` 는 DOM 재구성 없이 `.card__rel` 텍스트만
  (`live`→`elapsedLabel`, `end`→고정, 나머지→`relativeLabel`). 구간 넘으면 `true` 반환 → `main.js` 재렌더.
- **XSS**: 데이터는 `textContent`/`createElement` 로만 주입. `render.js` 는 `innerHTML` 금지(`img.onerror` 속성만 예외).
  (`notices.js` 는 v2 부터 티커 marquee 구조상 템플릿+`_attr`/`_esc` 이스케이프 사용 — 새 필드도 이스케이프됨.)

---

## 4. 계약 D — 시간 표기 규칙 (`time.js`)

- 저장 UTC, 표시 **KST(UTC+9)**. `Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul'})`.
- `formatKST(iso, opts={})` → `"MM/DD HH:mm"`. `opts.full===true` → `"YYYY-MM-DD HH:mm"`.
- `relativeLabel(iso, nowMs)`:
  | 조건 (start − now) | 출력 |
  |---|---|
  | < −5분 (지각) | `"{n}분 지각"` / `"{h}시간 {m}분 지각"` (최소 1분) |
  | < 60초 | `"곧 시작"` |
  | 오늘 (같은 KST 날짜) | `"{h}시간 {m}분 후"` (h·m 0 처리) |
  | 7일 이내 (오늘 아님) | `"D-{n} {HH}:{mm}"` — `n` = KST 캘린더 자정 기준 일수차(올림, 최소 1) |
  | 그 외 | `"{YYYY}-{MM}-{DD} {HH}:{mm}"` (KST) |
- `elapsedLabel(actualStartIso, nowMs)` → `"방송 중 ({m}분)"`.
- `isLate(iso, nowMs)`: `scheduled_start` 를 5분(`LATE_GRACE_MS`) 넘게 지났는지 boolean. `render.js` 가 `.card__rel--late` 토글에 사용.
- `.card__rel` 은 `updateCountdowns()` 가 **1분마다 사용자 장치 시계 기준**으로 갱신 (`main.js` `COUNTDOWN_TICK_MS`).

---

## 5. 계약 E — (폐지) `pending.json`

v2 의 `pending.json`(폴링 FSM 상태 저장)은 **삭제**. `src/backend/pending.py` 없음.
FSM 은 `statemachine.derive` 가 `preview.json` 아이템에서 **저장 타이머 없이 파생**:

`derive(item, now_iso, *, live_seen=None, preview_stream_seen=False) -> Tick(next_state, next_check_at, log)`

| 규칙 | 조건 | 결과 |
|---|---|---|
| pre-live 진입 | state ∈ (announced, upcoming) && `now ≥ ss − 3분` | `watching`, check `now+3분` |
| pre-live 예약 | 위인데 아직 3분 전 아님 | state 유지, check `ss − 3분` |
| watching 체크 | state==watching && `now − ss < 120분` && !live_seen | check `now+3분` |
| watching → live | state==watching && `live_seen is True` | `live`, check `now+10분` |
| watching 지각 강등 | state==watching && `now − ss ≥ 120분` | `announced` (url·video_id 살림), check 없음 |
| assumed-live 폴백 | state ∈ (announced,upcoming) && `assumed_live` && no video_id && `now − ss ≥ 90분` | `none` |
| membership 직행 | `membership` && `live_seen is True` | `live` (watching 스킵) |
| live cadence | state==live && `live_seen != False` — `now − actual_start < 60분` → 10분 / 이상 → 3분 | 유지 |
| live → end | state==live && `live_seen is False` (명시적 확인. None=미확인은 유지) | `end`, check `now+5분` |
| end 창 | state==end && `now − state_since < 30분` | check `now+5분` |
| end → none | state==end && `now − state_since ≥ 30분` && 계속 live 아님 | `none` |
| end → upcoming | state==end && `preview_stream_seen` (예고 스트림 재등장) | `upcoming` |

- 상수: `PRELIVE_LEAD_SEC=180`, `PRELIVE_TIGHT_SEC=180`, `WATCH_LATE_DEMOTE_SEC=7200`,
  `ASSUMED_LIVE_MAX_SEC=5400`, `LIVE_EARLY_SEC=600`, `LIVE_EARLY_WINDOW_SEC=3600`, `LIVE_TIGHT_SEC=180`,
  `END_WINDOW_SEC=1800`, `END_TICK_SEC=300`, `MAX_TASK_HORIZON_SEC=696*3600`.
- `next_check_at` 은 반환 직전 `[now+60s, now+MAX_TASK_HORIZON_SEC]` 클램프. **저장 안 함** — `handlers` 가
  video_id 있는 watching/live/end 아이템의 `next_check_at` 만 `wakes` 로 받아 Cloud Tasks `/wake` enqueue.

---

## 6. 계약 F — `control.json` (data 브랜치 루트)

```jsonc
{ "paused": false, "since": null, "by": null, "log_level": "normal", "updated_at": "..." }
```

- 기본형: `{"paused": false, "since": null, "by": null, "log_level": "normal", "updated_at": null}`.
- `control.py` 순수 헬퍼: `default_control()`, `is_paused(c)`, `get_log_level(c)`(이상값→"normal"),
  `set_paused(c, paused, *, by, now_iso)`, `set_log_level(c, level, *, by, now_iso)`. `set_*` 는 다른 필드 보존.
- **log_level 별 전송 이벤트** (`notify.allows(level, kind)`):
  | kind | detail | normal | simple |
  |---|:-:|:-:|:-:|
  | `announced` | ✓ | ✓ | ✗ |
  | `upcoming` / `live_start` / `live_end` | ✓ | ✓ | ✓ |
  | `demote` (watching→announced 지각 강등) | ✓ | ✗ | ✗ |
  | `notice` / `tweet` | ✓ | ✓ | ✗ |
  | `ingest` / `fallback` / `error` / `summary` | ✓ | ✗ | ✗ |
  - 다운 감지(healthchecks.io grace 초과)는 log_level 무관 항상 알림.
  - 운영자가 직접 친 명령의 응답은 게이팅 안 함.

---

## 6-1. 계약 G — `admin_state.json` (data 브랜치 루트)

텔레그램 제어 명령의 상태. `admin.py` 순수 헬퍼.

```jsonc
{
  "pending_op": null | {           // (v3) /edit·/ingest tweet 마법사 — cmd×contents×step
    "cmd": "edit", "contents": "preview", "step": "await_field",
    "ctx": { "unit","id","idx","patch","pre",... }, "at": "..."   // TTL 60s
  },
  "edit_lock": null | { "id": "pv_ab12cd34", "until": "..." },     // 아이템 단위 편집 락 (TTL 60s)
  "suppress": [ { "url": "...", "until": "..." } ],                // /del terminate — url 12h 재진입 차단
  "undo": null | {
    "cmd": "...", "contents": "...", "action": "/del arale#2",
    "path": "preview.json",         // preview.json | notices.json | tweets.json
    "prev_content": { /* 그 파일 전체(변경 직전) */ }, "new_sha": "...", "at": "..."
  },
  "pending_undo": null | { "at": "...", "target_sha": "...", "action": "..." },  // /undo (y/N) TTL 60s
  // v2 호환 슬롯 (텔레그램 되묻기 플로우 — /notice-edit, /ingest·/notice·/del 무인자, 유닛 되묻기)
  "pending_del": null | { "unit","idx","snapshot","warn_text","at" },     // TTL 300s
  "pending_ingest": null | { "at" },                                      // TTL 180s
  "pending_notice": null | { "at" },                                      // TTL 180s
  "pending_notice_edit": null | { "nid","step","new","at" },              // TTL 300s
  "pending_member": null | { "raw","at" }                                 // TTL 300s
}
```

- `set_*`/`clear_*` 는 원본 복사 후 해당 슬롯만 갱신(타 슬롯 보존).
- **취소 토큰** `aNoneTokyo` — 전 되묻기 단계 공통.
- **edit_lock 반영**: `handlers._run` 이 커밋 직전 `admin.suppressed(url)`(차단 url 아이템 제외) +
  `admin.edit_lock_active(id)`(락 걸린 id 는 prev 값 유지 — 이번 사이클 갱신 스킵)를 적용.
- **쓰기 경합**: preview/notices/tweets 를 쓰는 모든 경로(봇 명령, 메인 `/tick`·`/wake`)는
  CAS(`prev_sha`) + 1회 재계산 재시도로 직렬화. 크로스 서비스 분산 락 없음.

---

## 6-2. 계약 H — `notices.json` / `notice_archive.json` (data 브랜치)

방송 외 이벤트(라이브 예고·음반/굿즈·타 플랫폼·기타) 티커. `notices.py`.

- `notices.json` = `{ generated_at, notices[] }`. 항목: `id`·`category(live|release|platform|etc)`·
  `title`·`title_ko`·`title_raw`·`body_raw`·`body_for_llm`·`date`·`time`·`deadline`·`site`·`url`·
  `tweet_url`·`src_handle`·`needs_tl?`·`seen_ids[]`·`first_seen`·`last_updated`·`expires_at`. 정렬 date→time→id.
  `title_raw`(정규식 제목)·`body_raw`(원문, 600자 컷)는 파싱·번역 품질 개선용 기록 — 프론트 안 읽음, 아카이브까지 이관.
- **중복 판정** (`_same_group`): `url` 일치 OR `title` 일치(공백 정규화). v2 의 `date + anchor_a/b` 대체.
- `notice_archive.json` = `{ notices[] }` (항목 + `archived_at`, append-only, `id` dedupe).
- `xnotice.parse(text, now_iso, *, tag, title)` — 날짜·시각 둘 다 없으면 / `配信スケジュール`·`出演情報` 면 `None`.
  분류·날짜·URL 은 정규식 전담. `title`/`title_raw` 는 정규식 헤드라인, `title_ko`=None.
- **자동 인입 시 LLM 제목추출·번역** (v3.1.2): `_apply_notice` 가 병합 직후 `llm.notice_title(body_for_llm)` 을
  1회 호출해 `title`(정제된 일본어)·`title_ko` 채움. 실패하면 `needs_tl=true` → 다음 `/tick` 의
  `_translate_sweep` 가 재시도. 운영자 `/translate notice` 는 즉시. (트윗 v3.0.1 인라인 번역과 동일 구조)
- `notices.merge_notice(prev, inc, now_iso, *, archive)` → `(new_notices, new_archive, changed, mode∈added|updated|recap|dup|skip)`.
  지난 날짜의 신규 소식은 `skip`. `sweep_expired` → 만료분 아카이브. `edit_notice(prev, nid, patch, now_iso)` — `_EDITABLE`(+`title_ko`) 만 대입.

---

## 6-3. 계약 I — `tweets.json` / `tweet_archive.json` (data 브랜치)

멤버 5인의 **개인 트윗** — 예고판 상단 편지 배지. `xtweet.py`.

- `tweets.json` = `{ generated_at, tweets: { "<channel_key>": [ { channel_key, id, text, text_ko,
  url, handle, received_at, expires_at, needs_tl? }, … ] } }`. **채널당 스레드 = 메시지 배열, 최신이 뒤,
  최대 `xtweet.MAX_THREAD`(=5)건** (v3.1). v2.8 단건 dict 는 `_as_list` 가 `[dict]` 로 감싸 하위호환.
  `id` = 트윗 Snowflake 또는 합성 `"p"+sha1[:15]`. `expires_at` = `received_at` + 24h (메시지별).
- `tweet_archive.json` = `{ tweets[] }` (항목 + `archived_at` + `archived_reason∈expired|rolled`).
  `rolled` = 스레드 5건 초과로 밀려난 것.
- `xtweet.route_by_title(title, channels_cfg, *, test_titles)` → `"official"` | `"<channel_key>"` | `"test"`
  (`config/channels.json` 의 `x_names[]` 매칭).
- `xtweet.parse(text, *, title, tag, channel_key, now_iso, handle)` → 트윗 dict / `None`.
  **리트윗/타인글 필터**: 본문이 `^\s*(?:RT\s+)?@[\w]+\s*[:：]` 로 시작하면 `None`.
  본인 글은 예고 여부와 무관하게 스레드에 실린다(예고는 preview 로도 승격 — 이중 노출 유지).
- `xtweet.merge_thread(prev, inc, now_iso, *, archive)` → `(new_tweets, new_archive, changed, mode∈added|rolled|dup|stale)`
  — id 중복이면 `dup`, 아니면 append 후 `received_at`↑ 정렬, 5건 초과분을 오래된 것부터 아카이브(`rolled`).
  `merge_tweet` 은 하위호환 별칭. `sweep_expired` → **메시지별** 만료 아카이브, 스레드 비면 키 제거.
- **번역**: `text_ko`. `handlers` 가 파이프라인 말단에서 자동 번역, 실패 시 `needs_tl=true` 플래그 →
  다음 `/tick` `_translate_sweep` 이 재시도. 운영자 `/translate tweet` 는 즉시.
- **개인 예고 → preview 승격**: `xtweet.parse_schedule`(`配信` 계열 + 날짜/URL 게이트) →
  `merge_personal_schedule(prev_items, inc, now_iso) -> (items, changed)` (같은 방송 upsert, `source:"personal"`).
  `apply_overrides(new_items, prev_items, now_iso)` — 트윗이 정한 `scheduled_start` 를 API 재구성이
  안 덮게 (API 값이 `api_start_seen` 과 ±60초면 트윗값 유지, 벗어나면 API 승). `handlers.tick` 이 `build_preview` 직후 호출.

---

## 7. 직렬화 / 시간 규칙 (전 모듈 공통)

- JSON 저장: `json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"` (끝 개행 1개).
  `gh_store._serialize` / `store.save_json_if_changed` 동일. 어기면 불필요한 커밋 발생.
- ISO 파싱: `datetime.fromisoformat(s.replace("Z", "+00:00"))`, 항상 tz-aware UTC.
- ISO 출력: `dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.
- 시각 비교·산술은 전부 UTC. KST 변환은 프론트 `time.js` 전담.

---

## 8. 백엔드 모듈 (`src/backend/`)

### 8.0 재사용 (`src/collector/` — 수정 금지, import)

- `rss.py` — `fetch_rss_video_ids`, `fetch_all_rss_video_ids` (쿼터 0).
- `youtube.py` — `VideoInfo`(dataclass: `video_id, channel_id, title, thumbnail, live_state, scheduled_start,
  actual_start, actual_end, concurrent_viewers`), `YouTubeClient`(`videos_list` / `search_upcoming` /
  `channels_list`, `quota_used` 카운터).
- `config.py` — `load_channels()`, `channel_url(handle)`.
- `reconcile.py`/`store.py`/`main.py` — v1 GitHub Actions break-glass 전용. v3 무의존.

### 8.1 `preview.py` (순수 — 네트워크·파일·시계 금지, `now_iso` 인자)

```python
def default_preview() -> dict
def new_id(channel_key, first_seen_iso) -> str                    # "pv_" + sha1[:8]
def make_item(*, channel_key, state, source, now_iso, **fields) -> dict   # 스키마 기본값 + expires_at 계산
def match_item(items, inc, *, superscede_sec=4*3600) -> dict | None       # §1-1
def sort_items(items) -> list                                     # 정렬 규칙
def promote_state(item) -> str                                    # §1-2 → "announced" | "upcoming"
def set_state(item, new_state, now_iso) -> dict                   # 사본 + state/state_since/last_updated
def to_archive_record(item, now_iso) -> dict                      # + archived_at
```

### 8.2 `statemachine.py` (순수) — §5

`Tick(next_state, next_check_at, log)` dataclass + `derive(...)`. FSM 규칙·상수는 §5.

### 8.3 `preview_build.py` (순수)

```python
def build_preview(channels_cfg, videos, prev_preview, now_iso, *, avatars=None, ytnotif_items=None)
    -> (new_preview, transitions: list[str], wakes: dict[video_id→iso], gone_items: list[dict])
def build_archive_appends(prev_archive, gone_items, now_iso) -> (new_archive, changed)
```

`reconcile.build_schedule` 포크. 흐름:
1. **채널 블록** — avatar carry-over (baseline 만 `channels_list`, light 는 이전 값).
2. **videos.list 결과** — video_id 로 prev 아이템 매칭 → 필드 갱신(`info_source` 가 personal/x-relay 면
   `scheduled_start` 는 안 덮고 `api_start_seen` 만 기록). 신규는 `make_item(state="announced")` →
   `promote_state`. `live_state=="live"` → state="live"+actual_start. `"none"` && state=="live" → `end`.
   각 아이템 `statemachine.derive` 적용 → 전이 로그 + `next_state=="none"` 은 `gone_items` 로.
3. **prev 아이템 중 이번 videos 에 없던 것** —
   · video_id 有: removed 유예(`STALE_REMOVE_SEC` 6.5h). 유예 중 carry + FSM, 경과 시 removed.
   · video_id 無 (announced 자리표시): 참여자 채널에 실물 ±4h → supersede + `_carry_collab`.
     `expires_at` 도달 / `first_seen`+18h(시각 없음) → gone. 아니면 FSM(assumed-live·지각강등).
4. **ytnotif 머지** — video_id 로 `items` 직접 스캔(ytnotif 는 channel_key 없음). `reminder`/`sub_start` →
   매칭 아이템 live 승격, `tunein` → scheduled_start 보강. 미매칭+채널미상은 skip
   (다음 tick 이 videos.list 후보로 흡수. 회원전용 자동카드는 `INGEST_YT_ENABLED` 뒤).
5. 정렬 후 반환.

### 8.4 `llm.py`

```python
DEFAULT_MODEL = "openai/gpt-oss-120b"; FALLBACK_MODEL = "llama-3.3-70b-versatile"
class LLMClient(api_key, *, model=DEFAULT_MODEL, fallback=FALLBACK_MODEL, session=None, timeout=20.0):
    def notice_title(body_no_date_url, *, lang_hint="ja") -> {"title_ja","title_ko"} | None
    def translate(text_ja) -> str | None
```

- Groq REST (`https://api.groq.com/openai/v1/chat/completions`). `reasoning_effort="low"`, `temperature=0`.
  `response_format` 모델별 분기(gpt-oss=json_schema, llama-3.3=json_object).
- api_key 비면 disabled → 모든 호출 None. 429/5xx → 지수 백오프 3회 → 폴백 모델 1회 → None.
- 환각 가드: 출력 비었거나 입력 길이 3배 초과 → None (기본선, 배포 후 실측 보강).

### 8.5 `ytnotif.py` (순수)

`parse_yt_notif(nx: dict, now_iso) -> dict | None`. `pde_noti_pkg != com.google.android.youtube` /
`::SUMMARY::` 태그 / slot_key 11자 아님 / 빈 제목 → None. `chime.thread_id` 접두어로 종류 분기 후
제목 필드 선택: `TUNEIN`→`android.text`, `REMINDER`→`android.title`, `SUBSCRIPTION_LIVESTREAM_START`→`android.text`.
제목 앞 `🔴 ` 만 제거(`【…】` 는 유튜브 제목 관용 접두라 보존). `video_id`=slot_key, url/thumbnail 조립.
`scheduled_start`: TUNEIN → `now+30분`+`time_approx=True`, 그 외 → `now`. 반환 dict: `{video_id, url,
thumbnail, title, kind(tunein|reminder|sub_start), scheduled_start, time_approx, source:"yt-notif"}`.

### 8.6 `vxtwitter.py`

`fetch_tweet(tweet_id, *, session=None, timeout=8.0, base=cfg.vxtwitter_base) -> dict | None`
(`GET {base}/i/status/{id}`. 비200·타임아웃·JSON 오류 → None + warning).
`extract(j) -> {text, media: [url...], urls: [expanded...], yt_video_id: str|None}` —
`youtube.com/(watch\?v=|live/)` · `youtu.be/` 뒤 11자 추출. 서드파티 무료 서비스 → 실패 시 조용히 skip.

### 8.7 `gh_store.py` — GitHub Contents API

`GitHubStore(token, repo, branch="data", *, session=None, timeout=15.0)`. `read_json(path) -> (data|None, sha|None)`.
`write_json(path, data, *, prev_sha, message) -> (bool, sha|None)` — 현재 원격 재조회해 내용 동일이면 PUT 안 함;
`prev_sha` 와 현재 sha 다르면 `ConflictError`(다른 내용 커밋됨). 409/422 → `ConflictError`. 네트워크만 재시도.

### 8.8 `tasks.py` + `oidc.py`

`TaskQueue(*, project, location, queue, target_url, invoker_sa)` — `enqueue_wake(video_id, iso)` (path `/wake`),
`enqueue_tick(mode, iso)` (path `/tick`). 태스크 이름의 분버킷(epoch//60)으로 dedupe(`AlreadyExists` 무시).
`oidc.verify_request(headers, *, expected_audience, expected_sa=None)` — Bearer JWT 검증. `ALLOW_UNAUTH=="1"` 이면 통과.

### 8.9 `handlers.py` — `tick(mode)` / `wake(video_id)`

`_run(mode, woken_video_id)` 흐름:
1. **control 가드**: `is_paused` 면 healthcheck 핑만 + `{"paused": True}` 반환.
2. `_pv0 = preview.json` 읽기 → 후보 video_id = `_tracked_unresolved_ids(_pv0)`(video_id 있고 state ∈
   announced~end) ∪ woken ∪ (tick 이면) RSS 전부.
3. `YouTubeClient` — `channels_list`(baseline 만), `videos_list(sorted(후보))`.
4. **커밋 루프 (최대 2회, ConflictError 재계산)**:
   a. `prev_preview` / `prev_archive` + sha 재읽기.
   b. `new_preview, transitions, wakes, gone_items = build_preview(cfg, videos, prev_preview, now_iso, avatars=avatars)`.
   c. `admin_state` 읽어 `suppress`/`edit_lock` 반영(차단 url 제외, 락 id prev 유지).
   d. `_stable_view` 동일하면 volatile 동결 + `generated_at` heartbeat(20분).
   e. `build_archive_appends` → `preview_archive.json`(변경 시).
   f. `gh.write_json("preview.json", …, prev_sha=pv_sha)`. `ConflictError` → a 재시도, 2회째 실패 → 예외.
5. **Cloud Tasks**: `wakes` → `enqueue_wake`. `transitions` 에 `"→end"` 있으면 `enqueue_tick("light", now+20분)`.
   video_id 없는 announced 예고 시각(지금~+3h) → `_scheduled_wake_times` → `enqueue_tick("light", ss)`.
6. **LLM 번역 sweep** (tick 만): `_translate_sweep` — `notices.json`/`tweets.json` 의 `needs_tl` 행 재번역.
7. **Telegram diff**: `notify.diff_events(_pv0.items, new_preview.items, transitions, channels, now)` →
   레벨 게이팅 후 개별 전송 + `summary`(detail).
8. 성공 끝 healthcheck GET. 예외 → `notify.error_text` 후 re-raise.

반환 dict: `{mode, woken, candidates, videos, preview_changed, archive_changed, archived,
preview_items, state_counts, wakes, enqueued, enqueue_errors, translated, quota_used, log}`.

### 8.10 `notify.py`

```python
class Telegram(token, chat_id, *, session=None, timeout=10.0)   # 비면 disabled
@dataclass
class Event: kind; channel_ko; title; text   # kind: announced|upcoming|live_start|live_end|demote
def diff_events(prev_items, new_items, transitions, channels_cfg, now_iso) -> list[Event]
def allows(level, kind) -> bool                                  # §6 표
def summary_text(result, now_iso) -> str                        # D(요약)
def error_text(where, exc) -> str
```

`diff_events` 순수. 첫실행 가드: `prev_items` None/빈 리스트면 `announced` 이벤트 생성 안 함. `id`(또는
video_id)로 인덱싱. `announced`(new 등장) / `upcoming`(announced→upcoming) / `live_start`(*→live,
lateness=actual_start−scheduled_start) / `live_end`(live→end) / `demote`(`transitions` 에 `watching-demote` 토큰).

### 8.11 `telegram_app.py` — 공개 webhook 서비스

Flask. 엔트리포인트 `src.backend.telegram_app:app`. `ALLOW_UNAUTH=1`. 라우트 `POST /telegram` · `POST /ingest` · `GET /`.

**`/telegram`**: `X-Telegram-Bot-Api-Secret-Token` + `chat.id` 검증. 항상 **200**, 응답은 `sendMessage` 별도.
followup 소진 순서: del/undo (y/N/terminate) → `_handle_ingest_followup` → `_handle_member_followup` →
`_handle_notice_followup` → `_handle_notice_edit_followup` → `_handle_op_followup`(pending_op) → 명령 디스패치.

**{cmd}×{contents} 격자** — `_split_contents(arg)`: 첫 토큰이 `preview|notice|tweet` 면 그것, 아니면
`preview`(+ 전체를 sub-arg. `/list arale` 하위호환).

| 명령 | preview | notice | tweet |
|---|---|---|---|
| `/list <c> [rest]` | 5인 살아있는 아이템(state announced~end) 유닛별 idx | `/notice-list` | 배지 떠 있는 유닛 트윗 |
| `/ingest <c>` | `pending_ingest` 슬롯 → 원문/파일 → `xrelay.parse` → `merge_announced` | `pending_notice` → `xnotice`+`notices.merge_notice` | `pending_op` → 유닛→원문 → `_maybe_personal_tweet` |
| `/edit <c>` | `pending_op` 마법사 (유닛→idx→필드/값 반복→`done`, `edit_lock`, 답한 필드만 patch, tick 충돌 알림) | `/notice-edit` 재사용 (제목→날짜→URL) | 유닛→원문 → `merge_tweet` 교체 |
| `/del <c> …` | `<유닛> <idx>` → 확인 `(terminate/y/N)`. terminate = 삭제 + `add_suppress(url, 12h)` | `/notice-del <id\|번호>` | `<유닛>` → 슬롯 제거 |
| `/undo` | 직전 mutating 명령 1건(계통 무관 단일 슬롯). 2단계 확인 + sha 2중 가드. `undo.path` 로 3파일 복원 |
| `/translate <notice\|tweet>` | 미번역 행 전부 `*_ko` 채움(원문 보존). `GROQ_API_KEY` 필요. 수동 명령 — 자동 sweep 과 별개 |

일반: `/status`(v3 양식 — preview 6상태 카운트·notice·tweet·마지막 sync·LLM 큐=`needs_tl` 행 수) ·
`/pause` · `/resume`(paused=false + 메인 `/tick` OIDC 호출) · `/log [detail|normal|simple]`.
별칭 유지: `/notice` `/notice-list`(`/notices`) `/notice-del`(`/ndel`) `/notice-edit`(`/nedit`) `/add`.

**`/ingest`** (X 릴레이): `X-Ingest-Secret` 헤더. 본문 form/JSON `text`(필수)/`title`/`template`/`tag`.
`xtweet.route_by_title(title)` → 개인 5인이면 `_maybe_personal_tweet`(→ `tweets.json` + 예고면 preview
승격) 후 즉시 200. 테스트 부계정(`INGEST_TEST_TITLES`, 기본 `jehy`)은 `force_echo`. 공식·미매칭은
`_maybe_auto_notice` → `xrelay.parse` → `merge_announced` → `preview.json`. `INGEST_ECHO`/`INGEST_DRY_RUN`
이면 저장 안 하고 회신 + 스케줄 트윗은 `ingest_queue.json` 버퍼(실배포 전환 시 첫 `/ingest` 에서 drain).

### 8.12 `config.py`

`load_config()` — `ALLOW_UNAUTH != "1"` 이면 `_REQUIRED`(GITHUB_TOKEN, GITHUB_REPO, YOUTUBE_API_KEY,
GCP_PROJECT, GCP_LOCATION, TASKS_QUEUE, SERVICE_URL, INVOKER_SA) 필수. 선택:
`DATA_BRANCH`(기본 "data"), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`,
`HEALTHCHECK_URL`, `MAIN_SERVICE_URL`, `INGEST_SECRET`, `INGEST_ECHO`, `INGEST_DRY_RUN`,
`INGEST_TEST_TITLES`, **`GROQ_API_KEY`**, **`GROQ_MODEL`**(기본 `openai/gpt-oss-120b`),
**`GROQ_MODEL_FALLBACK`**(기본 `llama-3.3-70b-versatile`), **`VXTWITTER_BASE`**(기본
`https://api.vxtwitter.com`), **`INGEST_YT_ENABLED`**(기본 `""` — `"1"` 이어야 ytnotif 라우팅).

### 8.13 `app.py` (비공개, OIDC)

`@app.post("/tick")` → `oidc.verify_request` → `handlers.tick(mode="light" 기본)`.
`@app.post("/wake")` → video_id 필수(없으면 400) → `handlers.wake(vid)`. `@app.get("/","/healthz")` → "ok".
예외 → 500 + `notify.error_text` DM. `PermissionError` → 403.

---

## 9. 프론트엔드 모듈 (`src/frontend/`)

- **index.html**: `<head>` 에 `<meta name="color-scheme" content="dark">` + 5개 css +
  `<script type="module" src="js/main.js">`. body 는 `#notice` + `#board` + `#foot`.
- **다크 전용 테마.** `reset.css :root { color-scheme: dark }` + 위 메타로 브라우저 자동
  어둡게(삼성 인터넷·Chrome Android force-dark)를 끈다 — 선언이 없으면 기기 다크 모드에서
  투명 섞기 색(헤더 그라데이션·트윗 말풍선)이 이중 처리돼 뭉개진다. 라이트/다크 분기 CSS 없음.
- **css/**: `reset` · `layout`(`#board` ≥1100px `grid-template-columns:repeat(5,1fr)`, <1100px 가로 스크롤) ·
  `card`(6상태 클래스 §3, mobile @media 파일 끝) · `notices` · `tweets`.
- **js/config.js** — `PREVIEW_URL`(raw githubusercontent data/preview.json), `NOTICES_URL`, `TWEETS_URL`,
  `POLL_MS=75000`, `COUNTDOWN_TICK_MS=60000`, `FETCH_TIMEOUT_MS=8000`, `FALLBACK_CHANNEL_ORDER`, `FALLBACK_CHANNELS`.
- **js/time.js** — 계약 D. 순수, DOM 접근 없음. selfcheck: `time.selfcheck.mjs`.
- **js/api.js** — `fetchPreview(url)`: AbortController + `FETCH_TIMEOUT_MS`, `cache:"no-store"`. `{ok,data|error}`.
- **js/render.js** — `renderBoard(boardEl, preview, nowMs)` (계약 C 전체 재구성. 알 수 없는 channel_key 무시),
  `renderFooter`, `updateCountdowns`. selfcheck: `render.selfcheck.mjs`(순수 헬퍼 `bucketOf`/`laneKeys`).
- **js/main.js** — `poll()` → `fetchPreview(PREVIEW_URL)` → 성공 시 `renderBoard`+`renderFooter`, 실패 시
  마지막 데이터 유지 + `{stale:true}`. + `pollNotices` + `pollTweets` + 카운트다운 틱.
- **js/notices.js** + **css/notices.css** — `NOTICES_URL` 75초 폴링 → `#notice` 티커. `title_ko` 있으면
  제목을 `[번역]　—　[원문]` 순으로 한 줄에 이어 marquee(길이 넘칠 때 순환). 없으면 원문만.
- **js/tweets.js** + **css/tweets.css** — `TWEETS_URL` 75초 폴링. 유닛 아바타 편지 배지(안 읽은 메시지
  2건+ 이면 카운트 pill). 배지 클릭/호버 → **메신저형 스레드**: PC `.lane__bubble` 패널 / 모바일
  `.tw-toast` 시트에 최근 최대 5개 메시지를 최신이 아래로 스택, ~2분 내 연속은 시각 1개로 묶음
  (`.lane__thread__grp`/`__msg`/`__t`), 열면 맨 아래로 스크롤 + 표시분 전부 읽음. `한/日` 토글은
  헤더에 1개(전역 `mew:tllang`), 원문(X) 링크는 메시지별(`.ori`). 만료·404 면 안 뜸.

---

## 10. Telegram 모니터링·제어 — 결정 사항

- **인바운드는 별도 공개 서비스** `mewtype-telegram`(같은 이미지, 다른 엔트리포인트). 인증 =
  `X-Telegram-Bot-Api-Secret-Token` + `chat.id` 허용목록. 아웃바운드 알림은 메인이 직접.
- **pause = 완전 중단 + resume 시 full heal**: `/resume` 이 `paused=false` 쓰고 곧바로 메인 `tick("light")` 1회.
- **tick 요약(D)은 변경 있을 때만**. `announced/upcoming/live_start/live_end/demote` 는 항상 개별 전송(레벨 게이팅).
- **다운 감지 = healthchecks.io**: 메인 `/tick` 성공 끝에 `HEALTHCHECK_URL` GET. grace 초과 시 알림.
- 메시지 포맷은 한국어 HTML parse_mode. 명령 상세: `docs/plan/v3_telegram_controller.md`.

---

## 11. 사각지대 보정

방송 패턴 실측(`ref/broadcast-patterns.md`)으로 드러난 케이스. 상세: `docs/SCHEDULE.md`.

| # | 사각지대 | 보정 | 위치 |
|---|---|---|---|
| 1 | tick/wake 동시 실행 시 낡은 payload 로 덮어써 전이 유실 | `ConflictError` + 1회 재계산 재시도 | `gh_store.py`, `handlers.py` |
| 2 | `videos.list` 일시 누락·"공개→회원전용" 전환을 즉시 removed 처리 | `last_updated` 기준 `STALE_REMOVE_SEC`(6.5h) 유예 | `preview_build.py` |
| 3 | 방송 종료 직후 시작하는 짧은 다음 방송을 3h tick 간격에 놓침 | `→end` 전이 시 `now+20분` 후속 `light` tick 1개(분버킷 dedupe) | `handlers.py` |
| 4 | video_id 못 얻은 채 예정 시각 지난 announced/upcoming | `assumed_live` + `now − ss ≥ 90분` → `none` (FSM) | `statemachine.py` |

**커버 못 하는 것**: 회원 전용 방송은 RSS·`search.list` 에 안 떠서 발견 불가 — `INGEST_YT_ENABLED` +
업스트림 YouTube 알림 중계가 유일한 경로(트리거 조건 미충족 — `docs/plan/v3_draft.md`).

---

## 12. 인프라 / 배포

`requirements.txt`: `requests>=2.31`, `flask>=3.0`, `gunicorn>=21`, `google-cloud-tasks>=2.16`,
`google-auth>=2.28`. (Groq·vxtwitter 는 `requests` 재사용 — 추가 의존 없음.)

`Dockerfile` (레포 루트): `python:3.12-slim` + `pip install -r src/backend/requirements.txt` + `COPY src config`.
`CMD` = `gunicorn ... src.backend.app:app`. `mewtype-telegram` 은 `--command=gunicorn
--args=...,src.backend.telegram_app:app` 로 엔트리포인트만 교체.

`deploy/` (값은 `deploy/env.sh` = 루트 `.env` 매핑, gitignore):
- `setup.sh` — API·SA 2개·IAM·Cloud Tasks 큐·Secret (`YOUTUBE_API_KEY`, `GITHUB_TOKEN`,
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `INGEST_SECRET`, **`GROQ_API_KEY`**). 멱등.
- `deploy.sh` — `gcloud run deploy mewtype-backend --source . --no-allow-unauthenticated --service-account RUNTIME_SA`
  + secrets/env. `GROQ_API_KEY` 는 Secret 이 있을 때만 마운트. 배포 후 `SERVICE_URL` env 재설정.
- `scheduler.sh` — `mewtype-baseline`(`0 6 * * *` Asia/Tokyo) / `mewtype-light`(`0 */3 * * *` Etc/UTC). OIDC.
- `deploy_telegram.sh` — 같은 소스 + telegram 엔트리포인트 + `--allow-unauthenticated --service-account INVOKER_SA`
  `ALLOW_UNAUTH=1`. `GROQ_API_KEY`(조건부) + `INGEST_YT_ENABLED` env.
- `telegram_webhook.sh` — `setWebhook`.

**Cloud Run/Scheduler/Tasks 는 같은 리전**(`asia-northeast1`). OIDC audience = 서비스 `status.url`.
`mewtype-telegram` 은 `INVOKER_SA` 로 실행해야 `/resume` 의 메인 `/tick` 호출이 통과.
`--concurrency=1 --max-instances=1` 로 `data` 브랜치 쓰기 직렬화.

---

## 13. `config/channels.json` 확정본

```json
{
  "channel_order": ["arale", "yuno", "nonoka", "ritsu", "miyako"],
  "channels": {
    "arale":  { "name": "仲町あられ -Nakamachi Arale-",  "name_ko": "나카마치 아라레", "channel_id": "UCWfF0DB6m_t2CE3KcOOOX7g", "handle": "arale_yumemita" },
    "yuno":   { "name": "千石ユノ -Sengoku Yuno-",       "name_ko": "센고쿠 유노",   "channel_id": "UC99kOG6_9RD0mR3OG4EOfxw", "handle": "yuno_yumemita" },
    "nonoka": { "name": "宮永ののか -Miyanaga Nonoka-",   "name_ko": "미야나가 노노카", "channel_id": "UCGeCnpimiSN5rgiKbJzHd3A", "handle": "nonoka_yumemita" },
    "ritsu":  { "name": "峰月律 -Minetsuki Ritsu-",       "name_ko": "미네츠키 리츠",  "channel_id": "UCxc0MrPoACKTFlV24GqX2sg", "handle": "ritsu_yumemita" },
    "miyako": { "name": "藤都子 -Fuji Miyako-",           "name_ko": "후지 미야코",   "channel_id": "UCZXxRYaP7mfuglPnptnBBCA", "handle": "miyako_yumemita" },
    "group":  { "name": "夢限大みゅーたいぷ(グループ公式)", "name_ko": "무겐다이 뮤타입 그룹 공식", "channel_id": "UCxL_Vlnhfo46sN6vPHR_4hA", "handle": "BDP_yumemita", "is_group": true }
  }
}
```

+ 각 채널 `x_names[]` (트윗 표시명 매칭용, `xtweet.route_by_title`). `channel_url` 은
`https://www.youtube.com/@{handle}` 로 코드 파생. **채널 추가/변경은 이 파일 한 곳만.**
`group` 은 `channel_order` 밖 — RSS/`videos.list` 폴링 대상이지만 전용 레인은 없다(§1-3-1).
