"""notices.json / notice_archive.json 스키마 + 머지·중복판정·수명 (순수 함수).

계약: docs/plan/v3_impl_spec.md WP-7 (v3 개정)

notices.json
  { "generated_at": "...Z",
    "notices": [ { id, category, title, title_ko, title_raw, body_raw, body_ko, body_for_llm,
                   date, time, deadline, site, url, tweet_url, src_handle, anchor_a, anchor_b,
                   title_slug, is_recap, needs_tl?, seen_ids[], first_seen, last_updated, expires_at,
                   categories?, live_name?, live_date? } ] }
notice_archive.json  { "notices": [ <notice + archived_at> ] }  (append-only, id dedupe)
  title_raw/body_raw 는 파싱·번역 품질 개선용 원문 기록 (프론트 안 읽음).
  body_ko (v4.0.5) = body_raw 의 한글 번역. None(키 없음) = 아직 번역 안 됨 → 번역 sweep 이 채운다.
    body_raw 가 바뀌면(더 최신 트윗으로 갱신) 같이 비운다 — 옛 본문의 번역이 남지 않게.
  categories (v4.7.0) = 분류 목록 — live(라이브공연) · event(오프라인행사) · goods(음원·굿즈) · broadcast(방송) 중 여럿,
    또는 game(Our Notes, 게임 계정 글) · etc(기타) 단독. 판정 = telegram_app._notice_categories(LLM 4분류 + 코드 규칙).
    키가 없으면(v4.7.0 이전 줄 · 판정 실패) 화면은 옛 `category`(정규식 4종)를 바꿔 읽는다. `category` 는 그대로 남긴다(옛 호환).
  live_name · live_date (v4.7.0) = 라이브공연 소식의 공연 이름(원문 표기) · 공연일(YYYY-MM-DD, 일본 날짜) — 라이브공연 탭 공연별 묶음.
    둘 다 없을 수 있다(공연 이름 없는 글 · 판정 실패).

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
    # (v4.0.5) 본문이 바뀌면 번역도 새 본문 것으로 — 없으면 비워 번역 sweep 이 다시 채우게
    if inc.get("body_raw") and inc["body_raw"] != cur.get("body_raw"):
        out["body_ko"] = inc.get("body_ko") or None
    for k in ("title", "title_ko", "title_raw", "body_raw", "body_for_llm", "time", "url",
              "site", "tweet_url", "src_handle", "category",
              "anchor_a", "anchor_b", "title_slug", "expires_at", "participants",
              "categories", "live_name", "live_date"):
        v = inc.get(k)
        if v:
            out[k] = v
    # (v4.7.0) 새 글의 분류 판정이 라이브공연이 아니면 옛 공연 이름 · 공연일을 지운다(합쳐진 글이 다른 성격이 됨)
    if inc.get("categories") and "live" not in inc["categories"]:
        out.pop("live_name", None)
        out.pop("live_date", None)
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
        "id", "category", "title", "title_ko", "title_raw", "body_raw", "body_ko", "body_for_llm",
        "date", "time", "deadline", "site", "url",
        "tweet_url", "src_handle", "anchor_a", "anchor_b", "title_slug", "expires_at",
        "participants", "categories", "live_name", "live_date",
    )}
    for k in ("categories", "live_name", "live_date"):      # (v4.7.0) 없으면 키도 안 만든다(옛 줄과 같은 모양)
        if row.get(k) is None:
            row.pop(k)
    row["deadline"] = bool(row.get("deadline"))
    row["seen_ids"] = [inc["id"]] if inc.get("id") else []
    row["first_seen"] = now_iso
    row["last_updated"] = now_iso
    return row


def merge_notice(prev: dict, incoming: dict, now_iso: str, *, archive: dict | None = None,
                 seen_ids: set | frozenset | None = None) -> tuple[dict, dict, bool, str]:
    """(new_notices, new_archive, changed, mode). mode ∈ added|updated|recap|dup|skip.
    seen_ids = 보관함 정리로 일자 파일에 옮겨진 옛 소식 · 트윗 id 색인(`archive_rotate.notice_index`) — 캐시 밖이어도 이미 본 트윗은 dup."""
    prev = prev or default_notices()
    arch = archive if archive is not None else default_archive()
    notices = [dict(n) for n in prev.get("notices", [])]
    arch_list = [dict(n) for n in arch.get("notices", [])]
    tid = incoming.get("id") or ""
    past = bool(incoming.get("date")) and incoming["date"] < _today_jst(now_iso)

    # 1) 이미 본 트윗
    if tid and (any(_seen(n, tid) for n in notices) or any(_seen(n, tid) for n in arch_list)
                or (seen_ids and tid in seen_ids)):
        return prev, arch, False, "dup"

    # 2) 활성 소식에서 같은 그룹
    for i, n in enumerate(notices):
        if _same_group(n, incoming):
            # (v4.6.2) 정규식 「후기」 표시(is_recap)로 거르던 분기는 없앴다 — 소감 · 보고는 준비 단계의 LLM 시점 판정
            # (`timing_decision`)이 병합 전에 막는다(2026-10-21 운영자 결정: 규칙이 아니라 LLM 으로).
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


def _next_midnight_utc(day_jst: str) -> str:
    """JST 날짜(YYYY-MM-DD) 다음 날 00:00 JST 를 UTC ISO 로."""
    d = datetime.fromisoformat(day_jst).replace(tzinfo=_JST) + timedelta(days=1)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def timing_decision(verdict: dict | None, posted_date: str) -> dict:
    """(v4.6.2) 소식 시점 판정(`llm.notice_timing`) → 올릴지. 2026-10-21 운영자 결정:
    지난 일의 소감 · 보고는 안 올림 · 오늘 있는 일에 대한 글은 오늘 자정(KST)까지 · 소감에 붙은 다음 일정은 그 부분만(v4.6.3 부터 오늘 일의 소감이어도) · 판정 실패면 올림(실패 기록).
    posted_date = 게시일(JST YYYY-MM-DD). 반환 {"action": post|today|next|drop|failed, "until": UTC ISO|None, "next_text": str|None, "why": str}.
    """
    out = {"action": "post", "until": None, "next_text": None, "why": ""}
    if not verdict:
        return dict(out, action="failed", why="시점 판정 실패 — 올림")
    if verdict.get("kind") != "report":
        return dict(out, why="앞으로 · 지금 기간 중인 일을 알리는 글")
    sd = verdict.get("subject_date")
    subj = (verdict.get("subject") or "").strip()
    past = bool(sd) and sd < posted_date
    nx = "\n".join(verdict.get("next_lines") or []).strip()
    if nx:
        # (v4.6.3 운영자 결정) 다음 일정 줄이 있으면 그 일의 날짜와 상관없이 다음 일정만 올린다 — 오늘 일의 감사 + 다음 회차 안내가
        # 「오늘 자정까지」로 통째로 내려가 다음 회차 안내까지 사라지던 것(10-22 실측: 5th 싱글 릴리즈 이벤트 감사 + 「次回は10/4」).
        # until = 다음 일정 줄이 소식 형식이 아닐 때 대신 쓸 「오늘 자정까지」(오늘 일일 때만, 지난 일이면 None = 안 올림)
        return dict(out, action="next", next_text=nx, until=None if past else _next_midnight_utc(posted_date),
                    why=(f"지난 일({subj or '?'} · {sd})" if past else f"오늘 있는 일({subj or '?'})") + "의 소감 — 다음 일정만 올림")
    if not past:
        return dict(out, action="today", until=_next_midnight_utc(posted_date),
                    why=f"오늘 있는 일({subj or '?'})에 대한 글 — 오늘 자정까지")
    return dict(out, action="drop", why=f"지난 일({subj or '?'} · {sd})의 소감 · 보고 — 안 올림")


def merge_into(prev: dict, target_id: str, incoming: dict, now_iso: str) -> tuple[dict, bool]:
    """(v3.7) LLM 이 같은 행사로 판정한 기존 소식(`target_id`)에 `incoming` 필드를 병합.

    `merge_notice`의 2번 분기(url/title 일치)와 갱신 규칙(`_merge_fields`)은 동일 —
    다만 "같은 행사"라는 판정 자체를 URL/제목 일치 대신 호출측(LLM 의미 비교, 같은
    날짜 후보로 이미 좁혀진 상태)이 내렸다는 점만 다르다. 호출측 게이트는
    `telegram_app._inline_notice_dup_check` 참고.

    반환 (new_prev, found) — target_id 가 없으면 (prev, False) 로 아무것도 안 바꾼다.
    """
    prev = prev or default_notices()
    lst = [dict(n) for n in prev.get("notices", [])]
    idx = next((i for i, n in enumerate(lst) if n.get("id") == target_id), None)
    if idx is None:
        return prev, False
    lst[idx] = _merge_fields(lst[idx], incoming, now_iso)
    out = dict(prev)
    out["notices"] = _sorted(lst)
    out["generated_at"] = now_iso
    return out, True


_EDITABLE = ("title", "title_ko", "body_ko", "date", "time", "url", "site", "anchor_a", "category",
             "deadline", "title_slug", "expires_at", "needs_tl",
             "categories", "live_name", "live_date")            # (v4.7.0) 관리 페이지 소식 수정 — 값 None 이면 키를 지운다


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
        if k in ("categories", "live_name", "live_date") and v is None:   # (v4.7.0) None = 지움
            if k in row:
                row.pop(k)
                touched = True
        elif k in _EDITABLE and row.get(k) != v:
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


# (v4.7.1) 라이브공연 공연별 묶음 유지 — 묶음은 공연일 + LIVE_KEEP_DAYS 일의 24:00 KST 까지 남고, 그 안의 하위 소식은
# 각자 기간(expires_at)이 지나도 묶음과 함께 내려간다(2026-10-23 운영자). 화면(js/notices.js _liveHolds)과 같은 규칙.
LIVE_KEEP_DAYS = 7
_LIVE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _norm_live(name) -> str:
    """같은 공연 판정 — 전각/반각 · 대소문자 · 공백 · 괄호 · 구두점 무시(프론트 js/notices.js _liveKey 와 같은 규칙)."""
    import unicodedata
    return re.sub(r"[\s「」『』“”\"'’・·:：!！?？\-–—_.,、。☆★]", "", unicodedata.normalize("NFKC", str(name or "")).lower())


def live_until(live_date: str | None) -> str | None:
    """공연일(YYYY-MM-DD) → 공연별 묶음 유지 끝 = 공연일 + LIVE_KEEP_DAYS 일의 24:00 KST(UTC ISO). 형식이 틀리면 None."""
    if not _LIVE_DATE_RE.match(str(live_date or "")):
        return None
    try:
        d = datetime.fromisoformat(live_date).replace(tzinfo=_JST) + timedelta(days=LIVE_KEEP_DAYS + 1)
    except ValueError:
        return None
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _most_common(vals: list) -> str | None:
    """가장 많이 나온 값(같으면 정렬상 앞선 값 — 날짜는 이른 날). 프론트 _mostCommon 과 같게."""
    best, bn, cnt = None, 0, {}
    for v in sorted(v for v in vals if v):
        cnt[v] = cnt.get(v, 0) + 1
    for v in sorted(cnt):
        if cnt[v] > bn:
            best, bn = v, cnt[v]
    return best


def _iso_dt(s: str | None):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def live_group_key(n: dict) -> str:
    """공연별 묶음 열쇠 — 라이브공연 분류이고 공연 이름이 있을 때만(없으면 빈 문자열 = 묶음 아님)."""
    return _norm_live(n.get("live_name")) if "live" in (n.get("categories") or []) else ""


def live_holds(notices: list[dict]) -> dict[str, str]:
    """공연별 묶음마다 유지 끝(UTC ISO) — max(공연일 + 7일 24:00 KST, 하위 소식 expires_at 중 가장 늦은 것).
    공연일이 없는 묶음은 하위 소식 중 가장 늦은 기간까지(전과 같음). 공연일 = 묶음 안에서 가장 많이 나온 live_date."""
    groups: dict[str, list[dict]] = {}
    for n in notices:
        k = live_group_key(n)
        if k:
            groups.setdefault(k, []).append(n)
    out = {}
    for k, items in groups.items():
        cands = [_iso_dt(live_until(_most_common([n.get("live_date") for n in items if _LIVE_DATE_RE.match(str(n.get("live_date") or ""))])))]
        cands += [_iso_dt(n.get("expires_at")) for n in items]
        cands = [c for c in cands if c]
        if cands:
            out[k] = max(cands).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def sweep_expired(prev: dict, archive: dict, now_iso: str) -> tuple[dict, dict, list[dict]]:
    """expires_at 지난 소식 → notice_archive.json (archived_at 추가, id dedupe).
    (v4.7.1) 라이브공연 공연별 묶음의 하위 소식은 묶음 유지 끝(`live_holds`)이 지나야 묶음째 옮긴다 —
    그 전엔 자기 기간이 지나도 남는다(화면이 어둡게 「지난 소식」으로 보인다). expires_at 은 고치지 않는다."""
    prev = prev or default_notices()
    archive = archive or default_archive()
    holds = live_holds(prev.get("notices", []))
    live, moved = [], []
    for n in prev.get("notices", []):
        k = live_group_key(n)
        if _reached(holds[k] if k in holds else n.get("expires_at"), now_iso):
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
# (v4.7.0) 새 분류 이름 — 프론트 js/notices.js CATS 와 같게
CAT_KO = {"live": "라이브공연", "event": "오프라인행사", "goods": "음원·굿즈", "broadcast": "방송", "game": "Our Notes", "etc": "기타"}


def summary_line(n: dict) -> str:
    d = n.get("date") or "?"
    tm = (" " + n["time"]) if n.get("time") else ""
    mark = "〜 " if n.get("deadline") else ""
    kind = "·".join(CAT_KO.get(c, c) for c in n["categories"]) if n.get("categories") else _KIND_KO.get(n.get("category"), "기타")
    return f"[{kind}] {mark}{d}{tm} · {n.get('title', '')[:60]}"


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

    # seen_ids — 캐시에서 빠진 옛 트윗 id 도 같은 트윗이면 dup (보관함 정리 뒤에도 다시 올리지 않게)
    _, _, ch, m = merge_notice(default_notices(), inc(id="900", url="https://old.jp/z"), NOW, seen_ids={"900"})
    assert not ch and m == "dup", m
    _, _, ch, m = merge_notice(default_notices(), inc(id="901", url="https://old.jp/z"), NOW, seen_ids=frozenset({"900"}))
    assert ch and m == "added", m
    print("[OK] seen_ids — 캐시 밖 옛 트윗 id 는 dup")

    # merge_into (v3.7 LLM 의미 중복 게이트가 호출하는 병합 — url/title 안 다르게 만든 케이스)
    N3, A3, ch, m = merge_notice(default_notices(), inc(id="20", title="다른표현A", url=None), NOW, archive=default_archive())
    assert ch and m == "added"
    merged, found = merge_into(N3, "20", inc(id="21", title="다른표현B", time="19:00", url=None), NOW)
    assert found and merged["notices"][0]["title"] == "다른표현B" and merged["notices"][0]["time"] == "19:00"
    assert merged["notices"][0]["seen_ids"] == ["20", "21"], merged["notices"][0]["seen_ids"]
    _, found2 = merge_into(N3, "no-such-id", inc(id="22"), NOW)
    assert not found2
    print("[OK] merge_into (LLM 의미 중복 병합 — url/title 달라도 지정 대상에 필드 갱신)")

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

    # (v4.6.2) 활성 소식과 같은 그룹이면 is_recap 이어도 갱신(정규식 후기 분기 없앰 — 소감은 준비 단계 LLM 판정이 막는다)
    _, _, ch, m = merge_notice({"notices": [inc(id="50", url="https://x.jp/a")]}, inc(id="51", url="https://x.jp/a", date="2026-09-06", is_recap=True), NOW)
    assert ch and m == "updated", m
    # (v4.6.2) 시점 판정 → 올릴지
    TD = "2026-10-11"
    assert timing_decision({"kind": "announce"}, TD)["action"] == "post"
    assert timing_decision(None, TD)["action"] == "failed"
    t1 = timing_decision({"kind": "report", "subject": "13th LIVE", "subject_date": "2026-10-11", "next_lines": []}, TD)
    assert t1["action"] == "today" and t1["until"] == "2026-10-11T15:00:00Z", t1           # 오늘 자정(KST)까지
    assert timing_decision({"kind": "report", "subject_date": None, "next_lines": []}, TD)["action"] == "today", "날짜를 모르면 오늘 일로"
    assert timing_decision({"kind": "report", "subject_date": "2026-10-10", "next_lines": []}, TD)["action"] == "drop"
    t4 = timing_decision({"kind": "report", "subject_date": "2026-09-20", "next_lines": ["次回は9/27(日)開催", "https://x.jp/t"]}, TD)
    assert t4["action"] == "next" and t4["next_text"] == "次回は9/27(日)開催\nhttps://x.jp/t" and t4["until"] is None, t4
    print("[OK] (v4.6.2) timing_decision — 알림 올림 · 오늘 일 자정까지 · 지난 일 안 올림 · 다음 일정만 · 실패 올림")
    # (v4.6.3) 오늘 일(또는 날짜 모름)의 소감 + 다음 일정 → 다음 일정만(전엔 「오늘 자정까지」로 통째로 내려가 다음 일정도 사라졌다)
    for _sd in ("2026-10-11", None):
        t5 = timing_decision({"kind": "report", "subject": "リリースイベント", "subject_date": _sd,
                              "next_lines": ["次回は、10/4(日)ヨドバシカメラマルチメディアAkiba 様にて開催❕"]}, TD)
        assert t5["action"] == "next" and t5["until"] == "2026-10-11T15:00:00Z" and "오늘 있는 일" in t5["why"], t5
    print("[OK] (v4.6.3) timing_decision — 오늘 일의 소감 + 다음 일정 → 다음 일정만(줄을 못 읽으면 오늘 자정까지)")

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

    # (v4.0.5) body_ko — 신규 보존 · 같은 본문 갱신이면 유지 · 본문이 바뀌면 새 번역(없으면 비움) · 수정 가능
    B = default_notices()
    B, _, _, m = merge_notice(B, inc(id="70", url="https://b.jp/1", body_raw="本文A", body_ko="본문A"), NOW)
    assert m == "added" and B["notices"][0]["body_ko"] == "본문A"
    B, _, _, m = merge_notice(B, inc(id="71", url="https://b.jp/1", body_raw="本文A"), NOW)
    assert m == "updated" and B["notices"][0]["body_ko"] == "본문A", "같은 본문 → 번역 유지"
    B, _, _, m = merge_notice(B, inc(id="72", url="https://b.jp/1", body_raw="本文B"), NOW)
    assert m == "updated" and B["notices"][0]["body_raw"] == "本文B" and B["notices"][0]["body_ko"] is None, "본문 바뀜 → 비움"
    B, _, _, m = merge_notice(B, inc(id="73", url="https://b.jp/1", body_raw="本文C", body_ko="본문C"), NOW)
    assert B["notices"][0]["body_ko"] == "본문C"
    B2, ch = edit_notice(B, B["notices"][0]["id"], {"body_ko": "고친 본문"}, NOW)
    assert ch and B2["notices"][0]["body_ko"] == "고친 본문"
    print("[OK] body_ko (신규 · 유지 · 본문 바뀌면 비움 · 수정)")

    # v3.2 — participants (비전 OCR 로 판별된 출연 채널) 필드가 신규/갱신 모두 보존되는지
    NP, AP = default_notices(), default_archive()
    NP, AP, ch, m = merge_notice(
        NP, inc(id="60", url="https://youtube.com/live/x", title="크로스오버 특번",
                participants=["nonoka"]),
        NOW, archive=AP,
    )
    assert ch and m == "added" and NP["notices"][0]["participants"] == ["nonoka"], NP["notices"][0]
    NP, AP, ch, m = merge_notice(
        NP, inc(id="61", url="https://youtube.com/live/x", title="크로스오버 특번(정정)",
                participants=["nonoka"]),
        NOW, archive=AP,
    )
    assert ch and m == "updated" and NP["notices"][0]["participants"] == ["nonoka"], NP["notices"][0]
    print("[OK] participants 필드 신규/갱신 보존 (비전 OCR 출연 채널)")

    # (v4.7.0) categories · live_name · live_date — 신규 · 갱신 · 라이브공연이 아니게 되면 공연 이름 지움 · 수정(None = 지움)
    NC = default_notices()
    NC, _, ch, m = merge_notice(NC, inc(id="80", url="https://c.jp/1", categories=["live", "goods"],
                                       live_name="RESONEXT", live_date="2026-12-24"), NOW)
    r = NC["notices"][0]
    assert m == "added" and r["categories"] == ["live", "goods"] and r["live_name"] == "RESONEXT" and r["live_date"] == "2026-12-24", r
    NC, _, ch, m = merge_notice(NC, inc(id="81", url="https://c.jp/1"), NOW)
    assert m == "updated" and NC["notices"][0]["live_name"] == "RESONEXT", "판정 없는 새 글 → 기존 값 유지"
    NC, _, ch, m = merge_notice(NC, inc(id="82", url="https://c.jp/1", categories=["goods"]), NOW)
    assert NC["notices"][0]["categories"] == ["goods"] and "live_name" not in NC["notices"][0] and "live_date" not in NC["notices"][0]
    NO, _, _, _ = merge_notice(default_notices(), inc(id="83", url="https://c.jp/2"), NOW)
    assert not {"categories", "live_name", "live_date"} & set(NO["notices"][0]), "판정 없으면 키도 없음(옛 줄과 같은 모양)"
    NE, ch = edit_notice(NC, NC["notices"][0]["id"], {"categories": ["live"], "live_name": "X", "live_date": None}, NOW)
    assert ch and NE["notices"][0]["categories"] == ["live"] and NE["notices"][0]["live_name"] == "X" and "live_date" not in NE["notices"][0]
    assert summary_line(NE["notices"][0]).startswith("[라이브공연]"), summary_line(NE["notices"][0])
    print("[OK] categories · live_name · live_date (v4.7.0)")

    # (v4.7.1) 라이브공연 공연별 묶음 유지 — 공연일 + 7일 24:00 KST 까지 하위 소식을 묶음째 남긴다
    assert live_until("2026-12-24") == "2026-12-31T15:00:00Z", live_until("2026-12-24")   # 12-24 + 7일 = 12-31 24:00 KST
    assert live_until(None) is None and live_until("12/24") is None
    assert _norm_live("ＲＥＳＯ　ＮＥＸＴ") == _norm_live("RESONEXT")
    def _lv(id_, date, exp, name="RESONEXT", ld="2026-12-24", cats=("live",)):
        r = inc(id=id_, url=f"https://l/{id_}", title=f"t{id_}", date=date, expires_at=exp, categories=list(cats))
        if name: r["live_name"] = name
        if ld: r["live_date"] = ld
        return r
    LG = {"notices": [
        _lv("a1", "2026-11-01", "2026-11-01T15:00:00Z"),                       # 티켓 선행(공연 전 기간 끝)
        _lv("a2", "2026-12-24", "2026-12-24T15:00:00Z", name="ＲＥＳＯ ＮＥＸＴ"),  # 표기만 다른 같은 공연
        _lv("a3", "2026-12-26", "2026-12-26T15:00:00Z", ld=None),               # 공연일 없는 하위 소식(묶음 공연일을 따름)
        _lv("b1", "2026-11-05", "2026-11-05T15:00:00Z", name="X LIVE", ld=None),  # 공연일 미정 묶음
        _lv("b2", "2026-11-09", "2026-11-09T15:00:00Z", name="X LIVE", ld=None),
        _lv("c1", "2026-11-01", "2026-11-01T15:00:00Z", name=None, ld=None),    # 공연 이름 없음 = 묶음 아님
        _lv("d1", "2026-11-01", "2026-11-01T15:00:00Z", cats=("goods",)),       # 라이브공연 아님 = 묶음 아님
    ]}
    H = live_holds(LG["notices"])
    assert H == {_norm_live("RESONEXT"): "2026-12-31T15:00:00Z", _norm_live("X LIVE"): "2026-11-09T15:00:00Z"}, H
    def _ids(d): return sorted(n["id"] for n in d["notices"])
    s1, a1, mv = sweep_expired(LG, default_archive(), "2026-11-02T00:00:00Z")   # a1 · c1 · d1 기간 지남
    assert _ids(s1) == ["a1", "a2", "a3", "b1", "b2"] and sorted(m["id"] for m in mv) == ["c1", "d1"], (_ids(s1), mv)
    s2, a2, mv = sweep_expired(s1, a1, "2026-11-06T00:00:00Z")                  # b1 기간 지남 · 묶음(11-09)은 유지
    assert _ids(s2) == ["a1", "a2", "a3", "b1", "b2"] and not mv
    s3, a3, mv = sweep_expired(s2, a2, "2026-11-09T15:00:00Z")                  # 공연일 미정 묶음 = 마지막 하위 소식과 함께
    assert _ids(s3) == ["a1", "a2", "a3"] and sorted(m["id"] for m in mv) == ["b1", "b2"]
    s4, a4, mv = sweep_expired(s3, a3, "2026-12-31T14:59:59Z")                  # 공연 + 7일 23:59:59 KST — 아직 남음
    assert _ids(s4) == ["a1", "a2", "a3"] and not mv
    assert s4["notices"][0]["expires_at"] == "2026-11-01T15:00:00Z", "자기 기간(expires_at)은 그대로 — 화면이 지난 소식으로 어둡게"
    s5, a5, mv = sweep_expired(s4, a4, "2026-12-31T15:00:00Z")                  # 공연 + 7일 24:00 — 묶음째
    assert not s5["notices"] and sorted(m["id"] for m in mv) == ["a1", "a2", "a3"]
    assert {n["id"] for n in a5["notices"]} == {"a1", "a2", "a3", "b1", "b2", "c1", "d1"}
    LT = {"notices": [_lv("e1", "2027-03-01", "2027-03-01T15:00:00Z", ld="2026-12-24")]}   # 하위 소식 기간이 공연 + 7일보다 늦으면 그때까지
    assert live_holds(LT["notices"]) == {_norm_live("RESONEXT"): "2027-03-01T15:00:00Z"}
    print("[OK] 라이브공연 공연별 묶음 유지 (v4.7.1)")

    print("\nSUCCESS: notices.py smoke test 통과")
