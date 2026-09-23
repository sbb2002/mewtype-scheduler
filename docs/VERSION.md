# VERSION

버전별로 무엇이 추가·변경·제거됐는지 내림차순으로 요약한다.

**후속 패치 표기 (2026-09-23 확정)**: vX.Y.Z 의 후속 패치는 **vX.Y.Z[a-z]** 로 붙인다(v3.8.9 → v3.8.9a →
v3.8.9b …). 커밋 메시지·PR 제목·코드 주석·문서 모두 같은 표기. 이 규칙 이전 표기 중 코드 주석 "v3.8.5 후속"은 v3.8.5a 로
바꿨고, "v3.8.7 후속" 주석 11곳은 실제로 v3.8.7 본 커밋(`0007d29`)·v3.8.8 커밋으로 올라간 코드라
"v3.8.7"로 바꿨다(사용자 결정). 이미 머지된 커밋 메시지는 그대로 둔다.

후속 순서는 **푸시된 시간순**. 이 규칙 이전 후속 패치의 대응(커밋 시각 기준, 이미 머지된 커밋 메시지는 그대로):

| 새 표기 | 커밋 | 시각(KST) | 원래 메시지 표기 |
|---|---|---|---|
| v3.8.4a | `5400812` | 09-22 13:42 | v3.8.4-후속 |
| v3.8.4b | `78bf871` | 09-22 14:01 | v3.8.4-후속2 |
| v3.8.4c | `652988d` | 09-22 15:12 | v3.8.4-후속3 |
| v3.8.5a | `12dd80e` | 09-22 22:59 | (코드 주석 "v3.8.5 후속" — 이 커밋에 함께 실림) |
| v3.8.6a | `12dd80e` | 09-22 22:59 | v3.8.6 후속 |
| v3.8.7a | `a557918` | 09-22 23:36 | v3.8.7 후속 |
| v3.8.9a | `4b176e4` | 09-23 13:41 | v3.8.9 후속 |

- **v3.8.9a** (v3.8.9 의 후속 패치 — 웹 monitor UI·과거 소급)
  1. **모바일 전체 추이 가로 스크롤 제거** — 잔디+주간 막대를 한 줄에 그리면 약 490px 라 폰에서 가로 스크롤이
     생겼다. 640px 이하에선 잔디 칸 크기를 화면 폭에 맞추고(390px 폭 실측: 262px/영역 291px), "📊 주간요약 보기"
     버튼(타임라인 "요약 보기"와 같은 모양·모바일 전용)으로 잔디 ↔ 주차별 막대(주 날짜 범위 라벨)를 토글. 선택은
     60초 자가갱신·월 탭 전환 뒤에도 유지. PC 는 그대로.
  2. **데이터 0건인 월 탭 비활성** — 요약/상세 어디에도 그 달 날짜가 없으면 disabled(보고 있는 달은 예외).
  3. **업스트림 감지 아이콘 = 메인 화면 preview 네임플레이트의 X·YouTube 아이콘**(`render.js` `X_ICON_D`·
     `YT_ICON_D` 그대로, 13px, 밝은 글자색)을 결과색(정상 초록/에러 빨강) **둥근 네모 테두리**(20px) 안에 —
     결과색 채움은 없앴다(사용자 결정). 네모 안쪽은 타임라인 바탕색(`--panel`)으로 채운다 — 투명이면 먼저 깔린 트리거
     세로선·행 가로선이 네모 안으로 비쳐 선이 아이콘 위에 올라간 것처럼 보였다(그리기 순서는 원래 선이 먼저).
  3-1. **트리거 우측 요약** — `트리거 N건 (실패 M)` 한 줄 → 백엔드 상태 요약과 같은 줄 스타일 두 줄:
     `[초록 네모] 정상 n건` / `[빨강 네모] 실패 m건`(실패 0건이어도 표시, 호버 시 전체 건수). 기준선 위(막대 쪽)에 배치.
  3-2. **소식·개인 트윗 우측 요약 막대에 `N건` 라벨** — 이 막대는 누적이 아니라 그날 전체 건수 단색 막대(초록).
     패널 폭은 그대로 두고 막대 최대 길이에서 라벨 자리(46px)를 빼 가장 긴 막대+라벨도 패널 안에(0건은 흐린 `0건`만).
     모바일("요약 보기")은 패널 폭을 행 라벨 옆 남은 폭에 맞춤 — 고정 234px 라 390px 폰에서 10px 가로 넘침이 원래
     있었다(라벨 64 + 패널 235 > 289). 실측: PC 텍스트 끝 196/234px, 모바일 185/223px, 넘침 0.
  3-3. **타임라인 시간 틱 세로 그리드선(`.tl-hour`) 제거** — 시간 라벨만 남김(트리거 위치 점선 가이드는 유지).
  4. **과거 소급** (`monitor_report._derive_upstream` / `_derive_cmd`) — 실제 기록이 없던 시각(그날 첫 실제 기록 이전)의
     알림·명령을 기존 로그에서 복원해 같은 행에 그리고 팝업·표에 "(이전 로그에서 복원)" 표시:
     - 업스트림: `/ingest` 한 요청이 남기는 기록 규칙대로 — 개인 트윗은 (ts, 멤버) 하나 = 1건(부가 기록 포함), 공식은
       최종 relay 1줄(`mode: …`) = 1건(같은 초 소식은 거기 붙임), `mode: yt-member-live` = YouTube 1건. 같은 초에 여러
       알림이 몰리는 실례(2026-09-20 01:29:53Z, 멤버 4명 + 공식)가 있어 "같은 ts = 한 요청"으로는 묶지 않는다.
     - 운영자 명령: `/pause`·`/resume`(ops), `/del`·`/edit` 로 생긴 preview 기록, 수동 `/ingest`(via=ops). 응답 DM 은 기록이
       없어 비움.
     - 생략(복원 불가): via 없는 옛 소식(자동/수동 구분 불가), `[백필]` 기록(사후 복원, 실제 알림 아님), 로그를 안 남긴
       요청(무시·ECHO·조회성 명령).
     트리거 📥·잔디 숫자도 이 업스트림 건수 기준(복원 못 한 건 세지 않음).
  5. **실시간 기록 이전 날짜** — 2026-09-09~09-14 로그는 전부 `[백필]`(실시간 모니터링은 09-15 부터). 트리거 수를
     알 수 없어 잔디에 숫자 대신 `?`, 툴팁 "실시간 기록 이전(사후 복원 기록만)"(`backfillOnly` / 요약
     `{backfill_only:true}`). v3.8.9 로 보면 이 날들이 2~58건으로 보였는데 전부 백필 기록을 센 값이었다.
  6. **검증** — self-test(복원 규칙: 같은 초 분리·부가/백필 제외·실제 기록 이후 미복원) 통과, 공개 data 저장소 실데이터로
     복원 결과 확인(9/20 알림 51건·YouTube 1건, 9/22 30건·명령 1건), 390px 폭 iframe 에서 잔디/주간요약 토글·가로 스크롤
     없음, PC 에서 아이콘·복원 팝업 확인.
  7. **배포 순서 주의** — 모니터링 스냅샷은 한 번 찍으면 다시 안 만든다(`run_daily` 는 요약에 없는 날짜만). 첫 06:10
     실행 전에 이 버전을 배포해야 과거 날짜 스냅샷에 복원분·`backfillOnly` 가 들어간다.
- **v3.8.9** (핫픽스) — 웹 monitor(버전태그 이스터에그)를 **전 기간 리포트**로 전환하고, KST 06:10 자동 실행을
  "HTML 리포트 DM" → "전일 모니터링 스냅샷 + 멤버 현황 텍스트 DM"으로 바꿈. 이스터에그로 언제든 볼 수 있어 일간 HTML DM 이
  불필요해졌고, 월간/연간도 페이지 안 잔디로 흡수.
  1. **모니터링 스냅샷** (`monitor_snapshot.py` 신규, `app.py` `_monitor()`, 용어집 등재) — 지난 날짜 이벤트 로그는 06:00 경계 뒤로 더
     안 늘어나므로 하루가 끝나면 한 번 계산해 `monitoring/days/YYYY-MM-DD.json` 에 굳히고, 잔디용 요약을
     `monitoring/summary.json` 에 쌓는다. **monitor_auto 와 무관하게 매일** 찍힌다(`/monitor --off` 는 DM 만 끔).
     최초 실행은 `monitoring/` 의 기존 `events-*.jsonl` 로 과거 날짜를 백필(로그 파일이 있는 날만, 실행당 10일 —
     실데이터 기준 2026-09-09~ 이라 첫 실행 뒤 한 번 더 돌아야 다 채워짐), 이후엔 스케줄러 누락분만 메운다.
  2. **추측 금지** (`monitor_report.py`) — healthchecks.io 다운 구간·Vercel 수치 조회 실패/키 없음을 예전엔
     `[]`/`0` 으로 채워 조회 여부가 데이터에 안 남았다. 이제 `None` 으로 저장·전달한다. 표시: Vercel 은
     `? / 100 확인 불가`. 백엔드 상태는 **기존 합의대로 정상으로 그린다**(healthchecks.io 를 날짜마다 몰아 부르지
     않기 위한 근사 — v3.5 설계·v3.8.5 연간 리포트) — 막대 툴팁에만 "미조회 — 다운 없음으로 간주"를 밝힌다.
     그날 이벤트 로그 파일이 없으면 `hasLog:false` / 요약 `{no_log:true}` — 잔디는 숫자 대신 `?`(0건인지 기록
     누락인지 구분 불가).
  3. **웹 monitor 전 기간화** (`telegram_app.py`, 템플릿 JS) — `/monitor-live(.json)` 은 오늘 상세 + 전 기간 요약
     (잔디 제목 "전체 추이", 연도 2개 이상이면 연도 탭). 지난 날짜 칸을 누르면 `/monitor-live/day.json` 으로 그날만
     불러온다(스냅샷 없으면 이벤트 로그에서 즉석 계산, 페이지 상단에 출처 표시). 60초 자가갱신은 여전히 오늘치만
     다시 계산 — 지난 날짜 파일을 반복해서 읽지 않는다. `latest.html` 폴백도 같은 형식(전날 상세 + 잔디).
  4. **DM** — 전일 "오늘의 멤버 현황"(멤버별 트윗 ✓/✕ · 라이브 구간 · 소식 등록 성공/실패) 텍스트만. 하루 경계를
     넘긴 라이브는 `익일 06:00 넘어서까지`, 06:00 이전부터 이어진 라이브는 `06:00 이전부터`로 표기(경계에서
     끝/시작했다고 단정하지 않음 — 선행 세그먼트에 `carried` 표시 추가).
  5. **버그 수정: 자정 넘긴 라이브 시간** — 멤버 현황의 라이브 구간이 `23:33 ~ 01:15` 를 `0분`·"익일" 없이
     표시하던 것(`hmToMin` 이 실제 시각을 06:00 기준으로 안 바꿈)을 `minutesOf` 기준으로 고침(실데이터 2026-09-22
     아라레 방송 → `23:33 ~ 익일 01:15 (102분)`).
  6. **Vercel 한도 수치 = Vercel REST API 실제 배포 시도 수** (`monitor_report._vercel_deploys`) — v3.8.8 까지는
     GitHub `main` 커밋 수로 근사했다(`push_monitor.fetch_commits`). push 1회에 커밋이 여러 개면 부풀고, 다른
     브랜치 preview·실패 배포는 못 셌다 — 2026-09-22 실측 커밋 16 / 실제 `main` push 7 / Vercel 배포 시도 18
     (production 7 · preview 11 · ERROR 2). 이제 `/v6/deployments` 를 그날 06:00~익일 06:00 KST 로 조회해
     `vercelDeploys = {total, production, preview, error}` 로 저장(구 `vercelPush` 숫자 필드 대체), EXT 탭은
     "배포 시도 N / 100"(타일 툴팁에 내역). Hobby 한도엔 브랜치·성공 여부 무관하게 다 잡히므로 total 기준.
     토큰 = 새 Secret `VERCEL_TOKEN`(두 서비스, Secret 있을 때만 마운트 — `deploy.sh`·`deploy_telegram.sh`·
     `setup.sh`). 프로젝트/팀 ID 는 비밀값 아니라 코드 상수. API 한도 실측 약 1분당 1,000회(응답 헤더) —
     웹 monitor 60초 갱신 1회는 무시 가능. `push_monitor.py` 는 이제 어디서도 안 쓰인다(삭제 후보, 이번엔 유지).
     GCP Secret Manager 에 `VERCEL_TOKEN` 등록 완료(2026-09-23, 저장값으로 조회 검증) — 두 서비스는 다음 배포부터 연결.
     EXT 패널 설명문도 "push 카운트" → "Vercel API 실제 배포 시도 수"로 교체.
  6-1. **타임라인 "💬 운영자 명령" 행** (트리거와 백엔드 상태 사이) — 제어 채널(텔레그램 DM)로 온 요청 1건 = 점 1개.
     그전엔 `/pause`·`/resume` 만 트리거 레인(🎛️)에 찍히고 나머지 명령(`/list /del /edit /ingest /monitor` …)은
     기록 자체가 없었다. `telegram_app` 웹훅의 모든 반환이 지나는 `_done()` 에서 `flow="cmd"` 이벤트 1줄
     (`who`=명령어, `detail`=명령 원문 120자, `reply`=마지막 응답 DM 첫 줄 100자). 점 색/팝업의 결과는 **응답 DM
     문구로 판정한 근사**(핸들러가 결과를 반환하지 않고 DM 으로만 알려서): 처리 중 예외·⚠️/❌ 응답 = 에러,
     "사용법" 안내·안전망(응답 누락) = 부분 실패, 그 외 정상. 이벤트 로그는 공개 data 저장소라 `/` 로 시작하지 않는
     후속 입력(y/N·마법사 답·원문 붙여넣기)은 12자 이하 한 줄만 그대로, 나머지는 글자 수만 남긴다. 명령 원문·응답
     요약은 툴팁/표에 escape 해서 넣는다. 트리거 수(잔디)엔 안 넣음. `/pause`·`/resume` 은 기존 🎛️ 트리거와 이 행
     양쪽에 찍힌다(백엔드 동작 트리거 vs 명령 요청 — 역할이 달라 유지). 로그 기록 실패는 웹훅 응답에 영향 없음.
     트리거 행은 막대가 기준선에서 위로만 자라 기준선 아래 절반이 늘 비어 있었는데, 기준선을 행 높이의 80% 지점으로
     내리고(`baseFrac`) 행 높이를 96→60(좁은 화면 88→56)으로 줄여 그 빈 공간에 이 행을 넣었다(막대 최대 높이 영역은 동일).
  6-3. **"📣 X 예고 릴레이" 행 → "🛰️ 업스트림 감지" 행** (운영자 명령 아래, 백엔드 상태 바로 위) — relay 행은
     preview·소식·개인 트윗과 역할이 겹쳐 주는 정보가 애매했다. 이제 업스트림(`POST /ingest`) 알림 1건 = 점 1개
     (`flow="upstream"`, `source` x|yt): X 알림은 X 로고, YouTube 알림은 ▶ 로고, 색 = 수신 처리 결과(빈 본문·처리 중
     예외 = 에러, 무시·일시정지 = 정상 수신). 팝업 = 발신자(`android.title`)·보낸 갈래(공식 스케줄 N건·개인 트윗·회원 방송
     시작·유튜브 TUNEIN 등). **콘텐츠가 어떻게 바뀌었는지는 담지 않는다**(요청 단위 묶음·preview 변화 추적은 범위 밖,
     사용자 합의) — 같은 시각의 preview·소식·개인 트윗 행을 함께 본다. 구현: `/ingest` 라우트를 `_ingest_impl` 로
     감싸 응답 본문에서 갈래를 읽어 기록(핸들러 무변경, 403 은 기록 안 함, 기록 실패는 응답 무영향). relay 파싱
     결과는 타임라인 행에선 빠지고 이벤트 표엔 남는다. 🎯 트리거의 📥 도 업스트림 이벤트 기준으로 — 그전엔
     relay·notice·tweet 로그에서 역산해 운영자 수동 `/ingest`(via=ops)까지 인입으로 셌다. 업스트림 기록이 없는
     옛 날짜는 역산을 유지하되 via=ops 는 제외(잔디 숫자도 같은 정의, `day_trigger_count`).
  6-2. **EXT YouTube quota 그래프에 일일 한도(10,000) 빨간 점선** — 한도선이 항상 보이도록 y 축 상한을
     max(누적, 10,000)×1.08 로(평소 누적은 수백 units 라 곡선이 바닥에 붙어 보이는 게 실제 비율).
  7. **잔디 주간 막대 색** — 초록(OK) → 잔디 칸과 같은 청록(hsl 175) 계통, 이 달 주간 합계 최대값 대비 명도.
  8. **검증** — `monitor_report`·`monitor_snapshot`(신규)·`gh_store`·`telegram_app` self-test 통과.
     `_vercel_deploys` 실토큰 조회: 9/22 = 18(같은 API 로 먼저 뽑아 건별로 본 배포 목록 18건과 일치 — Vercel 대시보드와는 직접 대조 안 함), 9/21 = 6, 9/13(사고일) = 75,
     잘못된 토큰 → None(확인 불가). 공개 data
     저장소 실데이터를 읽기 전용으로 쓰고 쓰기는 메모리에만 받는 로컬 서버로 `run_daily` 백필(10일)·DM 텍스트·
     `/monitor-live`·`day.json`(스냅샷/즉석 계산 양쪽)·`latest.html` 폴백을 브라우저에서 직접 확인. Flask 테스트
     클라이언트로 `/monitor` 라우트를 monitor_auto on/off 로 돌려 스냅샷은 둘 다, DM 은 on 일 때만 나가는 것 확인.
     **미확인**: 실 healthchecks 키로 과거 날짜 flips 가 얼마나 거슬러 조회되는지(보관 기간) — 조회 실패면
     "확인 불가"로 남을 뿐 틀린 값은 안 들어감. 배포 후 첫 06:10 실행 결과 확인 필요.
- **v3.8.8** (핫픽스) — 웹 monitor(`/monitor-live`)에서 타임라인을 클릭해 팝업을 고정(pin)하면
  60초 self-refresh 자체가 통째로 건너뛰어져, 오늘의 멤버 현황·우측 요약·표 등 타임라인과 무관한
  패널까지 같이 멎어 보이던 문제 수정. 사용자가 실배포판을 버전태그 이스터에그로 열어보다가
  발견("타임플롯 우측 요약이나 오늘의 멤버 현황이 업데이트 안되는 것 같다").
  1. **원인** (`monitor_report.py`) — self-refresh `setInterval`이 `if (... || isPinned()) return;`로
     tick 자체를 건너뛰었다. `isPinned()`는 타임라인 아무 곳이나 한 번 클릭하면 true가 되므로(팝업/
     흰 실선을 고정해서 찬찬히 보라는 의도), 그 순간부터 고정 해제 전까지 `loadDay()`가 아예 안 불려
     페이지 전체가 멈춰 보였다.
  2. **수정** — `loadDay(dateStr, opts)`에 `skipTimeline` 옵션 추가. self-refresh tick은 고정 여부와
     무관하게 항상 `REPORT`를 새로 받아 `loadDay(currentDate, { skipTimeline: isPinned() })`를 호출 —
     고정 중엔 `renderTimeline()`(SVG를 `innerHTML=""`로 통째로 새로 그려 고정해둔 팝업 위치가
     어긋나는 원인)만 건너뛰고, `renderStats()`/`renderRightPanel()`/`renderTable()`/`renderGrass()`
     등 나머지는 계속 최신화. 타임라인 그림 자체는 고정 해제할 때까지 그 시점 스냅샷으로 유지.
  3. **검증** — `python -m src.backend.monitor_report` 정상 실행(기존에도 있던 날짜 의존 assert
     실패 1건은 이 변경과 무관 — 변경 전 커밋으로 stash 대조해 동일 재현 확인). `render_html()`을
     최소 REPORT로 직접 호출해 HTML 생성 확인 후 내장 `<script>`를 `node --check`로 문법 검증.
     **미확인**: 브라우저 확장 미연결로 실제 클릭→고정→60초 대기→갱신 흐름은 직접 못 봄 — 배포 후
     실물 확인 필요.
- **v3.8.5** (핫픽스, v3.8.4 후속) - `/monitor --full` → `--monthly`로 개명 + `--yearly`
  (연간보고서) 신규 + 자동 실행(KST 06:00) 월간/연간 자동 대체.
  1. **개명(`monitor_report.py`, `telegram_app.py`)** - `--full`은 "이번 달 전체"라는 의미가
     이름에서 드러나지 않아 `--monthly`로 바꿨다(하위호환 없음 - 명시적 개명 요청). 내부
     `build_report(full=..., ...)`/`REPORT.full`/`REPORT.month`도 각각 `monthly`/`REPORT.
     monthly`/`REPORT.dates`로 맞춰 바꿨다(프론트 JS 포함).
  2. **`--yearly` 신규** (`_year_dates`, `build_report(yearly=True)`) - 올해(또는 `date_kst`가
     속한 해) 1월 1일~해당 날짜 전부를 "연간 추이" 그리드(월간의 잔디 그리드와 같은 구조,
     최대 366칸)로 담는다. 날짜당 healthchecks.io/Vercel 조회까지 366번 부르면 부하가 커
     `_build_day(fetch_external=False)`를 추가해 `date_kst`로 지정한 날짜 외엔 그 두 외부
     API를 건너뛴다(잔디 색은 이벤트 로그만으로 계산되므로 영향 없음 - 다른 날짜를 클릭해
     열면 그 날의 downRanges/vercelPush만 비어 보이는 게 알려진 한계).
  3. **자동 실행 월간/연간 대체** (`app.py` `_monitor()`) - 기존엔 매일 KST 06:10에 전일자
     하루치만 보냈다. 이제 그날이 **매월 1일**이면 하루치 대신 **전월** `--monthly`(anchor를
     전날=전월 마지막 날로 줘서 `_month_dates`가 그 달 전체를 계산), **1월 1일**이면 하루치
     대신 **전년** `--yearly`(anchor를 `전년-12-31`로 줘서 `_year_dates`가 그 해 전체를
     계산)를 대신 보낸다. DM 캡션에 `(월간)`/`(연간)`/`(일간)` 라벨을 붙여 구분.
  4. **타임아웃 상향** (`Dockerfile`, `deploy/deploy_telegram.sh`) - 자동 `/monitor`가 붙는
     백엔드(`mewtype-scheduler`) gunicorn `--timeout`을 120→300s로, 수동 `/monitor --yearly`
     명령을 받는 `mewtype-telegram`은 60→240s로 올렸다 - 날짜당 GitHub 읽기가 최대 366회로
     늘어 기존 값으로는 리포트 생성 도중 워커가 죽을 위험이 있어서(기존 `--monthly`도 최대
     31회라 60s에 근접하던 걸 이번에 같이 여유를 뒀다).
  5. **첨부 파일명** (`monitor_report.report_filename`) - 텔레그램 DM 첨부 파일명이 항상
     `monitor.html`로 고정이라 여러 건을 받으면 구분이 안 됐다. `monitor_YYYYMMDD.html`
     (daily) / `monitor_YYYYMM.html`(monthly) / `monitor_YYYY.html`(yearly)로 기간에 맞는
     자릿수만 남기도록 바꿨다. `run()`이 `{"html","date","events","filename"}`을 반환하도록
     확장(`telegram_app._handle_monitor`/`app.py _monitor()` 둘 다 이 filename으로 전송).
     `monitoring/latest.html`(내부 커밋 경로)·프론트 `monitor.html`(이스터에그 정적 페이지,
     `src/frontend/monitor.html`)은 별개라 안 건드림.
  6. **검증** - `python -m src.backend.monitor_report`(`_year_dates`/`build_report(yearly=True)`/
     `_build_day(fetch_external=False)`/`report_filename` 신규 케이스 포함)·`telegram_app`
     self-test 전부 통과. `bash -n deploy/deploy_telegram.sh`·`deploy/deploy.sh` 문법 확인.
     날짜/네트워크를 동결·모킹한 스크립트로 `/monitor`(무인자)·`--monthly`·`--yearly`·특정
     날짜·`--auto`/`--off`·잘못된 인자를 `telegram_app._handle_monitor`에 직접 통과시켜
     `monitor_report.run`에 넘어가는 kwargs·DM 캡션·첨부 파일명을 실측 확인, `app.py
     _monitor()`도 평일/매월1일/1월1일 세 날짜를 얼려 같은 방식으로 확인(모두 기대값과
     일치: 매월1일→전월 `--monthly`, 1월1일→전년 `--yearly`, 나머지→일간). 실배포 후 확인
     필요: 1월 1일/매월 1일 실제 자동 발사(다음 기회는 2026-10-01), `--yearly` 실측 소요 시간.
- **v3.8.4** (핫픽스) - 유튜브 앱 푸시(30분전·라이브 시작)가 `/ingest`에서 조용히 무시되던 문제 수정 +
  DM 가독성 + `/monitor` 타임라인 버그 2건. 2026-09-22 09:33 千石ユノ TUNEIN(30분전) 알림에 처리
  DM 이 안 왔고, 09:40 정기 tick 이 대신 주운 것이 계기.
  1. **원인** - `_handle_yt_relay`(`source=yt` 중계)가 `ytnotif.parse_member_live_relay` 한 함수만
     썼고, 이건 회원전용 라이브 시작(`SPONSORSHIPS_LIVESTREAM_START`) kind 만 처리한다. TUNEIN(30분
     전)·REMINDER·SUBSCRIPTION_LIVESTREAM_START(일반 채널 시작) 는 전부 `parsed is None` →
     `{"ok": True, "ignored": True}` 로 버려졌다 - DM 도, preview.json 반영도, 예약도 없이. 결과만
     10분 간격 `mewtype-light` tick 이 뒤늦게 주워담아 "이유 없이 늦게 반영"된 것처럼 보였다.
  2. **수정(1·2)** - `ytnotif.parse_public_live_relay`(신규): TUNEIN/REMINDER/SUBSCRIPTION_
     LIVESTREAM_START 를 폰이 이미 보내오던 폼(`source=yt&video_id&title&kind&tag`, 폰 쪽 변경
     없음)에서 파싱. `video_id` 가 실제 11자 ID 면(공개 채널 - 실측상 전부 해당) 새 GitHub 쓰기 없이
     `_enqueue_wake_now(video_id, now)` 하나만 호출 - 승격(announced/upcoming 자동 판정, live_state
     가 이미 live 면 곧장 live)·DM·모니터로그·다음 wake 예약은 기존 `/wake`(`handlers._run`) 파이프
     라인이 그대로 처리한다(새 병합 로직 없음). `video_id="default"`(회원전용 추정, 미확인 포맷)면
     TUNEIN 은 오판 위험이 커서 승격을 보류(기존처럼 무시, 정기 tick 안전망에 맡김)하고, REMINDER/
     SUB_START 는 기존에 검증된 회원-라이브(`SPONSORSHIPS_LIVESTREAM_START`) 경로로 위임한다.
     레이스(즉시-wake 대 정기 tick/wake)는 기존 `gh.write_json` 낙관적 동시성 재시도 + Cloud Tasks
     `wake-{video_id}-{분버킷}` dedupe + `build_preview`/FSM 의 멱등성으로 이미 방어돼 새 코드 없음.
  3. **수정(3·4)** - `writeclient.call_write(kind, *, label=None, ...)`: 대기 DM 에 내용 태그를 붙인다
     (`"⏳ 처리 대기 중… [千石ユノ 예고]merge_rows"`, `label` 생략 시 기존 `action=` 인자를 폴백으로
     재사용). 대기 DM 이 실제로 나간 경우에만 처리 종료 시 짝이 되는 완료(`✅`)/실패(`⚠️`) DM 을
     보낸다 - 예전엔 "처리 대기 중…"만 오고 끝났는지 알 길이 없었다. 2초 안에 끝나는 빠른 경로는
     기존과 동일(DM 없음, 각 핸들러의 자체 완료 DM 그대로).
  4. **수정(5·6·7, `/monitor`)** - 조사 중 원인 2건을 코드로 확정: (A) `handlers.py` 가 모니터 로그에
     `flow:"preview"` 이벤트를 쓸 때 `from_state`/`to_state` 를 `detail` 문자열에만 담고 top-level
     키로는 안 넣던 버그(간트 생성기 `monitor_report._preview_json` 은 top-level 키를 전제) - 추가.
     (B) 회원전용 라이브 커밋(`_commit_yt_member_live`)이 `flow:"relay"` 로그만 남기고 `flow:"preview"`
     전이 로그를 아예 안 남겨서, 알림으로 live 전환되는 순간이 간트에서 통째로 빠지고 다음 정기
     tick 이 잡는 "→end" 로 바로 건너뛰던 것(item 7: "announced/upcoming/end 만 보이고 live 안 보임"
     과 일치) - `handlers._preview_log_events` 를 재사용해 같은 모양의 `flow:"preview"` 이벤트를
     추가로 남기도록 수정. "end 가 무한정 유지되는 것처럼 보임"(item 5)·"줌에 따라 상태가 달라
     보임"(item 6)은 정적 리뷰로는 FSM 버그를 못 찾았고(위 두 로그 버그의 표시 부작용일 가능성이
     높음), 실배포 로그로 확정 필요 - 후속 확인 과제로 남김.
  5. **추가(8·9·10, `/monitor` 타임라인 UI)** - 같은 세션에서 추가 요청.
     - **item 8** - 트리거 레인(🎛️🕒📡📥)이 같은 시각에 여러 건 겹치면 종류별로 세로로 늘어놓아
       겹쳐 보이던 것 → 같은 시각(t)은 무조건 점 하나로 합치고 반지름을 건수(1~4단계, 5건↑는
       고정)로 표현. 대표 아이콘은 `TRIGGER_PRIORITY`(ops>ingest>tick/wake) 상 1순위. 상세 목록은
       호버/클릭(`wireLegend` 재사용 - 범례와 같은 pin 메커니즘). 반지름 상한(호버 확대 포함 최대
       35px)이 트리거 레인 높이(rowH=110, 중심 기준 ±55px) 안에 항상 들어가도록 계산해 다른 레인을
       침범하지 않는다.
     - **item 9** - preview 막대 클릭 시 상태 라벨이 `null` 로 뜨던 것 - item 5·6·7(A)에서 고친
       `from_state`/`to_state` 누락 버그와 동일 원인. 이번 배포 이후 새로 쌓이는 이벤트는 정상
       표시되고, 그 버그가 고쳐지기 전에 쌓인 과거 날짜 데이터는 여전히 `null` 일 수 있어
       `stateLabel()` 헬퍼로 방어적 기본 표시("상태 미상")를 추가.
     - **item 10** - live 미만 등급 색을 노랑 계열로: `announced`=어두운 노랑(`#8a6d1a`),
       `upcoming`=노랑(`#f5c344`), `watching`=같은 노랑 바탕에 빗금(패턴 배경색만 흰색→노랑으로
       교체). 신규: `assumed_live`(FSM 의 "확신도 낮은 추정 live" 플래그, 기존엔 간트에 전혀 안
       실리던 값) 가 true 인 구간은 상태색과 무관하게 빨강 빗금(`liveAssumedHatch`)으로 덮어
       그린다 - `handlers._preview_log_events`/`_commit_yt_member_live`/`monitor_report._preview_json`
       세 곳에 필드를 새로 실어 보냄.
  6. **검증** - `python -m src.backend.ytnotif`·`writeclient`·`handlers`·`telegram_app`·`monitor_report`
     self-test 전부 통과(신규 케이스 포함, 09-22 09:33 실측 payload 회귀 테스트 포함). 모니터
     타임라인 JS 는 `node --check` 로 문법 검증(브라우저 실제 렌더링 확인은 배포 후 별도 필요).
     item 5·6 은 코드 리뷰만으로 최종 검증 불가 - 배포 후 `monitoring/events-*.jsonl` 실측 확인 필요.
- **v3.8.3** (핫픽스) - 본인 채널에서 열린 합동방송(예: 리츠 채널에 유노 게스트)이 합동으로 감지되지 않던 것 수정. 2026-09-21 리츠×유노 `#ぷりはとDay1` 이 계기.
  1. **원인** - URL 우선 ingest(v3.6)의 `xtweet.resolve_url_host` 는 영상 채널 ≠ 트윗 작성자일 때만 `collab_with` 를 채웠다. 본인 채널 영상이면 게스트가
     제목(`【峰月律/千石ユノ】`)·본문(`ユノ＆律こらぼ`)에 있어도 `collab_with=null` 이었고, 이후 `merge_video_confirmed`·`preview_build` 가 최초 값을 보존해 유노 레인에 안 떴다.
  2. **수정** - `xtweet.find_guest_members`(신규): 영상 제목·트윗 원문에서 다른 개인 멤버의 **정식 표기**(`x_names`·`name_ko`)를 찾아 `collab_with` 에 합친다
     (호스트 본인·그룹 제외, `channel_order` 순). `_maybe_url_confirmed_schedule` 이 본인/타멤버 채널(host 없음) 경로에서 호출. 별칭(`ユノ` 단독 등)은 오탐 위험이라 안 본다.
     `merge_video_confirmed` 는 `collab_with` 를 **추가만** 한다(기존 값 삭제 없음) - 같은 트윗 재-`/ingest` 로 이미 등록된 아이템도 보정된다.
  3. **한계** - 제목·본문에 정식 이름이 없고 별칭만 있는 합동은 못 잡는다. 유튜브 URL 없는 텍스트 예고 경로는 영상 제목이 없어 미적용.
  4. **검증** - `python -m src.backend.xtweet`·`telegram_app` self-test 통과(신규 케이스 포함). 실제 config·트윗·제목으로 재현: 수정 전 운영 리츠 아이템 `collab_with=null` -> 재-ingest 머지 후 `["yuno"]`, `kind=collab`.
- **v3.8.1** (핫픽스) - v3.8.0 배포본 확인 후 트윗 말풍선 UI 수정. 프론트만(`tweets.css`·`tweets.js`·`layout.css`), 백엔드·데이터 변경 없음.
  1. **2열 배치** - 좌 = X 카드, 우 = 번역 말풍선(PC 패널 540px = 카드 300 + 번역, 모바일 토스트 = 카드 250(X 카드 최소 폭) + 번역 최소 110px,
     모자라면 목록이 가로로 밀림). 한 트윗의 두 열은 더 긴 쪽 높이로 같다. 번역 OFF 면 번역 열이 접혀 카드만(PC 패널 330px, 모바일은 카드가 가득 참).
  2. **번역 ON/OFF 애니메이션** - OFF: 번역 페이드아웃(0.18s) -> 열 접힘(0.25s) -> 카드 크기 변경은 그 끝(0.43s)에 한 번에. ON: 카드 즉시 원위치 ->
     열 펼침(0.25s) -> 번역 페이드인. 카드 iframe 이 매 프레임 다시 그려지지 않게 한 것. 모션 줄이기 설정이면 애니메이션 없음.
  3. **스크롤** - 카드 자체엔 스크롤 없음(전체 높이). PC 말풍선은 화면 높이 1/2 를 넘으면 말풍선이 세로 스크롤. 모바일 토스트는 기존 상한 유지.
  4. **꼬리 위치** - PC 말풍선 꼬리를 캐릭터 아바타(동그라미)의 x축 중앙 바로 아래로(가장자리 보정으로 패널이 밀려도 유지, 열린 뒤 0.3s 후 재보정).
  5. **디스클레이머** - 말풍선(PC 패널·모바일 토스트)에서는 제거하고 사이트 하단 디스클레이머만 유지. 하단 팝업의 "GitHub Issues" 링크에 밑줄.
     (v3.8.0 항목 5의 "패널·시트 하단" 서술은 이 버전에서 바뀜 - 모바일은 하단 푸터만 남음)
  6. **검증** - 실제 저장 데이터 픽스처로 로컬 Chrome 확인: 좌우 열 높이 일치(PC 5건), 꼬리 중심 = 아바타 중심(x 87), 스크롤 영역 안 스크롤바 없음, 애니메이션
     타이밍 등록 확인, 모바일 360px 폭 2열·OFF 시 카드 324px. 미확인: 백그라운드 탭이 아닌 실제 재생 모습(사용자 확인), Safari·실기기.
- **v3.8.0** (기능) - 말풍선 트윗을 **번역 말풍선 + X 공식 트윗 카드**로만 구성한다. 트윗의 요소(원문 텍스트·이미지·영상·참조 트윗 미디어)를
  우리가 다시 조립해 그리지 않는다. 프론트만 바뀌었다(`tweets.js`, `tweets.css`, `index.html`).
  1. **방침(2026-09-19 자문)** - 일본 최고재판소가 트윗 이미지를 UI 에서 재조립해(잘라 표시해 저자 표기가 사라짐) 성명표시권 침해로 본 사례가
     있어, 재조립을 없애고 "X 트윗카드 + 원문 번역"만 남긴다. 이 형태는 디스클레이머(비공식 팬 번역·비영리·삭제 요청 시 예고 없이 중단 가능·
     문의 창구)를 갖추면 위험이 낮다는 자문. notice(텍스트 요약·번역)는 자문상 위험이 낮아 변경 없음.
  2. **UI (번역 위, 카드 아래)** - 트윗 하나 = `번역 말풍선`(원문 트윗의 `text_ko`; 참조 트윗이 있으면 그 번역 `quote.text_ko` 를 안쪽 말풍선으로,
     미디어는 없음) + `X 공식 카드`(iframe). 번역이 없으면 원문 대신 "번역 준비 중…" 을 보여 준다(재조립 금지). 번역은 즉시 보이고 카드는 뒤늦게
     붙는다. 기존 日/한 전환은 "번역 ON/OFF"(카드는 재로드하지 않고 CSS 로 번역만 숨김)로 바뀌었다. 합성 id(숫자 아님) 트윗은 카드를 만들 수 없어
     "X에서 원문 보기" 링크만.
  3. **저장 데이터는 유지** - `tweets.json` 의 `text/media/quote`(모두 URL·텍스트, 파일 아님)는 유지보수용으로 그대로 두되 화면에는 쓰지 않는다
     (화면이 쓰는 것은 `id`·`text_ko`·`quote.text_ko`·`received_at`). 백엔드 변경 없음.
  4. **X 카드 제약(모두 실측)** - ① 폭 250px 이상이어야 렌더링·자동 높이 메시지가 온다 -> PC 패널 폭 268 -> **320px**(모바일 시트는 폭 400px 에서 카드
     340px 로 충분). ② 높이는 카드가 `twttr.private.resize` 로 알려주는 값을 상한 없이 적용(폭 285px 기준 짧은 텍스트 230, 긴 글 422, 이미지 611, 영상+참조
     1,053, 참조 트윗 1,110px) - 패널 스크롤에 맡김. ③ 영상 카드 5개를 동시에 띄우자 브라우저가 멈춤 -> **화면에 들어올 때만**(IntersectionObserver,
     rootMargin 300px) 로드하고 나머지는 자리표시(230px). ④ 첫 로딩 4~10초 이상 - iframe `load` 후에도 신호가 늦을 뿐이면 오류로 보지 않고, 로드 자체가
     안 될 때만(15초) "카드가 열리지 않아요 · X에서 보기". 패널·시트를 닫으면 카드를 지운다.
  5. **디스클레이머** - 패널·시트 하단 "비공식 팬 번역 · 비영리 운영 · 삭제 요청 시 예고 없이 서비스가 중단될 수 있습니다 · 문의·삭제 요청 (GitHub
     Issues)" + 사이트 푸터 안내에 두 항목 추가. 창구는 이 저장소의 GitHub Issues.
  6. **폴링 재렌더 가드** - 75초 폴링마다 열린 패널이 다시 채워져 X 카드가 계속 재로드되던 문제를, 표시 내용(id·번역)이 바뀔 때만 다시 그리게 수정.
  7. **검증** - 실제 저장 데이터 픽스처(번역·참조 트윗 번역·번역 누락·합성 id·영상 카드)로 로컬 프론트를 Chrome 에서 확인: 번역 말풍선·안쪽 참조 번역·
     번역 ON/OFF·지연 로딩·자동 높이(441·1,048px)·재렌더 시 iframe 유지·닫으면 정리·모바일 시트(400px). 이미지·영상 요소 0개. 미확인(배포 후 확인):
     Safari·실기기 모바일, 번역이 여러 건 동시에 갱신되는 폴링.
  8. **기각된 방식(기록)** - 영상을 `<video src>` 로 X 서버 mp4 주소에서 직접 재생하는 안(X 서버 mp4 주소 저장 + `no-referrer` 메타)은 위 자문으로 기각했다.
     이 저장소(main)에는 그 코드가 없고, 브랜치 `feat/v3.8.0a-tweet-video` 에만 보존한다(배포·병합 금지).
- **v3.7.4** (핫픽스) — 영상 첨부 트윗의 말풍선 미디어가 깨지던 버그.
  1. **원인** — 프론트(`tweets.js` `_mediaGrid`)는 `media` 의 모든 URL 을 `<img src>` 로 그리는데(v2.8 설계: 본인 트윗
     첨부 "이미지"), `vxtwitter` 응답은 영상 트윗의 `mediaURLs`/`media_extended[].url` 이 mp4 이고 썸네일은
     `thumbnail_url` 에 따로 있다. `extract()` 가 mp4 를 그대로 `media` 에 넣어 깨진 이미지로 표시됐다(2026-09-19 18:07 KST
     아라레: 약 85MB mp4). v3.7.3 의 폴백과 무관한 기존 문제. 저장된 트윗 187건 중 영상 URL 포함 3건이었다(9/17 21:34 KST 미야코
     참조 미디어, 9/19 00:08 KST 미야코, 9/19 18:07 KST 아라레).
  2. **수정** (`vxtwitter._media_urls`) — 영상·GIF(`video`/`gif`/`animated_gif`)는 `thumbnail_url` 을 쓰고 썸네일이 없으면 넣지
     않는다. `media_extended` 없이 `mediaURLs` 만 있을 때도 mp4/m3u8/`video.twimg.com` 은 거른다. 참조 트윗(`qrt`) 미디어에도 같이
     적용. `fxtwitter` 변환도 `vxtwitter` 와 같은 형식(`url`=원본, `thumbnail_url`)으로 맞춰 두 경로가 같은 썸네일을 낸다.
  3. **복구** — 저장된 3건(9/19 18:07 KST 아라레, 00:08·18:19 KST 미야코[아라레 영상 참조])의 `media` 를 썸네일로 교체(본문·번역 유지).
- **v3.7.3** (핫픽스) — 유튜브 앱 "회원 전용 실시간 스트림" 알림으로 회원 전용 방송을 live 로 전환.
  1. **업스트림 유튜브 알림이 전부 400 이던 문제** — 업스트림이 유튜브 알림을 `source=yt&video_id&title&kind&tag`
     폼으로 `/ingest` 에 중계하는데 `/ingest` 는 `text` 만 읽어 5ms 만에 `400 empty text` 를 반환했다
     (Cloud Run 로그 2026-09-09~18, 32건 전부. 타임아웃이 아니었다 — flow-11 로그에서 유튜브 알림 HTTP 31건은
     모두 0.2~4.2초에 응답을 받았고 HTTP 실패 148건은 전부 X 트윗 중계). `source=yt` 를 별도 분기로 빼
     항상 200 으로 응답하고, 회원 전용 시작(`SPONSORSHIPS_LIVESTREAM_START`)+5인만 처리, 나머지는 무시.
  2. **회원 전용 방송 live 전환** — 알림의 `video_id` 는 `default` 라 영상을 알 수 없다. 알림 즉시 그 멤버
     채널 streams 탭을 yt-dlp 로 읽어(`ytdlp_probe.py`, `--flat-playlist`) `subscriber_only` 라이브의
     video_id/URL 을 얻는다(제목 일치 → 없으면 is_live 1건). 쿠키 없이 Cloud Run(데이터센터 IP)에서 동작함을
     임시 Job 으로 실측(2026-09-19). 쿠키(`YT_COOKIES_FILE`, Secret `YT_COOKIES`)가 있으면 먼저 쿠키로 시도하고
     실패하면 쿠키 없이 재시도. 상한 6초(Automate HTTP 타임아웃 약 10초 대응) + 목록 반영 지연 대비 1회 재시도.
  3. **반영** — 커밋은 `/write` 잡 `yt_member_live_commit` → `xtweet.merge_member_live`(순수): 같은 채널의
     video_id 없는 예고 자리표시(±3h)를 제자리 live 로 승격(membership=True, video_id/url/title 채움) /
     없으면 새 live 항목 생성 / 같은 알림 재도착은 noop. 조회 실패 시 채널 링크로 live 처리하고 운영자 DM.
     video_id 가 없는 자리표시는 API 가 조회할 방법이 없어 live 로 확정되지 못했다(9/18 아라레). video_id 를
     알게 되면 이후 live→end 는 기존 API 경로(`videos.list`, 회원 전용 영상도 조회됨을 2026-09-19 실측 —
     종료된 영상 기준)가 처리한다. 9/18 의 `watching↔announced` 왕복은 별개 문제로 이번에 안 고침.
  4. **보정** — `render.js`: live 카드 링크 폴백(`channel_url`).
  5. **예고 자리표시 왕복 차단** (`statemachine`) — 규칙 3(예정 후 120분 뒤 `watching→announced`)과 규칙 1
     (예정 시각이 지났으면 `announced→watching`)이 실행마다 서로를 되돌려 TTL 까지 왕복했다(9/18 아라레 자리표시
     `pv_c181ee4c`: 22:57 KST `watching` 진입 → 2시간 조용 → 23:00~00:00 KST 140회 왕복, 분당 평균 2.3회·최대 5회 →
     00:00 KST TTL 로 소멸). 예정 후 120분이 지난 예고는 `announced` 로 두고(`late-hold`) 재진입시키지 않는다.
  6. **웨이크 체인 증식 차단** — 상대 체크 시각(`now + 3분/5분/10분`)이 실행 시각마다 달라, 정기 tick·다른
     방송의 wake 가 돌 때마다 위상이 다른 체인이 하나씩 추가됐다(wake 태스크 이름은 (영상, 분)이라 dedupe 안 됨).
     `DWMQTpDQ1fc` 3분 주기가 위상 3개로 분당 1회가 되어 9/17 17:13 KST~ 48시간 3,331회. `statemachine._after` 가
     상대 시각을 주기 격자의 다음 눈금으로 맞춰(지연 [주기/2, 1.5×주기)) 같은 구간의 모든 실행이 같은 시각·같은
     이름으로 dedupe 되게 했다. 절대 시각(예정 3분 전 예약)은 대상 아님.
  7. **먼 미래 웨이크 미등록** (`handlers._wakes_within_horizon`) — 시작이 24시간 넘게 남은 방송의 wake 는 등록하지
     않는다(창 안으로 들어오면 다음 light tick 이 등록). 29일 상한으로 잘린 시각("지금+29일")이 실행마다 새 이름으로
     쌓여 12/24 라이브(`h31Mi6AS7a0`) wake 가 큐에 3,319건 누적됐다(기존 누적분은 별도 정리).
  8. **미래로 밀린 `watching` 되돌림** (`statemachine`) — 예정 시각이 3분보다 미래로 정정된 `watching` 항목은
     `upcoming`(video_id 있음)/`announced` 로 되돌리고 예정 3분 전 재진입을 예약한다. 9/17 17:03 KST 에 예정 시각이
     수신 시각으로 잡혀 `watching` 이 된 항목이 9/25 로 정정된 뒤에도 유지돼 위 3,331회의 원인이 됐다. 규칙 2 테스트의
     시각(주석 의도는 "ss-3분 이후"인데 실제 값은 ss-60분)을 의도대로 수정.
  9. **`vxtwitter` → `fxtwitter` 폴백** (`vxtwitter.py`) — vxtwitter 가 특정 트윗을 HTTP 500 으로 영구히 못 줘(9/14~19
     고유 트윗 12건이 며칠 뒤에도 500) 첨부 이미지·참조 트윗(QRT)이 유실됐다(9/18 19:32 KST 아라레 "2年半前…💛💙":
     참조 트윗 단독 조회도 500). 실패(HTTP 오류·예외·JSON 오류) 시 fxtwitter 로 폴백해 vxtwitter 형식으로 변환
     (영상·GIF 는 썸네일). 응답에 실린 참조 트윗을 그대로 쓰고(`extract()["qrt"]`), 없을 때만 id 로 재조회.
     타임아웃 8초→vx 5초/fx 4초(순차로 돌아도 업스트림 HTTP 타임아웃 약 10초 안).
  10. **배포·운영 조치 (2026-09-19 KST)** — `mewtype-backend` 리비전 `00094-vdp`, `mewtype-telegram` `00073-chr` 배포
     (17:40~18:15 KST). 유튜브 멤버십 쿠키를 Secret `YT_COOKIES` 로 올려 `/secrets/yt-cookies.txt` 마운트
     (`YT_COOKIES_FILE`). 첫 쿠키(01:08 KST 내보냄)는 서버 쪽에서 이미 무효(로그인 필요 페이지 접근 불가)라 올리지
     않았고, 새 쿠키(18:07 KST)는 로그인·회원 영상 접근을 확인해 올렸다. 쿠키는 저장소 밖(`~/.secrets/`)에 보관하고
     `.gitignore` 에 패턴을 넣었다. 쿠키 없이도 streams 탭 조회 결과는 같았다(실익 미확인). Cloud Tasks 큐에 쌓인
     `h31Mi6AS7a0` 웨이크 3,345건을 삭제(정상 웨이크 5건 유지)했고, 17:50 KST 정기 tick 이 전체를 재계산한 뒤에도
     재적재가 없음을 확인했다.
  - 배포 주의: `writers.py` 를 건드렸으므로 `mewtype-telegram`·`mewtype-backend` 둘 다 재배포. `.gitignore` 에
    쿠키 파일 패턴 추가(자격증명).
- **v3.7.2** (핫픽스) — 트윗 24시간 노출 복구 + 웹 monitor 접속 시각 기준 리포트.
  1. **개인 트윗이 다음날 전부 사라지던 버그** — v3.5.3 이 프론트 `tweets.js`(`_visible`)에 얹은
     `VISIBLE_WINDOW_MS=12h` 필터가 원인. 백엔드(`tweets.json`, 메시지별 `expires_at`=+24h, sweep)는 정상이라
     저장은 24시간 유지됐지만 화면은 12시간만 보였다(멤버들이 밤에 올리고 낮엔 조용해 다음날 낮이면 거의 전부
     사라짐. 실데이터 시뮬레이션: 9/18 12:00 KST 12h 창 1건 vs 24h 창 16건). 12시간 필터를 제거해
     `expires_at`(24h) + 상한 50건만 남김.
  2. **웹 monitor 가 06:00 스냅샷을 보여주던 버그** — `monitor.html` 이 미리 커밋된 `monitoring/latest.html`
     (06:00 자동 실행=전일치, 또는 마지막 `/monitor` 수동 실행분)만 읽었다. 제어 채널에 읽기 전용
     `GET /monitor-live`(60초 캐시, CORS 허용)를 추가해 접속 시각 기준 — 가장 최근 06:00 KST~지금 — 리포트를
     즉석 생성하고, `monitor.html` 은 이걸 먼저 부른 뒤 실패하면 `latest.html` 로 폴백. 06:00 자동 DM 리포트는 그대로.
- **v3.7.1** (2026-09-17) — v3.7 운영 점검(`ref/v3_improvisation.md`) 후속 개선. 구현 명세:
  `docs/plan/v3_improvisation.md`. 결정 근거·사고 재현 애니메이션은 명세 §0 참고.
  1. **[P0] `/ingest` 개인 트윗 500 수정** — v3.7 배포(2026-09-17 11:29 KST)부터 `_ingest` 가 지역변수
     `gh` 를 대입 전에 써서 `UnboundLocalError` → 멤버 5인 트윗이 전부 500 으로 유실되던 버그.
     `gh = _make_gh()` 를 라우팅 전으로 옮기고, `/ingest` 라우트를 실제로 치는 self-test 5케이스 추가
     (기존 self-test 는 라우트 함수를 안 불러서 못 잡았다).
  2. **write-queue A-1 — 외부 호출은 제어 채널, `/write` 잡은 커밋만.** v3.7 은 외부 LLM·`videos.list`·
     vxtwitter·비전 OCR 까지 백엔드(`concurrency=1`) 잡 안에서 돌려, 외부 장애 때 `/tick`·`/wake` 가 뒤에서
     같이 막히는 구조였다(최악 수백 초). 소식(`_prepare_notice`/`_commit_notice`)·개인 트윗
     (`_prepare_personal_tweet`/`_commit_personal_tweet`)·URL 확정 예고(`_url_confirmed_commit`, kind
     `url_confirmed_schedule` → `url_confirmed_commit`)를 준비/커밋으로 분리. Cloud Tasks 즉시 wake 등록은
     제어 채널에 env 가 없어 백엔드 잡 안에 남김. 상세: `docs/SPEC.md` §8.14.
     - 큐 폐기안(B안)은 기각 — 2026-09-16 노노카 트윗 유실의 충돌 상대가 백엔드가 아니라 같은 초에
       들어온 다른 `/ingest` 요청들의 커밋이었음을 커밋 이력·Cloud Logging 으로 확인.
     - 남는 한계: 모니터 로그·`admin_state.json` 마법사·`control.json` 은 여전히 제어 채널 직접 커밋.
  3. **모니터 로그 커밋 축소** — `data` 저장소 커밋의 약 95% 가 `data: monitor` 였다. 백엔드 실행 1회당
     이벤트를 모아 `monitor_log.log_events` 로 커밋 최대 1개, 변화 없는 tick/wake 는 기록 안 함
     (`handlers._should_log_run`). `/monitor` 의 quota·호출 수 표기를 "기록된 실행" 기준으로 변경.
  4. **외부 LLM 폴백 기본값 통일** — 제어 채널 `_make_llm_client()` 의 폴백 기본값이 이 계정에서 404 나는
     `llama-3.3-70b-versatile` 이었다 → `llm.FALLBACK_MODEL`(`openai/gpt-oss-20b`).
  5. **라이브 후기 wake 3분 → 5분** (`LIVE_TIGHT_SEC=300`) — 프론트가 읽는 raw CDN 캐시가 `max-age=300` 이라
     3분 간격은 화면에 반영되지 않았다.
  6. **`xtweet.apply_overrides` v3 재작성 + 연결** — 문서엔 "tick 이 호출"로 적혀 있었지만 실제로는
     어디서도 호출되지 않았고, 로직도 v2 형태(`info_source="bdp_schedule"` 등)를 가정해 그대로 연결하면
     오작동. `api_start_seen` 이 직전 tick 대비 60초 넘게 바뀌면(스트림 예약 실제 수정) API 시각이
     트윗/릴레이 시각을 이기도록 고쳐 `handlers._run` 의 `build_preview` 직후에 연결.
  7. **배포 재현성** — `deploy.sh`·`deploy_telegram.sh` 가 `HEALTHCHECKS_IO_READONLEY_TOKEN` Secret 을
     무조건 마운트해 `setup.sh` 로 새로 세운 프로젝트에선 첫 배포가 실패 → Secret 있을 때만 마운트 +
     `setup.sh` 생성 목록에 추가, `env.example.sh` 갱신(데이터 저장소 `GITHUB_REPO` 등).
  8. 3h tick 시절 주석 정정(`handlers.py`·`preview_build.py`, 동작 변경 없음) + `SPEC.md`·`CLAUDE.md`·
     `INGEST_FLOW.md` 현행화.

- **v3.7** (2026-09-17, 커밋 `b07d7b5` — 기록 누락분 소급) — 세 기능이 한 커밋에 들어갔다.
  1. **write-queue** (`POST /write`, `writers.py`, `writeclient.py`) — GitHub Contents API PUT 이 브랜치 HEAD
     단위로 충돌하는 탓에 제어 채널의 동시 처리 요청끼리 409 를 내 트윗이 유실된 사고(2026-09-16 20:12 KST
     노노카 트윗) 대응. 제어 채널의 콘텐츠 쓰기 14종을 `concurrency=1 · max-instances=1` 인 백엔드의
     `/write` 로 동기 호출해 직렬화. 마법사형 명령(`/del` `/undo` `/notice-edit` `/edit preview`)은 처음 캡처한
     스냅샷/sha 만 근거로 커밋. (이 배포에 v3.7.1 의 P0 버그가 포함돼 있었다.)
  2. **소식 LLM 의미 중복판정** (`llm.duplicate_notice`, `notices.merge_into`) — url/title 정확 일치로 못 잡는
     같은 행사를, **같은 날짜**(threshold=0일) 기존 소식이 있을 때만 등록 직전 LLM 에 물어 병합. 날짜가 다른
     연속 행사는 비교 대상에서 제외, 실패·미설정이면 새 소식으로 등록(정보 손실 방지 우선).
  3. **상시 모니터 페이지** — `/monitor` 리포트를 `monitoring/latest.html` 로도 커밋하고
     `src/frontend/monitor.html` 이 raw URL 로 불러와 표시. 메인 예고판과 링크 없이 이스터에그로 진입:
     PC 는 `y` 입력 후 10초 안에 `umewapower`, 모바일은 풋터 버전 표시를 5초 안에 15번 탭(탭마다 멤버
     아이콘 풍선). 데이터 저장소가 public 이라 raw URL 을 알면 누구나 열람 가능하다.
  4. 자동 리포트(`mewtype-monitor`, KST 06:10)가 막 시작된 당일 대신 **전일** 버킷을 보도록 수정.

- **v3.6** — 개인 5인 트윗 예고 판정 URL 우선 재설계 + `/telegram` 웹훅 DM 안전망 + light tick
  3h→10분. 실사례 2건이 계기: (1) 노노카 쇼츠 라이브가 `配信` 키워드 없이 시작해 light tick
  텀(당시 3h)만큼 감지가 늦었던 버그, (2) 아라레 후기 트윗("先行プレイ配信 ありがとうございました
  …ガッツリ**2時間**プレイ…**9/24**まで待ち遠しい")의 "2時間"(플레이 시간)·"9/24"(게임
  출시일)가 정규식에 각각 시각·날짜로 오합성돼 9/24 02:00 방송 예고로 둔갑한 오탐.
  1. **light tick 3h → 10분** (`deploy/scheduler.sh` `mewtype-light` cron). 자원 재확인: YouTube
     쿼터 10분×144회/일=288 units(무료 한도 1만의 3%), GitHub API·Cloud Run 무료 티어 전부 여유
     — 실질적으로 소모되는 유상 자원 없음.
  2. **URL 우선 ingest** (`telegram_app._maybe_url_confirmed_schedule`, `xtweet.resolve_url_host`/
     `build_item_from_video`/`merge_video_confirmed`) — 개인 트윗 원문에 완결된 유튜브 URL이
     있으면 `配信` 키워드 유무와 무관하게 `videos.list` 로 즉시 사실관계(제목·실제 상태
     live/watching/upcoming·시각) 확정. 채널별 분기:
     - 본인 채널 → 바로 등록, state 는 API 실제값으로 직결(고정값 아님 — 이미 라이브 중이면
       곧장 `live`).
     - 5인 중 다른 멤버/그룹 공식 채널(`@BDP_yumemita`) → 그 채널이 host, 작성자는
       `collab_with`(그룹 채널이면 v3.1.4 팬아웃과 동일하게 5인 전원).
     - 외부 채널(우리 5인도 공식도 아님) → `LLMClient.participation()` 으로 "이 멤버가
       참여하는 콘텐츠인가" 확인 후에만 작성자 레인에 등록.
     - **API 로 확정 실패**(`YOUTUBE_API_KEY` 미설정·`videos.list` 예외·영상 조회 실패)는
       조용히 드롭하지 않고 **텍스트 파싱(3번)으로 폴백** — v3.6 이전 신뢰도 밑으로는 안
       떨어짐(`_maybe_nonyt_url_notice` 도 유튜브 URL 을 비유튜브로 오분류하지 않도록 가드).
     - 등록되면 Cloud Tasks wake 를 그 자리에서 즉시 enqueue(`_enqueue_wake_now`) — light
       tick 을 안 기다리고 live/watching 전이를 실시간에 가깝게 반영. undo 스냅샷도 기록
       (LLM 오판 시 `/undo` 로 되돌릴 수 있게).
  3. **비유튜브 URL → 소식 이관** (`telegram_app._maybe_nonyt_url_notice`) — bilibili 등은
     라이브/종료를 API 로 확인할 방법이 없어 "등록은 되는데 절대 안 끝나는" 반쪽 preview
     카드를 만드는 대신, 기존 공식 계정 소식 경로(`_apply_notice`)를 그대로 재사용해
     `notices.json` 으로 보낸다(번역·undo 전부 그대로 딸려옴).
  4. **URL 없는 텍스트 예고 — LLM 최종 확인** (`xtweet.parse_schedule` 후보 + `llm.
     announces_own_broadcast()`) — 정규식 게이트(`配信` 키워드)+날짜/시각 추출까지 통과한
     후보도, 등록 직전 "작성자는 추후 진행할 방송을 예고하는 글을 썼니?"를 LLM 에게 물어
     최종 확인한다. 아라레 실사례로 실제 Groq 호출 검증 — 정규식은 "配信"·"2時間"·"9/24"를
     문맥 없이 각각 캐치하지만 LLM 은 "이건 후기지 예고가 아니다"를 정확히 판정. 동시에
     `xtweet._RECAP_RE` 가드 자체도 고침 — "추출된 날짜가 과거일 때만 후기로 인정"하던
     조건이 오합성된 미래 날짜엔 무력화되던 버그를 없애고 `_RECAP_RE`+"오늘 마커 없음"만으로
     판정하도록 단순화.
  5. **모니터링 — 조용한 폴백 근절.** LLM/API 인프라 문제로 등록을 못 한 경우(키 미설정·
     API/LLM 호출 실패·5회 재시도 소진)만 `monitor_log.log_event(flow="tweet",
     result="degraded")` 로 기록(`_log_event_safe` — 기록 실패가 원 로직을 안 죽임). LLM 이
     명확히 "아니오"라고 판정한 정상 케이스는 노이즈라 기록 안 함 — "판단 자체를 못 내린 것"과
     "판단해서 아니라고 한 것"을 구분. 기존 `/monitor` 개인 트윗 레인에 그대로 잡힘, UI 변경 없음.
  6. **`/telegram` 웹훅 DM 안전망** (`_dm_sent_ctx` `ContextVar` + `_done()`) — 버그리포트:
     `/del preview`(유닛/번호 누락) 명령이 응답 DM 없이 조용히 끝났다는 보고(코드 추적으론
     재현 안 됨 — 배포 지연 가능성). 개별 핸들러를 하나하나 감사하는 대신, 웹훅의 모든 반환
     지점을 `_done()` 하나로 통일해 명령 처리 후 DM 이 한 건도 안 나가면 자동으로 안내 DM을
     보내도록 일반화 — 앞으로 어떤 새 명령/경로에 이런 누락이 생겨도 자동으로 잡힌다.
  상세 설계 대화·흐름도: `docs/v3_pamphlet.html`(devpapers) "개인 트윗 예고 판정" 섹션(8개
  트윗 유형별 애니메이션 경로).

- **v3.5.5** (핫픽스) — `/monitor` 상단 요약에 "오늘의 멤버 현황" 패널 추가.
  기존 4개 요약 카드(총 이벤트/에러/부분 실패/quota)만 있던 자리에, 멤버별 개인 트윗
  수집 결과(건수 · ✓성공/✕실패)와 이 날짜 안 라이브(live) 진입 여부를 함께 보여준다.
  - 왼쪽: 멤버 5행 — 타임라인 라벨과 동일한 `MEMBER_ICON` 얼굴 아이콘 + `TWEET`을
    `member` 기준으로 집계(성공은 `tone!=="err"`, 기존 통계 집계 관례와 동일하게 degraded
    도 성공 쪽에 포함) + 그 날 `PREVIEW[member].segs`에 `s:"live"` 세그먼트가 하나라도
    있으면 라이브 점 on.
  - 소식은 멤버 구분이 없는 계정 단위 이벤트라 표에 넣지 않고, 표 아래 한 줄로
    성공/실패/총계만 별도 집계(`NOTICE` tone 기준).
  - 오른쪽: 기존 4개 요약 카드를 세로 목록으로 압축해 왼쪽과 같은 높이로 배치, 전체가
    하나의 직사각형 패널이 되도록 구성(`.combo`/`.combo-left`/`.combo-right`).
  - 배포 전 사용자에게 아티팩트로 배치를 먼저 보여주고(멤버 2열 접기 → 최종 5행 세로로
    확정) 승인받은 뒤 구현.

- **v3.5.4** (핫픽스) — `/monitor` 타임라인 라벨 서브칸 겹침 수정 + 멤버 얼굴 아이콘 도입.
  1) **그룹 아이콘/멤버 이름 라벨 겹침 수정** (`monitor_report.py`). v3.5.3 에서 홀수 행
     그룹(preview/개인 트윗, 멤버 5명)의 그룹 아이콘을 `groupTop - 14`로 밀어 겹침을
     피하려 했으나, 실측 스크린샷 결과 여전히 데이터에 따라 옆 그룹 아이콘이나 멤버
     라벨과 겹치는 경우가 남아 있었음(버그리포트: `ref/timeline_uibug.png`). 세로
     오프셋으로 피하는 방식 대신 라벨 칸을 아이콘 서브칸(왼쪽 28px)/이름 서브칸(오른쪽)
     으로 좌우 분리 — 세로 위치가 뭐든 물리적으로 겹칠 수 없는 구조로 바꾸고, 관련
     특수 케이스 코드(`g._labelY` 홀짝 분기)를 삭제.
  2) **멤버 얼굴 도트 아이콘 도입.** 이름 서브칸의 텍스트("아라레" 등)를 유닛 공식
     굿즈(ぷちぷれ゛ドリーミーピクセルヘッドアイコン) 도트 그림에서 얼굴만 누끼 딴
     16×16 아이콘으로 교체 — 텍스트보다 폭이 좁아 라벨 칸 전체 폭을 64px→50px 로 줄여
     플롯 영역을 넓혔다. 원본 PNG(40×40, 배경 제거)는 `assets/member_icons/` 에 보관,
     `monitor_report.py` 에는 base64 로 임베드(`MEMBER_ICON`, 텔레그램 DM 전송 시
     외부 리소스 의존 없이 단일 HTML로 완결). 아라레는 트윈테일이, 미야코는 단발
     실루엣이 되도록 크롭 경계를 캐릭터별로 맞춰 잘랐다.

- **v3.5.3** (핫픽스) — 개인 트윗 노출 정책 변경 + `/monitor` 타임라인 인터랙션 개편 + 번역
  파이프라인 버그 수정.
  1) **개인 트윗 노출: 유닛당 최근 5개 고정 → 최근 12시간 전부.** 활발한 멤버가 12시간
     안에 5건을 넘기면 더 오래된 트윗이 이미 밀려나 있던 문제 — 저장 상한
     `xtweet.MAX_THREAD` 를 5에서 50(안전 상한, 실제로 걸릴 일은 거의 없음)으로 올리고,
     프론트 `tweets.js`(`_visible`)에 `VISIBLE_WINDOW_MS=12h` 필터를 새로 얹었다. 배포
     직전 실데이터(`tweet_archive.json`) 대조 확인 결과 12시간 안에서 이미 밀려난 항목은
     없어 별도 백필 불필요. 메시지 수가 늘어도 말풍선(`.lane__bubble`/`.tw-toast`)이
     화면 세로 2/3(`calc(66.6vh - 44px)`)을 넘지 않도록 내부 스크롤로 흡수(`tweets.css`).
  2) **`/monitor` 타임라인 UI/인터랙션 개편** (`monitor_report.py`).
     - 플롯 좌측에 05:30~06:00 여유 공백(`AXIS_LEAD_MIN=30`)을 얹어 06:00 라인이
       컨테이너 왼쪽 가장자리에서 잘려 보이던 문제 수정.
     - 트리거(🎯) 점·아이콘이 평소엔 오밀조밀 모여 있다가, 마우스가 그 시간대에 오면
       애니메이션으로 커지며 퍼지고 벗어나면 원상복구(쉬는 상태 반지름도 7→9로 확대).
     - preview/개인 트윗처럼 멤버 5명(홀수) 라인의 그룹 아이콘이 가운데 멤버 라벨과
       겹치던 문제 — 그룹 바로 위 여백으로 이동해 해결.
     - 인터랙션을 Pointer Events 로 통합해 PC/모바일 공통화: 드래그(모바일은 터치
       드래그)로 좌우 이동, PC는 ctrl+휠(macOS 트랙패드 핀치도 동일)·모바일은 두 손가락
       핀치로 현재 크로스헤어 기준 확대/축소, 클릭(탭)으로 크로스헤어 고정/해제.
     - `mewtype-monitor` 스케줄러를 baseline tick 과 같은 06:00 KST 에서 **06:10** 으로
       늦춤 — 두 Cloud Scheduler 잡이 동시 발사되면(Cloud Run concurrency=1) `/monitor`
       가 그날 첫 이벤트 로그가 쓰이기 전에 먼저 처리돼 완전히 빈 리포트가 DM 발송되던
       레이스 실측 수정(`deploy/scheduler.sh`).
  3) **번역(Groq) 파이프라인 버그** (`llm.py`) — 메인 모델이 HTTP 200 + 빈 `content`("
     reasoning_effort=low" 짧은 프롬프트에서 추론 토큰이 답변 예산을 다 써버림)를 반환해도
     폴백 모델 전환 조건이 `is None`만 체크해 빈 문자열(`''`)을 걸러내지 못하고 곧장
     환각 가드로 떨어져 실패하던 버그 수정(`not response` 로 변경) + `max_tokens` 하한
     200→500. 실측: 같은 짧은 입력에서 `/translate` 재시도까지 포함해 4회 결정적으로
     실패(`in=155/out=''`)하던 것 확인 후 수정.

- **v3.5.2** (핫픽스) — 프론트 트윗 말풍선/하단 디스클레이머 UI 버그 2건.
  1) 트윗 편지 배지를 호버로 열고 있는 도중 다시 호버하거나 클릭하면 말풍선이 두 번
     뜨고, 그중 하나(호버로 열린 쪽)가 이후 어떻게 해도 안 닫히는 "좀비" 버그 수정
     (특정 멤버 한정 아님 — 재현 조건은 "열리는 애니메이션 도중 재상호작용"). 원인은
     `_closeBubble`의 비동기 제거 예약(`transitionend`/260ms 타임아웃)이 예약 시점
     상태만 보고, 실행 시점에 그새 다시 열렸는지 재검증을 안 하던 것 — `tweets.js`에
     ⓐ `pointerover`/클릭이 이미 열려있는(peek/pinned) 채널에는 재진입하지 않도록
     트리거 자체를 잠그고, ⓑ `_showBubble`의 `requestAnimationFrame` 콜백과
     `_closeBubble`의 지연 제거 콜백 양쪽에 실행 시점 재검증을 추가해 이중으로 막음.
     겸사겸사 발견한 별개 버그도 같이 수정: 말풍선 패널(`.lane__bubble`)이 레인의
     DOM 자식이 아니라 `#board`의 형제 노드라, 호버 중 마우스를 배지에서 패널 쪽으로
     옮기면 `pointerout`이 "레인을 벗어났다"고 오판해 바로 닫혀버려 패널 위에서
     스크롤·번역 토글이 사실상 불가능했던 것 — 패널로의 이동도 "안에 있음"으로 인정.
  2) 하단 디스클레이머가 문구 5건을 4초 간격으로 하나씩 끊어 전환하던 것 → 끊김 없이
     이어붙여 천천히 흐르는 연속 marquee로 변경(속도 하향, 문구 사이 간격도 넓힘 —
     일반 스페이스는 CSS상 연속 공백이 collapse 되므로 NBSP로 교체). 호버/클릭 시
     펼쳐지는 팝오버 폭도 "업데이트 시각 오른쪽 끝 ~ `ver.♾️` 왼쪽 끝"에 정확히
     맞추도록 JS에서 동적 계산(`main.js` `positionDisclaimerPopup`).
- **v3.5.1** (`/monitor` 후속 보강 — 핫픽스 + 기능 추가) — v3.5.0 배포 직후 모바일 실사용
  피드백 반영.
  1) (핫픽스) 타임라인 좌측 라벨 컬럼(168px)이 모바일 폭을 너무 많이 잡아먹어 플롯이
     작게 보이던 것 — 레인 그룹 라벨(🎯 트리거 등)을 텍스트 대신 이모지 아이콘 하나로
     줄이고(클릭 시 뜨는 팝업은 그대로) 컬럼을 46px로 축소, 확보한 폭만큼 플롯이 넓어짐.
     폭 640px 이하에서는 트리거 레인(옵셋 겹침 방지 계산 때문에 고정)을 뺀 나머지 레인의
     행 높이·그룹 간격도 줄여 세로로 더 밀집시킴.
  2) (기능 추가) "하루" 경계를 KST 00:00 → **06:00~익일 06:00 KST**로 변경 — 멤버들이
     자정을 넘겨 방송하는 경우가 흔해 하루를 정확히 쪼개지 못하던 문제. `monitor_log.py`
     에 `bucket_date_kst`/`DAY_START_HOUR=6` 추가(`event_path`가 이걸로 파일명 결정),
     `monitor_report.py`의 healthchecks/Vercel 조회 창(`_day_bounds`)과 프론트 타임라인
     x축 원점(`minutesOf`/`fmtHM`의 `DAY_START_MIN=360` 앵커 변환)도 같은 경계로 맞춤.
     리포트 안 날짜 표시기(제목·부제) 옆에 "(06:00~익일 06:00 KST 기준)"을 항상 병기.
     프로덕션에 쌓인 이벤트가 아직 0건이라 마이그레이션 없이 그대로 적용.
  3) (기능 추가) **`/monitor --full`** — 이번 달 1일~오늘 전체를 한 리포트에 담는다.
     `build_report(full=True)`가 날짜별로 `monitoring/events-*.jsonl`을 각각 읽어
     `REPORT.days[날짜]`에 저장하고, 리포트 상단에 "월간 추이" 그리드(잔디, 날짜별 최악
     톤으로 색칠)가 나타나 클릭하면 그 날짜로 전체(통계·타임라인·표·EXT 탭)가 즉시
     전환된다(`loadDay()` — 서버 재요청 없이 이미 임베드된 데이터 안에서 전환).
     실측 방송 패턴 기준 한 달치 페이로드는 대략 1MB 안팎으로 추정 — Telegram 문서
     전송 한도·브라우저 파싱 모두 문제 없는 크기라 클라이언트 재조회 없이 서버에서
     통째로 만드는 쪽을 선택(잔디 클릭마다 GitHub raw를 다시 fetch하는 구조는 healthchecks/
     Vercel 조회에 필요한 키를 클라이언트에 노출해야 해서 기각). 인자 없는 `/monitor`·
     `--auto` 자동 실행은 계속 하루치만(가벼움 유지).
- **v3.5.0** (기능 교체) — `/push-monitor`(git 커밋 기반 Vercel 배포 한도 감시)를
  `/monitor`(실제 파이프라인 이벤트 기반 운영 모니터링)로 완전 교체.
  1) `src/backend/monitor_log.py` 신규 — tick/wake/preview 전이/notice/tweet/relay/
     운영자 `/pause`·`/resume` 마다 `monitoring/events-YYYY-MM-DD.jsonl`(data 저장소,
     KST 날짜)에 한 줄씩 append. 공통 필드 `ts/flow/result/who/detail` + 흐름별 추가
     필드, `result`는 `ok`/`degraded`/`err` 3톤(성공/실패로 미리 뭉치지 않음). tweet/relay는
     `via`(`ingest`|`ops`)로 X 웹훅 자동 인입과 `/edit` 수동 교체를 구분해서 남긴다.
  2) `src/backend/monitor_report.py` 신규 — 하루치 이벤트 로그 + healthchecks.io
     읽기 전용 API(백엔드 상태 4색) + 코드 저장소 커밋 수(Vercel push 요약)를 모아
     대시보드 html 생성. 트리거(운영자 제어/정기수집·라이브감지/X 웹훅 인입) → preview
     생애주기·릴레이·소식·개인 트윗을 한 시간축에 그린다(2026-09-16 세션에서 Artifact
     목업으로 먼저 검증한 UI). 실데이터라 목업에 있던 여러 날짜 브라우징(잔디)·인과관계
     점선·트윗 말풍선/썸네일은 뺐다 — 재현 근거 데이터가 없어서. 다른 날짜는
     `/monitor YYYY-MM-DD`로 재요청.
  3) `control.json`의 `push_monitor_auto` → `monitor_auto`로 개명(기존 값은 리셋되니
     배포 후 `/monitor --auto` 재실행 필요). Cloud Scheduler 잡도
     `mewtype-push-monitor`(`/push-monitor`) → `mewtype-monitor`(`/monitor`)로 교체.
  4) `src/backend/push_monitor.py`는 대시보드 코드를 걷어내고 `fetch_commits`/
     `list_branches`(Vercel push 요약이 재사용)만 남김 — 옛 대시보드 배경(2026-09-13
     Vercel 100/일 한도 사고)은 이 문서의 v3.2.2~v3.4.x 항목 참고.
- **v3.4.7** (기능 추가) — 하단 푸터에 비공식 팬 메이드 프로젝트 안내 문구.
  구글 검색 노출을 검토하다 "커뮤니티 공개 수준을 유지하되, 비공식·비영리임은 명시해두자"로
  결론 — `#foot-updated` 옆에 `#foot-disclaimer`(`.fdisc`) 추가. 기본 문구(비공식 팬 메이드
  프로젝트임을 밝히는 문장)는 항상 노출되고, 나머지 4건(비영리·저작권 귀속·정보 출처 한정·
  AI 번역 서비스 안내)은 `소식` 티커처럼 4초 간격으로 1개씩 순환 표시하다가 마우스
  호버/포커스 시 4건 전체가 펼쳐지는 팝오버로 보인다. 순환 문구가 폭을 넘치면(길이가 길어
  2줄로 꺾이려 할 때) `notices.js`의 marquee 기법(세그먼트 2개를 이어붙여 `translateX(-50%)`
  무한 루프)을 그대로 재사용해 항상 한 줄을 유지한다. 모바일(≤767px)은 순환 문구를 숨기고
  짧은 라벨만 보이되, 탭하면(포커스) 같은 팝오버가 화면 중앙에 고정폭으로 뜬다.
- **v3.4.6** (기능 보강, 핫픽스 1건 포함) — 인용(QRT) 카드 번역.
  (핫픽스) `/translate tweet` 수동 명령이 트윗 본인 텍스트(`text_ko`)만 확인하고 인용문
  (`quote.text_ko`)은 아예 안 봐서, 인용문이 미번역인 채로 남아 있어도 "모두 번역돼
  있습니다"로 잘못 보고하고 아무 것도 안 하던 것 수정 — `_handle_translate` 가 이제
  각 트윗의 `quote` 도 같은 재사용 우선 로직(`xtweet.find_reused_ko`)으로 확인·번역한다.
  v3.4.5 에서 인용 트윗 텍스트·이미지를 말풍선에 표시하게 됐지만 번역이 안 붙어 원문(일본어)
  그대로만 보이던 것 — `quote`에 `text_ko` 필드를 추가하고, `xtweet.find_reused_ko`로 같은
  원문이 tweets.json/tweet_archive.json/notices.json 어디든 이미 번역된 적 있으면 그 번역을
  재사용, 없을 때만 LLM 을 새로 호출(실패 시 `quote.needs_tl` 로 큐잉해 다음 tick 재시도).
  같은 인용 원본이 여러 멤버·트윗에 반복 등장해도(오탈자 정정 재게시 등) 매번 재번역하지
  않는다. `tweets.js`는 번역 토글이 한국어일 때 `quote.text_ko`를 표시.
- **v3.4.5** (핫픽스) — 개인 트윗 ingest 3건.
  1) `xtweet.parse_schedule` 게이트가 `明日`(내일) 류 상대날짜를 못 읽어, "次回の配信予定は
     明日22:00！" 처럼 명시 날짜 없이 `明日`+시각만 있는 예고 트윗이 배지로만 남고
     preview(예고판)로 안 올라가던 것 수정 — `今日`류(당일)와 같은 자리에서 `xrelay._TOMORROW_WORD`
     를 재사용해 +1일로 반영.
  2) 개인 트윗이 남의 글을 인용(QRT)하면서 이미지를 실었을 때, 인용된 글의 텍스트·이미지가
     말풍선에 전혀 안 보이던 것 — `telegram_app._enrich_personal_media` 가 vxtwitter 로 본인
     첨부 미디어 + 인용 트윗(있으면)을 재조회해 `tweets.json` 행에 `media`/`quote` 로 채우고,
     `tweets.js` 가 말풍선 안에 썸네일/인용카드로 표시한다. 인용된 글 자체는 표시만 하고
     예고 파싱 등 ingest 대상엔 넣지 않는다.
  3) 짧은 간격으로 개인 트윗이 연달아 여러 건 ingest 돼도(각각 `data` 브랜치 커밋 1회) Vercel
     배포 예산은 안 먹는다 — `src/frontend/vercel.json` 이 `main` 외 전 브랜치 배포를 이미
     막고 있고(v3.4.2 정정에서 확정), Push Monitor 한도 판정도 `code_main`(main 브랜치 push)만
     본다. 코드 변경 없음 — 기존 설정으로 이미 충족돼 있음을 확인.
- **v3.4.2** (버그 수정) — 실제 모바일 캡처로 발견된 v3.4.1 회귀 3건 수정.
  1) 상세 SVG 차트가 `viewBox`만으로 좁은 화면에 과도하게 축소돼(144개 10분bin
     막대가 2~3px로 뭉개짐) 육안 확인 불가 — `#chart{min-width:760px}` 추가해
     넓은 화면에선 그대로 유연하게 줄고, 그 아래로는 `.chart-wrap`의 기존
     `overflow-x:auto`로 가로 스크롤(막대 폭 확보, 실측 5.3px/막대로 개선)하도록.
  2) v3.4.1에서 "한도 초과" 판정을 `code_main`(실제 배포 대상인 main 브랜치 push)
     단독 → 그날 총 push 건수로 바꿨던 게 잘못이었음. `vercel.json`이 data/
     devpapers 브랜치를 배포 트리거에서 제외해서, 실제 Vercel 배포 시도는
     `code_main`만 카운트된다 — total 은 data 브랜치 봇 커밋까지 섞여 한도와
     무관. 실측(2026-09-08~13): total 100+ 인 날에도 code_main 은 최대 30이었고
     실제로 배포는 정상 동작했음(운영자 기억과 일치). `code_main` 기준으로 원복,
     라벨도 "Vercel 배포 한도(100/일) 초과일"로 되돌림.
  3) 상단 스탯 카드 "마지막 한도초과 이후"(도움 안 되는 정보) → "이번달 한도초과
     일수"로 교체.
- **v3.4.1** (모바일 대응 + 버그 수정) — Push Monitor UI/로직 정리.
  1) 잔디 그리드를 연간 전체 → 한 달만(`◀ YYYY-MM ▶`) 보여주도록 축소, 년월
     버튼을 누르면 스크롤 스냅 기반 년/월 다이얼 팝업으로 바로 이동(라이브러리 없이
     네이티브 스크롤 스냅만 사용). 옆 월별 추이 차트·분기 비교·요약 표는 계속
     연 단위(currentYear)로 동작.
  2) 상세 SVG 차트를 고정폭(1040px) → `viewBox` 기반 반응형으로 바꿔 모바일에서
     가로 스크롤 없이 화면 폭에 맞게 축소되게 함.
  3) 범례를 자동화/수동제어/코드/기타 4그룹으로 묶어 표시, 이벤트 표는 640px
     이하에서 카드형 레이아웃으로 전환, 날짜 셀·연도 이동 버튼 터치 타깃 확대.
  4) 상단에 "오늘 총 커밋 / 최다 카테고리 / 마지막 한도초과 이후" 요약 스탯 카드 추가.
  5) `notice` 범례 색(#2E9E5C)이 `tweet`(#43A047)과 정상 시력에서도 구분이 거의
     안 되던 문제(델타E 2.8) 수정 — 청록 쪽(#00806B)으로 이동, 델타E 16.5로 개선.
  6) 잔디 그리드·요약 표의 "한도 초과" 판정 기준을 `code_main`(코드 push)만 세던
     것 → 그날 전체 push 총건수(`total`) 기준으로 변경. 아울러 이 한도값이
     Vercel Hobby 플랜 실제 한도(하루 100회)와 다르게 200으로 잘못 박혀 있던
     것도 100으로 정정 — 안내 문구(`Hobby 플랜 하루 100건`)와도 이제 일치.
- **v3.4.0** (변경) — Push Monitor 범례 색을 작업 성격별로 재배정(자동화=녹색계 /
  수동제어=노란계 / 코드 push=회색 / 기타·예외=빨강, 배경 대비 시인성 확보) +
  실행 방식 전면 개편: html을 더 이상 GitHub에 커밋하지 않고 텔레그램 DM으로만
  전송(`Telegram.send_document()` 신설). 매시간 자동 커밋(Cloud Scheduler
  `mewtype-push-monitor`)을 없애고, 텔레그램 `/push-monitor` 명령으로 대체 —
  인자 없이 치면 즉시 1회 tick+DM, `--auto`면 매일 KST 06:00 자동 tick+DM 켬,
  `--off`면 끔(`control.json` `push_monitor_auto` 플래그, Cloud Scheduler는
  1일 1회 가볍게 깨워 플래그만 확인). `monitoring/push_monitor_history.json`(집계
  수치만) 은 계속 devpapers에 누적 커밋하되, 조회 기간을 고정값 대신
  `_backfill_days()`로 history 마지막 기록일 대비 자동 확장 — `--auto`를
  며칠~몇 달 꺼뒀다 켜도 그 사이 날짜가 누락되지 않는다.
- **v3.3.0** (기능 추가) — Push Monitor 대시보드(`docs/PUSH_MONITOR.html`, `devpapers`
  브랜치) + 문서 브랜치 분리. 새 모듈 `src/backend/push_monitor.py` — GitHub REST API
  로 `data`/`main` 브랜치 최근 7일 커밋 이력을 읽어 카테고리별(preview/tweet/notice/
  undo_snapshot/personal_schedule/xrelay/manual/기타/코드) 10분 단위 누적 막대로
  집계, 날짜별 히트맵(총 push 건수, 클릭 시 그 날 상세로 드릴다운) + 인터랙티브 SVG
  차트(호버 시 시간대·카테고리별 건수 툴팁)로 렌더링해 1시간마다 `POST /push-monitor`
  (Cloud Scheduler `mewtype-push-monitor`)가 자동 커밋. Vercel 배포 quota 재소진
  조기 감지용(v3.2.2 사고 재발 방지). `gh_store.py` 에 `read_text`/`write_text`
  추가(HTML 등 비-JSON 파일용, PUT 로직은 `write_json` 과 공유).
  겸사겸사 `docs/` 를 정리 — 개발 중 상시 참조하는 4개(SPEC.md·TERMINOLOGY.md·
  VERSION.md·INGEST_FLOW.md)만 `main`에 남기고, 나머지(배경자료·구버전 기록·
  운영자용 설명자료 등)를 새 `devpapers` 브랜치로 이전. `data` 브랜치와 같은 이유로
  Vercel 배포 트리거 밖(`vercel.json`)에 둔다.
- **v3.2.2** (핫픽스) — `handlers.py` 의 v3.1.17 "wake 하트비트"(상태 변화가 없어도
  `/wake` 마다 `generated_at` 을 무조건 지금 시각으로 갱신)를 완전히 제거. 방송이
  여러 건 겹치면 각자 3~10분 간격인 wake 들이 서로 어긋나며 겹쳐서, 상태 변화가
  전혀 없어도(심지어 수 초 간격으로) 커밋이 발생하고 있었다. 실측(2026-09-13):
  24시간 `preview.json` 커밋 118건 중 92건(78%)이 `generated_at` 한 줄만 다른
  순수 하트비트였고, `data` 브랜치 커밋이 (vercel.json 위치 버그로 인해) 전부
  Vercel 배포 시도로도 잡히는 바람에 이 하트비트 폭증이 Hobby 플랜 "하루 100회
  배포" 한도를 소진시켜 실제 배포가 막히는 사고로 이어졌다. 이제 실질 변화가
  없으면(`_stable_view` 동일) `generated_at` 도 prev 값 그대로 두어, `gh.write_json`
  이 완전한 무변화로 보고 **커밋 자체를 생략**한다 — 프론트 "업데이트" 표시는 실제
  데이터가 바뀔 때만 움직인다(요청사항). self-test 로 동결 동작 회귀 고정.
- **v3.2.1** (핫픽스) — 비전 OCR 프롬프트가 "출연진 패널이 아니면 없다고 답하라"는
  탈출구 없이 무조건 이름을 뽑으라고만 지시해서, 캐스트 패널이 아닌 이미지(게임/
  일러스트 썸네일 등)에 대해서도 두 모델 다 장식 텍스트를 이름인 것처럼 지어내
  형식만 맞춰 출력했다(실측: "歌枠"라는 장식 문구를 "1. 歌枠"로 답함). `_CAST_PROMPT`
  에 `NONE` 마커를 추가해 패널이 아니면 그것만 출력하도록 하고, `cast_names()`가
  `NONE` 을 확정 실패로 처리해 폴백 모델로 재시도하지 않도록(낭비 방지) 수정.
  실측 재검증: 실제 캐스트 이미지는 여전히 정답과 일치, 무관한 썸네일은 두 모델
  다 `NONE` 응답.
- **v3.2.0** (기능 추가) — 크로스오버 공식 계정(`@bang_dream_on`) 팔로잉 + 비전 OCR
  출연진 판독. 새 모듈 `src/backend/vision.py`(Groq 비전, `qwen/qwen3.8-27b` 주
  + `qwen/qwen3.6-27b` 폴백 — 무료 티어 RPM 30/RPD 1,000/TPM 8,000 공유, 실측상
  이 두 모델은 일반 텍스트 LLM보다 OTPM 이 훨씬 낮아 지수 백오프 대신 즉시 폴백
  1회 전환 방식 채택). `_apply_notice`가 `src_handle`이 대상 계정이면 vxtwitter 로
  첨부 이미지를 얻어 좁은 프롬프트("보이는 글자만 그대로, 지어내지 마라")로 OCR →
  `xrelay.NAME_TO_KEY` 로 5인 매칭 → `notices.json` `participants` 필드에 기록.
  실측(2026-09-13, "アワーノーツ" 특번 이미지): 열린 질문 프롬프트는 발음·번역을
  지어내는 할루시네이션이 섞였으나, 범위를 좁히자 두 모델 다 정답과 완전히 일치.
  프론트 표시는 아직 없음(백엔드 데이터만 축적, 추후 UI 확장 여지).
- **v3.1.21** (핫픽스) — 예고 영역의 "오늘" 버킷이 `scheduled_start - now < 24시간`
  으로만 판정돼, KST 밤에 다음날 새벽 방송이 24시간 이내라는 이유만으로 "오늘"에
  잘못 들어가던 버그 수정(실측: 미야코 9/14 아침 예정 방송이 9/13 밤에 오늘로 노출).
  `render.js bucketKey()` 가 이제 KST 캘린더 날짜 문자열이 정확히 같을 때만 "오늘"로
  판정.
- **v3.1.20** (핫픽스) — 업스트림 알림 축약본 잘림으로 소식(notice) 의 `url` 이
  `"https://…"` 처럼 완결되지 않은 문자열로 남아, 클릭해도 아무 데도 못 가는 깨진
  링크가 그대로 노출되던 버그 수정(실측: `@bang_dream_on` 리트윗). `xnotice.py` 가
  "…"/"..." 포함 URL 후보를 버려 `url=None`으로 떨어뜨리면, 프론트가 이미 갖고 있던
  `tweet_url`(트윗 id 로 구성돼 항상 온전함) 폴백이 자동으로 동작한다.
- **v3.1.19** — `end`(방송 종료) 카드에 배지가 없어 한눈에 파악하기 어렵던 것을 개선.
  live/watching 과 동일하게 썸네일 우상단에 회색 "종료" 배지 추가.
- **v3.1.18** (핫픽스) — `xrelay.merge_announced()` 가 `preview.match_item()` 의
  시각 근접(±4h) 매칭만 보고 기존 항목을 통째로 교체해, 이미 `video_id`/제목/썸네일
  까지 확보된 실물 `upcoming` 항목을 그룹 공식 채널(`@BDP_yumemita`) 일일 스케줄
  재공지가 `video_id` 없는 `announced` 자리표시자로 되돌려버리던 버그 수정(실측:
  2026-09-13 미야코·리츠의 API 확정 upcoming 이 재공지에 덮어써져 watching/live
  전이가 다음 정기 tick 전까지 전혀 일어나지 못함). 매칭된 기존 항목이 이미 상위
  티어(video_id 보유 또는 state != announced)면 핵심 필드는 보존하고 빈 보조 필드만
  채우도록 변경.
- **v3.1.17** (핫픽스) — `preview_build.build_preview` 가 `config/channels.json` 미등록
  채널(외부 굿즈 판매사 등) 영상을 무조건 스킵하던 것 → 이미 추적 중이던 아이템(video_id
  매칭)이면 enrich 를 계속하도록 수정. 예전엔 이미 반영해둔 외부 채널 합동방송이 다음
  tick 에 후보로 다시 잡히자마자 통째로 사라지고(archive 도 안 됨) end 판정도 못 받는
  버그가 실측됨(신규 발견인데 채널 미상인 경우만 계속 스킵).
  같이 보강: 텔레그램 `/edit preview` 로 `state` 를 직접 바꿔도(예: 긴급 종료 처리)
  라벨만 바뀌고 FSM/Cloud Tasks wake/archive 가 전혀 안 따라가던 것 → `_activate_state_edit`
  가 목표 상태에 맞는 실제 로직을 그 자리에서 이행(`none`→즉시 제거+아카이브, video_id
  있으면 메인 서비스 `/wake` 호출로 API 재검증+wake 재예약, 없으면 로컬 FSM 1회 파생).
  `state_since` 도 편집 시점으로 리셋.
  또 하나: `generated_at` heartbeat 이 tick/wake 구분 없이 20분 스로틀이라, live/end 를
  몇 분 간격으로 계속 확인 중이어도 프론트 하단 "업데이트" 시각이 tick 주기로만 움직이는
  것처럼 보이던 것 → `/wake` 는 스로틀 없이 매번 즉시 갱신, `/tick` 만 20분 스로틀 유지.
- **v3.1.16** — v3.1.15 에서 "バンドリ！"/"バンドリ!"/"バンドリ" 세 변형 + 강제 느낌표로
  등록했던 것을 단순화: 등록값은 "뱅드림"(구두점 없이 용어만) 하나로 충분 — 원문에 느낌표가
  있으면 번역에도 그대로 남으므로 굳이 고정할 필요가 없었다. 토큰-영숫자 들러붙음 방지
  로직은 유지. notices.json 에서 원문에 느낌표가 없던 1건("バンドリ13thライブ")의 과잉
  느낌표도 제거.
- **v3.1.15** — 용어집(`GLOSSARY`)에 "バンドリ"("밴드리"로 오역되던 것) 추가. 토큰이
  영숫자에 바로 들러붙어(예: "バンドリ13th") LLM 이 뒤 문장을 통째로 미번역으로 남기던
  부작용을 그 경우에만 공백을 끼워 넣어 수정. 이미 커밋돼 있던 notices.json 4건의 "밴드리"
  표기도 소급 정정(세부 등록 방식은 v3.1.16 에서 단순화됨).
- **v3.1.14** — `llm.py`에 용어집(`GLOSSARY`) 도입: 그룹명 "夢限大みゅーたいぷ"가 호출마다
  "꿈한계대 뮤타입"/"꿈꾸다"/"유메미타" 등으로 제각각 번역되던 것을 "무겐다이 뮤타입"으로
  고정. 프롬프트 지시만으론 불충분해(실측상 무시하고 의역) 입력에서 원문을 자리표시자로
  가려 LLM 이 못 건드리게 하고 응답에서 고정값으로 복원하는 마스킹 방식 채택 — preview
  제목·notice 제목·tweet 번역 전부 이 경로(`translate`/`notice_title`)를 거치므로 세
  파이프라인 어디서든 동일하게 적용됨. 이미 커밋돼 있던 preview·notice·tweet 데이터의
  기존 변형 표기도 소급 정정.
- **v3.1.13** — preview(방송 예고) 제목도 notice/tweet 처럼 LLM 한국어 번역. 계약 A′ 에
  `title_ko`/`needs_tl` 추가 — `preview_build.build_preview` 가 제목 신규·변경 시
  `needs_tl=true` 로 표시하고, `handlers._translate_sweep` 이 (tick 마다) `notices.json`/
  `tweets.json` 과 같은 방식으로 `llm.translate()` 재시도. 프론트 `render.js` 는
  `title_ko` 있으면 `[번역]　—　[원문]` 한 줄(marquee)로 표시(없으면 원문만) — notices.js 와
  동일 포맷. 배포 시점에 이미 떠 있던 preview 4건 제목도 번역해 `data` 브랜치에 소급 반영.
- **v3.1.12** (핫픽스) — v3.1.11 로 배지는 옮겼지만 PC 카드 제목이 여전히 살짝 잘렸던 것
  마저 수정: `card__body`(title+meta 고정 높이)의 padding/gap 이 살짝 커서 두 자연 높이
  합이 가용 공간을 초과 → flexbox 가 근소하게 눌러 글자 아랫부분이 잘렸다. padding/gap
  을 줄여 자연 높이가 가용 공간에 딱 맞도록(잘림 0px, 실측 확인) 조정.
  겸사겸사 모바일에도 marquee 적용: 예전엔 제목을 2줄 클램프(길면 끝 "..." 로 잘림)했는데,
  PC 와 동일하게 한 줄 + 흐르는 marquee 로 바꿔 전체 텍스트가 다 보이게 함
  (`applyMarquees()` 는 이미 화면 크기 무관하게 동작해서 모바일 전용 줄바꿈 CSS만 제거하면 됨).
- **v3.1.11** (핫픽스) — v3.1.10 이 실물 확정 카드(upcoming/watching/live/end)에도 "합동"
  표시를 넣으려고 `card__body`(title+meta 2줄 높이로 고정)에 참여자 라벨을 3번째 줄로
  더했는데, 그 결과 flexbox 가 세 줄을 전부 짓눌러 제목이 점(...)처럼 뭉개지는 화면 깨짐이
  실배포 직후 발견됨(실사례: 리미스타 합동 생중계 카드). 라벨을 body 밖으로 빼서 썸네일
  좌측 상단에 독립 배지("합동")로 대신 — 우측 상단의 상태 배지(LIVE/대기 중)와 안 겹침.
- **v3.1.10** (핫픽스) — `xrelay.parse_live_now` 가 "生配信中"처럼 종결형 어미가 붙은 경우만
  즉시개시 공지로 인식하던 것 → "生配信"(생중계) 단독으로도 인식. 그룹 멤버 전원이 실제로
  콜라보 생중계 중인데도, 그 영상이 `config/channels.json` 미등록 채널(굿즈 판매사 등) 소유란
  이유만으로 놓치던 실사례(5th Single 발매 기념 사인회 생중계, 리미스타 채널)를 계기로 수정.
  `video_id` 기반 enrich(`videos.list`)는 원래 채널 제한이 없으므로 텍스트만 잡아내면 된다.
  같은 계기로 `scheduled_start` 도 종전엔 무조건 ingest 시각을 박았는데, 텍스트에 `本日12時〜`
  같은 당일 시각, `明日20時〜`/`明日朝7:00〜` 같은 익일 시각(`parse_bdp_schedule` 의 `明日`
  +1일 관례와 동일 어휘 확장)이 있으면 그걸 우선하도록 보강 — x-relay 로 찍힌
  `scheduled_start` 는 이후 API 재구성이 못 덮으므로(§1-3-1) 최초 값이 정확해야 함.
  같이 발견된 프론트 회귀도 수정: `render.js` 의 "합동" 배지/좌측 색띠(`card--collab`)가
  `state=="announced"` 카드에만 붙고 실물 확정 이후(`upcoming`/`watching`/`live`/`end`)에는
  전혀 안 붙던 것 — v3.0(6상태 전환) 리팩터링 때 예고 분기로만 옮겨지고 나머지 분기엔
  누락됐던 것으로 보임(v2.4 도입 당시엔 CSS 상 상태 무관 범용 클래스로 설계됨). 이제 실물
  분기에도 참여자 라벨/배지가 뜬다.
- **v3.1.9** (핫픽스) — v3.1.8과 다른 패턴으로 또 `/translate`가 특정 트윗 1건에서 항상
  실패하던 것 수정. 이번엔 의성어 반복이 아니라 "おーまーーたーーせー…"처럼 장음부호를
  글자마다 다른 길이로 끼워 늘려쓰는 강조체 — `_REPEAT_RE`(맨 앞 단일 유닛 반복만 잡음)로는
  못 잡아 LLM이 똑같이 반복 루프에 빠짐(204자 입력 → 2035자 응답, 환각 가드에 매번 걸림).
  장음부호류 연속만 표적으로 접는 정규화를 번역 전에 추가(멤버명·단어·URL의 정상적인
  글자 반복은 건드리지 않도록 표적 축소 후 실 API 검증 완료), `max_tokens` 상한도 추가로
  걸어 미지 패턴 재발 시 방어선을 이중화.
- **v3.1.8** (핫픽스) — `/translate`가 특정 트윗 1건에서 항상 실패하던 것 수정. 의성어가
  8회 이상 연속 반복되는 입력("もぐもぐもぐ…")을 LLM에 그대로 보내면 반복 루프에 빠져
  환각 가드에 매번 걸림(`temperature=0`이라 재시도해도 항상 같은 실패). 반복 구간을
  압축해 단위만 문맥과 함께 번역한 뒤 다시 펼치는 방식으로 회피.
- **v3.1.7** (핫픽스) — v3.1.6 이 대응한 "인코딩 손상"은 조사 도구의 콘솔 인코딩 버그로 인한
  오진단이었음(실제 저장 데이터엔 손상 이력 없음, `data` 브랜치 전 구간 재확인 완료). 대신
  **진짜 원인**을 찾음: 안드로이드 알림 축약본(`contentText`)만 읽히는 경우가 있어 긴 트윗이
  말줄임표도 없이 조용히 잘려서 온다(실측: 9문단 트윗이 앞 3문단·125자만 ingest됨 — 텍스트
  패턴으로 감지 불가능한 잘림). `/ingest`를 "손상 감지 시 복구"에서 "**tweet id 있으면 vxtwitter
  정본을 항상 우선, 실패시만 폰 원문 폴백**"으로 우선순위 자체를 뒤집음. 발견 계기가 된 트윗도
  원문으로 교정.
- **v3.1.6** (핫픽스, v3.1.7 참고) — 폰(Automate)이 이모지 처리 중 트윗 원문 바이트를 깨뜨려
  보내는 걸로 보여 vxtwitter 재조회 복구 로직을 추가했으나, 그 진단 자체가 오진이었음(v3.1.7).
  로직은 무해하게 유지, 실제 문제 해결은 v3.1.7.
- **v3.1.5** (핫픽스) — 모바일에서 다른 앱 갔다가 돌아오면 이미 끝난 방송이 "OOO시간 지각"으로
  잘못 보이던 것 수정. 백그라운드 중 폴링 타이머가 멈춰 화면이 아주 오래된 데이터로 멈춰
  있었던 게 원인 — 포그라운드 복귀를 감지해 즉시 재조회하도록 함(새로고침 없이도 해결).
- **v3.1.4** — 5인 동시시청 등 그룹 공식 채널(`@BDP_yumemita`) 방송이 예고판에 안 뜨던 것 수정.
  이 채널을 RSS/API 폴링 대상에 추가해 실물 영상이 뜨면 자동으로 5인 레인 팬아웃. 더불어
  "配信開始" 같은 즉시개시 트윗도 감지해 폴링을 기다리지 않고 바로 반영.
- **v3.1.3** (핫픽스) — 소식 티커가 번역·원문을 `[번역] — [원문]` 순으로 함께 흐르도록(그동안 원문만 보였고, 제목을 길게 눌러야 번역이 떴음). 수동 번역 명령이 번역문만 채우고 제목은 정규식 결과 그대로 두던 것 → 제목도 LLM 정제본으로 갱신(자동 재시도와 동일). 번역 명령 결과 보고를 총건수·시도·성공·실패·기존 유지로 상세화.
- **v3.1.2** — 자동 수집된 소식도 제목을 LLM 으로 정제·한국어 번역(그동안 정규식 헤드라인 그대로였음). 실패 시 다음 수집 때 재시도. 소식 원문과 정규식 결과를 함께 기록해 두어 이후 파싱·번역 품질 개선에 쓸 수 있게 함(트윗과 동일).
- **v3.1.1** — 기기 다크 모드에서 브라우저의 자동 어둡게 처리가 이미 다크인 화면에 겹쳐, 트윗 말풍선 구분과 예고판 헤더의 유닛별 그라데이션이 뭉개지던 것 수정(사이트가 다크 전용임을 선언).
- **v3.1.0** — 유닛별 개인 트윗을 최근 1건 → 최근 5건 메신저형 스레드로 표시. 연속 메시지 묶음, 안 읽은 개수 배지, 열면 표시분 전부 읽음 처리. 번역 토글은 스레드 단위. 예고성 트윗도 본인 글이면 스레드에 표시하고(예고판 반영은 그대로), 리트윗·타인 글만 제외.
- **v3.0.2** — 예고 목록을 PC에서도 모바일과 같은 3구간(오늘 / 7일 이내 / 그 이후)으로 통합. 레인 헤더 우측에 유튜브·X 바로가기 아이콘 추가.
- **v3.0.1** — 개인 트윗 3건 수정: 다른 유닛 트윗을 열면 번역 토글이 앞 유닛 내용으로 오염되던 것, 알림에서 잘린 유튜브 링크 탓에 예고가 방송 중으로 잘못 승격되던 것, 자동 수집된 트윗이 번역되지 않던 것.
- **v3.0.0** — 방송 상태를 3단계 → 6단계(예고·예정·대기·방송 중·종료)로 확장, 상태 판정을 상시 저장 없이 그때그때 파생. 소식 제목 추출과 개인 트윗 번역에 외부 LLM 도입. 예고 정보를 출처 신뢰도 순으로 병합. 텔레그램 관리 명령을 명령×대상 격자로 재편.
- **v2.8.5** — 소식 파서 정밀화: 지난 이벤트 회고글을 오늘 이벤트로 잘못 등록하던 것 차단, 제목 추출 규칙 개선.
- **v2.8.4** — 라이브 시작 직후 폴링 간격을 좁혀 짧은 방송의 종료 감지 지연 축소.
- **v2.8.3** — 텔레그램 수동 등록이 본문 유튜브 링크로 채널을 자동 판별(실패 시 유닛 되묻기). 소식 편집 명령(제목→날짜→링크 순) 추가.
- **v2.8.2** — 알림 로그 레벨을 알림 종류 기준으로 재정의(간단 / 보통 / 상세).
- **v2.8.1** — 개인 트윗이 방송 예고면 예고판에 자동 반영. 트윗이 알린 시각을 정기 수집이 덮지 않도록 하고, 스트림이 실제로 수정됐을 때만 수집값을 우선.
- **v2.8** — 멤버 5인 개인 트윗 수집 → 예고판 상단 편지 배지(PC 말풍선 / 모바일 토스트), 24시간 수명.
- **v2.7.1** — 소식 티커 마감: 0건도 막대 유지, 펼침을 예고판 위 오버레이로, 모바일 레이아웃 정리.
- **v2.7** — 방송 외 이벤트(라이브 예고·음반/굿즈·타 플랫폼) 자동 수집 → 예고판 상단 소식 티커.
- **v2.6.1** — 알림에서 게시자 이름·트윗 링크도 수신(소식 게시판 준비 단계).
- **v2.6** — 합동방송이 참여 멤버 개인 채널에서 열려도 실물 확정 후 참여자 전원 레인에 표시.
- **v2.5.2** — 되돌리기를 2단계 확인으로 전환, 되돌릴 시점과 대상 목록을 먼저 표시.
- **v2.5.1** — 수동 등록을 2단계 대기(텍스트 / 파일 첨부)로 전환, 인식 실패 줄 수 표시.
- **v2.5** — 텔레그램 수동 관리 명령(목록·삭제·등록·되돌리기).
- **v2.4** — 합동방송을 참여 멤버 전원 레인에 표시, 외부 이벤트 출연 트윗 파서 추가.
- **v2.3** — 공식 일일 스케줄 트윗을 폰이 중계 → 유튜브 영상이 아직 없는 예고 행으로 반영.
- **v2.1** — 텔레그램 봇 상태 모니터링·원격 제어 + 상태 전이 알림.
- **v2.0** — 상시 가동 없는 스케일-투-제로 백엔드 + 방송별 정밀 wake.
- **v1.2** — '오늘'(24시간 이내) 구간 + 분 단위 카운트다운 + 예정 방송 지각 표시.
- **v1.1** — 모바일 1인 1화면 무한 캐러셀 + 레인 헤더·버킷 피드 영역 재디자인.
- **v1.0** — 5채널 RSS+YouTube API 수집 → 시간순 방송 예고판, 반응형 정적 사이트.
