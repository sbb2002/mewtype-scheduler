# v4.5.9 핫픽스(작업 중) — 게임 계정 글: 게임 밖 콜라보 · 행사는 행사 배너 대신 소식으로

작성 2026-10-20 23:50 KST · 상태 **미완 · 미커밋 · 미배포** (운영자: 「병합은 나중에」, 커밋 · 푸시도 보류)

## 1. 계기

- 2026-10-20 14:42 KST 게임 계정 `@bang_dream_on`(バンドリ！アワーノーツ) 트윗
  https://x.com/bang_dream_on/status/2112419038190281019 — 「#推し旅 コラボ開催決定！ JR東海×『BanG Dream! Our Notes』」
  (오리지널 보이스 드라마 · 캐스트 크로스 토크 무비 · 도카이도 신칸센 승차 특전, 2026-11-30 ~ 2027-02-28).
- 14:44 KST 백엔드가 행사 배너 `bn_b1f2b1e8` 「あなたと紡ぐ はじまりの旅」(이름은 첨부 키비주얼 이미지 글자)로 올림.
  LLM 판단 기록 `llm_1cef1cba59`(ops `llm_actions.json`, kind `banner_judge`).
- **운영자 결정(2026-10-20)**: 게임과의 콜라보는 맞지만 게임 안 이벤트 스토리 · 가챠가 있는 구성이 아니므로 배너가 아니라 **일반 소식**.
  게임 계정 글 중 소식으로 올리는 범위 = **게임 밖 콜라보 · 행사만**(외부 기업 콜라보 · 오프라인 행사 · 굿즈 · 캠페인).
  점검 · 보상 · 로그인 보너스 · 업데이트 · 곡 추가 · 생방송 안내 같은 일상 공지는 지금처럼 버린다.

## 2. 원인 (코드 확인)

- `telegram_app.py` `/ingest` 분기: 게임 계정 글(`_game_account`)은 **행사 판정(`_handle_banner_ingest` → `_banner_ingest_core`)으로만** 가고
  판정이 none 이면 버려진다 — 소식으로 가는 길이 없었다. 그래서 이 글은 배너 아니면 버림 둘 중 하나였고, LLM 이 개최 기간이 있다고 배너를 골랐다.

## 3. 지금까지 한 것 — 워크트리 `mewtype-scheduler-worktrees/v4/hotfix-game-collab-notice`(브랜치 `hotfix/game-collab-notice`, origin/main `329732a` 기준, **커밋 안 됨**)

변경분 전체 = 같은 폴더의 `game_collab_notice.patch`(`git apply` 로 복원 가능 — 다른 PC 면 `origin/main` 에서 새 브랜치를 만들고 적용).

- `src/backend/llm.py` `banner_judge`
  - 출력에 **`post_kind`**(game_event · gacha · game_notice · broadcast · outside · other)를 먼저 고르게 하고, action enum 에 **`notice`** 추가.
  - **코드가 post_kind 로 정한다**: `outside` 이고 action 이 none/upsert → `notice` · action 이 notice 인데 post_kind 가 outside 가 아니면 → `none`.
    (action 만 물었을 때 같은 13건에 실행마다 9~13건 일치로 흔들렸다.) notice 면 event · gacha 는 비운다. 반환 dict 에 `post_kind` 추가.
  - 프롬프트: 배너(upsert)는 글(이미지 글자 포함)에 게임 안 이벤트 · 가챠 표현(チャレンジライブイベント · イベント報酬 · イベントpt · ガチャ · ゲーム内 ·
    イベントストーリー · 「(밴드)初イベント」 · イベント「제목」予告)이 있을 때만 · 캐릭터 줄거리 이벤트 예고는 game_event ·
    외부 기업 · 철도 · 영화 콜라보 · 오프라인 행사 · 토크쇼 · 사인회 · 광고 게재 · 굿즈 · 특전 · 시리얼 코드 배포 · 캠페인 → notice ·
    운영 공지(로그인 보너스 — 「開催記念」 「公開記念」 포함 · 곡/MV 추가 · 업데이트 · 시리얼 코드 사용 안내 등)와 방송 안내 → none.
- `src/backend/telegram_app.py`
  - `_banner_ingest_core`: 판정이 `notice` 면 배너 쓰기(`apply_banner`)를 부르지 않고 **`_maybe_auto_notice(raw, now_iso, tag, title)`**(기존 소식 파이프라인 —
    제목 추출 · 번역 · 중복 판정 · `banners.covers_text` 겹침 확인)로 넘긴다. LLM 판단 기록은 `undo=None`(검토용 — 되돌릴 배너 데이터 없음).
    모니터 이벤트 `flow=notice detail="banner mode: notice · 소식 <mode>"`. 응답 `{"banner": "notice", "detail": "소식 <mode>"}`.
  - `_BANNER_VERDICT["notice"] = "행사 배너 아님 — 게임 밖 콜라보 · 행사라 소식으로"`.
  - `_run_banner`(LLM 판단 반려 → 사용자 판단): `choice == "notice"` 면 강제 판정 `{"action": "notice", …}` 로 같은 경로.
  - 셀프테스트(`python -m src.backend.telegram_app`): notice 판정이면 소식 파이프라인을 부르고 배너 쓰기를 안 부르는지(`_game_account` 테스트 바로 뒤).
- `src/backend/admin_static/admin.html`: LLM 판단 「사용자 판단」 팝업(banner_judge)에 선택지 **「소식으로 올림」** 추가.
- 셀프테스트 통과: `telegram_app`(전부터 있던 의도된 Traceback 5개는 변경 전과 같음) · `llm` · `banners` · `admin_api`.

## 4. 실제 LLM 확인(Groq, 이 폴더의 스크립트 — 루트 `.env` 의 `GROQ*` 를 읽는다, 워크트리 경로는 스크립트 안 `sys.path` 를 고칠 것)

- 재료 `bj_cases.json` = ops `llm_actions.json` 의 banner_judge 입력 원문 55건(중복 제외, 10-06 ~ 10-20).
- `bj_live.py`(13건 기대값 대조): 마지막 프롬프트 직전 버전에서 3회 연속 13/13.
- `bj_all.py`(55건 전부, 옛 판정과 비교): JR 「推し旅」 · 도쿄메트로 광고 · 영화 입장 특전 · 마치★아소비 토크쇼/사인회 → notice,
  점검 · 업데이트 · 곡 추가 · 생방송 → none, 챌린지 라이브 · 가챠 → upsert. (`active=[]` 로 돌려서 옛날엔 「이미 반영한 재공지」였던 글이
  none→upsert 로 많이 나오는 것은 정상 — 실서비스는 현재 배너 목록을 준다.)
- 처음에 「millsage 初イベント 「お願い、サイドスロー」予告」(이벤트 스토리 예고)가 outside 로, 「13th☆LIVE 開催記念 特別ログインボーナス」가 game_event 로 오판 → 규칙 보강.
- `bj_focus.py`(경계 11건 × 3회): **마지막 결과 33회 중 3회 어긋남** — 모두 영화 「公開記念 特別ログインボーナス」 글 2건이 outside(notice)로 나옴(기대 game_notice).
  최종 프롬프트로는 `bj_live.py` · `bj_all.py` 를 다시 돌리지 않았다 — 이어받으면 먼저 다시 돌릴 것.

## 5. 운영자 결정 대기 (2건)

1. **영화 공개 기념 로그인 보너스**(「📢開催決定！ 映画『Ave Mujica prima aurora』公開記念 特別ログインボーナス」 등): 게임 안 로그인 보너스라 버림인가, 영화 콜라보라 소식인가.
   (Claude 안 = 버림. LLM 은 33회 중 3회 소식으로 봄.)
2. **오프라인 행사 사후 · 현장 보고**: 마치★아소비처럼 「토크쇼 시작」 「아트 디렉터 토크」 「사인회 종료」가 따로 오면 소식 3건이 될 수 있다
   (같은 날짜 소식은 LLM 중복 판정이 일부만 합친다). 「終了しました」 같은 사후 보고를 소식에서 뺄지.

## 6. 남은 일 (순서)

1. 위 2건 결정 → 프롬프트 반영 → `bj_focus.py` · `bj_live.py` · `bj_all.py` 재확인.
2. 문서: `docs/SPEC.md` 계약 J(행사 배너) 판정 결과에 `notice` · `post_kind`, `docs/VERSION.md` v4.5.9 항목(+ 병합 뒤 태그 대조표 한 줄),
   `CLAUDE.md` 상단 「현재 버전」 줄 · v4.5.9 항목, `README.md` 「현재 버전」, 필요하면 `docs/TERMINOLOGY.md`(「게임 밖 콜라보 · 행사」).
3. 커밋 → PR → 병합(운영자 결정) → **두 서비스 배포**(`bash deploy/deploy.sh` · `bash deploy/deploy_telegram.sh` — 둘 다 telegram_app · llm 을 씀.
   배포 전 메인 폴더가 origin/main 과 같은지 확인) → 태그 `v4.5.9`.
4. **데이터 정리**(운영자 확인 뒤): 배너 `bn_b1f2b1e8` 을 내리고(관리 페이지 「소식 · 트윗」 탭 맨 위 삭제 = 보관함 이동, 또는 LLM 판단 `llm_1cef1cba59` 반려 →
   「사용자 판단: 소식으로 올림」 — 이 경로면 배너 롤백 + 소식 등록이 한 번에 된다, 배포 뒤에만 가능) 같은 글을 소식으로.
   반려 경로가 가장 깔끔하다(`restore_banner` before=None → 배너 제거, 이어서 소식 파이프라인).

## 7. 참고

- 이 대화(2026-10-20)에서 v4.5.8 은 배포 완료(백엔드 `mewtype-backend-00162-gjs` · `mewtype-telegram-00114-2g5`, 프론트 main `bc05ec3`, 태그 `v4.5.8` → `bc05ec3`).
  v4.5.9 는 그 위의 다음 핫픽스.
- 행사 배너 설계 원문: `ref/v4a/v4a_event_banner_design.md`, 계약 `docs/SPEC.md` 계약 J, 용어 `docs/TERMINOLOGY.md` 「행사 배너 용어」.
