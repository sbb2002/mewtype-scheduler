# v4a 로컬 시험판 운영 안내

- 대상: 브랜치 `v4a` (배포 · 머지하지 않음). 운영(v3.8.10, Cloud Run)은 그대로 둔 채 로컬 PC 에서 며칠 나란히 돌려 본다.
- 구성 · 검증: `v4a_impl_plan.md`(계획) · `v4a_verify_report.md`(검증 결과) · `v4a_verify_flow.html`(관측 흐름 애니메이션)

## 1. 한 번만 준비

| # | 할 일 | 누가 |
|---|---|---|
| 1 | 코드: `git worktree add ../mewtype-scheduler-v4a v4a` (이미 있으면 생략) → 그 폴더에서 `pip install -r src/backend/requirements.txt` | 운영자 |
| 2 | **로컬 전용 텔레그램 봇**을 BotFather 로 새로 만든다. 운영 봇 토큰을 쓰면 안 된다 — 러너는 webhook 이 걸린 봇이면 폴링을 거부한다(운영 webhook 을 지우지 않기 위한 안전장치) | 운영자 |
| 3 | `ref/v4a/local_env.example` 을 저장소 루트의 `.env.local` 로 복사해 값 채우기. `INGEST_SECRET` · `ADMIN_SECRET` 은 운영과 다른 새 값 | 운영자 |
| 4 | 설정 점검: `python -m src.backend.local_runner --check` → 누락이 있으면 알려 준다 | 운영자 |
| 5 | 폰 Automate: 기존 `HTTP request` 블록(운영) **뒤에** 블록 하나 추가 — URL `http://100.79.146.124:8787/ingest`, 헤더 `{"X-Ingest-Secret": "<로컬 INGEST_SECRET>"}`, 본문은 기존과 같은 `body`. 로컬이 꺼져 있어도 플로우가 멈추지 않게 실패 경로를 다음 블록으로 연결(블록 이름은 Automate 에서 확인 필요) | 운영자 |
| 6 | 폰 Tailscale 켜 두기 (Exit Node = None) | 운영자 |

## 2. 실행 · 확인

```bash
# 저장소 루트(../mewtype-scheduler-v4a)에서
python -m src.backend.local_runner          # 켜 두기. 종료는 Ctrl+C
```

| 확인 | 방법 |
|---|---|
| 팬 화면 | 폰 · PC 브라우저 `http://100.79.146.124:8787/` |
| 관리 페이지 | 로컬 봇에 `/admin` → 받은 링크(5분 · 1회용)를 연다 |
| 비상 명령 | 로컬 봇에 `/status` · `/pause` · `/resume` · `/list` |
| 러너 상태 | `http://127.0.0.1:8787/healthz-local` (대기 작업 수) |
| 웹 모니터 | `http://100.79.146.124:8787/monitor.html` |
| 데이터 · 로그 | `_local/data` (공개 콘텐츠) · `_local/ops` (운영 상태 · 작업 이력) · `_local/monitoring` (이벤트 로그 · 유실 큐) · `_local/raw` (원문 보존) · `_local/queue` (대기 작업 — 재시작해도 이어짐) |

처음 켜면 곧바로 reconcile(전체 · baseline) 이 한 번 돌고, 이후 10분마다 · 매일 06:00 JST · 06:10 KST(스냅샷)에 돈다.
data 는 비어 있는 상태에서 시작한다(콜드 스타트) — 예고는 RSS · API 와 새로 들어오는 알림으로 채워진다.

## 3. 주의

- **YouTube 쿼터 공유**: 운영과 같은 API 키면 하루 10,000 을 함께 쓴다. 로컬 10분 reconcile ≈ 300/일, URL 없는 예고마다 `search.list` 100.
- **텔레그램 DM 이 두 벌**: 운영 봇과 로컬 봇이 각자 알림을 보낸다. 로컬 봇 대화에서 오는 것이 v4a.
- **PC 절전**: 절전 중 들어온 알림은 로컬 쪽에서만 유실된다(운영은 정상). 같은 시간대 운영 기록과 비교하면 알 수 있다.
- **비교 관찰 포인트**: D1(알림으로 live) · D2(20분 전 watching) · D3(30분 전 알림 → URL 없는 예고 합치기) · D4(+2분 검색 · +1시간 out) ·
  D6(end → live 복구) · D16(리트윗 소식 제외) · D18(트윗 48h) — `v4a_decisions.md`.
- 관리 페이지 **삭제** 버튼은 브라우저 확인창 두 번(삭제 → 재등록 차단 여부)을 띄운다.
- 항목 단위 **되돌리기(undo)는 아직 없다** — 관리 페이지 작업 이력은 조회만.
