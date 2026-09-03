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

from .control import (
    LOG_LEVELS,
    default_control,
    get_log_level,
    is_paused,
    set_log_level,
    set_paused,
)
from .gh_store import ConflictError, GitHubStore

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


def _merge_rows_into_schedule(gh, rows, now_iso, message) -> bool:
    """rows 를 merge_scheduled 로 schedule.json 에 반영 (base-sha 충돌 시 1회 재시도)."""
    changed = False
    for attempt in (1, 2):
        prev, sha = gh.read_json("schedule.json")
        merged = xrelay.merge_scheduled(prev or {}, rows, now_iso)
        try:
            changed, _ = gh.write_json("schedule.json", merged, prev_sha=sha, message=message)
            break
        except ConflictError:
            if attempt == 2:
                raise
            log.warning("ingest: schedule.json 충돌 — 재계산 후 재시도")
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
            else:
                # 도움말
                help_text = (
                    "<b>📱 mewtype 텔레그램 봇</b>\n\n"
                    "명령:\n"
                    "/status — 현재 상태 조회\n"
                    "/pause — 수집 일시정지\n"
                    "/resume — 수집 재개\n"
                    "/log [detail|normal|simple] — 알림 상세도"
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
                gh, rows, now_iso, message=f"data: xrelay scheduled {now_iso}"
            )

            summary = xrelay.summary_text(rows, channels_cfg)
            if drained:
                summary += f"\n\n📥 대기열 {drained}건({drained_rows}행)도 함께 반영"
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

    print("\n" + "=" * 60)
    print("✓ All smoke tests passed!")
    print("=" * 60)
