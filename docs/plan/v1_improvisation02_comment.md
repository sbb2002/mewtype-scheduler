# v1_improvisation02 검토 코멘트 (2026-08-31)

`v1_improvisation02.md`의 두 의문 + 역할 분담안에 대한 답변.

## 역할 분담 정리

제안한 구도는 성립함:

| 구성요소 | 역할 |
|---|---|
| **Google Cloud Scheduler** | 백엔드 핑 & 트리거. 고정 주기 heartbeat + (선택) 방송별 정밀 wake. |
| **GitHub Actions** | 백엔드 로직. 트리거되면: 방송인 상태 수집 → 프론트(`data` 브랜치) 업데이트 → 5인 live 상태로 자신의 다음 실행 타이밍 결정 → GCS(또는 Cloud Tasks) 갱신 → 종료. |
| **Vercel** | 유저가 보는 정적 프론트엔드 (`data/schedule.json` fetch). 현행 그대로. |

**단, 주의**: Actions를 compute로 쓰면 러너 준비 ~2~3분 오버헤드가 매 wake마다 붙음.
굵은 주기(RSS 폴링, upcoming 확인)엔 문제 없지만, "임박 구간 3분마다 폴링" 같은 촘촘한 단계엔 낭비가 큼.
그 단계까지 촘촘히 가려면 compute를 Cloud Run/Functions로 옮기는 게 맞음(§아래 Q1-c, 이전 comment의 A-3).
v1.x 목표가 5~10분급 지연이면 Actions compute로 충분.

---

## Q1. 실행 중에 GCS 트리거 타이밍을 바꿀 수 있나 — 가능, 단 제약

Cloud Scheduler REST API로 백엔드가 서비스 계정 권한으로 자기 잡을 수정 가능:
- `jobs.patch` → `schedule`(cron)·`timeZone` 변경
- `jobs.run`(즉시 실행) / `jobs.pause` / `jobs.resume`

**제약**: GCS는 **반복 cron 전용, 일회성 트리거 개념 없음.** "특정 일시에 한 번만"을 cron으로 표현 불가(연도 불가).
매 실행마다 cron 재작성은 지저분함(연 1회 재발화 → pause로 막아야 함).

### 대안

- **(a) 가장 단순 — GCS 타이밍 고정.** 고정 주기(예: 5분)로 두고 백엔드가 매 호출마다 `pending` 상태 읽어 할 일 없으면 즉시 종료(적응형 폴링). 그림의 "백엔드 on/off"는 Cloud Run scale-to-zero로 공짜로 얻음 → 별도 관리 불필요.
- **(b) 정밀 wake 필요 시 — Cloud Tasks.** 태스크에 `scheduleTime`(최대 30일 후) 지정 → HTTP 엔드포인트 1회 호출. 구조: GCS = 굵은 heartbeat(예: 1h RSS), Cloud Tasks = 방송별 정밀 wake(T-60분, 임박 단계는 3분마다 자기 재큐).
- **(c) 촘촘한 폴링까지 — compute를 Cloud Run/Functions로.** 콜드스타트 1~2초, 러너 오버헤드 제거, 지연 <30초. Actions 대비 이주 폭 큼(컨테이너화, `data` 커밋 git 인증을 잡 안에서).

---

## Q2. 최초 1회 수동 디스패치 후 완전 자동 루프 — 가능, 조건부

메커니즘상 성립:
부트스트랩 1회 → 매 실행: RSS+reconcile → 상태 갱신 → 다음 wake 계산 → GCS patch(또는 Cloud Task 큐잉) → 종료(scale-to-zero = 꺼짐).

### 반드시 지킬 것 (안 지키면 한 번 깨지면 영영 안 깨어남)

1. **저빈도 안전망 트리거 항상 유지.** self-scheduling 루프의 치명적 약점: 다음 wake를 설정할 그 실행이 죽으면(API 오류·쿼터·버그) 체인이 끊기고 아무도 안 깨움. GCS 고정 잡(예: 1~3h마다)을 별도로 두면 끊긴 링크가 몇 시간 안에 자가 복구. **자기가 설정한 트리거에만 의존 금지.**
2. **상태는 외부에 durable하게.** 인스턴스는 휘발성 — `pending` wake 시각, 방송별 폴링 단계는 `data` 브랜치/GCS 버킷/Firestore에. (이전 comment §2와 동일)
3. **로직 멱등성.** GCS·Cloud Tasks 둘 다 at-least-once(중복 발화 가능). reconcile은 이미 멱등(현재 YouTube 상태로부터 순수 재계산) — 이 성질 유지.
4. **인증.** Cloud Run/GCF에 서비스 계정 붙이면 키 파일 없이 `roles/cloudscheduler.admin` 또는 `roles/cloudtasks.enqueuer` 획득. Actions를 compute로 쓰면 SA 키를 시크릿에 넣거나 Workload Identity Federation(키리스, 세팅 소량).

---

## 추천 (단순한 순)

1. **GCS 고정 주기 + 백엔드 조기 종료.** self-reschedule 없음. on/off는 Cloud Run이 알아서. 가장 견고.
2. **GCS 굵은 heartbeat + Cloud Tasks 방송별 일회성 wake.** 낭비 호출 최소화가 필요하면.
3. **피할 것**: GCS cron 문자열 런타임 재작성. 되긴 하나 일회성 표현 불가 + 실행 1회 실패로 루프 사망.

---

## 그림(lifespan_overall_clean.png) 관련 관찰

"warm-up/cooldown ±1h"는 보수적임. Cloud Run 콜드스타트 1~2초라 작은 수집기엔 ±1h 예열이 거의 불필요 —
T-15분, 심지어 T-3분에 깨워도 됨. buffer를 줄이면 "ontime" 유지 비용도 같이 줄어듦. (`plot_lifespan_overall.py`의 `BUFFER` 상수)
