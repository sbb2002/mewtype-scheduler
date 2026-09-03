"""X(트위터) 예고 릴레이 — 파서 + scheduled 행 머지 (순수 함수).

계약: docs/plan/v2_3_x_relay.md

흐름:
  Automate(폰) 가 삼성 브라우저 웹푸시 알림 텍스트를 `telegram_app` 의 공개
  `POST /ingest` 로 그대로 POST → 여기서 `@BDP_yumemita` 일일 스케줄 트윗을
  파싱해 `schedule.json` 의 `status=="scheduled"` 행(= YouTube 영상이 아직 없는
  최하 단계)으로 반영한다. video_id 가 없으므로 Cloud Tasks / pending 은 안 탄다.
  이후 정기 `/tick` 의 reconcile 이 실물 upcoming 이 뜨면 supersede, TTL 로 소멸.

파서 A(`parse_bdp_schedule`) 만 구현. 멤버 개인 예고(파서 B)는 후속.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
UTC = timezone.utc

# 일본어 이름 부분매치 → channel_key
NAME_TO_KEY: list[tuple[str, str]] = [
    ("あられ", "arale"),
    ("ユノ", "yuno"),
    ("ののか", "nonoka"),
    ("律", "ritsu"),
    ("都子", "miyako"),
]

# 5인 전원 (config/channels.json channel_order 와 동일 — 순수 모듈이라 하드코딩)
ALL_KEYS = ["arale", "yuno", "nonoka", "ritsu", "miyako"]

# 트윗 앞머리 아이콘 → 방송 종류. 목록에 없는 이모지는 kind="unknown" + icon 보존.
ICON_KIND: dict[str, str] = {
    "🎮": "game",
    "💭": "talk",
    "🎤": "song",
    "💪": "collab",
    "☀": "morning",
}

KIND_KO = {
    "game": "게임",
    "talk": "잡담",
    "song": "노래",
    "collab": "합방",
    "morning": "아침",
    "unknown": "",
}

# "8/30(日) 配信スケジュール" / "8/17(月)の配信スケジュール🌟"
HEADER_RE = re.compile(r"(\d{1,2})/(\d{1,2})\([日月火水木金土]\)\s*の?\s*配信スケジュール")
# "11:00〜" / "23:30頃〜"
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})(頃)?〜")
# 온전한 YouTube 영상 URL (id 11자 + 잘림표시 없음). watch/live/shorts 모두.
# 트윗에서 "…" 로 잘린 URL 은 링크가 깨지므로 매치하지 않는다.
YT_VIDEO_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?youtube\.com/(?:live/|watch\?v=|shorts/)([\w-]{11})(?![\w-])"
)

# "出演情報" 계열 — @BDP_yumemita 가 외부 이벤트/합방 출연을 알릴 때 (일일 스케줄과 서식 다름).
#   ＼出演情報／  9/10(木) 22:00頃〜  「이벤트명」  夢限大みゅーたいぷ 5名が出演  <영상 URL>
APPEARANCE_MARK_RE = re.compile(r"出演情報|出演決定|出演告知|出演のお知らせ")
APPEARANCE_DT_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})\([日月火水木金土]\)\s*(\d{1,2}):(\d{2})(頃)?\s*〜"
)
APPEARANCE_COUNT_RE = re.compile(r"(\d+)\s*名(?:が)?\s*(?:出演|参加|登場)")
_TITLE_RE = re.compile(r"[「『]([^」』\n]{1,60})[」』]")

_FW = str.maketrans("０１２３４５６７８９：", "0123456789:")

_RANK = {"live": 0, "upcoming": 1, "scheduled": 2}

# scheduled 행 TTL: 시각 없을 때 first_seen 으로부터 (reconcile 과 동일 상수)
_NO_TIME_TTL_SEC = 18 * 3600


def normalize(text: str) -> str:
    """개행·전각 문자·물결표 통일. VS16(️) 제거."""
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.translate(_FW)
    t = t.replace("～", "〜").replace("~", "〜")
    t = t.replace("️", "")
    return t


def _infer_year(month: int, day: int, now_jst: datetime) -> int:
    """(month, day) 에 now 와 가장 가까운 연도를 붙인다 (연말 롤오버 대응)."""
    best: tuple[int, int] | None = None
    for yr in (now_jst.year - 1, now_jst.year, now_jst.year + 1):
        try:
            d = datetime(yr, month, day, tzinfo=JST)
        except ValueError:
            continue
        diff = abs((d.date() - now_jst.date()).days)
        if best is None or diff < best[0]:
            best = (diff, yr)
    return best[1] if best else now_jst.year


def _names(line: str) -> tuple[str | None, list[str]]:
    """줄에서 인식되는 이름들 → (주채널, 콜라보상대들). 등장 순서 유지."""
    found: list[tuple[int, str]] = []
    for token, key in NAME_TO_KEY:
        idx = line.find(token)
        if idx >= 0:
            found.append((idx, key))
    found.sort()
    keys: list[str] = []
    for _, k in found:
        if k not in keys:
            keys.append(k)
    if not keys:
        return None, []
    return keys[0], keys[1:]


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _video_url_near(lines: list[str], idx: int) -> str | None:
    """엔트리 줄(idx) 바로 뒤의 URL 줄에서 온전한 YouTube 영상 URL 을 찾는다.

    트윗 서식은 `[아이콘]HH:MM〜 이름` 다음 줄에 URL 이 온다. 다음 엔트리(시각 줄)나
    헤더를 만나면 중단. 잘린 URL(`…`)이나 `@handle` 채널 URL 은 대상 아님.
    """
    for k in range(idx + 1, min(idx + 3, len(lines))):
        cand = lines[k].strip()
        if not cand:
            continue
        if TIME_RE.search(cand) or HEADER_RE.search(cand):
            break
        hit = YT_VIDEO_RE.search(cand)
        if hit:
            u = hit.group(0)
            return u if u.startswith("http") else "https://" + u
        break  # 엔트리 직후 첫 비어있지 않은 줄이 URL 이 아니면 없음
    return None


def parse_bdp_schedule(text: str, now_iso: str) -> list[dict]:
    """`@BDP_yumemita` 일일 스케줄 트윗 → scheduled 행 리스트.

    헤더(`M/D(曜) 配信スケジュール`)가 없으면 `[]`.
    한 줄에 시각이 여러 개면(예: `21:30〜／☀明日朝7:00〜`) 시각마다 1행.
    `明日` 가 그 시각 앞에 있으면 헤더 날짜 +1일.
    """
    t = normalize(text)
    m = HEADER_RE.search(t)
    if not m:
        return []

    try:
        now_jst = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).astimezone(JST)
    except (ValueError, AttributeError):
        now_jst = datetime.now(JST)

    month, day = int(m.group(1)), int(m.group(2))
    base = datetime(_infer_year(month, day, now_jst), month, day, tzinfo=JST)

    rows: list[dict] = []
    lines = t.split("\n")
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        times = list(TIME_RE.finditer(line))
        if not times:
            continue
        key, collab = _names(line)
        if not key:
            continue
        members_only = "メン限" in line
        line_has_collab = bool(collab) or "×" in line
        # 합동 방송은 5인 공동명의(公式) 채널에서 함 — 멤버 개인 채널이 아니다.
        # 트윗의 영상 URL 을 그대로 링크로 쓰고, host="group" 으로 표시한다.
        video_url = _video_url_near(lines, idx) if line_has_collab else None

        for i, tm in enumerate(times):
            hh, mm = int(tm.group(1)), int(tm.group(2))
            # 일본 심야 표기: 24:00〜29:59 = 다음날 00:00〜05:59
            hour_carry, hh = divmod(hh, 24)
            approx = bool(tm.group(3))
            seg_start = times[i - 1].end() if i > 0 else 0
            seg = line[seg_start:tm.start()]
            # 이 시각 직전 구간의 아이콘(없으면 줄 맨앞 아이콘)
            icon = next((c for c in seg if c in ICON_KIND), "")
            if not icon and i == 0:
                lead = line.lstrip()
                if lead[:1] in ICON_KIND:
                    icon = lead[0]
            plus1 = "明日" in line[:tm.start()]

            start = (base + timedelta(days=(1 if plus1 else 0) + hour_carry)).replace(
                hour=hh, minute=mm
            )
            start_z = _iso_z(start)
            kind = "collab" if line_has_collab else ICON_KIND.get(icon, "unknown")
            # 회원전용은 API 로 종료를 못 보므로 TTL 을 넉넉히(5h). 공개는 3h.
            ttl_h = 5 if members_only else 3
            rows.append(
                {
                    "status": "scheduled",
                    "channel_key": key,
                    "sched_id": f"sched:{key}:{start_z}",
                    "video_id": None,
                    "title": None,
                    "url": video_url,
                    "host": "group" if line_has_collab else None,
                    "thumbnail": None,
                    "scheduled_start": start_z,
                    "start_approx": approx,
                    "kind": kind,
                    "icon": icon,
                    "members_only": members_only,
                    "collab_with": collab,
                    "source": "bdp_schedule",
                    "source_at": now_iso,
                    "first_seen": now_iso,
                    "last_updated": now_iso,
                    "assumed_live": False,   # 예고 시각 도달 시 reconcile 이 True (회원전용 추정용)
                    "expires_at": _iso_z(start.astimezone(UTC) + timedelta(hours=ttl_h)),
                }
            )
    return rows


def parse_appearance(text: str, now_iso: str) -> list[dict]:
    """`出演情報` 계열 트윗 → scheduled(host="group") 행 1개. 형식 아니면 `[]`.

    일일 스케줄과 서식이 다르다: `M/D(曜) HH:MM頃〜` 단일 시각 + `「이벤트명」`
    + `N名が出演` + 영상 URL. 5인(또는 이름이 직접 나온 멤버) 전원 레인에 팬아웃되도록
    `channel_key` + `collab_with` 로 나눠 담는다.
    """
    t = normalize(text)
    if not APPEARANCE_MARK_RE.search(t):
        return []
    dt = APPEARANCE_DT_RE.search(t)
    if not dt:
        return []

    try:
        now_jst = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).astimezone(JST)
    except (ValueError, AttributeError):
        now_jst = datetime.now(JST)

    month, day = int(dt.group(1)), int(dt.group(2))
    hh, mm = int(dt.group(3)), int(dt.group(4))
    approx = bool(dt.group(5))
    day_carry, hh = divmod(hh, 24)          # 심야표기 24:00〜
    base = datetime(_infer_year(month, day, now_jst), month, day, tzinfo=JST)
    start = (base + timedelta(days=day_carry)).replace(hour=hh, minute=mm)
    start_z = _iso_z(start)

    # 참여자: 이름이 직접 나오면 그것, 아니면 "N名"/"夢限大みゅーたいぷ" → 전원
    key, collab = _names(t)
    if key:
        members = [key, *collab]
    else:
        cnt = APPEARANCE_COUNT_RE.search(t)
        n = int(cnt.group(1)) if cnt else 0
        whole = ("夢限大みゅーたいぷ" in t) or ("ゆめみた" in t)
        members = list(ALL_KEYS) if (n >= len(ALL_KEYS) or (whole and n == 0)) else []
    if not members:
        return []

    tm = _TITLE_RE.search(t)
    title = tm.group(1).lstrip("#＃ ").strip() if tm else None
    hit = YT_VIDEO_RE.search(t)
    url = None
    if hit:
        u = hit.group(0)
        url = u if u.startswith("http") else "https://" + u

    return [
        {
            "status": "scheduled",
            "channel_key": members[0],
            "sched_id": f"sched:{members[0]}:{start_z}",
            "video_id": None,
            "title": title,
            "url": url,
            "host": "group",
            "thumbnail": None,
            "scheduled_start": start_z,
            "start_approx": approx,
            "kind": "collab",
            "icon": "📺",
            "members_only": False,
            "collab_with": members[1:],
            "source": "bdp_appearance",
            "source_at": now_iso,
            "first_seen": now_iso,
            "last_updated": now_iso,
            "assumed_live": False,
            "expires_at": _iso_z(start.astimezone(UTC) + timedelta(hours=3)),
        }
    ]


def parse(text: str, now_iso: str) -> list[dict]:
    """트윗 → scheduled 행. 일일 스케줄 우선, 없으면 出演情報."""
    return parse_bdp_schedule(text, now_iso) or parse_appearance(text, now_iso)


def looks_relayable(text: str) -> bool:
    """폰이 relay 할 가치가 있는(스케줄/출연) 트윗인지 — 큐 적재 가드용."""
    t = text or ""
    return "配信スケジュール" in t or bool(APPEARANCE_MARK_RE.search(normalize(t)))


def _jst_date(iso: str) -> str:
    try:
        return (
            datetime.fromisoformat(iso.replace("Z", "+00:00"))
            .astimezone(JST)
            .strftime("%Y-%m-%d")
        )
    except (ValueError, AttributeError):
        return ""


def _jst_hm(iso: str | None) -> str:
    try:
        return (
            datetime.fromisoformat(iso.replace("Z", "+00:00"))
            .astimezone(JST)
            .strftime("%H:%M")
        )
    except (ValueError, AttributeError):
        return "--:--"


def _sort_broadcasts(bcasts: list[dict]) -> list[dict]:
    return sorted(
        bcasts,
        key=lambda b: (
            _RANK.get(b.get("status"), 3),
            b.get("scheduled_start") is None,
            b.get("scheduled_start") or "",
            b.get("video_id") or b.get("sched_id") or "",
        ),
    )


def merge_scheduled(prev_schedule: dict, rows: list[dict], now_iso: str) -> dict:
    """이전 schedule.json + 새 scheduled 행 → 새 schedule.json.

    같은 소스(`bdp_schedule`)·같은 JST 날짜의 기존 scheduled 행은 **전량 교체**.
    다른 날짜·다른 소스·`upcoming`/`live` 행은 그대로 둔다.
    """
    # ponytail: replace-by-date 는 항상 교체. 푸시 알림이 "Show more" 로 잘려 앞
    # 2~3건만 오면 그 날 나머지 엔트리가 사라진다. Phase 1 테스트로 잘림 여부 확인 후,
    # 잘리면 여기에 "엔트리 수 < 기존 → upsert(교체 아님)" 가드를 넣는다.
    prev = prev_schedule or {}
    broadcasts = [dict(b) for b in prev.get("broadcasts", [])]

    new_dates = {
        _jst_date(r.get("scheduled_start") or r.get("source_at") or "") for r in rows
    }
    kept: list[dict] = []
    for b in broadcasts:
        if b.get("status") == "scheduled" and b.get("source") == "bdp_schedule":
            d = _jst_date(b.get("scheduled_start") or b.get("source_at") or "")
            if d in new_dates:
                continue  # 교체됨
        kept.append(b)
    kept.extend(rows)

    out = dict(prev)
    out["broadcasts"] = _sort_broadcasts(kept)
    out["generated_at"] = now_iso
    return out


def summary_text(rows: list[dict], channels_cfg: dict | None = None) -> str:
    """ingest 반영 결과 → Telegram DM 본문 (계약 G)."""
    chan = (channels_cfg or {}).get("channels", {})
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(
            _jst_date(r.get("scheduled_start") or r.get("source_at") or ""), []
        ).append(r)

    lines = [f"🛸 <b>X 스케줄 반영</b> ({len(rows)}건)"]
    for d in sorted(by_date):
        lines.append(f"\n<b>{d or '?'}</b>")
        for r in sorted(by_date[d], key=lambda x: x.get("scheduled_start") or ""):
            nm = chan.get(r["channel_key"], {}).get("name_ko", r["channel_key"])
            hm = _jst_hm(r.get("scheduled_start"))
            ap = "~" if r.get("start_approx") else ""
            label = KIND_KO.get(r.get("kind"), "") or r.get("icon") or ""
            mem = " 🔒" if r.get("members_only") else ""
            lines.append(f"· {hm}{ap} {label} {nm}{mem}".replace("  ", " ").rstrip())
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    NOW = "2026-09-03T00:00:00Z"

    S1 = (
        "🛸#ゆめみた\n"
        "8/30(日) 配信スケジュール\n"
        "🎮11:00〜 宮永ののか\n"
        "youtube.com/@nonoka_yumemi…\n"
        "💭21:00〜 峰月律\n"
        "youtube.com/@ritsu_yumemita\n"
        "🎤21:30〜／☀明日朝7:00〜 藤都子\n"
        "youtube.com/@miyako_yumemi…\n"
        "🎤22:00〜 仲町あられ\n"
        "youtube.com/@arale_yumemita\n"
        "【メン限】23:00〜 千石ユノ\n"
        "※時刻は予告なく変更の場合がございます。\n"
        "#バンドリ #ゆめみた"
    )
    r1 = parse_bdp_schedule(S1, NOW)
    assert len(r1) == 6, [(x["channel_key"], x["scheduled_start"]) for x in r1]
    by_key = {}
    for x in r1:
        by_key.setdefault(x["channel_key"], []).append(x)
    assert by_key["nonoka"][0]["kind"] == "game"
    assert by_key["ritsu"][0]["kind"] == "talk"
    assert by_key["arale"][0]["kind"] == "song"
    assert by_key["yuno"][0]["members_only"] is True
    assert by_key["yuno"][0]["kind"] == "unknown"
    assert by_key["yuno"][0]["assumed_live"] is False
    # 회원전용 → TTL 5h, 공개 → 3h
    _y = by_key["yuno"][0]
    assert _y["expires_at"] == _iso_z(
        datetime.fromisoformat(_y["scheduled_start"].replace("Z", "+00:00")) + timedelta(hours=5)
    ), _y["expires_at"]
    _n = by_key["nonoka"][0]
    assert _n["expires_at"] == _iso_z(
        datetime.fromisoformat(_n["scheduled_start"].replace("Z", "+00:00")) + timedelta(hours=3)
    ), _n["expires_at"]
    # 藤都子: 21:30 (당일) + 翌朝7:00 (다음날 = 8/31)
    miy = sorted(by_key["miyako"], key=lambda x: x["scheduled_start"])
    assert _jst_date(miy[0]["scheduled_start"]) == "2026-08-30"
    assert _jst_hm(miy[0]["scheduled_start"]) == "21:30"
    assert _jst_date(miy[1]["scheduled_start"]) == "2026-08-31"
    assert _jst_hm(miy[1]["scheduled_start"]) == "07:00"
    assert miy[1]["kind"] == "morning"  # ／☀ 직전 구간
    print("[OK] S1  (6행, miyako 2슬롯, メン限, 아이콘→kind)")

    S2 = (
        "🛸#ゆめみた\n"
        "8/29(土) 配信スケジュール🌟\n"
        "🎮11:00〜 宮永ののか\n"
        "💪12:00〜 仲町あられ×藤都子\n"
        "youtube.com/watch?v=--7cN8…\n"
        "🎤21:00〜 千石ユノ\n"
        "🎤22:00〜 仲町あられ\n"
        "【メン限】23:00〜 峰月律\n"
    )
    r2 = parse_bdp_schedule(S2, NOW)
    assert len(r2) == 5, len(r2)
    col = next(x for x in r2 if x["kind"] == "collab")
    assert col["channel_key"] == "arale" and col["collab_with"] == ["miyako"], col
    assert col["host"] == "group", col                 # 합동 → 公式 채널
    assert col["url"] is None, col                     # URL 잘림(…) → 링크 안 잡음
    assert all(x["host"] is None for x in r2 if x["kind"] != "collab")
    assert all(_jst_date(x["scheduled_start"]) == "2026-08-29" for x in r2)
    print("[OK] S2  (콜라보 A×B → host=group, 잘린 URL 무시)")

    S3 = (
        "／\n🛸夢限大みゅーたいぷ\n"
        "8/17(月)の配信スケジュール🌟\n＼\n"
        "🎮22:00〜 千石ユノ\n"
        "youtube.com/watch?v=4yH9F6…\n"
        "【メン限】23:30〜 峰月律\n"
        "☀明日朝7:00〜 千石ユノ\n"
        "※時刻は予告なく変更の場合がございます。\n#バンドリ #ゆめみた"
    )
    r3 = parse_bdp_schedule(S3, NOW)
    assert len(r3) == 3, len(r3)
    yno = sorted((x for x in r3 if x["channel_key"] == "yuno"), key=lambda x: x["scheduled_start"])
    assert _jst_date(yno[0]["scheduled_start"]) == "2026-08-17" and yno[0]["kind"] == "game"
    assert _jst_date(yno[1]["scheduled_start"]) == "2026-08-18" and yno[1]["kind"] == "morning"
    print("[OK] S3  (독립 ☀明日朝 줄 → 다음날 morning)")

    S4 = (
        "／\n🛸夢限大みゅーたいぷ\n9/2(水)の配信スケジュール🌟\n＼\n"
        "💭23:30頃〜 峰月律\n"
        "youtube.com/watch?v=0o96Zl…\n"
        "※時刻は予告なく変更の場合がございます。\n#バンドリ #ゆめみた"
    )
    r4 = parse_bdp_schedule(S4, NOW)
    assert len(r4) == 1 and r4[0]["start_approx"] is True, r4
    assert r4[0]["channel_key"] == "ritsu" and r4[0]["kind"] == "talk"
    print("[OK] S4  (頃 → start_approx)")

    # S5: 실측 (2026-09-03 19:30 KST) — 심야표기 24:00, 📺 미지 아이콘, A×B 콜라보, ～(FW)
    S5 = (
        "／\n🛸夢限大みゅーたいぷ\n"
        "9/3(木)の配信スケジュール🌟\n＼\n\n"
        "📺24:00～ 仲町あられ×宮永ののか\n"
        "https://youtube.com/live/kx-nhmTj4Eg\n\n"
        "※時刻は予告なく変更の場合がございます。\n#バンドリ #ゆめみた"
    )
    r5 = parse_bdp_schedule(S5, NOW)
    assert len(r5) == 1, r5
    assert r5[0]["channel_key"] == "arale" and r5[0]["collab_with"] == ["nonoka"], r5
    assert r5[0]["kind"] == "collab", r5
    assert r5[0]["host"] == "group", r5
    assert r5[0]["url"] == "https://youtube.com/live/kx-nhmTj4Eg", r5[0]["url"]
    assert _jst_date(r5[0]["scheduled_start"]) == "2026-09-04", r5[0]["scheduled_start"]
    assert _jst_hm(r5[0]["scheduled_start"]) == "00:00", r5[0]["scheduled_start"]
    print("[OK] S5  (24:00 심야 + host=group + 영상 URL 캡처)")

    # S6: watch?v= 형태 온전한 URL (외부 이벤트/합방 공지가 일일 스케줄에 실릴 때)
    S6 = (
        "／\n🛸夢限大みゅーたいぷ\n9/5(金)の配信スケジュール🌟\n＼\n\n"
        "📺21:00〜 千石ユノ×峰月律\n"
        "https://www.youtube.com/watch?v=PAfMVT3GTLg\n"
        "※時刻は予告なく変更の場合がございます。"
    )
    r6 = parse_bdp_schedule(S6, NOW)
    assert len(r6) == 1, r6
    assert r6[0]["channel_key"] == "yuno" and r6[0]["collab_with"] == ["ritsu"], r6
    assert r6[0]["host"] == "group", r6
    assert r6[0]["url"] == "https://www.youtube.com/watch?v=PAfMVT3GTLg", r6[0]["url"]
    print("[OK] S6  (watch?v= 온전 URL 캡처)")

    # S7: 出演情報 — 실측 (@BDP_yumemita, 5인 외부 이벤트 출연)
    S7 = (
        "＼🛸出演情報📢／\n\n"
        "9/10(木) 22:00頃〜\n"
        "「#バンドリTVLIVE 2026」\n\n"
        "夢限大みゅーたいぷ 5名が出演🛸\n\n"
        "📺配信URLはこちら\nhttps://youtube.com/live/ri2_BimgJIA\n\n"
        "お見逃しなく✨\n#ゆめみた"
    )
    assert parse_bdp_schedule(S7, NOW) == []            # 일일 스케줄 파서는 무시
    r7 = parse_appearance(S7, NOW)
    assert len(r7) == 1, r7
    a = r7[0]
    assert a["channel_key"] == "arale" and a["collab_with"] == ["yuno", "nonoka", "ritsu", "miyako"], a
    assert a["host"] == "group" and a["kind"] == "collab", a
    assert a["start_approx"] is True, a                 # 22:00頃
    assert a["url"] == "https://youtube.com/live/ri2_BimgJIA", a["url"]
    assert a["title"] == "バンドリTVLIVE 2026", a["title"]
    assert _jst_hm(a["scheduled_start"]) == "22:00" and _jst_date(a["scheduled_start"]) == "2026-09-10", a
    assert parse(S7, NOW) == r7                         # 통합 진입점
    assert looks_relayable(S7) and looks_relayable("x 配信スケジュール y")
    assert not looks_relayable("다운로드 완료")
    print("[OK] S7  (出演情報 → host=group 전원, 頃/title/URL)")

    # 형식 아님 → []
    assert parse_bdp_schedule("＼本日配信📢／\n⛱️ブシロードTCG戦略発表会2026 夏", NOW) == []
    assert parse_appearance("＼本日配信📢／\n⛱️ブシロードTCG戦略発表会2026 夏", NOW) == []
    print("[OK] 비스케줄 트윗 → []")

    # merge_scheduled: replace-by-date
    prev = {
        "generated_at": "2026-09-03T00:00:00Z",
        "broadcasts": [
            {"video_id": "vidA", "channel_key": "arale", "status": "upcoming",
             "scheduled_start": "2026-09-03T05:00:00Z"},
            {"sched_id": "sched:yuno:2026-08-30T12:00:00Z", "channel_key": "yuno",
             "status": "scheduled", "source": "bdp_schedule",
             "scheduled_start": "2026-08-30T12:00:00Z"},  # ← 8/30 (JST 21:00), S1 이 교체
        ],
    }
    merged = merge_scheduled(prev, r1, "2026-09-03T01:00:00Z")
    kinds = [b.get("status") for b in merged["broadcasts"]]
    assert kinds.count("upcoming") == 1  # vidA 유지
    old_yuno = [b for b in merged["broadcasts"] if b.get("sched_id") == "sched:yuno:2026-08-30T12:00:00Z"]
    assert old_yuno == [], "8/30 기존 scheduled 는 교체됐어야"
    assert sum(1 for b in merged["broadcasts"] if b.get("status") == "scheduled") == 6
    assert merged["generated_at"] == "2026-09-03T01:00:00Z"
    print("[OK] merge_scheduled  (replace-by-date, upcoming 보존)")

    print("\nSUCCESS: xrelay self-test 통과")
