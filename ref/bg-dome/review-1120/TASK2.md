# 체험 과제 — UFO 테마 처음부터 끝까지 (첫 접속 가정)

요청자: 운영자(Claude t3 중계). 세 모델(Claude · Codex · Antigravity)이 각자 체험 → Claude 가 모아 전달.
**코드 수정 · 커밋 금지.** 읽기 · 로컬 실행 · 캡처만.

## 대상
- 브랜치 `feat/bg-dome` **HEAD 5599a2e** (앞 검토 뒤 수정 반영본 — 사진 못 받은 워프 · 저사양 배경 보기 멈춤 · 첫 해금 무음 · 핀치 안내 기억 · 기어 패널 겹침 · 패널 잘림 · 성능 정리)
- 워크트리 `C:\Users\User\Documents\pyworks\mewtype-scheduler-worktrees\v4\feat-bg-dome`
- 로컬 실행: 워크트리에서 `python scripts/serve_local.py <포트>` → `http://localhost:<포트>/src/frontend/` (**?bg= 없이** — 첫 방문은 기본 테마). 폰 폭(390×844 등) · 터치 에뮬레이션.
  다른 모델과 포트가 겹치지 않게: Codex 8141, Antigravity 8142.

## 체험 방법
- **첫 접속 가정**: 저장소(localStorage) 빈 상태에서 시작. 기본 테마 화면 → 테마 버튼 길게 눌러 UFO 선택 → 배경 보기(레인 빈 곳 길게 눌러 위로 튕기기) → 두 손가락 벌려 조작 패널 → 찾기 · 해금(토성 → 초행성X → 성운 → 성간 이동 → 워프 → 딥필드 5곳 표식 → 달 궤도 → 지구 → 보상 YMMT · 자유 항해 · 별자리 5개 → 별빛 조명) → 플레이어 곡 재생 중 연동까지 **끝까지**.
- 가능한 한 **실제 손길**(CDP 터치 · 클릭)로. 헤드리스엔 자이로가 없으므로 시선 이동만 `?bgdebug` 의 `__bgview(방위, 고도)` 를 써도 된다(쓴 곳은 표시). `__bgunlock` 의 `targets` 로 대상 위치를 보는 것은 「공략을 본 것」이므로 쓰면 그렇다고 밝힐 것. 모두 열기(`bgunlock=all`)로 건너뛰지 말 것.
- 막히면 막힌 지점 · 얼마나 헤맸는지가 곧 소감의 핵심이다.

## 결과 (한국어 마크다운)
1. 단계별 체험 기록(무엇을 했고 무엇이 보였나 · 걸린 시간 · 막힌 곳)
2. **소감** — 재미 · 몰입 · 헷갈림 · 지루함 · 감동 포인트, 처음 사용자 입장에서 솔직하게
3. 새로 발견한 문제(앞 검토에 없던 것) — 근거(캡처 경로 · 파일:행)
4. 확인 못 한 것은 「확인 필요」
저장: Codex → `C:/Users/User/AppData/Local/Temp/claude/190db50d1f62be64/ba7c07e8-ac05-4e01-b05f-6ca6d0aa05b7/scratchpad/review/play_codex.md`, Antigravity → `C:/Users/User/AppData/Local/Temp/claude/190db50d1f62be64/ba7c07e8-ac05-4e01-b05f-6ca6d0aa05b7/scratchpad/review/play_antigravity.md`. 끝에 `END` 한 줄.
