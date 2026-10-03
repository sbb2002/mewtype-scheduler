# 배선 재설계안 (검토용 — 2026-10-02)

> **상태: 제안 — 폰에 적용되지 않음. 10-02 운영자 결정: timeout 1분으로 문제가 해결돼 적용하지 않음(재발 시 재검토).** 현행 배선은 `docs/v4a_automate_wire.md`(10-02 반영본)이고 이 파일은 그것을 건드리지 않는다.
> 아래 「전체 배선」은 현행 배선 전체를 그대로 옮기고, **새로 만들거나 바꿔야 하는 부분만** 위아래를 주석으로 감쌌다.
>
> - `# ▼▼▼ [신규] … ▼▼▼` … `# ▲▲▲ [신규] 끝 ▲▲▲` — 새로 추가하는 블록
> - `# ▼▼▼ [변경] … ▼▼▼` … `# ▲▲▲ [변경] 끝 ▲▲▲` — 현행 블록을 고치는 곳(고친 줄에는 `← 변경` 표시)
> - 표시가 없는 블록은 현행 그대로다.
>
> 새 블록 번호는 `r0 ~ r4` 로 적었다(실제 번호는 운영자가 붙임).

## 왜 다시 설계하나

10-01 폰 로그로 확인된 사실(`ref/v4a/v4a_pending_checks.md` 1-4 · 1-6):

- `[51]` failure catch 의 retry limit 2 는 **재시도를 하지 않는다.** 첫 실패 즉시 ERROR 경로 → `v4a FAIL retry=1` → `Stopped at end`.
  `[47]` 요청 수(41) = 알림 수(41).
- 22:08 접속 실패 원인 = Tailscale 유휴 피어 재연결 지연(약 17초, `v4a_pending_checks.md` 「22:08 접속 실패 원인」).
  `[47]` timeout 을 1분으로 올려 이 경우는 흡수될 것으로 보이나, **그보다 긴 장애는 여전히 유실**(재시도가 없으므로).

그래서 failure catch 의 `retry limit` 에 기대지 않고 **재시도를 블록으로 직접 그린다**
(실패 → 횟수 +1 → 한도 안이면 잠깐 대기 → 다시 전송). failure catch 는 「실패를 잡아 ERROR 경로로 보내는 역할」만 맡긴다.

## 바뀌는 것 요약 (현행 대비)

| # | 변경 | 효과 |
|---|---|---|
| ① | v4a 파이버 맨 앞에 시도 횟수 변수 `v4a_try = 0` (`[r0]`) | 재시도 한도를 우리가 센다 |
| ② | `[51]` retry limit 2 → **0**, ERROR 경로를 「횟수 +1 → 한도 확인 → 대기 → `[51]` 로 되돌아감」 루프로 연결(`[r2]`~`[r4]`) | 접속 실패를 실제로 재시도 (기본 3회 · 간격 20초) |
| ③ | `[47]` 뒤에 HTTP 코드 확인 블록(`[r1]`, 선택) | 서버가 5xx 를 주면 실패로 보고 같은 루프로 |
| ④ | 성공 · 실패 로그(`[52]` · `[54]`)에 `try=` 를 값으로 남김 | 몇 번째 시도에서 성공했는지 폰 로그로 확인 |

운영 파이버(`[49]` → `[40]` → `[50]`/`[53]`)와 알림 받기 · 판정 · `[48]` Fork 구조는 그대로다.
운영 `/ingest` 는 응답이 느려도 서버가 처리를 끝내는 경우가 있어 재시도하면 중복 위험이 있다(아래 「확인이 필요한 것」 2). 그래서 운영은 이번에도 재시도를 넣지 않는다.

---

## 전체 배선

```
[1] flow beginning
    - go to [35]
[35] fork stop with
    - OK route: go to [2]
    - NEW route: go to [43]
[2] when notification
    - go to [42]
    - variables
        <input>
        - package: com.sec.android.app.sbrowser
        <output>
        - posted package: pkg
        - title: ntitle
        - message: nmsg
        - nticker: nticker
        - dictionary of extras: nx
[42] fork stop with
    - OK route : go to [2]
    - NEW route : [45]
[43] when notification
    - go to [44]
    - variables
        <input>
        - package: com.google.android.youtube
        <output>
        - posted package: pkg
        - title: ntitle
        - message: nmsg
        - nticker: nticker
        - dictionary of extras: nx
[44] fork stop with
    - OK route : go to [43]
    - NEW route : [45]
[45] log append
    - go to [46]
    - message: pkg
[46] log append
    - go to [20]
    - message: nx
[20] expression true?
    - formula: `pkg = "com.google.android.youtube" && trim(coalesce(nx["chime.slot_key"], "")) != "" && contains(coalesce(nx["chime.thread_id"], ""), "LIVESTREAM") != 0`
    - YES route: go to [37]
    - NO route: go to [36]
[37] variable set
    - go to [48]
    - variable: body
    - values:
        urlEncode(
            {
                "source": "yt",
                "video_id": nx["chime.slot_key"],
                "title": nx["android.text"],
                "kind": nx["chime.thread_id"],
                "tag": coalesce(nx["pde_noti_tag"], "")
            }
        )

[36] expression true?
    - formula: `pkg = "com.sec.android.app.sbrowser" && contains(coalesce(nx["android.template"], ""), "BigTextStyle") != 0 && contains(coalesce(nx["pde_noti_tag"], ""), "#1tweet-") != 0 && trim(coalesce(nx["android.text"], nx["android.bigText"], "")) != ""`
    - YES route: go to [38]
    - NO route: end
[38] variable set
    - go to [48]
    - variable: body
    - values:
        urlEncode(
            {
                "source": "x",
                "text": coalesce(nx["android.text"], nx["android.bigText"], nmsg, nticker, ""),
                "title": coalesce(nx["android.title"], ""),
                "template": coalesce(nx["android.template"], ""),
                "tag": coalesce(nx["pde_noti_tag"], "")
            }
        )

# 변수 규칙: 새 이름은 그 블록의 <output> 칸에서 처음 선언한다. HTTP 결과는 현행 이름(httpcode · httppresp)을 그대로 쓴다 —
# [48] Fork 뒤 두 파이버는 변수를 각자 복사본으로 가지므로 운영 · v4a 가 같은 이름을 써도 서로 덮지 않는다.

# ▼▼▼ [변경] [48] Fork — NEW route(v4a)의 행선지만 [51] → [r0] ▼▼▼
[48] fork
    - OK route : go to [49]      (이 파이버 = 운영 — 변경 없음)
    - NEW route : go to [r0]     ← 변경: [51] → [r0]  (새 파이버 = v4a — body · nx 는 fork 시점 값이 복사돼 넘어간다)
# ▲▲▲ [변경] 끝 ▲▲▲

# ── 운영 (Cloud Run) — 변경 없음 ──

[49] failure catch
    - OK route : go to [40]
    - ERROR route : go to [53]
    - variables
        <input>
        - retry limit: 0                            (운영은 재시도 안 함 — 아래 「확인이 필요한 것」 2)
        <output>
        - retry count: prod_retry
        - failure block id: prod_fail_block
        - failure type: prod_fail_type
        - failure message: prod_fail_msg
[40] http requests
    - go to [50]
    - variables
        <input>
        - request url: "https://mewtype-telegram-lk3cg7l7ka-an.a.run.app/ingest"
        - request method: POST
        - request content type: WWW form
        - request content body: body
        - request headers:
            {
                "X-ingest-Secret": [INGEST_SECRET]
            }
        - save response: (비움)
        - timeout: 1m
        <output>
        - response status code: httpcode
        - response content or filename: httppresp
[50] log append
    - message: "prod http=" ++ httpcode ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
      (message 칸 수식(fx) 모드)
    - go to end
[53] log append
    - message: "prod FAIL block=" ++ prod_fail_block ++ " " ++ prod_fail_type ++ ": " ++ prod_fail_msg ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end

# ── v4a (로컬 PC, Tailscale) — 재시도 루프 ──

# ▼▼▼ [신규] [r0] 시도 횟수 변수 초기화 ▼▼▼
[r0] variable set
    - go to [51]
    - variable: v4a_try
    - value: 0                                      (숫자. 따옴표 없는 0)
# ▲▲▲ [신규] 끝 ▲▲▲

# ▼▼▼ [변경] [51] failure catch — retry limit 2 → 0, ERROR 행선지 [54] → [r2] ▼▼▼
[51] failure catch
    - OK route : go to [47]
    - ERROR route : go to [r2]                      ← 변경: [54] → [r2]
    - variables
        <input>
        - retry limit: 0                            ← 변경: 2 → 0 (재시도는 아래 루프가 한다)
        <output>
        - retry count: v4a_retry                    (기존 선언 유지 — 항상 0. 로그에는 v4a_try 를 쓴다)
        - failure block id: v4a_fail_block
        - failure type: v4a_fail_type
        - failure message: v4a_fail_msg
# ▲▲▲ [변경] 끝 ▲▲▲

# ▼▼▼ [변경] [47] http requests — 성공 뒤 행선지만 [52] → [r1] (③ 을 안 쓰면 [52] 그대로) ▼▼▼
[47] http requests
    - for v4a test
    - go to [r1]                                    ← 변경: [52] → [r1]
    - variables
        <input>
        - request url: "http://<tailscaleIP>:8787/ingest"   (러너는 TLS 없는 http, 포트 8787)
        - request method: POST
        - request content type: WWW form
        - request content body: body
        - request headers:
            {
                "X-ingest-Secret": [INGEST_SECRET_LOCAL]
            }
        - save response: (비움)
        - timeout: 1m
        <output>
        - response status code: httpcode
        - response content or filename: httppresp
# ▲▲▲ [변경] 끝 ▲▲▲

# ▼▼▼ [신규] [r1] HTTP 5xx 판정 (선택 ③ — 쓰지 않으면 이 블록을 빼고 [47] 의 go to 를 [52] 로) ▼▼▼
[r1] expression true?
    - formula: `httpcode >= 500`
    - YES route: go to [r2]                         (서버 오류 — 실패로 보고 재시도 루프로)
    - NO route: go to [52]
# ▲▲▲ [신규] 끝 ▲▲▲

# ▼▼▼ [변경] [52] 성공 로그 — try 를 값으로 ▼▼▼
[52] log append
    - message: "v4a http=" ++ httpcode ++ " try=" ++ (v4a_try + 1) ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
      ← 변경: 기존 retry=v4a_retry → try=(v4a_try + 1)
    - go to end
# ▲▲▲ [변경] 끝 ▲▲▲

# ▼▼▼ [신규] 실패 시 재시도 루프 [r2] → [r3] → [r4] → [51] (한도 소진 시 [54]) ▼▼▼
[r2] variable set
    - go to [r3]
    - variable: v4a_try
    - value: v4a_try + 1
[r3] expression true?
    - formula: `v4a_try < 3`                        (3 = 최대 시도 횟수. 늘리려면 숫자만 바꾼다)
    - YES route: go to [r4]
    - NO route: go to [54]
[r4] delay
    - go to [51]                                    (재시도 — 다시 failure catch → [47])
    - duration: 20s                                 (Tailscale 재연결이 17초 걸린 전례)
# ▲▲▲ [신규] 끝 ▲▲▲

# ▼▼▼ [변경] [54] 실패 로그 — try · http 를 값으로 ▼▼▼
[54] log append
    - message: "v4a FAIL try=" ++ v4a_try ++ " block=" ++ v4a_fail_block ++ " " ++ v4a_fail_type ++ ": " ++ v4a_fail_msg ++ " http=" ++ coalesce(httpcode, "-") ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
      ← 변경: 기존 retry=v4a_retry → try=v4a_try, http= 추가
    - go to end
# ▲▲▲ [변경] 끝 ▲▲▲


## disconnected(deprecated)
[41] log append                                     ← 삭제 후보: [50] · [52] 으로 대체
                                                       (nx 전체 덤프가 필요하면 [46] 이 이미 남긴다)
```

### 동작 시나리오

| 상황 | 경로 | 폰 로그 |
|---|---|---|
| 정상 | r0 → 51 → 47 → r1(NO) → 52 | `v4a http=200 try=1` |
| 첫 시도 연결 실패, 2번째 성공 | … 47 실패 → 51(ERROR) → r2(try=1) → r3(YES) → r4(20초) → 51 → 47 → r1 → 52 | `v4a http=200 try=2` |
| 3회 모두 실패 | … r2(try=3) → r3(NO) → 54 | `v4a FAIL try=3 block=47 …` |
| 서버 5xx | 47 → r1(YES) → r2 … 같은 루프 | 성공 시 `try=n`, 한도 소진 시 `v4a FAIL try=3 … http=500` |

최대 소요: 시도 3회 × timeout 1분 + 대기 20초 × 2 = 이론상 약 3분 40초(접속이 아예 안 될 때는 시도마다 1분을 다 쓴다).

---

## 확인이 필요한 것 (추측으로 채우지 않은 부분)

1. **failure catch 를 루프로 다시 들어가도 되는지.** `[r4]` 가 `[51]` 로 되돌아가 다시 실패를 잡는 구조다. 10-01 로그로 아는 것은
   「`[51]` 이 첫 실패를 잡아 ERROR 경로로 보낸다」까지다. 되돌아갔을 때 두 번째 실패도 정상적으로 잡히는지는 **모른다**.
   시험: 러너를 끈 상태에서 알림 1건 → 약 3분 뒤 `v4a FAIL try=3 …` 1줄. 이때 `[47]` 요청이 폰 로그에 3번 보여야 한다.
   두 번째 실패부터 잡히지 않고 파이버가 죽으면 구조를 고쳐야 한다(예: 루프마다 새 failure catch 를 거치게).
2. **재시도 중복.** 요청이 서버에 도착해 처리가 끝났는데 응답만 timeout 으로 놓친 경우(예: 처리 1분 초과)에는 같은 알림이 두 번 들어간다.
   - 트윗은 같은 id 면 `merge_thread`/`merge_tweet` 가 덮어쓰는 구조로 알고 있어 대체로 무해하지만, **v4a `/ingest` 전체 경로에서 중복 인입이 안전한지는 이 안을 쓰기 전에 코드로 확인해야 한다**
     (소식 · 공식 일정 · 예고 DM 이 두 번 나갈 수 있음).
   - 한도(3회)와 대기(20초)는 운영자 판단.
3. **`httpcode` 가 연결 실패 때 비어 있는지.** `[54]` 의 `coalesce(httpcode, "-")` 는 변수가 아예 선언되지 않았거나 비었을 때를 가정했다.
   이전 시도의 값이 남아 있으면 오해를 부를 수 있다(로그 표시만의 문제).
4. **`[r4]` 이름.** Automate 의 대기 블록 이름 · 칸 이름(`Delay` · `duration`)은 폰 앱에서 확인해 맞출 것.
5. **`[r1]`(HTTP 5xx 판정)은 선택.** 5xx 는 서버가 일부 처리한 뒤 낸 것일 수 있어 2 의 중복 위험과 겹친다. 불안하면 `[47]` 의 `go to` 를 `[52]` 로 두고 `[r1]` 을 생략한다.

## 이 안으로도 못 막는 것

- 한도(약 3분 40초)를 넘기는 장기 장애 — PC 꺼짐 · Tailscale 끊김이 길 때. 이 경우는 `v4a FAIL` 로그에 남기만 하고,
  원문은 폰 알림에만 있어 PC 쪽에서 복구할 방법이 없다. 방어하려면 PC 쪽 복구 경로가 따로 필요 — 이 안의 범위 밖.
- 유휴 후 첫 요청의 재연결 지연은 재시도 없이도 timeout 1분이 흡수한다. 더 확실히 하려면 PC 에서 8분 미만 간격으로 `tailscale ping 100.82.203.42` 를 돌려 피어를 데워 둔다(선택, 운영자 결정).
