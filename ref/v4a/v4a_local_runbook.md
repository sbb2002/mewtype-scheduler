# v4a 로컬 시험판 — 사용 방법

- 대상: 브랜치 `v4a` (배포 · 머지하지 않음). 운영(v3.8.10, Cloud Run)은 그대로 둔 채, **별도 테스트 기기**에서 며칠 나란히 돌려 본다.
- 구성 · 검증: `v4a_impl_plan.md`(계획) · `v4a_verify_report.md`(검증 결과) · `v4a_verify_flow.html`(관측 흐름 애니메이션)

```
폰(Automate) ──Tailscale──▶ 테스트 기기 :8787 /ingest ─┐
운영자 브라우저 ─Tailscale─▶ 테스트 기기 :8787 / · /admin │  로컬 러너 (한 프로세스)
로컬 전용 텔레그램 봇 ◀── getUpdates 폴링 ────────────────┘  저장: <저장소>/_local/
테스트 기기 ──▶ YouTube API · Groq · vxtwitter (나가는 연결만. 인바운드 방화벽 해제 불필요)
```

## 1. 테스트 기기 준비 (한 번만)

| # | 할 일 |
|---|---|
| 1 | **Tailscale** 설치 → 폰과 **같은 계정**으로 로그인. 확인: `tailscale ip -4` 가 `100.x.x.x` 를 출력, `tailscale status` 에 폰(`s23`)이 보임 |
| 2 | **Python 3.10 이상**(검증은 3.13) + git |
| 3 | 코드 받기: `git clone https://github.com/sbb2002/mewtype-scheduler.git` → `cd mewtype-scheduler` → `git checkout v4a` |
| 4 | 가상환경 + 의존성: `python -m venv .venv` → 활성화(Windows `.venv\Scripts\activate`, 그 외 `source .venv/bin/activate`) → `pip install -r src/backend/requirements.txt` |
| 5 | **로컬 전용 텔레그램 봇**을 BotFather 로 새로 만든다. 운영 봇 토큰 금지 — 러너는 webhook 이 걸린 봇이면 폴링을 거부한다(운영 webhook 보호) |
| 6 | `ref/v4a/local_env.example` 을 저장소 루트 `.env.local` 로 복사해 값 채우기. `INGEST_SECRET` · `ADMIN_SECRET` 은 운영과 다른 새 값. `LOCAL_BIND` 는 비워 두면 그 기기의 Tailscale IP 를 자동으로 쓴다 |
| 7 | 점검: `python -m src.backend.local_runner --check` — 필수 값 누락 · 감지한 Tailscale IP · 접속 주소를 알려 준다 |
| 8 | **절전 끄기** — 24시간 켜 둔다. 절전 중 온 알림은 로컬 쪽에서만 빠진다 |

## 2. 폰 Automate (한 번만)

기존 `HTTP request` 블록(운영 전송) **뒤에** 블록 하나를 추가한다.

| 항목 | 값 |
|---|---|
| URL | `http://<테스트 기기 Tailscale IP>:8787/ingest` (1-7 점검 출력의 접속 주소) |
| Headers | `{"X-Ingest-Secret": "<.env.local 의 INGEST_SECRET>"}` |
| Request content | 기존 블록과 같은 `body` |
| 실패 처리 | 테스트 기기가 꺼져 있어도 플로우가 멈추지 않게 실패 경로를 다음 블록으로 연결 (Automate 에서 해당 설정 이름 확인 필요) |

운영 전송이 먼저, 로컬 전송이 나중 — 순서를 바꾸지 않는다.

## 3. 실행

```bash
# 저장소 루트에서 (가상환경 활성화 후)
python -m src.backend.local_runner          # 켜 두기. 종료는 Ctrl+C
```

처음 켜면 곧바로 reconcile(전체 · baseline) 한 번, 이후 10분마다 · 매일 06:00 JST · 06:10 KST(스냅샷).
data 는 빈 상태에서 시작한다(콜드 스타트) — 예고는 RSS · API 와 새로 들어오는 알림으로 채워진다.
대기 작업은 `_local/queue/` 에 저장돼 재시작해도 이어진다.

## 4. 쓰는 법

| 하고 싶은 것 | 방법 |
|---|---|
| 팬 화면 보기 | 폰 · PC 브라우저 `http://<테스트 기기 IP>:8787/` |
| 관리 페이지 | 로컬 봇에 `/admin` → DM 으로 온 링크(5분 · 1회용) 열기 → 예고 · 원문 투입 · 소식/트윗 · 작업 · 유실 원문 · 운영 · 리포트 탭 |
| 급할 때 | 로컬 봇에 `/status` · `/pause` · `/resume` · `/list [notice\|tweet]` |
| 웹 모니터 | `http://<테스트 기기 IP>:8787/monitor.html` |
| 러너 상태 | 테스트 기기에서 `http://127.0.0.1:8787/healthz-local` (대기 작업 수) |
| 데이터 들여다보기 | `_local/data`(공개 콘텐츠) · `_local/ops`(운영 상태 · 작업 이력) · `_local/monitoring`(이벤트 로그 · 유실 큐) · `_local/raw`(원문 보존) |
| 다시 검증 | `python ref/v4a/verify/harness.py` (가짜 외부 서비스로 78개 확인) → `python ref/v4a/verify/gen_verify.py` (애니메이션 갱신) |
| 새 코드 받기 | `git pull` 후 러너 재시작 |

## 5. 주의

- **YouTube 쿼터 공유**: 운영과 같은 API 키면 하루 10,000 을 함께 쓴다. 로컬 10분 reconcile ≈ 300/일, URL 없는 예고마다 `search.list` 100.
- **텔레그램 DM 두 벌**: 운영 봇과 로컬 봇이 각자 알림을 보낸다. 로컬 봇 대화가 v4a.
- **방화벽**: 처음 실행할 때 OS 가 Python 의 네트워크 허용을 물으면 **개인 네트워크만** 허용. 폰에서 안 열리면 Tailscale 인터페이스 쪽 인바운드가 막힌 것.
- 관리 페이지 예고 **삭제**는 확인창 세 번(대상 확인 → 재등록 차단 여부 → 최종 확인, 어느 단계든 취소하면 안 지운다). 항목 단위 **되돌리기는 아직 없다**(작업 이력은 조회만).
- 관리 페이지 **작업** 탭: 지금 상태(러너 · 텔레그램 봇 · 마지막 X/YouTube 알림 · 적용 큐 · 방송 · 데이터 갱신) +
  최근 흐름(알림 · 관리 조작 · 방송 확인 1건씩, 누르면 단계별 경로 재생). 흐름 기록은 `_local/ops/flows.json`(최근 200건, 로컬 전용).
- **관찰 포인트**(`v4a_decisions.md`): D1 알림으로 live · D2 20분 전 watching · D3 30분 전 알림으로 URL 없는 예고 합치기 · D4 +2분 검색 · +1시간 out ·
  D6 end → live 복구 · D16 리트윗 소식 제외 · D18 트윗 48h.
