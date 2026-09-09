# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트

夢限大みゅーたいぷ(무겐다이 뮤타입) 소속 유튜브 방송인 5명의 **예약 방송·라이브 상태**를 취합해
보여주는 반응형 정적 웹사이트. 팬이 사이트에 방문하면 누가 언제 방송하는지, 지금 라이브 중인지,
어느 주소로 가면 되는지 한눈에 확인한다.

- 요구사항·설계 배경: `docs/beta_version/PRD.md`, 인터뷰 원본 `docs/beta_version/INTERVIEW*.md`
- **용어 기준 (세션 간 표현 일관성): `docs/TERMINOLOGY.md`** — 프론트엔드/백엔드/업스트림 시스템/외부 LLM 등.
  표현이 엇갈리면 여기에 추가.
- **현행 구현 명세 (계약 A~I, 백엔드·프론트 모듈): `docs/SPEC.md`** — v3 기준.
  원본 `docs/old/v1/IMPLEMENTATION.md`, `docs/old/v2/IMPLEMENTATION_v2{,.1}.md`
- **현행 전체 흐름 (박스별 설명 + 그림): `docs/ARCHITECTURE.md`** + `docs/v2_4_flow.png`
- 백엔드 스케줄(운영자 시점 요약): `docs/SCHEDULE.md`. 아키텍처 구상도: `docs/old/v2/v1_impro_final.md`

> **현행 = v3.0** (배포 2026-09-09). 아래 저장소 구조·데이터 흐름 서술은 v2 계보를 담고
> 있고, v3 델타는 아래 상자 + `docs/plan/v3_*.md` 에 있다. 새 작업은 v3 기준으로.
>
> **v3.0 델타 (요약)** — 상세: `docs/plan/v3_backend_surgery.md`(기능), `docs/plan/v3_impl_spec.md`
> (코드 WP), `docs/plan/v3_golive.md`(전환·롤백 런북), `docs/plan/v3_draft.md`(결정 로그):
> - `schedule.json` → **`preview.json`** (계약 A′), `archive.json` → `preview_archive.json`.
>   상태 `none|announced|upcoming|watching|live|end` **6상태** (기존 `scheduled`→`announced`).
> - **`pending.json` 폐지** — FSM 은 preview 아이템에서 파생(`statemachine.py` 재작성, 저장 타이머 없음).
> - 새 모듈: `preview.py`(계약)·`preview_build.py`(reconcile 포크)·`llm.py`(Groq 번역/제목추출)·
>   `ytnotif.py`(YT 앱 알림 파서, `INGEST_YT_ENABLED` 뒤)·`vxtwitter.py`(트윗 unfurl).
> - **외부 LLM(Groq `gpt-oss-120b`/폴백 `gpt-oss-20b`)**: 소식 제목추출(json_schema strict)·개인
>   트윗 번역. 결과는 `notices.json` `title_ko` / `tweets.json` `text_ko` 에 원문과 함께 저장.
>   실패 행은 `needs_tl:true` → 다음 tick 재시도. `GROQ_API_KEY` Secret.
> - **예고 머지 모델** = 소스 신뢰도 티어(1 API / 2 명시값 / 3 파생값). 높은 티어 승, 동일 티어 안 최신순.
> - 텔레그램 명령 `{cmd}×{contents}` 격자 (`/list /ingest /edit /del /undo /translate × preview|notice|tweet`).
> - 업스트림 Automate 플로우 v3: 패키지별 리스너 2개(삼성 인터넷 + YouTube) + Fork. `docs/AUTOMATE_MANUAL.md §4b`.
> - 데이터는 **콜드 스타트** — v2 파일은 `data:.old/`, 마이그레이션 스크립트 없음.
- 그림: `docs/old/v2/v2_1_telegram.png` (v2.1)
- **v2.3 (X 예고 릴레이 → `scheduled`)**: `docs/old/v2/v2_3_x_relay.md`, 핸드오프 `docs/old/v2/v2_3_handoff.md`
- **업스트림 시스템(운영자 폰 Automate) 수식 작성 참고: `docs/AUTOMATE_MANUAL.md`** — 알림 중계
  플로우의 Expression 을 만들거나 고칠 때 먼저 볼 것 (`find` 없음·`contains` 사용·`++` 연결·`nx` 키 등)
- **v2.4 (합동방송 → 참여 멤버 레인 중복 · ingest 큐)**: `docs/old/v2/v2_4_collab.md`,
  **실배포 전환 런북 `docs/old/v2/v2_4_golive.md`**
- **v2.5 (텔레그램 수동 관리 명령 `/list` `/del` `/ingest` `/undo`)**: `docs/old/v2/v2_5_admin_commands.md`
- **v2.7 (소식 게시판 — 방송 외 이벤트 티커. 구현 완료)**: `docs/old/v2/v2_7_notice_board.md`
  + UI 목업 `docs/old/v2/v2_7_notice_board_mockup.html`
- **현행 ingest 신호 처리 흐름: `docs/INGEST_FLOW.md`** — `POST /ingest` 가 들어온 텍스트를
  소식·스케줄·개인트윗으로 분기하는 경로 (mermaid 흐름도)
- **v2.8 (멤버 개인 트윗 — 예고판 상단 편지 배지)**: `docs/old/v2/v2_8_personal_tweets.md`

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
    index.html         # #notice(v2.7 소식) + #board + #foot 스켈레톤, <script type="module">
    css/{reset,layout,card,notices,tweets}.css
    js/                # ES 모듈, 상대 import
      config.js        # 상수 (DATA_URL, NOTICES_URL, TWEETS_URL, 폴링 주기, 폴백 채널 메타)
      time.js          # UTC→KST 포맷, 상대시간 라벨 — 순수 함수
      api.js           # fetchSchedule(url): AbortController 타임아웃, {ok,data|error} (notices 도 재사용)
      render.js        # renderBoard / renderFooter / updateCountdowns
      notices.js       # (v2.7) renderNotices(#notice, data) — 소식 티커 (접힘/펼침/5초 순환/램프/marquee)
      tweets.js        # (v2.8) renderTweets/reapplyTweets — 유닛 아바타 편지 배지 + PC 말풍선 / 모바일 토스트
      main.js          # DOMContentLoaded → poll(스케줄) + pollNotices + pollTweets + 카운트다운 틱
  collector/           # v1 순수 모듈 — v2 백엔드가 import 재사용. main.py 는 break-glass 전용
    main.py            # v1 오케스트레이션 (python -m src.collector.main [light|deep])
    config.py          # config/channels.json + YOUTUBE_API_KEY 로드
    rss.py             # 채널 RSS → videoId 발견 (쿼터 0)
    youtube.py         # YouTube Data API v3 (videos.list / search.list), VideoInfo
    reconcile.py       # 상태 판정 + 이전 스냅샷 대비 diff — 순수 함수
    store.py           # schedule.json / archive.json 로드·저장 (변경 시에만 기록)
  backend/             # Cloud Run 서비스 (Flask + gunicorn). v3.0.
    app.py             # 메인 라우트 /tick(Scheduler) /wake(Cloud Tasks) · `/` 헬스체크(GFE 가 /healthz 가로챔)
    handlers.py        # (v3) tick/wake → preview_build → preview.json 커밋 + LLM 말단 번역(needs_tl sweep)
    preview.py         # (v3) preview.json 계약 A′ — make_item/match_item/sort/promote_state (순수)
    preview_build.py   # (v3) reconcile 포크 → 6상태 preview 재구성 (순수)
    statemachine.py    # (v3) FSM 파생 — derive(item, now) → (next_state, next_check_at, log). 저장 안 함
    llm.py             # (v3) Groq 클라이언트 — notice_title(json_schema strict) / translate. 실패 시 None
    ytnotif.py         # (v3) YouTube 앱 푸시알림 파서 (`chime.*` 키). INGEST_YT_ENABLED 뒤
    vxtwitter.py       # (v3) 트윗 unfurl — 잘린 URL·이미지 복원 (api.vxtwitter.com)
    #  (삭제됨) pending.py — v3 는 FSM 을 preview 아이템에서 파생하므로 불필요
    gh_store.py        # GitHub Contents API read/write (직렬화 규칙 store.py 와 동일)
    tasks.py           # Cloud Tasks enqueue (OIDC 타깃, 720h 상한 클램프)
    oidc.py            # Scheduler/Tasks OIDC bearer 토큰 검증
    config.py          # 환경변수 → Config
    notify.py          # (v2.1) Telegram 알림 + diff_events(A~F). (v2.8.2) allows(level,kind) —
                       #        simple=upcoming·live / normal=+scheduled·notice·tweet / detail=+ingest·fallback·요약
    control.py         # (v2.1) control.json 스키마 (paused)
    telegram_app.py    # (v2.1) 공개 webhook 서비스 — 엔트리포인트 src.backend.telegram_app:app.
                       #        (v2.3) POST /ingest — 업스트림 시스템(운영자 폰 Automate)이 X 알림 텍스트를 중계
                       #        (v2.5) /list /del /ingest(=/add) /undo — 텔레그램 수동 관리 명령
    admin.py           # (v2.5) admin_state.json 스키마 (pending_del/ingest/notice/undo 슬롯, undo.path) — 순수
                       #        (v2.7.x) pending_notice_edit 슬롯 — /notice-edit 마법사(title→date→url 단계·new 누적)
                       #        (v2.8.1+) pending_member 슬롯 — 수동 /ingest 개인 예고 채널 미상 시 유닛 되묻기(raw 저장)
    xnotice.py         # (v2.7) 방송 외 이벤트 트윗 → notices 항목 파서 + 카테고리/anchor — 순수
                       #        (v2.7.x) _headline: _join_shout_titles(💪…💪·／…＼ 여러 줄 병합) + 라벨/스트리밍나열 감점
                       #                 + _TITLE_NOUN(最終回) 가점 + _MID_DECO 이모지 제거. _DATE_RE 명시 연도 캡처.
                       #                 _RE_RETRO(今日は何の日/N年前) → is_recap → 지난 날짜 소식 skip
    notices.py         # (v2.7) notices.json/notice_archive.json 계약 + 중복판정·머지·수명 sweep — 순수
                       #        (v2.7.x) edit_notice(prev,nid,patch,now) — /notice-edit 수동 필드 수정 (id/seen_ids 보존)
    xrelay.py          # (v2.3) X 예고 트윗 파서(@BDP_yumemita 일일 스케줄) + scheduled 행 머지 — 순수
                       #        (v2.4/2.6) 합동방송 kind="collab" + URL→video_id · parse_appearance(出演情報)
                       #        (v2.5.1) unparsed_lines(인식 실패 줄) · (v2.6) _SKIP_LINE_RE(全員/비-YT)
    xtweet.py          # (v2.8) android.title 라우팅(route_by_title) + tweets.json/tweet_archive.json
                       #        계약(parse·merge_tweet·sweep_expired) — 순수. 개인 5인 트윗 전용 파이프라인
                       #        (v2.8.1) parse_schedule(예고 게이트) · merge_personal_schedule(같은 방송 upsert)
                       #        · apply_overrides(handlers 후처리 — 트윗 시각이 API 재구성을 override)
                       #        (v2.8.1+) 수동 /ingest 도 개인 예고 폴백 — 본문 YT URL→videos.list(quota 1)로
                       #        채널 판별, 실패 시 텔레그램에서 유닛 되묻기 (telegram_app._try_personal_ingest)
Dockerfile             # python:3.12-slim + gunicorn. 두 서비스가 이 이미지 공유(엔트리포인트만 다름)
deploy/                # gcloud 배포 스크립트. env.sh 는 루트 .env 매핑(gitignore)
  setup.sh deploy.sh scheduler.sh deploy_telegram.sh telegram_webhook.sh README.md
config/channels.json   # 5채널 단일 소스 (channel_order, channel_id, handle, name, name_ko)
fixtures/              # schedule.sample.json(프론트/로직 공용), rss_arale.xml(파싱 테스트)
.github/workflows/collect.yml   # v2: workflow_dispatch 전용 (정기 cron 제거됨)
data 브랜치 (v3)        # preview.json + preview_archive.json + control.json
                       #   + notices.json / notice_archive.json (소식, +title_ko)
                       #   + tweets.json / tweet_archive.json (개인 트윗, +text_ko)
                       #   + admin_state.json (계약 G′ — pending_op/edit_lock/suppress/undo 슬롯)
                       #   .old/ = 전환 시 치워둔 v2 파일(schedule/pending/ingest_queue …). 롤백용. 코드 없음
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
python -m src.backend.preview        # (v3) preview.json 계약 — match_item/sort/promote_state
python -m src.backend.statemachine   # (v3) FSM 파생 derive() — 0.2 전이표 시나리오
python -m src.backend.preview_build  # (v3) 6상태 preview 재구성
python -m src.backend.llm            # (v3) Groq 클라이언트 (실호출은 GROQ_API_KEY 있을 때 --live)
python -m src.backend.ytnotif        # (v3) YT 앱 알림 파서
python -m src.backend.vxtwitter      # (v3) 트윗 unfurl (fixtures/vxtwitter.sample.json)
python -m src.backend.xrelay         # X 스케줄 파서 — S1~S9 + unparsed_lines + merge
python -m src.backend.notify         # diff_events + allows() 레벨 게이팅
python -m src.backend.control        # (v2.1) control.json 헬퍼
python -m src.backend.admin          # (v2.5+) admin_state.json 헬퍼 (pending_del/ingest/notice/notice_edit/undo/member, undo.path)
python -m src.backend.xnotice        # (v2.7) 소식 파서 — S1~S12 (카테고리·날짜·anchor·recap·제목 추출 규칙)
python -m src.backend.notices        # (v2.7) notices 머지·중복판정·sweep·edit_notice
python -m src.backend.xtweet         # (v2.8) route_by_title + parse + merge_tweet + sweep
                                    #   (v2.8.1) parse_schedule + merge_personal_schedule + apply_overrides
python -m src.backend.telegram_app   # /list /del /undo /notice /notice-edit 흐름 포함 (Flask 설치 시 라우트까지)
python -m src.backend.gh_store       # 직렬화 규칙 (실제 호출은 GH_TOKEN_TEST 있을 때만)

# 백엔드 배포 (gcloud 로그인 + deploy/env.sh 필요. 상세: deploy/README.md)
bash deploy/setup.sh          # API·SA·IAM·Cloud Tasks 큐·Secret (멱등. GROQ_API_KEY 포함)
bash deploy/deploy.sh         # mewtype-backend 재배포 → SERVICE_URL 확정
bash deploy/scheduler.sh      # mewtype-light / mewtype-baseline 스케줄러 잡 (URL 불변이면 생략 가능)
bash deploy/deploy_telegram.sh && bash deploy/telegram_webhook.sh   # webhook 서비스
# 전체 전환(v→v) 절차·롤백: docs/plan/v3_golive.md

# 프론트 로컬 (저장소 루트에서 — fixture 상대경로 유지 위해)
python -m http.server 8099           # http://localhost:8099/src/frontend/
# 개발 중엔 src/frontend/js/config.js 의 DATA_URL 을 ../../fixtures/schedule.sample.json 으로 교체
```

테스트 프레임워크 없음. 각 collector 모듈의 `if __name__ == "__main__":` 블록이 스모크 테스트.

## 아키텍처 핵심

### 데이터 흐름 (v2 계보 — v3 델타는 상단 상자, 상세 `docs/SPEC.md` §8 · `docs/plan/v3_backend_surgery.md`)
1. **Cloud Scheduler** 가 `POST /tick` (baseline JST 06:00 / light 매 3h) 을 OIDC 로 호출.
   `/tick` = RSS + `videos.list` 배치 1회 → (v3) `preview_build` → `preview.json` 재구성.
   FSM 은 저장 없이 파생 — `pending.json` 은 v3 에서 없다.
2. 각 예정 방송마다 **Cloud Tasks** 에 `scheduled_start − 15분` 시각으로 wake 태스크 1개 enqueue.
   도달 시 `POST /wake {video_id}` → 라이브 여부 확인 → 다음 체크 재예약
   (pre-live 3분 / live-watch 시작~+60분 10분 · +60분 이후 3분).
   Cloud Tasks 상한 720h — 장기 예약은 `now+696h` 로 클램프해 롱폴링.
3. Cloud Run 이 변경분만 **GitHub Contents API**(fine-grained PAT, Secret Manager)로 `data` 브랜치 커밋.
4. **프론트**는 `raw.githubusercontent.com/.../data/schedule.json` 을 75초마다 fetch (v1 과 동일, 무변경).
   raw CDN 캐시로 최대 ~5분 지연 — 3시간 단위 예고엔 문제 없음(의도된 트레이드오프).
5. **(v2.1)** `/tick`·`/wake` 진입 시 `control.json` 확인 — `paused` 면 healthcheck 핑만 하고 no-op.
   상태 전이(upcoming/live 시작·종료, fallback, 오류)는 Telegram DM 으로 알림. `/status /pause /resume`
   명령은 공개 서비스 `mewtype-telegram` 이 처리. 상세는 `docs/SPEC.md` §10.
6. **(v2.3)** X 예고 릴레이 — 업스트림 시스템(운영자 폰 Automate)이 `@BDP_yumemita` 일일 스케줄
   트윗의 삼성 브라우저 웹푸시 알림 텍스트를 `mewtype-telegram` 공개 `POST /ingest`(`X-Ingest-Secret` 헤더)로 보낸다.
   `xrelay.parse_bdp_schedule` → `schedule.json` 에 `status:"scheduled"` 행(YouTube 영상 아직
   없는 최하 단계, `video_id` 없음). 정기 `/tick` 의 reconcile 이 보존하다가 실물 `upcoming`/`live`
   가 같은 채널에 ±4h 안에 뜨면 supersede, `expires_at`(start+3h) 도달 시 제거. Cloud Tasks/
   `pending.json` 은 안 탄다. `INGEST_DRY_RUN=1` 이면 저장 없이 DM 회신만. `INGEST_ECHO=1` 이면
   파싱조차 안 하고 받은 텍스트만 DM 회신(임시 테스트 훅) + 로그에 잘림 계측(`tail_ok`).
   ECHO/DRY-RUN 중 온 스케줄 트윗은 `ingest_queue.json` 에 적재됐다가 실배포 전환
   (`INGEST_ECHO=0`+`INGEST_DRY_RUN=0`) 후 첫 `/ingest` 에서 drain 돼 반영된다. 상세는 `docs/old/v2/v2_3_x_relay.md`.
7. **(v2.4/2.6)** 합동방송 — `xrelay` 가 `kind=="collab"` 행 + 트윗의 온전한 영상 URL 을 채우고,
   `render.js` 가 참여 멤버 전원(`channel_key` ∪ `collab_with`) 레인에 같은 `.card--collab` 카드를
   팬아웃(PC 5열 그리드·모바일 캐러셀 레이아웃 무변경). **(v2.6)** 합동이 공용 채널이 아니라 참여
   멤버 개인 채널에서 열리는 경우가 잦다 → 합동 줄의 `watch?v=`/`live/` URL 에서 `video_id` 를
   추출해 정규 파이프라인이 확정하고, `reconcile` 은 참여자(`channel_key` ∪ `collab_with`) 중
   아무 채널에나 실물이 뜨면 supersede 하며 `_carry_collab` 로 실물 행에 `collab_with` 를 이관한다.
   `host="group"` 특례(supersede 안 함)는 `parse_appearance`(出演情報) 전용. `全員【bilibili】` 등
   비-YT 라인은 스킵. 상세는 `docs/old/v2/v2_4_collab.md` §8.
8. **(v2.7)** 소식 게시판 — `xrelay` 가 행을 안 내는(스케줄 아님) 트윗은 `xnotice.parse` 로
   방송 외 이벤트(라이브 예고·음반/굿즈·타 플랫폼·기타) 판별 → `notices.merge_notice` 로
   `notices.json` 에 반영(중복키 = 같은 date + anchor_a/b). 자정 지난 소식은 `sweep_expired` 가
   `notice_archive.json` 로. 텔레그램 `/notice`·`/notice-list`·`/notice-del`·`/notice-edit`
   (제목→날짜→URL 순 되묻기, 유지=`aNoneTokyo`, `pending_notice_edit` 슬롯), `/undo` 는
   `undo.path` 로 schedule/notices 구분. 프론트는 `js/notices.js`+`css/notices.css` 티커(`#notice`).
   **(v2.7.x)** `_headline` 이 외침형 제목 블록(`💪…💪`)을 병합하고 `日程：`/`会場：` 라벨 줄을
   감점 — 그래도 틀리면 `/notice-edit` 로 교정. 상세: `docs/old/v2/v2_7_notice_board.md`.
9. **(v2.8)** 멤버 개인 트윗 — `/ingest` 가 본문 파싱 직후 `xtweet.route_by_title(android.title)` 로
   갈래를 나눈다. 개인 5인 표시명(`config/channels.json` `x_names`)이면 `_maybe_personal_tweet` →
   `xtweet.parse` → `merge_tweet`(더 최신 Snowflake id 면 교체, 기존 건 `tweet_archive.json`) →
   `tweets.json` 커밋하고 **즉시 종료**(소식/스케줄 파이프라인 안 탐). 24h 지난 슬롯은 `sweep_expired`.
   테스트 부계정(`INGEST_TEST_TITLES`, 기본 `jehy`)은 4번 거치되 `force_echo` 로 무조건 ECHO(업스트림
   시스템 생존 확인용 헬스체크, 상시 유지). 공식·미매칭·빈 title 은 기존 경로. 프론트는
   `js/tweets.js`+`css/tweets.css` — 유닛 아바타 편지 배지, PC 호버·고정 말풍선 / 모바일 토스트,
   배경 = 유닛 `--lane-color` 재사용. 흐름도 `docs/INGEST_FLOW.md`, 상세 `docs/old/v2/v2_8_personal_tweets.md`.
   **(v2.8.1)** 개인 5인 분기는 배지 + `xtweet.parse_schedule`(`配信`+날짜[+시각]/URL 게이트) 둘 다
   수행 → 예고면 `merge_personal_schedule` 로 `schedule.json` `scheduled`(`source:"personal"`) 승격.
   `time_tbd`(날짜만) 지원. `handlers.tick()` 이 `reconcile` 직후 `xtweet.apply_overrides` 로 트윗이
   정한 `scheduled_start` 를 API 재구성이 안 덮게 함(스트림 실제 수정 시만 API 승 — `api_start_seen`).
   계약 A 필드: `source`/`time_tbd`/`info_source`/`info_at`/`api_start_seen`. 상세 `docs/old/v2/v2_8_1_personal_schedule.md`.

### 수집 로직 (`main.py` → `reconcile.build_schedule`)
- **후보 집합** = RSS로 발견한 최근 videoId ∪ 이전 `schedule.json`의 미해결(upcoming/live) videoId
  ∪ (deep 모드면) `search.list?eventType=upcoming` 결과.
- `videos.list` 로 일괄 enrich → `snippet.liveBroadcastContent` 로 분기:
  `upcoming`/`live` 는 `schedule.json` 에 유지, `none` 은 이전에 추적 중이었으면 `archive.json` 으로
  이관(`ended`/`canceled`), 후보에서 아예 사라졌으면 `removed`.
- `schedule.json` 정렬: `live` 우선 → `scheduled_start` 오름차순.
- 시각은 전부 UTC ISO(`Z`)로 저장, KST 변환은 **프론트 `time.js` 담당**.

### 계약 (변경 시 `docs/SPEC.md` 먼저 수정)
- (v3) `preview.json` / `preview_archive.json` 스키마 (계약 A′): `docs/SPEC.md` · `docs/plan/v3_backend_surgery.md` "v3 데이터 스키마".
- `pending.json` (계약 E) — **v3 에서 폐지**.
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
