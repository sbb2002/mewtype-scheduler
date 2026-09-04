# 구현 명세 (SPEC) — 현행 통합본

`IMPLEMENTATION.md`(v1) + `IMPLEMENTATION_v2.md`(v2.0) + `IMPLEMENTATION_v2.1.md`(v2.1) 에서
**현행 유효분만** 합친 문서. 원본 3개는 `docs/old/` 로 이관됨. 빌드 당시의 병렬 작업 배정
(`haiku #N` / `Sonnet 담당`), v1 GitHub Actions 정기 cron 등 **폐기된 내용은 제외**했다.

- v2.3(X 예고 릴레이) · v2.4(합동방송) 상세 설계: `docs/plan/v2_3_x_relay.md`,
  `docs/plan/v2_4_collab.md`, 전환 런북 `docs/plan/v2_4_golive.md`
- 운영자 시점 스케줄 요약: `docs/SCHEDULE.md`
- 요구사항 배경: `docs/beta_version/PRD.md`

**인터페이스 계약(§1~§7)을 벗어나는 변경은 이 문서를 먼저 고친다.**

---

## 0. 아키텍처 / 저장소 구조

서버 상시 가동 없음. 무료 인프라만 사용.

| 역할 | 수단 |
|---|---|
| 수집·판정 | **Cloud Run**(scale-to-zero, `src/backend/`, Flask+gunicorn). 리전 `asia-northeast1` |
| 정기 트리거 | **Cloud Scheduler** 2잡 — baseline JST 06:00 / light 3h → `POST /tick` (OIDC) |
| 방송별 정밀 wake | **Cloud Tasks** — 방송마다 1회성 `POST /wake {video_id}` (OIDC). 720h 상한 → `now+696h` 클램프 롱폴링 |
| 저장 | **GitHub `data` 브랜치** — Cloud Run 이 GitHub Contents API(fine-grained PAT, Secret Manager)로 커밋 |
| 프론트 | **Vercel** 정적 호스팅 (빌드 없음). `raw.githubusercontent.com/.../data/schedule.json` 75초 폴링 |
| 모니터링·제어 | 공개 서비스 **`mewtype-telegram`**(같은 이미지, 다른 엔트리포인트) — Telegram webhook + `/ingest` |

```
src/
  frontend/            # Vercel Root Directory = src/frontend, 빌드 없음
    index.html         # 빈 #board + #foot 스켈레톤, <script type="module">
    css/{reset,layout,card}.css
    js/{config,time,api,render,main}.js      # ES 모듈, 상대 import
  collector/           # v1 순수 모듈 — v2 백엔드가 import 재사용. main.py 는 break-glass 전용
    main.py config.py rss.py youtube.py reconcile.py store.py
  backend/             # v2 Cloud Run 서비스
    app.py             # /tick /wake /healthz
    handlers.py        # tick/wake 오케스트레이션
    statemachine.py    # pending.json 폴링 FSM (순수)
    pending.py         # pending.json 스키마 헬퍼
    gh_store.py        # GitHub Contents API read/write (낙관적 동시성)
    tasks.py           # Cloud Tasks enqueue (OIDC 타깃, 720h 클램프)
    oidc.py            # Scheduler/Tasks OIDC bearer 검증
    config.py          # 환경변수 → Config
    notify.py          # (v2.1) Telegram 알림 + diff_events(A~F)
    control.py         # (v2.1) control.json 스키마
    telegram_app.py    # (v2.1) 공개 webhook /telegram · (v2.3) POST /ingest
    xrelay.py          # (v2.3/2.4) X 예고 트윗 파서 + scheduled 행 머지 (순수)
Dockerfile             # python:3.12-slim + gunicorn. 두 서비스가 이 이미지 공유(엔트리포인트만 다름)
deploy/                # gcloud 배포 스크립트. env.sh 는 루트 .env 매핑(gitignore)
config/channels.json   # 5채널 단일 소스
fixtures/              # schedule.sample.json, rss_arale.xml
.github/workflows/collect.yml   # workflow_dispatch 전용 (정기 cron 제거됨 — break-glass)
data 브랜치             # schedule.json + archive.json + pending.json + control.json + ingest_queue.json. 코드 없음
```

- 프론트는 빌드 단계 없음. ES 모듈을 브라우저가 직접 로드.
- 파이썬 3.12. 시각은 전부 UTC ISO(`Z`) 저장, KST 변환은 프론트 `time.js` 담당.
- v1 대비 변경: 백엔드 compute 가 GitHub Actions 러너 → Cloud Run, 정기 cron → Cloud Scheduler
  2잡, `data` 브랜치 쓰기가 git push → Contents API. 프론트는 무변경.

---

## 1. 계약 A — `schedule.json` 스키마 (동결)

`data` 브랜치 루트. 프론트가 `raw.githubusercontent.com` 에서 직접 fetch.

```jsonc
{
  "generated_at": "2026-08-30T12:00:00Z",          // ISO UTC, 'Z'. 매 tick/wake 실행시각
  "channel_order": ["arale","yuno","nonoka","ritsu","miyako"],
  "channels": {
    "arale": {
      "name": "仲町あられ -Nakamachi Arale-",
      "name_ko": "나카마치 아라레",
      "channel_id": "UCWfF0DB6m_t2CE3KcOOOX7g",
      "handle": "arale_yumemita",
      "channel_url": "https://www.youtube.com/@arale_yumemita",
      "avatar": "https://yt3.googleusercontent.com/...=s176-c-k-c0x00ffffff-no-rj"
      // baseline 스캔이 channels.list 로 취득. light 는 이전 값 유지. 없을 수도 있음(프론트가 원형 폴백)
    }
    // yuno / nonoka / ritsu / miyako 동일 구조
  },
  "broadcasts": [
    {
      "video_id": "h31Mi6AS7a0",
      "channel_key": "arale",
      "title": "【歌枠】まったりお歌〜",
      "url": "https://www.youtube.com/watch?v=h31Mi6AS7a0",
      "thumbnail": "https://i.ytimg.com/vi/h31Mi6AS7a0/hqdefault.jpg",
      "status": "upcoming",                         // "upcoming" | "live"
      "scheduled_start": "2026-08-31T11:00:00Z",     // ISO UTC. live 에서도 유지(있으면)
      "actual_start": null,                          // live 면 ISO UTC
      "concurrent_viewers": null,                    // live 면 정수 가능(없으면 null)
      "first_seen": "2026-08-30T09:00:00Z",
      "last_updated": "2026-08-30T12:00:00Z"
    }
  ]
}
```

규칙:
- `broadcasts` 정렬: `status=="live"` 먼저 → `scheduled_start` 오름차순(프론트도 재정렬하므로 방어적).
- 파일 없을 때 기본형: `{"generated_at": null, "channel_order": [...], "channels": {...}, "broadcasts": []}`.
- 프론트는 `channel_order`/`channels` 가 비면 `config.js` 폴백을 쓴다.
- `generated_at` heartbeat: 실질 변화가 없어도 `_HEARTBEAT_MIN_SEC`(20분) 간격으로 전진시켜
  커밋한다 (`handlers._heartbeat_generated_at`). 라이브 중 wake 3분마다 커밋되는 것은 막는다.

### 1-1. `status == "scheduled"` 행 (v2.3 X 릴레이 / v2.4 합동)

`broadcasts[]` 에 `video_id` 없는 행이 섞일 수 있다. `@BDP_yumemita` 일일 스케줄 트윗이
폰(Automate) → `mewtype-telegram` `POST /ingest` 로 릴레이돼 만들어진, **YouTube 영상이 아직
없는 최하 단계**다. 파서 규칙: `docs/plan/v2_3_x_relay.md`.

```jsonc
{
  "status": "scheduled",
  "channel_key": "nonoka",
  "sched_id": "sched:nonoka:2026-08-30T02:00:00Z",  // video_id 대체 키
  "video_id": null, "title": null, "url": null, "thumbnail": null,
  "scheduled_start": "2026-08-30T02:00:00Z",         // JST→UTC. 파싱 실패 시 null
  "start_approx": false,                              // 트윗에 "頃" 등
  "kind": "game",                                     // game|talk|song|collab|morning|unknown
  "icon": "🎮",                                        // 원본 이모지 (kind=unknown 이면 프론트가 이것만)
  "members_only": false,
  "collab_with": [],                                  // A×B 합방 시 상대 channel_key[]
  "host": null,                                        // (v2.4) "group" = 5인 공동명의(公式) 채널 방송. 아니면 null
  "source": "bdp_schedule",                           // 또는 "bdp_appearance"(出演情報)
  "source_at": "2026-09-03T01:05:00Z",
  "first_seen": "...", "last_updated": "...",
  "assumed_live": false,                              // reconcile 이 scheduled_start 지나면 true
  "expires_at": "2026-08-30T05:00:00Z"               // start + (회원전용 5h / 공개 3h). null 이면 first_seen+18h
}
```

- 정렬 확장: `live` → `upcoming` → `scheduled`, 그룹 내 `scheduled_start` asc(null 뒤).
- `reconcile.build_schedule` 이 매 tick 보존한다. 같은 채널 실물 `upcoming`/`live` 가 ±4h 안에
  뜨면 제거(supersede), `expires_at` 도달 시 제거, `scheduled_start` 지난 행은 `assumed_live=true`
  (회원전용은 API 로 실물을 못 봄 → 이 플래그로만 "방송 중 추정"). Cloud Tasks/`pending.json` 은
  안 타지만 `handlers._scheduled_wake_times` 가 `scheduled_start`(지금~+3h)마다 `light /tick` 1개를
  예약 — 공개 방송의 정시 시작을 3h 주기 안 기다리고 RSS 로 줍는다.
- `host` 있는 행(`host=="group"`)은 멤버 개인 실물로 supersede 하지 않는다 (그룹 채널은 추적
  5채널이 아님 → TTL 로만 소멸).
- **프론트 렌더**: `render.js` 가 `upcoming` 과 같은 버킷에 `scheduled_start` 순으로 섞어 그린다.
  `.card--scheduled` = 점선·감광, 썸네일 대신 `icon`, "예고" 배지, 링크는 `channel_url`. DOM 은 §3.
  구버전 프론트는 이 행을 무시(롤백 안전). `kind=="collab"` 이면 `.card--collab` 추가 +
  **참여 멤버 전원**(`channel_key` ∪ `collab_with`) 레인에 같은 카드로 팬아웃, 링크는 `url`(그룹 영상).
- **`ingest_queue.json`** (`data` 브랜치, `{"pending":[{raw,title,received_at}]}`): 테스트 모드
  (`INGEST_ECHO`/`INGEST_DRY_RUN`) 중 온 스케줄 트윗 원문 버퍼. 실배포 전환
  (`INGEST_ECHO=0`+`INGEST_DRY_RUN=0`) 후 첫 `/ingest` 에서 `telegram_app._ingest_queue_drain`
  이 순서대로 파싱·머지하고 비운다. 런북: `docs/plan/v2_4_golive.md`.

---

## 2. 계약 B — `archive.json` 스키마

```jsonc
{
  "updated_at": "2026-08-30T12:00:00Z",
  "broadcasts": [
    {
      "video_id": "MGVRS_MYXSw",
      "channel_key": "arale",
      "title": "…",
      "url": "https://www.youtube.com/watch?v=MGVRS_MYXSw",
      "thumbnail": "https://i.ytimg.com/vi/MGVRS_MYXSw/hqdefault.jpg",
      "status": "ended",
      "scheduled_start": "2026-08-29T15:00:00Z",
      "actual_start": "2026-08-29T15:03:00Z",
      "actual_end": "2026-08-29T17:20:00Z",
      "archived_at": "2026-08-30T12:00:00Z",
      "reason": "ended"                              // "ended" | "removed" | "canceled"
    }
  ]
}
```

- append-only, `video_id` 기준 dedupe. 프론트는 읽지 않음.
- `reason`: `ended`(정상 종료, `actual_end` 있음) / `canceled`(`liveBroadcastContent=="none"` 인데
  `actual_end` 없음) / `removed`(응답에서 통째로 사라짐).
- `liveBroadcastContent=="none"` 명시 신호(`ended`/`canceled`)는 유예 없이 즉시 이관.
- `removed` 는 **즉시 이관하지 않고** `last_updated` 기준 `STALE_REMOVE_SEC`(6.5h) 이상 연속
  누락일 때만 이관 (배치 일시 누락·"공개→회원전용" 전환 오탐 방지 — §11 / `SCHEDULE.md` §5.2).

---

## 3. 계약 C — 프론트 DOM 구조 (동결)

`render.js` 가 생성하고 `css/` 가 스타일링하는 정확한 구조. class 이름 변경은 이 문서 수정 후에만.

```html
<main id="board">
  <section class="lane" data-channel="arale" style="--lane-color: rgb(...)">
    <!-- --lane-color: render.js 가 아바타 평균색을 canvas 샘플링해 인라인 설정. 실패 시 CSS 폴백 -->
    <header class="lane__header">   <!-- ::before = 좌→우 캐릭터색 그라데이션 -->
      <a class="lane__link" href="{channels[key].channel_url}" target="_blank" rel="noopener">
        <span class="lane__avatar" style="background-image:url('{avatar =s176}')"></span>
        <span class="lane__meta">
          <span class="lane__name-line">
            <span class="lane__name-ko">나카마치 아라레</span>
            <span class="lane__name-orig">仲町あられ -Nakamachi Arale-</span>
          </span>
          <span class="lane__handle">@arale_yumemita</span>
        </span>
      </a>
    </header>

    <div class="lane__live" data-state="on">     <!-- 빨간 테두리 존. data-state: "on" | "off" -->
      <!-- on: status=="live" 카드 1개 이상 -->
      <!-- off: <span class="lane__live-off">OFF-AIR</span> (회색 중앙) -->
    </div>

    <!-- upcoming 0개면: <p class="lane__empty">예정된 방송이 없어요</p> -->
    <div class="lane__buckets">
      <section class="lane__bucket" data-bucket="today">  <!-- today(<24h) / week(24h~7일) / month(7~30일) / later(≥30일·null) -->
        <h3 class="lane__bucket-label">오늘</h3>            <!-- week="7일 이내", month="한 달 이내", later="그 이후" -->
        <ul class="lane__bucket-list">                    <!-- overflow-y:auto, 길면 개별 스크롤 -->
          <li class="lane__item"><!-- upcoming 카드 --></li>
          <!-- 비었으면: <li class="lane__bucket-none">예고 없음</li> -->
        </ul>
      </section>
      <!-- week, month, later 섹션 동일 구조로 항상 4개 렌더 -->
    </div>
  </section>
  <!-- channel_order 순서대로 lane 반복 -->
</main>

<footer id="foot">
  <div class="foot__inner">
    <span id="foot-updated">업데이트: 08/30 21:00</span>
    <span id="foot-status" hidden>업데이트 지연</span>
  </div>
</footer>
```

카드(라이브/예정 공통, 최상위는 `<a>`):

```html
<a class="card card--live" href="{url}" target="_blank" rel="noopener">
  <!-- 예정: class="card card--upcoming" -->
  <div class="card__thumb-wrap">
    <img class="card__thumb" src="{thumbnail}" loading="lazy" alt=""
         onerror="this.dataset.fallback ? this.classList.add('card__thumb--broken') : (this.dataset.fallback=1, this.src=this.src.replace('hqdefault','mqdefault'))">
    <span class="card__badge card__badge--live">LIVE</span>
    <!-- 예정 카드에는 badge 없음 -->
  </div>
  <div class="card__body">
    <p class="card__title">{title}</p>
    <p class="card__meta">
      <time class="card__time" datetime="{scheduled_start ISO}">08/31 20:00</time>
      <span class="card__rel">3시간 후</span>   <!-- live 면 "방송 중", 예정 시각 지남(live 미확인)이면 class="card__rel card__rel--late" + "n분 지각" -->
    </p>
  </div>
</a>
```

예고 카드(`status=="scheduled"`, §1-1) — 썸네일 없음, 채널 링크만:

```html
<a class="card card--scheduled" href="{channels[key].channel_url}" target="_blank" rel="noopener">
  <!-- assumed_live 면 class="card card--scheduled card--sched-live", .card__rel = "방송 중 (추정)"(빨강), 테두리 실선·빨강기 -->
  <!-- (v2.4) kind=="collab" 이면 class 에 card--collab 추가, href={url}(그룹 영상), 배지 "합동" -->
  <div class="card__thumb-wrap">
    <span class="card__icon">🎮</span>            <!-- icon 없으면 class="card__icon card__icon--empty" + "📺" -->
    <span class="card__badge card__badge--sched">예고</span>   <!-- collab: card__badge--collab "합동" -->
  </div>
  <div class="card__body">
    <span class="card__chip">🔒 회원 전용</span>     <!-- members_only 일 때만 -->
    <p class="card__title card__title--label">게임</p>  <!-- KIND_LABEL[kind]. unknown 이면 이 <p> 생략. collab 이면 "합동 · {그 레인 제외한 참여자 name_ko}" -->
    <p class="card__host">공식 채널 합동방송</p>       <!-- (v2.4) host=="group" 일 때만 -->
    <p class="card__meta">
      <time class="card__time" datetime="{scheduled_start ISO}"><span class="card__approx">약 </span>08/31 07:00</time>
      <span class="card__rel">약 5시간 후</span>    <!-- scheduled 는 card__rel--late 안 붙임. scheduled_start 없으면 <time> 생략 + "시간 미정" -->
    </p>
  </div>
</a>
```

- 라이브인데 `scheduled_start` 없으면 `<time>` 은 `actual_start` 사용, 없으면 `<time>` 생략하고 `card__rel` 만 "방송 중".
- 전체 재렌더 방식 허용(폴링마다 `#board` 재구성). 단 `updateCountdowns()` 는 DOM 재구성 없이 `.card__rel` 텍스트만 갱신.
- XSS 방지: 데이터는 `textContent`/`createElement` 로만 주입. `innerHTML` 금지(`onerror` 속성만 예외).

---

## 4. 계약 D — 시간 표기 규칙 (`time.js`)

- 저장은 UTC, 표시는 **KST(UTC+9)**. `Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul'})`.
- `formatKST(iso)` → `"MM/DD HH:mm"` (24h, KST). 예: `"08/31 20:00"`.
- `relativeLabel(iso, nowMs)`:
  | 조건 (start − now) | 출력 |
  |---|---|
  | < −5분 (예정 시각을 5분 넘게 지남, upcoming→live 전환 미확인) | `"{n}분 지각"` / `"{h}시간 {m}분 지각"` (최소 1분) |
  | < 60초 | `"곧 시작"` |
  | < 24시간 | `"{h}시간 {m}분 남음"` (h==0: `"{m}분 남음"`, m==0: `"{h}시간 남음"`) |
  | < 7일 | `"{n}일 후"` (올림, 최소 1) |
  | ≥ 7일 | `formatKST(iso)` 그대로 |
- `LATE_GRACE_MS`(5분): 예정 시각을 막 지나도 곧바로 "지각" 판정 안 함.
- `isLate(iso, nowMs)`: `scheduled_start` 를 5분 넘게 지났는지(boolean). `render.js` 가 `.card__rel--late` 토글에 사용.
- 라이브 카드 상대 라벨은 `render.js` 가 `"방송 중"` 으로 고정(time.js 호출 안 함).
- `.card__rel` 텍스트는 `updateCountdowns()` 가 **1분마다 사용자 장치 시계 기준**으로 갱신
  (`main.js` `COUNTDOWN_TICK_MS`). 카드가 다른 시간대 구간으로 넘어가면 `true` 반환 → `main.js` 가 보드 재렌더(재분류).

---

## 5. 계약 E — `pending.json` 스키마 (data 브랜치 루트)

```jsonc
{
  "updated_at": "2026-08-31T12:00:00Z",          // ISO UTC 'Z'. 엔트리 변경 시 갱신
  "entries": {
    "<video_id>": {
      "channel_key": "arale",
      "phase": "pre-live",                         // "pre-live" | "live-watch"
      "scheduled_start": "2026-08-31T13:00:00Z",   // 최신 예정 시각. live-watch 에서 null 가능
      "actual_start": null,                        // phase=="live-watch" 에서 채움
      "next_check_at": "2026-08-31T12:45:00Z",     // 다음 Cloud Task 도달 예정
      "attempts": 0,                               // 현재 phase 에서 처리된 횟수
      "first_seen": "2026-08-31T09:00:00Z",
      "last_checked": null
    }
  }
}
```

- 기본형(파일 없음): `{"updated_at": null, "entries": {}}`.
- `entries` key = video_id. 직렬화 규칙은 §7.

---

## 6. 계약 F — `control.json` (data 브랜치 루트, v2.1)

```jsonc
{
  "paused": false,
  "since": null,               // paused=true 로 바뀐 시각 (ISO 'Z'), 아니면 null
  "by": null,                  // "telegram:/pause" 등 출처 메모
  "log_level": "normal",       // "detail" | "normal" | "simple"  — Telegram 알림 상세도
  "updated_at": "2026-08-31T12:00:00Z"
}
```

- 기본형(파일 없음): `{"paused": false, "since": null, "by": null, "log_level": "normal", "updated_at": null}`.
- **log_level 별 전송 이벤트** (`notify.allows(level, kind)`):
  | 종류 | detail | normal | simple |
  |---|:-:|:-:|:-:|
  | A upcoming / B live_start / C live_end | ✓ | ✓ | ✗ |
  | D sync 요약 | 매 실행 | ✗ | ✗ |
  | E fallback / F 오류 / 다운 알림 | ✓ | ✓ | ✓ |

`control.py` (순수 헬퍼): `default_control()`, `is_paused(c)`, `get_log_level(c)`(이상값→"normal"),
`set_paused(c, paused, *, by, now_iso)`, `set_log_level(c, level, *, by, now_iso)`(이상 level→ValueError).
`set_*` 는 원본 복사 후 해당 키만 갱신(다른 필드 유실 금지). 로드/저장은 호출부가
`GitHubStore.read_json/write_json("control.json")` 로 직접.

---

## 6-1. 계약 G — `admin_state.json` (data 브랜치 루트, v2.5)

텔레그램 수동 관리 명령(`/list` `/del` `/ingest` `/undo`, `docs/plan/v2_5_admin_commands.md`)의
상태. `pending_del`/`undo` 각각 슬롯 1개(새 값이 오면 이전 값을 덮어씀).

```jsonc
{
  "pending_del": null | {
    "unit": "arale",             // /del 대상 유닛
    "idx": 2,                    // /list 당시 1-based 순번 (표시용 — 매칭은 snapshot 사용)
    "snapshot": { /* ... */ },   // 지우려는 broadcasts[] 항목 원본 (확인 시 재대조)
    "warn_text": "...",
    "at": "2026-09-05T12:00:00Z" // 확인 대기 시작 (TTL 300s, admin.PENDING_DEL_TTL_SEC)
  },
  "undo": null | {
    "action": "/del arale#2",    // 사람이 읽을 설명
    "prev_content": { /* schedule.json 전체(변경 직전) */ },
    "new_sha": "...",            // 변경 커밋 직후 schedule.json sha (undo 시 CAS 확인용)
    "at": "2026-09-05T12:00:05Z"
  }
}
```

`src/backend/admin.py` (순수 헬퍼): `default_admin_state()`,
`get_pending_del(s)`/`set_pending_del(s, *, unit, idx, snapshot, warn_text, now_iso)`/`clear_pending_del(s)`,
`pending_del_expired(pending, now_iso, ttl_sec=300)`,
`get_undo(s)`/`set_undo(s, *, action, prev_content, new_sha, now_iso)`/`clear_undo(s)`.
`set_*`/`clear_*` 는 원본 복사 후 해당 슬롯만 갱신(다른 슬롯 보존).

`/undo` 판정: 지금 `schedule.json` sha `==` 기록된 `new_sha` 일 때만 `prev_content` 로 복원.
다르면(정기 `/tick` 이 그 사이 supersede/TTL 제거했거나 다른 명령이 또 건드림) 거부 —
`prev_content` 로 무작정 덮으면 그 사이의 정당한 변경이 같이 날아가기 때문. 상세 근거는
`docs/plan/v2_5_admin_commands.md` §4.

---

## 7. 직렬화 / 시간 규칙 (전 모듈 공통)

- JSON 저장: `json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"` (끝 개행 1개).
  `store.save_json_if_changed` / `gh_store._serialize` 동일. 어기면 불필요한 커밋 발생.
- ISO 파싱: `datetime.fromisoformat(s.replace("Z", "+00:00"))`, 항상 tz-aware UTC.
- ISO 출력: `dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.
- 시각 비교·산술은 전부 UTC. KST 변환은 프론트 `time.js` 전담.

---

## 8. 백엔드 모듈 (`src/backend/`)

### 8.0 재사용 (`src/collector/*` — 수정 금지, import)

- `rss.py` — `fetch_rss_video_ids`, `fetch_all_rss_video_ids`, `_parse_rss` (쿼터 0).
- `youtube.py` — `VideoInfo`(dataclass), `YouTubeClient`(`videos_list` / `search_upcoming` /
  `channels_list`, `quota_used` 카운터), `_video_from_item`.
  - `VideoInfo`: `video_id, channel_id, title, thumbnail, live_state("none"|"upcoming"|"live"),
    scheduled_start, actual_start, actual_end, concurrent_viewers`.
  - `videos_list`: `part=snippet,liveStreamingDetails`, 50개 청크, 호출당 `quota_used += 1`.
  - `search_upcoming`: `quota_used += 100`. 오류 시 `[]` + warning.
- `reconcile.py` — `build_schedule(channels_cfg, videos, prev_schedule, now_iso, avatars=None) ->
  (new_schedule, newly_ended)`, `ended_record`. 순수 함수(네트워크/파일 금지).
  - 후보 = RSS videoId ∪ 이전 schedule 의 미해결(upcoming/live) ∪ (deep) `search.list?eventType=upcoming`.
  - `live_state` 분기: `upcoming`/`live` 유지, `none` 은 추적 중이었으면 `ended`/`canceled` 이관.
  - `removed` 유예: `STALE_REMOVE_SEC`(6.5h) — §2, §11.
  - `scheduled` 행 보존/supersede/만료/`assumed_live` — §1-1.
- `config.py` — `load_channels()`, `channel_url(handle)`.
- `src/collector/main.py` (v1 오케스트레이터)는 Actions break-glass 경로용으로만 유지. v2 코드는 무의존.

### 8.1 `pending.py` + `statemachine.py` (순수 — 네트워크·파일·시계 금지, `now_iso` 인자)

#### `pending.py`
```python
PHASE_PRELIVE = "pre-live"; PHASE_LIVEWATCH = "live-watch"
def default_pending() -> dict                                   # {"updated_at": None, "entries": {}}
def make_entry(*, channel_key, scheduled_start, next_check_at, now_iso,
               phase=PHASE_PRELIVE, actual_start=None) -> dict   # attempts=0, first_seen=now_iso, last_checked=None
def validate(pending) -> dict                                    # 구조 방어. 이상 엔트리 제외한 새 dict(원본 불변) + warning
```

#### `statemachine.py` — FSM 상수 (config 아님, 코드 고정)
| 상수 | 값 | 의미 |
|---|---|---|
| `PRELIVE_LEAD_SEC` | 15분 | 최초 wake = `scheduled_start − 15분` |
| `PRELIVE_TIGHT_SEC` | 3분 | `scheduled_start` 지난 뒤 촘촘 간격 |
| `PRELIVE_FALLBACK_AFTER_SEC` | 60분 | `scheduled_start + 60분` 경과 → fallback |
| `FALLBACK_RETRY_SEC` | 60분 | fallback 재시도 간격 |
| `FALLBACK_MAX_ATTEMPTS` | 6 | 6회 연속 미확인 → canceled, 엔트리 드롭 |
| `LIVEWATCH_EARLY_SEC` | 30분 | 라이브 시작 후 초기 간격 |
| `LIVEWATCH_EARLY_WINDOW_SEC` | 60분 | "초기" 구간 (시작 ~ +60분) |
| `LIVEWATCH_TIGHT_SEC` | 3분 | 라이브 +60분 이후 간격 |
| `MAX_TASK_HORIZON_SEC` | 696시간 | Cloud Tasks 720h 하드리밋보다 보수적인 롱폴링 상한 |

```python
@dataclass
class Decision:
    new_pending: dict
    enqueue: list[tuple[str, str]]   # [(video_id, schedule_time_iso)]
    dropped: list[str]
    log: list[str]

def sync_pending(prev_pending, videos, channel_id_to_key, now_iso, *,
                 mode: str,                  # "wake" | "sync"
                 woken_video_id: str | None = None) -> Decision
```
`pending.json` 과 Cloud Tasks enqueue 목록만 계산 (schedule/archive 는 `reconcile` 담당). 흐름:

1. **신규 엔트리 감지** (mode 무관): `videos` 중 pending 에 없는 것 —
   `upcoming`+`scheduled_start` → pre-live 엔트리, `next = max(ss − LEAD, now+60s)`, enqueue.
   `live` → live-watch 엔트리(`actual_start` 채움), `next = now + EARLY`. 그 외 무시.
2. **drift refresh**: pre-live 엔트리의 `v.scheduled_start` 가 바뀌고 미래면 → 갱신 + 재예약, `attempts=0`.
3. **due 처리** (`next_check_at <= now`; `mode=="wake"` 면 `woken_video_id` 는 무조건 포함):
   - **pre-live**: `none`/누락 → `attempts+=1`, ≥6 이면 drop("canceled"), 아니면 `now+RETRY`.
     `live` → live-watch 전이, `now+EARLY`. `upcoming` → `now<ss`: `ss` / `<ss+FALLBACK_AFTER`: `now+TIGHT` /
     그 이후: `now+RETRY`.
   - **live-watch**: `none`/누락 → drop("ended"), enqueue 없음. `live` → `elapsed<EARLY_WINDOW`: `now+EARLY`,
     아니면 `now+TIGHT`. `upcoming`(드묾) → pre-live 로 되돌림.
4. **마무리**: 변경 있으면 `updated_at=now_iso`. enqueue 시각은 `[now+60s, now+696h]` 클램프,
   살아있는 엔트리 `next_check_at` 도 그 값에 맞춤.

### 8.2 `gh_store.py` — GitHub Contents API (`requests`)

```python
class GitHubStore:
    API = "https://api.github.com"
    def __init__(self, token, repo, branch="data", *, session=None, timeout=15.0)   # token 비면 ValueError
    def read_json(self, path) -> tuple[dict | None, str | None]                       # 200→(data, sha) / 404→(None,None) / else→RuntimeError
    def write_json(self, path, data, *, prev_sha, message) -> tuple[bool, str | None]
class ConflictError(RuntimeError): ...
```
- `write_json` 직렬화 = §7. 절차: (1) 현재 원격 재조회, 내용 동일하면 `(False, sha)` — PUT 안 함.
  (2) `prev_sha` 주어졌는데 현재 sha 와 다르면 → 남이 **다른 내용**을 커밋한 것 → `ConflictError`.
  (3) 아니면 PUT. 409/422 → `ConflictError`. (4) 네트워크 오류만 재시도, 그 외 상태코드 → RuntimeError.
  `prev_sha=None` 이면 sha 검사 없이 씀(부트스트랩).
- **낙관적 동시성**: 예전엔 충돌 시 낡은 payload 를 새 sha 로 재-PUT 해 조용히 덮어써서, 방송 시작
  시간대에 tick/wake 가 겹치면 pending 전이가 유실됐다. 이제 `ConflictError` → `handlers` 재계산.

### 8.3 `tasks.py` (`google.cloud.tasks_v2`) + `oidc.py` (`google-auth`)

```python
class TaskQueue:
    def __init__(self, *, project, location, queue, target_url, invoker_sa, client=None)
    def enqueue_wake(self, video_id, schedule_time_iso) -> str   # path="/wake", body={"video_id":…}, name=f"wake-{vid}-{분버킷}"
    def enqueue_tick(self, mode, schedule_time_iso) -> str       # path="/tick", body={"mode":…}, name=f"tick-{mode}-{분버킷}"
def _build_task(cfg, *, path, body, name_key, schedule_time_iso) -> dict   # 순수. oidc_token: {service_account_email: invoker_sa, audience: target_url}
```
- 태스크 이름의 **분 버킷**(schedule_time epoch // 60)으로 dedupe: 같은 이름·같은 분 재시도는
  `AlreadyExists` 무시, 다른 시각은 새 태스크. gcloud `--args` 값이 `-` 로 시작하면 `--args=...` 로 붙일 것.

```python
def verify_request(headers, *, expected_audience, expected_sa=None) -> None
```
- `Authorization: Bearer <JWT>` 파싱 → `verify_oauth2_token(..., audience=expected_audience)` →
  `iss` 확인 → `expected_sa` 주어지면 `payload["email"]==expected_sa` 확인. 실패 시 `PermissionError`.
  `ALLOW_UNAUTH == "1"` 이면 즉시 return(로컬).

### 8.4 `handlers.py` — `tick(mode)` / `wake(video_id)`

공통 흐름:
1. **control 가드 (맨 앞)**: `control, _ = gh.read_json("control.json")`; `is_paused` 면 healthcheck
   핑만 하고 `{"paused": True}` 반환. `/wake` 도 동일.
2. `cfg = load_channels()`; `gh = GitHubStore(...)`; `prev_schedule/pending/archive` + 각 sha 읽기.
3. 후보 video_id 집합 — `wake`: `{video_id} ∪ pending.keys() ∪ schedule 의 upcoming/live`.
   `tick`: `∪ fetch_all_rss_video_ids` 전부.
4. `yt = YouTubeClient(...)`; `avatars = yt.channels_list(...)` **`mode=="baseline"` 일 때만**;
   `videos = yt.videos_list(sorted(후보))`.
5. **커밋 루프 (최대 2회, ConflictError 재시도)** — RSS/YouTube 는 한 번만, `videos` 재사용:
   a. `prev_*` / `*_sha` 를 루프 안에서 **새로** 읽는다.
   b. `new_schedule, newly_ended = build_schedule(cfg, videos, prev_schedule, now_iso, avatars)`;
      `_stable_view` 변화 없으면 volatile 필드(`generated_at`/`last_updated`/`concurrent_viewers`)
      동결 + `generated_at` heartbeat(20분).
   c. `decision = sync_pending(prev_pending, videos, channel_id_to_key, now_iso,
      mode=("wake" if wake else "sync"), woken_video_id=…)`.
   d. `gh.write_json` × 3 (schedule / archive(변경 시) / pending), 각각 위 `*_sha` 를 `prev_sha` 로.
      `ConflictError` → 1회 a 로 되돌아가 재계산. 2회째 실패 → 예외(스케줄러 재시도).
6. **Cloud Tasks enqueue**: `decision.enqueue` 전부 `enqueue_wake`. `newly_ended` 있으면
   `enqueue_tick("light", now + _POST_END_RECHECK_SEC(20분))` **1개**(분버킷 dedupe) — 백투백 다음
   방송을 ~20분 내에 줍는다. `scheduled` 행이 있으면 `_scheduled_wake_times` 가 `scheduled_start`
   마다 `light /tick` 1개 예약(§1-1).
7. **Telegram diff**: 루프 진입 전 스냅샷(`_ps0`)과 `new_schedule` 을 `diff_events` 로 비교(재시도로
   루프 안 `prev_schedule` 이 바뀌어도 전이 알림 유지). 이벤트 개별 전송 + 조건 충족 시 요약(D).
8. **성공 끝**: `HEALTHCHECK_URL` 있으면 GET 1발(실패 무시). **예외 경로**: `notify.error_text` 전송 후 re-raise.

반환 dict: `{"mode","woken","candidates","videos","schedule_changed","archive_changed","archived",
"pending_changed","pending_entries","dropped","enqueue_planned","enqueued","enqueue_errors",
"quota_used","log"}`.

### 8.5 `app.py` (비공개, OIDC)

```python
@app.post("/tick")   # oidc.verify_request → handlers.tick(mode="light" 기본)
@app.post("/wake")   # oidc.verify_request → video_id 필수(없으면 400) → handlers.wake(vid)
@app.get("/healthz") # "ok", 200
```
- 예외 → 500 + `{"error": str(e)}` 로깅. `PermissionError` → 403.
- `videos.list` 쿼터 실패(RuntimeError)는 500 반환 → Cloud Tasks 큐 기본 재시도.

### 8.6 `notify.py` (v2.1) — Telegram `sendMessage` (`requests`)

```python
class Telegram:
    def __init__(self, token, chat_id, *, session=None, timeout=10.0)   # 비면 disabled → send() no-op + warning
    def send(self, text, *, parse_mode="HTML", silent=False) -> bool     # 실패는 예외 없이 False + warning

@dataclass
class Event: kind; channel_ko; title; text   # kind: "upcoming"|"live_start"|"live_end"|"fallback"

def diff_events(prev_schedule, new_schedule, newly_ended, sm_log, channels_cfg, now_iso) -> list[Event]
def summary_text(result, now_iso) -> str    # D(요약) 본문
def error_text(where, exc) -> str           # F(서버 오류) 본문
```
- `diff_events` 순수. **첫 실행 가드**: `prev_schedule.generated_at` 가 None 이거나 prev broadcasts
  0개면 upcoming(A) 이벤트 생성 안 함(초기 스팸 방지).
  - A upcoming: new 에 `status=="upcoming"` 인데 prev 에 없음.
  - B live_start: `upcoming`→`live` 또는 new 에 `live` 로 등장. `lateness = actual_start − scheduled_start`.
  - C live_end: `newly_ended` 각 레코드. `reason` → 사유 라벨. 길이 = `actual_end − actual_start`.
  - E fallback: `sm_log` 중 `"fallback "` 로 시작하는 토큰(`statemachine` 이 fallback 진입 시 append).
- 지각 라벨: `lateness_sec > 300` → `"{n}분 지각"`; `−300..300` → `"정시"`; `< −300` → `"{n}분 일찍"`.

### 8.7 `telegram_app.py` (v2.1) — 공개 webhook 서비스

Flask. 엔트리포인트 `src.backend.telegram_app:app`. 같은 이미지, 배포 시 `--command`/`--args` 로 지정.
`ALLOW_UNAUTH=1` (OIDC 검증 안 함 — 자체 시크릿 인증. `/tick`·`/wake` 라우트 없음).

```
POST /telegram   # Telegram webhook
POST /ingest     # (v2.3) 폰 Automate → X 알림 텍스트 릴레이
GET  /           # 200 헬스체크
```

**`/telegram`**: (1) `X-Telegram-Bot-Api-Secret-Token == cfg.telegram_webhook_secret` 아니면 200
무시. (2) `message.chat.id != cfg.telegram_chat_id` → 200 무시. (3) `text` 파싱. (4) 항상 **200**
반환, 응답은 `sendMessage` 로 별도.
- `/status` — 라이브·예정 버킷 카운트·대기 wake 수+가장 이른 `next_check_at`·마지막 tick
  (`generated_at` 상대)·`paused` 상태·`log_level`.
- `/pause` — `set_paused(True, by="telegram:/pause")` → `write_json`.
- `/resume` — `set_paused(False)` → write → 메인 `POST {MAIN_SERVICE_URL}/tick {"mode":"light"}` 를
  OIDC 발급해 호출(heal). 런타임 SA 가 메인서비스 `run.invoker` 필요.
- `/log [detail|normal|simple]` — `control.json.log_level`. 인자 없으면 현재값.
- **(v2.5)** `/list [유닛]` — `schedule.json` 방송을 유닛별 idx 로 나열(상태순→시각순).
  `/del <유닛> <idx>` — 2단계 확인(y/N, 경고 DM) 후 삭제, 확인 대기는 `admin_state.json` `pending_del`
  (슬롯 1개, TTL 300s). `/ingest <트윗 원문>`(별칭 `/add`) — `POST /ingest` 라우트와 별개 네임스페이스,
  같은 파싱·반영 경로 재사용, ECHO/DRY-RUN 무관 항상 실제 반영. `/undo` — 이 봇으로 방금 반영된
  변경 1건만 되돌림(`admin_state.json` `undo`, sha 불일치면 거부). 상세: §6-1, `docs/plan/v2_5_admin_commands.md`.

**`/ingest`** (v2.3 X 릴레이): `X-Ingest-Secret` 헤더 == env `INGEST_SECRET`. 본문 form/JSON 의
`text`(필수)/`title`(선택).
- 폰 Automate 빌드가 `urlEncode({"text": expr})` 의 값을 폼 **키** 자리로 흘리므로 — `text` 값이
  비고 (`text`/`title` 외) 폼 키가 딱 하나 + 그 값도 비면 **그 키 이름을 원문으로 복구**한다
  (`# ponytail:` 표시. 폰에서 `"text=" ++ urlEncode(...)` 로 제대로 보낼 수 있게 되면 삭제).
- `INGEST_ECHO=1`: 파싱·저장 안 함. 받은 텍스트 DM 회신 + `ingest ECHO: len=.. tail_ok=..` 로그.
  `xrelay.looks_relayable`(본문에 `配信スケジュール` 또는 `出演情報`) 이면 `ingest_queue.json` 에 적재.
- `INGEST_DRY_RUN=1`: 파싱은 하고 저장 안 함. 원문 + 파싱 결과 DM.
- 실배포(`INGEST_ECHO=0`·`INGEST_DRY_RUN=0`): `control.json` `paused` 확인 → `_ingest_queue_drain`
  이 큐 원문을 `received_at` 순서로 `xrelay.parse` → `merge_scheduled` → `schedule.json` 커밋,
  큐 비움. 이번 요청 본문도 파싱·머지. 결과 DM(계약 G `xrelay.summary_text`).
- `xrelay.py` (순수): `parse(text, now_iso)` — 일일 스케줄(`parse_bdp_schedule`) 우선, 없으면
  `parse_appearance`(`出演情報`). `looks_relayable`, `merge_scheduled`(replace-by-date), `summary_text`.
  `APPEARANCE_MARK_RE = re.compile(r"出演情報")` — 실측 확인된 유일 마커. 변형은 실물 트윗에서 본 뒤 추가.

### 8.8 `config.py` — 환경변수 → Config

`load_config()` 는 누락돼도 통과(기능만 off, 로컬 예외). 목록:
```
GITHUB_TOKEN, GITHUB_REPO, DATA_BRANCH(기본 "data"), YOUTUBE_API_KEY,
GCP_PROJECT, GCP_LOCATION, TASKS_QUEUE, SERVICE_URL, INVOKER_SA, ALLOW_UNAUTH(기본 "")
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_WEBHOOK_SECRET(telegram_app 만),
HEALTHCHECK_URL(메인 tick 만), MAIN_SERVICE_URL(telegram_app /resume), INGEST_SECRET,
INGEST_ECHO, INGEST_DRY_RUN
```

---

## 9. 프론트엔드 모듈 (`src/frontend/`)

- **index.html**: `<head>` 에 3개 css, `<script type="module" src="js/main.js">`. body 는
  `<main id="board">` + `<footer id="foot">` 빈 컨테이너. `lang="ko"`, viewport 메타.
- **css/reset.css**: 최소 리셋. **css/layout.css**: `#board` 데스크톱(≥1100px)
  `grid-template-columns:repeat(5,1fr)`, `<1100px` `grid-auto-flow:column` + `overflow-x:auto`(가로 스크롤).
  **css/card.css**: mobile `@media` 는 파일 끝. PC 카드 고정 세로 `--card-h`(썸네일 132px),
  모바일 가로 레이아웃. `.card__title` PC 1줄 넘치면 `applyMarquees()` 무한 흐름.
- **js/config.js** — 상수만: `DATA_URL`(raw githubusercontent data/schedule.json), `POLL_MS=75000`,
  `COUNTDOWN_TICK_MS=60000`, `FETCH_TIMEOUT_MS=8000`, `FALLBACK_CHANNEL_ORDER`, `FALLBACK_CHANNELS`.
- **js/time.js** — 계약 D. `formatKST(iso)`, `relativeLabel(iso, nowMs=Date.now())`. 순수, DOM 접근 없음.
- **js/api.js** — `fetchSchedule(url)`: AbortController + `FETCH_TIMEOUT_MS`, `cache:"no-store"`.
  성공 `{ok:true, data}` / 실패 `{ok:false, error:Error}`.
- **js/render.js** — `renderBoard(boardEl, schedule, nowMs)` (계약 C 전체 재구성),
  `renderFooter(footEl, schedule, {stale})`, `updateCountdowns(boardEl, nowMs)` (`.card__rel` 텍스트만).
  `channel_key` 로 broadcasts 그룹핑, 알 수 없는 key 무시.
- **js/main.js** — `poll()`: `fetchSchedule` 성공 시 `renderBoard`+`renderFooter{stale:false}`,
  실패 시 마지막 데이터 유지 + `{stale:true}`. `DOMContentLoaded` → `poll()` + `setInterval(poll, POLL_MS)`
  + `setInterval(() => updateCountdowns(board), COUNTDOWN_TICK_MS)`.

---

## 10. Telegram 모니터링·제어 (v2.1) — 결정 사항

- **결정 1 — 인바운드는 별도 공개 서비스**: Telegram webhook 은 OIDC 를 못 붙이므로 공개
  엔드포인트 필요. 메인 `mewtype-backend` 를 공개로 바꾸는 대신 같은 이미지를 다른 엔트리포인트로
  띄운 `mewtype-telegram`(公開). 메인 보안 태세(`--no-allow-unauthenticated` + OIDC) 무변경.
  인증 = `X-Telegram-Bot-Api-Secret-Token` + `chat.id` 허용목록. 아웃바운드 알림(A~F)은 메인이 직접.
- **결정 2 — pause = 완전 중단 + resume 시 full heal**: `paused` 동안 `/tick` 은 healthcheck 핑만,
  `/wake` 는 200 즉시 반환(체인 휴면). `/resume` 은 `paused=false` 쓰고 곧바로 `tick("light")` 1회 —
  밀린 `next_check_at <= now` 엔트리가 재처리·재enqueue 되어 체인 복구.
- **결정 3 — tick 요약(D)은 변경 있을 때만**: `schedule_changed or newly_ended or dropped or
  enqueue_errors` 중 하나라도. A/B/C/E 는 항상 개별 전송.
- **결정 4 — 다운 감지 = healthchecks.io**: 메인 `/tick` 이 성공 끝에 `HEALTHCHECK_URL` GET 1발.
  grace(예: 3h30m) 초과 시 Telegram 알림. 스케줄러 멈춤 / Cloud Run 사망 둘 다 포착.

메시지 포맷은 한국어 HTML parse_mode (`docs/old/IMPLEMENTATION_v2.1.md` §4 예시 참고).

---

## 11. 사각지대 보정 패치

방송 패턴 실측(`ref/broadcast-patterns.md`)으로 드러난 3건. 상세: `docs/SCHEDULE.md` §1.1 / §5.

| # | 사각지대 | 보정 | 파일 |
|---|---|---|---|
| 1 | tick/wake 동시 실행 시 `write_json` 이 낡은 payload 로 조용히 덮어써 pending 전이 유실 | `ConflictError` + `handlers._run` 1회 재계산·재시도 (RSS/YT 재조회 없음) | `gh_store.py`, `handlers.py` |
| 2 | `videos.list` 일시 누락·"공개→회원전용" 전환을 즉시 `removed` archive → 오탐 잔류 | `last_updated` 기준 `STALE_REMOVE_SEC`(6.5h) 유예 후 이관 | `reconcile.py` |
| 3 | 일반 방송 종료 직후 시작하는 짧은 다음 방송을 3h tick 간격에 통째로 놓침 | 종료 감지 시 `now+20분` 후속 `light` tick 1개 예약(분버킷 dedupe) | `tasks.py`, `handlers.py` |

**커버 못 하는 것**: 회원 전용 방송은 RSS·`search.list` 어디에도 안 떠서 발견 자체가 불가 —
#3 재확인으로도 못 잡는다. 공개 방송의 백투백/재시작만 커버(구조적 한계, 별도 수집 경로 필요).

---

## 12. 인프라 / 배포

`requirements.txt`: `requests>=2.31`, `flask>=3.0`, `gunicorn>=21`, `google-cloud-tasks>=2.16`,
`google-auth>=2.28`.

`Dockerfile` (레포 루트): `python:3.12-slim` + `pip install -r src/backend/requirements.txt` +
`COPY src config`. `CMD` 는 `gunicorn ... src.backend.app:app` (메인). `mewtype-telegram` 은 배포 시
`--command=gunicorn --args=...,src.backend.telegram_app:app` 로 엔트리포인트만 교체.

`deploy/` (모든 값은 `deploy/env.sh` = 루트 `.env` 매핑, gitignore):
- `setup.sh` — API 활성화, SA 2개(`RUNTIME_SA`/`INVOKER_SA`), IAM(`cloudtasks.enqueuer`,
  `serviceAccountUser` on INVOKER_SA, `secretmanager.secretAccessor`), Cloud Tasks 큐, 시크릿
  (`YOUTUBE_API_KEY`, `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `INGEST_SECRET`). 멱등.
- `deploy.sh` — `gcloud run deploy mewtype-backend --source . --no-allow-unauthenticated
  --service-account RUNTIME_SA` + secrets/env. 배포 후 `SERVICE_URL` env 재설정, `INVOKER_SA` 에
  `run.invoker` 부여.
- `scheduler.sh` — `mewtype-baseline`(`0 6 * * *` Asia/Tokyo, `{"mode":"baseline"}`) /
  `mewtype-light`(`0 */3 * * *` Etc/UTC, `{"mode":"light"}`). 둘 다 OIDC(`INVOKER_SA`, audience=URL).
- `deploy_telegram.sh` — 같은 소스 + `--command=gunicorn --args=...,src.backend.telegram_app:app`
  `--allow-unauthenticated --service-account INVOKER_SA` `ALLOW_UNAUTH=1`. `INVOKER_SA` 에 메인서비스
  `run.invoker` 재확인(`/resume` heal 용).
- `telegram_webhook.sh` — `setWebhook` (`url=.../telegram`, `secret_token`, `allowed_updates=["message"]`).

`.github/workflows/collect.yml` — `on.schedule` 삭제됨, `workflow_dispatch` 만. 수동 break-glass
전용(pending.json 갱신 안 함). `date -u +%H` 산술 시 `$(( 10#$H ... ))` 필수(8진수 파싱 회피).

**Cloud Run/Scheduler/Tasks 는 같은 리전**(`asia-northeast1`). OIDC audience = 서비스 `status.url`
(배포마다 `SERVICE_URL` env 재설정). `mewtype-telegram` 은 `INVOKER_SA` 로 실행해야 `/resume` 의 메인
`/tick` 호출이 통과(메인 `oidc.verify_request` 가 caller email 검사).

healthchecks.io: 운영자가 project 1개 + check(period 3h, grace 40m) 생성 → ping URL 을
`HEALTHCHECK_URL` 로. Integrations 에서 Telegram 연결.

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
    "miyako": { "name": "藤都子 -Fuji Miyako-",           "name_ko": "후지 미야코",   "channel_id": "UCZXxRYaP7mfuglPnptnBBCA", "handle": "miyako_yumemita" }
  }
}
```
`channel_url` 은 코드에서 `https://www.youtube.com/@{handle}` 로 파생. **채널 추가/변경은 이 파일 한 곳만.**
