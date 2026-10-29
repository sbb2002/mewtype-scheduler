"""보관함 정리 — 캐시 보관함의 오래된 항목을 일자 보관함으로 옮긴다 (핫픽스 archive-split, 2026-10-26).

캐시 보관함(파일 이름은 그대로 — 운영 코드의 읽기 · 쓰기 경로를 바꾸지 않으려고):
  tweet_archive.json (data)  — 게시 7일 이내
  notice_archive.json (data) — 보관 시각 · 행사 날짜 중 늦은 것이 30일 이내
  llm_actions.json (ops)     — 판단 21일 이내 (관리 페이지에서 반려 · 재판단할 수 있는 기간)
  preview_archive.json (data) — 보관 7일 이내 (v4.9.6 — 프론트는 오늘 예고의 끝난 방송만 찾는다)
일자 보관함(보존용 — 운영 경로는 안 읽음, 웹 모니터 지난 날짜 조회 · 분석만):
  tweet_archive/YYYY-MM-DD.json · notice_archive/YYYY-MM-DD.json(+ notice_archive/index.json) · llm_actions/YYYY-MM-DD.json(ops)
  · preview_archive/YYYY-MM-DD.json

계기: GitHub Contents API 는 1MB 넘는 파일을 기본 형식으로 읽으면 내용을 비워 준다(`gh_store.read_json` 예외) —
트윗 보관함이 888,969B(10-26)로 11-03 전후 1MB 를 넘어 개인 트윗 저장이 전부 막힐 참이었다.
명세 = devpapers `ref/archive-split/impl_spec.md`.

하루 한 번 `apply.run_snapshot`(KST 06:10 `/monitor`)이 `run_all` 을 부른다. 순서 = 일자 파일에 먼저 합쳐 쓰고(id 로 합침 — 두 번 써도 같음)
→ (소식) 색인 → 캐시에서 뺀다. 중간에 실패해도 같은 항목이 양쪽에 남을 뿐 잃지 않는다. 백엔드는 한 번에 한 요청만 받아 이 작업 동안 `/write` 가
기다리므로 한 번에 쓰는 일자 파일은 대상마다 MAX_FILES_PER_RUN 개 — 밀린 첫 이전은 `scripts/split_archives.py` 가 git 으로 한 번에 한다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
_TW_EPOCH_MS = 1288834974657            # X Snowflake 기준 시각 (xtweet._TW_EPOCH_MS 와 같음)

TWEET_KEEP_DAYS = 7
NOTICE_KEEP_DAYS = 30
LLM_KEEP_DAYS = 21                      # 관리 페이지 「LLM 판단」 반려 · 재판단 유효기간 — admin_api · admin.html 이 이 값을 쓴다
PREVIEW_KEEP_DAYS = 7                   # (v4.9.6) 프론트(오늘 예고의 끝난 방송)는 하루 남짓만 쓰고, 웹 모니터 최근 일주일은 캐시로 바로 찾는다
MAX_FILES_PER_RUN = 3                   # 대상마다 한 번에 쓰는 일자 파일 수
CACHE_LIMIT_BYTES = 800_000             # 캐시가 이보다 크면 기간 안이라도 오래된 날짜부터 더 옮긴다(1MB 까지 여유 약 250KB)

TWEET_CACHE, TWEET_DIR = "tweet_archive.json", "tweet_archive"
NOTICE_CACHE, NOTICE_DIR = "notice_archive.json", "notice_archive"
NOTICE_INDEX = "notice_archive/index.json"
LLM_CACHE, LLM_DIR = "llm_actions.json", "llm_actions"
PREVIEW_CACHE, PREVIEW_DIR = "preview_archive.json", "preview_archive"


# ── 시각 · 날짜 ───────────────────────────────────────────────────────────────

def _parse_iso(s) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def snowflake_dt(tid) -> Optional[datetime]:
    """트윗 id(숫자 문자열) → 게시 시각. 숫자가 아니면 None."""
    s = str(tid or "")
    if not s.isdigit() or len(s) < 15:
        return None
    try:
        return datetime.fromtimestamp(((int(s) >> 22) + _TW_EPOCH_MS) / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def kst_date(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(KST).strftime("%Y-%m-%d") if dt else None


def day_path(directory: str, date: str) -> str:
    return f"{directory}/{date}.json"


def tweet_dt(t: dict) -> Optional[datetime]:
    """트윗 날짜 기준 = 게시 시각(id) → 없으면 받은 시각 → 보관 시각."""
    return snowflake_dt(t.get("id")) or _parse_iso(t.get("received_at")) or _parse_iso(t.get("archived_at"))


def tweet_day(tweet_or_id) -> Optional[str]:
    """트윗(또는 트윗 id) 이 들어 있을 트윗 일자 파일 날짜(KST)."""
    if isinstance(tweet_or_id, dict):
        return kst_date(tweet_dt(tweet_or_id))
    return kst_date(snowflake_dt(tweet_or_id))


def _notice_event_end(n: dict) -> Optional[datetime]:
    """소식의 행사 날짜(date — KST 달력 날짜)가 끝나는 시각. 없거나 이상하면 None."""
    d = n.get("date")
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").replace(tzinfo=KST) + timedelta(days=1) if d else None
    except ValueError:
        return None


def notice_keep_ref(n: dict) -> Optional[datetime]:
    """소식을 캐시에 남길지 재는 기준 = 보관 시각과 행사 날짜 중 늦은 것.
    날짜가 아직 안 지났는데 일찍 내려간 소식(판단 반려 · 병합 오류 등)이 캐시에 남아 같은 글이 다시 올라오는 것을 막는다."""
    refs = [x for x in (_parse_iso(n.get("archived_at")), _notice_event_end(n)) if x]
    return max(refs) if refs else None


def notice_day(n: dict) -> Optional[str]:
    """소식 일자 파일 날짜 = 처음 받은 날(first_seen) → 없으면 보관한 날."""
    return kst_date(_parse_iso(n.get("first_seen")) or _parse_iso(n.get("archived_at")))


def notice_index_keys(n: dict) -> tuple[list[str], list[str]]:
    """(트윗 · 소식 id 키, 시각 키). id 키는 소식 중복 판정(이미 본 트윗)에, 시각 키는 웹 모니터 찾기에 쓴다."""
    ids = [str(x) for x in [n.get("id"), *(n.get("seen_ids") or [])] if x]
    ts = [str(x) for x in (n.get("first_seen"), n.get("last_updated")) if x]
    return ids, ts


# ── 대상 정의 ─────────────────────────────────────────────────────────────────

@dataclass
class Target:
    name: str
    cache: str
    directory: str
    list_key: str
    keep_days: int
    keep_ref: Callable[[dict], Optional[datetime]]
    day_of: Callable[[dict], Optional[str]]
    index: Optional[str] = None
    extra: dict = field(default_factory=dict)
    key: Optional[Callable[[dict], str]] = None     # 일자 파일 안 같은 항목 열쇠 — 없으면 _key(id)


TWEETS = Target("tweet", TWEET_CACHE, TWEET_DIR, "tweets", TWEET_KEEP_DAYS, tweet_dt, lambda t: kst_date(tweet_dt(t)))
NOTICES = Target("notice", NOTICE_CACHE, NOTICE_DIR, "notices", NOTICE_KEEP_DAYS, notice_keep_ref, notice_day, index=NOTICE_INDEX)
LLM = Target("llm", LLM_CACHE, LLM_DIR, "items", LLM_KEEP_DAYS, lambda e: _parse_iso(e.get("ts")),
             lambda e: kst_date(_parse_iso(e.get("ts"))))


def _key(item: dict) -> str:
    """일자 파일 안에서 같은 항목을 가르는 열쇠 — id, 없으면 내용 전체."""
    i = item.get("id")
    return str(i) if i not in (None, "") else json.dumps(item, sort_keys=True, ensure_ascii=False)


def preview_key(item: dict) -> str:
    """(v4.9.6) 예고 보관 기록의 열쇠 = id + 보관 시각. 같은 예고가 preview 로 돌아왔다 다시 보관되면(관리 명령 경로는 캐시 안 중복을
    따지지 않는다) 두 기록이 모두 남게 — id 만으로 합치면 뒤 기록이 버려진다."""
    return f"{_key(item)}|{item.get('archived_at') or ''}"


def key_of(target: Target) -> Callable[[dict], str]:
    return target.key or _key


# (v4.9.6) 예고 보관함 — 기준 시각 · 날짜 = 보관 시각(archived_at, KST 달력 날짜. 예고보드의 04:00 하루와 무관)
PREVIEWS = Target("preview", PREVIEW_CACHE, PREVIEW_DIR, "items", PREVIEW_KEEP_DAYS, lambda p: _parse_iso(p.get("archived_at")),
                  lambda p: kst_date(_parse_iso(p.get("archived_at"))), key=preview_key)
TARGETS = (TWEETS, NOTICES, LLM, PREVIEWS)


def _size(data: dict) -> int:
    return len((json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


# ── 계획 (순수) ───────────────────────────────────────────────────────────────

def plan(items: list[dict], target: Target, now: datetime, *, max_files: int = MAX_FILES_PER_RUN,
         limit_bytes: int = CACHE_LIMIT_BYTES) -> tuple[list[dict], dict[str, list[dict]], bool]:
    """(남길 것, {날짜: 옮길 것}, 크기 초과가 남았나).

    1) 기준 시각이 keep_days 보다 오래된 항목을 옮길 후보로(기준 시각 · 날짜를 못 정하면 남김).
    2) 후보를 날짜별로 묶어 오래된 날짜부터 max_files 개까지만 이번에 옮긴다(나머지는 다음 정리 때).
    3) 그래도 캐시가 limit_bytes 를 넘으면, 파일 상한 안에서 남은 항목 중 오래된 날짜를 통째로 더 옮긴다.
    캐시 안 항목의 순서는 그대로 둔다."""
    cutoff = now - timedelta(days=target.keep_days)
    due: dict[str, list[int]] = {}
    for i, it in enumerate(items):
        ref, day = target.keep_ref(it), target.day_of(it)
        if ref is not None and day and ref < cutoff:
            due.setdefault(day, []).append(i)
    chosen = sorted(due)[:max_files]
    move_idx = {i for d in chosen for i in due[d]}

    def _keep():
        return [it for i, it in enumerate(items) if i not in move_idx]

    over = _size({target.list_key: _keep()}) > limit_bytes
    while over and len(chosen) < max_files:
        rest: dict[str, list[int]] = {}
        for i, it in enumerate(items):
            day = target.day_of(it)
            if i not in move_idx and day:
                rest.setdefault(day, []).append(i)
        if not rest:
            break
        d = min(rest)
        chosen.append(d)
        move_idx.update(rest[d])
        over = _size({target.list_key: _keep()}) > limit_bytes
    moves: dict[str, list[dict]] = {}
    for i, it in enumerate(items):
        if i in move_idx:
            moves.setdefault(target.day_of(it), []).append(it)
    return _keep(), moves, over


def merge_day(existing: list[dict], incoming: list[dict], key: Callable[[dict], str] = _key) -> list[dict]:
    """일자 파일에 합치기 — 이미 있는 열쇠는 그대로 두고 새 것만 뒤에. 두 번 합쳐도 같다."""
    have = {key(x) for x in existing}
    out = list(existing)
    for x in incoming:
        k = key(x)
        if k not in have:
            have.add(k)
            out.append(x)
    return out


def merge_index(index: Optional[dict], moved: list[dict], day: str) -> dict:
    idx = {"ids": dict((index or {}).get("ids") or {}), "ts": dict((index or {}).get("ts") or {})}
    for n in moved:
        ids, ts = notice_index_keys(n)
        for k in ids:
            idx["ids"].setdefault(k, day)
        for k in ts:
            idx["ts"].setdefault(k, day)
    return idx


# ── 실행 (저장 호출) ──────────────────────────────────────────────────────────

def _write_merged(gh, path: str, list_key: str, incoming: list[dict], message: str, tries: int = 3,
                  key: Callable[[dict], str] = _key) -> None:
    from .gh_store import ConflictError
    for t in range(tries):
        cur, sha = gh.read_json(path)
        merged = merge_day(list((cur or {}).get(list_key) or []), incoming, key)
        try:
            gh.write_json(path, {list_key: merged}, prev_sha=sha, message=message)
            return
        except ConflictError:
            if t == tries - 1:
                raise


def rotate(gh, target: Target, now_iso: str, **kw) -> dict:
    """한 대상 정리. 반환 {name, moved, files, cache_bytes, over_limit, skipped}. 캐시가 없으면 skipped."""
    from .gh_store import ConflictError
    now = _parse_iso(now_iso) or datetime.now(timezone.utc)
    for attempt in range(3):
        cache, sha = gh.read_json(target.cache)
        if cache is None:
            return {"name": target.name, "skipped": "no-cache", "moved": 0, "files": []}
        items = list(cache.get(target.list_key) or [])
        keep, moves, over = plan(items, target, now, **kw)
        if not moves:
            return {"name": target.name, "moved": 0, "files": [], "cache_bytes": _size(cache), "over_limit": over}
        files = []
        for day in sorted(moves):
            path = day_path(target.directory, day)
            _write_merged(gh, path, target.list_key, moves[day], f"data: archive {target.name} → {path} ({len(moves[day])}) {now_iso}",
                          key=key_of(target))
            files.append(path)
        if target.index:
            for t in range(3):
                idx, isha = gh.read_json(target.index)
                new_idx = idx
                for day in sorted(moves):
                    new_idx = merge_index(new_idx, moves[day], day)
                try:
                    gh.write_json(target.index, new_idx, prev_sha=isha, message=f"data: archive {target.name} index {now_iso}")
                    break
                except ConflictError:
                    if t == 2:
                        raise
        new_cache = dict(cache)
        new_cache[target.list_key] = keep
        try:
            gh.write_json(target.cache, new_cache, prev_sha=sha,
                          message=f"data: archive {target.name} cache −{sum(len(v) for v in moves.values())} {now_iso}")
        except ConflictError:
            log.info("보관함 정리 %s: 캐시 쓰기 충돌(%d) — 다시 읽어 재계산", target.name, attempt + 1)
            continue
        return {"name": target.name, "moved": sum(len(v) for v in moves.values()), "files": files,
                "cache_bytes": _size(new_cache), "over_limit": over}
    raise RuntimeError(f"보관함 정리 {target.name}: 캐시 쓰기 충돌이 계속됨")


def run_all(gh, now_iso: str, *, log_fn: Callable | None = None) -> list[dict]:
    """대상(트윗 · 소식 · LLM 판단 · 예고)을 차례로 정리. 한 대상이 실패해도 나머지는 계속. log_fn(result) 로 모니터 기록(호출부가 넘김)."""
    out = []
    for t in TARGETS:
        try:
            r = rotate(gh, t, now_iso)
        except Exception as e:  # noqa: BLE001
            log.warning("보관함 정리 실패 %s", t.name, exc_info=True)
            r = {"name": t.name, "error": str(e)[:200], "moved": 0, "files": []}
        out.append(r)
        if log_fn is not None:
            try:
                log_fn(r)
            except Exception:  # noqa: BLE001
                log.warning("보관함 정리 기록 실패 %s", t.name, exc_info=True)
    return out


# ── 읽기 도우미 (웹 모니터 · 소식 중복 판정) ──────────────────────────────────

def read_day(gh, target: Target, day: str) -> list[dict]:
    """일자 파일 한 개의 항목. 없거나 못 읽으면 []."""
    try:
        d, _ = gh.read_json(day_path(target.directory, day))
    except Exception:  # noqa: BLE001
        log.warning("일자 보관함 읽기 실패 %s %s", target.name, day, exc_info=True)
        return []
    return list((d or {}).get(target.list_key) or [])


def notice_index(gh) -> dict:
    """소식 색인 {"ids": {id: 날짜}, "ts": {시각: 날짜}}. 없으면 빈 색인. 읽기 실패는 예외 그대로(호출부가 판단)."""
    d, _ = gh.read_json(NOTICE_INDEX)
    return {"ids": dict((d or {}).get("ids") or {}), "ts": dict((d or {}).get("ts") or {})}


# ── self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from .gh_store import ConflictError

    class _G:
        """경로별 {data, sha} 가짜 저장소. fail_cache_once=True 면 캐시 첫 쓰기에서 충돌."""
        def __init__(self, files=None, fail_path=None):
            self.f = {k: v for k, v in (files or {}).items()}
            self.sha = {k: "s0" for k in self.f}
            self.writes = []
            self.fail_path = fail_path

        def read_json(self, p):
            return (json.loads(json.dumps(self.f[p])) if p in self.f else None), self.sha.get(p)

        def write_json(self, p, data, *, prev_sha, message):
            if p == self.fail_path:
                self.fail_path = None
                self.sha[p] = "other"
                raise ConflictError("x")
            if prev_sha is not None and self.sha.get(p) not in (None, prev_sha):
                raise ConflictError("sha")
            self.f[p] = json.loads(json.dumps(data))
            self.sha[p] = f"s{len(self.writes) + 1}"
            self.writes.append(p)
            return True, self.sha[p]

    def sf(dt):  # 시각 → 트윗 id
        return str((int(dt.timestamp() * 1000) - _TW_EPOCH_MS) << 22)

    NOW = datetime(2026, 10, 26, 21, 10, tzinfo=timezone.utc)   # KST 10-27 06:10
    now_iso = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 날짜 계산 — KST 자정 경계 · 옛 id
    a = datetime(2026, 10, 1, 14, 59, tzinfo=timezone.utc)      # KST 10-01 23:59
    b = datetime(2026, 10, 1, 15, 1, tzinfo=timezone.utc)       # KST 10-02 00:01
    assert tweet_day(sf(a)) == "2026-10-01" and tweet_day(sf(b)) == "2026-10-02"
    assert tweet_day({"id": "p8dbc9abb72e5427", "received_at": "2026-09-09T15:53:51Z"}) == "2026-09-10"
    assert tweet_day("p8dbc9") is None
    print("[OK] 날짜 — Snowflake · KST 자정 · 옛 id 는 받은 시각")

    # 트윗: 7일 기준 · 파일 3개 상한 · 순서 유지
    old = [{"id": sf(NOW - timedelta(days=d, hours=1)), "text": f"d{d}"} for d in (20, 12, 11, 10, 9, 2)]
    keep, moves, over = plan(old, TWEETS, NOW)
    assert sorted(moves) == sorted({tweet_day(x) for x in old[:3]}), moves.keys()   # 오래된 날짜 3개만
    assert [x["text"] for x in keep] == ["d10", "d9", "d2"] and not over
    print("[OK] 트윗 7일 · 한 번에 3개 날짜 · 나머지는 다음 정리")

    # 소식: 보관 시각과 행사 날짜 중 늦은 것 30일
    n_old = {"id": "1", "archived_at": "2026-09-01T00:00:00Z", "date": "2026-09-01", "first_seen": "2026-08-20T00:00:00Z"}
    n_future = {"id": "2", "archived_at": "2026-09-01T00:00:00Z", "date": "2026-12-01", "first_seen": "2026-08-20T00:00:00Z",
                "archived_reason": "llm_review"}
    n_nodate = {"id": "3", "archived_at": "2026-10-20T00:00:00Z", "first_seen": "2026-10-19T00:00:00Z"}
    keep, moves, _ = plan([n_old, n_future, n_nodate], NOTICES, NOW)
    assert [n["id"] for n in keep] == ["2", "3"] and list(moves) == ["2026-08-20"]
    print("[OK] 소식 30일 — 일찍 내려간 앞날 소식은 행사 날짜 + 30일까지 캐시에 남음")

    # LLM 21일 · 기준 시각 없는 항목은 남김
    es = [{"id": "a", "ts": "2026-10-01T00:00:00Z"}, {"id": "b", "ts": "2026-10-10T00:00:00Z"}, {"id": "c"}]
    keep, moves, _ = plan(es, LLM, NOW)
    assert [e["id"] for e in keep] == ["b", "c"] and list(moves) == ["2026-10-01"]
    print("[OK] LLM 판단 21일 · 시각 없는 항목은 남김")

    # 크기 안전장치 — 기간 안이라도 오래된 날짜부터 더
    big = [{"id": sf(NOW - timedelta(days=d)), "text": "x" * 3000} for d in (6, 5, 4, 3)]
    keep, moves, over = plan(big, TWEETS, NOW, limit_bytes=4000)      # 한 건 약 3.1KB → 1건만 남아야 4000 안
    assert len(moves) == 3 and len(keep) == 1 and not over, (len(moves), len(keep), over)
    keep, moves, over = plan(big, TWEETS, NOW, limit_bytes=10, max_files=2)
    assert len(moves) == 2 and over
    print("[OK] 크기 안전장치 — 파일 상한 안에서 더 옮기고, 그래도 크면 over_limit")

    # rotate: 일자 파일 합치기 → 색인 → 캐시, 두 번 돌려도 같음
    notices_cache = {"notices": [n_old, n_future, n_nodate]}
    g = _G({NOTICE_CACHE: notices_cache,
            "notice_archive/2026-08-20.json": {"notices": [{"id": "1", "title": "이미 옮겨진 것"}]}})
    r = rotate(g, NOTICES, now_iso)
    assert r["moved"] == 1 and r["files"] == ["notice_archive/2026-08-20.json"]
    assert g.f["notice_archive/2026-08-20.json"]["notices"] == [{"id": "1", "title": "이미 옮겨진 것"}]   # 이미 있는 id 는 그대로
    assert [n["id"] for n in g.f[NOTICE_CACHE]["notices"]] == ["2", "3"]
    assert g.f[NOTICE_INDEX]["ids"]["1"] == "2026-08-20" and g.f[NOTICE_INDEX]["ts"]["2026-08-20T00:00:00Z"] == "2026-08-20"
    assert g.writes == ["notice_archive/2026-08-20.json", NOTICE_INDEX, NOTICE_CACHE], g.writes   # 순서: 일자 → 색인 → 캐시
    n_w = len(g.writes)
    assert rotate(g, NOTICES, now_iso)["moved"] == 0 and len(g.writes) == n_w
    print("[OK] rotate — 일자 파일 먼저 · 이미 있는 id 유지 · 색인 · 캐시 순, 다시 돌리면 할 일 없음")

    # 캐시 쓰기 충돌 → 다시 읽어 재계산(일자 파일은 합치기라 같은 결과)
    g2 = _G({TWEET_CACHE: {"tweets": old}}, fail_path=TWEET_CACHE)
    r2 = rotate(g2, TWEETS, now_iso)
    assert r2["moved"] == 3 and len(g2.f[TWEET_CACHE]["tweets"]) == 3
    moved_ids = {x["id"] for d in r2["files"] for x in g2.f[d]["tweets"]}
    assert moved_ids == {x["id"] for x in old[:3]}
    print("[OK] 캐시 쓰기 충돌 → 재계산, 잃은 것 · 중복 없음")

    # 일자 파일 쓰기 실패 → 캐시는 그대로(예외는 run_all 이 잡음)
    class _Bad(_G):
        def write_json(self, p, data, *, prev_sha, message):
            if p.startswith(TWEET_DIR + "/"):
                raise RuntimeError("boom")
            return super().write_json(p, data, prev_sha=prev_sha, message=message)
    g3 = _Bad({TWEET_CACHE: {"tweets": old}, LLM_CACHE: {"items": es}})
    logged = []
    res = run_all(g3, now_iso, log_fn=logged.append)
    assert len(g3.f[TWEET_CACHE]["tweets"]) == len(old) and res[0].get("error")
    assert res[1]["skipped"] == "no-cache" and res[2]["moved"] == 1 and len(logged) == 4 and res[3]["skipped"] == "no-cache"
    print("[OK] 일자 파일 쓰기 실패 → 캐시 안 줄임 · 다른 대상은 계속")

    # (v4.9.6) 예고: 보관 시각 7일 · 날짜 = 보관 시각의 KST 날짜 · 같은 id 다른 보관 시각은 둘 다 남김 · 다시 돌려도 같음
    pv = [{"id": "pv_a", "archived_at": "2026-10-10T16:00:00Z", "actual_start": "2026-10-10T12:00:00Z"},   # KST 10-11 01:00 → 10-11 파일
          {"id": "pv_b", "archived_at": "2026-10-12T03:00:00Z"},
          {"id": "pv_a", "archived_at": "2026-10-12T05:00:00Z", "state": "out"},                          # 다시 보관된 같은 예고
          {"id": "pv_c", "archived_at": "2026-10-25T03:00:00Z"},                                         # 7일 안 → 캐시에 남음
          {"id": "pv_d"}]                                                                                 # 보관 시각 없음 → 남음
    keep, moves, _ = plan(pv, PREVIEWS, NOW)
    assert [p.get("id") for p in keep] == ["pv_c", "pv_d"] and sorted(moves) == ["2026-10-11", "2026-10-12"], (keep, moves)
    g4 = _G({PREVIEW_CACHE: {"generated_at": "x", "items": pv},
             "preview_archive/2026-10-12.json": {"items": [{"id": "pv_b", "archived_at": "2026-10-12T03:00:00Z", "title": "이미 옮겨진 것"}]}})
    r4 = rotate(g4, PREVIEWS, now_iso)
    assert r4["moved"] == 3 and g4.f[PREVIEW_CACHE] == {"generated_at": "x", "items": pv[3:]}
    d12 = g4.f["preview_archive/2026-10-12.json"]["items"]
    assert [(p["id"], p.get("title")) for p in d12] == [("pv_b", "이미 옮겨진 것"), ("pv_a", None)], d12
    assert [p["id"] for p in g4.f["preview_archive/2026-10-11.json"]["items"]] == ["pv_a"]
    n_w = len(g4.writes)
    assert rotate(g4, PREVIEWS, now_iso)["moved"] == 0 and len(g4.writes) == n_w
    assert PREVIEWS in TARGETS
    print("[OK] 예고 7일 — 보관 시각 KST 날짜 · 같은 id 다시 보관분도 남김 · 캐시의 다른 키(generated_at) 유지 · 다시 돌리면 할 일 없음")

    # 캐시 없음
    assert rotate(_G(), TWEETS, now_iso)["skipped"] == "no-cache"
    print("[OK] 캐시 없음 → 건너뜀")
    print("archive_rotate self-test 통과")
