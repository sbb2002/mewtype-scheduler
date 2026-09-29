# v4a 구현 계획 — 로컬 시험판

- 작성: 2026-09-29 · 브랜치 `v4a` (기준 `origin/main` `6af6db7`, v3.8.10) · 워크트리 `../mewtype-scheduler-v4a`
- 입력: `v4a_design.md`(배선) · `v4a_decisions.md`(기능 결정 D1~D25) · `v4a_idea.md`(요약)
- **목표: 배포·머지하지 않는다.** 완성 후 운영자 로컬 PC(24시간 가동)에서 며칠 시험 운영한다. 운영(v3.8.10)은 그대로 둔다.
- 표기: **(선택)** = 사용자 미확정이라 기본값으로 둔 설계 선택. **(확인 필요)** = 코드·실측으로 아직 검증 안 함.

## 0. 로컬 시험판의 전제

| 전제 | 내용 | 근거 |
|---|---|---|
| 로컬 PC | 24시간 가동. 외부 인바운드 방화벽 해제 불가 | 사용자 |
| 폰 → 로컬 | Tailscale. 로컬 PC `100.79.146.124`, 폰 `s23` `100.82.203.42`, 직접 연결, 폰→PC HTTP 확인 | 2026-09-29 실측 |
| 저장 | GitHub 데이터 저장소 안 씀 → **로컬 디렉터리** (`_local/<브랜치>/`) | 사용자 |
| 외부 서비스 | Vercel 제외 그대로 (YouTube API · Groq · vxtwitter · healthchecks · Telegram) | 사용자 |
| 프론트 | 로컬에서 띄우고 **Tailscale IP 로 접속** | 사용자 |
| GCP | Cloud Run · Cloud Tasks · Cloud Scheduler 는 로컬 PC 에 닿지 못함(인바운드 불가) → **로컬 대응물로 대체 (선택)** | Tailscale 주소는 외부 인터넷에서 안 보임 |
| 텔레그램 | 봇 하나에 webhook 하나 → **로컬 전용 봇 + `getUpdates` 폴링 (선택)**. 봇 생성(BotFather)은 운영자 작업 | |
| 업스트림 | Automate 에 로컬 URL 로 **추가 발송**(운영 먼저, 로컬 나중, 로컬 실패해도 계속) **(선택)** — 운영자 작업 | |

## 1. v4a 구성 요소 → 로컬 대응물

흐름도(`v4a_flow.html`)의 구성 요소를 로컬에서 같은 **역할·순서**로 재현한다. 검증(§6)은 이 대응표 기준.

| v4a 구성 요소 | 로컬 대응물 | 모듈 |
|---|---|---|
| 접수 서비스 `mewtype-intake` | 로컬 러너 안 Flask 앱 (현 `telegram_app.app` 라우트 재사용 + `/admin`) | `local_runner.py` |
| 쓰기 서비스 `mewtype-writer` | 로컬 러너 안 **적용 큐 워커 스레드 1개** (`q-apply`) — data 를 쓰는 유일한 스레드 | `apply.py` · `jobqueue.py` |
| 적용 큐 `mewtype-apply` (동시 1) | `LocalQueue("apply")` — 순차 실행 · 예약 실행(run_at) · 이름 중복 제거 · 재시도 · 마지막 시도 실패 콜백 · 디스크 영속 | `jobqueue.py` |
| 가공 큐 `mewtype-enrich` | `LocalQueue("enrich")` — 번역 재시도 | `jobqueue.py` · `enrich.py` |
| 정기 reconcile 잡 (10분 · 06:00 JST) · 스냅샷 잡 (06:10 KST) | 로컬 러너 스케줄러 스레드가 적용 큐에 `reconcile` / `snapshot` 적재 | `local_runner.py` |
| `data` · `ops` · `monitoring` 브랜치 | `_local/data/` · `_local/ops/` · `_local/monitoring/` (+ 원문 보존 `_local/raw/`) | `local_store.py` · `storage.py` |
| raw CDN → 팬 브라우저 | 로컬 러너가 `/data/*` 로 서빙 + 프론트 `/` 서빙 (Tailscale IP 바인딩) | `local_runner.py` · 프론트 `config.js` |
| Telegram webhook | 로컬 봇 `getUpdates` 폴링 → 같은 `/telegram` 처리 함수로 전달 | `tg_poll.py` |

**원칙(설계 §4) 로컬 적용:** ① data 쓰기는 `q-apply` 스레드만(커밋 기록에 스레드 이름을 남겨 검증) ② 접수는 적재 ③ 즉시 wake·자기 호출·재개 tick → 전부 `reconcile(범위)` 적재 ④ 느린 외부 호출은 접수 쪽(예외: reconcile 의 YouTube 조회) ⑤ 운영 상태는 `ops`.

**알려진 차이 (선택):** 원칙 ②에서 접수 쪽은 현행 DM 문구를 유지하려고 **적재 후 결과를 기다린다**(`submit_and_wait`). Cloud Tasks 는 결과를 돌려주지 않으므로, 배포 단계에서 비동기 적재 + 작업 결과 조회로 바꿔야 한다(§7).

## 2. 기능 결정(D1~D25) 구현 위치

| 결정 | 구현 | 담당 |
|---|---|---|
| D1 live = YT 알림 + 폴링 안전망 | `apply` 작업 `yt_notif` (알림 → 해당 아이템 live) + 기존 폴링 유지 | Claude |
| D2 watching = 예고 20분 전 / YT 30분 전 알림 | `statemachine.PRELIVE_LEAD_SEC = 20*60`, `yt_notif(tunein)` → watching | Claude |
| D3 URL 없는 announced + 30분 전 알림(±45분) | `yt_notif`: video_id 로 못 찾으면 같은 채널 URL 없는 announced 중 예고 시각이 (알림시각+30분) ±45분인 것에 URL 부여 → watching | Claude |
| D4 시작+2분 `search.list` 1회, 예고+1h 까지 live 못 오르면 out | reconcile 이 URL 없는 announced 를 보고 판단. `YouTubeClient.search_live(channel_id)` 신규 | Claude · H3 |
| D5 assumed-live · announced 지각 강등 폐지 | `statemachine` 규칙 4 삭제, URL 없는 아이템 규칙 3·late-hold 대체. **영상 있는 watching 의 120분 강등은 upcoming 으로 유지 (선택)** | Claude |
| D6 end → 같은 영상 live 재관측 시 복구 | `preview_build` 섹션 1 + `derive` end 분기 | Claude |
| D7·D8 `none` → `out`, 용어 등록 | 상태값만 개명(YouTube `liveBroadcastContent="none"`·소식 `mode:"none"` 등 다른 의미의 none 은 그대로). 모니터 리포트는 옛 로그의 `none` 도 읽음. `docs/TERMINOLOGY.md` | Claude |
| D9 레인에 live 가 있으면 end 보다 ON-AIR 우선 (합동 포함) | `render.js` | H5 |
| D11·D12 판정 방식 | 현행 유지(공식 = 정규식, 개인 = 정규식 + LLM) | — |
| D13 공식 트윗 영상 URL → 즉시 `videos.list` → upcoming | 접수 쪽 릴레이 경로에서 row 에 video 정보 보강 후 적재 | Claude |
| D14 upcoming 필수 = URL · 날짜 · 제목 | `preview.promote_state` | Claude |
| D15 개인 트윗 썸네일 안 받음 | 현행과 같음 (확인됨) | — |
| D16 소식 리트윗 제외 | `xnotice.parse` | H4 |
| D17 개인 트윗 리트윗 제외 | 현행과 같음 | — |
| D18 트윗 보존 48h | `xtweet.TTL_HOURS = 48` | H4 |
| D19 스케줄 관련 원문 보존 | `rawlog.append_raw` → `_local/raw/` (배포 시 위치는 미결 — 공개 저장소 문제) | H6 · Claude(연결) |
| D20~D22 현행 유지 | 회원 전용 · 콜라보 판정 · 비유튜브 URL → 소식 | — |
| D23 모니터링 유지 | 로컬 store 로 그대로 | Claude(연결) |
| D24 관리자 웹 UI + DM 은 status · pause · resume · list (+ `/admin`) | `admin_web.py` + `admin_api.py`, `/telegram` 명령 축소 | H7 · Claude |
| D25 DB 이관 보류 | — | — |

## 3. 작업 패키지 (WP)

파일 소유권을 겹치지 않게 나눴다. **한 WP 는 표에 적힌 파일만 수정한다.** Haiku 에이전트는 커밋하지 않는다(Claude 가 검증 후 커밋).

### Wave 1 — 병렬 (Haiku H1~H6 ∥ Claude C1)

| WP | 담당 | 파일 | 내용 · 완료 조건 |
|---|---|---|---|
| H1 | Haiku | `src/backend/local_store.py` (신규) | `GitHubStore` 와 같은 인터페이스·의미의 로컬 파일 store. self-test |
| H2 | Haiku | `src/backend/jobqueue.py` (신규) | `LocalQueue` — 순차 워커 · run_at · 이름 중복 제거 · 재시도/마지막 시도 · 영속 · `submit_and_wait`. self-test |
| H3 | Haiku | `src/collector/youtube.py` | `search_live(channel_id)` 추가 + self-test(mock) |
| H4 | Haiku | `src/backend/xtweet.py` · `src/backend/xnotice.py` | D18 48h · D16 리트윗 소식 제외 + self-test 갱신 |
| H5 | Haiku | `src/frontend/js/config.js` · `render.js` · `src/frontend/monitor.html` | 로컬 데이터 URL 모드 · D9 live 우선 |
| H6 | Haiku | `src/backend/tg_poll.py` · `src/backend/rawlog.py` (신규) | getUpdates 폴링 · 원문 보존 append. self-test |
| C1 | Claude | `statemachine.py` · `preview_build.py` · `preview.py` · `handlers.py` · `notify.py` · `monitor_report.py` | D2 · D4(판단부) · D5 · D6 · D7 · D14 |

### Wave 2 — 배선 (Claude C2 ∥ Haiku H7)

| WP | 담당 | 파일 | 내용 |
|---|---|---|---|
| C2 | Claude | `storage.py` · `apply.py` · `enrich.py` · `local_runner.py` (신규), `writeclient.py` · `handlers.py` · `monitor_log.py` · `app.py` · `telegram_app.py` · `config.py` | store 팩토리(로컬/깃허브, `control.json`·`admin_state.json` → ops 라우팅) · 적용 큐 · reconcile 통일 · 가공 큐 · D1·D3·D4(실행부)·D13·D19 연결 · 텔레그램 명령 축소 · 로컬 러너 |
| C2' | Claude | `src/backend/admin_api.py` (신규) | 관리 페이지가 부르는 함수 모음(읽기 + 적재). H7 이 쓸 시그니처를 먼저 고정 |
| H7 | Haiku | `src/backend/admin_web.py` · `src/backend/admin_static/admin.html` (신규) | 로그인 링크(HMAC · nonce · 세션 쿠키 · CSRF) + 화면(예고 · 원문 투입 · 소식/트윗 · 작업 이력 · 유실 원문 · 운영 · 리포트 링크) |

### Wave 3 — 검증 · 문서 (Claude)

| WP | 내용 |
|---|---|
| V1 | 전 모듈 self-test · 로컬 러너 기동 · 시나리오 재생(§6) · 흐름도 대조 |
| V2 | 플로우차트 애니메이션 HTML (`ref/v4a/v4a_verify_flow.html`) — 검증에서 실제 관측된 경로를 흐름도 스타일로 재생 |
| V3 | `CLAUDE.md` · `docs/TERMINOLOGY.md` · 로컬 운영 안내(`ref/v4a/v4a_local_runbook.md`) |

## 4. 인터페이스 명세 (Wave 1 WP 가 지켜야 할 것)

### 4-1. `LocalStore` (H1)
- `LocalStore(root: str, branch: str)` — 파일은 `<root>/<branch>/<path>`. 속성 `root` · `branch` · `repo="local"` · `token=""` · `session=None` · `timeout=0`.
- `read_json(path) -> (dict|None, sha|None)` · `write_json(path, data, *, prev_sha, message) -> (changed, sha)` ·
  `read_text` · `write_text(path, text, *, prev_sha=None, message)` · `list_dir(path) -> [파일명]`(하위 디렉터리 제외, 없으면 `[]`) ·
  `with_branch(branch) -> LocalStore`.
- 의미는 `gh_store.GitHubStore` 와 동일: 직렬화 `gh_store._serialize` 재사용, 내용 같으면 쓰지 않음(False, 현재 sha), `prev_sha` 가 현재 sha 와 다르면 `gh_store.ConflictError`.
- sha = 파일 바이트의 sha1 hex. 쓰기는 임시파일 + `os.replace`(원자적). 프로세스 내 경로별 잠금.
- 쓸 때마다 `<root>/<branch>/.commits.jsonl` 에 `{"ts","path","message","sha","thread"}` 한 줄 추가(`thread` = `threading.current_thread().name`) — 단일 쓰기 원칙 검증용.

### 4-2. `LocalQueue` (H2)
- `LocalQueue(name, handler, *, persist_path=None, max_attempts=5, backoff_sec=(1,2,4,8,16), on_done=None, on_dead=None, clock=time.time)`
- `handler(kind: str, args: dict, meta: dict) -> dict` — `meta = {"job_id","name","attempt","is_last","queue"}`.
- `enqueue(kind, args, *, run_at_iso=None, name=None) -> job_id` — 바로 반환. `name` 이 같은 대기 작업이 있으면 추가하지 않고 기존 id 반환(Cloud Tasks 태스크 이름 의미).
- `submit_and_wait(kind, args, *, timeout=120) -> dict` — 적재 후 결과를 기다림(예외는 호출자에게 다시 던짐).
- 워커 스레드 1개(`q-<name>`), `run_at` 도달 순 실행. 예외 → 백오프 재시도, 마지막 시도 실패 → `on_dead(job, exc)`. 성공 → `on_done(job, result)`.
- `persist_path` 가 있으면 대기 작업을 JSON 으로 저장·기동 시 복원. `start()` · `stop()` · `pending() -> list[dict]`.

### 4-3. 그 외
- H3 `YouTubeClient.search_live(channel_id: str) -> list[str]` — `search.list` `part=id, channelId, eventType=live, type=video, maxResults=5`. 실패 시 `[]`. (쿼터 100)
- H6 `rawlog.append_raw(store, *, kind: str, raw: str, meta: dict, now_iso: str) -> bool` — `raw/YYYY-MM.jsonl` 에 한 줄 append(`read_text`/`write_text`, `ConflictError` 3회 재시도). 예외 안 던짐.
- H6 `tg_poll.run_polling(bot_token, on_update, *, stop_event, offset_path=None, session=None)` — 시작 시 `deleteWebhook`, `getUpdates` long polling(timeout 50), offset 영속, 네트워크 오류 백오프.
- H5 데이터 URL: 호스트가 `*.vercel.app` 이면 기존 raw URL, 아니면 같은 출처 `/data/preview.json` · `/data/notices.json` · `/data/tweets.json`.

## 5. 로컬 러너 (C2)

```
python -m src.backend.local_runner          # .env.local 읽음
  바인딩: 127.0.0.1 + LOCAL_BIND(기본 100.79.146.124), 포트 LOCAL_PORT(기본 8787)
  /            프론트 (src/frontend)
  /data/*      _local/data/*  (no-store)
  /ingest      업스트림 (X-Ingest-Secret)
  /admin …     관리 페이지
  /monitor-live 웹 모니터
  스레드: q-apply(쓰기) · q-enrich · scheduler · tg-poll
```
필요 env(로컬 전용): `V4A_RUNTIME=local` · `LOCAL_DATA_DIR` · `LOCAL_BIND` · `LOCAL_PORT` · `INGEST_SECRET`(운영과 다른 값) ·
`TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID`(로컬 봇) · `YOUTUBE_API_KEY` · `GROQ_API_KEY` · `ADMIN_SECRET` · (선택) `HEALTHCHECK_URL` 비움.

## 6. 검증 (V1)

1. **self-test**: 기존 모듈 전부 + 신규(local_store · jobqueue · tg_poll · rawlog · apply · admin_web).
2. **시나리오 재생**: 로컬 러너를 띄우고 fixture·실측 알림 원문을 `/ingest` 로 흘려(YouTube API 는 mock 옵션) 기능별 경로를 관측 —
   공식 스케줄(URL 유/무) · 개인 트윗(예고/일반/리트윗) · 소식 · YT tunein/start(URL 유/무, ±45분) · 회원 전용 · 종료→재개(D6) · URL 없는 예고 +2분 검색/+1h out(D4) · 관리 페이지 조작.
3. **흐름도 대조**: 이벤트 로그 · `.commits.jsonl`(쓰기 스레드) · 큐 기록으로 흐름도의 단계 순서와 비교 — 특히 원칙 ①(data 쓰기 = `q-apply` 만) ③(지름길 없음).
4. 결과를 `ref/v4a/v4a_verify_report.md` 에 표로 남기고, 차이는 숨기지 않는다.

## 7. 이번 범위 밖 (배포 단계)

Cloud Tasks 적용·가공 큐 어댑터 · `/apply`·`/enrich` OIDC · Cloud Run 이름 전환 · Scheduler 잡 교체 · 비동기 적재 + 작업 결과 조회(§1 알려진 차이) · 60건 버스트 측정 ·
원문 보존 위치(공개 저장소 문제) · 사장 코드 정리(`ingest_queue` · `push_monitor.py` · ECHO/DRY-RUN 등, 설계 §12-1) · 항목 단위 되돌리기(관리 페이지에서 목록만 먼저).
