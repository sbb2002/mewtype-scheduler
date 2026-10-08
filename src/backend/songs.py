"""신곡 자동 감지 (v4.2.0) — 토픽 채널 RSS 에서 새 곡을 찾아 곡 목록(`songs.json`)에 등록한다. 순수 로직 + RSS 조회.

배경: 곡은 그룹 공식 채널이 아니라 음원 자동 생성 채널(`Mugendai MewType - Topic`)에 올라온다. 이 채널은 방송이 아니라
`preview.json` · FSM 과 무관하므로 방송 파이프라인(`preview_build`)에 끼우지 않고 별도 경로로 둔다(`handlers._detect_new_songs`).
RSS 는 쿼터 0 이고, 새 곡이 있을 때만 쓰기가 일어난다.

규칙 (운영자 결정 2026-10-06):
  - 곡명이 이미 데이터에 있으면 등록하지 않는다(영상 ID 가 달라도). 새 곡명만 등록.
  - 구분은 제목으로: 끝에 「(Cover)」(대소문자 · 전각 괄호 무관)가 붙으면 `cover`, 아니면 `original`. 다른 표기(예: 「(Solo)」)에 대한 규칙은 두지 않는다.
  - `feat.` 곡은 등록하지 않는다.
  - 독음(`reading`)은 RSS 에 없으므로 외부 LLM(Groq)이 곡명으로 작성(`handlers._detect_new_songs` → `fill_readings`). 실패하면 빈 문자열 + `needs_reading`.
피드 버스트(한 번에 15개 넘게 올라오는 경우)는 아직 고려하지 않는다.

곡 문서 `songs.json` = `{"songs": [...], "rejected": [...], "seen": [...]}` (프론트는 `songs` 만 읽는다).
  - `rejected`: 삭제 · 반려한 곡(영상 ID + 곡명 키). RSS 최근 15건에 곡이 남아 있어도 다시 등록되지 않게 한다. 차단 해제 가능.
  - `seen`: 이미 판단 기록을 남긴 「곡명 중복 건너뜀」(같은 건너뜀을 tick 마다 다시 기록하지 않게, 최근 200건).
  - 곡의 `needs_reading`: 독음(LLM)을 아직 못 채운 곡 → 다음 tick 이 재시도(tick 당 3건). `reading_manual`: 운영자가 직접 정한 독음(LLM 이 덮지 않음).

순수 함수: parse_feed_entries / classify / name_key / is_feat / kst_date / find_new_songs / merge_songs / delete_song / unblock / edit_song / add_song / fill_readings / mark_seen. 네트워크는 fetch_feed_entries 뿐.
self-test: python -m src.backend.songs
"""
from __future__ import annotations

import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)

SONGS_PATH = "songs.json"           # data 브랜치 — 프론트가 raw URL 로 읽는다
SONG_FEEDS_KEY = "song_feeds"       # config/channels.json 최상위 키 (channels 와 별개 — 방송 파이프라인이 읽지 않게)

_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# 제목 끝의 「(Cover)」 (전각 괄호 포함, 대소문자 무관)
_COVER_RE = re.compile(r"\s*[\(（]\s*cover\s*[\)）]\s*$", re.I)
# 그룹 채널 커버 영상의 「【Covered by …】」 꼬리 — 곡명 비교에서 뗀다
_COVERED_BY_RE = re.compile(r"\s*【\s*covered\s+by[^】]*】\s*$", re.I)
_FEAT_RE = re.compile(r"(?<![a-z])(?:feat|ft)\.", re.I)


def parse_feed_entries(xml_text: str) -> list[dict]:
    """YouTube 채널 RSS(Atom) → [{video_id, title, published(UTC ISO), description}] (피드 순서 = 최신순, 최대 15)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("곡 RSS 파싱 실패: %s", e)
        return []
    out = []
    for entry in root.findall("atom:entry", _NS):
        vid = entry.findtext("yt:videoId", default="", namespaces=_NS)
        title = entry.findtext("atom:title", default="", namespaces=_NS)
        if not vid or not title:
            continue
        out.append({
            "video_id": vid,
            "title": title.strip(),
            "published": entry.findtext("atom:published", default="", namespaces=_NS),
            "description": entry.findtext("media:group/media:description", default="", namespaces=_NS),
        })
    return out


def fetch_feed_entries(channel_id: str, *, timeout: float = 10.0, session: Optional[requests.Session] = None) -> list[dict]:
    """채널 RSS 를 가져와 parse_feed_entries. 어떤 오류든 [] (경고 로그)."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        r = (session or requests).get(url, timeout=timeout, headers={"User-Agent": _UA})
        r.raise_for_status()
        return parse_feed_entries(r.text)
    except Exception as e:  # noqa: BLE001
        log.warning("곡 RSS 조회 실패 (%s): %s", channel_id, e)
        return []


def classify(title: str) -> str:
    """제목 → "cover"(끝에 (Cover)) | "original"."""
    return "cover" if _COVER_RE.search(title or "") else "original"


def clean_title(title: str) -> str:
    """표시용 곡명 — 끝의 (Cover) 와 【Covered by …】 를 뗀다(구분은 kind 가 맡는다)."""
    t = _COVERED_BY_RE.sub("", title or "")
    t = _COVER_RE.sub("", t)
    return t.strip()


def name_key(title: str) -> str:
    """곡명 동일성 비교 키 — 꼬리표를 떼고 NFKC · 소문자 · 공백 제거."""
    t = unicodedata.normalize("NFKC", clean_title(title)).casefold()
    return re.sub(r"\s+", "", t)


def is_feat(title: str) -> bool:
    """「feat.」 곡인가 (예: "Song (feat. X)")."""
    return bool(_FEAT_RE.search(title or ""))


def kst_date(published_iso: str) -> str:
    """UTC ISO → KST 날짜(YYYY-MM-DD). 파싱 실패 시 앞 10자."""
    try:
        dt = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
        return (dt.astimezone(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return (published_iso or "")[:10]


KINDS = ("original", "cover")
REJECTED_MAX = 500
SEEN_MAX = 200
READING_BATCH = 3                    # tick 당 LLM 독음 호출 상한(신곡 + 재시도 합산)
REASON_NAME_DUP, REASON_FEAT, REASON_ID_DUP, REASON_REJECTED = "name_dup", "feat", "id_dup", "rejected"
EDITABLE = ("title", "reading", "kind", "who", "date")


def norm_doc(doc: Optional[dict]) -> dict:
    """곡 문서를 `{"songs": [...], "rejected": [...], "seen": [...]}` 형태로 맞춘 새 사본(다른 키는 보존). 프론트는 `songs` 만 읽는다."""
    d = dict(doc or {})
    d["songs"] = [dict(s) for s in (d.get("songs") or [])]
    d["rejected"] = [dict(r) for r in (d.get("rejected") or [])]
    d["seen"] = [dict(r) for r in (d.get("seen") or [])]
    return d


def _entry_snapshot(e: dict) -> dict:
    """판단 기록의 입력 스냅샷 — RSS 항목에서 재현에 필요한 것만(설명은 300자까지)."""
    return {"video_id": e.get("video_id"), "title": e.get("title"), "published": e.get("published"),
            "description": (e.get("description") or "")[:300]}


def find_new_songs(entries: list[dict], existing: list[dict], *, who: str = "group", now_iso: str = "",
                   rejected: Optional[list[dict]] = None) -> tuple[list[dict], list[dict]]:
    """RSS 항목 → (새 곡 레코드 목록, 건너뜀 목록).

    새 곡: 영상 ID · 곡명(name_key)이 목록에 없고 반려 목록에도 없는 곡, feat. 제외. 같은 곡명이 묶음에 여럿이면 가장 먼저 올라온 하나만. 공개 시각 오름차순.
    건너뜀: `[{"entry": RSS 항목, "reason": name_dup|feat|id_dup|rejected, "dup_of": {"id","title"}|None, "snapshot": {...}}]`
    (`name_dup` 만 판단 기록 대상 — `dup_of` 는 같은 곡명으로 이미 있는 곡).
    새 곡 레코드는 독음을 아직 모르므로 `reading=""`, `needs_reading=True`(LLM 이 채운다 — `fill_readings`).
    """
    have_ids = {s.get("id") for s in existing}
    by_name: dict[str, dict] = {}
    for s in existing:
        by_name.setdefault(name_key(s.get("title", "")), s)
    rej_ids = {r.get("id") for r in (rejected or [])}
    rej_names = {r.get("name_key") for r in (rejected or []) if r.get("name_key")}
    out: list[dict] = []
    skipped: list[dict] = []

    def skip(e, reason, dup=None):
        skipped.append({"entry": e, "reason": reason, "snapshot": _entry_snapshot(e),
                        "dup_of": {"id": dup.get("id"), "title": dup.get("title")} if dup else None})

    for e in sorted(entries, key=lambda x: x.get("published") or ""):
        title = e["title"]
        key = name_key(title)
        if not key:
            continue
        if e["video_id"] in have_ids:
            skip(e, REASON_ID_DUP)
            continue
        if e["video_id"] in rej_ids or key in rej_names:
            skip(e, REASON_REJECTED)
            continue
        if is_feat(title):
            skip(e, REASON_FEAT)
            continue
        if key in by_name:
            skip(e, REASON_NAME_DUP, by_name[key])
            continue
        rec = {
            "id": e["video_id"],
            "title": clean_title(title),
            "kind": classify(title),
            "who": who,
            "date": kst_date(e.get("published", "")),
            "reading": "",
            "needs_reading": True,
        }
        if now_iso:
            rec["added_at"] = now_iso
        by_name[key] = rec   # 이번 묶음 안의 같은 곡명 중복 방지(먼저 올라온 것이 이긴다)
        out.append(rec)
    return out, skipped


def merge_songs(doc: Optional[dict], additions: list[dict]) -> dict:
    """곡 문서에 새 곡을 덧붙인 새 문서. 원본은 건드리지 않는다."""
    d = norm_doc(doc)
    d["songs"] = d["songs"] + [dict(a) for a in additions]
    return d


def mark_seen(doc: dict, ids_reasons: list[tuple[str, str]], now_iso: str) -> dict:
    """이미 판단 기록을 남긴 건너뜀을 `seen` 에 적는다(같은 건너뜀을 tick 마다 다시 기록하지 않게). 최근 200건."""
    d = norm_doc(doc)
    have = {r.get("id") for r in d["seen"]}
    for vid, reason in ids_reasons:
        if vid not in have:
            d["seen"].append({"id": vid, "reason": reason, "ts": now_iso})
            have.add(vid)
    d["seen"] = d["seen"][-SEEN_MAX:]
    return d


def reject_song(doc: dict, song: dict, now_iso: str, by: str = "admin") -> dict:
    """곡을 목록에서 빼고 `rejected` 에 넣는다 — 자동 감지가 같은 영상 · 곡명을 다시 등록하지 못하게(RSS 에 계속 남아 있어서)."""
    d = norm_doc(doc)
    d["songs"] = [s for s in d["songs"] if s.get("id") != song.get("id")]
    key = name_key(song.get("title", ""))
    d["rejected"] = [r for r in d["rejected"] if r.get("id") != song.get("id")]
    d["rejected"].append({"id": song.get("id"), "name_key": key, "title": song.get("title", ""), "ts": now_iso, "by": by})
    d["rejected"] = d["rejected"][-REJECTED_MAX:]
    return d


def delete_song(doc: dict, song_id: str, now_iso: str, by: str = "admin") -> tuple[dict, Optional[dict]]:
    """삭제 = 목록에서 빼기 + 차단. 반환 (새 문서, 지운 곡|None)."""
    d = norm_doc(doc)
    s = next((x for x in d["songs"] if x.get("id") == song_id), None)
    if s is None:
        return d, None
    return reject_song(d, s, now_iso, by), s


def unblock(doc: dict, ident: str) -> tuple[dict, list[dict]]:
    """차단 해제 — 영상 ID 또는 곡명 키(name_key)로. 같은 곡명 · 영상 ID 의 차단을 모두 푼다. 반환 (새 문서, 풀린 항목들)."""
    d = norm_doc(doc)
    target = next((r for r in d["rejected"] if r.get("id") == ident or r.get("name_key") == ident), None)
    if target is None:
        return d, []
    gone = [r for r in d["rejected"] if r.get("id") == target.get("id") or (target.get("name_key") and r.get("name_key") == target["name_key"])]
    d["rejected"] = [r for r in d["rejected"] if r not in gone]
    return d, gone


def validate_fields(patch: dict, *, whos: Optional[list[str]] = None) -> Optional[str]:
    """편집 · 추가 입력 검증. 문제가 있으면 사유 문자열, 없으면 None."""
    if "kind" in patch and patch["kind"] not in KINDS:
        return "구분은 오리지널 · 커버 중 하나여야 합니다"
    if "who" in patch and whos is not None and patch["who"] not in whos:
        return "부른 사람이 올바르지 않습니다"
    if "title" in patch and not str(patch["title"]).strip():
        return "곡명이 비어 있습니다"
    if "date" in patch and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(patch["date"])):
        return "날짜는 YYYY-MM-DD 형식이어야 합니다"
    return None


def edit_song(doc: dict, song_id: str, patch: dict, now_iso: str) -> tuple[dict, Optional[dict], Optional[str]]:
    """곡 수정. 독음을 직접 고치면 `reading_manual=True` · `needs_reading` 해제(LLM 이 덮지 않게). 반환 (새 문서, 고친 곡, 오류)."""
    d = norm_doc(doc)
    s = next((x for x in d["songs"] if x.get("id") == song_id), None)
    if s is None:
        return d, None, "목록에 없는 곡입니다"
    p = {k: (v.strip() if isinstance(v, str) else v) for k, v in (patch or {}).items() if k in EDITABLE}
    if not p:
        return d, None, "고칠 항목이 없습니다"
    err = validate_fields(p)
    if err:
        return d, None, err
    if "title" in p and name_key(p["title"]) != name_key(s.get("title", "")):
        other = next((x for x in d["songs"] if x.get("id") != song_id and name_key(x.get("title", "")) == name_key(p["title"])), None)
        if other:
            return d, None, f"같은 곡명이 이미 있습니다 ({other.get('title')})"
    for k, v in p.items():
        s[k] = v
    if "reading" in p:
        if p["reading"]:
            s["reading_manual"] = True
            s["needs_reading"] = False
        else:   # 독음을 비우면 LLM 이 다음 tick 에 다시 쓴다
            s["reading_manual"] = False
            s["needs_reading"] = True
    s["edited_at"] = now_iso
    return d, s, None


def add_song(doc: dict, rec: dict, now_iso: str, *, force: bool = False, whos: Optional[list[str]] = None) -> tuple[dict, Optional[dict], Optional[str]]:
    """곡 직접 추가(수동 등록). 영상 ID 가 이미 있으면 거절, 곡명이 같은 곡이 있으면 `force=True` 일 때만 추가.
    차단 목록에 있던 영상 · 곡명이면 차단도 함께 푼다(운영자가 직접 넣는 것이므로). 독음이 비어 있으면 `needs_reading`(LLM 이 채움).
    반환 (새 문서, 추가된 곡, 오류)."""
    d = norm_doc(doc)
    vid = str(rec.get("id") or "").strip()
    if not re.fullmatch(r"[\w-]{11}", vid):
        return d, None, "영상 ID 가 올바르지 않습니다(11자)"
    if any(s.get("id") == vid for s in d["songs"]):
        return d, None, "이미 목록에 있는 영상입니다"
    title = clean_title(str(rec.get("title") or ""))
    kind = rec.get("kind") or classify(str(rec.get("title") or ""))
    new = {"id": vid, "title": title, "kind": kind, "who": rec.get("who") or "group",
           "date": str(rec.get("date") or ""), "reading": str(rec.get("reading") or "").strip(), "added_at": now_iso, "manual": True}
    err = validate_fields({k: new[k] for k in ("kind", "who", "title", "date")}, whos=whos)
    if err:
        return d, None, err
    key = name_key(title)
    other = next((s for s in d["songs"] if name_key(s.get("title", "")) == key), None)
    if other and not force:
        return d, None, f"같은 곡명이 이미 있습니다 ({other.get('title')}) — 그래도 넣으려면 강제로 추가하세요"
    if new["reading"]:
        new["reading_manual"] = True
    else:
        new["needs_reading"] = True
    d["rejected"] = [r for r in d["rejected"] if r.get("id") != vid and r.get("name_key") != key]
    d["songs"].append(new)
    return d, new, None


def fill_readings(doc: dict, reader, *, limit: int = READING_BATCH, only_ids: Optional[set] = None) -> tuple[dict, list[str]]:
    """`needs_reading` 이고 운영자가 독음을 직접 정하지 않은 곡의 독음을 `reader(title) -> str|None` 으로 채운다(최대 limit 건).
    실패(None)면 그대로 두어 다음 tick 이 재시도. 반환 (새 문서, 채운 곡 id 들)."""
    d = norm_doc(doc)
    done: list[str] = []
    calls = 0
    for s in d["songs"]:
        if calls >= limit:
            break
        if not s.get("needs_reading") or s.get("reading_manual") or (only_ids is not None and s.get("id") not in only_ids):
            continue
        calls += 1
        r = reader(s.get("title", ""))
        if r:
            s["reading"] = r
            s.pop("needs_reading", None)
            done.append(s["id"])
    return d, done


_VIDEO_ID_RE = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:[^#\s]*&)?v=|live/|shorts/|embed/)|music\.youtube\.com/watch\?(?:[^#\s]*&)?v=)([\w-]{11})")


def parse_video_id(text: str) -> Optional[str]:
    """YouTube URL 또는 11자 영상 ID → 영상 ID (없으면 None)."""
    t = (text or "").strip()
    if re.fullmatch(r"[\w-]{11}", t):
        return t
    m = _VIDEO_ID_RE.search(t)
    return m.group(1) if m else None


def fetch_video_meta(video_id: str, api_key: str, *, timeout: float = 10.0, session: Optional[requests.Session] = None) -> Optional[dict]:
    """YouTube Data API `videos.list`(part=snippet, 쿼터 1)로 {title, published(UTC ISO), channel_title}. 키 없음 · 실패 · 없는 영상이면 None.
    직접 추가(수동 등록)가 제목 · 날짜를 채우는 데 쓴다 — 실패하면 호출부가 운영자 입력값을 쓴다."""
    if not api_key or not video_id:
        return None
    try:
        r = (session or requests).get("https://www.googleapis.com/youtube/v3/videos", timeout=timeout,
                                      params={"part": "snippet", "id": video_id, "key": api_key})
        r.raise_for_status()
        items = (r.json() or {}).get("items") or []
        if not items:
            return None
        sn = items[0].get("snippet") or {}
        return {"title": sn.get("title") or "", "published": sn.get("publishedAt") or "", "channel_title": sn.get("channelTitle") or ""}
    except Exception as e:  # noqa: BLE001
        log.warning("videos.list 실패 (%s): %s", video_id, e)
        return None


# 가나 독음 → 한글 (프론트 js/songs.js `kanaToHangul` 과 같은 규칙 — 어드민이 한글 독음 미리보기를 API 로 받는다)
_H_BASE = {
    "あ": "아", "い": "이", "う": "우", "え": "에", "お": "오", "か": "카", "き": "키", "く": "쿠", "け": "케", "こ": "코",
    "さ": "사", "し": "시", "す": "스", "せ": "세", "そ": "소", "た": "타", "ち": "치", "つ": "츠", "て": "테", "と": "토",
    "な": "나", "に": "니", "ぬ": "누", "ね": "네", "の": "노", "は": "하", "ひ": "히", "ふ": "후", "へ": "헤", "ほ": "호",
    "ま": "마", "み": "미", "む": "무", "め": "메", "も": "모", "や": "야", "ゆ": "유", "よ": "요",
    "ら": "라", "り": "리", "る": "루", "れ": "레", "ろ": "로", "わ": "와", "を": "오",
    "が": "가", "ぎ": "기", "ぐ": "구", "げ": "게", "ご": "고", "ざ": "자", "じ": "지", "ず": "즈", "ぜ": "제", "ぞ": "조",
    "だ": "다", "ぢ": "지", "づ": "즈", "で": "데", "ど": "도", "ば": "바", "び": "비", "ぶ": "부", "べ": "베", "ぼ": "보",
    "ぱ": "파", "ぴ": "피", "ぷ": "푸", "ぺ": "페", "ぽ": "포",
}
_H_COMBO = {
    "き": "캬큐쿄", "し": "샤슈쇼", "ち": "차추초", "に": "냐뉴뇨", "ひ": "햐휴효", "み": "먀뮤묘", "り": "랴류료",
    "ぎ": "갸규교", "じ": "자주조", "び": "뱌뷰뵤", "ぴ": "퍄퓨표",
}
_H_INIT = {"카": "가", "키": "기", "쿠": "구", "케": "게", "코": "고", "타": "다", "치": "지", "츠": "즈", "테": "데", "토": "도"}


def kana_to_hangul(src: str) -> str:
    """가나 독음 → 한글(외래어 표기 단순화: 어두 か·た행 가·다, ん=ㄴ · っ=ㅅ 받침, 장음 생략). 가나가 아닌 글자는 그대로."""
    t = "".join(chr(ord(c) - 96) if "ァ" <= c <= "ヶ" else c for c in str(src or ""))
    out = ""
    at_start = True
    i = 0

    def last():
        return ord(out[-1]) if out else 0

    def no_batchim(c):
        return 0xAC00 <= c <= 0xD7A3 and (c - 0xAC00) % 28 == 0

    while i < len(t):
        c = t[i]
        n = t[i + 1] if i + 1 < len(t) else ""
        if c in _H_COMBO and n and n in "ゃゅょ":
            out += _H_COMBO[c]["ゃゅょ".index(n)]
            i += 2
            at_start = False
            continue
        if c == "ん":
            if no_batchim(last()):
                out = out[:-1] + chr(last() + 4)
            i += 1
            continue
        if c == "っ":
            if no_batchim(last()):
                out = out[:-1] + chr(last() + 19)
            i += 1
            continue
        if c == "ー":
            i += 1
            continue
        if c == "う" and 0xAC00 <= last() <= 0xD7A3 and ((last() - 0xAC00) % 588) // 28 in (8, 12, 13, 17):
            i += 1
            continue
        if c in _H_BASE:
            h = _H_BASE[c]
            if at_start and h in _H_INIT:
                h = _H_INIT[h]
            out += h
            at_start = False
            i += 1
            continue
        out += c
        at_start = c.isspace()
        i += 1
    return out


if __name__ == "__main__":
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    n = 0

    def ok(cond, msg):
        global n
        n += 1
        assert cond, f"FAIL: {msg}"
        print(f"[OK] {msg}")

    # 분류 · 정규화
    ok(classify("オリオンをなぞる (Cover)") == "cover", "(Cover) → cover")
    ok(classify("曲 (cover)") == "cover" and classify("曲 （COVER）") == "cover", "(cover) 소문자 · 전각 괄호 → cover")
    ok(classify("夢我夢中") == "original", "표기 없음 → original")
    ok(classify("Cover Me") == "original", "제목 중간의 Cover 는 표기가 아님")
    ok(clean_title("オリオンをなぞる (Cover)") == "オリオンをなぞる", "꼬리표 제거")
    ok(clean_title("オリオンをなぞる【Covered by 夢限大みゅーたいぷ】") == "オリオンをなぞる", "Covered by 꼬리 제거")
    ok(name_key("ＺＥＡＬ of Proud (Cover)") == name_key("zeal of proud"), "곡명 키: 전각 · 대소문자 · 공백 · 꼬리표 무시")
    ok(is_feat("Song (feat. Someone)") and is_feat("Song ft. X") and not is_feat("Defeat the Odds"), "feat 판별 (단어 일부는 제외)")
    ok(kst_date("2026-09-27T11:00:19+00:00") == "2026-09-27" and kst_date("2026-09-27T16:00:00Z") == "2026-09-28", "UTC → KST 날짜 (자정 경계)")

    # 실제 RSS 발췌(fixtures/topic_feed.sample.xml, 2026-10-06 수집)로 감지
    entries = parse_feed_entries((root / "fixtures" / "topic_feed.sample.xml").read_text(encoding="utf-8"))
    ok(len(entries) == 9 and entries[0]["video_id"] == "jlnbYlVunfg", "RSS 파싱 9건 · 순서 유지")
    ok("Released on: 2026-09-28" in next(e for e in entries if e["video_id"] == "Fp2a-MhCFVw")["description"], "설명(발매일) 파싱")
    existing = json.loads((root / "src" / "frontend" / "assets" / "songs.json").read_text(encoding="utf-8"))["songs"]
    new, skipped = find_new_songs(entries, existing, now_iso="2026-10-06T00:00:00Z")
    names = {s["title"]: s for s in new}
    ok("夢我夢中" in names and names["夢我夢中"]["id"] == "Fp2a-MhCFVw", "새 곡 夢我夢中 감지")
    ok(names["夢我夢中"]["kind"] == "original" and names["夢我夢中"]["who"] == "group" and names["夢我夢中"]["date"] == "2026-09-27", "夢我夢中: original · group · 업로드 KST 날짜")
    ok(names["夢我夢中"]["reading"] == "" and names["夢我夢中"]["needs_reading"] is True, "독음은 빈 값 + needs_reading(LLM 이 채움)")
    ok("これはぼくたちの生存のあらすじ" not in names and "オリオンをなぞる" not in names, "이미 있는 곡명은 등록 안 함 ((Cover) 표기 · 영상 ID 무관)")
    ok(names["うちゅうのふしぎ"]["id"] == "TedsUWY90Vs", "같은 곡명이 묶음에 둘이면 먼저 올라온 영상만")
    ok(names["唱"]["kind"] == "cover" and names["唱"]["title"] == "唱", "(Cover) 곡: kind=cover · 제목에서 꼬리표 제거")
    ok(len({s["id"] for s in new}) == len(new) and [s["date"] for s in new] == sorted(s["date"] for s in new), "중복 없음 · 오름차순")
    # 건너뜀 사유
    by_id = {s["entry"]["video_id"]: s for s in skipped}
    ok(by_id["jlnbYlVunfg"]["reason"] == "name_dup" and by_id["jlnbYlVunfg"]["dup_of"]["id"] == "4XbNBhZuBoA", "건너뜀: 곡명 중복 + 어느 곡과 같은지(dup_of)")
    ok(by_id["zPieTviOC54"]["reason"] == "name_dup" and by_id["zPieTviOC54"]["dup_of"]["id"] == "TedsUWY90Vs", "건너뜀: 묶음 안 중복은 먼저 올라온 곡이 dup_of")
    ok(by_id["1_WyE1U0f4E"]["reason"] == "id_dup", "건너뜀: 이미 목록에 있는 영상은 id_dup (곡명이 같아도 ID 가 먼저)")
    ok(find_new_songs([{"video_id": "QQQQQQQQQQQ", "title": "オリオンをなぞる (Cover)", "published": "2026-10-01T00:00:00+00:00"}], existing)[1][0]["reason"] == "name_dup", "(Cover) 표기 차이는 같은 곡명(name_dup)")
    ok(by_id["4XbNBhZuBoA"]["reason"] == "id_dup", "건너뜀: 이미 있는 영상 ID 는 id_dup")
    ok(len(skipped) == 5, "건너뜀 5건 — " + str([(s["entry"]["video_id"], s["reason"]) for s in skipped]))
    feat = [{"video_id": "x" * 11, "title": "Duet (feat. Someone)", "published": "2026-10-01T00:00:00+00:00", "description": ""}]
    f_new, f_skip = find_new_songs(feat, existing)
    ok(f_new == [] and f_skip[0]["reason"] == "feat", "feat. 곡은 등록 안 함 (사유 feat)")
    i_new, i_skip = find_new_songs([{"video_id": existing[0]["id"], "title": "아무거나", "published": "2026-10-01T00:00:00+00:00"}], existing)
    ok(i_new == [] and i_skip[0]["reason"] == "id_dup", "이미 있는 영상 ID → id_dup")

    # 병합 · 멱등
    merged = merge_songs({"songs": existing}, new)
    ok(len(merged["songs"]) == len(existing) + len(new) and len(existing) == 65, "병합: 원본 불변 · 곡 수 증가")
    ok(find_new_songs(entries, merged["songs"])[0] == [], "병합 뒤 재실행하면 새 곡 없음(멱등)")
    ok(merge_songs(None, new)["songs"] == new and merge_songs(None, new)["rejected"] == [], "문서가 없으면 새로 만듦(rejected · seen 빈 목록)")

    # 삭제 · 반려 → 재등록 차단 → 차단 해제
    doc = merge_songs({"songs": existing}, new)
    doc2, gone = delete_song(doc, "Fp2a-MhCFVw", "2026-10-06T01:00:00Z", by="admin")
    ok(gone["title"] == "夢我夢中" and all(s["id"] != "Fp2a-MhCFVw" for s in doc2["songs"]), "삭제: 목록에서 빠짐")
    ok(doc2["rejected"][0]["id"] == "Fp2a-MhCFVw" and doc2["rejected"][0]["name_key"] == name_key("夢我夢中"), "삭제: rejected 에 영상 ID · 곡명 키")
    r_new, r_skip = find_new_songs(entries, doc2["songs"], rejected=doc2["rejected"])
    ok(all(s["id"] != "Fp2a-MhCFVw" for s in r_new) and any(s["reason"] == "rejected" and s["entry"]["video_id"] == "Fp2a-MhCFVw" for s in r_skip), "삭제한 곡은 RSS 에 남아 있어도 재등록 안 됨(rejected)")
    other_vid = [{"video_id": "ZZZZZZZZZZZ", "title": "夢我夢中", "published": "2026-10-09T00:00:00+00:00"}]
    ok(find_new_songs(other_vid, doc2["songs"], rejected=doc2["rejected"])[0] == [], "삭제한 곡명은 다른 영상 ID 로 올라와도 차단(곡명 키)")
    doc3, freed = unblock(doc2, "Fp2a-MhCFVw")
    ok(len(freed) == 1 and doc3["rejected"] == [], "차단 해제(영상 ID)")
    ok(any(s["id"] == "Fp2a-MhCFVw" for s in find_new_songs(entries, doc3["songs"], rejected=doc3["rejected"])[0]), "차단 해제 뒤 다시 감지")
    ok(unblock(doc2, name_key("夢我夢中"))[1] and unblock(doc2, "없는키")[1] == [], "차단 해제: 곡명 키로도 가능 · 없는 항목은 빈 결과")

    # 수정
    d4, s4, err = edit_song(doc, "Fp2a-MhCFVw", {"reading": "ゆめがむちゅう", "kind": "cover"}, "2026-10-06T02:00:00Z")
    ok(err is None and s4["reading"] == "ゆめがむちゅう" and s4["kind"] == "cover" and s4["reading_manual"] is True and s4.get("needs_reading") is False, "수정: 독음 직접 입력 → reading_manual · needs_reading 해제")
    ok(s4["edited_at"] == "2026-10-06T02:00:00Z", "수정: edited_at 기록")
    ok(edit_song(doc, "Fp2a-MhCFVw", {"kind": "solo"}, "t")[2] is not None, "수정: 잘못된 kind 거절")
    ok(edit_song(doc, "없는id", {"title": "x"}, "t")[2] == "목록에 없는 곡입니다", "수정: 없는 곡")
    ok("같은 곡명" in (edit_song(doc, "Fp2a-MhCFVw", {"title": "コハク"}, "t")[2] or ""), "수정: 다른 곡과 곡명이 같아지는 것 거절")
    ok(edit_song(doc, "Fp2a-MhCFVw", {"date": "2026/10/06"}, "t")[2] is not None, "수정: 날짜 형식 검증")

    d4b, s4b, _ = edit_song(d4, "Fp2a-MhCFVw", {"reading": ""}, "t")
    ok(s4b["reading"] == "" and s4b["needs_reading"] is True and s4b["reading_manual"] is False, "수정: 독음을 비우면 LLM 이 다시 쓰도록 needs_reading")

    # 직접 추가
    d5, s5, err = add_song(doc2, {"id": "AAAAAAAAAAA", "title": "新曲 (Cover)", "who": "arale", "date": "2026-10-05"}, "2026-10-06T03:00:00Z", whos=["arale", "group"])
    ok(err is None and s5["kind"] == "cover" and s5["title"] == "新曲" and s5["manual"] and s5["needs_reading"], "직접 추가: (Cover) → cover · 꼬리표 제거 · 독음은 LLM 대기")
    ok(add_song(d5, {"id": "AAAAAAAAAAA", "title": "다른곡", "date": "2026-10-05"}, "t")[2] == "이미 목록에 있는 영상입니다", "직접 추가: 영상 ID 중복 거절")
    ok("같은 곡명" in (add_song(d5, {"id": "BBBBBBBBBBB", "title": "新曲", "date": "2026-10-05"}, "t")[2] or ""), "직접 추가: 곡명 중복은 force 없이 거절")
    ok(add_song(d5, {"id": "BBBBBBBBBBB", "title": "新曲", "date": "2026-10-05"}, "t", force=True)[2] is None, "직접 추가: force 면 곡명 중복도 추가")
    ok(add_song(d5, {"id": "short", "title": "x", "date": "2026-10-05"}, "t")[2] is not None, "직접 추가: 영상 ID 형식 검증")
    d6, s6, err = add_song(doc2, {"id": "Fp2a-MhCFVw", "title": "夢我夢中", "date": "2026-09-27", "reading": "ゆめがむちゅう"}, "t")
    ok(err is None and d6["rejected"] == [] and s6["reading_manual"] and "needs_reading" not in s6, "직접 추가: 차단돼 있던 곡이면 차단도 해제 · 독음 입력하면 LLM 안 씀")

    # 독음 채우기 (가짜 LLM)
    calls = []

    def fake(t):
        calls.append(t)
        return None if t == "唱" else "よみ" + str(len(calls))

    d7, done = fill_readings(merge_songs(None, new), fake, limit=3)
    ok(len(calls) == 3 and len(done) == 2 and sum(1 for s in d7["songs"] if s.get("needs_reading")) == len(new) - 2, "독음: tick 당 상한 3건 · 실패(None)는 needs_reading 유지(재시도)")
    d8, done8 = fill_readings(d7, fake, limit=10)
    ok(all("needs_reading" not in s or s["title"] == "唱" for s in d8["songs"]), "독음: 다음 tick 에서 이어서 채움 · 실패한 곡만 남음")
    manual_doc = merge_songs(None, [dict(new[0], reading="しゅどう", reading_manual=True, needs_reading=True)])
    ok(fill_readings(manual_doc, fake)[1] == [], "독음: reading_manual 곡은 LLM 이 덮지 않음")

    # seen
    d9 = mark_seen({"songs": []}, [("a", "name_dup"), ("b", "name_dup")], "t1")
    ok([r["id"] for r in mark_seen(d9, [("a", "name_dup"), ("c", "name_dup")], "t2")["seen"]] == ["a", "b", "c"], "seen: 이미 적은 건 다시 안 적음")
    big = mark_seen({}, [(str(i), "name_dup") for i in range(SEEN_MAX + 20)], "t")
    ok(len(big["seen"]) == SEEN_MAX and big["seen"][-1]["id"] == str(SEEN_MAX + 19), "seen: 최근 200건만 유지")
    ok(norm_doc({"songs": [{"id": "a"}], "extra": 1})["extra"] == 1 and norm_doc(None) == {"songs": [], "rejected": [], "seen": []}, "norm_doc: 다른 키 보존 · 기본형")
    # URL 파싱 · 한글 독음
    ok(parse_video_id("https://youtu.be/Fp2a-MhCFVw") == "Fp2a-MhCFVw" and parse_video_id("https://www.youtube.com/watch?v=Fp2a-MhCFVw&t=3") == "Fp2a-MhCFVw", "URL → 영상 ID (youtu.be · watch)")
    ok(parse_video_id("https://music.youtube.com/watch?v=Fp2a-MhCFVw") == "Fp2a-MhCFVw" and parse_video_id("Fp2a-MhCFVw") == "Fp2a-MhCFVw", "music.youtube · 11자 ID 그대로")
    ok(parse_video_id("그냥 글") is None and parse_video_id("") is None, "영상 ID 아님 → None")
    ok(kana_to_hangul("ゆきとき") == "유키토키" and kana_to_hangul("ちょうわくせいXへのたび") == "초와쿠세이X헤노타비" and kana_to_hangul("まよなかゆうえんち") == "마요나카유엔치", "가나 → 한글 독음(프론트 kanaToHangul 과 같은 규칙)")
    ok(kana_to_hangul("ジレンマ") == "지렌마" and kana_to_hangul("いっぱい") == "잇파이" and kana_to_hangul("") == "", "가타카나 · ん · っ · 빈 문자열")
    print(f"\n{n}개 통과")
