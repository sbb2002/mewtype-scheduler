"""(v4a) 행사 배너 — banners.json / banners_archive.json 계약 + 판정 반영·상태 파생·정리 (순수 함수).

계약: docs/SPEC.md 계약 J. 용어: docs/TERMINOLOGY.md 「행사 배너 용어」.

banners.json
  { "generated_at": "...Z",
    "banners": [ { id, name_ja, name_ko, match_keys[], image_urls[], start_at, end_at, start_time_tbd?,
                   hold: null | {anchor, until}, gachas: [ {id, title_ja, title_ko, image_urls[], start_at, end_at} ],
                   src_ids[], first_seen, last_updated, gacha_only? } ] }      # gacha_only = (v4.5.10) 가챠 단독 배너
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
    """(옛 `llm.banner_judge` 의 active 인자 — v4.5.10 부터 판정에 안 쓴다) 대기 포함 활성 행사를 JST 문자열로."""
    return [{"id": b["id"], "name_ja": b.get("name_ja"), "start_jst": to_jst(b.get("start_at")),
             "end_jst": to_jst(b.get("end_at")), "hold": bool(b.get("hold")),
             "gachas": [g.get("title_ja") for g in b.get("gachas") or []],
             # (v4.5.3) 가챠 기간도 보여 준다 — 전엔 제목만 줘서, 날짜 없는 가챠 소개 글에 LLM 이 행사 기간을 가챠 기간으로 옮겨 적었다
             "gacha_periods": [f'{g.get("title_ja")} {to_jst(g.get("start_at")) or "?"}~{to_jst(g.get("end_at")) or "?"}'
                               for g in b.get("gachas") or []]} for b in active(prev, now_iso)]


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
    end_date_only = bool(e_raw) and (_JST_RE.match(e_raw) or [None] * 6)[4] is None
    return {"start_at": start, "end_at": end, "start_time_tbd": tbd, "end_date_only": end_date_only}, None


def _gacha_host(lst: list[dict], ga: dict, now: datetime, now_iso: str) -> dict | None:
    """행사 칸 없이 온 가챠(판정이 banner_ref 도 안 준 경우)가 딸릴 행사 — 가챠 시작이 그 행사 기간 안(시작 1시간 전 허용)인 것.

    여러 개면 시작 시각이 가장 가까운 행사. 없으면 None(→ 호출부가 가챠를 단독 행사로 올린다).
    """
    gt, err = _times(ga, now)
    gs = _parse_iso((gt or {}).get("start_at")) if not err else None
    if gs is None:
        return None
    best = None
    for b in lst:
        if derive(b, now_iso)[0] == "gone":
            continue
        bs, be = _parse_iso(b.get("start_at")), full_end(b)
        if bs is None or gs < bs - timedelta(hours=1) or (be is not None and gs > be):
            continue
        if best is None or abs(gs - bs) < abs(gs - _parse_iso(best["start_at"])):
            best = b
    return best


_DAY_WORDS = {"本日": 0, "今日": 0, "今夜": 0, "このあと": 0, "この後": 0, "まもなく": 0, "明日": 1, "あす": 1, "あした": 1}


def date_evidenced(iso: str | None, text: str, ref_iso: str | None) -> bool:
    """(v4.5.3) 이 시각(UTC ISO)의 **JST 날짜**가 글 · 이미지 글자에 실제로 적혀 있나 — 「10月28日」 「10/28」 「10.28」 표기,
    또는 상대 표현(本日 · 今日 · 明日 …)이 글 게시 시각(ref_iso) 기준으로 그 날짜를 가리킬 때."""
    dt = _parse_iso(iso)
    if dt is None:
        return False
    jd = dt.astimezone(_JST)
    t = unicodedata.normalize("NFKC", text or "")
    m, d = jd.month, jd.day
    if re.search(rf"(?<!\d)0?{m}\s*月\s*0?{d}\s*日", t) or re.search(rf"(?<!\d)0?{m}\s*[/.]\s*0?{d}(?!\d)", t):
        return True
    ref = _parse_iso(ref_iso)
    if ref is not None:
        rd = ref.astimezone(_JST).date()
        return any(w in t and rd + timedelta(days=off) == jd.date() for w, off in _DAY_WORDS.items())
    return False


def apply_judgement(prev: dict, j: dict, post: dict, now_iso: str, *, check_dup: bool = True) -> dict:
    """행사 판정 1건을 반영한다. 반환:

      {"banners": 새 목록(dict), "archive_add": [보관할 항목], "mode": str, "detail": str, "undo": dict|None, "id": str|None}

    mode ∈ added · updated · held · cancelled · none · dup · invalid · skip_permanent
    shown: 이 반영 뒤 그 행사가 화면에 올라가는가(대기면 False).  post = {"tweet_id": str, "media": [url…]}.  `prev` 는 바꾸지 않는다(사본).

    (v4.5.3) post 에 "text"(글 본문 + 이미지 OCR 글자)가 있으면 **이미 있는 날짜를 바꿀 때 근거를 확인**한다 — 새 날짜가 그 글자에
    적혀 있지 않으면(`date_evidenced`) 바꾸지 않는다. 날짜만 아는 값(「10月18日より」)이 같은 날의 시각까지 아는 값을 덮지도 않는다.
    비어 있던 날짜를 채우는 것 · 새 행사 · 운영자 판단(텍스트 없음)은 그대로. 계기: 2026-10-19 날짜 없는 가챠 소개 글 3건이 가챠 기간을
    행사 기간(종료 10/26)과 「10月18日」 00:00 으로 덮었다(정답 10/18 15:00 ~ 10/28 14:59).

    (v4.5.10) check_dup=False — 한 글에서 나온 여러 반영(`apply_post`)의 두 번째부터는 「이미 반영한 글」 검사를 건너뛴다(글 단위 검사는 apply_post 가 먼저 한다).
    j["gacha_only"] = True 면 새 행사에 `gacha_only` 표시(이벤트 없이 열린 가챠 단독 배너 — `plan_post` 2순위).
    """
    now = _parse_iso(now_iso)
    cur = copy.deepcopy(prev or default_banners())
    lst: list[dict] = cur.setdefault("banners", [])
    out = {"banners": cur, "archive_add": [], "mode": "none", "detail": "", "undo": None, "id": None, "shown": False}
    tid = str(post.get("tweet_id") or "")

    ev_text = post.get("text") if isinstance(post.get("text"), str) else None
    ref_iso = post.get("posted_at") or now_iso
    ignored: list[str] = []                  # 근거가 없어 바꾸지 않은 날짜(상세 문구에 남긴다)

    def done(mode, detail, **kw):
        if ignored and mode in ("updated", "none"):
            detail = (detail + " · " if detail else "") + "근거 없는 날짜 변경 무시: " + ", ".join(ignored)
        out.update(mode=mode, detail=detail, **kw)
        return out

    def change_ok(label: str, old: str | None, new: str | None, date_only: bool) -> bool:
        """이미 있는 날짜(old)를 new 로 바꿔도 되나. 비어 있던 값 채우기는 허용."""
        if not new or new == old:
            return False
        if not old:
            return True
        od, nd = _parse_iso(old), _parse_iso(new)
        if date_only and od and nd and od.astimezone(_JST).date() == nd.astimezone(_JST).date():
            ignored.append(f"{label} {to_jst(new)}(날짜만 — 기존 {to_jst(old)} 유지)")
            return False
        if ev_text is not None and not date_evidenced(new, ev_text, ref_iso):
            ignored.append(f"{label} {to_jst(new)}(글 · 이미지에 없음 — 기존 {to_jst(old)} 유지)")
            return False
        return True

    if not isinstance(j, dict) or j.get("action") not in ACTIONS:
        return done("invalid", "판정 형식 오류")
    action = j["action"]
    if action == "none":
        return done("none", (j.get("reason") or "")[:120])
    # (v4.5.9) check_dup=False — 이미지 판독 예비(Cloud Vision)로 같은 글을 다시 반영할 때(`telegram_app._ocr_fallback_apply`)
    if check_dup and tid and any(tid in (b.get("src_ids") or []) for b in lst):
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

    # 2026-10-17 운영자 결정(v4.3.3): 밴드 · 멤버와 무관하게 행사 · 가챠는 전부 올린다. 판정이 가챠만 주고 행사 칸도 banner_ref 도 비운
    # 경우(실측: 같은 날 시작하는 가챠 글) — 기간이 겹치는 행사에 딸리고, 어느 행사에도 안 맞는 단독 가챠는 가챠 제목을 이름으로 한 새 행사로 올린다.
    # 판정이 가챠 제목을 행사 칸에도 그대로 넣는 경우(실측: 같은 글 3회 중 2회)도 같은 가챠 단독 글로 본다.
    if (action == "upsert" and ga and (ga.get("title_ja") or "").strip() and not target
            and (not (ev and (ev.get("name_ja") or "").strip()) or name_key(ev["name_ja"]) == name_key(ga["title_ja"]))):
        target = _gacha_host(lst, ga, now, now_iso)
        if target is not None:
            ev = None
        else:
            ev = {"name_ja": ga["title_ja"], "name_ko": ga.get("title_ko"), "start_jst": ga.get("start_jst") or (ev or {}).get("start_jst"),
                  "end_jst": ga.get("end_jst") or (ev or {}).get("end_jst"), "permanent": False}
            ga = None

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
        if j.get("gacha_only"):
            target["gacha_only"] = True
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
        if change_ok("행사 시작", target.get("start_at"), et["start_at"], bool(et["start_time_tbd"])):
            target["start_at"], target["start_time_tbd"] = et["start_at"], (bool(et["start_time_tbd"]) or None)
            dated = True
        if change_ok("행사 종료", target.get("end_at"), et["end_at"], bool(et.get("end_date_only"))):
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
            gt = {"start_at": None, "end_at": None, "start_time_tbd": False, "end_date_only": False}
        title_ja = ga["title_ja"].strip()
        gk = name_key(title_ja)
        g = next((x for x in target["gachas"] if name_key(x.get("title_ja")) == gk), None)
        if gk == name_key(target.get("name_ja")):          # 가챠 자체가 행사 카드인 경우(단독 가챠) — 새 기간은 카드에 반영, 하위 블록은 안 만든다
            if change_ok("가챠 시작", target.get("start_at"), gt["start_at"], bool(gt["start_time_tbd"])):
                target["start_at"], target["start_time_tbd"] = gt["start_at"], (bool(gt["start_time_tbd"]) or None)
            if change_ok("가챠 종료", target.get("end_at"), gt["end_at"], bool(gt.get("end_date_only"))):
                target["end_at"] = gt["end_at"]
            g = None
        elif g is None:
            if len(target["gachas"]) < MAX_GACHAS:
                g = {"id": _gacha_id(title_ja), "title_ja": title_ja, "title_ko": (ga.get("title_ko") or "").strip() or None,
                     "image_urls": [], "start_at": gt["start_at"], "end_at": gt["end_at"]}
                target["gachas"].append(g)
        else:
            if ga.get("title_ko") and not g.get("title_ko"):
                g["title_ko"] = ga["title_ko"].strip()
            if change_ok("가챠 시작", g.get("start_at"), gt["start_at"], bool(gt["start_time_tbd"])):
                g["start_at"] = gt["start_at"]
            if change_ok("가챠 종료", g.get("end_at"), gt["end_at"], bool(gt.get("end_date_only"))):
                g["end_at"] = gt["end_at"]
    else:
        g = None

    # 이미지 — 어느 카드에 붙일지는 판정이 정한다
    # 이미지 — 2026-10-02 운영자 결정: X 트윗에서 걸린 이미지 중 **행사 키비주얼**(로고 · 일러스트 · 개최기간만 있는 온전한 그림)만 쓴다.
    # 소개 카드 · 방송 화면 캡처 · 가챠 이미지(정사각형이라 배너 비율에 안 맞고 필수도 아님)는 안 쓴다. 판정이 이미지 용도를 못 정했으면
    # (비전 실패 등) 안 붙인다 — 잘못된 이미지가 올라가는 것보다 이미지가 없는 쪽이 낫다.
    media = [u for u in (post.get("media") or []) if isinstance(u, str)]
    roles = j.get("image_roles") if isinstance(j.get("image_roles"), list) else []
    if target.get("gacha_only"):
        # (v4.5.11 운영자 결정) 가챠 단독 배너는 이벤트 키비주얼이 없으니 가챠 이미지를 쓴다 — 이미지가 아직 없을 때만(가챠 소개 카드가 쌓이지 않게).
        # 용도 판정이 있으면 none(소개 카드 · 캡처)만 빼고, 판정이 없으면(비전 실패 등) 걸린 이미지를 그대로 쓴다.
        if media and not target.get("image_urls"):
            imgs = [u for u, r in zip(media, roles) if r != "none"] if len(roles) == len(media) else list(media)
            if imgs:
                target["image_urls"] = _merge_images([], imgs)
    elif media and len(roles) == len(media):
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


# ── (v4.5.10) 글 1건 → 반영 계획 — 2026-10-21 운영자 확정 기준 ─────────────────────────────
# LLM 은 「게임 안/밖」(llm.banner_scope)과 「이벤트 · 가챠 옮겨 적기」(llm.banner_extract)만 하고, 배너를 어떻게 할지는 여기서 코드가 정한다.
#   1순위 인게임 이벤트(게임 속 인물들의 스토리가 있는 이벤트) — 가챠는 같은 글의 이벤트, 아니면 시작 시각이 같은 이벤트에 딸린다.
#   2순위 이벤트 없이 다른 행사로 열린 한시 가챠 — 가챠 단독 배너(`gacha_only`).
#   미션 · 로그인 보너스 등은 추출 단계에서 빠진다(버림). 게임 밖 행사는 소식(호출부).
#   새 배너는 **시작 일자가 글 · 이미지 글자에 적혀 있을 때만**(종료는 나중 글 · 이미지로 채운다).
#   같은 이벤트를 별도 배너로 올리지 않는다 — 이름(포함 관계까지) 또는 같은 시작 시각의 이벤트 배너가 있으면 그 배너를 갱신한다.

def _similar(a: str | None, b: str | None) -> bool:
    ka, kb = name_key(a), name_key(b)
    return bool(ka and kb) and (ka == kb or (min(len(ka), len(kb)) >= _MIN_KEY_LEN and (ka in kb or kb in ka)))


def plan_post(prev: dict, items: list[dict], text: str, posted_at: str | None, now_iso: str,
              image_roles: list[str] | None = None) -> list[dict]:
    """추출 항목 → 반영 단계 목록 [{"desc": 설명, "j": apply_judgement 판정 | None, "merge": (가챠 단독 배너 id, 이벤트 이름) | None}].

    j 가 None 이고 merge 도 없으면 「버림」(desc 에 이유). `text` = 본문 + 이미지 글자 — 날짜 근거 확인(`date_evidenced`)에 쓴다.
    image_roles 는 첫 이벤트 단계에만 붙인다(키비주얼은 이벤트 배너에만 — 가챠 이미지는 안 쓴다, 2026-10-02 운영자 결정).
    (v4.5.11) 이벤트 단계가 없으면 가챠 단독 배너 단계에 붙인다(가챠 단독 배너는 가챠 이미지를 쓴다 — `apply_judgement`).
    """
    lst = active(prev, now_iso)
    ref_iso = posted_at or now_iso

    def evid(v, end=False):
        iso = parse_jst(v, end=end)[0] if v else None
        return v if iso and date_evidenced(iso, text or "", ref_iso) else None

    def find(title):
        for b in lst:
            if _similar(title, b.get("name_ja")):
                return b, None
            for g in b.get("gachas") or []:
                if _similar(title, g.get("title_ja")):
                    return b, g
        return None, None

    def event_at(s_iso, date_only=False):
        """시작이 같은 이벤트 배너. 날짜만 아는 값(「10月18日より開催中」)이면 시작 날짜(JST)가 같은 이벤트."""
        if not s_iso:
            return None
        day = _parse_iso(s_iso).astimezone(_JST).date()
        return next((b for b in lst if not b.get("gacha_only") and b.get("start_at") and (
            b["start_at"] == s_iso or (date_only and _parse_iso(b["start_at"]).astimezone(_JST).date() == day))), None)

    steps: list[dict] = []
    made: list[str] = []                  # 이 글이 새로 만든 이벤트 이름
    roles_left = list(image_roles or [])

    def step(desc, j=None, merge=None):
        steps.append({"desc": desc, "j": j, "merge": merge})

    for it in [i for i in items if i.get("kind") == "event"] + [i for i in items if i.get("kind") == "gacha"]:
        t = (it.get("title_ja") or "").strip()
        if not t:
            continue
        ko = it.get("title_ko") or None
        s, e = evid(it.get("start_jst")), evid(it.get("end_jst"), end=True)
        s_iso, s_tbd = parse_jst(s) if s else (None, False)
        when = f"{s or '시작?'} ~ {e or '종료?'}"
        b, g = find(t)
        is_event = it["kind"] == "event"
        if b is None and is_event and s_iso:
            b = event_at(s_iso, s_tbd)
            if b is not None:
                step(f"이벤트 「{t}」 — 이름은 다르지만 시작이 같은 이벤트 배너 「{b.get('name_ja')}」로 봄")
        status = it.get("status") or "normal"
        if status in ("postponed", "cancelled"):
            if b is None:
                step(f"{'이벤트' if is_event else '가챠'} 「{t}」 {'보류' if status == 'postponed' else '취소'} — 대상 배너 없음(버림)")
            else:
                act = "hold" if status == "postponed" else "cancel"
                step(f"「{b.get('name_ja')}」 {'보류 표시' if act == 'hold' else '취소로 내림'}", {"action": act, "banner_ref": b["id"], "event": None, "gacha": None})
            continue
        if is_event:
            ev = {"name_ja": t, "name_ko": ko, "start_jst": s, "end_jst": e, "permanent": False}
            j = None
            if b is not None and not b.get("gacha_only"):
                j = {"action": "upsert", "banner_ref": b["id"], "event": dict(ev, name_ja=b.get("name_ja")), "gacha": None}
                step(f"이벤트 「{t}」({when}) 기존 배너 갱신", j)
            elif s:
                j = {"action": "upsert", "banner_ref": None, "event": ev, "gacha": None}
                step(f"이벤트 「{t}」({when}) 새 배너", j)
                made.append(t)
                for x in lst:            # 먼저 가챠 단독으로 올라 있던 같은 시작의 가챠 → 이 이벤트 밑으로
                    if x.get("gacha_only") and x.get("start_at") == s_iso:
                        step(f"가챠 단독 배너 「{x.get('name_ja')}」 → 이벤트 「{t}」 밑으로", merge=(x["id"], t))
            else:
                step(f"이벤트 「{t}」 버림 — 시작 일자가 적혀 있지 않고 같은 이벤트 배너도 없음")
            if j is not None and roles_left:
                j["image_roles"], roles_left = roles_left, []
            continue
        ga = {"title_ja": t, "title_ko": ko, "start_jst": s, "end_jst": e}
        if b is not None:
            if b.get("gacha_only"):
                gj = {"action": "upsert", "banner_ref": b["id"], "event": {
                    "name_ja": b.get("name_ja"), "name_ko": ko, "start_jst": s, "end_jst": e, "permanent": False}, "gacha": None}
                if roles_left and not made:
                    gj["image_roles"], roles_left = roles_left, []
                step(f"가챠 「{t}」({when}) 가챠 단독 배너 갱신", gj)
            else:
                step(f"가챠 「{t}」({when}) 「{b.get('name_ja')}」의 가챠 갱신", {"action": "upsert", "banner_ref": b["id"], "event": None,
                     "gacha": dict(ga, title_ja=(g or {}).get("title_ja") or t)})
        elif made:
            step(f"가챠 「{t}」({when}) 같은 글의 이벤트 「{made[0]}」에 붙임",
                 {"action": "upsert", "banner_ref": make_id(made[0]), "event": None, "gacha": ga})
        elif s_iso and event_at(s_iso, s_tbd) is not None:
            h = event_at(s_iso, s_tbd)
            step(f"가챠 「{t}」({when}) 시작이 같은 이벤트 「{h.get('name_ja')}」에 붙임",
                 {"action": "upsert", "banner_ref": h["id"], "event": None, "gacha": ga})
        elif s and not s_tbd:
            gj = {"action": "upsert", "banner_ref": None, "gacha_only": True,
                  "event": {"name_ja": t, "name_ko": ko, "start_jst": s, "end_jst": e, "permanent": False}, "gacha": None}
            if roles_left and not made:
                gj["image_roles"], roles_left = roles_left, []      # (v4.5.11) 가챠 단독 배너도 이미지를 쓴다
            step(f"가챠 「{t}」({when}) 붙을 이벤트 없음 → 가챠 단독 배너", gj)
        elif s:
            # 날짜만 있는 가챠(「10月18日より開催中」 — 소개 · 재공지 글)로는 가챠 단독 배너를 새로 만들지 않는다(개최 공지에는 시각이 있다)
            step(f"가챠 「{t}」 버림 — 시작이 날짜만({s})이고 같은 날 시작하는 이벤트 · 같은 가챠 배너도 없음")
        else:
            step(f"가챠 「{t}」 버림 — 시작 일자가 적혀 있지 않고 붙을 배너도 없음")
    return steps


_MODE_RANK = ("added", "cancelled", "held", "updated")


def apply_post(prev: dict, steps: list[dict], post: dict, now_iso: str, *, check_dup: bool = True) -> dict:
    """`plan_post` 단계들을 차례로 반영한다 — 반환 형식은 `apply_judgement` 와 같다(mode 는 가장 큰 변화, detail 은 단계별 결과를 이음).

    undo = {"type": "restore_banner", "items": [단계별 되돌리기 …]} — `restore` 가 거꾸로 풀어 한 번에 되돌린다.
    같은 글(tweet_id)을 이미 반영했으면 아무것도 안 하고 dup. (v4.5.9) check_dup=False — 이미지 판독 예비(Cloud Vision)로
    같은 글을 다시 반영할 때(`telegram_app._ocr_fallback_apply`)는 이 검사를 건너뛴다.
    """
    cur = copy.deepcopy(prev or default_banners())
    tid = str(post.get("tweet_id") or "")
    out = {"banners": cur, "archive_add": [], "mode": "none", "detail": "", "undo": None, "id": None, "shown": False}
    if check_dup and tid and any(tid in (b.get("src_ids") or []) for b in cur.get("banners") or []):
        out.update(mode="dup", detail="이미 반영한 글")
        return out
    modes, details, undos = [], [], []
    for st in steps:
        if st.get("merge"):
            gid, ename = st["merge"]
            lst = cur["banners"]
            gb = next((x for x in lst if x.get("id") == gid), None)
            host = next((x for x in lst if x.get("id") == make_id(ename)), None)
            if gb is None or host is None:
                details.append(st["desc"] + " — 건너뜀(대상 없음)")
                continue
            undos += [{"type": "restore_banner", "id": gid, "before": copy.deepcopy(gb), "was_removed": True},
                      {"type": "restore_banner", "id": host["id"], "before": copy.deepcopy(host)}]
            if not any(name_key(x.get("title_ja")) == name_key(gb.get("name_ja")) for x in host.get("gachas") or []):
                host.setdefault("gachas", []).append({"id": _gacha_id(gb.get("name_ja") or ""), "title_ja": gb.get("name_ja"),
                                                      "title_ko": gb.get("name_ko"), "image_urls": [],
                                                      "start_at": gb.get("start_at"), "end_at": gb.get("end_at")})
            host["src_ids"] = (list(host.get("src_ids") or []) + [x for x in gb.get("src_ids") or [] if x not in (host.get("src_ids") or [])])[-20:]
            host["match_keys"] = _keys(host)
            host["last_updated"] = now_iso
            lst.remove(gb)
            modes.append("updated")
            details.append(st["desc"])
            continue
        if st.get("j") is None:
            details.append(st["desc"])
            continue
        r = apply_judgement(cur, st["j"], post, now_iso, check_dup=False)
        modes.append(r["mode"])
        details.append(f"{st['desc']} → {r['mode']}" + (f" ({r['detail']})" if r["mode"] in ("invalid", "none") and r["detail"] else ""))
        if r["mode"] in _MODE_RANK:
            cur = r["banners"]
            out["archive_add"] += r["archive_add"]
            if r["undo"]:
                undos.append(r["undo"])
            out["id"] = out["id"] or r["id"]
            out["shown"] = out["shown"] or r["shown"]
    mode = next((m for m in _MODE_RANK if m in modes), None) or next((m for m in modes if m not in ("none",)), "none")
    if mode in _MODE_RANK:
        cur["banners"] = sorted(cur.get("banners") or [], key=lambda b: (b.get("start_at") or "", b.get("id") or ""))
        cur["generated_at"] = now_iso
    out.update(banners=cur, mode=mode, detail=" · ".join(details)[:400] or "뽑을 이벤트 · 가챠 없음",
               undo={"type": "restore_banner", "items": undos} if undos else None)
    return out


def restore(prev: dict, undo: dict, archive: dict, now_iso: str) -> tuple[dict, dict, str]:
    """되돌리기. 반환 (banners, archive, 결과 문구). 사본을 돌려준다.

    (v4.5.10) undo["items"](한 글이 여러 배너를 바꾼 경우 — `apply_post`)면 거꾸로 하나씩 풀고, 하나라도 풀리면 「되돌림」."""
    if isinstance(undo.get("items"), list):
        cur, arc, msgs = prev, archive, []
        for u in reversed(undo["items"]):
            cur, arc, m = _restore_one(cur, u, arc, now_iso)
            msgs.append(m)
        return cur, arc, "되돌림" if "되돌림" in msgs else (msgs[0] if msgs else "되돌릴 것 없음")
    return _restore_one(prev, undo, archive, now_iso)


def _restore_one(prev: dict, undo: dict, archive: dict, now_iso: str) -> tuple[dict, dict, str]:
    """배너 하나 되돌리기. was_archived = 취소로 보관된 것 되살림 · (v4.5.10) was_removed = 다른 배너에 합쳐져 사라진 것 되살림 ·
    before=None = 새로 만든 것 지움 · 그 밖 = before 로 바꿈."""
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
    elif undo.get("was_removed"):
        if now_row:
            return cur, arc, "이미 활성에 있음"
        if before is None:
            return cur, arc, "되살릴 내용 없음"
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
            lst = v if isinstance(v, list) else []
            bad = [u for u in lst if not (isinstance(u, str) and re.match(r"^https?://\S+$", u.strip()))]
            if bad:
                return prev, False, f"이미지 링크는 http(s):// 로 시작해야 합니다: {str(bad[0])[:60]}"
            if len(lst) > MAX_IMAGES:
                return prev, False, f"이미지는 최대 {MAX_IMAGES}장입니다"
            v = _merge_images([], [u.strip() for u in lst])
        b[k] = v
    if "hold" in patch and patch["hold"] is None:
        b["hold"] = None
    gj = patch.get("gachas_ja")
    if isinstance(gj, dict):                     # {가챠 id: 일본어 원제} — 빈 값은 무시(원문은 비울 수 없음). id 는 안 바뀐다
        for g in b.get("gachas") or []:
            v = gj.get(g.get("id"))
            if isinstance(v, str) and v.strip():
                g["title_ja"] = v.strip()
    gk = patch.get("gachas_ko")
    if isinstance(gk, dict):                     # {가챠 id: 한글 제목} — 빈 문자열이면 한글 없음(원제만 표시)
        for g in b.get("gachas") or []:
            if g.get("id") in gk:
                g["title_ko"] = (gk[g["id"]] or "").strip() or None
    gp = patch.get("gachas_period")
    if isinstance(gp, dict):                     # {가챠 id: {start_at, end_at}} — 빈 값(None · "")이면 「행사와 같음」
        for g in b.get("gachas") or []:
            o = gp.get(g.get("id"))
            if not isinstance(o, dict):
                continue
            for key in ("start_at", "end_at"):
                if key in o:
                    val = o[key]
                    if val in (None, ""):
                        g[key] = None
                    elif _parse_iso(val) is None:
                        return prev, False, f"가챠 {key} 형식 오류"
                    else:
                        g[key] = val
            gs, ge = _parse_iso(g.get("start_at")), _parse_iso(g.get("end_at"))
            if gs and ge and ge < gs:
                return prev, False, "가챠 종료가 시작보다 앞섭니다"
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

    # (v4.3.3) 행사 칸 · banner_ref 없이 온 가챠 — 기간이 겹치는 행사에 딸리고, 어느 행사에도 안 맞으면 가챠 제목이 이름인 단독 행사로 올린다
    gonly = {"title_ja": "差し込む光、始まりのとき", "title_ko": "비치는 빛, 시작의 때", "start_jst": "2026-09-30 18:00", "end_jst": None}
    rg = apply_judgement(P1, {"action": "upsert", "banner_ref": None, "event": None, "gacha": gonly, "image_for": "none", "reason": ""}, P("g1"), N)
    assert rg["mode"] == "updated" and rg["id"] == b["id"] and len(rg["banners"]["banners"]) == 1, rg
    assert [x["title_ja"] for x in rg["banners"]["banners"][0]["gachas"]] == [GA["title_ja"].strip(), "差し込む光、始まりのとき"], rg
    rg2 = apply_judgement(P1, {"action": "upsert", "banner_ref": None, "gacha": gonly, "image_for": "none", "reason": "",
                               "event": {"name_ja": gonly["title_ja"], "name_ko": gonly["title_ko"], "start_jst": None, "end_jst": None, "permanent": False}}, P("g1b"), N)
    assert rg2["mode"] == "updated" and rg2["id"] == b["id"] and len(rg2["banners"]["banners"][0]["gachas"]) == 2, rg2     # 가챠 제목을 행사 칸에도 넣은 판정
    alone = dict(gonly, title_ja="はじめてを奏でる光彩讃歌ガチャ", start_jst="2026-10-18 15:00")
    ra = apply_judgement(P1, {"action": "upsert", "banner_ref": None, "event": None, "gacha": alone, "image_for": "none", "reason": ""}, P("g2"), "2026-10-17T09:06:00Z")
    assert ra["mode"] == "added" and len(ra["banners"]["banners"]) == 2, ra          # 행사(10-08 종료)와 안 겹침 → 단독 행사
    ab = next(x for x in ra["banners"]["banners"] if x["id"] == ra["id"])
    assert ab["name_ja"] == "はじめてを奏でる光彩讃歌ガチャ" and ab["gachas"] == [] and ab["start_at"] == "2026-10-18T06:00:00Z" and ab["end_at"] is None
    assert derive(ab, "2026-10-17T09:06:00Z") == ("announced", "")                    # 종료일 몰라도 개최 전엔 올림
    # 단독 가챠에 종료일이 뒤늦게 들어오면 카드 기간에 반영(하위 블록 안 만듦)
    rb = apply_judgement(ra["banners"], {"action": "upsert", "banner_ref": ab["id"], "event": None, "gacha": dict(alone, end_jst="2026-10-25 14:59"),
                                         "image_for": "none", "reason": ""}, P("g3"), "2026-10-18T06:00:00Z")
    bb = next(x for x in rb["banners"]["banners"] if x["id"] == ab["id"])
    assert rb["mode"] == "updated" and bb["end_at"] == "2026-10-25T05:59:00Z" and bb["gachas"] == [], rb
    # 시작도 모르는 가챠는 행사로 만들 수 없음 → 올리지 않음
    assert apply_judgement(default_banners(), {"action": "upsert", "event": None, "gacha": dict(alone, start_jst=None), "image_for": "none", "reason": ""}, P("g4"), N)["mode"] == "invalid"

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
    # 가챠 원제 수정(id 유지, match_keys 는 새 제목으로 다시 계산)
    ej, cj, _ = edit_banner(P1, b["id"], {"gachas_ja": {gid: " 新しいガチャ名 "}}, N)
    assert cj and ej["banners"][0]["gachas"][0]["title_ja"] == "新しいガチャ名" and ej["banners"][0]["gachas"][0]["id"] == gid
    assert any("新しいガチャ名" in k or name_key("新しいガチャ名") == k for k in ej["banners"][0]["match_keys"])
    assert not edit_banner(P1, b["id"], {"gachas_ja": {gid: "   "}}, N)[1]          # 빈 원문은 무시
    # 이미지 링크 수정 — http(s) 만, 최대 6장, 비우면 이미지 없음
    ei, ci, er_i = edit_banner(P1, b["id"], {"image_urls": ["https://x/1.jpg", " https://x/2.jpg "]}, N)
    assert ci and er_i is None and ei["banners"][0]["image_urls"] == ["https://x/1.jpg", "https://x/2.jpg"]
    assert edit_banner(P1, b["id"], {"image_urls": ["javascript:alert(1)"]}, N)[2] is not None
    assert edit_banner(P1, b["id"], {"image_urls": ["https://x/%d.jpg" % i for i in range(7)]}, N)[2] is not None
    ec, cc, _ = edit_banner(ei, b["id"], {"image_urls": []}, N)
    assert cc and ec["banners"][0]["image_urls"] == []
    # 가챠 기간 수정 — 값을 주면 설정, 빈 값이면 행사와 같음(null), 종료가 시작보다 앞서면 거절
    gp, cg, eg2 = edit_banner(P1, b["id"], {"gachas_period": {gid: {"start_at": "2026-09-30T09:00:00Z", "end_at": "2026-10-09T02:59:00Z"}}}, N)
    assert cg and eg2 is None and gp["banners"][0]["gachas"][0]["end_at"] == "2026-10-09T02:59:00Z"
    gq, cq, _ = edit_banner(gp, b["id"], {"gachas_period": {gid: {"start_at": "", "end_at": None}}}, N)
    assert cq and gq["banners"][0]["gachas"][0]["start_at"] is None and gq["banners"][0]["gachas"][0]["end_at"] is None
    assert edit_banner(P1, b["id"], {"gachas_period": {gid: {"start_at": "2026-10-09T00:00:00Z", "end_at": "2026-10-08T00:00:00Z"}}}, N)[2] is not None
    assert edit_banner(P1, b["id"], {"gachas_period": {gid: {"end_at": "not-a-date"}}}, N)[2] is not None

    # (v4.5.3) 2026-10-19 실측 재현 — 날짜 없는 가챠 소개 글의 판정이 가챠 기간을 행사 종료 · 「10月18日」 00:00 으로 덮던 것
    NOW = "2026-10-19T03:05:52Z"
    SH = {"banners": [{"id": "bn_16b9bd4d", "name_ja": "Shake Your 魂, Baby!!", "name_ko": "Shake Your 영혼, Baby!!",
                       "start_at": "2026-10-18T06:00:00Z", "end_at": "2026-10-26T05:59:00Z", "start_time_tbd": None, "hold": None,
                       "gachas": [{"id": "gc_e33a9595", "title_ja": "はじめてを奏でる光彩讃歌ガチャ", "title_ko": "광채 찬가 가챠", "image_urls": [],
                                   "start_at": "2026-10-18T06:00:00Z", "end_at": "2026-10-28T05:59:00Z"}],
                       "image_urls": [], "match_keys": ["shakeyour魂baby"], "src_ids": ["1"], "first_seen": NOW, "last_updated": NOW}]}
    intro = "10月18日より開催中🎉\n「はじめてを奏でる光彩讃歌ガチャ」\n\n新登場したSSRメンバー、須賀 蕾叶を紹介✌️"
    jw = {"action": "upsert", "banner_ref": "bn_16b9bd4d", "event": None,
          "gacha": {"title_ja": "はじめてを奏でる光彩讃歌ガチャ", "start_jst": "2026-10-18", "end_jst": "2026-10-26 14:59"}}
    rw = apply_judgement(SH, jw, {"tweet_id": "2112016385584812434", "text": intro, "posted_at": NOW}, NOW)
    gw = rw["banners"]["banners"][0]["gachas"][0]
    assert (gw["start_at"], gw["end_at"]) == ("2026-10-18T06:00:00Z", "2026-10-28T05:59:00Z"), gw
    assert "근거 없는 날짜 변경 무시" in rw["detail"] and "10-26 14:59" in rw["detail"] and "날짜만" in rw["detail"], rw["detail"]
    # 텍스트가 없어도(운영자 판단 · 옛 호출) 날짜만 값이 같은 날의 시각을 덮지는 않는다
    rw2 = apply_judgement(SH, dict(jw, gacha=dict(jw["gacha"], end_jst=None)), {"tweet_id": "9"}, NOW)
    assert rw2["banners"]["banners"][0]["gachas"][0]["start_at"] == "2026-10-18T06:00:00Z"
    # 근거가 글 · 이미지에 있으면 바꾼다(연장 공지) — 이미지 OCR 글자도 근거
    ext = intro + "\n" + "開催期間 10月18日 15:00 ~ 10月30日 14:59"
    re_ = apply_judgement(SH, dict(jw, gacha=dict(jw["gacha"], start_jst=None, end_jst="2026-10-30 14:59")),
                          {"tweet_id": "10", "text": ext, "posted_at": NOW}, NOW)
    assert re_["banners"]["banners"][0]["gachas"][0]["end_at"] == "2026-10-30T05:59:00Z" and "무시" not in re_["detail"]
    # 행사 날짜도 같은 규칙 — 근거 없는 종료 변경은 무시, 상대 표현(本日)은 게시일로 근거 인정
    je = {"action": "upsert", "banner_ref": "bn_16b9bd4d", "gacha": None,
          "event": {"name_ja": "Shake Your 魂, Baby!!", "start_jst": "2026-10-19 18:00", "end_jst": "2026-10-27 14:59"}}
    rv = apply_judgement(SH, je, {"tweet_id": "11", "text": "本日18:00より開催！「Shake Your 魂, Baby!!」", "posted_at": NOW}, NOW)
    bv = rv["banners"]["banners"][0]
    assert bv["start_at"] == "2026-10-19T09:00:00Z" and bv["end_at"] == "2026-10-26T05:59:00Z", (bv["start_at"], bv["end_at"])
    # 비어 있던 날짜 채우기 · 새 행사는 근거 확인 없이(「明日15:00より」 같은 글로 새 행사를 올리는 기존 동작)
    assert date_evidenced("2026-10-27T05:59:00Z", "～10/27(火)14:59まで", None) and not date_evidenced("2026-10-27T05:59:00Z", "11/27", None)
    assert date_evidenced("2026-10-20T06:00:00Z", "明日15:00より", "2026-10-19T03:00:00Z")
    fl2 = for_llm(SH, NOW)
    assert fl2[0]["gacha_periods"] == ["はじめてを奏でる光彩讃歌ガチャ 2026-10-18 15:00~2026-10-28 14:59"], fl2
    print("[OK] (v4.5.3) 날짜 근거 확인 · 날짜만 값의 시각 덮어쓰기 차단 · 가챠 기간 판정 목록 표시")

    # (v4.5.10) plan_post · apply_post — 2026-10-21 운영자 확정 기준(실측 14건 재현 실험의 축약)
    def run(state, items, text, now, tid, roles=None):
        stp = plan_post(state, items, text, now, now, roles)
        return apply_post(state, stp, {"tweet_id": tid, "media": [], "text": text, "posted_at": now}, now), stp
    def ev(t, s=None, e=None, kind="event", status="normal"):
        return {"kind": kind, "status": status, "title_ja": t, "title_ko": None, "start_jst": s, "end_jst": e, "period_evidence": ""}
    T1 = "2026-10-17T09:00:00Z"
    sh_txt = "明日15:00より開催🎉\nチャレンジライブイベント「Shake Your 魂, Baby!!」\nイベント\n開催期間：10月18日 15:00 ～ 10月26日 14:59"
    r1, _ = run(default_banners(), [ev("Shake Your 魂, Baby!!", "2026-10-18 15:00", "2026-10-26 14:59")], sh_txt, T1, "101")
    assert r1["mode"] == "added" and len(r1["banners"]["banners"]) == 1 and r1["undo"]["items"], r1
    S1 = r1["banners"]
    assert apply_post(S1, plan_post(S1, [ev("Shake Your 魂, Baby!!")], sh_txt, T1, T1), {"tweet_id": "101"}, T1)["mode"] == "dup"
    # (v4.5.10 · v4.5.9 이미지 판독 예비) 다시 반영(check_dup=False)이면 같은 글이라도 계획대로 반영 — 이미지에서 읽은 종료일을 채운다
    _rc = apply_post(S1, plan_post(S1, [ev("Shake Your 魂, Baby!!", None, "2026-10-26 14:59")], sh_txt, T1, T1), {"tweet_id": "101"}, T1,
                     check_dup=False)
    assert _rc["mode"] != "dup", _rc
    # 스토리 예고(날짜 없음) — 새 배너를 만들지 않고 같은 배너
    r2, _ = run(S1, [ev("Shake Your 魂, Baby!!")], "✌️一家Dumb Rock!初イベント✌️\n「Shake Your 魂, Baby!!」予告", T1, "102")
    assert len(r2["banners"]["banners"]) == 1 and r2["mode"] in ("updated", "none"), r2
    # 가챠 글 — 시작이 같은 이벤트에 딸린다(기간이 겹치는 것만으로는 안 붙인다)
    g_txt = "明日15:00より開催✨\n「はじめてを奏でる光彩讃歌ガチャ」\n開催期間：10月18日15:00～10月28日14:59まで"
    r3, _ = run(r2["banners"], [ev("はじめてを奏でる光彩讃歌ガチャ", "2026-10-18 15:00", "2026-10-28 14:59", kind="gacha")], g_txt, T1, "103")
    b3 = r3["banners"]["banners"]
    assert len(b3) == 1 and b3[0]["gachas"][0]["end_at"] == "2026-10-28T05:59:00Z", b3
    # SSR 소개(「10月18日より開催中」 날짜만) — 가챠 시작 15:00 을 덮지 않고, 새 배너도 없다
    T2 = "2026-10-19T03:00:00Z"
    r4, _ = run(r3["banners"], [ev("はじめてを奏でる光彩讃歌ガチャ", "2026-10-18", kind="gacha")], "10月18日より開催中🎉\n「はじめてを奏でる光彩讃歌ガチャ」", T2, "104")
    assert len(r4["banners"]["banners"]) == 1 and r4["banners"]["banners"][0]["gachas"][0]["start_at"] == "2026-10-18T06:00:00Z"
    # 이름이 조금 달라도(포함 관계) · 이름이 달라도 시작이 같으면 같은 이벤트 — 별도 배너 안 만듦
    r5, _ = run(S1, [ev("Shake Your 魂", "2026-10-18 15:00")], "明日15:00より開催 「Shake Your 魂」", T1, "105")
    assert len(r5["banners"]["banners"]) == 1, r5
    r5b, st5b = run(S1, [ev("一家Dumb Rock!初イベント", "2026-10-18 15:00")], "明日15:00より開催 一家Dumb Rock!初イベント", T1, "106")
    assert len(r5b["banners"]["banners"]) == 1 and "시작이 같은" in st5b[0]["desc"], st5b
    # 날짜 없는 새 이벤트 · 붙을 데 없는 날짜 없는 가챠 → 버림(배너 그대로)
    r6, st6 = run(default_banners(), [ev("新イベント"), ev("新ガチャ", kind="gacha")], "新イベント 新ガチャ", T1, "107")
    assert r6["mode"] == "none" and not r6["banners"]["banners"] and all(s["j"] is None for s in st6), st6
    # 2순위 — 붙을 이벤트가 없는 한시 가챠(Ave Mujica) → 가챠 단독 배너(gacha_only). 기간 겹치는 サイドスロー(시작 10/9)에는 안 붙는다
    T3 = "2026-10-15T13:42:53Z"
    side = apply_post(default_banners(), plan_post(default_banners(), [ev("お願い、サイドスロー", "2026-10-09 15:00", "2026-10-17 14:59")],
                      "開催期間：10月9日 15:00～10月17日 14:59", T3, T3), {"tweet_id": "200"}, T3)["banners"]
    av_txt = "公開記念 Ave Mujicaピックアップガチャ\n開催期間\n10月16日 15:00 ～ 10月25日 23:59"
    r7, _ = run(side, [ev("Ave Mujicaピックアップガチャ", "2026-10-16 15:00", "2026-10-25 23:59", kind="gacha")], av_txt, T3, "201")
    av = next(b for b in r7["banners"]["banners"] if b["name_ja"].startswith("Ave"))
    assert av.get("gacha_only") and av["end_at"] == "2026-10-25T14:59:00Z" and not av["gachas"], av
    assert not next(b for b in r7["banners"]["banners"] if b["name_ja"].startswith("お願い"))["gachas"]
    # (v4.5.11) 관리 페이지에서 시작만으로 수동 등록한 행사 → 뒤이은 글이 이름(또는 같은 시작 시각)으로 같은 배너를 찾아 종료일을 채운다
    T5 = "2026-11-01T03:00:00Z"
    man = apply_judgement(default_banners(), {"action": "upsert", "banner_ref": None, "event": {"name_ja": "星降る夜のセレナーデ", "name_ko": None,
                          "start_jst": "2026-11-05 15:00", "end_jst": None, "permanent": False}, "gacha": None, "reason": "사용자 판단"}, {"tweet_id": ""}, T5)
    assert man["mode"] == "added" and man["banners"]["banners"][0]["end_at"] is None, man
    m_txt = "チャレンジライブイベント「星降る夜のセレナーデ」\n開催期間：11月5日 15:00 ～ 11月13日 14:59"
    m1, _ = run(man["banners"], [ev("星降る夜のセレナーデ", "2026-11-05 15:00", "2026-11-13 14:59")], m_txt, T5, "401")
    assert len(m1["banners"]["banners"]) == 1 and m1["banners"]["banners"][0]["end_at"] == "2026-11-13T05:59:00Z", m1
    m2, _ = run(man["banners"], [ev("夜空のセレナーデ", "2026-11-05 15:00", "2026-11-13 14:59")], m_txt.replace("星降る夜", "夜空"), T5, "402")
    assert len(m2["banners"]["banners"]) == 1 and m2["banners"]["banners"][0]["end_at"] == "2026-11-13T05:59:00Z", ("이름이 달라도 같은 시작이면 채운다", m2)
    # (v4.5.11) 가챠 단독 배너도 이미지를 쓴다 — 용도 gacha · event 는 붙이고 none(소개 카드)은 빼고, 판정이 없으면 그대로. 이미 있으면 안 바꾼다
    def run_img(state, items, text, now, tid, media, roles):
        return apply_post(state, plan_post(state, items, text, now, now, roles), {"tweet_id": tid, "media": media, "text": text, "posted_at": now}, now)
    avg = [ev("Ave Mujicaピックアップガチャ", "2026-10-16 15:00", "2026-10-25 23:59", kind="gacha")]
    _img = lambda r: next(b for b in r["banners"]["banners"] if b["name_ja"].startswith("Ave"))["image_urls"]
    assert _img(run_img(side, avg, av_txt, T3, "211", ["https://x/av.jpg"], ["gacha"])) == ["https://x/av.jpg"]
    assert _img(run_img(side, avg, av_txt, T3, "212", ["https://x/av.jpg"], [])) == ["https://x/av.jpg"], "용도 판정이 없으면 그대로 쓴다"
    assert _img(run_img(side, avg, av_txt, T3, "213", ["https://x/card.jpg"], ["none"])) == [], "소개 카드(none)는 안 쓴다"
    _r9 = run_img(side, avg, av_txt, T3, "214", ["https://x/av.jpg"], ["gacha"])
    _r10 = run_img(_r9["banners"], avg, av_txt, T3, "215", ["https://x/ssr.jpg"], ["gacha"])
    assert _img(_r10) == ["https://x/av.jpg"], "이미 이미지가 있으면 뒤 글의 가챠 이미지로 바꾸지 않는다"
    # 가챠 단독이 먼저 오고 같은 시작의 이벤트가 뒤에 오면 → 이벤트 배너 밑으로 합친다 · 되돌리기는 한 번에
    G0 = run(default_banners(), [ev("光彩讃歌ガチャ", "2026-10-18 15:00", "2026-10-28 14:59", kind="gacha")], g_txt, T1, "300")[0]["banners"]
    r8, st8 = run(G0, [ev("Shake Your 魂, Baby!!", "2026-10-18 15:00", "2026-10-26 14:59")], sh_txt, T1, "301", roles=["event"])
    b8 = r8["banners"]["banners"]
    assert len(b8) == 1 and b8[0]["name_ja"] == "Shake Your 魂, Baby!!" and b8[0]["gachas"][0]["title_ja"] == "光彩讃歌ガチャ", b8
    assert not b8[0].get("gacha_only") and "300" in b8[0]["src_ids"] and any(s["merge"] for s in st8)
    back, _a, msg = restore(r8["banners"], r8["undo"], default_archive(), T1)
    assert msg == "되돌림" and [b["name_ja"] for b in back["banners"]] == ["光彩讃歌ガチャ"] and back["banners"][0]["gacha_only"], back
    # 날짜만 있는 가챠 소개(「10月18日より開催中」)가 가챠 글보다 먼저 와도 — 같은 날 시작하는 이벤트에 붙고, 붙을 데 없으면 새 배너를 만들지 않는다
    ssr = "10月18日より開催中🎉\n「はじめてを奏でる光彩讃歌ガチャ」"
    r10, _ = run(S1, [ev("はじめてを奏でる光彩讃歌ガチャ", "2026-10-18", kind="gacha")], ssr, T2, "500")
    assert len(r10["banners"]["banners"]) == 1 and r10["banners"]["banners"][0]["gachas"][0]["title_ja"] == "はじめてを奏でる光彩讃歌ガチャ", r10
    r11, st11 = run(default_banners(), [ev("はじめてを奏でる光彩讃歌ガチャ", "2026-10-18", kind="gacha")], ssr, T2, "501")
    assert r11["mode"] == "none" and not r11["banners"]["banners"] and "날짜만" in st11[0]["desc"], st11
    # 취소 공지 → 그 배너를 내린다
    r9, _ = run(S1, [ev("Shake Your 魂, Baby!!", status="cancelled")], "「Shake Your 魂, Baby!!」開催中止のお知らせ", T1, "400")
    assert r9["mode"] == "cancelled" and not r9["banners"]["banners"] and r9["archive_add"], r9
    print("[OK] (v4.5.10) plan_post · apply_post — 1순위 이벤트 · 같은 시작 가챠 · 2순위 가챠 단독 · 중복 배너 방지 · 합치기 · 버림 · 묶음 되돌리기")
    print("[PASS] banners self-test (시각 · 이름 키 · 반영 · 보류/재개 · 취소/되돌리기 · sweep · 소식 겹침 · 수정)")
