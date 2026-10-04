"""(v4a) 가공 큐 — 번역 재시도(needs_tl)를 쓰기 경로 밖에서.

v4a 설계 §7 "번역 재시도: reconcile 이 needs_tl 을 보면 가공 큐 → /enrich → 적용 큐". 로컬 시험판에서는
가공 큐 = `LocalQueue("enrich")`(스레드 q-enrich). 흐름:

  reconcile(전체) ─ 적재 → [q-enrich] translate_sweep: data 를 **읽기만** 하고 LLM 번역을 모은다
                                      └ 적재 → [q-apply] apply_translation: 번역을 data 에 반영(쓰기)

`collect()` / `apply_translations()` 는 v3 `handlers._translate_sweep` 을 읽기 단계와 쓰기 단계로 나눈 것이다 —
판단 규칙(대상 필드 · 재사용 번역 · needs_tl 해제)은 그대로. 운영(v3) 경로의 `_translate_sweep` 도 이 둘을 이어 부른다.
"""
from __future__ import annotations

import logging

from . import xtweet
from .gh_store import ConflictError

log = logging.getLogger("backend.enrich")

_q = None  # LocalQueue("enrich") — local_runner 가 set_queue 로 등록


def set_queue(q) -> None:
    global _q
    _q = q


def has_queue() -> bool:
    return _q is not None


def pending() -> list[dict]:
    return _q.pending() if _q is not None else []


def enqueue_sweep() -> str | None:
    """번역 재시도 작업 적재 (이름 중복 제거 — 대기 중인 sweep 이 있으면 하나만)."""
    if _q is None:
        return None
    return _q.enqueue("translate_sweep", {}, name="translate-sweep")


# (v4.0.5) 소식 본문 번역(body_ko)은 한 번에 이만큼만 — 지난 소식 백필(활성 32 · 아카이브 78건, 10-04)이
# 첫 수집 한 번에 몰리지 않게. 정기 수집 10분마다 나눠서 채운다.
BODY_TL_PER_SWEEP = 10


def empty_updates() -> dict:
    return {"notices": {}, "tweets": {}, "preview": {}, "notice_body": {}, "archive_body": {}}


def _needs_body_ko(n: dict) -> bool:
    """본문 번역이 아직 없는 소식 — body_ko 가 없거나 None (빈 문자열 = 관리자가 비운 것, 건드리지 않음)."""
    return bool(n.get("id") and (n.get("body_raw") or "").strip() and n.get("body_ko") is None)


def count(updates: dict) -> int:
    return sum(len(v) for v in (updates or {}).values())


def collect(store, llm, now_iso: str) -> dict:
    """needs_tl 행을 찾아 번역만 한다(읽기 전용). 반환 = apply_translations 입력.

    {"notices": {nid: {"title", "title_ko"}},
     "tweets":  {"<unit>|<tweet id>": {"text_ko"?, "quote_text_ko"?}},
     "preview": {item_id: {"title", "title_ko"}},   # preview 는 번역 당시 원제목을 같이 실어 반영 때 대조
     "notice_body":  {nid: {"body_raw", "body_ko"}},  # (v4.0.5) 소식 본문 번역 — 번역한 본문을 같이 실어 대조
     "archive_body": {nid: {"body_raw", "body_ko"}}}  #   지난 소식(notice_archive.json) 백필. 합쳐 BODY_TL_PER_SWEEP 건까지
    """
    out = empty_updates()
    if llm is None:
        return out

    nj = None
    try:
        nj, _ = store.read_json("notices.json")
        for n in (nj or {}).get("notices", []) or []:
            if not n.get("needs_tl") or not n.get("id"):
                continue
            res = llm.notice_title(n.get("body_for_llm") or n.get("title") or "")
            if res and res.get("title_ko"):
                out["notices"][n["id"]] = {
                    "title": res.get("title_ja") or n.get("title"),
                    "title_ko": res["title_ko"],
                }
    except Exception as e:  # noqa: BLE001
        log.warning("notice 번역 수집 실패: %s", e)

    # (v4.0.5) 소식 본문 번역 — 활성 소식 먼저, 남으면 지난 소식(최근 것부터)
    budget = BODY_TL_PER_SWEEP
    for path, key in (("notices.json", "notice_body"), ("notice_archive.json", "archive_body")):
        if budget <= 0:
            break
        try:
            data = nj if path == "notices.json" else store.read_json(path)[0]
            rows = [n for n in (data or {}).get("notices", []) or [] if _needs_body_ko(n)]
            if path == "notice_archive.json":
                rows.sort(key=lambda n: n.get("archived_at") or "", reverse=True)
            for n in rows[:budget]:
                budget -= 1
                ko = llm.translate(n["body_raw"])
                if ko:
                    out[key][n["id"]] = {"body_raw": n["body_raw"], "body_ko": ko}
        except Exception as e:  # noqa: BLE001
            log.warning("%s 본문 번역 수집 실패: %s", path, e)

    try:
        tj, _ = store.read_json("tweets.json")
        for unit, lst in ((tj or {}).get("tweets") or {}).items():
            norm = lst if isinstance(lst, list) else ([lst] if isinstance(lst, dict) else [])
            for t in norm:
                key = f"{unit}|{t.get('id')}"
                q = t.get("quote")
                if q and q.get("needs_tl") and q.get("text") and not q.get("text_ko"):
                    ko = (xtweet.find_reused_ko(q["text"], tweets_data=tj, notices_data=nj)
                          or llm.translate(q["text"]))
                    if ko:
                        out["tweets"].setdefault(key, {})["quote_text_ko"] = ko
                if t.get("needs_tl"):
                    ko = llm.translate(t.get("text") or "")
                    if ko:
                        out["tweets"].setdefault(key, {})["text_ko"] = ko
    except Exception as e:  # noqa: BLE001
        log.warning("tweet 번역 수집 실패: %s", e)

    try:
        pj, _ = store.read_json("preview.json")
        for it in (pj or {}).get("items", []) or []:
            if not it.get("needs_tl") or not it.get("title") or not it.get("id"):
                continue
            ko = llm.translate(it["title"])
            if ko:
                out["preview"][it["id"]] = {"title": it["title"], "title_ko": ko}
    except Exception as e:  # noqa: BLE001
        log.warning("preview 번역 수집 실패: %s", e)

    return out


def _write_retry(store, path: str, mutate, message: str) -> int:
    """read → mutate(data) → write(prev_sha). ConflictError 는 다시 읽어 최대 3회. 반환 = 반영 건수."""
    for _ in range(3):
        data, sha = store.read_json(path)
        if not data:
            return 0
        n = mutate(data)
        if not n:
            return 0
        try:
            store.write_json(path, data, prev_sha=sha, message=message)
            return n
        except ConflictError:
            continue
    log.warning("%s 번역 반영: 충돌 3회 — 다음 sweep 에서 재시도", path)
    return 0


def apply_translations(store, updates: dict, now_iso: str, *, force: bool = False) -> dict:
    """collect() 결과를 data 에 반영(쓰기 — 적용 큐 작업 안에서만 호출). 반환 = 파일별 반영 건수.

    force=True 는 관리 페이지 수동 번역 — needs_tl 표시가 없어도(이미 번역됐어도) 덮어쓴다.
    """
    updates = updates or empty_updates()
    res = {"notice_tl": 0, "tweet_tl": 0, "preview_tl": 0}

    nu = updates.get("notices") or {}
    if nu:
        def _m_notices(nj):
            n_ok = 0
            for n in nj.get("notices", []) or []:
                u = nu.get(n.get("id"))
                if not u or (not force and not n.get("needs_tl")):
                    continue
                n["title"] = u.get("title") or n.get("title")
                n["title_ko"] = u["title_ko"]
                n.pop("needs_tl", None)
                n["last_updated"] = now_iso
                n_ok += 1
            if n_ok:
                nj["generated_at"] = now_iso
            return n_ok
        res["notice_tl"] = _write_retry(store, "notices.json", _m_notices, f"data: notices tl {now_iso}")

    # (v4.0.5) 소식 본문 번역 — 그 사이 본문이 바뀐 행 · 이미 번역이 생긴 행(관리자 수정 등)은 건너뛴다.
    # force 는 본문엔 안 쓴다(관리 페이지는 수정 창에서 body_ko 를 직접 고친다).
    for path, key in (("notices.json", "notice_body"), ("notice_archive.json", "archive_body")):
        bu = updates.get(key) or {}
        if not bu:
            continue

        def _m_body(data, bu=bu, path=path):
            n_ok = 0
            for n in data.get("notices", []) or []:
                u = bu.get(n.get("id"))
                if not u or n.get("body_raw") != u.get("body_raw") or n.get("body_ko") is not None:
                    continue
                n["body_ko"] = u["body_ko"]
                n_ok += 1
            if n_ok and path == "notices.json":
                data["generated_at"] = now_iso
            return n_ok
        res["notice_tl"] += _write_retry(store, path, _m_body, f"data: {path.split('.')[0]} body tl {now_iso}")

    tu = updates.get("tweets") or {}
    if tu:
        def _m_tweets(tj):
            n_ok = 0
            for unit, lst in list((tj.get("tweets") or {}).items()):
                # 계약 I — tweets[ck] 는 메시지 배열. v2.8 단건 dict 는 [dict] 로 승계.
                norm = lst if isinstance(lst, list) else ([lst] if isinstance(lst, dict) else [])
                if norm is not lst:
                    tj["tweets"][unit] = norm
                for t in norm:
                    u = tu.get(f"{unit}|{t.get('id')}")
                    if not u:
                        continue
                    q = t.get("quote")
                    if u.get("quote_text_ko") and q and q.get("needs_tl") and not q.get("text_ko"):
                        q["text_ko"] = u["quote_text_ko"]
                        q.pop("needs_tl", None)
                        n_ok += 1
                    if u.get("text_ko") and (force or t.get("needs_tl")):
                        t["text_ko"] = u["text_ko"]
                        t.pop("needs_tl", None)
                        n_ok += 1
            if n_ok:
                tj["generated_at"] = now_iso
            return n_ok
        res["tweet_tl"] = _write_retry(store, "tweets.json", _m_tweets, f"data: tweets tl {now_iso}")

    pu = updates.get("preview") or {}
    if pu:
        def _m_preview(pj):
            n_ok = 0
            for it in pj.get("items", []) or []:
                u = pu.get(it.get("id"))
                # 번역한 뒤 제목이 바뀌었으면(reconcile 이 새 제목을 가져옴) 반영하지 않는다 — 다음 sweep 이 새 제목으로
                if not u or (not force and not it.get("needs_tl")) or it.get("title") != u.get("title"):
                    continue
                it["title_ko"] = u["title_ko"]
                it.pop("needs_tl", None)
                n_ok += 1
            if n_ok:
                pj["generated_at"] = now_iso
            return n_ok
        res["preview_tl"] = _write_retry(store, "preview.json", _m_preview, f"data: preview tl {now_iso}")

    return res


def handle(kind: str, args: dict, meta: dict) -> dict:
    """가공 큐 작업 처리 (스레드 q-enrich). data 는 읽기만 하고, 반영은 적용 큐로 넘긴다."""
    if kind != "translate_sweep":
        raise ValueError(f"unknown enrich job kind: {kind!r}")
    from datetime import datetime, timezone

    from . import apply, storage
    from .config import load_config
    from .handlers import _make_llm

    cfg = load_config()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not cfg.groq_api_key:
        return {"skipped": "no GROQ_API_KEY"}
    llm = _make_llm(cfg)
    updates = collect(storage.make_store("data"), llm, now_iso)
    n = count(updates)
    job_id = None
    if n:
        job_id = apply.submit("apply_translation", {"updates": updates, "now_iso": now_iso}, wait=False).get("job_id")
    return {"collected": n, "apply_job": job_id}


if __name__ == "__main__":
    import os
    import tempfile

    from .local_store import LocalStore

    class _LLM:
        def notice_title(self, body):
            return {"title_ja": "題", "title_ko": "제목"}

        def translate(self, text):
            return f"KO:{text}"

    with tempfile.TemporaryDirectory() as d:
        s = LocalStore(d, "data")
        now = "2026-09-29T12:00:00Z"
        s.write_json("notices.json", {"notices": [{"id": "n1", "needs_tl": True, "title": "t"},
                                                  {"id": "n2", "title": "ok", "title_ko": "완료"}]},
                     prev_sha=None, message="t")
        s.write_json("tweets.json", {"tweets": {"arale": [{"id": "t1", "text": "こんにちは", "needs_tl": True}]}},
                     prev_sha=None, message="t")
        s.write_json("preview.json", {"items": [{"id": "p1", "title": "歌枠", "needs_tl": True},
                                                {"id": "p2", "title": "雑談", "needs_tl": True}]},
                     prev_sha=None, message="t")
        before = open(os.path.join(d, "data", ".commits.jsonl"), encoding="utf-8").read().count("\n")
        up = collect(s, _LLM(), now)
        after = open(os.path.join(d, "data", ".commits.jsonl"), encoding="utf-8").read().count("\n")
        assert before == after, "collect 는 쓰지 않는다"
        assert count(up) == 4 and up["tweets"]["arale|t1"]["text_ko"] == "KO:こんにちは", up
        # 그 사이 p2 제목이 바뀐 경우 → p2 는 반영 안 함
        pj, sha = s.read_json("preview.json")
        pj["items"][1]["title"] = "雑談(変更)"
        s.write_json("preview.json", pj, prev_sha=sha, message="t")
        r = apply_translations(s, up, now)
        assert r == {"notice_tl": 1, "tweet_tl": 1, "preview_tl": 1}, r
        pj, _ = s.read_json("preview.json")
        assert pj["items"][0]["title_ko"] == "KO:歌枠" and "needs_tl" not in pj["items"][0]
        assert pj["items"][1].get("needs_tl") is True, "제목이 바뀐 항목은 다음 sweep 으로"
        assert s.read_json("notices.json")[0]["notices"][0]["title_ko"] == "제목"
        assert count(collect(s, None, now)) == 0

        # (v4.0.5) 소식 본문 번역 — 활성 · 아카이브, 상한, 본문 바뀐 행 · 관리자가 비운 행 건너뜀
        rows = [{"id": f"b{i}", "title": "t", "title_ko": "제", "body_raw": f"本文{i}"} for i in range(4)]
        rows.append({"id": "b9", "title": "t", "title_ko": "제", "body_raw": "本文9", "body_ko": ""})
        nj, sha = s.read_json("notices.json")
        nj["notices"] = rows
        s.write_json("notices.json", nj, prev_sha=sha, message="t")
        s.write_json("notice_archive.json", {"notices": [
            {"id": "a1", "body_raw": "古い", "archived_at": "2026-09-01T00:00:00Z"},
            {"id": "a2", "body_raw": "新しい", "archived_at": "2026-09-20T00:00:00Z"},
            {"id": "a3", "body_raw": "済み", "body_ko": "완료"}]}, prev_sha=None, message="t")
        old_cap = BODY_TL_PER_SWEEP
        globals()["BODY_TL_PER_SWEEP"] = 5
        up = collect(s, _LLM(), now)
        assert set(up["notice_body"]) == {"b0", "b1", "b2", "b3"} and list(up["archive_body"]) == ["a2"], up
        nj, sha = s.read_json("notices.json")
        nj["notices"][1]["body_raw"] = "本文1改"          # 그 사이 본문이 바뀜 → 반영 안 함
        s.write_json("notices.json", nj, prev_sha=sha, message="t")
        r = apply_translations(s, up, now)
        assert r["notice_tl"] == 4, r
        nl = {n["id"]: n for n in s.read_json("notices.json")[0]["notices"]}
        assert nl["b0"]["body_ko"] == "KO:本文0" and nl["b1"].get("body_ko") is None and nl["b9"]["body_ko"] == ""
        al = {n["id"]: n for n in s.read_json("notice_archive.json")[0]["notices"]}
        assert al["a2"]["body_ko"] == "KO:新しい" and al["a1"].get("body_ko") is None and al["a3"]["body_ko"] == "완료"
        up = collect(s, _LLM(), now)                       # 다음 수집: b1(새 본문) · a1
        assert list(up["notice_body"]) == ["b1"] and list(up["archive_body"]) == ["a1"], up
        globals()["BODY_TL_PER_SWEEP"] = old_cap
    print("[PASS] enrich self-test: collect 읽기 전용 · apply 반영 · 제목 바뀐 항목 보류 · 소식 본문 번역(상한 · 백필)")
