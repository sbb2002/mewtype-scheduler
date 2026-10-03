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

> **현행 = v4.0** (배포 2026-10-04, v4a 로컬 시험판의 정식화 — 요약 `docs/VERSION.md`, 계획 · 진행 `ref/v4a/v4_release_plan.md`).
> 처리 로직은 아래 상자 맨 끝 **v4a** 항목, 배포 연결부는 그 안의 「v4.0 배포」 항목이 기준이다. 그 위의 v3.x 항목들과
> 아래 저장소 구조·데이터 흐름 서술은 v2~v3 계보 기록이다(v4.0 에서 바뀐 곳은 v4a 항목이 우선).
> (이전: 현행 = v3.0, 배포 2026-09-09.)
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
> - **v3.7.4** (핫픽스): 영상 첨부 트윗의 미디어가 깨지던 것 수정(`vxtwitter._media_urls`: 영상·GIF 는 썸네일 URL, 프론트가 `<img>` 로만
>   그림). 요약 `docs/VERSION.md`.
> - **v3.8.0** (기능): 말풍선 트윗 = 번역 말풍선 + X 공식 트윗 카드만(원문 텍스트·이미지·영상 재조립 제거, 법률 자문), 디스클레이머 + GitHub Issues
>   창구. 프론트만 변경(`tweets.js`·`tweets.css`·`index.html`), 저장 데이터는 유지. 요약 `docs/VERSION.md`.
> - **v3.8.1** (핫픽스): 트윗 말풍선 좌 X 카드 / 우 번역 2열 + 번역 ON/OFF 애니메이션 + 꼬리를 아바타 중앙으로 + 말풍선 디스클레이머 제거(하단만).
>   프론트만 변경. 요약 `docs/VERSION.md`.
> - **v3.8.3** (핫픽스): 본인 채널 합동방송 감지 — `xtweet.find_guest_members` 가 영상 제목·트윗 원문의 다른 멤버 정식 표기(`x_names`/`name_ko`)를
>   `collab_with` 에 추가(`_maybe_url_confirmed_schedule`), `merge_video_confirmed` 는 `collab_with` 추가만. 별칭 단독은 미감지. 요약 `docs/VERSION.md`.
> - **v3.8.6~v3.8.7** (핫픽스, 세부 미반영): 콜라보 LLM 게이트 확장·방송 취소/변경 판정·모니터 타임플롯 개선(v3.8.6) +
>   `/del`·`/edit` 상태변경 모니터로그 누락·웹 monitor 자가갱신 깜빡임 제거·self_origin http→https mixed content 수정(v3.8.7).
>   이 상자엔 아직 요약 미기록 — 커밋 `12dd80e`·`0007d29`·`a557918` 참고, 다음 세션에서 채울 것.
> - **v3.8.8** (핫픽스): 웹 monitor(`/monitor-live`) 타임라인 클릭(팝업 고정)이 60초 self-refresh 전체를
>   막아 오늘의 멤버 현황·우측 요약 등 무관한 패널까지 같이 멎어 보이던 문제 — `loadDay()` 에 `skipTimeline`
>   옵션을 추가해 고정 중엔 타임라인 렌더만 건너뛰고 나머지는 계속 최신화하도록 분리
>   (`monitor_report.py`). 요약 `docs/VERSION.md`.
> - **v3.8.9** (핫픽스): 웹 monitor(이스터에그)를 **전 기간 리포트**로 — 매일 KST 06:10 `/monitor` 가 전일 모니터링 스냅샷
>   (`monitoring/days/`)·요약(`monitoring/summary.json`)을 **monitor_auto 와 무관하게** 찍고(`monitor_snapshot.py`,
>   기존 이벤트 로그로 과거 백필), monitor_auto 켜져 있으면 "오늘의 멤버 현황" **텍스트 DM** 만 보낸다(일간/월간/연간
>   HTML 자동 DM 폐지, 수동 `/monitor` 명령은 그대로). 페이지는 오늘만 실시간 계산, 지난 날짜는 칸 클릭 시
>   `/monitor-live/day.json`. 외부 조회 실패는 `None` 으로 저장. Vercel 한도 수치는 `main` 커밋 수 근사 →
>   Vercel REST API 실제 배포 시도 수(새 Secret `VERCEL_TOKEN`, 등록 완료). 타임라인에 "💬 운영자 명령" 행
>   (제어 채널 명령마다 `flow="cmd"` 로그 — 결과는 응답 DM 문구 기반 근사) + "X 예고 릴레이" 행 → "🛰️ 업스트림
>   감지" 행(`/ingest` 알림마다 `flow="upstream"`, X/YouTube 로고, 트리거 📥 기준) + EXT YouTube quota 한도 10,000 점선.
>   요약 `docs/VERSION.md`.
> - **v3.8.9a** (v3.8.9 후속 패치): 웹 monitor 모바일 전체 추이 가로 스크롤 제거("📊 주간요약 보기" 토글) + 데이터 없는 월 탭
>   비활성 + 업스트림 아이콘을 메인 화면 네임플레이트 X·YouTube 아이콘으로(결과색 둥근 네모 테두리) + 업스트림·운영자 명령을
>   기존 로그에서 소급 복원(`_derive_upstream`/`_derive_cmd`, 복원 불가분 생략) + 09-09~09-14(전부 `[백필]`)는
>   트리거 수 `?`. 요약 `docs/VERSION.md`.
> - **v3.9** (2026-09-25 배포): **트윗 유실 방어 4겹**. 2026-09-24 19:50 KST 버스트에서 미야코 2건·
>   리츠 1건·공식 릴레이 1건이 유실된 사고 대응(모니터 로그·Cloud Run 로그로 원인 확정).
>   원인은 **두 가지가 동시에** 터진 것 — ① 백엔드가 `max-instances=1`이라 Cloud Run 이 초과 요청을
>   버퍼링하지 않고 **429 로 거절**(`no available instance`)하는데 `call_write` 에 재시도가 없었고,
>   ② 직렬화 밖에서 제어 채널이 직접 커밋하는 **모니터 로그가 `data` 브랜치 HEAD 를 흔들어** 백엔드의
>   `tweets.json` PUT 을 409 로 밀어냈다(최근 100커밋 중 65개가 모니터 로그였다).
>   `writers.py` 주석의 "Cloud Run 이 초과 요청을 자체 버퍼링" 전제가 **사실과 반대**였던 것이 핵심.
>   - **방어 1** `writeclient.call_write` — HTTP **429/503 만** 지수 백오프 재시도(1.5→3→6→12→20초,
>     지터 포함 최대 45초). 429 는 컨테이너에 **닿기 전** 거절이라 중복 커밋 위험이 없다. 반면
>     네트워크 예외는 서버가 이미 처리 중일 수 있어 **재시도하지 않는다**(기존 동작 유지).
>   - **방어 2** 409 재시도 강화 — `_commit_personal_tweet`·`monitor_log.log_events` 둘 다 "즉시 2회"
>     에서 **5회 + 백오프(0.5→1→2→4초, 지터 300ms)**. 재시도마다 반드시 **다시 읽어 머지**한다.
>   - **방어 3** **`monitoring` 브랜치 분리** — 이벤트 로그·`latest.html`·유실 큐를 `data` 가 아닌
>     전용 브랜치에 쓴다. GitHub Contents API 충돌 단위가 브랜치 HEAD 이므로 구조적으로 경합 불가.
>     `monitor_log._monitor_gh(gh)` 가 넘겨받은 store 의 브랜치만 바꾼 복제본을 돌려주는 방식이라
>     **`log_event` 호출부 49곳(handlers 11 + telegram_app 38)은 한 줄도 안 고쳤다.**
>     env `MONITOR_BRANCH`(기본 `monitoring`), 배포 스크립트 2개에 주입. `vercel.json` 배포 제외 추가.
>   - **방어 4** 유실 원문 보존 — `_dm_lost_raw` 가 유실 확정 4지점(`/write` 호출 예외 ·
>     백엔드 `mode:"error"` 반환 · auto notice 실패 · `/ingest` 라우트 예외)에서 원문을 **DM 으로 전량
>     회신**(텔레그램 4096 은 UTF-16 코드 유닛 기준이라 조립된 최종 길이를 재서 분할)하고,
>     **동시에 `monitoring/lost_queue.json` 에 적재**(최대 50건, 오래된 것부터 제거).
>     유실은 쓰기가 막혀 생기는데 그 기록을 또 막힌 곳에 쓰면 같이 실패하므로 **반드시 monitoring 브랜치**.
>     큐 항목에 `tag`(트윗 태그)를 보관해 재투입 때 vxtwitter 원문·미디어를 복원한다.
>   - **`/ingest --retroactive`** — 큐를 읽어 **한 건씩 순차** 재투입(동시 발사가 애초 유실 원인).
>     `kind` 별로 personal_tweet / notice / route 재판정 분기, 개별 try/except, **성공한 항목만 큐에서 제거**.
>   - 같이 고친 것: `app.py _monitor()` 에서 함수 내 `from .gh_store import GitHubStore` 가 이름을
>     지역 변수로 만들어 함수 앞부분이 `UnboundLocalError` 로 죽던 버그(배포 후 실동작 검증에서 발견 —
>     self-test 는 못 잡았다), `monitor_report` self-test 가 06:00 경계를 안 써서 00:00~05:59 KST 에
>     항상 실패하던 기존 버그.
>   - 상세 요약 `docs/VERSION.md`. 흐름 도식(플로우차트): 이번 세션 산출물.
> - **v3.8.10** (핫픽스, 2026-09-25): **같은 방송 판정 시각 창 ±4h → ±45분** — 두 상수 모두.
>   `preview.match_item` 기본 `superscede_sec`(예고가 **들어올 때** 기존 항목과 합칠지) +
>   `preview_build.SCHEDULED_SUPERSEDE_SEC`(**tick 때** `video_id` 없는 announced 를 같은 채널
>   실물의 자리표시로 보고 지울지). 계기: 그룹 공식 채널 방송은 `channel_key=channel_order[0]`
>   (=`arale`)로 저장되는데, 09-25 19:30 그룹 DAY2(`video_id` 有)와 3h 차인 아라레 22:30 개인 방송
>   예고가 `match_item` ±4h 에 걸려 그룹 항목에 흡수됐다(`merge_announced` 상위 티어 보호 분기 →
>   시각 버려짐, 로그는 `mode: added` 로 성공처럼 남음). `match_item` 만 줄이면 다음 tick 의 2-b 가
>   같은 이유로 다시 지우므로 둘 다 바꿨다. 45분 근거(09-01~09-25 종료 라이브 47건, YouTube API
>   실측): 같은 채널 종료→다음 시작 최소 6.7h, 라이브 최단 14.6분. **부작용**: 실물 영상의 예정
>   시각이 예고 시각과 45분 넘게 다르면 자리표시가 `expires_at`(예고+3h)까지 카드 2장으로 남고,
>   같은 방송 시각 변경을 45분 넘게 재공지하면 기존 예고가 갱신되지 않고 새 항목이 생긴다.
>   `merge_member_live` 의 ±3h(`MEMBER_LIVE_MATCH_SEC`)·v1 `collector/reconcile.py` 의 4h 는 미변경.
> - **v4.0 배포 (2026-10-04)** — 아래 v4a 가 정식 배포됐다. 로컬 러너 서술 중 **배포판에서 다른 점**: 저장 = GitHub
>   `data` / `ops` / `monitoring` 브랜치(`_local/` 아님) · 적용 큐 대신 쓰기 서비스 `/write`(→ `apply.handle`, 접수 서비스가 동기 호출 또는
>   Cloud Tasks 적재) · 예약 = Cloud Tasks `/wake` `/tick`(큐 `mewtype-wake`) · 가공 큐 대신 정기 수집 안 번역 sweep · 텔레그램 = webhook ·
>   관리 페이지 작업 탭의 경로 재생(`flowtrace`)은 로컬 전용(배포판은 LLM 판단 기록 · 이벤트 로그 · Cloud Tasks 예약을 보여줌) ·
>   원문 보존 = `monitoring` 브랜치 `raw/YYYY-MM-DD.jsonl`. 서비스 이름 · URL 은 v3 그대로(`mewtype-backend` · `mewtype-telegram`).
>   스테이징 배포 `STAGE=1 bash deploy/deploy.sh`(`deploy/env.stage.sh`). 상세 `docs/VERSION.md` v4.0.
> - **v4a (브랜치 `v4a` 에서 개발 · 로컬 시험판 → 2026-10-04 v4.0 으로 배포)** (2026-09-29): 운영자 로컬 PC 에서
>   `python -m src.backend.local_runner` 로 돌린다(Tailscale 로 폰 알림 수신, 저장은 `_local/<브랜치>/`).
>   **이 상자 위 서술(Cloud Run · Tasks · data 브랜치 커밋 경로)은 운영 v3.8.10 기준이고, v4a 에서는 아래가 다르다.**
>   문서: `ref/v4a/` — 계획 `v4a_impl_plan.md` · 결정 `v4a_decisions.md`(D1~D34, 10-01 후속 결정 = §1-9 D26~D34) · 검증 `v4a_verify_report.md` ·
>   2차 검증 `v4a_verify_report_0930.md` · **남은 작업 `v4a_remaining_0930.md`**(10-01 갱신 — 결정 6건 · 작은 수정 6건 반영 결과와 남은 것) ·
>   **남은 실측 확인 `v4a_pending_checks.md`**(상황이 와야 볼 수 있는 것 — 폰 배선 · 프리미어 · 예고 DM · OCR · D4. 다른 세션이 이어받아 확인) ·
>   폰 Automate 배선 `docs/v4a_automate_wire.md`(10-01 Fork 분리 · 재시도 적용) ·
>   관측 흐름 `v4a_verify_flow.html` · 운영 `v4a_local_runbook.md` · 재검증 `verify/harness.py`(79개 확인) ·
>   `verify/harness_b.py`(09-30 이후 기능 97개 — 결과 `results_b.json`, git 제외).
>   - 배선: `storage.py`(V4A_RUNTIME=local → `LocalStore`, control·admin_state 는 ops 로 라우팅) ·
>     `apply.py`(적용 큐 = 쓰기 스레드 `q-apply`, data 를 쓰는 유일한 스레드) · `enrich.py`(가공 큐 `q-enrich`, 번역 수집) ·
>     `jobqueue.py`(LocalQueue) · `writeclient.call_write` 는 로컬이면 적용 큐 적재 후 **결과 대기**(로컬 한정 — 배포 시 비동기로) ·
>     즉시 wake · 자기 호출 · 재개 tick → reconcile(범위) 적재.
>   - 상태 전이: watching = 영상 있는 예고 20분 전(D2) · URL 없는 예고는 +2분 `search.list` 1회 · +1h `out`(D4) ·
>     assumed-live 폐지(D5) · end→live 복구(D6) · 아카이브 신호 `none` → **`out`**(D7) · upcoming = 영상·날짜·제목(D14) ·
>     live_seen 3값(API upcoming=미확인). YouTube 알림 → `yt_notif` 작업(D1~D3).
>   - 그 밖: 공식 스케줄 영상 URL 즉시 확인(D13) · 소식 리트윗 제외(D16) · 트윗 48h(D18) · 원문 보존 `_local/raw`(D19 — 10-01 부터 예고를 내리거나
>     옮기게 한 휴방 · 변경 글도 `broadcast_change` 로, D31) ·
>     관리 페이지 `/admin`(`admin_web.py` · `admin_api.py`, 로그인 = 텔레그램 `/admin` 일회용 링크) ·
>     텔레그램은 `/status /pause /resume /list /admin` 만(D24).
>   - 관리 페이지 보강(2026-09-29~30): 세션 쿠키 `SameSite=Lax`(텔레그램 링크 로그인) · 예고 id 고유화
>     (`preview.new_id` salt + `ensure_unique_ids` — 같은 tick 발견 항목 id 중복으로 수정 · 삭제가 엉뚱한 항목에 적용되던 문제) ·
>     예고 수정에 합동 멤버 · 회원 전용 · 원문/한글 제목(번역 버튼, `title_manual` 이면 API 제목 · 자동 번역이 덮지 않음) ·
>     소식 수정 파생값 재계산 · 트윗 단위 삭제/번역 · 작업 탭 = 지금 상태 + 흐름 경로 재생(`flowtrace.py`, 로컬 전용 ·
>     `_local/ops/flows.json`) · 운영 탭 카드 정리.
>   - 원문 투입 탭 개편(2026-09-30): 2단 카드(입력 / 확인 후 반영) · 종류 세그먼트 버튼 · **트윗은 URL 만 투입**
>     (`admin_api.ingest_tweet_url` — vxtwitter/fxtwitter 응답의 작성자 X 핸들을 `channels.json` `handle`(X 핸들과 동일,
>     운영자 확인)과 대소문자 무시로 맞춰 호스트 자동 판별 · X 카드 + 번역 자동. 멤버가 아니면 `confirm_needed:"not_member"`
>     로 되묻고, "그래도 넣기"는 붙일 호스트를 골라 `force_unit` 으로 다시 미리보기). `vxtwitter.extract` 가 `author` 를 돌려줌.
>   - 원문 투입 탭 **자동 / 수동 세부 탭**(2026-09-30, 초안 아티팩트대로 구현). 수동 = 관리자가 값을 직접 정한다:
>     예고 `ingest_preview_manual`(호스트 · 합동 · 날짜/시각 KST→UTC 또는 시각 미정 · 회원 전용 · 원문/한글 제목 · 유튜브 URL —
>     확정 시 `manual_preview` 적용 큐 작업 `telegram_app._commit_manual_preview`: 같은 방송(`match_item` 호스트+video_id/url/±45분)이
>     있으면 그 항목에 값을 덮어쓰되 상태·video_id 보존, 없으면 `source:"manual"` announced 신규 추가. 제목은 `title_manual` 보호,
>     한글 비우면 `needs_tl` 로 자동 번역. URL 있으면 `enqueue_reconcile(video_id)`) ·
>     소식 `ingest_notice_manual`(제목/한글 제목/날짜/분류/URL, 한글 비우면 자동 번역) ·
>     트윗 `ingest_tweet_manual`(URL + 호스트 + 원문 + 번역, `_prepare_personal_tweet(text_ko_override)` 로 LLM 생략).
>     제목·본문 「번역」 버튼 = 기존 `translate_text`. 자동 탭 호스트 선택도 칩 버튼.
>   - 소식·트윗 탭 버튼 통일(2026-09-30): 소식·트윗 모두 **수정 / 삭제**(목록 「번역」 버튼 제거 — 수정 창 안의 번역과 중복).
>     트윗 수정 = `admin_api.edit_tweet`(→ `tweet_edit_commit` 적용 큐 → `telegram_app._tweet_edit_commit`) — **한글 번역만** 고친다
>     (원문 읽기 전용 · 비울 수 없음: 번역이 없으면 팬 화면이 「번역 준비 중…」으로 남는다 · needs_tl 해제로 자동 번역이 안 덮음 · undo 스냅샷).
>     같은 트윗을 다시 투입해도 내용이 같으면 `_commit_personal_tweet` 이 바로 돌아가 고친 번역이 유지된다(2026-09-30 검증). 새 번역으로
>     덮이는 건 지운 뒤 다시 넣었거나 원문 · 미디어가 달라진 경우. 관리 API `translate`(목록 번역) · `undo(history_id)`(미구현)는 UI 에서 안 써 10-01 삭제했다.
>   - **자동 · 예고 = URL 하나**(2026-09-30, 호스트 칩 · 원문 붙여넣기 UI 제거 — `ingest_preview_raw` API 는 남아 있음): `admin_api.ingest_preview_url`.
>     트윗 URL → 작성자 핸들로 호스트 판별(멤버 = 개인 예고, 그룹 공식 `@BDP_yumemita` = 일일 스케줄 서식, 그 밖 = 되묻기 `not_member` +
>     `force_unit`), 본문 · 인용 · 영상 URL 은 원문 투입과 같은 경로(`_ingest_preview_raw_core` 에 `tag`·`quote` 추가, 영상 URL 은 `_video_preview`
>     로 미리보기, 확정에서 API 확정 실패 시 본문 파싱 폴백). **YouTube 영상 URL** → `_ingest_video_url`: 멤버 · 그룹 채널 영상만(외부 채널 거부),
>     제목 · 시각 · 상태는 API(예정 · 임박 · 라이브로 바로), 회원 전용 · 비공개 영상은 API 가 못 봐서 수동 탭으로.
>     **그룹 공식 채널 영상은 5인 합동으로 자동 팬아웃하지 않고**, 미리보기 때 「참여 멤버 선택」 팝업(수동 · 예고의 합동 멤버와 같은 칩)을 띄워
>     고른 멤버만 올린다(1명 = 그 멤버의 일반 예고, 2명 이상 = `host="group"` 합동, `url_confirmed_commit` 직접 커밋 — LLM 합동 확인 · 팬아웃 경로 생략).
>     이미 같은 영상이 등록돼 있으면 새로 만들지 않고 예고 탭 수정으로 안내.
>     **멤버 트윗 URL 안에 든 그룹 영상도 같은 팝업**(멤버 없이 확정 요청은 거절) — 글 · 영상 제목의 근거(아래 `members_evidence`)를 먼저,
>     없으면 트윗 첨부 이미지 비전 OCR(`telegram_app._ocr_cast_keys` → `vision.cast_names` → `xrelay.NAME_TO_KEY`)로 참여 멤버를 미리 선택해 두고,
>     맞으면 확인 · 틀리면 칩으로 수정. 트윗+예고 동시 추가도 동일. 공식 트윗 URL(근거 없는 그룹 방송 글)도 같은 팝업(`admin_api._official_group_video`).
>   - **그룹 영상 = 근거가 있을 때만**(2026-09-30 운영자 결정 · 구현): 어느 경로도 근거 없이 5인 합동으로 팬아웃하지 않는다. 근거 순서 =
>     글의 **정식 이름**(`xrelay.FORMAL_NAME_TO_KEY` = x_names, 곡 크레디트 줄 제외) · **인원 표현**(`WHOLE_GROUP_RE`: 全員 · 全体(生)配信 ·
>     5名 · 5人 → 전원. 「全編無料配信」의 全 · 「5名様」 · 5명 미만 N名은 근거 아님) → (멤버 트윗이면) 영상 제목의 정식 이름 → **첨부 이미지 OCR**.
>     그룹 명의(夢限大みゅーたいぷ · #ゆめみた 해시태그)만으로는 근거가 아니다 — 전엔 이것만으로 5인이었다(`parse_live_now` · `parse_appearance`).
>     근거가 없으면 예고에 올리지 않고 **「참여 멤버 확인 대기」**(ops `group_pending.json`, 적용 큐 작업 `group_pending`)에 적고 DM(관리자 조치가 필요해
>     알림 레벨과 무관하게 보냄) → 관리 페이지 예고 탭 맨 위 카드에서 멤버 고르기(`resolve_group_pending`) · 무시(`dismiss_group_pending`), 또는
>     **같은 영상 URL 을 담은 뒤이은 공식 글에 근거가 나오면 자동 확정**(`telegram_app._resolve_group_videos`, 예: DAY2 09-17 첫 공지 → 09-24
>     「メンバー5人」). 대기는 따로 적을 뿐 다른 인입(같은 글의 다른 행 · 소식 · 이후 알림)을 막지 않는다. 예정 시각 + 6시간이 지나면 대기에서 빠진다.
>     경로별: 공식 X(`xrelay.parse` 근거 행 · `parse_pending` 후보 → OCR → 대기) · 일일 스케줄 「全員」 줄 = 5인 행(전엔 스킵) · 멤버 트윗 안
>     그룹 영상(`_maybe_url_confirmed_schedule`, 작성자를 자동으로 넣지 않음 · 이미 예고에 있으면 참여 멤버 유지) · 수집(`preview_build`)은
>     그룹 영상을 **새로 만들지 않는다**(등록된 것만 갱신) — RSS 제외와 별개로 예약된 확인 · 알림 후 확인도 막는다.
>     예고를 지우면 그 영상의 **예약된 확인도 취소**(`apply.cancel_video_checks` ← `_remove_broadcast`, `jobqueue.LocalQueue.cancel`).
>     실측 대조(공식 트윗 185건, 09-12~09-30): 사인회 = 이미지 OCR 로 5인 · DAY2 = 대기 → 09-24 같은 URL 근거로 5인 · 全員集合 · FINAL = 인원 표현으로 5인.
>   - **RSS 는 개인 유닛 채널만**(2026-09-30, `handlers.py` `rss_ids`): 그룹 공식 채널(@BDP_yumemita)을 돌리면 5th 싱글 뮤비 같은 **노래 영상**이
>     5인 합동 방송으로 팬아웃돼 올라왔다(운영·로컬 모두 `source:api`, tick 이 최초 생성). 그룹 채널 영상은 이제 RSS 로는 새로 발견되지 않는다(근거가 있는 트윗 · 관리 페이지 입력 · 이미 추적 중인 영상만 — 위 「그룹 영상 = 근거가 있을 때만」).
>     추적 중인 영상의 enrich · 아바타용 `id_by_key` 는 그룹 채널 포함 그대로. **운영(v3.8.10, main) 코드는 미변경** — 운영 RSS 는 아직 그룹 채널을 돈다.
>     운영 데이터의 5th 싱글 뮤비 항목은 `/del terminate` 와 동일하게 제거(data 저장소 커밋 `44bcb605` `c44f9d84`, 재등록 차단 12h). 자동 · 트윗에는
>     「내용 감지를 통한 트윗과 예고를 같이 추가」(`with_preview`) — 같은 트윗에서 예고도 만들어 미리보기 · 확정에 함께 반영.
>   - **내용 감지를 통한 예고 수정**(2026-09-30): 원문 투입 체크박스(자동·예고 · 자동·트윗 · 수동·트윗 — 자동·예고에서는 멤버 트윗 URL 일 때만
>     쓰여, YouTube URL · 공식 계정 트윗 URL 을 넣으면 10-01 부터 체크박스를 숨긴다(`admin.html` `previewUrlTakesDetect`)). 글에서 방송
>     취소·변경을 감지해 미리보기에 대상 예고 체크 목록을 보이고(LLM 이 고른 것이 미리 체크), 확정 시 **체크된 예고에만** 적용.
>     취소 = `/del` terminate 와 동일(삭제 + 영상 URL 12h 재등록 차단 · 채널 자리표시 URL 은 차단 생략). 변경 = 시각 이동 — 단 영상이 있는 예고는
>     다음 수집(reconcile)이 API 예정 시각으로 되돌린다(2026-09-30 검증, 유튜브 프레임 시각이 그대로면 변경이 10분 안에 사라짐) — **의도된 동작**
>     (2026-10-01 운영자 결정 D27: YouTube API 가 진실, 현행 유지).
>     자동 경로의 취소 후보(`_change_candidates` = channel_key 가 그 멤버인 활성 예고)에는 `channel_key=channel_order[0]`(아라레)로 저장되는
>     그룹 합동 방송도 들어간다. 잘못된 자동 취소의 복구 = 작업 탭 「LLM 판단」 되돌리기(되살림 + 재등록 차단 해제), 또는 관리 페이지에 그 영상 URL 을
>     다시 넣기 — 미리보기가 「재등록 차단 중(해제 시각)」을 알리고, 관리자가 **그 영상 하나를 직접 확정하는 경로**(영상 URL · 멤버 트윗 URL ·
>     참여 멤버 선택 · 수동 예고 URL)에서는 확정 시 차단을 푼다(`admin_api._lift_suppress`, 10-01). 공식 스케줄 원문을 통째로 넣을 때는 풀지 않는다.
>     `llm.broadcast_change_targets`(후보 목록 중 영향받는 id 선택 — "오늘 휴방"이면 오늘 방송 전부, "아침만"이면 그것만) ·
>     `telegram_app._detect_broadcast_change` / `_terminate_broadcast` / `_change_candidates`. **자동 인입 경로
>     `_maybe_broadcast_change` 도 같은 판정으로 교체** — 예전(v3.8.7)은 `find_active_item` 이 가장 이른 1개만 골라 "오늘 휴방"에
>     방송이 2개면 1개만 내려갔다(2026-09-30 리츠). 감지만 되고 예고로는 인식되지 않는 글(휴방 안내)도 확정 가능(`change_only`).
>     판정은 전부 LLM(정규식·키워드 분류 없음) — 단, 자동 인입 경로의 `配信` 포함 게이트(v3.8.7)는 운영자 결정으로 **유지**.
>     LLM 은 판정마다 **근거 한 문장(`reason`)** 을 쓰고(없음일 때도), 자동 경로는 "없음"도 monitor 이벤트로 남긴다
>     (`broadcast-change none · <근거>`), 관리 페이지 미리보기엔 "판정 근거"로 표시 — 놓친 취소를 확인·프롬프트 조정하는 자료.
>     같이 고친 것: 영상 없는 수동 예고의 url(채널 페이지)이 같아 `match_item` 이 다른 방송을 합치고 `make_item` id salt 가 충돌하던 문제
>     (수동 예고는 url 매칭 제외 + 시각·제목으로 id 부여). 개인 트윗 예고(`xtweet.parse_schedule`, url = 채널 페이지)도 `match_item` url 매칭으로
>     **같은 멤버의 영상 없는 예고 2건이 1건으로 합쳐지던 것**(날짜가 달라도 — 한쪽 시각이 사라짐, 09-30 재현 · 운영 3주 실제 발생 0건)을 10-01 에
>     `preview.match_item` 에서 고쳤다(D30, **v4a 만** — 운영 v3.8.10 은 그대로): 채널 페이지 url(`_is_channel_page`)은 같은 방송 근거에서 빼고,
>     대신 한쪽이 시각 미정(time_tbd)이면 JST 같은 날짜끼리 같은 방송(`_jst_day` — 「10/11 配信」 뒤 「10/11 21:00〜」 가 같은 카드를 채우게).
>   - **그룹 공식 채널의 프리미어(녹화 영상 공개 — 노래 · 뮤비 · 커버 등)는 방송 카드로 올리지 않는다**(2026-09-30 운영자 결정 · 구현, 10-01
>     그룹 채널로 한정 D26 — 멤버 개인 채널 프리미어(퀴즈 · 기념 영상 · 커버 등)는 카드로 올린다. 첫 실례: 노노카 「このエピソード夢？現実？クイズ」
>     10-01 18:00 KST). 프리미어 = 미리 올린 녹화본을 정해진 시각에 다 같이 처음 보는 YouTube 공개 방식(대기실 · 실시간 채팅). 歌枠 같은 노래
>     **생방송**은 해당 없음. 판정 지점 = `preview_build.is_group_release`(프리미어 + 그룹 채널, 4경로 공용). 카테고리로는 못 가른다(그룹 채널은
>     싱글 무비 · 생방송 · 라디오가 전부 24). 프리미어 판정 자체는 `videos.list` 의 `status.uploadStatus == "processed"`(영상 파일이 이미 있음) 또는 duration 이 `P0D` 가 아님, 그리고
>     예정 · 진행 중(`collector/youtube.py` `VideoInfo.is_premiere`, part 에 contentDetails · status 추가 — 쿼터는 그대로 1). 실측: 5th 싱글 기념 무비
>     프리미어 = processed · duration 없음, 예정 생방송 5건 = uploaded · P0D. 수집(`preview_build` — 새로 안 만들고 트윗 등으로 먼저 올라온
>     항목도 뺌) · 공식 스케줄 영상 즉시 확인 · 멤버 트윗 URL · 관리 페이지 URL 투입 모두 막는다. 뺀 영상은 버리지 않고 ops `video_releases.json`
>     (`handlers.record_video_releases`, 적용 큐 작업 `video_release`)에 기록 — 추후 보조 기능("유메미타 플레이어") 재료.
>     10-01 전 기록엔 멤버 채널 프리미어 1건(노노카 퀴즈 `zh6vG0isdAE`)이 섞여 있다.
>   - **LLM 판단 기록 · 되돌리기**(2026-09-30 운영자 요청): 자동 인입에서 LLM 이 내린 판단을 ops `llm_actions.json`(최근 300건)에 남기고
  - **LLM 판단 반려 · 재판단 · 사용자 판단**(2026-10-02, v4a 만 — 설계·판단별 시나리오 `ref/v4a/v4a_llm_review_scenarios.md`): 「되돌리기」를 「반려」로 바꾸고(동작 동일 = 그 판단이 한 변경만 롤백, 검토용 판단도 표시만 반려), 반려된 판단은 **LLM 재판단**(기록의 `input` 으로 같은 판정을 `llm.REVIEW_HINT` 힌트와 함께 재실행) 또는 **사용자 판단**(종류별 선택지를 강제값 `_REVIEW["forced"]` 로 주입해 같은 반영 경로)으로 잇는다. 7종 전부(banner_judge · broadcast_change · collab_guest · duplicate_notice[병합 전 스냅샷 `restore_notice`] · ocr_members · own_broadcast · participation). 새 기록은 `parent_id`·`by` 로 이어지고 다시 반려 가능, 한 기록의 후속은 한 번(`followup` 선점). 입력 없는 옛 기록은 재판단 불가. 코드: `telegram_app._llm_review`·`_REVIEW_RUNNERS`, API `rejudge_llm_action`·`decide_llm_action`·`llm_review_options`(POST). 검증 `ref/v4a/verify/harness_c.py`(52개).
>     흐름에 표시(`flowtrace.add_llm`) — 작업 탭 「최근 흐름」 **「LLM 판단」 필터**, 펼친 경로 재생 영역에 판단 · 근거 · **「되돌리기」**
>     (`admin_api.undo_llm_action` → 적용 큐 `llm_action` op=undo → `telegram_app._llm_undo`). 대상과 되돌리기: 방송 취소(되살림 + 재등록 차단 해제) ·
>     시각 변경(그때 바꾼 값이면 원래 값) · 본인 예고 최종 확인(등록한 예고 지움 / 합쳤으면 합치기 전으로) · 외부 채널 참여(등록 지움) ·
>     게스트 확인(더한 게스트 뺌) · 그룹 영상 이미지 OCR(예고에서 빼고 「확인 대기」로, OCR 제안 유지). **그때 바뀐 항목만** 되돌리고 그 뒤 다른
>     이유로 바뀐 항목은 건너뛴다(결과에 표시). "아님" 판단(예고 아님 · 참여 아님 · 게스트 아님 · 취소 아님) · 소식 중복 판정은 **검토용**(되돌릴
>     데이터 없음 — 원문 투입으로 직접). 번역 · 소식 제목 추출은 판단이 아니라 제외. 관리자가 미리보기로 확인하고 확정한 조작도 제외.
>     한 번 되돌린 판단은 다시 되돌릴 수 없다. 공식 일일 스케줄 합동 줄의 LLM 게스트 재확인(`_confirm_relay_rows_collab`)은 10-01 부터 게스트를
>     **빼는** 판단만 검토용으로 기록(`collab_guest` — 키 없음 · 5회 실패로 빈 경우는 판단이 아니라 기록 안 함).
>   - **2차 검증 후속 수정(2026-10-01, v4a 만 — 운영 main 반영은 시험 운영 뒤 한꺼번에 D32)**: ① 알림 레벨 표(`notify._LEVEL_KINDS`)에 없는 옛 이름
>     `scheduled` 로 보내던 `_auto_dm` 4곳(URL 확정 예고 · 본인 예고 · 공식 일일 스케줄 요약 · 대기열 반영)을 `announced` 로(D29) — v3.0 부터 어느 레벨에서도
>     안 나가던 DM 이 normal 이상에서 나간다. **운영 main 은 여전히 안 나간다.** ② 멤버가 **공식 일일 스케줄을 인용**한 글의 영상 URL 이 본문엔 없고
>     인용문에만 있으면 작성자를 게스트로 넣지 않고, 이름 언급 게스트 찾기 · LLM 게스트 확인에도 스케줄 인용문을 쓰지 않는다(D28 —
>     `xrelay.is_daily_schedule` · `_maybe_url_confirmed_schedule`, 관리 페이지 미리보기 `_ingest_preview_raw_core` 도 같게). 실측 오탐 09-23 노노카 → 미야코 방송.
>     스케줄이 아닌 인용(09-22 리츠가 유노 예고 인용)은 그대로 작성자를 게스트로(`xtweet.resolve_url_host`). 한계: 인용문의 **첫 영상**을 처리하고 끝나므로
>     인용문 뒤쪽의 작성자 본인 영상은 이 글로는 안 잡힌다. ③ 예고 수정 `url` 은 http(s) 만(`admin_api.edit_preview`). ④ Windows 파일 교체 권한 오류
>     짧은 재시도(`local_store.replace_retry` — flows · recent_jobs · LocalStore · jobqueue). ⑤ 옛 `llm.broadcast_change` 삭제(→ `broadcast_change_targets`).
>   - **10-01 오후 후속(v4a)**: ① 관리 페이지 수정 팝업 「팬 화면 표시」가 같은 문장 2줄로 나오던 것 — 마퀴 조각 class `seg` 가 원문 투입
>     종류 버튼의 `.seg`(3열 그리드)를 물려받아 블록으로 쌓였다 → `mq-seg`. ② **LLM 판단 되돌리기 화면 표시** — 누르면 버튼이 「되돌리는 중…」으로
>     잠기고(두 번 눌림 방지), 응답 뒤 흐름도가 마지막 단계부터 LLM 이 판단한 단계(준비 · Groq)까지 거꾸로 감긴다(`rewindFlow` — 지나간 단계 노랑 점선
>     「↩ 되돌림」 · 화살표 반대, 판단 단계 초록 「↩ 판단 되돌림」, 결과 칸 「→ ↩ LLM 판단 되돌림 — 내용」). 끝나면 판단 칸이 초록으로 번쩍이고 버튼은
>     없어지지 않고 **「되돌려짐!」 비활성**으로 남는다(운영자 요청). 흐름 목록 태그 「LLM 판단 n · ✓ 되돌림」. 이미 되돌린 흐름을 열거나 다시 재생해도
>     같은 모습. 번쩍임은 감길 때 한 번만(`flashOnce` — 끝나면 클래스를 뗀다. 안 떼면 5초 갱신이 상세를 다시 붙일 때마다 재생돼 주기적으로 번쩍였다). 전엔 토스트 3초뿐이고 상세가 안 바뀌어(흐름 기록이 그대로라 다시 그리지 않음) 두 번 누르게 됐다. ③ 작업 탭 「최근 자동 처리」 —
>     `llm_action` 등 내부 이름을 우리말로, 되돌리기는 「↩ LLM 판단 되돌리기 — 내용」(`apply._brief` 에 `op`). ④ **멤버 리트윗 판정**(운영 v3.8.11 과
>     같은 수정 — `telegram_app._personal_retweet_reason`, 운영 쪽은 PR #50 열림 · 병합 · 배포는 운영자 결정): `/ingest` 가 원문을 vxtwitter 본문으로
>     바꾸면 리트윗 표시(`@핸들:`)가 사라져 D17 필터가 무력화돼 있었다(10-01 미야코가 애니 재방송 안내를 리트윗 → 가짜 「10/01 23:00」 예고). 교체 전 폰
>     원문의 `@핸들:` · vxtwitter 작성자 ≠ 멤버 handle 이면 건너뜀. **응답 서비스에 따라 다르다** — vxtwitter 는 리트윗 자체(`RT @…:` 본문, 작성자 =
>     리트윗한 계정), fxtwitter(폴백)는 원 글 본문 + 원 작성자 + `reposted_by`. 이 PC 에서는 vxtwitter 가 자주 403/500 이라 fxtwitter 로 떨어진다.
>     ⑤ **쓰기 대기 · 결과 DM**(`writeclient._Progress`, 2026-10-01 운영자 결정 — v4a 만, 운영 v3 는 핫픽스 안 함): 2초 넘는 쓰기의 「⏳ … 처리 중」과
>     짝 DM 을 **알림 레벨 「자세히」에서만**(notify `_LEVEL_KINDS` detail 의 `progress`), 짝 DM 은 「처리 완료」가 아니라 **실제 결과**(✅ 추가 · 갱신 ·
>     반영 / ☑️ 안 올림 — 지난 소식과 같은 글(recap) · 이미 본 글 · 바뀐 것 없음 / ⚠️ 실패). 적용 큐(로컬)와 `/write`(배포) 두 경로 공용 — 전엔 로컬
>     경로엔 이 DM 이 없었다. 계기: 운영이 recap 으로 끝난 소식에 「✅ 처리 완료 [소식 제목]apply_notice」를 보내 올라간 것처럼 읽혔다.
>     ⑥ **「공식」 경로 = @BDP_yumemita 가 직접 쓴 글만**(10-01 운영자 결정 · 구현, v4a 만): 소식 · 공식 스케줄 판정 **전에**
>     `telegram_app._official_skip_reason` — 리트윗 표시(`_retweet_mark`: 폰 원문 `@핸들:` · vxtwitter `RT @…:` 본문 · fxtwitter `reposted_by`,
>     `vxtwitter.extract` 가 돌려줌) → 작성자(vx/fx)가 그룹 핸들 아님 → 작성자를 모르면 알림 표시명이 「夢限大みゅーたいぷ」로 시작 안 함 순으로 건너뛴다
>     (monitor `relay` 「mode: none · 공식 글 아님 · …」). 전엔 개인 5인 표시명이 아닌 알림은 전부 공식 경로라, fxtwitter 로 떨어지면 남의 글 리트윗이
>     소식이 될 수 있었고 **「バンドリ！アワーノーツ」(게임 계정) 글이 소식으로 올라가고 있었다**(09-30~10-01 추가 8 · 갱신 2 — 게임 공지와 5th Single 발매 소식.
>     이제 안 올라간다 — 그 계정을 허용할지는 운영자 확인 대기, `ref/v4a/v4a_remaining_0930.md` §3-6). ⑦ 작업 탭 흐름 결과에 소식 판정
>     (`_NOTICE_VERDICT` — 「스케줄 형식 아님 · 소식 추가 / 소식 안 올림 — 이미 본 글 / 소식 아님」, 전엔 소식 쓰기가 돌면 무조건 「소식으로 반영」).
>     ⑧ **리포트 백엔드 상태 막대**(`monitor_report.py`, v4a 만 — 운영 main 은 표시 버그라 핫픽스 안 함, 운영자 결정): 하루 끝(1440분)이 `fmtHM` 으로
>     「06:00」이 돼 마지막 정상 구간(마지막 기록 tick 이후)이 1px · 누계 누락이던 것(v3.5.0 부터) → `segLabel` 로 「30:00」. 오늘은 `day.nowHm`(현재 시각)까지만
>     칠하고 누계 % 도 관측 시간 기준(`dayEndMin`). + v4a 한정 타임라인 「현재 시각까지」 흰 반투명 배경(`REPORT.runMark` = `V4A_RUNTIME=local`,
>     트리거 기준선 ~ 개인 트윗 미야코 줄 아래, x=0 ~ 지금).
>     ⑨ **트윗 수명 = X 게시 시각 + 48h**(10-01 운영자 결정, D18 의 기준 변경): `xtweet.parse` 가 `posted_at`(Snowflake) 저장,
>     `expires_at = posted_at + 48h`(게시 시각 모르면 `received_at` + 48h) — 48h 지난 트윗은 `merge_thread` 가 `stale` 로 안 올린다.
>     관리 페이지 트윗 투입(자동 URL · 수동)은 경고창 「게시된지 48시간이 지난 트윗입니다.」(`admin_api._tweet_too_old` → `too_old`).
>     팬 화면(`tweets.js`) 말풍선 아래 시각 · 정렬 · 묶음 = 게시 시각(못 얻으면 받은 시각 + 「등록」). 하네스 가짜 트윗 id 는 실행 시각 기준(`harness.TP`).
>     유실 원문 재투입(관리 페이지)도 같은 논리(`admin_api._lost_tweet_stale`, 10-01 운영자 결정): **멤버 트윗**이 게시 48h 지났으면, 그 트윗이 알린 방송이
>     아직 유효할 때(예정 · 라이브 · 끝났어도 end 창 = 종료 + 30분 `statemachine.END_WINDOW_SEC` 안 — end 단계에서 다시 켜는 경우 대비)만 재투입하고,
>     아니면 재투입하지 않고 경고창(「게시된지 48시간이 지난 트윗입니다.」 + 끝난 방송이면 「이미 끝난 방송입니다 (종료 + 30분 지남).」), 항목은 큐에 남긴다.
>     영상 URL 이 있으면 `videos.list` 로, 없으면 본문 예고 파싱(게시 시각 기준)의 `expires_at` 으로 판단. 공식 계정 원문(소식 경로)은 대상 아님.
>     (운영자는 「live 종료 + 20분」이라 했으나 코드의 end 창이 30분이라 30분으로 맞춤 — 운영자 확인 10-01.)
>   - **행사 배너**(2026-10-02, v4a 만): 게임 계정(`config/channels.json` `game_accounts` — `bang_dream_on`, 표시명 バンドリ！アワーノーツ)의 글은 소식 · 스케줄이 아니라
    **행사 판정**(`llm.banner_judge` → `banners.apply_judgement`)으로만 간다 → 소식 란 펼침 맨 위 **행사 카드**(안에 딸린 가챠 하위 블록, `banners.json`, 프론트 `js/banners.js` · `css/banners.css`).
    **개최 전 공지는 종료일을 몰라도 올림**(시작 일시를 먼저 알림), 시작한 뒤에도 종료일 없는 행사 · 상시화 행사는 안 올림(대기로 저장), 개최 보류는 `mm.dd(보류)` + 15일,
    디자인 = 흐린 이미지 배경 + 절취선 카드(종료 일정 박스 두 칸 · 진행 막대: 늦은 종료 100% · 먼저 끝나는 종료는 점선 · 점선 이후 `///` · 달력 D-3 부터 노랑 · 점선을 넘으면 빨강 · 말풍선 꼬리는 현재 위치),
    **모두 종료돼도 그날 자정(KST)까지 회색 「종료」로 표시**,
    이미지는 **X 트윗의 행사 키비주얼만**(링크만, 가챠 이미지 · 소개 카드 · 출처 불분명한 배너는 안 씀, 여러 장이면 5초 한 방향 슬라이드),
    개최기간이 이미지에만 있는 글은 비전(`vision.read_card`)으로 읽어 재판정(2단계). 게임 계정 글이 아니어도 행사 · 가챠 이름이 본문에 있으면 소식으로 안 올림(`banners.covers_text`).
    LLM 판단은 작업 탭 「LLM 판단」(`kind=banner_judge`)에 기록 · 되돌리기(`restore_banner`). 관리 페이지 「소식 · 트윗」 탭 맨 위에서 수정 · 삭제.
    용어 `docs/TERMINOLOGY.md` 「행사 배너 용어」, 계약 `docs/SPEC.md` 계약 J, 설계 · 구현 결과 `ref/v4a/v4a_event_banner_design.md`.
    **운영 v3.8.10 에는 없음**(운영은 아직 이 계정 글을 소식으로 올린다).
  - **모바일 UI**(2026-09-30, `admin.html` 한 파일, ≤640px 미디어 쿼리): 하단 고정 탭 바(7탭 아이콘+글자) · 버튼 44px/입력 16px(iOS 확대 방지) ·
>     수정·참여 멤버 팝업은 바닥 시트 · 토스트는 탭 바 위 · 원문 투입 미리보기 시 결과 카드로 자동 스크롤. 높이 제한 스크롤 목록(`.flows`/`.jlist`/`#jobs-tl`)은
>     `grid-auto-rows: max-content` — 안 그러면 button `min-height` 때문에 줄이 눌려 서로 겹친다. 작업 탭 「최근 흐름」의 경로 재생 영역은 누른 줄 **바로 아래**로
>     펼쳐지는 아코디언(`toggleFlow`/`placeFlowDetail`, 같은 줄 재클릭 = 접기, 다른 줄 = 접은 뒤 이동), 5초 갱신 때도 유지. 데스크톱도 동일.
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
                       #   /monitor(Scheduler, v3.8.9: 모니터링 스냅샷 + 멤버 현황 텍스트 DM) · `/` 헬스체크(GFE 가 /healthz 가로챔)
    handlers.py        # (v3) tick/wake → preview_build → (v3.7.1) apply_overrides → preview.json 커밋
                       #   + LLM 말단 번역(needs_tl sweep) + (v3.7.1) 모니터 로그 실행당 1커밋·무변화 스킵
    writers.py         # (v3.7) /write 잡 kind → telegram_app 커밋 함수 매핑(지연 import).
                       #   (v3.7.1 A-1) 잡은 커밋 전용 — 외부 호출은 제어 채널에서 준비해 인자로 넘김
    writeclient.py     # (v3.7) 제어 채널 → 백엔드 /write 동기 호출(OIDC, 60초). MAIN_SERVICE_URL 없으면 로컬 디스패치
                       #        (v3.9) HTTP 429/503 만 지수 백오프 재시도(1.5→3→6→12→20초 +지터,
                       #        최대 45초). 429 는 Cloud Run 이 컨테이너 배정 전에 거절한 것이라
                       #        중복 커밋 위험이 없어 재시도가 안전. 네트워크 예외는 서버가 이미
                       #        처리 중일 수 있어 재시도 안 함
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
    push_monitor.py    # (v3.8.9 부터 미사용 — 삭제 후보) (v3.5, 구 v3.4 대시보드에서 축소) `_CODE_REPO`(main/devpapers 등
                       #        코드 브랜치 고정 저장소) + fetch_commits/list_branches만
                       #        남음 — v3.8.8 까지 monitor_report.py 의 Vercel push count 계산용.
                       #        v3.8.9 에 Vercel REST API 배포 시도 수(`_vercel_deploys`)로 대체돼 안 쓰임.
                       #        옛 대시보드(카테고리별 누적 막대+날짜 히트맵) 코드는
                       #        git 이력(v3.4.14 이전)에만 남아있음.
    monitor_log.py     # (v3.9) _monitor_gh(gh) — 넘겨받은 store 의 브랜치만 MONITOR_BRANCH
                       #        (기본 monitoring)로 바꾼 복제본 반환. log_event/log_events 가
                       #        내부에서 이걸 쓰므로 **호출부 49곳은 무수정**.
                       #        + 유실 원문 큐 push_lost/read_lost/write_lost
                       #        (monitoring/lost_queue.json, 최대 50건). push_lost 는 ConflictError
                       #        만 재시도하고 그 외 예외는 1회로 끝낸다 — 유실 처리 경로에서
                       #        호출되므로 여기서 7.5초를 더 쓰면 버스트를 악화시킨다. 예외 안 던짐
                       # (v3.5) 모니터링 이벤트 로그 — tick/wake/preview 전이/notice/tweet/
                       #        relay/운영자 `/pause`·`/resume` 마다 `monitoring/events-
                       #        YYYY-MM-DD.jsonl`(data 저장소)에 한 줄 append. 공통 필드
                       #        `ts/flow/result/who/detail` + 흐름별 추가 필드, `result`는
                       #        `ok`/`degraded`/`err`(성공/실패로 미리 안 뭉침). tweet/relay는
                       #        `via`(`ingest`|`ops`)로 자동/수동 구분. (v3.8.9) `flow="cmd"` —
                       #        제어 채널 명령 1건마다(telegram_app `_done()`). `flow="upstream"` —
                       #        업스트림 알림 1건마다(`/ingest` → `_ingest_impl` 래퍼). (v3.5.1) 하루 경계
                       #        `DAY_START_HOUR=6`(KST 06:00~익일 06:00) — 자정 넘겨 방송하는
                       #        멤버가 흔해서 00:00 경계 대신 씀. `bucket_date_kst()` 참고.
    monitor_snapshot.py # (v3.8.9) 모니터링 스냅샷 — 일별 `monitoring/days/YYYY-MM-DD.json` + 전 기간 요약
                       #        `monitoring/summary.json`(잔디) + 멤버 현황 DM 텍스트. `run_daily` 는
                       #        app.py `/monitor`(KST 06:10)가 monitor_auto 와 무관하게 매일 호출.
                       #        외부 조회 실패는 None(확인 불가), 로그 파일 없는 날은 no_log.
    monitor_report.py  # (v3.5) `/monitor` — 위 이벤트 로그 + healthchecks.io(백엔드 상태) +
                       #        Vercel 배포 시도 수(v3.8.9, Vercel REST API · Secret VERCEL_TOKEN.
                       #        구 push_monitor.fetch_commits 커밋 수 근사 대체)를 모아 트리거→
                       #        preview/릴레이/소식/개인트윗 Ops Timeline HTML 생성(html은
                       #        커밋 안 하고 텔레그램 DM 으로만). (v3.5.1) `monthly=True`
                       #        (`/monitor --monthly`, v3.8.5 이전 이름 `--full`)면 이번 달
                       #        1일~오늘 전부를 `REPORT.days`에 담아 리포트 안 "월간 추이"
                       #        그리드(잔디)로 날짜 전환(재요청 없이 클라이언트 쪽 전환) 가능.
                       #        (v3.8.5 핫픽스) `yearly=True`(`/monitor --yearly`)는 같은
                       #        방식으로 올해 1월 1일~오늘(또는 `date_kst` 기준 그 해) 전부를
                       #        "연간 추이" 그리드로 담는다 — 날짜당 최대 366회라 `date_kst`로
                       #        지정한 날 외엔 healthchecks.io/Vercel 조회를 건너뛴다
                       #        (`_build_day(fetch_external=False)`). 기본(`/monitor`,
                       #        `--auto`)은 하루치만. (v3.8.9) 자동 실행(KST 06:10)은 더 이상
                       #        HTML 을 안 보낸다 — 모니터링 스냅샷 + 멤버 현황 텍스트 DM(`monitor_snapshot`).
                       #        웹 monitor(`/monitor-live`)는 `snapshot_report()` 전 기간(all) 형식.
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
                       #        (v3.9) /ingest --retroactive — monitoring/lost_queue.json 의
                       #        유실 원문을 **한 건씩 순차** 재투입(동시 발사가 애초 유실 원인).
                       #        kind 별 분기(personal_tweet/notice/route 재판정) · 개별 try/except ·
                       #        **성공한 항목만 큐에서 제거**(실패분은 남아 다음에 재시도).
                       #        _dm_lost_raw(reason, raw, kind/channel_key/tag/gh) 도 같은 버전 —
                       #        DM 전량 회신 + 큐 적재를 함께 한다(4지점에서 호출)
                       #        (v3.5, 구 /push-monitor) /monitor [--auto|--off|--monthly|
                       #        --yearly|YYYY-MM-DD] — Ops Monitor 리포트 즉시 DM / 자동
                       #        실행 on-off / 이번 달 전체(월간 그리드) / 올해 전체(연간
                       #        그리드, v3.8.5) / 특정 날짜. `--monthly`는 v3.8.5 이전엔
                       #        `--full`이었음(이름만 변경).
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
monitoring 브랜치 (v3.9) # 데이터 저장소의 로그 전용 브랜치. `data` 에서 분기해 만들었으므로
                       #   기존 monitoring/ 파일이 히스토리째 승계됨(이관 스크립트 없음).
                       #   monitoring/events-YYYY-MM-DD.jsonl (이벤트 로그, 06:00 KST 경계)
                       #   + monitoring/latest.html (모니터 스냅샷)
                       #   + monitoring/lost_queue.json (유실 원문 큐 `{"pending":[...]}`, 최대 50건)
                       #   **data 브랜치 HEAD 와 경합하지 않게 하는 것이 존재 이유** — 이 로그들은
                       #   /write 직렬화 창구를 안 거치고 제어 채널이 직접 커밋하는데, 제어 채널은
                       #   인스턴스가 최대 20개라 버스트 때 data 브랜치 쓰기를 409 로 밀어냈다(v3.9).
                       #   env MONITOR_BRANCH 로 지정(기본 monitoring).
                       #   ※ 이 브랜치는 **데이터 저장소에만** 있다 — 코드 저장소의 vercel.json 과
                       #   무관(Vercel 은 코드 저장소만 본다). vercel.json 은 `"*": false` +
                       #   `"main": true` 라 main 외 전부 이미 차단되므로 손댈 것 없음
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
python -m src.backend.monitor_snapshot # (v3.8.9) 백필 날짜 선정·요약·멤버 현황 DM 텍스트·run_daily 멱등 (mock)

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
- **버전 표기 — 후속 패치는 `vX.Y.Z[a-z]`** (2026-09-23 사용자 확정): vX.Y.Z 의 후속 패치가 생기면 새 번호를
  올리지 않고 v3.8.9 → v3.8.9a → v3.8.9b … 로 붙인다. 커밋 메시지(`fix(v3.8.9a): …`)·PR 제목·코드 주석·문서
  (`docs/VERSION.md` 항목 등) 모두 같은 표기. "vX.Y.Z 후속" 같은 다른 표기를 임의로 만들지 말 것. 후속 순서는 푸시된
  시간순(옛 후속 대응표: `docs/VERSION.md` 머리말). 이미 머지된 커밋 메시지는 그대로 둔다.
- **버전 번호 올리는 기준** (2026-09-25 사용자 확정):
  - **핫픽스**(새 요소가 아닌 버그 수정)는 **패치 번호 Z 만** 올린다 — `v3.8.Z` 계열에 이어 붙인다.
    새 요소가 아니므로 마이너(Y)를 올리지 않는다. 예: v3.9 배포 이후의 핫픽스도 v3.9a·v3.9.1 이 아니라 **v3.8.10**.
  - **기능**(새 요소)일 때만 마이너 Y 를 올린다(예: v3.9).
  - **알파벳 접미사 `[a-z]` 는 패치 분기가 발생할 때만** 쓴다 — 같은 패치 번호에서 갈라진 후속이 생긴 경우.
    단순히 "다음 핫픽스"에 알파벳을 붙이지 말 것(잘못된 예: v3.9 다음 핫픽스를 v3.9a 로 표기 — v3.8.10 으로 정정됨).
