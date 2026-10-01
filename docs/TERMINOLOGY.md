# 용어집 (TERMINOLOGY)

세션이 바뀌어도 같은 대상을 같은 단어로 부르기 위한 기준. 표현이 엇갈리면 여기에 추가한다.

| 정식 명칭 | 가리키는 것 | 쓰지 말 것 |
|---|---|---|
| **프론트엔드** | Vercel 정적 호스팅(`src/frontend/`). 빌드 없음, ES 모듈. `raw.githubusercontent.com` 의 JSON 을 폴링해 렌더링만 함. | 프론트서버, 웹앱 |
| **백엔드** | GCP Cloud Run 서비스(`src/backend/`). 메인 콘텐츠(preview·tweet·notice)를 **판정·상태전이·저장**. Cloud Scheduler/Tasks 트리거, GitHub `data` 브랜치에 커밋. 공개 webhook `mewtype-telegram` 도 이 범주. | 서버(단독), GCP(단독) |
| **업스트림 시스템** | 운영자 폰의 Automate 플로우. X·YouTube 푸시알림을 양식만 맞으면 `POST /ingest` 로 **중계**. 데이터 흐름상 백엔드 앞단의 1st-party 노드이며, 코드베이스 밖이라 런타임에서 관측·버전관리가 안 됨. | 외부 백엔드, 폰 릴레이, 서드파티(★ 진짜 서드파티는 X·YouTube 의 푸시알림 시스템이고, 이 폰 플로우는 그 신호의 중계기) |
| **외부 LLM** | Groq 이 서빙하는 LLM(`gpt-oss-120b`/폴백 `gpt-oss-20b`). v3 부터 상용 운영 중. notice 제목 추출·notice/개인트윗 번역 + (v3.6) 외부 채널 콜라보 참여판정·텍스트 예고 최종확인(`participation`/`announces_own_broadcast`) + (v3.2) 크로스오버 공지 비전 OCR. 실패(5xx·재시도 소진)는 정규식/보수적 미등록으로 폴백(정규식이 기준선, LLM 은 보강 — 단 v3.6 최종확인 게이트는 LLM 없이는 등록 자체를 안 함). | 외부 백엔드2, LLM 서버 |
| **제어 채널** | 운영자가 백엔드를 제어·조회하는 경로. 명령(`/status` `/pause` `/resume` `/list` `/ingest` `/edit` `/del` `/undo` 등)으로 `control.json`·`admin_state.json` 을 바꾸거나 상태를 읽음. 데이터 경로(`/tick` `/wake`)와 분리된 out-of-band 경로. 현재 transport 는 텔레그램, 실체는 공개 webhook 서비스 `mewtype-telegram`. | 텔레그램 봇(개념 지칭 시), 관리 콘솔 |

## 관련 용어 (위 항목에 딸린 것)

- **`POST /ingest`** — 업스트림 시스템이 중계한 푸시알림 텍스트를 백엔드가 받는 공개 엔드포인트. transport 추상화 경계 — 입력 소스가 바뀌어도 이 이후 스키마는 불변.
- **`data` 브랜치** — 백엔드가 상태를 커밋하는 GitHub 브랜치. 코드 없음, JSON 만.
- **`monitoring` 브랜치** (v3.9) — 데이터 저장소의 **로그 전용** 브랜치. 이벤트 로그
  (`monitoring/events-*.jsonl`)·모니터 스냅샷(`latest.html`)·유실 원문 큐(`lost_queue.json`)가
  여기 쌓인다. `data` 에서 분기해 만들어 과거 로그를 히스토리째 승계했다. **분리한 이유**는
  GitHub Contents API 의 PUT 이 파일이 아니라 **브랜치 HEAD 단위로 충돌**하기 때문 — 이 로그들은
  `/write` 직렬화 창구를 거치지 않고 제어 채널이 직접 커밋하는데, 제어 채널은 인스턴스가 최대
  20개라 버스트 때 `data` 브랜치 쓰기를 409 로 밀어냈다(2026-09-24 트윗 유실 사고).
  env `MONITOR_BRANCH` 로 지정(기본 `monitoring`). "로그 브랜치"라고 불러도 되지만 문서·코드
  표기는 `monitoring` 브랜치로 통일.
- **`devpapers` 브랜치** — 개발 중 상시 참조하지 않는 문서(배경자료·구버전 기록·운영자용
  설명자료 등)를 모아두는 GitHub 브랜치. `docs/`에서 개발 시 계속 쓰는 4개
  (`SPEC.md`·`TERMINOLOGY.md`·`VERSION.md`·`INGEST_FLOW.md`)만 `main`에 남기고 나머지가
  여기 있다. `PUSH_MONITOR.html`처럼 자동으로 시간마다 갱신·커밋되는 문서도 여기 둔다 —
  `data` 브랜치와 같은 이유로 Vercel 배포 트리거에서 제외돼 있다(`vercel.json`). **"docs
  브랜치"라고 부르지 말 것** — `docs/` 폴더명과 헷갈린다.
- **메인 콘텐츠** — preview(방송예고) · tweet(개인 트윗) · notice(공식 소식) 3종.
- **모니터링 스냅샷** — (v3.8.9) 매일 KST 06:10 백엔드 `/monitor` 가 방금 끝난 하루(06:00~익일
  06:00 KST)의 모니터 리포트 데이터를 계산해 굳혀 둔 것. `monitoring/days/YYYY-MM-DD.json`
  (하루치 상세) + `monitoring/summary.json`(전 기간 잔디용 요약), `monitor_snapshot.py`.
  웹 monitor 는 오늘치만 실시간으로 계산하고 지난 날짜는 이것을 읽는다. 외부 조회값
  (healthchecks.io·Vercel)은 찍은 시각(`snapshotAt`) 기준. **"스냅샷"만 단독으로 쓰지 말 것** —
  undo 스냅샷(`/undo` 되돌리기용), reconcile 의 "이전 스냅샷 대비 diff" 와 헷갈린다.

## v4a 용어 (브랜치 `v4a` — 2026-09-29 구현, 미배포)

`ref/v4a/v4a_design.md` §3 에서 2026-09-28 확정한 용어를 v4a 구현과 함께 옮긴다. 현행 운영(v3.8.10)을 가리킬 때는 위 표의
이름(백엔드 · 제어 채널 · `/tick` 등)을 그대로 쓰고, v4a 구성 요소를 가리킬 때만 아래 이름을 쓴다.

| 정식 명칭 | 가리키는 것 | 현행 대응 · 쓰지 말 것 |
|---|---|---|
| **접수 서비스** (`mewtype-intake`) | 바깥에서 오는 모든 것을 받는 공개 서비스 — `/ingest` · 관리 페이지 · 텔레그램 비상 명령 · 외부 호출로 가공. data 브랜치에 쓰지 않는다 | 현행 제어 채널 `mewtype-telegram` |
| **쓰기 서비스** (`mewtype-writer`) | data 브랜치를 쓰는 **유일한** 주체. reconcile · 작업 적용 · 다음 확인 예약 · 알림 DM | 현행 백엔드 `mewtype-backend` |
| **적용 큐** (`mewtype-apply`) | 쓰기 서비스로 작업을 하나씩 전달하는 큐. 모든 쓰기 요청 · reconcile 요청이 여기로 | 현행 wake · tick 예약 큐 · `/write` |
| **가공 큐** (`mewtype-enrich`) | 번역 재시도를 쓰기 경로 밖(접수 쪽)에서 하게 전달하는 큐 | 현행 tick 안 `_translate_sweep` |
| **reconcile(범위)** | "지금 상태가 어때야 하나"를 다시 계산해 data 에 맞추는 동작. 범위 = 전체 또는 영상 하나. 즉시 wake · 자기 호출 · 재개 tick 을 전부 대체 | 현행 `/tick` · `/wake` |
| **작업 · 작업 id** | 적용 큐로 전달되는 요청 하나와 그 식별자(태스크 이름 = 중복 적재 방지) | job(단독) |
| **`ops` 브랜치** | 운영 상태 — `control.json` · `admin_state.json`(재등록 차단 · 잔재 슬롯) · 작업 이력(`history.json`) · 로그인 nonce | 현행 data 브랜치의 control · admin_state |
| **관리 페이지** | 운영자 웹 화면(`/admin`). 로그인 = 텔레그램 `/admin` 일회용 링크 | 관리 콘솔, 어드민 |
| **텔레그램 비상 명령** | v4a 에서 텔레그램에 남는 명령 — `/status` `/pause` `/resume` `/list` `/admin` | — |
| **`out`** | (v4a D7) preview 아이템이 `preview.json` 에서 빠져 `preview_archive.json` 으로 가는 신호. 저장되는 상태가 아니다(FSM 파생 값). 구 이름 `none` — 옛 모니터 로그의 `none` 은 같은 뜻으로 읽는다 | `none`(preview 상태를 가리킬 때). YouTube `liveBroadcastContent="none"` · 소식 `mode:"none"` 은 다른 뜻이라 그대로 |
| **`yt_notif` 작업** | (v4a D1~D3) 업스트림 YouTube 알림을 상태 신호로 쓰는 적용 큐 작업 — reconcile(영상) 후 30분 전 알림 → watching, 시작 알림 → live, URL 없는 예고는 ±45분 자리표시에 URL 부여 | — |
| **로컬 시험판** *(제안 — 사용자 확인 전)* | v4a 를 배포하지 않고 운영자 로컬 PC(24시간)에서 돌리는 형태. 저장은 `_local/<브랜치>/`, 폰 알림은 Tailscale 로 수신 | — |
| **로컬 러너** *(제안 — 사용자 확인 전)* | 로컬 시험판을 한 프로세스로 띄우는 `python -m src.backend.local_runner` — 접수 앱 + 쓰기 스레드 `q-apply` + 가공 스레드 `q-enrich` + 정기 잡 스레드 + 텔레그램 폴링 | — |
| **프리미어** | YouTube 「プレミア公開」 — 미리 올린 녹화본을 정해진 시각에 다 같이 처음 보는 공개 방식(대기실 · 실시간 채팅 · 끝나면 일반 영상). API 는 라이브 예정(`upcoming`)과 똑같이 보고하므로 `VideoInfo.is_premiere`(업로드 상태 `processed` / duration ≠ `P0D`)로 가른다. v4a 는 **그룹 공식 채널** 프리미어만 방송 카드에서 뺀다(D26, `preview_build.is_group_release`) — 멤버 개인 채널 프리미어는 카드로 올린다. OBS 로 녹화본을 틀어 켜는 방송은 API 상 생방송이라 프리미어가 아니다 | 노래 영상(프리미어가 아닌 일반 업로드 노래 영상 · 歌枠 생방송까지 섞여 들린다), 녹화 방송 |
