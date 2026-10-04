# v4 후속 작업 — 2026-10-04 이어받기

작성: 2026-10-04 (KST 02시경). 이전 세션이 토큰 한도로 중단 — 아래 두 작업이 운영자 요청으로 남았다.
현행 운영 = **v4.0.4** (`main` `b598bd4`, 리비전 `mewtype-backend-00128-2zw` · `mewtype-telegram-00094-fm4`).

> **2026-10-04 오전 갱신**: 작업 1 · 2 를 브랜치 `fix/v4.0.5-popup-pin-notice-body-ko` 에서 구현(v4.0.5, `docs/VERSION.md`).
> 운영자 결정 — 빗나간 클릭은 위아래 레인까지 본다(써 보고 조정) · 필드 이름 `body_ko` · 관리 페이지에서 수정 가능 · 지난 소식 백필함.
> 추가 요청(같은 세션): 고정한 요소 표시 — 호버 흰 테두리를 팝업이 떠 있는 동안 유지. 검증: self-test · 하네스 80/117/52 ·
> Chrome 데스크톱 + 모바일 폭(500px)에서 10-03 실제 리포트 데이터로 빗나간 클릭 → 고정 · 링크 새 창 · 바깥 클릭 닫힘 · 드래그 · 자동 갱신 중 유지.
> **남은 것**: 배포 후 실제 공식 소식 1건이 `body_ko` 와 함께 저장되는지 · 백필 진행(정기 수집 10분마다 10건, 약 2시간).
배포 · 버전 경과: `docs/VERSION.md` v4.0 ~ v4.0.4, 배포 계획 · 진행 기록 `ref/v4a/v4_release_plan.md` §10.

---

## 작업 1. 리포트 팝업 — 클릭하면 고정, 바깥 클릭이면 닫힘 (모바일은 가까운 요소로 보정)

**운영자 요청 원문**: 관리자가 팝업을 사용할 수 있도록 해당 요소를 클릭 시(모바일에서는 가까운 요소 클릭으로 보정) 팝업이 항상
떠 있도록 유지. 팝업의 바깥을 클릭하면 팝업이 꺼지도록.

**왜 필요한가**: v4.0.4 에서 팝업에 링크(YT url · X url)가 생겼는데, 링크는 **고정된 팝업에서만** 누를 수 있다(호버 팝업은 마우스를
옮기면 사라짐). 모바일은 호버가 없고 점(반지름 5px)이 작아 거의 못 맞힌다.

**지금 동작 (코드로 확인, `src/backend/monitor_report.py` 템플릿 JS)**
- `wireTip(el, tipData)`: `mousemove` = 호버 팝업, `click` = `pinTip()`(고정) + `stopPropagation`. 이미 고정이면 무시.
- 플롯 영역 `scrollEl` 의 `click` 핸들러(`setupInteraction` 안): 고정 중이면 **아무 데나 눌러도 `unpinTip()`** — 팝업 안의
  링크를 누르는 클릭은 팝업이 `#tooltip`(플롯 밖 `position:fixed`)이라 여기 안 걸리지만, 플롯 안 다른 요소 클릭은 닫기로만 쓰인다.
  고정이 아니면: 트리거 밴드 안이면 가장 가까운 트리거 막대로 보정(`findNearestTriggerMark`, 터치 `TRIGGER_TOUCH_SNAP_PX=70`),
  **그 밖이면 요소를 빗나간 클릭을 「세로선 고정」(`placeCrosshair` + `pinned=true`, 팝업 없음)으로 처리**한다 —
  2026-10-04 검증 중 점을 몇 px 빗나간 클릭이 이렇게 돼 「고정됐는데 팝업이 없는」 상태가 됐다.
- `document` 의 `click`: 고정 중이고 클릭이 팝업 · 플롯 밖이면 `unpinTip()`.
- 모바일 판정 상수 `IS_NARROW` 가 이미 있다.

**바꿀 것 (제안 — 착수 전에 운영자와 세부 확인)**
1. 플롯 안 빈 곳 클릭: 고정 중이면 닫기(지금과 같음). 고정이 아니면 **가장 가까운 팝업 요소**(예고 구간 · 소식/트윗 점 · 업스트림 아이콘 ·
   명령 점)를 찾아 그 팝업을 고정 — 같은 줄(Y 레인) 안에서 X 거리로, 스냅 거리는 모바일(`IS_NARROW` 또는 `pointerType==="touch"`)을
   넉넉히. 찾을 게 없을 때만 지금의 세로선 고정.
   - 요소마다 `tipData` 와 위치(x, 레인 y)를 배열로 모아 두면(트리거의 `triggerMarks` 방식) 찾기가 쉽다.
2. 고정된 팝업은 **팝업 바깥 클릭이 있을 때까지 유지**(5초 자가 갱신 · 60초 `/monitor-live.json` 갱신으로 다시 그려질 때도 —
   v3.8.8 `loadDay({skipTimeline})` 가 고정 중 타임라인 재렌더를 건너뛰는지 확인할 것).
3. 팝업 안 링크 클릭 · 텍스트 선택은 닫기로 처리하지 않는다(지금 `document` 핸들러가 `tooltip.contains` 로 이미 제외).
4. 모바일에서 고정 팝업이 화면 밖으로 나가지 않게 위치 보정(지금 `showTip` 은 커서 +14px 고정).

**확인 방법**: Chrome 데스크톱 + 모바일 폭(DevTools 기기 모드 또는 실제 폰)에서 — 점을 몇 px 빗나가게 탭 → 그 점 팝업이 고정되는지,
링크가 새 창으로 열리는지, 팝업 바깥 탭 → 닫히는지. 드래그 이동(v4.0.3)과 충돌 없는지(`dragMoved` 로 드래그 끝 클릭 무시 중).

---

## 작업 2. 소식 본문 한글 번역 저장

**운영자 요청 원문**: 소식도 번역에 대해 저장할 것.

**지금 상태 (데이터 · 코드로 확인)**
- `notices.json` 항목 필드: `title`(원문에서 뽑은 일본어 제목) · `title_ko`(LLM 이 뽑은 **한글 제목** — 번역이 아니라 별도 추출,
  팬 화면 소식 줄에 「title_ko — title」로 표시) · `title_raw` · `body_raw`(트윗 원문) · `tweet_url` 등. **본문 한글 번역 필드는 없다.**
- 그래서 v4.0.4 리포트 팝업의 소식 「한글」 칸은 `title_ko`(제목)를 대신 보여준다(`monitor_report.attach_details`).
- 개인 트윗은 `tweets.json` `text_ko` 에 본문 번역이 이미 저장된다 — 같은 방식으로 맞추면 된다.

**바꿀 것**
1. 계약: 소식 항목에 `body_ko`(이름은 TERMINOLOGY · SPEC 기준 확인 후 — 트윗의 `text_ko` 와 맞출지 운영자와 상의) 추가.
   `docs/SPEC.md` 소식 계약 · `src/backend/notices.py`(필드 목록: 머지 시 보존하는 키 · 편집 가능 키 `_EDITABLE`) 먼저.
2. 번역 시점: 소식 준비 단계 `telegram_app._prepare_notice`(접수 서비스, 외부 LLM 은 여기서 — v4 원칙 ④)에서 `llm.translate` 로
   본문 번역 → 커밋(`_commit_notice` · writers `apply_notice`)이 저장. 실패하면 `needs_tl` 로 남기고 재시도 —
   재시도 경로 `enrich.collect` / `enrich.apply_translations`(로컬) · `handlers._translate_sweep`(배포판, 정기 수집 안)이 소식의 어떤 필드를
   번역 대상으로 보는지 확인해 `body_ko` 를 추가.
3. 리포트: `monitor_report.attach_details` 의 소식 `ko` 를 `body_ko`(없으면 지금처럼 `title_ko`)로.
4. 관리 페이지 소식 수정 창에 본문 번역 표시 · 수정이 필요한지 운영자에게 확인(트윗 수정은 한글 번역만 고치는 방식 — `admin_api.edit_tweet`).
5. 지난 소식: 새 필드가 없으므로 비어 있다. 백필이 필요하면 별도(번역 호출 비용 — Groq).

**확인 방법**: self-test(`python -m src.backend.notices` · `telegram_app` · `enrich`) · 하네스 `ref/v4a/verify/harness*.py`(80/117/52) ·
배포 후 실제 공식 소식 1건이 `notices.json` 에 `body_ko` 와 함께 저장되고 리포트 팝업 「한글」에 본문 번역이 나오는지.

---

## 그 밖에 남은 것 (이전 세션 기록)

- **스테이징 정리**: 서비스 `mewtype-backend-stage` · `mewtype-telegram-stage`, 큐 `mewtype-wake-stage`, 데이터 저장소 브랜치
  `data-stage` · `monitoring-stage` · `ops-stage`, Secret `ADMIN_SECRET_STAGE` — 관찰(48h) 뒤 정리. 비용 거의 없음(scale-to-zero).
- **로컬 v4a 러너**(`desktop-68v1g6c`)는 아직 폰에서 알림을 같이 받는다 — 계속 둘지 · 폰 v4a 쪽 전송을 뗄지 운영자 결정.
  배포판이 놓친 알림 대조용으로 쓸 수 있다(관리 페이지 `/admin/api/jobs_overview` 흐름).
- 리포트 팝업 「video:」 칸이 멤버 줄의 마지막 제목을 공유하던 문제는 v4.0.4 에서 구간별로 바뀌었다(해결).
- 배포 시 주의: `gcloud run deploy --source .` 는 로컬 트리를 올린다 — 배포 전 `git fetch` 후 로컬 = origin 확인(메모리 `deploy_verify_origin_sync`).
  운영 배포는 Claude Code 자동 권한 판정에 막힐 수 있다(10-03 실제로 막힘 → 운영자가 `/permissions` 로 허용).
- 핫픽스 번호: `v4.0.Z` 의 Z 만 올린다. 다음은 **v4.0.5**.
