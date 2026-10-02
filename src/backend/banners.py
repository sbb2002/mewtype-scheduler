"""(v4a) 행사 배너 — banners.json / banners_archive.json 계약 + 판정 반영·상태 파생·정리 (순수 함수).

계약: docs/SPEC.md 계약 J. 용어: docs/TERMINOLOGY.md 「행사 배너 용어」.

banners.json
  { "generated_at": "...Z",
    "banners": [ { id, name_ja, name_ko, match_keys[], image_urls[], start_at, end_at, start_time_tbd?,
                   hold: null | {anchor, until}, gachas: [ {id, title_ja, title_ko, image_urls[], start_at, end_at} ],
                   src_ids[], first_seen, last_updated } ] }
banners_archive.json  { "banners": [ <banner + archived_at, archived_reason> ] }

원칙
  - 시각은 UTC ISO(`...Z`). LLM 은 JST 문자열("YYYY-MM-DD HH:MM" / "YYYY-MM-DD")로 주고 `parse_jst` 가 바꾼다.
  - 표시 상태는 저장하지 않고 `derive` 로 현재 시각에서 파생한다(프론트 `banners.js` 도 같은 규칙).
  - LLM 출력은 그대로 믿지 않는다 — `apply_judgement` 가 형식 · 순서 · 참조 id 를 검증한 뒤에만 반영한다.
  - 종료일 없는 행사 · 상시화 행사 · 120일 넘는 행사는 **배너로 올리지 않는다**(2026-10-02 운영자 결정).
    다만 정보가 글 여러 개에 나뉘어 오므로(09-24 글은 시작만, 09-30 글은 종료만 — 실측) 시작 · 종료 중 하나만 아는 행사는
    「대기」로 저장해 두고(화면에는 안 보임, LLM 에게는 기존 행사로 보여줌) 둘이 다 채워지면 그때 올린다.
    상시화(permanent) · 120일 초과는 저장하지도 않는다.
"""
from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone

_JST = timezone(timedelta(hours=9))

HOLD_DAYS = 15                  # 보류 표시 유지 기간(보류 시작 때 표시한 개최일 + 15일)
MAX_EVENT_DAYS = 120            # 이보다 긴 행사는 상시화로 보고 올리지 않는다
PENDING_DAYS = 30             # 시작 · 종료 중 하나만 알고 이 기간 갱신이 없으면 정리
MAX_IMAGES = 6
MAX_GACHAS = 4
_SANE_YEARS = 1                 # 현재 기준 ±1년 밖 날짜는 LLM 오독으로 본다
_MIN_KEY_LEN = 4                # 소식 겹침 판정에 쓰는 이름 키 최소 길이(너무 짧으면 오탐)

ACTIONS = ("none", "upsert", "hold", "cancel")


def default_banners() -> dict:
    return {"generated_at": None, "banners": []}


def default_archive() -> dict:
    return {"banners": []}


# ── 시각 ─────────────────────────────────────────────────────────────

def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_JST_RE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?\s*$")


def parse_jst(s: str | None, *, end: bool = False) -> tuple[str | None, bool]:
    """JST 문자열 → (UTC ISO, 시각 미정 여부). 형식이 틀리면 (None, False).

    "YYYY-MM-DD HH:MM" → 그 시각. "YYYY-MM-DD"(날짜만): 시작이면 00:00 JST + 시각 미정, 종료면 그 날 23:59 JST.
    """
    m = _JST_RE.match(s or "")
    if not m:
        return None, False
    y, mo, d = int(m[1]), int(m[2]), int(m[3])
    try:
        if m[4] is not None:
            dt = datetime(y, mo, d, int(m[4]), int(m[5]), tzinfo=_JST)
            return _iso(dt), False
        dt = datetime(y, mo, d, 23, 59, tzinfo=_JST) if end else datetime(y, mo, d, 0, 0, tzinfo=_JST)
        return _iso(dt), (not end)
    except ValueError:
        return None, False


def _sane(dt: datetime, now: datetime) -> bool:
    return abs((dt - now).days) <= 365 * _SANE_YEARS


# ── 이름 키 ──────────────────────────────────────────────────────────

_QUOTE_RE = re.compile(r"[「『“\"]([^」』”\"]{2,})[」』”\"]")
_STRIP_RE = re.compile(r"[\s　!！?？・･~〜～\-ー—–_.,，、。:：;；/／\\|()（）\[\]【】<>＜＞'’`´]+")


def _norm(s: str) -> str:
    return _STRIP_RE.sub("", unicodedata.normalize("NFKC", s or "")).lower()


def name_key(name: str | None) -> str:
    """행사 · 가챠 이름의 비교 키 — 「」 안 이름이 있으면 그것(앞 수식어 제거), 없으면 전체. 정규화(NFKC · 공백 · 기호 제거 · 소문자)."""
    n = (name or "").strip()
    m = _QUOTE_RE.search(n)
    return _norm(m.group(1) if m else n)


def make_id(name_ja: str) -> str:
    return "bn_" + hashlib.sha1(name_key(name_ja).encode("utf-8")).hexdigest()[:8]


def _keys(b: dict) -> list[str]:
    ks = [name_key(b.get("name_ja"))] + [name_key(g.get("title_ja")) for g in b.get("gachas") or []]
    return [k for k in ks if len(k) >= _MIN_KEY_LEN]


def covers_text(banners: list[dict], text: str) -> str | None:
    """본문이 이미 행사 배너가 다루는 행사 · 가챠를 가리키면 그 이름 키, 아니면 None — 소식 중복 방지용."""
    t = _norm(text)
    if not t:
        return None
    for b in banners:
        for k in _keys(b):
            if k in t:
                return k
    return None


# ── 표시 상태 파생 ────────────────────────────────────────────────────

_KST = timezone(timedelta(hours=9))


def full_end(b: dict) -> datetime | None:
    """완전 종료 시각 — 행사 종료와 가챠 자체 종료(없으면 행사와 같음) 중 가장 늦은 것."""
    ends = [_parse_iso(b.get("end_at"))] + [_parse_iso(g.get("end_at")) for g in b.get("gachas") or []]
    ends = [e for e in ends if e is not None]
    return max(ends) if ends else None


def _midnight_after(dt: datetime) -> datetime:
    """dt 가 속한 한국 시간 날짜의 다음 날 00:00(KST) — 완전 종료 뒤 「종료」 표시를 내리는 시각."""
    k = dt.astimezone(_KST)
    return (k.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc)


def derive(b: dict, now_iso: str) -> tuple[str, str]:
    """(상태, 사유). 상태 ∈ hold | announced | live | done | gone | pending.

    announced 에는 **종료일을 아직 모르는 개최 전 공지**도 포함한다(시작 일시를 먼저 알려준다 — 2026-10-02 운영자 결정).
    done: 행사 · 가챠가 모두 끝났지만 그날 자정(KST)까지는 「종료」로 계속 보인다.
    pending: 시작을 모르거나, 종료를 모르는데 이미 시작했음(화면에 안 올림 — 상시화 행사 거르기). gone 사유:
    hold_expired(보류 + 15일 지남) · ended(종료일 다음 날 자정 지남) · incomplete_expired(대기인 채 30일 넘게 갱신 없음).
    """
    now = _parse_iso(now_iso)
    end = _parse_iso(b.get("end_at"))
    start = _parse_iso(b.get("start_at"))
    h = b.get("hold")
    if start is None or (end is None and not h and now >= start):
        if end is not None and now >= _midnight_after(end):
            return "gone", "ended"
        last = _parse_iso(b.get("last_updated")) or now
        if (now - last).days >= PENDING_DAYS:
            return "gone", "incomplete_expired"
        return "pending", "incomplete"
    if h:
        until = _parse_iso(h.get("until"))
        if until is None or now >= until:
            return "gone", "hold_expired"
        return "hold", ""
    if end is None:                       # 개최 전 · 종료일 미정
        return "announced", ""
    fe = full_end(b) or end
    if now >= _midnight_after(fe):
        return "gone", "ended"
    if now >= fe:
        return "done", ""
    return ("announced" if now < start else "live"), ""


def active(prev: dict, now_iso: str) -> list[dict]:
    """gone 이 아닌 행사 전부(대기 포함) — 판정 LLM 에게 「지금 있는 행사」로 보여주고 소식 겹침 판정에 쓴다."""
    return [b for b in prev.get("banners") or [] if derive(b, now_iso)[0] != "gone"]


def to_jst(iso: str | None) -> str | None:
    """UTC ISO → "YYYY-MM-DD HH:MM"(JST). 판정 LLM 프롬프트용."""
    dt = _parse_iso(iso)
    return dt.astimezone(_JST).strftime("%Y-%m-%d %H:%M") if dt else None


def for_llm(prev: dict, now_iso: str) -> list[dict]:
    """`llm.banner_judge` 의 active 인자 — 대기 포함 활성 행사를 JST 문자열로."""
    return [{"id": b["id"], "name_ja": b.get("name_ja"), "start_jst": to_jst(b.get("start_at")),
             "end_jst": to_jst(b.get("end_at")), "hold": bool(b.get("hold")),
             "gachas": [g.get("title_ja") for g in b.get("gachas") or []]} for b in active(prev, now_iso)]


def visible(prev: dict, now_iso: str) -> list[dict]:
    """화면에 올라가는 행사 — 보류 · 예정 · 진행 중 · 종료(그날 자정까지)."""
    return [b for b in prev.get("banners") or [] if derive(b, now_iso)[0] in ("hold", "announced", "live", "done")]


# ── 판정 반영 ────────────────────────────────────────────────────────

def _find(prev_list: list[dict], ref: str | None, name_ja: str | None) -> dict | None:
    if ref:
        hit = next((b for b in prev_list if b.get("id") == ref), None)
        if hit:
            return hit
    k = name_key(name_ja)
    if len(k) >= _MIN_KEY_LEN:
        for b in prev_list:
            if k in _keys(b) or any(k and (k in x or x in k) for x in _keys(b)[:1]):
                return b
    return None


def _merge_images(cur: list[str], new: list[str]) -> list[str]:
    out = list(cur or [])
    for u in new or []:
        if isinstance(u, str) and u.startswith("http") and u not in out:
            out.append(u)
    return out[-MAX_IMAGES:]


def _gacha_id(title_ja: str) -> str:
    return "gc_" + hashlib.sha1(name_key(title_ja).encode("utf-8")).hexdigest()[:8]


def _times(obj: dict | None, now: datetime) -> tuple[dict | None, str | None]:
    """LLM 의 start_jst/end_jst → UTC 로 바꾸고 검증. 반환 (값 dict, 오류 사유)."""
    obj = obj or {}
    s_raw, e_raw = obj.get("start_jst"), obj.get("end_jst")
    start = end = None
    tbd = False
    if s_raw:
        start, tbd = parse_jst(s_raw)
        if start is None:
            return None, f"시작 시각 형식 오류: {s_raw!r}"
    if e_raw:
        end, _ = parse_jst(e_raw, end=True)
        if end is None:
            return None, f"종료 시각 형식 오류: {e_raw!r}"
    for v in (start, end):
        if v and not _sane(_parse_iso(v), now):
            return None, f"날짜가 현재 기준 ±{_SANE_YEARS}년 밖: {v}"
    if start and end:
        s, e = _parse_iso(start), _parse_iso(end)
        if e < s:
            return None, "종료가 시작보다 앞섬"
        if (e - s).days > MAX_EVENT_DAYS:
            return None, f"기간 {(e - s).days}일 — 상시화 의심(>{MAX_EVENT_DAYS}일)"
    return {"start_at": start, "end_at": end, "start_time_tbd": tbd}, None


def apply_judgement(prev: dict, j: dict, post: dict, now_iso: str) -> dict:
    """행사 판정 1건을 반영한다. 반환:

      {"banners": 새 목록(dict), "archive_add": [보관할 항목], "mode": str, "detail": str, "undo": dict|None, "id": str|None}

    mode ∈ added · updated · held · cancelled · none · dup · invalid · skip_permanent
    shown: 이 반영 뒤 그 행사가 화면에 올라가는가(대기면 False).  post = {"tweet_id": str, "media": [url…]}.  `prev` 는 바꾸지 않는다(사본).
    """
    now = _parse_iso(now_iso)
    cur = copy.deepcopy(prev or default_banners())
    lst: list[dict] = cur.setdefault("banners", [])
    out = {"banners": cur, "archive_add": [], "mode": "none", "detail": "", "undo": None, "id": None, "shown": False}
    tid = str(post.get("tweet_id") or "")

    def done(mode, detail, **kw):
        out.update(mode=mode, detail=detail, **kw)
        return out

    if not isinstance(j, dict) or j.get("action") not in ACTIONS:
        return done("invalid", "판정 형식 오류")
    action = j["action"]
    if action == "none":
        return done("none", (j.get("reason") or "")[:120])
    if tid and any(tid in (b.get("src_ids") or []) for b in lst):
        return done("dup", "이미 반영한 글")        # 같은 글 재전송(폰 재시도)은 건드리지 않는다

    ev = j.get("event") if isinstance(j.get("event"), dict) else None
    ga = j.get("gacha") if isinstance(j.get("gacha"), dict) else None
    if ev and ev.get("permanent"):
        return done("skip_permanent", "상시화된 행사 — 올리지 않음")
    target = _find(lst, j.get("banner_ref"), (ev or {}).get("name_ja"))
    if target and ev and ev.get("name_ja") and name_key(ev["name_ja"]) != name_key(target.get("name_ja")):
        # 판정이 가챠 정보를 행사 칸에 넣은 경우(실측: 가챠만 소개한 글) — 가챠로 옮긴다. 행사 날짜를 건드리면 안 된다.
        if ga is None:
            ga = {"title_ja": ev["name_ja"], "title_ko": ev.get("name_ko"), "start_jst": ev.get("start_jst"), "end_jst": ev.get("end_jst")}
        ev = None

    def snapshot(b):
        return copy.deepcopy(b) if b else None

    # ── 취소 ── 활성 행사를 보관으로 내린다
    if action == "cancel":
        if not target:
            return done("none", "취소 대상 행사 없음")
        before = snapshot(target)
        lst.remove(target)
        out["archive_add"].append(dict(target, archived_at=now_iso, archived_reason="cancelled"))
        return done("cancelled", f"취소 — {target.get('name_ko') or target.get('name_ja')}", id=target["id"],
                    undo={"type": "restore_banner", "id": target["id"], "before": before, "was_archived": True})

    # ── 보류 ──
    if action == "hold":
        if not target:
            return done("none", "보류 대상 행사 없음")
        if target.get("hold"):
            return done("none", "이미 보류 중")
        anchor = _parse_iso(target.get("start_at"))
        if anchor is None:
            return done("none", "개최일을 몰라 보류 표시를 할 수 없음")
        before = snapshot(target)
        target["hold"] = {"anchor": _iso(anchor), "until": _iso(anchor + timedelta(days=HOLD_DAYS))}
        if tid:
            target.setdefault("src_ids", []).append(tid)
        target["last_updated"] = now_iso
        return done("held", f"보류 — {target.get('name_ko') or target.get('name_ja')}", id=target["id"],
                    undo={"type": "restore_banner", "id": target["id"], "before": before})

    # ── upsert ──
    if not ev and not (ga and target):
        return done("none", "행사 정보 없음")
    et, err = _times(ev, now)
    if err:
        return done("invalid", err)

    before = snapshot(target)
    is_new = target is None
    if is_new:
        name_ja = (ev.get("name_ja") or "").strip()
        if not name_ja or not (et["start_at"] or et["end_at"]):
            return done("invalid", "새 행사에 이름과 시작 · 종료 중 하나는 필요")
        target = {"id": make_id(name_ja), "name_ja": name_ja, "name_ko": (ev.get("name_ko") or "").strip() or None,
                  "match_keys": [], "image_urls": [], "start_at": et["start_at"], "end_at": et["end_at"],
                  "start_time_tbd": bool(et["start_time_tbd"]) or None, "hold": None, "gachas": [], "src_ids": [],
                  "first_seen": now_iso, "last_updated": now_iso}
        if any(b.get("id") == target["id"] for b in lst):          # 이름 키가 같은데 못 찾은 경우(방어)
            target = next(b for b in lst if b["id"] == target["id"])
            is_new = False
            before = snapshot(target)
        else:
            lst.append(target)

    if not is_new and ev:
        # 새 사실만 덮는다 — 빈 값은 기존 유지. 날짜가 바뀌면 보류 해제(재공지로 기간이 올라왔다는 뜻).
        if ev.get("name_ko") and not target.get("name_ko"):
            target["name_ko"] = ev["name_ko"].strip()
        dated = False
        if et["start_at"] and et["start_at"] != target.get("start_at"):
            target["start_at"], target["start_time_tbd"] = et["start_at"], (bool(et["start_time_tbd"]) or None)
            dated = True
        if et["end_at"] and et["end_at"] != target.get("end_at"):
            target["end_at"] = et["end_at"]
            dated = True
        if target.get("end_at") and target.get("start_at") and _parse_iso(target["end_at"]) < _parse_iso(target["start_at"]):
            return done("invalid", "갱신 결과 종료가 시작보다 앞섬")
        if target.get("hold") and (dated or (et["start_at"] and et["end_at"])):
            target["hold"] = None

    # 가챠
    if ga and (ga.get("title_ja") or "").strip():
        gt, gerr = _times(ga, now)
        if gerr:
            gt = {"start_at": None, "end_at": None, "start_time_tbd": False}
        title_ja = ga["title_ja"].strip()
        gk = name_key(title_ja)
        g = next((x for x in target["gachas"] if name_key(x.get("title_ja")) == gk), None)
        if g is None:
            if len(target["gachas"]) < MAX_GACHAS:
                g = {"id": _gacha_id(title_ja), "title_ja": title_ja, "title_ko": (ga.get("title_ko") or "").strip() or None,
                     "image_urls": [], "start_at": gt["start_at"], "end_at": gt["end_at"]}
                target["gachas"].append(g)
        else:
            if ga.get("title_ko") and not g.get("title_ko"):
                g["title_ko"] = ga["title_ko"].strip()
            if gt["start_at"]:
                g["start_at"] = gt["start_at"]
            if gt["end_at"]:
                g["end_at"] = gt["end_at"]
    else:
        g = None

    # 이미지 — 어느 카드에 붙일지는 판정이 정한다
    # 이미지 — 2026-10-02 운영자 결정: X 트윗에서 걸린 이미지 중 **행사 키비주얼**(로고 · 일러스트 · 개최기간만 있는 온전한 그림)만 쓴다.
    # 소개 카드 · 방송 화면 캡처 · 가챠 이미지(정사각형이라 배너 비율에 안 맞고 필수도 아님)는 안 쓴다. 판정이 이미지 용도를 못 정했으면
    # (비전 실패 등) 안 붙인다 — 잘못된 이미지가 올라가는 것보다 이미지가 없는 쪽이 낫다.
    media = [u for u in (post.get("media") or []) if isinstance(u, str)]
    roles = j.get("image_roles") if isinstance(j.get("image_roles"), list) else []
    if media and len(roles) == len(media):
        ev_imgs = [u for u, r in zip(media, roles) if r == "event"]
        if ev_imgs:
            target["image_urls"] = _merge_images(target.get("image_urls"), ev_imgs)

    target["match_keys"] = _keys(target)
    if tid and tid not in target["src_ids"]:
        target["src_ids"].append(tid)
        target["src_ids"] = target["src_ids"][-20:]
    changed = is_new or snapshot(target) != before
    if not changed:
        return done("none", "바뀐 것 없음", id=target["id"])
    target["last_updated"] = now_iso
    cur["banners"] = sorted(lst, key=lambda b: (b.get("start_at") or "", b.get("id") or ""))
    cur["generated_at"] = now_iso
    name = target.get("name_ko") or target.get("name_ja")
    st = derive(target, now_iso)[0]
    note = " (시작 · 종료 중 하나를 아직 몰라 대기)" if st == "pending" else ""
    out["shown"] = st in ("hold", "announced", "live", "done")
    return done("added" if is_new else "updated", f"{'새 행사' if is_new else '갱신'} — {name}{note}", id=target["id"],
                undo={"type": "restore_banner", "id": target["id"], "before": before})


def restore(prev: dict, undo: dict, archive: dict, now_iso: str) -> tuple[dict, dict, str]:
    """되돌리기. 반환 (banners, archive, 결과 문구). 사본을 돌려준다."""
    cur = copy.deepcopy(prev or default_banners())
    arc = copy.deepcopy(archive or default_archive())
    bid, before = undo.get("id"), undo.get("before")
    lst = cur.setdefault("banners", [])
    now_row = next((b for b in lst if b.get("id") == bid), None)
    if undo.get("was_archived"):
        # 취소로 보관된 것 — 보관에서 꺼내 되살린다(이미 되살아났거나 없으면 건너뜀)
        if now_row:
            return cur, arc, "이미 활성에 있음"
        rows = arc.get("banners") or []
        hit = next((r for r in rows if r.get("id") == bid), None)
        if hit is None or before is None:
            return cur, arc, "보관에 없음"
        arc["banners"] = [r for r in rows if r is not hit]
        lst.append(before)
    elif before is None:
        if not now_row:
            return cur, arc, "이미 없음"
        lst.remove(now_row)                                  # 새로 만든 행사 — 지움
    else:
        if not now_row:
            return cur, arc, "그 뒤 사라짐(건너뜀)"
        lst[lst.index(now_row)] = before
    cur["banners"] = sorted(lst, key=lambda b: (b.get("start_at") or "", b.get("id") or ""))
    cur["generated_at"] = now_iso
    return cur, arc, "되돌림"


def sweep(prev: dict, archive: dict, now_iso: str) -> tuple[dict, dict, list[dict]]:
    """derive 가 gone 인 행사를 banners_archive.json 으로 — (새 banners, 새 archive, 옮긴 목록)."""
    keep, moved = [], []
    for b in (prev or {}).get("banners") or []:
        st, why = derive(b, now_iso)
        (moved if st == "gone" else keep).append(dict(b, archived_at=now_iso, archived_reason=why) if st == "gone" else b)
    if not moved:
        return prev, archive, []
    seen = {r.get("id") for r in (archive or {}).get("banners") or []}
    arc = dict(archive or default_archive())
    arc["banners"] = list(arc.get("banners") or []) + [m for m in moved if m["id"] not in seen]
    return dict(prev, banners=keep, generated_at=now_iso), arc, moved


_EDITABLE = ("name_ko", "name_ja", "start_at", "end_at", "image_urls")


def edit_banner(prev: dict, bid: str, patch: dict, now_iso: str) -> tuple[dict, bool, str | None]:
    """관리 페이지 수정. 반환 (banners, changed, 오류). `_EDITABLE` 키만 대입, 날짜는 검증, 보류 해제는 `hold: None` 으로."""
    cur = copy.deepcopy(prev or default_banners())
    b = next((x for x in cur.get("banners") or [] if x.get("id") == bid), None)
    if b is None:
        return prev, False, "행사를 찾을 수 없음"
    before = copy.deepcopy(b)
    for k in _EDITABLE:
        if k not in patch:
            continue
        v = patch[k]
        if k in ("start_at", "end_at"):
            if _parse_iso(v) is None:
                return prev, False, f"{k} 형식 오류"
        if k == "image_urls":
            v = _merge_images([], v if isinstance(v, list) else [])
        b[k] = v
    if "hold" in patch and patch["hold"] is None:
        b["hold"] = None
    gk = patch.get("gachas_ko")
    if isinstance(gk, dict):                     # {가챠 id: 한글 제목} — 빈 문자열이면 한글 없음(원제만 표시)
        for g in b.get("gachas") or []:
            if g.get("id") in gk:
                g["title_ko"] = (gk[g["id"]] or "").strip() or None
    if isinstance(patch.get("drop_gachas"), list):
        b["gachas"] = [g for g in b.get("gachas") or [] if g.get("id") not in patch["drop_gachas"]]
    s, e = _parse_iso(b.get("start_at")), _parse_iso(b.get("end_at"))
    if s is None or e is None or e < s:
        return prev, False, "시작 · 종료 날짜가 올바르지 않음(종료가 시작보다 앞서거나 비어 있음)"
    if b == before:
        return prev, False, None
    b["match_keys"] = _keys(b)
    b["last_updated"] = now_iso
    cur["generated_at"] = now_iso
    return cur, True, None


if __name__ == "__main__":
    N = "2026-10-02T03:00:00Z"                      # 10-02 12:00 KST
    EV = {"name_ja": "チャレンジライブイベント「アイの奔流 AtoZ」", "name_ko": "사랑은 격류 AtoZ 챌린지 라이브",
          "start_jst": "2026-09-30 18:00", "end_jst": "2026-10-08 20:59", "permanent": False}
    GA = {"title_ja": "「ワタシが主役のサイバーナイトガチャ」", "title_ko": "「내가 주인공 사이버 나이트 가챠」",
          "start_jst": None, "end_jst": None}
    P = lambda t, m=(): {"tweet_id": t, "media": list(m)}

    # 시각 변환
    assert parse_jst("2026-09-30 18:00") == ("2026-09-30T09:00:00Z", False)
    assert parse_jst("2026-10-08", end=True) == ("2026-10-08T14:59:00Z", False)
    assert parse_jst("2026-10-08") == ("2026-10-07T15:00:00Z", True)
    assert parse_jst("10/08") == (None, False) and parse_jst("2026-13-01") == (None, False)
    # 이름 키
    assert name_key("チャレンジライブイベント「アイの奔流 AtoZ」") == name_key("「アイの奔流 AtoZ」") == "アイの奔流atoz"
    assert make_id("「アイの奔流 AtoZ」") == make_id(EV["name_ja"])

    # 새 행사 + 가챠 + 이미지
    r = apply_judgement(default_banners(), {"action": "upsert", "banner_ref": None, "event": EV, "gacha": GA,
                                            "image_roles": ["event"], "image_for": "event", "reason": "r"}, P("111", ["https://x/e.jpg"]), N)
    assert r["mode"] == "added", r
    b = r["banners"]["banners"][0]
    assert b["start_at"] == "2026-09-30T09:00:00Z" and b["end_at"] == "2026-10-08T11:59:00Z"
    assert b["image_urls"] == ["https://x/e.jpg"] and len(b["gachas"]) == 1 and b["gachas"][0]["start_at"] is None
    assert derive(b, N) == ("live", "")
    assert derive(b, "2026-09-29T00:00:00Z") == ("announced", "")
    assert derive(b, "2026-10-08T12:00:00Z") == ("done", "")                 # 종료 직후 — 그날 자정까지 「종료」 표시
    assert derive(b, "2026-10-08T14:59:00Z") == ("done", "")                 # 10.08 23:59 KST
    assert derive(b, "2026-10-08T15:00:00Z") == ("gone", "ended")            # 10.09 00:00 KST — 내림
    # 가챠가 더 늦게 끝나면 완전 종료는 가챠 기준
    bg = dict(b, gachas=[dict(b["gachas"][0], end_at="2026-10-09T02:59:00Z")])
    assert derive(bg, "2026-10-08T12:00:00Z") == ("live", "") and derive(bg, "2026-10-09T03:00:00Z") == ("done", "")
    assert derive(bg, "2026-10-09T15:00:00Z") == ("gone", "ended")
    # 종료일을 모르는 개최 전 공지는 올린다(announced), 시작한 뒤에도 종료일이 없으면 안 올린다(pending)
    ns = {"id": "x", "name_ja": "x", "start_at": "2026-10-05T09:00:00Z", "end_at": None, "gachas": [], "last_updated": N}
    assert derive(ns, N) == ("announced", "") and derive(ns, "2026-10-05T09:00:00Z") == ("pending", "incomplete")
    P1 = r["banners"]

    # 같은 글 재전송 = dup, 새 사실 없는 재공지(판정 none)는 그대로
    assert apply_judgement(P1, {"action": "upsert", "event": EV, "gacha": None, "image_for": "none", "reason": ""}, P("111"), N)["mode"] == "dup"
    assert apply_judgement(P1, {"action": "none", "reason": "새 사실 없음"}, P("222"), N)["mode"] == "none"

    # 가챠 이미지 갱신(행사 정보 없이 banner_ref 로)
    r2 = apply_judgement(P1, {"action": "upsert", "banner_ref": b["id"], "event": None, "gacha": dict(GA, start_jst="2026-09-30 18:00", end_jst="2026-10-09 11:59"),
                              "image_roles": ["gacha"], "image_for": "gacha", "reason": ""}, P("333", ["https://x/g.jpg"]), N)
    g0 = r2["banners"]["banners"][0]["gachas"][0]
    assert r2["mode"] == "updated" and g0["image_urls"] == [] and g0["end_at"] == "2026-10-09T02:59:00Z", r2     # 가챠 이미지는 안 씀, 기간은 갱신

    # 종료일 없음 · 상시 · 120일 초과 → 안 올림
    noend = dict(EV, end_jst=None)
    rn = apply_judgement(default_banners(), {"action": "upsert", "event": noend, "gacha": None, "image_for": "none", "reason": ""}, P("1"), N)
    assert rn["mode"] == "added" and rn["shown"] is False and derive(rn["banners"]["banners"][0], N) == ("pending", "incomplete"), rn   # 종료일 없음 → 저장하되 안 보임
    assert visible(rn["banners"], N) == [] and len(active(rn["banners"], N)) == 1
    # 실측 흐름: 09-24 글(시작만) → 09-30 글(종료만) 로 채워져 올라감
    only_start = {"name_ja": EV["name_ja"], "name_ko": EV["name_ko"], "start_jst": "2026-09-28 15:00", "end_jst": None, "permanent": False}
    only_end = {"name_ja": EV["name_ja"], "name_ko": None, "start_jst": None, "end_jst": "2026-10-08 20:59", "permanent": False}
    a1 = apply_judgement(default_banners(), {"action": "upsert", "event": only_start, "gacha": GA, "image_for": "none", "reason": ""}, P("a1"), "2026-09-24T13:30:00Z")
    assert a1["mode"] == "added" and a1["shown"]                  # 시작 전 공지는 종료일을 몰라도 올린다(예정)
    a2 = apply_judgement(a1["banners"], {"action": "upsert", "banner_ref": a1["id"], "event": only_end, "gacha": None, "image_for": "none", "reason": ""}, P("a2"), "2026-09-30T09:13:00Z")
    assert a2["mode"] == "updated" and a2["shown"] and a2["banners"]["banners"][0]["start_at"] == "2026-09-28T06:00:00Z", a2
    # 날짜 재공지(「このあと18:00より」)로 시작일이 바뀜 — 보류 없이도 갱신, 이후 진행 중
    a3 = apply_judgement(a2["banners"], {"action": "upsert", "banner_ref": a1["id"], "event": {"name_ja": EV["name_ja"], "name_ko": None, "start_jst": "2026-09-30 18:00", "end_jst": None, "permanent": False},
                                         "gacha": None, "image_for": "none", "reason": ""}, P("a3"), "2026-09-30T09:20:00Z")
    assert a3["banners"]["banners"][0]["start_at"] == "2026-09-30T09:00:00Z" and a3["banners"]["banners"][0]["end_at"] == "2026-10-08T11:59:00Z"
    # 대기가 30일 넘게 방치되면 정리
    sp, spa, mv = sweep(a1["banners"], default_archive(), "2026-10-30T00:00:00Z")
    assert mv and mv[0]["archived_reason"] == "incomplete_expired" and sp["banners"] == []
    assert sweep(a1["banners"], default_archive(), "2026-10-01T00:00:00Z")[2] == []
    assert apply_judgement(default_banners(), {"action": "upsert", "event": dict(EV, permanent=True), "gacha": None, "image_for": "none", "reason": ""}, P("2"), N)["mode"] == "skip_permanent"
    longev = dict(EV, end_jst="2027-01-30 20:59")
    rl = apply_judgement(default_banners(), {"action": "upsert", "event": longev, "gacha": None, "image_for": "none", "reason": ""}, P("3"), N)
    assert rl["mode"] == "invalid" and "상시" in rl["detail"], rl
    bad = dict(EV, end_jst="2026-09-01 10:00")
    assert apply_judgement(default_banners(), {"action": "upsert", "event": bad, "gacha": None, "image_for": "none", "reason": ""}, P("4"), N)["mode"] == "invalid"

    # 보류 → 표시 · 15일 후 gone → 새 날짜 공지로 해제
    rh = apply_judgement(P1, {"action": "hold", "banner_ref": b["id"], "event": None, "gacha": None, "image_for": "none", "reason": ""}, P("444"), N)
    assert rh["mode"] == "held"
    hb = rh["banners"]["banners"][0]
    assert hb["hold"]["anchor"] == "2026-09-30T09:00:00Z" and hb["hold"]["until"] == "2026-10-15T09:00:00Z"
    assert derive(hb, N) == ("hold", "") and derive(hb, "2026-10-15T09:00:00Z") == ("gone", "hold_expired")
    ev2 = dict(EV, start_jst="2026-10-05 18:00", end_jst="2026-10-12 20:59")
    rr = apply_judgement(rh["banners"], {"action": "upsert", "banner_ref": b["id"], "event": ev2, "gacha": None, "image_for": "none", "reason": ""}, P("555"), N)
    nb = rr["banners"]["banners"][0]
    assert rr["mode"] == "updated" and nb["hold"] is None and nb["start_at"] == "2026-10-05T09:00:00Z" and nb["end_at"] == "2026-10-12T11:59:00Z", rr
    # 날짜 없는 갱신(이미지만)은 보류를 풀지 않는다
    ri = apply_judgement(rh["banners"], {"action": "upsert", "banner_ref": b["id"], "event": {"name_ja": EV["name_ja"], "name_ko": None, "start_jst": None, "end_jst": None, "permanent": False},
                                         "gacha": None, "image_for": "event", "reason": ""}, P("666", ["https://x/n.jpg"]), N)
    assert ri["banners"]["banners"][0]["hold"] is not None and ri["mode"] == "updated"

    # 취소 → 보관, 되돌리기 → 되살림
    rc = apply_judgement(P1, {"action": "cancel", "banner_ref": b["id"], "event": None, "gacha": None, "image_for": "none", "reason": ""}, P("777"), N)
    assert rc["mode"] == "cancelled" and rc["banners"]["banners"] == [] and rc["archive_add"][0]["archived_reason"] == "cancelled"
    arc = {"banners": rc["archive_add"]}
    back, arc2, msg = restore(rc["banners"], rc["undo"], arc, N)
    assert msg == "되돌림" and back["banners"][0]["id"] == b["id"] and arc2["banners"] == [], msg
    # 새로 만든 것 되돌리면 삭제 / 그 뒤 사라졌으면 건너뜀
    back2, _, m2 = restore(P1, r["undo"], default_archive(), N)
    assert m2 == "되돌림" and back2["banners"] == []
    assert restore(default_banners(), r["undo"], default_archive(), N)[2] == "이미 없음"
    # 갱신 되돌리기
    back3, _, m3 = restore(r2["banners"], r2["undo"], default_archive(), N)
    assert m3 == "되돌림" and back3["banners"][0]["gachas"][0]["end_at"] is None

    # sweep
    sw, sa, moved = sweep(P1, default_archive(), "2026-10-09T00:00:00Z")
    assert sw["banners"] == [] and moved[0]["archived_reason"] == "ended" and len(sa["banners"]) == 1
    assert sweep(P1, default_archive(), N)[2] == []

    # 이미지마다 용도를 판정(image_roles)했으면 그대로 나눈다 — 행사 2장 · 가챠 1장, none 은 안 붙임
    rr = apply_judgement(default_banners(), {"action": "upsert", "banner_ref": None, "event": EV, "gacha": GA,
                                             "image_roles": ["none", "event", "gacha", "none"], "image_for": "none", "reason": ""},
                         P("rr1", ["https://x/1.jpg", "https://x/2.jpg", "https://x/3.jpg", "https://x/4.jpg"]), N)
    rb = rr["banners"]["banners"][0]
    assert rb["image_urls"] == ["https://x/2.jpg"] and rb["gachas"][0]["image_urls"] == [], rb      # event 용도만, 가챠 이미지는 안 씀
    # 용도를 못 정했으면(roles 없음 · 장수 불일치) 이미지를 안 붙인다
    rn2 = apply_judgement(default_banners(), {"action": "upsert", "banner_ref": None, "event": EV, "gacha": None, "image_for": "event", "reason": ""},
                          P("rn2", ["https://x/1.jpg"]), N)
    assert rn2["banners"]["banners"][0]["image_urls"] == []

    # 이미지 용도가 none 이어도 upsert 글의 첨부 이미지는 행사(가챠만 소개한 글이면 가챠)에 붙는다
    im = apply_judgement(default_banners(), {"action": "upsert", "banner_ref": None, "event": EV, "gacha": None, "image_roles": ["event"], "image_for": "none", "reason": ""}, P("im1", ["https://x/a.jpg"]), N)
    assert im["banners"]["banners"][0]["image_urls"] == ["https://x/a.jpg"]

    # 가챠만 소개한 글이 행사 칸에 들어와도 행사 날짜는 그대로, 가챠가 붙는다
    gx = apply_judgement(P1, {"action": "upsert", "banner_ref": b["id"], "gacha": None, "image_for": "none", "reason": "",
                              "event": {"name_ja": "「新ガチャ」", "name_ko": "새 가챠", "start_jst": "2026-10-01 18:00", "end_jst": None, "permanent": False}}, P("gx"), N)
    gb = gx["banners"]["banners"][0]
    assert gb["start_at"] == b["start_at"] and any(g["title_ja"] == "「新ガチャ」" and g["start_at"] == "2026-10-01T09:00:00Z" for g in gb["gachas"]), gx

    # 소식 중복 방지
    assert covers_text(P1["banners"], "チャレンジライブイベント「アイの奔流 AtoZ」開催🎧") is not None
    assert covers_text(P1["banners"], "「ワタシが主役のサイバーナイトガチャ」このあと18:00より") is not None
    assert covers_text(P1["banners"], "緊急メンテナンス早期完了のお知らせ") is None
    assert covers_text([], "アイの奔流 AtoZ") is None
    fl = for_llm(P1, N)
    assert fl[0]["start_jst"] == "2026-09-30 18:00" and fl[0]["end_jst"] == "2026-10-08 20:59" and fl[0]["gachas"], fl

    # 수정
    ed, ch, er = edit_banner(P1, b["id"], {"name_ko": "수정"}, N)
    assert ch and er is None and ed["banners"][0]["name_ko"] == "수정"
    assert edit_banner(P1, b["id"], {"end_at": "2026-09-01T00:00:00Z"}, N)[2] is not None
    assert edit_banner(P1, "nope", {}, N)[2] is not None
    gid = P1["banners"][0]["gachas"][0]["id"]
    eg, chg, _ = edit_banner(P1, b["id"], {"gachas_ko": {gid: "수정한 가챠"}}, N)
    assert chg and eg["banners"][0]["gachas"][0]["title_ko"] == "수정한 가챠"
    ed2, chg2, _ = edit_banner(P1, b["id"], {"drop_gachas": [gid]}, N)
    assert chg2 and ed2["banners"][0]["gachas"] == []
    print("[PASS] banners self-test (시각 · 이름 키 · 반영 · 보류/재개 · 취소/되돌리기 · sweep · 소식 겹침 · 수정)")
