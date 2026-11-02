# 원격에 아직 못 올린 버전 태그

버전 태그는 그 버전이 `main` 에 들어온 **병합 커밋**에 주석 태그로 붙여 원격에 올린다(CLAUDE.md 「버전 올릴 때 할 일」 1번).
클라우드 세션에서 태그 푸시가 막혀 못 올린 것을 여기 모아 두고, 운영자가 로컬에서 작업할 때 올린다.
올린 뒤에는 그 줄을 지우고 `docs/VERSION.md`(main) 태그 대조표의 판단 메모에서 「태그 원격 푸시 실패」 문구도 지운다.

## 남은 태그

### v4.11.8 — 병합 커밋 `2ab5f3a`

- 기록 시각: 2026-11-03 (KST)
- 병합 커밋 전체 해시: `2ab5f3abd2dd9e60ecf21d6f566e92b0ea3f0490`(PR #143, 브랜치 `hotfix/yuno-birthday-script`)
- 못 올린 이유: 클라우드 세션에서 `git push origin refs/tags/v4.11.8` 를 여섯 번 시도했으나 매번 원격이 연결을 끊었다(`remote end hung up`). 같은 세션에서 브랜치 푸시는 정상이었다.
- 태그 메시지 둘째 줄 = `docs/VERSION.md` 의 v4.11.8 항목 첫 줄을 줄인 것.

로컬 `mewtype-scheduler/`(main 체크아웃)에서:

```bash
git fetch origin
git tag -a v4.11.8 2ab5f3abd2dd9e60ecf21d6f566e92b0ea3f0490 -m "v4.11.8" -m "유노 생일 대사 — 「YUNO's party Lv. 3」 를 「내 생일 파티」 로 · 가려지던 「왜 별을 세냐고?」 살리기 · 감사 카드 · 제어 패널 도움말 정리 (일반 패치 · 핫픽스 등급)"
git push origin refs/tags/v4.11.8
git ls-remote --tags origin v4.11.8   # 확인: 태그 줄과 ^{} 줄이 2ab5f3a… 를 가리키면 끝
```

- `git push --tags` 는 쓰지 않는다(로컬 실험 태그까지 올라간다).
- 로컬에 같은 이름 태그가 이미 있으면 `git tag -d v4.11.8` 로 지우고 다시 만든다.
