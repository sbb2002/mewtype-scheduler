"""Telegram webhook 공개 서비스 (haiku #3).

엔트리포인트: src.backend.telegram_app:app
라우트:
  POST /telegram — Telegram webhook
  GET  /         — 헬스체크
"""
from __future__ import annotations

import html
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from flask import Flask, jsonify, request
    _FLASK_AVAILABLE = True
except ImportError:
    _FLASK_AVAILABLE = False
    Flask = None
    jsonify = None
    request = None

try:
    from google.oauth2.id_token import fetch_id_token
    from google.auth.transport.requests import Request
except ImportError:
    fetch_id_token = None
    Request = None

try:
    import requests
except ImportError:
    requests = None

try:
    from .notify import Telegram
except ImportError:
    Telegram = None

try:
    from . import xrelay
except ImportError:
    xrelay = None

try:
    from . import admin
except ImportError:
    admin = None

from .control import (
    LOG_LEVELS,
    default_control,
    get_log_level,
    is_paused,
    set_log_level,
    set_paused,
)
from .gh_store import ConflictError, GitHubStore

# admin_state.json 경로 (v2.5 — /list /del /ingest /undo 수동 관리 명령)
_ADMIN_STATE_PATH = "admin_state.json"
_UNIT_KEYS = ("arale", "yuno", "nonoka", "ritsu", "miyako")
_STATUS_RANK = {"live": 0, "upcoming": 1, "scheduled": 2}
_STATUS_BADGE = {"live": "🔴", "upcoming": "🟢", "scheduled": "🕊"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram_app")

# Flask 앱 생성
if _FLASK_AVAILABLE:
    app = Flask(__name__)
else:
    app = None

# KST 시간대 설정
KST = timezone(timedelta(hours=9))


def _get_kst_now() -> datetime:
    """현재 시각을 KST로 반환."""
    return datetime.now(KST)


def _kst_to_hm(dt: Optional[datetime]) -> Optional[str]:
    """datetime(KST) → "HH:MM" 문자열. None이면 None."""
    if dt is None:
        return None
    return dt.strftime("%H:%M")


def _relative_time(dt_iso: Optional[str], now_iso: Optional[str] = None) -> str:
    """
    ISO 'Z' 문자열(UTC) → 상대시간 라벨 (KST 기준).

    예: "1시간 전", "5분 후", "내일", "3일 뒤"
    """
    if dt_iso is None:
        return "알 수 없음"
    try:
        dt_utc = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
        now_kst = _get_kst_now()
        delta = dt_utc.astimezone(KST) - now_kst

        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            # 과거
            total_seconds = -total_seconds
            if total_seconds < 60:
                return f"{total_seconds}초 전"
            elif total_seconds < 3600:
                return f"{total_seconds // 60}분 전"
            elif total_seconds < 86400:
                return f"{total_seconds // 3600}시간 전"
            else:
                days = total_seconds // 86400
                return f"{days}일 전"
        else:
            # 미래
            if total_seconds < 60:
                return f"{total_seconds}초 후"
            elif total_seconds < 3600:
                return f"{total_seconds // 60}분 후"
            elif total_seconds < 86400:
                return f"{total_seconds // 3600}시간 후"
            else:
                days = total_seconds // 86400
                if days == 1:
                    return "내일"
                else:
                    return f"{days}일 뒤"
    except Exception:
        return "알 수 없음"


def _load_config_dict(gh: GitHubStore, path: str) -> dict:
    """GitHub에서 JSON 파일 로드. 없으면 빈 dict 반환."""
    try:
        data, _ = gh.read_json(path)
        return data if data is not None else {}
    except Exception as e:
        log.warning(f"Failed to load {path}: {e}")
        return {}


def _parse_iso_to_kst(iso_str: Optional[str]) -> Optional[datetime]:
    """ISO 'Z' 문자열 → KST datetime. None이면 None."""
    if iso_str is None:
        return None
    try:
        utc_dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return utc_dt.astimezone(KST)
    except Exception:
        return None


def _sorted_unit_broadcasts(schedule: dict, unit: str) -> list[dict]:
    """schedule['broadcasts'] 중 unit 이 당사자(본인 채널 또는 합동 참여)인 항목,
    상태(live→upcoming→scheduled)·시각순 정렬. (v2.5 /list /del)"""
    broadcasts = schedule.get("broadcasts", []) or []
    items = [
        b for b in broadcasts
        if b.get("channel_key") == unit or unit in (b.get("collab_with") or [])
    ]
    return sorted(
        items,
        key=lambda b: (_STATUS_RANK.get(b.get("status"), 9), b.get("scheduled_start") or ""),
    )


def _time_range_text(b: dict) -> str:
    """방송 1건의 표시용 시간 범위. (v2.5)

    live = "HH:MM~ (진행중)", scheduled = "HH:MM~HH:MM(예상)"(expires_at 기준),
    그 외(upcoming 등, 종료 미정) = "HH:MM~".
    """
    start_hm = _kst_to_hm(_parse_iso_to_kst(b.get("scheduled_start"))) or "?"
    status = b.get("status")
    if status == "live":
        return f"{start_hm}~ (진행중)"
    if status == "scheduled":
        end_hm = _kst_to_hm(_parse_iso_to_kst(b.get("expires_at")))
        if end_hm:
            return f"{start_hm}~{end_hm}(예상)"
    return f"{start_hm}~"


def _format_list_text(channels_cfg: dict, schedule: dict, unit: str = "") -> str:
    """/list 응답 본문. unit 비우면 5채널 전체. (v2.5)"""
    chan = channels_cfg.get("channels", {})
    units = [unit] if unit else list(_UNIT_KEYS)
    blocks = []
    for u in units:
        name = chan.get(u, {}).get("name_ko", u)
        lines = [f"<b>{name}</b> ({u})"]
        items = _sorted_unit_broadcasts(schedule, u)
        if not items:
            lines.append("· (없음)")
        else:
            for i, b in enumerate(items, start=1):
                badge = _STATUS_BADGE.get(b.get("status"), "❔")
                title = (b.get("title") or xrelay.KIND_KO.get(b.get("kind"), "")) if xrelay else (b.get("title") or "")
                title_part = f" 「{title[:20]}」" if title else ""
                collab_part = " (합동)" if b.get("host") == "group" else ""
                lines.append(f"#{i} {badge} {_time_range_text(b)}{title_part}{collab_part}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _save_undo(gh: GitHubStore, *, action: str, prev_content: dict, new_sha, now_iso: str) -> None:
    """schedule.json 을 바꾼 직후 admin_state.json 에 undo 스냅샷 기록. 실패해도 본 작업은 막지 않음."""
    if admin is None:
        return
    try:
        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = admin.set_undo(
            state or admin.default_admin_state(),
            action=action, prev_content=prev_content, new_sha=new_sha, now_iso=now_iso,
        )
        gh.write_json(
            _ADMIN_STATE_PATH, state, prev_sha=sha,
            message=f"data: undo snapshot ({action}) {now_iso}",
        )
    except Exception:
        log.exception("undo 스냅샷 저장 실패 (무시 — /undo 만 이번 건 불가해짐)")


def _build_status_text(
    now_iso: str,
    gh: GitHubStore,
    channels_cfg: dict,
) -> str:
    """
    /status 명령 응답 본문 생성.

    상태: 🟢 정상   (또는  ⏸ 일시정지 (12분째))
    마지막 sync: 21:00 (12분 전)
    라이브: 1 — 리츠 「ASMR…」 22:07~
    예정: 오늘 2 · 이번주 1 · 이후 3
    대기 wake: 6건 · 다음 22:45
    """
    now_kst = _get_kst_now()
    now_date = now_kst.date()

    # 1. schedule.json, pending.json, control.json 로드
    schedule = _load_config_dict(gh, "schedule.json")
    pending = _load_config_dict(gh, "pending.json")
    control = _load_config_dict(gh, "control.json") or default_control()

    broadcasts = schedule.get("broadcasts", [])
    generated_at = schedule.get("generated_at")
    entries = pending.get("entries", {}) or {}

    # 2. 상태 라인
    if is_paused(control):
        since_iso = control.get("since")
        since_kst = _parse_iso_to_kst(since_iso)
        elapsed = ""
        if since_kst:
            delta = now_kst - since_kst
            mins = int(delta.total_seconds() / 60)
            if mins < 60:
                elapsed = f" ({mins}분째)"
            else:
                hours = mins // 60
                elapsed = f" ({hours}시간 {mins % 60}분째)"
        status_line = f"상태: ⏸ 일시정지{elapsed}"
    else:
        status_line = "상태: 🟢 정상"
    status_line += f"  ·  로그 {get_log_level(control)}"

    # 3. 마지막 sync
    last_sync = ""
    if generated_at:
        gen_kst = _parse_iso_to_kst(generated_at)
        if gen_kst:
            hm = _kst_to_hm(gen_kst)
            rel = _relative_time(generated_at, now_iso)
            last_sync = f"마지막 sync: {hm} ({rel})"

    # 4. 라이브 (status=="live")
    live_text = ""
    live_broadcasts = [b for b in broadcasts if b.get("status") == "live"]
    if live_broadcasts:
        live_items = []
        for b in live_broadcasts:
            ch_key = b.get("channel_key")
            ch_name = channels_cfg.get("channels", {}).get(ch_key, {}).get("name_ko", ch_key)
            title = b.get("title", "제목 없음")[:20]  # 길이 제한
            actual_start = b.get("actual_start")
            if actual_start:
                start_kst = _parse_iso_to_kst(actual_start)
                if start_kst:
                    start_hm = _kst_to_hm(start_kst)
                    live_items.append(f"{ch_name} 「{title}…」 {start_hm}~")
        if live_items:
            live_text = "라이브: " + " · ".join(live_items)

    # 5. 예정 (status=="upcoming")
    upcoming_broadcasts = [b for b in broadcasts if b.get("status") == "upcoming"]
    today_count = 0
    week_count = 0
    later_count = 0
    for b in upcoming_broadcasts:
        ss_iso = b.get("scheduled_start")
        if ss_iso:
            ss_kst = _parse_iso_to_kst(ss_iso)
            if ss_kst:
                ss_date = ss_kst.date()
                delta_days = (ss_date - now_date).days
                if delta_days == 0:  # 오늘
                    today_count += 1
                elif 0 < delta_days < 7:  # 이번주
                    week_count += 1
                else:  # 이후
                    later_count += 1

    upcoming_text = f"예정: 오늘 {today_count} · 이번주 {week_count} · 이후 {later_count}"

    # 6. 대기 wake (entries는 dict)
    wake_text = ""
    if entries:
        next_check_times = []
        for video_id, entry in entries.items():
            nca = entry.get("next_check_at")
            if nca:
                nca_kst = _parse_iso_to_kst(nca)
                if nca_kst:
                    next_check_times.append(nca_kst)
        if next_check_times:
            next_check_times.sort()
            next_hm = _kst_to_hm(next_check_times[0])
            wake_text = f"대기 wake: {len(entries)}건 · 다음 {next_hm}"
        else:
            wake_text = f"대기 wake: {len(entries)}건"
    else:
        wake_text = "대기 wake: 없음"

    # 7. 결합
    lines = [status_line]
    if last_sync:
        lines.append(last_sync)
    if live_text:
        lines.append(live_text)
    lines.append(upcoming_text)
    lines.append(wake_text)

    return "\n".join(lines)


def _send_telegram(text: str, silent: bool = False) -> bool:
    """Telegram으로 메시지 전송."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        log.warning("Telegram not configured (BOT_TOKEN or CHAT_ID missing)")
        return False

    if Telegram is None:
        log.warning("Telegram class not available")
        return False

    tg = Telegram(bot_token, chat_id)
    return tg.send(text, parse_mode="HTML", silent=silent)


# /status 두 번째 메시지 — 첫 메시지(_build_status_text)에 나오는 용어 풀이.
_STATUS_GLOSSARY = (
    "📖 <b>/status 필드</b>\n"
    "· <b>상태</b> — 🟢 정상 / ⏸ 일시정지 (/pause 로 멈춤, 괄호는 경과 시간). "
    "정지 중엔 tick·wake 가 no-op\n"
    "· <b>로그</b> — 현재 Telegram 알림 레벨 (/log 로 변경)\n"
    "· <b>마지막 sync</b> — 백엔드가 schedule.json 을 마지막으로 재구성한 시각 "
    "(schedule.generated_at). 괄호는 지금으로부터 경과\n"
    "· <b>라이브</b> — 지금 방송 중인 항목. 「제목」 뒤 시각은 실제 시작 시각\n"
    "· <b>예정</b> — upcoming 방송 수. <b>오늘</b>=KST 같은 날 · <b>이번주</b>=1~6일 뒤 · "
    "<b>이후</b>=7일 이상 뒤\n"
    "· <b>대기 wake</b> — Cloud Tasks 에 예약된 방송별 상태확인 건수 (pre-live + live-watch). "
    "<b>다음</b>=가장 이른 재확인 시각\n"
    "\n"
    "🔧 <b>로그 레벨</b> (/log 로 변경)\n"
    "· <b>detail</b> — 전이 + fallback/오류 + 매 실행 sync 요약\n"
    "· <b>normal</b> — 전이 + fallback/오류 (sync 요약 없음) · 기본값\n"
    "· <b>simple</b> — fallback/오류만"
)


def _handle_status(gh: GitHubStore, channels_cfg: dict, now_iso: str) -> None:
    """/status 명령 처리. 상태 요약 + 용어집 2개 메시지."""
    try:
        text = _build_status_text(now_iso, gh, channels_cfg)
        _send_telegram(text)
        _send_telegram(_STATUS_GLOSSARY, silent=True)
    except Exception as e:
        log.exception("Error handling /status")
        _send_telegram(f"⚠️ 오류: /status 처리 실패\n{str(e)[:100]}")


_LOG_LEVEL_DESC = {
    "detail": "모든 알림 + 매 실행 sync 요약",
    "normal": "전이(예정/시작/종료) + fallback/오류. sync 요약 없음",
    "simple": "fallback/오류만",
}


def _handle_log(gh: GitHubStore, now_iso: str, arg: str) -> None:
    """/log [detail|normal|simple] — 인자 없으면 현재 레벨 표시."""
    try:
        control, _ = gh.read_json("control.json")
        if control is None:
            control = default_control()

        if not arg:
            cur = get_log_level(control)
            lines = [f"현재 로그 레벨: <b>{cur}</b> — {_LOG_LEVEL_DESC[cur]}", "", "변경: /log &lt;레벨&gt;"]
            lines += [f"· {lv} — {_LOG_LEVEL_DESC[lv]}" for lv in LOG_LEVELS]
            _send_telegram("\n".join(lines))
            return

        if arg not in LOG_LEVELS:
            _send_telegram(f"⚠️ 알 수 없는 레벨: {arg}\n택: {', '.join(LOG_LEVELS)}")
            return

        control = set_log_level(control, arg, by="telegram:/log", now_iso=now_iso)
        gh.write_json(
            "control.json", control, prev_sha=None,
            message=f"data: log_level={arg} via Telegram /log {now_iso}",
        )
        _send_telegram(f"🔧 로그 레벨 → <b>{arg}</b>\n{_LOG_LEVEL_DESC[arg]}")
    except Exception as e:
        log.exception("Error handling /log")
        _send_telegram(f"⚠️ 오류: /log 처리 실패\n{str(e)[:100]}")


def _handle_pause(gh: GitHubStore, now_iso: str) -> None:
    """
    /pause 명령 처리.
    """
    try:
        control, _ = gh.read_json("control.json")
        if control is None:
            control = default_control()

        control = set_paused(control, True, by="telegram:/pause", now_iso=now_iso)
        changed, _ = gh.write_json(
            "control.json",
            control,
            prev_sha=None,
            message=f"data: pause via Telegram /pause {now_iso}",
        )

        if changed:
            _send_telegram("⏸ 일시정지됨. /resume 으로 재개하세요.")
        else:
            log.info("Control not changed (already paused?)")
            _send_telegram("⏸ 이미 일시정지 상태입니다.")
    except Exception as e:
        log.exception("Error handling /pause")
        _send_telegram(f"⚠️ 오류: /pause 처리 실패\n{str(e)[:100]}")


def _handle_resume(gh: GitHubStore, now_iso: str, main_service_url: str) -> None:
    """
    /resume 명령 처리.
    1. control 업데이트 (paused=False)
    2. 회신 1: "▶️ 재개. 동기화 중…"
    3. OIDC로 메인 /tick 호출
    4. 회신 2: "▶️ 완료. pending {n}건, enqueue {m}건."
    """
    try:
        # 1. control 업데이트
        control, _ = gh.read_json("control.json")
        if control is None:
            control = default_control()

        control = set_paused(control, False, by="telegram:/resume", now_iso=now_iso)
        changed, _ = gh.write_json(
            "control.json",
            control,
            prev_sha=None,
            message=f"data: resume via Telegram /resume {now_iso}",
        )

        # 2. 회신 1
        _send_telegram("▶️ 재개. 동기화 중…")

        # 3. OIDC 토큰 발급 및 메인 /tick 호출
        tick_result = None
        if fetch_id_token and Request and requests and main_service_url:
            try:
                tok = fetch_id_token(Request(), main_service_url)
                resp = requests.post(
                    f"{main_service_url}/tick",
                    json={"mode": "light"},
                    headers={"Authorization": f"Bearer {tok}"},
                    timeout=30,
                )
                if resp.status_code == 200:
                    tick_result = resp.json()
                    log.info(f"Tick succeeded: {tick_result}")
                else:
                    log.warning(f"Tick failed: {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                log.exception(f"Failed to call /tick: {e}")
        else:
            log.warning("google-auth, requests not available, or MAIN_SERVICE_URL not set")

        # 4. 회신 2
        if tick_result:
            pending_count = tick_result.get("pending_entries", 0)
            enqueue_count = tick_result.get("enqueued", 0)
            _send_telegram(f"▶️ 완료. pending {pending_count}건, enqueue {enqueue_count}건.")
        else:
            _send_telegram("▶️ 재개 완료 (동기화 상태 확인 불가).")

    except Exception as e:
        log.exception("Error handling /resume")
        _send_telegram(f"⚠️ 오류: /resume 처리 실패\n{str(e)[:100]}")


def _load_channels_config() -> dict:
    """config/channels.json 로드."""
    try:
        with open("config/channels.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Failed to load config/channels.json: {e}")
        return {"channels": {}}


def _make_gh() -> "GitHubStore | None":
    """env 에서 GitHubStore 구성. 필수 값 없으면 None."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip()
    branch = os.environ.get("DATA_BRANCH", "data").strip() or "data"
    if not token or not repo:
        return None
    return GitHubStore(token, repo, branch)


# ── ingest 대기열 (ECHO/DRY-RUN 중 받은 스케줄 트윗을 실배포 전환 시 반영) ──
_INGEST_QUEUE_PATH = "ingest_queue.json"
_INGEST_QUEUE_MAX = 30       # data 브랜치 파일 비대 방지 (일일 트윗이라 넉넉)
_INGEST_RAW_CAP = 8000       # 저장 원문 상한


def _merge_rows_into_schedule(gh, rows, now_iso, message, action: str | None = None) -> bool:
    """rows 를 merge_scheduled 로 schedule.json 에 반영 (base-sha 충돌 시 1회 재시도).

    실제로 변경됐으면 admin_state.json 에 undo 스냅샷을 남긴다(v2.5, `action` 없으면 `message` 사용).
    """
    changed = False
    prev = new_sha = None
    for attempt in (1, 2):
        prev, sha = gh.read_json("schedule.json")
        merged = xrelay.merge_scheduled(prev or {}, rows, now_iso)
        try:
            changed, new_sha = gh.write_json("schedule.json", merged, prev_sha=sha, message=message)
            break
        except ConflictError:
            if attempt == 2:
                raise
            log.warning("ingest: schedule.json 충돌 — 재계산 후 재시도")
    if changed:
        _save_undo(gh, action=action or message, prev_content=prev or {}, new_sha=new_sha, now_iso=now_iso)
    return changed


def _remove_broadcast(gh, snapshot: dict, now_iso: str, action: str) -> bool:
    """snapshot 과 정확히 일치하는 broadcasts[] 항목 1개를 제거 (v2.5 /del).

    그 사이 항목이 바뀌었거나 이미 없으면(다른 실행이 먼저 건드림) False — 아무것도 안 지운다.
    base-sha 충돌 시 1회 재시도.
    """
    changed = False
    prev = new_sha = None
    for attempt in (1, 2):
        prev, sha = gh.read_json("schedule.json")
        prev = prev or {}
        broadcasts = prev.get("broadcasts", []) or []
        match_i = next((i for i, b in enumerate(broadcasts) if b == snapshot), None)
        if match_i is None:
            return False
        new_sched = dict(prev)
        new_sched["broadcasts"] = broadcasts[:match_i] + broadcasts[match_i + 1:]
        new_sched["generated_at"] = now_iso
        try:
            changed, new_sha = gh.write_json("schedule.json", new_sched, prev_sha=sha, message=f"data: {action} {now_iso}")
            break
        except ConflictError:
            if attempt == 2:
                raise
            log.warning("del: schedule.json 충돌 — 재계산 후 재시도")
    if changed:
        _save_undo(gh, action=action, prev_content=prev, new_sha=new_sha, now_iso=now_iso)
    return changed


def _ingest_queue_push(gh, raw: str, title: str, now_iso: str) -> None:
    """ECHO/DRY-RUN 중 받은 스케줄 트윗 원문을 data 브랜치 큐에 적재.

    실배포(`INGEST_ECHO=0` + `INGEST_DRY_RUN=0`) 전환 후 첫 `/ingest` 에서
    `_ingest_queue_drain` 이 순서대로 파싱·머지한다 → 테스트 기간에 온 트윗도 유실 없이 반영.
    큐 실패는 ECHO/DRY-RUN 응답을 막지 않는다(best-effort).
    """
    try:
        q, sha = gh.read_json(_INGEST_QUEUE_PATH)
        pending = list((q or {}).get("pending", []))
        clipped = raw[:_INGEST_RAW_CAP]
        if pending and pending[-1].get("raw") == clipped:
            return  # 폰 재시도 등 직전과 동일 원문 → 스킵
        pending.append({"raw": clipped, "title": title, "received_at": now_iso})
        gh.write_json(
            _INGEST_QUEUE_PATH, {"pending": pending[-_INGEST_QUEUE_MAX:]},
            prev_sha=sha, message=f"data: ingest queue += {now_iso}",
        )
    except Exception:
        log.exception("ingest queue push 실패 (무시)")


def _ingest_queue_drain(gh, now_iso: str) -> tuple[int, int]:
    """큐의 원문을 순서대로 파싱·머지하고 큐를 비운다. (반영 건수, 총 파싱행수)."""
    try:
        q, sha = gh.read_json(_INGEST_QUEUE_PATH)
    except Exception:
        log.exception("ingest queue read 실패")
        return 0, 0
    items = (q or {}).get("pending", [])
    if not items:
        return 0, 0
    applied = total_rows = 0
    for it in items:
        rows = xrelay.parse(it.get("raw", ""), it.get("received_at") or now_iso)
        if not rows:
            continue
        _merge_rows_into_schedule(
            gh, rows, now_iso, message=f"data: xrelay queued {it.get('received_at')}"
        )
        applied += 1
        total_rows += len(rows)
    try:
        gh.write_json(
            _INGEST_QUEUE_PATH, {"pending": []},
            prev_sha=sha, message=f"data: ingest queue drained ({applied}) {now_iso}",
        )
    except Exception:
        log.exception("ingest queue clear 실패 (다음 ingest 에서 재시도)")
    return applied, total_rows


# ── v2.5 수동 관리 명령: /list /del /ingest(=/add) /undo ────────────────

def _handle_list(gh, channels_cfg: dict, arg: str) -> None:
    """/list [unit] — 현재 리스트업된 방송을 유닛별 idx 로 보여줌."""
    try:
        unit = arg.strip().lower()
        if unit and unit not in _UNIT_KEYS:
            _send_telegram(f"⚠️ 알 수 없는 유닛: {unit}\n택: {', '.join(_UNIT_KEYS)} (생략 시 전체)")
            return
        schedule = _load_config_dict(gh, "schedule.json")
        text = _format_list_text(channels_cfg, schedule, unit)
        _send_telegram(text or "(방송 없음)")
    except Exception as e:
        log.exception("Error handling /list")
        _send_telegram(f"⚠️ 오류: /list 처리 실패\n{str(e)[:100]}")


def _handle_del_request(gh, channels_cfg: dict, now_iso: str, unit_arg: str, idx_arg: str) -> None:
    """/del <unit> <idx> — 삭제 확인 대기 상태로 등록 + 경고 DM(y/N 대기)."""
    try:
        unit = (unit_arg or "").strip().lower()
        if unit not in _UNIT_KEYS:
            _send_telegram(f"⚠️ 사용법: /del <유닛> <번호>\n유닛: {', '.join(_UNIT_KEYS)} (번호는 /list 로 확인)")
            return
        try:
            idx = int((idx_arg or "").strip())
        except ValueError:
            _send_telegram("⚠️ 사용법: /del <유닛> <번호>  (번호는 /list 로 확인)")
            return

        schedule = _load_config_dict(gh, "schedule.json")
        items = _sorted_unit_broadcasts(schedule, unit)
        if idx < 1 or idx > len(items):
            _send_telegram(f"⚠️ {unit} 에 #{idx} 항목이 없습니다. /list {unit} 로 확인하세요.")
            return
        b = items[idx - 1]
        name = channels_cfg.get("channels", {}).get(unit, {}).get("name_ko", unit)

        warn = f"#{idx} {name}의 {_time_range_text(b)} 방송예고를 내리시겠습니까?"  # warn_deltry
        if b.get("status") in ("upcoming", "live"):
            warn += "\n해당 예고는 감지기능으로 다시 되살아날 수 있습니다."          # warn_live
        warn += "\n그래도 지우시겠습니까? (y/N)"

        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = admin.set_pending_del(
            state or admin.default_admin_state(),
            unit=unit, idx=idx, snapshot=b, warn_text=warn, now_iso=now_iso,
        )
        gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: /del 확인대기 {unit}#{idx} {now_iso}")
        _send_telegram(warn)
    except Exception as e:
        log.exception("Error handling /del")
        _send_telegram(f"⚠️ 오류: /del 처리 실패\n{str(e)[:100]}")


def _handle_del_confirm(gh, now_iso: str, yes: bool) -> None:
    """대기 중인 /del 요청에 대한 (y/N) 답변 처리."""
    try:
        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = state or admin.default_admin_state()
        pending = admin.get_pending_del(state)
        if not pending or admin.pending_del_expired(pending, now_iso):
            state = admin.clear_pending_del(state)
            gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: /del 대기 정리(만료) {now_iso}")
            _send_telegram("⌛ 대기 중인 삭제 요청이 없습니다(만료됨). /del 로 다시 시도하세요.")
            return

        if not yes:
            state = admin.clear_pending_del(state)
            gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: /del 취소 {now_iso}")
            _send_telegram("↩️ 취소했습니다.")
            return

        unit, idx, snapshot = pending["unit"], pending["idx"], pending["snapshot"]
        action = f"/del {unit}#{idx}"
        removed = _remove_broadcast(gh, snapshot, now_iso, action)

        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = admin.clear_pending_del(state or admin.default_admin_state())
        gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: /del 완료 {now_iso}")

        if removed:
            _send_telegram(f"🗑 {action} 반영됨. /undo 로 되돌릴 수 있습니다.")
        else:
            _send_telegram(f"⚠️ {action} 실패 — 그 사이 항목이 바뀌거나 사라졌습니다. /list 로 확인하세요.")
    except Exception as e:
        log.exception("Error handling /del confirm")
        _send_telegram(f"⚠️ 오류: /del 확인 처리 실패\n{str(e)[:100]}")


def _handle_manual_ingest(gh, channels_cfg: dict, now_iso: str, raw: str) -> None:
    """/ingest <트윗 원문>(=/add) — 폰 자동 릴레이와 동일 파싱·반영 경로를 수동으로 실행."""
    try:
        if xrelay is None:
            _send_telegram("⚠️ xrelay 모듈을 불러올 수 없습니다.")
            return
        control, _ = gh.read_json("control.json")
        if is_paused(control or default_control()):
            _send_telegram("⏸ 일시정지 중 — /ingest 무시", silent=True)
            return

        drained, drained_rows = _ingest_queue_drain(gh, now_iso)
        rows = xrelay.parse(raw, now_iso)
        if not rows:
            msg = "ℹ️ /ingest: 스케줄/출연 형식 아님 — 무시\n" + raw[:200]
            if drained:
                msg += f"\n📥 대기열 {drained}건({drained_rows}행) 반영됨"
            _send_telegram(msg, silent=not drained)
            return

        changed = _merge_rows_into_schedule(
            gh, rows, now_iso,
            message=f"data: telegram /ingest {now_iso}",
            action=f"/ingest {raw[:40].strip()}",
        )
        channels_cfg = channels_cfg or _load_channels_config()
        summary = xrelay.summary_text(rows, channels_cfg)
        if drained:
            summary += f"\n\n📥 대기열 {drained}건({drained_rows}행)도 함께 반영"
        if changed:
            summary += "\n\n↩️ /undo 로 되돌릴 수 있습니다."
        _send_telegram(summary)
    except Exception as e:
        log.exception("Error handling manual /ingest")
        _send_telegram(f"⚠️ 오류: /ingest 처리 실패\n{str(e)[:100]}")


def _handle_undo(gh, now_iso: str) -> None:
    """/undo — 이 봇을 통해 방금 수행된 schedule.json 변경(ingest·/del) 1건을 되돌림.

    그 사이 정기 `/tick` 등으로 schedule.json 이 또 바뀌었으면(SHA 불일치) 안전하게 거부.
    """
    try:
        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = state or admin.default_admin_state()
        undo = admin.get_undo(state)
        if not undo:
            _send_telegram("↩️ 되돌릴 작업이 없습니다.")
            return

        cur, cur_sha = gh.read_json("schedule.json")
        if cur_sha != undo.get("new_sha"):
            state = admin.clear_undo(state)
            gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: undo 슬롯 정리(만료) {now_iso}")
            _send_telegram(
                "↩️ 되돌리기 불가 — 그 사이 스케줄이 갱신됐습니다(정기 동기화 등).\n"
                "/list 로 현재 상태를 확인한 뒤 /del 로 수동 처리하세요."
            )
            return

        gh.write_json(
            "schedule.json", undo["prev_content"], prev_sha=cur_sha,
            message=f"data: undo({undo.get('action')}) {now_iso}",
        )
        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = admin.clear_undo(state or admin.default_admin_state())
        gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: undo 슬롯 정리 {now_iso}")
        _send_telegram(f"↩️ 되돌림 — {undo.get('action')}")
    except Exception as e:
        log.exception("Error handling /undo")
        _send_telegram(f"⚠️ 오류: /undo 처리 실패\n{str(e)[:100]}")


# Flask 라우트 정의 (Flask 설치 시만)
if _FLASK_AVAILABLE:

    @app.post("/telegram")
    def _telegram_webhook():
        """Telegram webhook 엔드포인트."""
        # 1. 헤더 검증
        webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
        received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "").strip()

        if webhook_secret and received_secret != webhook_secret:
            log.warning(f"Invalid webhook secret")
            return jsonify({"ok": False}), 200  # 항상 200

        # 2. chat_id 검증
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        body = request.get_json(silent=True) or {}
        message = body.get("message", {})
        msg_chat_id = str(message.get("chat", {}).get("id", ""))

        if chat_id and msg_chat_id != chat_id:
            log.warning(f"Invalid chat_id: {msg_chat_id} != {chat_id}")
            return jsonify({"ok": False}), 200  # 항상 200

        # 3. 명령 파싱
        text = (message.get("text") or "").strip()
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            # GitHub 저장소 초기화
            gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
            gh_repo = os.environ.get("GITHUB_REPO", "").strip()
            gh_branch = os.environ.get("DATA_BRANCH", "data").strip() or "data"

            if not gh_token or not gh_repo:
                log.warning("GitHub config missing")
                _send_telegram("⚠️ GitHub 설정 누락")
                return jsonify({"ok": False}), 200

            gh = GitHubStore(gh_token, gh_repo, gh_branch)
            channels_cfg = _load_channels_config()

            # v2.5: 대기 중인 /del 확인(y/N) 이 있으면 명령 디스패치보다 먼저 처리.
            # admin_state.json 읽기 실패는 일반 명령 처리를 막지 않는다(무시하고 통과).
            if admin is not None:
                try:
                    _admin_state, _ = gh.read_json(_ADMIN_STATE_PATH)
                    _pending = admin.get_pending_del(_admin_state)
                except Exception:
                    log.warning("admin_state.json 조회 실패 — /del 확인 스킵하고 일반 명령으로 처리")
                    _pending = None
                _low = text.strip().lower()
                if _pending and not admin.pending_del_expired(_pending, now_utc) and _low in ("y", "yes", "n", "no"):
                    _handle_del_confirm(gh, now_utc, yes=_low in ("y", "yes"))
                    return jsonify({"ok": True}), 200

            # 명령 디스패치 ("/log detail" 처럼 인자 포함 가능)
            cmd, _, arg = text.partition(" ")
            arg = arg.strip()
            if cmd == "/status":
                _handle_status(gh, channels_cfg, now_utc)
            elif cmd == "/pause":
                _handle_pause(gh, now_utc)
            elif cmd == "/resume":
                main_service_url = os.environ.get("MAIN_SERVICE_URL", "").strip()
                if not main_service_url:
                    _send_telegram("⚠️ MAIN_SERVICE_URL 미설정")
                else:
                    _handle_resume(gh, now_utc, main_service_url)
            elif cmd == "/log":
                _handle_log(gh, now_utc, arg)
            elif cmd == "/list":
                _handle_list(gh, channels_cfg, arg)
            elif cmd == "/del":
                parts = arg.split()
                _unit = parts[0] if len(parts) >= 1 else ""
                _idx = parts[1] if len(parts) >= 2 else ""
                _handle_del_request(gh, channels_cfg, now_utc, _unit, _idx)
            elif cmd in ("/ingest", "/add"):
                if not arg:
                    _send_telegram(f"⚠️ 사용법: {cmd} <트윗 원문>")
                else:
                    _handle_manual_ingest(gh, channels_cfg, now_utc, arg)
            elif cmd == "/undo":
                _handle_undo(gh, now_utc)
            else:
                # 도움말
                help_text = (
                    "<b>📱 mewtype 텔레그램 봇</b>\n\n"
                    "명령:\n"
                    "/status — 현재 상태 조회\n"
                    "/pause — 수집 일시정지\n"
                    "/resume — 수집 재개\n"
                    "/log [detail|normal|simple] — 알림 상세도\n"
                    "/list [유닛] — 방송 목록 (유닛: arale/yuno/nonoka/ritsu/miyako, 생략 시 전체)\n"
                    "/del &lt;유닛&gt; &lt;번호&gt; — 목록의 항목을 내림 (확인 y/N 필요)\n"
                    "/ingest &lt;트윗 원문&gt; — 트윗 텍스트를 붙여넣어 수동 반영\n"
                    "/undo — 방금 한 작업(/ingest, /del) 되돌리기"
                )
                _send_telegram(help_text)

        except Exception as e:
            log.exception("Webhook processing error")
            _send_telegram(f"⚠️ 처리 오류: {str(e)[:100]}")

        # 항상 200 반환 (Telegram 재시도 방지)
        return jsonify({"ok": True}), 200

    @app.post("/ingest")
    def _ingest():
        """Automate(폰) → 삼성 브라우저 웹푸시 알림 텍스트 인입 (v2.3 X 릴레이).

        인증: `X-Ingest-Secret` 헤더 == env `INGEST_SECRET`.
        본문: form 또는 JSON 의 `text`(필수) / `title`(선택, dry-run 에코용).
        `@BDP_yumemita` 일일 스케줄 트윗만 파싱 → `schedule.json` 의 `scheduled` 행으로 머지.
        형식이 아니거나 일시정지 중이면 no-op. 결과는 운영자 DM 으로 회신(계약 G).

        `INGEST_DRY_RUN` env 가 참이면: **저장 안 하고** 받은 원문 + 파싱 결과만
        DM 으로 회신 (푸시 알림이 "Show more" 로 잘리는지 확인용).
        `INGEST_ECHO` env 가 참이면: 파싱조차 안 하고 받은 텍스트 그대로만 DM 회신
        (임시 테스트 훅 — 아래 해당 블록 주석 참고).
        """
        secret = os.environ.get("INGEST_SECRET", "").strip()
        got = request.headers.get("X-Ingest-Secret", "").strip()
        if not secret or got != secret:
            log.warning("ingest: bad or missing secret")
            return jsonify({"ok": False}), 403

        payload = request.form if request.form else (request.get_json(silent=True) or {})
        raw = (payload.get("text") or "").strip()
        title = (payload.get("title") or "").strip()

        # 폰 Automate 빌드가 `urlEncode({"text": expr})` 를 `<expr값>=` 로 만들어버린다
        # (트윗 본문이 값이 아니라 폼 키 자리로 샌다). text 값이 비었는데 정체불명 키가
        # 딱 하나 있고 그 값도 비어 있으면, 그 키 이름을 원문으로 간주한다.
        # ponytail: Automate 빌드 특유의 urlEncode 딕셔너리 버그 우회. 폰에서 body 를
        #           `"text=" ++ urlEncode(...)` 로 제대로 보낼 수 있게 되면 이 블록 삭제.
        if not raw and request.form:
            odd = [k for k in request.form.keys() if k not in ("text", "title")]
            if len(odd) == 1 and not (request.form.get(odd[0]) or "").strip():
                raw = odd[0].strip()

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ─── v2.3 임시 ECHO 테스트 훅 (INGEST_ECHO 가 참일 때만) ───────────────
        # 폰 Automate 가 `@BDP_yumemita` 푸시알림을 키워드 필터 없이 그대로 relay 할 때,
        # 백엔드 처리(파싱·저장) 전혀 없이 "들어온 텍스트 그대로"만 DM 으로 회신한다.
        # 웹푸시 본문이 온전히/잘려서/비어서 오는지 확인용.
        # 확인 끝나면 env 에서 INGEST_ECHO 만 내리면 아래 실제 로직으로 복귀.
        # (이 블록 자체를 지워도 무방 — 나머지 로직은 이 블록에 의존하지 않음.)
        if os.environ.get("INGEST_ECHO", "").strip() not in ("", "0", "false", "False", "no"):
            body_preview = request.get_data(as_text=True)[:1000]
            # 잘림 판정용 계측 — DM 없이 Cloud Run 로그만으로도 확인 가능해야.
            #   tail_ok = 트윗 말미 고정 문구가 왔는가 (오면 본문이 안 잘린 것)
            tail_ok = "予告なく変更" in raw or "時刻は予告" in raw
            log.warning(
                "ingest ECHO: len=%d clen=%s tail_ok=%s ct=%r form_keys=%r "
                "head=%r tail=%r",
                len(raw), request.content_length, tail_ok, request.content_type,
                list(request.form.keys()), raw[:120], raw[-120:],
            )
            _send_telegram(
                "📡 <b>ingest ECHO</b> — 백엔드 처리 안 함\n"
                f"ct=<code>{html.escape(request.content_type or '-')}</code> · "
                f"form_keys={list(request.form.keys())}\n"
                f"title=<code>{html.escape(title) or '(없음)'}</code>\n"
                f"len(text)={len(raw)} · 말미문구 {'✅' if tail_ok else '❌'}\n"
                "───── text ─────\n"
                f"<code>{html.escape(raw) if raw else '(빈 text)'}</code>\n"
                "───── raw body[:1000] ─────\n"
                f"<code>{html.escape(body_preview)}</code>"
            )
            # 스케줄 트윗이면 큐에 적재 — 실배포 전환 시 반영되도록 (유실 방지).
            if raw and xrelay is not None and xrelay.looks_relayable(raw):
                _gh = _make_gh()
                if _gh is not None:
                    _ingest_queue_push(_gh, raw, title, now_iso)
            return jsonify({"ok": True, "echo": True, "len": len(raw), "tail_ok": tail_ok}), 200
        # ─────────────────────────────────────────────────────────────────────

        if not raw:
            # 폰(Automate)이 text 를 빈 값으로 보내는 원인 추적용 계측.
            log.warning(
                "ingest empty text: ct=%r len=%s form_keys=%r json=%r body[:800]=%r",
                request.content_type,
                request.content_length,
                list(request.form.keys()),
                request.get_json(silent=True),
                request.get_data(as_text=True)[:800],
            )
            return jsonify({"ok": False, "error": "empty text"}), 400
        if xrelay is None:
            return jsonify({"ok": False, "error": "xrelay unavailable"}), 500

        dry = os.environ.get("INGEST_DRY_RUN", "").strip() not in ("", "0", "false", "False", "no")

        try:
            channels_cfg = _load_channels_config()
            rows = xrelay.parse(raw, now_iso)

            if dry:
                cut = 3500
                body = raw if len(raw) <= cut else raw[:cut] + "\n…(len 초과 잘림)"
                brief = " / ".join(
                    f"{r['channel_key']} {xrelay._jst_hm(r['scheduled_start'])}(JST)"
                    f"{'🔒' if r['members_only'] else ''}"
                    for r in rows
                ) or "(파싱 0건)"
                _send_telegram(
                    "🧪 <b>ingest DRY-RUN</b> — 저장 안 함\n"
                    f"title: <code>{html.escape(title) or '(없음)'}</code>\n"
                    f"len(text)={len(raw)} · 파싱 {len(rows)}건\n"
                    f"{html.escape(brief)}\n"
                    "─────\n"
                    f"<code>{html.escape(body)}</code>"
                )
                if xrelay is not None and xrelay.looks_relayable(raw):
                    _gh = _make_gh()
                    if _gh is not None:
                        _ingest_queue_push(_gh, raw, title, now_iso)
                return jsonify({"ok": True, "dry_run": True, "parsed": len(rows)}), 200

            gh = _make_gh()
            if gh is None:
                _send_telegram("⚠️ ingest: GitHub 설정 누락")
                return jsonify({"ok": False, "error": "gh config"}), 200

            control, _ = gh.read_json("control.json")
            if is_paused(control or default_control()):
                log.info("ingest: paused — skip")
                _send_telegram("⏸ 일시정지 중 — ingest 무시", silent=True)
                return jsonify({"ok": True, "paused": True}), 200

            # 실배포 전환 후 첫 호출 — 테스트 기간(ECHO/DRY-RUN)에 쌓인 트윗 먼저 반영.
            drained, drained_rows = _ingest_queue_drain(gh, now_iso)

            if not rows:
                msg = "ℹ️ ingest: 스케줄/출연 형식 아님 — 무시\n" + raw[:200]
                if drained:
                    msg += f"\n📥 대기열 {drained}건({drained_rows}행) 반영됨"
                _send_telegram(msg, silent=not drained)
                return jsonify({"ok": True, "parsed": 0, "drained": drained}), 200

            changed = _merge_rows_into_schedule(
                gh, rows, now_iso, message=f"data: xrelay scheduled {now_iso}",
                action=f"ingest {title or raw[:40]}".strip(),
            )

            summary = xrelay.summary_text(rows, channels_cfg)
            if drained:
                summary += f"\n\n📥 대기열 {drained}건({drained_rows}행)도 함께 반영"
            if changed:
                summary += "\n\n↩️ /undo 로 되돌릴 수 있습니다."
            _send_telegram(summary)
            return jsonify(
                {"ok": True, "parsed": len(rows), "changed": changed, "drained": drained}
            ), 200
        except Exception as e:
            log.exception("ingest failed")
            _send_telegram(f"⚠️ ingest 오류: {str(e)[:200]}")
            return jsonify({"ok": False, "error": str(e)}), 200

    @app.get("/")
    def _health():
        """헬스체크."""
        return "ok", 200


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대비
    except Exception:
        pass

    print("=" * 60)
    print("telegram_app.py smoke test")
    print("=" * 60)

    # ── ingest 대기열 (Flask 없이도 동작) ──────────────────────────────
    print("\n[Queue] _ingest_queue_push / _drain")
    if xrelay is not None:
        class _FakeGH:
            def __init__(self):
                self.store = {}
            def read_json(self, path):
                return (self.store.get(path), "sha0" if path in self.store else None)
            def write_json(self, path, data, *, prev_sha=None, message=""):
                self.store[path] = data
                return True, "sha1"

        _S = (
            "／\n🛸夢限大みゅーたいぷ\n9/3(木)の配信スケジュール🌟\n＼\n\n"
            "📺24:00～ 仲町あられ×宮永ののか\nhttps://youtube.com/live/kx-nhmTj4Eg\n"
            "※時刻は予告なく変更の場合がございます。"
        )
        g = _FakeGH()
        _ingest_queue_push(g, _S, "t", "2026-09-03T13:00:00Z")
        _ingest_queue_push(g, _S, "t", "2026-09-03T13:01:00Z")  # 직전과 동일 → 스킵
        assert len(g.store[_INGEST_QUEUE_PATH]["pending"]) == 1, g.store[_INGEST_QUEUE_PATH]
        _ingest_queue_push(g, _S + "\n#x", "t", "2026-09-03T13:02:00Z")  # 다르면 추가
        assert len(g.store[_INGEST_QUEUE_PATH]["pending"]) == 2
        applied, nrows = _ingest_queue_drain(g, "2026-09-04T00:00:00Z")
        assert applied == 2 and nrows == 2, (applied, nrows)
        assert g.store[_INGEST_QUEUE_PATH]["pending"] == []          # 비워짐
        sched = g.store["schedule.json"]
        assert any(b.get("host") == "group" for b in sched["broadcasts"]), sched
        assert _ingest_queue_drain(g, "2026-09-04T00:00:00Z") == (0, 0)  # 빈 큐 no-op
        print("  ✓ dedup · drain · merge · 큐 비우기")
    else:
        print("  (xrelay 미로드 — 스킵)")

    # ── v2.5 admin 명령: /list /del /undo (Flask 없이도 동작) ──────────
    print("\n[Admin v2.5] /list · /del · /undo")
    if admin is not None:
        class _FakeGH2:
            """실제 gh_store 처럼 write 시 내용 동일하면 no-op, 다르면 sha 증가."""
            def __init__(self):
                self.store: dict[str, tuple] = {}
                self._n = 0

            def read_json(self, path):
                item = self.store.get(path)
                return (item[0], item[1]) if item else (None, None)

            def write_json(self, path, data, *, prev_sha=None, message=""):
                cur = self.store.get(path)
                if cur is not None and cur[0] == data:
                    return False, cur[1]
                self._n += 1
                new_sha = f"sha{self._n}"
                self.store[path] = (data, new_sha)
                return True, new_sha

        _sent: list[str] = []
        _orig_send = _send_telegram
        globals()["_send_telegram"] = lambda text, silent=False: (_sent.append(text) or True)

        try:
            g2 = _FakeGH2()
            g2.write_json(
                "schedule.json",
                {
                    "broadcasts": [
                        {"channel_key": "ritsu", "status": "live", "title": "ASMR",
                         "scheduled_start": "2026-09-05T02:00:00Z"},
                        {"channel_key": "arale", "status": "scheduled", "source": "bdp_schedule",
                         "sched_id": "sched:arale:2026-09-05T11:00:00Z",
                         "scheduled_start": "2026-09-05T11:00:00Z",
                         "expires_at": "2026-09-05T14:00:00Z", "kind": "game", "title": None},
                        {"channel_key": "yuno", "status": "upcoming", "video_id": "abc",
                         "scheduled_start": "2026-09-06T03:00:00Z", "title": "가라오케"},
                        {"channel_key": "arale", "collab_with": ["nonoka"], "status": "scheduled",
                         "source": "bdp_schedule", "host": "group",
                         "sched_id": "sched:arale:2026-09-05T15:00:00Z",
                         "scheduled_start": "2026-09-05T15:00:00Z",
                         "expires_at": "2026-09-05T18:00:00Z", "kind": "collab", "title": None},
                    ]
                },
                prev_sha=None, message="seed",
            )
            _cfg = _load_channels_config()

            # _sorted_unit_broadcasts: 상태순(live→upcoming→scheduled) + collab_with 로 다른 유닛에도 노출
            arale_items = _sorted_unit_broadcasts(g2.read_json("schedule.json")[0], "arale")
            assert len(arale_items) == 2, arale_items
            nonoka_items = _sorted_unit_broadcasts(g2.read_json("schedule.json")[0], "nonoka")
            assert len(nonoka_items) == 1 and nonoka_items[0]["host"] == "group", nonoka_items
            ritsu_items = _sorted_unit_broadcasts(g2.read_json("schedule.json")[0], "ritsu")
            assert ritsu_items[0]["status"] == "live"
            print("  ✓ _sorted_unit_broadcasts (상태순 정렬 · collab_with 팬아웃)")

            # _time_range_text
            assert "진행중" in _time_range_text(ritsu_items[0])
            assert "(예상)" in _time_range_text(arale_items[0])  # scheduled → expires_at 기준
            print("  ✓ _time_range_text (live/scheduled 표기)")

            # /del 요청 → 확인대기 등록 (arale #1 = scheduled 행)
            _handle_del_request(g2, _cfg, "2026-09-05T01:00:00Z", "arale", "1")
            assert "그래도 지우시겠습니까? (y/N)" in _sent[-1], _sent[-1]
            assert "감지기능으로 다시 되살아날" not in _sent[-1], "scheduled 행엔 warn_live 없어야 함"
            pend = admin.get_pending_del(g2.read_json(_ADMIN_STATE_PATH)[0])
            assert pend is not None and pend["unit"] == "arale" and pend["idx"] == 1
            print("  ✓ /del 확인대기 등록 (warn_deltry, scheduled → warn_live 없음)")

            # upcoming 행 대상이면 warn_live 포함
            _handle_del_request(g2, _cfg, "2026-09-05T01:00:01Z", "yuno", "1")
            assert "감지기능으로 다시 되살아날 수 있습니다" in _sent[-1], _sent[-1]
            # arale#1 확인대기가 yuno#1 로 덮어써짐(슬롯 1개)
            pend2 = admin.get_pending_del(g2.read_json(_ADMIN_STATE_PATH)[0])
            assert pend2["unit"] == "yuno"
            print("  ✓ /del 확인대기 (upcoming → warn_live 포함, 슬롯 1개 덮어씀)")

            # (y/N) = N → 취소, broadcasts 안 바뀜
            n_before = len(g2.read_json("schedule.json")[0]["broadcasts"])
            _handle_del_confirm(g2, "2026-09-05T01:00:02Z", yes=False)
            assert "취소했습니다" in _sent[-1]
            assert len(g2.read_json("schedule.json")[0]["broadcasts"]) == n_before
            assert admin.get_pending_del(g2.read_json(_ADMIN_STATE_PATH)[0]) is None
            print("  ✓ /del (N) → 취소, 변경 없음")

            # 다시 요청 후 (y/N) = Y → 실제 삭제 + undo 스냅샷
            _handle_del_request(g2, _cfg, "2026-09-05T01:00:03Z", "yuno", "1")
            _handle_del_confirm(g2, "2026-09-05T01:00:04Z", yes=True)
            assert "🗑" in _sent[-1] and "/undo" in _sent[-1], _sent[-1]
            assert len(g2.read_json("schedule.json")[0]["broadcasts"]) == n_before - 1
            undo = admin.get_undo(g2.read_json(_ADMIN_STATE_PATH)[0])
            assert undo is not None and undo["action"] == "/del yuno#1"
            print("  ✓ /del (Y) → 삭제 반영 + undo 스냅샷 기록")

            # /undo → 원상복구, 슬롯 비움
            _handle_undo(g2, "2026-09-05T01:00:05Z")
            assert "↩️ 되돌림" in _sent[-1], _sent[-1]
            assert len(g2.read_json("schedule.json")[0]["broadcasts"]) == n_before
            assert admin.get_undo(g2.read_json(_ADMIN_STATE_PATH)[0]) is None
            print("  ✓ /undo → schedule.json 복원, undo 슬롯 비움")

            # 다시 /undo → "되돌릴 작업 없음"
            _handle_undo(g2, "2026-09-05T01:00:06Z")
            assert "되돌릴 작업이 없습니다" in _sent[-1]
            print("  ✓ /undo 재호출 → no-op 안내")

            # SHA 가드: del 후 외부(예: /tick)가 schedule.json 을 또 바꾸면 undo 거부
            _handle_del_request(g2, _cfg, "2026-09-05T01:00:07Z", "arale", "1")
            _handle_del_confirm(g2, "2026-09-05T01:00:08Z", yes=True)
            cur_sched, _ = g2.read_json("schedule.json")
            cur_sched = dict(cur_sched)
            cur_sched["broadcasts"] = cur_sched["broadcasts"] + [{"channel_key": "miyako", "status": "live"}]
            g2.write_json("schedule.json", cur_sched, prev_sha=None, message="외부 변경(예: /tick)")
            _handle_undo(g2, "2026-09-05T01:00:09Z")
            assert "되돌리기 불가" in _sent[-1], _sent[-1]
            assert any(b.get("channel_key") == "miyako" for b in g2.read_json("schedule.json")[0]["broadcasts"]), \
                "거부됐으면 외부 변경이 살아있어야 함"
            print("  ✓ /undo SHA 가드 — 그 사이 외부 변경 있으면 거부(외부 변경 보존)")
        finally:
            globals()["_send_telegram"] = _orig_send
    else:
        print("  (admin 미로드 — 스킵)")

    # Flask 미설치 확인
    if Flask is None or app is None:
        print("\nFlask not installed. Skipping Flask route tests.")
        print("Install with: pip install flask google-auth requests")
        sys.exit(0)

    # Test 1: webhook 시크릿 불일치 → 200 무시
    print("\n[Test 1] webhook 시크릿 불일치")
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "secret123"
    os.environ["TELEGRAM_CHAT_ID"] = "123456"
    with app.test_client() as client:
        resp = client.post(
            "/telegram",
            json={"message": {"chat": {"id": "123456"}, "text": "/status"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("  ✓ 200 무시")

    # Test 2: chat_id 불일치 → 200 무시
    print("\n[Test 2] chat_id 불일치")
    with app.test_client() as client:
        resp = client.post(
            "/telegram",
            json={"message": {"chat": {"id": "999999"}, "text": "/status"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret123"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("  ✓ 200 무시")

    # Test 3: /status 요청 (mock gh_store)
    print("\n[Test 3] /status 명령 처리 (mock)")
    os.environ["GITHUB_TOKEN"] = "fake_token"
    os.environ["GITHUB_REPO"] = "test/repo"
    os.environ["DATA_BRANCH"] = "data"
    # TELEGRAM_BOT_TOKEN 없으면 Telegram.send() no-op
    os.environ["TELEGRAM_BOT_TOKEN"] = ""

    # Mock GitHubStore를 만들기 위해 monkeypatch
    original_gh_store = __import__("src.backend.gh_store", fromlist=["GitHubStore"]).GitHubStore

    class MockGitHubStore:
        def read_json(self, path):
            if path == "schedule.json":
                return (
                    {
                        "broadcasts": [
                            {
                                "status": "live",
                                "channel_key": "arale",
                                "title": "ASMR",
                                "actual_start": "2026-08-31T12:00:00Z",
                            },
                            {
                                "status": "upcoming",
                                "channel_key": "ritsu",
                                "title": "노래틀",
                                "scheduled_start": "2026-08-31T22:00:00Z",
                            },
                        ],
                        "generated_at": "2026-08-31T12:10:00Z",
                    },
                    "sha123",
                )
            elif path == "pending.json":
                return (
                    {
                        "updated_at": "2026-08-31T12:10:00Z",
                        "entries": {
                            "vid1": {
                                "channel_key": "arale",
                                "phase": "pre-live",
                                "scheduled_start": "2026-08-31T13:00:00Z",
                                "actual_start": None,
                                "next_check_at": "2026-08-31T12:45:00Z",
                                "attempts": 0,
                                "first_seen": "2026-08-31T09:00:00Z",
                                "last_checked": None,
                            }
                        }
                    },
                    "sha456",
                )
            elif path == "control.json":
                return (
                    {
                        "paused": False,
                        "since": None,
                        "by": None,
                        "updated_at": None,
                    },
                    "sha789",
                )
            return None, None

    import sys
    import types

    # gh_store 모듈 mock
    gh_store_module = sys.modules.get("src.backend.gh_store")
    if gh_store_module:
        gh_store_module.GitHubStore = MockGitHubStore

    # POST /telegram /status 요청 (TELEGRAM_BOT_TOKEN 없으므로 메시지 전송 안 됨)
    with app.test_client() as client:
        resp = client.post(
            "/telegram",
            json={"message": {"chat": {"id": "123456"}, "text": "/status"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret123"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("  ✓ /status 처리 (메시지 전송은 TELEGRAM_BOT_TOKEN 없으므로 skip)")

    # Test 4: 헬스체크
    print("\n[Test 4] GET / 헬스체크")
    with app.test_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.data == b"ok", f"Expected b'ok', got {resp.data}"
        print("  ✓ 200 ok")

    # Test 5: /ingest 인증·검증 (GitHub 미접촉 경로만)
    print("\n[Test 5] POST /ingest secret/검증")
    os.environ["INGEST_SECRET"] = "ing123"
    with app.test_client() as client:
        r = client.post("/ingest", data={"text": "x"}, headers={"X-Ingest-Secret": "nope"})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
        r = client.post("/ingest", data={"text": "   "}, headers={"X-Ingest-Secret": "ing123"})
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        print("  ✓ bad secret 403 · empty text 400")

        # Automate urlEncode 버그 우회: 트윗 본문이 폼 키로 온 경우 (값은 빔)
        os.environ["INGEST_ECHO"] = "1"
        try:
            body = "8/30(%E6%97%A5)%20%E9%85%8D%E4%BF%A1%E3%82%B9%E3%82%B1%E3%82%B8%E3%83%A5%E3%83%BC%E3%83%AB="
            r = client.post(
                "/ingest", data=body,
                content_type="application/x-www-form-urlencoded",
                headers={"X-Ingest-Secret": "ing123"},
            )
            j = r.get_json()
            assert r.status_code == 200 and j.get("len", 0) > 0, (r.status_code, j)
            # text= 빈값 + 본문키 동시에 와도 본문키를 집는다
            r = client.post(
                "/ingest", data="text=&" + body,
                content_type="application/x-www-form-urlencoded",
                headers={"X-Ingest-Secret": "ing123"},
            )
            assert r.get_json().get("len", 0) > 0, r.get_json()
        finally:
            os.environ.pop("INGEST_ECHO", None)
        print("  ✓ 폼 키로 온 원문 복구")

    print("\n" + "=" * 60)
    print("✓ All smoke tests passed!")
    print("=" * 60)
