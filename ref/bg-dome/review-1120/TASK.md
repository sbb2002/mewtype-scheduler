# 병합 전 검토 과제 — UFO 돔 테마(feat/bg-dome → v4.12.0 예정)

요청자: 운영자(Claude Code t3 세션이 중계). 세 모델(Claude · Codex · Antigravity)이 각자 독립 검토 → Claude 가 합집합 요약.
**코드는 고치지 말 것(읽기 · 로컬 실행 · 캡처만).** 커밋 · 푸시 금지.

## 대상
- 브랜치 `feat/bg-dome` (HEAD 94a9d95), 워크트리 `C:\Users\User\Documents\pyworks\mewtype-scheduler-worktrees\v4\feat-bg-dome`
- 명세: 그 워크트리 `docs/SPEC.md` 「배경 장식」 절(대략 425~470행) · 인계 `git show origin/devpapers:ref/bg-dome/HANDOFF.md`
- 주요 코드: `src/frontend/js/bgdomegl.js`(장면) · bgunlock(해금) · bgwarp · bggear · bgpanel · bghud · bgsound(효과음) · bgmusic(플레이어 곡 연동) · bgpeek(배경 보기) · bgtier(성능 등급)
- 곡 목록: `src/frontend/assets/songs.json` (유메미타 플레이어 곡)
- 로컬 실행: 워크트리에서 `python scripts/serve_local.py <포트>` → `http://localhost:<포트>/src/frontend/?bg=normal` (UFO 테마, 폰 폭 390px 권장. 운영 사이트를 열면 주소에 `?va=claude` 등 통계 제외 파라미터 필수 — 가능하면 로컬만)

## 검토 항목 (4개 모두 답할 것)
1. **UX 어색함** — UFO 테마 이스터에그를 처음 사용자가 **시간 순서대로**(첫 진입 → 배경 보기 → 조작 패널 → 찾기/해금 → 워프 · 성간 이동 → 지구 · 보상 …) 체험할 때 어색하거나 끊기는 지점.
2. **프레임 드랍** — 드랍이 날 만한 구간(전환 · 워프 · 블러 · 재투영 · 딥필드 로드 · 저사양 등급 등). 실측했다면 수치, 코드 추정이면 「추정」 명시.
3. **효과 · 연출 개선 여지** — SE · BGM · 화면 연출.
4. **유메미타 플레이어로 BGM 깔기** — 특정 동작(예: 워프, 지구 도착, 보상, 별자리 찾기 등) 중 플레이어 곡을 BGM 으로 쓸 수 있다면 songs.json 에서 **실제 곡 제목**으로 어울리는 곡 추천 + 이유. 목록에 없는 곡은 쓰지 말 것.

## 규칙
- 확인 못 한 것은 추측으로 채우지 말고 「확인 필요」 로 표시. 각 지적에 근거(파일:행 또는 실측) 첨부.
- 결과는 한국어 마크다운으로 아래 파일에 저장하고, 끝나면 마지막 줄에 `END` 한 줄:
  - Codex → `C:/Users/User/AppData/Local/Temp/claude/190db50d1f62be64/ba7c07e8-ac05-4e01-b05f-6ca6d0aa05b7/scratchpad/review/codex.md`
  - Antigravity → `C:/Users/User/AppData/Local/Temp/claude/190db50d1f62be64/ba7c07e8-ac05-4e01-b05f-6ca6d0aa05b7/scratchpad/review/antigravity.md`
