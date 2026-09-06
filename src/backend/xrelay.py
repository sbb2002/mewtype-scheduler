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
# (v2.6) 現在 미지원 라인 — YouTube 가 아닌 플랫폼(bilibili 등) 이나 "全員" 표기.
#   "⭐22:00～ 全員【bilibili】" / "https://space.bilibili.com/..." 같은 줄은 조용히 스킵한다.
#   나중에 지원하려면 全員→5인 전원 + 비-YT URL 처리를 추가.
_SKIP_LINE_RE = re.compile(
    r"全員|みんな|【\s*(?:bilibili|ビリビリ|ニコ生?|ニコニコ|ツイキャス|twitcast|mildom|twitch)\s*】",
    re.IGNORECASE,
)

# "出演情報" — @BDP_yumemita 가 외부 이벤트/합방 출연을 알릴 때 (일일 스케줄과 서식 다름).
#   ＼出演情報／  9/10(木) 22:00頃〜  「이벤트명」  夢限大みゅーたいぷ 5名が出演  <영상 URL>
# 실측 확인된 마커는 `出演情報` 하나뿐. 변형(出演決定 등)은 실물 트윗에서 본 뒤 추가.
APPEARANCE_MARK_RE = re.compile(r"出演情報")
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
        if _SKIP_LINE_RE.search(line):
            continue                         # (v2.6) 全員/비-YT 플랫폼 라인 — 미지원, 스킵
        key, collab = _names(line)
        if not key:
            continue
        members_only = "メン限" in line
        line_has_collab = bool(collab) or "×" in line
        # (v2.6) 합동방송이라도 공용 채널이 아니라 참여 멤버 1명의 개인 채널에서 하는 경우가
        # 잦다. 공식 트윗은 그럴 때도 영상/채널 URL 을 함께 준다 → 그걸 진실로 삼는다.
        #   · watch?v=/live/ 온전 URL → video_id 추출(정규 파이프라인이 upcoming/live 로 확정)
        #   · @handle 채널 URL / URL 없음 → video_id 없이 자리표시. reconcile 이 참여자 중
        #     아무 채널에나 실물이 뜨면 supersede 하며 collab_with 를 실물 행에 이관.
        # host="group" 특례(절대 supersede 안 함)는 여기서 안 붙인다 — parse_appearance 만 씀.
        video_url = _video_url_near(lines, idx) if line_has_collab else None
        video_id = None
        if video_url:
            _vm = YT_VIDEO_RE.search(video_url)
            video_id = _vm.group(1) if _vm else None

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
                    "video_id": video_id,
                    "title": None,
                    "url": video_url,
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


# `HH:MM` 처럼 보이지만 `〜` 가 없어 TIME_RE 로는 안 잡히는 느슨한 시각 패턴
_LOOSE_TIME_RE = re.compile(r"\d{1,2}:\d{2}")


def unparsed_lines(text: str) -> list[str]:
    """스케줄 엔트리로 보이지만 행을 못 만든 줄 목록.

    일일 스케줄 트윗(`配信スケジュール` 헤더 있음)에서, 시각/아이콘/`メン限` 이 있어
    엔트리처럼 보이는데 `parse_bdp_schedule` 이 버린 줄(이름 누락·오타, `〜` 없는
    시각, 시각 자체 누락 등)을 돌려준다. DM 에 "인식 실패 N줄" 을 표기하는 용도.
    헤더가 없으면(=일일 스케줄 트윗이 아니면) 빈 리스트.
    """
    t = normalize(text)
    if not HEADER_RE.search(t):
        return []
    bad: list[str] = []
    for raw_line in t.split("\n"):
        line = raw_line.strip()
        if not line or HEADER_RE.search(line):
            continue
        looks_entry = (
            bool(_LOOSE_TIME_RE.search(line))
            or line[:1] in ICON_KIND
            or "メン限" in line
        )
        if not looks_entry:
            continue
        if _SKIP_LINE_RE.search(line):        # (v2.6) 全員/비-YT — 의도적 미지원, 실패 아님
            continue
        key, _ = _names(line)
        if TIME_RE.search(line) and key:      # 정상 처리되는 줄
            continue
        bad.append(line)
    return bad


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
    # (v2.6) 이미 실물(upcoming/live)로 확정된 video_id 를 가진 새 scheduled 행은 버린다
    #        — reconcile 이 다음 tick 에 정리하지만 그 사이 카드가 겹쳐 보이는 걸 막는다.
    _resolved = {
        b.get("video_id") for b in kept
        if b.get("video_id") and b.get("status") != "scheduled"
    }
    kept.extend(r for r in rows if not (r.get("video_id") and r["video_id"] in _resolved))

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
    assert "host" not in col, col                      # (v2.6) daily 합동엔 host 안 붙임
    assert col["url"] is None and col["video_id"] is None, col   # URL 잘림(…) → 링크·id 없음
    assert all("host" not in x for x in r2)
    assert all(_jst_date(x["scheduled_start"]) == "2026-08-29" for x in r2)
    print("[OK] S2  (콜라보 A×B → kind=collab, 잘린 URL → id/url 없음)")

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
    assert "host" not in r5[0], r5
    assert r5[0]["url"] == "https://youtube.com/live/kx-nhmTj4Eg", r5[0]["url"]
    assert r5[0]["video_id"] == "kx-nhmTj4Eg", r5[0]           # (v2.6) live/ URL → video_id
    assert _jst_date(r5[0]["scheduled_start"]) == "2026-09-04", r5[0]["scheduled_start"]
    assert _jst_hm(r5[0]["scheduled_start"]) == "00:00", r5[0]["scheduled_start"]
    print("[OK] S5  (24:00 심야 + 합동 + 영상 URL→video_id)")

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
    assert "host" not in r6[0], r6
    assert r6[0]["url"] == "https://www.youtube.com/watch?v=PAfMVT3GTLg", r6[0]["url"]
    assert r6[0]["video_id"] == "PAfMVT3GTLg", r6[0]          # (v2.6) watch?v= → video_id
    print("[OK] S6  (watch?v= 온전 URL → video_id)")

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

    # S8: 실측 (7/12) — 합동 줄에 watch?v= URL, 솔로 줄엔 @handle 채널 URL
    S8 = (
        "／\n🛸夢限大みゅーたいぷ\n7/12(日)の配信スケジュール🌟\n＼\n\n"
        "⭐21:30～ 藤都子\nhttps://youtube.com/watch?v=Ph7LqCpgyEc\n\n"
        "⭐22:00～ 仲町あられ×宮永ののか\nhttps://youtube.com/watch?v=SVRa_W82oAk\n\n"
        "⭐23:30～ 千石ユノ\nhttps://youtube.com/@yuno_yumemita\n\n"
        "⭐明日朝7:00～ 藤都子\nhttps://youtube.com/@miyako_yumemita\n\n"
        "#バンドリ #ゆめみた"
    )
    r8 = parse_bdp_schedule(S8, NOW)
    assert len(r8) == 4, [x["channel_key"] for x in r8]
    c8 = next(x for x in r8 if x["kind"] == "collab")
    assert c8["channel_key"] == "arale" and c8["collab_with"] == ["nonoka"], c8
    assert c8["video_id"] == "SVRa_W82oAk" and "host" not in c8, c8   # 합동 → 트윗 URL 우선
    # 솔로 줄은 URL 캡처 안 함(개인 채널 RSS 로 잡힘). watch?v= 든 @handle 이든 video_id 없음.
    for x in r8:
        if x["kind"] != "collab":
            assert x["video_id"] is None and x["url"] is None, x
    print("[OK] S8  (7/12 — 합동만 watch?v=→video_id, 솔로 줄은 URL 무시)")

    # S9: 실측 (6/23) — 全員【bilibili】 라인은 스킵, 솔로 @handle 줄만 반영
    S9 = (
        "／\n🛸夢限大みゅーたいぷ\n6/23(火)の配信スケジュール🌟\n＼\n\n"
        "⭐22:00～ 全員【bilibili】\nhttps://space.bilibili.com/3546592848120041\n\n"
        "⭐明日朝6:30～ 仲町あられ\nhttps://youtube.com/@arale_yumemita\n\n"
        "※URLは本人のXで告知いたします。\n#バンドリ #ゆめみた"
    )
    r9 = parse_bdp_schedule(S9, NOW)
    assert len(r9) == 1 and r9[0]["channel_key"] == "arale", r9   # 全員 줄은 스킵됨
    assert r9[0]["video_id"] is None, r9[0]
    assert unparsed_lines(S9) == [], unparsed_lines(S9)           # 全員 줄 → 실패 아님
    print("[OK] S9  (全員【bilibili】 스킵 · unparsed 에서도 제외)")

    # unparsed_lines: 이름 누락 / 〜 없는 시각 / 정상 줄 구분
    S_BAD = (
        "8/30(日) 配信スケジュール\n"
        "🎮11:00〜 宮永ののか\n"        # 정상
        "💭21:00〜 だれか\n"           # 이름 인식 실패
        "🎤21:30 藤都子\n"            # 〜 없음 → 시각 인식 실패
        "【メン限】千石ユノ\n"          # 시각 없음
        "※時刻は予告なく変更の場合がございます。\n#バンドリ"
    )
    bad = unparsed_lines(S_BAD)
    assert len(bad) == 3, bad
    assert len(parse_bdp_schedule(S_BAD, NOW)) == 1        # 정상 줄만 반영
    assert unparsed_lines(S1) == []                        # 정상 트윗 → 실패 0
    assert unparsed_lines("配信スケジュール 없음\n🎮11:00〜 だれか") == []  # 헤더 없으면 []
    print("[OK] unparsed_lines  (이름·시각 누락 줄 계수)")

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

    # (v2.6) 이미 upcoming 으로 확정된 video_id 를 가진 새 scheduled 행은 버린다
    prev2 = {"broadcasts": [
        {"video_id": "RESOLVED0123", "channel_key": "yuno", "status": "upcoming",
         "scheduled_start": "2026-09-10T12:00:00Z"},
    ]}
    rows2 = [
        {"video_id": "RESOLVED0123", "sched_id": "sched:yuno:2026-09-10T12:00:00Z",
         "channel_key": "yuno", "status": "scheduled", "source": "bdp_schedule",
         "scheduled_start": "2026-09-10T12:00:00Z", "collab_with": ["ritsu"], "kind": "collab"},
        {"video_id": None, "sched_id": "sched:arale:2026-09-10T13:00:00Z",
         "channel_key": "arale", "status": "scheduled", "source": "bdp_schedule",
         "scheduled_start": "2026-09-10T13:00:00Z"},
    ]
    m2 = merge_scheduled(prev2, rows2, "2026-09-10T00:00:00Z")
    _sids = {b.get("sched_id") for b in m2["broadcasts"] if b.get("status") == "scheduled"}
    assert _sids == {"sched:arale:2026-09-10T13:00:00Z"}, _sids   # 확정된 것은 안 들어옴
    assert any(b.get("video_id") == "RESOLVED0123" and b["status"] == "upcoming" for b in m2["broadcasts"])
    print("[OK] merge_scheduled  (확정 video_id 자리표시 드롭)")

    print("\nSUCCESS: xrelay self-test 통과")
