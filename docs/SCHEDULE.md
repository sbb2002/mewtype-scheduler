# 백엔드 스케줄 (v2)

v2 백엔드는 Cloud Run **scale-to-zero** HTTP 서비스다. 요청이 올 때만 인스턴스가 뜨고,
그 외 시간엔 인스턴스 0 · 비용 0. 백엔드를 깨우는 트리거는 두 종류뿐이다.

| 트리거 | 엔드포인트 | 주체 | 언제 |
|---|---|---|---|
| 정기 tick | `POST /tick` | Cloud Scheduler | 아래 §1 고정 스케줄 |
| 방송별 wake | `POST /wake` | Cloud Tasks | 아래 §2 상태머신이 방송마다 동적으로 예약 |
| 종료후 재확인 tick | `POST /tick` (light) | Cloud Tasks | 방송이 방금 끝난 tick/wake 가 **now + 20분** 으로 1개 예약 (§1.1) |

관련 코드: `deploy/scheduler.sh`(스케줄러 정의), `src/backend/handlers.py`(tick/wake 오케스트레이션),
`src/backend/statemachine.py`(wake 타이밍 계산), `src/backend/tasks.py`(Cloud Tasks enqueue).

---

## 1. Cloud Scheduler — 정기 tick

`deploy/scheduler.sh` 가 만드는 잡. 모두 `/tick` 으로 POST.

| 잡 이름 | cron | TZ | body | 빈도 |
|---|---|---|---|---|
| `mewtype-baseline` | `0 6 * * *` | Asia/Tokyo | `{"mode":"baseline"}` | JST 06:00 매일 1회 |
| `mewtype-light` | `0 */3 * * *` | Etc/UTC | `{"mode":"light"}` | UTC 3시간 간격 (00·03·06·09·12·15·18·21시) |

- **light**: RSS로 최근 videoId 발견 → 후보(이전 pending·schedule의 미해결 + RSS) 를
  `videos.list` 로 일괄 조회 → `schedule.json` / `archive.json` / `pending.json` 갱신,
  필요한 wake 태스크 enqueue. 예약이 몰리지 않는 시간대의 안전망.
- **baseline**: light가 하는 일 전부 + `channels.list` 로 채널 아바타 URL 갱신.
  하루 한 번 채널 메타를 새로 고치는 용도.
- deep 모드 스케줄 잡은 **없다**. v1의 "매시간 deep" 은 폐기됨. v2에서 촘촘한 폴링은
  아래 방송별 wake(§2)가 이벤트 드리븐으로 담당한다.
- Cloud Run concurrency=1 이라 처리 중이면 429 → 스케줄러가 재시도
  (`--max-retry-attempts=3`, backoff 30~300s).

> GitHub Actions `.github/workflows/collect.yml` 은 cron이 제거됐고 `workflow_dispatch`
> 수동 전용(break-glass)이다. 평소 스케줄에 관여하지 않는다.

### 1.1 종료후 재확인 tick (백투백 방송 대비)

일반 방송이 끝나고 **곧이어 다른 방송**(회원 전용 재시작 포함)이 시작되는 경우가 있다.
정기 light tick 은 3시간 간격이라 그 사이에 시작·종료되는 짧은 다음 방송을 통째로 놓칠 수 있다.

→ tick/wake 처리 중 `archive.json` 으로 넘어간 방송(`newly_ended`)이 하나라도 있으면,
`handlers._run` 이 **`now + 20분`(`_POST_END_RECHECK_SEC`)** 시각으로 `POST /tick {"mode":"light"}`
태스크를 Cloud Tasks 에 1개 예약한다. 그 tick 이 RSS + `videos.list` 로 새로 뜬 방송을 줍는다.

- 태스크 이름 `tick-light-{분버킷}` → 한 tick 에서 여러 방송이 끝나도 후속 tick 은 **1개**로 dedupe.
- 비용: 방송 종료당 `videos.list` 약 1콜(+RSS 0). 하루 몇 콜 수준.
- 한계: **회원 전용** 다음 방송은 RSS·`search.list` 어디에도 안 떠서 이 재확인으로도 못 잡는다
  (구조적 사각지대, `ref/broadcast-patterns.md` 참고). 공개 방송의 백투백/재시작만 커버.

### 프론트 하단 "업데이트" 시각 = `schedule.json.generated_at`

- 매 tick/wake 마다 `build_schedule` 이 `generated_at = 실행시각` 으로 세팅.
- 방송 목록에 **실질 변화**(추가·삭제·status 전이·`scheduled_start`·제목·썸네일)가 있으면
  그대로 커밋 → 시각 전진.
- 실질 변화가 없어도 `generated_at` 은 **`_HEARTBEAT_MIN_SEC`(20분)** 간격으로 전진시켜
  커밋한다 (`handlers._heartbeat_generated_at`). "스케줄대로 확인은 했다" 를 사용자가 알 수
  있도록. 라이브 중 wake 3분 간격마다 커밋되는 것은 막는다.
- 따라서 프론트 표시 지연 상한 ≈ 20분(heartbeat) + 75초(폴링) + ~5분(raw CDN 캐시).

---

## 2. 방송별 wake — 폴링 상태머신

`statemachine.sync_pending()` 이 `pending.json` 의 각 엔트리에 대해 "다음에 언제 깨울지"
(`next_check_at`) 를 계산하고, 그 시각으로 Cloud Tasks 태스크를 enqueue 한다.
wake가 실행되면 해당 방송 하나만 조회하고 다시 다음 wake를 예약 — 방송이 끝나면 엔트리 삭제.

엔트리는 두 phase를 갖는다: `pre-live`(예정~시작 전) → `live-watch`(라이브 중).

### 상수 (statemachine.py 상단, config 아님 · 코드 고정)

| 상수 | 값 | 의미 |
|---|---|---|
| `PRELIVE_LEAD_SEC` | 15분 | 최초 wake = `scheduled_start − 15분` |
| `PRELIVE_TIGHT_SEC` | 3분 | `scheduled_start` 지난 뒤 촘촘 폴링 간격 |
| `PRELIVE_FALLBACK_AFTER_SEC` | 60분 | `scheduled_start + 60분` 경과 시 fallback 진입 |
| `FALLBACK_RETRY_SEC` | 60분 | fallback 재시도 간격 |
| `FALLBACK_MAX_ATTEMPTS` | 6 | fallback 6회 연속 미확인 → canceled 로 간주, 엔트리 드롭 |
| `LIVEWATCH_EARLY_SEC` | 30분 | 라이브 시작 후 초기 폴링 간격 |
| `LIVEWATCH_EARLY_WINDOW_SEC` | 60분 | "초기" 로 보는 구간 (시작 ~ +60분) |
| `LIVEWATCH_TIGHT_SEC` | 3분 | 라이브 +60분 이후 폴링 간격 |
| `MAX_TASK_HORIZON_SEC` | 696시간 (29일) | Cloud Tasks 720h 하드리밋보다 보수적인 롱폴링 상한 |

### pre-live phase

| 상황 | 다음 wake |
|---|---|
| 신규 upcoming 감지 (tick에서) | `scheduled_start − 15분`. 이미 지났으면 `now + 60초` |
| `scheduled_start` 가 바뀜 (drift) | 새 `scheduled_start − 15분` 로 재예약, `attempts` 리셋 |
| wake 시점에 아직 `upcoming`, 시작 시각 미래 | `scheduled_start` 정각 |
| wake 시점에 아직 `upcoming`, 시작 후 60분 이내 | `now + 3분` |
| wake 시점에 아직 `upcoming`, 시작 후 60분 초과 | `now + 60분` (fallback) |
| wake 시점에 `live` 로 바뀜 | → **live-watch 전이**, `now + 30분` |
| wake 시점에 `none`(영상 사라짐), `attempts < 6` | `now + 60분` 재시도 |
| wake 시점에 `none`, `attempts >= 6` | **canceled** — 엔트리 드롭, 이후 wake 없음 |

### live-watch phase

| 상황 | 다음 wake |
|---|---|
| 신규 `live` 감지 (관측 누락 복구, tick에서) | `now + 30분` |
| wake 시점에 `live`, 시작 후 60분 이내 | `now + 30분` |
| wake 시점에 `live`, 시작 후 60분 초과 | `now + 3분` |
| wake 시점에 `none` | **ended** — 엔트리 드롭, 이후 wake 없음 (`archive.json` 이관은 reconcile 담당) |
| wake 시점에 `upcoming` 으로 되돌아감 (드묾) | pre-live 로 되돌리고 `scheduled_start − 15분` 재예약 |

### 장기 예약 (대기소·프리챗·굿즈안내 프레임)

`liveBroadcastContent=upcoming` 인데 `scheduled_start` 가 1~2년 뒤인 준영구 프레임은
Cloud Tasks 720h 상한을 넘는다. → `next_check_at` 을 `now + 696시간` 으로 클램프해
그 시각에 깨어나 재평가("롱폴링"). 여전히 먼 미래면 다시 696시간 뒤로 재예약.

### enqueue 시각 클램프 (공통 마무리)

모든 enqueue 시각은 `[now + 60초, now + 696시간]` 범위로 클램프되고,
살아있는 엔트리의 `next_check_at` 도 그 값에 맞춰 `pending.json` 과 실제 태스크를 일치시킨다.

- Cloud Tasks dedupe: 태스크 이름 `wake-{video_id}-{분버킷}` — 같은 방송·같은 분이면
  중복 enqueue 무시.

---

## 3. 전파 지연 — 변화가 화면에 뜨기까지

백엔드가 `data` 브랜치에 `schedule.json` 을 커밋한 순간부터 팬 브라우저에 반영되기까지:

| 단계 | 지연 |
|---|---|
| 백엔드 → `data` 브랜치 커밋 (GitHub Contents API) | 즉시 |
| `raw.githubusercontent.com` CDN 캐시 (`Cache-Control: max-age=300`) | 최대 **~5분** — 새 커밋이어도 만료 전엔 옛 내용 |
| 프론트 다음 폴링 (`config.js` `POLL_MS = 75초`) | 최대 **75초** |
| 렌더 (`main.js`: 직전과 바이트가 다르면 `renderBoard` 즉시) | 즉시 |

→ **커밋 → 화면 반영: 최악 ~6분** (≈ 5분 + 75초). 보통은 1~3분 — raw CDN 엣지마다
캐시 상태가 달라 항상 5분을 꽉 채우지는 않음. 3시간 단위 방송 예고엔 충분한 트레이드오프
(INTERVIEW #14).

### 실제 이벤트부터 (감지 지연 포함)

커밋은 백엔드가 wake/tick 으로 깨어나 변화를 **발견**했을 때만 일어나므로, 현실 이벤트와
커밋 사이 지연이 앞에 붙는다:

- 예정 시작 직후 라이브 전환 감지: pre-live tight 폴링 → 최대 **~3분** (pre-live 단계),
  이미 live-watch 면 초기 **30분** 간격
- 방송 종료 감지: live-watch **3분**(시작 +60분 이후) 또는 **30분** 간격

즉 팬 입장 end-to-end "라이브 켜짐 → 사이트에 뜸" ≈ 감지 3분 + 전파 6분 = **최대 ~10분**,
평상시 5분 안팎.

---

## 4. 한눈에 보기 — 방송 하나의 생애

```
                 tick(RSS)이 upcoming 최초 발견
                          │
   scheduled_start-15m ───┤ 첫 wake (pre-live)
                          │  ├ still upcoming & 시작 전 → scheduled_start 정각에 wake
   scheduled_start ───────┤  ├ still upcoming & <60m  → 3분 간격
                          │  ├ still upcoming & >60m  → 60분 간격 (fallback, 최대 6회)
                          │  └ live 확인 → live-watch 전이
                          │
   actual_start ──────────┤ live-watch
                          │  ├ <60m → 30분 간격
   actual_start+60m ──────┤  └ >60m → 3분 간격
                          │
   방송 종료(none) ────────┘ 엔트리 드롭, wake 종료
```

정기 `light` tick(3시간 간격)은 이 흐름과 별개로 계속 돌면서 wake가 놓친 방송을
주워담고 pending 을 정합화한다.

---

## 5. 정합성 보정 (사각지대 패치)

### 5.1 동시 실행 충돌 — 낙관적 동시성 재시도

방송 시작 시간대엔 정기 tick 과 여러 `/wake` 가 겹쳐 같은 `data` 브랜치 파일
(`schedule.json` / `pending.json` / `archive.json`)을 동시에 고치려 한다.

`gh_store.write_json` 은 **호출자가 계산을 시작할 때 읽은 sha**(`prev_sha`)를 PUT 에 실어
낙관적 동시성을 건다. 그 사이 다른 실행이 다른 내용으로 먼저 커밋했으면 `ConflictError`.
`handlers._run` 은 이때 **RSS/YouTube 재조회 없이**(이미 받은 `videos` 재사용) 최신
`prev_*` 를 다시 읽어 `build_schedule` / `sync_pending` 을 1회 재계산하고 다시 쓴다.
2회째도 충돌하면 예외를 올려 tick 을 실패시킨다(스케줄러/Cloud Tasks 가 재시도).

> 예전 `write_json` 은 충돌 시 낡은 payload 를 새 sha 로 재-PUT 해 **조용히 덮어썼다**.
> 그러면 겹친 실행의 pending 상태 전이가 유실돼 특정 방송의 wake 체인이 끊겼다(다음 3h
> tick 이 "관측 누락 복구" 로 되살리긴 함). 이제 유실 없음.

### 5.2 `videos.list` 일시 누락 유예 — `removed` 오탐 방지

추적 중이던 방송이 `videos.list` 응답에서 **통째로 빠지면**(삭제/비공개, 또는 "공개→회원전용"
전환 순간, 배치 응답 일시 누락) `reconcile.build_schedule` 이 `archive.json` 으로
`reason:"removed"` 이관한다. archive 는 `video_id` dedupe 라 되돌리기가 지저분하므로,

→ 마지막으로 본 지(`last_updated` 기준) **`STALE_REMOVE_SEC`(6.5시간, light tick 2회분+여유)**
미만이면 **유예**: 마지막으로 알려진 상태 그대로 `schedule.json` 에 유지하고 archive 하지 않는다.
그 시간 이상 연속으로 누락돼야 진짜 삭제로 보고 이관한다.

- `liveBroadcastContent == "none"`(+`actualEndTime` → `ended`, 없으면 `canceled`)은 YouTube 의
  명시 신호이므로 **유예 없이 즉시** archive. "응답에서 통째로 사라짐" 만 애매해서 유예 대상.
- 유예 중엔 `last_updated` 를 갱신하지 않는다(`_stable_view` 가 무시하는 필드라 불필요 커밋 없음).
