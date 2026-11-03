# 유노 생일 이스터에그 자료 (완료)

유노(11월 4일) 생일 이스터에그 작업에서 나온 자료만 모은 폴더다. 2026-11-03 운영자가 「유노 이스터에그 작업 완료」 를 알렸고,
다른 멤버 작업과 섞이지 않게 멤버별로 나눴다. 다른 멤버 자료는 `ref/easteregg-<멤버>/` 에, 5명 공통 자료는 `ref/easteregg-common/` 에 둔다.

사이트에 들어간 버전: v4.10.0(생일 스킨 · 유노 장면) ~ v4.11.9 — 버전별 내용은 `main` 의 `docs/VERSION.md`.
다음 멤버를 이어서 만드는 법은 `main` 의 `docs/BIRTHDAY_SKIN.md` 를 본다.

| 경로 | 내용 | 원래 위치 |
|---|---|---|
| `birthday-script/YUNO_SCRIPT.md` | 곡 시각별 유노 대사 점검표(`hotfix/yuno-story-arc` 코드에서 생성) | devpapers `ref/birthday-script/` |
| `bgm/` | 생일 음원 원본 2곡(`Noctural Run.mp3` · `Midnight Groove.mp3`). `main` 의 `src/frontend/assets/birthday/bgm/noctural.mp3` · `midnight.mp3` 와 같은 파일(MD5 일치, 2026-11-03 확인) | devpapers `ref/bgm_easteregg_birthday/`(미커밋) |
| `BIRTHDAY_STORY_HANDOFF.md` | 감상 이야기 · 완주 보상 인계(2026-11-01 작성). **문서 안의 「미완성 WIP · 배포 안 함」 은 작성 당시 상태** — 이후 `feat/birthday-story` 로 v4.11.3 에 병합 · 배포됐다 | `main` 작업 트리 `docs/`(미커밋) |
| `docs/` | 유노 작업 전용 인계 · 검증 기록 4개 — `BIRTHDAY_MUSIC_SCENE_HANDOFF.md`(v4.11.0 음악 연동 Codex 인계) · `BIRTHDAY_MUSIC_SCENE_VERIFICATION.md`(v4.11.0 3차 검증 · 성능 표) · `BIRTHDAY_PLAYER_HOTFIX_VERIFICATION.md`(v4.11.1) · `BIRTHDAY_GREETING_HOTFIX_VERIFICATION.md`(v4.11.2). 안의 `docs/…` 표기는 `main` 의 문서를 가리킨다 | `main` `docs/`(브랜치 `docs/easteregg-yuno-archive` 에서 옮김) |
| `birthday-continuation/` | 이전 세션들이 쓴 보조 스크립트(검증 · 측정 · 릴리스 준비) · 산출 JSON · PR 본문 초안 · `delivery/` · `monitor-delivery/`(당시 반영본 사본). 실행 경로는 옛 `tools/birthday-continuation/` 기준이라 그대로 돌아가지 않을 수 있다 | `main` 작업 트리 `tools/birthday-continuation/`(미커밋) |
