# 구현 명세 v2.1 (IMPLEMENTATION_v2.1) — Telegram 모니터링 & 제어

v2.0 백엔드(`docs/IMPLEMENTATION_v2.md`) 위에 **Telegram 봇 알림 + 원격 제어**를 얹는다.
운영자(1인) 전용. 팬용 프론트엔드와 무관.

---

## 0. 목표

**아웃바운드 알림** (봇 → 운영자 DM)

| # | 트리거 | 내용 |
|---|--------|------|
| A | upcoming 신규 발생 | 채널(한글명), 제목, 시작 시각(KST + 상대) |
| B | live 시작 | 채널, 제목, 예정→실제 시각, **지각 n분 / 정시 / n분 일찍** |
| C | live 종료 | 채널, 제목, 방송 구간·길이, 사유(정상/취소/삭제) |
| D | light/deep tick 요약 | 후보·조회 수, schedule 변경 여부, enqueue 결과, 전이 요약 — **변경 있을 때만** |
| E | fallback 발생 | 어느 방송이, 왜(예정 지났는데 미시작 등), 다음 확인 시각 |
| F | 서버 오류 / 다운 | 예외 내용 / 핑 유실 감지 |

**인바운드 명령** (운영자 → 봇)

| 명령 | 동작 |
|------|------|
| `/status` | 현재 라이브·예정·대기 wake·마지막 tick·일시정지 상태 요약 |
| `/pause` | 수집·판정·enqueue·알림 전면 중단 (`control.json`) |
| `/resume` | 재개 + 즉시 full sync 로 wake 체인 복구 |

---

## 1. 확정 사항 (v2.0 대비 아키텍처 변경)

### 결정 1 — 인바운드는 **별도 공개 서비스**로 분리 (메인 서비스는 비공개 유지)

Telegram webhook 은 Google OIDC 토큰을 못 붙이므로 도달하려면 공개 엔드포인트가 필요하다.
메인 `mewtype-backend` 를 공개로 바꾸는 대신, **같은 컨테이너 이미지**를 다른 엔트리포인트로 띄운
**`mewtype-telegram`** (公開, `--allow-unauthenticated`) 를 새로 만든다.

- 메인 서비스 보안 태세(`--no-allow-unauthenticated` + OIDC) **변경 없음**.
- `mewtype-telegram` 인증 = `X-Telegram-Bot-Api-Secret-Token` 헤더 + `message.chat.id` 허용목록.
- `mewtype-telegram` 은 `control.json` 을 직접 읽고/쓰며(자체 PAT), `/resume` 시 메인 `/tick` 을
  OIDC 토큰 발급해 호출(heal).
- **아웃바운드 알림(A~F)** 은 메인 서비스가 직접 Telegram `sendMessage` 호출 — 인바운드 노출 불필요.

> 대안(채택 안 함): 메인 서비스를 공개로 바꾸고 전 라우트 앱 내부 인증. 부품은 적지만
> `/tick`·`/wake` 가 앱 코드 인증에만 의존하게 되어 태세가 약해짐.

### 결정 2 — pause 의미: **완전 중단 + resume 시 full heal** (구현 단순안)

`paused` 동안:
- `/tick` : healthcheck 핑만 하고(다운 오탐 방지) 즉시 반환. RSS·videos.list·쓰기·enqueue·알림 전부 skip.
- `/wake` : 200 즉시 반환. 처리·재enqueue **안 함** → wake 체인 휴면.
- `/resume` : `paused=false` 로 쓰고 곧바로 `tick("light")` 1회 실행. `pending.json` 의
  `next_check_at <= now` 엔트리(정지 중 밀린 것 전부)가 section 3 에서 재처리·재enqueue 되어 체인 복구.
  section 3.5(720h 힐링)도 함께 돎.

### 결정 3 — tick 요약(D)은 **변경 있을 때만**

`schedule_changed or newly_ended or decision.dropped or enqueue_errors` 중 하나라도면 전송.
전부 비면 조용히 넘어감(3h마다 스팸 방지). 단 A/B/C/E 이벤트는 항상 개별 전송.

### 결정 4 — 다운 감지: **healthchecks.io** (무료, Telegram 네이티브)

메인 `/tick` 이 성공 끝에 `HEALTHCHECK_URL` 로 GET 1발. healthchecks.io 에서
grace period(예: light 3h 주기 → 3h30m) 초과 시 운영자에게 Telegram 알림.
→ 스케줄러가 멈춘 경우 / Cloud Run 이 죽어 tick 자체가 안 도는 경우 모두 포착.
Cloud Monitoring 알림정책은 이번 범위 밖(healthcheck 로 충분).

---

## 2. 새/변경 파일

```
src/backend/
  notify.py         # Telegram sendMessage + 메시지 포맷 + diff_events()      [haiku #1]
  control.py        # control.json 스키마 + gh_store 연동 load/save           [haiku #2]
  telegram_app.py   # 공개 webhook Flask 앱: /telegram, 명령 디스패치           [haiku #3]
  handlers.py       # (변경) control 체크 + 이벤트 감지 + notify 호출          [Sonnet]
  statemachine.py   # (변경) fallback 진입 시 명시적 로그 토큰                  [Sonnet]
  config.py         # (변경) TELEGRAM_* / HEALTHCHECK_URL / MAIN_SERVICE_URL   [Sonnet]
deploy/
  deploy_telegram.sh   # mewtype-telegram 배포 (같은 이미지, 다른 엔트리포인트) [haiku #4]
  setup.sh             # (변경) TELEGRAM_* 시크릿 추가                          [haiku #4]
  telegram_webhook.sh  # setWebhook 등록/해제                                  [haiku #4]
Dockerfile             # (변경 없음 — 엔트리포인트는 배포 시 --command 로 지정)
```

`control.json` 은 `data` 브랜치 루트에 신규. `schedule.json`/`archive.json`/`pending.json` 와 동거.

---

## 3. 계약 F — `control.json` (data 브랜치 루트)

```jsonc
{
  "paused": false,
  "since": null,               // paused=true 로 바뀐 시각 (ISO 'Z'), 아니면 null
  "by": null,                  // "telegram:/pause" 등 출처 메모
  "updated_at": "2026-08-31T12:00:00Z"
}
```
- 기본형(파일 없음): `{"paused": false, "since": null, "by": null, "updated_at": null}`.
- 직렬화 규칙은 v2.0 §6 과 동일.

### `control.py` API  [haiku #2]

```python
def default_control() -> dict: ...
def is_paused(control: dict) -> bool: ...
def set_paused(control: dict, paused: bool, *, by: str, now_iso: str) -> dict:
    """새 dict 반환. paused=True 면 since=now_iso, False 면 since=None."""
```
- 로드/저장은 handlers·telegram_app 이 `GitHubStore.read_json("control.json")` /
  `write_json("control.json", ...)` 로 직접. `control.py` 는 순수 헬퍼만.

---

## 4. `notify.py`  [haiku #1]

`requests` 만. Telegram Bot API `https://api.telegram.org/bot{token}/sendMessage`.

```python
class Telegram:
    def __init__(self, token: str, chat_id: str, *, session=None, timeout: float = 10.0):
        """token/chat_id 비면 disabled 플래그. send() 는 no-op + warning."""
    def send(self, text: str, *, parse_mode: str = "HTML", silent: bool = False) -> bool:
        """POST sendMessage. 실패(네트워크/4xx)는 예외 없이 False + logging.warning.
           절대 호출부의 주 로직을 깨지 않는다."""
```

### 이벤트 감지 — 순수 함수

```python
from dataclasses import dataclass

@dataclass
class Event:
    kind: str            # "upcoming" | "live_start" | "live_end" | "fallback"
    channel_ko: str
    title: str
    text: str            # 이미 포맷된 전송용 본문 (HTML)

def diff_events(prev_schedule: dict, new_schedule: dict, newly_ended: list[dict],
                sm_log: list[str], channels_cfg: dict, now_iso: str) -> list[Event]:
    """
    prev/new schedule.broadcasts 를 video_id 로 대조 + newly_ended + statemachine 로그로
    A/B/C/E 이벤트 목록 생성. 순수(네트워크/시계 없음, now_iso 인자).

    - 첫 실행 가드: prev_schedule.get("generated_at") 가 None 이거나
      prev broadcasts 가 0개면 upcoming(A) 이벤트는 생성하지 않음(초기 스팸 방지).
    - A upcoming : new 에 있고 status=="upcoming" 인데 prev 에 없음.
    - B live_start : 같은 video_id 가 prev "upcoming" → new "live",
        또는 new 에 새로 status=="live" 로 등장. lateness = actual_start − scheduled_start.
    - C live_end : newly_ended 각 레코드. reason → 사유 라벨. 길이 = actual_end − actual_start(둘 다 있으면).
    - E fallback : sm_log 중 "fallback " 로 시작하는 토큰 (statemachine 이 명시적으로 남김).
    채널 한글명은 channels_cfg["channels"][key]["name_ko"].
    """

def summary_text(result: dict, now_iso: str) -> str:
    """handlers 의 tick 결과 dict → D(요약) 본문. 호출부가 '변경 있을 때만' 판단."""

def error_text(where: str, exc: BaseException) -> str:
    """F(서버 오류) 본문."""
```

### 메시지 포맷 (한국어, HTML parse_mode)

```
📅 <b>예정 방송</b>
나카마치 아라레
「歌枠 ~まったりお歌~」
시작: 09/07 23:45 (6일 후)

🔴 <b>방송 시작</b>
미네츠키 리츠
「【ASMR】…」
예정 22:00 → 실제 22:07 · <b>7분 지각</b>

⚫ <b>방송 종료</b>
미네츠키 리츠
「【ASMR】…」
22:07 ~ 00:14 (2시간 7분) · 정상 종료

🔄 <b>light sync</b> 21:00
후보 78 · 조회 78 · 쿼터 2
schedule 변경 O · pending 6건 · enqueue 3/3
전이: new pre-live ×2

⚠️ <b>fallback</b>
치토세 유노 「新春配信」
예정 22:00 경과·미시작 (시도 3회) → 다음 확인 23:00

🚨 <b>서버 오류</b>
/wake video_id=abc123
RuntimeError: YouTube API error: 403 quotaExceeded
```

지각 라벨: `lateness_sec > 300` → `"{n}분 지각"` / `"{h}시간 {m}분 지각"`; `-300..300` → `"정시"`;
`< -300` → `"{n}분 일찍"`. (프론트 `time.js` 의 5분 유예와 동일 기준)

---

## 5. `handlers.py` 변경  [Sonnet]

`_run()` 흐름에 삽입:

1. **맨 앞**: `control, _ = gh.read_json("control.json")`; `if is_paused(control): ` → healthcheck 핑만 하고
   `return {"paused": True}`. (`/wake` 도 동일 가드 — `wake()` 진입 직후)
2. 기존 로직(reconcile → statemachine → 쓰기 → enqueue) 그대로.
3. **쓰기 후, enqueue 후**:
   ```python
   tg = Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id)
   events = diff_events(prev_schedule, new_schedule, newly_ended,
                        decision.log, channels_cfg, now_iso)
   for ev in events:
       tg.send(ev.text)
   if result["schedule_changed"] or newly_ended or decision.dropped or result["enqueue_errors"]:
       tg.send(summary_text(result, now_iso), silent=True)
   ```
4. **성공 끝**: `if cfg.healthcheck_url: requests.get(cfg.healthcheck_url, timeout=5)` (실패 무시).
5. **예외 경로** (`app.py` 의 500 핸들러 + `_run` 을 감싸는 try): `tg.send(error_text(where, exc))` 후 re-raise.
   - healthcheck 는 실패 시엔 안 침 → 연속 실패면 grace 후 다운 알림.

`prev_schedule` 은 이미 `_run` 이 읽고 있으므로 추가 I/O 없음.

## 6. `statemachine.py` 변경  [Sonnet]

fallback 진입 분기(`now >= ss + PRELIVE_FALLBACK_AFTER_SEC`)에서 로그를
`"pre-live wait {vid} attempts={n}"` → **추가로** `"fallback {vid} attempts={n} next={iso}"` 도 append.
`diff_events` 가 이 토큰을 파싱. 다른 로직 변화 없음. self-test 시나리오 하나 추가.

## 7. `telegram_app.py` — 공개 webhook 서비스  [haiku #3]

Flask. 엔트리포인트 `src.backend.telegram_app:app`. **같은 이미지**, 배포 시 `--command` 로 지정.

```python
POST /telegram      # Telegram webhook
GET  /              # 200 헬스체크
```

`/telegram` 처리:
1. `request.headers.get("X-Telegram-Bot-Api-Secret-Token") == cfg.telegram_webhook_secret` 아니면 → 200 무시.
2. body `message.chat.id` (문자열화) != `cfg.telegram_chat_id` → 200 무시 (남에게 응답 안 함).
3. `text` 파싱 — `/status` / `/pause` / `/resume` / 그 외(도움말).
4. 항상 **200** 반환 (Telegram 재시도 방지). 응답 메시지는 `sendMessage` 로 별도 전송.

명령별:

- **`/status`**
  - `gh.read_json("schedule.json")`, `read_json("pending.json")`, `read_json("control.json")`.
  - 라이브: `broadcasts` 중 status=="live" (채널·제목·`actual_start` KST).
  - 예정: 버킷 카운트 — today(<24h) / week(<7d) / later. (프론트 버킷 기준과 동일)
  - 대기 wake: `pending.entries` 수 + 가장 이른 `next_check_at`.
  - 마지막 tick: `schedule.generated_at` (상대시간).
  - 일시정지: `control.paused` → `since` 상대시간.
  ```
  상태: 🟢 정상   (또는  ⏸ 일시정지 (12분째))
  마지막 sync: 21:00 (12분 전)
  라이브: 1 — 리츠 「ASMR…」 22:07~
  예정: 오늘 2 · 이번주 1 · 이후 3
  대기 wake: 6건 · 다음 22:45
  ```

- **`/pause`**
  - `control = set_paused(control, True, by="telegram:/pause", now_iso=now)` → `gh.write_json`.
  - 회신: `⏸ 일시정지됨. /resume 으로 재개하세요.`

- **`/resume`**
  - `set_paused(..., False, ...)` → write.
  - 메인 서비스 `POST {MAIN_SERVICE_URL}/tick` 를 OIDC 토큰 발급해 호출 (`body {"mode":"light"}`).
    - OIDC: `google.oauth2.id_token.fetch_id_token(Request(), MAIN_SERVICE_URL)` (런타임 SA 가
      메인서비스 `run.invoker` 보유 필요 — §9).
  - 회신 1: `▶️ 재개. 동기화 중…` → 응답 오면 회신 2: `▶️ 완료. pending {n}건, enqueue {m}건.`

- **그 외 텍스트**: 짧은 도움말 (`/status /pause /resume`).

## 8. `config.py` 변경  [Sonnet]

추가 env (둘 다 서비스 공용, 없으면 해당 기능 비활성):
```
TELEGRAM_BOT_TOKEN       # BotFather
TELEGRAM_CHAT_ID         # 운영자 DM chat id
TELEGRAM_WEBHOOK_SECRET  # setWebhook 시 지정한 secret_token (telegram_app 만 사용)
HEALTHCHECK_URL          # healthchecks.io ping URL (메인 tick 만 사용)
MAIN_SERVICE_URL         # telegram_app 의 /resume 이 호출할 메인 서비스 URL (= 기존 SERVICE_URL)
```
`load_config()` 는 이것들이 없어도 통과(기능만 off). `TELEGRAM_*` 없으면 `Telegram.send` no-op.

---

## 9. 인프라  [haiku #4]

### `deploy/setup.sh` 추가
```sh
create_secret TELEGRAM_BOT_TOKEN      "BotFather 봇 토큰"          "${TELEGRAM_BOT_TOKEN:-}"
create_secret TELEGRAM_WEBHOOK_SECRET "webhook secret (임의 문자열)" "${TELEGRAM_WEBHOOK_SECRET:-}"
# TELEGRAM_CHAT_ID, HEALTHCHECK_URL 은 비밀 아님 → env 로 주입 (deploy 스크립트)
```
`deploy/env.sh`(=.env 매핑)에 `TELEGRAM_BOT_TOKEN` `TELEGRAM_WEBHOOK_SECRET` `TELEGRAM_CHAT_ID`
`HEALTHCHECK_URL` 추가.

### `deploy/deploy.sh` 변경 (메인)
`--set-env-vars` 에 `TELEGRAM_CHAT_ID=…,HEALTHCHECK_URL=…` 추가,
`--set-secrets` 에 `TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest` 추가.

### `deploy/deploy_telegram.sh` (신규)
```sh
source deploy/env.sh
MAIN_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$GCP_LOCATION" --format='value(status.url)')
# 같은 이미지, 다른 엔트리포인트. --source 재빌드 대신 메인이 만든 이미지를 재사용해도 되나
# 간단히 --source . + --command 로.
# INVOKER_SA 로 실행 — /resume 이 메인 /tick 을 호출할 때 메인의 oidc.verify_request 가
# caller email == INVOKER_SA 를 요구하기 때문. INVOKER_SA 는 secretmanager.secretAccessor 필요(setup.sh).
gcloud run deploy mewtype-telegram \
  --source . --region "$GCP_LOCATION" \
  --allow-unauthenticated \
  --service-account "$INVOKER_SA" \
  --command=gunicorn \
  --args="--bind=0.0.0.0:8080,--workers=1,--threads=4,--timeout=60,src.backend.telegram_app:app" \
  --set-secrets "GITHUB_TOKEN=GITHUB_TOKEN:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest" \
  --set-env-vars "GITHUB_REPO=$GITHUB_REPO,DATA_BRANCH=$DATA_BRANCH,TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID,MAIN_SERVICE_URL=$MAIN_URL,ALLOW_UNAUTH=1"
# ALLOW_UNAUTH=1: telegram_app 은 OIDC 검증 안 함(자체 시크릿 인증). tick/wake 라우트가 없으므로 안전.
# INVOKER_SA 에 메인서비스 invoker 권한 (/resume heal 호출용). deploy.sh 가 이미 부여하지만 멱등 재확인.
gcloud run services add-iam-policy-binding "$SERVICE_NAME" --region "$GCP_LOCATION" \
  --member "serviceAccount:$INVOKER_SA" --role roles/run.invoker
```

### `deploy/telegram_webhook.sh` (신규)
```sh
source deploy/env.sh
TG_URL=$(gcloud run services describe mewtype-telegram --region "$GCP_LOCATION" --format='value(status.url)')
curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${TG_URL}/telegram" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  -d "allowed_updates=[\"message\"]"
# 해제: deleteWebhook
```

### healthchecks.io
운영자가 project 1개 만들고 check 생성 (period 3h, grace 40m) → ping URL 을 `HEALTHCHECK_URL` 로.
Integrations 에서 Telegram 연결.

---

## 10. 테스트

- `notify.py` self-test: `diff_events` 시나리오 —
  (1) prev 없음→upcoming 무시(첫 실행 가드),
  (2) 신규 upcoming 1건→Event kind="upcoming",
  (3) upcoming→live, actual 7분 지각→"7분 지각",
  (4) newly_ended ended→live_end + 길이,
  (5) sm_log "fallback vid …"→fallback Event.
  `Telegram.send` 는 token 없으면 no-op True 반환 확인.
- `control.py` self-test: set_paused true/false round-trip.
- `telegram_app` : 로컬 `ALLOW_UNAUTH=1`, 가짜 update JSON POST → 시크릿 불일치 200/무시,
  chat_id 불일치 200/무시, `/status` 문자열 생성(네트워크 없이 mock gh).
- 통합: 배포 후 실제 봇에서 `/status` → 응답, `/pause` → `control.json` 커밋 확인 →
  다음 스케줄 tick 이 `{"paused": true}` 반환 → `/resume` → heal tick 로그 확인.

## 11. 병렬 배정

| ID | 파일 | 의존 | 네트워크 |
|----|------|------|----------|
| haiku #1 | `src/backend/notify.py` | 계약(schedule/archive 스키마), channels_cfg | requests (Telegram) |
| haiku #2 | `src/backend/control.py` | 계약 F | 없음 (순수) |
| haiku #3 | `src/backend/telegram_app.py` | notify·control·gh_store, google-auth | Flask, google-auth |
| haiku #4 | `deploy/{setup,deploy,deploy_telegram,telegram_webhook}.sh`, `env.sh` 갱신 | §9 | gcloud/curl 텍스트 |
| Sonnet | `handlers.py`·`statemachine.py`·`config.py` 변경, 통합·검수 | 위 전부 | — |

## 12. 운영자 사전 작업 (구현 후 배포 시)

1. **@BotFather** 로 봇 생성 → `TELEGRAM_BOT_TOKEN`. `/setcommands` 로 `status,pause,resume` 등록(선택).
2. 봇과 DM 시작 → `https://api.telegram.org/bot<token>/getUpdates` 로 자기 `chat.id` 확인 → `TELEGRAM_CHAT_ID`.
3. `TELEGRAM_WEBHOOK_SECRET` = 임의의 긴 랜덤 문자열 직접 생성.
4. **healthchecks.io** 무료 가입 → check 생성(period 3h / grace 40m) → ping URL → `HEALTHCHECK_URL`.
   Integrations → Telegram 연결.
5. `.env` 에 위 4개 추가:
   ```
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   TELEGRAM_WEBHOOK_SECRET=...
   HEALTHCHECK_URL=https://hc-ping.com/....
   ```
6. 배포:
   ```bash
   bash deploy/setup.sh          # 새 시크릿 2개 등록
   bash deploy/deploy.sh         # 메인 서비스 재배포 (알림 기능 활성)
   bash deploy/deploy_telegram.sh   # 공개 webhook 서비스 신규
   bash deploy/telegram_webhook.sh  # setWebhook 등록
   ```
7. 봇에 `/status` 보내서 응답 확인.

## 13. 롤백

- webhook 해제: `deleteWebhook` → 인바운드 무력화.
- `mewtype-telegram` 서비스 삭제: `gcloud run services delete mewtype-telegram`.
- 메인 서비스: `TELEGRAM_BOT_TOKEN` env 제거하고 재배포 → 알림 no-op, 나머지 v2.0 동작 그대로.
- `control.json` 은 남아도 무해(`paused:false` 면 v2.0 과 동일).
