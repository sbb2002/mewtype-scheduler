# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트

夢限大みゅーたいぷ(무겐다이 뮤타입) 소속 유튜브 방송인 5명의 **예약 방송·라이브 상태**를 취합해
보여주는 반응형 정적 웹사이트. 팬이 사이트에 방문하면 누가 언제 방송하는지, 지금 라이브 중인지,
어느 주소로 가면 되는지 한눈에 확인한다.

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
  기준으로 맞추고, 거기 없는 새 용어가 필요하면 임의로 정하지 말고 사용자와 상의 후 추가한다.
  이 파일(`CLAUDE.md`) 자체도 코드 변경 시 같이 갱신 — 오래된 서술이 남으면 그 자체가 사용자를
  오도하는 이해용 문서가 된다.

틀린 문서는 문서가 없는 것보다 위험하다 — 사용자의 정신모델이 실제 시스템과 어긋나게 만들고,
정작 해결하려던 "이해 병목"을 더 위험한 형태로 재생산한다.

> **문서 위치 (2026-09-14 정리)**: `docs/` 아래 이 파일에서부터 가리키는 경로들 중
> `SPEC.md`·`TERMINOLOGY.md`·`VERSION.md`·`INGEST_FLOW.md` 넷만 `main`에 있다. 그 외
> (`beta_version/`·`old/`·`plan/`·`ARCHITECTURE.md`·`SCHEDULE.md`·`AUTOMATE_MANUAL.md`·
> `IDEA.md`·`SECURITY.md`·`bug_report/`·`v2_4_flow.png`·`v3_pamphlet.html` 등, 개발 중
> 상시 참조하기보다 배경자료·구버전 기록·운영자용 설명자료에 가까운 것들)는 전부
> **`devpapers` 브랜치**로 옮겨졌다 — `data` 브랜치와 같은 이유(자동 생성되는
> `PUSH_MONITOR.html` 시간별 갱신 커밋이 Vercel 배포 트리거에 안 걸리게, `vercel.json`
> 참고). 아래 경로 표기(`docs/xxx`)는 어느 브랜치 것이든 그대로 유효 — `git show
> origin/devpapers:docs/ARCHITECTURE.md` 식으로 조회. 용어는 `docs/TERMINOLOGY.md`
> "`devpapers` 브랜치" 항목 참고.

- 요구사항·설계 배경: `docs/beta_version/PRD.md`, 인터뷰 원본 `docs/beta_version/INTERVIEW*.md` (devpapers)
- **용어 기준 (세션 간 표현 일관성): `docs/TERMINOLOGY.md`** — 프론트엔드/백엔드/업스트림 시스템/외부 LLM 등.
  표현이 엇갈리면 여기에 추가.
- **현행 구현 명세 (계약 A~I, 백엔드·프론트 모듈): `docs/SPEC.md`** — v3 기준.
  원본 `docs/old/v1/IMPLEMENTATION.md`, `docs/old/v2/IMPLEMENTATION_v2{,.1}.md` (devpapers)
- **현행 전체 흐름 (박스별 설명 + 그림): `docs/ARCHITECTURE.md`** + `docs/v2_4_flow.png` (devpapers)
- 백엔드 스케줄(운영자 시점 요약): `docs/SCHEDULE.md`. 아키텍처 구상도: `docs/old/v2/v1_impro_final.md` (devpapers)

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
>   트윗 번역·(v3.1.13) 방송 제목 번역. 결과는 `notices.json` `title_ko` / `tweets.json` `text_ko`
>   / `preview.json` `title_ko` 에 원문과 함께 저장.
>   실패 행은 `needs_tl:true` → 다음 tick 재시도. `GROQ_API_KEY` Secret.
> - **예고 머지 모델** = 소스 신뢰도 티어(1 API / 2 명시값 / 3 파생값). 높은 티어 승, 동일 티어 안 최신순.
> - 텔레그램 명령 `{cmd}×{contents}` 격자 (`/list /ingest /edit /del /undo /translate × preview|notice|tweet`).
> - 업스트림 Automate 플로우 v3: 패키지별 리스너 2개(삼성 인터넷 + YouTube) + Fork. `docs/AUTOMATE_MANUAL.md §4b`.
> - 데이터는 **콜드 스타트** — v2 파일은 `data:.old/`, 마이그레이션 스크립트 없음.
> - **v3.1.4**: 5인 합동 전용 그룹 공식 채널(`@BDP_yumemita`, `config/channels.json` `channels.group`,
>   `channel_order` 밖)을 RSS/API 폴링 대상에 추가 — `preview_build.build_preview` 가 이 채널
>   영상을 `channel_key=channel_order[0]` + `collab_with=나머지 4인` + `host="group"` 로 5인
>   레인에 자동 팬아웃(`GROUP_CHANNEL_KEY`). + `xrelay.parse_live_now` — 일일 스케줄/出演情報
>   서식이 아닌 "지금 막 시작" 즉시개시 트윗(`配信開始`+온전한 영상 URL)을 감지해 `video_id`
>   포함 `announced` 아이템으로 즉시 반영(폴링 지연 없이). 상세: `docs/SPEC.md` §1-3-1/§1-3-2.
> - **v3.6** (2026-09-16~17, 설계 검토→구현): 개인 5인 트윗 예고 판정을 URL 우선으로 재설계.
>   실사례 2건이 계기 — 노노카 쇼츠 라이브가 `配信` 키워드 없이 시작해 light tick(3h) 텀만큼
>   감지가 늦었던 것, 아라레 후기 트윗(`2時間プレイ…9/24まで`)의 무관한 숫자가 정규식에 날짜/
>   시각으로 오합성됐던 것. 대응:
>   - **light tick 3h → 10분** (`deploy/scheduler.sh`) — 자원 소모 재확인 결과 YouTube 쿼터
>     (10분×144회/일=288 units, 무료 한도 1만의 3%)·GitHub API·Cloud Run 무료 티어 전부 여유.
>   - **URL 우선 ingest** — 유튜브 URL 있으면 `videos.list` 로 즉시 사실 확정(본인/타멤버/그룹
>     채널은 바로 등록, 외부 채널은 LLM 참여판정 후 등록) → API 실패 시 텍스트 파싱으로 자동
>     폴백(v3.6 이전 신뢰도 밑으로 안 떨어짐). 비유튜브 URL(bilibili 등)은 라이브/종료 추적이
>     안 돼 `notices.json` 으로 이관(preview 스코프 아웃).
>   - **LLM 최종 확인** — URL 없는 텍스트 예고 후보도 등록 직전 `announces_own_broadcast()` 로
>     "진짜 본인 예고인가" 재확인(정규식 게이트+날짜추출만으론 후기 오탐을 못 막음).
>   - Cloud Tasks wake 즉시 enqueue(등록과 동시에, light tick 안 기다림) + undo 스냅샷(LLM
>     오판 대비) + monitor 이벤트 로그(`flow="tweet"`, `result="degraded"` — LLM/API 인프라
>     문제로 스킵한 경우만, 정상 "아니오" 판정은 노이즈라 제외).
>   - `/telegram` 웹훅 안전망: 모든 반환 지점을 `_done()` 으로 통일해, 명령 처리 후 DM 이
>     한 건도 안 나가면 자동으로 안내 DM(버그리포트 `/del preview` 무응답 — 재현은 안 됐지만
>     일반화된 안전망으로 대응).
>   - `xtweet.parse_schedule` 후기가드(`_RECAP_RE`) 도 별도로 고침 — "추출된 날짜가 과거일
>     때만 후기로 인정"하던 조건이 오합성된 미래 날짜엔 무력화되던 버그.
>   상세 설계 대화/흐름도: `docs/v3_pamphlet.html`(devpapers) "개인 트윗 예고 판정" 섹션.
> - **v3.7** (2026-09-17, `b07d7b5`): **write-queue** — 제어 채널(`mewtype-telegram`)의 `data` 콘텐츠
>   쓰기를 백엔드 `POST /write`(`concurrency=1`)로 보내 직렬화(`writers.py`/`writeclient.py`). GitHub
>   Contents API PUT 이 브랜치 HEAD 단위로 충돌해, 같은 초에 들어온 `/ingest` 요청끼리 409 를 내 트윗이
>   유실된 사고(2026-09-16) 대응. + 소식 LLM 의미 중복판정(같은 날짜만, `llm.duplicate_notice`) +
>   상시 모니터 페이지(`monitor.html` ← `monitoring/latest.html`, 이스터에그 진입).
> - **v3.7.1** (2026-09-17): v3.7 점검 후속. 명세 `docs/plan/v3_improvisation.md`, 요약 `docs/VERSION.md`.
>   - `/ingest` 개인 트윗 500(P0, `gh` 대입 전 사용) 수정 + `/ingest` 라우트 self-test.
>   - **write-queue A-1**: 외부 LLM·`videos.list`·vxtwitter·비전 OCR 은 **제어 채널에서 준비**
>     (`_prepare_notice`/`_prepare_personal_tweet`/`_maybe_url_confirmed_schedule`), `/write` 잡은
>     **커밋만**(`_commit_notice`/`_commit_personal_tweet`/`_url_confirmed_commit`). 외부 장애가 백엔드
>     `/tick`·`/wake` 를 같이 막지 않게. Cloud Tasks 즉시 wake 등록은 백엔드 잡 안(제어 채널엔 Tasks env 없음).
>     모니터 로그·`admin_state` 마법사·`control.json` 은 여전히 제어 채널 직접 커밋(A-2 미채택). `docs/SPEC.md` §8.14.
>   - 백엔드 모니터 로그: 실행당 커밋 최대 1개(`monitor_log.log_events`), 변화 없는 tick/wake 미기록.
>   - 라이브 후기 wake 3분→5분, 외부 LLM 폴백 기본값 404 모델 제거, `apply_overrides` v3 재작성·연결,
>     healthchecks Secret 조건부 마운트.
> - **v3.7.2** (핫픽스): 개인 트윗이 다음날 전부 사라지던 버그(프론트 `VISIBLE_WINDOW_MS=12h` 필터 제거 →
>   `expires_at` 24h + 상한 50건) + 웹 monitor 가 06:00 스냅샷을 보여주던 버그(제어 채널 `GET /monitor-live` 로
>   접속 시각 기준 즉석 생성, `latest.html` 은 폴백). 요약 `docs/VERSION.md`.
> - **v3.7.3** (핫픽스): 업스트림 유튜브 알림(`source=yt`)이 400 이던 것 수정 + 회원 전용 방송 시작 알림 →
>   yt-dlp(`ytdlp_probe.py`)로 video_id/URL 조회 → `yt_member_live_commit` 로 live 전환(`xtweet.merge_member_live`).
>   쿠키는 선택(`YT_COOKIES_FILE`) — 없어도 동작. 같은 버전: 예고 자리표시 왕복 차단(`late-hold`)·웨이크 체인 증식
>   차단(`statemachine._after` 격자)·먼 미래(24h+) 웨이크 미등록(`handlers._wakes_within_horizon`)·미래로 밀린
>   `watching` 되돌림, `vxtwitter` HTTP 500 시 `fxtwitter` 폴백(참조 트윗 유실). 요약 `docs/VERSION.md`.
> - **v3.8.0a** (기각): `<video>` 직접 재생 방식 — 법률 자문(UI 재조립 시 성명표시권 침해 사례)으로 배포하지 않음, 브랜치 `feat/v3.8.0a-tweet-video` 보존.
> - **v3.8.0b** (진행 중·미병합): 말풍선 트윗 = 번역 말풍선 + X 공식 트윗 카드만(재조립 요소 제거), 디스클레이머 + GitHub Issues 창구.
>   브랜치 `feat/v3.8.0b-tweet-embed`. 요약 `docs/VERSION.md`.
> - **v3.7.4** (핫픽스): 영상 첨부 트윗의 미디어가 깨지던 것 수정(`vxtwitter._media_urls`: 영상·GIF 는 썸네일 URL, 프론트가 `<img>` 로만
>   그림). 요약 `docs/VERSION.md`.
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
- **수집/판정** = **Cloud Run**(scale-to-zero, `src/backend/`) 2서비스 — 메인 `mewtype-backend`
  (`concurrency=1 · max-instances=1`) + 제어 채널 `mewtype-telegram`(텔레그램 웹훅·`/ingest`). 정기 트리거
  **Cloud Scheduler** 3잡(baseline JST 06:00 / light 10분(v3.6, 구 3h) / monitor KST 06:10) + 방송별 정밀
  wake **Cloud Tasks**. 리전 `asia-northeast1`.
- **저장** = **GitHub `data` 브랜치** — 2026-09-14 부터 별도 저장소 `sbb2002/mewtype-scheduler-data`
  (`docs/plan/data_repo_migration.md`). Cloud Run 이 GitHub Contents API(fine-grained PAT)로 커밋.
- **프론트** = **Vercel** 정적 호스팅. 배포 주소 `https://mewtype-schduler.vercel.app/`
  (레포명은 `mewtype-scheduler` 로 고쳤지만 Vercel 프로젝트/도메인은 옛 오타 `mewtype-schduler`
  그대로 — 헷갈리지 말 것). `main` 브랜치 푸시 시 자동 배포(`vercel.json` 은 `data` 브랜치만
  배포 제외). (v1 의 GitHub Actions 수집기는 `src/collector/` + `collect.yml`
  `workflow_dispatch` 로 남아 있지만 **실행해도 현행 사이트엔 반영 안 됨** — v1 `schedule.json` 을 코드
  저장소의 `data` 브랜치에 push 하는데, 프론트는 데이터 저장소의 `preview.json` 을 읽는다.)

## 저장소 구조

이 `mewtype-scheduler/` 폴더는 상위 `pyworks` 저장소 안에 **중첩된 별도 git 저장소**다
(`origin` = `github.com/sbb2002/mewtype-scheduler`). 상위 `pyworks`와 무관하게 취급.
(2026-08-30: 레포명 오타 `mewtype-schduler` → `mewtype-scheduler` 로 변경됨. 옛 raw URL은 404됨)

```
src/
  frontend/            # Vercel Root Directory = src/frontend, 빌드 없음
    index.html         # #notice(v2.7 소식) + #board + #foot 스켈레톤, <script type="module">
                       #   <meta name="color-scheme" content="dark"> — 다크 전용, 브라우저 force-dark 끔
    css/{reset,layout,card,notices,tweets}.css   # 다크 단일 테마 (reset.css :root color-scheme:dark)
    js/                # ES 모듈, 상대 import
      config.js        # 상수 (DATA_URL, NOTICES_URL, TWEETS_URL, 폴링 주기, 폴백 채널 메타)
      time.js          # UTC→KST 포맷, 상대시간 라벨 — 순수 함수
      api.js           # fetchSchedule(url): AbortController 타임아웃, {ok,data|error} (notices 도 재사용)
      render.js        # renderBoard / renderFooter / updateCountdowns
      notices.js       # (v2.7) renderNotices(#notice, data) — 소식 티커 (접힘/펼침/5초 순환/램프/marquee)
      tweets.js        # (v2.8) renderTweets/reapplyTweets — 유닛 아바타 편지 배지 + PC 말풍선 / 모바일 토스트
      main.js          # DOMContentLoaded → poll(스케줄) + pollNotices + pollTweets + 카운트다운 틱
                       #   (v3.7) 모니터 페이지 이스터에그 진입(PC 키 입력 / 모바일 풋터 버전 15탭)
    monitor.html       # (v3.7) monitoring/latest.html(데이터 저장소 raw URL)을 iframe 으로 표시. noindex
  collector/           # v1 순수 모듈 — v2 백엔드가 import 재사용. main.py 는 break-glass 전용
    main.py            # v1 오케스트레이션 (python -m src.collector.main [light|deep])
    config.py          # config/channels.json + YOUTUBE_API_KEY 로드
    rss.py             # 채널 RSS → videoId 발견 (쿼터 0)
    youtube.py         # YouTube Data API v3 (videos.list / search.list), VideoInfo
    reconcile.py       # 상태 판정 + 이전 스냅샷 대비 diff — 순수 함수
    store.py           # schedule.json / archive.json 로드·저장 (변경 시에만 기록)
  backend/             # Cloud Run 서비스 (Flask + gunicorn). v3.0.
    app.py             # 메인 라우트 /tick(Scheduler) /wake(Cloud Tasks) /write(v3.7, 제어 채널 쓰기 큐)
                       #   /monitor(Scheduler) · `/` 헬스체크(GFE 가 /healthz 가로챔)
    handlers.py        # (v3) tick/wake → preview_build → (v3.7.1) apply_overrides → preview.json 커밋
                       #   + LLM 말단 번역(needs_tl sweep) + (v3.7.1) 모니터 로그 실행당 1커밋·무변화 스킵
    writers.py         # (v3.7) /write 잡 kind → telegram_app 커밋 함수 매핑(지연 import).
                       #   (v3.7.1 A-1) 잡은 커밋 전용 — 외부 호출은 제어 채널에서 준비해 인자로 넘김
    writeclient.py     # (v3.7) 제어 채널 → 백엔드 /write 동기 호출(OIDC, 60초). MAIN_SERVICE_URL 없으면 로컬 디스패치
    preview.py         # (v3) preview.json 계약 A′ — make_item/match_item/sort/promote_state (순수)
    preview_build.py   # (v3) reconcile 포크 → 6상태 preview 재구성 (순수). (v3.1.4) 그룹 공식 채널
                       #      (@BDP_yumemita) 영상 → 5인 팬아웃(host="group")
    statemachine.py    # (v3) FSM 파생 — derive(item, now) → (next_state, next_check_at, log). 저장 안 함
    llm.py             # (v3) Groq 클라이언트 — notice_title(json_schema strict) / translate. 실패 시 None
                       #        (v3.6) participation(외부 채널 콜라보 참여판정) /
                       #        announces_own_broadcast(텍스트 예고 최종확인) 추가 — 둘 다 최대
                       #        5회 재시도, 5회 모두 실패 시 None(호출부 미등록 처리)
                       #        (v3.7) duplicate_notice(같은 날짜 소식 의미 중복판정)
                       #        폴백 기본값 FALLBACK_MODEL=openai/gpt-oss-20b (llama-3.3 은 이 계정에서 404)
    ytnotif.py         # (v3) YouTube 앱 푸시알림 파서 (`chime.*` 키). INGEST_YT_ENABLED 뒤
                       #   + (v3.7.3) `parse_member_live_relay` — 실제 중계 폼(`source=yt`)의 회원 전용 시작 알림
    ytdlp_probe.py     # (v3.7.3) 회원 전용 라이브 video_id/URL — yt-dlp 로 채널 streams 탭 조회(쿠키 선택)
    vxtwitter.py       # (v3) 트윗 unfurl — 잘린 URL·이미지 복원 (api.vxtwitter.com)
    vision.py          # (v3.2) Groq 비전 OCR — 크로스오버 공지 이미지 속 출연진 이름 판독
                       #        (qwen/qwen3.8-27b 주 + qwen/qwen3.6-27b 폴백). 실패 시 None
    #  (삭제됨) pending.py — v3 는 FSM 을 preview 아이템에서 파생하므로 불필요
    gh_store.py        # GitHub Contents API read/write (직렬화 규칙 store.py 와 동일)
                       #        (v3.3) read_text/write_text — HTML 등 비-JSON 파일용
    push_monitor.py    # (v3.5, 구 v3.4 대시보드에서 축소) `_CODE_REPO`(main/devpapers 등
                       #        코드 브랜치 고정 저장소) + fetch_commits/list_branches만
                       #        남음 — monitor_report.py 의 Vercel push count 계산용.
                       #        옛 대시보드(카테고리별 누적 막대+날짜 히트맵) 코드는
                       #        git 이력(v3.4.14 이전)에만 남아있음.
    monitor_log.py     # (v3.5) 모니터링 이벤트 로그 — tick/wake/preview 전이/notice/tweet/
                       #        relay/운영자 `/pause`·`/resume` 마다 `monitoring/events-
                       #        YYYY-MM-DD.jsonl`(data 저장소)에 한 줄 append. 공통 필드
                       #        `ts/flow/result/who/detail` + 흐름별 추가 필드, `result`는
                       #        `ok`/`degraded`/`err`(성공/실패로 미리 안 뭉침). tweet/relay는
                       #        `via`(`ingest`|`ops`)로 자동/수동 구분. (v3.5.1) 하루 경계
                       #        `DAY_START_HOUR=6`(KST 06:00~익일 06:00) — 자정 넘겨 방송하는
                       #        멤버가 흔해서 00:00 경계 대신 씀. `bucket_date_kst()` 참고.
    monitor_report.py  # (v3.5) `/monitor` — 위 이벤트 로그 + healthchecks.io(백엔드 상태) +
                       #        push_monitor.fetch_commits(Vercel push 요약)을 모아 트리거→
                       #        preview/릴레이/소식/개인트윗 Ops Timeline HTML 생성(html은
                       #        커밋 안 하고 텔레그램 DM 으로만). (v3.5.1) `full=True`
                       #        (`/monitor --full`)면 이번 달 1일~오늘 전부를 `REPORT.days`에
                       #        담아 리포트 안 "월간 추이" 그리드(잔디)로 날짜 전환(재요청 없이
                       #        클라이언트 쪽 전환) 가능. 기본(`/monitor`, `--auto`)은 하루치만.
    tasks.py           # Cloud Tasks enqueue (OIDC 타깃, 720h 상한 클램프)
    oidc.py            # Scheduler/Tasks OIDC bearer 토큰 검증
    config.py          # 환경변수 → Config
    notify.py          # (v2.1) Telegram 알림 + diff_events(A~F). (v2.8.2) allows(level,kind) —
                       #        simple=upcoming·live / normal=+scheduled·notice·tweet / detail=+ingest·fallback·요약
    control.py         # (v2.1) control.json 스키마 (paused). (v3.5, 구 push_monitor_auto)
                       #        monitor_auto 추가
    telegram_app.py    # (v2.1) 공개 webhook 서비스 — 엔트리포인트 src.backend.telegram_app:app.
                       #        (v2.3) POST /ingest — 업스트림 시스템(운영자 폰 Automate)이 X 알림 텍스트를 중계
                       #        (v2.5) /list /del /ingest(=/add) /undo — 텔레그램 수동 관리 명령
                       #        (v3.5, 구 /push-monitor) /monitor [--auto|--off|--full|
                       #        YYYY-MM-DD] — Ops Monitor 리포트 즉시 DM / 자동 실행 on-off /
                       #        이번 달 전체(월간 그리드) / 특정 날짜
                       #        (v3.6) 개인 트윗 예고 판정 3단 분기(_maybe_personal_schedule):
                       #        ①유튜브 URL→_maybe_url_confirmed_schedule(videos.list 확정,
                       #        API 실패 시 텍스트 파싱 폴백) ②비유튜브 URL→_maybe_nonyt_url_notice
                       #        (notices.json 이관, preview 는 라이브/종료 추적 불가라 스코프
                       #        아웃) ③URL 없음→parse_schedule 후보 + LLM announces_own_broadcast
                       #        최종확인(정규식이 못 잡는 후기 오탐 방지, 버그리포트 20260916 #2).
                       #        LLM/API 인프라 문제로 스킵한 경우만(정상 "아니오" 판정은 제외)
                       #        monitor 이벤트 로그에 degraded 로 기록(_log_event_safe) — 조용히
                       #        방치되지 않게. /telegram 웹훅은 모든 반환 지점을 _done() 으로
                       #        통일 — 명령 처리 후 DM 이 한 건도 안 나가면 안전망 DM 자동 발송
                       #        (버그리포트 20260916 #4, ContextVar 로 요청별 격리)
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
                       #        (v3.1.4) parse_live_now — 즉시개시 공지(配信開始+온전한 URL) → video_id
                       #        포함 announced 즉시 반영. 그룹 명의만 있으면 host="group" 5인 팬아웃
    xtweet.py          # (v2.8) android.title 라우팅(route_by_title) + tweets.json/tweet_archive.json
                       #        계약(parse·merge_tweet·sweep_expired) — 순수. 개인 5인 트윗 전용 파이프라인
                       #        (v2.8.1) parse_schedule(예고 게이트) · merge_personal_schedule(같은 방송 upsert)
                       #        · apply_overrides(handlers 후처리 — 트윗 시각이 API 재구성을 override.
                       #          v3.7.1 에 v3 형태로 재작성·연결: api_start_seen 이 직전 tick 대비 60초
                       #          넘게 바뀌면 API 승. 그 전엔 어디서도 호출 안 됐음)
                       #        (v2.8.1+) 수동 /ingest 도 개인 예고 폴백 — 본문 YT URL→videos.list(quota 1)로
                       #        채널 판별, 실패 시 텔레그램에서 유닛 되묻기 (telegram_app._try_personal_ingest)
                       #        (v3.6) resolve_url_host(본인/타멤버/그룹/외부 채널 4갈래) ·
                       #        build_item_from_video(videos.list 결과를 state 로 직결 — 고정값
                       #        아님) · merge_video_confirmed(video_id 기준 upsert, 상태 역행 방지)
                       #        — URL 우선 ingest(telegram_app._maybe_url_confirmed_schedule) 용
Dockerfile             # python:3.12-slim + gunicorn. 두 서비스가 이 이미지 공유(엔트리포인트만 다름)
deploy/                # gcloud 배포 스크립트. env.sh 는 루트 .env 매핑(gitignore)
  setup.sh deploy.sh scheduler.sh deploy_telegram.sh telegram_webhook.sh README.md
config/channels.json   # 5채널 단일 소스 (channel_order, channel_id, handle, name, name_ko)
                       #   + (v3.1.4) channels.group — 5인 합동 전용 그룹 공식 채널(@BDP_yumemita),
                       #   channel_order 밖(전용 레인 없음), RSS/API 폴링만
fixtures/              # preview/notices/tweets.sample.json(프론트), rss_arale.xml(파싱 테스트),
                       #   vxtwitter.sample.json. schedule.sample.json 은 v1/v2 잔재
.github/workflows/collect.yml   # v2: workflow_dispatch 전용 (정기 cron 제거됨)
data 브랜치 (v3)        # preview.json + preview_archive.json + control.json
                       #   + notices.json / notice_archive.json (소식, +title_ko)
                       #   + tweets.json / tweet_archive.json (개인 트윗, +text_ko)
                       #   + admin_state.json (계약 G′ — pending_op/edit_lock/suppress/undo 슬롯)
                       #   .old/ = 전환 시 치워둔 v2 파일(schedule/pending/ingest_queue …). 롤백용. 코드 없음
devpapers 브랜치 (v3.3)  # docs/ 중 개발 시 상시 참조 안 하는 문서 전부(배경자료·구버전 기록·
                       #   운영자용 설명자료 등) + docs/PUSH_MONITOR.html(1시간마다 자동 커밋).
                       #   코드 없음. data 브랜치와 같은 이유로 Vercel 배포 트리거 밖
                       #   (vercel.json). 용어는 docs/TERMINOLOGY.md 참고, "docs 브랜치"라
                       #   부르지 말 것(docs/ 폴더명과 헷갈림)
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
python -m src.backend.writers        # (v3.7) /write 잡 kind 레지스트리
python -m src.backend.writeclient    # (v3.7) MAIN_SERVICE_URL 없을 때 로컬 디스패치
python -m src.backend.handlers       # _scheduled_wake_times·_preview_log_events·(v3.7.1) _should_log_run·apply_overrides 연결
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
python -m src.backend.gh_store       # 직렬화 규칙 + read_text/write_text (실제 호출은 GH_TOKEN_TEST 있을 때만)
python -m src.backend.push_monitor   # (v3.5, 축소됨) fetch_commits/list_branches 필드 매핑만 (mock)
python -m src.backend.vision         # (v3.2) 비전 OCR (실호출은 GROQ_API_KEY + fixtures/awarnoutz_cast.jpg 있을 때 --live)
python -m src.backend.monitor_log    # (v3.5) event_path(06:00 KST 경계)·log_event append/충돌 재시도 (mock)
python -m src.backend.monitor_report # (v3.5) parse_events/그룹핑/preview 세그먼트·render_html·(v3.5.1) full=True 월간 조회 (mock)

# 백엔드 배포 (gcloud 로그인 + deploy/env.sh 필요. 상세: deploy/README.md)
bash deploy/setup.sh          # API·SA·IAM·Cloud Tasks 큐·Secret (멱등. GROQ_API_KEY 포함)
bash deploy/deploy.sh         # mewtype-backend 재배포 → SERVICE_URL 확정
bash deploy/scheduler.sh      # mewtype-light / mewtype-baseline / mewtype-monitor 스케줄러 잡 (URL 불변이면 생략 가능)
bash deploy/deploy_telegram.sh && bash deploy/telegram_webhook.sh   # webhook 서비스
# writers.py·telegram_app.py 등 두 서비스 공통 코드를 바꾸면 deploy.sh + deploy_telegram.sh 둘 다
# 전체 전환(v→v) 절차·롤백: docs/plan/v3_golive.md

# 프론트 로컬 (저장소 루트에서 — fixture 상대경로 유지 위해)
python -m http.server 8099           # http://localhost:8099/src/frontend/
# 개발 중엔 src/frontend/js/config.js 의 PREVIEW_URL 을 ../../fixtures/preview.sample.json 으로 교체(주석 처리된 줄 있음)
```

테스트 프레임워크 없음. 각 collector 모듈의 `if __name__ == "__main__":` 블록이 스모크 테스트.

## 아키텍처 핵심

### 데이터 흐름 (v2 계보 — v3 델타는 상단 상자, 상세 `docs/SPEC.md` §8 · `docs/plan/v3_backend_surgery.md`)
1. **Cloud Scheduler** 가 `POST /tick` (baseline JST 06:00 / light 매 10분(v3.6, 구 3h)) 을 OIDC 로 호출.
   `/tick` = RSS + `videos.list` 배치 1회 → (v3) `preview_build` → `preview.json` 재구성.
   FSM 은 저장 없이 파생 — `pending.json` 은 v3 에서 없다.
2. video_id 있는 예정 방송마다 **Cloud Tasks** 에 wake 태스크 enqueue (v3 FSM: `scheduled_start − 3분`).
   도달 시 `POST /wake {video_id}` → 라이브 여부 확인 → 다음 체크 재예약
   (watching 3분 / live 시작~+60분 10분 · +60분 이후 5분(v3.7.1, 구 3분) / end 창 5분).
   Cloud Tasks 상한 720h — 장기 예약은 `now+696h` 로 클램프해 롱폴링.
3. Cloud Run 이 변경분만 **GitHub Contents API**(fine-grained PAT, Secret Manager)로 `data` 브랜치 커밋.
4. **프론트**는 데이터 저장소 `raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/preview.json`
   (+ notices/tweets) 을 75초마다 fetch. raw CDN 캐시(`max-age=300`)로 최대 ~5분 지연 — 의도된 트레이드오프
   (그래서 v3.7.1 에서 live 후기 wake 도 5분으로 맞춤).
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
   `time_tbd`(날짜만) 지원. (v3) `preview_build` 가 personal/x-relay 아이템의 `scheduled_start` 를 안 덮고
   `api_start_seen` 만 갱신하며, (v3.7.1) `handlers._run` 이 `build_preview` 직후 `xtweet.apply_overrides` 로
   `api_start_seen` 이 직전 tick 대비 60초 넘게 바뀐 경우(스트림 실제 수정)에만 API 시각을 적용한다.
   계약 A 필드: `source`/`time_tbd`/`info_source`/`info_at`/`api_start_seen`. 상세 `docs/old/v2/v2_8_1_personal_schedule.md`.
   **(v3.6)** `parse_schedule` 게이트는 **URL 없을 때만** 최종 경로 — 유튜브 URL 있으면
   `_maybe_url_confirmed_schedule`(videos.list 확정, 실패 시 여기로 폴백), 비유튜브 URL 있으면
   `_maybe_nonyt_url_notice`(소식 이관)가 먼저 가로챈다. 이 경로까지 온 후보도 등록 직전
   `LLMClient.announces_own_broadcast()` 최종 확인을 거친다. 상세: 위 v3.6 델타 상자.

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

- **`vercel.json` 은 반드시 `src/frontend/vercel.json`에 있어야 한다** (Vercel 프로젝트 Root
  Directory = `src/frontend`). 저장소 루트에 두면 Vercel 이 이 파일을 아예 못 읽는다 — CLI 가
  `vercel deploy` 시 "The vercel.json file should be inside of the provided root directory"로
  경고해준다. (버그리포트 20260913 #5) 이 설정이 루트에 잘못 있던 탓에 `git.deploymentEnabled.data:
  false`(data 브랜치 배포 제외)가 **한 번도 적용된 적이 없었다** — data 브랜치는 봇이 몇 분 간격으로
  커밋하는데, 매 커밋마다 Vercel 이 무시하지 않고 실제 배포 시도를 만들어 즉시 ERROR 처리했고, 이게
  전부 Hobby 플랜 "하루 100회 배포" 한도에 그대로 카운트됐다. 결국 한도를 넘겨 `main` 브랜치의 정상
  배포까지 전부 막히고(웹훅 트리거 자체가 조용히 실패), 프로덕션이 옛 커밋에 몇 시간이고 고정되는
  사고로 이어졌다. 위치를 옮긴 뒤에도 이미 초과된 하루 한도는 24시간 롤링 윈도우로 풀리므로 즉시
  재배포는 안 될 수 있다 — `vercel ls --token=$VERCEL_TOKEN` 으로 최근 배포 상태를, REST
  `GET /v9/projects/{id}` 의 `targets.production.meta.githubCommitSha` 로 실제 라이브 커밋을
  확인할 것(CLI `whoami`/`teams`/`inspect`/`logs` 는 이 토큰에서 "User not found" 로 죽는 별개
  버그가 있으니 `ls`·REST API 직접 호출로 우회).
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
- **업스트림(운영자 폰 Automate) 구조적 한계 — 긴 트윗 원문 잘림.** 안드로이드 알림은
  "축약본"(`contentText`)과 "전체본"(`bigText`) 두 필드가 있는데, Automate 의 알림 리스너가
  다루는 값이 축약본으로 좁혀지는 경우가 있다. 이땐 말줄임표(…)도 인코딩 손상도 없이
  **완결된 문장처럼 보이는 상태로 조용히 잘려서** `/ingest`에 도착한다(실측: 9문단짜리 트윗이
  앞 3문단·125자만 옴 — 버그리포트 20260913 #2). 텍스트만 봐서는 절대 감지 불가능 — 그래서
  근본 해결이 아니라 **우회**로 대응 중: `telegram_app._recover_raw_via_vxtwitter` 가 tweet id만
  있으면 폰 원문을 아예 안 믿고 vxtwitter 조회 결과를 정본으로 우선 사용(`docs/SPEC.md` §8.6).
  vxtwitter(서드파티 무료 API)가 죽어 있거나 tweet id 를 못 뽑는 극소수 경우에만 폰 원문으로
  폴백 — 그 경우엔 이 잘림이 그대로 재발할 수 있다는 걸 기억할 것. Automate 쪽 알림 리스너
  설정을 bigText 우선으로 고치는 게 진짜 근본 수정이지만 `docs/AUTOMATE_MANUAL.md` 상 아직
  미확인 — 다음에 알림 리스너 Expression 을 만지게 되면 이 문서부터 먼저 볼 것.
- 코드 주석·문서·커밋 메시지는 한국어.
