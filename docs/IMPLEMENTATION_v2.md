# 구현 명세 v2.0 (IMPLEMENTATION_v2)

`docs/plan/v1_impro_final.md` 의 확정 아키텍처를 구현 단위로 분해한 문서.
v1 명세는 `docs/IMPLEMENTATION.md` (그대로 유효). 이 문서는 **v2.0에서 새로 추가/변경되는 것만** 다룬다.

모든 병렬 작업은 이 문서의 **인터페이스 계약**을 기준으로 한다. 계약을 벗어나는 변경은 이 문서를 먼저 고친다.

---

## 0. v1 → v2.0 요약

| | v1 | v2.0 |
|---|---|---|
| 백엔드 compute | GitHub Actions 러너 (`main.py light\|deep`, cron `0 * * * *`) | **Cloud Run** HTTP 서비스 (Flask+gunicorn, scale-to-zero) |
| 정기 트리거 | Actions `schedule:` cron | **Cloud Scheduler** 2잡 (baseline JST 06:00 / light 3h) → `POST /tick` |
| 방송별 정밀 wake | 없음 (매시간 일괄) | **Cloud Tasks** 큐, 방송별 1회성 `POST /wake` |
| 진행 상태 저장 | (없음) | **`pending.json`** (data 브랜치 루트) |
| data 브랜치 쓰기 | Actions 러너가 git commit/push | **GitHub Contents API** + fine-grained PAT (Secret Manager) |
| 인증 | — | Scheduler/Tasks → Cloud Run: **OIDC 토큰** (invoker SA, `roles/run.invoker`) |
| 프론트 | raw CDN 폴링 | **변경 없음** |

## 1. 재사용 (수정 금지, import 해서 사용)

- `src/collector/rss.py` — `fetch_rss_video_ids`, `fetch_all_rss_video_ids`, `_parse_rss`
- `src/collector/youtube.py` — `VideoInfo`(dataclass), `YouTubeClient`(`videos_list` / `search_upcoming` / `channels_list`), `_video_from_item`
- `src/collector/reconcile.py` — `build_schedule(channels_cfg, videos, prev_schedule, now_iso, avatars=None) -> (new_schedule, newly_ended)`, `ended_record`
  - v2 보정: `videos.list` 응답에서 추적 방송이 **통째로 빠졌을 때** 곧바로 `reason:"removed"`
    archive 하지 않고, `last_updated` 기준 `STALE_REMOVE_SEC`(6.5h) 이상 연속 누락일 때만 이관한다
    (배치 일시 누락·"공개→회원전용" 전환 순간의 오탐 방지, SCHEDULE.md §5.2).
    `liveBroadcastContent=="none"` 명시 신호(`ended`/`canceled`)는 유예 없이 즉시 이관 — 무변경.
- `src/collector/config.py` — `load_channels()`, `channel_url(handle)`
- `src/frontend/**` — v2.0에서 손대지 않음

`src/collector/main.py` (v1 오케스트레이터)는 Actions break-glass 경로용으로 유지. v2.0 코드는 여기 의존하지 않음.

## 2. 새 패키지 `src/backend/`

```
src/backend/
  __init__.py
  config.py         # Cloud Run 환경변수 로드                              [Sonnet]
  pending.py        # pending.json 스키마 + load/dump/validate 헬퍼         [haiku #1]
  statemachine.py   # 순수: 폴링 상태 전이 (pending + enqueue 계산)          [haiku #1]
  gh_store.py       # GitHub Contents API 저장소 (read/write JSON)          [haiku #2]
  tasks.py          # Cloud Tasks enqueue                                  [haiku #3]
  oidc.py           # OIDC bearer 토큰 검증 (방어적 심화)                    [haiku #3]
  handlers.py       # 오케스트레이션: tick() / wake()                       [Sonnet]
  app.py            # Flask 앱, 라우트                                      [Sonnet]
  requirements.txt                                                         [haiku #4]
Dockerfile                                                                 [haiku #4]
deploy/
  env.example.sh    # 필요한 모든 env 변수 + 설명                            [haiku #4]
  setup.sh          # gcloud 1회 셋업 (API·큐·SA·IAM·Secret)               [haiku #4]
  deploy.sh         # gcloud run deploy                                    [haiku #4]
  scheduler.sh      # gcloud scheduler jobs create ×2                      [haiku #4]
```

기존 파일 변경: `.github/workflows/collect.yml` — `schedule:` 트리거 제거, `workflow_dispatch` 유지 [haiku #4].

---

## 3. 계약 E — `pending.json` 스키마 (data 브랜치 루트)

```jsonc
{
  "updated_at": "2026-08-31T12:00:00Z",          // ISO UTC 'Z'. 엔트리 변경 시 갱신
  "entries": {
    "<video_id>": {
      "channel_key": "arale",
      "phase": "pre-live",                         // "pre-live" | "live-watch"
      "scheduled_start": "2026-08-31T13:00:00Z",   // ISO UTC 'Z'. 최신 예정 시각. live-watch에서 null 가능
      "actual_start": null,                        // ISO UTC 'Z'. phase=="live-watch"에서 채움
      "next_check_at": "2026-08-31T12:45:00Z",     // ISO UTC 'Z'. 다음 Cloud Task 도달 예정
      "attempts": 0,                               // 현재 phase에서 백엔드가 이 엔트리를 처리한 횟수
      "first_seen": "2026-08-31T09:00:00Z",        // 엔트리 최초 생성 시각
      "last_checked": null                         // 마지막 처리 시각. 없으면 null
    }
  }
}
```

- 기본형(파일 없음): `{"updated_at": null, "entries": {}}`.
- `entries` key = video_id. 직렬화 규칙은 §6 (v1 `store.save_json_if_changed` 와 동일: `sort_keys=True, indent=2, ensure_ascii=False`, 끝 개행 1개).

---

## 4. 모듈별 상세 & 담당

### [haiku #1] `src/backend/pending.py` + `src/backend/statemachine.py`

순수 파이썬. **네트워크·파일·시계 접근 금지** (`now_iso` 는 인자로 받음). Python 3.12, 표준 라이브러리만.
`VideoInfo` 는 duck-typing (`.video_id .channel_id .live_state .scheduled_start .actual_start .actual_end .concurrent_viewers .title .thumbnail`) — 테스트는 `types.SimpleNamespace` 로.

#### `pending.py`

```python
PHASE_PRELIVE = "pre-live"
PHASE_LIVEWATCH = "live-watch"

def default_pending() -> dict:
    """{"updated_at": None, "entries": {}}"""

def make_entry(*, channel_key: str, scheduled_start: str | None, next_check_at: str,
               now_iso: str, phase: str = PHASE_PRELIVE,
               actual_start: str | None = None) -> dict:
    """계약 E 형태의 엔트리 1개 생성. attempts=0, first_seen=now_iso, last_checked=None."""

def validate(pending: dict) -> dict:
    """구조 방어. dict 아니거나 entries 없으면 default_pending().
       엔트리 중 필수 키(channel_key, phase, next_check_at) 없거나 phase 값이 이상하면
       그 엔트리만 제외한 새 dict 반환 (원본 불변). logging.warning 로 사유 남김."""
```

#### `statemachine.py`

```python
from dataclasses import dataclass, field

# 상수 — 문서 §백엔드 로직 그대로. config 아님, 여기 고정.
PRELIVE_LEAD_SEC          = 15 * 60   # 최초 wake: scheduled_start − 15분
PRELIVE_TIGHT_SEC         = 3  * 60   # scheduled_start 지난 뒤 3분 간격
PRELIVE_FALLBACK_AFTER_SEC= 60 * 60   # scheduled_start + 60분 경과 → fallback 진입
FALLBACK_RETRY_SEC        = 60 * 60   # fallback에서 변동 없을 때 1시간 간격
FALLBACK_MAX_ATTEMPTS     = 6         # fallback 6회(≈6h) 연속 실패 시 canceled 로 간주하고 엔트리 드롭
LIVEWATCH_EARLY_SEC       = 30 * 60   # live 시작 ~ +60분: 30분 간격
LIVEWATCH_EARLY_WINDOW_SEC= 60 * 60
LIVEWATCH_TIGHT_SEC       = 3  * 60   # +60분 이후: 3분 간격

@dataclass
class Decision:
    new_pending: dict                          # 갱신된 pending.json (updated_at 포함)
    enqueue: list[tuple[str, str]] = field(default_factory=list)  # [(video_id, schedule_time_iso)]
    dropped: list[str] = field(default_factory=list)              # 이번에 pending에서 제거된 video_id
    log: list[str] = field(default_factory=list)                  # 사람이 읽을 전이 로그

def sync_pending(
    prev_pending: dict,
    videos: dict[str, "VideoInfo"],
    channel_id_to_key: dict[str, str],
    now_iso: str,
    *,
    mode: str,                     # "wake" | "sync"
    woken_video_id: str | None = None,
) -> Decision:
    """
    pending.json 과 Cloud Tasks enqueue 목록만 계산한다.
    schedule.json / archive.json 은 이 모듈의 책임이 아님(reconcile.build_schedule 담당).

    now = parse(now_iso).  parse: 'Z' → '+00:00', datetime.fromisoformat, tz-aware UTC.
    모든 시각 산술은 UTC. 출력 시각도 "...Z".

    ── 1. 신규 엔트리 감지 (mode 무관) ──
    videos 중 pending.entries 에 없는 것:
      live_state == "upcoming" 이고 scheduled_start 존재:
        next = max(scheduled_start − PRELIVE_LEAD_SEC, now + 60s)
        make_entry(phase=pre-live, ...); enqueue (video_id, next); log "new pre-live {vid}"
      live_state == "live":
        next = now + LIVEWATCH_EARLY_SEC
        make_entry(phase=live-watch, actual_start=v.actual_start, scheduled_start=v.scheduled_start, ...)
        enqueue; log "new live-watch {vid} (관측 누락 복구)"
      그 외(none 등): 무시.

    ── 2. drift refresh (mode 무관) ──
    pending 의 phase==pre-live 엔트리 중 videos 에 존재하고 live_state=="upcoming":
      v.scheduled_start != entry["scheduled_start"] 이고 v.scheduled_start 가 미래:
        entry["scheduled_start"] = v.scheduled_start
        next = max(v.scheduled_start − PRELIVE_LEAD_SEC, now + 60s)
        entry["next_check_at"] = next; entry["attempts"] = 0
        enqueue (vid, next); log "reschedule {vid} → {next}"

    ── 3. due 처리 (phase FSM) ──
    처리 대상 = { entry : parse(entry["next_check_at"]) <= now }.
      mode=="wake" 이면 woken_video_id 는 next_check_at 무관하게 항상 포함.
    각 대상 엔트리에 대해 v = videos.get(vid):

      phase == "pre-live":
        v is None  또는  v.live_state == "none":
          attempts += 1
          if attempts >= FALLBACK_MAX_ATTEMPTS:  → dropped += [vid]; 엔트리 삭제; log "canceled {vid}"
          else: next = now + FALLBACK_RETRY_SEC; enqueue; log "pre-live none, retry {vid}"
        v.live_state == "live":
          phase = "live-watch"; actual_start = v.actual_start or now_iso; attempts = 0
          next = now + LIVEWATCH_EARLY_SEC; enqueue; log "pre-live→live-watch {vid}"
        v.live_state == "upcoming":
          ss = parse(entry["scheduled_start"])  (없으면 now 취급)
          attempts += 1
          if now < ss:                              next = ss
          elif now < ss + PRELIVE_FALLBACK_AFTER_SEC: next = now + PRELIVE_TIGHT_SEC
          else:                                      next = now + FALLBACK_RETRY_SEC  # fallback 대기
          enqueue (vid, iso(next)); log "pre-live wait {vid} attempts={attempts}"

      phase == "live-watch":
        v is None  또는  v.live_state == "none":
          dropped += [vid]; 엔트리 삭제; NO enqueue; log "live-watch→ended {vid}"
        v.live_state == "live":
          attempts += 1
          started = parse(entry["actual_start"]) if entry.get("actual_start") else now
          elapsed = (now - started).total_seconds()
          next = now + (LIVEWATCH_EARLY_SEC if elapsed < LIVEWATCH_EARLY_WINDOW_SEC else LIVEWATCH_TIGHT_SEC)
          enqueue; log "live-watch continue {vid}"
        v.live_state == "upcoming":   # 재예약된 드문 케이스
          phase = "pre-live"; attempts = 0; entry["scheduled_start"] = v.scheduled_start
          next = max(parse(v.scheduled_start) - PRELIVE_LEAD_SEC, now + 60s) if v.scheduled_start else now + FALLBACK_RETRY_SEC
          enqueue; log "live-watch→pre-live {vid} (재예약)"

    처리한 엔트리는 last_checked = now_iso, next_check_at = iso(next) (삭제된 건 제외).

    ── 4. 마무리 ──
    변경이 하나라도 있으면 new_pending["updated_at"] = now_iso, 없으면 prev 값 유지.
    enqueue 목록의 각 시각은 "...Z" ISO. 과거 시각이면 now + 60s 로 클램프.
    """
```

**self-test** (`if __name__ == "__main__":`): 최소 6 시나리오 assert —
(1) 신규 upcoming → pre-live 엔트리+enqueue,
(2) pre-live + live 관측 → live-watch 전이,
(3) pre-live + 여전히 upcoming, 시작 전 → next==scheduled_start,
(4) pre-live + 시작 60분 경과 none, attempts 누적 → canceled drop,
(5) live-watch + none → ended drop, enqueue 없음,
(6) drift: scheduled_start 변동 → reschedule enqueue.

---

### [haiku #2] `src/backend/gh_store.py`

`requests` 사용. GitHub Contents API (`https://api.github.com`).

```python
class GitHubStore:
    API = "https://api.github.com"

    def __init__(self, token: str, repo: str, branch: str = "data",
                 *, session: "requests.Session | None" = None, timeout: float = 15.0):
        """token: fine-grained PAT (Contents: Read and write, 해당 레포 한정).
           repo: "owner/name". token 비어있으면 ValueError."""

    def read_json(self, path: str) -> tuple[dict | None, str | None]:
        """GET /repos/{repo}/contents/{path}?ref={branch}
           헤더: Authorization: Bearer {token}, Accept: application/vnd.github+json,
                 X-GitHub-Api-Version: 2022-11-28
           200 → (json.loads(base64decode(resp["content"])), resp["sha"])
           404 → (None, None)
           그 외/네트워크 오류 → RuntimeError(f"...")"""

    def write_json(self, path: str, data: dict, *, prev_sha: str | None,
                   message: str) -> tuple[bool, str | None]:
        """직렬화: json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
           1) 현재 원격 내용을 read_json 으로 재조회. 문자열이 동일하면 (False, 현재 sha) — PUT 안 함
              (남이 우리와 같은 내용을 먼저 커밋한 경우 포함).
           2) prev_sha 가 주어졌는데 현재 sha 와 다르면 → 우리가 읽은 뒤 남이 **다른 내용**을
              커밋한 것 → `ConflictError` (호출자가 최신 상태로 재계산 후 재시도해야 함).
           3) 아니면 PUT /repos/{repo}/contents/{path}
              body: {message, content: base64(직렬화), branch, sha: 현재 sha(있으면)}
              201/200 → (True, resp["content"]["sha"]).  409/422 → `ConflictError`.
           4) 네트워크 오류만 몇 번 재시도. 그 외 상태코드 → RuntimeError.
           prev_sha=None 이면 sha 검사 없이 현재 sha 로 그대로 씀(부트스트랩·단독 실행).

        > 낙관적 동시성. 예전엔 충돌 시 낡은 payload 를 새 sha 로 재-PUT 해 조용히 덮어썼는데,
        > 방송 시작 시간대에 tick/wake 가 겹치면 pending 상태 전이가 유실됐다. 이제 ConflictError
        > 를 올리고 handlers 가 재계산한다 (§5 handlers 흐름, SCHEDULE.md §5.1)."""

class ConflictError(RuntimeError):
    """base sha 어긋남 — 호출자가 최신 상태를 다시 읽어 재계산 후 write_json 재시도."""
```

- 커밋 author 는 PAT 소유자 계정으로 자동. `message` 예: `"data: pending sync 2026-08-31T12:00:00Z"`.
- **self-test**: 네트워크 없이 직렬화 규칙만 검증(`_serialize(data) -> str` 내부 함수로 분리해 assert).
  env 에 `GH_TOKEN_TEST` 있으면 실제 read_json 스모크(옵션).

---

### [haiku #3] `src/backend/tasks.py` + `src/backend/oidc.py`

#### `tasks.py` — `google-cloud-tasks` (`google.cloud.tasks_v2`)

```python
class TaskQueue:
    def __init__(self, *, project: str, location: str, queue: str,
                 target_url: str, invoker_sa: str,
                 client: "tasks_v2.CloudTasksClient | None" = None):
        """target_url: Cloud Run 서비스 베이스 URL (예: https://mewtype-backend-xxx.a.run.app)
           invoker_sa: OIDC 토큰 발급에 쓸 서비스계정 email
           client 미지정 시 tasks_v2.CloudTasksClient()."""

    def enqueue_wake(self, video_id: str, schedule_time_iso: str) -> str:
        """방송별 wake: path="/wake", body={"video_id": …}, name_key=f"wake-{video_id}".
           create_task → 생성된 task.name 반환.
           AlreadyExists → 무시하고 기존 name 유추값 반환 + logging.info. 그 외 → RuntimeError."""

    def enqueue_tick(self, mode: str, schedule_time_iso: str) -> str:
        """후속 tick: path="/tick", body={"mode": mode}, name_key=f"tick-{mode}".
           handlers 가 "방송 방금 종료 → ~20분 뒤 재확인" 용으로 쓴다. 이름이 `tick-{mode}-{분버킷}`
           이라 한 tick 에서 여러 방송이 끝나도 후속 tick 은 1개로 dedupe."""

def _build_task(cfg, *, path: str, body: dict, name_key: str, schedule_time_iso: str) -> dict:
    """순수. tasks_v2 Task 메시지로 변환 가능한 dict 반환:
       {
         "name": f"{queue_path}/tasks/{name_key}-{bucket}",  # bucket = schedule_time epoch//60 (분 버킷)
         "schedule_time": {"seconds": epoch},
         "http_request": {
           "http_method": "POST",
           "url": f"{target_url}{path}",
           "headers": {"Content-Type": "application/json"},
           "body": json.dumps(body).encode(),
           "oidc_token": {"service_account_email": invoker_sa, "audience": target_url},
         },
       }
       name 의 분 버킷 덕분에: 같은 이름·같은 분 재시도는 dedupe(AlreadyExists), 다른 시각은 새 태스크."""
```

- 의존성: `google-cloud-tasks>=2.16`.
- **self-test**: `_build_task` 를 mock cfg 로 호출해 url·body·oidc·name 형식 assert (네트워크 없이).

#### `oidc.py` — `google-auth`

```python
def verify_request(headers, *, expected_audience: str, expected_sa: str | None = None) -> None:
    """headers: dict-like (Flask request.headers). 'Authorization: Bearer <JWT>' 파싱.
       google.oauth2.id_token.verify_oauth2_token(token, google.auth.transport.requests.Request(),
                                                  audience=expected_audience)
       - 검증 통과 후 payload['iss'] in ('https://accounts.google.com','accounts.google.com') 확인
       - expected_sa 주어지면 payload.get('email') == expected_sa 확인
       실패 시 PermissionError(사유). 토큰 없으면 PermissionError("missing bearer token").
       환경변수 ALLOW_UNAUTH == '1' 이면 즉시 return (로컬 개발)."""
```

- 의존성: `google-auth>=2.28`.
- **self-test**: ALLOW_UNAUTH=1 일 때 no-op, 토큰 없을 때 PermissionError 만 assert.

---

### [haiku #4] 인프라

Python 3.12. gcloud 스크립트는 `set -euo pipefail`, 모든 값은 `deploy/env.sh`(gitignore) 에서 `source`.
커밋되는 건 `deploy/env.example.sh`.

#### `src/backend/requirements.txt`
```
requests>=2.31
flask>=3.0
gunicorn>=21
google-cloud-tasks>=2.16
google-auth>=2.28
```

#### `Dockerfile` (레포 루트)
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY src/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY config ./config
ENV PORT=8080
CMD ["sh", "-c", "exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 120 src.backend.app:app"]
```

#### `deploy/env.example.sh`
```sh
# 복사해서 deploy/env.sh 로 저장하고 값 채우기 (deploy/env.sh 는 .gitignore)
export GCP_PROJECT="your-project-id"
export GCP_LOCATION="asia-northeast1"          # Cloud Run / Tasks / Scheduler 동일 리전
export SERVICE_NAME="mewtype-backend"
export TASKS_QUEUE="mewtype-wake"
export RUNTIME_SA="mewtype-backend@${GCP_PROJECT}.iam.gserviceaccount.com"
export INVOKER_SA="mewtype-invoker@${GCP_PROJECT}.iam.gserviceaccount.com"
export GITHUB_REPO="sbb2002/mewtype-scheduler"
export DATA_BRANCH="data"
# Secret Manager 에 넣을 값 (스크립트가 생성 시 물어봄 / 또는 미리 gcloud secrets create)
#   YOUTUBE_API_KEY, GITHUB_TOKEN(fine-grained PAT: Contents R/W, 해당 레포)
# SERVICE_URL 은 deploy.sh 가 배포 후 채워서 재설정
```

#### `deploy/setup.sh` (1회)
1. `gcloud config set project "$GCP_PROJECT"`
2. `gcloud services enable run.googleapis.com cloudtasks.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com`
3. 서비스계정 2개 생성: `$RUNTIME_SA`(설명 "Cloud Run runtime"), `$INVOKER_SA`(설명 "Scheduler/Tasks invoker"). 이미 있으면 skip.
4. IAM:
   - `$RUNTIME_SA` ← `roles/cloudtasks.enqueuer` (프로젝트)
   - `$RUNTIME_SA` ← `roles/iam.serviceAccountUser` **on `$INVOKER_SA`** (OIDC 토큰 태스크 생성 시 act-as)
   - `$RUNTIME_SA` ← `roles/secretmanager.secretAccessor` (프로젝트 또는 시크릿별)
5. 큐 생성: `gcloud tasks queues create "$TASKS_QUEUE" --location="$GCP_LOCATION"` (이미 있으면 skip).
6. 시크릿: `YOUTUBE_API_KEY`, `GITHUB_TOKEN` 없으면 `gcloud secrets create ... --replication-policy=automatic` 후 값 입력 안내(에코 금지, `--data-file=-`).

#### `deploy/deploy.sh`
1. `source deploy/env.sh`
2. `gcloud run deploy "$SERVICE_NAME" --source . --region "$GCP_LOCATION" --no-allow-unauthenticated --service-account "$RUNTIME_SA" --set-secrets "YOUTUBE_API_KEY=YOUTUBE_API_KEY:latest,GITHUB_TOKEN=GITHUB_TOKEN:latest" --set-env-vars "GITHUB_REPO=$GITHUB_REPO,DATA_BRANCH=$DATA_BRANCH,GCP_PROJECT=$GCP_PROJECT,GCP_LOCATION=$GCP_LOCATION,TASKS_QUEUE=$TASKS_QUEUE,INVOKER_SA=$INVOKER_SA"`
3. URL 추출: `URL=$(gcloud run services describe "$SERVICE_NAME" --region "$GCP_LOCATION" --format='value(status.url)')`
4. `SERVICE_URL` env 재설정: `gcloud run services update "$SERVICE_NAME" --region "$GCP_LOCATION" --update-env-vars "SERVICE_URL=$URL"`
5. invoker 권한: `gcloud run services add-iam-policy-binding "$SERVICE_NAME" --region "$GCP_LOCATION" --member "serviceAccount:$INVOKER_SA" --role roles/run.invoker`
6. 끝에 `echo "SERVICE_URL=$URL"` (scheduler.sh 에서 필요).

#### `deploy/scheduler.sh`
```sh
source deploy/env.sh
URL=$(gcloud run services describe "$SERVICE_NAME" --region "$GCP_LOCATION" --format='value(status.url)')
# baseline: JST 06:00
gcloud scheduler jobs create http mewtype-baseline --location="$GCP_LOCATION" \
  --schedule="0 6 * * *" --time-zone="Asia/Tokyo" \
  --uri="$URL/tick" --http-method=POST \
  --headers="Content-Type=application/json" --message-body='{"mode":"baseline"}' \
  --oidc-service-account-email="$INVOKER_SA" --oidc-token-audience="$URL"
# light 안전망: 3시간 간격
gcloud scheduler jobs create http mewtype-light --location="$GCP_LOCATION" \
  --schedule="0 */3 * * *" --time-zone="Etc/UTC" \
  --uri="$URL/tick" --http-method=POST \
  --headers="Content-Type=application/json" --message-body='{"mode":"light"}' \
  --oidc-service-account-email="$INVOKER_SA" --oidc-token-audience="$URL"
```
(이미 있으면 `jobs update` 로. 스크립트가 존재 확인 후 분기.)

#### `.github/workflows/collect.yml` 수정
- `on.schedule` 블록 **삭제**. `on.workflow_dispatch` 유지.
- 나머지(체크아웃·mode 결정·commit) 그대로. 상단에 주석: "v2.0: 정기 수집은 Cloud Run. 이 워크플로우는 수동 break-glass 전용. pending.json 은 갱신하지 않음."

#### `deploy/README.md` (짧게)
`setup.sh → (시크릿 값 입력) → deploy.sh → scheduler.sh` 순서, 롤백 방법, 로그 확인 명령(`gcloud run services logs read`).

---

## 5. [Sonnet] 통합 — `config.py` / `handlers.py` / `app.py`

### `src/backend/config.py`
환경변수 → 설정 객체. 누락 시 명확한 에러(`ALLOW_UNAUTH` 제외 전부 필수, 단 로컬은 예외).
```
GITHUB_TOKEN, GITHUB_REPO, DATA_BRANCH(기본 "data"),
YOUTUBE_API_KEY, GCP_PROJECT, GCP_LOCATION, TASKS_QUEUE,
SERVICE_URL, INVOKER_SA, ALLOW_UNAUTH(기본 "")
```

### `src/backend/handlers.py`
```python
def tick(mode: str) -> dict          # mode: "baseline" | "light"
def wake(video_id: str) -> dict
```
공통 흐름:
1. `cfg = load_channels()`; `id_by_key`, `channel_id_to_key`.
2. `gh = GitHubStore(token, repo, branch)`;
   `prev_schedule, sched_sha = gh.read_json("schedule.json")` (None → `store.default_schedule(cfg)` 재사용 or 인라인 기본형);
   `prev_pending, pend_sha = gh.read_json("pending.json")` (None → `default_pending()`);
   `prev_archive, arch_sha = gh.read_json("archive.json")` (None → `{"updated_at": None, "broadcasts": []}`).
3. 후보 video_id 집합:
   - `wake`: `{video_id} ∪ prev_pending.entries.keys() ∪ prev_schedule 의 upcoming/live video_id`
   - `tick`: `∪ fetch_all_rss_video_ids(id_by_key) 전부`
4. `yt = YouTubeClient(youtube_api_key)`;
   `avatars = yt.channels_list(list(id_by_key.values()))` **오직 mode=="baseline"** 일 때만;
   `videos = yt.videos_list(sorted(후보))`.
5. **커밋 루프 (최대 2회, ConflictError 시 재시도)** — RSS/YouTube 는 위에서 한 번만, `videos` 재사용:
   a. `prev_schedule/sched_sha`, `prev_pending/pend_sha`, `prev_archive/arch_sha` 를 **루프 안에서 새로** 읽는다.
   b. `new_schedule, newly_ended = build_schedule(cfg, videos, prev_schedule, now_iso, avatars)`;
      `_stable_view` 변화 없으면 volatile 필드 동결 + `generated_at` heartbeat.
   c. `decision = sync_pending(prev_pending, videos, channel_id_to_key, now_iso, mode=("wake" if wake else "sync"), woken_video_id=…)`.
   d. `gh.write_json` × 3 (schedule / archive(변경 시) / pending), 각각 위에서 읽은 `*_sha` 를 `prev_sha` 로.
      → `ConflictError` 나면 1회에 한해 a 로 되돌아가 재계산. 2회째 실패 → 예외(스케줄러가 재시도).
6. **Cloud Tasks enqueue** (`tq = _make_task_queue(cfg)` — 라이브러리/설정 없으면 None):
   - `for vid, when in decision.enqueue: tq.enqueue_wake(vid, when)`.
   - `newly_ended` 있으면 `tq.enqueue_tick("light", now + _POST_END_RECHECK_SEC(20분))` **1개** —
     백투백 다음 방송을 3h 이내가 아니라 ~20분 이내에 줍는다. 이름 `tick-light-{분버킷}` 로 dedupe.
7. **Telegram diff** 는 루프 진입 전 스냅샷(`_ps0`)과 `new_schedule` 을 비교 — 재시도로 루프 안
   `prev_schedule` 이 첫 커밋 결과로 바뀌어도 전이 알림을 놓치지 않도록.
8. 반환 dict: `{"mode","woken","candidates":n,"videos":n,"schedule_changed":bool,"archive_changed":bool,
   "archived":[...],"pending_changed":bool,"pending_entries":n,"dropped":[...],"enqueue_planned":n,
   "enqueued":n,"enqueue_errors":[...],"quota_used":yt.quota_used,"log":decision.log}`.

### `src/backend/app.py`
```python
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.post("/tick")
def _tick():
    oidc.verify_request(request.headers, expected_audience=cfg.SERVICE_URL, expected_sa=cfg.INVOKER_SA)
    mode = (request.get_json(silent=True) or {}).get("mode", "light")
    return jsonify(handlers.tick(mode))

@app.post("/wake")
def _wake():
    oidc.verify_request(request.headers, expected_audience=cfg.SERVICE_URL, expected_sa=cfg.INVOKER_SA)
    vid = (request.get_json(silent=True) or {}).get("video_id")
    if not vid: return jsonify({"error": "video_id required"}), 400
    return jsonify(handlers.wake(vid))

@app.get("/healthz")
def _healthz():
    return "ok", 200
```
- 예외 → 500 + `{"error": str(e)}` 로깅. `PermissionError` → 403.
- `videos.list` 쿼터 실패(RuntimeError)는 500 반환해 Cloud Tasks 가 재시도(큐 기본 재시도)하게 둔다.

---

## 6. 직렬화 / 시간 규칙 (전 모듈 공통)

- JSON 저장: `json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"`.
- ISO 파싱: `datetime.fromisoformat(s.replace("Z", "+00:00"))`, 항상 tz-aware UTC 로 다룸.
- ISO 출력: `dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.
- 시각 비교·산술은 전부 UTC. KST 변환은 프론트 `time.js` 담당(v2.0에서도 불변).

## 7. 병렬 배정 요약

| ID | 산출 파일 | 의존 | 네트워크 |
|----|-----------|------|----------|
| haiku #1 | `src/backend/pending.py`, `src/backend/statemachine.py` | 계약 E, VideoInfo shape | 없음 (순수) |
| haiku #2 | `src/backend/gh_store.py` | GitHub Contents API | requests |
| haiku #3 | `src/backend/tasks.py`, `src/backend/oidc.py` | google-cloud-tasks, google-auth | 라이브러리만 |
| haiku #4 | `Dockerfile`, `src/backend/requirements.txt`, `deploy/*`, `collect.yml` 수정 | §4·§5 | gcloud (스크립트 텍스트) |
| Sonnet | `src/backend/config.py`, `handlers.py`, `app.py`, `__init__.py`, 전체 검수·병합 | 위 전부 | — |

각 haiku 산출물은 Sonnet 이 **계약 준수·엣지케이스·예외처리·시크릿 노출** 기준으로 검수 후 병합.
haiku 는 자기 파일의 `if __name__ == "__main__":` 스모크 테스트가 통과하는 상태로 제출.

---

## 8. 사각지대 보정 (2026-09 패치)

방송 패턴 실측(`ref/broadcast-patterns.md`)으로 드러난 스케줄 사각지대 3건을 보정. 상세 동작은
`docs/SCHEDULE.md` §1.1 / §5.

| # | 사각지대 | 보정 | 파일 |
|---|---|---|---|
| 1 | tick/wake 동시 실행 시 `write_json` 이 낡은 payload 로 조용히 덮어써 pending 전이 유실 | `ConflictError` + `handlers._run` 1회 재계산·재시도 (RSS/YT 재조회 없음) | `gh_store.py`, `handlers.py` |
| 2 | `videos.list` 일시 누락·"공개→회원전용" 전환을 즉시 `removed` archive → 오탐 잔류 | `last_updated` 기준 `STALE_REMOVE_SEC`(6.5h) 유예 후 이관 | `reconcile.py` |
| 3 | 일반 방송 종료 직후 시작하는 짧은 다음 방송을 3h tick 간격에 통째로 놓침 | 종료 감지 시 `now+20분` 후속 `light` tick 1개 예약 (`enqueue_tick`, 분버킷 dedupe) | `tasks.py`, `handlers.py` |

**커버 못 하는 것**: 회원 전용 방송은 RSS·`search.list` 어디에도 안 떠서 발견 자체가 불가 —
#3 재확인으로도 못 잡는다. 공개 방송의 백투백/재시작만 커버. (구조적 한계, 별도 수집 경로 필요.)
