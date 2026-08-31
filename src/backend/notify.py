"""
Telegram 알림 모듈: 상태 전이 이벤트 감지 및 메시지 전송.

계약: docs/IMPLEMENTATION_v2.1.md §4 [haiku #1]
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


@dataclass
class Event:
    """상태 전이 이벤트."""

    kind: str  # "upcoming" | "live_start" | "live_end" | "fallback"
    channel_ko: str
    title: str
    text: str  # 이미 포맷된 전송용 본문 (HTML)


def diff_events(
    prev_schedule: dict,
    new_schedule: dict,
    newly_ended: list[dict],
    sm_log: list[str],
    channels_cfg: dict,
    now_iso: str,
) -> list[Event]:
    """
    이전·현재 schedule과 로그를 대조해 A/B/C/E 이벤트 목록 생성.

    Args:
        prev_schedule: 이전 schedule.json (또는 None)
        new_schedule: 현재 schedule.json
        newly_ended: reconcile.build_schedule 에서 반환한 newly_ended 리스트
        sm_log: statemachine 로그 (decision.log)
        channels_cfg: config/channels.json 의 channels 부분
        now_iso: 현재 시각 (ISO 'Z')

    Returns:
        Event 리스트
    """
    events = []

    # 첫 실행 가드: prev가 없거나 generated_at이 None이면 upcoming(A) 생성 안 함
    # (broadcasts가 0개여도 generated_at이 있으면 과거에 실행된 상태)
    first_run = prev_schedule is None or prev_schedule.get("generated_at") is None

    if prev_schedule is None:
        prev_schedule = {"broadcasts": []}

    # 비디오 ID로 인덱싱
    prev_by_id = {b.get("video_id"): b for b in prev_schedule.get("broadcasts", [])}
    new_by_id = {b.get("video_id"): b for b in new_schedule.get("broadcasts", [])}

    # ─ A: upcoming 신규 발생 ─
    if not first_run:
        for vid, new_bc in new_by_id.items():
            if vid not in prev_by_id and new_bc.get("status") == "upcoming":
                channel_ko = channels_cfg.get(new_bc.get("channel_key"), {}).get(
                    "name_ko", "알 수 없음"
                )
                title = html.escape(new_bc.get("title", "제목 없음"))
                start_iso = new_bc.get("scheduled_start", "")
                start_kst = _to_kst(start_iso) if start_iso else "미정"

                # 상대시간 계산 (단순 구현 — 프론트 time.js와 동기화)
                try:
                    start_dt = _parse_iso(start_iso)
                    now_dt = _parse_iso(now_iso)
                    delta = (start_dt - now_dt).total_seconds()
                    if delta < 0:
                        relative = "진행 중"
                    elif delta < 3600:
                        minutes = int(delta // 60) + 1
                        relative = f"{minutes}분 후"
                    elif delta < 86400:
                        hours = int(delta // 3600) + 1
                        relative = f"{hours}시간 후"
                    elif delta < 604800:
                        days = int(delta // 86400) + 1
                        relative = f"{days}일 후"
                    else:
                        weeks = int(delta // 604800) + 1
                        relative = f"{weeks}주 후"
                except Exception:
                    relative = "미정"

                text = (
                    f"📅 <b>예정 방송</b>\n"
                    f"{channel_ko}\n"
                    f"「{title}」\n"
                    f"시작: {start_kst} ({relative})"
                )
                events.append(
                    Event(
                        kind="upcoming",
                        channel_ko=channel_ko,
                        title=title,
                        text=text,
                    )
                )

    # ─ B: live 시작 ─
    for vid, new_bc in new_by_id.items():
        if new_bc.get("status") == "live":
            prev_bc = prev_by_id.get(vid)
            # 이전에 upcoming이었거나 새로 live로 등장
            if prev_bc is None or prev_bc.get("status") != "live":
                channel_ko = channels_cfg.get(new_bc.get("channel_key"), {}).get(
                    "name_ko", "알 수 없음"
                )
                title = html.escape(new_bc.get("title", "제목 없음"))

                scheduled_start = new_bc.get("scheduled_start", "")
                actual_start = new_bc.get("actual_start", "")

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

    # ─ C: live 종료 ─
    for end_bc in newly_ended:
        channel_ko = channels_cfg.get(end_bc.get("channel_key"), {}).get(
            "name_ko", "알 수 없음"
        )
        title = html.escape(end_bc.get("title", "제목 없음"))

        actual_start = end_bc.get("actual_start", "")
        actual_end = end_bc.get("actual_end", "")

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

        reason = end_bc.get("reason", "정상")
        reason_label = {
            "ended": "정상 종료",
            "canceled": "취소됨",
            "removed": "삭제됨",
        }.get(reason, "정상 종료")

        text = (
            f"⚫ <b>방송 종료</b>\n"
            f"{channel_ko}\n"
            f"「{title}」\n"
            f"{start_kst} ~ {end_kst} ({length_str}) · {reason_label}"
        )
        events.append(
            Event(
                kind="live_end",
                channel_ko=channel_ko,
                title=title,
                text=text,
            )
        )

    # ─ E: fallback 발생 ─
    for log_token in sm_log:
        if log_token.startswith("fallback "):
            # 포맷: "fallback {vid} attempts={n} next={iso}"
            parts = log_token.split()
            if len(parts) >= 2:
                vid = parts[1]
                attempts_str = next(
                    (p for p in parts[2:] if p.startswith("attempts=")), ""
                )
                next_str = next(
                    (p for p in parts[2:] if p.startswith("next=")), ""
                )

                attempts = attempts_str.split("=")[1] if "=" in attempts_str else "?"
                next_iso = next_str.split("=")[1] if "=" in next_str else ""

                # vid에 해당하는 broadcast 찾기
                broadcast = new_by_id.get(vid)
                if broadcast:
                    channel_ko = channels_cfg.get(
                        broadcast.get("channel_key"), {}
                    ).get("name_ko", "알 수 없음")
                    title = html.escape(broadcast.get("title", "제목 없음"))
                    scheduled_start = broadcast.get("scheduled_start", "")

                    scheduled_kst = (
                        _to_kst(scheduled_start) if scheduled_start else "미정"
                    )
                    next_check_kst = _to_kst(next_iso) if next_iso else "미정"

                    text = (
                        f"⚠️ <b>fallback</b>\n"
                        f"{channel_ko} 「{title}」\n"
                        f"예정 {scheduled_kst} 경과·미시작 (시도 {attempts}회) "
                        f"→ 다음 확인 {next_check_kst}"
                    )
                    events.append(
                        Event(
                            kind="fallback",
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
    mode_label = "light sync" if mode == "light" else "baseline sync"

    candidates = result.get("candidates", 0)
    videos = result.get("videos", 0)
    quota = result.get("quota_used", 0)
    schedule_changed = "O" if result.get("schedule_changed") else "X"
    pending_count = result.get("pending_entries", 0)
    enqueue_errors = result.get("enqueue_errors", [])
    enqueue_ok = result.get("enqueued", 0)
    enqueue_total = enqueue_ok + len(enqueue_errors)

    # 로그에서 전이 요약 추출
    log = result.get("log", [])
    transitions = {}
    for log_token in log:
        if "pre-live" in log_token:
            key = "new pre-live" if "new pre-live" in log_token else "pre-live"
            transitions[key] = transitions.get(key, 0) + 1
        elif "live-watch" in log_token:
            transitions["live-watch"] = transitions.get("live-watch", 0) + 1
        elif "pre-live→live-watch" in log_token:
            transitions["pre-live→live-watch"] = (
                transitions.get("pre-live→live-watch", 0) + 1
            )

    transition_str = " · ".join(
        f"{k} ×{v}" for k, v in sorted(transitions.items())
    )
    transition_line = f"전이: {transition_str}" if transition_str else ""

    text = (
        f"🔄 <b>{mode_label}</b> {kst}\n"
        f"후보 {candidates} · 조회 {videos} · 쿼터 {quota}\n"
        f"schedule 변경 {schedule_changed} · pending {pending_count}건 · "
        f"enqueue {enqueue_ok}/{enqueue_total}"
    )
    if transition_line:
        text += f"\n{transition_line}"

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
    print("Telegram notify.py 스모크 테스트")
    print("=" * 70)

    # 테스트용 채널 설정
    channels_cfg = {
        "arale": {"name_ko": "나카마치 아라레"},
        "yuno": {"name_ko": "센고쿠 유노"},
        "ritsu": {"name_ko": "미네츠키 리츠"},
    }

    now_iso = "2026-08-31T12:00:00Z"

    # 시나리오 1: 첫 실행 가드 — prev 없으면 upcoming 무시
    print("\n[시나리오 1] 첫 실행 가드 — prev 없으면 upcoming 무시")
    print("-" * 70)

    prev_schedule_1 = None
    new_schedule_1 = {
        "generated_at": now_iso,
        "broadcasts": [
            {
                "video_id": "vid1",
                "channel_key": "arale",
                "title": "新春配信",
                "status": "upcoming",
                "scheduled_start": "2026-09-01T13:00:00Z",
                "actual_start": None,
            }
        ],
    }
    newly_ended_1 = []
    sm_log_1 = []

    events_1 = diff_events(
        prev_schedule_1,
        new_schedule_1,
        newly_ended_1,
        sm_log_1,
        channels_cfg,
        now_iso,
    )

    assert len(events_1) == 0, f"첫 실행이므로 upcoming 이벤트 없어야 함, got {len(events_1)}"
    print("✓ 첫 실행 가드 작동: upcoming 이벤트 0개")

    # 시나리오 2: 신규 upcoming → Event 생성
    print("\n[시나리오 2] 신규 upcoming → Event 생성")
    print("-" * 70)

    prev_schedule_2 = {
        "generated_at": "2026-08-31T11:00:00Z",
        "broadcasts": [],
    }
    new_schedule_2 = {
        "generated_at": now_iso,
        "broadcasts": [
            {
                "video_id": "vid2",
                "channel_key": "arale",
                "title": "歌枠 ~まったりお歌~",
                "status": "upcoming",
                "scheduled_start": "2026-09-07T23:45:00Z",
                "actual_start": None,
            }
        ],
    }

    events_2 = diff_events(
        prev_schedule_2,
        new_schedule_2,
        [],
        [],
        channels_cfg,
        now_iso,
    )

    assert len(events_2) == 1, f"upcoming 이벤트 1개 기대, got {len(events_2)}"
    assert events_2[0].kind == "upcoming"
    assert "나카마치 아라레" in events_2[0].text
    assert "歌枠" in events_2[0].text
    print("✓ upcoming 이벤트 생성됨")
    print(f"  {events_2[0].text[:80]}...")

    # 시나리오 3: upcoming → live, 지각 7분 → Event B 생성
    print("\n[시나리오 3] upcoming → live, 지각 7분 → Event B 생성")
    print("-" * 70)

    prev_schedule_3 = {
        "generated_at": "2026-08-31T11:00:00Z",
        "broadcasts": [
            {
                "video_id": "vid3",
                "channel_key": "ritsu",
                "title": "【ASMR】…",
                "status": "upcoming",
                "scheduled_start": "2026-08-31T22:00:00Z",
                "actual_start": None,
            }
        ],
    }
    new_schedule_3 = {
        "generated_at": now_iso,
        "broadcasts": [
            {
                "video_id": "vid3",
                "channel_key": "ritsu",
                "title": "【ASMR】…",
                "status": "live",
                "scheduled_start": "2026-08-31T22:00:00Z",
                "actual_start": "2026-08-31T22:07:00Z",
            }
        ],
    }

    events_3 = diff_events(
        prev_schedule_3,
        new_schedule_3,
        [],
        [],
        channels_cfg,
        now_iso,
    )

    assert len(events_3) == 1
    assert events_3[0].kind == "live_start"
    assert "7분 지각" in events_3[0].text
    print("✓ live_start 이벤트 생성됨 (지각 라벨 포함)")
    print(f"  {events_3[0].text}")

    # 시나리오 4: newly_ended → Event C 생성
    print("\n[시나리오 4] newly_ended → Event C 생성")
    print("-" * 70)

    prev_schedule_4 = {"generated_at": "2026-08-31T11:00:00Z", "broadcasts": []}
    new_schedule_4 = {"generated_at": now_iso, "broadcasts": []}
    newly_ended_4 = [
        {
            "video_id": "vid4",
            "channel_key": "ritsu",
            "title": "【ASMR】…",
            "actual_start": "2026-08-31T22:07:00Z",
            "actual_end": "2026-09-01T00:14:00Z",
            "reason": "ended",
        }
    ]

    events_4 = diff_events(
        prev_schedule_4,
        new_schedule_4,
        newly_ended_4,
        [],
        channels_cfg,
        now_iso,
    )

    assert len(events_4) == 1
    assert events_4[0].kind == "live_end"
    assert "2시간 7분" in events_4[0].text
    assert "정상 종료" in events_4[0].text
    print("✓ live_end 이벤트 생성됨")
    print(f"  {events_4[0].text}")

    # 시나리오 5: sm_log fallback 토큰 → Event E 생성
    print("\n[시나리오 5] sm_log fallback 토큰 → Event E 생성")
    print("-" * 70)

    prev_schedule_5 = {"generated_at": "2026-08-31T11:00:00Z", "broadcasts": []}
    new_schedule_5 = {
        "generated_at": now_iso,
        "broadcasts": [
            {
                "video_id": "vid5",
                "channel_key": "yuno",
                "title": "新春配信",
                "status": "upcoming",
                "scheduled_start": "2026-08-31T22:00:00Z",
                "actual_start": None,
            }
        ],
    }
    sm_log_5 = ["fallback vid5 attempts=3 next=2026-08-31T23:00:00Z"]

    events_5 = diff_events(
        prev_schedule_5,
        new_schedule_5,
        [],
        sm_log_5,
        channels_cfg,
        now_iso,
    )

    assert any(e.kind == "fallback" for e in events_5), "fallback 이벤트 없음"
    fallback_event = [e for e in events_5 if e.kind == "fallback"][0]
    assert "시도 3회" in fallback_event.text
    print("✓ fallback 이벤트 생성됨")
    print(f"  {fallback_event.text}")

    # 시나리오 6: Telegram.send disabled (token/chat_id 없음)
    print("\n[시나리오 6] Telegram.send disabled (token/chat_id 없음)")
    print("-" * 70)

    tg = Telegram("", "")
    result = tg.send("Test message")
    assert result is True, "disabled 상태에서 True 반환해야 함"
    print("✓ Telegram send no-op: True 반환")

    # 시나리오 7: summary_text
    print("\n[시나리오 7] summary_text()")
    print("-" * 70)

    result_dict = {
        "mode": "light",
        "candidates": 78,
        "videos": 78,
        "quota_used": 2,
        "schedule_changed": True,
        "pending_entries": 6,
        "enqueued": 3,
        "enqueue_errors": [],
        "log": [
            "new pre-live vid1",
            "new pre-live vid2",
            "pre-live→live-watch vid3",
        ],
    }

    summary = summary_text(result_dict, now_iso)
    assert "light sync" in summary
    assert "후보 78" in summary
    assert "schedule 변경 O" in summary
    assert "enqueue 3/3" in summary
    print("✓ summary_text 생성됨")
    print(f"  {summary}")

    # 시나리오 8: error_text
    print("\n[시나리오 8] error_text()")
    print("-" * 70)

    exc = RuntimeError("YouTube API error: 403 quotaExceeded")
    error_msg = error_text("/wake video_id=abc123", exc)
    assert "🚨" in error_msg
    assert "RuntimeError" in error_msg
    assert "quotaExceeded" in error_msg
    print("✓ error_text 생성됨")
    print(f"  {error_msg}")

    # 시나리오 9: HTML escape
    print("\n[시나리오 9] HTML escape (제목/오류 텍스트)")
    print("-" * 70)

    dangerous_schedule = {
        "generated_at": "2026-08-31T11:00:00Z",
        "broadcasts": [
            {
                "video_id": "vid9",
                "channel_key": "arale",
                "title": 'Test <script>alert("xss")</script>',
                "status": "upcoming",
                "scheduled_start": "2026-09-01T13:00:00Z",
                "actual_start": None,
            }
        ],
    }
    events_9 = diff_events(
        prev_schedule_2,  # non-first-run
        dangerous_schedule,
        [],
        [],
        channels_cfg,
        now_iso,
    )
    assert any(e.kind == "upcoming" for e in events_9)
    upcoming = [e for e in events_9 if e.kind == "upcoming"][0]
    assert "<script>" not in upcoming.text  # escaped
    assert "&lt;script&gt;" in upcoming.text
    print("✓ HTML escape 작동")

    print("\n" + "=" * 70)
    print("SUCCESS: 모든 9개 스모크 테스트 통과")
    print("=" * 70)
