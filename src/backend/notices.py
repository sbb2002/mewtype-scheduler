"""notices.json / notice_archive.json 스키마 + 머지·중복판정·수명 (순수 함수).

계약: docs/plan/v3_impl_spec.md WP-7 (v3 개정)

notices.json
  { "generated_at": "...Z",
    "notices": [ { id, category, title, title_ko, title_raw, body_raw, body_for_llm,
                   date, time, deadline, site, url, tweet_url, src_handle, anchor_a, anchor_b,
                   title_slug, is_recap, needs_tl?, seen_ids[], first_seen, last_updated, expires_at } ] }
notice_archive.json  { "notices": [ <notice + archived_at> ] }  (append-only, id dedupe)
  title_raw/body_raw 는 파싱·번역 품질 개선용 원문 기록 (프론트 안 읽음).

중복 판정 (merge_notice) — v3: url ∥ title 기반
  1. incoming.id 가 어느 소식의 id/seen_ids 에 이미 있음        → "dup" (no-op)
  2. **URL 일치 OR 제목 일치** (공백 정규화)                    → 같은 소식
       - is_recap + 이벤트 날짜 지남   → seen_ids 만 append          "recap"
       - 그 외                          → 필드 갱신(newer 우선)        "updated"
  3. 활성에 없고 아카이브에서 같은 그룹 발견                       → 아카이브 seen_ids append "recap"
  4. 아무 데도 없음:
       - is_recap + 이벤트 날짜 지남   → 버림                          "skip"
       - 그 외                          → 새 소식                        "added"
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_JST = timezone(timedelta(hours=9))


def default_notices() -> dict:
    return {"generated_at": None, "notices": []}


def default_archive() -> dict:
    return {"notices": []}


def _today_jst(now_iso: str) -> str:
    try:
        return datetime.fromisoformat(now_iso.replace("Z", "+00:00")).astimezone(_JST).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return datetime.now(_JST).strftime("%Y-%m-%d")


def _reached(iso_when: str | None, now_iso: str) -> bool:
    try:
        return datetime.fromisoformat((iso_when or "").replace("Z", "+00:00")) <= \
               datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False


def _sort_key(n: dict):
    return (n.get("date") or "9999-99-99", n.get("time") or "99:99", n.get("id") or "")


def _sorted(notices: list[dict]) -> list[dict]:
    return sorted(notices, key=_sort_key)


def _same_group(a: dict, b: dict) -> bool:
    """같은 이벤트인가 — URL 일치 OR 제목 일치.

    v3: anchor_a/b 기반 그룹핑에서 url|title 기반으로 변경.
    """
    # URL 일치 우선 (가장 확정적)
    url_a, url_b = a.get("url"), b.get("url")
    if url_a and url_b and url_a == url_b:
        return True
    # 제목 일치 (URL 없을 때)
    # ponytail: 제목 비교는 공백 정규화 (오타/줄바꿈 용인)
    title_a = re.sub(r"\s+", "", a.get("title") or "").lower()
    title_b = re.sub(r"\s+", "", b.get("title") or "").lower()
    if title_a and title_b and title_a == title_b:
        return True
    return False


def _seen(notice: dict, tid: str) -> bool:
    return tid == notice.get("id") or tid in (notice.get("seen_ids") or [])


def _merge_fields(cur: dict, inc: dict, now_iso: str) -> dict:
    """기존 소식에 새 트윗 정보 반영 — 나중 트윗이 더 확정적이라고 보고 덮음."""
    out = dict(cur)
    for k in ("title", "title_ko", "title_raw", "body_raw", "body_for_llm", "time", "url",
              "site", "tweet_url", "src_handle", "category",
              "anchor_a", "anchor_b", "title_slug", "expires_at"):
        v = inc.get(k)
        if v:
            out[k] = v
    # date 는 유지(같은 이벤트). deadline 은 새 값이 True 면 반영.
    if inc.get("deadline"):
        out["deadline"] = True
    ids = list(out.get("seen_ids") or [])
    if inc.get("id") and inc["id"] not in ids:
        ids.append(inc["id"])
    out["seen_ids"] = ids
    out["last_updated"] = now_iso
    return out


def _new_row(inc: dict, now_iso: str) -> dict:
    row = {k: inc.get(k) for k in (
        "id", "category", "title", "title_ko", "title_raw", "body_raw", "body_for_llm",
        "date", "time", "deadline", "site", "url",
        "tweet_url", "src_handle", "anchor_a", "anchor_b", "title_slug", "expires_at",
    )}
    row["deadline"] = bool(row.get("deadline"))
    row["seen_ids"] = [inc["id"]] if inc.get("id") else []
    row["first_seen"] = now_iso
    row["last_updated"] = now_iso
    return row


def merge_notice(prev: dict, incoming: dict, now_iso: str, *, archive: dict | None = None
                 ) -> tuple[dict, dict, bool, str]:
    """(new_notices, new_archive, changed, mode). mode ∈ added|updated|recap|dup|skip."""
    prev = prev or default_notices()
    arch = archive if archive is not None else default_archive()
    notices = [dict(n) for n in prev.get("notices", [])]
    arch_list = [dict(n) for n in arch.get("notices", [])]
    tid = incoming.get("id") or ""
    past = bool(incoming.get("date")) and incoming["date"] < _today_jst(now_iso)

    # 1) 이미 본 트윗
    if tid and (any(_seen(n, tid) for n in notices) or any(_seen(n, tid) for n in arch_list)):
        return prev, arch, False, "dup"

    # 2) 활성 소식에서 같은 그룹
    for i, n in enumerate(notices):
        if _same_group(n, incoming):
            if incoming.get("is_recap") and past:
                notices[i] = _merge_fields(n, {"id": tid}, now_iso)   # seen_ids 만
                mode = "recap"
            else:
                notices[i] = _merge_fields(n, incoming, now_iso)
                mode = "updated"
            out = dict(prev); out["notices"] = _sorted(notices); out["generated_at"] = now_iso
            return out, arch, True, mode

    # 3) 아카이브에서 같은 그룹 (지난 이벤트의 후속·후기)
    for i, n in enumerate(arch_list):
        if _same_group(n, incoming):
            ids = list(n.get("seen_ids") or [])
            if tid and tid not in ids:
                ids.append(tid)
                arch_list[i] = dict(n, seen_ids=ids)
                out_a = dict(arch); out_a["notices"] = arch_list
                return prev, out_a, True, "recap"
            return prev, arch, False, "dup"

    # 4) 신규
    if past:
        # 이미 지난 날짜의 새 소식(회고글·지각 후기 등)은 예고판에 안 올린다.
        # 추적 중이던 이벤트의 후기는 위 2)·3) 에서 seen_ids 로 흡수됨.
        return prev, arch, False, "skip"
    notices.append(_new_row(incoming, now_iso))
    out = dict(prev); out["notices"] = _sorted(notices); out["generated_at"] = now_iso
    return out, arch, True, "added"


_EDITABLE = ("title", "title_ko", "date", "time", "url", "site", "anchor_a", "category",
             "deadline", "title_slug", "expires_at")


def edit_notice(prev: dict, nid: str, patch: dict, now_iso: str) -> tuple[dict, bool]:
    """소식 1건의 필드를 사람이 고친 값(`patch`)으로 덮어쓴다 (v2.7.x 수동 편집).

    `patch` 에 온 `_EDITABLE` 키만 반영. 파생값(`title_slug`/`expires_at`/`site`/`anchor_a`)은
    호출측이 미리 계산해 함께 넣는다 — 이 함수는 순수 대입. `id`/`seen_ids`/`first_seen`
    은 절대 안 바꾼다. 반환 `(new, changed)`; 해당 id 없으면 `(prev, False)`.
    """
    prev = prev or default_notices()
    lst = [dict(n) for n in prev.get("notices", [])]
    idx = next((i for i, n in enumerate(lst) if n.get("id") == nid), None)
    if idx is None:
        return prev, False
    row = dict(lst[idx])
    touched = False
    for k, v in (patch or {}).items():
        if k in _EDITABLE and row.get(k) != v:
            row[k] = v
            touched = True
    if not touched:
        return prev, False
    row["last_updated"] = now_iso
    lst[idx] = row
    out = dict(prev)
    out["notices"] = _sorted(lst)
    out["generated_at"] = now_iso
    return out, True


def remove_notice(prev: dict, nid: str) -> tuple[dict, bool]:
    prev = prev or default_notices()
    kept = [n for n in prev.get("notices", []) if n.get("id") != nid]
    if len(kept) == len(prev.get("notices", [])):
        return prev, False
    out = dict(prev); out["notices"] = _sorted(kept)
    return out, True


def sweep_expired(prev: dict, archive: dict, now_iso: str) -> tuple[dict, dict, list[dict]]:
    """expires_at 지난 소식 → notice_archive.json (archived_at 추가, id dedupe)."""
    prev = prev or default_notices()
    archive = archive or default_archive()
    live, moved = [], []
    for n in prev.get("notices", []):
        if _reached(n.get("expires_at"), now_iso):
            moved.append(dict(n, archived_at=now_iso))
        else:
            live.append(n)
    if not moved:
        return prev, archive, []
    have = {a.get("id") for a in archive.get("notices", [])}
    new_arch = dict(archive)
    new_arch["notices"] = list(archive.get("notices", [])) + [m for m in moved if m.get("id") not in have]
    out = dict(prev); out["notices"] = _sorted(live); out["generated_at"] = now_iso
    return out, new_arch, moved


_KIND_KO = {"live": "라이브예고", "release": "음반·굿즈", "platform": "타 플랫폼", "etc": "기타"}


def summary_line(n: dict) -> str:
    d = n.get("date") or "?"
    tm = (" " + n["time"]) if n.get("time") else ""
    mark = "〜 " if n.get("deadline") else ""
    return f"[{_KIND_KO.get(n.get('category'), '기타')}] {mark}{d}{tm} · {n.get('title', '')[:60]}"


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    NOW = "2026-09-10T00:00:00Z"   # JST 09-10

    def inc(**kw):
        base = dict(id="", category="etc", title="t", title_raw="t raw", body_raw="원문 t 9月13日",
                    body_for_llm="원문 t", date="2026-09-13", time=None,
                    deadline=False, site="x", url=None, tweet_url=None,
                    src_handle="@BDP_yumemita", anchor_a=None, anchor_b=None,
                    title_slug="t", is_recap=False, expires_at="2026-09-14T15:00:00Z")
        base.update(kw)
        return base

    N, A = default_notices(), default_archive()

    # added (url 기반 추적)
    N, A, ch, m = merge_notice(N, inc(id="1", url="https://eplus.jp/x", title="특번", time="21:00"), NOW, archive=A)
    assert ch and m == "added" and len(N["notices"]) == 1, m
    assert N["notices"][0]["body_raw"] and N["notices"][0]["title_raw"], "원문 보존"
    # dup (같은 트윗 id)
    _, _, ch, m = merge_notice(N, inc(id="1", url="https://eplus.jp/x"), NOW, archive=A)
    assert not ch and m == "dup", m
    # updated (같은 URL, 다른 트윗 id) — 필드 갱신
    N, A, ch, m = merge_notice(N, inc(id="2", url="https://eplus.jp/x", title="특번(시간확정)", time="21:30"), NOW, archive=A)
    assert ch and m == "updated", m
    assert N["notices"][0]["time"] == "21:30" and N["notices"][0]["seen_ids"] == ["1", "2"]
    assert len(N["notices"]) == 1
    print("[OK] added / dup / updated (같은 URL 기반 중복)")

    # 제목 일치로 그룹 (URL 없을 때)
    N2, A2, ch, m = merge_notice(default_notices(), inc(id="10", title="새음반발매", url=None), NOW, archive=default_archive())
    N2, A2, ch, m = merge_notice(N2, inc(id="11", title="새음반발매", url=None), NOW, archive=A2)
    assert ch and m == "updated" and len(N2["notices"]) == 1, m
    print("[OK] 제목 일치 그룹 병합")

    # 다른 제목·다른 URL이면 별도 (DAY1/DAY2 별도 이벤트)
    N2, A2, ch, m = merge_notice(N2, inc(id="12", title="추가이벤트", url="https://other.jp/y"), NOW, archive=A2)
    assert ch and m == "added" and len(N2["notices"]) == 2, m
    print("[OK] URL/제목 다르면 별도 소식")

    # 지난 이벤트 후기, 추적한 적 없음 → skip
    _, _, ch, m = merge_notice(default_notices(), inc(id="20", date="2026-09-06", is_recap=True), NOW, archive=default_archive())
    assert not ch and m == "skip", m
    # 지난 날짜의 신규 소식(회고글 등)은 is_recap 아니어도 skip
    _, _, ch, m = merge_notice(default_notices(), inc(id="20b", date="2025-09-07", is_recap=False), NOW, archive=default_archive())
    assert not ch and m == "skip", m
    print("[OK] 지난 날짜 신규 → skip (is_recap 무관)")

    # 아카이브된 그룹의 후속 → archive seen_ids append, 부활 안 함
    arch = {"notices": [inc(id="30", date="2026-09-06", anchor_b="fes", seen_ids=["30"], archived_at=NOW)]}
    n3, a3, ch, m = merge_notice(default_notices(), inc(id="31", date="2026-09-06", anchor_b="fes", is_recap=True), NOW, archive=arch)
    assert ch and m == "recap" and len(n3["notices"]) == 0, m
    assert "31" in a3["notices"][0]["seen_ids"]
    print("[OK] 아카이브 그룹 후속 → recap (부활 안 함)")

    # sweep
    S = {"generated_at": None, "notices": [
        inc(id="40", expires_at="2026-09-09T15:00:00Z"),   # 지남
        inc(id="41", expires_at="2026-09-20T15:00:00Z"),   # 미래
    ]}
    s_out, s_arch, moved = sweep_expired(S, default_archive(), NOW)
    assert len(s_out["notices"]) == 1 and s_out["notices"][0]["id"] == "41"
    assert len(moved) == 1 and s_arch["notices"][0]["id"] == "40" and s_arch["notices"][0]["archived_at"] == NOW
    print("[OK] sweep_expired")

    # remove
    r_out, ok = remove_notice(s_out, "41")
    assert ok and len(r_out["notices"]) == 0
    assert remove_notice(r_out, "nope")[1] is False
    print("[OK] remove_notice")

    # edit_notice (v3: title_ko 지원)
    E = {"generated_at": None, "notices": [
        inc(id="50", title="会場:GARDEN", title_ko=None, date="2026-11-21", url="https://eplus.jp/x",
            anchor_a="x", seen_ids=["50"], first_seen="2026-09-01T00:00:00Z"),
    ]}
    E2, ch = edit_notice(E, "50", {
        "title": "集え！筋トレ部", "title_ko": "모여라! 근력 운동부", "title_slug": "集え筋トレ部",
        "date": "2026-11-22", "expires_at": "2026-11-23T15:00:00Z",
        "url": "https://eplus.jp/yumemita_kinntorebu2026/", "site": "web",
        "anchor_a": "yumemita_kinntorebu2026",
    }, "2026-09-10T05:00:00Z")
    assert ch and E2["notices"][0]["title"] == "集え！筋トレ部"
    assert E2["notices"][0]["title_ko"] == "모여라! 근력 운동부"
    assert E2["notices"][0]["date"] == "2026-11-22"
    assert E2["notices"][0]["anchor_a"] == "yumemita_kinntorebu2026"
    assert E2["notices"][0]["seen_ids"] == ["50"], "seen_ids 보존"
    assert E2["notices"][0]["first_seen"] == "2026-09-01T00:00:00Z", "first_seen 보존"
    assert E2["notices"][0]["last_updated"] == "2026-09-10T05:00:00Z"
    assert edit_notice(E, "nope", {"title": "x"}, NOW)[1] is False
    assert edit_notice(E, "50", {"title": "会場:GARDEN"}, NOW)[1] is False   # 동일값 → no-op
    assert edit_notice(E, "50", {"id": "hax"}, NOW)[1] is False              # id 는 편집 불가
    print("[OK] edit_notice (title_ko 지원 · id/seen_ids/first_seen 보존 · no-op)")

    print("\nSUCCESS: notices.py smoke test 통과")
