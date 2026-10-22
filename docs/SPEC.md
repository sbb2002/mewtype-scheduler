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
| 정기 트리거 | **Cloud Scheduler** 4잡 — baseline JST 06:00 / light 10분(v3.6, 구 3h) → `POST /tick`, monitor KST 06:10 → `POST /monitor`, (v4.5.0) websub-renew KST 06:20 → `POST /websub-renew` (OIDC) |
| 방송별 정밀 wake | **Cloud Tasks** — `POST /wake {video_id}` (OIDC). 720h 상한 → `now+696h` 클램프 롱폴링 |
| 저장 | **GitHub `data` 브랜치** — 2026-09-14 부터 별도 저장소 `sbb2002/mewtype-scheduler-data`(Vercel 비연결). Cloud Run 이 GitHub Contents API(fine-grained PAT, Secret Manager)로 커밋 |
| 프론트 | **Vercel** 정적 호스팅 (빌드 없음). `raw.githubusercontent.com/.../data/preview.json` 75초 폴링 |
| 모니터링·제어 | 공개 서비스 **`mewtype-telegram`**(같은 이미지, 다른 엔트리포인트) — Telegram webhook + `/ingest` + (v4.5.0) PubSub 콜백 `/websub/<이름>` |
| PubSub(WebSub) | (v4.5.0) 허브가 멤버 5채널 · 뮤타입 음원 채널의 변경을 `mewtype-telegram` 으로 POST → 즉시 wake / 신곡 등록(v4.5.2 — PubSub 전용 큐 `mewtype-websub` 로 예약, 수신 기록은 쓰기 서비스). 구독 일일 갱신은 `mewtype-backend` `/websub-renew`. §8.16 |
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
      notices.js       # 소식판 — (v4.6.4) PC 날짜별 묶음 · 모바일 칩+카드, 분류 탭, 제목 한 줄, 소식 팝업 카드/시트
      tweets.js        # 유닛 아바타 편지 배지 (+ text_ko 원문↔번역 토글 버튼)
      main.js          # DOMContentLoaded → poll(preview) + pollNotices + pollTweets + 카운트다운 틱
  collector/           # v1 순수 모듈 — config/rss/youtube 는 v3 백엔드가 import 재사용.
    rss.py youtube.py  #   (v1 실행기 main.py · reconcile.py · store.py 는 2026-10-20 삭제)
    config.py
  backend/             # v3 Cloud Run 서비스
    app.py             # /tick(Scheduler) /wake(Cloud Tasks) /write(제어 채널) /monitor(Scheduler) · `/` 헬스체크
    handlers.py        # tick/wake 오케스트레이션 — preview.json 커밋 + LLM 번역 sweep + 모니터 로그(실행당 최대 1커밋)
    writers.py         # (v3.7) write-queue — /write 잡 kind → telegram_app 커밋 함수 매핑 (§8.14)
    writeclient.py     # (v3.7) 제어 채널 → 백엔드 /write 동기 호출 (OIDC). MAIN_SERVICE_URL 없으면 로컬 디스패치
    monitor_log.py     # (v3.5) monitoring/events-YYYY-MM-DD.jsonl append (log_event / log_events 배치)
    monitor_report.py  # (v3.5) /monitor Ops Timeline HTML 생성. (v3.8.9) 웹 monitor 는 전 기간(all) 리포트
    monitor_snapshot.py # (v3.8.9) 모니터링 스냅샷 — 일별(monitoring/days/)·전 기간 요약(summary.json)·멤버 현황 DM 텍스트
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
                       #   + (v3.8.9) monitoring/days/YYYY-MM-DD.json (하루치 스냅샷) +
                       #     monitoring/summary.json ({"days": {날짜: 요약}, "backfill_complete"})
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
      "src_url": "https://x.com/i/status/…", // (v4.0.4, 선택) 이 예고를 처음 알린 트윗(공식 스케줄 · 본인 예고 · URL 확정).
                                           //   비어 있을 때만 채운다. 리포트 팝업 X url · announced at(트윗 ID 게시 시각). 프론트 미사용
      "api_start_seen": null,              // 마지막 API scheduled_start. 이 값이 바뀌면(스트림 실수정) 트윗값 대신 API 승
      "announced_start": null,             // (v4.5.8, 선택) 이 실물에 흡수된 영상 없는 예고(자리표시)의 scheduled_start — 여럿이면 가장 이른 것,
                                           //   시각 미정 예고는 안 넘김. preview_build._carry_collab 이 채운다. 프론트 king.js 의 지각 기준(약속 시각)

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

같은 `channel_key` + (`video_id` 일치 ∥ `url` 일치 ∥ `scheduled_start` ±45분(`superscede_sec`, v3.8.10 — 구 ±4h)).
매칭되면 같은 `id` 유지·필드 갱신. 안 되면 새 `id`. `none` 으로 사라진 뒤 오는 예고는 무조건 새 아이템.

### 1-2. 상태 승격 (`preview.promote_state`)

`upcoming` = `scheduled_start` && !`time_tbd` && `title` && `thumbnail` && `url` && `video_id` 전부.
아니면 `announced`. 승격 판정은 `preview_build` 가 매 tick 수행 (FSM 은 승격을 되돌리지 않음 — 지각 강등만).

### 1-3. 합동방송 (collab)

`xrelay`/`xtweet` 가 `collab_with` 채운 `announced` 아이템을 참여 유닛 전부에 fan-out.
url(video_id) 확정 시 일반 방송 추적과 동일 — 상태머신은 레인이 아니라 url 추적. `preview_build` 가
참여자(`channel_key` ∪ `collab_with`) 중 아무 채널에나 실물 ±45분(`SCHEDULED_SUPERSEDE_SEC`, v3.8.10 — 구 ±4h) 안에 뜨면 supersede 하고
`_carry_collab` 로 실물 행에 `collab_with` + `kind="collab"` 이관(+ (v4.0.8) 회원 전용 · (v4.5.8) 예고 시각 `announced_start` — 합동이 아니어도). `host=="group"` 은 supersede 면제.
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
`#board` 골격(`<section class="lane">` × `channel_order`, `lane__header`)은 v2 와 동일 —
`docs/old/v2/IMPLEMENTATION_v2.md` §3 참조. v3 변경분 아래. **v4.1.0 에서 `lane__live`(ON-AIR 존) ·
`lane__buckets`(오늘 / 7일 이내 / 7일 이후)를 없애고 타임테이블로 대체했다 — 아래 「타임테이블 · 이후 예고」 참조.**

### 레인 헤더 (`lane__header`) — v3.0.2

`<div class="lane__link" role="button" tabindex="0">`(아바타 `lane__avatar` + `lane__meta`) **+** `<nav class="lane__nav">`
(우측 세로 레일: `lane__nav-btn lane__nav-yt` = `channel_url`, `lane__nav-btn lane__nav-x` =
`https://x.com/<handle>`). 헤더는 `display:flex` (tweets.css 가 layout.css override).
**(v4.3.4)** 네임플레이트(아바타 · 편지 배지 · 이름 = PC 타임테이블 `tt__nm` 포함)는 이동 링크가 아니라
`tweets.js` 가 클릭을 위임 처리하는 **말풍선 토글**(PC 고정 패널 / 모바일 토스트)이다 — 트윗이 없으면 아무 일도 없다
(v4.3.3 까지는 `<a>` 라 이름 · 트윗 없는 아바타가 YouTube 로 이동). 채널 이동은 우측 레일 버튼만.
이후 예고 열(`data-no-badge`)의 헤더는 말풍선 대상이 아니다. SVG 아이콘은 `render.js svgIcon()`(`createElementNS`).

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

### 타임테이블 · 이후 예고 (v4.1.0) — `timetable.js` · `css/timetable.css`

예고판의 **ON-AIR 존(`lane__live`) + 오늘 / 7일 이내 / 7일 이후 버킷(`lane__buckets`)을 대체**한다.
`render.js renderBoard(boardEl, preview, nowMs, archive)` 가 화면 폭(`mqlPhone`, <768px)으로 두 구성 중 하나를 만든다.

**오늘 구간** = KST 06:00 ~ 익일 06:00(`timetable.dayWindow`, 모니터링 하루 경계 `monitor_log.DAY_START_HOUR` 와 같음).
`timetable.classify(items, archiveItems, nowMs, order)` 가 아이템을 나눈다:

| 구분 | 기준 |
|---|---|
| `live` | `state=="live"` — 시작 = `actual_start`(없으면 `scheduled_start`) |
| `ended` | `state=="end"`(끝 = `state_since`) + `preview_archive.json` 에서 **오늘 06:00 이후 시작해 이미 끝난** 항목(끝 = `archived_at`, 길이 10분~12시간만. 같은 `video_id` 는 한 번만) |
| `upcoming` | announced/upcoming/watching 이고 `scheduled_start` 가 오늘 구간 안 (시각 미정 제외) |
| `later` (이후 예고) | announced/upcoming/watching 이고 구간 뒤(`>= de`)이거나 `time_tbd` · 시각 없음. 기간 구분 없이 시작시각순 |

합동(`collab_with`)은 참여 멤버(알려진 채널) **전원 행/레인에 팬아웃**(`timetable.itemKeys`, v3 와 같은 규칙).

**PC (≥768px)** — `#board.board--tt`(5열 그리드 해제) 안에 위에서 아래로:
1. `section.tt` 타임테이블: `.tt__axis`(06:00 부터 3시간 눈금, 자정은 `.is-midnight` 강조 + 익일 날짜) · 멤버 5행
   (왼쪽 `section.lane.tt__lane[data-channel]` > `header.lane__header.tt__who` > `.lane__avatar` — **편지 배지(`.lane__tw`)와 말풍선의 기준 요소**.
   오른쪽 `.tt__track[data-channel]` 에 블록 `.tt-blk.tt-blk--{upcoming|live|ended}`) · `.tt__ov`(지금 선 `.tt__now` · 지난 구간 음영 `.tt__past` · 자정 점선).
   블록 폭 = 종료 시각을 알면(ended) 실제 길이, 모르면 고정 폭(live 는 시작~지금, 최소 폭 있음). 한 행에 한 줄만 쓰고 겹치면 앞 블록을 다음 블록 시작에서 자른다.
   좁아도 블록 모양은 같고 넘치는 부분만 잘린다. 제목은 한 줄 + 넘치면 무한 marquee(`applyTimetableMarquees`).
   블록 안은 항상 **3줄 고정 높이**(v4.5.6): ① 시각 + 태그(`.tt-blk__t`) ② 카운트다운(`.tt-blk__rel` — 예고만. 「방송시작까지 1.5시간」 · 60분 미만 「n분」 정수 · 정각 「2시간」 · 시각이 지나면 「지각」, 모바일 카드 링과 같은 규칙) ③ 제목(`.tt-blk__n`). 라이브 · 종료 블록의 ② 는 빈 줄(`.tt-blk__sp`, king.js 가 `.tt-blk__rel` 을 「지각」 자리로 쓰므로 클래스를 나눔). 예정 블록 고정 폭 `W_FIXED` = 250px.
   블록은 **클릭해도 이동하지 않고** 호버 = 카드 팝업(`.tt-pop`) · 클릭 = 고정(바깥 클릭 / Esc / 재클릭으로 닫힘). 영상 이동은 팝업의 이미지 · 「▶ YouTube에서 보기」로만.
2. `.tt-fold` 「오늘 이후 예고 N건 펼치기」(펼치면 「오늘 이후 예고 접기」)(방송인별 건수 아바타 포함).
3. `.tt-later` 5열: 펼침(`#board.board--later-open`)일 때만 보임. 열 = `.lane.lane--later[data-channel][data-no-badge]` — **기존 네임플레이트**(`buildHeader`, 우측 세로 YT·X)
   + `.lane__later` 안에 기존 카드(`createCard`). `data-no-badge` 인 레인에는 편지 배지가 안 붙는다(`tweets.js` 가 건너뜀) — 배지는 타임테이블 왼쪽 칸에만.

**모바일 (<768px)** — 현행 1명씩 가로 슬라이드(`initMobileCarousel`, 스냅 · 무한 회전 · 하단 도트) 그대로. 레인 하나 = `lane__header`(편지 배지 포함) + `.tt-today`(오늘 카드 `.tcard`) +
`.tt-fold` + `.lane__later`. 오늘 카드: 예정 = 카운트다운 링(1시간 넘게 남으면 24시간 기준으로 차오름 · (v4.5.8) 1시간 이내는 노랑 분 단위 링이 0분까지 닳음 — 아래 「타이머 링」, **이미지가 아니라 제목 영역 오른쪽**, 영역 높이에 맞춘 크기), 방송 중 = `LIVE` 알약 + 빨간 테두리 + **경과 링**(제목 영역 오른쪽, 12시부터 시계방향으로 60분간 채워지고 다음 60분은 같은 방향으로 비워지는 2시간 주기 반복 · 글자 "N분" + "방송중", 시작 = `actual_start`, 1분 틱이 갱신 · `@property --p` 로 부드럽게 보간), 종료 = 회색 + `종료` 알약.
**지금 보는 레인만 동작**: `render.js initMobileCarousel` 가 현재 슬라이드에만 `.lane--active` 를 주고 나머지(클론 포함)는 `inert` 로 **동작만** 막는다(겉모양 · 스크롤바는 그대로 — `overflow:hidden` 으로 숨기면 스크롤바 폭만큼 카드가 움찔거려 쓰지 않음) — 옆에 비쳐 보이는 레인의 스크롤 · 클릭이 반응하지 않는다(드래그/스와이프 시작점으로는 보드가 받음).
하단 페이지 도트(`#pager-dots .dot`)는 멤버 프로필 이미지(레인 아바타와 같은 이미지)로 그린다. 펼침 상태가 `#board` 클래스라 캐러셀 클론 레인도 같이 열리고 닫힌다.
이후 예고가 0건이면 `.tt-fold` 와 목록을 만들지 않는다(PC = 전체 0건, 모바일 = 그 멤버 0건).
합동 카드는 이미지 **왼쪽 위에 참여 멤버 아바타만**(하단 선택 아이콘과 같은 고정 순서 아라레-유노-노노카-리츠-미야코로 겹쳐서, 이름 글자 없음, **그 레인의 본인은 뺀다**. 본인 외 참여자를 모르면 빈 알약을 만들지 않는다) 놓고, "합동" 글자는 날짜 옆 태그로만 쓴다.
회원 전용(`membership`) 카드는 이미지 오른쪽 아래 알약 줄(`.tcard__pills`)의 **LIVE · 종료 알약 왼쪽에 🔒 알약**이 붙는다(예정 카드는 🔒 만).
오늘 카드의 날짜·시각 줄(`.tcard__when`)은 상태와 관계없이 같은 굵은 글씨(종료는 `[날짜] [시작~종료]` — 글꼴은 같고 색만 종료 카드의 흐린 색. 방송 시간은 글자 대신 오른쪽 **회색 링**: 방송 중 경과 링이 끝난 순간에 멈춘 모양, "N분" + "방송") — "LIVE · 방송 중" · "N분 후" · 종료/예고 태그는 쓰지 않고(이미지 알약 · 링이 보여 줌) 태그는 **합동 · 회원 전용**만, 모자라면 다음 줄로 내려간다.
오늘 카드 제목(`.tcard__ti`)은 한 줄 + 넘치면 기존 카드와 같은 marquee(`render.js applyMarquees`).
마우스 드래그(`pointerType=="mouse"`)로도 넘길 수 있다 — 드래그 중 `#board.board--dragging`(스냅 해제), 놓으면 가장 가까운 유닛으로 `goDom`; 5px 넘게 끌었으면 그 클릭은 무시.

- 모바일 오늘 카드 타이머 링(v4.3.6): 예고(upcoming) = 큰 글자 「n시간」(1시간 이상, 내림) · 「n분」(1시간 미만) + 작은 글자 「시작까지」, 시작 시각이 지나면 「지각」.
  (v4.5.8) `timetable.updateRing`: 1시간 넘게 남음 = `--p` = 24시간 중 지난 비율(차오름, 레인 색) · **1시간 이내**(`.is-min`) = `--p` = 남은 분 / 60 — 가득 찬 노랑 링이
  12시부터 시계방향으로 비워져 0분에 빈 링(방송 중 링의 「비우기」와 같은 방향), 글자 「n분 / 시작까지」 · **시작 시각 지남**(`.is-late`) = 빈 링 + 노랑 「지각」
  (전엔 꽉 찬 레인 색 링 + 「지각」). 노노카 지각 이스터에그가 붙은 카드(`data-king`)는 「지각」 대신 「행차 / 준비 중」(`king.KING_RING_LATE`). 방송 중 링(「N분 / 방송중」)과 같은 2단 구조 · 글꼴(`.tcard__ring--up` = `.tcard__ring--live` 와 스타일 공유). PC 블록의 `relShort` 표기는 별개.
- 갱신: `updateCountdowns` → `timetable.tickTimetable` 이 지금 선 · 링을 1분마다 옮기고, **오늘 구간이 끝나면(`nowMs >= boardEl.__ttDe`) `true`** 를 돌려 `main.js` 가 재렌더. 데이터는 75초 폴링(`poll`)이 바꿈.
- 종료 블록용 `preview_archive.json`(`config.ARCHIVE_URL`)은 `main.js pollArchive` 가 따로 폴링 — 404 여도 보드는 그려지고 종료는 preview 의 `end` 상태만 나온다.
- 한계(의도): 예고 항목에는 **종료 시각 필드가 없어** 예정 블록은 고정 폭이다. 종료 길이는 끝난 방송(`end` · 아카이브)에서만 알 수 있다.
  시각 미정(`time_tbd`)은 타임테이블에 놓을 수 없어 이후 예고로 간다.
- 자체 점검: `node src/frontend/js/timetable.selfcheck.mjs`(순수 함수 `dayWindow` · `classify` · `itemKeys`).

### PC 보기 방식 · 카드 보기 (v4.4.0) — `render.js` · `timetable.js` · `css/timetable.css`

PC(≥768px)에서만 **보기 방식 탭 `.vt` [테이블 | 카드]** 가 「오늘 예고」 머리줄(`.tt__head`, `timetable.buildBoardHead`) 오른쪽 끝에 붙는다. 모바일은 탭 없음.

- **저장**: `localStorage["mew.board.view"]` = `"table"`(기본) | `"cards"`. 읽기 · 쓰기 모두 `try/catch` — 못 쓰면 모듈 변수(`viewOverride`)로 이번 세션만 유지. 탭 클릭 → `setViewMode` → `document` 에 `mew:view-change`(`VIEW_CHANGE_EVENT`) → `main.js` 가 `paintBoard()`(보드 재렌더 + 편지 배지 재적용). 재렌더 뒤 키보드 포커스는 새 선택 탭으로 되돌린다(`boardEl.__focusTab`). 탭은 ←/→ 키로도 바꾼다(`role=tablist` · `aria-selected`).
- **테이블 보기** = 위 「타임테이블 · 이후 예고」 그대로(`#board.board--tt`).
- **카드 보기** = `#board.board--tt.board--cards` > `section.tt.tt--cards` > 머리줄 + `.cards-board`(5열 그리드, `align-items:start`) + `.tt-fold`.
  레인 = `section.lane[data-channel]` > `buildHeader`(기존 네임플레이트) + `buildTodayCards(ctx, key, {compact:true})`(모바일과 같은 오늘 카드) + `buildLaterList`(`.lane__later`, 접힘). `data-no-badge` 없음 → 편지 배지 · 말풍선 · 노노카 이스터에그가 모바일 레인과 같은 경로로 동작.
- **펼치기 전 세로 고정**: `.board--cards .lane` 은 `container-type:inline-size`; `.cards-board .tt-today` 높이 = `34px + 2·pad + 2·카드높이 + 12px + 30px`(카드 2장 + 다음 카드가 살짝 보임), 넘치면 `overflow-y:auto`. 카드높이 = `(100cqw − 2·pad − 2px)·9/16 + --bh + 2px`, `.tcard__body{height:--bh}`(78px, ≤1100px 에서 pad 11.2px · bh 72px). 날짜줄은 줄바꿈 없이 한 줄. (v4.5.8) 노노카 지각 이스터에그가 붙은 카드(`.k-card`)만 본문이 `height:auto; min-height:--bh` 로 늘어나고 대신의 말 글자를 줄인다(`king.css`) — 고정 높이에 잘려 안 보였다.
- **이후 예고 펼치기**: 단일 `.tt-fold`(`buildFoldButton(counts, ctx, {perMember:true})`)가 `#board.board--later-open` 을 토글 → 5개 `.lane__later` 가 동시에 열리고 닫힌다. `toggleLater` 의 애니메이션 대상 선택자는 `board--cards` 이면 `.lane__later`(테이블 보기는 `.tt-later`). 이후 예고가 전체 0건이면 버튼 없음(레인별 「이후 예고 없음」 문구는 `buildLaterList` 기본).
- 펼침 상태(`board--later-open`)는 보기 방식을 바꿔도 `#board` 에 남는다.

### 노노카 지각 이스터에그 (v4.3.1) — `king.js` · `css/king.css`

> (v4.5.1) 입장 후 유지 3분 → **1분**, 그 뒤 즉시 제거 → **1.2초에 걸쳐 서서히 복귀**(`.k-leave`).
> **(v4.5.8) 라이브 입장 연출 기준 변경(운영자 결정)** — 「`actual_start` + 1분 안」 대신 **지각한 방송이 라이브인 동안은 무조건**: 페이지가 그 방송을 라이브로
> 처음 그릴 때 입장 연출을 한 번 재생하고, 끝나면 바로 서서히 평소 라이브 카드로. 「입장 후 1분 유지」 구간과 그 말은 없앴다. 지각은 **약속 시각**\* 기준.
> 계기(2026-10-20): ① 화면이 라이브를 알게 되는 건 백엔드 감지(0.3~6분, 10-14~10-20 16건 실측) + raw CDN 캐시(최대 5분) + 폴링(75초) 뒤라 1분 창이 거의 늘 지나 있었다.
> ② 20:00 영상 없는 예고가 20:26 에 바로 시작한 영상(별개 항목)에 흡수되며 실물 `scheduled_start` 가 20:26:26 이라 지각이 17초로 계산됐다.
> \* 약속 시각 = `scheduled_start` 와 `announced_start`(흡수된 예고 시각, 백엔드가 넘김 — §1-3) 중 이른 것.
> 같은 버전: PC 카드 보기(v4.4.0)에서 대신의 말이 고정 높이 본문에 잘려 안 보이던 것 — 노노카 카드만 본문이 늘어나고 글자를 줄인다(`king.css` 「PC 카드 보기」). 아래 표 · 클래스 설명은 v4.5.8 기준.

노노카 본인 방송(`item.channel_key == "nonoka"`, `time_tbd` 아님)이 예정 시각을 넘기면 타임테이블 · 오늘 카드에 장식이 붙는다. `preview.json` 필드 `channel_key` · `scheduled_start` · `actual_start` · `time_tbd` · `video_id` 와 (v4.5.8) `announced_start` 를 읽는다.

**판정** `king.phaseOf(item, state, nowMs, playedAt)` (순수 — DOM 없음). `state` 는 `timetable.classify` 의 분류(`upcoming` | `live` | `ended`), `playedAt` = 이 페이지가 그 항목의 입장 연출을 시작한 시각(아직이면 없음).

| 입력 | 결과 |
|---|---|
| `upcoming` 이고 `late = now − scheduled_start` 가 0 초과 ~ 3시간(`MAX_LATE_MS`) | `{phase:"wait", stage, late}` — `lateStage(late)`: ~3분 1 · 3~5분 2 · 5~10분 3 · 10~20분 4 · 20분~ 5 (경계는 이상/미만) |
| `live` 이고 `actual_start − 약속 시각(promisedStart) ≥ 1분`(`ARRIVE_MIN_LATE_MS`) 이고, 아직 재생 안 했거나(`playedAt` 없음) 재생한 지 `ARRIVE_MS`(3.8초) 안 | `{phase:"live", waited, since}` — `actual_start` 뒤 시간 제한 없음 |
| 그 밖(대상 아님 · 종료 · `actual_start` 없음 · 1분 미만 지각 · 이 페이지에서 이미 재생함) | `null` → 장식 없음 / 복귀 연출 후 걷어냄 |

예고(`upcoming`)의 지각은 화면에 보이는 `scheduled_start` 기준이다(`announced_start` 는 안 씀 — 카드 링 「시작까지」와 어긋나지 않게).

**장식 root 와 클래스** — `king.js` 가 root 요소에 붙이고 `root.dataset.king`(`"card"`·`"popup"`·`"block"`) · `root.__king`(상태 객체)을 둔다.
`.k-on` 장식 중 · `.k-s1`~`.k-s5` 지각 단계(누적) · `.k-arrive` 입장 연출 중(`ARRIVE_MS` 3.8초) · `.k-live` 금빛 「입장 후」 모습(v4.5.8 부터 모션 줄이기 · 재생 도중 다시 그려진 경우만) · `.k-leave` 복귀 연출 중(`.k-arrive` 또는 `.k-live` 와 함께 붙음, `LEAVE_MS` 1.2초). 입장 연출이 끝나면(`.k-arrive` 를 붙이고 `ARRIVE_MS` 뒤 — 1초 틱도 `phaseOf` 가 `null` 이면 같은 일을 한다) `leave()` 가 `.k-leave` 를 붙이고(모션 줄이기면 바로 `finish()`), 1.2초 뒤 `finish()` 가 클래스 · 추가한 노드 · 바꾼 글자를 모두 원복한다(보드를 다시 그리지 않고 제자리에서).

**복귀 연출(`.k-leave`)** — 무대(`.kg-scene`)는 썸네일 위에 겹쳐 있어 투명해지면(1.2초) 아래의 평소 썸네일이 드러난다. 대신의 말 칸(`.king-msg`)은 0.5초에 옅어지고 1초에 걸쳐 접힌다(`leave()` 가 현재 높이를 `max-height` 인라인 px 로 고정한 뒤 `.k-leave` 가 0 으로 — 접힘 끝의 `margin-top −4px` 는 카드 `.tcard__main` · 팝업 `.tt-pop__body` 의 `gap 4px` 보정). 블록의 왕관 · 카펫 띠도 옅어진다. 카드 오른쪽 도넛(`.tcard__ring`)은 장식이 아니라 건드리지 않으며, 말 칸이 접히는 동안 세로 중앙 정렬에 따라 제자리로 올라온다. 장식은 링크 요소의 자손이고 `pointer-events:none` 이라 연출 중에도 클릭은 영상 링크로 이어진다. 블록 위쪽에 놓인 팝업은 `timetable.js` 가 `data-anchor-bottom` 에 아래 가장자리를 적어 두고 `king.js repin()` 이 줄어드는 동안 블록에 붙여 둔다.

| 위치 | 함수 · root | 삽입 | 호출 지점 |
|---|---|---|---|
| 모바일 오늘 카드 | `decorateCard(a, th, main, entry, state)` · `a.tcard`(`.k-card`) | `th`(`.tcard__th`) **첫 자식**으로 무대 `.kg-scene`(LIVE · 합동 알약보다 아래), `main`(`.tcard__main`) 끝에 `.king-msg` | `timetable.todayCard` — `laneKey === "nonoka"` |
| PC 블록 팝업 | `decoratePopup(pop, img, body, entry, state)` · `.tt-pop`(`.k-pop`) | `img`(`.tt-pop__img`) 첫 자식 `.kg-scene`, `body` 끝 `.king-msg` | `showCardPop(..., rowKey)` — 노노카 행의 블록에서 연 팝업만. 높이를 재기 **전에** 장식(위치 계산이 높이에 의존) |
| PC 타임테이블 블록 | `decorateBlock(blk, entry, state)` · `.tt-blk`(`.k-blk`) | `.tt-blk__th` 안에 `.kb-crown`(왕관 + 후광 + 궤도 별) · `.kb-zz` · `.kb-flare` · `.kb-sparks`, 블록 끝에 `.kb-carpet` 띠. `.tt-blk__rel`(「지각」 자리) 글자 교체 | `blockEl(..., rowKey)` — `buildTimetable` 이 행 키(`key`)를 넘김 |

`rowKey`/`laneKey` 가 `"nonoka"`(`king.KING_KEY`)가 아니면 아무것도 붙지 않는다 — 노노카가 게스트인 다른 멤버의 합동 방송 · 노노카 방송이 다른 행에 팬아웃된 블록은 대상 아님. 영상 없는 예고 블록은 레인 색 자리표시 위 아바타 동그라미 **윗부분**에 왕관이 얹히도록 `.k-blk .tt-blk__th.tt-ph` 를 아래쪽 정렬(`padding-bottom: 2px`)한다.

**PC 블록 글자**(`blockLabel`): 1~2단계 「행차 준비」 · 3~5단계 「대기 +MM:SS」(1초마다 갱신), 걷어내면 원래 글자.

**색 약속**: 입장 전 = 은빛(`--k-silver*`), 왕관은 움직이지 않음. 입장 순간부터 = 금빛 — 왕관 은빛 층(`.kg-cs`)이 금빛 층(`.kg-cg`)으로 크로스페이드 + 후광(`.kg-halo`) · 궤도 별(`.kg-orbit`) · 금빛 광선(`.kg-rays.kg-gold`) · 광택(`.kg-sweep`). `.k-on.k-arrive/.k-live` 가 `--k-trim`·`--k-glow` 를 금색으로 바꾼다. PC 블록은 아바타가 주인공이라 후광(최대 불투명도 .22~.3) · 발광 · 별(.45)을 약하게 한다.

**입장 연출은 페이지당 항목마다 한 번**: `played` Map(키 = `video_id`‖`id`‖`scheduled_start`)이 연출을 시작한 시각을 기억한다. 보드를 다시 그려 새 root 가 만들어져도 이미 재생이 끝났으면 장식 없음(평소 라이브 카드), 3.8초 안이면 입장 연출을 다시 보여준다. 새로 접속(새로고침)하면 `played` 가 비어 다시 재생한다 — 라이브인 동안 언제 들어와도 입장 연출을 먼저 본다. `.k-arrive` 는 장막이 닫힌 상태에서 열리는 전환이 보이도록 **두 프레임 뒤**에 붙이고, 걷어내기 타이머(`ARRIVE_MS`)는 클래스가 실제로 붙은 순간부터 잰다.
(v4.5.8) **탭이 숨겨져 있으면(`document.hidden`) 재생하지 않고 기다린다**(`k.mode = "await"`, `played` 기록 안 함) — 백그라운드 탭이 폴링으로 라이브를 받았을 때 아무도 안 보는 사이 끝나지 않게. 1초 틱이 탭이 보이는 순간 재생을 시작한다.

**1초 틱**(`ensureTicker`, 장식 root 가 있을 때만 돌고 없으면 멈춤): `[data-king]` 전부에 대해 `phaseOf` 를 다시 계산 — `wait` 이면 단계 변경 · 카운터(`.king-count`) · 블록 글자 갱신, `null` 이면 `leave`(복귀 연출), `live` 이고 `await` 이면 재생 시작. 시계는 클라이언트 시각이다.

**말** `king.speech(kind, stage, waitedMs)`: 머리말 「대신이 고하오」 + 본문. 대신은 왕보다 낮고 신하(시청자)보다 높은 신분이라 왕은 「전하」, 시청자는 「그대들」, 하오체. 3단계부터 「그대들이 기다린 시간」 + 카운터(`+MM:SS`). 입장 = 「전하 납시오!」 + 「그대들이 +MM:SS 기다린 끝에 납시었소!」(기다린 시간 = `actual_start − 약속 시각`). (v4.5.8 전의 입장 후 말 「…그 충심을 기억하겠소.」는 유지 구간과 함께 없앴다.) 문구 전체는 `king.js speech` 가 기준.

**모션 줄이기**(`prefers-reduced-motion`): CSS 가 `.k-on` 안의 애니메이션 · 전환을 끄고, `king.js` 는 입장 연출을 건너뛰고 「입장 후」 모습(`.k-live`)을 `ARRIVE_MS` 동안 보인 뒤 바로 걷어낸다(코드 작성 · 단위 검증만, 실제 화면 확인은 안 함).

**XSS**: 무대 · 왕관 · 말 모두 `createElement`/`createElementNS` + `textContent`(`innerHTML` 금지).

자체 점검: `node src/frontend/js/king.selfcheck.mjs`(48개 — 대상 · 단계 경계 · `phaseOf`(지각 1분 · 라이브인 동안 시간 제한 없음 · 재생 후 `ARRIVE_MS` 경계 · `announced_start` 약속 시각 · 시계 오차) · 복귀 시간 상수 · 말 · 블록 글자). DOM 함수는 호출하지 않는다.

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

### 방송 중 회원 전용 전환 감지 (v4.3.2) — `handlers._probe_live_membership`

- 배경: `videos.list` 응답에는 회원 전용 여부가 없다. 회원 전용 표시(`membership`)는 트윗 문구 · 회원 전용 시작 YouTube 알림 · 예고 자리표시 흡수로만 켜졌으므로,
  일반 공개로 시작했다가 방송 중 회원 전용으로 바뀐 영상은 `False` 로 남았다(2026-10-16 아라레 `NETX7vJNdW8` — 시작 알림이 일반 `sub_start`).
- 동작: **`/wake`** 가 깨운 `video_id` 의 아이템이 `state=="live"` 이고 `membership` 이 거짓일 때만, 그 채널 streams 탭을 `ytdlp_probe.list_streams`(yt-dlp flat, 쿠키 불필요)로 읽는다.
  같은 `video_id` 항목의 `availability == "subscriber_only"` 면 `membership=True` 로 올린다. `/tick` 에서는 호출하지 않는다.
- 규칙: 올리기만 하고 내리지 않는다(풀림 미반영 — 표본 부족). 조회 실패 · 목록에 영상 없음은 빈 결과 → 아무것도 바꾸지 않는다(`try/except` 격리, 로그 경고). 외부 호출은 커밋 재시도 루프 밖에서 1회.
  올렸으면 monitor 이벤트 1건(`flow="preview"`, 「방송 중 회원 전용 전환 감지」). 라이브 종료 판정은 변경 없음(API `videos.list`).
- 실측(2026-10-16): 같은 영상이 flat 목록에서 `live_status=is_live` · `availability=subscriber_only`. 단일 영상 조회(`watch?v=`)는 회원 전용이라 쿠키 없이 실패하므로 목록 방식만 쓴다.

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
  `title`·`title_ko`·`title_raw`·`body_raw`·`body_ko?`·`body_for_llm`·`date`·`time`·`deadline`·`site`·`url`·
  `tweet_url`·`src_handle`·`needs_tl?`·`participants?`·`seen_ids[]`·`first_seen`·`last_updated`·`expires_at`.
  정렬 date→time→id.
  `title_raw`(정규식 제목)·`body_raw`(원문, 600자 컷)는 파싱·번역 품질 개선용 기록 — 프론트 안 읽음, 아카이브까지 이관.
- **`body_ko`** (v4.0.5) = `body_raw` 의 한글 번역(`title_ko` 는 한글 **제목**이라 별개). 팬 화면은 안 읽고, 리포트 팝업 「한글」 칸 ·
  관리 페이지 소식 수정 창이 쓴다. 키가 없거나 `None` = 아직 번역 안 됨.
  - 번역 시점: 접수 단계 `telegram_app._prepare_notice` 가 실제로 올라가거나(added) 본문이 바뀌는(updated) 소식일 때만
    `llm.translate(body_raw)` → 커밋(`_commit_notice`)이 **번역한 본문이 지금 행의 본문과 같을 때만** 저장. dup · recap · skip 은 번역 안 함.
  - 갱신(`_merge_fields`)으로 `body_raw` 가 바뀌면 `body_ko` 를 새 번역(없으면 `None`)으로 — 옛 본문의 번역이 남지 않게.
  - 재시도 · 백필: 번역 sweep(`enrich.collect` — 배포판은 정기 수집 안 `_translate_sweep`, 로컬은 가공 큐)이 `body_ko` 가 없는
    소식을 번역한다. `needs_tl` 플래그는 안 쓴다(제목 번역 전용 그대로). 한 번에 `enrich.BODY_TL_PER_SWEEP`(10)건까지,
    `notices.json` 먼저 그다음 `notice_archive.json`(보관 시각 최근 것부터) — 지난 소식 백필도 이 경로로 나눠 채운다.
  - 관리 페이지 수정(`admin_api.edit_notice` `body_ko`): 원문은 읽기 전용, 한글만 고친다. 비우고 저장하면 `None` → 다음 수집이 다시 자동 번역.
  - 수동 소식 입력(`ingest_notice_manual`)은 본문 = 제목이라 한글 제목을 넣으면 그대로 `body_ko`.
- **`participants`** (v3.2, 선택 필드): 크로스오버 공식 계정(`_CAST_LOOKUP_HANDLES`, 현재
  `bang_dream_on`) 소식만 대상 — 첨부 이미지를 `vision.py`(Groq 비전 OCR, `qwen/qwen3.8-27b`
  — v4.5.9 부터 폴백 없음)로 읽어 5인 중 출연이 확인된 `channel_key` 배열. `telegram_app
  ._maybe_tag_cast_participants`가 `_apply_notice` 파싱 직후 채운다(tweet id 없음·이미지
  없음·OCR 실패·매칭 없음이면 그냥 비워둠 — 일반 소식으로 정상 표시, 무회귀). 프론트는 아직
  이 필드를 읽지 않음(추후 UI 확장 여지).
- **소식 시점 판정** (v4.6.2, 2026-10-21 · 10-22 운영자 결정): 지난 일의 소감 · 감사 · 현장 보고는 소식으로 올리지 않는다(규칙이 아니라 LLM). `telegram_app._prepare_notice` 가 `xnotice.parse` 직후
  `_notice_timing` → `llm.notice_timing(text, posted_jst)` = `{kind: announce|report, subject, subject_date(YYYY-MM-DD|null), evidence[], next_lines[], reason}`(근거 · 다음 일정 줄은 원문 그대로 — 아니면 다시 묻기 5회,
  24시 이상 표기는 다음 날로) → `notices.timing_decision(verdict, 게시일)`: announce = 올림 · report 이고 그 일의 날짜가 게시일과 같거나 뒤, 또는 날짜 미상 = 올리되 `expires_at` 을 게시일 다음 00:00 KST 로 ·
  report 이고 게시일보다 앞 = 안 올림 · (v4.6.3) report 이고 `next_lines` 가 있으면 **그 일의 날짜와 상관없이** 그 줄만 다시 `xnotice.parse` 해서 올림(그 줄이 소식 형식이 아니면 오늘 일은 오늘 자정까지, 지난 일은 안 올림) · 판정 실패 = 올림. 게시일 = 트윗 id(Snowflake), 없으면 지금.
  **판정을 부르지 않는 경우**(Groq 를 아끼려고): 이미 본 트윗(활성 · 보관 소식의 `seen_ids` — `_notice_already_seen`, 커밋에서 어차피 「dup」) · `timing="off"`(관리 페이지 원문 투입 확정 · 텔레그램 수동 소식 — 운영자가 정한 글).
  `timing="show"`(관리 페이지 원문 투입 미리보기)는 판정만 결과에 붙이고(`prepared["timing"]`, 미리보기 경고) 확정하면 그대로 올린다.
  판단 기록 kind `notice_timing`: 안 올림 · 다음 일정만 = 검토용(undo 없음 → 반려 뒤 재판단 · 사용자 판단 「소식으로 올림」(강제 announce) / 「올리지 않음」), 실패 = `undo {type: remove_notice, id}`(반려하면 그 소식을 보관함으로, 다른 소식에 합쳐졌으면 건너뜀).
  옛 정규식 후기 판정(`xnotice._RE_RECAP` · `_RE_RETRO` → `is_recap`, `merge_notice` 의 「후기 + 지난 날짜 → seen_ids 만」)은 없앴다 — `is_recap` 은 호환용 `False`. 「지난 날짜의 새 소식 = skip」은 날짜 안전장치로 남김.
  소급(이미 올라간 소감 글 정리)은 코드에 넣지 않았다 — 10-22 해당 1건(FM802 출연 감사)을 data 브랜치에서 직접 보관함으로 옮김(`archived_reason: recap`).
- **중복 판정** (`_same_group`): `url` 일치 OR `title` 일치(공백 정규화). v2 의 `date + anchor_a/b` 대체.
- `notice_archive.json` = `{ notices[] }` (항목 + `archived_at`, append-only, `id` dedupe).
- `xnotice.parse(text, now_iso, *, tag, title)` — 날짜·시각 둘 다 없으면 / `配信スケジュール`·`出演情報` 면 `None`.
  분류·날짜·URL 은 정규식 전담. `title`/`title_raw` 는 정규식 헤드라인, `title_ko`=None.
- **자동 인입 시 LLM 제목추출·번역** (v3.1.2): `_apply_notice` 가 병합 직후 `llm.notice_title(body_for_llm)` 을
  1회 호출해 `title`(정제된 일본어)·`title_ko` 채움. 실패하면 `needs_tl=true` → 다음 `/tick` 의
  `_translate_sweep` 가 재시도. 운영자 `/translate notice` 는 즉시. (트윗 v3.0.1 인라인 번역과 동일 구조)
  **(v4.6.4) 기존 소식에 합쳐질 때(updated)도 제목을 새 글 기준으로**: `_merge_fields` 가 원문 제목 · 본문을 새 글 것으로 덮는데, 전엔 한글 제목이 이미 있으면
  새 추출 결과를 버려 **원문과 뜻이 다른 한글 제목**이 남았다(10-22 실측 약 15건 — 예: 본문은 筋トレ部, 한글 제목은 RESONEXT). 이제 `_commit_notice` 가
  추출 결과(`tl`)가 있으면 합쳐진 행에도 `title` · `title_ko` 를 덮고, 추출이 실패했으면 옛 한글 제목을 비우고(`None`) `needs_tl` — 다음 번역 sweep 이 다시 채우고 그동안 프론트는 원문 제목.
  이미 잘못 남아 있는 행은 이 수정으로 바뀌지 않는다(다음 병합 때부터).
- **출처 표기** (v4.6.4): 게임 계정(`config/channels.json` `game_accounts`) 글이 소식이 되면(v4.5.10 게임 밖 행사) `src_handle` = 그 계정(`@bang_dream_on`).
  `_prepare_notice` 가 알림 표시명으로 판별(`_game_account_handle`). 전엔 `xnotice._src_handle` 기본값 `@BDP_yumemita` 로 적혔다.
- **분류(`category`)는 아직 옛 정규식 4종**(live · release · platform · etc, `xnotice._category`). 프론트(v4.6.4 소식판)는 6분류 탭으로 **바꿔 읽는다**: `live` → 방송출연(옛 「라이브예고」는 실제로
  대부분 방송) · `release` → 음원·굿즈·출판 · `platform` · `etc` · 모르는 값 → 기타. 새 6분류 값(`live`=오프라인 라이브 · `event` · `broadcast` · `goods` · `game` · `etc`)을 백엔드가 쓰기 시작하면(소식 판독 핫픽스 —
  다음 버전) 이 바꿔 읽기 표를 같이 바꿔야 한다(옛 `live` 와 새 `live` 의 뜻이 다르다).
- `notices.merge_notice(prev, inc, now_iso, *, archive)` → `(new_notices, new_archive, changed, mode∈added|updated|recap|dup|skip)`.
  지난 날짜의 신규 소식은 `skip`. `sweep_expired` → 만료분 아카이브. `edit_notice(prev, nid, patch, now_iso)` — `_EDITABLE`(+`title_ko` · v4.0.5 `body_ko`) 만 대입.

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

## 6-4. 계약 J — `banners.json` / `banners_archive.json` (data 브랜치, v4a)

게임 계정(`bang_dream_on`)이 알리는 **행사**(챌린지 라이브 등)와 딸린 **가챠**를 소식 란 맨 위 카드로 보이는 데이터. `banners.py`.
용어: `docs/TERMINOLOGY.md` 「행사 배너 용어」. 설계 배경: `ref/v4a/v4a_event_banner_design.md`.

- `banners.json` = `{ generated_at, banners[] }`. 행사 항목:
  `id`(`bn_<이름 키 해시>` — 날짜가 바뀌어도 안 변함)·`name_ja`·`name_ko`·`match_keys[]`(소식과 겹침 판정용 정규화 이름)·
  `image_urls[]`(링크만 저장 · 최대 6)·`start_at`·`end_at`(UTC ISO — **둘 다 필수**)·`start_time_tbd?`(날짜만 알려진 시작)·
  `hold`(`null` 또는 `{anchor, until}` — 보류 시작 때 표시한 개최일 · +15일)·`gachas[]`·`src_ids[]`(근거 트윗 id)·
  `first_seen`·`last_updated`·`gacha_only?`(v4.5.10 — `true` = 이벤트 없이 열린 한시 가챠의 **가챠 단독 배너**, 이름 = 가챠 제목 · 하위 가챠 블록 없음. 프론트는 이 값을 안 본다).
  가챠: `{id, title_ja, title_ko, image_urls[], start_at|null, end_at|null}` — 기간이 `null` 이면 행사와 같음(표시도 생략).
- **저장하지 않는 값**: 표시 상태는 현재 시각으로 파생(`banners.derive`) — `hold`(보류, `hold.until` 전) · `announced`(시작 전) · `live`(진행 중) ·
  `gone`(종료 · 보류 만료 · 종료일 없음). `gone` 은 `sweep` 이 `banners_archive.json` 으로 옮긴다. 프론트(`banners.js`)도 같은 규칙으로 숨긴다.
- **올리지 않는 경우**: 기간이 120일 초과(상시 의심, 저장도 안 함) · 같은 행사의 새 사실 없는 재공지 · (v4.5.10) 미션 · 로그인 보너스 · 캠페인 · 시리얼 코드 등 이벤트 · 가챠가 아닌 게임 소식(버림) ·
  게임 밖 행사(소식으로). 밴드 · 멤버는 따지지 않는다(v4.3.3).
  **종료일이 없는 행사는 화면에 안 올린다** — 다만 시작 · 종료가 글 여러 개에 나뉘어 오므로(09-24 글은 시작만, 09-30 글은 종료만 — 실측) 하나만 알면 **대기**
  (`derive` = `pending`)로 저장해 두고 나머지가 채워지면 올린다. 대기는 LLM 에게는 기존 행사로 보이고(`for_llm`), 30일 갱신이 없으면 정리된다.
- **이미지**: 링크만 저장한다(자체 복사 안 함). **X 트윗에서 걸린 이미지 중 행사 키비주얼(로고 · 일러스트 · 개최기간만 있는 온전한 그림)만 쓴다**(2026-10-02 운영자 결정).
  소개 카드 · 방송 화면 캡처 · **가챠 이미지는 쓰지 않는다**(공식 가챠 이미지는 정사각형뿐이고 필수도 아님). 나무위키 등 출처가 불분명한 배너는 쓰지 않는다.
  (v4.5.10) **게임 안의 일을 알리는 글**(판정 1단계)에 첨부 이미지가 있으면 비전(`vision.read_cards`, qwen3.8-27b — Groq 비전 모델은 이것과 제한 프리뷰 하나뿐이라 **폴백 없음**,
  요청당 이미지 3장 · 장당 입력 2048 토큰 · ITPM 7000 이라 429 는 안내 시간만큼 기다려 재시도)으로 카드 속 글자(개최기간은 본문이 아니라 이미지에만 있는 경우가 실측으로 있었다)를 읽어 2단계 추출에 넘긴다.
  **본문이 정본, 이미지 글자는 보조**(본문에 없는 정보만 채운다 · 같은 정보는 본문 표기 — 2026-10-21 운영자 지시).
  `image_roles` 로 이미지마다 event/gacha/none 을 정하고 **event 만 저장**한다. 소개 카드 표지(「イベント情報」 「紹介」 「あらすじ」 등)가 글자에 있으면 코드가 event 를
  none 으로 돌린다(`telegram_app._filter_banner_roles`). 용도를 못 정했으면 이미지를 안 붙인다. 최대 4장을 읽고 항목당 6장까지 저장.
  프론트는 여러 장이면 5초 머문 뒤 다음 이미지가 오른쪽으로 밀려 들어오는 한 방향 슬라이드를 무한 반복(호버 중 멈춤).
- **관리 페이지 수정(2026-10-02)**: 행사 수정 창에서 이름(한글 · 원문) · 시작 · 종료 · **행사 이미지 링크**(한 줄에 하나, 최대 6장, http(s) 만, 비우면 이미지 없음 — 자체 업로드 없음, 입력하면 미리보기) ·
  **가챠 한글 제목 · 가챠 기간**(시작 · 종료, 비우면 「행사와 같음」, 종료가 시작보다 앞서면 거절) · 보류 해제를 고친다(`admin_api.edit_banner` → `banners.edit_banner`).
  트윗 · 소식은 팬 화면이 이미지를 직접 쓰지 않아(트윗은 X 공식 카드, 소식은 이미지 없음) 이미지 수정 항목이 없다.
- **가챠**: 행사 카드 안에 딸린 하위 블록(이미지 없음). `start_at`/`end_at` 이 `null` 이면 행사와 같다는 뜻 — 프론트는 행사와 같은 부분은 적지 않고 다른 부분만 적는다.
- **카드 디자인(확정, 2026-10-02 — 아티팩트 「행사 배너 절충안 상세」)**: 흐린 행사 이미지 배경 + 절취선으로 나뉜 [이미지 | 정보]. 정보 칸 순서 = 행사 제목(한글, 작은 원제) · 날짜(원제와 같은 작은 글씨) →
  딸린 가챠(「함께 진행」 유리 패널) → 종료 일정 박스(행사 종료 / 가챠 종료) → 진행 막대. 모바일(≤640px)은 이미지가 맨 위에 꽉 차고 절취선은 가로.
- **탭 + 카드 1장 (PC, 2026-10-17 사용자 확정 — 아티팩트 「행사 배너 E안 확정 시안」)**: PC 는 행사가 2개 이상이면 위에 **탭 줄**, 아래에 **선택한 카드 1장**만 보인다(나머지 카드는 DOM 에 있되 CSS 로 숨김 —
  `.bnr.has-tabs > .bnr__card:not([data-active="true"])`). 탭 1칸 = 상태 점 · 「상태 · 남은 시간」(`_tabRemain` — 카드 말풍선 · 칩과 같은 기준: 달력 D-n, 당일은 시간 · 분, 개최 전은 「D-n 개최」) · 행사 이름.
  **탭 순서 = 시작 시각순**(`visibleBanners` 그대로, 같으면 id). **처음 열리는 탭 = 가장 급한 행사**(`RANK`: urgent → warn → live → sched → done → hold, 같은 급은 앞쪽).
  탭은 **한 번에 3개**(`TAB_VISIBLE`)만 보이고, 4개 이상이면 양옆 화살표로 **한 칸씩** 이동(끝에서는 그쪽 화살표 비활성). 탭을 고르거나 ←/→ 키로 옮기면 선택한 탭이 보이는 자리로 자동 이동. 행사가 1개면 탭 줄 없음.
  선택(`_sel` = 선택한 행사 id · 탭 줄 위치)은 모듈 상태라 폴링으로 다시 그려져도 유지되고, 선택한 행사가 사라지면 가장 급한 행사로 되돌아간다. 탭을 바꾸면 다시 그리지 않고 표시만 바꾸며,
  카드 높이가 달라지므로 `mew:banners-resize` 이벤트로 소식 목록(`notices.js`)이 펼침 높이를 다시 잰다.
  **모바일(≤640px, v4.3.6)도 탭 + 카드 1장**. 화살표(`.bnr__arrow`)는 숨기고 탭 줄(`.bnr__tabvp`)을 가로 스크롤한다 — 터치는 브라우저 기본 스와이프(`overflow-x:auto` + `scroll-snap-type:x mandatory`), 마우스는 `banners.js` `_wireTabScroll` 의 포인터 드래그(5px 넘게 움직이면 드래그, 드래그 끝의 클릭은 탭 선택으로 치지 않음).
  탭 폭 `min(58%, 220px)`(다음 탭이 살짝 보이게), 높이 44px 이상, 오른쪽 끝 흐림(`.bnr__tabbar::after`)은 끝에 닿으면(`.at-end`) 사라진다. 탭 줄 아래 점 표시(`.bnr__dots`)로 현재 위치를 알린다(모바일만). 탭을 고르면 그 탭이 보이게 스크롤(`scrollTo`, 움직임 줄이기면 즉시), 다시 그려질 때도 고른 탭 위치로 맞춘다. PC 의 3개 단위 화살표 이동(`TAB_VISIBLE`)은 PC 전용.
  이미지 칸 폭 `min(42%, 440px)`(전엔 `min(44%, 300px)`).
  **배너 드래그 (v4.6.4)**: 배너가 2개 이상이면 카드 영역을 좌우로 끌어(손가락 · 마우스, PC · 모바일) 옆 배너로 넘긴다(`banners.js` `_wireCardDrag`). 가로 이동이 세로보다 클 때만 드래그,
  카드 폭의 15%(`DRAG_RATIO`) 이상 끌거나 빠르게 튕기면(`FLICK_V` 0.5px/ms) 넘김 — 왼쪽으로 끌면 다음. 넘길 때는 탭 선택과 같은 `select` 를 써서 탭 · 점 · 탭 줄 · 펼침 높이가 따라온다.
  처음/끝에서는 저항만(고무줄), `touch-action: pan-y`(세로 스크롤 유지), 드래그 끝의 클릭은 무시, 움직임 줄이기면 애니메이션 없이 바로.
- **표시 상태(`banners.derive` · 프론트 `bannerInfo` 가 같은 규칙)**: `hold`(보류) · `announced`/`sched`(개최 전 — **종료일을 몰라도 올린다**, 시작 일시를 굵게 먼저 알림, 종료는 「미정」) · `live` ·
  `warn`(먼저 끝나는 종료까지 **달력 기준 D-3 이내**, 노랑) · `urgent`(먼저 끝나는 종료를 넘김, 늦은 종료만 남음, 빨강) · `done`(행사 · 가챠 모두 종료 — **종료일 자정(KST)까지 회색 「종료」로 표시**) ·
  `gone`(자정 뒤 — 내림) · `pending`(시작을 모르거나, 종료를 모르는데 이미 시작 — 안 올림). **D-n 은 한국 시간 달력 날짜 차이**(시간 올림 아님), 종료 당일은 남은 시간(60분 안이면 분).
- **진행 막대**: 시작 → 행사 · 가챠 중 **늦은 종료를 100%**로, 먼저 끝나는 종료 시점에 점선(막대 세로 폭 안), 점선~100% 는 `///` 무늬. 말풍선 꼬리는 막대의 현재 위치(채움 끝):
  노랑 구간 「(먼저 끝나는 쪽) 종료까지 D-n」 · 빨강 구간 「(늦게 끝나는 쪽) 종료까지 D-n」 — 두 구간 모두 달력 D-n, 종료 당일만 시간(60분 안이면 분).
  평소(청록)는 말풍선 없이 날짜 줄 끝에 칩 문구, 개최 전은 「개최까지 D-n」 말풍선(종료일 미정이면 칩 문구).
  행사 · 가챠 중 **어느 쪽이 먼저 끝나도 같은 규칙**이다 — 영화 「prima aurora」 공개 기념(10/16~11/19, 가챠만 10/25 까지)은 가챠가 먼저 끝나 점선 뒤 25일이 빨강 + 「행사 종료까지 D-n」.
  **(v4.6.0 변경)** ① 빨강 구간 문구가 항상 「n시간」이던 것을 D-n 으로(점선 뒤가 길면 「588시간」이 됐다) ② 「이벤트」 표기를 「행사」로 통일 ③ 모양 — 동그란 손잡이를 없애고 둥근 막대(12px) 하나,
  `///` 무늬는 지난 구간(채움) 위에도 보이고, 점선은 막대 위아래로 삐져나오지 않으면서 밝은 칸 / 어두운 칸이 번갈아 어느 바탕에서도 보인다. 디자인 = 목업 아티팩트 「v4.6.0 테마 목업」(진행 막대 상태별).
- **행사 판정 (v4.5.10 — 2026-10-21 운영자 확정 기준)**: LLM 은 두 가지만 하고, 배너를 어떻게 할지는 코드가 정한다(전엔 `llm.banner_judge` 한 번에 「행사인가 · 무엇을 할까 ·
  기존 어느 배너인가 · 소식인가」를 다 물어 같은 글에도 답이 흔들렸다 — 경위 `ref/v4.5.9/`).
  - 기준: **1순위 = 인게임 이벤트**(게임 속 인물들의 스토리가 있는 이벤트, 예: 챌린지 라이브) + 그 가챠 · **2순위 = 가챠**(인게임 이벤트 없이 다른 행사로 열린 한시 가챠 — 가챠 단독 배너) ·
    **게임 밖 행사 = 소식**(타 기업 · 장소 콜라보 · 오프라인 행사 · 굿즈 등 유저 대상 일반 행사) · **미션 · 로그인 보너스 · 캠페인 등 = 버림**(이 앱은 유메미타 활동 소식이 목적이라 게임 잡소식을 채우지 않는다).
  - ① `llm.banner_scope(text)` → `{scope: in_game|outside, evidence[], reason}`. 근거는 원문에서 그대로 복사한 구절 **목록**(한 구절이면 떨어진 줄을 이어 붙여 실패했다), 원문에 없으면 다시 묻는다.
    `outside` → `_banner_ingest_core` 가 배너를 건드리지 않고 소식 파이프라인(`_maybe_auto_notice`)으로.
  - ② `in_game` 이면 이미지 글자를 읽고 `llm.banner_extract(text, posted_jst, images_ocr)` → `{items: [{kind: event|gacha, status: normal|postponed|cancelled, title_ja, title_ko,
    start_jst, end_jst}], image_roles, reason}` — **적힌 그대로 옮겨 적기만**. 제목은 본문에 있어야 하고 「…」 안쪽 · 본문 표기로 맞춘다(`_banner_title`).
    날짜는 **그 항목 자기 근거 구절**(`start_evidence` · `end_evidence`)에 적혀 있어야 한다(`_jst_in_evidence` — 날짜 · 시각, 明日 등은 게시일 기준). 3회 다시 묻고도 안 되면 그 날짜만 비운다
    (실측: AtoZ 가챠 종료에 이벤트 종료를 빌려 씀). event 는 제목 앞 40자 · 뒤 20자 안에 「イベント」가 있어야 한다(`_near_event_word` — 실측: 13th☆LIVE 「DIMENSIONAL OVERLAP」 공연 이름을 이벤트로 뽑음).
  - ③ 커밋 때(`_commit_banner`, 지금 배너 상태로) `banners.plan_post` → `apply_post`:
    이벤트 = 이름(포함 관계까지, `_similar`) 또는 **같은 시작 시각**의 이벤트 배너가 있으면 그 배너 갱신, 없고 시작 일자가 적혀 있으면 새 배너(종료는 나중 글 · 이미지로 채움 — 개최 전 공지는 종료 미정으로 표시),
    시작도 기존 배너도 없으면 버림 — **같은 이벤트를 별도 배너로 올리지 않는다**(운영자 요구).
    가챠 = 같은 이름의 가챠 · 가챠 단독 배너 갱신 → 같은 글의 이벤트 → **시작 시각이 같은 이벤트**(날짜만이면 같은 날 시작) → 시각까지 있는 시작 **+ 종료가 적혀 있으면** 가챠 단독 배너(`gacha_only`) → 그 밖 버림((v4.6.2 운영자 결정) 종료가 없는 가챠 = 상시 가챠일 수 있어 가챠 단독 배너로 올리지 않는다 — 행사 배너는 한정 기간의 이벤트 + 가챠를 보여 주는 곳. 이벤트 배너는 그대로 시작만으로 올린다).
    기간이 겹치는 것만으로는 붙이지 않는다(옛 `_gacha_host` — 영화 기념 Ave Mujica 가챠가 サイドスロー 에 붙었다). 가챠 단독 배너가 먼저 있고 같은 시작의 이벤트가 오면 이벤트 밑으로 합친다.
    (v4.5.11) 가챠 단독 배너도 이미지를 쓴다 — 이벤트 단계가 없는 글이면 이미지 용도를 가챠 단독 단계에 넘기고, 배너에 이미지가 아직 없을 때만 용도 none 을 뺀 이미지를 붙인다(판정이 없으면 걸린 이미지 그대로).
    프론트는 가챠 단독 배너를 「가챠」로 적고(카드 머리 · 종료 박스 · 말풍선 · 탭) 카드 · 탭에 종류 배지(행사 / 가챠)를 붙인다.
    종류 색(A안): 카드 테두리 · 막대 채움 · 종료 박스 윗선(`data-kind`) · 딸린 가챠 패널 · 고른 탭 = 행사 하늘 / 가챠 분홍, 점선 뒤 무늬 = 늦게 끝나는 쪽 색(`data-late`). 상태 색은 상태 표시 · 말풍선 · 탭 머리에.
    `status` postponed / cancelled 는 찾은 배너를 보류 / 취소(`hold` / `cancel`). 이미지 용도는 첫 이벤트 단계에만.
  - 한 글이 여러 배너를 바꾸면 `undo = {"type": "restore_banner", "items": [...]}` — `banners.restore` 가 거꾸로 한 번에 푼다(합쳐져 사라진 가챠 단독 배너는 `was_removed` 로 되살림).
  - (v4.5.9 이미지 판독 예비, §8.17) ②의 이미지 읽기는 `_ocr_banner_images_ex` — 호출 실패(429 · 5xx)면 본문만으로 계속하고 커밋 뒤 「이미지 판독 대기」에 적는다. 운영자가 허가한 판독은
    같은 글을 다시 이 경로로 돌린다(주입된 글자 `_OCR_OVERRIDE` 를 비전 대신 쓰고, 「이미 반영한 글」 검사를 건너뛰는 `apply_post(check_dup=False)`).
  - 사용자 판단(관리 페이지 「행사로 올림(직접 입력)」 · 「소식으로 올림」)은 옛 단일 판정 형식(`{action, event, gacha …}` → `apply_judgement`) 그대로.
  - 시각은 LLM 이 JST 문자열로 주고 코드가 UTC 로 바꾼다. LLM 5회 실패 → 등록하지 않음(소식과 반대 기본값) + monitor `err`. 같은 글(tweet id) 재전송은 `dup`.
  - 검증: 실측 14건(이벤트 개최 예고 · 스토리 예고 · 보상 · 가챠 · SSR 소개 · 미션패스 · 로그인 보너스 · 한정 미션 · 영화 기념 가챠 · JR 콜라보)을 시간순으로 이어 돌려 기대와 대조(devpapers `ref/v4.5.9/`).
- **날짜 근거 확인 (v4.5.3)**: 이미 있는 날짜(행사 시작 · 종료, 가챠 시작 · 종료)를 **바꿀 때는** 새 날짜가 그 글의 본문 또는 첨부 이미지 OCR 글자에
  실제로 적혀 있어야 한다(`banners.date_evidenced` — 「10月28日」 「10/28」 「10.28」 또는 本日 · 今日 · 今夜 · このあと · まもなく · 明日 가 게시일 기준으로 그 날짜를 가리킴). 없으면 기존 값을 유지하고 상세에 「근거 없는 날짜 변경 무시: …」를 남긴다.
  날짜만 있는 값(「10月18日より」 → 00:00 · 시각 미정)은 같은 날의 시각까지 아는 값을 덮지 않는다. 비어 있던 날짜 채우기 · 새 행사 · 운영자 판단(글자 없음)은 그대로.
  근거 글자는 `telegram_app._prepare_banner` 가 `post["text"]`(본문 + OCR) · `post["posted_at"]` 로 넘긴다. (v4.5.10 부터 판정 LLM 에 현재 배너 목록을 보여 주지 않는다 — `for_llm` 은 쓰지 않음.)
  계기: 2026-10-19 날짜 없는 가챠 소개 글 3건(「10月18日より開催中 … SSR … 紹介」)이 가챠 기간(10/18 15:00 ~ 10/28 14:59)을 행사 종료(10/26 14:59) · 10/18 00:00 으로 덮었다.
  가챠 종료와 행사 종료의 관계는 고정 규칙이 아니다(이 행사는 가챠가 이틀 늦게 끝남) — 날짜는 공지 · 이미지에 적힌 것만 쓴다.
- **대상 (v4.3.3)**: 게임 계정이 알리는 행사 · 가챠 **전부**(밴드 · 멤버 무관). (v4.5.10 에 가챠 처리는 위 「행사 판정」 ③으로 바뀜 — `_gacha_host` 는 `apply_judgement` 안에 남아 있지만 v4.5.10 경로 · 사용자 판단 경로 모두 가챠만 온 판정을 넘기지 않아 쓰이지 않는다.)
- 되돌리기: `_llm_record(kind="banner_judge", undo={"type":"restore_banner", …})` — 변경 전 항목 스냅샷으로 복원, 새로 만든 항목이면 삭제. (v4.5.10) 여러 배너면 `items`.
- 소식과의 중복 방지: 게임 계정 글은 소식 경로를 타지 않고, 다른 계정 글이라도 활성 · 보관 행사의 `match_keys` 가 본문에 들어 있으면 소식으로 올리지 않는다(`banners.covers_text`).

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
- (삭제) `reconcile.py`/`store.py` — v1 잔재, v3 무의존이라 2026-10-20 삭제(현행 판정은 포크한 `preview_build.py`). v1 실행기 `main.py` 와 GitHub Actions `collect.yml` 도 같은 날 삭제 — 한 번도 수동 실행된 적 없고, 결과를 받던 코드 저장소 `data` 브랜치도 같은 날 삭제, 기록 = 태그 `archive/data-2026-09-15`.

### 8.1 `preview.py` (순수 — 네트워크·파일·시계 금지, `now_iso` 인자)

```python
def default_preview() -> dict
def new_id(channel_key, first_seen_iso) -> str                    # "pv_" + sha1[:8]
def make_item(*, channel_key, state, source, now_iso, **fields) -> dict   # 스키마 기본값 + expires_at 계산
def match_item(items, inc, *, superscede_sec=45*60) -> dict | None       # §1-1
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
   · video_id 無 (announced 자리표시): 참여자 채널에 실물 ±45분(v3.8.10, 구 ±4h) → supersede + `_carry_collab`.
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
    def announces_own_broadcast(text_ja, unit_name) -> bool | None     # (v3.6) 텍스트 예고 최종확인 (v4.5.5 근거 필수 · last_reason)
    def duplicate_notice(new_text, candidates) -> str | None           # (v3.7) 같은 날짜 소식 의미 중복판정
```

- Groq REST (`https://api.groq.com/openai/v1/chat/completions`). `reasoning_effort="low"`, `temperature=0`.
  구조화 출력이 필요한 호출만 `response_format: json_schema`(strict), `translate` 는 자유 텍스트.
- api_key 비면 disabled → 모든 호출 None. `_call_groq`: 5xx·타임아웃(20초) → 1초·2초 대기하며 최대 3회 시도,
  그 외 상태(400 등)는 즉시 None. 메인 실패 시 폴백 모델로 같은 호출. 판정 함수 8개(`participation` · `announces_own_broadcast` ·
  `collab_partners` · `broadcast_change_targets` · `duplicate_notice` · `banner_scope` · `banner_extract` · (v4.6.2) `notice_timing`)는 **답이 틀렸을 때만**(JSON 깨짐 · 필드 없음 · 근거 없음)
  (메인→폴백) 쌍을 최대 5회 다시 묻는다.
- **(v4.6.1) 429 — 다시 보내지 않고 그 모델을 한동안 막는다.** `_call_groq` 가 429 를 받으면 재시도 · 대기 없이 None 을 돌려주고, 그 프로세스에서 그 모델을
  일일 한도(429 본문에 `per day` · `(TPD)` · `(RPD)`)면 1시간(`DAILY_BLOCK_SEC`), 분당 한도면 Groq 가 알려 준 대기 시간(`retry-after` 헤더 → 본문 「try again in …」 →
  없으면 60초, 1~600초) 동안 부르지 않는다(`_RATE_BLOCK`, 상태 = `llm.rate_block_state()`). 막힌 모델은 요청 없이 바로 None.
  판정 함수의 다시 묻기도 호출 실패(429 · 5xx · 네트워크 · 막힘)면 바로 끝낸다 — 판정 1건이 보내는 요청은 429 일 때 모델마다 1번(전엔 최대 30번 =
  다시 묻기 5회 × 두 모델 × `_call_groq` 3번). 모델별로 막는 이유: 한도가 모델마다 따로인지 공식 문서로 확인하지 못해, 주 모델이 막혀도 폴백 모델은 한 번 불러 본다.
  호출이 막혀 실패한 경우의 처리는 원래 실패와 같다(번역 = `needs_tl` 로 다음 수집 때 다시 · 판정 = 각 호출부의 실패 처리). 같은 방식의 비전 쪽 차단은 §8.17.
  계기: 2026-10-21 실측 스크립트 · 운영 재시도가 겹쳐 운영 번역이 429 로 실패(Cloud Run 「Groq 429 … 재시도」 72줄 · 「번역 없음」 12줄, 22:10~23:40 KST).
- **(v4.5.5) `announces_own_broadcast` 근거 필수**: 출력 `{announces, evidence, reason}` — `evidence` = 원문에서 그대로 복사한 구절, `reason` = 한 문장.
  근거가 비었거나(reason 5자 미만) 원문에 없는 구절이면(`llm.evidence_in_text` — NFKC 후 글자 · 숫자만 비교, 기호 · 장식 문자 무시) **그 판정을 받지 않고**
  「바로 전 답은 근거가 없었다」를 붙여 다시 묻는다(5회 안, 5회 모두 그러면 None → 미등록 + monitor err). 통과한 근거는 `last_reason` →
  LLM 판단 기록(`own_broadcast`)의 reason 「… (근거: 「…」)」. 프롬프트: 방송 **주제는 따지지 않음**(게임 · 굿즈 소개 · 라이브 회고 · 발표 · 朝活 등),
  플랫폼이 없으면 본인 유튜브 방송, false = 후기 · 감사 · **연기 · 취소 · 휴방(새 날짜가 있어도 — 일정 변경은 `broadcast_change_targets` 가 처리)** · 방송 아닌 일정 · 타인 홍보 · 타 플랫폼 · 날짜 없는 언급.
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

**(v4.5.7) 반각 가나 · 가나 잔존 재요청** — 미야코 트윗 「🍭ﾍﾟﾛｷｬﾝ」 이 번역되지 않고 남았다(실측: 수정 전 3/3 잔존). 원인은 둘이다 — ① 모델이 반각 가타카나를 이모티콘 · 효과음처럼 보고 그대로 둠 ② 번역 뒤 가나 잔존 검사 `_KANA_RE` 가 전각(U+3040~30FF)만 봐서 경고도 없었음.
대응: `translate()` 진입 때 `_widen_halfwidth_kana()` 가 반각 가나 구간(`[ｦ-ﾟ]+`)만 NFKC 로 전각화(「ﾍﾟﾛｷｬﾝ」→「ペロキャン」 — ！ ～ 등 다른 문자는 불변, 모델에 보내는 문장에만 적용하고 저장 원문은 그대로) · 프롬프트 규칙 2 에 「이모지 옆 짧은 가타카나 단어 · 말장난 · 줄임말도 뜻이 분명하면 뜻으로, 불분명하면 한국어 독음으로(ペロキャン→페로캔)」 · `_KANA_RE` 를 반각 가나(U+FF66~FF9F)까지 확대 · 번역에 가나가 남으면 `_retranslate_residual()` 이 남은 글자를 짚어 **1회 재요청**(가나가 줄 때만 채택, 실패 · 환각 · 안 줄면 이전 결과 유지 + 기존 「부분 번역 의심」 WARN). 실측(Groq gpt-oss-120b): 수정 후 「ﾍﾟﾛｷｬﾝ」→「페로캔」 4/4, 「ﾊｯ」「ﾏﾃﾞ」 문장 퇴행 없음.
참고: 메인 모델이 429 로 폴백 모델(20b)로 넘어가면 반각 가나를 더 자주 남긴다(수정 전 실측: 「ﾊｯ」 · 「ﾏﾃﾞ」 잔존 · 「마데」 직역).
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
   announced~end) ∪ woken ∪ (tick 이면) RSS 전부 — (v4.5.0) `WEBSUB_REPLACE_RSS=1` 의 light 틱은 RSS 를 빼고 추적 중인 영상만(`handlers._poll_plan`).
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
`@app.post("/monitor")` (v3.5, v3.8.9 개편) → **매일**(monitor_auto 와 무관) `monitor_snapshot.run_daily`:
전일(06:00 KST 경계) 하루치를 `monitoring/days/{날짜}.json` 에 굳히고 `monitoring/summary.json` 에 요약 한 줄을
추가(요약 = `{"triggers","events"}`, 그날 이벤트 로그 파일이 없으면 숫자 대신 `{"no_log": true}`). 백필:
`backfill_complete` 가 false 면 `monitoring/` 의 `events-*.jsonl` 목록으로 로그 파일이 있는 과거 날짜만 채우고,
이후엔 마지막 요약 날짜 다음 날~전날 누락분을 채운다(실행당 최대 10일, 남으면 다음 실행이 이어서).
외부 조회(healthchecks.io 다운 구간·Vercel 배포 시도 수) 실패/키 없음은 `null` 로 저장(조회 여부를 데이터에 남김).
Vercel 수치(`vercelDeploys = {total, production, preview, error}`)는 Vercel REST API `/v6/deployments`
(Secret `VERCEL_TOKEN`)로 그날 06:00~익일 06:00 KST 배포 시도를 센다 — Hobby 하루 100회 한도엔 브랜치·성공
여부 무관하게 다 잡히므로 total 기준.
표시: Vercel 은 "확인 불가", 백엔드 상태는 기존 합의대로 다운 없음=정상으로 그리고 툴팁에 "미조회"만 밝힌다
(healthchecks.io 를 날짜마다 몰아 부르지 않기 위한 근사). 스냅샷엔 `snapshotAt`(조회 시각)·`hasLog` 동봉. 이어서 `monitoring/latest.html`(전날 상세 +
전 기간 잔디)을 커밋하고, `monitor_auto` 가 켜져 있을 때만 "오늘의 멤버 현황"(멤버별 트윗 수집 ✓/✕ · 라이브 구간 ·
소식 등록 성공/실패) **텍스트 DM**. v3.8.8 까지의 일간/월간(매월 1일)/연간(1월 1일) HTML 자동 DM 은 폐지(수동
`/monitor [--monthly|--yearly|날짜]` 는 그대로 HTML).
제어 채널(`telegram_app`)의 `@app.get("/monitor-live")` (v3.7.2) → 웹 `monitor.html` 이 부르는 읽기 전용 공개
라우트. (v3.8.9) **전 기간(all) 리포트** — 상세는 "오늘"(가장 최근 06:00 KST~지금)만 즉석 생성(60초 캐시), 지난
날짜는 `summary.json`(10분 캐시)로 잔디만 그린다(오늘 칸은 실시간 값). `@app.get("/monitor-live.json")` 은 같은
데이터(60초 자가갱신 폴링용). `@app.get("/monitor-live/day.json?date=YYYY-MM-DD")` (v3.8.9) → 잔디 칸 클릭 시 지난
날짜 상세: 스냅샷이 있으면 그대로(메모리 캐시, 불변), 없으면 이벤트 로그에서 즉석 계산(저장 안 함, `snapshotAt:
null`, 10분 캐시). 오늘 이후 날짜는 400. 모두 CORS `*`, 실패 시 500 — `monitor.html` 이 `latest.html` 로 폴백.
`@app.get("/")` → "ok" (`/healthz` 는 GFE 가 가로챔).
(v3.8.9) 제어 채널 웹훅 `/telegram` 은 요청마다 모니터 로그 `flow="cmd"` 1줄(`who`=명령어, `detail`=원문 120자 —
`/` 로 시작 안 하는 후속 입력은 12자 이하 한 줄만, 그 외 글자 수만, `reply`=마지막 응답 DM 첫 줄, `result`=응답
DM 문구 기반 근사: 예외·⚠️/❌ → err, "사용법"·응답 누락 → degraded, 그 외 ok) → 웹 monitor 타임라인 "💬 운영자
명령" 행(트리거와 백엔드 상태 사이).
(v3.8.9) `POST /ingest` 는 알림 1건마다(403 제외) 모니터 로그 `flow="upstream"` 1줄(`source`=x|yt, `who`=
`android.title`, `detail`=응답 본문에서 읽은 갈래, `result`=HTTP 4xx/5xx 또는 ok=false → err, 그 외 ok) → 웹 monitor
"🛰️ 업스트림 감지" 행(백엔드 상태 바로 위, 구 "X 예고 릴레이" 행 대체)과 트리거 📥 의 기준.
(v3.8.9a) 하루치 상세의 `upstream`·`cmd` 는 실제 기록 + 그날 첫 실제 기록 이전 시각의 **복원분**(`derived: true`,
`monitor_report._derive_upstream`/`_derive_cmd`)을 합친 것 — 업스트림은 `/ingest` 한 요청의 기록 규칙대로(개인 트윗 =
(ts, 멤버) 1건, 공식 = 최종 relay `mode: …` 1줄 1건 + 같은 초 소식 부착, `mode: yt-member-live` = YouTube 1건), 명령은
ops·`/del`·`/edit` preview 기록·via=ops 인입에서. via 없는 옛 기록·`[백필]` 기록·로그 없는 요청은 복원하지 않는다.
트리거 📥 = `upstream` 건수. 그날 이벤트가 전부 `[백필]`(실시간 모니터링 2026-09-15 이전)이면 상세에 `backfillOnly: true`,
요약 항목은 `{"backfill_only": true, "events": N}` — 트리거 수를 단정하지 않는다(잔디 `?`).
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

### 8.15 신곡 자동 감지 · 곡 관리 — `songs.py` + `handlers._detect_new_songs` + 어드민 음반 탭 API (v4.2.0)

곡은 그룹 공식 채널이 아니라 **뮤타입 음원 채널**(YouTube 가 음원 배포로 자동 만든 채널 「`Mugendai MewType - Topic`」, `UCeXzCxZsDcaF5xI68fK5owA`)에 올라온다 — 방송이 아니라 `preview.json` · FSM(`preview_build`)과 무관하므로
방송 파이프라인에 끼우지 않고 별도 경로로 둔다. `config/channels.json` 최상위 `song_feeds`(`channels` 와 별개 키 — 방송 쪽이 읽지 않음)에 채널을 둔다.

**곡 문서 `songs.json`**(data 브랜치) = `{"songs": [...], "rejected": [...], "seen": [...]}` — 프론트 플레이어는 `songs` 만 읽는다.
- 곡: `{id(video_id), title, kind(original|cover), who, date, reading, added_at?, manual?, edited_at?, needs_reading?, reading_manual?}`.
  `needs_reading` = 외부 LLM 독음을 아직 못 채운 곡(다음 tick 이 재시도) · `reading_manual` = 운영자가 직접 정한 독음(LLM 이 덮지 않음) · `edited_at` = 운영자 수정 시각(반려가 덮어 지우지 않는 근거).
- `rejected`: 삭제 · 반려한 곡 `{id, name_key, title, ts, by}`. **RSS 최근 15건에 곡이 남아 있어도 다시 등록되지 않게 한다**(영상 ID · 곡명 키 둘 다). 차단 해제 가능(최대 500건).
- `seen`: 이미 판단 기록을 남긴 「곡명 중복 건너뜀」 `{id, reason, ts}`(같은 건너뜀을 tick 마다 다시 기록하지 않게, 최근 200건).

**감지**(① 매 `/tick` — light 10분 · baseline 06:00 JST, 실제 배포 Cloud Scheduler 값 · wake 제외. ② (v4.5.0) PubSub 알림 — 아래 §8.16. `WEBSUB_REPLACE_RSS=1` 이면 light 틱은 건너뛰고 baseline 만): `song_feeds` 의 RSS(쿼터 0)를 읽고 `songs.json` 과 비교해 **즉시 등록**(승인 대기 없음).
- **규칙**(운영자 결정 2026-10-06): ① **곡명이 이미 있으면 등록 안 함**(영상 ID 가 달라도 — 앨범마다 같은 곡이 새 영상으로 올라온다) · 곡명 비교는 NFKC · 대소문자 · 공백 · 꼬리표 무시
  ② 제목 끝 **「(Cover)」**(대소문자 · 전각 괄호 무관)가 있으면 `cover`, 없으면 `original`. 다른 표기(「(Solo)」 등)에 대한 규칙은 두지 않는다 ③ `feat.` 곡은 등록 안 함
  ④ 같은 곡명이 한 묶음에 여럿이면 먼저 올라온 영상 하나만 ⑤ 반려 목록(`rejected`)에 있는 영상 · 곡명은 등록 안 함 ⑥ `who="group"`, `date`=공개 시각의 KST 날짜.
  건너뜀 사유는 `name_dup`(어느 곡과 같은지 `dup_of`) · `feat` · `id_dup` · `rejected` 로 구분해 돌려준다(`find_new_songs` → `(새 곡, 건너뜀)`).
- **독음은 외부 LLM(Groq)이 쓴다**(`llm.song_reading` — 일본어는 히라가나, 영문 곡명은 가타카나 발음. 가나 · 영숫자 외 응답은 버림). 실패하면 `reading=""` + `needs_reading=True` 로 남아
  **이후 tick 이 재시도**(tick 당 최대 3건, 신곡 + 재시도 합산). 운영자가 독음을 직접 고치면 `reading_manual` 이 돼 LLM 이 덮지 않고, 독음을 비우거나 「독음 다시 만들기」를 하면 LLM 이 다시 쓴다.
- **판단 기록 · 이벤트**: 등록 1곡 = `llm_actions.json`(ops) 기록 `song_register`(`by="rule"`, undo = `{type:"remove_song", id, title, added_at}`, input = RSS 항목 스냅샷),
  곡명 중복 건너뜀 1건 = `song_skip`(검토용, undo 없음, `seen` 으로 한 번만). 둘 다 작업 탭 「LLM 판단」에 보이고 반려할 수 있다. 모니터 이벤트 `flow="song"`
  (`action` = added · skipped · reading · rss_empty — 어드민 조작은 `via="ops"` 로 edited · deleted · added_manual · unblocked · rejected · reading_regen)가 같은 이벤트 로그(보관 · 스냅샷 · 리포트 전 기간)에 쌓여 리포트 타임라인 「🎵 신곡 감지」 레인에 점으로 나온다.
  RSS 가 비어 있으면(조회 실패 포함) 그 시간의 첫 tick(분 < 10)에만 degraded 이벤트 1건 — 시간당 1회. 상세 상태는 어드민이 「지금 RSS 조회」로 본다(`songs_status`).
- **쓰기 경로**: 감지 쪽은 tick 안에서 gh 로 **직접** 쓴다(`/write` 자기 호출은 `concurrency=1` 교착 — `record_video_releases` 와 같은 방식; 한 tick 에 songs.json 1번 + 판단 기록 1번(배치) + 이벤트 1번 이하,
  기록은 songs.json 쓰기 **성공 뒤에만**). 어드민 편집은 `/write` 직렬화(writers kind `song_edit` → `telegram_app._song_edit_commit`, sha 충돌 재시도 4회). 외부 LLM 호출은 호출부가 먼저(A-1).
- **안전**: `songs.json` 이 없으면(시드 전) 새로 만들지 않고 건너뜀. 쓰기 충돌(409)은 다음 tick 이 같은 RSS 로 다시 계산. **어떤 실패도 tick 을 막지 않는다.** 한계: RSS 는 최근 15건 — 한 번에 15곡을 넘는 버스트는 고려하지 않음.

**어드민 화면**(`admin_static/admin.html`, 목업 `ref/v4.2_admin_mockup.html`): **현황 탭**(세부 탭 예고 | 소식 | 트윗 — 소식 세부 탭은 행사 배너 + 소식이 한 목록 칸, 행사(b)·소식(n)은 상세창을 같이 쓰므로 선택 · 펼침을 목록 칸 전체 기준으로 하나만 유지) ·
**음반 탭**(신곡 감지 상태 카드 · 곡 목록 · 수정 · 삭제 · 직접 추가 · 차단 목록/해제 — 시드 전에는 쓰기 버튼 비활성) · 작업 탭 신곡 판단(`llmKindLabel` · `undoDescribe` · `buildDecideForm` 신곡 양식, 재판단 버튼 없음).
곡 직접 추가는 제목 · 날짜를 비워 두면 `add_song` 이 RSS → YouTube API 순으로 채운다(별도 「불러오기」 호출 없음).

**어드민 API**(`admin_api` · 계약 `ref/v4.2_admin_api_contract.md`): 읽기 `list_songs`(곡 · 차단 목록 · 카운트 · 한글 독음 미리보기) · `songs_status`(시드 여부 · **지금 RSS 조회**(쿼터 0) · 등록 예정/건너뜀 dry-run · 최근 `song` 이벤트 7일),
쓰기 `edit_song` · `delete_song`(= 삭제 + 재등록 차단) · `add_song`(YouTube URL/ID → RSS → videos.list 순으로 제목 · 날짜를 채워 보고, 안 되면 직접 입력 · 곡명 중복은 force) · `unblock_song` · `regenerate_song_reading`(독음 다시 만들기).
**작업 탭 반려**: `song_register` 반려 = 목록에서 지우고 `rejected` 에 추가(그때 등록한 그대로일 때만 — 운영자가 그 뒤 수정했으면 건너뜀) → 사용자 판단 = 다른 값(제목 · 구분 · 부른 사람 · 날짜)으로 다시 등록.
`song_skip` 반려 → 사용자 판단 = **강제 등록**(곡명이 같아도 다른 곡). 규칙 판단이라 **LLM 재판단은 없다**(`llm_review_options.rejudge=false`, 요청하면 오류).
- self-test: `python -m src.backend.songs`(60건 — 분류 · 곡명 키 · 실제 RSS 발췌 `fixtures/topic_feed.sample.xml` 감지 · 건너뜀 사유 · 삭제 · 차단 · 해제 · 수정 · 직접 추가 · 독음 채우기 · 가나→한글),
  `python -m src.backend.handlers`(`_detect_new_songs` 가짜 gh · 가짜 LLM — 등록 · 판단 기록 · 이벤트 · 멱등 · 반려 재등록 차단 · LLM 재시도 · 시드 전/충돌/예외),
  `python -m src.backend.admin_api`(로컬 저장소 통합 흐름 — 감지 → 반려 → 재감지 안 됨 → 사용자 판단 재등록 → 삭제 · 차단 해제 · 직접 추가 · 수정 · LLM 독음 실패 재시도 · 재요청).

---

### 8.16 PubSub(WebSub) 수신 — `websub.py` + `handlers.detect_songs_from_push` (v4.5.0, 버스트 대비 v4.5.2)

YouTube 채널 피드의 변경(새 영상 · 예약 생성 · 제목/설명 수정)을 허브(`pubsubhubbub.appspot.com`)가 우리 주소로 **POST** 해 준다 — RSS 폴링 없이 약 1분 안에 발견.
(WebSub = 옛 PubSubHubbub, 웹훅 방식. GCP Cloud Pub/Sub 과는 다른 서비스.) 시험 결과 · 설계 배경 `ref/pubsub_probe/PUBSUB_VS_POLLING.md`.

**구독 대상**(`websub.subscriptions`): 멤버 5명의 채널 + 뮤타입 음원 채널(`song_feeds`). 그룹 공식 채널은 RSS 와 같은 이유로 제외(노래 영상이 합동 방송으로 올라옴).
구독 이름 = 멤버 키(`arale` …) · `song-<song_feeds.key>`. 콜백 주소 = `<접수 서비스 URL>/websub/<이름>`.

**콜백**(접수 서비스 `mewtype-telegram`, `websub.register_callbacks`):
- `GET /websub/<이름>` — 허브 검증. `hub.mode`(subscribe|unsubscribe) · `hub.topic`(우리 채널의 피드 주소) · `hub.challenge` 를 확인하고 challenge 를 그대로 돌려준다. 이벤트 `action=verify` 기록.
- `POST /websub/<이름>` — 알림(Atom). **인증 = `X-Hub-Signature`**(`<algo>=<hex>`, `hub.secret` 으로 만든 본문 HMAC — sha1/256/384/512, 상수 시간 비교). 서명이 없거나 틀리면 **2xx 로 받고 무시**
  (WebSub 규약 — 허브 재시도 방지), 이벤트 `action=reject` 는 프로세스당 10분에 한 번만. 비밀 `WEBSUB_SECRET`(Secret Manager) 이 없으면 503.
  - 멤버 채널 → **영상 ID 만** 쓴다: **즉시 확인 1건**을 PubSub 전용 큐(`WEBSUB_QUEUE`, 아래)에 예약(Cloud Tasks `/wake`, 본문에 `websub: {who, title, attempt:1}`. 이름이 영상 ID + 분이라 같은 분의 같은 알림은 흡수). 판정은 wake 의 `videos.list` 가 한다 — 알림 본문은 판정에 안 쓴다.
    (v4.5.2) 「2분 뒤 한 번 더」는 쓰기 서비스가 건다 — 첫 확인에서 `videos.list` 가 그 영상을 아직 모를 때만(신규 영상 반영 지연) `WAKE_RETRY_SEC`(120초) 뒤 `attempt:2` 를 같은 큐에 예약하고, 두 번째에도 없으면 더 걸지 않고 warn 으로 기록(`handlers._websub_followup`). v4.5.0 은 접수 서비스가 알림마다 두 번을 무조건 걸었다.
  - 뮤타입 음원 채널 → 본문 항목(`video_id` · `title` · `published`, RSS 항목과 같은 필드)을 쓰기 작업 `song_push` 로 PubSub 전용 큐에 적재 → `handlers.detect_songs_from_push` → `_detect_new_songs(via="push")`.
    곡명이 이미 있으면 건너뛰므로 같은 알림이 여러 번 와도 한 번만 등록. 쓰기 충돌 · 독음 작성 실패는 예외로 던져 Cloud Tasks 가 재시도(최대 5회), 그래도 안 되면 일일 baseline 이 안전망.
  - 예약 · 적재가 실패하면 **503** 으로 응답해 허브가 알림을 다시 보내게 한다(이벤트 `notify_fail`). 삭제 알림(tombstone)은 서비스 로그로만 남긴다. 항목의 채널 ID 가 구독 채널과 다르면 무시.
  - (v4.5.2) **알림 POST 는 커밋 없이 응답한다** — 수신 기록 `notify` 는 그 확인(또는 `song_push`)을 처리하는 **쓰기 서비스**가 남긴다. 쓰기 서비스는 한 번에 하나만 처리하므로 `monitoring` 브랜치 커밋이 서로 부딪히지 않는다.
    v4.5.0 은 접수 서비스가 알림마다 커밋해, 10건 이상이 몰리면 같은 이벤트 파일에 동시 커밋이 몰려 충돌 · 응답 지연(최대 약 25초) · 기록 유실이 났다(스테이징 실측, `docs/VERSION.md` v4.5.2).
    접수 쪽 커밋은 드문 경우(서명 불일치 `reject` — 10분에 한 번 · 예약 실패 `notify_fail`)만 남았다.

**PubSub 전용 큐 `WEBSUB_QUEUE`**(v4.5.2, 운영 `mewtype-websub` · 스테이징 `mewtype-websub-stage`, `deploy/setup.sh` 가 만든다): 동시 1건 · 초당 0.2건(5초에 1건) · 쓰기 서비스가 바빠 거절(429)하면 5초부터 다시(최대 20회).
쓰기 서비스(동시 1건)가 PubSub 확인으로 쉬지 않고 바빠지지 않게 해 그 틈으로 접수 서비스의 동기 쓰기(트윗 저장 등)가 들어가게 하려는 것. 단 Cloud Tasks 가 순간 허용량(burst)을 10 으로 자동 설정해 **처음 10건 정도는 제한 없이 연달아** 나간다(실측: 12건이 약 3.5초 간격) —
버스트 개선의 대부분은 큐 속도보다 접수 커밋 제거와 확인 횟수 절반에서 왔다. 큐가 없으면(env 미설정 · 로컬 시험판) 기본 큐로 예약한다. 예고를 지울 때의 예약 취소(`apply.cancel_video_checks`)는 이 큐의 `wake-<영상>-` 도 지운다.

**구독 갱신**(쓰기 서비스 `POST /websub-renew`, Cloud Scheduler 매일 KST 06:20, OIDC): 6개(멤버 5 + 뮤타입 음원 채널 1) 구독 전부 `hub.mode=subscribe`(`hub.verify=async` · `hub.lease_seconds=432000`=5일 · `hub.secret`)를 다시 보낸다(멱등 — 임대 갱신).
허브가 곧바로 검증 GET 을 보내고 콜백이 `verify` 를 기록한다 — **`verify` 가 로그에 보이면 구독이 살아 있다**. 갱신 잡은 갱신 **전에** 최근 3일 `flow=websub` 이벤트를 읽어 `verify` 가
36시간 넘게 없는 구독을 찾아 DM 한다(이전 `renew` 기록이 없으면 첫 실행이라 판정 불가). 요청 실패(202/204 아님)도 DM. 결과는 이벤트 `action=renew`(문제가 있으면 warn).

**모니터 이벤트 `flow="websub"`**: `verify` · `notify`(영상 ID · 제목 · 확인 결과 — 쓰기 서비스가 기록, v4.5.2) · `renew` · `reject` · `notify_fail`. 웹 monitor 리포트에는 아직 레인이 없다(이벤트 로그 파일에서 본다).
(v4.5.2) `notify` 는 `merge_key`(`websub-notify:<영상>`)로 **같은 영상이 10분 안에 또 오면 새 줄 대신 기존 줄의 `count` 를 올리고 `last_ts` · `detail` 을 갱신**한다(`monitor_log._apply_merges`). 같은 분의 반복은 Cloud Tasks 이름 중복으로 확인 자체가 1번이라 count 에도 1번으로 잡힌다(매 알림은 접수 서비스 Cloud Run 로그 「PubSub 알림」 줄).
`flow="song"` 의 `added` 이벤트에 `via`(tick|baseline|push)가 붙는다 — **`WEBSUB_REPLACE_RSS=1` 인데 `via=baseline` 으로 곡이 등록되면 푸시가 못 잡았다는 뜻이라 warn** (추가 감시 없이 푸시 실패를 알아채는 장치).

**RSS 대체 스위치 `WEBSUB_REPLACE_RSS`**(쓰기 서비스 env, 기본 0): 0 = 알림도 받고 폴링도 그대로(이중 운영 · 롤백). 1 = 10분 light 틱이 RSS · 신곡 감지를 생략하고(`handlers._poll_plan`),
이미 추적 중인 영상의 재확인만 한다. **일일 baseline(JST 06:00)은 RSS · 신곡 감지를 그대로 해 안전망**으로 남는다. 켜기 전에 `verify` 기록으로 구독이 살아 있는지 확인할 것.

**검증되지 않은 가정**: ① 허브가 `hub.secret` 을 준 구독의 알림에 `X-Hub-Signature` 를 실제로 보내는지(시험기는 서명 없이 구독해 헤더를 기록한 적이 없다 — 첫 실알림에서 `reject`(헤더 없음)가 뜨면 이 가정이 틀린 것),
② 허브가 허용하는 최대 임대, ③ 허브의 재시도 정책, ④ 뮤타입 음원 채널(자동 생성 채널)이 푸시를 실제로 보내는지(시험 기간 신곡 없음). ④ 는 baseline 안전망이 받아 주고 `via=baseline` warn 으로 드러난다.

### 8.17 이미지 판독 대기 · 예비 판독(Cloud Vision) — `cloudvision.py` + `telegram_app._ocr_pending_*` + 관리 페이지 작업 탭 (v4.5.9)

Groq 비전(`vision.py`, `qwen/qwen3.8-27b`)이 이미지를 **읽지 못하면**(429 · 5xx · 네트워크 — 「글자 없음 · NONE」은 실패가 아님) 자동 경로는 지금처럼 본문만으로 처리를 계속하고,
그 글을 **이미지 판독 대기**(ops `ocr_pending.json`)에 적어 운영자에게 DM 한다. 운영자가 관리 페이지 작업 탭 「확인 필요」 하위 탭의 「이미지 판독 대기」 카드에서 허가하면
**예비 판독 = Google Cloud Vision 텍스트 감지**로 읽어 같은 경로를 다시 탄다. **Cloud Vision 은 자동으로 부르지 않는다**(2026-10-21 운영자 결정).
계기: 2026-10-21 실험이 같은 키(조직 단위 한도)의 Groq 비전 일일 토큰 200,000 을 193,767 까지 써서 운영 OCR 이 막힐 뻔했다. Groq 비전에는 쓸 수 있는 다른 모델이 없다
(문서상 qwen3.8-27b 와 제한 프리뷰뿐, 옛 폴백 qwen3.6-27b 는 404 — 기본 폴백 제거).

- **대상**: 행사 카드 OCR(`_prepare_banner` → `kind=banner`) · 그룹 영상 참여 멤버 OCR(`_ocr_cast_keys` 상태 `failed` → `_record_group_pending` → `kind=cast_group`).
  소식 참여 멤버 OCR(`_maybe_tag_cast_participants`)은 제외 — 대상 계정(`bang_dream_on`) 글이 v4a 부터 소식 경로를 안 타고, `participants` 도 화면에서 안 쓴다.
- **일일 한도 429**: `vision._call` 이 본문의 `per day` · `(TPD)` · `(RPD)` 를 보면 재시도 · 대기 없이 실패하고, 그 프로세스에서 1시간(`DAILY_BLOCK_SEC`) 동안 Groq 비전을 부르지 않는다(`groq_vision_state`).
- **ops `ocr_pending.json`** = `{items[], usage{"YYYY-MM": 건수}, groq{state, at}, last_dm_at}`. 항목 = `{id, kind, status: pending|done, acct, tag|video_id, tweet_url, raw|title,
  media[], reason, current(본문만으로 처리한 결과), created_at, last_seen, (처리 뒤) done_at, engine, units, result, ocr_preview, note}`. 같은 글 · 같은 영상의 대기는 한 줄(갱신).
  48시간 지나면 정리. 쓰기 = 적용 큐 작업 `ocr_pending`(`_ocr_pending_commit` op add · update · remove · reserve · dm_mark). DM 은 1시간에 한 번(`_OCR_DM_GAP_SEC`), 알림 레벨과 무관.
- **월 상한**: Cloud Vision 에는 월 할당량이 없어(분당만) 앱이 센다 — 허가 때 `reserve`(이미지 수만큼 이번 달 `usage` 에 먼저 더함, `cloudvision.MONTHLY_CAP`=900 을 넘으면 거절) 뒤에 호출.
  요금(2026-10-21 공식): 이미지 1장 = 1단위, 월 1,000단위 무료, 넘으면 1,000단위당 $1.50.
- **허가 뒤 다시 처리**(`_ocr_fallback_apply`): 행사 배너 = 판독 글자를 `_OCR_OVERRIDE` 로 주입해 `_banner_ingest_core` 를 다시 돌린다(같은 글이라도 `recheck` 로 「이미 반영한 글」 검사를 건너뜀 —
  `apply_judgement(check_dup=False)` — v4.5.10 부터 `apply_post(check_dup=False)`, 판단 기록 사유에 「[이미지 판독 Cloud Vision]」, 반려 가능). 그룹 영상 = 판독 글자에서 5인 **정식 이름**(`xrelay.FORMAL_NAME_TO_KEY`, 곡 크레디트 줄 제외)을
  찾아 확인 대기 항목의 제안 멤버로 넣는다(확정은 지금처럼 예고 탭). 「Groq 로 다시」(마지막 실패 1시간 뒤부터)는 같은 처리를 Groq 비전으로.
- **관리 API**: `list_ocr_pending`(읽기) · `read_ocr_pending(item_id, engine=cloud|groq)` · `dismiss_ocr_pending(item_id)`. 작업 탭 버튼 배지 = 대기 건수(1분마다 갱신).
- **첫 입장 팝업**: 대기가 있으면 관리 페이지에 들어올 때 「지금 확인해 주셔야 할 작업이 있습니다」 → 「지금 확인하기」 = 작업 탭 「확인 필요」 하위 탭. 「다시 보지 않기」는 그 로그인 세션 동안만(세션별 CSRF 토큰의 짧은 해시를 `localStorage` `mew.admin.attnHide` 에), 배지는 그대로.

**작업 탭 구성 (v4.5.9, 운영자가 고른 시안 D — 아티팩트 「작업 탭 재구성 시안」)**: ① 요약 카드 3장(확인 필요 · 시스템 = 지금 상태 타일 중 가장 나쁜 것 · 다음 예정 = 첫 예약 + 예약 · 번역 대기 · 오늘 실패, 누르면 그 하위 탭) ② 하위 탭 [타임라인 · 확인 필요 · 예약·대기 · 시스템 상태](`#jobs-tab[data-sub]`) ③ 타임라인 = 흐름(경로 재생) · 자동 처리(배포판 = 이벤트 로그) · 내 조작(`list_history`)을 시간순 한 줄로, 시간대 머리줄(「오늘 16시」)로 묶고 칩 [전체 · 알림 · 방송 확인 · 자동 처리 · 내 조작 · LLM 판단 · 멈춤·진행 중 · 실패만]. 로컬은 관리 조작도 흐름이 되므로 흐름에 관리 조작이 있으면 내 조작은 빼 겹치지 않게 한다. 흐름을 누르면 PC 넓은 화면(≥1100px)은 오른쪽 상세, 좁으면 그 줄 아래로 펼침. 옛 「최근 자동 처리」 · 「내가 한 조작」 칸은 타임라인으로 합쳤다.
- **배포**: `vision.googleapis.com` 활성화 · 접수 서비스 실행 계정(INVOKER_SA)에 `roles/serviceusage.serviceUsageConsumer`(`deploy/setup.sh`). 키 없음(서비스 계정 인증).

## 9. 프론트엔드 모듈 (`src/frontend/`)

- **index.html**: `<head>` 에 `<meta name="color-scheme" content="dark light">` + 테마 결정 인라인 스크립트(아래) + css(맨 끝 `theme.css`) +
  Vercel Web Analytics(아래) + `<script type="module" src="js/main.js">`. body 는 `#notice` + `#board` + `#player-dock` + `#pager-dots` + `#foot`.
- **밝게 / 어둡게 테마 (v4.6.0 — 그 전엔 어둡게 전용).** 테마 = `<html data-theme="light|dark">`.
  - **처음 정하기**: head 인라인 스크립트가 CSS 보다 먼저 정한다(첫 화면이 다른 테마로 깜빡이지 않게) — 저장된 선택(`localStorage` `theme`)이 있으면 그것,
    없으면 기기 설정(`prefers-color-scheme: light` 면 밝게, 그 밖은 어둡게). 저장소를 못 쓰는 환경(시크릿 모드 등)은 기기 설정만 따른다.
  - **전환 버튼**(`js/theme.js` `themeButton`): 소식 막대(`.ntc__bar`)의 **마지막 칸**(▾ 오른쪽, 같은 높이 · 같은 세로 구분선). 아이콘 = 지금 테마(어둡게 = 달, 밝게 = 해 — BPM 테마 토글과 같은 방식).
    누르면 반대 테마로 바꾸고 그 선택을 저장(다음 방문에도 유지). 버튼은 한 번만 만들고 `notices.js` 가 막대를 다시 그릴 때마다(75초 폴링 · 소식 0건 막대 포함) 같은 버튼을 옮겨 붙인다.
    소식 막대 · 펼친 목록 폭은 v4.5.x 와 같다(버튼이 막대 안 한 칸을 쓰고 티커 글자 자리만 그만큼 줄어든다, 모바일은 ▾ · 전환 두 칸을 2.25rem 으로 좁힘).
  - **기기 설정 따라가기**: 한 번도 직접 고르지 않았으면 기기 설정이 바뀔 때 화면도 따라 바뀐다(`initTheme`). 직접 고른 뒤에는 그 선택이 우선.
  - **색**: 각 css 의 `:root` 토큰이 어둡게 값(기본), `css/theme.css` 의 `:root[data-theme="light"]` 가 밝게 값으로 덮는다(디자인 = 목업 아티팩트 「v4.6.0 테마 목업」 밝게 A — BPM 톤:
    배경 #f5f4fb · 카드 #fff · 글자 #232436). 멤버 레인 색(아바타 평균색) · 트윗 말풍선(멤버 색) · 썸네일 위 덮개는 두 테마 공통.
    X 공식 카드도 같은 테마로 불러오고(`tweets.js` `_embedSrc` 의 `theme=`), 테마를 바꾸면 열린 카드를 다시 불러온다(`mew:theme` 이벤트).
    노노카 지각 이스터에그(`king.css`)의 무대 그림은 자체 어두운 배경이라 두 테마 공통. (v4.5.8) 카드 · 팝업 본문 위 대신의 말 글자 · 단계 테두리는 테마를 따른다 —
    `king.css` 토큰 `--k-ink-kick` · `--k-ink` · `--k-ink-gold-kick` · `--k-ink-gold` · `--k-edge-lo` · `--k-edge`(어둡게 = 은빛 · 연금색), 밝게 값은 `theme.css`(진한 쇠색 · 진한 금색). 밝은 바탕에서 은빛 글자가 안 보였다.
  - 바꾸는 순간에만 배경 · 글자 · 테두리 색이 0.3초에 걸쳐 바뀐다(`html.theme-anim`, 움직임 줄이기 설정이면 즉시).
  - **브라우저 자동 어둡게(삼성 인터넷 · Chrome Android force-dark)는 계속 끈다** — `color-scheme` 메타가 dark 를 포함하고 `:root` 의 `color-scheme` 이 테마를 따른다.
    선언이 없으면 기기 다크 모드에서 투명 섞기 색(헤더 그라데이션 · 트윗 말풍선)이 이중 처리돼 뭉개진다.
- **방문 통계 (v4.5.4, v4.6.0 Claude 접속 제외)**: Vercel Web Analytics 스크립트. **주소에 `?va=claude` 가 붙은 탭은 통계를 보내지 않는다** — 공식 `beforeSend`(null 반환)로 막고,
  표시는 그 탭의 `sessionStorage`(`va-skip`)에 남아 같은 탭에서 새로고침 · 이동해도 계속 빠진다. 같은 브라우저의 다른 탭(운영자 접속)은 그대로 집계된다.
  Claude 가 운영 사이트를 브라우저로 열 때 이 표시를 붙인다(CLAUDE.md). 그 전(10-16 · 10-19, Chrome 접속 4회)은 집계에 들어가 있다.
- **css/**: `reset` · `layout`(`#board` ≥1100px `grid-template-columns:repeat(5,1fr)`, <1100px 가로 스크롤 · 공통 색 토큰) ·
  `card`(6상태 클래스 §3, mobile @media 파일 끝) · `timetable` · `king` · `player` · `playerpop` · `notices` · `banners` · `tweets` · `theme`(v4.6.0, 맨 끝 — 밝게 값 · 전환 버튼).
- **js/theme.js** — (v4.6.0) 위 「밝게 / 어둡게 테마」. `themeButton()` · `initTheme()` · `currentTheme()` · `THEME_EVENT`(`mew:theme`).
- **js/config.js** — `PREVIEW_URL`(raw githubusercontent data/preview.json), `ARCHIVE_URL`(v4.1.0), `NOTICES_URL`, `TWEETS_URL`,
  `POLL_MS=75000`, `COUNTDOWN_TICK_MS=60000`, `FETCH_TIMEOUT_MS=8000`, `FALLBACK_CHANNEL_ORDER`, `FALLBACK_CHANNELS`.
- **js/time.js** — 계약 D. 순수, DOM 접근 없음. selfcheck: `time.selfcheck.mjs`.
- **js/api.js** — `fetchPreview(url)`: AbortController + `FETCH_TIMEOUT_MS`, `cache:"no-store"`. `{ok,data|error}`.
- **js/render.js** — `renderBoard(boardEl, preview, nowMs, archive)` (계약 C 전체 재구성. 알 수 없는 channel_key 무시. **v4.1.0**: PC = 타임테이블 + 이후 예고, 모바일 = 1명씩 슬라이드),
  `renderFooter`, `updateCountdowns`. selfcheck: `render.selfcheck.mjs`(순수 헬퍼 `bucketOf`/`laneKeys`).
- **js/playerbtn.js** + **css/player.css** — (v4.2.0) 「CD + 음표 >」 버튼. `createPlayerButton(cls)` — 모바일은 `render.js initMobileCarousel` 이 `#pager-dots` 에
  `.player-btn--dock`(화면 왼쪽 끝 절대 위치)으로 붙인다. **PC(≥768px)는 버튼이 없다** — 플레이어가 `#player-dock`(보드 아래)에 상시 표시된다(아래). 클릭 시 `mew:player-open` 이벤트를 발행하고, `main.js` 가 받아 `player.js` 를 **처음 눌렀을 때만** 동적 import 해 `openPlayer()` 를 부른다(모바일 모달).
  - **PC 하단 도크**: `index.html` 의 `#player-dock`(≥768px 에서만 표시). `main.js syncPlayerDock` 이 도크가 화면 400px 안으로 오면 그때 `player.js` 를 import 해 `mountDock(dock)` — 팝업 본체(`.mp-pop`)를 도크로 옮기고 `.mp-pop--dock`(모달 아님, 내리기 버튼 숨김). 767px 아래로 가면 `unmountDock()` 으로 모달 배경에 되돌린다.
    프레임(iframe)은 옮기지 않고 재생부(`.mp-slot`) 위에 문서 좌표(absolute, z-index 40 — 고정 푸터 아래)로 겹치며 `dockSync`(rAF)가 레이아웃 변동을 따라간다. **재생부가 화면 밖으로 나가면(`IntersectionObserver`) 재생 중인 프레임은 오른쪽 아래 플로팅**으로 남고, 플로팅의 ▴ · 더블클릭은 도크로 스크롤한다(`openPlayer`).
- **js/timetable.js** + **css/timetable.css** — (v4.1.0) 위 「타임테이블 · 이후 예고」. `dayWindow` · `classify` · `buildTimetable` · `buildTodayCards` ·
  `buildFoldButton` · `tickTimetable` · `applyTimetableMarquees` · `closeCardPop`. selfcheck: `timetable.selfcheck.mjs`.
- **js/king.js** + **css/king.css** — (v4.3.1) 노노카 지각 이스터에그. 위 「노노카 지각 이스터에그 (v4.3.1)」. `timetable.js` 가 `decorateBlock` · `decoratePopup` · `decorateCard` 를 호출. selfcheck: `king.selfcheck.mjs`.
- **js/main.js** — `poll()` → `fetchPreview(PREVIEW_URL)` → 성공 시 `renderBoard`+`renderFooter`, 실패 시
  마지막 데이터 유지 + `{stale:true}`. + `pollNotices` + `pollTweets` + 카운트다운 틱.
  **(v3.1.5)** 모바일에서 백그라운드 동안 `setInterval` 폴링이 멈추거나 크게 스로틀링될 수 있어
  (브라우저 스펙상 보장 안 됨) — `visibilitychange`(visible 전이) + `pageshow`(`persisted`,
  bfcache 복원) 리스너로 포그라운드 복귀 시 `poll`+`pollNotices`+`pollTweets` 즉시 재실행.
  없으면 복귀 직후 오래된 `lastSchedule` 로 카운트다운을 계산해 이미 끝난 방송이
  "OOO시간 지각"처럼 잘못 보이다가 다음 정기 poll(최대 `POLL_MS`) 이 돼야 정정됐음.
- **js/notices.js** + **css/notices.css** — `NOTICES_URL` 75초 폴링 → `#notice` 소식판. 아래 「소식판 (v4.6.4)」.
  (v4.6.3 까지: 한 줄 티커 + 펼친 목록, 제목을 `[번역]　—　[원문]` 으로 이어 marquee — v4.6.4 에서 없앰.)
- **js/tweets.js** + **css/tweets.css** — `TWEETS_URL` 75초 폴링. 유닛 아바타 트윗 알림 배지 — **동그라미만**(v4.1.0: 같은 크기의 원 — 안 읽음 1건 = 빈 원, 2건+ = 숫자 원, 모두 읽음 = 표시 없음(테두리도 안 남김). 봉투 아이콘 제거). 배지 클릭/호버 → **메신저형 스레드**: PC `.lane__bubble` 패널 / 모바일
  `.tw-toast` 시트에 **`expires_at`(24h)이 안 지난 메시지 최대 50건**을 최신이 아래로 스택
  (v3.5.3 — 이전엔 유닛당 최근 5개 고정. v3.5.3~v3.7.1 은 12시간 창을 따로 걸어 밤에 온 트윗이 다음날 낮에 전부 사라졌음 → v3.7.2 에서 제거),
  ~2분 내 연속은 시각 1개로 묶음(`.lane__thread__grp`/`__msg`/`__t`), 열면 맨 아래로 스크롤 + 표시분
  전부 읽음. 메시지가 많아도 말풍선(헤더 포함)이 화면 세로 2/3을 넘지 않도록 내부 스크롤 영역
  높이를 `calc(66.6vh - 44px)` 로 고정(css). `한/日` 토글은 헤더에 1개(전역 `mew:tllang`), 원문(X)
  링크는 메시지별(`.ori`). 만료·404 면 안 뜸.
- **js/player.js** + **js/songs.js** + **css/playerpop.css** + **assets/songs.json** — (v4.2.0) 플레이어. 아래 「플레이어 (v4.2.0)」.

### 소식판 (v4.6.4) — `notices.js` · `css/notices.css`

2026-10-22 운영자 확정(시안 아티팩트 「소식 팝업 카드」 · 「소식판 시안」). 경계 = 767px(이하 모바일).
- **PC = 날짜별 묶음**: 접힌 막대 = [소식] [오늘 n · 7일 안 n] [5초마다 넘어가는 티커] [▾] [테마]. 티커 한 줄 = D-day · 분류 아이콘 · 제목 · 날짜(요일) 시각.
  **티커 제목을 누르면 링크로 가지 않고** 목록을 펼쳐 그 소식 팝업을 고정해 연다. 펼침 = 행사 배너 → 분류 칩(스크롤해도 위에 붙음) + [한글 | 원문] → 날짜 묶음
  (날짜 칸 한 줄 「10/24 (토) [D-day]」, 소식 줄 = 시각 · 분류 아이콘 · 제목 / 분류 이름 · 이날까지 · 출처). 날짜 없는 소식은 「날짜 미정」 묶음.
- **모바일 = 칩 + 카드**: 접힌 막대 = 움직이지 않는 분류별 건수 칩(누르면 그 분류로 펼침). 펼침 = 「분류 n건」 + [한글 | 원문] / 밑줄 탭 / 카드 1열
  ([분류 아이콘] [제목 / D-day · 분류 · 날짜(요일) · 시각]).
- **제목**: PC · 모바일 모두 **15.5px 한 줄, 넘치면 말줄임(…)**. marquee · 글꼴 줄이기 없음(10-22 운영자 결정 — 글꼴 크기가 들쭉날쭉하고 marquee 가 많아 읽기 어려웠다).
  잘린 제목 전체는 소식 팝업 카드에서 본다.
- **분류 탭**(`CATS` · `CAT_READ`): [전체] + 6분류(라이브 · 행사 · 방송출연 · 음원·굿즈·출판 · 게임 · 기타), 0건 분류는 숨김(전체는 항상, 고른 분류가 0건이 되면 전체로).
  저장 값은 아직 옛 4종이라 바꿔 읽는다 — 계약 H 「분류」.
- **언어**: [한글 | 원문] 한 번에 한 언어, 기본 한글, `localStorage` `mew.notice.lang`(트윗 번역 설정과 별개). 한글 제목이 없으면 원문.
- **소식 팝업 카드** — 트윗 말풍선과 같은 방식:
  - PC: 소식 줄 **호버 = 잠깐 열림**(팝업으로 옮겨도 유지 · 떠나면 닫힘, 닫기는 160ms 미룸), **클릭 = 고정**(한 번에 1개, 같은 줄 다시 클릭 · ✕ · Esc · 바깥 클릭으로 닫힘, 고정 중 호버 무시).
    `.ntc__pop`(#notice 안 · 목록 밖, z-index 43 — 펼친 목록 42 · 플레이어 도크 40 위). 아래 공간이 모자라면 위로, 화면 안으로 맞춤, 꼬리, 목록 스크롤 · 창 크기 변화에 따라감.
  - 모바일: 카드 탭 = body 에 붙인 **아래 시트**(`.ntc-sheet` z 901 · 배경 `.ntc-scrim` 900, 트윗 시트와 같은 층). ✕ · 배경 · Esc 로 닫힘, 열린 동안 body 스크롤 잠금. 시트 안을 눌러도 소식 목록은 안 닫힌다.
  - 내용: 분류 · D-day · 날짜(요일, 마감이면 〜) · 시각 · 출처 / 전체 제목(언어 전환 따름) / **번역 본문(`body_ko`, 없으면 「번역 준비 중…」)** / **X 공식 트윗 카드** / 「자세히 보기 ↗」(`url`) · 「원문 트윗 ↗」(`tweet_url`, http(s)만).
    **원문 모드에서도 본문 원문(`body_raw`)은 우리가 그리지 않는다**(v3.8.0 법률 자문 — 원문 · 이미지는 X 카드가 보여 준다, 트윗 말풍선과 같은 원칙). PC = 본문 | X 카드(280px) 2열, 모바일 = 1열.
  - X 카드는 `tweets.js` 의 `makeXCard` · `loadXCards` · `stopXCards`(트윗 말풍선 코드 재사용 — 테마 전환 · 높이 신호 · 15초 실패 링크 같음). 호버 팝업은 **0.5초 머물러야** 카드를 불러오고(`PEEK_CARD_MS`), 고정 · 시트는 바로. 닫으면 iframe 제거.
  - 소식 줄 · 카드는 링크가 아니라 버튼(`role=button` · `tabindex=0` · `aria-haspopup=dialog`, Enter/Space 로 열기, 키보드로 닫으면 포커스가 그 줄로).
  - 75초 폴링으로 다시 그릴 때: 고정 팝업 · 시트는 같은 소식이 남아 있으면 유지(내용이 바뀌면 다시 채움), 없으면 닫음. 호버 팝업은 닫음.
- **펼친 목록 높이**: 행사 배너 + 분류 줄 + 소식 영역(`LIST_CAP` PC 420 · 모바일 460px 상한), 전체는 화면 높이 70% 상한. 펼친 목록 z-index 42(v4.6.3 까지 30 — PC 플레이어 도크(40)의 YouTube 화면 밑으로 들어가던 것을 고침).
- 데이터 주입: 템플릿 + `_esc` · `_attr` 이스케이프(v2 부터의 방식 그대로), 링크는 http(s)만.

### 플레이어 (v4.2.0) — `player.js` · `songs.js` · `css/playerpop.css` · `assets/songs.json`

「CD + 음표 >」 버튼(`mew:player-open`)으로 여는 **YouTube 곡 플레이어**. 곡 목록은 **data 브랜치 `songs.json`**(`SONGS_URL` — 신곡 자동 감지가 등록, 어드민 음반 탭에서 수정 · 삭제 · 직접 추가, 아래 §8.15)을 먼저 읽고,
없으면(시드 전 · 로컬 개발) 프론트에 같이 배포되는 정적 `assets/songs.json`(`SONGS_FALLBACK_URL`, `scripts/build_songs_json.py` 로 생성)으로 폴백한다.
곡 레코드: `{id(video_id), title, kind(original|cover), who(멤버 키|group), date, reading(가나 독음, 없으면 ""), added_at?(자동 등록분)}` — YouTube 에서 얻는 값만. **솔로 구분은 없다**(솔로도 cover — 운영자 결정 2026-10-06, 정규 규칙은 제목 끝 「(Cover)」 하나뿐).
BPM · 키 · energy · valence 는 오디오 분석(GPU, 메인 로컬)이 필요하고 플레이어가 쓰지 않아 **일부러 제외**. (별칭 기능은 2026-10-07 에 없앴다 — 곡 줄의 「✎ 별칭」 버튼 · `localStorage` 저장 모두 제거.)

**곡 데이터의 출처와 갱신**: 초기 데이터(시드)는 BPM 프로젝트(`bandori-playlist-maker-data` 저장소 `origin/data` 의 `data/songs_master.csv`)의 곡 목록에 YouTube 업로드 시각을 붙인
`ref/player/songs_release.json`(65곡, 조사 보고 `docs/yumemita_player/REPORT.md` @devpapers)에서 `python scripts/build_songs_json.py` 로 만든 `assets/songs.json` 이다(64곡 — 두 번 들어 있던 「オリオンをなぞる」 중 `ekZUC5KaJFw` 1건을 2026-10-08 에 직접 지웠다. `config/songs_seed.json` 도 같음).
출시일(`date`)은 **공식 발매일이 아니라 영상 업로드 시각**(KST 날짜)이다 — 뮤타입 음원 채널의 음원은 MV 공개일과 다를 수 있다. 이후 신곡은 BPM 프로젝트의 `/update-new-songs` 와 **무관하게**
백엔드가 뮤타입 음원 채널(PubSub 알림 · 일일 RSS 확인)에서 자동 감지해 data 브랜치 `songs.json` 에 등록한다(§8.15). **운영 전 시드 필요**: data 브랜치에 `songs.json` 이 없으면 자동 등록은 아무것도 하지 않는다 —
`assets/songs.json` 을 data 브랜치 `songs.json` 으로 올려 시드한다(운영자 작업, 아직 하지 않음).

- **재생**: YouTube IFrame Player API(`https://www.youtube.com/iframe_api`, 처음 열 때 로드)의 임베드 프레임만 쓴다. **광고 건너뛰기 없음** — 광고는 프레임 안에서 YouTube 가 처리.
  (개발자 정책 III.I.5 광고 수정·차단 금지 · III.I.9 백그라운드 플레이어 금지 · 필수 최소 기능 200×200, 프레임 앞 오버레이 금지.)
  오류(임베드 제한 등)면 「YouTube 에서 보기」 링크를 보여준다.
- **곡 목록 | 재생목록 탭**(v4.2.1~v4.2.2, 2026-10-09): 아래(모바일) / 오른쪽(PC) 한 칸을 탭 바(`.mp-tabs`)로 나눠 쓴다 — 곡 목록(`.mp-lib`)과 재생목록(`.mp-q`, 탭 패널 `.mp-qpanel` 안)은 한쪽만 보여 서로 밀지 않는다.
  재생목록 탭에는 곡 수 배지(곡을 추가하면 펄스, 탭은 자동 전환 안 함). 재생부(`.mp-stage`)는 영상 · 곡 정보 · 컨트롤뿐이라 PC 도크(높이 700px)에서 영상을 칸 폭 가득(최대 720px)으로 쓴다. 곡 줄의 「재생목록 N번」 뱃지는 여러 번 쌓여도 「N번 외 K」로 글자 수 상한. 모바일은 위(재생부) 고정 + 아래 탭 한 칸만 스크롤.
- **재생목록**(2026-10-07~08): 오른쪽 곡 목록의 곡을 **누르면 재생목록(재생부 아래 「재생목록」 칸 — 움푹 패인 우물 모양)의 맨 뒤에 쌓인다. 같은 곡을 또 눌러도 또 쌓인다(빠지지 않음, 곡 줄에는 「재생목록 1·3번」)**.
  **재생목록이 비어 있다가 처음 들어가는 곡은 쌓이면서 바로 재생**하고, 이후 곡은 쌓기만 한다. 재생 버튼은 멈춰 있고 지금 곡이 재생목록에서 고른 것이 아니면 1번부터 시작한다.
  같은 곡이 여러 번 있을 수 있어 「지금 곡」은 곡 id 가 아니라 **재생목록 위치(`st.qi`, 0부터, -1 = 재생목록에서 고른 곡이 아님)** 로 추적한다. 재생목록 칸의 곡을 누르면 그 위치로 이동·재생, ✕ 로 빼기(지금 곡을 빼면 끝까지 재생 후 멈춤), 「비우기」로 전체 삭제.
  곡이 끝나면 **재생목록의 다음 위치로 넘어가고, 마지막이면 멈춘다**(`cueVideoById` 로 첫 화면 복귀 — 추천 영상으로 안 넘어가게). 재생목록이 비어 있으면 한 곡만 재생하고 멈춘다.
  이전·다음 버튼은 재생목록이 있으면 그 안에서(끝에서 처음으로 순환, 셔플이면 무작위), 없으면 현재 검색·정렬 결과 순서. 재생목록은 저장하지 않는다(새로고침하면 비워짐).
  플로팅 상태의 손잡이 줄 제목은 재생목록에서 고른 곡이면 「<곡명> (n/m)」(곡명만 말줄임, `(n/m)` 은 항상 보임).
- **랜덤플리 오마카세**(v4.5.6, 2026-10-19): 컨트롤 오른쪽 「🎁 랜덤플리 오마카세」(`.mp-oma`) → 말풍선(`.mp-bubble`, 칩 [전체 / 오리지널 / 커버] + 곡 수). 칩 = 그 종류의 **모든 곡**(검색 · 정렬 무시, `s.kind`)을 Fisher–Yates 로 섞어 `st.queue` 를 **덮어쓰고** `playQueueAt(0)` 으로 바로 재생(재생 시작은 클릭 직후). 셔플 토글과는 별개. 반영 직후 **재생목록 탭으로 자동 이동**(`setTab("queue")`).
  연출 = 0.62초 뒤섞임(`.rolling` — 흔들림 · 🎁 회전 · 글자 순서 섞기) → 5초 쿨타임(`.cooldown::after` — 반투명 막이 버튼을 덮고 **오른쪽 끝부터 왼쪽으로 걷힘**, `scaleX` 1→0, 클릭 시점부터 5초 · 그동안 `disabled`). 모션 줄이기면 연출 없이 5초 잠금만. 곡이 없으면(목록 로드 실패) 비활성. 말풍선은 바깥 클릭 · Esc 로 닫힘(Esc 가 팝업까지 닫지 않음).
  컨트롤 5개 + 오마카세 버튼은 한 줄에 **가운데 정렬**(말풍선도 버튼 가운데 기준). 좁은 화면(≤480px)은 컨트롤 아래 줄 전체 폭.
- **반복**(BPM 프로젝트 `playbar.js` 와 같은 3단계, 2026-10-07): 반복 버튼을 누를 때마다 **꺼짐 → 한 곡 → 전체 → 꺼짐**. 한 곡 = 같은 곡을 처음부터 다시(버튼 안 글자 「1」), 전체 = 재생목록 마지막 곡 뒤에 1번으로(「A」).
  자동 넘김과 순환은 **재생목록 안의 곡**에만 적용된다(재생목록 밖 곡은 전체 반복이어도 끝나면 멈춤).
- **팝업 ↔ 플로팅**: 프레임 요소(`.mp-frame`)는 한 번 만들고 **옮기지 않는다**(옮기면 iframe 이 다시 로드돼 재생이 끊김). 팝업이 열려 있으면 JS 가 재생부 자리(`.mp-slot`)에 맞춰 위치·크기를 주고,
  내리면 `.is-float`(오른쪽 아래, 356×200 — 높이 200 이 최소 요건) 로 남는다. 손잡이 줄(`.mp-grip`)은 프레임 **바깥 위**에 붙는다 — 끌어서 이동 · 더블클릭 = 팝업으로 · ▴ 열기 · ✕ 정지하고 치움.
  프레임은 재생을 한 번이라도 시작했을 때만 남는다. 모바일은 하단 도트 띠(푸터 45 + 도트 44) 위, PC 는 고정 푸터 위.
- **신곡 NEW**(2026-10-08): 곡의 **발매일(`date`) +14일까지**(그날 포함, KST)가 신곡이다(`songs.js isNewSong`). 발매일 전 날짜는 신곡이 아니다. 등록 시각(`added_at`)은 쓰지 않는다 — 2026-10-08 오전까지는 `added_at` 기준 7일이었으나 발매일 +14일로 바꿨다(운영자 결정). 시드 곡도 최근 14일 안에 발매됐으면 신곡이다.
  첫 시드 후 첫 tick 에 한꺼번에 등록되는 과거 곡(10곡)도 모두 신곡이 된다. 표시: ① CD 버튼 오른쪽 위 `NEW` 배지(`playerbtn.js initNewSongBadge` 가 페이지 로드 때 곡 목록을 읽어 `<html data-new-song>` 를 켜고 CSS 가 PC · 모바일 버튼에 그림) ② 곡 줄 · 재생 중 곡 제목 옆 `NEW` 알약 ③ 필터 「신곡」 버튼(신곡만).
  **신곡은 정렬과 무관하게 항상 목록 맨 위, 최신 순**(발매일 내림차순 → 등록 시각 → 곡명) — 나머지만 고른 정렬대로. NEW 표시에는 광택 + 맥박 애니메이션(움직임 줄이기 설정이면 멈춤).
- **한글 음차 표시**(2026-10-07): 곡명에 일본어(가나·한자)가 있고 독음이 있는 곡만, 곡 줄과 재생 중 곡 정보의 **날짜 줄 아래**에 한글 음차를 한 줄 보인다(`songs.js displayKo`). 영문 곡명 · 독음 없는 곡은 표시 없음. **가나 독음 자체는 화면에 보이지 않는다**(검색 · 이름순 정렬에만 쓴다).
  변환(`kanaToHangul`)은 단순화 규칙이다 — 조사 は 도 「하」, 작은 모음(ゥ ェ …)은 지운다(`トゥ`→토).
- **검색**(`songs.js`): 곡명 · 독음(가나 + 자동 변환한 한글)을 한 번에 부분 일치. 대소문자 · 전각 무시, 가타카나 = 히라가나, 한글은 초성 평음화(ㅋ=ㄱ ㅌ=ㄷ ㅍ=ㅂ ㅊ=ㅈ)로 표기 차이를 흡수.
  가나 → 한글 변환은 외래어 표기법을 단순화한 것(`kanaToHangul`: 어두 か·た행 가·다, ん=ㄴ · っ=ㅅ 받침, 장음 생략, 조사 は 도 글자 그대로 「하」). 부른 사람 · 종류 · 날짜는 검색 대상 아님(종류는 필터 버튼).
- **정렬**: 이름순(독음 있으면 독음, 없으면 곡명, `localeCompare("ja")`) · 날짜순(같은 날은 곡명순). 기본 날짜 내림차순.
- **하단 디스클레이머 팝업**(v4.5.7): 마우스를 `.fdisc` 에 **2초 유지해야** 열린다(`main.js initDisclaimerHover` 가 `.is-open` 부착 · 2초 전에 벗어나면 취소). 열린 뒤엔 `.fdisc`/팝업 위에 있는 동안 유지, 벗어나면 0.3초 뒤 닫음(`.fdisc` 와 팝업 사이 틈을 지나 GitHub Issues 링크로 갈 수 있게). 포커스(클릭 · 키보드 · 터치 탭)는 CSS `:focus`/`:focus-within` 으로 **즉시** 열린다(터치는 호버가 없음). Esc 로 닫힘. 호버 중 흐르는 문구는 바로 멈춤(읽기용).
- **z-index**: 도트 띠 25 < 플로팅 프레임 45 < 디스클레이머 팝업(`#foot`) 50 < 팝업 배경 800 < 팝업 안 프레임 810 < 트윗 시트 900.
- selfcheck: `songs.selfcheck.mjs`(변환 · 정규화 · 검색 · 정렬 · 강조 구간 · 종류 30건). **보류**: 곡명 한글 해석 검색.

**확인 필요 · 미정 (2026-10-06 구현 시점)** — 임의로 넘겨짚지 않고 남겨 둔 것:
1. **시드 · 첫 실행**: data 브랜치에 `songs.json` 이 없어서 자동 등록이 아직 동작하지 않는다(시드 전 = 건너뜀). 시드 뒤 **첫 tick 은 뮤타입 음원 채널 RSS 최근 15건 중 곡명이 없는 곡을 한꺼번에 등록**한다 —
   2026-10-06 RSS 기준 10곡(`TearJerker` · `Face The Next` · `一番のひかり` · `うちゅうのふしぎ` · `夢はトゥルーエンド！` · `in my words` · `愛は衝動` · `にこいちミライ` · `唱`(cover) · `夢我夢中`).
   BPM 보고서가 「분류 불명 9곡」으로 보류했던 곡들이 규칙대로 original 로 들어가므로, 시드 전에 포함해도 되는지 운영자 확인이 필요하다. 신곡에 필요한 값은 RSS 만으로 얻는다(제목 · 공개 시각 · 구분) — `videos.list` 쿼터 0.
2. **독음 15곡은 예시 — 운영자 검수 필요**. 나머지 50곡은 독음이 없어 독음(가나·한글) 검색이 안 된다. 채우는 방법(직접 입력 / 자동 생성)은 미정. `scripts/build_songs_json.py` 의 `READ` 에 있다.
3. **이름순 정렬 한계**: 독음이 있으면 독음, 없으면 곡명(한자 · 기호 포함)으로 정렬해 섞여 보인다. 독음이 전 곡에 채워지면 해소.
4. **미분류 9곡 · `feat.`**: 미분류 9곡 중 뮤타입 음원 채널에 있는 곡은 위 1항대로 자동 등록 대상이다. `feat.` 곡은 자동 등록 · 시드에서 모두 제외(`songs.py` · `build_songs_json.py`). 피드 15건을 넘는 버스트는 아직 고려하지 않았다.
5. **미검증(헤드리스 Chrome 에서 영상이 검은 화면이라 못 본 것)**: 실제 영상 재생 · 임베드 제한 영상의 오류 안내(`onError`) · 재생/일시정지 상태 동기화(`onStateChange`) · 모바일 실제 터치(손잡이 드래그 · 더블탭 → 팝업). 실기기 확인 필요.
6. **정책 해석**: 「팝업을 내려도 재생 유지」를 위해 프레임을 항상 보이게 두는 것은 III.I.9(백그라운드 플레이어 금지)와 최소 200×200 요건의 **원문을 근거로 한 해석**이다. 플로팅 프레임의 허용 여부를 YouTube 에 문의해 확인한 것은 아니다.
7. **✕(정지하고 치우기) 버튼**은 목업에 없던 추가 기능이다 — 플로팅 프레임이 높이 200px 로 화면을 계속 차지해 치울 방법이 필요하다고 판단. 유지 여부는 운영자 확인.
8. **새 용어 미등재**: 「플로팅 프레임」 · 「별칭」 · 「독음」 · 「손잡이 줄」 은 `docs/TERMINOLOGY.md` 에 아직 없다(임의로 추가하지 않음 — 운영자와 정한 뒤 등재).
9. **멤버 표시 분류 규칙**: 곡의 `who` 는 업로드 채널명으로 정한다(멤버 이름 일·영문 모두 인식, 「`Yuno Sengoku - Topic`」 같은 자동 생성 아티스트 채널 포함, 그 밖은 `group`). 멤버별 곡 수는 그룹 28 · 아라레 11 · 유노 8 · 미야코 7 · 리츠 6 · 노노카 5.
   한 곡이 여러 멤버의 곡인지(참여 멤버)는 데이터에 없다.

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
| 5 | (v4.5.0) PubSub 알림이 안 와서(허브 장애 · 구독 끊김) 새 영상을 못 찾음 | 일일 baseline RSS 가 안전망(대체 모드에서도 유지) · 구독 갱신 잡이 허브 검증 기록으로 끊긴 구독 DM · 음원 채널은 `via=baseline` warn | `websub.py`, `handlers.py` |

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
  `HEALTHCHECKS_IO_READONLEY_TOKEN`(v3.7.1 추가), **`WEBSUB_SECRET`**(v4.5.0 — 허브 서명 키, 값이 없으면 임의 생성)) + (v4.5.2) PubSub 전용 큐 `WEBSUB_QUEUE`(기본 `mewtype-websub`, 동시 1 · 초당 0.2). 멱등.
- `deploy.sh` — `gcloud run deploy mewtype-backend --source . --no-allow-unauthenticated --service-account RUNTIME_SA`
  + secrets/env. `GROQ_API_KEY`·`HEALTHCHECKS_IO_READONLEY_TOKEN` 은 Secret 이 있을 때만 마운트(v3.7.1 — 전엔
  healthchecks Secret 을 무조건 마운트해 새 프로젝트에서 첫 배포가 실패). 배포 후 `SERVICE_URL` env 재설정.
  (v4.5.0) `WEBSUB_SECRET`(Secret, 있을 때만) · `WEBSUB_CALLBACK_BASE`(접수 서비스 URL — 배포 때 조회, 접수 서비스를 **먼저** 배포) · `WEBSUB_REPLACE_RSS`(기본 0) · (v4.5.2) `WEBSUB_QUEUE`(PubSub 확인 재예약용) env.
- `scheduler.sh` — `mewtype-baseline`(`0 6 * * *` Asia/Tokyo) / `mewtype-light`(`*/10 * * * *` Etc/UTC, v3.6) /
  `mewtype-monitor`(`10 6 * * *` Asia/Seoul → `/monitor`) / (v4.5.0) `mewtype-websub-renew`(`20 6 * * *` Asia/Seoul → `/websub-renew`). OIDC.
- `deploy_telegram.sh` — 같은 소스 + telegram 엔트리포인트 + `--allow-unauthenticated --service-account INVOKER_SA`
  `ALLOW_UNAUTH=1` + `MAIN_SERVICE_URL`(write-queue·`/resume`). `GROQ_API_KEY`·`HEALTHCHECKS_IO_READONLEY_TOKEN`
  (조건부) + `INGEST_YT_ENABLED` env. (v4.5.0) `WEBSUB_SECRET`(조건부 — 없으면 `/websub/*` 는 503) · (v4.5.2) `WEBSUB_QUEUE`(알림 확인 · 신곡 등록 예약 큐 — 큐가 없으면 예약 실패 → 503 이라 `setup.sh` 로 **먼저** 만든다). (v3.7.3) Secret `YT_COOKIES` 가 있으면 `/secrets/yt-cookies.txt` 로 마운트 +
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
