# AUTOMATE_MANUAL — LlamaLab Automate 수식 작성 참고

운영자 폰(Automate)이 삼성 브라우저 웹푸시 알림을 `mewtype-telegram` 의 공개
`POST /ingest` 로 릴레이한다 (X 예고 릴레이, `docs/plan/v2_3_x_relay.md`).
**그 플로우의 블록 표현식(Expression)을 만들거나 고칠 때 이 문서를 먼저 본다.**

실측 기준: 2026-09-06, 무료 티어. 공식 함수 목록은
<https://llamalab.com/automate/doc/function/index.html>, 블록은
<https://llamalab.com/automate/doc/block/index.html>.

---

## 0. 제약

- **무료 티어 = 플로우당 블록 6개.** 현재 플로우는 시작 블록 포함 6개를 다 씀:
  `@1 Flow beginning` → `@2 Notification posted?` → `@12 Expression true?` →
  `@13 Variable set` → `@6 HTTP request` → `@11 Log`. 새 블록을 넣으려면 뭔가 빼야 한다.
- 동시성 처리(fiber 분기)는 블록을 더 먹고 폰 부하도 커서 안 함. 처리 중 도착한 알림은
  드물게 유실될 수 있고, 그건 텔레그램 `/ingest` 수동 등록으로 보완한다.

## 1. 자주 물리는 함정 (먼저 읽기)

| 흔한 실수 | 실제 | 대안 |
|---|---|---|
| `find(text, sub)` | **`find` 함수 없음** | `contains(text, sub)` — 포함하면 `1`, 아니면 `0` |
| `matches(text, "abc")` 로 부분일치 | `matches` 는 **전체 문자열 일치**(Java `Matcher.matches()`) | 부분일치는 `contains()`. 굳이 정규식이면 `matches(t, "(?s).*abc.*")` |
| `length(text)` | **`length` 함수 없음** | 문자열 길이 함수 없음 — 비었는지만 보면 `trim(x) != ""` |
| `startsWith` / `endsWith` | **둘 다 없음** | `matches(x, "prefix.*")` / `matches(x, "(?s).*suffix")` 또는 `substr` |
| `"a" + "b"` 로 문자열 연결 | 이 빌드에서 문자열 `+` 는 `NaN` (커밋 `1c21d9a` 확인) | **`"a" ++ "b"`** |
| `coalesce(x, y)` 로 "빈 값 건너뛰기" | `coalesce` 는 **첫 non-null**. `""`(빈 문자열)은 non-null → 거기서 멈춤 | `trim(coalesce(x,"")) != "" ? x : y` 삼항으로 직접 |
| `indexOf(text, sub)` 로 문자열 위치 | `indexOf` 는 **배열 전용** | `contains()` 로 존재만 확인 |
| 딕셔너리/헤더 리터럴 `[ ... ]` | 이 빌드는 `[ ]` 저장 거부 | **`{ "k": v, ... }`** 중괄호 |

- 조건 분기 블록 이름은 최신판에서 **`Expression true?`** (구 `Decision`). `False` 출력을
  연결 안 하면 그 지점에서 흐름 종료.
- 표현식은 여러 줄에 걸쳐 써도 된다. 삼항 `조건 ? a : b` 지원, 중첩 가능.

## 2. 쓸 수 있는 함수 (문자열·구조 위주, 공식 목록 발췌)

- 존재/포함: `contains(container, value[, flags])` → 1/0. array·dict·text 공용.
- 정규식: `matches(text, regex)`(전체일치) · `findAll(text, regex)` · `replaceAll(text, regex, repl)` ·
  `split(text, regex)` · `glob(text, pattern)`(`*` 와일드카드)
- 부분 문자열: `substr(text, start[, end])`
- 대소문자·공백: `lowerCase` · `upperCase` · `trim`
- 배열: `join(array, delim)` · `indexOf(array, value)` · `distinct` · `sort` · `slice` · `filter`
- 딕셔너리: `keys` · `values` · `associate` · `extend` · `sift`
- 인코딩: `urlEncode` · `urlDecode` · `base64Encode/Decode` · `hexEncode/Decode` ·
  `jsonEncode/Decode` · `xmlEncode/Decode`
- 값: `coalesce(a, b, …)`(첫 non-null) · `type` · `copy` · `min` · `max`
- 날짜/시간: `time` · `date` · `dateFormat` · `dateParse` · `dateParts` · `localTime` · `utcTime`
- **없는 것**: `find`, `length`, `startsWith`, `endsWith`, `size`, `strlen`

### `urlEncode(dict)` — form-urlencoded 바디

`urlEncode({"text": a, "title": b})` → `text=<enc(a)>&title=<enc(b)>`. 값은 퍼센트
인코딩(일본어 1자 → `%E3%81%82` 등), 키는 ASCII 그대로. `HTTP request` 블록 바디에 그대로.

## 3. `Notification posted?` 블록이 주는 값

| 출력 | 내용 |
|---|---|
| `ntitle` / `nmsg` / `nticker` | 알림 제목 / 메시지 / 티커 (편의 단축값) |
| `nx` | **알림 extras 딕셔너리** — 실제 데이터는 여기 |

`nx` 의 주요 키 (삼성 인터넷 웹푸시, `ref/flow-7 (3).log` 실측):

| 키 | 예시 | 비고 |
|---|---|---|
| `nx["android.text"]` | 트윗 본문 | 미디어 트윗에서도 채워짐. **1순위로 읽기** |
| `nx["android.bigText"]` | 트윗 본문 (확장) | 보통 `android.text` 와 동일. 폴백 |
| `nx["android.textLines"]` | (그룹 요약에서만, 대개 빔) | 안 씀 |
| `nx["android.title"]` | 게시자 **표시 이름** (`夢限大みゅーたいぷ`, `jehy`) | 출처 판별용. **계정 ID 아님** — 이름은 바뀔 수 있음 |
| `nx["android.template"]` | `android.app.Notification$BigTextStyle` | **유형 판별의 핵심** |
| `nx["pde_noti_tag"]` | `p#https://x.com/#1tweet-2096552878769152326` | `tweet-<id>` 는 **트윗 ID**(계정 아님). 중복제거·링크용 |
| `nx["pde_noti_pkg"]` | `com.sec.android.app.sbrowser` | |

### 알림 유형별 필드 (분류 근거)

| 유형 | `android.title` | `android.template` | `pde_noti_tag` |
|---|---|---|---|
| X 원글 / 리포스트 | 계정 표시 이름 | `…$BigTextStyle` | `p#https://x.com/#1tweet-<id>` |
| 그룹 요약(여러 트윗 묶음) | (없음) | `…$InboxStyle` | `p#…#1tweet-<id>` (있음!) |
| 미디어 재생 | `X` | `…$MediaStyle` | null |
| 다운로드 진행/완료 | null | (진행바) | `DownloadNotificationService` |
| 이미지 저장 | `모든 이미지 저장` / `100%` | (없음) | null |

- 리포스트/인용 구분: `android.text` 가 `@<handle>:` 로 시작하거나 `pic.x.com/` 포함.

## 4. 현행 플로우의 확정 표현식

### `@12 Expression true?` — 잡음 게이트

```
contains(coalesce(nx["android.template"], ""), "BigTextStyle") != 0
  && contains(coalesce(nx["pde_noti_tag"], ""), "#1tweet-") != 0
  && trim(coalesce(nx["android.text"], nx["android.bigText"], "")) != ""
```

`BigTextStyle` 검사 하나로 다운로드·그룹요약·미디어재생·이미지저장이 전부 걸러진다.
`#1tweet-` 는 안전빵(삼성 인터넷의 다른 BigTextStyle 알림 대비).

### `@13 Variable set` — 본문 텍스트

- `Variable`: `body`
- `Value`:
  ```
  trim(coalesce(nx["android.text"],"")) != "" ? nx["android.text"] :
  trim(coalesce(nx["android.bigText"],"")) != "" ? nx["android.bigText"] :
  trim(coalesce(nmsg,"")) != "" ? nmsg :
  coalesce(nticker,"")
  ```

### `@6 HTTP request` — 전송

- Method `POST`, URL `<telegram service>/ingest`,
  Content-Type `application/x-www-form-urlencoded`
- Headers (dict): `{"X-Ingest-Secret": "<INGEST_SECRET>"}`
- Request content body:
  ```
  urlEncode({
    "text": body,
    "title": coalesce(nx["android.title"], ""),
    "template": coalesce(nx["android.template"], ""),
    "tag": coalesce(nx["pde_noti_tag"], "")
  })
  ```

백엔드(`telegram_app._ingest`)는 이 4개 폼 필드를 읽고, `tag` 에서
`https://x.com/i/status/<id>` 링크를 만든다. `text` 만 파싱에 쓰고 나머지는 분류·링크용.

## 5. 디버깅

- `@11 Log` 에 `nx` 를 통째로 찍어 두면 새 알림 유형이 왔을 때 필드를 바로 볼 수 있다.
- 백엔드가 `INGEST_ECHO=1` 이면 받은 `text`/`title`/`template`/트윗 링크 + raw body
  디코드본을 운영자 DM 으로 되돌려준다 (파싱·저장 안 함).
- 실배포 전환은 `INGEST_ECHO=0` + `INGEST_DRY_RUN=0` (`docs/plan/v2_4_golive.md`).
