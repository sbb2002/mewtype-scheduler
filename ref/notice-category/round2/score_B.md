# B안 채점 — 36건, 분류 완전 일치 32/36, 합격 FAIL

| 분류 | 정답 수 | TP | FP | FN | TN | precision | recall | accuracy | 기준 | 판정 | 빠뜨림(FN) | 잘못 붙임(FP) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| live | 7 | 6 | 0 | 1 | 29 | 100.0% | 85.7% | 97.2% | 100.0% | FAIL | #50 |  |
| event | 7 | 7 | 0 | 0 | 29 | 100.0% | 100.0% | 100.0% | 95.0% | PASS |  |  |
| goods | 17 | 17 | 1 | 0 | 18 | 94.4% | 100.0% | 97.2% | 95.0% | FAIL |  | #10 |
| broadcast | 14 | 12 | 0 | 2 | 22 | 100.0% | 85.7% | 94.4% | 95.0% | FAIL | #15 #16 |  |
| etc | 3 | 3 | 0 | 0 | 33 | 100.0% | 100.0% | 100.0% | — | (제외) |  |  |

분류 간 혼동표 (행 = 정답, 열 = 판정, 복수 분류라 한 글이 여러 칸에 들어감)

| 정답 \ 판정 | live | event | goods | broadcast | etc |
|---|---|---|---|---|---|
| live | 6 | 0 | 4 | 1 | 0 |
| event | 0 | 7 | 6 | 0 | 0 |
| goods | 3 | 6 | 17 | 0 | 0 |
| broadcast | 0 | 2 | 2 | 12 | 0 |
| etc | 0 | 0 | 0 | 0 | 3 |

틀린 글

- #10 정답 live / 판정 goods+live / related=True — 꿈한대밴드의 라이브 공연 티켓 판매 안내이며, 티켓은 goods이면서 live 이벤트이기도 하다.
- #15 정답 broadcast+event+goods / 판정 event+goods / related=True — 싱글 발매 기념 사인회 개최 안내이며, 싱글은 굿즈이므로 event와 goods 두 카테고리에 포함된다.
- #16 정답 broadcast+event+goods / 판정 event+goods / related=True — 위와 동일하게 싱글 발매 기념 사인회이며, 싱글은 굿즈이므로 event와 goods 모두 해당한다.
- #50 정답 broadcast+live / 판정 broadcast / related=True — YouTubeでの生配信は放送に該当する。
