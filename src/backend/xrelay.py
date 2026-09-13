"""X(트위터) 예고 릴레이 — 파서 + announced 아이템 머지 (순수 함수, v3).

v3 계약: docs/plan/v3_impl_spec.md 0.1, WP-9

흐름:
  Automate(폰) 가 삼성 브라우저 웹푸시 알림 텍스트를 `telegram_app` 의 공개
  `POST /ingest` 로 그대로 POST → 여기서 `@BDP_yumemita` 일일 스케줄 트윗을
  파싱해 `preview.json` 의 `state=="announced"` 아이템(= YouTube 영상이 아직 없는
  최하 단계)으로 반영한다. video_id 가 없으므로 Cloud Tasks 는 안 탄다.
  이후 정기 `/tick` 의 preview_build 가 실물 upcoming 이 뜨면 supersede, TTL 로 소멸.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import preview

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


def normalize(text: str, *, strip_vs16: bool = True) -> str:
    """개행·전각 문자·물결표 통일.

    strip_vs16=True(기본): VS16(U+FE0F) 제거 — 파서 매칭용(이모지 장식이 노이즈).
    strip_vs16=False: VS16 보존 — 트윗 본문처럼 그대로 표시할 텍스트용
      (☀️ 등 text-default 이모지가 흑백 글리프로 깨지는 것 방지).
    """
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.translate(_FW)
    t = t.replace("～", "〜").replace("~", "〜")
    if strip_vs16:
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
    """`@BDP_yumemita` 일일 스케줄 트윗 → announced 아이템 리스트 (v3).

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
        membership = "メン限" in line
        line_has_collab = bool(collab) or "×" in line
        # (v2.6) 합동방송이라도 공용 채널이 아니라 참여 멤버 1명의 개인 채널에서 하는 경우가
        # 잦다. 공식 트윗은 그럴 때도 영상/채널 URL 을 함께 준다 → 그걸 진실로 삼는다.
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

            item = preview.make_item(
                channel_key=key,
                state="announced",
                source="x-relay",
                now_iso=now_iso,
                first_seen=now_iso,
                kind=kind,
                membership=membership,
                collab_with=collab or None,
                url=video_url,
                video_id=video_id,
                scheduled_start=start_z,
                info_source="x-relay",
                info_at=now_iso,
            )
            # ponytail: icon, start_approx, assumed_live 필드는 v3에서 미사용이지만
            # 호환성·디버그 목적으로 extra 에 남겨둔다 — 불필요하면 이후 정리
            rows.append(item)
    return rows


def parse_appearance(text: str, now_iso: str) -> list[dict]:
    """`出演情報` 계열 트윗 → announced(host="group") 아이템 1개 (v3). 형식 아니면 `[]`.

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

    item = preview.make_item(
        channel_key=members[0],
        state="announced",
        source="x-relay",
        now_iso=now_iso,
        first_seen=now_iso,
        title=title,
        url=url,
        scheduled_start=start_z,
        kind="collab",
        membership=False,
        collab_with=members[1:] or None,
        host="group",
        info_source="x-relay",
        info_at=now_iso,
    )
    return [item]


# "配信開始📢/📡" · "同時視聴配信" · "生配信"(単独でも「今まさに」のニュアンス) 등 —
# 예고가 아니라 "지금 막 시작했다/한다" 트윗. 일일 스케줄(HEADER_RE)·出演情報(APPEARANCE_MARK_RE)
# 어느 쪽 서식도 아닌 공지문(예: 그룹 공식 채널의 동시시청 방송 개시 공지, 외부 채널 콜라보 생중계
# 공지). video_id 없이는 노이즈가 크므로 온전한 URL 필수(YT_VIDEO_RE 게이트).
LIVE_NOW_RE = re.compile(r"配信開始|同時視聴配信|生配信|ただいま配信|配信中です")

# "本日12時〜"/"明日20:00〜" 류 상대날짜 + 시각 표기 — xnotice.py _TODAY_WORD 와 동일
# 어휘(순환 import 피하려 여기 별도 정의) + "明日" 계열("明日"/"明日朝"/"明晩"/"明朝"/"あす",
# parse_bdp_schedule 의 "明日" +1일 관례와 동일). 시각 뒤 〜/~/～(…부터) 가 붙어야 매치 —
# "24時間耐久" 같은 소요시간 표기 오인식 방지. 시각 앞 마커와 숫자 사이엔 "朝"/"夜" 같은
# 시간대어가 낄 수 있어(예: "明日朝7:00") 최대 3자 필러를 허용한다.
# 이 시각이 있으면 scheduled_start 를 ingest 시각 대신 이걸로 잡는다(v3.1.10 — 릴레이가
# 실제 시작보다 먼저 도착한 경우 대비. 예: 아침에 릴레이된 "本日12時〜").
_TODAY_WORD = ("本日", "今夜", "今晩", "まもなく", "これから", "ただいま")
_TOMORROW_WORD = ("明日", "明晩", "明朝", "あす")
_DAY_TIME_RE = re.compile(
    r"(?P<day>" + "|".join(_TOMORROW_WORD + _TODAY_WORD) + r")"
    r"[^\d\n]{0,3}(?P<h>\d{1,2})\s*(?::|：|時)\s*(?P<mi>\d{2})?\s*分?\s*[〜~～]"
)


def _relative_day_time_jst(t: str, now_iso: str) -> str | None:
    """`本日12時〜`/`明日20:00〜` 에서 상대날짜+시각을 뽑아 UTC ISO 로.

    못 뽑으면 None(호출부가 now_iso 대체).
    """
    m = _DAY_TIME_RE.search(t)
    if not m:
        return None
    h = int(m.group("h"))
    if h > 29:
        return None
    mi = int(m.group("mi")) if m.group("mi") else 0
    try:
        now_jst = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).astimezone(JST)
    except (ValueError, AttributeError):
        now_jst = datetime.now(JST)
    day_carry, hh = divmod(h, 24)          # 심야표기 24:00〜29:59 = 다음날 00:00〜05:59
    if m.group("day") in _TOMORROW_WORD:
        day_carry += 1
    base = datetime(now_jst.year, now_jst.month, now_jst.day, tzinfo=JST)
    dt_jst = base + timedelta(days=day_carry, hours=hh, minutes=mi)
    return dt_jst.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_live_now(text: str, now_iso: str) -> list[dict]:
    """"지금 막 시작" 계열 트윗 → announced(video_id 포함) 아이템 1개 (v3). 형식 아니면 `[]`.

    일일 스케줄/出演情報 마커가 없고, 즉시개시 문구 + 온전한 YouTube 영상 URL 이 함께 있을 때만
    반응한다. 개인 이름이 있으면 그 멤버(+동석자), 없고 그룹 명의(夢限大みゅーたいぷ/ゆめみた)면
    5인 전원(host="group") — 그 외엔 채널을 특정 못 하므로 `[]`.
    video_id 가 이미 있으므로 다음 videos.list 후보에 바로 잡혀 API 로 title/thumbnail 이 채워진다.
    """
    t = normalize(text)
    if HEADER_RE.search(t) or APPEARANCE_MARK_RE.search(t):
        return []                            # 스케줄/출연 서식은 각자 파서가 담당
    if not LIVE_NOW_RE.search(t):
        return []
    hit = YT_VIDEO_RE.search(t)
    if not hit:
        return []                            # video_id 없는 "지금 시작" 공지는 노이즈 위험 → 무시
    video_url = hit.group(0)
    if not video_url.startswith("http"):
        video_url = "https://" + video_url
    video_id = hit.group(1)

    key, collab = _names(t)
    host = None
    if not key:
        if "夢限大みゅーたいぷ" in t or "ゆめみた" in t:
            key, collab = ALL_KEYS[0], ALL_KEYS[1:]
            host = "group"
        else:
            return []                        # 채널 특정 불가

    tm = _TITLE_RE.search(t)
    title = tm.group(1).lstrip("#＃ ").strip() if tm else None
    scheduled_start = _relative_day_time_jst(t, now_iso) or now_iso

    item = preview.make_item(
        channel_key=key,
        state="announced",
        source="x-relay",
        now_iso=now_iso,
        first_seen=now_iso,
        title=title,
        url=video_url,
        video_id=video_id,
        scheduled_start=scheduled_start,
        kind="collab" if collab else None,
        membership=False,
        collab_with=collab or None,
        host=host,
        info_source="x-relay",
        info_at=now_iso,
    )
    return [item]


def parse(text: str, now_iso: str) -> list[dict]:
    """트윗 → scheduled 행. 일일 스케줄 우선 → 出演情報 → 즉시개시 공지."""
    return (
        parse_bdp_schedule(text, now_iso)
        or parse_appearance(text, now_iso)
        or parse_live_now(text, now_iso)
    )


def looks_relayable(text: str) -> bool:
    """폰이 relay 할 가치가 있는(스케줄/출연/즉시개시) 트윗인지 — 큐 적재 가드용."""
    t = text or ""
    tn = normalize(t)
    return (
        "配信スケジュール" in t
        or bool(APPEARANCE_MARK_RE.search(tn))
        or bool(LIVE_NOW_RE.search(tn) and YT_VIDEO_RE.search(tn))
    )


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


def merge_announced(prev_items: list[dict], inc_list: list[dict], now_iso: str) -> tuple[list[dict], bool]:
    """announced 아이템 upsert (v3).

    각 inc 아이템에 대해 preview.match_item으로 prev_items에서 매칭.
    찾으면 upsert, 아니면 append. 정렬 후 반환.
    host="group" 특례는 없음 (preview_build 에서 처리).

    v3.1.18 — 매칭된 기존 항목이 이미 announced 보다 상위 티어(video_id 확보
    = upcoming/watching/live/end, 또는 state 가 announced 가 아님)면 통째로
    덮어쓰지 않는다. 그룹 공식 채널 일일 스케줄 공지는 "오늘 누가 몇 시에
    한다"는 재확인일 뿐 — 이미 API/개인트윗으로 video_id·제목·썸네일까지
    확보된 실물 항목을 매일 재게시되는 요약 트윗이 지워버리면 안 된다.
    이 경우 kind/membership/collab_with 등 비어있는 보조 필드만 채우고
    핵심 식별 필드(video_id/url/title/thumbnail/state/scheduled_start 등)는
    기존 값을 유지한다.
    실측 버그: 2026-09-13 미야코·리츠의 API 확정 upcoming(video_id 有)이
    같은 날 그룹 스케줄 재공지에 덮어써져 video_id 를 잃고 announced 로
    되돌아가, 이후 watching/live 전이가 전혀 일어나지 못했다.
    """
    items = [dict(i) for i in prev_items or []]
    changed = False

    for inc in inc_list:
        matched = preview.match_item(items, inc)
        if matched is None:
            items.append(dict(inc))
            changed = True
            continue

        idx = items.index(matched)
        cur = items[idx]
        original = dict(cur)
        is_higher_tier = bool(cur.get("video_id")) or cur.get("state") != "announced"

        if is_higher_tier:
            # 보조 필드만 보강 — 핵심 필드(state/video_id/url/title/thumbnail/
            # scheduled_start 등)는 이미 상위 티어가 확정한 값을 유지.
            if not cur.get("kind") and inc.get("kind"):
                cur["kind"] = inc["kind"]
            if not cur.get("membership") and inc.get("membership"):
                cur["membership"] = inc["membership"]
            if not cur.get("collab_with") and inc.get("collab_with"):
                cur["collab_with"] = inc["collab_with"]
            cur["last_updated"] = now_iso
        else:
            items[idx] = dict(inc)
            items[idx]["last_updated"] = now_iso

        if items[idx] != original:
            changed = True

    return preview.sort_items(items), changed


def summary_text(items: list[dict], channels_cfg: dict | None = None) -> str:
    """announced 아이템 반영 결과 → Telegram DM 본문 (v3)."""
    chan = (channels_cfg or {}).get("channels", {})
    by_date: dict[str, list[dict]] = {}
    for item in items:
        by_date.setdefault(
            _jst_date(item.get("scheduled_start") or ""), []
        ).append(item)

    lines = [f"🛸 <b>X 스케줄 반영</b> ({len(items)}건)"]
    for d in sorted(by_date):
        lines.append(f"\n<b>{d or '?'}</b>")
        for item in sorted(by_date[d], key=lambda x: x.get("scheduled_start") or ""):
            nm = chan.get(item["channel_key"], {}).get("name_ko", item["channel_key"])
            hm = _jst_hm(item.get("scheduled_start"))
            label = KIND_KO.get(item.get("kind"), "") or ""
            mem = " 🔒" if item.get("membership") else ""
            lines.append(f"· {hm} {label} {nm}{mem}".replace("  ", " ").rstrip())
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
    # v3 preview 형식: state="announced", source="x-relay"
    assert all(x["state"] == "announced" for x in r1), "state 체크"
    assert all(x["source"] == "x-relay" for x in r1), "source 체크"
    assert by_key["nonoka"][0]["kind"] == "game"
    assert by_key["ritsu"][0]["kind"] == "talk"
    assert by_key["arale"][0]["kind"] == "song"
    assert by_key["yuno"][0]["membership"] is True
    assert by_key["yuno"][0]["kind"] == "unknown"
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
    assert miy[1]["kind"] == "morning"
    print("[OK] S1  (6개 announced, miyako 2슬롯, 회원전용, 아이콘→kind)")

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
    assert col.get("host") is None, col                # daily 합동은 host 미지정
    assert col["url"] is None and col["video_id"] is None, col   # URL 잘림 → 링크·id 없음
    assert all(x.get("host") is None for x in r2)
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
    assert len(r4) == 1, r4
    assert r4[0]["channel_key"] == "ritsu" and r4[0]["kind"] == "talk"
    print("[OK] S4  (1개 announced)")

    # S5: 실측 — 심야표기 24:00, 합동, live URL
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
    assert r5[0].get("host") is None, r5
    assert r5[0]["url"] == "https://youtube.com/live/kx-nhmTj4Eg", r5[0]["url"]
    assert r5[0]["video_id"] == "kx-nhmTj4Eg", r5[0]
    assert _jst_date(r5[0]["scheduled_start"]) == "2026-09-04", r5[0]["scheduled_start"]
    assert _jst_hm(r5[0]["scheduled_start"]) == "00:00", r5[0]["scheduled_start"]
    print("[OK] S5  (24:00 심야 + 합동 + live/ URL→video_id)")

    # S6: watch?v= 온전 URL
    S6 = (
        "／\n🛸夢限大みゅーたいぷ\n9/5(金)の配信スケジュール🌟\n＼\n\n"
        "📺21:00〜 千石ユノ×峰月律\n"
        "https://www.youtube.com/watch?v=PAfMVT3GTLg\n"
        "※時刻は予告なく変更の場合がございます。"
    )
    r6 = parse_bdp_schedule(S6, NOW)
    assert len(r6) == 1, r6
    assert r6[0]["channel_key"] == "yuno" and r6[0]["collab_with"] == ["ritsu"], r6
    assert r6[0].get("host") is None, r6
    assert r6[0]["url"] == "https://www.youtube.com/watch?v=PAfMVT3GTLg", r6[0]["url"]
    assert r6[0]["video_id"] == "PAfMVT3GTLg", r6[0]
    print("[OK] S6  (watch?v= 온전 URL→video_id)")

    # S7: 出演情報 — host="group"
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
    assert a["state"] == "announced" and a["source"] == "x-relay"
    assert a["channel_key"] == "arale" and a["collab_with"] == ["yuno", "nonoka", "ritsu", "miyako"], a
    assert a["host"] == "group" and a["kind"] == "collab", a
    assert a["url"] == "https://youtube.com/live/ri2_BimgJIA", a["url"]
    assert a["title"] == "バンドリTVLIVE 2026", a["title"]
    assert _jst_hm(a["scheduled_start"]) == "22:00" and _jst_date(a["scheduled_start"]) == "2026-09-10", a
    assert parse(S7, NOW) == r7
    assert looks_relayable(S7) and looks_relayable("x 配信スケジュール y")
    assert not looks_relayable("다운로드 완료")
    print("[OK] S7  (出演情報 → host=group 5인 announced)")

    # 형식 아님 → []
    assert parse_bdp_schedule("＼本日配信📢／\n⛱️ブシロードTCG戦略発表会2026 夏", NOW) == []
    assert parse_appearance("＼本日配信📢／\n⛱️ブシロードTCG戦略発表会2026 夏", NOW) == []
    print("[OK] 비스케줄 트윗 → []")

    # S8: 합동만 URL 캡처
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
    assert c8["video_id"] == "SVRa_W82oAk" and c8.get("host") is None, c8
    for x in r8:
        if x["kind"] != "collab":
            assert x["video_id"] is None and x["url"] is None, x
    print("[OK] S8  (합동만 watch?v=→video_id, 솔로 URL 무시)")

    # S9: 全員 라인 스킵
    S9 = (
        "／\n🛸夢限大みゅーたいぷ\n6/23(火)の配信スケジュール🌟\n＼\n\n"
        "⭐22:00～ 全員【bilibili】\nhttps://space.bilibili.com/3546592848120041\n\n"
        "⭐明日朝6:30～ 仲町あられ\nhttps://youtube.com/@arale_yumemita\n\n"
        "※URLは本人のXで告知いたします。\n#バンドリ #ゆめみた"
    )
    r9 = parse_bdp_schedule(S9, NOW)
    assert len(r9) == 1 and r9[0]["channel_key"] == "arale", r9
    assert r9[0]["video_id"] is None, r9[0]
    assert unparsed_lines(S9) == [], unparsed_lines(S9)
    print("[OK] S9  (全員【bilibili】 스킵)")

    # S10: 실측 — 그룹 공식(@BDP_yumemita) "配信開始" 즉시개시 공지 → parse_live_now
    S10 = (
        "＼配信開始📡／\n\n"
        "🛸#アニメゆめみた 同時視聴配信 #13🛸\n\n"
        "夢限大みゅーたいぷ 5名と\nアニメを同時視聴！\n\n"
        "📺ご視聴はこちら\n"
        "https://youtube.com/live/2nZzqEspCrU\n\n"
        "場面写を使用した振り返りも\nぜひご覧ください🎶\n\n"
        "#バンドリ"
    )
    assert parse_bdp_schedule(S10, NOW) == []
    assert parse_appearance(S10, NOW) == []
    r10 = parse_live_now(S10, NOW)
    assert len(r10) == 1, r10
    g10 = r10[0]
    assert g10["state"] == "announced" and g10["source"] == "x-relay", g10
    assert g10["channel_key"] == "arale" and g10["collab_with"] == ["yuno", "nonoka", "ritsu", "miyako"], g10
    assert g10["host"] == "group" and g10["kind"] == "collab", g10
    assert g10["video_id"] == "2nZzqEspCrU", g10
    assert g10["url"] == "https://youtube.com/live/2nZzqEspCrU", g10["url"]
    assert parse(S10, NOW) == r10
    assert looks_relayable(S10)
    print("[OK] S10  (즉시개시 공지 → host=group 5인 announced, video_id 확보)")

    # S11: 잘린 URL(…) 이면 parse_live_now 도 무시 (노이즈 방지)
    S11 = "＼配信開始📢／\n夢限大みゅーたいぷ\nhttps://youtube.com/live/2nZzqEspC…"
    assert parse_live_now(S11, NOW) == [], parse_live_now(S11, NOW)
    assert not looks_relayable(S11)
    print("[OK] S11  (잘린 URL → parse_live_now 무시)")

    # S12: 개인 계정의 즉시개시 공지 — 이름만 있고 그룹 명의 없음
    S12 = "＼配信開始📢／\n仲町あられ\nhttps://youtube.com/watch?v=AAAAAAAAAAA"
    r12 = parse_live_now(S12, NOW)
    assert len(r12) == 1 and r12[0]["channel_key"] == "arale", r12
    assert r12[0].get("host") is None and r12[0]["collab_with"] is None, r12[0]
    print("[OK] S12  (개인 즉시개시 공지 → host 없이 단독)")

    # S13: 실측 — 외부(굿즈사) 채널 콜라보 생중계 공지. "生配信中" 이 아니라 "生配信！" 뿐이고
    # video_id 는 config/channels.json 미등록 채널(굿즈사) 소유지만, videos.list 는 채널 제한
    # 없이 video_id 로 조회하므로 channel_key 미등록 여부와 무관하게 반영돼야 한다(2026-09-13).
    S13 = (
        "＼本日開催📢／\n\n"
        "🛸夢限大みゅーたいぷ 5th Single\n"
        "「これはぼくたちの生存のあらすじ」\n"
        "リリース記念 インターネットサイン会🖋\n\n"
        "⏰本日12時～\n"
        "サイン会の様子を生配信！\n\n"
        "📺ご視聴はこちら\n"
        "https://youtube.com/live/V2AJBNJGR8E\n\n"
        "ダブルチャンス抽選の発表もお見逃しなく✨\n\n"
        "#リミスタ #バンドリ"
    )
    assert parse_bdp_schedule(S13, NOW) == []
    assert parse_appearance(S13, NOW) == []
    r13 = parse_live_now(S13, NOW)
    assert len(r13) == 1, r13
    g13 = r13[0]
    assert g13["channel_key"] == "arale" and g13["collab_with"] == ["yuno", "nonoka", "ritsu", "miyako"], g13
    assert g13["host"] == "group" and g13["kind"] == "collab", g13
    assert g13["video_id"] == "V2AJBNJGR8E", g13
    # NOW = 2026-09-03T00:00:00Z(09:00 JST) → "本日12時〜" = 같은 날 12:00 JST = 03:00 UTC
    assert g13["scheduled_start"] == "2026-09-03T03:00:00Z", g13["scheduled_start"]
    assert parse(S13, NOW) == r13
    assert looks_relayable(S13)
    print("[OK] S13  (生配信 단독 + 외부 채널 URL + 本日HH時〜 → host=group, 당일 시각 반영)")

    # S14: 시각 표기가 없으면(예: "配信開始" 만) 종전대로 ingest 시각(now_iso)을 씀
    S14 = "＼配信開始📢／\n夢限大みゅーたいぷ\nhttps://youtube.com/live/aBcDeFgHiJk"
    r14 = parse_live_now(S14, NOW)
    assert len(r14) == 1 and r14[0]["scheduled_start"] == NOW, r14
    print("[OK] S14  (당일 시각 표기 없음 → scheduled_start=ingest 시각 그대로)")

    # S15: "明日" 계열 — +1일 반영 (parse_bdp_schedule 의 明日 관례와 동일)
    S15 = "＼本日開催📢／\n夢限大みゅーたいぷ\n明日20時〜生配信！\nhttps://youtube.com/live/tmrwVideoI1"
    r15 = parse_live_now(S15, NOW)
    assert len(r15) == 1, r15
    # NOW = 2026-09-03T00:00:00Z(09:00 JST) → 明日20:00 = 2026-09-04 20:00 JST = 11:00 UTC
    assert r15[0]["scheduled_start"] == "2026-09-04T11:00:00Z", r15[0]["scheduled_start"]
    print("[OK] S15  (明日HH時〜 → +1일 반영)")

    # S16: "明日朝" 복합형(明日 + 시간대어 필러) — parse_bdp_schedule 의 明日朝 표기와 동일
    S16 = "＼本日開催📢／\n夢限大みゅーたいぷ\n明日朝7:00〜生配信！\nhttps://youtube.com/live/tmrwVideoI2"
    r16 = parse_live_now(S16, NOW)
    assert len(r16) == 1, r16
    assert r16[0]["scheduled_start"] == "2026-09-03T22:00:00Z", r16[0]["scheduled_start"]  # 익일 07:00 JST
    print("[OK] S16  (明日朝HH:MM〜 → 필러 건너뛰고 +1일 반영)")

    # unparsed_lines
    S_BAD = (
        "8/30(日) 配信スケジュール\n"
        "🎮11:00〜 宮永ののか\n"
        "💭21:00〜 だれか\n"
        "🎤21:30 藤都子\n"
        "【メン限】千石ユノ\n"
        "※時刻は予告なく変更の場合がございます。\n#バンドリ"
    )
    bad = unparsed_lines(S_BAD)
    assert len(bad) == 3, bad
    assert len(parse_bdp_schedule(S_BAD, NOW)) == 1
    assert unparsed_lines(S1) == []
    assert unparsed_lines("配信スケジュール 없음\n🎮11:00〜 だれか") == []
    print("[OK] unparsed_lines  (이름·시각 누락)")

    # merge_announced: upsert 로직 (v3)
    prev = [
        preview.make_item(
            channel_key="arale", state="upcoming", source="api", now_iso=NOW,
            scheduled_start="2026-09-03T05:00:00Z", video_id="vidA"
        ),
    ]
    merged, changed = merge_announced(prev, r1, "2026-09-03T01:00:00Z")
    assert changed is True, "r1 (6개) 추가되면 changed=True"
    assert len(merged) >= 6, f"기존 1개 + 새 6개(중복 제거) >= 6: {len(merged)}"
    existing_upcoming = next((x for x in merged if x.get("video_id") == "vidA"), None)
    assert existing_upcoming is not None, "기존 upcoming 보존"
    assert existing_upcoming["state"] == "upcoming"
    new_announced = next((x for x in merged if x.get("state") == "announced"), None)
    assert new_announced is not None, "새 announced 추가"
    print("[OK] merge_announced  (announced 추가, upcoming 보존)")

    # merge_announced: replace by match (둘 다 announced — 시각 갱신된 재공지)
    prev_stale = [
        preview.make_item(
            channel_key="arale", state="announced", source="x-relay", now_iso=NOW,
            scheduled_start="2026-08-30T13:00:00Z"
        ),
    ]
    r_replay = [
        preview.make_item(
            channel_key="arale", state="announced", source="x-relay", now_iso=NOW,
            scheduled_start="2026-08-30T13:30:00Z"  # 30분 정정
        ),
    ]
    merged2, changed2 = merge_announced(prev_stale, r_replay, NOW)
    assert changed2 is True
    assert len(merged2) == 1, "기존과 근접 시각 → replace 되므로 1개 유지"
    assert merged2[0]["scheduled_start"] == "2026-08-30T13:30:00Z", "정정된 시각 반영"
    print("[OK] merge_announced  (replace by match)")

    # merge_announced: 상위 티어(video_id 확보) 항목은 재공지에 덮어써지지 않음
    # 실측 버그(2026-09-13): API 로 확정된 upcoming(video_id 有)이 같은 날 그룹
    # 공식 채널 일일 스케줄 재공지에 매칭돼 video_id 없는 announced 로 되돌아갔다.
    prev_confirmed = [
        preview.make_item(
            channel_key="miyako", state="upcoming", source="api", now_iso=NOW,
            id="pv_confirmed1", scheduled_start="2026-09-13T11:00:00Z",
            video_id="7Q2gPHbBrdw", title="최종회 스페셜",
            thumbnail="https://i.ytimg.com/vi/7Q2gPHbBrdw/maxresdefault_live.jpg",
            url="https://www.youtube.com/watch?v=7Q2gPHbBrdw",
        ),
    ]
    daily_reannounce = [
        preview.make_item(
            channel_key="miyako", state="announced", source="x-relay", now_iso=NOW,
            scheduled_start="2026-09-13T11:00:00Z", kind="talk",
        ),
    ]
    merged_hi, changed_hi = merge_announced(prev_confirmed, daily_reannounce, NOW)
    assert len(merged_hi) == 1, "동일 방송 재공지는 1개로 유지"
    kept = merged_hi[0]
    assert kept["video_id"] == "7Q2gPHbBrdw", f"video_id 유지 실패: {kept}"
    assert kept["state"] == "upcoming", f"state 유지 실패: {kept}"
    assert kept["title"] == "최종회 스페셜", "title 유지 실패"
    assert kept["kind"] == "talk", "빈 보조 필드(kind)는 보강되어야 함"
    print("[OK] merge_announced  (상위 티어 항목 보존 — 보조 필드만 보강)")

    # merge_announced: empty
    merged3, changed3 = merge_announced(prev, [], NOW)
    assert changed3 is False, "빈 inc_list → changed=False"
    assert len(merged3) == len(prev), "기존 그대로"
    print("[OK] merge_announced  (empty list → changed=False)")

    print("\nSUCCESS: xrelay v3 self-test 통과")
