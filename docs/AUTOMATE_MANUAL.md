# AUTOMATE_MANUAL — LlamaLab Automate 수식 작성 참고

운영자 폰(Automate)이 푸시알림을 `mewtype-telegram` 의 공개 `POST /ingest` 로 릴레이한다.
현재 배포판은 삼성 브라우저 웹푸시(X) 알림만 받는다 (X 예고 릴레이, `docs/old/v2/v2_3_x_relay.md`).
**v3 목표는 YouTube 앱 알림도 함께 받는 2소스 분기 플로우** (§4b, `docs/plan/v3_backend_surgery.md`).
**그 플로우의 블록·표현식(Expression)을 만들거나 고칠 때 이 문서를 먼저 본다.**

실측 기준: 삼성 웹푸시 `ref/flow-7 (3).log` (2026-09-06), YouTube 알림 `ref/flow-7 (4).log`
(2026-09-08), 무료 티어 한도 정정 2026-09-09. 공식 함수 목록은
<https://llamalab.com/automate/doc/function/index.html>, 블록은
<https://llamalab.com/automate/doc/block/index.html>.

---

## 0. 제약

- **무료 티어 = 실행 중(running) 블록 총 30개.** "플로우당" 이 아니라 **동시에 돌아가는 모든
  플로우 합산**이다 (1플로우×30, 15플로우×2, 아무 조합). 실행 중 플로우 안의 **미연결 블록도
  카운트**. 정지된 플로우는 개수 제한 없음. 30 초과 시 추가 블록이 실행 안 됨(플로우 start 실패).
  출처: <https://llamalab.com/automate/doc/premium.html>.
  (구 메모의 "플로우당 6개" 는 오기 — 2026-09-09 정정. 실제로 10블록 넘겨도 돌아간다.)
- 현행 X 릴레이는 ~6블록, v3 2소스 플로우도 ~10블록이라 30 한도에 여유가 크다. 다른 개인
  자동화 플로우와 30을 공유한다는 점만 주의(실행 중 플로우에 스크래치 블록 남기지 말 것).
- **`Notification posted?` 는 `proceed = When transition` 에서 알림 1건당 fiber 1개만
  통과시키고 스스로 재무장하지 않는다.** 반드시 마지막에 `@2` 로 되돌리는 arrow 가 있어야
  계속 듣는다 (NO=알림 제거 경로도 `@2` 로). 처리 중(HTTP ~2s) 도착분 유실을 막으려면
  `@2` YES 직후 `Fork` — 한 갈래는 즉시 `@2` 로 복귀(재무장), 다른 갈래가 게이트→전송→로그.
  블록 여유가 있으니 v3 플로우는 Fork 를 쓴다 (§4b).

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

- 조건 분기 블록 이름은 최신판에서 **`Expression true?`** (구 `Decision`). 출력을 연결 안 하면
  그 **fiber** 가 끝난다 — Fork 로 리스너를 따로 살려 두면(§4b) worker fiber 의 미연결 종료는
  무해하지만, 리스너 fiber 의 경로는 반드시 `@2` 로 돌아와야 한다.
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

## 3-1. YouTube 앱 알림 `nx` (`ref/flow-7 (4).log` 실측)

패키지 `com.google.android.youtube`. **삼성 웹푸시와 키 세트가 완전히 다르다** (`chime.*` 계열).
SUMMARY 더미 + 실항목이 **쌍으로** 온다 — `chime.slot_key` 유무로 실항목만 통과시키면 됨.

| 키 | 예시 | 비고 |
|---|---|---|
| `nx["chime.slot_key"]` | `bgzve7Y7S50` | **video_id 온전한 11자.** YT 알림을 쓰는 이유 전부. SUMMARY 더미엔 없음 |
| `nx["chime.thread_id"]` | `a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:536ba428805e0000` | 종류. `LIVESTREAM_TUNEIN`(예정−30분) / `LIVESTREAM_REMINDER`(예약분 시작) / `SUBSCRIPTION_LIVESTREAM_START`(구독 채널 시작). 셋 다 `LIVESTREAM` 포함 |
| `nx["android.text"]` | `【チラズアート新作「雪葬」＃2】…【峰月律/ゆめみた】` | **방송 제목 풀텍스트. 1순위** |
| `nx["android.title"]` | `🔴 30분 후에 峰月律… 실시간 스트림 시청하기` | **잘림·장식 — 쓰지 말 것** |
| `nx["android.template"]` | `…$BigPictureStyle`(TUNEIN·START) / `…$BigTextStyle`(REMINDER) | 삼성과 달리 유형 판별엔 `chime.thread_id` 를 씀 |
| `nx["pde_noti_tag"]` | 실항목 `bgzve7Y7S50::<uuid>` / 더미 `1611430723::SUMMARY::<n>` | `::SUMMARY::` 면 버림 |
| `nx["pde_noti_pkg"]` | `com.google.android.youtube` | `@2` 의 `Package` 출력과 동일값 |
| `nx["android.subText"]` | `null` (X 웹푸시는 `x.com`) | 소스 구분 보조 |
| `nx["chime.account_name_hash"]` | `1611430723` (int) | **운영자 단일 계정** — 개인/공식 채널 구분 불가 |
| 이미지 | `android.largeIcon` · `android.pictureIcon` = `null` | 비트맵 제거됨. 썸네일은 `i.ytimg.com/vi/<id>/mqdefault.jpg` 조립 |

## 4. 플로우 구조

### 4a. 현행 배포판 (X 단일 소스, v2.3~) — 확정 표현식

`@1 Flow beginning` → `@2 Notification posted?` → `@12 Expression true?` →
`@13 Variable set` → `@6 HTTP request` → `@11 Log`. (`@11` 은 `@2` 로 되돌아옴.)

#### `@12 Expression true?` — 잡음 게이트

```
contains(coalesce(nx["android.template"], ""), "BigTextStyle") != 0
  && contains(coalesce(nx["pde_noti_tag"], ""), "#1tweet-") != 0
  && trim(coalesce(nx["android.text"], nx["android.bigText"], "")) != ""
```

`BigTextStyle` 검사 하나로 다운로드·그룹요약·미디어재생·이미지저장이 전부 걸러진다.
`#1tweet-` 는 안전빵(삼성 인터넷의 다른 BigTextStyle 알림 대비).

#### `@13 Variable set` — 본문 텍스트

- `Variable`: `body`
- `Value`:
  ```
  trim(coalesce(nx["android.text"],"")) != "" ? nx["android.text"] :
  trim(coalesce(nx["android.bigText"],"")) != "" ? nx["android.bigText"] :
  trim(coalesce(nmsg,"")) != "" ? nmsg :
  coalesce(nticker,"")
  ```

#### `@6 HTTP request` — 전송

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

### 4b. X + YouTube 2소스 분기 (폰 Automate 에 구성 완료 — 2026-09-09)

블록 수 걱정이 사라졌으니(§0), 단일 fiber 루프 대신 **Fork 로 리스너와 처리를 분리**한다.
9블록, 30 한도 내. 폰 플로우에 아래대로 입력해 뒀다(백엔드 `/ingest` 의 `source` 분기
처리는 v3 착수 시 — 그 전까지는 기존 X 경로만 반응, YT 페이로드는 `source:"yt"` 로 와서
미처리 로그만 남음).

```
@1  Flow beginning
@2  Notification posted?            proceed = When transition,  Package = any
      ├ YES → @3
      └ NO  → @2                    (알림 제거 이벤트 — 무시하고 재대기)
@3  Fork                           "Stop with parent" = ON
      ├ OK  → @2                    (부모 fiber = 리스너, 즉시 재무장 — 버스트 유실 방지)
      └ new → @4                    (자식 fiber = 일회용 worker)
@4  Expression true?  [YT 게이트]    ├ YES → @6   └ NO → @5
@5  Expression true?  [X 게이트]     ├ YES → @7   └ NO → (미연결; worker fiber 종료)
@6  Variable set  body = «YT 페이로드»   → @8
@7  Variable set  body = «X 페이로드»    → @8
@8  HTTP request  POST <telegram>/ingest  · Request content = body · out: status  ├ 응답 → @9   └ 실패 → @9
@9  Log append   message = pkg ++ http=status ++ id ++ 본문80자   → (미연결; worker fiber 종료)
```

- `Fork` 출력은 `OK`(원래=부모 fiber) + `new`(새 자식 fiber). 둘 다 즉시 병렬 진행하고
  자식은 변수 상태를 복제한다(그 시점 `nx`·`Package` 가 worker 쪽에 고정 — 새 알림이 와도
  안 덮임). `OK → @2` 로 리스너를 계속 살리고 `new → @4` 로 처리를 일회용 fiber 에 넘긴다.
  `Stop with parent = ON` 이라야 플로우 정지 시 in-flight worker 도 정리된다.
- `@2` 는 `When transition` — 알림 1건당 fiber 1개, 스스로 재무장 안 함. `OK → @2` 루프가
  그 역할. Fork 가 없으면 `@8`(~2s) 도는 동안 온 알림을 놓친다.
- `@4`/`@5` 의 NO, `@9` 뒤는 **연결 안 해도 됨** — 리스너는 `OK` 갈래로 이미 살아있고 worker
  fiber 만 끝난다. `@2` 의 NO(알림 제거)만은 반드시 `@2` 로.
- `Package` 는 `@2` 출력 변수. `nx["pde_noti_pkg"]` 와 동일.
- 배열 리터럴(`contains([...], pkg)`)을 피하려고 게이트는 `Package == "..."` 등가비교를 쓴다
  (§1 의 `[ ]` 저장 이슈 회피).

#### `@4 Expression true?` — YouTube 게이트

```
Package == "com.google.android.youtube"
  && trim(coalesce(nx["chime.slot_key"], "")) != ""
  && contains(coalesce(nx["chime.thread_id"], ""), "LIVESTREAM") != 0
```

`chime.slot_key` 유무 하나로 SUMMARY 더미·댓글·업로드 알림이 전부 탈락한다.

#### `@5 Expression true?` — X 게이트 (§4a 게이트에 Package 조건만 추가)

```
Package == "com.sec.android.app.sbrowser"
  && contains(coalesce(nx["android.template"], ""), "BigTextStyle") != 0
  && contains(coalesce(nx["pde_noti_tag"], ""), "#1tweet-") != 0
  && trim(coalesce(nx["android.text"], nx["android.bigText"], "")) != ""
```

> **입력 시 주의** — Automate 표현식 필드는 정렬용 공백·줄바꿈을 넣어도 되지만, 전각
> `：` `，` `"` 가 섞이면 `Expected ':' but found ','` 로 튕긴다. 반각으로만. 아래 두
> 페이로드는 한 줄로 붙여넣는 형태로 적어 둔다.

#### `@6 Variable set` — YT 페이로드

`chime.slot_key` 가 온전한 video_id 라 잘린 URL 복원이 불필요.

```
urlEncode({"source": "yt", "video_id": nx["chime.slot_key"], "title": nx["android.text"], "kind": nx["chime.thread_id"], "tag": coalesce(nx["pde_noti_tag"], "")})
```

`kind` 예: `a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:536ba428…` → 백엔드가 가운데 토큰
(`LIVESTREAM_TUNEIN` / `LIVESTREAM_REMINDER` / `SUBSCRIPTION_LIVESTREAM_START`)만 파싱.

#### `@7 Variable set` — X 페이로드 (§4a 와 동일 + `source`)

```
urlEncode({"source": "x", "text": coalesce(nx["android.text"], nx["android.bigText"], nmsg, nticker, ""), "title": coalesce(nx["android.title"], ""), "template": coalesce(nx["android.template"], ""), "tag": coalesce(nx["pde_noti_tag"], "")})
```

`text` 는 §4a 의 3중 삼항 대신 `coalesce` 로 축약했다 — `@5` 게이트가 이미
`trim(coalesce(android.text, android.bigText, "")) != ""` 를 통과시키므로, 여기 도달 시
`android.text` 는 비어 있지 않거나(대개) `null`+`bigText` 존재뿐이라 `coalesce` 로 충분.
(`coalesce` 는 첫 non-null 반환이고 `""` 는 non-null 이지만, `android.text == ""` 케이스는
게이트에서 걸러진다.)

#### `@8 HTTP request` — 공통

| 필드 | 값 |
|---|---|
| Request method | `POST` |
| Request URL | `<SERVICE_URL>/ingest` (배포 `mewtype-telegram` URL) |
| Request headers | `{"X-Ingest-Secret": "<INGEST_SECRET>"}` |
| Request content type | `application/x-www-form-urlencoded` |
| Request content | `body` |

`@6`/`@7` 이 `body` 에 완성된 폼 문자열(`urlEncode` 결과 = `k=v&k=v`)을 넣어 놨으므로
Request content 는 `body` 한 단어. 헤더에 `Content-Type` 을 또 넣지 않는다(전용 필드가 있음).
출력(`Response status code` 등)은 `@9 Log append` 로.

백엔드 `_ingest` 는 `source` 로 먼저 갈래를 나눈다. `source` 없으면 `"x"` 로 간주(전환기
호환). `yt` 면 `video_id` 로 정규 파이프라인(`videos.list`/reconcile) 진입.

`@6`/`@7` 없이 `@8` 한 블록에 인라인하려면 Request content 에 직접 분기(길어서 비권장):

```
nx["pde_noti_pkg"] == "com.google.android.youtube" ? urlEncode({"source": "yt", "video_id": nx["chime.slot_key"], "title": nx["android.text"], "kind": nx["chime.thread_id"], "tag": coalesce(nx["pde_noti_tag"], "")}) : urlEncode({"source": "x", "text": coalesce(nx["android.text"], nx["android.bigText"], nmsg, nticker, ""), "title": coalesce(nx["android.title"], ""), "template": coalesce(nx["android.template"], ""), "tag": coalesce(nx["pde_noti_tag"], "")})
```

#### `@9 Log append` — message

Automate 가 앞에 `날짜 시각 블록id` 를 자동으로 붙이므로 message 는 소스·HTTP 결과·식별자·
본문 앞부분만. 문자열 연결은 `++` (`+` 는 NaN).

```
coalesce(nx["pde_noti_pkg"], "?") ++ " http=" ++ coalesce(status, "?") ++ " id=" ++ coalesce(nx["chime.slot_key"], nx["pde_noti_tag"], "-") ++ " | " ++ substr(coalesce(nx["android.text"], nmsg, nticker, ""), 0, 80)
```

`status` = `@8` 의 Response status code 출력 변수. 출력 예:
`… U 68@9: com.google.android.youtube http=200 id=bgzve7Y7S50 | 【チラズアート…【峰月律/ゆめみた】`

#### 안 하는 것 / 폰 쪽 선행조건

- **개인/공식 채널 구분은 폰에서 안 함.** `chime.account_name_hash` 는 운영자 단일 계정이라
  소속 불가. video_id 만 넘기면 백엔드가 `videos.list` 로 채널을 확정한다.
- InboxStyle 그룹 요약(2+ 트윗 묶임)은 X 게이트에서 탈락. 근본 해결은 **삼성 인터넷 알림
  채널의 그룹화 끄기**(폰 설정) — 그래야 트윗마다 개별 BigTextStyle 이 뜬다. 벌충안: vxtwitter
  unfurl 도입 후(`docs/plan/v3_backend_surgery.md` §2) `pde_noti_tag` 의 트윗 id 하나만
  릴레이하는 InboxStyle 폴백 분기를 추가할 수 있다(id 는 묶음 중 최신 1건뿐).

## 5. 디버깅

- `Log append` 블록에 `nx` 를 통째로 찍어 두면 새 알림 유형이 왔을 때 필드를 바로 볼 수 있다
  (`ref/flow-7 (3).log` = 삼성 웹푸시, `ref/flow-7 (4).log` = YouTube 알림이 그렇게 수집됨).
- 백엔드가 `INGEST_ECHO=1` 이면 받은 폼 필드 + raw body 디코드본을 운영자 DM 으로 되돌려준다
  (파싱·저장 안 함). v3 2소스에선 `source` 필드로 X/YT 구분을 먼저 확인.
- 실배포 전환은 `INGEST_ECHO=0` + `INGEST_DRY_RUN=0` (`docs/old/v2/v2_4_golive.md`).
