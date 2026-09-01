# 백엔드 스케줄 (v2)

v2 백엔드는 Cloud Run **scale-to-zero** HTTP 서비스다. 요청이 올 때만 인스턴스가 뜨고,
그 외 시간엔 인스턴스 0 · 비용 0. 백엔드를 깨우는 트리거는 두 종류뿐이다.

| 트리거 | 엔드포인트 | 주체 | 언제 |
|---|---|---|---|
| 정기 tick | `POST /tick` | Cloud Scheduler | 아래 §1 고정 스케줄 |
| 방송별 wake | `POST /wake` | Cloud Tasks | 아래 §2 상태머신이 방송마다 동적으로 예약 |

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

## 3. 한눈에 보기 — 방송 하나의 생애

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
