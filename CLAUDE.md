# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트

夢限大みゅーたいぷ(무겐다이 뮤타입) 소속 유튜브 방송인 5명의 **예약 방송·라이브 상태**를 취합해
보여주는 반응형 정적 웹사이트. 팬이 사이트에 방문하면 누가 언제 방송하는지, 지금 라이브 중인지,
어느 주소로 가면 되는지 한눈에 확인한다.

**현재 버전 = v4.9.5 (일반 패치, 2026-10-28)** — `README.md` 「현재 버전」 줄과 같다. 버전마다 git 태그 `vX.Y.Z`
(`git describe --tags`). 버전별로 무엇이 바뀌었는지 · 배포 리비전 · 롤백 대상은 **`docs/VERSION.md`**(맨 위 태그 대조표 + 버전별 상세)가 정본이다 —
이 파일에는 버전 이력을 쌓지 않는다(아래 「버전 올릴 때 할 일」).

## Claude 작업 원칙 (2026-09-17 확정)

사용자는 이 시점부터 **코드 리뷰를 전적으로 Claude에 위임**했다 — 직접 코드를 읽는 대신,
Claude가 만드는 이해용 산출물(팜플렛 HTML·다이어그램·아키텍처 요약·이 파일 포함)을 통해
시스템을 파악하고 다음 작업 방향을 정한다. 따라서 이런 문서가 사용자의 **유일한 진실 소스**다.

- **이해용 문서에 실제 코드 동작과 다른 내용을 쓰면 안 된다.** 기억·추측으로 "아마 이럴
  것이다"를 채우지 말 것 — 반드시 현재 코드를 직접 읽어(Read/Grep) 확인한 뒤 작성한다.
  가능하면 실제로 동작시켜 검증한다(예: `docs/v3_pamphlet.html`(devpapers) v3.6 다이어그램은
  브라우저로 렌더링·탭 전환까지 직접 확인 후 게시 — 이 수준이 최저 기준선).
- **애매하거나 확인이 안 되는 부분은 상의 없이 임의로 넘겨짚지 않는다.** 불확실하면 질문하거나
  "확인 필요"로 명시해 둔다.
- **용어는 `docs/TERMINOLOGY.md` 기준을 따른다.** 코드/문서 간 표현이 갈리면 그 문서를
  기준으로 맞추고, 거기 없는 새 용어가 필요하면 **쓰되 그 자리에서 뜻을 함께 적는다**(2026-10-19 운영자 확정) —
  괄호로 풀이하거나 「OOO*」 로 쓰고 아래에 「* OOO = 한 줄 설명」 을 단다. 설명 없이 새 이름을 정해 쓰지 않는다
  (이름을 설명 없이 정해 놓고 넘어간 일이 있었다 — 「토픽 채널」 → 운영자가 「뮤타입 음원 채널」 로 확정). 쓴 용어는 `docs/TERMINOLOGY.md` 에 올려 둔다.
- **이 파일(`CLAUDE.md`) 자체도 코드 변경 시 같이 갱신** — 오래된 서술이 남으면 그 자체가 사용자를
  오도하는 이해용 문서가 된다. 단, 기능 · 버전의 세부는 여기 말고 `docs/SPEC.md` · `docs/VERSION.md` 에 쓴다.

틀린 문서는 문서가 없는 것보다 위험하다 — 사용자의 정신모델이 실제 시스템과 어긋나게 만들고,
정작 해결하려던 "이해 병목"을 더 위험한 형태로 재생산한다.

## 문서 지도 — 무엇을 어디서 찾나

`main` 의 `docs/` 에는 개발 중 상시 보는 것만 둔다. 나머지는 **`devpapers` 브랜치**(코드 없음, Vercel 배포 트리거 밖 — 「docs 브랜치」라 부르지 말 것)에 있다.
devpapers 문서는 `git show origin/devpapers:docs/ARCHITECTURE.md` 로 읽거나, 워크트리 `../mewtype-scheduler-worktrees/devpapers` 에서 연다.
문서 · 주석의 `docs/xxx` · `ref/xxx` 표기는 어느 브랜치 것이든 그대로 유효하다.

| 찾는 것 | 위치 |
|---|---|
| 현행 구현 명세 — 계약 A~J(데이터 스키마) · 백엔드 모듈(§8) · 프론트 모듈(§9) · 인프라(§12) | `docs/SPEC.md` (main) |
| 용어 기준 | `docs/TERMINOLOGY.md` (main) |
| 버전별 변경 · 태그 대조표 · 배포 리비전 · 롤백 | `docs/VERSION.md` (main) |
| `/ingest` 분기 흐름(소식 · 스케줄 · 개인 트윗) | `docs/INGEST_FLOW.md` (main) |
| 폰 Automate 배선 · v4 한눈에 보기 | `docs/v4_AUTOMATE_WIRE.md` · `docs/v4_PAMPHLET.html` (main) |
| 에러 버스 봉투 스키마 · 예시(발신기 self-test 가 읽음) | `docs/bus/` (main) |
| 전체 흐름(박스별 설명) · 운영자용 스케줄 요약 | `docs/ARCHITECTURE.md` · `docs/SCHEDULE.md` (devpapers) |
| 폰 Automate 수식 작성법(`contains` · `++` · `nx` 키 등) — Expression 을 고치기 전에 먼저 | `docs/AUTOMATE_MANUAL.md` (devpapers) |
| 요구사항 · 인터뷰 원본 | `docs/beta_version/PRD.md` · `INTERVIEW*.md` (devpapers) |
| v3 설계 · 전환 런북 · 결정 로그 | `docs/plan/v3_*.md` (devpapers) — `v3_golive.md` = 전환 · 롤백 런북 |
| v4a(→ v4.0) 설계 · 결정 D1~D34 · 검증 · 남은 실측 확인 | `ref/v4a/` (devpapers) — `v4a_decisions.md` · `v4a_impl_plan.md` · `v4a_pending_checks.md` · `v4_release_plan.md` |
| v1 · v2 시절 명세 · 기능별 설계(X 릴레이 · 합동 · 소식 · 개인 트윗 …) | `docs/old/v1/` · `docs/old/v2/` (devpapers) |
| 이 파일의 2026-10-26 정리 전 원본(버전별 서술 · v4a 세부 전부) | `docs/old/CLAUDE_md_v4.8.5.md` (devpapers) |
| 작업 기록 · 설계 메모 · 실험 자료 · 목업 · 캡처 | `ref/` (devpapers) |

- **`ref/` 는 `devpapers` 에서만 관리한다** (2026-10-20 사용자 확정) — `main` 에는 두지 않는다. 새 자료는 devpapers 워크트리의 `ref/` 에 넣어 커밋한다.
- `scripts/build_songs_json.py` 의 입력 `ref/player/songs_release.json` 도 devpapers 에 있으니 돌릴 땐 먼저 꺼내 둔다
  (`git show origin/devpapers:ref/player/songs_release.json > ref/player/songs_release.json`).

## 인프라

서버 상시 가동 없음. 무료 인프라만 사용. 리전 `asia-northeast1`(Cloud Run · Scheduler · Tasks 는 같은 리전이어야 함).

- **Cloud Run 2서비스**(같은 이미지, 엔트리포인트만 다름):
  - `mewtype-backend`(쓰기 서비스, `concurrency=1 · max-instances=1` — data 쓰기 직렬화) — `/tick` `/wake` `/write` `/monitor` `/websub-renew` `/daily`.
  - `mewtype-telegram`(접수 서비스, 공개) — 텔레그램 webhook · `POST /ingest`(폰 알림) · PubSub 콜백 `/websub/<이름>` · 관리 페이지 `/admin` · 웹 모니터 `/monitor-live` · 상시 조사 `/gap-check` · 보충 작업 `/gap-fill`(둘은 OIDC 강제 검증).
    콘텐츠 쓰기는 직접 하지 않고 백엔드 `/write` 로 보낸다(`writeclient` → `writers` → `apply`).
- **Cloud Scheduler 3잡**(v4.9.0 — 옛 4잡을 줄였다): light 10분 → 쓰기 `/tick` · **daily** KST 06:00 → 쓰기 `/daily`(baseline tick + 그날 06:10 `/monitor` · 06:20 `/websub-renew` 을 Cloud Tasks 로 먼저 예약) · **gapcheck** 매분 → 접수 `/gap-check`(상시 조사). 운영 잡 이름 `mewtype-light` · `mewtype-daily` · `mewtype-gapcheck`.
- **Cloud Tasks**: 방송별 정밀 `/wake {video_id}`(큐 `mewtype-wake`) · PubSub 알림 전용 큐 `mewtype-websub` · 보충 작업 `/gap-fill`(큐 `mewtype-gapfill`, 동시 1 · 3회, 이름 `gapfill-<트윗 id>`) · 일일 묶음 예약 `/monitor` `/websub-renew`(큐 `mewtype-daily`, 동시 1 · 4회). 상한 720h → `now+696h` 클램프.
- **저장 = GitHub 데이터 저장소 `sbb2002/mewtype-scheduler-data`** 의 브랜치들(Contents API, fine-grained PAT):
  `data`(팬 화면이 읽는 preview · notices · tweets · banners · songs 등) · `ops`(control · admin_state · LLM 판단 기록 등 운영 상태, `storage.OPS_PATHS`) ·
  `monitoring`(이벤트 로그 · 스냅샷 · 유실 원문 큐 · 원문 보존 `raw/`). 브랜치를 나눈 이유 = Contents API 충돌 단위가 브랜치 HEAD 라서(v3.9 유실 사고).
  Contents API 는 **1MB 넘는 파일을 못 읽는다** — 보관함(트윗 · 소식 · LLM 판단 기록)은 최근분 캐시 + 일자 파일로 나눠 매일 KST 06:10 정리한다(`archive_rotate`, SPEC §8.18).
  상한 없이 자라는 파일을 새로 만들면 같은 방식을 쓸 것.
  **코드 저장소에는 `data` 브랜치가 없다**(2026-10-20 삭제, 옛 기록 = 태그 `archive/data-2026-09-15`).
- **프론트 = Vercel 정적 호스팅**(Root Directory `src/frontend`, 빌드 없음). `main` 푸시 시 자동 배포, 다른 브랜치는 전부 제외(`src/frontend/vercel.json`).
  주소 `https://mewtype-schduler.vercel.app/` — 레포 · Vercel 프로젝트 이름은 `mewtype-scheduler` 지만 **도메인은 옛 오타 그대로**.
  데이터는 `raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/*.json` 을 75초마다 fetch(raw CDN 캐시 최대 ~5분 지연 — 의도된 트레이드오프).
  방문 통계 = Vercel Web Analytics(쿠키 없음).
- **외부 LLM = Groq**(`llm.py` 번역 · 판정, `vision.py` 비전 OCR) · 예비 OCR = Google Cloud Vision(`cloudvision.py`, 운영자 허가 시에만).
- **업스트림 시스템 = 운영자 폰 Automate** — X · YouTube 푸시 알림을 `/ingest` 로 중계(코드베이스 밖).
- 로컬 시험판: `python -m src.backend.local_runner`(저장 = 로컬 파일, `V4A_RUNTIME=local`). 스테이징 배포 = `STAGE=1 bash deploy/deploy.sh`.

## 데이터 흐름 (현행)

1. **발견** — light 틱(10분)이 멤버 개인 채널 RSS + `videos.list` 로 `preview.json` 을 다시 만든다(`handlers` → `preview_build`, FSM 은 저장 없이 `statemachine.derive` 로 파생).
   PubSub 수신은 운영 중이다(멤버 알림 → 즉시 wake, 구독은 매일 갱신). env `WEBSUB_REPLACE_RSS` 가 1 이면 light 틱이 RSS · 신곡 감지를 생략하고 일일 baseline 만 안전망으로 남는데,
   **운영값은 0 — 알림과 10분 RSS 폴링이 같이 돈다**(2026-10-26 Cloud Run `mewtype-backend-00184` env 로 확인). 1 로 바꾸려면 `deploy/env.sh` 에 넣고 재배포.
2. **상태** `none|announced|upcoming|watching|live|end`(+ 아카이브 신호 `out`). wake 간격(`statemachine.py` 상수):
   watching = 예정 20분 전부터 3분 간격 · live = 시작 후 60분까지 10분, 그 뒤 5분 · end 창 30분 동안 5분. URL 없는 예고 = 시작 +2분 `search.list` 1회, +1h 까지 못 오르면 `out`.
3. **트윗 · 알림 인입** — 폰이 `/ingest` 로 보낸 알림을 표시명으로 가른다: 공식 계정 → 일일 스케줄(예고) 또는 소식 · 개인 5인 → 개인 트윗(+ 예고 판정) ·
   게임 계정 → 행사 배너 판정. 원문은 tweet id 가 있으면 vxtwitter/fxtwitter 결과를 정본으로 쓴다. 상세 `docs/INGEST_FLOW.md` · `docs/SPEC.md` §8.11.
   **빠진 트윗 · 자기 답글**(v4.9.0): 폰이 빠뜨리거나 자기 답글은 알림이 안 오므로, 접수 서비스 `/gap-check` 가 1분마다 멤버 5명의 최근 글을 훑어 보충 작업(`/gap-fill`)으로 넣는다(일반 글은 게시 7분 뒤, 자기 답글은 바로). 자기 답글은 `reply_to_id` 로 원글에 이어 붙이고, 글타래 수명은 가장 늦은 글 + 48h. 명세 `docs/SPEC.md` 계약 I.
4. **쓰기** — 모든 콘텐츠 쓰기는 백엔드 `/write` 한 곳에서 직렬화. 외부 호출(LLM · API · OCR)은 접수 서비스에서 준비하고 `/write` 잡은 커밋만 한다.
5. **표시** — 프론트가 data 브랜치 JSON 을 폴링해 그린다. 시각은 전부 UTC ISO(`Z`) 저장, KST 변환은 프론트 `time.js` 담당.

## 현행 동작 핵심 규칙 (자주 되묻는 것 — 세부는 SPEC · `ref/v4a`)

- **그룹 영상은 근거가 있을 때만 참여 멤버에 올린다** — 근거 = 글의 정식 이름 · 인원 표현(全員 · 5名 등) · 영상 제목의 이름 · 첨부 이미지 OCR · 같은 URL 을 담은 뒤이은 공식 글.
  그룹 명의(夢限大みゅーたいぷ · #ゆめみた)만으로는 근거가 아니다. 근거가 없으면 「참여 멤버 확인 대기」(ops `group_pending.json`)에 적고 DM — 다른 인입은 막지 않는다.
- **RSS 는 멤버 개인 채널만** 돈다. 그룹 공식 채널(`config/channels.json` 의 `group`, `is_group: true`) 영상은 수집이 새로 만들지 않는다(등록된 것만 갱신).
- **그룹 채널 프리미어(노래 · MV 등 녹화본 공개)는 방송 카드로 올리지 않는다**(`preview_build.is_group_release`) — ops `video_releases.json` 에 기록만. 멤버 개인 채널 프리미어는 올린다.
- **「공식」 경로 = @BDP_yumemita 가 직접 쓴 글만**(`telegram_app._official_skip_reason`) — 리트윗 · 다른 계정 글은 건너뛴다. 게임 계정(`game_accounts`, バンドリ！アワーノーツ) 글은 행사 판정으로만.
- **같은 방송 판정 시각 창 = ±45분**(`preview.match_item` · `preview_build.SCHEDULED_SUPERSEDE_SEC`).
- **운영자 · 트윗이 정한 예정 시각은 YouTube 예약 시각이 실제로 바뀔 때만 API 를 따른다**(v4.7.2, 예고마다 `auto_edit`) — `docs/SPEC.md` 「예고 자동 수정 권한 · 운영자 지정 시각」.
- **트윗 수명 = X 게시 시각 + 48h**(`xtweet.TTL_HOURS`, 게시 시각을 모르면 받은 시각 + 48h).
- **새 LLM 판정은 근거 필수**(운영자 지시) — 원문 그대로의 근거 구절을 받고, 근거가 없거나 원문에 없으면 그 판정을 버리고 다시 묻는다.
  지금 적용된 판정: `announces_own_broadcast` · `notice_categories` · `live_info` · `banner_scope` · `banner_extract`(`participation` · `broadcast_change_targets` 는 아직 근거 검사 없음 — `reason` 만).
  자동 판단은 ops `llm_actions.json` 에 기록되고 관리 페이지에서 반려 · 재판단 · 사용자 판단할 수 있다.
- 관리는 **관리 페이지 `/admin`**(로그인 = 텔레그램 `/admin` 일회용 링크)에서. 텔레그램 명령은 `/status /pause /resume /list /admin` 만.

## 저장소 구조

이 `mewtype-scheduler/` 폴더는 상위 `pyworks` 저장소 안에 **중첩된 별도 git 저장소**다
(`origin` = `github.com/sbb2002/mewtype-scheduler`). 상위 `pyworks`와 무관하게 취급.
(2026-08-30 레포명 오타 `mewtype-schduler` → `mewtype-scheduler` 로 변경. 옛 raw URL은 404.)

모듈마다 한 줄 역할만 적는다. 계약 · 세부 동작은 `docs/SPEC.md` §8(백엔드) · §9(프론트).

```
src/
  frontend/            # Vercel Root Directory. 빌드 없음, ES 모듈. 데이터는 textContent/createElement 로만 주입(innerHTML 금지)
    index.html  monitor.html(운영 모니터, 이스터에그 진입)  vercel.json  assets/songs.json(곡 목록 시드 · 폴백)
    css/                # 각 파일 :root 토큰 = 어둡게, theme.css(맨 끝) = 밝게 값
    js/
      main.js          # 진입점 — 폴링(preview · notices · tweets · banners) + 카운트다운 틱
      config.js        # 상수 · 데이터 URL · APP_VERSION/APP_DATE(하단 ver. 말풍선)
      time.js api.js   # KST 포맷 · 상대시간 / fetch(타임아웃)
      render.js timetable.js   # 보드 — PC 오늘 타임테이블 · 카드 보기 / 모바일 오늘 카드 + 이후 예고
      notices.js banners.js tweets.js   # 소식판 · 행사 배너 · 멤버 트윗 시트
      tweetlogic.js    # 트윗 시트 순수 로직(글타래 · 글자색 · 시각 표기 · 미디어 격자 · X 카드 치수로 두 면 위치 맞추기) — DOM 없음
      player.js playerbtn.js songs.js   # YouTube 곡 플레이어(첫 클릭 때 동적 import)
      king.js          # 노노카 지각 이스터에그
      theme.js sheetdrag.js   # 밝게/어둡게 전환 · 시트/토스트 끌어 닫기
      *.selfcheck.mjs  # 순수 로직 self-check
  collector/           # v1 순수 모듈 — config · rss · youtube 를 백엔드가 import 재사용
  bus/                 # 에러 버스 발신기 — MEW_BUS_DIR 없으면 no-op(배포판은 미설정)
  backend/             # Cloud Run (Flask + gunicorn)
    app.py             # 쓰기 서비스 라우트 /tick /wake /write /monitor /websub-renew /daily
    telegram_app.py    # 접수 서비스 — webhook · /ingest 분기 · 커밋 함수들(_commit_*) · 웹 모니터
    admin_web.py admin_api.py admin_static/   # 관리 페이지(블루프린트 · API · 정적 파일)
    handlers.py        # tick/wake 오케스트레이션 → preview.json 커밋 · 번역 sweep · 신곡 감지 · 모니터 로그
    writers.py writeclient.py apply.py   # 쓰기 큐 — 잡 kind 매핑 · /write 호출(429/503 백오프) · 적용
    storage.py gh_store.py local_store.py # store 선택(로컬/GitHub, ops 라우팅) · Contents API · 로컬 파일
    preview.py preview_build.py statemachine.py   # 예고 계약 · 재구성 · FSM 파생 (순수)
    xrelay.py xnotice.py notices.py xtweet.py banners.py songs.py   # 공식 스케줄 · 소식 · 개인 트윗 · 행사 배너 · 곡 (순수 위주)
    llm.py vision.py cloudvision.py   # Groq 번역 · 판정 / Groq 비전 OCR / Cloud Vision 예비
    vxtwitter.py ytnotif.py ytdlp_probe.py websub.py   # 트윗 unfurl / YT 앱 알림 파서 / 회원 전용 라이브 조회 / PubSub 수신
    monitor_log.py monitor_snapshot.py monitor_report.py rawlog.py   # 이벤트 로그 · 일일 스냅샷 · 리포트 HTML · 원문 보존
    notify.py control.py admin.py config.py tasks.py oidc.py   # 텔레그램 알림 · control.json · admin_state.json · env · Cloud Tasks · OIDC 검증
    enrich.py jobqueue.py local_runner.py tg_poll.py flowtrace.py   # 로컬 시험판 전용(가공 큐 · 작업 큐 · 러너 · 텔레그램 폴링 · 흐름 기록)
    push_monitor.py    # 미사용 — 삭제 후보
config/channels.json   # 채널 단일 소스 — channel_order(5인) · channels(5인 + group) · song_feeds · game_accounts
deploy/                # gcloud 배포 스크립트(README.md). env.sh 는 루트 .env 매핑(gitignore)
scripts/               # 일회성 데이터 스크립트(곡 목록 생성 · 곡 미디어 적용 · 모니터 백필)
fixtures/              # self-test · 프론트 개발용 샘플
Dockerfile             # python:3.12-slim + gunicorn, 두 서비스 공유
```

## 명령

```bash
# 모듈 self-test (네트워크 불필요, 테스트 프레임워크 없음 — 각 모듈의 if __name__ == "__main__" 블록)
# Windows 콘솔은 PYTHONIOENCODING=utf-8 권장
python -m src.backend.<모듈>         # self-test 있는 모듈: src/backend 전부(app · local_runner 제외 — 서버 · 러너를 띄운다) + src.collector.rss · src.collector.youtube · src.bus.conform · src.bus.publisher
python -m src.backend.vision --live  # 실제 Groq 비전 호출(GROQ_API_KEY + fixtures/awarnoutz_cast.jpg 있을 때만)
node src/frontend/js/<이름>.selfcheck.mjs   # 프론트 순수 로직(king · render · songs · time · timetable · tweetlogic)

# 백엔드 배포 (gcloud 로그인 + deploy/env.sh 필요. 상세: deploy/README.md) — 배포는 운영자 결정
bash deploy/setup.sh          # API·SA·IAM·Cloud Tasks 큐·Secret (멱등)
bash deploy/deploy.sh         # mewtype-backend
bash deploy/deploy_telegram.sh && bash deploy/telegram_webhook.sh   # mewtype-telegram
bash deploy/scheduler.sh      # 스케줄러 3잡(light · daily · gapcheck) — KST 05:50~06:30 에는 거부, STAGE=1 이면 아무것도 안 함 (URL 불변이면 생략 가능)
# writers.py · telegram_app.py 등 두 서비스 공통 코드를 바꾸면 deploy.sh + deploy_telegram.sh 둘 다

# 프론트 로컬 (저장소 루트에서 — fixture 상대경로 유지 위해)
python -m http.server 8099           # http://localhost:8099/src/frontend/
# fixture 로 보려면 src/frontend/js/config.js 의 PREVIEW_URL 을 주석 처리된 fixture 줄로 교체
```

## 주의점

- **계약을 바꿀 땐 `docs/SPEC.md` 먼저** — 데이터 스키마(계약 A′~J) · 프론트 DOM 구조와 class 이름 · 시간 표기 규칙.
- **JSON 직렬화는 전 모듈 공통**: `json.dumps(sort_keys=True, indent=2, ensure_ascii=False)` + 끝 개행 1개(`gh_store._serialize`). 어기면 불필요한 커밋이 생긴다.
- **채널 추가/변경은 `config/channels.json` 한 곳만** 고치면 된다. `channel_url` 은 `@{handle}` 로 코드에서 파생.
- **`vercel.json` 은 반드시 `src/frontend/vercel.json`** (Vercel Root Directory). 루트에 두면 Vercel 이 못 읽어, 봇 커밋마다 배포 시도가 생겨 Hobby 「하루 100회」 한도를
  다 쓰고 `main` 배포까지 막힌 사고가 있었다(버그리포트 20260913 #5). 배포 상태 확인은 `vercel ls --token=$VERCEL_TOKEN` · REST `GET /v9/projects/{id}`
  (CLI `whoami`/`inspect`/`logs` 는 이 토큰에서 "User not found" 로 죽는다).
- **준영구 「대기소 · 프리챗 · 굿즈안내」 프레임**(`upcoming` 인데 예정 시각이 1~2년 뒤)이 섞여 들어온다 — 필터 없이 노출(보류 결정). 그래서 날짜 표기에 연도를 생략하지 않는다.
- **폰 알림 원문은 조용히 잘릴 수 있다** — Automate 리스너가 축약본(`contentText`)만 넘기면 말줄임표 없이 완결된 문장처럼 잘려 온다(버그리포트 20260913 #2).
  그래서 tweet id 가 있으면 vxtwitter 결과를 정본으로 쓴다(`telegram_app._recover_raw_via_vxtwitter`, SPEC §8.6). vxtwitter 가 죽으면 잘림이 재발할 수 있다.
- **OIDC**: audience = 서비스 `status.url`. `mewtype-telegram` 은 INVOKER_SA 로 실행해야 메인 `/tick` 호출이 통과한다.
  gcloud `--args` 는 값이 `-` 로 시작하면 `--args=...` 형태로 붙인다.
- **Claude 가 운영 사이트를 브라우저로 열 때는 주소에 `?va=claude` 를 붙인다** (2026-10-19 사용자 요청) — 그 탭은 방문 통계에서 빠진다(탭 단위, 새 탭마다 다시).
  curl · WebFetch · 로컬 서버는 해당 없음.
- 코드 주석·문서·커밋 메시지는 한국어.
- **병합 · 배포는 운영자 결정** — 커밋 · 브랜치 푸시 · PR 생성까지만 하고, 병합 · 배포는 지시가 있을 때만.

### 버전 번호

- **등급 (2026-10-27 사용자 확정)**: `vX.Y.Z` = **메이저 · 마이너 · 일반 패치**.
  - **일반 패치(Z)** — 버그 수정 · 작은 조정. **핫픽스는 일반 패치에 속한다.** `main` 의 가장 최근 X.Y 에 이어 붙인다(2026-10-22 — v4.6.0 뒤 = v4.6.1).
  - **마이너(Y)** — **새 요소가 추가되는** 변경(새 화면 부품 · 새 기능). 버그를 고치려다 새 요소가 들어가도 마이너(첫 적용 = 자기 답글 보충 + 트윗 시트, 2026-10-27).
  - **메이저(X)** — **대규모 변화(인프라 포함)**.
  - 등급이 애매하면 Claude 가 근거를 들어 제안하고 운영자가 정한다. 그 전 규칙(핫픽스 = Z · 기능 = Y, 옛 마이너 줄기에 잇기 — v3.8.10 · v4.5.6~v4.5.11)으로 붙인 번호 · 태그는 그대로 둔다.
- **알파벳 접미사 `vX.Y.Z[a-z]` 는 같은 패치 번호에서 갈라진 후속이 생겼을 때만**(2026-09-23 · 09-25 확정). 단순한 다음 일반 패치엔 붙이지 않는다.
  커밋 메시지(`fix(v3.8.9a): …`) · PR 제목 · 주석 · 문서 모두 같은 표기, 「vX.Y.Z 후속」 같은 표기를 만들지 말 것. 이미 머지된 커밋 메시지는 그대로 둔다.
- **브랜치 이름에는 버전 번호를 쓰지 않는다**(2026-10-17): 테스트 = `test/<이름>`, 핫픽스 = `hotfix/<이름>`. 번호 등급은 브랜치 접두사가 아니라 **들어간 내용**으로 정한다(위 등급) — `hotfix/` 로 시작했어도 새 요소가 들어가면 마이너.

### 버전 올릴 때 할 일 (2026-10-20 사용자 확정)

새 번호가 `main` 에 들어가면 **빠짐없이** 아래를 같이 한다. 병합을 맡은 쪽(운영자 또는 병합을 지시받은 세션)이 같은 자리에서 끝낸다.

0. **병합 전 — 묻힌 수정 확인**(2026-10-24): `gh pr list --state open` · `git branch -r --no-merged origin/main | grep -E 'hotfix/|feat/'` 로
   열린 PR · 병합 안 된 브랜치를 보고 운영자에게 알린다(병합할지 · 버릴지는 운영자 결정). 계기: PR #83 · `hotfix/live-name-solo` 가 묻힌 채 v4.7.1 · v4.7.2 가 배포됐다.
1. **git 태그** — 그 버전이 `main` 에 들어온 **병합 커밋**에 주석 태그를 붙여 **이름을 지정해** 푸시:
   `git tag -a v4.6.1 <병합 커밋> -m "v4.6.1" -m "<VERSION.md 그 버전 첫 줄>"` → `git push origin refs/tags/v4.6.1`.
   `git push --tags` 금지(로컬 실험 태그까지 올라간다). 여러 번에 나뉘어 들어왔으면 마지막 코드 병합, 한 병합에 두 버전이 섞였으면 앞 버전은 브랜치 안의 그 커밋.
   병합 뒤 「배포 완료 표기」 docs 커밋은 기준이 아니다.
2. **`docs/VERSION.md` 맨 위 「버전 태그 대조표」 맨 위에 한 줄** — `| vX.Y.Z | \`병합 커밋 7자리\` | 시각(KST) | \`들어온 브랜치\` | 병합 커밋 | 판단 메모 |`.
   해시는 병합 뒤에야 생기므로 태그 직후 「배포 완료 표기」 docs 커밋과 같이 넣는다.
3. **`README.md` 「현재 버전」 줄**(+ 기능 표 · 구조 설명이 바뀌었으면 같이).
4. **이 파일 맨 위 「현재 버전」 줄만** 새 번호 · 날짜로. 버전 항목은 여기 쓰지 않는다(2026-10-26 — 전엔 여기 버전마다 항목을 쌓아 978줄이 됐다).
5. **`docs/VERSION.md` 「버전별 상세」** 항목(머지 커밋 · 배포 리비전 · 롤백 대상 · 미확인 사항 포함).
6. **`src/frontend/js/config.js` 의 `APP_VERSION` · `APP_DATE`** — 4 번과 같은 번호 · 날짜.

### 로컬 워크트리 배치 (2026-10-20 사용자 확정, 여러 PC 공통)

- 메인 저장소(`mewtype-scheduler/`)는 제자리에서 **`main`** 을 체크아웃한다(한 브랜치는 한 폴더에서만 열 수 있다).
- 그 밖의 브랜치는 형제 폴더 `mewtype-scheduler-worktrees/<큰 버전>/<브랜치 이름에서 / 를 - 로>`:
  `git worktree add ../mewtype-scheduler-worktrees/v4/hotfix-xxx hotfix/xxx`. 접두사는 브랜치 것 그대로(`feat-` · `hotfix-` · `test-` · `docs-` · `deprecated-`).
  큰 버전 = 들어갈 줄기(지금 `main` = v4). `devpapers` 는 `mewtype-scheduler-worktrees/devpapers`.
- `.agents/` · `.claude/` · `skills-lock.json`(운영자 PC 의 Claude 스킬 설치분)은 `.gitignore` 로 뺀다.
- 병합이 끝난 워크트리는 지운다(`git worktree remove`).
