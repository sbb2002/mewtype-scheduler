# v3 초안 — v3.0 배포 완료 (2026-09-09)

이 문서는 v3 "백엔드 수술"의 **결정 로그**다. 기능 상세는 `v3_backend_surgery.md`,
전환·롤백 절차는 `v3_golive.md`.

## 상태: v3.0 배포됨 (2026-09-09) — `main` 이 현행

전환 절차·검증·롤백은 `docs/plan/v3_golive.md` 에 기록. 아래는 착수 판단 근거(이력).

> **착수 트리거**: YouTube 회원전용 방송이 폰 푸시알림으로 도달하는 것이 확인되고,
> 그 알림 텍스트로 회원전용 방송을 실사용 가능한 수준으로 표시할 수 있다고 판단될 때.

**충족 근거 (2026-09-09~10)**:
1. 회원전용 알림 폰 도달 확인 — `ref/flow-7 (5).log` 라인 35(`SPONSORSHIPS_LIVESTREAM_TUNEIN`,
   예정−30분)·41(`..._START`). 후지 미야코 `💜メン限 雑談💜みやこの部屋#11`.
2. `android.text` 에 채널명(`藤都子 -Fuji Miyako-`) + 제목 다 실림 → "회원전용 방송 중" 카드 구성 가능
   (트리거가 요구한 최저선).
3. 초과 달성: 트윗 경로로 video_id 확보 시 썸네일·상태추적까지 정규 처리 가능.
   - `videos.list` 는 회원전용도 **정상 응답**(실측 `0_e9LxlMYHU`: `items:1`,
     thumbnails·`liveStreamingDetails` 다 옴). "videos.list 404" 는 오판이었음.
   - vxtwitter unfurl 로 잘린 URL 복원 확인(실측 트윗 `2096795604856836521` →
     `iWWGpoZfH5g` → `i.ytimg.com` 썸네일 200). `vxtwitter.py` 는 브랜치에 있음.

### 착수 후 병행 검증 (블로커 아님)
- 회원전용 알림 샘플 1건뿐 — 다른 멤버·다음 회차 1~2건 더 (payload 형태 동일성).
- **upcoming(예고) 상태** 회원전용에서 `videos.list` 응답 — 오늘 테스트는 종료된 스트림.
- 업스트림 2소스 플로우는 폰에 구성 완료(`AUTOMATE_MANUAL §4b`), 실트래픽 관측 축적 중.

---

## 확정된 결정

### 1. 입력 소스 = 업스트림 시스템(폰 Automate 플로우) 유지

용어: **업스트림 시스템** = 운영자 폰의 Automate 플로우. 푸시알림을 `POST /ingest` 로
중계하는, 백엔드 앞단의 1st-party 노드(코드베이스 밖이라 런타임 관측·버전관리 불가).

트윗 수집 방식으로 폴링 / 웹훅 / 업스트림 시스템을 비교한 결과 업스트림 유지:

| | 업스트림 시스템 | X API 폴링 | X 웹훅 (Account Activity v2) |
|---|---|---|---|
| 비용 | **$0** | 월 $20~40 | 월 $30~50 (표본 부족, 오차 큼) |
| 정시성 | 즉시 | 폴링 주기만큼 지연 | 즉시 |
| 미디어(이미지/영상) | ✗ | ✓ | ✓ |
| 트윗 id·시각 정확도 | 파싱 의존 | ✓ | ✓ |
| 커버리지 | 폰에 푸시 뜬 것만 | 전체 | 전체 |
| 회원전용 영상 | ✗ | ✗ | ✗ |
| 폭주 비용 리스크 | 없음 | 있음 (크레딧 순삭) | 있음 |

- **폴링**: 정시성 손해가 큼.
- **웹훅**: Account Activity API v2 도 이벤트 전달마다 과금. RT·리플·좋아요 등
  필터로 버릴 이벤트까지 다 받고 돈을 냄 (계정 단위 all-or-nothing, 서버측 필터 없음).
- X API 는 2026-02 부터 pay-per-use (post read $0.005 / post create $0.015, 링크 포함 $0.20,
  월 200만 read 상한). 구 Basic $200/월·Pro $5,000/월 티어는 폐지·강제 이관됨.
- 전환 명분은 **미디어 + 정확도** 뿐인데, 그게 v3 필수 요구가 아니면 업스트림 유지가 우세.
  미디어가 꼭 필요한 개별 항목만 트윗 URL 로 보강 (무료 CDN).

### 2. 데이터 브랜치 재구성은 입력 소스 결정과 분리

- 데이터 스키마는 **상태 모델**(announced/watching/live/end…)의 산출물이지,
  트윗이 어떻게 들어오냐의 산출물이 아님.
- `/ingest` 엔드포인트가 transport 추상화 경계 — 업스트림이든 API 든 같은 텍스트가 들어와
  같은 파서·저장 계층을 탐. 입력 소스를 나중에 갈아끼워도 스키마 불변.
- 따라서 v3 착수 시 데이터 처리를 먼저 해도 안전. **콜드 스타트** — 기존 데이터는 `.old/` 로
  치우고 v3 스키마 파일을 빈 상태에서 새로 쓴다(기존 행 일괄 치환/마이그레이션 스크립트 없음).
  안정화 확인 후 쓸만한 old 데이터 백필은 별건. 상세: `v3_backend_surgery.md` "데이터 전환".

### 3. 회원전용 영상 (2026-09-10 정정 — "열화" 는 video_id 없을 때만)

실측 후 판정 수정: **회원전용도 video_id 만 있으면 정규 처리된다.**
`videos.list` 는 회원전용 메타데이터를 정상 반환하고(멤버십 게이트는 재생만 막음),
썸네일은 `i.ytimg.com/vi/<id>/…` 문자열 조립이라 API 조차 불필요.

| video_id 확보 경로 | 처리 |
|---|---|
| 트윗의 watch URL (X 릴레이 + vxtwitter 로 잘린 URL 복원) | **정규** — 썸네일·`liveStreamingDetails`·live/end 추적 전부 v2 와 동일. `membership:true` 는 프론트 배지용 플래그일 뿐 |
| YouTube 앱 푸시만 (`chime.slot_key == "default"`) | **열화** — video_id 없음. 텍스트 카드 + 자물쇠 아이콘 + assumed-live 시간 폴백 |

- 열화 경로 = `source:"yt-memberonly"`, `video_id` 없음, `thumbnail` 없음, `watching` 스킵,
  알림(`SPONSORSHIPS_LIVESTREAM_START`) 오면 바로 `live`. 종료 판정 불가 → 예정+N시간 폴백 → `none`.
- 프론트 `.card--membership` — 자물쇠 아이콘, "회원전용 방송 중" (열화 경로에만; 트윗 경로는 일반 카드 + 배지).
- 상세·전이표: `v3_backend_surgery.md` §1.

---

## 미결 항목 (v3 착수 전 결정)

- [x] `pending.json`(계약 E) 흡수 → **폐지 확정**. FSM 을 파생으로 돌리고 `watching`/`end`
      상태를 `preview.json` 에 올림. 상세: `v3_backend_surgery.md` "v3 데이터 스키마".
- [x] `scheduled` → `announced` 리네임 + `watching`/`end` 추가 시 data 처리 →
      콜드 스타트로 결정(마이그레이션 없음). 위 "확정된 결정 2" 참조.
- [ ] 텔레그램 현행→v3 명령어 대응표 (`/notice-*` 4개, `/notice-edit` 마법사,
      `pending_*` 슬롯 5종 → `/list /ingest /edit /del /undo × contents` 로 어떻게 접히는지).
      **→ 다른 세션에서 작업 예정 (현행 기능과 거의 동일).**
- [x] `/edit -i` → `/edit` 에 흡수 (별도 명령 아님). 상세는 텔레그램 대응표 작업 때.
- [x] 외부LLM(Groq) 도입 **확정**. 모델 `openai/gpt-oss-120b`(폴백 llama-3.3-70b), 작업 큐.
      번역 실패/환각 폴백은 모델별 실측 후 확정(기본선 = 원문 노출).
      상세: `v3_backend_surgery.md` "모델 선정" / "LLM 작업 큐".
- [x] `watching` 지각 120분 초과 시 강등 대상 = `announced` (url 은 살림).
- [x] **예고 머지 모델 = 소스 신뢰도 티어**. 아이템 = `{제목, 날짜/시각, url, 썸네일}` 필드
      합집합. 갱신 규칙: **높은 티어가 이김, 같은 티어 안에서만 최신순.**
      티어1 `videos.list`/API · 티어2 명시값(트윗 파싱·수동 ingest·YT 알림 제목) ·
      티어3 파생값(TUNEIN 도착+30분). v2.8.1 `api_start_seen` 예외는 v3 에선 불필요
      (그건 "매 tick API 재구성 + 티어 없음" 의 workaround 였음). 필드별 `*_tier` 마커 1개면 충분.
      상세: `v3_backend_surgery.md` "예고 머지 모델".
- [ ] **데드맨 스위치** — `/ingest` 침묵 N시간(예: 6h) 초과 시 Telegram 경보.
      2026-09-09 Automate 조용히 사망 계기. "v3 부터 운용" 합의. `/tick` 이 마지막 ingest
      시각 확인(별도 `heartbeat.json` 또는 기존 파일 mtime) → `notify` 훅. 착수 시 구현.

---

## 참고

- 컨테이너 뷰 아키텍처 그림: `docs/plan/v3_ARCH_DIAGRAM.png` (점선 = 배포·운영 경계).
  용어는 `docs/TERMINOLOGY.md` 와 일치.
- 착수 조건 미충족 시에도 선행 실험(YouTube 알림 문구 수집)은 진행 가능 — v3 코드가 아님.
- v3 는 v2 와 비호환 가능성이 높아 메이저 버전 업으로 잡음.
