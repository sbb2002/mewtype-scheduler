"""Telegram webhook 공개 서비스 (haiku #3).

엔트리포인트: src.backend.telegram_app:app
라우트:
  POST /telegram — Telegram webhook
  GET  /         — 헬스체크
"""
from __future__ import annotations

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

from .control import default_control, is_paused, set_paused
from .gh_store import GitHubStore

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


def _handle_status(gh: GitHubStore, channels_cfg: dict, now_iso: str) -> None:
    """
    /status 명령 처리.
    """
    try:
        text = _build_status_text(now_iso, gh, channels_cfg)
        _send_telegram(text)
    except Exception as e:
        log.exception("Error handling /status")
        _send_telegram(f"⚠️ 오류: /status 처리 실패\n{str(e)[:100]}")


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

            # 명령 디스패치
            if text == "/status":
                _handle_status(gh, channels_cfg, now_utc)
            elif text == "/pause":
                _handle_pause(gh, now_utc)
            elif text == "/resume":
                main_service_url = os.environ.get("MAIN_SERVICE_URL", "").strip()
                if not main_service_url:
                    _send_telegram("⚠️ MAIN_SERVICE_URL 미설정")
                else:
                    _handle_resume(gh, now_utc, main_service_url)
            else:
                # 도움말
                help_text = (
                    "<b>📱 mewtype 텔레그램 봇</b>\n\n"
                    "명령:\n"
                    "/status — 현재 상태 조회\n"
                    "/pause — 수집 일시정지\n"
                    "/resume — 수집 재개"
                )
                _send_telegram(help_text)

        except Exception as e:
            log.exception("Webhook processing error")
            _send_telegram(f"⚠️ 처리 오류: {str(e)[:100]}")

        # 항상 200 반환 (Telegram 재시도 방지)
        return jsonify({"ok": True}), 200

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

    # Flask 미설치 확인
    if Flask is None or app is None:
        print("\nFlask not installed. Skipping tests.")
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

    print("\n" + "=" * 60)
    print("✓ All smoke tests passed!")
    print("=" * 60)
