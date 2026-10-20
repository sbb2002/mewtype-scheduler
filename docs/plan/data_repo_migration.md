# data 저장소 분리 전환 핸드오프

> 다른 세션에서 이어서 작업할 수 있어 남겨두는 문서. 완료되면 devpapers 브랜치로 이전(다른
> `docs/plan/*` 런북과 같은 규칙 — CLAUDE.md "문서 위치" 참고).

## 현황 (2026-09-14 작성)

- **문제**: Vercel Hobby "하루 100회 무료 배포" 한도(`api-deployments-free-per-day`, 고정
  자정 리셋이 아니라 **24시간 롤링 윈도우**)를 `data` 브랜치의 자동 커밋(백엔드가 tick마다
  preview.json/notices.json/tweets.json 등을 나눠 커밋)이 계속 소진시켜, `main`(실제 프론트
  코드) 배포가 막힌 상태로 발견됨.
- **확인 방법**:
  - `gh api repos/sbb2002/mewtype-scheduler/commits/<sha>/status` — Vercel 컨텍스트의
    `description`에 정확한 사유가 찍힌다.
  - Vercel API 직접 호출로도 재확인 가능(아래 "막힘 여부 확인" 참고) — 이땐
    `payment_required` + `code: "api-deployments-free-per-day"` 로 응답.
- **근본 이유**: `vercel.json`의 `git.deploymentEnabled: {"*":false,"main":true}`는 `data`
  브랜치 커밋의 실제 빌드/공개(promote)는 막는다(Vercel API로 봐도 이 시도들은
  `state:"ERROR", target:None`로 끝나 실제 배포되진 않음) — 하지만 **시도 자체는 하루 100회
  한도에 그대로 카운트됨**. GitHub Contents API로 만든 커밋도 일반 `git push`와 동일하게
  브랜치 ref를 갱신하고 push 웹훅을 발생시키기 때문 — 커밋 생성 경로(API vs CLI)는 Vercel
  입장에서 구분되지 않는다.
- **해결 방향**: `data` 브랜치를 Vercel과 연결 안 된 별도 저장소로 분리 — 이 저장소가
  Vercel GitHub App 웹훅 대상이 아니게 되므로 카운트 자체가 발생하지 않음.

## 완료된 것

1. 새 저장소 생성 + 기존 `data` 브랜치 히스토리 그대로 이전:
   **https://github.com/sbb2002/mewtype-scheduler-data** (public, 기본 브랜치 `data`)
2. raw CDN 익명 접근 확인 완료
   (`https://raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/preview.json` → 200)
3. 기존 fine-grained PAT(`GITHUB_TOKEN` Secret)의 repo 권한 범위에
   `mewtype-scheduler-data` 추가 완료(사용자 작업, 2026-09-14)

## 완료 (2026-09-14, 계속)

Vercel 막힘이 안 풀린 상태에서도 2·3단계를 바로 진행하기로 결정 — 이유: 2단계(Cloud Run
env 전환) 자체가 Vercel과 무관해서 언제든 실행 가능하고, 이걸 먼저 하면 `data` 브랜치가
`mewtype-scheduler`(Vercel 연결 repo)에 더는 커밋을 안 하게 되어 24h 롤링 카운트가
새로 채워지지 않고 자연히 빠지기 시작하므로 오히려 3단계(프론트 배포)가 더 빨리 풀릴
가능성이 큼. git push 자체(3단계 커밋)는 Vercel 한도와 무관하게 항상 성공하고, 그 push에
딸린 "배포 시도"만 큐에 쌓여 있다가 슬롯이 열리는 순간 자동으로 반영된다.

4. Cloud Run 환경변수 전환 완료 — `mewtype-backend`(revision `mewtype-backend-00066-677`),
   `mewtype-telegram`(revision `mewtype-telegram-00061-j98`) 둘 다 `GITHUB_REPO=
   sbb2002/mewtype-scheduler-data`로 전환. `deploy/env.sh`도 같이 갱신(다음 재배포 시
   되돌아가지 않게, 이 파일은 gitignore 대상이라 커밋 불필요).
5. 프론트 설정 전환 완료 — `src/frontend/js/config.js`의 `PREVIEW_URL`/`NOTICES_URL`/
   `TWEETS_URL`을 `raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/...`로
   변경, main에 커밋·푸시. **Vercel 배포 슬롯이 열리는 순간 자동 반영됨** — 별도 작업 불필요.

### 확인 방법 (다른 세션에서 이어볼 때)
- 백엔드가 새 저장소에 쓰고 있는지: `https://github.com/sbb2002/mewtype-scheduler-data`
  commits 탭에서 최근 커밋 시각 확인, 또는
  `curl -s https://raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/preview.json`
  의 `generated_at`이 최근인지 확인.
- 프론트 배포가 실제로 반영됐는지: 라이브 사이트(`https://mewtype-schduler.vercel.app/`)에서
  개발자도구 Network 탭으로 `config.js` 요청 확인, 또는 그냥 `curl -s
  https://mewtype-schduler.vercel.app/js/config.js | grep PREVIEW_URL` 로 어느 저장소를
  가리키는지 확인.
- Vercel 막힘 여부 재확인:
  ```bash
  curl -s "https://api.vercel.com/v13/deployments?teamId=team_13wMbRg9gpyOZm4v2xj8skq1" \
    -H "Authorization: Bearer $VERCEL_TOKEN" -H "Content-Type: application/json" \
    -X POST -d '{"name":"mewtype-scheduler","project":"mewtype-scheduler","target":"production","gitSource":{"type":"github","repoId":1351113978,"ref":"main"}}'
  ```
  `payment_required` / `api-deployments-free-per-day` 응답이면 아직 막힘. (`VERCEL_TOKEN`은
  저장소 루트 `.env`에 있음 — `set -a; source .env; set +a`로 로드.)

## 이후 정리 (선택, 급하지 않음)

- 옛 `mewtype-scheduler` 저장소의 `data` 브랜치는 그대로 둬도 무해(더는 안 갱신됨) — 원하면
  나중에 삭제.
- `push_monitor.py`의 `run()`이 `for branch in ("data", "main")`을 **같은 저장소**에서만
  조회하도록 하드코딩돼 있음(`src/backend/push_monitor.py:1118`). data가 다른 저장소로
  옮겨지면 이 로직도 갱신 필요 — 원래 목적이 "Vercel 100/day 한도 위험 감지"였는데, data
  분리 후엔 `main` 저장소 커밋만 보면 충분해짐(그 자체가 유일한 위험 요소이므로). `data`
  저장소 쪽 활동은 참고용으로만 별도 조회하거나, 위험 감지 목적상 제거해도 됨.
- `devpapers` 브랜치도 같은 계열 위험(문서 커밋이 Vercel 카운트에 잡힘)이 있지만 커밋
  빈도가 낮아 당장 급하지 않음. 필요해지면 같은 방식(별도 저장소 분리)으로 대응.

## 참고 — "커밋"과 "푸시"의 본질적 차이 (2026-09-14 세션 Q&A)

Q: 자동화로 트윗이 들어와 `data` 브랜치에 **커밋**하는 것과, 브랜치에 **push**하는 것의
본질적 차이는?

A: **차이 없음.** GitHub Contents API(`gh_store.py`)로 만든 커밋도 브랜치 ref를 즉시
원격에서 갱신하고 그 순간 push 이벤트/웹훅을 발생시킨다 — `git push` CLI로 만든 커밋과
Vercel 입장에서는 완전히 동일하게 보인다("로컬 커밋만 하고 push 안 함" 같은 중간 상태가
API 경로엔 없음). 오늘 소진된 100회 한도는 정확히 이 백엔드 자동 커밋들 때문이었음(Vercel
Preview/ERROR로 잡힌 배포 시도의 sha들이 실제 봇 커밋 sha와 정확히 일치함을 확인).

반면 **프론트가 데이터를 가져오는 경로(GitHub raw CDN 직접 fetch)는 Vercel과 완전히
무관**하다 — Vercel의 배포 파이프라인을 전혀 타지 않는, 순수 HTTP GET이기 때문. 그래서
Vercel 배포가 막혀 있는 동안에도 노노카의 새 트윗이 라이브 사이트에 즉시 반영된 것 —
백엔드 커밋이 Vercel 카운트를 안 먹어서가 아니라, 프론트가 그 카운트와 아예 상관없는
경로로 데이터를 읽기 때문이다.
