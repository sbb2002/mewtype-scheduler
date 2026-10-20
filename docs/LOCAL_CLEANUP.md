# 로컬 정리 절차 (PC 마다 한 번)

여러 PC 에서 작업하다 보면 PC 마다 워크트리 · 미추적 자료 · 시험 데이터가 제각각 쌓인다. 이 문서는 한 PC 를 아래 **목표 상태**로
맞추는 절차다. 2026-10-20 에 첫 PC 를 이 순서로 정리했다(맨 아래 「첫 정리 기록」).

> **Claude 세션에게**: 운영자가 「`docs/LOCAL_CLEANUP.md` 읽고 정리해」라고 하면 이 문서대로 진행한다.
> - 1단계(안 올린 커밋)와 2단계(조사)는 **아무것도 바꾸지 않는다**. 결과를 운영자에게 먼저 보여준다.
> - **지우기 전에 반드시 대조한다** — 원격(`origin/main` · `origin/devpapers`)이나 보관소에 **해시까지 같은 것**이 있을 때만 지운다.
> - 분류표로 판단이 안 서는 파일 · 폴더, `main` 에 병합 안 된 브랜치, 안 올린 커밋은 **임의로 처리하지 말고 목록으로 보여주고 묻는다**.
>   이 PC 에만 있는 자료일 수 있다.
> - `main` 병합 · 배포는 운영자 결정. 이 절차에서 `main` 을 고칠 일은 없다(규칙은 이미 `main` 에 있다).

## 목표 상태

규칙의 원본은 `main` 의 `CLAUDE.md` 「주의점」(**로컬 워크트리 배치** · **버전 올릴 때 할 일**) · 「문서 위치」 상자다. 여기는 요약.

```
myprojects/
  mewtype-scheduler/              ← 메인 저장소 = main 체크아웃 (제자리 — 옮기면 Claude 프로젝트 메모리 경로가 바뀐다)
  mewtype-scheduler-worktrees/
    devpapers/                    ← devpapers 브랜치 (ref/ · 기록 문서는 여기서 관리)
    v4/<브랜치 이름의 / 를 ->     ← 예: hotfix/web-analytics → v4/hotfix-web-analytics
    v3/…                          ← 옛 줄기 브랜치를 열 때
  mewtype-scheduler-localdata/    ← git 밖. 로컬 러너 시험 데이터(.env.local · _local/) — 비밀값 있음, 커밋 금지
    <이름>/.env.local · _local/ · verify/
  mewtype-bus/                    ← 에러 버스 공유 폴더(워크트리 아님, 있으면 그대로)
```

- `ref/`(작업 기록 · 실험 자료 · 목업 · 캡처 · 로그)는 **`devpapers` 에만** 둔다. `main` 에는 없다.
- `.agents/` · `.claude/` · `skills-lock.json`(Claude 스킬 설치분)은 `main` 의 `.gitignore` 대상 — 그대로 둔다.
- 병합이 끝난 워크트리 · 브랜치는 지운다. 원격 브랜치는 지우지 않는다.

## 1. 안 올린 커밋 찾기 (가장 먼저 — 읽기만)

```bash
cd myprojects/mewtype-scheduler
git fetch --all --prune
git log --branches --not --remotes --oneline --decorate   # 어느 원격에도 없는 로컬 커밋
git stash list                                              # 잊힌 stash
```

나오면 정리 전에 운영자에게 묻는다: 푸시할지 · 버릴지 · 그대로 둘지. 같은 변경이 이미 `main` 에 다른 커밋으로 들어갔는지는
`git cherry origin/main <브랜치>`(`-` = 같은 패치가 main 에 있음) 와 파일 내용 비교로 확인해 같이 알려준다.

## 2. 조사 (읽기만)

```bash
ls ../ | grep mewtype                                   # 형제 폴더들
git worktree list                                       # 워크트리 · 체크아웃 브랜치
git branch -vv | grep ': gone]'                         # 원격에서 지워진 로컬 브랜치
for w in $(git worktree list --porcelain | awk '$1=="worktree"{print $2}'); do
  echo "== $w"; git -C "$w" status --short --ignored    # ?? = 미추적, !! = 무시됨(.env · _local · .venv 등)
done
```

경로가 바뀐 옛 워크트리가 있으면 `git worktree prune` 전에 실제 폴더가 남아 있는지 본다.
결과를 아래 3단계 분류표로 나눠 **표로 보여준 뒤** 진행한다.

## 3. 파일 분류

| 무엇 | 확인 | 처리 |
|---|---|---|
| 원격에 **해시까지 같은** 파일이 있음 | 아래 대조 명령 | 지움 |
| `ref/` 자료(또는 `docs/` 아래 기록 문서)인데 `devpapers` 에 없음 · 내용 다름 | 대조 + 비밀값 검사 | `devpapers` 워크트리에 복사해 커밋 · 푸시. 내용이 다르면 어느 쪽이 새것인지 운영자 확인 |
| `.env*` · `_local/` · 검증 결과처럼 git 제외로 정한 시험 데이터 | 크기 · 키 이름만 확인(값 출력 금지) | `mewtype-scheduler-localdata/<이름>/` 으로 복사 → 체크섬 대조 → 원래 자리 정리 |
| `.venv/` · `__pycache__/` · 빈 파일 | — | 다시 만들 수 있으므로 지움 |
| `.agents/` · `.claude/` · `skills-lock.json` | — | 그대로 |
| **위에 안 맞는 것** | — | **목록으로 묻는다** |

대조(파일 이름에 공백 · 일본어가 있어도 되게 `-z`):

```bash
# 미추적 파일 각각이 devpapers 에 같은 내용으로 있는지
git ls-files -z --others ref | while IFS= read -r -d '' f; do
  b=$(git rev-parse -q --verify "origin/devpapers:$f" 2>/dev/null)
  if [ -z "$b" ]; then echo "없음   $f"
  elif [ "$(git hash-object "$f")" = "$b" ]; then echo "같음   $f"
  else echo "다름   $f"; fi
done
# --exclude-standard 를 붙이지 않았으므로 무시된 파일(로그 등)까지 나온다. ref 밖은 경로만 바꿔 같은 식으로
```

비밀값 검사(`devpapers` 에 올리기 전, 특히 로그):

```bash
grep -lE "gsk_[A-Za-z0-9]{10}|ghp_[A-Za-z0-9]{10}|github_pat_|Bearer [A-Za-z0-9._-]{20}|AIza[0-9A-Za-z_-]{20}|[0-9]{8,10}:AA[A-Za-z0-9_-]{30}" <파일들>
grep -ciE "secret|token|password" <파일들>   # 이름만 나오는지, 실제 값이 있는지 눈으로 확인
```

시험 데이터 보관(복사 → 대조 → 정리):

```bash
L=../mewtype-scheduler-localdata/<이름>; mkdir -p "$L"
cp -a <워크트리>/.env.local <워크트리>/_local "$L"/
(cd <워크트리> && find .env.local _local -type f -exec md5sum {} + | sort -k2) > /tmp/a.md5
(cd "$L"      && find .env.local _local -type f -exec md5sum {} + | sort -k2) > /tmp/b.md5
cmp /tmp/a.md5 /tmp/b.md5 && echo 동일
```

보관한 데이터로 로컬 러너 돌리기(복사 없이 경로만): `LOCAL_DATA_DIR=<L>/_local python -m src.backend.local_runner --env <L>/.env.local`
(셸에서 준 값이 env 파일 값보다 우선 — `local_runner.load_env_file`). 보관소에 `README.md` 로 무엇을 왜 넣었는지 적어 둔다.

## 4. 워크트리 옮기기 · 지우기

```bash
git worktree move <옛 경로> ../mewtype-scheduler-worktrees/v4/<브랜치 이름의 / 를 -> # 규칙 경로로
git worktree remove <병합 끝난 워크트리>                                              # 3단계 끝난 뒤에만
```

- 실행 중인 프로세스(로컬 러너 · 수신기 · venv 파이썬)가 폴더를 잡고 있으면 Windows 에서 이동 · 삭제가 실패한다. 프로세스를 임의로 끄지 말고
  운영자에게 끄라고 요청한다.
- `git worktree remove` 는 **무시된 파일(.env · _local 등)도 같이 지운다** — 반드시 3단계 보관을 먼저.
- 메인 폴더를 `main` 으로: `main` 이 다른 워크트리에 열려 있으면 그 워크트리를 먼저 지운다(한 브랜치는 한 폴더에서만).
  로컬 `main` 에 안 올린 커밋이 있으면 1단계 결정에 따른다.
- 브랜치 없이 커밋만 체크아웃된(detached) 워크트리는 그 커밋이 `main` 에 들어 있으면(`git branch -a --contains <커밋>`) 지운다.
- `.venv` 는 옮긴 뒤에도 `python.exe` 직접 호출은 되지만 `activate` 스크립트는 옛 경로를 가리킨다 — 다시 만드는 게 깔끔.

## 5. 브랜치 정리

```bash
git branch -vv | grep ': gone]' | sed -E 's/^[*+ ] +//' | awk '{print $1}' | while read b; do
  git merge-base --is-ancestor "$b" origin/main && echo "병합됨  $b" || echo "미병합  $b"
done
git branch -d <병합됨 브랜치들>        # -D 는 쓰지 않는다. 미병합은 운영자에게 묻는다
```

다른 브랜치를 원격에 맞추는 것(fast-forward 만)은 `pull-from-origin` 스킬이 있으면 그걸로, 없으면 브랜치마다 `git merge --ff-only`.

## 6. 마무리 보고

운영자에게: 지운 것 · 옮긴 것(어디로) · 보관한 것(어디에) · `devpapers` 커밋 해시 · 남겨 둔 것과 이유 · 물어볼 것.
PC 별로 다른 결정(보관소 이름, 남겨 둔 워크트리 등)은 그 PC 의 Claude 메모리에 적어 둔다 — 메모리는 PC 사이에 공유되지 않는다.

## 첫 정리 기록 (2026-10-20, 운영자 데스크톱 1대)

- 안 올린 커밋: 로컬 `main` 의 2커밋(국왕 연출 1분 유지 + 그 병합) — 원 커밋은 `feat/king-leave-fade` 에 남아 있고 같은 변경이 v4.5.1 로
  `main` 에 있어 버리고 `origin/main` 에 맞춤.
- 워크트리: 제각각 이름(`own-bc` · `king-hotfix` …)을 `v4/<브랜치>` 규칙으로 이동, `worktrees/main` 폐지(메인 폴더가 `main`),
  병합 끝난 `v4a` · detached `websub-burst` 삭제.
- 미추적 자료: 메인 폴더 `ref/` 26개 · 워크트리 로그를 `devpapers` 로(`a0dd31f` · `a4f0990` · `d055fe6`), 원격과 같은 사본은 대조 후 삭제,
  `docs/` → `ref/` 로 옮기다 멈춘 문서 3개는 `devpapers` 의 원래 경로로, 빈 `gcloud` 파일 삭제.
- 시험 데이터: `v4a` 워크트리의 `.env.local` · `_local/` · 검증 결과를 `mewtype-scheduler-localdata/v4a/` 로.
- 브랜치: 원격에서 지워진 19개(전부 `main` 병합분) 삭제.
- 1단계를 건너뛰고 시작했다가 문서 작성 뒤 뒤늦게 확인한 것 2건(→ 1단계를 먼저 할 것):
  로컬 전용 `feat/king-leave-fade`(`b70adeb`, 같은 내용이 `main` 에 반영돼 있어 브랜치 · 워크트리 삭제),
  stash 「v3 docs WIP」(09-10 중단본 — 현행판으로 대체됐지만 기록 가치가 있어 `devpapers` `ref/v3_docs_wip_2026-09-10/` 에 보관 후 삭제, `a411bb6`).
- 같은 날 `main` 에 들어간 규칙: PR #68 · #69 · #70(버전 태그 · README 현재 버전 · 워크트리 배치 · `ref/` 는 devpapers · 스킬 설치분 gitignore).
