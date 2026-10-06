"""신곡 자동 감지 (v4.2.0) — 토픽 채널 RSS 에서 새 곡을 찾아 곡 목록(`songs.json`)에 등록한다. 순수 로직 + RSS 조회.

배경: 곡은 그룹 공식 채널이 아니라 음원 자동 생성 채널(`Mugendai MewType - Topic`)에 올라온다. 이 채널은 방송이 아니라
`preview.json` · FSM 과 무관하므로 방송 파이프라인(`preview_build`)에 끼우지 않고 별도 경로로 둔다(`handlers._detect_new_songs`).
RSS 는 쿼터 0 이고, 새 곡이 있을 때만 쓰기가 일어난다.

규칙 (운영자 결정 2026-10-06):
  - 곡명이 이미 데이터에 있으면 등록하지 않는다(영상 ID 가 달라도). 새 곡명만 등록.
  - 구분은 제목으로: 끝에 「(Cover)」(대소문자 · 전각 괄호 무관)가 붙으면 `cover`, 아니면 `original`. 다른 표기(예: 「(Solo)」)에 대한 규칙은 두지 않는다.
  - `feat.` 곡은 등록하지 않는다.
  - 독음(`reading`)은 RSS 에 없으므로 빈 문자열 — 운영자가 따로 채운다.
피드 버스트(한 번에 15개 넘게 올라오는 경우)는 아직 고려하지 않는다.

순수 함수: parse_feed_entries / classify / name_key / is_feat / kst_date / find_new_songs / merge_songs. 네트워크는 fetch_feed_entries 뿐.
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


def find_new_songs(entries: list[dict], existing: list[dict], *, who: str = "group", now_iso: str = "") -> list[dict]:
    """RSS 항목 중 곡 목록에 없는 새 곡을 곡 레코드로 만든다.

    제외: 이미 있는 영상 ID · 이미 있는 곡명(name_key) · feat. 곡 · 같은 곡명이 이번 묶음에 여러 개면 가장 먼저 올라온 것 하나만.
    반환은 공개 시각 오름차순.
    """
    have_ids = {s.get("id") for s in existing}
    have_names = {name_key(s.get("title", "")) for s in existing}
    out: list[dict] = []
    for e in sorted(entries, key=lambda x: x.get("published") or ""):
        title = e["title"]
        key = name_key(title)
        if not key or e["video_id"] in have_ids or key in have_names or is_feat(title):
            continue
        have_names.add(key)   # 이번 묶음 안의 같은 곡명 중복 방지
        rec = {
            "id": e["video_id"],
            "title": clean_title(title),
            "kind": classify(title),
            "who": who,
            "date": kst_date(e.get("published", "")),
            "reading": "",
        }
        if now_iso:
            rec["added_at"] = now_iso
        out.append(rec)
    return out


def merge_songs(doc: Optional[dict], additions: list[dict]) -> dict:
    """곡 문서(`{"songs": [...]}`)에 새 곡을 덧붙인 새 문서. 원본은 건드리지 않는다."""
    songs = list((doc or {}).get("songs") or [])
    return {**(doc or {}), "songs": songs + additions}


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
    new = find_new_songs(entries, existing, now_iso="2026-10-06T00:00:00Z")
    names = {s["title"]: s for s in new}
    ok("夢我夢中" in names and names["夢我夢中"]["id"] == "Fp2a-MhCFVw", "새 곡 夢我夢中 감지")
    ok(names["夢我夢中"]["kind"] == "original" and names["夢我夢中"]["who"] == "group" and names["夢我夢中"]["date"] == "2026-09-27", "夢我夢中: original · group · 업로드 KST 날짜")
    ok(names["夢我夢中"]["reading"] == "", "독음은 빈 값")
    ok("これはぼくたちの生存のあらすじ" not in names, "이미 있는 곡명(영상 ID 가 달라도) 은 등록 안 함")
    ok("オリオンをなぞる" not in names, "이미 있는 곡명((Cover) 표기 유무 무관) 은 등록 안 함")
    ok(names["うちゅうのふしぎ"]["id"] == "TedsUWY90Vs", "같은 곡명이 묶음에 둘이면 먼저 올라온 영상만")
    ok(names["唱"]["kind"] == "cover" and names["唱"]["title"] == "唱", "(Cover) 곡: kind=cover · 제목에서 꼬리표 제거")
    ok(len({s["id"] for s in new}) == len(new) and [s["date"] for s in new] == sorted(s["date"] for s in new), "중복 없음 · 오름차순")
    # feat 제외 · 재실행 멱등
    feat = [{"video_id": "x" * 11, "title": "Duet (feat. Someone)", "published": "2026-10-01T00:00:00+00:00", "description": ""}]
    ok(find_new_songs(feat, existing) == [], "feat. 곡은 등록 안 함")
    merged = merge_songs({"songs": existing}, new)
    ok(len(merged["songs"]) == len(existing) + len(new) and len(existing) == 65, "병합: 원본 불변 · 곡 수 증가")
    ok(find_new_songs(entries, merged["songs"]) == [], "병합 뒤 재실행하면 새 곡 없음(멱등)")
    ok(merge_songs(None, new)["songs"] == new, "문서가 없으면 새로 만듦")
    print(f"\n{n}개 통과")
