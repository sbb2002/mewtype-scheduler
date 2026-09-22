# 구현 명세 (SPEC) — v3.0 (현행 v3.7.1 반영)

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
| 정기 트리거 | **Cloud Scheduler** 3잡 — baseline JST 06:00 / light 10분(v3.6, 구 3h) → `POST /tick`, monitor KST 06:10 → `POST /monitor` (OIDC) |
| 방송별 정밀 wake | **Cloud Tasks** — `POST /wake {video_id}` (OIDC). 720h 상한 → `now+696h` 클램프 롱폴링 |
| 저장 | **GitHub `data` 브랜치** — 2026-09-14 부터 별도 저장소 `sbb2002/mewtype-scheduler-data`(Vercel 비연결). Cloud Run 이 GitHub Contents API(fine-grained PAT, Secret Manager)로 커밋 |
| 프론트 | **Vercel** 정적 호스팅 (빌드 없음). `raw.githubusercontent.com/.../data/preview.json` 75초 폴링 |
| 모니터링·제어 | 공개 서비스 **`mewtype-telegram`**(같은 이미지, 다른 엔트리포인트) — Telegram webhook + `/ingest` |
| 외부 LLM | **Groq**(선택) — notice 제목 추출·의미 중복판정 + notice/개인트윗/방송 제목 번역 + 개인 예고 판정(참여·예고확인). 키 없으면 원문 노출 폴백 |
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
    app.py             # /tick(Scheduler) /wake(Cloud Tasks) /write(제어 채널) /monitor(Scheduler) · `/` 헬스체크
    handlers.py        # tick/wake 오케스트레이션 — preview.json 커밋 + LLM 번역 sweep + 모니터 로그(실행당 최대 1커밋)
    writers.py         # (v3.7) write-queue — /write 잡 kind → telegram_app 커밋 함수 매핑 (§8.14)
    writeclient.py     # (v3.7) 제어 채널 → 백엔드 /write 동기 호출 (OIDC). MAIN_SERVICE_URL 없으면 로컬 디스패치
    monitor_log.py     # (v3.5) monitoring/events-YYYY-MM-DD.jsonl append (log_event / log_events 배치)
    monitor_report.py  # (v3.5) /monitor Ops Timeline HTML 생성
    preview.py         # (신규) preview.json 스키마 헬퍼 (id·매칭·정렬·승격·아카이브) — 순수
    preview_build.py   # (신규) reconcile 포크 → build_preview(6상태 + FSM 파생 + ytnotif 머지) — 순수
    statemachine.py    # (v3 재작성) derive(item, now) → 상태 전이·다음 wake 시각. 저장 타이머 없음 — 순수
    llm.py             # (신규) Groq 클라이언트 — notice_title / translate / participation / announces_own_broadcast
                       #   / duplicate_notice, 백오프·환각가드 — 순수 로직
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
                       #   / merge_personal_schedule / apply_overrides(v3.7.1 handlers 연결). 리트윗(^@handle:) 필터 — 순수
Dockerfile             # python:3.12-slim + gunicorn. 두 서비스가 이 이미지 공유(엔트리포인트만 다름)
deploy/                # gcloud 배포 스크립트. env.sh 는 루트 .env 매핑(gitignore)
config/channels.json   # 5채널 단일 소스 (channel_order, channel_id, handle, name, name_ko, x_names)
data 브랜치             # preview.json + preview_archive.json + control.json + admin_state.json
                       #   + notices.json / notice_archive.json + tweets.json / tweet_archive.json
                       #   + ingest_queue.json (ECHO/DRY-RUN 버퍼)
                       #   + monitoring/events-YYYY-MM-DD.jsonl (이벤트 로그) + monitoring/latest.html
                       #     (/monitor 리포트 — 공개 저장소라 raw URL 로 누구나 열람 가능). 코드 없음.
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

      "title": "【チラズアート】…",           // JP 원문. announced 단계엔 null 가능
      "title_ko": null,                     // (v3.1.13) LLM 번역. 없으면 프론트가 원문만 표시
      "needs_tl": false,                    // (v3.1.13) true → 다음 tick 의 _translate_sweep 재시도 대상.
                                             //   title 이 새로 생기거나 바뀌면(API 재구성 등) title_ko 를 비우고 다시 true 로
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
- `generated_at` heartbeat: 실질 변화가 없어도 전진 커밋. `/tick`(정기)은 `_HEARTBEAT_MIN_SEC`
  (20분) 스로틀, **`/wake`(방송별 정밀 체크)는 스로틀 없이 매번 즉시 now 로 갱신**(v3.1.17 —
  전엔 tick/wake 구분 없이 20분 스로틀이라, live/end 를 몇 분 간격으로 계속 확인 중이어도
  프론트 하단 업데이트 시각이 tick 주기로만 움직이는 것처럼 보였다)
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

일일 스케줄(`配信スケジュール`)도 出演情報도 아닌, "지금 막 시작(한다)" 계열 공지
(`配信開始`/`同時視聴配信`/`生配信`(단독으로도 매치 — "생중계"라는 말 자체가 즉시성을
내포한다고 보고 v3.1.10 부터 `中`/`開始` 같은 접미사 없이도 반응)/`ただいま配信`/
`配信中です` 등 + **온전한** YouTube 영상 URL)를 감지해 `video_id` 를 이미 채운 `announced`
아이템으로 즉시 반영한다. `video_id` 만 있으면 되므로 그 영상이 `config/channels.json`
미등록 채널(예: 외부 굿즈 판매사 채널) 소유여도 무방 — `videos.list(id=...)` 는 채널 제한이
없는 조회라 다음 tick 에서 그대로 enrich 된다(v3.1.10, 실측: 5th Single 리리스 기념
인터넷사인회 생중계가 「리미스타」명의 채널에서 열린 사례). RSS/API 폴링(최대 light tick
3h 간격)을 기다리지 않고 `/ingest` 시점에 바로 preview 에 올라가는 것이 목적 — 그룹 채널
폴링(1-3-1)과 상호보완적 이중 경로(둘 중 먼저 도착하는 쪽이 반영, 이후 `video_id` 매칭으로
합류). 텍스트에 개인 이름이 있으면 그 멤버(+동석자), 없고 그룹 명의(`夢限大みゅーたいぷ`/
`ゆめみた`)만 있으면 5인 전원(`host="group"`). 둘 다 없으면 채널 특정 불가로 무시. 잘린 URL
(`…`)은 `video_id` 를 못 얻으므로 노이즈 방지 차 무시.

`scheduled_start` 는 기본은 ingest 시각(`now_iso`)이지만, 텍스트에 `本日12時〜`/`明日20時〜`
류 상대날짜+시각 표기(`_DAY_TIME_RE` — 당일 `本日`/`今夜`/`まもなく` 등, 익일 `明日`/`明日朝`/
`明晩`/`明朝`/`あす` — `parse_bdp_schedule` 의 `明日` +1일 관례와 동일 어휘 + 시각 +
`〜`/`~`/`～`)가 있으면 그 시각을 우선 사용한다(v3.1.10). 릴레이가 실제 방송 시작 전에(예: 당일 아침) 도착해도
정확한 시각이 찍히게 하기 위함 — `info_source="x-relay"` 아이템은 이후 `videos.list` 의
API 재구성이 `scheduled_start` 를 덮지 않으므로(§1-3-1·v2.8.1 override 규칙), 최초에 잘못
찍히면 자체 교정될 기회가 없다.

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
| `end` | `card card--end` | 썸네일 유지, 배지 "종료"(`card__badge--end`) | `"방송 종료"`. 빨강 테두리 없음(OFF-AIR 소등) |

- `membership` true → `card--membership` 추가. 썸네일 자리 자물쇠 `🔒`(`card__icon`), body 에 `card__chip` "🔒 회원 전용 방송".
- `assumed_live` && state ∈ (announced, upcoming) → `card--sched-live` 추가, `.card__rel` = `"방송 중 (추정)"`(빨강), 테두리 실선.
- `kind=="collab"` (또는 `collab_with` 존재) → `card--collab` 추가, 배지 "합동"(`card__badge--collab`), href = `url`.
  `announced` 는 우측 상단 배지 자리를 "합동"이 대신 차지(예고/합동 상호 배타). `upcoming`/
  `watching`/`live`/`end` 는 그 자리를 상태 배지(LIVE/대기 중)가 이미 쓰므로 좌측 상단에
  별도로 띄운다(`card__badge--corner-left`, v3.1.11) — `card__body`는 title+meta 2줄
  높이로 고정돼 있어, 참여자 라벨을 거기 3번째 줄로 보태면 flexbox 가 전부 짓눌러 글자가
  점처럼 뭉개지는 회귀가 났었다(v3.1.10 배포 직후 발견, body 밖 배지로 수정).
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
| live cadence | state==live && `live_seen != False` — `now − actual_start < 60분` → 10분 / 이상 → 5분(v3.7.1, 구 3분) | 유지 |
| live → end | state==live && `live_seen is False` (명시적 확인. None=미확인은 유지) | `end`, check `now+5분` |
| end 창 | state==end && `now − state_since < 30분` | check `now+5분` |
| end → none | state==end && `now − state_since ≥ 30분` && 계속 live 아님 | `none` |
| end → upcoming | state==end && `preview_stream_seen` (예고 스트림 재등장) | `upcoming` |

- 상수: `PRELIVE_LEAD_SEC=180`, `PRELIVE_TIGHT_SEC=180`, `WATCH_LATE_DEMOTE_SEC=7200`,
  `ASSUMED_LIVE_MAX_SEC=5400`, `LIVE_EARLY_SEC=600`, `LIVE_EARLY_WINDOW_SEC=3600`, `LIVE_TIGHT_SEC=300`(v3.7.1 — 프론트가 읽는 raw CDN 캐시가 `max-age=300` 이라 3분은 화면에 반영 안 됨),
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
  `tweet_url`·`src_handle`·`needs_tl?`·`participants?`·`seen_ids[]`·`first_seen`·`last_updated`·`expires_at`.
  정렬 date→time→id.
  `title_raw`(정규식 제목)·`body_raw`(원문, 600자 컷)는 파싱·번역 품질 개선용 기록 — 프론트 안 읽음, 아카이브까지 이관.
- **`participants`** (v3.2, 선택 필드): 크로스오버 공식 계정(`_CAST_LOOKUP_HANDLES`, 현재
  `bang_dream_on`) 소식만 대상 — 첨부 이미지를 `vision.py`(Groq 비전 OCR, `qwen/qwen3.8-27b`
  주+`qwen/qwen3.6-27b` 폴백)로 읽어 5인 중 출연이 확인된 `channel_key` 배열. `telegram_app
  ._maybe_tag_cast_participants`가 `_apply_notice` 파싱 직후 채운다(tweet id 없음·이미지
  없음·OCR 실패·매칭 없음이면 그냥 비워둠 — 일반 소식으로 정상 표시, 무회귀). 프론트는 아직
  이 필드를 읽지 않음(추후 UI 확장 여지).
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
  url, handle, received_at, expires_at, needs_tl?, media, quote }, … ] } }`. **채널당 스레드 = 메시지
  배열, 최신이 뒤, 저장 안전 상한 `xtweet.MAX_THREAD`(=50, v3.5.3)** — 실제 화면 노출은 프론트
  `tweets.js` 가 메시지별 `expires_at`(24h)이 안 지난 것만 최대 `MAX_THREAD`(=50)건까지 보여줌(v3.7.2 — 그 전엔 12시간 창이 따로 있었음, 아래 참고).
  v2.8 단건 dict 는 `_as_list` 가 `[dict]` 로
  감싸 하위호환. `id` = 트윗 Snowflake 또는 합성 `"p"+sha1[:15]`. `expires_at` = `received_at` + 24h (메시지별).
  `media`(=`[url,...]`, 본인 트윗 첨부 이미지 — 영상·GIF 는 썸네일 이미지 URL, v3.7.4. v3.8.0 부터 화면은 media·quote 의 원문/미디어를 쓰지 않고 `id`·`text_ko`·`quote.text_ko` 와 X 카드로 대체 - 데이터는 유지보수용으로 보존) / `quote`(=`{text,media,text_ko,needs_tl?}` | `null`,
  인용(QRT)한 남의 트윗 — **표시만**, 예고 파싱 등 ingest 대상 아님)는 (v3.4.5) `telegram_app.
  _enrich_personal_media` 가 tweet id 로 vxtwitter 를 재조회해 채운다(실패·미첨부·id 없음 →
  `[]`/`null`, 무회귀). 프론트 `tweets.js`(`_mediaGrid`/`_quoteCard`) 가 말풍선 안에 썸네일/인용카드로
  렌더 — 번역 토글이 한국어면 `quote.text_ko` 를 쓴다. (v3.4.6) `quote.text_ko` 는 `xtweet.
  find_reused_ko(text, tweets_data, archive_data, notices_data)` 로 **같은 원문이 tweets/
  tweet_archive/notices 어디서든 이미 번역된 적 있으면 그 번역을 재사용**하고, 없을 때만
  LLM 을 새로 호출한다(인라인 실패 시 `quote.needs_tl=True` → `handlers._translate_sweep` 가
  같은 순서로 재시도) — 같은 인용 원본이 여러 멤버·트윗에 반복 등장할 때 중복 번역 호출을 줄인다.
- `tweet_archive.json` = `{ tweets[] }` (항목 + `archived_at` + `archived_reason∈expired|rolled`).
  `rolled` = 스레드 `MAX_THREAD`건 초과로 밀려난 것.
- `xtweet.route_by_title(title, channels_cfg, *, test_titles)` → `"official"` | `"<channel_key>"` | `"test"`
  (`config/channels.json` 의 `x_names[]` 매칭).
- `xtweet.parse(text, *, title, tag, channel_key, now_iso, handle)` → 트윗 dict / `None`.
  **리트윗/타인글 필터**: 본문이 `^\s*(?:RT\s+)?@[\w]+\s*[:：]` 로 시작하면 `None`.
  본인 글은 예고 여부와 무관하게 스레드에 실린다(예고는 preview 로도 승격 — 이중 노출 유지).
- `xtweet.merge_thread(prev, inc, now_iso, *, archive)` → `(new_tweets, new_archive, changed, mode∈added|rolled|dup|stale)`
  — id 중복이면 `dup`, 아니면 append 후 `received_at`↑ 정렬, `MAX_THREAD`건 초과분을 오래된 것부터 아카이브(`rolled`).
  `merge_tweet` 은 하위호환 별칭. `sweep_expired` → **메시지별** 만료 아카이브, 스레드 비면 키 제거.
- **번역**: `text_ko`. `handlers` 가 파이프라인 말단에서 자동 번역, 실패 시 `needs_tl=true` 플래그 →
  다음 `/tick` `_translate_sweep` 이 재시도. 운영자 `/translate tweet` 는 즉시.
- **개인 예고 → preview 승격**: `xtweet.parse_schedule`(`配信` 계열 + 날짜/URL 게이트) →
  `merge_personal_schedule(prev_items, inc, now_iso) -> (items, changed)` (같은 방송 upsert, `source:"personal"`).
  날짜가 명시 안 돼 있어도 `今日`류(당일) + `明日`류(`xrelay._TOMORROW_WORD` 재사용, +1일)
  키워드 + 시각이 함께 있으면 그 날짜로 게이트 통과 (v3.4.5 핫픽스 — "明日22:00" 형태가
  날짜 없음으로 걸러지던 것).
  `apply_overrides(new_items, prev_items, now_iso)` — (v3.7.1 재작성·연결) `handlers._run` 이 커밋 루프에서
  `build_preview` 직후(suppress/edit_lock 반영 전) 호출. `build_preview` 는 `info_source ∈ (personal, x-relay)`
  아이템의 `scheduled_start` 를 안 덮고 `api_start_seen` 만 매 tick API 값으로 갱신하므로, 아이템 `b` 와
  이전 아이템 `pb` 를 비교해: `info_source ∉ (personal, x-relay)` · `time_tbd` · 둘 중 하나의
  `api_start_seen` 없음(처음 관측) → 그대로 / `|b.api_start_seen − pb.api_start_seen| ≤ 60초` → 트윗값 유지 /
  60초 초과(스트림 예약 실제 수정) → `scheduled_start = api_start_seen`, `info_source="api"`, `info_at=now`
  (이후 tick 은 API 값으로 계속 갱신). 이 tick 의 wake 예약은 override 전 시각 기준 — 다음 light tick(≤10분)에 재계산.
  (v3.7.1 이전에는 정의만 있고 어디서도 호출되지 않았다.)

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
   채널이 `config/channels.json` 미등록이어도(예: 외부 굿즈 판매사 채널) **이미 추적 중이던
   아이템**(video_id 매칭)이면 enrich 를 계속한다(v3.1.17) — 신규 발견인데 채널 미상인 것만
   스킵. 예전엔 채널 미상이면 무조건 스킵해서, 이미 반영해둔 외부 채널 합동방송이 다음
   tick 에 이 video_id 를 후보로 다시 잡자마자 섹션 2 도 "이미 처리됨"으로 오판해 통째로
   사라지는(archive 도 안 되는) 버그가 있었다(실측: 리미스타 채널 합동 생중계).
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
DEFAULT_MODEL = "openai/gpt-oss-120b"; FALLBACK_MODEL = "openai/gpt-oss-20b"   # llama-3.3-70b-versatile 은 이 계정에서 404
class LLMClient(api_key, *, model=DEFAULT_MODEL, fallback=FALLBACK_MODEL, session=None, timeout=20.0):
    def notice_title(body_no_date_url, *, lang_hint="ja") -> {"title_ja","title_ko"} | None
    def translate(text_ja) -> str | None
    def participation(text_ja, *, member_name) -> bool | None          # (v3.6) 외부 채널 URL 참여판정
    def announces_own_broadcast(text_ja) -> bool | None                # (v3.6) 텍스트 예고 최종확인
    def duplicate_notice(new_text, candidates) -> str | None           # (v3.7) 같은 날짜 소식 의미 중복판정
```

- Groq REST (`https://api.groq.com/openai/v1/chat/completions`). `reasoning_effort="low"`, `temperature=0`.
  구조화 출력이 필요한 호출만 `response_format: json_schema`(strict), `translate` 는 자유 텍스트.
- api_key 비면 disabled → 모든 호출 None. `_call_groq`: 429/5xx·타임아웃(20초) → 1초·2초 대기하며 최대 3회 시도,
  그 외 상태(400 등)는 즉시 None. 메인 실패 시 폴백 모델로 같은 호출. `participation`·`announces_own_broadcast`·
  `duplicate_notice` 는 유효한 JSON 을 받을 때까지 (메인→폴백) 쌍을 최대 5회 반복.
- (v3.7.1) 제어 채널의 `telegram_app._make_llm_client()` 도 기본값을 이 두 상수로 쓴다(환경변수
  `GROQ_MODEL`/`GROQ_MODEL_FALLBACK` 이 있으면 우선). 이전엔 폴백 기본값이 404 모델이었다.
- 환각 가드: 출력 비었거나 입력 길이 3배 초과 → None (기본선, 배포 후 실측 보강).
- **용어집(`GLOSSARY`, v3.1.14)**: 고유명사가 호출마다 다르게 번역되는 문제(실측: 그룹명
  "夢限大みゅーたいぷ"가 "꿈한계대 뮤타입"/"꿈꾸다"/"유메미타" 등으로 매번 달라짐) 대응.
  프롬프트 지시만으론 불충분(실측상 무시하고 의역하는 사례 있음) → `_mask_glossary`가
  입력 중 등록된 원문을 `@@GLOSSARYn@@` 토큰으로 바꿔 LLM 이 못 건드리게 막고,
  `_unmask_glossary`가 응답에서 그 토큰을 고정값으로 복원(`notice_title`은 `title_ja`→원문,
  `title_ko`→고정 한국어역 각각 복원; `translate`는 한국어역만). preview/notice/tweet
  번역 전부 이 경로를 거치므로 용어집 항목은 어디서든 동일하게 고정된다. 현재 등록:
  `{"夢限大みゅーたいぷ": "무겐다이 뮤타입", "バンドリ": "뱅드림"}` (v3.1.15 — "バンドリ"가
  "밴드리"로 오역되던 것 추가 등록). 등록값에 구두점(느낌표 등)은 넣지 않는다 — 원문에
  있으면 번역에도 그대로 남으므로("バンドリ！" → "뱅드림！"/"뱅드림!") 용어 자체만 고정하면
  충분하다. 토큰이 영숫자에 바로 들러붙으면(예: "バンドリ13th") LLM 이 뒤 문장을 통째로
  미번역으로 남기는 사례가 있어 그 경우만 공백을 끼워 넣는다.

**(v3.1.8) `translate()` 반복 압축** — 짧은 단위(1~6자)가 8회 이상 연속 반복되는 입력
(`_REPEAT_RE`, 예: "もぐもぐもぐ…" 의성어)은 그대로 보내면 LLM 이 반복 루프에 빠져 수백~
수천자를 토해내고 환각 가드에 매번 걸린다(`temperature=0`이라 재시도해도 항상 같은 실패
반복 — 버그리포트 20260913 #3). `_translate_repeated`가 반복을 감지하면 단위를
`_translate_repeat_unit(unit, count)`로 번역(맨입으로 넘기면 문맥 없어 오역되기 쉬워
"반복 횟수·의성어/의태어" 문맥을 프롬프트에 명시 — 실측: `もぐ` 단독 요청 시 "몰입"
오역, 반복 문맥 제공 시 "우걱"으로 정확) 후 그 결과를 `count`번 반복, 나머지(`remainder`)는
`_translate_once`로 따로 번역해 이어붙인다.

**(v3.1.9) 장음부호 늘려쓰기 정규화 + `max_tokens` 상한** — `_REPEAT_RE`는 문자열 맨 앞의
**단일 유닛** 반복만 잡아서, "おーまーーたーーせーーーしーーーーました"처럼 글자마다
다른 길이로 장음부호(ー/ｰ/〜/～)가 흩어져 끼어드는 늘려쓰기 강조체는 못 잡는다(버그리포트
20260913 #4, 실측: 204자 입력 → 2035자 응답, 환각 가드에 매번 걸림). `translate()` 진입 시
`_normalize_stretch()`로 장음부호류 연속 2회+ 를 1회로 접은 뒤 `_REPEAT_RE`/`_translate_once`
로 넘긴다. 표적을 장음부호류로 좁힌 이유 — 아무 문자나 2연속 접으면 "宮永ののか"(멤버명
자체의 반복 글자) → "宮永のか", "かわいい" → "かわい", URL(`https://www.`→`htps:/w.`)까지
깨진다(실측 후 표적 축소). 추가로 `_call_groq` payload에 `max_tokens = max(200, len(prompt)//2)`
를 상한선으로 걸어, 정규화를 뚫는 미지 패턴이 또 나와도 API 단에서 조기 절단되게 함(2중 방어).

### 8.5 `ytnotif.py` (순수)

`parse_yt_notif(nx: dict, now_iso) -> dict | None`. `pde_noti_pkg != com.google.android.youtube` /
`::SUMMARY::` 태그 / slot_key 11자 아님 / 빈 제목 → None. `chime.thread_id` 접두어로 종류 분기 후
제목 필드 선택: `TUNEIN`→`android.text`, `REMINDER`→`android.title`, `SUBSCRIPTION_LIVESTREAM_START`→`android.text`.
제목 앞 `🔴 ` 만 제거(`【…】` 는 유튜브 제목 관용 접두라 보존). `video_id`=slot_key, url/thumbnail 조립.
`scheduled_start`: TUNEIN → `now+30분`+`time_approx=True`, 그 외 → `now`. 반환 dict: `{video_id, url,
thumbnail, title, kind(tunein|reminder|sub_start), scheduled_start, time_approx, source:"yt-notif"}`.

**(v3.7.3) 회원 전용 라이브** — 위 `parse_yt_notif` 은 `chime.*` dict 입력용이고 `/ingest` 에 연결돼 있지 않다
(v3.8.4 이후도 그대로 — 이 함수 자체는 안 쓰이는 self-test 전용, 아래 `parse_public_live_relay` 가 실전 파서).
실제 업스트림은 유튜브 알림을 폼 `source=yt&video_id&title&kind&tag` 로 중계한다(`ref/v3_automate_wire.md` —
`chime.thread_id` 에 "LIVESTREAM" 이 있으면 종류 불문 전부 이 폼으로 옴). `parse_member_live_relay(form,
channels_cfg)` 는 `kind` 에 `NOTIFICATION_TYPE_SPONSORSHIPS_LIVESTREAM_START` 가 있고 `title`
(`"<채널 표시명> / <그룹명> 실시간 스트리밍 시작: <영상 제목>"`) 앞부분이 5인 `channels.json` `name` 과 일치할 때만
`{channel_key, title, tag}` 를 반환(`video_id` 는 `default` 라 무시). `ytdlp_probe.find_member_live(channel_id, title)`
이 streams 탭(`--flat-playlist`)에서 `subscriber_only` + (`is_live`|`is_upcoming`) 를 제목 일치→is_live 1건 순으로
골라 `{video_id, url}` (상한 6초, 쿠키 있으면 쿠키→쿠키 없이 폴백). `telegram_app._handle_member_live_start` 가
조립해 `/write` 잡 `yt_member_live_commit`(`_commit_yt_member_live` → 순수 `xtweet.merge_member_live`: 자리표시
승격 / 신규 생성 / noop)로 반영. 항상 200.

**(v3.8.4) TUNEIN/REMINDER/SUBSCRIPTION_LIVESTREAM_START(일반 채널)** — 09-22 09:33 千石ユノ TUNEIN 알림이
`parse_member_live_relay` 의 kind 필터에 안 걸려 조용히 무시된 게 발단. `parse_public_live_relay(form,
channels_cfg=None) -> dict | None` 이 같은 폼에서 이 세 kind 를 파싱한다: `video_id`(=`chime.slot_key`,
공개 채널이면 실측상 항상 실제 11자 ID)가 유효하면 `resolved=True` — `_handle_yt_relay` 는 이때 preview.json
을 직접 안 건드리고 `_enqueue_wake_now(video_id, now)` 만 호출한다. 나머지(승격 판정·DM·모니터로그·다음
wake 예약)는 전부 기존 `/wake`(`handlers._run`) 파이프라인이 처리 — `build_preview` 섹션 1 이 신규
video_id 도 그대로 `videos.list` 후보에 넣고, 없던 아이템이면 `make_item(state="announced")` →
`promote_state` 가 필드(scheduled_start·title·thumbnail·url·video_id)가 다 갖춰진 즉시 upcoming 으로
승격한다(announced 단계를 거칠 필요 없음). `video_id` 가 `"default"`(회원전용 추정, placeholder — 실물
ID 미상)면 `resolved=False`: TUNEIN 은 이 포맷이 실제로 오는지 미확인이고 videos.list 로도 확정 불가해
오판 위험이 커서 승격 보류(무시, 기존 10분 light tick 안전망에 맡김), REMINDER/SUB_START 는 회원전용
라이브 시작과 같은 포맷으로 보고 `_handle_member_live_start`(위 문단) 로 위임한다.

### 8.6 `vxtwitter.py`

`fetch_tweet(tweet_id, *, session=None, timeout=8.0, base=cfg.vxtwitter_base) -> dict | None`
(`GET {base}/i/status/{id}`. 비200·타임아웃·JSON 오류 → None + warning).
`extract(j) -> {text, media: [url...], urls: [expanded...], yt_video_id: str|None}` —
`youtube.com/(watch\?v=|live/)` · `youtu.be/` 뒤 11자 추출. 서드파티 무료 서비스 → 실패 시 조용히 skip.

**(v3.1.7) 원문 우선순위 — vxtwitter 정본 우선, 폰 원문은 폴백** —
`telegram_app._recover_raw_via_vxtwitter(raw, tag)`. 안드로이드 알림은 "축약본"(contentText)과
"전체본"(bigText) 두 필드가 있는데, 폰(Automate)이 축약본만 읽어오면 말줄임표(…)도 깨진 문자도
없이 **완결된 문장처럼 보이는 상태로 조용히 잘려서** 온다(실측: 문단 9개짜리 트윗이 앞 3개
문단·125자만 옴 — 버그리포트 20260913 #2). 이런 "조용한 잘림"은 텍스트 패턴만으로는 감지가
불가능하다 — 그래서 손상/잘림을 감지해 사후 복구하는 방식(v3.1.6, 폐기)이 아니라, **`tag`에서
tweet id 를 뽑을 수 있으면 무조건 vxtwitter 를 먼저 조회해 그 `text`를 정본으로 쓰고, 실패
(조회 안 됨·id 없음·network/404)할 때만 폰이 보낸 `raw`로 폴백**한다. 소식(`xnotice`)·
스케줄(`xrelay`)·개인트윗(`xtweet`) 모든 하위 파이프라인 **이전**에 태워서 항상 최선의 원문을
넘긴다. 기존 `_expand_truncated_yt`(URL만 복구, `_maybe_personal_schedule` 직전 2차 안전망)와
별개 경로 — 이쪽이 먼저 돌아 raw 를 이미 온전하게 만들어놓으므로 대개 no-op.

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
   b′. (v3.7.1) `xtweet.apply_overrides(new.items, prev.items, now)` (§6-3). 실패 시 경고 후 원래 items.
   d. `_stable_view` 동일하면 volatile 필드와 `generated_at` 을 이전 값으로 동결 → 커밋 안 함(v3.2.2, heartbeat 없음).
   e. `build_archive_appends` → `preview_archive.json`(변경 시).
   f. `gh.write_json("preview.json", …, prev_sha=pv_sha)`. `ConflictError` → a 재시도, 2회째 실패 → 예외.
5. **Cloud Tasks**: `wakes` → `enqueue_wake`. `transitions` 에 `"→end"` 있으면 `enqueue_tick("light", now+20분)`.
   video_id 없는 announced 예고 시각(지금~+3h) → `_scheduled_wake_times` → `enqueue_tick("light", ss)`.
   (뒤 두 개는 light tick 3h 시절 도입한 보정 — 10분 tick 과 겹치지만 무해해 유지.)
6. **LLM 번역 sweep** (tick 만): `_translate_sweep` — `notices.json`/`tweets.json`/`preview.json`(v3.1.13,
   방송 제목 `title`→`title_ko`) 의 `needs_tl` 행 재번역.
7. **Telegram diff**: `notify.diff_events(_pv0.items, new_preview.items, transitions, channels, now)` →
   레벨 게이팅 후 개별 전송 + `summary`(detail).
8. **모니터 로그** (v3.7.1): preview 전이 이벤트 + tick/wake 이벤트를 모아 `monitor_log.log_events` **1회**(커밋 최대 1개).
   tick/wake 이벤트는 `_should_log_run` — preview/archive 변경 · enqueue 오류 · 전이 이벤트 ≥1 · 번역 반영 ≥1 중
   하나라도 참일 때만 싣는다(변화 없는 실행은 기록 안 함 → `/monitor` 의 quota·호출 수는 "기록된 실행" 기준).
9. 성공 끝 healthcheck GET. 예외 → `notify.error_text` 후 re-raise.

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

`/edit preview` 로 `state` 를 바꾸면(예: 긴급 종료 처리) 라벨만 바뀌는 게 아니라
`_activate_state_edit`(v3.1.17)이 그 상태에 맞는 실제 로직을 마저 이행한다 — 안 하면
FSM 파생·Cloud Tasks wake 재예약·archive 반영이 전혀 안 일어나 다음 tick(당시 최대 3h)까지
방치되는 문제가 있었다. `state_since` 도 이 시점으로 리셋한다(안 하면 오래된 state_since
때문에 end→none 30분 판정이 리셋 없이 즉시 발동할 수 있음). 목표 상태별 동작:
- `"none"` — preview.json 에서 즉시 제거 + `preview_archive.json` 에 기록(FSM 의
  end→none 전이와 동일 취급).
- `video_id` 있음(live/end/watching/upcoming — API 로 실물 검증 가능) — 메인 서비스
  `/wake` 를 OIDC 로 호출해 실제 상태로 재확인 + Cloud Tasks wake 재예약까지 그쪽에
  맡긴다(운영자가 잘못 짚었어도 API 확인 결과가 우선하므로 안전).
- `video_id` 없음(announced 자리표시) — API 로 검증할 게 없으므로 로컬에서
  `statemachine.derive()` 1회만 돌려 리셋된 `state_since` 기준으로 다음 체크를 재계산.
| `/del <c> …` | `<유닛> <idx>` → 확인 `(terminate/y/N)`. terminate = 삭제 + `add_suppress(url, 12h)` | `/notice-del <id\|번호>` | `<유닛>` → 슬롯 제거 |
| `/undo` | 직전 mutating 명령 1건(계통 무관 단일 슬롯). 2단계 확인 + sha 2중 가드. `undo.path` 로 3파일 복원 |
| `/translate <notice\|tweet>` | 미번역 행 전부 `*_ko` 채움(원문 보존). `GROQ_API_KEY` 필요. 수동 명령 — 자동 sweep 과 별개 |

일반: `/status`(v3 양식 — preview 6상태 카운트·notice·tweet·마지막 sync·LLM 큐=`needs_tl` 행 수) ·
`/pause` · `/resume`(paused=false + 메인 `/tick` OIDC 호출) · `/log [detail|normal|simple]`.
별칭 유지: `/notice` `/notice-list`(`/notices`) `/notice-del`(`/ndel`) `/notice-edit`(`/nedit`) `/add`.

**`/ingest`** (X 릴레이): `X-Ingest-Secret` 헤더. 본문 form/JSON `text`(필수)/`title`/`template`/`tag`.
`xtweet.route_by_title(title)` → 개인 5인이면 `_maybe_personal_tweet`(→ `tweets.json` + 예고면 preview
승격 — 준비/커밋 분리는 §8.14) 후 즉시 200. 테스트 부계정(`INGEST_TEST_TITLES`, 기본 `jehy`)은 `force_echo`. 공식·미매칭은
`_maybe_auto_notice` → `xrelay.parse` → `merge_announced` → `preview.json`. `INGEST_ECHO`/`INGEST_DRY_RUN`
이면 저장 안 하고 회신 + 스케줄 트윗은 `ingest_queue.json` 버퍼(실배포 전환 시 첫 `/ingest` 에서 drain).

### 8.12 `config.py`

`load_config()` — `ALLOW_UNAUTH != "1"` 이면 `_REQUIRED`(GITHUB_TOKEN, GITHUB_REPO, YOUTUBE_API_KEY,
GCP_PROJECT, GCP_LOCATION, TASKS_QUEUE, SERVICE_URL, INVOKER_SA) 필수. 선택:
`DATA_BRANCH`(기본 "data"), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`,
`HEALTHCHECK_URL`, `MAIN_SERVICE_URL`, `INGEST_SECRET`, `INGEST_ECHO`, `INGEST_DRY_RUN`,
`INGEST_TEST_TITLES`, **`GROQ_API_KEY`**, **`GROQ_MODEL`**(기본 `openai/gpt-oss-120b`),
**`GROQ_MODEL_FALLBACK`**(기본 `openai/gpt-oss-20b`), **`VXTWITTER_BASE`**(기본
`https://api.vxtwitter.com`), **`INGEST_YT_ENABLED`**(기본 `""` — `"1"` 이어야 ytnotif 라우팅),
`HEALTHCHECKS_IO_READONLEY_TOKEN`(`/monitor` 백엔드 상태 조회용 healthchecks.io read-only 키 — 이름의
`READONLEY` 는 오타지만 운영 Secret 이름이라 유지. 비면 해당 패널만 비활성).

### 8.13 `app.py` (비공개, OIDC)

`@app.post("/tick")` → `oidc.verify_request` → `handlers.tick(mode="light" 기본)`.
`@app.post("/wake")` → video_id 필수(없으면 400) → `handlers.wake(vid)`.
`@app.post("/write")` (v3.7) → body `{kind, args}` → `writers.dispatch(kind, gh, args)` (알 수 없는 kind 400).
`@app.post("/monitor")` (v3.5) → `control.json monitor_auto` 켜져 있으면 전일(06:00 KST 경계) 리포트 생성 →
`monitoring/latest.html` 커밋 + 텔레그램 DM. 제어 채널(`telegram_app`)의 `@app.get("/monitor-live")` (v3.7.2) →
웹 `monitor.html` 이 부르는 읽기 전용 공개 라우트, 가장 최근 06:00 KST~지금 리포트를 즉석 생성(60초 캐시·CORS `*`,
실패 시 500 — `monitor.html` 이 `latest.html` 로 폴백). `@app.get("/")` → "ok" (`/healthz` 는 GFE 가 가로챔).
예외 → 500 + `notify.error_text` DM. `PermissionError` → 403.

### 8.14 write-queue — `writers.py` / `writeclient.py` (v3.7, v3.7.1 A-1)

GitHub Contents API 의 PUT 은 파일이 아니라 **브랜치 HEAD 단위**로 충돌한다(다른 파일이라도 읽은 뒤
다른 커밋이 끼면 409). 제어 채널(`mewtype-telegram`, 동시 처리 80)의 콘텐츠 쓰기를 백엔드
(`--concurrency=1 --max-instances=1`)의 `POST /write` 로 보내 한 줄로 세운다.

- `writeclient.call_write(kind, *, gh=None, label=None, **args) -> dict` — `MAIN_SERVICE_URL` 이 있으면 OIDC
  id token 으로 `POST {MAIN_SERVICE_URL}/write` 동기 호출(타임아웃 60초, 2초 넘으면 `"⏳ 처리 대기 중…
  [{label}]{kind}"` DM 1회 — `label` 생략 시 `args["action"]` 폴백), 없으면 같은 프로세스에서
  `writers.dispatch`(로컬 개발·self-test). (v3.8.4) 대기 DM 이 나갔으면 종료 시 짝이 되는 완료(`✅`)/
  실패(`⚠️`) DM 도 보낸다 — 2초 안에 끝나면(대기 DM 자체가 없으면) 지금처럼 아무 것도 안 보냄. 비200 →
  `WriteError`.
- `writers.dispatch(kind, gh, args)` — kind → `telegram_app` 의 커밋 함수(지연 import). 등록 kind:
  `merge_rows` `remove_broadcast` `apply_notice` `notice_sweep` `notice_del_commit` `notice_edit_commit`
  `personal_tweet` `tweet_sweep` `tweet_del_commit` `url_confirmed_commit` `yt_member_live_commit`(v3.7.3)
  `undo_restore` `apply_preview_edit` `ingest_queue_push` `ingest_queue_drain`.
  (v3.8.4) TUNEIN/REMINDER/SUBSCRIPTION_LIVESTREAM_START(video_id 실물 확보) 경로는 이 큐를 안 탄다 —
  `/write` 커밋이 아니라 `_enqueue_wake_now` 로 기존 `/wake` 를 깨우는 신호만 보낸다(§8.5 참고).
- **(v3.7.1) A-1 — 외부 호출은 제어 채널, `/write` 잡은 커밋만.** 잡 함수는 GitHub 읽기·쓰기(+ undo 스냅샷,
  모니터 로그, 텔레그램 DM, Cloud Tasks enqueue)만 하고 외부 LLM·`videos.list`·vxtwitter·비전 OCR 은 부르지
  않는다. 제어 채널이 먼저 준비해 결과를 JSON 인자로 넘긴다:

  | 경로 | 제어 채널(준비) | `/write` 잡(커밋) |
  |---|---|---|
  | 소식 | `_prepare_notice` — `xnotice.parse`, 비전 OCR, 제목추출 LLM, `notices.json` 읽어 사본으로 `merge_notice` → `added` 면 중복판정 LLM → `{parsed, tl, dup_id}` | `apply_notice` → `_commit_notice` — merge, `dup_id` 있으면 `merge_into`(→updated), 번역 반영 또는 `needs_tl`, undo |
  | 개인 트윗 | `_prepare_personal_tweet` — vxtwitter 미디어, `xtweet.parse`, 스냅샷으로 `merge_thread` → 변화 있을 때만 본문·인용 번역 → `{parsed, text_src, text_ko, quote_src, quote_ko}` | `personal_tweet` → `_commit_personal_tweet` — merge, `row.text == text_src` 일 때만 `text_ko` 반영(아니면 `needs_tl`), sweep, 모니터 로그 → `{mode, n_thread, needs_tl}` |
  | 개인 예고(URL) | `_maybe_url_confirmed_schedule` — `videos.list`, 본인/타멤버 채널이면 `find_guest_members`(v3.8.3, 제목·원문의 다른 멤버 정식 표기 → `collab_with`), 외부 채널이면 참여판정 LLM, `build_item_from_video` | `url_confirmed_commit` → `_url_confirmed_commit` — `merge_video_confirmed`(v3.8.3: `collab_with` 추가만), undo, **`_enqueue_wake_now`**(제어 채널 서비스엔 Cloud Tasks env 가 없어 반드시 백엔드) |
  | 개인 예고(텍스트) | `parse_schedule` + `announces_own_broadcast` LLM | `merge_rows`(`merge_fn="personal_schedule"`) |

  `_maybe_personal_tweet` 는 제어 채널 오케스트레이터(준비 → `personal_tweet` 잡 → DM → `_maybe_personal_schedule`).
  준비 시점 스냅샷 기준이라, 준비~커밋 사이 같은 날짜 소식이 새로 들어오면 중복판정에서 빠져 새 소식으로
  등록될 수 있다(LLM 실패 시와 같은 안전한 기본값).
- **남는 한계**: 모니터 로그(notice/relay/ops)·`admin_state.json` 마법사 단계·`control.json`·`/translate`·
  `/monitor` 의 `latest.html` 은 여전히 제어 채널이 직접 커밋 → 큐 잡과 409 가능(잡은 최신 재조회 후 1회 재시도).

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
  **(v3.1.5)** 모바일에서 백그라운드 동안 `setInterval` 폴링이 멈추거나 크게 스로틀링될 수 있어
  (브라우저 스펙상 보장 안 됨) — `visibilitychange`(visible 전이) + `pageshow`(`persisted`,
  bfcache 복원) 리스너로 포그라운드 복귀 시 `poll`+`pollNotices`+`pollTweets` 즉시 재실행.
  없으면 복귀 직후 오래된 `lastSchedule` 로 카운트다운을 계산해 이미 끝난 방송이
  "OOO시간 지각"처럼 잘못 보이다가 다음 정기 poll(최대 `POLL_MS`) 이 돼야 정정됐음.
- **js/notices.js** + **css/notices.css** — `NOTICES_URL` 75초 폴링 → `#notice` 티커. `title_ko` 있으면
  제목을 `[번역]　—　[원문]` 순으로 한 줄에 이어 marquee(길이 넘칠 때 순환). 없으면 원문만.
- **js/tweets.js** + **css/tweets.css** — `TWEETS_URL` 75초 폴링. 유닛 아바타 편지 배지(안 읽은 메시지
  2건+ 이면 카운트 pill). 배지 클릭/호버 → **메신저형 스레드**: PC `.lane__bubble` 패널 / 모바일
  `.tw-toast` 시트에 **`expires_at`(24h)이 안 지난 메시지 최대 50건**을 최신이 아래로 스택
  (v3.5.3 — 이전엔 유닛당 최근 5개 고정. v3.5.3~v3.7.1 은 12시간 창을 따로 걸어 밤에 온 트윗이 다음날 낮에 전부 사라졌음 → v3.7.2 에서 제거),
  ~2분 내 연속은 시각 1개로 묶음(`.lane__thread__grp`/`__msg`/`__t`), 열면 맨 아래로 스크롤 + 표시분
  전부 읽음. 메시지가 많아도 말풍선(헤더 포함)이 화면 세로 2/3을 넘지 않도록 내부 스크롤 영역
  높이를 `calc(66.6vh - 44px)` 로 고정(css). `한/日` 토글은 헤더에 1개(전역 `mew:tllang`), 원문(X)
  링크는 메시지별(`.ori`). 만료·404 면 안 뜸.

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
| 3 | 방송 종료 직후 시작하는 짧은 다음 방송을 (당시) 3h tick 간격에 놓침 | `→end` 전이 시 `now+20분` 후속 `light` tick 1개(분버킷 dedupe). v3.6 light 10분 이후엔 겹치지만 유지 | `handlers.py` |
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
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `INGEST_SECRET`, **`GROQ_API_KEY`**,
  `HEALTHCHECKS_IO_READONLEY_TOKEN`(v3.7.1 추가)). 멱등.
- `deploy.sh` — `gcloud run deploy mewtype-backend --source . --no-allow-unauthenticated --service-account RUNTIME_SA`
  + secrets/env. `GROQ_API_KEY`·`HEALTHCHECKS_IO_READONLEY_TOKEN` 은 Secret 이 있을 때만 마운트(v3.7.1 — 전엔
  healthchecks Secret 을 무조건 마운트해 새 프로젝트에서 첫 배포가 실패). 배포 후 `SERVICE_URL` env 재설정.
- `scheduler.sh` — `mewtype-baseline`(`0 6 * * *` Asia/Tokyo) / `mewtype-light`(`*/10 * * * *` Etc/UTC, v3.6) /
  `mewtype-monitor`(`10 6 * * *` Asia/Seoul → `/monitor`). OIDC.
- `deploy_telegram.sh` — 같은 소스 + telegram 엔트리포인트 + `--allow-unauthenticated --service-account INVOKER_SA`
  `ALLOW_UNAUTH=1` + `MAIN_SERVICE_URL`(write-queue·`/resume`). `GROQ_API_KEY`·`HEALTHCHECKS_IO_READONLEY_TOKEN`
  (조건부) + `INGEST_YT_ENABLED` env. (v3.7.3) Secret `YT_COOKIES` 가 있으면 `/secrets/yt-cookies.txt` 로 마운트 +
  `YT_COOKIES_FILE` env(회원 전용 라이브 yt-dlp 조회용, 없어도 동작). **`writers.py` 등 공통 코드를 바꾸면 두 서비스 모두 재배포.**
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
