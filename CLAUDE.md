# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트

夢限大みゅーたいぷ(무겐다이 뮤타입) 소속 유튜브 방송인 5명의 **예약 방송·라이브 상태**를 취합해
보여주는 반응형 정적 웹사이트. 팬이 사이트에 방문하면 누가 언제 방송하는지, 지금 라이브 중인지,
어느 주소로 가면 되는지 한눈에 확인한다.

- 요구사항·설계 배경: `docs/beta_version/PRD.md`, 인터뷰 원본 `docs/beta_version/INTERVIEW*.md`
- **현행 구현 명세 (계약 A~F, 백엔드·프론트 모듈): `docs/SPEC.md`** — v1/v2.0/v2.1 명세를 통합.
  원본 `docs/old/IMPLEMENTATION{,_v2,_v2.1}.md`
- **현행 전체 흐름 (박스별 설명 + 그림): `docs/ARCHITECTURE.md`** + `docs/v2_4_flow.png`
- 백엔드 스케줄(운영자 시점 요약): `docs/SCHEDULE.md`. 아키텍처 구상도: `docs/plan/v1_impro_final.md`
- 그림: `docs/plan/v2_1_telegram.png` (v2.1)
- **v2.3 (X 예고 릴레이 → `scheduled`)**: `docs/plan/v2_3_x_relay.md`, 핸드오프 `docs/plan/v2_3_handoff.md`
- **v2.4 (합동방송 → 참여 멤버 레인 중복 · ingest 큐)**: `docs/plan/v2_4_collab.md`,
  **실배포 전환 런북 `docs/plan/v2_4_golive.md`**
- **v2.5 (텔레그램 수동 관리 명령 `/list` `/del` `/ingest` `/undo`)**: `docs/plan/v2_5_admin_commands.md`

서버 상시 가동 없음. 무료 인프라만 사용:
- **수집/판정** = **Cloud Run**(scale-to-zero, `src/backend/`) — 정기 트리거 **Cloud Scheduler** 2잡
  (baseline JST 06:00 / light 3h) + 방송별 정밀 wake **Cloud Tasks**. 리전 `asia-northeast1`.
- **저장** = **GitHub `data` 브랜치** — Cloud Run 이 GitHub Contents API(fine-grained PAT)로 커밋.
- **프론트** = **Vercel** 정적 호스팅. (v1 의 GitHub Actions 수집기는 `src/collector/` + `collect.yml`
  `workflow_dispatch` 로 남아 있음 — 비상 수동 경로. 정기 cron 은 제거됨.)

## 저장소 구조

이 `mewtype-scheduler/` 폴더는 상위 `pyworks` 저장소 안에 **중첩된 별도 git 저장소**다
(`origin` = `github.com/sbb2002/mewtype-scheduler`). 상위 `pyworks`와 무관하게 취급.
(2026-08-30: 레포명 오타 `mewtype-schduler` → `mewtype-scheduler` 로 변경됨. 옛 raw URL은 404됨)

```
src/
  frontend/            # Vercel Root Directory = src/frontend, 빌드 없음
    index.html         # 빈 #board + #foot 스켈레톤, <script type="module">
    css/{reset,layout,card}.css
    js/                # ES 모듈, 상대 import
      config.js        # 상수 (DATA_URL, 폴링 주기, 폴백 채널 메타)
      time.js          # UTC→KST 포맷, 상대시간 라벨 — 순수 함수
      api.js           # fetchSchedule(): AbortController 타임아웃, {ok,data|error}
      render.js        # renderBoard / renderFooter / updateCountdowns
      main.js          # DOMContentLoaded → poll 루프 + 카운트다운 틱
  collector/           # v1 순수 모듈 — v2 백엔드가 import 재사용. main.py 는 break-glass 전용
    main.py            # v1 오케스트레이션 (python -m src.collector.main [light|deep])
    config.py          # config/channels.json + YOUTUBE_API_KEY 로드
    rss.py             # 채널 RSS → videoId 발견 (쿼터 0)
    youtube.py         # YouTube Data API v3 (videos.list / search.list), VideoInfo
    reconcile.py       # 상태 판정 + 이전 스냅샷 대비 diff — 순수 함수
    store.py           # schedule.json / archive.json 로드·저장 (변경 시에만 기록)
  backend/             # v2 Cloud Run 서비스 (Flask + gunicorn)
    app.py             # 메인 라우트 /tick(Scheduler) /wake(Cloud Tasks) /healthz
    handlers.py        # tick/wake 오케스트레이션 (rss/youtube/reconcile 재사용)
    statemachine.py    # pending.json 폴링 FSM (pre-live / live-watch) — 순수
    pending.py         # pending.json 스키마 헬퍼
    gh_store.py        # GitHub Contents API read/write (직렬화 규칙 store.py 와 동일)
    tasks.py           # Cloud Tasks enqueue (OIDC 타깃, 720h 상한 클램프)
    oidc.py            # Scheduler/Tasks OIDC bearer 토큰 검증
    config.py          # 환경변수 → Config
    notify.py          # (v2.1) Telegram 알림 + diff_events(A~F)
    control.py         # (v2.1) control.json 스키마 (paused)
    telegram_app.py    # (v2.1) 공개 webhook 서비스 — 엔트리포인트 src.backend.telegram_app:app.
                       #        (v2.3) POST /ingest — 폰 Automate 가 X 알림 텍스트를 릴레이
                       #        (v2.5) /list /del /ingest(=/add) /undo — 텔레그램 수동 관리 명령
    admin.py           # (v2.5) admin_state.json 스키마 (pending_del/undo 슬롯) — 순수
    xrelay.py          # (v2.3) X 예고 트윗 파서(@BDP_yumemita 일일 스케줄) + scheduled 행 머지 — 순수
                       #        (v2.4) 합동방송 host="group" + URL 캡처 · parse_appearance(出演情報 계열)
Dockerfile             # python:3.12-slim + gunicorn. 두 서비스가 이 이미지 공유(엔트리포인트만 다름)
deploy/                # gcloud 배포 스크립트. env.sh 는 루트 .env 매핑(gitignore)
  setup.sh deploy.sh scheduler.sh deploy_telegram.sh telegram_webhook.sh README.md
config/channels.json   # 5채널 단일 소스 (channel_order, channel_id, handle, name, name_ko)
fixtures/              # schedule.sample.json(프론트/로직 공용), rss_arale.xml(파싱 테스트)
.github/workflows/collect.yml   # v2: workflow_dispatch 전용 (정기 cron 제거됨)
data 브랜치             # schedule.json + archive.json + pending.json + control.json(v2.1)
                       #   + ingest_queue.json(v2.4 — ECHO/DRY-RUN 중 받은 트윗, 실배포 전환 시 drain)
                       #   + admin_state.json(v2.5 — pending_del/undo 슬롯). 코드 없음
```

## 명령

```bash
# 수집기 로컬 실행 (API 키 필요)
pip install -r src/collector/requirements.txt          # requests 만
DATA_DIR=./_data YOUTUBE_API_KEY=xxxx python -m src.collector.main light   # 또는 deep
# PowerShell: $env:DATA_DIR="./_data"; $env:YOUTUBE_API_KEY="xxxx"; python -m src.collector.main light

# 모듈 self-test (네트워크 불필요) — PYTHONIOENCODING=utf-8 권장(Windows 콘솔)
python -m src.collector.rss          # fixtures/rss_arale.xml 파싱, 15개 assert
python -m src.collector.youtube      # _video_from_item 매핑 확인
python -m src.collector.reconcile    # build_schedule 시나리오 → count=2, ['ended','removed']
python -m src.backend.statemachine   # 폴링 FSM 9 시나리오
python -m src.backend.xrelay         # (v2.3/2.4) X 스케줄 트윗 파서 — S1~S6 + merge
python -m src.backend.pending        # pending.json 헬퍼
python -m src.backend.notify         # (v2.1) diff_events 9 시나리오
python -m src.backend.control        # (v2.1) control.json 헬퍼
python -m src.backend.admin          # (v2.5) admin_state.json 헬퍼 (pending_del/undo)
python -m src.backend.telegram_app   # /list /del /undo 흐름 포함 (Flask 설치 시 라우트까지)
python -m src.backend.gh_store       # 직렬화 규칙 (실제 호출은 GH_TOKEN_TEST 있을 때만)

# v2 백엔드 배포 (gcloud 로그인 + deploy/env.sh 필요. 상세: deploy/README.md)
bash deploy/setup.sh          # API·SA·IAM·Cloud Tasks 큐·Secret (멱등)
bash deploy/deploy.sh         # mewtype-backend 재배포 → SERVICE_URL 확정
bash deploy/scheduler.sh      # mewtype-light / mewtype-baseline 스케줄러 잡
bash deploy/deploy_telegram.sh && bash deploy/telegram_webhook.sh   # (v2.1) webhook 서비스

# 프론트 로컬 (저장소 루트에서 — fixture 상대경로 유지 위해)
python -m http.server 8099           # http://localhost:8099/src/frontend/
# 개발 중엔 src/frontend/js/config.js 의 DATA_URL 을 ../../fixtures/schedule.sample.json 으로 교체
```

테스트 프레임워크 없음. 각 collector 모듈의 `if __name__ == "__main__":` 블록이 스모크 테스트.

## 아키텍처 핵심

### 데이터 흐름 (v2 — 상세는 `docs/SPEC.md` §8)
1. **Cloud Scheduler** 가 `POST /tick` (baseline JST 06:00 / light 매 3h) 을 OIDC 로 호출.
   `/tick` = RSS + `videos.list` 배치 1회 → `schedule.json` 재구성 + `pending.json` 갱신.
2. 각 예정 방송마다 **Cloud Tasks** 에 `scheduled_start − 15분` 시각으로 wake 태스크 1개 enqueue.
   도달 시 `POST /wake {video_id}` → 라이브 여부 확인 → 다음 체크 재예약 (pre-live 3분 / live-watch 30분).
   Cloud Tasks 상한 720h — 장기 예약은 `now+696h` 로 클램프해 롱폴링.
3. Cloud Run 이 변경분만 **GitHub Contents API**(fine-grained PAT, Secret Manager)로 `data` 브랜치 커밋.
4. **프론트**는 `raw.githubusercontent.com/.../data/schedule.json` 을 75초마다 fetch (v1 과 동일, 무변경).
   raw CDN 캐시로 최대 ~5분 지연 — 3시간 단위 예고엔 문제 없음(의도된 트레이드오프).
5. **(v2.1)** `/tick`·`/wake` 진입 시 `control.json` 확인 — `paused` 면 healthcheck 핑만 하고 no-op.
   상태 전이(upcoming/live 시작·종료, fallback, 오류)는 Telegram DM 으로 알림. `/status /pause /resume`
   명령은 공개 서비스 `mewtype-telegram` 이 처리. 상세는 `docs/SPEC.md` §10.
6. **(v2.3)** X 예고 릴레이 — 폰(Automate)이 `@BDP_yumemita` 일일 스케줄 트윗의 삼성 브라우저
   웹푸시 알림 텍스트를 `mewtype-telegram` 공개 `POST /ingest`(`X-Ingest-Secret` 헤더)로 보낸다.
   `xrelay.parse_bdp_schedule` → `schedule.json` 에 `status:"scheduled"` 행(YouTube 영상 아직
   없는 최하 단계, `video_id` 없음). 정기 `/tick` 의 reconcile 이 보존하다가 실물 `upcoming`/`live`
   가 같은 채널에 ±4h 안에 뜨면 supersede, `expires_at`(start+3h) 도달 시 제거. Cloud Tasks/
   `pending.json` 은 안 탄다. `INGEST_DRY_RUN=1` 이면 저장 없이 DM 회신만. `INGEST_ECHO=1` 이면
   파싱조차 안 하고 받은 텍스트만 DM 회신(임시 테스트 훅) + 로그에 잘림 계측(`tail_ok`).
   ECHO/DRY-RUN 중 온 스케줄 트윗은 `ingest_queue.json` 에 적재됐다가 실배포 전환
   (`INGEST_ECHO=0`+`INGEST_DRY_RUN=0`) 후 첫 `/ingest` 에서 drain 돼 반영된다. 상세는 `docs/plan/v2_3_x_relay.md`.
7. **(v2.4)** 합동방송(5인 공동명의 公式 채널) — `xrelay` 가 `kind=="collab"` 행에 `host="group"`
   + 트윗의 온전한 영상 URL 을 채운다. `render.js` 가 참여 멤버 전원(`channel_key` ∪ `collab_with`)
   레인에 같은 `.card--collab` 카드를 팬아웃(PC 5열 그리드·모바일 캐러셀 레이아웃 무변경).
   `reconcile` 은 `host` 있는 행을 멤버 개인 실물로 supersede 안 함. 상세는 `docs/plan/v2_4_collab.md`.

### 수집 로직 (`main.py` → `reconcile.build_schedule`)
- **후보 집합** = RSS로 발견한 최근 videoId ∪ 이전 `schedule.json`의 미해결(upcoming/live) videoId
  ∪ (deep 모드면) `search.list?eventType=upcoming` 결과.
- `videos.list` 로 일괄 enrich → `snippet.liveBroadcastContent` 로 분기:
  `upcoming`/`live` 는 `schedule.json` 에 유지, `none` 은 이전에 추적 중이었으면 `archive.json` 으로
  이관(`ended`/`canceled`), 후보에서 아예 사라졌으면 `removed`.
- `schedule.json` 정렬: `live` 우선 → `scheduled_start` 오름차순.
- 시각은 전부 UTC ISO(`Z`)로 저장, KST 변환은 **프론트 `time.js` 담당**.

### 계약 (변경 시 `docs/SPEC.md` 먼저 수정)
- `schedule.json` / `archive.json` 스키마: `docs/SPEC.md` §1, §2. `scheduled` 행: §1-1.
- `pending.json` 스키마 (계약 E): `docs/SPEC.md` §5.
- `control.json` 스키마 (계약 F): `docs/SPEC.md` §6.
- 프론트 DOM 구조·class 이름: `docs/SPEC.md` §3. `render.js` 가 생성하고 `css/` 가 스타일링.
  데이터는 `textContent`/`createElement` 로만 주입(XSS 방어), `innerHTML` 금지.
- 시간 표기 규칙(`formatKST`, `relativeLabel`): `docs/SPEC.md` §4.
- JSON 직렬화는 전 모듈 공통: `json.dumps(sort_keys=True, indent=2, ensure_ascii=False)` + 끝 개행 1개
  (`store.save_json_if_changed` / `gh_store._serialize`). 어겨지면 불필요한 커밋 발생.

## 주의점

- **채널 추가/변경은 `config/channels.json` 한 곳만** 고치면 된다. `channel_url` 은 `@{handle}` 로 코드에서 파생.
- 준영구 "대기소/프리챗/굿즈안내" 프레임(예: `liveBroadcastContent=upcoming` 인데 `scheduled_start` 가
  1~2년 뒤)이 `schedule.json` 에 섞여 들어온다. 현재는 필터 없이 노출(보류 결정). 거를 거면 reconcile 단계에서.
  v2 에서는 이런 장기 예약도 `pending.json` 에 들어가며, Cloud Tasks 720h 상한 때문에 `now+696h`
  로 클램프돼 사실상 월 1회 롱폴링된다 (`statemachine._bound_schedule_time`, section 3.5 힐링).
- **Cloud Run/Scheduler/Tasks 는 같은 리전**(`asia-northeast1`) 이어야 함. OIDC audience = 서비스
  `status.url` (배포마다 `SERVICE_URL` env 재설정). `mewtype-telegram` 은 INVOKER_SA 로 실행해야
  `/resume` 의 메인 `/tick` 호출이 통과 (메인 `oidc.verify_request` 가 caller email 검사).
- gcloud `--args` 는 값이 `-` 로 시작하면 `--args=...` 형태로 붙여야 함 (공백 쓰면 플래그로 오인).
- (v1 break-glass) GitHub Actions cron 은 정각 보장 안 됨(3~15분, 드물게 1h 지연/누락).
  `date -u +%H` 는 `08`/`09` 를 8진수로 파싱하므로 산술 시 `$(( 10#$H ... ))` 필수.
- 코드 주석·문서·커밋 메시지는 한국어.
