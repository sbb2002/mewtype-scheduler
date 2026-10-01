# 배선 (수정안 — 2026-10-01)

> **10-01 폰에 적용됨** — 현행 배선은 `docs/v4a_automate_wire.md`. 실제 번호: idx1→`[48]` · idx2→`[49]` · idx3→`[50]` · idx4→`[53]` ·
> idx5→`[51]` · idx6→`[52]` · idx7→`[54]`. 이 파일은 설계 근거 기록으로 남긴다. 아래 「확인이 필요한 것」은 적용 후 첫 폰 로그로 확인.

현행 `docs/v4a_automate_wire.md` 기준 수정안. 새 블록은 `idx1, idx2, …` 로 적었다(실제 번호는 운영자가 붙임).
근거: 폰 Automate 로그 `ref/flow-11_261001.log` 대조 — `ref/v4a/v4a_remaining_0930.md` §3-2.

## 바뀌는 것 요약

| # | 변경 | 막는 실패 |
|---|---|---|
| ① | `[40]` 응답을 파일로 저장하지 않음(「Save response」 비움 → 변수로만) | 동시 파이버끼리 `Download/Automate/ingest` 파일 충돌 (`FileSystemException: Failed to delete file`) |
| ② | body 를 만든 뒤 `[idx1]` Fork — 운영 `[40]` 과 v4a `[47]` 을 **서로 다른 파이버**로 | `[40]` 실패(`Software caused connection abort` · 파일 충돌)가 `[47]` 을 막음 · v4a 도착이 운영 응답(6~34초)만큼 늦어짐 |
| ③ | `[47]` 앞에 failure catch(retry limit 2 = 최대 3회 시도) | 폰 → PC 접속 실패(`failed to connect … after 10000ms`)가 한 번이면 그대로 유실 |
| ④ | `[40]` · `[47]` 결과(성공 코드 · 실패 블록 · 종류 · 메시지)를 각각 로그 — 변수는 현행 `httpcode` 와 failure catch 출력으로 새로 선언한 것만 씀 | 다음 누락 때 어느 쪽에서 왜 멈췄는지 바로 보이게 |
| ⑤ | `[38]` 수식 정리 — 끝 괄호 1개 제거 · `template` 키를 `android.template` 로 | (문서상 오타 — 실제 폰 설정과 다르면 무시) |

`[1]` ~ `[36]` · `[37]` · `[42]` ~ `[46]` (알림 받기 · 판정) 은 그대로.

---

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
    - go to [idx1]                                  ← 변경: [40] → [idx1]
    - variable: body
    - values:
        ```
        urlEncode(
            {
                "source": "yt",
                "video_id": nx["chime.slot_key"],
                "title": nx["android.text"],
                "kind": nx["chime.thread_id"],
                "tag": coalesce(nx["pde_noti_tag"], "")
            }
        )
        ```

[36] expression true?
    - formula: `pkg = "com.sec.android.app.sbrowser" && contains(coalesce(nx["android.template"], ""), "BigTextStyle") != 0 && contains(coalesce(nx["pde_noti_tag"], ""), "#1tweet-") != 0 && trim(coalesce(nx["android.text"], nx["android.bigText"], "")) != ""`
    - YES route: go to [38]
    - NO route: end
[38] variable set
    - go to [idx1]                                  ← 변경: [40] → [idx1]
    - variable: body
    - values:                                       ← 변경: template 키 · 끝 괄호
        ```
        urlEncode(
            {
                "source": "x",
                "text": coalesce(nx["android.text"], nx["android.bigText"], nmsg, nticker, ""),
                "title": coalesce(nx["android.title"], ""),
                "template": coalesce(nx["android.template"], ""),
                "tag": coalesce(nx["pde_noti_tag"], "")
            }
        )
        ```

# ── 여기부터 변경 ─────────────────────────────────────────────
# 변수 규칙: 새 이름은 그 블록의 <output> 칸에서 처음 선언한다. HTTP 결과는 현행 이름(httpcode · httppresp)을 그대로 쓴다 —
# [idx1] Fork 뒤 두 파이버는 변수를 각자 복사본으로 가지므로 운영 · v4a 가 같은 이름을 써도 서로 덮지 않는다.

[idx1] fork                                         ← 신규: 운영 · v4a 를 다른 파이버로
    - OK route : go to [idx2]      (이 파이버 = 운영)
    - NEW route : go to [idx5]     (새 파이버 = v4a — body · nx 는 fork 시점 값이 복사돼 넘어간다)

# ── 운영 (Cloud Run) ──

[idx2] failure catch                                ← 신규
    - OK route : go to [40]
    - ERROR route : go to [idx4]
    - variables
        <input>
        - retry limit: 0                            (운영은 재시도 안 함 — 아래 「확인이 필요한 것」 참고)
        <output>
        - retry count: prod_retry                   (신규 선언)
        - failure block id: prod_fail_block         (신규 선언)
        - failure type: prod_fail_type              (신규 선언)
        - failure message: prod_fail_msg            (신규 선언)
[40] http requests
    - go to [idx3]                                  ← 변경: [47] → [idx3]
    - variables
        <input>
        - request url: "https://mewtype-telegram-lk3cg7l7ka-an.a.run.app/ingest"
        - request method: POST
        - request content type: WWW form
        - request content body: body
        - request headers: ```
            {
                "X-ingest-Secret": [INGEST_SECRET]
            }
            ```
        - save response: (비움)                     ← 변경: 파일 `ingest` 저장 해제 — 동시 파이버 파일 충돌 원인
        - timeout: 10s                              (접속 제한 시간 — 응답 대기는 아님)
        <output>
        - response status code: httpcode            (현행 그대로)
        - response content or filename: httppresp   (현행 그대로 — 파일 저장을 끄면 내용이 들어온다)
[idx3] log append                                   ← 신규
    - message: "prod http=" ++ httpcode ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end
[idx4] log append                                   ← 신규: 운영 전송 실패
    - message: "prod FAIL block=" ++ prod_fail_block ++ " " ++ prod_fail_type ++ ": " ++ prod_fail_msg ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end

# ── v4a (로컬 PC, Tailscale) ──

[idx5] failure catch                                ← 신규 (재시도는 이 블록의 retry limit 으로 — 별도 반복 블록 없음)
    - OK route : go to [47]
    - ERROR route : go to [idx7]
    - variables
        <input>
        - retry limit: 2                            (실패한 블록을 2번 더 시도 = 최대 3회. 1회 접속 대기 10초)
        <output>
        - retry count: v4a_retry                    (신규 선언)
        - failure block id: v4a_fail_block          (신규 선언)
        - failure type: v4a_fail_type               (신규 선언)
        - failure message: v4a_fail_msg             (신규 선언)
[47] http requests
    - for v4a test
    - go to [idx6]                                  ← 변경: [41] → [idx6]
    - variables
        <input>
        - request url: "http://<tailscaleIP>:8787/ingest"   ← 확인: 러너는 TLS 없는 http, 포트 8787 (현행 문서 표기는 https · 포트 없음)
        - request method: POST
        - request content type: WWW form
        - request content body: body
        - request headers: ```
            {
                "X-ingest-Secret": [INGEST_SECRET_LOCAL]
            }
            ```
        - save response: (비움)
        - timeout: 10s
        <output>
        - response status code: httpcode            (현행 그대로)
        - response content or filename: httppresp   (현행 그대로)
[idx6] log append                                   ← 신규 ([41] 대체 — nx 전체 대신 결과만)
    - message: "v4a http=" ++ httpcode ++ " retry=" ++ v4a_retry ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end
[idx7] log append                                   ← 신규: v4a 전송 실패(재시도까지 모두 실패)
    - message: "v4a FAIL retry=" ++ v4a_retry ++ " block=" ++ v4a_fail_block ++ " " ++ v4a_fail_type ++ ": " ++ v4a_fail_msg ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end

[41] log append                                     ← 삭제 후보: [idx3] · [idx6] 으로 대체
                                                       (nx 전체 덤프가 필요하면 [46] 이 이미 남긴다)
```

---

## 확인이 필요한 것 (작성자가 추측으로 채우지 않은 부분)

- **failure catch 의 retry limit 동작** — 「실패한 블록을 retry limit 만큼 다시 시도하고, 그래도 실패하면 ERROR 경로」로 가정했다.
  재시도 사이에 대기가 있는지는 모른다(접속 실패는 1회에 10초가 걸려서 대기가 없어도 시도 간격은 10초).
  시험 권장: 러너를 끈 상태에서 알림 1건 → 약 30초 뒤 로그에 `v4a FAIL retry=2 …` 1줄이 남는지.
  retry limit 이 「ERROR 경로를 탄 뒤 되돌아오는 횟수」 같은 다른 뜻이면 `[idx5]` 를 다시 그려야 한다.
- **운영 `[idx2]` retry limit 0** — 운영 `[40]` 실패(연결 끊김 · 파일 충돌)는 서버가 이미 요청을 받아 처리한 뒤 폰 쪽에서만 끊긴 경우였다
  (Cloud Run 로그상 200). 재시도하면 같은 알림이 운영에 두 번 들어가므로 0 으로 뒀다 — 운영 데이터는 중복되지 않지만 공식 스케줄 요약 DM 은 다시 나간다.
- **`[47]` 주소** — 현행 문서는 `https://<tailscaleIP>/ingest` 인데 러너는 `http://100.79.146.124:8787` 로 떠 있다
  (`_local/ops/runner.json`). 실제 폰 설정 값으로 맞출 것.
- **Fork 의 OK/NEW** — 현행 `[35]` · `[42]` 와 같은 뜻(OK = 이 파이버가 계속, NEW = 새 파이버)으로 썼다.
- **v4a 재시도의 부작용** — 재시도는 접속 실패(요청이 서버에 닿기 전)를 겨냥한 것이다. v4a 가 요청을 이미 처리했는데 응답만 늦어
  실패로 잡히면 같은 알림이 다시 들어간다 — 소식(이미 본 글) · 개인 트윗(같은 내용이면 그대로) · 공식 스케줄(같은 행 다시 머지)은
  **데이터가 중복되지는 않지만**, 공식 스케줄 요약 DM 은 바뀐 게 없어도 다시 나간다(`telegram_app._ingest_impl` 이 요약 DM 을 조건 없이 보냄).
  지금까지 `[47]` 의 실패는 전부 접속 실패라 이 경우는 드물다.
