# v2.0 — 실시간 백엔드 재설계 · 계획

작성 2026-08-30 · 브랜치 `feat/v2.0-realtime-backend` · 상태: **설계 확정 전, 조사 반영본**

이 문서는 v2.0 의 "무엇을 왜 바꾸는가" 와 단계별 작업 순서를 정의한다.
스키마/시그니처 확정본은 구현 시 `docs/IMPLEMENTATION.md` 에 반영한다.

---

## 1. 배경 — v1 구조의 두 한계

1. **GitHub Actions `schedule:` 지연.** `cron: "0 * * * *"` 이 정시에 안 돈다. GitHub 이 스케줄
   이벤트를 후순위 처리해 3~15분, 드물게 1시간 지연/누락 (CLAUDE.md 주의점에도 기재).
2. **고정 주기 폴링이 상태 전환을 못 잡는다.** 매시간 1회로는 방송 시작 직후 라이브 영역 승격,
   종료 직후 강등을 제때 반영할 수 없다. `light`/`deep` 는 "예고 발견" 엔 맞지만 "상태 전환
   추적" 해상도가 부족하다.

## 2. 해결 방향 (전자동, 사람 개입 0)

- **실행**: 수집기를 **Render Cron Job** 으로 이전. `schedule:` 과 달리 정시성이 보장된다.
  무료 750h 웹서비스 풀과 무관한 별도 유료 미터(월 약 $1~3).
- **발견(discovery)**: **YouTube RSS 스윕** 으로 예정 방송을 찾는다 (쿼터 0). 새 videoId 는
  `videos.list` 로 enrich (호출당 1유닛).
- **판정(reconcile)**: 고정 2분 틱마다 `state.json` 을 읽어 "지금 무엇을 할 차례인지" 판정.
  적응형 폴링은 *스케줄* 이 아니라 *매 틱의 조건 판정* 으로 구현한다 (2분 격자에 스냅됨).
- **프론트 변경 없음**: Vercel 정적 + `raw.githubusercontent` 에서 `data` 브랜치 fetch 유지.
  라이브 전환은 (2분 틱) + (raw CDN 캐시 최대 ~5분) = 최대 ~7분 지연으로 노출된다. 감수한다.

### 2.1 X(트위터) 는 v2.0 범위에서 제외 — 조사 결론

`@BDP_yumemita` 가 매일 올리는 「配信スケジュール」 트윗을 발견 소스로 쓰려 했으나,
**무료로 "그날 올라온 트윗"을 자동 취득하는 방법이 없다** (상세는 부록 A).

- 되는 것: `cdn.syndication.twimg.com/tweet-result?id=<id>&token=<계산>` — 단일 트윗을 ID 로
  조회. 인증 불필요, 데이터 완전. **하지만 그날의 트윗 ID 를 알아낼 방법이 없음.**
- 안 되는 것: 임베드 타임라인(9일치 얼어붙음·비시계열 샘플), nitter(전멸), rsshub(인증벽),
  검색엔진(이 계정 트윗 사실상 미색인).
- 수동 붙여넣기(옛 "B안") 는 **전자동화 목표에 배치되어 폐기** (2026-08-30 사용자 결정).
- twscrape(실계정 스크레이핑) 는 기술적으로 가능하나 전용 X 계정 + 쿠키 시크릿 + 세션 만료/
  계정 정지 시 수동 재인증이 필요 → "진짜 무인" 이 아님. **보류** (부록 A 참조).

**결과로 포기하는 것 두 가지:**
1. **아침에 그날 전체 라인업 미리보기.** v2.0 에서는 유튜브가 대기 영상(placeholder)을 만든
   뒤에야 예정 카드가 뜬다 (스트리머 습관에 따라 방송 몇 시간~몇십 분 전).
2. **멤버 전용 방송.** RSS 미포함 + 비회원 API 응답 없음 → **감지 불가, 범위 밖.**

두 문제(#1 정시성, #2 라이브 전환)는 X 없이 완전히 해결된다.

---

## 3. 확정 사항

### 3.1 발견 (RSS 스윕)

| 항목 | 결정 |
|---|---|
| 소스 | `https://www.youtube.com/feeds/videos.xml?channel_id=<id>` × 5채널. 쿼터 0 |
| 주기 | 최소 10분마다 전 채널 스윕 (또는 매 틱; 비용 0이므로 여유롭게) |
| 처리 | RSS videoId ∪ `state.json` 미해결(upcoming/live) videoId 를 후보로 모아 `videos.list` 배치 |
| 분기 | `liveBroadcastContent`: `upcoming` → 추적 시작(stage=upcoming, `scheduledStartTime` 기록) · `live` → 즉시 live 로 추적 · `none` → 일반 VOD, 잠시 무시목록에 넣어 재조회 방지 |
| search.list | **기본 미사용.** 폴백/보강용으로만 — RSS 에 안 잡히는 예정 방송 대비, 저녁대 시간당 1회 등 저빈도 옵션 (100유닛/호출) |

### 3.2 적응형 판정 (고정 2분 틱)

| 단계 | 트리거 / 동작 |
|---|---|
| 시작 전 라이브 체크 | 예정시작 −3분 / +1분 / +5분 / 그 뒤 라이브 확인까지 2분 간격 |
| 라이브 판정 | `liveStreamingDetails.actualStartTime` 존재 **AND** `actualEndTime` 없음 → `live`. `schedule.json` 라이브 영역 승격 |
| no-show 컷오프 | 예정시작 **+120분** 까지 라이브 안 뜨면 `unconfirmed` → `schedule.json` 에서 내리고 추적 중단 (archive 로는 안 보냄, 로그만) |
| 종료 첫 체크 | **실제 시작시각**(`actualStartTime`, 없으면 승격한 시각) **+60분** |
| 종료 폴링 | 라이브면 **10분 간격** `videos.list` |
| 종료 판정 | `actualEndTime` 존재 OR `liveBroadcastContent == "none"`(직전 live) → `ended`. `archive.json` 이관 + `schedule.json` 에서 내림 + 추적 중단 |
| 쿼터 | 매 틱 `videos.list` 는 due videoId 전부 한 번에 배치 (호출당 1유닛). 2분 틱 24/7 이어도 720유닛/일 << 10,000 |

### 3.3 실행 / 인프라

| 항목 | 결정 |
|---|---|
| 실행 | Render **Cron Job**, 1차 `schedule: "*/2 * * * *"` (이후 3.4 시간대 한정 검토) |
| 인스턴스 | cron 은 free 인스턴스 불가 → `starter` (초당 과금, 월 약 $1~3). 무료 750h 풀과 무관 |
| 엔트리포인트 | `python -m src.collector.main tick` (기존 `run(light\|deep)` → `tick(now)` 로 대체) |
| 데이터 취득 | 각 틱이 `data` 브랜치를 얕게 clone (`_data/`) → 작업 → 변경 시 commit & push |
| 데이터 파일 | `schedule.json` + `archive.json` + **신설 `state.json`** (전부 `data` 브랜치) |
| Git 인증 | fine-grained PAT (이 repo, `contents: write`). Render env `GH_PAT` (`sync: false`) |
| 시크릿 | `YOUTUBE_API_KEY`, `GH_PAT` (둘 다 `sync: false`), `DATA_DIR=_data` |
| GitHub Actions | `.github/workflows/collect.yml` 의 `schedule:` 트리거 **제거**. `workflow_dispatch` 는 수동 백업으로 유지 |
| 프론트 | 변경 없음 |

### 3.4 크론 스케줄 (비용 최적화, 2차)

24/7 2분 틱 = 720 run/일. 대부분이 no-op 틱의 컨테이너 기동 오버헤드다. 시간대 한정으로
대략 절반까지 절감 가능 (관측된 방송 패턴 기준):

- 활성 창 (UTC): `11:00–19:00`, `21:00–24:00`, `01:00–07:00`
- 크론 2벌: 활성 창 `*/2`, 비활성 창 `*/15` (안전망)

1차는 단순하게 `*/2 * * * *` 24/7 로 배포 → 며칠 로그로 실비용 확인 후 조인다.

---

## 4. `state.json` — 신규 계약 (초안, 구현 시 IMPLEMENTATION.md §5 확정)

`data` 브랜치 루트. **봇 내부용** — 프론트는 읽지 않는다. `schedule.json` 의 잦은 재작성을
막기 위해 분리한다 (`next_check_at` 등이 매 틱 바뀜).

```jsonc
{
  "updated_at": "2026-08-30T12:00:00Z",
  "seen_vod": ["<videoId>", "..."],          // 최근 확인해서 'none' 이던 것 (재조회 스킵, 링버퍼)
  "tracked": {
    "<video_id>": {
      "channel_key": "arale",
      "stage": "upcoming",                    // upcoming | live | end_polling | ended | unconfirmed
      "scheduled_start": "2026-08-30T13:00:00Z",
      "actual_start": null,
      "first_seen": "2026-08-30T21:05:00Z",
      "last_check": "2026-08-30T21:05:00Z",
      "next_check_at": "2026-08-30T12:57:00Z"
    }
  }
}
```

- **stage 전이도**
  `upcoming` → (`actualStartTime` 확인) → `live` → (`actual_start`+60분) → `end_polling` → (`actualEndTime` / `none`) → `ended`
  `upcoming` → (`scheduled_start`+120분 경과, 미확인) → `unconfirmed`
  `ended` / `unconfirmed` → `tracked` 에서 제거
- **크래시 복구**: Render Cron 컨테이너는 매 run 독립이므로 `state.json` 이 유일한 상태.
  로드 실패/구버전이면 현재 `schedule.json` + RSS 재스윕 + 타임스탬프로 stage 재유도.

---

## 5. `schedule.json` 계약 변경

계약 A (IMPLEMENTATION §1) 는 **동결 유지.** v2.0 에서 추가 필드 없음.
(멤버 전용을 안 다루므로 `members_only` 등 신설 불필요. `video_id` 는 항상 존재.)

reconcile 동작만 강화:
- 라이브 승격 조건: `live_state == "live"` 단독 → **`actual_start and not actual_end` 우선**.
- 종료 판정: **`actual_end` 존재** 를 `live_state == "none"` 보다 우선.
- `unconfirmed` (no-show): `schedule.json` 에서 제외, archive 로는 보내지 않음 (로그만).

---

## 6. 모듈별 작업

### 6.1 `src/collector/main.py` — `run(mode)` → `tick(now)`

틱 알고리즘:

1. `_data/` 에서 `state.json` / `schedule.json` 로드, `channels.json` 로드. `now`(UTC) 계산.
2. **RSS 스윕** (마지막 스윕 후 ≥10분): `rss.fetch_all_rss_video_ids` → 새 videoId 중
   `seen_vod`·`tracked` 에 없는 것을 이번 enrich 대상에 추가.
3. **due 항목 수집** (`now >= next_check_at` 인 `tracked` 항목) → enrich 대상에 videoId 추가.
4. **`videos.list` 1회 배치** 로 enrich 대상 전부 조회.
5. 각 항목 판정:
   - 신규 `upcoming` → `tracked` 추가, `next_check_at` = 케이던스(−3/+1/+5/이후 +2분).
   - 신규/기존 `live` (`actual_start and not actual_end`) → stage=`live`, `next_check_at` = `actual_start`+60분, `schedule.json` 승격.
   - `upcoming` 인데 `now > scheduled_start`+120분 → `unconfirmed`, 추적 제거.
   - `end_polling` 대상이 `actual_end` 있음 / `live_state=="none"` → `ended`, archive 이관 + 추적 제거. 아니면 `next_check_at` = `now`+10분.
   - `none` → `seen_vod` 에 기록.
6. `reconcile.build_schedule(...)` → 새 `schedule.json`. `store.save_schedule` / `append_archive`. `state.save_state_if_changed`.
7. 파일 변경분 있으면 `_data/` 에서 `git add/commit/push origin data`.

- `config.get_api_key()` 유지. `search_upcoming` 은 저빈도 폴백 옵션으로만 호출 (기본 off).

### 6.2 신규 `src/collector/state.py`

```python
STATE_PATH = os.path.join(DATA_DIR, "state.json")
def load_state() -> dict                       # 없으면 기본형
def save_state_if_changed(state: dict) -> bool  # store.save_json_if_changed 재사용
```

### 6.3 `src/collector/reconcile.py`

- 라이브 승격/종료 판정 강화 (§5).
- 순수 함수 유지. `build_schedule` 시그니처는 가능하면 그대로.

### 6.4 `src/collector/rss.py`, `youtube.py`, `store.py`

- `rss.py`: 변경 없음 (채널 단위 `fetch_rss_video_ids` 그대로).
- `youtube.py`: 변경 없음. `VideoInfo` 에 이미 `actual_start`/`actual_end`/`concurrent_viewers` 존재.
- `store.py`: `save_json_if_changed` 재사용. 변경 없음.

### 6.5 인프라

- **신규 `render.yaml`** (repo 루트):
  ```yaml
  services:
    - type: cron
      name: mewtype-collector
      runtime: python
      plan: starter                 # cron 은 free 인스턴스 불가
      region: singapore
      schedule: "*/2 * * * *"        # 1차. 이후 시간대 한정 검토
      buildCommand: pip install -r src/collector/requirements.txt
      startCommand: python -m src.collector.main tick
      envVars:
        - key: PYTHON_VERSION
          value: "3.12.7"
        - key: DATA_DIR
          value: _data
        - key: YOUTUBE_API_KEY
          sync: false
        - key: GH_PAT
          sync: false
  ```
  (Render cron 스키마 필드명 `schedule`/`startCommand` 은 배포 시 대시보드/문서로 검증.)
- **`.github/workflows/collect.yml`**: `on.schedule` 블록 삭제, `workflow_dispatch` 만 유지.
- **`requirements.txt`**: 변경 없음 (`requests` 만).
- **CLAUDE.md**: "데이터 흐름", "명령", "수집 로직" 절을 Render Cron + 틱 모델로 갱신.
- **PAT 발급**: fine-grained, repo = `mewtype-scheduler`, permission = Contents(RW).

---

## 7. 마이그레이션 순서 (단계별 검증)

| # | 작업 | 검증 |
|---|---|---|
| 1 | `state.py` + 스키마 → IMPLEMENTATION.md §5 | 로드/세이브/변경감지 스모크 |
| 2 | `main.py` `tick()` + `reconcile.py` 강화 | `reconcile` self-test 갱신. `tick` 을 fixture·모의 시계로 dry-run |
| 3 | 로컬 실연: `data` 브랜치 워크트리 + 실제 API 키로 `tick` 을 수동 루프, 실제 방송일 하루 관찰 | `state.json` 이 upcoming→live→end_polling→ended 로 전이. `schedule.json` 승격/강등 타이밍 확인 |
| 4 | `render.yaml` 추가, Render Cron 배포(**push 비활성 dry-run**), env 시크릿 등록 | 로그에서 틱이 2분마다 정상 실행, no-op 비용 실측 |
| 5 | push 활성화 + **동시에** `collect.yml` 의 `schedule:` 제거 (data 브랜치 동시 기록 경쟁 방지) | `data` 브랜치가 Render 커밋으로만 갱신 |
| 6 | 며칠 관찰 후 크론 시간대 한정(3.4) 적용, CLAUDE.md / IMPLEMENTATION.md 최종 갱신 | 비용·정시성 안정 확인 |

단계 4까지는 `data` 브랜치를 안 건드리므로 운영 영향 없음.

---

## 8. 리스크 / 미해결

| 리스크 | 대응 |
|---|---|
| 예정 카드가 늦게 뜸 (placeholder 생성 후에야 발견) | 수용. 필요 시 `search.list` 저빈도 보강 (3.1) |
| 멤버 전용 방송 미표시 | 수용, 범위 밖 (2.1) |
| 2분 격자 + raw CDN ~5분 = 라이브 전환 최대 ~7분 지연 | 수용. 더 줄이려면 프론트가 Render HTTP 직독 — 범위 밖 |
| Render Cron 스키마/과금 세부 | 배포 시 대시보드 검증. 1차 `*/2` 24/7 로 실비용 실측 후 조정 |
| Actions ↔ Render 동시 `data` 브랜치 기록 | 단계 5 에서 전환을 원자적으로 (push 활성화 = `schedule:` 제거 동시) |
| Render Cron 컨테이너 재시작/실패로 틱 1회 누락 | 각 틱 멱등. 다음 틱이 `state.json` 보고 밀린 것 처리. no-show/종료 판정은 절대시각 기준이라 누락에 강함 |
| 향후 무료 X 자동 취득법 등장 시 | `discovery` 를 소스 추상화해 두면 갈아끼우기 쉬움 (지금은 RSS 단일 소스) |

---

## 9. 범위 밖

- X(트위터) 연동 일체 — 아침 라인업 미리보기, 멤버 전용 방송 (2.1)
- 프론트를 Render/저지연 소스로 전환
- 채널 추가/변경 (여전히 `config/channels.json` 한 곳)
- `archive.json` 을 읽는 프론트 기능

---

## 부록 A — X 무료 취득 조사 기록 (2026-08-30)

재조사를 막기 위한 기록. 목표는 "`@BDP_yumemita` 의 그날 「配信スケジュール」 트윗을 무인으로 취득".

| 경로 | 결과 |
|---|---|
| `syndication.twitter.com/srv/timeline-profile/screen-name/BDP_yumemita` (Referer 헤더 필요) | HTTP 200, 612KB. `__NEXT_DATA__` 에 `props.pageProps.timeline.entries` 101개. **`latest_tweet_id` 가 9일 전(Aug 21)에 얼어붙음**, 2022~2026 걸친 비시계열 샘플. 오늘 트윗 없음. `cf-cache-status: DYNAMIC` = 캐시 문제 아님 |
| `showReplies=true` | HTTP 200, 2KB 빈 페이지 |
| `cdn.syndication.twimg.com/timeline/profile?screen_name&user_id` (구 JSON) | HTTP 200, size 0 |
| **`cdn.syndication.twimg.com/tweet-result?id=<id>&token=<계산>`** | ✅ **완전 동작.** `text` + `entities.urls`(t.co→유튜브 핸들) + `created_at` + `note_tweet`. 토큰 = `((id/1e15)*PI).toString(36).replace(/(0+|\.)/g,'')`. **단 ID 를 알아야 함** |
| nitter (net / poast / privacydev / space / kavin.rocks / opnxng / tiekoetter / xcancel) | 전부 410 / 403 / 502 / 302 / timeout |
| rsshub.app/twitter/user | 302 (인증 필요) |
| fxtwitter / vxtwitter `/user` | 유저 프로필만. 타임라인 엔드포인트 없음 (404). 유저 수치 ID `1546362523561390081` 는 취득됨 |
| Bing `&format=rss` | 무시됨, 무관한 결과 |
| DuckDuckGo HTML | 이 계정 트윗을 **몇 주에 하나** 꼴로만 색인 (5/20, 6/25, 7/18, 8/6). 사실상 미색인 |
| Google News RSS | 트윗 미포함 |

**결론**: 트윗 *내용* 은 ID 만 있으면 무료로 완벽히 받는다. 그러나 *그날의 ID 를 무인으로
알아내는* 무료 경로가 존재하지 않는다.

**보류된 대안 — twscrape**: 실제 X 계정으로 내부 GraphQL(`UserTweets`)을 호출 → 시계열
타임라인 취득 가능. 라이브러리는 무료. 그러나 (a) 전용 X 계정 필요 + 스크레이핑 계정은
주기적으로 정지됨, (b) 신규 계정 생성/로그인에 전화·챌린지 = 사람 개입, (c) Render cron 은
휘발이라 세션(`accounts.db`)을 Render 시크릿에 쿠키로 넣고 매 run 주입해야 하며 만료 시
로컬 재인증 필요 → **"진짜 무인" 이 아님.** 공개 repo 라 `accounts.db` 커밋도 불가.
전자동화 목표에 부합하지 않아 채택하지 않음. 향후 재검토 가능성만 남김.
