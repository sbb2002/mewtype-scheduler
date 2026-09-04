# 夢限大みゅーたいぷ 방송 예고판

> **프로젝트:** 夢限大みゅーたいぷ 5인 유튜브 방송인의 예약/라이브 방송을 한곳에서 시간순으로 보여주는 정적 웹사이트

📋 [PRD](./docs/beta_version/PRD.md) | 📦 [구현 명세](./docs/SPEC.md)

---

## 구조

```
mewtype-scheduler/
├── src/
│   ├── frontend/               # Vercel 정적 호스팅
│   │   ├── index.html
│   │   ├── css/
│   │   └── js/
│   └── collector/              # 데이터 수집 (Python)
│       ├── main.py
│       ├── rss.py
│       ├── youtube.py
│       ├── reconcile.py
│       ├── store.py
│       └── requirements.txt
├── config/
│   └── channels.json           # 5채널 메타데이터
├── .github/workflows/
│   └── collect.yml             # 매시간 수집 자동화
└── data 브랜치                  # schedule.json + archive.json (GitHub Actions가 생성)
```

---

## 동작 방식

1. **GitHub Actions**가 매시간(UTC 0분) cron으로 실행되거나 수동 트리거 시 호출
2. **수집기**(Python)가 YouTube RSS 피드 + YouTube Data API v3로 5채널의 예약/라이브 상태 조회
3. 데이터가 변경되면 `data` 브랜치에 `schedule.json` + `archive.json`으로 커밋
4. **프론트엔드**는 `raw.githubusercontent.com`에서 `schedule.json`을 매 60~90초마다 fetch해 화면에 렌더

---

## 로컬 실행

### 수집기 (Bash/PowerShell)

```bash
# Linux/macOS
pip install -r src/collector/requirements.txt
DATA_DIR=./_data YOUTUBE_API_KEY=xxxx python -m src.collector.main light
```

```powershell
# PowerShell
pip install -r src/collector/requirements.txt
$env:DATA_DIR = "./_data"; $env:YOUTUBE_API_KEY = "xxxx"; python -m src.collector.main light
```

이 명령은 `_data/schedule.json`과 `_data/archive.json`을 생성합니다.

### 프론트엔드

정적 서버는 **저장소 루트**에서 실행합니다 (fixture 상대경로 `../../fixtures/...`가 서버 루트 밖으로 나가지 않도록):

```bash
python -m http.server 8099
# 브라우저에서 http://localhost:8099/src/frontend/ 접속
```

**개발 중**: `src/frontend/js/config.js`의 `DATA_URL`을 `../../fixtures/schedule.sample.json`로 임시 변경해 테스트 데이터로 확인할 수 있습니다.

---

## 배포

### Vercel (프론트엔드)

1. GitHub 저장소를 Vercel에 연결
2. **Root Directory**: `src/frontend`
3. **Build Command**: (없음 — 정적 HTML/CSS/JS)
4. 배포 완료

### data 브랜치 최초 부트스트랩

첫 워크플로 실행 전에 `data` 브랜치를 미리 생성하려면:

```bash
git switch --orphan data
git commit --allow-empty -m "init data"
git push -u origin data
git switch main
```

워크플로가 실행되면서 자동으로 생성되므로 선택사항입니다.

---

## 설정

### GitHub Secrets

저장소 Settings → Secrets and variables → Actions 에서 다음 설정:

| 이름 | 값 |
|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API v3 키 |

워크플로가 매시간 이 키로 YouTube API를 호출해 방송 정보를 수집합니다.

---

## 파일 설명

- `config/channels.json`: 모니터링할 5개 채널의 메타데이터 (유튜브 핸들, 채널 ID, 한글명 등)
- `src/collector/requirements.txt`: Python 의존성 (`requests>=2.31` 만 사용)
- `.github/workflows/collect.yml`: 매시간 수집 + `data` 브랜치 커밋 자동화
- `fixtures/`: 개발/테스트용 샘플 데이터

---

## 라이센스

공개 메타데이터 활용. YouTube 썸네일은 `i.ytimg.com` 핫링크 사용.
