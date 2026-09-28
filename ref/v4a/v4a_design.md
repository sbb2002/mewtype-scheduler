# v4a 설계안 — 서비스 2개 유지 + 적용 큐 일원화 + reconcile 통일 + 웹 관리 페이지

- 작성: 2026-09-28 · 기준 커밋 `origin/main` `6af6db7` (v3.8.10)
- 상태: **설계안 (미구현 · 미측정)**. 채택 여부는 §11 측정으로 결정.
- 함께 보는 자료: 흐름도 `ref/v4a/v4a_flow.html` · 기능 사용 점검 `ref/v4a/v4a_feature_audit.md` ·
  현재 기능 지도 `ref/v3b/v3b_feature_map.md` · 현재 배선 지도 `ref/v3b/v3b_wiring_map.md` · v3b 목표안 `ref/v3b/v3b_target_flow.html`
- 표기: **(확인 필요)** = 코드 · 공식 문서로 아직 검증하지 않은 가정. **(선택)** = 사용자가 아직 정하지 않아 기본값으로 둔 설계 선택.
- **용어**: 이 문서는 §3의 v4a 용어를 쓴다. 현재(v3.8.10) 시스템을 가리킬 때만 현재 이름(제어 채널 · 백엔드 · `/tick` 등,
  `docs/TERMINOLOGY.md` 기준)을 쓰고 "현재"라고 밝힌다. v4a 용어는 채택 · 구현 시점에 `docs/TERMINOLOGY.md` 로 옮긴다.

### 사용자 결정 (2026-09-28)

| 결정 | 내용 |
|---|---|
| 방향 | v4a = 서비스 2개 유지 + Cloud Tasks 적용 큐 일원화 + reconcile 통일 + `ops` 브랜치 |
| 이름 | §3 (접수 서비스 `mewtype-intake` · 쓰기 서비스 `mewtype-writer` · 적용 큐 · 가공 큐 · `/reconcile` · `/snapshot`) |
| 운영 조작 | 텔레그램 마법사 명령을 **웹 관리 페이지 하나**로 옮긴다 — 마법사는 급할 때는 되지만 복잡한 수정이 불편했음 |
| 로그인 | **텔레그램 일회용 링크** — 봇에 `/admin` → 서명된 짧은 수명 링크를 DM으로 받음 |
| 텔레그램 역할 | **알림 DM + 비상 명령**(`/status` `/pause` `/resume` `/admin`)만 |
| 드문 기능 | 9b(비YouTube URL → 소식) · 크로스오버 비전 OCR · 11(회원 전용 라이브) · 날짜만 있는 예고 — **유지** |
| 아워노츠 계정 알림 | 폰에서 계속 보낼 수 있으나 **처리 규칙은 만들지 않는다** (현재처럼 받고 반영 안 함) |
| 기능 전부 | 현행 26가지 기능(세부 37행)은 전부 v4a에서 동작해야 함 |

---

## 1. 왜 — 엉킴의 뿌리 두 가지 (+ 운영 조작의 불편)

**① Git 브랜치를 여러 곳이 동시에 쓰는 데이터베이스로 쓴다.**
GitHub Contents API는 브랜치 HEAD 단위로 충돌한다 — 파일이 달라도 먼저 커밋한 쪽 외에는 409.
그동안의 큰 패치(현재 백엔드 `max-instances=1`, v3.7 `/write` 쓰기 큐, v3.9 409 재시도 · `monitoring` 브랜치 분리 · 429 백오프)가
대부분 이 성질을 우회하려고 생겼다. 그런데도 현재 제어 채널이 data에 직접 쓰는 경로(`/translate` · `admin_state` · `control.json`)가 남아 있다.

**② "즉시" 처리하려는 지름길 배선이 기능마다 따로 붙었다.**
"알림 오면 바로 wake"(#12), "편집하면 바로 재확인"(#14d 자기 호출), "재개하면 바로 tick"(#16) —
이벤트가 생긴 자리에서 다음 동작을 직접 부른다. #12는 실측으로도 확인됐다 — 09-23~27 YouTube 앱 알림 24건이 즉시 확인을 요청했지만 예약되지 않았다(`v4a_feature_audit.md` §3).
반대로 **정기 tick은 매번 전체를 다시 계산하므로** 이벤트를 놓쳐도 다음 바퀴에 복구된다.

**③ 텔레그램 마법사는 복잡한 수정에 맞지 않는다.**
한 번에 한 필드를 되묻고, 그 대화 상태를 `admin_state.json` 에 만료 슬롯으로 저장한다(현재 대기 슬롯 7종 + 편집 락, 현재 `admin_state.json` 기준).
조작이 몇 건 안 되는 데 비해(점검: 09-24~25 명령 14건, 트윗 · 소식 수동 반영 0건) 이 대화 상태가 data 브랜치 쓰기를 늘리고,
확인 대기 슬롯이 정리되지 않고 남는 일도 있었다(현재 `pending_del` 잔존). `/undo` 는 슬롯이 하나라 자동 작업에 덮인다.

## 2. 참고한 업계 방식

| 패턴 | 요지 | v4a에서 |
|---|---|---|
| Single writer + 내구성 있는 큐 (inbox 패턴) | 공유 상태는 한 주체만 쓰고, 나머지는 요청을 큐에 넣기만 | 쓰기 서비스만 data를 씀. 접수 서비스는 적용 큐에 적재 |
| Level-triggered reconcile (쿠버네티스 컨트롤러 방식) | 이벤트를 따라가지 않고 "지금 어때야 하나"를 매번 계산 | 지름길 배선을 전부 `reconcile(범위)` 요청으로 통일 |
| Functional core, imperative shell | 판단은 순수 함수, 입출력은 바깥 껍데기 | `preview.py` · `statemachine.derive` · `merge_*` 는 그대로 |
| Modular monolith 우선 | 보안 · 확장 요구가 실제로 다를 때만 서비스를 나눔 | 공개 접수 / 비공개 쓰기 2개 유지 |
| Admin console + optimistic concurrency | 운영 조작은 대화형 명령이 아니라 폼 한 번 제출. 동시 수정은 잠금 대신 "열 때 본 값"과 비교 | 관리 페이지 + 제출 시 열람 값 동봉 → 적용 때 충돌 확인 (편집 락 불필요) |
| Magic link 로그인 | 비밀번호 대신 이미 신뢰하는 채널로 일회용 링크 전달 | 텔레그램 봇이 운영자 chat_id로 링크 DM |
| Strangler fig | 새 경로를 하나씩 붙이고 옛 경로를 걷어냄 | §12 단계마다 배포 가능 |

## 3. v4a 용어

이름 규칙: **서비스는 역할(동사)로, 큐는 전달하는 엔드포인트 이름으로, Scheduler 잡은 부르는 동작으로.**

### 구성 요소

| v4a 용어 | GCP 리소스 이름 | 정의 | 현재(v3.8.10) 대응 |
|---|---|---|---|
| **접수 서비스** | Cloud Run `mewtype-intake` (공개) | 바깥에서 오는 모든 것을 받는 공개 서비스. 업스트림 알림 접수, 관리 페이지 · 관리 API, 텔레그램 비상 명령, 외부 호출로 가공(LLM · vxtwitter · videos.list · yt-dlp · OCR), 적용 큐 적재, 웹 모니터. **data 브랜치에 쓰지 않는다** | 제어 채널 `mewtype-telegram` |
| **쓰기 서비스** | Cloud Run `mewtype-writer` (비공개, 동시 1 · 인스턴스 1) | data 브랜치를 쓰는 **유일한** 주체. reconcile · 작업 적용 · 다음 확인 예약 · 결과 기록 · 알림 DM · 모니터링 스냅샷 | 백엔드 `mewtype-backend` |
| **적용 큐** | Cloud Tasks `mewtype-apply` (동시 전달 1) | 쓰기 서비스 `/apply` 로 작업을 하나씩 전달. 모든 쓰기 요청 · reconcile 요청이 여기로 | 현재 wake · tick 예약 큐(`TASKS_QUEUE`) |
| **가공 큐** | Cloud Tasks `mewtype-enrich` (신규) | 접수 서비스 `/enrich` 로 번역 재시도 요청을 전달 | 없음 (tick 안 `_translate_sweep`) |
| **관리 페이지** | 접수 서비스가 서빙 (`/admin`) **(선택)** | 운영자가 쓰는 웹 화면 하나 — 예고 · 소식 · 트윗 목록과 편집 · 삭제, 원문 투입(미리보기 → 확정), 작업 이력 · 되돌리기, 유실 원문 재투입, 운영 설정, 리포트 | 텔레그램 명령 · 마법사 |
| **텔레그램 비상 명령** | 접수 서비스 `/telegram` | `/status` `/pause` `/resume` `/admin` 만. 관리 페이지가 안 열릴 때의 비상구 | 텔레그램 명령 전부 |
| **정기 reconcile 잡** | Cloud Scheduler `mewtype-reconcile-10m` · `mewtype-reconcile-daily` | 10분마다 · 매일 06:00 JST 쓰기 서비스 `/reconcile` 호출 (daily는 아바타 포함) | `mewtype-light` · `mewtype-baseline` |
| **스냅샷 잡** | Cloud Scheduler `mewtype-snapshot-daily` | 매일 06:10 KST 쓰기 서비스 `/snapshot` 호출 | `mewtype-monitor` |
| **`data` 브랜치** | 데이터 저장소 | 공개 콘텐츠(preview · notices · tweets + archive)만. 쓰기 서비스만 쓴다 | 같음 (admin_state · control 이 빠짐) |
| **`ops` 브랜치** | 데이터 저장소 (신규) | 운영 상태 — control · suppress(재등록 차단) · **작업 이력** · 로그인 링크 사용 기록 | 없음 (현재 data 브랜치 `admin_state` · `control`) |
| **`monitoring` 브랜치** | 데이터 저장소 | 이벤트 로그(작업 결과 포함) · 모니터링 스냅샷 · 유실 큐 | 같음 |

### 엔드포인트

| 엔드포인트 | 서비스 | 호출자 | 하는 일 | 현재 대응 |
|---|---|---|---|---|
| `POST /ingest` | 접수 | 업스트림 시스템 | X · YouTube 알림 접수 (경로 유지) | 같음 |
| `POST /telegram` | 접수 | Telegram webhook | 비상 명령 4개만 | 명령 전부 |
| `GET /admin` | 접수 | 운영자 브라우저 | 관리 페이지 (로그인 세션 필요) | 없음 |
| `GET /admin/login?t=…` | 접수 | 로그인 링크 | 일회용 토큰 확인 → 세션 쿠키 발급 | 없음 |
| `GET /admin/api/…` | 접수 | 관리 페이지 | 목록 · 상태 · 작업 이력 · 유실 원문 · 작업 결과 조회 (읽기) | 조회 명령 |
| `POST /admin/api/…` | 접수 | 관리 페이지 | 조작 → 대부분 적용 큐 적재, 운영 설정은 `ops` 직접 | 수정 명령 · 마법사 |
| `POST /enrich` | 접수 | 가공 큐 (OIDC, 앱 안 검증) | 번역 재시도 → 결과를 적용 큐에 적재 | 없음 |
| `GET /monitor-live` | 접수 | 프론트 `monitor.html` | 웹 모니터 즉석 생성 (읽기 전용) | 같음 |
| `POST /reconcile` | 쓰기 | 정기 reconcile 잡 | `reconcile(전체)` | `/tick` |
| `POST /apply` | 쓰기 | 적용 큐 | 작업 하나 적용 (콘텐츠 반영 · 관리 조작 · `reconcile(범위)`) | `/write` + `/wake` + Tasks발 `/tick` |
| `POST /snapshot` | 쓰기 | 스냅샷 잡 | 모니터링 스냅샷 + 멤버 현황 DM | `/monitor` |

### 동작 용어

| 용어 | 정의 |
|---|---|
| **reconcile(범위)** | "지금 상태가 어때야 하나"를 다시 계산해 data에 맞추는 동작. 범위는 `전체` 또는 `영상 하나`. 정기 reconcile 잡은 `/reconcile` 로, 나머지는 적용 큐 → `/apply` 로 요청한다 |
| **적재** | 적용 큐 · 가공 큐에 작업을 넣는 것. 넣으면 바로 돌아가고 결과를 기다리지 않는다 |
| **작업 · 작업 id** | 적용 큐로 전달되는 요청 하나와 그 식별자(Cloud Tasks 태스크 이름으로도 사용 — 중복 적재 방지). 종류는 현재 `writers.py` 잡 종류 재사용 + `reconcile` + 관리 조작. 서로 독립 · 멱등이어야 한다(§10) |
| **작업 결과** | 쓰기 서비스가 작업을 적용한 뒤 `monitoring` 이벤트 로그에 작업 id와 함께 남기는 한 줄. 관리 페이지는 이것을 조회해 "반영됨 / 충돌 / 실패"를 보여준다 **(선택)** |
| **열람 값 · 충돌** | 관리 페이지가 폼을 열 때 본 필드 값. 제출 시 함께 보내고, 적용 때 현재 값과 다르면(그 사이 reconcile이 바꿈) 해당 필드를 충돌로 알린다 — 현재 `/edit` 의 `pre` 비교와 같은 원리. 편집 락이 필요 없다 |
| **작업 이력** | 운영자 조작마다 `ops` 에 남기는 기록(무엇을 · 언제 · 바꾸기 전 항목). 되돌리기는 이력에서 골라 **항목 단위**로 한다 **(선택)** — 파일 통째 되돌리기(현재 `/undo`)는 자동 쓰기가 잦아 거의 항상 거부되고, 슬롯 하나라 자동 작업에 덮인다 |
| **로그인 링크** | 텔레그램 `/admin` 에 봇이 운영자 chat_id로 보내는 일회용 링크. 서명된 토큰 · 짧은 수명 · 한 번 쓰면 무효 |
| **리소스 이름 전환** | Cloud Run 서비스 이름을 실제로 `mewtype-intake` · `mewtype-writer` 로 바꾸는 일 (§10) |

## 4. 원칙

1. **data 브랜치를 쓰는 곳은 쓰기 서비스 하나.** (동시 1 · 인스턴스 1)
2. **접수 서비스는 적재하고 바로 돌아간다.** 동기 `/write` 대신 적용 큐 적재. 쓰기 서비스가 바쁘면 적용 큐가 재시도.
3. **예약 · 재확인은 전부 `reconcile(범위)` 요청으로.** 자기 호출 · 동기 호출 없음.
4. **느린 외부 호출(LLM · vxtwitter · videos.list · yt-dlp · OCR)은 접수 서비스에서.** 예외: reconcile의 YouTube 조회는 쓰기 서비스(판정 재료).
5. **운영 조작은 관리 페이지에서, 운영 상태는 `ops` 브랜치에.** 텔레그램은 알림과 비상 명령만. 대화 상태를 저장하지 않는다.

## 5. 관리 페이지

### 화면 (기능 사용 점검 결과 순서)

| 탭 | 하는 일 | 대응 기능 | 점검 결과 |
|---|---|---|---|
| **예고** | 5인 레인 목록 → 항목 폼(제목 · 상태 · 시각 · URL) 수정 · 삭제(재등록 차단 체크) · 번역 | 13 · 14d · 14g · 15 | 가장 많이 쓴 조작 |
| **원문 투입** | 예고 · 소식 · 트윗 원문 붙여 넣기 → **파싱 미리보기** → 확정 | 14a · 14b · 14c · 14f | 14a 드묾 · 나머지 미관측 — 자동 경로가 놓쳤을 때의 교정 수단 |
| **소식 · 트윗** | 목록 → 편집 · 삭제 · 번역 | 14e · 14h · 14i · 15 | 미관측 — 가볍게(버튼 수준) |
| **작업 이력** | 운영자 조작 목록 → 골라서 되돌리기 | 14j | 현재 `/undo` 문제(슬롯 하나 · 자동 작업에 덮임) 해결 |
| **유실 원문** | 유실 큐 목록 → 골라 재투입 | 18 | 드묾 |
| **운영** | pause · resume · 알림 레벨 · 자동 스냅샷 DM on/off | 16 · 17(`--auto/--off`) | 드묾 |
| **리포트** | 모니터 리포트 (웹 모니터와 같은 렌더러) | 17 · 23 | 드묾 |

**미리보기 → 확정**: 원문을 붙여 넣으면 접수 서비스가 파싱 · LLM 판정까지 해서 "이렇게 반영됩니다"를 먼저 보여주고, 확정을 눌러야 적재한다.
지금은 반영된 뒤에야 파싱 결과를 알 수 있다.

### 로그인 · 보안

1. 운영자가 텔레그램에 `/admin` → 접수 서비스가 chat_id 허용목록 확인(현재 `/telegram` 인증 그대로: Secret-Token 헤더 + chat_id).
2. 서명된 일회용 토큰(HMAC, 수 분 유효, nonce 포함)을 만들어 로그인 링크를 DM으로 보냄.
3. 링크를 열면 서명 · 만료 확인 + nonce를 `ops` 에 사용 처리(재사용 차단) → 세션 쿠키 발급(`HttpOnly` · `Secure` · `SameSite=Strict`, 수명 **(선택: 12시간)**).
4. 관리 API는 모든 요청에서 세션을 확인하고, 조작(POST)은 CSRF 토큰도 확인한다.

**주의**: 메모리의 09-17 v4 후보 안건에 따르면 현재 공개 서비스의 `ALLOW_UNAUTH=1` 이 `oidc.verify_request` 를 우회한다.
관리 API · `/enrich` 는 이 설정과 무관하게 **자체 인증을 강제**해야 한다 **(구현 시 코드 확인 필요)**.

### 서빙 위치 (선택)

접수 서비스가 `/admin` 으로 직접 서빙한다. 이유: 같은 출처라 CORS가 필요 없고 쿠키 세션이 단순하며, Vercel 배포(Hobby 하루 한도)와 무관하다.
대안: Vercel 정적 페이지 + 접수 서비스 API (CORS · 쿠키 도메인 설정 필요).

## 6. 브랜치별 쓰는 주체

| 브랜치 | 내용 | 쓰는 곳 | 읽는 곳 |
|---|---|---|---|
| `data` | preview · notices · tweets (+ archive) | **쓰기 서비스만** | 양쪽 · 프론트(raw CDN) |
| `ops` | control · suppress · 작업 이력 · 로그인 nonce | 접수 서비스(control · 로그인 nonce) + 쓰기 서비스(작업 이력 · suppress) | 양쪽 |
| `monitoring` | 이벤트 로그(작업 결과 포함) · 모니터링 스냅샷 · 유실 큐 | 양쪽 | 양쪽 · 관리 페이지(접수 서비스 경유) |

대기 슬롯 7종(`pending_ingest` · `pending_notice` · `pending_notice_edit` · `pending_op` · `pending_member` · `pending_del` · `pending_undo`)과
편집 락 · 60초 만료 로직은 **없어진다** — 웹 폼이 한 번에 제출하고, 동시 수정은 열람 값 비교로 확인한다.
`/pause` 는 적용 큐 상태와 무관하게 즉시 먹혀야 하므로 접수 서비스가 `ops` 에 직접 쓴다.

## 7. 트리거 통일

| 트리거 | 현재 | v4a |
|---|---|---|
| 10분 · 06:00 정기 | Scheduler → 백엔드 `/tick` | 정기 reconcile 잡 → `/reconcile` (같은 인스턴스라 적용 큐 작업과 한 줄로 선다. 429 → Scheduler 재시도, 현행 `--max-retry-attempts=3`) |
| 방송별 정밀 확인 | 백엔드 → Tasks → `/wake` | 쓰기 서비스 → 적용 큐 → `/apply reconcile(영상)` |
| 종료 후 재확인 · 영상 없는 예고 시각 | 백엔드 → Tasks → `/tick` | 적용 큐 → `/apply reconcile(전체)` |
| URL 확정 · 등록 즉시 확인 | `/write` 잡 안에서 Tasks 예약 | 작업 안에서 `reconcile(영상)` 적재 |
| YouTube 공개 알림 즉시 확인 (#12) | 제어 채널이 Tasks 예약 시도 → **env 없음, 불발** | 접수 서비스가 `reconcile(영상)` 적재 |
| 예고 상태 편집 후 재확인 (#14d) | 백엔드 → 자기 `/wake` 동기 호출 | 작업 안에서 `reconcile(영상)` 적재 |
| 재개 | 제어 채널 → `/tick` 동기 호출 | `ops` 에 control 쓰기 + `reconcile(전체)` 적재 |
| 번역 재시도 | tick 안 `_translate_sweep` | reconcile이 `needs_tl` 을 보면 가공 큐 → `/enrich` → 적용 큐 |

## 8. 기능 커버리지 — 26가지(세부 37행) + 신규 1

"변경" = v3.8.10 대비 경로가 바뀜. 사용자가 보는 동작(팬 화면)은 전부 유지된다. 운영자 조작은 텔레그램 명령에서 관리 페이지로 바뀐다.

| # | 기능 | v4a 경로 | v3.8.10 대비 |
|---|---|---|---|
| 1 | 예정 · 라이브 정기 감지 | 정기 reconcile 잡 → `/reconcile` → RSS + `videos.list` → preview 재구성 → data → CDN → 팬 | 유지 (이름만) |
| 2 | 방송별 정밀 추적 | 적용 큐 `reconcile(영상)` → `/apply` → `videos.list` → data → 다음 확인 재적재 | 변경 |
| 3 | 그룹 공식 채널 5인 팬아웃 | 1번 안 | 유지 |
| 4 | 종료 방송 보관 | 1 · 2번 안 | 유지 |
| 5 | 아바타 갱신 | `mewtype-reconcile-daily` → `/reconcile` → `channels.list` → data | 유지 (이름만) |
| 6 | 번역 재시도 | reconcile → 가공 큐 → `/enrich` → Groq → 적용 큐 → `/apply` → data | 변경 |
| 7 | 공식 스케줄 · 출연 공지 · 즉시 개시 릴레이 | `/ingest` → vxtwitter · 파싱 · Groq → 적용 큐(`merge_rows`) → `/apply` → data → 알림 DM | 변경 |
| 8 | 개인 트윗 배지 · 번역 | `/ingest` → vxtwitter · Groq → 적용 큐(`personal_tweet`) → `/apply` → data | 변경 |
| 9a | 개인 트윗 → 예고 (YouTube URL) | `/ingest` → `videos.list` (+ Groq) → 적용 큐(`url_confirmed_commit`) → `/apply` → data + `reconcile(영상)` 적재 | 변경 |
| 9b | 개인 트윗 → 소식 (비YouTube URL) | `/ingest` → Groq → 적용 큐(`apply_notice`) → `/apply` → data | 변경 (유지 결정) |
| 9c | 개인 트윗 → 예고 (URL 없음) | `/ingest` → 파싱 + Groq 최종 확인 → 적용 큐(`merge_rows`) → `/apply` → data | 변경 |
| 10 | 소식 게시판 (+ 크로스오버 비전 OCR) | `/ingest` → vxtwitter · 파싱 · Groq(+ OCR) → 적용 큐(`apply_notice`) → `/apply` → data | 변경 (OCR 유지 결정) |
| 11 | 회원 전용 라이브 시작 | `/ingest`(source=yt) → yt-dlp → 적용 큐(`yt_member_live_commit`) → `/apply` → data | 변경 (유지 결정) |
| 12 | 공개 방송 알림 즉시 확인 | `/ingest`(source=yt) → 적용 큐 `reconcile(영상)` → `/apply` → data | 변경 (**불발 해소**) |
| 13 | 조회 | 관리 페이지 → `GET /admin/api` → data · ops · monitoring 읽기 → 화면. 텔레그램 `/status` 는 비상용으로 유지 | 변경 (**웹**) |
| 14a | 예고 원문 수동 투입 | 관리 페이지 원문 투입 → 파싱 · Groq **미리보기** → 확정 → 적용 큐(`merge_rows`) → `/apply` → data + 작업 이력 → 작업 결과 | 변경 (**웹**) |
| 14b | 소식 원문 수동 투입 | 원문 투입 → Groq 미리보기 → 확정 → 적용 큐(`apply_notice`) → `/apply` → data + 이력 → 결과 | 변경 (**웹**) |
| 14c | 트윗 원문 수동 투입 | 원문 투입(유닛 선택) → Groq 미리보기 → 확정 → 적용 큐(`personal_tweet`) → `/apply` → data + 이력 → 결과 | 변경 (**웹**) |
| 14d | 예고 편집 | 예고 탭 폼(여러 필드 한 번에 + 열람 값) → 적용 큐(`apply_preview_edit`) → `/apply` → 충돌 확인 → data + 이력 → (state 변경 + 영상) `reconcile(영상)` 적재 → 결과 | 변경 (**웹 · 자기 호출 제거 · 편집 락 제거**) |
| 14e | 소식 편집 | 소식 탭 폼 → 적용 큐(`notice_edit_commit`) → `/apply` → data + 이력 → 결과 | 변경 (**웹**) |
| 14f | 트윗 교체 | 원문 투입(교체) → 14c와 같은 경로 | 변경 (**웹**) |
| 14g | 예고 삭제 | 예고 탭 삭제(확인 대화상자 · 재등록 차단 체크) → 적용 큐(`remove_broadcast`) → `/apply` → data + 이력 (+ suppress) → 결과 | 변경 (**웹 · 확인 대기 슬롯 제거**) |
| 14h | 소식 삭제 | 소식 탭 삭제 → 적용 큐(`notice_del_commit`) → `/apply` → data + 이력 → 결과 | 변경 (**웹**) |
| 14i | 트윗 삭제 | 트윗 탭 삭제 → 적용 큐(`tweet_del_commit`) → `/apply` → data + 이력 → 결과 | 변경 (**웹**) |
| 14j | 되돌리기 | 작업 이력 탭 → 골라 되돌리기 → 적용 큐(항목 단위 되돌리기) → `/apply` → data + 이력 → 결과 | 변경 (**웹 · 슬롯 하나 → 이력**) |
| 15 | 수동 번역 | 관리 페이지 번역 버튼 → Groq → 적용 큐 → `/apply` → data → 결과 | 변경 (**웹 · 직접 쓰기 제거**) |
| 16 | 일시정지 · 재개 · 알림 레벨 | 관리 페이지 운영 탭 **또는** 텔레그램 비상 명령 → `ops` control(sha 검사) → (재개) `reconcile(전체)` 적재 | 변경 (**웹 + 비상 명령**) |
| 17 | 모니터 리포트 | 관리 페이지 리포트 탭 → monitoring 읽기 + healthchecks · Vercel → 화면 (자동 DM on/off는 운영 탭) | 변경 (**웹**) |
| 18 | 유실 원문 재투입 | 관리 페이지 유실 원문 탭 → 골라 가공 재실행 → 적용 큐 → **적재 성공분** 유실 큐에서 제거 → `/apply` → data | 변경 (**웹**) |
| 19 | 상태 전이 알림 DM | `/reconcile` · `/apply reconcile` → data → 레벨 게이팅 DM (텔레그램 유지) | 유지 |
| 20 | 유실 원문 보존 | ① 접수 서비스 적재 실패 → DM + 유실 큐 ② 작업이 마지막 시도까지 실패 → 쓰기 서비스가 DM + 유실 큐 | 변경 (4곳 → 2곳) |
| 21 | 모니터 이벤트 로그 | 양쪽 → monitoring (작업 결과 포함) | 유지 |
| 22 | 일일 스냅샷 + 멤버 현황 DM | 스냅샷 잡 06:10 → `/snapshot` → monitoring → DM (텔레그램 유지) | 유지 (이름만) |
| 23 | 웹 모니터 | 브라우저 → 접수 서비스 `/monitor-live` → monitoring 읽기 (폴백 raw) | 유지 |
| 24 | 생존 신호 | `/reconcile` → healthchecks 핑 | 유지 |
| 25 | 팬 화면 | 브라우저 → raw CDN → data | 유지 |
| 26 | 배포 | `main` push → Vercel | 유지 |
| 27 | **관리 페이지 로그인** (신규) | 텔레그램 `/admin` → 일회용 링크 DM → 링크 열기 → nonce 사용 처리(`ops`) → 세션 쿠키 | 신규 |

아워노츠 계정 알림(업스트림의 약 24%)은 현재처럼 `/ingest` 로 받고 반영하지 않는다 — 처리 규칙은 만들지 않기로 결정.

## 9. 현재 배선(`v3b_wiring_map.md`) → v4a

| 현재 배선 | v4a | 비고 |
|---|---|---|
| E1 · E2 `/ingest` (X · YouTube) | 유지 | 경로 유지. 내부 핸들러만 분리 |
| E3 운영자 명령 | **변경** | 관리 페이지(`/admin` · `/admin/api`) + 텔레그램 비상 명령 4개 |
| E4 · E5 정기 tick | 변경 | 정기 reconcile 잡 → `/reconcile`. 번역 대신 가공 큐 적재 |
| E6 모니터 스냅샷 | 변경 | 스냅샷 잡 → `/snapshot` |
| I1 `/wake` 예약 | 변경 | 적용 큐 `reconcile(영상)` |
| I2 `/tick` 예약 (자기 재호출) | 흡수 | 적용 큐 `reconcile(전체)` |
| I3 `/write` 동기 쓰기 큐 | 변경 | 적용 큐 적재 (비동기) |
| I4 등록 즉시 wake | 흡수 | 작업 안에서 `reconcile(영상)` 적재 |
| I5 `/resume` → `/tick` | 변경 | `reconcile(전체)` 적재 |
| I6 백엔드 자기 호출 | **삭제** | |
| T `/tick` 한 바퀴 | 변경 | 번역 sweep 제거 |
| S1 preview (쓰는 갈래 둘) | 변경 | 쓰기 서비스 인스턴스 하나 |
| S2 · S3 `/translate` 우회 | 변경 | 적용 큐 경유 |
| S4 admin_state (제어 채널 직접) | **대부분 삭제** | 대화 슬롯 · 편집 락 없음. suppress · 작업 이력만 `ops` 로 |
| S5 control (충돌 검사 없음) | 변경 | `ops` 브랜치 + sha 검사 |
| S6 `ingest_queue.json` | **삭제** | |
| S7 이벤트 로그 · lost_queue | 유지 | 작업 결과 기록 추가, 유실 적재 지점 변경 |
| S8 `latest.html` (쓰는 쪽 둘) | 유지 | 정리는 선택 |
| X4 Groq (양쪽) | 변경 | 접수 서비스만 |
| X7 운영 DM | 변경 | 알림 DM(쓰기 서비스) + 비상 명령 응답 · 로그인 링크(접수 서비스). 조작 결과는 관리 페이지로 |
| X1 · X2 · X3 · X5 · X6 · X8 · X9 | 유지 | |
| F1~F6 | 유지 | F5 는 접수 서비스 URL을 가리킴 |
| (신규) 관리 페이지 ↔ 접수 서비스 | 추가 | 세션 쿠키 + CSRF |
| (신규) 가공 큐 → `/enrich` | 추가 | 앱 안 OIDC 검증 |
| (신규) `ops` 브랜치 | 추가 | |

## 10. 대가 · 확인 필요

| 항목 | 내용 |
|---|---|
| 공개 관리 화면 | data를 고칠 수 있는 화면이 인터넷에 생긴다. 로그인 링크 · 세션 · CSRF를 제대로 구현해야 하고, `ALLOW_UNAUTH=1` 우회 문제(§5)를 먼저 해결해야 한다 **(구현 시 코드 확인 필요)** |
| 결과가 비동기 | 조작 결과는 적재 뒤 작업 결과 기록을 페이지가 조회해 보여준다(수 초~). 조회 응답 · 미리보기는 즉시 |
| 묶음 커밋 없음 | 1건 = 1커밋. v3.8.2 측정(약 3.3초/커밋) 대입 시 60건 버스트는 약 3분 + reconcile 실행분. raw CDN 캐시가 원래 최대 약 5분 — **추정, 재측정 필요** |
| 순서 · 중복 | Cloud Tasks는 전달 순서를 보장하지 않고 드물게 중복 전달 **(확인 필요)** → 작업은 독립 · 멱등. 작업 id를 태스크 이름으로 써서 중복 적재 방지 |
| 데드레터 없음 | Cloud Tasks에는 DLQ가 없다 **(확인 필요)** → 최대 시도 횟수 + `X-CloudTasks-TaskRetryCount` 로 마지막 시도 판별 **(확인 필요)** → 유실 큐 |
| 작업 크기 | 원문 + 가공 결과를 작업 본문에. Cloud Tasks 작업 크기 상한 안인지 **확인 필요** |
| 번역이 커밋 두 번 | reconcile이 발견한 방송 제목은 원문으로 먼저, 번역은 가공 큐를 거쳐 나중에 |
| 항목 단위 되돌리기 | 파일 통째가 아니라 항목 단위라 되돌리기 작업 종류를 새로 만들어야 한다. 되돌리는 사이 그 항목이 또 바뀌었으면 충돌로 알림 |
| `ops` 이관 | control · suppress 를 읽는 곳(reconcile 포함)을 새 브랜치로. 현재 `admin_state` 의 잔존 슬롯은 버린다 |
| **리소스 이름 전환** | Cloud Run 서비스는 이름을 바꿀 수 없어 새로 배포 → **URL이 바뀐다**. 폰 Automate URL(경로 `/ingest` 는 그대로) · Telegram webhook · `monitor.html` 주소 · OIDC audience · IAM 갱신. 큐 · Scheduler 잡은 어차피 새로 만들어 추가 비용 작음 |

## 11. 채택 조건 — 측정

60건 버스트를 v3.8.2 방식 그대로 현재 / v4a에 흘려 지연 중앙값 · 유실을 비교한다. 유실이 늘거나 팬 화면 기준 지연이 눈에 띄게 늘면 채택하지 않거나
§13의 묶음 커밋을 얹는다.

## 12. 진행 순서 (단계마다 배포 가능)

1. **잔재 제거** — `ingest_queue` drain, `push_monitor.py`, `INGEST_YT_ENABLED` · `INGEST_ECHO` · `INGEST_DRY_RUN` · 테스트 부계정 헬스체크(미관측), `control.json` `push_monitor_auto` 키,
   v1 수집기 미사용 파일 · `collect.yml` (`v4a_feature_audit.md` §2). 드문 기능(9b · OCR · 11 · 날짜만 예고)은 **유지**.
2. **`ops` 브랜치 신설** — control · suppress 이관 + 읽기 경로 변경 + control sha 검사.
3. **`mewtype-apply` 큐 · `/apply` 신설 + 적재 전환** — `writers.py` 잡 종류 재사용, 작업 결과를 이벤트 로그에. 한동안 `/write` 와 병행 후 제거.
4. **지름길 → `reconcile` 적재 통일** — I1 · I2 · I4 · I5 · I6, #12, #14d. `/wake` 제거.
5. **번역 이동** — `mewtype-enrich` 큐 + `/enrich`, `_translate_sweep` 제거.
6. **관리 페이지** — 로그인 링크 · 세션 · CSRF 먼저, 그다음 화면을 점검 결과 순서(예고 → 원문 투입 → 작업 이력 → 유실 원문 → 운영 · 리포트 → 소식 · 트윗)로.
7. **텔레그램 명령 축소** — 비상 명령 4개만 남기고 마법사 · 대화 슬롯 · 명령 별칭 제거. 현재 `admin_state.json` 폐기.
8. **유실 처리 재배선** — 적재 실패 · 마지막 시도 2지점, 재투입 제거 기준 변경.
9. **이름 전환** — Scheduler 잡 3개 교체(`/tick` → `/reconcile`, `/monitor` → `/snapshot`), Cloud Run 리소스 이름 전환(폰 URL 변경 동반 — 시점은 운영자 판단).
10. **60건 버스트 측정** (§11).

## 13. v3b 목표안과 비교

| | v3b 목표안 (관제탑 + 우편함) | v4a |
|---|---|---|
| Cloud Run 서비스 | 3개 (게이트 · 감시자 · 관제탑) | 2개 (접수 서비스 · 쓰기 서비스) |
| 우편함 | Pub/Sub (신규 제품) | Cloud Tasks 적용 큐 (현재 큐의 역할 확장) + 가공 큐 |
| 쓰기 방식 | Git Data API 전환 (여러 파일 1커밋) | Contents API 그대로 |
| 묶음 커밋 | 있음 | 없음 (필요하면 `/apply` 에 얹음 — 설계 미정) |
| 데드레터 | Pub/Sub 기본 제공 | 마지막 시도 판별로 직접 구현 |
| 운영 조작 | 텔레그램 명령 체계 재정리 (미정) | 웹 관리 페이지 + 텔레그램 비상 명령 |
| 운영 상태 | data 브랜치 (관제탑이 씀) | `ops` 브랜치 — 대화 슬롯 없이 control · suppress · 작업 이력만 |
| 업스트림 폰 변경 | `/x` · `/yt` 분리 (경로 변경) | 경로 유지. URL은 리소스 이름 전환 때만 변경 |

## 14. 더 근본적인 대안 (참고)

가변 상태를 트랜잭션이 되는 저장소(예: Firestore)로 옮기고 Git은 공개 JSON 출력만 맡기면, 동시 쓰기 문제 자체가 사라진다.
대신 저장소가 하나 늘고 Git 이력 기반 감사 방식을 다시 설계해야 한다. v4a 범위 밖.
