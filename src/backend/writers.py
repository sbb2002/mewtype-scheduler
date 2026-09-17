"""(write-queue) GitHub data-branch 쓰기 job 디스패치.

GitHub Contents API 의 PUT 은 파일 단위가 아니라 브랜치 HEAD(ref) 단위로 직렬화된다
(다른 파일에 쓰는 두 요청도 같은 브랜치에 몰리면 서로 409를 유발) — 그래서 콘텐츠를
실제로 바꾸는 쓰기는 전부 이 모듈의 `dispatch()`를 통해 `mewtype-backend`
(`--concurrency=1 --max-instances=1`)의 `POST /write` 위에서만 실행되도록 모은다.
그 서비스는 이미 한 번에 요청 하나만 처리하므로, 이 파일에 등록된 job 은 자동으로
직렬화된다(Cloud Run 이 초과 요청을 자체 버퍼링 — 별도 큐 프로덕트 불필요).

실제 write+DM 로직은 `telegram_app.py`에 원래대로 남아 있다(옮기지 않음 — 4000줄
넘는 파일에서 기능을 뜯어 옮기는 리스크보다, 이미 검증된 함수를 그대로 재사용하는
쪽이 안전하다). 여기서는 지연 import 로 그 함수들을 불러와 kind → 함수로 매핑만 한다.

`telegram_app.py`가 admin_state.json 쓰기(마법사 pending_* bookkeeping)/`control.json`
토글까지 재사용하기 위해 새로 추가한 3개 "최종 커밋" 함수(_undo_restore_commit 등)는
telegram_app.py 안에 그대로 정의돼 있다 — 여기서는 그것도 마찬가지로 지연 import 한다.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from .gh_store import GitHubStore

log = logging.getLogger("backend.writers")


def _registry() -> dict[str, Callable[[GitHubStore, dict], Any]]:
    # 지연 import: telegram_app.py 는 Flask 앱 객체를 모듈 로드 시점에 만드므로,
    # writers.py/app.py 로드 시점이 아니라 실제 dispatch 시점에 가져온다(순환 참조 방지).
    from . import telegram_app as t

    return {
        "merge_rows": lambda gh, a: {
            "changed": t._merge_rows_into_schedule(
                gh, a["rows"], a["now_iso"], a["message"],
                action=a.get("action"),
                merge_fn=(t.xtweet.merge_personal_schedule
                          if a.get("merge_fn") == "personal_schedule" else None),
            )
        },
        "remove_broadcast": lambda gh, a: {
            "removed": t._remove_broadcast(gh, a["snapshot"], a["now_iso"], a["action"])
        },
        "apply_notice": lambda gh, a: dict(zip(
            ("mode", "parsed"),
            t._commit_notice(gh, a.get("prepared"), a["now_iso"]),
        )),
        "notice_sweep": lambda gh, a: {"moved": t._notice_sweep(gh, a["now_iso"])},
        "notice_del_commit": lambda gh, a: t._notice_del_commit(gh, a["nid"], a["now_iso"]),
        "notice_edit_commit": lambda gh, a: t._notice_edit_commit(gh, a["nid"], a["patch"], a["now_iso"]),
        "personal_tweet": lambda gh, a: t._commit_personal_tweet(
            gh, a["prepared"], channel_key=a["channel_key"], now_iso=a["now_iso"],
            via=a.get("via", "ingest"),
        ),
        "tweet_sweep": lambda gh, a: {"moved": t._tweet_sweep(gh, a["now_iso"])},
        "tweet_del_commit": lambda gh, a: t._tweet_del_commit(gh, a["unit"], a["now_iso"]),
        "url_confirmed_commit": lambda gh, a: t._url_confirmed_commit(
            gh, a["video_id"], a["new_item"], a.get("next_check_at"), a["host_key"],
            a["now_iso"], via=a.get("via", "ingest"),
        ),
        "undo_restore": lambda gh, a: t._undo_restore_commit(
            gh, a["path"], a["prev_content"], a["expected_sha"], a["action"], a["now_iso"],
        ),
        "apply_preview_edit": lambda gh, a: {
            "ok": t._apply_preview_edit(gh, a["now_iso"], a["ctx"]) or True
        },
        "ingest_queue_push": lambda gh, a: {
            "ok": t._ingest_queue_push(gh, a["raw"], a["title"], a["now_iso"]) or True
        },
        "ingest_queue_drain": lambda gh, a: dict(zip(
            ("applied", "rows"), t._ingest_queue_drain(gh, a["now_iso"]),
        )),
    }


def dispatch(kind: str, gh: GitHubStore, args: dict) -> dict:
    """kind 에 매핑된 job 함수를 실행하고 JSON 직렬화 가능한 dict 를 반환.

    알 수 없는 kind 는 ValueError. job 함수 자체가 던지는 예외(ConflictError 포함)는
    그대로 전파 — `/write` 라우트가 HTTP 5xx 로 변환해 호출부(writeclient)에 알린다.
    """
    fn = _registry().get(kind)
    if fn is None:
        raise ValueError(f"unknown write job kind: {kind!r}")
    result = fn(gh, args or {})
    return result if isinstance(result, dict) else {"result": result}


if __name__ == "__main__":
    # self-test: registry 에 kind 가 다 있고 알 수 없는 kind 는 명확히 실패하는지만 확인
    # (실제 GitHub 쓰기는 telegram_app.py 쪽 self-test 가 이미 커버).
    reg = _registry()
    expected = {
        "merge_rows", "remove_broadcast", "apply_notice", "notice_sweep",
        "notice_del_commit", "notice_edit_commit", "personal_tweet", "tweet_sweep",
        "tweet_del_commit", "url_confirmed_commit", "undo_restore",
        "apply_preview_edit", "ingest_queue_push", "ingest_queue_drain",
    }
    missing = expected - set(reg)
    assert not missing, f"registry missing kinds: {missing}"
    try:
        dispatch("no-such-kind", None, {})
        raise AssertionError("dispatch should raise on unknown kind")
    except ValueError:
        pass
    print("[PASS] writers registry self-test (WP-3a: apply_notice → _commit_notice)")
