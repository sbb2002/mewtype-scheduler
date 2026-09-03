# 구현 명세 (IMPLEMENTATION)

PRD.md를 구현 단위로 분해한 문서. 모든 병렬 작업은 이 문서의 **인터페이스 계약**을 기준으로 하며,
계약을 벗어나는 변경은 이 문서를 먼저 고친다.

---

## 0. 저장소 구조

```
mewtype-scheduler/
├── src/
│   ├── frontend/               # Vercel Root Directory = src/frontend
│   │   ├── index.html
│   │   ├── css/
│   │   │   ├── reset.css
│   │   │   ├── layout.css      # 5-lane grid, 헤더, 반응형
│   │   │   └── card.css        # 카드/뱃지/빈 상태/상태바
│   │   └── js/                 # <script type="module">
│   │       ├── config.js
│   │       ├── time.js
│   │       ├── api.js
│   │       ├── render.js
│   │       └── main.js
│   └── collector/
│       ├── __init__.py
│       ├── main.py            # 오케스트레이션 (Sonnet 담당)
│       ├── config.py          # 설정 로드 (Sonnet 담당)
│       ├── rss.py
│       ├── youtube.py
│       ├── reconcile.py
│       ├── store.py
│       └── requirements.txt
├── config/
│   └── channels.json          # 5채널 단일 소스 (확정본, 수정 금지 대상 아님)
├── fixtures/
│   ├── schedule.sample.json   # 프론트/reconcile 공용 예시 데이터
│   └── rss_arale.xml          # rss.py 오프라인 테스트용
├── .github/workflows/
│   └── collect.yml
└── docs/IMPLEMENTATION.md
```

- 프론트는 빌드 단계 없음. ES 모듈을 브라우저가 직접 로드.
- 파이썬 3.12, 외부 의존성은 `requests` 만. 날짜는 표준 라이브러리로 처리(`Z`는 `+00:00`으로 치환).

---

## 1. 공용 계약 A — `schedule.json` 스키마 (동결)

`data` 브랜치 루트에 위치. 프론트가 `raw.githubusercontent.com`에서 직접 fetch.

```jsonc
{
  "generated_at": "2026-08-30T12:00:00Z",          // ISO UTC, 'Z'
  "channel_order": ["arale","yuno","nonoka","ritsu","miyako"],
  "channels": {
    "arale": {
      "name": "仲町あられ -Nakamachi Arale-",
      "name_ko": "나카마치 아라레",
      "channel_id": "UCWfF0DB6m_t2CE3KcOOOX7g",
      "handle": "arale_yumemita",
      "channel_url": "https://www.youtube.com/@arale_yumemita",
      "avatar": "https://yt3.googleusercontent.com/...=s176-c-k-c0x00ffffff-no-rj"  // deep 스캔이 channels.list로 취득. light는 이전 값 유지. 없을 수도 있음(프론트가 원형 폴백)
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
      "scheduled_start": "2026-08-31T11:00:00Z",     // ISO UTC. live에서도 유지(있으면)
      "actual_start": null,                          // live면 ISO UTC
      "concurrent_viewers": null,                    // live면 정수 가능(없으면 null)
      "first_seen": "2026-08-30T09:00:00Z",
      "last_updated": "2026-08-30T12:00:00Z"
    }
  ]
}
```

규칙:
- `broadcasts`는 `status=="live"` 먼저, 그다음 `scheduled_start` 오름차순으로 정렬해 저장(프론트도 재정렬하므로 방어적).
- 파일이 없을 때의 기본 형태: `{"generated_at": null, "channel_order": [...], "channels": {...}, "broadcasts": []}`.
- 프론트는 `channel_order`/`channels`가 비면 `config.js`의 폴백을 쓴다.

### 1-1. `status == "scheduled"` 행 (v2.3 — X 릴레이)

`broadcasts[]` 에 `video_id` 없는 행이 섞일 수 있다. X(트위터) `@BDP_yumemita` 일일 스케줄
트윗이 폰(Automate) → `mewtype-telegram` `POST /ingest` 로 릴레이돼 만들어진, **YouTube 영상이
아직 없는 최하 단계**다. 설계·파서 규칙: `docs/plan/v2_3_x_relay.md`.

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
  "source": "bdp_schedule",
  "source_at": "2026-09-03T01:05:00Z",
  "first_seen": "...", "last_updated": "...",
  "expires_at": "2026-08-30T05:00:00Z"               // scheduled_start+3h. null 이면 first_seen+18h
}
```

- 정렬 확장: `live` → `upcoming` → `scheduled`, 그룹 내 `scheduled_start` asc(null 뒤).
- `reconcile.build_schedule` 이 매 tick 보존한다. 같은 채널 실물 `upcoming`/`live` 가 ±4h 안에
  뜨면 제거(supersede), `expires_at` 도달 시 제거. Cloud Tasks/`pending.json` 은 안 탄다.
- **프론트 v1 은 이 행을 무시**한다(live/upcoming 필터 밖) — `.card--scheduled` 렌더는 후속.

## 2. 공용 계약 B — `archive.json` 스키마

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
- append-only, `video_id` 기준 dedupe. v1 프론트는 읽지 않음.
- `reason`: `ended`(정상 종료, `actual_end` 있음) / `canceled`(`liveBroadcastContent=="none"` 인데 `actual_end` 없음) /
  `removed`(응답에서 통째로 사라짐). v2 는 `removed` 를 즉시 이관하지 않고 `last_updated` 기준
  약 6.5h 연속 누락일 때만 이관한다 (일시 누락·비공개 전환 오탐 방지 — `IMPLEMENTATION_v2.md` §8).

## 3. 공용 계약 C — 프론트 DOM 구조 (동결)

`render.js`가 생성하고 `css/`가 스타일링하는 정확한 구조. class 이름 변경은 이 문서 수정 후에만.

```html
<main id="board">
  <section class="lane" data-channel="arale" style="--lane-color: rgb(...)">
    <!-- --lane-color: render.js가 아바타 평균색을 canvas 샘플링해서 인라인 설정. 실패 시 CSS 폴백 -->
    <header class="lane__header">   <!-- ::before = 좌→우 캐릭터색 그라데이션 -->
      <a class="lane__link" href="{channels[key].channel_url}" target="_blank" rel="noopener">
        <span class="lane__avatar" style="background-image:url('{avatar =s176}')"></span>  <!-- 원형, 없으면 빈 원 -->
        <span class="lane__meta">
          <span class="lane__name-line">
            <span class="lane__name-ko">나카마치 아라레</span>
            <span class="lane__name-orig">仲町あられ -Nakamachi Arale-</span>   <!-- 작게·회색, 넘치면 … -->
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
      <span class="card__rel">3시간 후</span>   <!-- live면 "방송 중", 예정 시각 지남(live 미확인)이면 class="card__rel card__rel--late" + "n분 지각" -->
    </p>
  </div>
</a>
```

- 라이브인데 `scheduled_start`가 없으면 `<time>`은 `actual_start` 사용, 없으면 `<time>` 생략하고 `card__rel`만 "방송 중".
- 전체 재렌더 방식 허용(폴링마다 `#board` 재구성). 단 `updateCountdowns()`는 DOM 재구성 없이 `.card__rel` 텍스트만 갱신.

## 4. 공용 계약 D — 시간 표기 규칙 (`time.js`)

- 저장은 UTC, 표시는 **KST(UTC+9)**. `Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul'})` 사용.
- `formatKST(iso)` → `"MM/DD HH:mm"` (24h, KST). 예: `"08/31 20:00"`.
- `relativeLabel(iso, nowMs)`:
  | 조건 (start - now) | 출력 |
  |---|---|
  | < -5분 (예정 시각을 5분 넘게 지남, 아직 upcoming=live 전환 미확인) | `"{n}분 지각"` / `"{h}시간 {m}분 지각"` (최소 1분) |
  | < 60초 (예정 시각 임박 ~ 5분 지각 전까지 포함) | `"곧 시작"` |
  | < 24시간 | `"{h}시간 {m}분 남음"` (h==0: `"{m}분 남음"`, m==0: `"{h}시간 남음"`) — '오늘' 구간 카운트다운 |
  | < 7일 | `"{n}일 후"` (올림, 최소 1) |
  | ≥ 7일 | `formatKST(iso)` 그대로 |
  `LATE_GRACE_MS`(5분)는 오차 범위 — 예정 시각을 막 지나도 곧바로 "지각"으로 판정하지 않는다.
- `isLate(iso, nowMs)`: `scheduled_start`를 5분(`LATE_GRACE_MS`) 넘게 지났는지 여부(boolean).
  `render.js`가 `.card__rel--late` 토글에 사용 — 지각 중인 카드는 `--color-late`(주황) 로 강조.
- 라이브 카드의 상대 라벨은 render.js가 `"방송 중"`으로 고정(‑> time.js 호출 안 함).
- `.card__rel` 텍스트는 `updateCountdowns()`가 **1분마다 사용자 장치 시계 기준**으로 갱신
  (`main.js`의 `COUNTDOWN_TICK_MS`). 시간이 흘러 카드가 다른 시간대 구간으로
  넘어가면 `updateCountdowns()`가 `true`를 반환해 `main.js`가 보드를 재렌더(재분류)한다.
  데이터 브랜치와 무관.

---

## 5. 모듈별 상세 & 담당

### [FE] `src/frontend/*` — 담당: haiku #1 (프론트 전체)

입력: 계약 A(JSON), C(DOM), D(시간), `UI.png`, `fixtures/schedule.sample.json`.

- **index.html**: `<head>`에 3개 css 링크, `<script type="module" src="js/main.js">`. body에 `<main id="board">`(빈 컨테이너)와 `<footer id="foot">`. 페이지 타이틀 "夢限大みゅーたいぷ 방송 예고". `lang="ko"`. viewport 메타.
- **css/reset.css**: 최소 리셋(box-sizing, margin 0, img display block/max-width 100%, a 상속).
- **css/layout.css**:
  - `#board`: 데스크톱(≥1100px) `display:grid; grid-template-columns:repeat(5,1fr); gap`.
  - `<1100px`: `grid-auto-flow:column; grid-auto-columns:minmax(240px,1fr); overflow-x:auto`(레인 구조 유지, 가로 스크롤).
  - `.lane`: 세로 flex, 상단 헤더 sticky 선택.
  - `.lane__header`: 방송인명. `.lane__name-ko` 강조, `.lane__name-orig` 작게 1줄 말줄임.
  - `#foot`: 하단 고정 바, 작은 글씨.
- **css/card.css** (mobile `@media` 블록은 파일 끝 — layout.css 뒤 로드라 기본 규칙을 확실히 덮음):
  - PC: `.card`는 **고정 세로 크기 `--card-h`**(썸네일 132px + 본문). 폭 = 레인 컬럼. 세로 레이아웃.
    모바일(`<768px`): 가로 레이아웃(작은 썸네일 좌 42%/최대150px + 텍스트 우), `height:auto`.
  - `.card__thumb-wrap`: PC 고정 `height:132px` + `object-fit:cover`. 모바일은 `aspect-ratio:16/9`.
  - `.card__badge--live`: 우상단 절대배치, 빨강 배경 + "LIVE" 텍스트(색만으로 구분 금지).
  - `.card__title`: PC 1줄(`white-space:nowrap`). 넘치면 `render.js`의 `applyMarquees()`가
    `.card__title--marquee` + `.card__title-track`(텍스트 2벌)로 바꿔 무한 흐름(속도는 길이 비례,
    hover 시 정지, `prefers-reduced-motion` 존중). 모바일은 2줄 클램프(줄바꿈이라 marquee 안 걸림).
  - `.card--live`: 테두리/배경 강조.
  - `.lane__empty`: 흐린 안내 텍스트, 중앙.
  - `.card__thumb--broken`: 회색 플레이스홀더 배경(이미지 숨김).
  - 다크 단일 테마 권장(자유). 색은 CSS 변수로.
- **js/config.js**: 상수만 export.
  ```js
  export const DATA_URL = "https://raw.githubusercontent.com/sbb2002/mewtype-scheduler/data/schedule.json";
  export const POLL_MS = 75000;
  export const COUNTDOWN_TICK_MS = 60000;
  export const FETCH_TIMEOUT_MS = 8000;
  export const FALLBACK_CHANNEL_ORDER = ["arale","yuno","nonoka","ritsu","miyako"];
  export const FALLBACK_CHANNELS = { /* 계약 A channels 축약본, name_ko/channel_url 포함 */ };
  ```
  개발 중에는 `DATA_URL`을 `../../fixtures/schedule.sample.json`으로 바꿔 확인 가능(주석으로 안내).
- **js/time.js**: 계약 D 구현. `export function formatKST(iso)`, `export function relativeLabel(iso, nowMs = Date.now())`. 순수 함수, DOM 접근 없음.
- **js/api.js**:
  ```js
  export async function fetchSchedule(url) {
    // AbortController + FETCH_TIMEOUT_MS, cache:"no-store"
    // 성공: { ok:true, data }
    // 실패(네트워크/타임아웃/HTTP!=200/JSON파싱): { ok:false, error:Error }
  }
  ```
- **js/render.js**:
  ```js
  export function renderBoard(boardEl, schedule, nowMs = Date.now()) { /* 계약 C대로 전체 재구성 */ }
  export function renderFooter(footEl, schedule, { stale }) { /* 업데이트 시각 + 지연 표시 */ }
  export function updateCountdowns(boardEl, nowMs = Date.now()) { /* .card--upcoming 의 .card__rel 텍스트만 갱신 */ }
  ```
  - 정렬: lane 순서 = `schedule.channel_order || FALLBACK_CHANNEL_ORDER`. lane 내 upcoming = `scheduled_start` 오름차순.
  - `channel_key`로 broadcasts 그룹핑. 알 수 없는 key는 무시.
  - XSS 방지: 제목 등은 `textContent`로만 주입(innerHTML 금지, onerror 속성은 예외적으로 허용).
- **js/main.js**:
  ```js
  import ...
  const board = document.getElementById("board");
  const foot  = document.getElementById("foot");
  let last = null;
  async function poll() {
    const r = await fetchSchedule(DATA_URL);
    if (r.ok) { last = r.data; renderBoard(board, last); renderFooter(foot, last, {stale:false}); }
    else if (last) { renderFooter(foot, last, {stale:true}); }   // 마지막 데이터 유지
    else { /* 최초 로드 실패: board에 "불러오는 중 문제가 발생했어요" */ }
  }
  addEventListener("DOMContentLoaded", () => {
    poll();
    setInterval(poll, POLL_MS);
    setInterval(() => updateCountdowns(board), COUNTDOWN_TICK_MS);
  });
  ```
- 산출물 확인 기준: `fixtures/schedule.sample.json`을 `DATA_URL`로 지정하고 로컬에서 `python -m http.server`로 열었을 때 5레인 + 라이브/예정 카드가 시안대로 렌더, 좁은 화면에서 가로 스크롤.

### [RSS] `src/collector/rss.py` — 담당: haiku #2 (데이터 수집 레이어: rss + youtube)

```python
def fetch_rss_video_ids(channel_id: str, *, timeout: float = 10.0,
                        session: "requests.Session | None" = None) -> list[str]:
    """
    https://www.youtube.com/feeds/videos.xml?channel_id=<id> 를 받아
    video_id 목록을 최신순으로 반환(최대 15). 네임스페이스:
      atom = http://www.w3.org/2005/Atom
      yt   = http://www.youtube.com/xml/schemas/2015
    entry/yt:videoId 를 순서대로 수집. HTTP 오류/파싱 오류는 예외를 던지지 않고
    빈 리스트 반환 + logging.warning.
    """

def fetch_all_rss_video_ids(channel_id_by_key: dict[str, str]) -> dict[str, list[str]]:
    """channel_key -> [video_id]. 각 채널 독립 실패 허용(실패 시 [])."""
```
- `requests` 사용, User-Agent 헤더 지정. 표준 라이브러리 `xml.etree.ElementTree`.
- `fixtures/rss_arale.xml`로 오프라인 파싱 테스트가 되도록 `_parse_rss(xml_text: str) -> list[str]` 내부 함수 분리.

### [YT] `src/collector/youtube.py` — 담당: haiku #2

```python
from dataclasses import dataclass

@dataclass
class VideoInfo:
    video_id: str
    channel_id: str
    title: str
    thumbnail: str            # snippet.thumbnails 중 maxres>standard>high>medium>default,
                              # 없으면 f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    live_state: str           # snippet.liveBroadcastContent: "none"|"upcoming"|"live"
    scheduled_start: str | None   # liveStreamingDetails.scheduledStartTime (ISO, 'Z' 유지)
    actual_start: str | None      # liveStreamingDetails.actualStartTime
    actual_end: str | None        # liveStreamingDetails.actualEndTime
    concurrent_viewers: int | None  # liveStreamingDetails.concurrentViewers (문자열->int)

class YouTubeClient:
    BASE = "https://www.googleapis.com/youtube/v3"
    def __init__(self, api_key: str, *, session=None, timeout: float = 15.0):
        self.quota_used = 0
    def videos_list(self, video_ids: list[str]) -> dict[str, VideoInfo]:
        """part=snippet,liveStreamingDetails. 50개씩 청크. 호출당 quota_used += 1.
           응답에 없는 id는 결과에서 생략. HTTP 오류 시 RuntimeError."""
    def search_upcoming(self, channel_id: str, *, max_results: int = 25) -> list[str]:
        """part=id&type=video&eventType=upcoming&order=date. quota_used += 100.
           video_id 리스트 반환. 오류 시 [] + warning."""
```
- 네트워크 없이 테스트할 수 있도록 응답 dict -> VideoInfo 변환을 `_video_from_item(item: dict) -> VideoInfo` 순수 함수로 분리.
- API 키가 없으면 `YouTubeClient.__init__`에서 `ValueError`.

### [LOGIC] `src/collector/reconcile.py` — 담당: haiku #3 (reconcile + store)

```python
def build_schedule(
    channels_cfg: dict,            # config/channels.json 파싱 결과 {"channel_order":[...], "channels":{...}}
    videos: dict[str, "VideoInfo"],# video_id -> VideoInfo (RSS/search/tracked 후보의 조회 결과)
    prev_schedule: dict,           # 이전 schedule.json (없으면 기본형)
    now_iso: str,                  # "2026-08-30T12:00:00Z"
) -> tuple[dict, list[dict]]:
    """
    반환: (new_schedule, newly_ended)
    - channel_id -> channel_key 매핑은 channels_cfg로 구성.
    - 각 VideoInfo 처리:
        live_state == "upcoming" -> broadcasts에 status="upcoming", scheduled_start 채움
        live_state == "live"     -> status="live", actual_start/concurrent_viewers 채움
        live_state == "none":
            - prev_schedule에 해당 video_id가 upcoming/live로 있었고 actual_end 존재
              -> newly_ended 에 reason="ended"
            - prev에 있었으나 actual_end 없음(취소) -> newly_ended reason="canceled"
            - prev에 없음 -> 무시(일반 VOD)
    - prev에 upcoming/live였는데 이번 videos에 아예 없음(삭제/비공개)
      -> newly_ended reason="removed" (가능한 필드만 채움)
    - first_seen: prev에 있으면 보존, 없으면 now_iso.
    - last_updated: now_iso.
    - new_schedule.broadcasts 정렬: live 먼저, 그다음 scheduled_start asc (None은 뒤).
    - new_schedule.generated_at = now_iso, channel_order/channels = channels_cfg 기반.
    순수 함수. 네트워크/파일 접근 금지.
    """

def ended_record(prev_entry: dict, video: "VideoInfo | None", reason: str, now_iso: str) -> dict:
    """계약 B 형태의 archive 레코드 생성 헬퍼."""
```

### [STORE] `src/collector/store.py` — 담당: haiku #3

```python
import os, json
DATA_DIR = os.environ.get("DATA_DIR", "./_data")
SCHEDULE_PATH = ...  # os.path.join(DATA_DIR, "schedule.json")
ARCHIVE_PATH  = ...  # os.path.join(DATA_DIR, "archive.json")

def default_schedule(channels_cfg: dict) -> dict: ...
def load_schedule(channels_cfg: dict) -> dict:   # 없으면 default_schedule
def load_archive() -> dict:                      # 없으면 {"updated_at": None, "broadcasts": []}
def save_json_if_changed(path: str, data: dict) -> bool:
    """정렬된 key + indent=2 + ensure_ascii=False 로 직렬화.
       기존 파일과 문자열이 같으면 쓰지 않고 False, 다르면 쓰고 True."""
def save_schedule(data: dict) -> bool
def append_archive(records: list[dict]) -> bool  # video_id dedupe, updated_at 갱신
```

### [GLUE] `src/collector/main.py`, `config.py` — 담당: Sonnet(내가 직접). haiku 대상 아님.

### [INFRA] `config/channels.json`, `.github/workflows/collect.yml`, `requirements.txt`, `README.md` — 담당: haiku #4

- `config/channels.json`: 아래 §6 확정본을 그대로 파일로.
- `src/collector/requirements.txt`: `requests>=2.31` 한 줄.
- `.github/workflows/collect.yml`:
  ```yaml
  name: collect
  on:
    schedule:
      - cron: "0 * * * *"          # 매시 정각(UTC)
    workflow_dispatch:
      inputs: { mode: { type: choice, options: [auto, light, deep], default: auto } }
  permissions:
    contents: write
  concurrency: { group: collect, cancel-in-progress: false }
  jobs:
    run:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4                 # main
        - uses: actions/checkout@v4                 # data 브랜치를 _data/ 로
          with: { ref: data, path: _data, fetch-depth: 1 }
          continue-on-error: true                   # data 브랜치 최초엔 없음
        - run: mkdir -p _data
        - uses: actions/setup-python@v5
          with: { python-version: "3.12" }
        - run: pip install -r src/collector/requirements.txt
        - name: decide mode
          id: m
          run: |
            IN="${{ github.event.inputs.mode }}"
            if [ -z "$IN" ] || [ "$IN" = "auto" ]; then
              [ "$(( $(date -u +%H) % 6 ))" -eq 0 ] && echo "mode=deep" >> "$GITHUB_OUTPUT" || echo "mode=light" >> "$GITHUB_OUTPUT"
            else echo "mode=$IN" >> "$GITHUB_OUTPUT"; fi
        - name: collect
          env:
            YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
            DATA_DIR: _data
          run: python -m src.collector.main ${{ steps.m.outputs.mode }}
        - name: commit
          working-directory: _data
          run: |
            git config user.name "mewtype-collector[bot]"
            git config user.email "actions@users.noreply.github.com"
            git add -A
            git diff --cached --quiet && { echo "no change"; exit 0; }
            git commit -m "data: sync ${{ steps.m.outputs.mode }} $(date -u +%FT%TZ)"
            # data 브랜치가 없었으면 새로 생성
            git branch -M data
            git push origin data
  ```
  (data 브랜치 최초 생성 시나리오는 README에 수동 부트스트랩 절차도 적어둘 것: `git switch --orphan data && git commit --allow-empty ... && git push`.)
- `README.md`: 프로젝트 한줄 소개, 구조, 로컬 실행법(`DATA_DIR=./_data YOUTUBE_API_KEY=... python -m src.collector.main light`), Vercel 설정(Root Directory=`src/frontend`), `data` 브랜치 부트스트랩, Secret 등록 안내.

---

## 6. `config/channels.json` 확정본

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
`channel_url`은 코드에서 `https://www.youtube.com/@{handle}`로 파생.

---

## 7. 병렬 작업 배정 요약

| ID | 범위 | 산출 파일 | 의존 |
|----|------|-----------|------|
| haiku #1 | 프론트 전체 | `src/frontend/**` | 계약 A/C/D, fixtures/schedule.sample.json |
| haiku #2 | 수집 I/O | `src/collector/rss.py`, `src/collector/youtube.py` | 계약(VideoInfo), YouTube API |
| haiku #3 | 로직/저장 | `src/collector/reconcile.py`, `src/collector/store.py` | 계약 A/B, VideoInfo 시그니처 |
| haiku #4 | 인프라 | `config/channels.json`, `.github/workflows/collect.yml`, `src/collector/requirements.txt`, `README.md` | §5·§6 |
| Sonnet | 통합/검수 | `src/collector/main.py`, `src/collector/config.py`, `__init__.py`, 전체 리뷰·수정 | 위 전부 |

각 haiku 작업물은 Sonnet이 계약 준수·엣지케이스·보안(XSS, 키 노출)·파이썬 타입/예외 처리를 기준으로 검수 후 병합한다.
