# IDEA — 아직 구현 안 한 아이디어 메모

> 여기 적힌 건 **구상 단계**다. 착수 전에 재검토하고, 구현하면 해당 항목을 `docs/plan/` 로
> 옮기거나 삭제한다. (SPEC/ARCHITECTURE 는 현행 구현만 기술)

---

## 1) 회원전용 방송 감지

**문제**: 회원전용(멤버십) 라이브는 RSS 에 안 잡혀 `/tick` 후보집합에 안 들어간다.
YouTube Data API `videos.list` 는 video_id 만 알면 `liveBroadcastContent: "live"` 를 정상
반환하지만(2026-09-07 유노 `4SJPTPFKPB4` 로 실측 확인), **video_id 를 발견할 경로가 없다.**
현재 우회: 운영자가 `/ingest` 로 URL 이 든 텍스트를 수동 투입 → `scheduled` 행 → 다음 tick 이 승격.

**아이디어**: X(트윗) 릴레이와 같은 방식으로, **5개 유닛의 YouTube 채널에 대해 폰(Automate)에서
알림 설정**을 하고, "○○ さんがライブ配信を開始しました" 류 푸시 알림을 `POST /ingest`(또는 신규
엔드포인트)로 릴레이. 알림 텍스트에서 채널/URL 을 뽑아 후보집합에 주입 → 정규 파이프라인이
`live` 로 확정.

**확인 필요**:
- YouTube 앱이 **회원전용** 방송 시작에도 푸시 알림을 실제로 보내는가? (일반 방송은 보냄.
  회원전용은 안 보낼 가능성 있음 — 미검증)
- 알림 본문에 video_id/URL 이 들어오는가, 아니면 채널명만 오는가 (채널명만이면 그 채널
  `search.list` 1회 = quota 100, 또는 RSS 재시도로 커버)
- 알림 지연·중복·누락 특성 (X 릴레이처럼 dedupe 키 필요)

**관련**: `docs/plan/v2_3_x_relay.md`(릴레이 구조), `docs/AUTOMATE_MANUAL.md`(폰 수식),
`src/backend/xrelay.py`. 회원전용 TTL·`assumed_live` 는 이미 `xrelay`/`reconcile` 에 있음.

---

## 2) 트윗에서 제목·날짜·URL 파싱 — 제목만 LLM 후보

**날짜·URL**: 원문에서 정규식으로 충분히 추출 가능. 현재도 `xnotice._pick_event_date` /
`_site_url_anchor` 가 처리 중. 유지.

**제목**: 현행 `xnotice._headline`(줄별 점수: shout 블록 병합 · 라벨/스트리밍나열 감점 ·
`最終回` 류 가점 · 중간 이모지 제거 등, v2.8.5) 유지. **정규식으로도 역부족인 경우**
(제목이 장식 없는 2~3줄에 개념으로 흩어진 케이스 등)에 한해 **Groq(외부 백엔드2: LLM)** 로
제목만 추출하는 계획.

**설계 방향** (2026-09 논의):
- `xnotice.parse` 는 순수 함수 유지 — LLM 호출은 `telegram_app` 의 impure 레이어에서
  `parse` 성공 후 `merge_notice` 전에 `title`(+`title_slug`)만 덮어씀. 훅 지점: `_apply_notice`
  / `_maybe_auto_notice` 공용 헬퍼.
- `mewtype-telegram` 서비스에서만 돔. `GROQ_API_KEY` → Secret Manager → `deploy_telegram.sh`.
- `requests` 로 OpenAI 호환 엔드포인트(`api.groq.com/openai/v1/chat/completions`), 새 의존성 없음.
  model `llama-3.1-8b-instant`, `response_format=json_object`, 3s 타임아웃.
- 폴백: 키 없음 / 타임아웃 / 429 / 이상응답(길이초과·URL·해시태그 포함·빈값) → 정규식 `_headline`.
- self-test: `GROQ_API_KEY` 있을 때만 도는 통합 테스트 1개 (`gh_store` 의 `GH_TOKEN_TEST` 패턴).
- dedup 무영향: `notices._same_group` 은 `date`+`anchor_a`/`anchor_b` 만 씀 (`title`/`title_slug`
  안 씀).

**미해결**: **환각(hallucination) 대비가 아직 설계에 없음.** LLM 이 원문에 없는 제목을 지어낼 때
거르는 방법 필요 — 예: 출력 제목의 토큰이 원문에 실제로 존재하는지 검사, 또는 confidence 반환
요구 후 임계값 미달 시 폴백.

**착수 조건**: 프로덕션에서 개선된 정규식(`v2.8.5`)으로 2주쯤 돌려보고 "얇은/틀린 제목" 빈도가
여전히 거슬리면. 그전까진 `/notice-edit`(v2.8.3) 수동 교정으로 충분.
