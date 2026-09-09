"""
Telegram 알림 모듈: 상태 전이 이벤트 감지 및 메시지 전송.

계약: docs/SPEC.md §8.6 (메시지 포맷 예시는 docs/old/IMPLEMENTATION_v2.1.md §4)
"""

import html
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)


def _parse_iso(s: str) -> datetime:
    """ISO 문자열 파싱 (Z → +00:00, tz-aware UTC)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _to_iso(dt: datetime) -> str:
    """datetime을 ISO 문자열로 변환 (UTC, 'Z' suffix)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_kst(iso_str: str) -> str:
    """ISO 문자열을 KST MM/DD HH:mm 포맷으로 변환."""
    dt = _parse_iso(iso_str)
    kst = dt.astimezone(timezone(timedelta(hours=9)))
    return kst.strftime("%m/%d %H:%M")


def _lateness_label(lateness_sec: int) -> str:
    """지각 라벨 생성.

    lateness_sec > 300 → "{n}분 지각" / "{h}시간 {m}분 지각"
    -300..300 → "정시"
    < -300 → "{n}분 일찍"
    """
    if -300 <= lateness_sec <= 300:
        return "정시"
    elif lateness_sec > 300:
        minutes = lateness_sec // 60
        if minutes < 60:
            return f"{minutes}분 지각"
        else:
            hours = minutes // 60
            mins = minutes % 60
            if mins == 0:
                return f"{hours}시간 지각"
            else:
                return f"{hours}시간 {mins}분 지각"
    else:  # lateness_sec < -300
        minutes = abs(lateness_sec) // 60
        if minutes < 60:
            return f"{minutes}분 일찍"
        else:
            hours = minutes // 60
            mins = minutes % 60
            if mins == 0:
                return f"{hours}시간 일찍"
            else:
                return f"{hours}시간 {mins}분 일찍"


class Telegram:
    """Telegram Bot API 클라이언트."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        session: "requests.Session | None" = None,
        timeout: float = 10.0,
    ):
        """
        Telegram 봇 초기화.

        Args:
            token: BotFather에서 받은 봇 토큰. 비어있으면 disabled.
            chat_id: 운영자 DM chat_id. 비어있으면 disabled.
            session: 선택사항 requests.Session
            timeout: API 호출 타임아웃 (초)
        """
        self.token = token
        self.chat_id = chat_id
        self.session = session or requests.Session()
        self.timeout = timeout
        self.disabled = not token or not chat_id

    def send(
        self,
        text: str,
        *,
        parse_mode: str = "HTML",
        silent: bool = False,
    ) -> bool:
        """
        메시지 전송.

        token/chat_id 비면 no-op (warning 로그) + True 반환.
        전송 실패(네트워크/4xx)는 예외 없이 False + logging.warning 반환.

        Args:
            text: 메시지 본문 (parse_mode에 맞춘 포맷)
            parse_mode: "HTML" (기본) 또는 "Markdown"
            silent: True면 disable_notification=true

        Returns:
            성공하면 True, 실패하면 False
        """
        if self.disabled:
            logger.warning("Telegram disabled (token or chat_id missing)")
            return True

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if silent:
            payload["disable_notification"] = True

        try:
            resp = self.session.post(url, data=payload, timeout=self.timeout)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning(f"Telegram send failed: {exc}")
            return False


# 로그 레벨별 전송 허용 이벤트 종류 (control.json log_level). (v3)
#   detail : announced·upcoming·live_start·live_end·demote·notice·tweet·ingest + error/summary
#   normal : announced·upcoming·live_start·live_end·notice·tweet (demote ✗)
#   simple : upcoming·live_start·live_end 만
#   ── kind 목록 ──
#   announced : preview 신규 announced 항목 (첫실행 가드 유지)
#   upcoming  : announced→upcoming 전이
#   live_start: *→live 전이 (lateness 포함)
#   live_end  : live→end 전이
#   demote    : watching→announced 지각 강등 (v3 fallback 대체)
#   notice    : 소식 자동 인입(_maybe_auto_notice)
#   tweet     : 개인 트윗 배지 반영(_maybe_personal_tweet)
#   ingest    : /ingest 릴레이 반영 결과 DM
#   error / summary : 운영 진단 — detail 에서만
_LEVEL_KINDS = {
    "detail": {"announced", "upcoming", "live_start", "live_end", "demote",
               "notice", "tweet", "ingest", "error", "summary"},
    "normal": {"announced", "upcoming", "live_start", "live_end",
               "notice", "tweet"},
    "simple": {"upcoming", "live_start", "live_end"},
}


def allows(level: str, kind: str) -> bool:
    """log_level 에서 해당 이벤트 종류를 Telegram 으로 보낼지."""
    return kind in _LEVEL_KINDS.get(level, _LEVEL_KINDS["normal"])


@dataclass
class Event:
    """상태 전이 이벤트."""

    kind: str  # "announced" | "upcoming" | "live_start" | "live_end" | "demote"
    channel_ko: str
    title: str
    text: str  # 이미 포맷된 전송용 본문 (HTML)


def diff_events(
    prev_items: list[dict] | None,
    new_items: list[dict],
    transitions: list[str],
    channels_cfg: dict,
    now_iso: str,
) -> list[Event]:
    """
    v3 preview 아이템 상태 전이 → 이벤트 생성.

    preview items 의 state 전이를 감지해 Telegram 알림 이벤트 생성.
    첫실행 가드: prev_items 없으면 announced 이벤트 생성 안 함.

    Args:
        prev_items: 이전 preview.items (또는 None)
        new_items: 현재 preview.items
        transitions: statemachine.derive 로그 (상태 전이 토큰)
        channels_cfg: config/channels.json 의 channels 부분
        now_iso: 현재 시각 (ISO 'Z')

    Returns:
        Event 리스트
    """
    events = []
    first_run = prev_items is None or len(prev_items) == 0

    if prev_items is None:
        prev_items = []

    # ponytail: id 또는 video_id로 인덱싱. 둘 다 없으면 매칭 안 함
    prev_by_id = {}
    for item in prev_items:
        key = item.get("id") or item.get("video_id")
        if key:
            prev_by_id[key] = item

    new_by_id = {}
    for item in new_items:
        key = item.get("id") or item.get("video_id")
        if key:
            new_by_id[key] = item

    # ─ announced: new에 announced 등장 (첫실행 가드 유지) ─
    if not first_run:
        for key, new_item in new_by_id.items():
            if new_item.get("state") == "announced":
                prev_item = prev_by_id.get(key)
                if prev_item is None or prev_item.get("state") != "announced":
                    # 신규 announced 항목
                    channel_key = new_item.get("channel_key", "")
                    channel_ko = channels_cfg.get(channel_key, {}).get(
                        "name_ko", "알 수 없음"
                    )
                    title = html.escape(new_item.get("title", "제목 없음"))
                    scheduled_start = new_item.get("scheduled_start", "")
                    scheduled_kst = _to_kst(scheduled_start) if scheduled_start else "미정"

                    text = (
                        f"📢 <b>방송 예고</b>\n"
                        f"{channel_ko}\n"
                        f"「{title}」\n"
                        f"예정 {scheduled_kst}"
                    )
                    events.append(
                        Event(
                            kind="announced",
                            channel_ko=channel_ko,
                            title=title,
                            text=text,
                        )
                    )

    # ─ upcoming: announced→upcoming 전이 ─
    for key, new_item in new_by_id.items():
        if new_item.get("state") == "upcoming":
            prev_item = prev_by_id.get(key)
            if prev_item and prev_item.get("state") == "announced":
                # announced→upcoming 전이
                channel_key = new_item.get("channel_key", "")
                channel_ko = channels_cfg.get(channel_key, {}).get(
                    "name_ko", "알 수 없음"
                )
                title = html.escape(new_item.get("title", "제목 없음"))
                scheduled_start = new_item.get("scheduled_start", "")
                scheduled_kst = _to_kst(scheduled_start) if scheduled_start else "미정"

                # 상대시간
                try:
                    start_dt = _parse_iso(scheduled_start)
                    now_dt = _parse_iso(now_iso)
                    delta = (start_dt - now_dt).total_seconds()
                    if delta < 0:
                        relative = "진행 중"
                    elif delta < 3600:
                        minutes = max(1, int(delta // 60))
                        relative = f"{minutes}분 후"
                    elif delta < 86400:
                        hours = max(1, int(delta // 3600))
                        relative = f"{hours}시간 후"
                    else:
                        days = max(1, int(delta // 86400))
                        relative = f"{days}일 후"
                except Exception:
                    relative = "미정"

                text = (
                    f"📅 <b>예정 방송</b>\n"
                    f"{channel_ko}\n"
                    f"「{title}」\n"
                    f"시작: {scheduled_kst} ({relative})"
                )
                events.append(
                    Event(
                        kind="upcoming",
                        channel_ko=channel_ko,
                        title=title,
                        text=text,
                    )
                )

    # ─ live_start: *→live 전이 ─
    for key, new_item in new_by_id.items():
        if new_item.get("state") == "live":
            prev_item = prev_by_id.get(key)
            if prev_item is None or prev_item.get("state") != "live":
                # 새로 live 상태로 전이
                channel_key = new_item.get("channel_key", "")
                channel_ko = channels_cfg.get(channel_key, {}).get(
                    "name_ko", "알 수 없음"
                )
                title = html.escape(new_item.get("title", "제목 없음"))

                scheduled_start = new_item.get("scheduled_start", "")
                actual_start = new_item.get("actual_start", "")

                lateness_sec = 0
                if scheduled_start and actual_start:
                    try:
                        ss_dt = _parse_iso(scheduled_start)
                        as_dt = _parse_iso(actual_start)
                        lateness_sec = int((as_dt - ss_dt).total_seconds())
                    except Exception:
                        lateness_sec = 0

                scheduled_kst = _to_kst(scheduled_start) if scheduled_start else "미정"
                actual_kst = _to_kst(actual_start) if actual_start else "미정"
                lateness_label = _lateness_label(lateness_sec)

                text = (
                    f"🔴 <b>방송 시작</b>\n"
                    f"{channel_ko}\n"
                    f"「{title}」\n"
                    f"예정 {scheduled_kst} → 실제 {actual_kst} · "
                    f"<b>{lateness_label}</b>"
                )
                events.append(
                    Event(
                        kind="live_start",
                        channel_ko=channel_ko,
                        title=title,
                        text=text,
                    )
                )

    # ─ live_end: live→end 전이 ─
    for key, prev_item in prev_by_id.items():
        if prev_item.get("state") == "live":
            new_item = new_by_id.get(key)
            if new_item and new_item.get("state") == "end":
                # live→end 전이
                channel_key = prev_item.get("channel_key", "")
                channel_ko = channels_cfg.get(channel_key, {}).get(
                    "name_ko", "알 수 없음"
                )
                title = html.escape(prev_item.get("title", "제목 없음"))

                actual_start = prev_item.get("actual_start", "")
                actual_end = new_item.get("actual_end", "")

                start_kst = _to_kst(actual_start) if actual_start else "미정"
                end_kst = _to_kst(actual_end) if actual_end else "미정"

                length_str = "미정"
                if actual_start and actual_end:
                    try:
                        start_dt = _parse_iso(actual_start)
                        end_dt = _parse_iso(actual_end)
                        duration_sec = int((end_dt - start_dt).total_seconds())
                        hours = duration_sec // 3600
                        minutes = (duration_sec % 3600) // 60
                        if hours > 0:
                            length_str = f"{hours}시간 {minutes}분"
                        else:
                            length_str = f"{minutes}분"
                    except Exception:
                        pass

                text = (
                    f"⚫ <b>방송 종료</b>\n"
                    f"{channel_ko}\n"
                    f"「{title}」\n"
                    f"{start_kst} ~ {end_kst} ({length_str})"
                )
                events.append(
                    Event(
                        kind="live_end",
                        channel_ko=channel_ko,
                        title=title,
                        text=text,
                    )
                )

    # ─ demote: watching→announced 지각 강등 ─
    for token in transitions:
        if "demote" in token:
            # 포맷: "watching-demote {id}" 등 (상세는 statemachine 참조)
            parts = token.split()
            if len(parts) >= 2:
                key = parts[1] if "demote" in parts[0] else parts[0]
                new_item = new_by_id.get(key)
                if new_item and new_item.get("state") == "announced":
                    channel_key = new_item.get("channel_key", "")
                    channel_ko = channels_cfg.get(channel_key, {}).get(
                        "name_ko", "알 수 없음"
                    )
                    title = html.escape(new_item.get("title", "제목 없음"))
                    scheduled_start = new_item.get("scheduled_start", "")
                    scheduled_kst = (
                        _to_kst(scheduled_start) if scheduled_start else "미정"
                    )

                    text = (
                        f"⚠️ <b>방송 미시작</b>\n"
                        f"{channel_ko}\n"
                        f"「{title}」\n"
                        f"예정 {scheduled_kst} 2시간 이상 경과"
                    )
                    events.append(
                        Event(
                            kind="demote",
                            channel_ko=channel_ko,
                            title=title,
                            text=text,
                        )
                    )

    return events


def summary_text(result: dict, now_iso: str) -> str:
    """
    tick 결과 dict → D(요약) 본문 (변경 있을 때만 호출됨).

    D 형식:
    ```
    🔄 <b>light sync</b> 21:00
    후보 78 · 조회 78 · 쿼터 2
    schedule 변경 O · pending 6건 · enqueue 3/3
    전이: new pre-live ×2
    ```

    Args:
        result: handlers.tick 반환 dict (mode, candidates, videos, schedule_changed, etc.)
        now_iso: 현재 시각 (ISO 'Z')

    Returns:
        메시지 본문 (HTML)
    """
    kst = _to_kst(now_iso)
    mode = result.get("mode", "light")
    mode_label = {"light": "light sync", "baseline": "baseline sync", "wake": "wake"}.get(
        mode, mode
    )

    candidates = result.get("candidates", 0)
    videos = result.get("videos", 0)
    quota = result.get("quota_used", 0)
    preview_changed = "O" if result.get("preview_changed") else "X"
    item_count = result.get("preview_items", 0)
    enqueue_errors = result.get("enqueue_errors", [])
    enqueue_ok = result.get("enqueued", 0)
    enqueue_total = enqueue_ok + len(enqueue_errors)

    # 로그(statemachine.derive 토큰)에서 전이 요약 추출
    tallies: dict[str, int] = {}
    for tok in result.get("log", []):
        for mark in ("→watching", "→live", "→end", "end→none", "watching-demote", "assumed-live drop"):
            if mark in tok:
                tallies[mark] = tallies.get(mark, 0) + 1
                break
    transition_str = " · ".join(f"{k} ×{v}" for k, v in sorted(tallies.items()))

    tl = result.get("translated", {}) or {}
    tl_n = tl.get("notice_tl", 0) + tl.get("tweet_tl", 0)

    text = (
        f"🔄 <b>{mode_label}</b> {kst}\n"
        f"후보 {candidates} · 조회 {videos} · 쿼터 {quota}\n"
        f"preview 변경 {preview_changed} · {item_count}건 · enqueue {enqueue_ok}/{enqueue_total}"
    )
    if tl_n:
        text += f" · 번역 {tl_n}"
    if transition_str:
        text += f"\n전이: {transition_str}"

    return text


def error_text(where: str, exc: BaseException) -> str:
    """
    F(서버 오류) 본문.

    포맷:
    ```
    🚨 <b>서버 오류</b>
    /wake video_id=abc123
    RuntimeError: YouTube API error: 403 quotaExceeded
    ```

    Args:
        where: 발생 위치 (예: "/wake video_id=abc123")
        exc: 예외 객체

    Returns:
        메시지 본문 (HTML)
    """
    where_escaped = html.escape(str(where))
    exc_type = type(exc).__name__
    exc_msg = html.escape(str(exc))

    text = f"🚨 <b>서버 오류</b>\n{where_escaped}\n{exc_type}: {exc_msg}"
    return text


if __name__ == "__main__":
    # Windows UTF-8 콘솔 가드
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 70)
    print("Telegram notify.py v3 스모크 테스트")
    print("=" * 70)

    # 테스트용 채널 설정
    channels_cfg = {
        "arale": {"name_ko": "나카마치 아라레"},
        "yuno": {"name_ko": "센고쿠 유노"},
        "ritsu": {"name_ko": "미네츠키 리츠"},
    }

    now_iso = "2026-08-31T12:00:00Z"

    # 시나리오 1: 첫 실행 가드 — prev_items 없으면 announced 이벤트 생성 안 함
    print("\n[시나리오 1] 첫 실행 가드 — prev_items 없으면 announced 이벤트 안 함")
    print("-" * 70)

    prev_items_1 = None
    new_items_1 = [
        {
            "id": "pv_abc12345",
            "video_id": "vid1",
            "channel_key": "arale",
            "title": "新春配信",
            "state": "announced",
            "scheduled_start": "2026-09-01T13:00:00Z",
        }
    ]
    transitions_1 = []

    events_1 = diff_events(
        prev_items_1,
        new_items_1,
        transitions_1,
        channels_cfg,
        now_iso,
    )

    assert len(events_1) == 0, f"첫 실행이므로 announced 이벤트 없어야 함, got {len(events_1)}"
    print("✓ 첫 실행 가드 작동: announced 이벤트 0개")

    # 시나리오 2: announced 신규 등장 → Event 생성
    print("\n[시나리오 2] announced 신규 등장 → Event 생성")
    print("-" * 70)

    prev_items_2 = [
        # 첫 실행 가드를 피하기 위해 기존 항목 1개 포함
        {
            "id": "pv_old_item",
            "video_id": "vid_old",
            "channel_key": "yuno",
            "title": "이전 방송",
            "state": "ended",
        }
    ]
    new_items_2 = [
        {
            "id": "pv_old_item",
            "video_id": "vid_old",
            "channel_key": "yuno",
            "title": "이전 방송",
            "state": "ended",
        },
        {
            "id": "pv_def67890",
            "video_id": None,
            "channel_key": "arale",
            "title": "歌枠 ~まったりお歌~",
            "state": "announced",
            "scheduled_start": "2026-09-07T23:45:00Z",
        }
    ]

    events_2 = diff_events(
        prev_items_2,
        new_items_2,
        [],
        channels_cfg,
        now_iso,
    )

    assert len(events_2) == 1, f"announced 이벤트 1개 기대, got {len(events_2)}"
    assert events_2[0].kind == "announced"
    assert "나카마치 아라레" in events_2[0].text
    assert "歌枠" in events_2[0].text
    print("✓ announced 이벤트 생성됨")
    print(f"  {events_2[0].text[:80]}...")

    # 시나리오 3: announced→upcoming 전이 → Event 생성
    print("\n[시나리오 3] announced→upcoming 전이 → Event 생성")
    print("-" * 70)

    prev_items_3 = [
        {
            "id": "pv_ghi34567",
            "video_id": "vid3",
            "channel_key": "ritsu",
            "title": "【ASMR】…",
            "state": "announced",
            "scheduled_start": "2026-09-01T20:00:00Z",
        }
    ]
    new_items_3 = [
        {
            "id": "pv_ghi34567",
            "video_id": "vid3",
            "channel_key": "ritsu",
            "title": "【ASMR】…",
            "state": "upcoming",
            "scheduled_start": "2026-09-01T20:00:00Z",
            "thumbnail": "https://...",
        }
    ]

    events_3 = diff_events(
        prev_items_3,
        new_items_3,
        [],
        channels_cfg,
        now_iso,
    )

    assert len(events_3) == 1
    assert events_3[0].kind == "upcoming"
    assert "미네츠키 리츠" in events_3[0].text
    print("✓ upcoming 이벤트 생성됨 (announced→upcoming 전이)")
    print(f"  {events_3[0].text[:80]}...")

    # 시나리오 4: live→end 전이 → Event 생성
    print("\n[시나리오 4] live→end 전이 → Event 생성")
    print("-" * 70)

    prev_items_4 = [
        {
            "id": "pv_jkl78901",
            "video_id": "vid4",
            "channel_key": "ritsu",
            "title": "【ASMR】…",
            "state": "live",
            "actual_start": "2026-08-31T22:07:00Z",
        }
    ]
    new_items_4 = [
        {
            "id": "pv_jkl78901",
            "video_id": "vid4",
            "channel_key": "ritsu",
            "title": "【ASMR】…",
            "state": "end",
            "actual_start": "2026-08-31T22:07:00Z",
            "actual_end": "2026-09-01T00:14:00Z",
        }
    ]

    events_4 = diff_events(
        prev_items_4,
        new_items_4,
        [],
        channels_cfg,
        now_iso,
    )

    assert len(events_4) == 1
    assert events_4[0].kind == "live_end"
    assert "2시간 7분" in events_4[0].text
    print("✓ live_end 이벤트 생성됨")
    print(f"  {events_4[0].text[:80]}...")

    # 시나리오 5: watching→announced 지각 강등 (demote) → Event 생성
    print("\n[시나리오 5] watching→announced demote 전이 → Event 생성")
    print("-" * 70)

    prev_items_5 = [
        {
            "id": "pv_mno12345",
            "video_id": "vid5",
            "channel_key": "yuno",
            "title": "新春配信",
            "state": "watching",
            "scheduled_start": "2026-08-31T06:00:00Z",  # 6시간 전
        }
    ]
    new_items_5 = [
        {
            "id": "pv_mno12345",
            "video_id": "vid5",
            "channel_key": "yuno",
            "title": "新春配信",
            "state": "announced",  # 지각 강등됨
            "scheduled_start": "2026-08-31T06:00:00Z",
        }
    ]
    transitions_5 = ["watching-demote pv_mno12345"]

    events_5 = diff_events(
        prev_items_5,
        new_items_5,
        transitions_5,
        channels_cfg,
        now_iso,
    )

    assert any(e.kind == "demote" for e in events_5), "demote 이벤트 없음"
    demote_event = [e for e in events_5 if e.kind == "demote"][0]
    assert "센고쿠 유노" in demote_event.text
    assert "2시간 이상 경과" in demote_event.text
    print("✓ demote 이벤트 생성됨")
    print(f"  {demote_event.text}")

    # 시나리오 6: *→live 전이 (지각 포함) → live_start Event
    print("\n[시나리오 6] upcoming→live 전이, 지각 7분 → live_start Event")
    print("-" * 70)

    prev_items_6 = [
        {
            "id": "pv_pqr56789",
            "video_id": "vid6",
            "channel_key": "ritsu",
            "title": "新作ASMR",
            "state": "upcoming",
            "scheduled_start": "2026-08-31T22:00:00Z",
        }
    ]
    new_items_6 = [
        {
            "id": "pv_pqr56789",
            "video_id": "vid6",
            "channel_key": "ritsu",
            "title": "新作ASMR",
            "state": "live",
            "scheduled_start": "2026-08-31T22:00:00Z",
            "actual_start": "2026-08-31T22:07:00Z",
        }
    ]

    events_6 = diff_events(
        prev_items_6,
        new_items_6,
        [],
        channels_cfg,
        now_iso,
    )

    assert len(events_6) == 1
    assert events_6[0].kind == "live_start"
    assert "7분 지각" in events_6[0].text
    print("✓ live_start 이벤트 생성됨 (지각 라벨 포함)")
    print(f"  {events_6[0].text[:80]}...")

    # 시나리오 7: Telegram.send disabled (token/chat_id 없음)
    print("\n[시나리오 7] Telegram.send disabled (token/chat_id 없음)")
    print("-" * 70)

    tg = Telegram("", "")
    result = tg.send("Test message")
    assert result is True, "disabled 상태에서 True 반환해야 함"
    print("✓ Telegram send no-op: True 반환")

    # 시나리오 8: summary_text
    print("\n[시나리오 8] summary_text()")
    print("-" * 70)

    result_dict = {
        "mode": "light",
        "candidates": 78,
        "videos": 78,
        "quota_used": 2,
        "preview_changed": True,
        "preview_items": 6,
        "enqueued": 3,
        "enqueue_errors": [],
        "translated": {"notice_tl": 1, "tweet_tl": 0},
        "log": [
            "→watching pv_abc123",
            "→live pv_def456",
            "→end pv_ghi789",
        ],
    }

    summary = summary_text(result_dict, now_iso)
    assert "light sync" in summary
    assert "후보 78" in summary
    assert "preview 변경 O" in summary
    assert "enqueue 3/3" in summary
    assert "번역 1" in summary
    print("✓ summary_text 생성됨")
    print(f"  {summary[:80]}...")

    # 시나리오 9: error_text
    print("\n[시나리오 9] error_text()")
    print("-" * 70)

    exc = RuntimeError("YouTube API error: 403 quotaExceeded")
    error_msg = error_text("/wake video_id=abc123", exc)
    assert "🚨" in error_msg
    assert "RuntimeError" in error_msg
    assert "quotaExceeded" in error_msg
    print("✓ error_text 생성됨")
    print(f"  {error_msg}")

    # 시나리오 10: allows() — (v3) 레벨별 kind 게이팅
    print("\n[시나리오 10] allows() v3 레벨별 게이팅")
    print("-" * 70)
    # simple: upcoming, live_start, live_end
    assert allows("simple", "upcoming") and allows("simple", "live_start") and allows("simple", "live_end")
    assert not allows("simple", "announced") and not allows("simple", "demote")
    assert not allows("simple", "notice") and not allows("simple", "tweet")
    # normal: announced, upcoming, live_start, live_end, notice, tweet
    assert all(allows("normal", k) for k in ("announced", "upcoming", "live_start", "live_end", "notice", "tweet"))
    assert not allows("normal", "demote") and not allows("normal", "ingest")
    # detail: 모두 (announced, upcoming, live_*, demote, notice, tweet, ingest, error, summary)
    assert all(allows("detail", k) for k in
               ("announced", "upcoming", "live_start", "live_end", "demote",
                "notice", "tweet", "ingest", "error", "summary"))
    print("✓ v3: simple=upcoming/live_* · normal=+announced/notice/tweet · detail=+demote/ingest/error/summary")

    print("\n" + "=" * 70)
    print("SUCCESS: 모든 10개 v3 스모크 테스트 통과")
    print("=" * 70)
