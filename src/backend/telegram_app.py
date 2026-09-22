"""Telegram webhook 공개 서비스 (haiku #3).

엔트리포인트: src.backend.telegram_app:app
라우트:
  POST /telegram — Telegram webhook
  GET  /         — 헬스체크
"""
from __future__ import annotations

import contextvars
import copy
import html
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import unquote_plus

try:
    from flask import Flask, Response, jsonify, request
    _FLASK_AVAILABLE = True
except ImportError:
    _FLASK_AVAILABLE = False
    Flask = None
    Response = None
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
    from .notify import allows as _notify_allows
except ImportError:
    Telegram = None
    def _notify_allows(level, kind):   # noqa: E306 - notify 미탑재 시 전부 통과
        return True

try:
    from . import xrelay
except ImportError:
    xrelay = None

try:
    from . import admin
except ImportError:
    admin = None

try:
    from . import xnotice, notices          # (v2.7) 소식 게시판
except ImportError:
    xnotice = notices = None

try:
    from . import xtweet                    # (v2.8) 멤버 개인 트윗
except ImportError:
    xtweet = None

try:
    from . import ytnotif, ytdlp_probe       # (v3.7.3) 유튜브 앱 회원 전용 라이브 알림 + yt-dlp 조회
except ImportError:
    ytnotif = ytdlp_probe = None

try:
    from . import vxtwitter                  # (v3) 트윗 unfurl — 잘린 URL 복원
except ImportError:
    vxtwitter = None

try:
    from . import vision                     # (v3.2) 비전 OCR — 크로스오버 공지 이미지 출연진
except ImportError:
    vision = None

try:
    # (v2.8.1+) 수동 /ingest 개인 예고: 본문 YT URL → 채널 판별 (videos.list 1 quota)
    from ..collector.youtube import YouTubeClient
except Exception:                           # pragma: no cover
    YouTubeClient = None

from . import preview as preview_mod
from . import monitor_report
from . import statemachine
from . import writeclient
from . import llm
from .control import (
    LOG_LEVELS,
    default_control,
    get_log_level,
    get_monitor_auto,
    is_paused,
    set_log_level,
    set_paused,
    set_monitor_auto,
)
from .gh_store import ConflictError, GitHubStore
from .monitor_log import RESULT_DEGRADED, RESULT_ERR, RESULT_OK, log_event

# admin_state.json 경로 (v2.5 — /list /del /ingest /undo 수동 관리 명령)
_ADMIN_STATE_PATH = "admin_state.json"
_NOTICES_PATH = "notices.json"                 # (v2.7) 소식 게시판
_NOTICE_ARCHIVE_PATH = "notice_archive.json"
_TWEETS_PATH = "tweets.json"                   # (v2.8) 멤버 개인 트윗
_TWEET_ARCHIVE_PATH = "tweet_archive.json"
_UNIT_KEYS = ("arale", "yuno", "nonoka", "ritsu", "miyako")

# (v3.2) 출연진 이미지 그래픽을 쓰는 걸로 확인된 크로스오버 공식 계정.
# 이 handle 이 src_handle 에 포함된 소식만 비전 OCR 을 태운다 — 매번 모든 소식에
# 이미지가 있는지 찔러보면 낭비이자 오탐 확률만 늘어난다.
_CAST_LOOKUP_HANDLES = ("bang_dream_on",)


def _tw_list(v):
    """tweets[ck] → 메시지 list (계약 I v3.1). v2.8 단건 dict 는 [dict], xtweet 미탑재에도 안전."""
    if isinstance(v, list):
        return [m for m in v if isinstance(m, dict)]
    if isinstance(v, dict):
        return [v]
    return []
_PREVIEW_PATH = "preview.json"                 # (v3) schedule.json 대체
_PREVIEW_ARCHIVE_PATH = "preview_archive.json"
# (v3) 6상태 — none 은 파일에 없음
_STATE_RANK = {"live": 0, "watching": 1, "upcoming": 2, "announced": 3, "end": 4}
_STATE_BADGE = {"live": "🔴", "watching": "👀", "upcoming": "🟢",
                "announced": "🕊", "end": "⚫"}

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


def _sorted_unit_broadcasts(preview: dict, unit: str) -> list[dict]:
    """preview['items'] 중 unit 이 당사자(본인 채널 또는 합동 참여)인 항목,
    state(live→watching→upcoming→announced→end)·시각순 정렬. (v3 /list /del)"""
    rows = preview.get("items", []) or []
    items = [
        b for b in rows
        if b.get("channel_key") == unit or unit in (b.get("collab_with") or [])
    ]
    return sorted(
        items,
        key=lambda b: (_STATE_RANK.get(b.get("state"), 9), b.get("scheduled_start") or ""),
    )


def _kst_to_md(dt: Optional[datetime]) -> Optional[str]:
    """datetime(KST) → "YYYY/M/D" 문자열. None이면 None.

    준영구 "대기소" 프레임처럼 `scheduled_start` 가 1~2년 뒤인 항목도 섞여 들어오므로
    (CLAUDE.md 주의점) 연도를 생략하지 않는다.
    """
    if dt is None:
        return None
    return f"{dt.year}/{dt.month}/{dt.day}"


def _time_range_text(b: dict) -> str:
    """방송 1건의 표시용 날짜+시간 범위. (v2.5)

    live = "M/D HH:MM~ (진행중)", scheduled = "M/D HH:MM~HH:MM(예상)"(expires_at 기준),
    그 외(upcoming 등, 종료 미정) = "M/D HH:MM~". 날짜는 시작 시각(KST) 기준.
    """
    start_kst = _parse_iso_to_kst(b.get("scheduled_start"))
    start_md = _kst_to_md(start_kst) or "?"
    start_hm = _kst_to_hm(start_kst) or "?"
    state = b.get("state")
    if state == "live":
        return f"{start_md} {start_hm}~ (진행중)"
    if state == "end":
        return f"{start_md} {start_hm}~ (방송 종료)"
    if state == "announced":
        end_hm = _kst_to_hm(_parse_iso_to_kst(b.get("expires_at")))
        if end_hm:
            return f"{start_md} {start_hm}~{end_hm}(예상)"
    return f"{start_md} {start_hm}~"


def _format_list_text(channels_cfg: dict, preview: dict, unit: str = "") -> str:
    """/list 응답 본문. unit 비우면 5채널 전체. (v3)"""
    chan = channels_cfg.get("channels", {})
    units = [unit] if unit else list(_UNIT_KEYS)
    blocks = []
    for u in units:
        name = chan.get(u, {}).get("name_ko", u)
        lines = [f"<b>{name}</b> ({u})"]
        items = _sorted_unit_broadcasts(preview, u)
        if not items:
            lines.append("· (없음)")
        else:
            for i, b in enumerate(items, start=1):
                badge = _STATE_BADGE.get(b.get("state"), "❔")
                title = (b.get("title") or (xrelay.KIND_KO.get(b.get("kind"), "") if xrelay else "")) or ""
                title_part = f" 「{title[:20]}」" if title else ""
                collab_part = " (합동)" if (b.get("collab_with") or b.get("host") == "group") else ""
                lines.append(f"#{i} {badge} {_time_range_text(b)}{title_part}{collab_part}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _save_undo(gh: GitHubStore, *, action: str, prev_content: dict, new_sha, now_iso: str,
               path: str = "preview.json") -> None:
    """`path` 파일을 바꾼 직후 admin_state.json 에 undo 스냅샷 기록. 실패해도 본 작업은 안 막음."""
    if admin is None:
        return
    try:
        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = admin.set_undo(
            state or admin.default_admin_state(),
            action=action, prev_content=prev_content, new_sha=new_sha, now_iso=now_iso, path=path,
        )
        gh.write_json(
            _ADMIN_STATE_PATH, state, prev_sha=sha,
            message=f"data: undo snapshot ({action}) {now_iso}",
        )
    except Exception:
        log.exception("undo 스냅샷 저장 실패 (무시 — /undo 만 이번 건 불가해짐)")


def _build_status_text(now_iso: str, gh: GitHubStore, channels_cfg: dict) -> str:
    """/status 응답 본문 (v3). preview 6상태 카운트 + notice/tweet 요약 + 동기화 + LLM 큐."""
    now_kst = _get_kst_now()
    now_date = now_kst.date()

    preview = _load_config_dict(gh, _PREVIEW_PATH)
    notices_j = _load_config_dict(gh, _NOTICES_PATH)
    tweets_j = _load_config_dict(gh, _TWEETS_PATH)
    control = _load_config_dict(gh, "control.json") or default_control()

    items = preview.get("items", []) or []
    generated_at = preview.get("generated_at")

    paused = is_paused(control)
    head = ("{icon} <b>mewtype v3</b>  |  paused: {p}  |  log: {lv}").format(
        icon=("REDCIRCLE" if paused else "GREENCIRCLE"),
        p=("yes" if paused else "no"), lv=get_log_level(control))
    head = head.replace("REDCIRCLE", "🔴").replace("GREENCIRCLE", "🟢")

    cnt = {k: 0 for k in ("announced", "upcoming", "watching", "live", "end")}
    for b in items:
        if b.get("state") in cnt:
            cnt[b["state"]] += 1
    preview_line = "preview  " + " . ".join(
        f"{k} {cnt[k]}" for k in ("announced", "upcoming", "watching", "live", "end"))

    nlist = notices_j.get("notices", []) or []
    dmin = None
    for n in nlist:
        try:
            d = datetime.strptime(n.get("date", ""), "%Y-%m-%d").date()
            dd = (d - now_date).days
            dmin = dd if dmin is None else min(dmin, dd)
        except Exception:
            pass
    ntxt = f"notice   {len(nlist)}건" + (f" (가장 이른 D{dmin:+d})" if dmin is not None else "")

    tw = tweets_j.get("tweets", {}) or {}
    _tw_n = {k: len(_tw_list(tw.get(k))) for k in _UNIT_KEYS if k in tw}
    tw_units = [f"{k}×{_tw_n[k]}" if _tw_n[k] > 1 else k for k in _tw_n]
    ttxt = f"tweet    {', '.join(tw_units) or '없음'}  ({len(tw_units)}/5)"

    sync = ["동기화"]
    if generated_at:
        gk = _parse_iso_to_kst(generated_at)
        if gk:
            sync.append(f"  마지막 sync   {gk.strftime('%Y-%m-%d %H:%M')} JST "
                        f"({_relative_time(generated_at, now_iso)})")

    q = (sum(1 for n in nlist if n.get("needs_tl"))
         + sum(1 for lst in tw.values() for t in _tw_list(lst) if t.get("needs_tl")))
    qtxt = f"LLM 큐   {q}건 대기"

    nl = chr(10)
    return nl.join([head, "", preview_line, ntxt, ttxt, "",
                    nl.join(sync), "", qtxt])


# (v3.6) 명령 하나를 처리하는 동안 `_send_telegram` 이 한 번이라도 불렸는지 추적.
# 버그리포트 20260916 #4: `/del preview`(유닛/번호 누락)처럼 인식은 되지만 처리할 수
# 없는 명령이 응답 DM 없이 조용히 끝나면, 운영자는 명령이 씹혔는지 처리 중인지 구분할
# 방법이 없다 — 개별 핸들러마다 "이 경로는 DM을 보내는가"를 일일이 감사하는 대신,
# 웹훅 처리 마지막에 이 플래그로 "정말 아무 응답도 안 나갔는지"를 한 번에 확인해
# 안전망 DM을 보낸다. ContextVar 라 요청(스레드)마다 독립 — 동시 요청이 서로 안 건드림.
_dm_sent_ctx: "contextvars.ContextVar[bool]" = contextvars.ContextVar("_dm_sent", default=False)


def _send_telegram(text: str, silent: bool = False) -> bool:
    """Telegram으로 메시지 전송."""
    _dm_sent_ctx.set(True)
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


def _send_telegram_document(filename: str, content: bytes, *, caption: str = "") -> bool:
    """Telegram으로 파일 전송 (Push Monitor html 등)."""
    _dm_sent_ctx.set(True)
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        log.warning("Telegram not configured (BOT_TOKEN or CHAT_ID missing)")
        return False

    if Telegram is None:
        log.warning("Telegram class not available")
        return False

    tg = Telegram(bot_token, chat_id)
    return tg.send_document(filename, content, caption=caption)


def _auto_dm_allows(gh, kind: str) -> bool:
    """(v2.8.2) 자동 알림 `kind` 를 현재 control.json `log_level` 에서 보낼지.

    운영자가 직접 친 명령의 응답에는 쓰지 않는다 — 자동으로 튀어나오는 알림
    (소식/트윗/본인예고/ingest 결과)만 이 게이트를 통과해야 한다.
    레벨 매핑: notify._LEVEL_KINDS — detail=전부 / normal=scheduled·upcoming·live·notice·tweet / simple=upcoming·live.
    """
    try:
        control, _ = gh.read_json("control.json")
        level = get_log_level(control or default_control())
    except Exception:
        level = "normal"
    return _notify_allows(level, kind)


def _auto_dm(gh, kind: str, text: str, *, silent: bool = True) -> None:
    """`_auto_dm_allows` 통과하면 `_send_telegram`."""
    if _auto_dm_allows(gh, kind):
        _send_telegram(text, silent=silent)


# /status 두 번째 메시지 — 첫 메시지(_build_status_text)에 나오는 용어 풀이 (v3).
_STATUS_GLOSSARY = (
    "📖 <b>/status 필드 (v3)</b>\n"
    "· <b>paused</b> — /pause 로 멈춤. 정지 중엔 tick·wake·ingest 가 no-op\n"
    "· <b>preview</b> — 살아있는 예고 아이템(announced~end)의 상태별 개수. "
    "announced(정보 일부)→upcoming(전부)→watching(±3분 감시)→live→end(종료 유예)\n"
    "· <b>notice</b> — 소식 게시판 건수 + 가장 이른 D-day\n"
    "· <b>tweet</b> — 개인 트윗 배지가 떠 있는 유닛 (n/5)\n"
    "· <b>마지막 sync</b> — 백엔드가 preview.json 을 마지막으로 재구성한 시각\n"
    "· <b>LLM 큐</b> — 번역 대기(needs_tl) 행 수. /translate 로 즉시 처리 가능\n"
    "\n"
    "🔧 <b>로그 레벨</b> (/log 로 변경)\n"
    "· <b>detail</b> — announced·upcoming·live·demote·notice·tweet·ingest + 오류/요약\n"
    "· <b>normal</b> — announced·upcoming·live·notice·tweet (기본값)\n"
    "· <b>simple</b> — upcoming·live 만"
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
    "detail": "scheduled·upcoming·live·notice·tweet·ingest 전부 + fallback/오류/sync 요약 (성공·실패 무관)",
    "normal": "scheduled·upcoming·live·notice·tweet 만",
    "simple": "upcoming·live 만",
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


def _healthchecks_uuid() -> str:
    """HEALTHCHECK_URL(https://hc-ping.com/<uuid>)에서 uuid만 뽑는다 — 별도 env 불필요."""
    url = os.environ.get("HEALTHCHECK_URL", "").strip()
    return url.rsplit("/", 1)[-1] if url else ""


def _handle_monitor(gh: GitHubStore, now_iso: str, arg: str) -> None:
    """/monitor [--auto|--off|--monthly|--yearly|YYYY-MM-DD] — Ops Monitor 대시보드(v3.5,
    구 Push Monitor 대체).

    인자 없음: 오늘자(06:00 KST~익일 06:00 KST) 리포트를 즉시 생성해 DM 전송.
    YYYY-MM-DD: 그 날짜의 리포트 생성(다른 날짜는 이 방식으로 요청).
    --monthly (구 --full): 이번 달 1일~오늘 전부를 담아 생성 — 리포트 안 "월간 추이"
      그리드에서 날짜 전환 가능.
    --yearly (v3.8.5): 올해 1월 1일~오늘 전부를 "연간 추이" 그리드로 담아 생성.
    --auto: Cloud Scheduler(KST 06:00) 자동 생성+DM 켬 — 매월 1일은 전월 --monthly로,
      1월 1일은 전년 --yearly로 자동 대체된다(app.py `_monitor()`).
    --off: 자동 생성 끔 (수동 /monitor 는 계속 가능).
    """
    if arg in ("--auto", "--off"):
        try:
            control, _ = gh.read_json("control.json")
            if control is None:
                control = default_control()
            enabled = arg == "--auto"
            control = set_monitor_auto(
                control, enabled, by=f"telegram:/monitor {arg}", now_iso=now_iso,
            )
            gh.write_json(
                "control.json", control, prev_sha=None,
                message=f"data: monitor_auto={enabled} via Telegram {arg} {now_iso}",
            )
            if enabled:
                _send_telegram("🟢 Monitor 자동 실행 켬 — 매일 KST 06:00에 리포트 생성 후 DM으로 전송합니다.")
            else:
                _send_telegram("⚪ Monitor 자동 실행 끔 — /monitor 로 수동 실행은 계속 가능합니다.")
        except Exception as e:
            log.exception("Error handling /monitor %s", arg)
            _send_telegram(f"⚠️ 오류: /monitor {arg} 처리 실패\n{str(e)[:100]}")
        return

    monthly = arg.strip() == "--monthly"
    yearly = arg.strip() == "--yearly"
    date_kst = None if (monthly or yearly) else (
        arg.strip() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", arg.strip()) else None
    )
    if arg.strip() and not monthly and not yearly and date_kst is None:
        _send_telegram("사용법: /monitor [--auto|--off|--monthly|--yearly|YYYY-MM-DD]")
        return

    try:
        _send_telegram(
            "⏳ Monitor 리포트 생성 중..." + (
                " (이번 해 전체 — 훨씬 더 걸릴 수 있습니다)" if yearly else
                " (이번 달 전체 — 시간이 더 걸릴 수 있습니다)" if monthly else ""
            ),
            silent=True,
        )
        result = monitor_report.run(
            gh, date_kst=date_kst, monthly=monthly, yearly=yearly,
            healthchecks_api_key=os.environ.get("HEALTHCHECKS_IO_READONLEY_TOKEN", "").strip(),
            healthchecks_uuid=_healthchecks_uuid(),
            github_token_for_commits=gh.token,
        )
        html = result.pop("html")
        filename = result.pop("filename")
        if not monthly and not yearly:
            try:
                gh.write_text(
                    "monitoring/latest.html", html, prev_sha=None,
                    message=f"data: monitor latest (manual) {result['date']}",
                )
            except Exception:
                log.exception("monitor: latest.html 커밋 실패 (DM은 계속 진행)")
        ok = _send_telegram_document(
            filename,
            html.encode("utf-8"),
            caption=f"📊 Monitor — {result['date']} · {result['events']}건" + (
                " (올해 전체)" if yearly else " (이번 달 전체)" if monthly else ""
            ),
        )
        if not ok:
            _send_telegram("⚠️ 생성은 성공했지만 DM 전송에 실패했습니다.")
    except Exception as e:
        log.exception("Error handling /monitor")
        _send_telegram(f"⚠️ 오류: /monitor 처리 실패\n{str(e)[:100]}")


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
        try:
            log_event(gh, now_iso, "ops", RESULT_OK, who="/pause",
                      detail="control.json 커밋" if changed else "이미 일시정지 상태(무변화)")
        except Exception:  # noqa: BLE001
            log.warning("monitor_log 기록 실패(ops /pause)")
    except Exception as e:
        log.exception("Error handling /pause")
        _send_telegram(f"⚠️ 오류: /pause 처리 실패\n{str(e)[:100]}")
        try:
            log_event(gh, now_iso, "ops", RESULT_ERR, who="/pause", detail=str(e)[:150])
        except Exception:  # noqa: BLE001
            log.warning("monitor_log 기록 실패(ops /pause)")


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

        try:
            log_event(gh, now_iso, "ops", RESULT_OK if tick_result else RESULT_DEGRADED, who="/resume",
                      detail="control.json 커밋 + heal 즉시 호출" + ("" if tick_result else " (heal 호출 응답 확인 불가)"))
        except Exception:  # noqa: BLE001
            log.warning("monitor_log 기록 실패(ops /resume)")
    except Exception as e:
        log.exception("Error handling /resume")
        _send_telegram(f"⚠️ 오류: /resume 처리 실패\n{str(e)[:100]}")
        try:
            log_event(gh, now_iso, "ops", RESULT_ERR, who="/resume", detail=str(e)[:150])
        except Exception:  # noqa: BLE001
            log.warning("monitor_log 기록 실패(ops /resume)")


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


def _merge_rows_into_schedule(gh, rows, now_iso, message, action: str | None = None,
                              merge_fn=None) -> bool:
    """rows 를 `merge_fn` 으로 preview.json 의 items 에 반영 (base-sha 충돌 시 1회 재시도).

    (v3) merge_fn 계약: `xrelay.merge_announced(items, rows, now) -> (items, changed)` (rows 통째) /
    `xtweet.merge_personal_schedule(items, row, now) -> (items, changed)` (단일 row). 기본은 전자.
    변경됐으면 admin_state.json 에 undo 스냅샷(`path=preview.json`).
    """
    merge_fn = merge_fn or xrelay.merge_announced
    per_row = merge_fn is not xrelay.merge_announced   # personal 은 row 하나씩
    changed = False
    prev = new_sha = None
    for attempt in (1, 2):
        prev, sha = gh.read_json(_PREVIEW_PATH)
        prev = prev or {"items": []}
        items = list(prev.get("items", []) or [])
        any_ch = False
        if per_row:
            for r in rows:
                items, c1 = merge_fn(items, r, now_iso)
                any_ch = any_ch or c1
        else:
            items, any_ch = merge_fn(items, rows, now_iso)
        merged = dict(prev)
        merged["items"] = items
        merged["generated_at"] = now_iso
        try:
            changed, new_sha = gh.write_json(_PREVIEW_PATH, merged, prev_sha=sha, message=message)
            break
        except ConflictError:
            if attempt == 2:
                raise
            log.warning("ingest: preview.json 충돌 — 재계산 후 재시도")
    if changed:
        _save_undo(gh, action=action or message, prev_content=prev or {}, new_sha=new_sha, now_iso=now_iso)
    return changed


def _remove_broadcast(gh, snapshot: dict, now_iso: str, action: str) -> bool:
    """snapshot 과 정확히 일치하는 preview.items[] 항목 1개를 제거 (v3 /del).

    그 사이 항목이 바뀌었거나 이미 없으면 False — 아무것도 안 지운다. base-sha 충돌 시 1회 재시도.
    """
    changed = False
    prev = new_sha = None
    for attempt in (1, 2):
        prev, sha = gh.read_json(_PREVIEW_PATH)
        prev = prev or {}
        items = prev.get("items", []) or []
        # id 우선 매칭(스냅샷 이후 volatile 필드가 바뀌어도 동일 아이템으로 잡음), 없으면 완전일치
        match_i = None
        sid = snapshot.get("id")
        if sid:
            match_i = next((i for i, b in enumerate(items) if b.get("id") == sid), None)
        if match_i is None:
            match_i = next((i for i, b in enumerate(items) if b == snapshot), None)
        if match_i is None:
            return False
        new_pv = dict(prev)
        new_pv["items"] = items[:match_i] + items[match_i + 1:]
        new_pv["generated_at"] = now_iso
        try:
            changed, new_sha = gh.write_json(_PREVIEW_PATH, new_pv, prev_sha=sha, message=f"data: {action} {now_iso}")
            break
        except ConflictError:
            if attempt == 2:
                raise
            log.warning("del: preview.json 충돌 — 재계산 후 재시도")
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
    channels_cfg = _load_channels_config()
    for it in items:
        raw = it.get("raw", "")
        rows = xrelay.parse(raw, it.get("received_at") or now_iso)
        if not rows:
            continue
        rows = _confirm_relay_rows_collab(gh, raw, rows, channels_cfg, now_iso, via="ingest")
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
        schedule = _load_config_dict(gh, _PREVIEW_PATH)
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

        schedule = _load_config_dict(gh, _PREVIEW_PATH)
        items = _sorted_unit_broadcasts(schedule, unit)
        if idx < 1 or idx > len(items):
            _send_telegram(f"⚠️ {unit} 에 #{idx} 항목이 없습니다. /list {unit} 로 확인하세요.")
            return
        b = items[idx - 1]
        name = channels_cfg.get("channels", {}).get(unit, {}).get("name_ko", unit)

        warn = f"#{idx} {name}의 {_time_range_text(b)} 방송예고를 내리시겠습니까?"  # warn_deltry
        if b.get("state") in ("announced", "upcoming", "watching", "live"):
            warn += "\n해당 예고는 감지기능으로 다시 되살아날 수 있습니다."          # warn_live
        warn += ("\n(<code>y</code> = 삭제 · <code>terminate</code> = 삭제 + 그 URL 12h 재등록 차단 "
                 "· <code>N</code>/무응답 = 취소)")

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


def _handle_del_confirm(gh, now_iso: str, answer: str) -> None:
    """대기 중인 /del 요청에 대한 답변 처리. answer ∈ y | n | terminate.

    (v3) `terminate` = 삭제 + 그 url 을 12h 재진입 차단(`admin.add_suppress`). url 이 없으면
    `y` 와 동일 + 안내. `/tick` reconcile 이 suppress 목록을 대조해 재등록을 막는다.
    """
    ans = (answer or "").strip().lower()
    try:
        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = state or admin.default_admin_state()
        pending = admin.get_pending_del(state)
        if not pending or admin.pending_del_expired(pending, now_iso):
            state = admin.clear_pending_del(state)
            gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: /del 대기 정리(만료) {now_iso}")
            _send_telegram("⌛ 대기 중인 삭제 요청이 없습니다(만료됨). /del 로 다시 시도하세요.")
            return

        if ans not in ("y", "yes", "terminate"):
            state = admin.clear_pending_del(state)
            gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: /del 취소 {now_iso}")
            _send_telegram("↩️ 취소했습니다.")
            return

        unit, idx, snapshot = pending["unit"], pending["idx"], pending["snapshot"]
        action = f"/del {unit}#{idx}"
        removed = writeclient.call_write(
            "remove_broadcast", gh=gh, snapshot=snapshot, now_iso=now_iso, action=action,
        ).get("removed")

        note = ""
        if ans == "terminate" and removed:
            url = snapshot.get("url")
            if url:
                try:
                    st2, sh2 = gh.read_json(_ADMIN_STATE_PATH)
                    gh.write_json(
                        _ADMIN_STATE_PATH,
                        admin.add_suppress(st2 or admin.default_admin_state(),
                                           url=url, now_iso=now_iso),
                        prev_sha=sh2, message=f"data: suppress += {url} {now_iso}",
                    )
                    note = "\n🚫 이 URL 은 12시간 동안 재등록이 차단됩니다."
                except Exception:
                    log.exception("suppress 추가 실패")
                    note = "\n⚠️ 재진입 차단 등록 실패 (삭제는 됨)."
            else:
                note = "\nℹ️ url 이 없어 재진입 차단은 생략했습니다(일반 삭제와 동일)."

        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = admin.clear_pending_del(state or admin.default_admin_state())
        gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: /del 완료 {now_iso}")

        if removed:
            _send_telegram(f"🗑 {action} 반영됨. /undo 로 되돌릴 수 있습니다.{note}")
        else:
            _send_telegram(f"⚠️ {action} 실패 — 그 사이 항목이 바뀌거나 사라졌습니다. /list 로 확인하세요.")
    except Exception as e:
        log.exception("Error handling /del confirm")
        _send_telegram(f"⚠️ 오류: /del 확인 처리 실패\n{str(e)[:100]}")


def _failed_lines_block(failed: list, limit: int = 8) -> str:
    """xrelay.unparsed_lines 결과 → DM 에 넣을 목록 문자열 (줄당 80자, 최대 limit 줄)."""
    shown = [f"· {ln[:80]}" for ln in failed[:limit]]
    if len(failed) > limit:
        shown.append(f"…외 {len(failed) - limit}줄")
    return "\n".join(shown)


_TWEET_ID_RE = re.compile(r"tweet-(\d{6,25})")


def _tweet_url_from_tag(tag: str) -> str:
    """삼성 인터넷 웹푸시 태그(`p#https://x.com/#1tweet-<id>`) → 트윗 링크. 못 뽑으면 "".

    폰 Automate 가 `/ingest` 에 `tag` 필드로 `nx["pde_noti_tag"]` 를 넘겨준다(v2.3.x).
    작성자 handle 은 태그에 없으므로 `x.com/i/status/<id>` 형태(작성자 무관, X 가 리다이렉트).
    """
    m = _TWEET_ID_RE.search(tag or "")
    return f"https://x.com/i/status/{m.group(1)}" if m else ""


_INGEST_PROMPT = (
    "📝 <b>/ingest 대기 중</b> (3분)\n"
    "3분 내에 공식계정(@BDP_yumemita)의 예고트윗 텍스트를 입력하시거나 "
    "텍스트 파일(txt, md 등)을 업로드해주세요.\n"
    "취소하려면 <code>aNoneTokyo</code> 라고 입력하세요."
)
_INGEST_CANCEL_TOKEN = "aNoneTokyo"
_INGEST_FILE_MAX_BYTES = 256 * 1024


def _download_telegram_file(file_id: str) -> Optional[str]:
    """Telegram 파일(file_id)을 내려받아 UTF-8 텍스트로 반환. 실패 시 None.

    getFile → file_path → https://api.telegram.org/file/bot<token>/<file_path>.
    256KB 초과 파일은 거부(None).
    """
    if requests is None:
        return None
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or not file_id:
        return None
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id}, timeout=10,
        )
        r.raise_for_status()
        info = (r.json() or {}).get("result") or {}
        file_path = info.get("file_path")
        if not file_path:
            return None
        if (info.get("file_size") or 0) > _INGEST_FILE_MAX_BYTES:
            log.warning("ingest file too large: %s bytes", info.get("file_size"))
            return None
        fr = requests.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=15
        )
        fr.raise_for_status()
        if len(fr.content) > _INGEST_FILE_MAX_BYTES:
            return None
        return fr.content.decode("utf-8", "replace")
    except Exception:
        log.exception("Telegram 파일 다운로드 실패")
        return None


def _handle_ingest_followup(
    gh, channels_cfg: dict, now_iso: str, message: dict, text: str
) -> bool:
    """`pending_ingest` 슬롯이 살아있을 때 들어온 메시지를 원문/파일/취소로 소비.

    반환값:
      True  — 이 메시지를 ingest 흐름이 소진함(웹훅은 즉시 200, 명령 디스패치 안 함)
      False — 소진하지 않음(만료됐거나 다른 `/명령` — 정상 디스패치로 흘려보냄)
    """
    if admin is None:
        return False
    try:
        state, _ = gh.read_json(_ADMIN_STATE_PATH)
    except Exception:
        log.warning("admin_state.json 조회 실패 — /ingest 후속 처리 스킵")
        return False
    pending = admin.get_pending_ingest(state)
    if not pending:
        return False

    def _clear_slot() -> None:
        try:
            st, sh = gh.read_json(_ADMIN_STATE_PATH)
            gh.write_json(
                _ADMIN_STATE_PATH,
                admin.clear_pending_ingest(st or admin.default_admin_state()),
                prev_sha=sh, message=f"data: pending_ingest 슬롯 정리 {now_iso}",
            )
        except Exception:
            log.exception("pending_ingest 슬롯 정리 실패")

    # 1) 만료 — 취소 안내만 하고 이 메시지는 정상 디스패치로 흘려보낸다.
    if admin.pending_ingest_expired(pending, now_iso):
        _clear_slot()
        _send_telegram("⏱ 이전 /ingest 요청이 만료되어 취소되었습니다.")
        return False

    # 2) 취소 토큰
    if text.strip() == _INGEST_CANCEL_TOKEN:
        _clear_slot()
        _send_telegram("🚫 ingest가 취소되었습니다.")
        return True

    # 3) 다른 명령 — 대기를 접고 그 명령을 실행하게 둔다.
    if text.startswith("/"):
        _clear_slot()
        _send_telegram("ℹ️ /ingest 대기를 취소하고 입력한 명령을 실행합니다.")
        return False

    # 4) 파일 업로드
    doc = message.get("document") or {}
    raw = ""
    if doc.get("file_id"):
        content = _download_telegram_file(doc["file_id"])
        if content is None:
            _send_telegram(
                "⚠️ 파일을 읽지 못했습니다(형식/크기 확인, 256KB 이하 텍스트). "
                "다시 보내주세요. (대기 유지)"
            )
            return True
        raw = content.strip()
    elif text.strip():
        raw = text.strip()
    else:
        # 사진·스티커 등
        _send_telegram("⚠️ 예고 원문 텍스트나 텍스트 파일을 보내주세요. (대기 유지)")
        return True

    # 5) 원문 확보 — 슬롯 비우고 접수 안내 후 반영
    _clear_slot()
    _send_telegram("📥 예고 원문 받았습니다. 반영될 때까지 기다려주세요.")
    _handle_manual_ingest(gh, channels_cfg, now_iso, raw)
    return True


def _channel_key_by_video(video_id: str) -> str | None:
    """YouTube 영상 id → 5인 중 한 명의 channel_key. 못 정하면 None.

    `videos.list` 1회(quota 1 unit)로 `snippet.channelId` 를 얻어
    `config/channels.json` 의 `channel_id` 와 대조한다. YOUTUBE_API_KEY 가 없거나
    영상이 비공개/미존재거나 5인 채널이 아니면 None.
    """
    if not video_id or YouTubeClient is None:
        return None
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        log.warning("YOUTUBE_API_KEY 없음 — 수동 /ingest 개인 예고 채널 판별 불가")
        return None
    try:
        info = YouTubeClient(api_key).videos_list([video_id]).get(video_id)
    except Exception:
        log.exception("videos.list 실패 (수동 /ingest 채널 판별)")
        return None
    if not info or not info.channel_id:
        return None
    for ck, meta in _load_channels_config().get("channels", {}).items():
        if meta.get("channel_id") == info.channel_id:
            return ck
    log.info("수동 /ingest 개인 예고 URL 채널 미매칭: channel_id=%s", info.channel_id)
    return None


_MEMBER_PROMPT = (
    "ingest하려는 유메미타 멤버는 누구죠? 취소하시려면 aNoneTokyo라고 입력하세요.\n"
    "[1]아라레 [2]유노 [3]노노카 [4]리츠 [5]미야코"
)
_MEMBER_CHOICE = {
    "1": "arale", "2": "yuno", "3": "nonoka", "4": "ritsu", "5": "miyako",
    "아라레": "arale", "유노": "yuno", "노노카": "nonoka", "리츠": "ritsu", "미야코": "miyako",
    "arale": "arale", "yuno": "yuno", "nonoka": "nonoka", "ritsu": "ritsu", "miyako": "miyako",
}


def _ingest_personal_row(gh, channels_cfg: dict, raw: str, channel_key: str,
                         now_iso: str) -> bool:
    """주어진 `channel_key` 로 raw 를 개인 예고로 파싱·머지.

    `xtweet.parse_schedule`(게이트 = `配信` 계열 + 날짜/URL) → `merge_personal_schedule`
    로 `schedule.json` 의 scheduled(`source:"personal"`) 행 + undo 스냅샷 + DM.
    폰 릴레이의 `_maybe_personal_schedule` 와 결과가 같다. 항상 True(요청 소진 —
    예고 형식이 아니면 그 안내만 냄).
    """
    chans = (channels_cfg or {}).get("channels", {})
    name = chans.get(channel_key, {}).get("name_ko", channel_key)
    try:
        row = xtweet.parse_schedule(
            raw, channel_key=channel_key, tag=None, now_iso=now_iso,
            handle=chans.get(channel_key, {}).get("handle", ""),
        )
    except Exception:
        log.exception("parse_schedule 실패 (수동 /ingest 개인 예고)")
        row = None
    if not row:
        _send_telegram(
            f"ℹ️ /ingest: {html.escape(name)} 개인 예고로 봤지만 형식"
            "(<code>配信</code> 계열 + 날짜/URL)이 아닙니다 — 무시\n"
            f"<code>{html.escape(raw[:200])}</code>"
        )
        return True
    result = writeclient.call_write(
        "merge_rows", gh=gh, rows=[row], now_iso=now_iso,
        message=f"data: telegram /ingest personal {channel_key} {now_iso}",
        action=f"/ingest 개인예고 {name} ({raw[:40].strip()})",
        merge_fn="personal_schedule",
    )
    changed = result.get("changed")
    when = ("시간 미정" if row.get("time_tbd")
            else xrelay._jst_hm(row.get("scheduled_start")) + " JST")
    link = row.get("url") or ""
    _send_telegram(
        f"📅 <b>{html.escape(name)}</b> 개인 예고 반영 → {when}"
        + (f"\n{html.escape(link)}" if link else "")
        + ("\n\n↩️ /undo 로 되돌릴 수 있습니다." if changed
           else "\n\n(이미 반영돼 있어 변경 없음)")
    )
    return True


def _ask_member(gh, raw: str, now_iso: str) -> None:
    """개인 예고인데 채널을 못 정함 → `pending_member` 슬롯에 raw 저장하고 유닛 되묻기."""
    if admin is not None and gh is not None:
        try:
            _st, _sh = gh.read_json(_ADMIN_STATE_PATH)
            gh.write_json(
                _ADMIN_STATE_PATH,
                admin.set_pending_member(_st or admin.default_admin_state(),
                                         raw=raw[:_INGEST_RAW_CAP], now_iso=now_iso),
                prev_sha=_sh, message=f"data: pending_member 대기 시작 {now_iso}",
            )
        except Exception:
            log.exception("pending_member 세팅 실패")
            _send_telegram("⚠️ 유닛 되묻기 상태 저장 실패 — 잠시 후 다시 시도하세요.")
            return
    _send_telegram(_MEMBER_PROMPT)


def _try_personal_ingest(gh, channels_cfg: dict, raw: str, now_iso: str) -> bool:
    """수동 /ingest 원문이 @BDP 스케줄/출연 형식이 아닐 때 — 멤버 개인 예고로 시도.

    본문에 온전한 YouTube URL 이 있으면 `_channel_key_by_video`(videos.list 1 quota)
    로 채널을 판별해 바로 반영한다. URL 이 없거나 채널을 못 정하면(영상 비공개 · 링크
    잘림 · 키 미설정 · 5인 채널 아님) `pending_member` 슬롯에 원문을 넣고 유닛을 되묻는다.

    반환: xtweet/xrelay 사용 가능하면 항상 True(이 경로가 요청을 맡음),
          모듈이 없으면 False(호출측이 기존 안내를 냄).
    """
    if xtweet is None or xrelay is None:
        return False
    ck = None
    m = xrelay.YT_VIDEO_RE.search(xrelay.normalize(raw))
    if m:
        ck = _channel_key_by_video(m.group(1))
    if ck:
        return _ingest_personal_row(gh, channels_cfg, raw, ck, now_iso)
    _ask_member(gh, raw, now_iso)
    return True


def _handle_member_followup(gh, channels_cfg: dict, now_iso: str, text: str) -> bool:
    """`pending_member` 슬롯이 살아있을 때 (1~5 / 이름 / 취소 / 다른 명령) 응답을 소비.

    반환:
      True  — 이 메시지를 유닛 되묻기가 소진함 (웹훅 즉시 200, 명령 디스패치 안 함)
      False — 소진 안 함 (만료됐거나 다른 `/명령` — 정상 디스패치로 흘려보냄)
    """
    if admin is None:
        return False
    try:
        state, _ = gh.read_json(_ADMIN_STATE_PATH)
    except Exception:
        log.warning("admin_state.json 조회 실패 — 유닛 되묻기 후속 스킵")
        return False
    pending = admin.get_pending_member(state)
    if not pending:
        return False

    def _clear() -> None:
        try:
            st, sh = gh.read_json(_ADMIN_STATE_PATH)
            gh.write_json(
                _ADMIN_STATE_PATH,
                admin.clear_pending_member(st or admin.default_admin_state()),
                prev_sha=sh, message=f"data: pending_member 슬롯 정리 {now_iso}",
            )
        except Exception:
            log.exception("pending_member 슬롯 정리 실패")

    if admin.pending_member_expired(pending, now_iso):
        _clear()
        _send_telegram("⏱ 유닛 선택 시간(5분)이 지나 취소되었습니다.")
        return False

    t = (text or "").strip()
    if t == _INGEST_CANCEL_TOKEN:
        _clear()
        _send_telegram("🚫 ingest가 취소되었습니다.")
        return True
    if t.startswith("/"):
        _clear()
        _send_telegram("ℹ️ 유닛 되묻기를 취소하고 입력한 명령을 실행합니다.")
        return False
    ck = _MEMBER_CHOICE.get(t) or _MEMBER_CHOICE.get(t.lower())
    if not ck:
        _send_telegram(
            "⚠️ 1~5 숫자나 멤버 이름으로 답해주세요. (취소: <code>aNoneTokyo</code>)\n"
            + _MEMBER_PROMPT
        )
        return True                        # 슬롯 유지 — 다시 입력받는다
    raw = pending.get("raw") or ""
    _clear()
    if not raw:
        _send_telegram("⚠️ 저장된 예고 원문이 없습니다 — /ingest 부터 다시 해주세요.")
        return True
    _send_telegram("📥 예고 원문 반영 중…")
    _ingest_personal_row(gh, channels_cfg or _load_channels_config(), raw, ck, now_iso)
    return True


def _handle_manual_ingest(gh, channels_cfg: dict, now_iso: str, raw: str) -> None:
    """예고 트윗 원문 → 폰 자동 릴레이와 동일 파싱·반영 경로를 수동으로 실행.

    `/ingest`(무인자) 후 후속 메시지/파일로 받은 원문을 `_handle_ingest_followup`
    이 넘겨준다. (인라인 `/ingest <원문>` 은 v2.5.1 에서 제거 — 텔레그램 클라이언트의
    `||스포일러||` 마스킹이 명령행 텍스트를 변형시키던 문제 회피.)

    @BDP 일일 스케줄/`出演情報` 형식이 아니면 멤버 개인 예고 트윗으로 보고
    `_try_personal_ingest`(본문 YT URL → 채널 판별)로 한 번 더 시도한다.
    """
    try:
        if xrelay is None:
            _send_telegram("⚠️ xrelay 모듈을 불러올 수 없습니다.")
            return
        control, _ = gh.read_json("control.json")
        if is_paused(control or default_control()):
            _send_telegram("⏸ 일시정지 중 — /ingest 무시", silent=True)
            return

        _drain = writeclient.call_write("ingest_queue_drain", gh=gh, now_iso=now_iso, label="큐 반영")
        drained, drained_rows = _drain.get("applied", 0), _drain.get("rows", 0)
        rows = xrelay.parse(raw, now_iso)
        rows = _confirm_relay_rows_collab(gh, raw, rows, channels_cfg, now_iso, via="ops")
        failed = xrelay.unparsed_lines(raw)
        if not rows:
            # @BDP 형식이 아니고 인식 실패 줄도 없으면 멤버 개인 예고일 수 있다 —
            # 본문 YT URL 로 채널 판별(못 정하면 유닛 되묻기) 후 xtweet.parse_schedule.
            if not failed and _try_personal_ingest(gh, channels_cfg, raw, now_iso):
                if drained:
                    _send_telegram(
                        f"📥 대기열 {drained}건({drained_rows}행)도 반영됨", silent=True
                    )
                return
            if failed:
                msg = (
                    f"⚠️ /ingest: 스케줄 트윗이나 {len(failed)}줄 모두 인식 실패\n"
                    + _failed_lines_block(failed)
                )
            else:
                msg = "ℹ️ /ingest: 스케줄/출연 형식 아님 — 무시\n" + raw[:200]
            if drained:
                msg += f"\n📥 대기열 {drained}건({drained_rows}행) 반영됨"
            _send_telegram(msg, silent=not drained)
            return

        changed = writeclient.call_write(
            "merge_rows", gh=gh, rows=rows, now_iso=now_iso,
            message=f"data: telegram /ingest {now_iso}",
            action=f"/ingest {raw[:40].strip()}",
        ).get("changed")
        channels_cfg = channels_cfg or _load_channels_config()
        summary = xrelay.summary_text(rows, channels_cfg)
        if failed:
            summary += (
                f"\n\n⚠️ 인식 실패 {len(failed)}줄 (반영 안 됨):\n"
                + _failed_lines_block(failed)
            )
        if drained:
            summary += f"\n\n📥 대기열 {drained}건({drained_rows}행)도 함께 반영"
        if changed:
            summary += "\n\n↩️ /undo 로 되돌릴 수 있습니다."
        _send_telegram(summary)
    except Exception as e:
        log.exception("Error handling manual /ingest")
        _send_telegram(f"⚠️ 오류: /ingest 처리 실패\n{str(e)[:100]}")


# ── (v2.7) 소식 게시판 — /notice /notice-del /notice-list + 자동 인입 ──────────


def _notice_label(prepared: dict | None) -> str:
    """(v3.8.4) `apply_notice` 대기/완료 DM 태그용 — 제목이 있으면 그걸로, 없으면 빈 문자열
    (call_write 가 빈 label 은 태그를 안 붙임)."""
    prepared = prepared or {}
    title = ((prepared.get("tl") or {}).get("title_ko")
             or (prepared.get("parsed") or {}).get("title") or "")
    return f"소식 {title}".strip()[:40]


_NOTICE_PROMPT = (
    "📝 <b>/notice 대기 중</b> (3분)\n"
    "소식으로 올릴 트윗 원문(또는 /ingest 릴레이 DM)을 붙여넣거나 텍스트 파일을 올려주세요.\n"
    "취소: <code>aNoneTokyo</code>"
)


def _prepare_notice(raw: str, now_iso: str, *, tag=None, title=None, gh=None) -> dict | None:
    """(WP-3a) 소식 준비 (제어 채널에서 실행).

    외부 호출(비전 OCR·LLM) + 중복판정까지 한 뒤 결과를 반환.
    반환: {"parsed": dict, "tl": dict|None, "dup_id": str|None} | None
    """
    if xnotice is None or notices is None:
        return None
    parsed = xnotice.parse(raw, now_iso, tag=tag, title=title)
    if not parsed:
        return None

    # 1. 크로스오버 출연진 비전 OCR
    _maybe_tag_cast_participants(parsed, tag)

    # 2. 제목추출·번역 (재시도와 무관하게 한 번만)
    tl = None
    if not parsed.get("title_ko"):
        tl = _inline_notice_title(
            parsed.get("body_for_llm") or parsed.get("body_raw") or parsed.get("title"))

    # 3. 중복판정 사전 계산
    dup_id = None
    if gh is not None:
        try:
            prev, _ = gh.read_json(_NOTICES_PATH)
            arch, _ = gh.read_json(_NOTICE_ARCHIVE_PATH)
            prev = prev or notices.default_notices()
            arch = arch or notices.default_archive()

            # 사본으로 merge_notice 호출 (인자 변형 방지)
            prev_copy = copy.deepcopy(prev)
            arch_copy = copy.deepcopy(arch)
            parsed_copy = copy.deepcopy(parsed)
            new_n, new_a, changed, mode = notices.merge_notice(
                prev_copy, parsed_copy, now_iso, archive=arch_copy)

            # changed and mode == "added" 일 때만 중복판정 LLM 호출
            if changed and mode == "added":
                dup_id = _inline_notice_dup_check(parsed, prev)
        except Exception:
            log.warning("준비: notices 읽기 실패", exc_info=True)
            dup_id = None

    return {
        "parsed": parsed,
        "tl": tl,
        "dup_id": dup_id,
    }


def _prepare_personal_tweet(raw: str, *, title: str, tag: str | None, channel_key: str, now_iso: str,
                            vx_extract: dict | None = None, gh: GitHubStore | None = None) -> dict | None:
    """(WP-3b) 개인 트윗 준비 (제어 채널에서 실행).

    외부 호출(vxtwitter·LLM) + 머지 변화 판정까지 한 뒤 결과를 반환.
    반환: {"parsed": dict, "text_src": str, "text_ko": str|None, "quote_src": str|None, "quote_ko": str|None} | None
    """
    if xtweet is None:
        return None
    channels_cfg = _load_channels_config()
    handle = channels_cfg.get("channels", {}).get(channel_key, {}).get("handle", "")
    media, quote = _enrich_personal_media(tag, prefetched=vx_extract)
    parsed = xtweet.parse(raw, title=title, tag=tag, channel_key=channel_key,
                          now_iso=now_iso, handle=handle, media=media, quote=quote)
    if not parsed:
        return None

    # 변화 판정: gh가 있으면 current snapshot으로 merge 검사
    changed = True  # gh 없으면 안전한 기본값(번역 진행)
    new_t, new_a = None, None
    if gh is not None:
        try:
            prev, _ = gh.read_json(_TWEETS_PATH)
            arch, _ = gh.read_json(_TWEET_ARCHIVE_PATH)
            prev = prev or xtweet.default_tweets()
            arch = arch or xtweet.default_archive()

            # 사본으로 merge_thread 호출 (인자 변형 방지)
            prev_copy = copy.deepcopy(prev)
            arch_copy = copy.deepcopy(arch)
            parsed_copy = copy.deepcopy(parsed)
            new_t, new_a, changed, mode = xtweet.merge_thread(prev_copy, parsed_copy, now_iso, archive=arch_copy)
        except Exception:
            log.warning("준비: tweets 읽기 실패", exc_info=True)
            changed = True  # 읽기 실패 → 안전한 기본값(번역 진행)

    text_src = parsed.get("text") or ""
    text_ko = None
    quote_src = None
    quote_ko = None

    # changed 일 때만 번역
    if changed:
        if text_src and not parsed.get("text_ko"):
            text_ko = _inline_translate(text_src)

        # 인용
        quote_src = (parsed.get("quote") or {}).get("text")
        if quote_src:
            quote_ko = xtweet.find_reused_ko(quote_src, tweets_data=new_t, archive_data=new_a)
            if not quote_ko:
                try:
                    nj, _ = gh.read_json(_NOTICES_PATH)
                    quote_ko = xtweet.find_reused_ko(quote_src, notices_data=nj)
                except Exception:
                    pass
            if not quote_ko:
                quote_ko = _inline_translate(quote_src)

    return {
        "parsed": parsed,
        "text_src": text_src,
        "text_ko": text_ko,
        "quote_src": quote_src,
        "quote_ko": quote_ko,
    }


def _commit_notice(gh, prepared: dict | None, now_iso: str) -> tuple[str, dict | None]:
    """(WP-3a) 소식 커밋 (백엔드 잡에서 실행).

    준비된 소식을 notices.json 에 반영.
    반환: (mode, parsed)
    """
    if xnotice is None or notices is None or prepared is None:
        return "none", None

    parsed = prepared.get("parsed")
    tl = prepared.get("tl")
    dup_id = prepared.get("dup_id")

    for _try in (1, 2):
        prev, psha = gh.read_json(_NOTICES_PATH)
        arch, asha = gh.read_json(_NOTICE_ARCHIVE_PATH)
        prev = prev or notices.default_notices()
        arch = arch or notices.default_archive()
        new_n, new_a, changed, mode = notices.merge_notice(prev, parsed, now_iso, archive=arch)
        if not changed:
            return mode, parsed

        # (v3.7) LLM 판정으로 중복 찾았으면 즉시 병합
        if mode == "added" and dup_id:
            merged, found = notices.merge_into(prev, dup_id, parsed, now_iso)
            if found:
                new_n, mode = merged, "updated"

        # 방금 병합된 소식 행에 번역 반영
        row = next((n for n in new_n.get("notices", [])
                    if parsed.get("id") == n.get("id")
                    or parsed.get("id") in (n.get("seen_ids") or [])), None)
        if row and not row.get("title_ko"):
            if tl and tl.get("title_ko"):
                row["title"] = tl.get("title_ja") or row.get("title")
                row["title_ko"] = tl["title_ko"]
                row.pop("needs_tl", None)
            else:
                row["needs_tl"] = True

        try:
            _, nsha = gh.write_json(_NOTICES_PATH, new_n, prev_sha=psha,
                                    message=f"data: notice {mode} {now_iso}")
            if new_a is not arch:
                gh.write_json(_NOTICE_ARCHIVE_PATH, new_a, prev_sha=asha,
                              message=f"data: notice archive {now_iso}")
        except ConflictError:
            if _try == 2:
                raise
            log.warning("notice: notices.json 충돌 — 재시도")
            continue
        if mode in ("added", "updated"):
            _save_undo(gh, action=f"소식 {mode} ({(parsed.get('title') or '')[:30]})",
                       prev_content=prev, new_sha=nsha, now_iso=now_iso, path=_NOTICES_PATH)
        return mode, parsed
    return "error", parsed


def _commit_personal_tweet(gh, prepared: dict | None, *, channel_key: str, now_iso: str,
                           via: str = "ingest") -> dict:
    """(WP-3b) 개인 트윗 커밋 (백엔드 잡에서 실행).

    준비된 개인 트윗을 tweets.json에 반영.
    반환: {"mode": str, "n_thread": int, "needs_tl": bool}
    """
    if xtweet is None or prepared is None:
        return {"mode": "none", "n_thread": 0, "needs_tl": False}

    parsed = prepared.get("parsed")
    text_src = prepared.get("text_src", "")
    text_ko = prepared.get("text_ko")
    quote_src = prepared.get("quote_src")
    quote_ko = prepared.get("quote_ko")

    if not parsed:
        return {"mode": "none", "n_thread": 0, "needs_tl": False}

    row = None
    try:
        for _try in (1, 2):
            prev, psha = gh.read_json(_TWEETS_PATH)
            arch, asha = gh.read_json(_TWEET_ARCHIVE_PATH)
            prev = prev or xtweet.default_tweets()
            arch = arch or xtweet.default_archive()
            new_t, new_a, changed, mode = xtweet.merge_thread(prev, parsed, now_iso, archive=arch)
            if not changed:
                n_thread = len(_tw_list(new_t.get("tweets", {}).get(channel_key)))
                return {"mode": mode, "n_thread": n_thread, "needs_tl": False}

            # 방금 들어온 메시지에 번역 반영
            row = next((m for m in _tw_list(new_t["tweets"].get(channel_key))
                        if str(m.get("id")) == str(parsed.get("id"))), None)
            if row:
                if text_ko and text_src and row["text"] == text_src:
                    row["text_ko"] = text_ko
                    row.pop("needs_tl", None)
                elif text_ko is None and text_src:
                    row["needs_tl"] = True

            # 인용(QRT) 카드 번역
            if row and quote_src and (row.get("quote") or {}).get("text"):
                if row["quote"].get("text") == quote_src:
                    if quote_ko:
                        row["quote"]["text_ko"] = quote_ko
                        row["quote"].pop("needs_tl", None)
                    else:
                        row["quote"]["needs_tl"] = True

            try:
                gh.write_json(_TWEETS_PATH, new_t, prev_sha=psha,
                              message=f"data: tweet {mode} {channel_key} {now_iso}")
                if new_a is not arch:
                    gh.write_json(_TWEET_ARCHIVE_PATH, new_a, prev_sha=asha,
                                  message=f"data: tweet archive {now_iso}")
            except ConflictError:
                if _try == 2:
                    raise
                log.warning("tweet: tweets.json 충돌 — 재시도")
                continue
            break

        _tweet_sweep(gh, now_iso)  # 만료 슬롯 정리 (best-effort)
    except Exception:
        log.exception("personal tweet 반영 실패")
        try:
            log_event(gh, now_iso, "tweet", RESULT_ERR, who=channel_key, detail="mode: error (exception)", via=via)
        except Exception:  # noqa: BLE001
            log.warning("monitor_log 기록 실패(tweet)")
        return {"mode": "error", "n_thread": 0, "needs_tl": False}

    needs_tl = bool(row and (row.get("needs_tl") or (row.get("quote") or {}).get("needs_tl")))
    try:
        log_event(
            gh, now_iso, "tweet", RESULT_DEGRADED if needs_tl else RESULT_OK,
            who=channel_key, detail=f"mode: {mode}" + (", needs_tl=true" if needs_tl else ""), via=via,
        )
    except Exception:  # noqa: BLE001
        log.warning("monitor_log 기록 실패(tweet)")

    n_thread = len(_tw_list((new_t or {}).get("tweets", {}).get(channel_key)))
    return {"mode": mode, "n_thread": n_thread, "needs_tl": needs_tl}


def _notice_sweep(gh, now_iso: str) -> int:
    """expires_at 지난 소식 → notice_archive.json. 반환: 이관 건수 (best-effort)."""
    if notices is None:
        return 0
    try:
        prev, psha = gh.read_json(_NOTICES_PATH)
        if not prev or not prev.get("notices"):
            return 0
        arch, asha = gh.read_json(_NOTICE_ARCHIVE_PATH)
        new_n, new_a, moved = notices.sweep_expired(
            prev, arch or notices.default_archive(), now_iso)
        if not moved:
            return 0
        gh.write_json(_NOTICES_PATH, new_n, prev_sha=psha,
                      message=f"data: notice sweep ({len(moved)}) {now_iso}")
        gh.write_json(_NOTICE_ARCHIVE_PATH, new_a, prev_sha=asha,
                      message=f"data: notice archive sweep {now_iso}")
        return len(moved)
    except Exception:
        log.exception("notice sweep 실패 (무시)")
        return 0


def _notice_result_dm(mode: str, parsed: dict | None, raw: str) -> None:
    if mode == "none":
        _send_telegram("ℹ️ 날짜/시각 없음 또는 스케줄 형식 — 소식 등록 안 함.\n" + raw[:200])
    elif mode in ("dup", "skip"):
        _send_telegram("ℹ️ 이미 있는 소식이거나 지난 이벤트 후기 — 등록 안 함.")
    elif mode == "recap":
        _send_telegram("📎 지난 이벤트 후속으로 기록(게시판 노출 없음).")
    elif mode in ("added", "updated"):
        act = "추가" if mode == "added" else "갱신"
        _send_telegram(
            f"🆕 소식 {act}됨\n{notices.summary_line(parsed)}\n\n↩️ /undo 로 되돌릴 수 있습니다."
        )
    else:
        _send_telegram("⚠️ 소식 처리 실패.")


def _handle_notice_followup(gh, now_iso: str, message: dict, text: str) -> bool:
    """pending_notice 슬롯이 살아있을 때 온 메시지를 소식 원문/파일/취소로 소비.

    반환 True = 소진(웹훅 즉시 200). /ingest 후속과 같은 규칙.

    (WP-3a) 준비(외부 호출)와 커밋(쓰기)를 분리.
    """
    if admin is None or notices is None:
        return False
    try:
        state, _ = gh.read_json(_ADMIN_STATE_PATH)
    except Exception:
        log.warning("admin_state.json 조회 실패 — /notice 후속 스킵")
        return False
    pending = admin.get_pending_notice(state)
    if not pending:
        return False

    def _clear() -> None:
        try:
            st, sh = gh.read_json(_ADMIN_STATE_PATH)
            gh.write_json(_ADMIN_STATE_PATH,
                          admin.clear_pending_notice(st or admin.default_admin_state()),
                          prev_sha=sh, message=f"data: pending_notice 정리 {now_iso}")
        except Exception:
            log.exception("pending_notice 정리 실패")

    if admin.pending_notice_expired(pending, now_iso):
        _clear()
        _send_telegram("⏱ 이전 /notice 요청이 만료되어 취소되었습니다.")
        return False
    if text.strip() == _INGEST_CANCEL_TOKEN:
        _clear()
        _send_telegram("🚫 /notice 가 취소되었습니다.")
        return True
    if text.startswith("/"):
        _clear()
        _send_telegram("ℹ️ /notice 대기를 취소하고 입력한 명령을 실행합니다.")
        return False

    doc = (message or {}).get("document") or {}
    raw = ""
    if doc.get("file_id"):
        content = _download_telegram_file(doc["file_id"])
        if content is None:
            _send_telegram("⚠️ 파일을 읽지 못했습니다(256KB 이하 텍스트). 다시 보내주세요. (대기 유지)")
            return True
        raw = content.strip()
    elif text.strip():
        raw = text.strip()
    else:
        _send_telegram("⚠️ 트윗 원문 텍스트나 텍스트 파일을 보내주세요. (대기 유지)")
        return True

    _clear()
    _send_telegram("📥 접수했습니다. 반영 중…")

    # 준비 단계: 파싱 + LLM + 중복판정
    prepared = _prepare_notice(raw, now_iso, gh=gh)
    if prepared is None:
        _notice_result_dm("none", None, raw)
        return True

    try:
        writeclient.call_write("notice_sweep", gh=gh, now_iso=now_iso, label="소식정리")
        result = writeclient.call_write("apply_notice", gh=gh, prepared=prepared, now_iso=now_iso,
                                        label=_notice_label(prepared))
        mode, parsed = result.get("mode"), result.get("parsed")
    except Exception as e:
        log.exception("Error handling /notice")
        _send_telegram(f"⚠️ 오류: /notice 처리 실패\n{str(e)[:100]}")
        return True
    _notice_result_dm(mode, parsed, raw)
    return True


def _notice_del_commit(gh, nid_or_idx: str, now_iso: str) -> dict:
    """(write-queue) /notice-del 실제 반영 — id/번호 해석 + 삭제 + undo 스냅샷을 한 job 으로.

    `nid_or_idx` 는 호출부(운영자 명령)가 그 순간 받은 인자 그대로 — 큐 대기 중에
    notices.json 이 바뀌었을 가능성이 있으므로 번호→id 해석은 여기(커밋 시점)에서 한다.
    """
    prev, psha = gh.read_json(_NOTICES_PATH)
    prev = prev or notices.default_notices()
    lst = prev.get("notices", []) or []
    nid = nid_or_idx
    if nid.isdigit() and 1 <= int(nid) <= len(lst):
        nid = lst[int(nid) - 1].get("id")
    new_n, removed = notices.remove_notice(prev, nid)
    if not removed:
        return {"removed": False, "nid": nid}
    _, nsha = gh.write_json(_NOTICES_PATH, new_n, prev_sha=psha,
                            message=f"data: notice del {now_iso}")
    _save_undo(gh, action=f"소식 삭제 ({nid})", prev_content=prev, new_sha=nsha,
               now_iso=now_iso, path=_NOTICES_PATH)
    return {"removed": True, "nid": nid}


def _handle_notice_del(gh, now_iso: str, arg: str) -> None:
    """/notice-del <id | 번호> — 소식 1건 제거 (+ /undo 스냅샷)."""
    if notices is None:
        _send_telegram("⚠️ notices 모듈 없음")
        return
    nid_arg = (arg or "").strip()
    if not nid_arg:
        _send_telegram("사용법: /notice-del &lt;id | 번호&gt;  (/notice-list 로 확인)")
        return
    try:
        result = writeclient.call_write("notice_del_commit", gh=gh, nid=nid_arg, now_iso=now_iso,
                                        label=f"소식삭제 {nid_arg}")
        if not result.get("removed"):
            _send_telegram(f"해당 소식이 없습니다: {html.escape(result.get('nid') or nid_arg)}")
            return
        _send_telegram(f"🗑 소식 삭제됨 (<code>{html.escape(result['nid'])}</code>). /undo 로 되돌릴 수 있습니다.")
    except Exception as e:
        log.exception("notice-del")
        _send_telegram(f"⚠️ 오류: /notice-del 실패\n{str(e)[:100]}")


def _handle_notice_list(gh, now_iso: str) -> None:
    if notices is None:
        _send_telegram("⚠️ notices 모듈 없음")
        return
    try:
        writeclient.call_write("notice_sweep", gh=gh, now_iso=now_iso, label="소식정리")
        prev, _ = gh.read_json(_NOTICES_PATH)
        lst = (prev or {}).get("notices", []) or []
        if not lst:
            _send_telegram("📋 소식 없음.")
            return
        lines = [f"📋 <b>소식 {len(lst)}건</b>"]
        for i, n in enumerate(lst, 1):
            lines.append(f"{i}. <code>{html.escape(n.get('id') or '')}</code> "
                         f"{html.escape(notices.summary_line(n))}")
        _send_telegram("\n".join(lines))
    except Exception as e:
        log.exception("notice-list")
        _send_telegram(f"⚠️ 오류: /notice-list 실패\n{str(e)[:100]}")


# ── (v2.7.x) /notice-edit — title→date→url 순 되묻기 마법사 ───────────────────
_NOTICE_EDIT_STEPS = ("title", "date", "url")
_NOTICE_EDIT_KEEP = _INGEST_CANCEL_TOKEN          # aNoneTokyo → 그 필드 유지
_NOTICE_EDIT_LABEL = {"title": "제목", "date": "날짜 (YYYY-MM-DD 또는 11/21)", "url": "URL"}


def _notice_edit_prompt(step: str, row: dict) -> str:
    cur = {"title": row.get("title"), "date": row.get("date"), "url": row.get("url")}[step]
    n = _NOTICE_EDIT_STEPS.index(step) + 1
    return (f"{n}/3 새 {_NOTICE_EDIT_LABEL[step]} 를 입력하세요.\n"
            f"현재: <code>{html.escape(str(cur) if cur else '(없음)')}</code>\n"
            f"(유지하려면 <code>{_NOTICE_EDIT_KEEP}</code> · 취소하려면 다른 /명령)")


def _notice_edit_apply_value(step: str, value: str, new: dict) -> tuple[bool, str]:
    """단계 입력값 검증 후 `new[step]` 채움. (ok, err_msg)."""
    v = (value or "").strip()
    if step == "title":
        if len(v) < 2:
            return False, "제목이 너무 짧습니다."
        new["title"] = v[:90]
        return True, ""
    if step == "date":
        iso = None
        m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$", v)
        if m:
            try:
                iso = datetime(int(m[1]), int(m[2]), int(m[3])).strftime("%Y-%m-%d")
            except ValueError:
                iso = None
        if not iso and xnotice is not None:
            now_jst = datetime.now(timezone.utc).astimezone(xnotice.JST)
            iso, _dl = xnotice._pick_event_date(xnotice.normalize(v), now_jst)
        if not iso:
            return False, "날짜를 못 읽었습니다 (YYYY-MM-DD 또는 11/21 형식)."
        new["date"] = iso
        return True, ""
    if step == "url":
        if not v.startswith("http"):
            v = "https://" + v.lstrip("/")
        new["url"] = v
        return True, ""
    return False, "알 수 없는 단계."


def _notice_edit_finalize(new: dict, row: dict, now_iso: str) -> dict:
    """마법사가 모은 값 → 실제 patch (바뀐 필드 + 파생값만)."""
    patch: dict = {}
    if new.get("title") and new["title"] != row.get("title"):
        patch["title"] = new["title"]
        if xnotice is not None:
            patch["title_slug"] = xnotice._title_slug(new["title"])
    if new.get("date") and new["date"] != row.get("date"):
        patch["date"] = new["date"]
        if xnotice is not None:
            now_jst = datetime.now(timezone.utc).astimezone(xnotice.JST)
            patch["expires_at"] = xnotice._expires_at(
                new["date"], row.get("time"), now_iso, now_jst)
    if new.get("url") and new["url"] != row.get("url"):
        patch["url"] = new["url"]
        if xnotice is not None:
            site, u, anchor_a = xnotice._site_url_anchor(new["url"])
            patch["url"] = u or new["url"]
            patch["site"] = site
            patch["anchor_a"] = anchor_a
    return patch


def _handle_notice_edit(gh, now_iso: str, arg: str) -> None:
    """/notice-edit <id | 번호> — 편집 마법사 시작 (title → date → url 순 되묻기)."""
    if notices is None or xnotice is None or admin is None:
        _send_telegram("⚠️ notice/admin 모듈 없음 — /notice-edit 사용 불가")
        return
    key = (arg or "").strip().split()[0] if (arg or "").strip() else ""
    if not key:
        _send_telegram("사용법: /notice-edit &lt;id | 번호&gt;  (/notice-list 로 확인)")
        return
    try:
        prev, _ = gh.read_json(_NOTICES_PATH)
        lst = (prev or {}).get("notices", []) or []
        if key.isdigit() and 1 <= int(key) <= len(lst):
            row = lst[int(key) - 1]
        else:
            row = next((n for n in lst if n.get("id") == key), None)
        if not row:
            _send_telegram(f"해당 소식이 없습니다: {html.escape(key)}")
            return
        nid = row.get("id")
        st, sh = gh.read_json(_ADMIN_STATE_PATH)
        gh.write_json(
            _ADMIN_STATE_PATH,
            admin.set_pending_notice_edit(
                st or admin.default_admin_state(), nid=nid, step="title", new={}, now_iso=now_iso),
            prev_sha=sh, message=f"data: pending_notice_edit 시작 {now_iso}",
        )
        _send_telegram(
            "✏️ <b>소식 편집</b> — " + html.escape(notices.summary_line(row)) + "\n\n"
            + _notice_edit_prompt("title", row)
        )
    except Exception as e:
        log.exception("notice-edit")
        _send_telegram(f"⚠️ 오류: /notice-edit 실패\n{str(e)[:100]}")


def _notice_edit_commit(gh, nid: str, patch: dict, now_iso: str) -> dict:
    """(write-queue) /notice-edit 최종 커밋 — 호출부(마법사)가 이미 확정한 `nid`/`patch`
    그대로 반영(재시도 2회) + undo 스냅샷. 대상 재해석 없음 — patch 자체가 대상+변경분."""
    for _try in (1, 2):
        prevn, psha = gh.read_json(_NOTICES_PATH)
        new_n, changed = notices.edit_notice(
            prevn or notices.default_notices(), nid, patch, now_iso)
        if not changed:
            return {"changed": False}
        try:
            _, nsha = gh.write_json(_NOTICES_PATH, new_n, prev_sha=psha,
                                    message=f"data: notice edit {nid} {now_iso}")
        except ConflictError:
            if _try == 2:
                raise
            log.warning("notice-edit: notices.json 충돌 — 재시도")
            continue
        _save_undo(gh, action=f"소식 편집 ({nid})", prev_content=prevn or {},
                   new_sha=nsha, now_iso=now_iso, path=_NOTICES_PATH)
        row2 = next((n for n in (new_n or {}).get("notices", []) if n.get("id") == nid), None)
        return {"changed": True, "row": row2}
    return {"changed": False}


def _handle_notice_edit_followup(gh, now_iso: str, text: str) -> bool:
    """`pending_notice_edit` 슬롯이 살아있을 때 각 단계 응답(값 / aNoneTokyo / /명령)을 소비.

    반환: True = 소진(웹훅 즉시 200) · False = 만료/타 명령 → 정상 디스패치로 통과.
    """
    if admin is None or notices is None:
        return False
    try:
        state, _ = gh.read_json(_ADMIN_STATE_PATH)
    except Exception:
        log.warning("admin_state.json 조회 실패 — /notice-edit 후속 스킵")
        return False
    pending = admin.get_pending_notice_edit(state)
    if not pending:
        return False

    def _clear() -> None:
        try:
            st, sh = gh.read_json(_ADMIN_STATE_PATH)
            gh.write_json(_ADMIN_STATE_PATH,
                          admin.clear_pending_notice_edit(st or admin.default_admin_state()),
                          prev_sha=sh, message=f"data: pending_notice_edit 정리 {now_iso}")
        except Exception:
            log.exception("pending_notice_edit 정리 실패")

    if admin.pending_notice_edit_expired(pending, now_iso):
        _clear()
        _send_telegram("⏱ /notice-edit 시간(5분)이 지나 취소되었습니다.")
        return False
    t = (text or "").strip()
    if t.startswith("/"):
        _clear()
        _send_telegram("ℹ️ /notice-edit 를 취소하고 입력한 명령을 실행합니다.")
        return False

    nid = pending.get("nid")
    step = pending.get("step") or "title"
    new = dict(pending.get("new") or {})
    try:
        prev, _ = gh.read_json(_NOTICES_PATH)
    except Exception:
        _clear()
        _send_telegram("⚠️ notices.json 조회 실패 — /notice-edit 취소")
        return True
    row = next((n for n in (prev or {}).get("notices", []) or [] if n.get("id") == nid), None)
    if not row:
        _clear()
        _send_telegram("⚠️ 편집하려던 소식이 사라졌습니다 — /notice-edit 취소")
        return True

    if t != _NOTICE_EDIT_KEEP:
        ok, err = _notice_edit_apply_value(step, t, new)
        if not ok:
            _send_telegram(f"⚠️ {err} 다시 입력하세요. (유지: <code>{_NOTICE_EDIT_KEEP}</code>)")
            return True

    idx = _NOTICE_EDIT_STEPS.index(step)
    if idx + 1 < len(_NOTICE_EDIT_STEPS):
        nxt = _NOTICE_EDIT_STEPS[idx + 1]
        try:
            st, sh = gh.read_json(_ADMIN_STATE_PATH)
            gh.write_json(
                _ADMIN_STATE_PATH,
                admin.set_pending_notice_edit(
                    st or admin.default_admin_state(), nid=nid, step=nxt, new=new, now_iso=now_iso),
                prev_sha=sh, message=f"data: pending_notice_edit {nxt} {now_iso}")
        except Exception:
            log.exception("pending_notice_edit 단계 저장 실패")
            _clear()
            _send_telegram("⚠️ 상태 저장 실패 — /notice-edit 를 다시 시작하세요.")
            return True
        _send_telegram(_notice_edit_prompt(nxt, row))
        return True

    # 마지막 단계 완료 → 파생값 계산 + 커밋
    _clear()
    patch = _notice_edit_finalize(new, row, now_iso)
    if not patch:
        _send_telegram("변경 사항이 없습니다 — 소식은 그대로입니다.")
        return True
    try:
        result = writeclient.call_write("notice_edit_commit", gh=gh, nid=nid, patch=patch, now_iso=now_iso,
                                        label=f"소식수정 {nid}")
        if not result.get("changed"):
            _send_telegram("변경 사항이 없습니다 — 소식은 그대로입니다.")
            return True
        row2 = result.get("row") or row
        _send_telegram("✏️ 소식 수정됨 — " + html.escape(notices.summary_line(row2))
                       + "\n↩️ /undo 로 되돌릴 수 있습니다.")
    except Exception as e:
        log.exception("notice-edit 커밋 실패")
        _send_telegram(f"⚠️ 오류: /notice-edit 반영 실패\n{str(e)[:100]}")
    return True


def _maybe_auto_notice(raw: str, now_iso: str, *, tag=None, title=None) -> str:
    """(v2.7) 소식 자동 인입 — INGEST_ECHO/DRY-RUN 과 **무관하게** 별개로 돈다.

    파싱(순수)이 소식이 아니면 GitHub 은 아예 안 건드린다. 반환: mode 문자열(로그용).
    added/updated 만 운영자 DM.

    (WP-3a) 준비(외부 호출)와 커밋(쓰기)를 분리.
    """
    if not raw or xnotice is None or notices is None:
        return "none"

    gh = _make_gh()
    if gh is None:
        return "no-gh"

    # 준비 단계: 파싱 + LLM + 중복판정
    prepared = _prepare_notice(raw, now_iso, tag=tag, title=title, gh=gh)
    if prepared is None:
        return "none"

    try:
        writeclient.call_write("notice_sweep", gh=gh, now_iso=now_iso, label="소식정리")
        result = writeclient.call_write("apply_notice", gh=gh, prepared=prepared, now_iso=now_iso,
                                        label=_notice_label(prepared))
        mode, parsed = result.get("mode"), result.get("parsed")
    except Exception:
        log.exception("auto notice 실패")
        try:
            log_event(gh, now_iso, "notice", RESULT_ERR, detail="mode: error (exception)", via="ingest")
        except Exception:  # noqa: BLE001
            log.warning("monitor_log 기록 실패(notice)")
        return "error"
    try:
        log_event(gh, now_iso, "notice", RESULT_OK, detail=f"mode: {mode}", via="ingest")
    except Exception:  # noqa: BLE001
        log.warning("monitor_log 기록 실패(notice)")
    if mode in ("added", "updated") and _auto_dm_allows(gh, "notice"):
        _notice_result_dm(mode, parsed, raw)
    else:
        log.info("auto notice: %s (조용히, mode=%s)", "gated" if mode in ("added", "updated") else "", mode)
    return mode


# ── (v2.8) 멤버 개인 트윗 — tweets.json 만 건드린다. notice/schedule 무관 ──────────

def _inline_translate(text: str) -> Optional[str]:
    """자동 인입 트윗 인라인 번역. 실패하면 None → 호출부가 `needs_tl` 로 큐잉해
    다음 `/tick` 의 `handlers._translate_sweep` 가 재시도. (버그리포트 20260910 #4)"""
    if not text or not text.strip():
        return None
    llm = _make_llm_client()
    if llm is None:
        return None
    try:
        return llm.translate(text) or None
    except Exception:
        log.exception("인라인 번역 실패")
        return None


def _inline_notice_title(body: str):
    """자동 인입 소식 인라인 제목추출·번역 → {title_ja, title_ko} | None.
    실패하면 None → 호출부가 `needs_tl` 로 큐잉, 다음 tick sweep 가 재시도. (v3.1.2)"""
    if not body or not body.strip():
        return None
    llm = _make_llm_client()
    if llm is None:
        return None
    try:
        return llm.notice_title(body) or None
    except Exception:
        log.exception("인라인 소식 제목/번역 실패")
        return None


def _inline_notice_dup_check(parsed: dict, prev: dict) -> str | None:
    """(v3.7) 같은 날짜(threshold=0일)의 기존 소식과 LLM 으로 의미상 중복 판정.

    같은 이름의 행사가 여러 날에 걸쳐 진행돼도(예: 3일 연속 페스티벌) 일차마다 다른
    소식일 수 있어 날짜가 다르면 애초에 비교 후보에 안 넣는다. 실패/미설정/후보없음/
    판정없음이면 전부 None(호출부는 새 소식으로 등록 — 안전한 기본값)."""
    date = parsed.get("date")
    if not date:
        return None
    candidates = [
        {"id": n.get("id"), "text": n.get("body_raw") or n.get("title") or ""}
        for n in (prev.get("notices") or [])
        if n.get("date") == date and n.get("id")
    ]
    if not candidates:
        return None
    llm = _make_llm_client()
    if llm is None:
        return None
    try:
        return llm.duplicate_notice(parsed.get("body_raw") or parsed.get("title") or "", candidates)
    except Exception:
        log.exception("소식 중복판정 실패")
        return None


# 웹푸시 알림이 긴 URL 을 …/... 로 잘라 보낸 흔적 — 11자 영상 ID 를 못 뽑는 경우.
_TRUNC_YT_RE = re.compile(r"(?:youtube\.com|youtu\.be)/\S*?(?:…|\.\.\.)")

def _recover_raw_via_vxtwitter(raw: str, tag: str | None) -> tuple[str, dict | None]:
    """tweet id 가 있으면 vxtwitter 원문을 raw 보다 우선한다 — 실패 시에만 raw 폴백.

    (버그리포트 20260913 #2) 폰(Automate)이 안드로이드 알림의 "축약본"(contentText) 만
    읽고 "전체본"(bigText)을 못 읽는 경우가 있다 — 이땐 말줄임표(…)도 손상 문자도 없이
    완결된 문장처럼 보이는 상태로 조용히 잘려서 온다(예: 문단 3개짜리 트윗이 전체 9개
    문단 중 앞 3개만 옴). 이런 "조용한 잘림"은 텍스트만 봐서는 감지할 방법이 없으므로,
    감지 후 복구가 아니라 **tweet id 가 있으면 항상 vxtwitter 를 정본으로 우선** 조회한다.
    tweet id 없음 · vxtwitter 모듈/조회 실패 · 응답에 text 없음 → raw 그대로(무회귀,
    보정 전보다 나빠지지 않음).

    반환: (text, extract_dict|None) — extract_dict 는 이미 조회한 vxtwitter JSON 을
    `vxtwitter.extract()` 한 결과(media/qrt_url 포함)라 (v3.4.5) `_enrich_personal_media` 가
    개인 트윗에서 **재조회 없이** 재사용한다(같은 tweet id 를 이 요청 안에서 두 번 안 때림).
    """
    if not raw or vxtwitter is None or xtweet is None:
        return raw, None
    tid = xtweet._tweet_id(tag) if tag else ""
    if not tid or not tid.isdigit():
        return raw, None
    j = vxtwitter.fetch_tweet(tid)
    ex = vxtwitter.extract(j) if j else None
    text = ex.get("text") if ex else None
    if not text:
        log.warning("ingest: vxtwitter 원문 조회 실패 — raw 폴백 (tweet %s)", tid)
        return raw, None
    if text != raw:
        log.info("ingest: vxtwitter 원문으로 교체 (tweet %s, raw_len=%d vx_len=%d)",
                  tid, len(raw), len(text))
    return text, ex


def _expand_truncated_yt(raw: str, tag) -> str:
    """본문의 YouTube URL 이 `…`/`...` 로 잘렸으면 트윗 id(tag)로 vxtwitter unfurl 해
    온전한 watch URL 을 본문 끝에 덧붙인다. (버그리포트 20260910 #2)

    온전한 YT URL 이미 있음 · 잘린 흔적 없음 · tweet id 없음 · vxtwitter 모듈/조회
    실패 → raw 그대로(무회귀).
    """
    if not raw or vxtwitter is None or xrelay is None:
        return raw
    if xrelay.YT_VIDEO_RE.search(raw) or not _TRUNC_YT_RE.search(raw):
        return raw
    tid = xtweet._tweet_id(tag) if xtweet is not None else ""
    if not tid or not tid.isdigit():
        return raw
    j = vxtwitter.fetch_tweet(tid)
    vid = vxtwitter.extract(j).get("yt_video_id") if j else None
    if not vid:
        log.warning("잘린 YT URL 복원 실패 (tweet %s)", tid)
        return raw
    url = f"https://www.youtube.com/watch?v={vid}"
    log.info("잘린 YT URL 복원: %s (tweet %s)", url, tid)
    return raw.rstrip() + "\n" + url


def _enrich_personal_media(tag: str | None, *, prefetched: dict | None = None
                           ) -> tuple[list[str], dict | None]:
    """개인 트윗 id 로 vxtwitter 조회 — 본인 첨부 미디어 + 인용(QRT)한 남의 트윗 {text,media}.

    인용 트윗은 **표시만** 하고(말풍선에 카드로 실음) 예고 파싱 등 ingest 대상엔 안 넣는다.
    tweet id 없음·vxtwitter 모듈/조회 실패·인용 없음 → ([], None) 무회귀(배지·본문 표시는 그대로).

    `prefetched`: `_recover_raw_via_vxtwitter` 가 같은 tweet id 로 이미 받아온
    `vxtwitter.extract()` 결과 — 있으면 본인 트윗 재조회를 건너뛴다(같은 id 중복 fetch 방지).
    """
    if vxtwitter is None or xtweet is None or not tag:
        return [], None
    tid = xtweet._tweet_id(tag)
    if not tid or not tid.isdigit():
        return [], None
    if prefetched is not None:
        ex = prefetched
    else:
        j = vxtwitter.fetch_tweet(tid)
        if not j:
            return [], None
        ex = vxtwitter.extract(j)
    media = ex.get("media") or []
    quote = None
    # (v3.7.3) 응답에 인용 트윗 본문이 이미 실려 있으면 그것을 쓴다. 참조 트윗을 id 로 다시 조회하는 것은
    # 실려 있지 않을 때만 — vxtwitter 가 특정 참조 트윗을 영구 500 으로 못 주는 경우가 있다(2026-09-18 아라레).
    emb = ex.get("qrt")
    if emb:
        quote = {"text": emb.get("text") or "", "media": emb.get("media") or []}
    else:
        qid = vxtwitter.qrt_id(ex.get("qrt_url"))
        if qid:
            qj = vxtwitter.fetch_tweet(qid)
            qex = vxtwitter.extract(qj) if qj else {}
            if qex.get("text") or qex.get("media"):
                quote = {"text": qex.get("text") or "", "media": qex.get("media") or []}
    return media, quote


def _maybe_personal_tweet(raw: str, *, title: str, tag: str | None,
                          channel_key: str, now_iso: str,
                          vx_extract: dict | None = None, via: str = "ingest") -> str:
    """(WP-3b) 개인 트윗 인입 — 제어 채널 오케스트레이터.

    `_ingest` 3.5 라우팅이 개인 5인으로 판정하면 여기로.
    `/edit → tweet` 마법사(운영자가 원문을 직접 붙여넣는 수동 교체)도 같은 함수를 탄다.

    ECHO/DRY-RUN/paused 와 무관하게 실행(이 갈래에 온 시점에서 이미 개인 트윗). 반환: mode(로그용).
    파싱이 트윗이 아니면(본문 없음) GitHub 은 안 건드린다.

    `vx_extract`: `_ingest` 가 `_recover_raw_via_vxtwitter` 로 이미 조회해 둔 같은 tweet 의
    vxtwitter 결과 — 있으면 `_enrich_personal_media` 가 재조회 없이 재사용.
    `via`: 모니터링 로그용 트리거 구분 — "ingest"(X 웹훅 자동 인입, 기본값) | "ops"(운영자
    수동 편집). 자동/수동을 구분해서 보고 싶다는 요청(2026-09-16)으로 추가.
    """
    if xtweet is None:
        return "no-xtweet"

    gh = _make_gh()
    if gh is None:
        return "no-gh"

    # 준비 단계 (제어 채널)
    prepared = _prepare_personal_tweet(raw, title=title, tag=tag, channel_key=channel_key,
                                       now_iso=now_iso, vx_extract=vx_extract, gh=gh)
    if prepared is None:
        return "none"

    # 커밋 단계 (write-queue)
    try:
        res = writeclient.call_write("personal_tweet", gh=gh, prepared=prepared,
                                     channel_key=channel_key, now_iso=now_iso, via=via,
                                     label=f"{channel_key} 트윗")
        mode = res.get("mode", "error")
        n_thread = res.get("n_thread", 0)
    except Exception:
        log.exception("personal tweet write 호출 실패")
        try:
            log_event(gh, now_iso, "tweet", RESULT_ERR, who=channel_key,
                      detail="mode: error (/write 호출 실패)", via=via)
        except Exception:  # noqa: BLE001
            log.warning("monitor_log 기록 실패(tweet)")
        return "error"

    # DM 발송
    channels_cfg = _load_channels_config()
    name = channels_cfg.get("channels", {}).get(channel_key, {}).get("name_ko", channel_key)
    handle = channels_cfg.get("channels", {}).get(channel_key, {}).get("handle", "")
    parsed = prepared.get("parsed", {})
    if mode in ("added", "rolled"):
        _auto_dm(gh, "tweet",
                 f"🐦 <b>{html.escape(name)}</b> 새 트윗 (스레드 {n_thread}/{xtweet.MAX_THREAD})\n"
                 f"{html.escape(xtweet.summary_line(parsed))}")

    # (v2.8.1) 예고글이면 schedule.json 의 scheduled 행으로도 승격
    # (v3.8.5) 인용(QRT)한 트윗 본문도 같이 넘긴다 — URL이 인용 쪽에만 있는 경우 대응
    quote_src = (parsed.get("quote") or {}).get("text")
    _maybe_personal_schedule(raw, tag=tag, channel_key=channel_key, name=name,
                             handle=handle, now_iso=now_iso, via=via, quote=quote_src)
    # (v3.8.7) 기존 예고 취소/변경 여부는 새 예고 생성과 별개로 항상 확인
    _maybe_broadcast_change(gh, raw, channel_key, now_iso, channels_cfg, via=via)
    return mode


def _url_confirmed_commit(gh, video_id: str, new_item: dict, next_check_at: str | None,
                          host_key: str, now_iso: str, *, via: str = "ingest") -> dict:
    """(WP-3b) URL 확정 예고 커밋 (백엔드 잡에서 실행).

    preview.json 에 반영하고 필요시 Cloud Tasks wake enqueue.
    반환: {"changed": bool, "error": bool}
    """
    try:
        for attempt in (1, 2):
            prev, sha = gh.read_json(_PREVIEW_PATH)
            prev = prev or {"items": []}
            items, changed = xtweet.merge_video_confirmed(
                prev.get("items", []) or [], video_id, new_item, now_iso,
            )
            merged = dict(prev)
            merged["items"] = items
            merged["generated_at"] = now_iso
            try:
                _, new_sha = gh.write_json(
                    _PREVIEW_PATH, merged, prev_sha=sha,
                    message=f"data: personal url-schedule {host_key} {now_iso}",
                )
                break
            except ConflictError:
                if attempt == 2:
                    raise
                log.warning("URL 확정 예고: preview.json 충돌 — 재시도")
    except Exception:
        log.exception("URL 확정 예고 반영 실패")
        _log_event_safe(gh, now_iso, "tweet", RESULT_ERR, who=host_key,
                  detail="url-schedule write 실패 — 확정된 정보가 유실됨", via=via)
        return {"changed": False, "error": True}

    if changed:
        _save_undo(gh, action=f"URL 확정 예고 {host_key} ({video_id})",
                   prev_content=prev or {}, new_sha=new_sha, now_iso=now_iso)
        if next_check_at:
            _enqueue_wake_now(video_id, next_check_at)

    return {"changed": changed, "error": False}


def _commit_yt_member_live(gh, live: dict, now_iso: str, *, via: str = "ingest") -> dict:
    """(v3.7.3) 회원 전용 라이브 시작 알림 커밋 (백엔드 잡에서 실행).

    preview.json 에 반영(`xtweet.merge_member_live`) — 자리표시 승격 / 신규 생성 / 중복 no-op.
    반환: {"changed": bool, "mode": str, "error": bool}
    """
    ck = live.get("channel_key")
    try:
        for attempt in (1, 2):
            prev, sha = gh.read_json(_PREVIEW_PATH)
            prev = prev or {"items": []}
            prev_items = prev.get("items", []) or []
            items, changed, mode = xtweet.merge_member_live(prev_items, live, now_iso)
            if not changed:
                return {"changed": False, "mode": mode, "error": False}
            merged = dict(prev)
            merged["items"] = items
            merged["generated_at"] = now_iso
            try:
                _, new_sha = gh.write_json(
                    _PREVIEW_PATH, merged, prev_sha=sha,
                    message=f"data: member live {ck} {mode} {now_iso}",
                )
                break
            except ConflictError:
                if attempt == 2:
                    raise
                log.warning("회원 전용 라이브: preview.json 충돌 — 재시도")
    except Exception:
        log.exception("회원 전용 라이브 반영 실패")
        _log_event_safe(gh, now_iso, "relay", RESULT_ERR, who=ck,
                        detail="mode: yt-member-live write 실패", via=via)
        return {"changed": False, "mode": "error", "error": True}

    _save_undo(gh, action=f"회원 전용 라이브 {ck} ({mode})", prev_content=prev or {},
               new_sha=new_sha, now_iso=now_iso)
    _log_event_safe(gh, now_iso, "relay", RESULT_OK, who=ck,
                    detail=f"mode: yt-member-live {mode}", via=via)

    # (v3.8.4) item 7 핫픽스 — 위 "relay" 로그와 별개로, /monitor 타임라인(간트)이 그리는
    # flow="preview" 상태전이 로그를 여기서도 남긴다. 이 커밋은 handlers._run(/tick·/wake)
    # 을 안 거치고 여기서 직접 preview.json 을 쓰기 때문에, 지금까지는 회원전용 방송이
    # 알림으로 live 전환되는 순간이 간트에서 통째로 빠지고(다음 정기 tick 이 나중에 잡는
    # "→end" 로 바로 건너뜀) "live(빨강)로 안 뜨고 announced/upcoming/end 만 보인다"는
    # 증상으로 나타났다. handlers._preview_log_events 와 같은 (순수) diff 로직을 그대로
    # 재사용해 전이만 뽑는다.
    try:
        from .handlers import _preview_log_events
        for ev in _preview_log_events(prev_items, items, []):
            _log_event_safe(
                gh, now_iso, "preview", RESULT_OK,
                who=ev.get("channel_key", ""),
                detail=f"{ev.get('from_state')}→{ev.get('to_state')}",
                from_state=ev.get("from_state"), to_state=ev.get("to_state"),
                video_id=ev.get("video_id"), item_id=ev.get("id"), title=ev.get("title"),
                assumed_live=ev.get("assumed_live", False),
            )
    except Exception:  # noqa: BLE001
        log.warning("monitor_log 기록 실패(preview, member-live)")

    return {"changed": True, "mode": mode, "error": False}


def _handle_member_live_start(parsed: dict, channels_cfg: dict, now_iso: str) -> tuple[dict, int]:
    """(v3.7.3, v3.8.4 에서 `_handle_yt_relay` 에서 분리) 회원전용 라이브 "시작" 알림 반영.

    `parsed` = {"channel_key", "title", "tag"} — `ytnotif.parse_member_live_relay` 또는
    (v3.8.4) `parse_public_live_relay` 가 REMINDER/SUBSCRIPTION_LIVESTREAM_START 를 video_id
    미상(회원전용 추정)으로 판별한 경우 동일한 모양으로 넘겨준다.
    """
    ck = parsed["channel_key"]
    ch = (channels_cfg.get("channels") or {}).get(ck, {})
    name = ch.get("name_ko") or ck

    found = None
    if ytdlp_probe is not None and ch.get("channel_id"):
        try:
            found = ytdlp_probe.find_member_live(ch["channel_id"], parsed["title"])
        except Exception:  # noqa: BLE001
            log.exception("회원 전용 라이브 yt-dlp 조회 예외")
    live = {
        "channel_key": ck,
        "title": (found or {}).get("title") or parsed["title"],
        "video_id": (found or {}).get("video_id"),
        "url": (found or {}).get("url") or f"https://www.youtube.com/channel/{ch.get('channel_id')}/streams",
    }

    try:
        res = writeclient.call_write("yt_member_live_commit", gh=_make_gh(), live=live,
                                     now_iso=now_iso, via="ingest", label=f"{name} 회원라이브")
    except Exception as e:  # noqa: BLE001
        log.exception("회원 전용 라이브 /write 실패")
        _send_telegram(f"⚠️ 🔒 {html.escape(name)} 회원 전용 방송 시작 감지 — 반영 실패\n{html.escape(str(e)[:150])}")
        return {"ok": False, "error": str(e)[:200]}, 200

    mode = res.get("mode")
    if res.get("error"):
        _send_telegram(f"⚠️ 🔒 {html.escape(name)} 회원 전용 방송 시작 감지 — preview.json 쓰기 실패")
    elif mode in ("created", "upgraded", "updated"):
        title_h = html.escape(live["title"] or "(제목 미상)")
        if live["video_id"]:
            _send_telegram(f"🔒 <b>{html.escape(name)}</b> 회원 전용 방송 시작 → live 반영\n{title_h}\n{live['url']}")
        else:
            _send_telegram(f"⚠️ 🔒 <b>{html.escape(name)}</b> 회원 전용 방송 시작 감지 — yt-dlp 로 영상 URL 을 "
                           f"못 찾아 채널 링크로 live 처리했습니다.\n{title_h}")
    return {"ok": True, "member_live": ck, "mode": mode, "video_id": live["video_id"]}, 200


def _handle_yt_relay(payload) -> tuple[dict, int]:
    """(v3.7.3, v3.8.4 확장) `source=yt` 중계 처리.

    v3.7.3: 회원 전용 라이브 시작(5인, `SPONSORSHIPS_LIVESTREAM_START`)만 반영하고 나머지는 200 무시.
    v3.8.4: 09-22 09:33 千石ユノ TUNEIN(30분전) 알림이 이 "나머지"에 걸려 조용히 버려진 게 발단 —
    TUNEIN·REMINDER·SUBSCRIPTION_LIVESTREAM_START(일반 채널) 도 반영한다.

    업스트림 Automate 의 HTTP 타임아웃(약 10초) 안에 끝나야 해서 외부 호출은 yt-dlp 조회 1개
    (상한 6초, 회원전용 추정 케이스만) 뿐이고 LLM·vxtwitter 는 쓰지 않는다. 항상 200(업스트림
    재시도 불필요).
    """
    if ytnotif is None or xtweet is None:
        return {"ok": True, "ignored": "unavailable"}, 200
    channels_cfg = _load_channels_config()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 회원전용 시작 — 기존 경로 그대로(우선순위 유지: parse_public_live_relay 는 이 kind 를 걸러낸다).
    parsed = ytnotif.parse_member_live_relay(payload, channels_cfg)
    if parsed is not None:
        return _handle_member_live_start(parsed, channels_cfg, now_iso)

    # (v3.8.4) TUNEIN/REMINDER/SUBSCRIPTION_LIVESTREAM_START — 이전엔 여기서 전부 무시됐다.
    public = ytnotif.parse_public_live_relay(payload, channels_cfg)
    if public is None:
        return {"ok": True, "ignored": True}, 200

    if public["resolved"]:
        # 실제 video_id 확보 — 새 GitHub 쓰기 없이 즉시 wake 하나만 예약한다. 승격
        # (announced/upcoming 자동 판정, live_state 가 이미 live 면 곧장 live)·DM·모니터
        # 로그·다음 wake 예약은 기존 handlers._run(/wake) 파이프라인이 전부 처리한다 —
        # 여기서 preview.json 을 직접 건드리지 않는다(레이스는 기존 낙관적 동시성 재시도 +
        # Cloud Tasks 태스크명 dedupe 로 이미 방어됨).
        _enqueue_wake_now(public["video_id"], now_iso)
        log.info("public yt relay → 즉시 wake: kind=%s video_id=%s", public["relay_kind"], public["video_id"])
        return {"ok": True, "public_relay": public["relay_kind"], "video_id": public["video_id"],
                "woken": True}, 200

    # video_id 미상("default") — 회원전용으로 추정.
    if public["relay_kind"] == "tunein":
        # 회원전용 "30분전" 알림이 이 폼으로 오는지 실측 확인이 안 됐고, videos.list 도 회원전용
        # 영상은 못 봐서 "upcoming" 여부를 API 로 확정할 수도 없다 — 잘못 승격(아직 방송 전인데
        # live 로 표시 등)하는 위험이 더 크므로 이번 핫픽스에서는 승격을 시도하지 않고 기존처럼
        # 무시한다(정기 light tick 안전망에 맡김).
        log.info("회원전용 추정 TUNEIN(video_id=default) — 미확인 포맷, 승격 스킵: ck=%s",
                  public.get("channel_key"))
        return {"ok": True, "ignored": "member-tunein-unresolved"}, 200

    # reminder/sub_start + video_id 미상 → 이미 검증된 회원전용 라이브 시작 경로 그대로 재사용.
    ck = public.get("channel_key")
    if ck is None:
        return {"ok": True, "ignored": True}, 200
    return _handle_member_live_start(
        {"channel_key": ck, "title": public.get("title"), "tag": public.get("tag")},
        channels_cfg, now_iso,
    )


def _enqueue_wake_now(video_id: str, schedule_time_iso: str) -> None:
    """(v3.6) URL 확정 예고 반영 직후 Cloud Tasks wake 즉시 등록.

    light tick(10분 간격, 2026-09-16 3h→10분 단축)을 안 기다리고 live/watching 전이를
    바로 예약 — 버그리포트 20260916 #1(미예고 방송 발견까지 tick 텀만큼 지연)의 근본 대응.
    실패해도 non-fatal(다음 light tick 이 안전망으로 회수).
    """
    try:
        from .tasks import TaskQueue
        tq = TaskQueue(
            project=os.environ.get("GCP_PROJECT", "").strip(),
            location=os.environ.get("GCP_LOCATION", "").strip(),
            queue=os.environ.get("TASKS_QUEUE", "").strip(),
            target_url=os.environ.get("SERVICE_URL", "").strip().rstrip("/"),
            invoker_sa=os.environ.get("INVOKER_SA", "").strip(),
        )
        tq.enqueue_wake(video_id, schedule_time_iso)
    except Exception:
        log.debug("URL 확정 예고: wake enqueue 실패 (다음 light tick 에서 회수)")


def _log_event_safe(gh, now_iso: str, flow: str, result: str, **kw) -> None:
    """(v3.6) `log_event` 를 try/except 로 감싼 버전 — 모니터링 기록 실패가 주 로직(이미
    실패했거나 폴백 중인 경로일 수 있음)을 새로 죽이지 않게 한다(기존 `_maybe_personal_tweet`
    의 관례와 동일)."""
    try:
        log_event(gh, now_iso, flow, result, **kw)
    except Exception:  # noqa: BLE001
        log.warning("monitor_log 기록 실패(%s)", flow)


def _confirm_llm_collab_guests(gh, text: str, *, host_key: str, guest_keys: list[str],
                               channels_cfg: dict, now_iso: str, via: str,
                               flow: str = "tweet") -> list[str]:
    """(v3.8.6) 트윗/릴레이 텍스트에 이름이 언급된 게스트 후보를 LLM으로 최종 확인.

    발동시점(2026-09-22 확정) — 아래 **둘 중 하나라도** 해당하면 무조건 호출:
      1. `멤버1×멤버2` 류 정규식(× 구분자)이 매치된 경우
      2. 호스트가 아닌 다른 멤버의 정식 표기 이름이 텍스트에 그냥 나온 경우
    (`find_guest_members`/`xrelay._names()`가 이미 이 두 조건으로 걸러 `guest_keys`로
    넘겨준다.) 판단 대상: "이 방송이 언급된 멤버와 실제로 합동하는 방송인가?" —
    이름이 나왔다고/×로 묶였다고 무조건 합동은 아니다(안부 인사·잡담 등). 합동
    멤버는 여럿일 수 있으나, 애초에 텍스트에 언급된 멤버만 후보로 카운팅한다
    (언급 안 된 멤버를 LLM 이 임의로 추가하진 않음 — schema enum이 candidate_names로 고정).

    GROQ_API_KEY 없거나 LLM 5회 모두 실패하면 안전한 기본값(게스트 미추가) — 등록
    자체(호스트 채널·author 콜라보)는 이 판정과 무관하게 이미 확정돼 있으므로 막지 않는다.
    `flow`: 모니터 이벤트 로그 분류용("tweet" 개인트윗 경로 | "relay" 공식 계정 릴레이 경로).
    """
    if not guest_keys:
        return []
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        log.warning("GROQ_API_KEY 없음 — 게스트 언급 콜라보 판정 스킵, 미추가")
        _log_event_safe(gh, now_iso, flow, RESULT_DEGRADED, who=host_key,
                  detail="collab-guest skip: GROQ_API_KEY 미설정 — 게스트 미추가", via=via)
        return []

    channels_map = channels_cfg.get("channels", {})
    host_name = channels_map.get(host_key, {}).get("name_ko", host_key)
    candidate_names = [channels_map.get(k, {}).get("name_ko", k) for k in guest_keys]
    name_to_key = dict(zip(candidate_names, guest_keys))

    from .llm import LLMClient
    confirmed = LLMClient(groq_key).collab_partners(
        text, host_name=host_name, candidate_names=candidate_names)
    if confirmed is None:
        log.warning("게스트 언급 콜라보 판정: LLM 5회 모두 실패 — 미추가")
        _log_event_safe(gh, now_iso, flow, RESULT_DEGRADED, who=host_key,
                  detail="collab-guest skip: collab_partners() 5회 모두 실패 — 미추가", via=via)
        return []
    return [name_to_key[n] for n in confirmed if n in name_to_key]


def _confirm_relay_rows_collab(gh, raw: str, rows: list[dict], channels_cfg: dict,
                               now_iso: str, *, via: str) -> list[dict]:
    """(v3.8.6) `xrelay.parse` 가 뽑은 행 중 특정 멤버 이름으로 collab_with 가 채워진
    것만 LLM 로 재확인 — 무조건(언급/× 매치가 곧 확정이던 것을 대체).

    `host="group"` (전원 팬아웃, `夢限大みゅーたいぷ`/인원수 표기 기반)은 대상이 아니다 —
    특정 멤버 이름을 지목한 게 아니라 "5명 다"라는 서로 다른 신호라 이름언급 오탐과는
    무관하다. 판정 후 아무도 확인 안 되면 collab_with=None, kind(=="collab")도
    되돌린다(원래 아이콘 기반 kind 는 이 시점엔 복원 불가 — None 으로 단순화).
    """
    for row in rows:
        if row.get("host") == "group" or not row.get("collab_with"):
            continue
        confirmed = _confirm_llm_collab_guests(
            gh, raw, host_key=row["channel_key"], guest_keys=list(row["collab_with"]),
            channels_cfg=channels_cfg, now_iso=now_iso, via=via, flow="relay",
        )
        row["collab_with"] = confirmed or None
        if not confirmed and row.get("kind") == "collab":
            row["kind"] = None
    return rows


_BROADCAST_KEYWORD = "配信"
_MMDD_HHMM_RE = re.compile(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})")


def _parse_kst_mmdd_hhmm(text: str | None, now_iso: str) -> str | None:
    """(v3.8.7) LLM 이 준 "MM/DD HH:MM"(KST) 를 UTC ISO 로. 파싱 실패 시 None.

    연도는 xrelay._infer_year 와 동일하게 now 와 가장 가까운 연도로 추정(연말 롤오버).
    """
    if xrelay is None:
        return None
    m = _MMDD_HHMM_RE.search(text or "")
    if not m:
        return None
    mo, d, hh, mm = (int(x) for x in m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31 and 0 <= hh <= 29 and 0 <= mm <= 59):
        return None
    try:
        now_jst = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).astimezone(xrelay.JST)
    except (ValueError, AttributeError):
        now_jst = datetime.now(xrelay.JST)
    day_carry, hh = divmod(hh, 24)          # 심야표기 24:00〜29:59
    try:
        base = datetime(xrelay._infer_year(mo, d, now_jst), mo, d, tzinfo=xrelay.JST)
    except ValueError:
        return None
    dt = base + timedelta(days=day_carry, hours=hh, minutes=mm)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _maybe_broadcast_change(gh, raw: str, channel_key: str, now_iso: str,
                            channels_cfg: dict, *, via: str = "ingest") -> None:
    """(v3.8.7) 개인 트윗에 `配信` 키워드가 있으면, 그 멤버가 **호스트**인 기존 예고를
    취소·변경하는 글인지 LLM 으로 판정해 반영한다.

    실측 계기(2026-09-22): 노노카가 당일 방송 취소를 공지했는데, 어떤 로직도 기존
    예고를 내리지 않았다 — 그 뒤 그 날의 옛 공식 그룹 공지가 재-ingest 되면서 이미
    취소된 방송이 되살아나는 사고로 이어졌다. 게스트(collab_with)로만 엮인 예고는
    대상 아님(2026-09-22 확정 — 호스트 본인 트윗만, 게스트 취소는 추후 과제).

    반영은 `/edit preview` 마법사와 동일한 커밋 함수(`apply_preview_edit`)를 그대로
    재사용 — state="none" 패치는 그 안에서 `_activate_state_edit`(즉시 제거+아카이브)
    까지 자동으로 이어진다.
    """
    if _BROADCAST_KEYWORD not in (raw or "") or xtweet is None:
        return
    try:
        prev, _ = gh.read_json(_PREVIEW_PATH)
    except Exception:
        log.exception("방송 취소/변경 판정: preview.json 조회 실패")
        return
    target = xtweet.find_active_item((prev or {}).get("items", []) or [], channel_key)
    if target is None:
        return   # 취소/변경할 활성 예고 자체가 없음 — LLM 호출 비용 절감

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        log.warning("GROQ_API_KEY 없음 — 방송 취소/변경 판정 스킵")
        _log_event_safe(gh, now_iso, "tweet", RESULT_DEGRADED, who=channel_key,
                  detail="broadcast-change skip: GROQ_API_KEY 미설정", via=via)
        return

    from .llm import LLMClient
    result = LLMClient(groq_key).broadcast_change(raw)
    if result is None:
        log.warning("방송 취소/변경 판정: LLM 5회 모두 실패 — 미반영")
        _log_event_safe(gh, now_iso, "tweet", RESULT_DEGRADED, who=channel_key,
                  detail="broadcast-change skip: broadcast_change() 5회 모두 실패", via=via)
        return

    action = result.get("action")
    if action == "del":
        patch = {"state": "none"}
        pre = {"state": target.get("state")}
        label = f"{channel_key} 방송 취소(LLM)"
    elif action == "edit":
        new_iso = _parse_kst_mmdd_hhmm(result.get("when"), now_iso)
        if not new_iso:
            log.warning("방송 취소/변경 판정: edit 인데 when 파싱 실패 — 미반영 (%r)", result.get("when"))
            return
        patch = {"date": new_iso}
        pre = {"date": target.get("scheduled_start")}
        label = f"{channel_key} 방송 일정변경(LLM)"
    else:
        return   # action == "none" — 취소/변경 아님

    ctx = {"id": target["id"], "patch": patch, "pre": pre}
    try:
        writeclient.call_write("apply_preview_edit", gh=gh, now_iso=now_iso, ctx=ctx, label=label)
    except Exception:
        log.exception("방송 취소/변경 반영 실패")
        _log_event_safe(gh, now_iso, "tweet", RESULT_ERR, who=channel_key,
                  detail="broadcast-change write 실패 — 취소/변경 유실", via=via)


def _maybe_url_confirmed_schedule(gh, raw: str, channel_key: str, now_iso: str,
                                  channels_cfg: dict, *, via: str = "ingest",
                                  quote: str | None = None) -> bool:
    """(v3.6) 원문에 유튜브 URL 이 있으면 `videos.list` 로 즉시 메타 확정해 반영.

    설계(2026-09-16 대화):
      1. 원문에서 유튜브 URL 추출 — 없으면 False(호출부가 기존 텍스트 파싱으로).
      2. `videos.list` 로 title/시각/실제 라이브 상태 확정.
      3. 채널이 우리 5인 개인 채널/그룹 공식 채널이면 그 레인(+콜라보 상대)에 바로 등록.
      4. 아니면(외부 채널) LLM 에게 "이 트윗 작성자가 참여하는 콘텐츠인가" 확인 후
         yes 일 때만 작성자 레인에 등록, no/판정불가면 스킵.
      5. 등록되면 Cloud Tasks wake 즉시 enqueue(light tick 을 안 기다림).

    반환: True == 이 경로가 등록/명시적 스킵까지 확정적으로 처리함(호출부는 텍스트
    파싱으로 넘어가지 않는다). False == 유튜브 URL 자체가 없거나(비유튜브 URL 포함),
    있긴 한데 API 로 사실관계를 확정 못 해서(키 미설정·videos.list 장애·영상 조회
    실패) 판단을 못 내린 경우 — 이때는 구버전처럼 텍스트 파싱이 최소한의 안전망
    역할을 하도록 호출부에 넘긴다(v3.6 도입 전 신뢰도 밑으로는 절대 안 떨어지게).

    `quote`: (v3.8.5 핫픽스) 인용(QRT)한 트윗의 본문. 실측 버그(2026-09-22) — 리츠가
    유노의 예고 트윗을 QRT 하며 "肉、食べます\nユノちゃんちに来ました"만 덧붙였는데,
    영상 URL 은 인용된 유노 원문에만 있어 `raw` 단독 검색으로는 못 찾고 예고 승격이
    통째로 스킵됐다. URL 탐색·게스트 이름 탐색 모두 `raw`+`quote` 합본에서 본다 —
    영상 채널이 우리 5인/그룹 채널이 아니면 여전히 LLM 참여판정을 거치므로(host_key
    분기), 무관한 인용(다른 사람 영상에 대한 감상 등)이 오탐 등록될 위험은 기존
    v3.6 설계 수준 그대로다.
    """
    if xtweet is None or xrelay is None or YouTubeClient is None:
        return False
    search_text = raw + ("\n" + quote if quote else "")
    m = xrelay.YT_VIDEO_RE.search(xrelay.normalize(search_text))
    if not m:
        return False
    video_id = m.group(1)

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        log.warning("YOUTUBE_API_KEY 없음 — URL 확정 예고 스킵, 텍스트 파싱으로 폴백")
        _log_event_safe(gh, now_iso, "tweet", RESULT_DEGRADED, who=channel_key,
                  detail="url-schedule skip: YOUTUBE_API_KEY 미설정 — 텍스트 파싱 폴백", via=via)
        return False
    try:
        info = YouTubeClient(api_key).videos_list([video_id]).get(video_id)
    except Exception:
        log.exception("videos.list 실패 (URL 확정 예고) — 텍스트 파싱으로 폴백")
        _log_event_safe(gh, now_iso, "tweet", RESULT_DEGRADED, who=channel_key,
                  detail="url-schedule skip: videos.list 실패 — 텍스트 파싱 폴백", via=via)
        return False
    if info is None or not info.channel_id:
        # 비공개/삭제된 영상 등 API 로 확정 불가 — 텍스트에 날짜/시각이 있으면
        # 그거라도 건지도록 폴백(v3.6 이전과 동일한 최소 보장). 이건 흔한 정상
        # 케이스(회원전용·삭제 등)라 monitor 에는 안 남긴다.
        return False

    host_key, host, collab_with = xtweet.resolve_url_host(info.channel_id, channel_key, channels_cfg)

    if host_key is not None and host is None:
        # (v3.8.3) 본인 채널 합동 — 제목/원문에 다른 멤버 정식 표기가 있으면 게스트 후보.
        # (v3.8.6) 언급됐다고 곧장 확정하지 않고 LLM 으로 "실제로 같이 나오는 방송인가"
        # 재확인한다 — 이름 언급이 안부 인사·잡담일 수도 있어 오탐 위험(find_guest_members
        # 는 "정식 표기가 나온다"만 볼 뿐 문맥은 모른다).
        guests = xtweet.find_guest_members(channels_cfg, host_key, info.title, search_text)
        guests = _confirm_llm_collab_guests(
            gh, search_text, host_key=host_key, guest_keys=guests,
            channels_cfg=channels_cfg, now_iso=now_iso, via=via,
        )
        merged = [*(collab_with or []), *[g for g in guests if g not in (collab_with or [])]]
        collab_with = merged or None

    if host_key is None:
        groq_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not groq_key:
            log.warning("GROQ_API_KEY 없음 — 외부 채널 URL 참여판정 스킵")
            _log_event_safe(gh, now_iso, "tweet", RESULT_DEGRADED, who=channel_key,
                      detail="url-schedule skip: GROQ_API_KEY 미설정 — 참여판정 불가, 미등록", via=via)
            return True
        author_name = channels_cfg.get("channels", {}).get(channel_key, {}).get("name_ko", channel_key)
        from .llm import LLMClient
        ok = LLMClient(groq_key).participation(raw, member_name=author_name)
        if ok is None:
            # LLM 5회 재시도 모두 실패(infra) — "무관하다고 확인됨"과는 다르다, monitor 에 남긴다.
            log.warning("URL 확정 예고: 외부 채널 + LLM 참여판정 5회 모두 실패 — 미등록")
            _log_event_safe(gh, now_iso, "tweet", RESULT_DEGRADED, who=channel_key,
                      detail="url-schedule skip: participation() 5회 모두 실패 — 미등록", via=via)
            return True
        if ok is not True:
            log.info("URL 확정 예고: 외부 채널 + LLM 미확인(%s) — 스킵", ok)
            return True
        host_key, host, collab_with = channel_key, None, None

    new_item, next_check_at = xtweet.build_item_from_video(
        info, channel_key=host_key, host=host, collab_with=collab_with, now_iso=now_iso,
    )

    # (WP-3b) 커밋은 백엔드 잡에서 — call_write 로 위임
    try:
        res = writeclient.call_write("url_confirmed_commit", gh=gh, video_id=video_id,
                                     new_item=new_item, next_check_at=next_check_at,
                                     host_key=host_key, now_iso=now_iso, via=via,
                                     label=f"{host_key} 예고확정")
        changed = res.get("changed", False)
    except Exception:
        log.exception("URL 확정 예고: /write 호출 실패")
        _log_event_safe(gh, now_iso, "tweet", RESULT_ERR, who=channel_key,
                  detail="url-schedule write 실패 — 확정된 정보가 유실됨", via=via)
        return True

    if changed:
        name = channels_cfg.get("channels", {}).get(host_key, {}).get("name_ko", host_key)
        state_label = {"live": "🔴 라이브 중", "watching": "⏳ 시작 임박",
                       "upcoming": "📅 예정"}.get(new_item.get("state"), new_item.get("state"))
        _auto_dm(
            gh, "scheduled",
            f"📅 <b>{html.escape(name)}</b> URL 확정 예고 반영 → {state_label}"
            f"\n{html.escape(new_item.get('url') or '')}",
        )
    return True


def _maybe_nonyt_url_notice(gh, raw: str, tag: str | None, now_iso: str) -> bool:
    """(v3.6) 유튜브 URL은 없지만 다른 완결 URL(bilibili 등)이 있으면 소식(notice)으로 이관.

    이런 URL은 `videos.list` 로 라이브/종료를 확인할 방법이 없어 preview 로 추적 못
    한다 — 등록은 되는데 영원히 안 끝나는 반쪽 카드를 만드는 대신 preview 파이프라인
    밖(소식)으로 돌린다. 공식 계정 소식과 완전히 같은 경로를 재사용 —
    번역·undo 스냅샷 전부 그대로 딸려온다. 날짜/시각을 텍스트에서 못 뽑으면
    (`xnotice.parse` 자체 게이트) 소식도 안 됨 — 조용히 스킵.

    반환: True == 유튜브 아닌 완결 URL 이 있어서 이 경로가 처리를 맡음(등록/스킵 모두
    포함 — 호출부는 텍스트 예고 경로로 넘어가지 않는다). False == URL 자체가 없거나,
    있는 URL 이 유튜브 형식인 경우 — 후자는 `_maybe_url_confirmed_schedule` 가
    API 로 확정을 못 해 폴백해온 것일 수 있으므로(키 미설정·API 장애 등), 유튜브
    URL 을 "비유튜브"로 오분류해 소식으로 잘못 보내지 않는다.

    (WP-3a) 준비(외부 호출)와 커밋(쓰기)를 분리.
    """
    if xnotice is None or xrelay is None:
        return False
    t = xrelay.normalize(raw)
    if xrelay.YT_VIDEO_RE.search(t):
        return False   # 유튜브 URL — 소식이 아니라 텍스트 예고 경로가 최소 안전망 역할
    if not xnotice._URL_RE.search(t):
        return False

    try:
        # 준비 단계: 파싱 + LLM + 중복판정
        prepared = _prepare_notice(raw, now_iso, tag=tag, gh=gh)
        if prepared is None:
            log.info("비유튜브 URL → 소식 경로: none (파싱 실패)")
            return True

        # 커밋 단계
        writeclient.call_write("notice_sweep", gh=gh, now_iso=now_iso, label="소식정리")
        result = writeclient.call_write("apply_notice", gh=gh, prepared=prepared, now_iso=now_iso,
                                        label=_notice_label(prepared))
        mode = result.get("mode", "error")
    except Exception:
        log.exception("비유튜브 URL 소식 이관 실패")
        return True
    log.info("비유튜브 URL → 소식 경로: %s", mode)
    return True


def _maybe_personal_schedule(raw: str, *, tag: str | None, channel_key: str,
                             name: str, handle: str, now_iso: str, via: str = "ingest",
                             quote: str | None = None) -> None:
    """(v2.8.1) 개인 트윗이 방송 예고면 preview 행으로 승격.

    (v3.6) 3단 분기:
      1. 유튜브 URL 있음 → `_maybe_url_confirmed_schedule` 로 `videos.list` 확정 정보 사용.
      2. 유튜브 아닌 다른 완결 URL 있음 → `_maybe_nonyt_url_notice` 로 소식(notice)에 이관
         (preview 로는 라이브/종료 추적이 안 되므로 스코프 아웃).
      3. URL 자체 없음 → 기존 텍스트 파싱(`xtweet.parse_schedule`)으로 후보를 뽑되,
         등록 직전 `LLMClient.announces_own_broadcast` 로 "진짜 본인 예고인가" 최종
         확인한다 — 정규식은 문맥을 모르므로(예: 후기 트윗 속 우연한 날짜/시각 오합성,
         버그리포트 20260916 #2) LLM 이 마지막 관문.
    `_maybe_personal_tweet` 이 배지 처리 후 호출. 어느 단계든 게이트 미통과면 no-op(배지만).

    `quote`: (v3.8.5 핫픽스) 인용(QRT)한 트윗의 본문 — 1·2단계(URL 탐색)에서 `raw`와
    합쳐 함께 본다. 실측 버그(2026-09-22): 리츠가 유노의 예고 트윗을 QRT 하며 자기
    코멘트만 달았고 영상 URL 은 인용문 쪽에만 있어, `raw` 단독 검색으론 URL을 못 찾고
    승격 자체가 스킵됐다(합동 레인 누락). 3단계(텍스트만 파싱)는 인용문이 본인 말이
    아니므로 여전히 raw만 본다.
    """
    if xtweet is None:
        return
    raw = _expand_truncated_yt(raw, tag)
    gh = _make_gh()
    if gh is None:
        return
    try:
        control, _ = gh.read_json("control.json")
        if is_paused(control or default_control()):
            return
    except Exception:
        log.exception("control.json 조회 실패 — personal schedule 스킵")
        return

    channels_cfg = _load_channels_config()
    if _maybe_url_confirmed_schedule(gh, raw, channel_key, now_iso, channels_cfg, via=via,
                                     quote=quote):
        return   # 유튜브 URL 이 있었음(raw 또는 quote) — 반영/스킵 여부와 무관하게 아래로 안 넘어감
    if _maybe_nonyt_url_notice(gh, raw, tag, now_iso):
        return   # 비유튜브 URL 이 있었음 — 소식 경로가 처리(등록/스킵 모두 포함)

    try:
        row = xtweet.parse_schedule(raw, channel_key=channel_key, tag=tag,
                                    now_iso=now_iso, handle=handle)
    except Exception:
        log.exception("parse_schedule 실패")
        return
    if not row:
        return

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        log.warning("GROQ_API_KEY 없음 — 텍스트 예고 최종 확인 불가, 미등록(안전한 실패)")
        _log_event_safe(gh, now_iso, "tweet", RESULT_DEGRADED, who=channel_key,
                        detail="text-schedule skip: GROQ_API_KEY 미설정 — 최종확인 불가, 미등록", via=via)
        return
    from .llm import LLMClient
    confirmed = LLMClient(groq_key).announces_own_broadcast(raw)
    if confirmed is None:
        # LLM 5회 재시도 모두 실패(infra) — "예고 아님"으로 확인된 것과는 다르다, monitor 에 남긴다.
        log.warning("텍스트 예고 후보 — LLM 최종 확인 5회 모두 실패 → 미등록")
        _log_event_safe(gh, now_iso, "tweet", RESULT_DEGRADED, who=channel_key,
                        detail="text-schedule skip: announces_own_broadcast() 5회 모두 실패 — 미등록", via=via)
        return
    if confirmed is not True:
        log.info("텍스트 예고 후보 — LLM 최종 확인 미통과(%s) → 미등록", confirmed)
        return

    try:
        res = writeclient.call_write("merge_rows", gh=gh, rows=[row], now_iso=now_iso,
                                     message=f"data: personal schedule {channel_key} {now_iso}",
                                     action=f"본인 예고 {name} ({(raw[:40] or '').strip()})",
                                     merge_fn="personal_schedule")
        changed = res.get("changed", False)
    except Exception:
        log.exception("personal schedule 반영 실패")
        return
    when = "시간 미정" if row.get("time_tbd") else xrelay._jst_hm(row.get("scheduled_start")) + " JST"
    link = row.get("url") or ""
    _auto_dm(
        gh, "scheduled",
        f"📅 <b>{html.escape(name)}</b> 본인 예고 감지 → {when}"
        + (f"\n{html.escape(link)}" if link else "")
        + ("\n\n↩️ /undo 로 되돌릴 수 있습니다." if changed else ""),
    )


def _tweet_sweep(gh, now_iso: str) -> int:
    """expires_at 지난 개인 트윗 → tweet_archive.json. 반환: 이관 건수 (best-effort)."""
    if xtweet is None:
        return 0
    try:
        prev, psha = gh.read_json(_TWEETS_PATH)
        if not prev or not prev.get("tweets"):
            return 0
        arch, asha = gh.read_json(_TWEET_ARCHIVE_PATH)
        new_t, new_a, removed = xtweet.sweep_expired(
            prev, arch or xtweet.default_archive(), now_iso)
        if not removed:
            return 0
        gh.write_json(_TWEETS_PATH, new_t, prev_sha=psha,
                      message=f"data: tweet sweep ({len(removed)}) {now_iso}")
        gh.write_json(_TWEET_ARCHIVE_PATH, new_a, prev_sha=asha,
                      message=f"data: tweet archive sweep {now_iso}")
        return len(removed)
    except Exception:
        log.exception("tweet sweep 실패 (무시)")
        return 0


def _kst_dt(iso: str | None) -> str:
    """ISO 'Z' → 'YYYY-MM-DD HH:MM KST'. 파싱 실패 시 원문 그대로."""
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(
            timezone(timedelta(hours=9))
        )
        return dt.strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return iso


def _undo_target_text(undo: dict) -> str:
    """되돌리면 '어느 시점'으로 가는지 한 줄 안내."""
    at = _kst_dt(undo.get("at"))
    sha = (undo.get("new_sha") or "")[:7]
    tail = f" · 커밋 <code>{sha}</code> 취소" if sha else ""
    return f"⏱ 되돌리면 <b>{at} 직전</b> 상태가 됩니다{tail}."


def _undo_diff_text(prev_content: dict, cur_content: dict, limit: int = 8,
                    path: str = "preview.json") -> str:
    """undo(=prev_content 로 복원) 시 복원될/사라질 항목 요약. path 따라 대상 배열이 다름."""
    if path == "notices.json":
        prev_l = (prev_content or {}).get("notices", []) or []
        cur_l = (cur_content or {}).get("notices", []) or []
        _ids_p = {n.get("id") for n in prev_l}
        _ids_c = {n.get("id") for n in cur_l}
        restored = [n for n in prev_l if n.get("id") not in _ids_c]
        removed = [n for n in cur_l if n.get("id") not in _ids_p]

        def _line(n: dict) -> str:
            if notices is not None:
                return "· " + notices.summary_line(n)
            return "· " + (n.get("title") or n.get("id") or "?")[:60]
    else:
        prev_bcs = (prev_content or {}).get("items", []) or []
        cur_bcs = (cur_content or {}).get("items", []) or []
        restored = [b for b in prev_bcs if b not in cur_bcs]
        removed = [b for b in cur_bcs if b not in prev_bcs]

        def _line(b: dict) -> str:
            ck = b.get("channel_key", "?")
            hm = ""
            s = b.get("scheduled_start") or b.get("actual_start")
            if s and xrelay is not None:
                try:
                    hm = " " + xrelay._jst_hm(s) + "(JST)"
                except Exception:
                    hm = ""
            title = b.get("title") or b.get("state") or ""
            return f"· {ck}{hm} {title}".rstrip()

    parts = [f"<b>+{len(restored)} 복원 / −{len(removed)} 제거</b>"]
    for tag, rows in (("복원", restored), ("제거", removed)):
        for b in rows[:limit]:
            parts.append(f"[{tag}] {html.escape(_line(b))}")
        if len(rows) > limit:
            parts.append(f"[{tag}] …외 {len(rows) - limit}건")
    return "\n".join(parts)


def _undo_restore_commit(gh, path: str, prev_content: dict, expected_sha, action: str,
                         now_iso: str) -> dict:
    """(write-queue) /undo 실제 복원 — 대상은 호출부(마법사)가 이미 확정한 path/prev_content/
    expected_sha 그대로. 커밋 직전에 대상 파일 sha 를 다시 확인해(그 사이 또 바뀌었으면
    거부) admin_state.json pending_undo 슬롯을 재조회하지 않고도 안전하게 판단한다."""
    cur, cur_sha = gh.read_json(path)
    if cur_sha != expected_sha:
        return {"ok": False, "cur": cur, "cur_sha": cur_sha}
    gh.write_json(path, prev_content, prev_sha=cur_sha, message=f"data: undo({action}) {now_iso}")
    return {"ok": True, "cur": cur}


def _handle_undo_request(gh, now_iso: str) -> None:
    """/undo 1단계 — 되돌릴 작업을 보여주고 (y/N) 확인을 요청. 실제 되돌리기는 안 함."""
    try:
        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = state or admin.default_admin_state()
        undo = admin.get_undo(state)
        if not undo:
            _send_telegram("↩️ 되돌릴 작업이 없습니다.")
            return

        _path = undo.get("path") or _PREVIEW_PATH
        cur, _ = gh.read_json(_path)
        diff = _undo_diff_text(undo.get("prev_content") or {}, cur or {}, path=_path)
        gh.write_json(
            _ADMIN_STATE_PATH,
            admin.set_pending_undo(
                state, target_sha=undo.get("new_sha"),
                action=undo.get("action") or "직전 작업", now_iso=now_iso,
            ),
            prev_sha=sha, message=f"data: /undo 확인대기 {now_iso}",
        )
        _send_telegram(
            f"🔁 <b>{html.escape(undo.get('action') or '직전 작업')}</b> 을(를) 되돌립니다.\n"
            f"{_undo_target_text(undo)}\n"
            f"{diff}\n\n정말 되돌릴까요? (y/N — 60초 후 자동 취소)"
        )
    except Exception as e:
        log.exception("Error handling /undo request")
        _send_telegram(f"⚠️ 오류: /undo 처리 실패\n{str(e)[:100]}")


def _handle_undo_confirm(gh, now_iso: str, yes: bool) -> None:
    """/undo 2단계 — (y) 면 되돌리고, (n) 이면 취소. 슬롯은 어느 쪽이든 정리.

    (y) 라도 ① undo 슬롯이 그 사이 교체됐거나(target_sha 불일치) ② schedule.json 이
    또 바뀌었으면(SHA 불일치) 안전하게 거부한다.
    """
    try:
        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = state or admin.default_admin_state()
        pending = admin.get_pending_undo(state)

        if not yes:
            gh.write_json(_ADMIN_STATE_PATH, admin.clear_pending_undo(state),
                          prev_sha=sha, message=f"data: /undo 취소 {now_iso}")
            _send_telegram("🚫 undo가 취소되었습니다.")
            return

        undo = admin.get_undo(state)
        if not pending or not undo or undo.get("new_sha") != pending.get("target_sha"):
            gh.write_json(_ADMIN_STATE_PATH, admin.clear_pending_undo(state),
                          prev_sha=sha, message=f"data: /undo 슬롯 정리(교체됨) {now_iso}")
            _send_telegram("↩️ 그 사이 다른 작업이 있었습니다 — /undo 를 다시 실행하세요.")
            return

        _path = undo.get("path") or _PREVIEW_PATH
        target = _undo_target_text(undo)
        result = writeclient.call_write(
            "undo_restore", gh=gh, path=_path, prev_content=undo["prev_content"],
            expected_sha=undo.get("new_sha"), action=undo.get("action") or "직전 작업",
            now_iso=now_iso,
        )
        if not result.get("ok"):
            state = admin.clear_pending_undo(admin.clear_undo(state))
            gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha,
                          message=f"data: undo 슬롯 정리({_path} 갱신) {now_iso}")
            _hint = ("/list 로 현재 상태를 확인한 뒤 /del 로 수동 처리하세요."
                     if _path == _PREVIEW_PATH else "/notice-list 로 확인 후 /notice-del 하세요.")
            _send_telegram(f"↩️ 되돌리기 불가 — 그 사이 {_path} 이 갱신됐습니다.\n{_hint}")
            return

        diff = _undo_diff_text(undo.get("prev_content") or {}, result.get("cur") or {}, path=_path)
        state, sha = gh.read_json(_ADMIN_STATE_PATH)
        state = admin.clear_pending_undo(admin.clear_undo(state or admin.default_admin_state()))
        gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha, message=f"data: undo 슬롯 정리 {now_iso}")
        _send_telegram(
            f"↩️ <b>{html.escape(undo.get('action') or '직전 작업')}</b> 되돌려졌습니다.\n"
            f"{target}\n{diff}"
        )
    except Exception as e:
        log.exception("Error handling /undo confirm")
        _send_telegram(f"⚠️ 오류: /undo 확인 처리 실패\n{str(e)[:100]}")


# ── (v3) /translate — 수동 번역. 자동 파이프라인의 말단 번역과 별개. ─────────────
def _make_llm_client():
    """LLMClient. GROQ_API_KEY 없으면 None."""
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        return None
    try:
        from .llm import LLMClient

        return LLMClient(
            key,
            model=os.environ.get("GROQ_MODEL", "").strip() or llm.DEFAULT_MODEL,
            fallback=os.environ.get("GROQ_MODEL_FALLBACK", "").strip()
            or llm.FALLBACK_MODEL,
        )
    except Exception:
        log.exception("LLMClient 생성 실패")
        return None


def _make_vision_client():
    """VisionClient. GROQ_API_KEY 없거나 vision 모듈 미탑재면 None. (v3.2)"""
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key or vision is None:
        return None
    try:
        return vision.VisionClient(
            key,
            model=os.environ.get("GROQ_VISION_MODEL", "").strip()
            or vision.DEFAULT_VISION_MODEL,
            fallback=os.environ.get("GROQ_VISION_MODEL_FALLBACK", "").strip()
            or vision.FALLBACK_VISION_MODEL,
        )
    except Exception:
        log.exception("VisionClient 생성 실패")
        return None


def _maybe_tag_cast_participants(parsed: dict, tag: str | None) -> None:
    """(v3.2) 크로스오버 공식 계정 소식이면 첨부 이미지를 비전 OCR 로 읽어
    5인 중 누가 출연하는지 `parsed["participants"]` 에 채운다 (제자리 수정).

    조건이 하나라도 안 맞으면(계정 미대상·tweet id 없음·이미지 없음·OCR 실패·
    매칭되는 멤버 없음) 아무것도 안 하고 조용히 넘어간다 — 이 소식은 여전히
    일반 소식으로 정상 표시된다(무회귀).
    """
    src_handle = (parsed or {}).get("src_handle") or ""
    if not any(h in src_handle for h in _CAST_LOOKUP_HANDLES):
        return
    if vxtwitter is None or xtweet is None or xrelay is None:
        return
    tid = xtweet._tweet_id(tag) if tag else ""
    if not tid or not tid.isdigit():
        return
    j = vxtwitter.fetch_tweet(tid)
    media = vxtwitter.extract(j).get("media") if j else []
    if not media:
        return
    vc = _make_vision_client()
    if vc is None:
        return
    names = vc.cast_names(image_url=media[0])
    if not names:
        log.info("cast OCR: 이름 판독 실패 (tweet %s)", tid)
        return
    matched: list[str] = []
    for name in names:
        for token, key in xrelay.NAME_TO_KEY:
            if token in name and key not in matched:
                matched.append(key)
    if matched:
        parsed["participants"] = matched
        log.info("cast OCR: %s → 참여 채널 %s (tweet %s)", names, matched, tid)
    else:
        log.info("cast OCR: 판독된 이름 %s 중 5인 매칭 없음 (tweet %s)", names, tid)


def _translate_report(label: str, total: int, tried: int, ok: int) -> str:
    """/translate 결과 보고 — 총건수 / 시도 / 성공·실패 / 이미 번역됨."""
    if total == 0:
        return f"번역할 {label}이 없습니다."
    if tried == 0:
        return f"{label} {total}건 모두 번역돼 있습니다."
    fail = tried - ok
    msg = (f"🌐 {label} 번역: 총 {total}건 · 시도 {tried}건 → "
           f"성공 {ok} / 실패 {fail}")
    skipped = total - tried
    if skipped:
        msg += f" · 기존 {skipped}건 유지"
    if fail:
        msg += "\n실패분은 다음 정기 tick 에서 자동 재시도합니다 (needs_tl)."
    return msg


def _handle_translate(gh, now_iso: str, contents: str) -> None:
    """/translate <notice|tweet> — 미번역 행 전부에 `*_ko` 채운다(원문 보존).

    (preview 제목 번역은 계획상 자동/수동 모두 안 함 — 여기서도 지원 안 함.)
    """
    c = (contents or "").strip().lower()
    if c not in ("notice", "tweet"):
        _send_telegram("사용법: /translate &lt;notice | tweet&gt;")
        return
    llm = _make_llm_client()
    if llm is None:
        _send_telegram("⚠️ GROQ_API_KEY 미설정 — 번역 불가")
        return
    try:
        if c == "notice":
            prev, sha = gh.read_json(_NOTICES_PATH)
            lst = (prev or {}).get("notices", []) or []
            total = len(lst)
            n = 0
            pending = 0
            for row in lst:
                if row.get("title_ko"):
                    continue
                pending += 1
                res = llm.notice_title(row.get("body_for_llm") or row.get("title") or "")
                if res and res.get("title_ko"):
                    # 자동 sweep(handlers._translate_sweep)과 동일하게 title 도 LLM 정제본으로.
                    row["title"] = res.get("title_ja") or row.get("title")
                    row["title_ko"] = res["title_ko"]
                    row.pop("needs_tl", None)
                    n += 1
                else:
                    row["needs_tl"] = True
            if n:
                prev["generated_at"] = now_iso
                gh.write_json(_NOTICES_PATH, prev, prev_sha=sha,
                              message=f"data: /translate notice ({n}) {now_iso}")
            _send_telegram(_translate_report("소식", total, pending, n))
        else:  # tweet
            prev, sha = gh.read_json(_TWEETS_PATH)
            tw = (prev or {}).get("tweets", {}) or {}
            arch, _asha = gh.read_json(_TWEET_ARCHIVE_PATH)
            nj, _nsha = gh.read_json(_NOTICES_PATH)
            total = 0
            n = 0
            pending = 0
            for _k, lst in list(tw.items()):
                norm = _tw_list(lst)
                tw[_k] = norm                       # v2.8 단건 → 배열로 승계
                for row in norm:
                    total += 1
                    if row.get("text_ko"):
                        pass
                    else:
                        pending += 1
                        ko = llm.translate(row.get("text") or "")
                        if ko:
                            row["text_ko"] = ko
                            row.pop("needs_tl", None)
                            n += 1
                        else:
                            row["needs_tl"] = True
                    # 인용(QRT) 카드 번역 — 같은 원문이 이미 한 번이라도 번역됐으면
                    # (다른 트윗의 본문/인용, 또는 소식 제목) 재사용. (v3.4.6)
                    q = row.get("quote")
                    if q and q.get("text"):
                        total += 1
                        if q.get("text_ko"):
                            continue
                        pending += 1
                        ko = (xtweet.find_reused_ko(q["text"], tweets_data=prev,
                                                     archive_data=arch, notices_data=nj)
                              or llm.translate(q["text"]))
                        if ko:
                            q["text_ko"] = ko
                            q.pop("needs_tl", None)
                            n += 1
                        else:
                            q["needs_tl"] = True
            if n:
                prev["generated_at"] = now_iso
                gh.write_json(_TWEETS_PATH, prev, prev_sha=sha,
                              message=f"data: /translate tweet ({n}) {now_iso}")
            _send_telegram(_translate_report("트윗", total, pending, n))
    except Exception as e:
        log.exception("Error handling /translate")
        _send_telegram(f"⚠️ 오류: /translate 처리 실패\n{str(e)[:100]}")


# ── (v3) {cmd}×{contents} 격자 헬퍼 ─────────────────────────────────────────────
_CONTENTS = ("preview", "notice", "tweet")


def _split_contents(arg: str, default: str = "preview") -> tuple[str, str]:
    """`arg` 의 첫 토큰이 preview|notice|tweet 면 (그것, 나머지). 아니면 (default, arg 전체).

    `/list arale` 같은 v2 호출 하위호환 — arale 은 contents 가 아니므로 (preview, "arale").
    """
    parts = (arg or "").strip().split(None, 1)
    if parts and parts[0].lower() in _CONTENTS:
        return parts[0].lower(), (parts[1].strip() if len(parts) > 1 else "")
    return default, (arg or "").strip()


def _handle_tweet_list(gh, channels_cfg: dict) -> None:
    """/list tweet — 현재 배지가 떠 있는 유닛의 트윗."""
    if xtweet is None:
        _send_telegram("⚠️ xtweet 모듈 없음")
        return
    prev, _ = gh.read_json(_TWEETS_PATH)
    tw = (prev or {}).get("tweets", {}) or {}
    if not tw:
        _send_telegram("🐦 표시 중인 개인 트윗 없음.")
        return
    chans = channels_cfg.get("channels", {})
    lines = ["🐦 <b>개인 트윗</b>"]
    for k in _UNIT_KEYS:
        thread = _tw_list(tw.get(k))
        if not thread:
            continue
        name = chans.get(k, {}).get("name_ko", k)
        head = f"<b>{html.escape(name)}</b> ({k}) — {len(thread)}건"
        msgs = []
        for i, row in enumerate(thread, 1):      # 오래된 → 최신
            body = (row.get("text_ko") or row.get("text") or "").replace("\n", " ")[:80]
            msgs.append(f"#{i} {html.escape(body)}")
        lines.append(head + "\n" + "\n".join(msgs) + f"\n{thread[-1].get('url') or ''}")
    _send_telegram("\n\n".join(lines))


def _tweet_del_commit(gh, unit: str, now_iso: str) -> dict:
    """(write-queue) /del tweet 실제 반영 — 슬롯 제거 + undo 스냅샷."""
    prev, sha = gh.read_json(_TWEETS_PATH)
    prev = prev or {}
    tw = dict(prev.get("tweets", {}) or {})
    if unit not in tw:
        return {"found": False}
    tw.pop(unit)
    new = dict(prev)
    new["tweets"] = tw
    new["generated_at"] = now_iso
    _, nsha = gh.write_json(_TWEETS_PATH, new, prev_sha=sha,
                            message=f"data: /del tweet {unit} {now_iso}")
    _save_undo(gh, action=f"/del tweet {unit}", prev_content=prev, new_sha=nsha,
               now_iso=now_iso, path=_TWEETS_PATH)
    return {"found": True}


def _handle_tweet_del(gh, channels_cfg: dict, now_iso: str, unit: str) -> None:
    """/del tweet <유닛> — 그 유닛의 트윗 배지 슬롯을 즉시 제거(+undo)."""
    u = (unit or "").strip().lower()
    if u not in _UNIT_KEYS:
        _send_telegram(f"사용법: /del tweet &lt;유닛&gt;  ({', '.join(_UNIT_KEYS)})")
        return
    try:
        result = writeclient.call_write("tweet_del_commit", gh=gh, unit=u, now_iso=now_iso,
                                        label=f"{u} 트윗삭제")
        if not result.get("found"):
            _send_telegram(f"ℹ️ {u} 트윗이 없습니다.")
            return
        _send_telegram(f"🗑 {u} 트윗 배지 제거됨. /undo 로 되돌릴 수 있습니다.")
    except Exception as e:
        log.exception("del tweet")
        _send_telegram(f"⚠️ 오류: /del tweet 실패\n{str(e)[:100]}")


# ── (v3) /edit — pending_op 슬롯 기반 마법사 ───────────────────────────────────
_EDIT_FIELDS = ("title", "state", "date", "url")
_OP_TTL_SEC = 60


def _op_set(gh, now_iso, *, cmd, contents, step, ctx):
    st, sh = gh.read_json(_ADMIN_STATE_PATH)
    gh.write_json(_ADMIN_STATE_PATH,
                  admin.set_pending_op(st or admin.default_admin_state(),
                                       cmd=cmd, contents=contents, step=step, ctx=ctx,
                                       now_iso=now_iso),
                  prev_sha=sh, message=f"data: pending_op {cmd}/{contents}/{step} {now_iso}")


def _op_clear(gh, now_iso, *, release_lock_id=None):
    st, sh = gh.read_json(_ADMIN_STATE_PATH)
    st = st or admin.default_admin_state()
    st = admin.clear_pending_op(st)
    if release_lock_id:
        st = admin.clear_edit_lock(st)
    gh.write_json(_ADMIN_STATE_PATH, st, prev_sha=sh,
                  message=f"data: pending_op 정리 {now_iso}")


def _edit_form_preview(name: str, idx: int, item: dict, patch: dict) -> str:
    def _cur(f):
        if f == "date":
            k = _parse_iso_to_kst(item.get("scheduled_start"))
            return k.strftime("%Y-%m-%d %H:%M") if k else "(없음)"
        return str(item.get({"url": "url"}.get(f, f)) or "(없음)")
    lines = [f"<b>{html.escape(name)}</b> #{idx}  <code>{item.get('id')}</code>"]
    for f in _EDIT_FIELDS:
        mark = " ✏️" if f in patch else ""
        val = html.escape(str(patch[f])) if f in patch else html.escape(_cur(f))
        lines.append(f"* {f:<6}: {val}{mark}")
    lines.append("\n수정할 항목 이름(title/state/date/url)을 보내세요. 여러 개면 순서대로.")
    lines.append("끝내려면 <code>done</code> · 원문으로 통째 교체는 <code>ingest</code> · 취소 <code>aNoneTokyo</code>")
    return "\n".join(lines)


def _handle_edit(gh, channels_cfg: dict, now_iso: str, contents: str, rest: str) -> None:
    """/edit <preview|notice|tweet> — 편집 마법사 진입."""
    if admin is None:
        _send_telegram("⚠️ admin 모듈 없음 — /edit 사용 불가")
        return
    if contents == "notice":
        _handle_notice_edit(gh, now_iso, rest)          # 기존 마법사 재사용
        return
    if contents == "tweet":
        u = (rest or "").strip().lower()
        if u not in _UNIT_KEYS:
            _send_telegram(f"사용법: /edit tweet &lt;유닛&gt;  ({', '.join(_UNIT_KEYS)})")
            return
        _op_set(gh, now_iso, cmd="edit", contents="tweet", step="await_raw", ctx={"unit": u})
        _send_telegram(f"✏️ {u} 트윗을 교체할 새 원문을 보내세요. (취소 <code>aNoneTokyo</code>)")
        return
    # preview
    _handle_list(gh, channels_cfg, rest)
    _op_set(gh, now_iso, cmd="edit", contents="preview", step="await_unit", ctx={})
    _send_telegram("✏️ 어떤 유닛의 예고를 편집할까요? (유닛명 · 취소 <code>aNoneTokyo</code>)")


def _handle_op_followup(gh, channels_cfg: dict, now_iso: str, message: dict, text: str) -> bool:
    """pending_op(cmd=edit/ingest, contents=preview/tweet) 응답 소비. True=소진."""
    if admin is None:
        return False
    try:
        state, _ = gh.read_json(_ADMIN_STATE_PATH)
    except Exception:
        return False
    op = admin.get_pending_op(state)
    if not op:
        return False
    lock_id = (op.get("ctx") or {}).get("id")

    if admin.pending_op_expired(op, now_iso, _OP_TTL_SEC):
        _op_clear(gh, now_iso, release_lock_id=lock_id)
        _send_telegram("⏱ 편집 대기(60초)가 지나 취소되었습니다.")
        return False
    t = (text or "").strip()
    if t == _INGEST_CANCEL_TOKEN:
        _op_clear(gh, now_iso, release_lock_id=lock_id)
        _send_telegram("🚫 편집이 취소되었습니다.")
        return True
    if t.startswith("/"):
        _op_clear(gh, now_iso, release_lock_id=lock_id)
        _send_telegram("ℹ️ 편집을 취소하고 입력한 명령을 실행합니다.")
        return False

    cmd, contents, step = op.get("cmd"), op.get("contents"), op.get("step")
    ctx = dict(op.get("ctx") or {})

    # ── ingest tweet / edit tweet : 원문 한 방 ──
    if step == "await_raw" and contents == "tweet":
        raw = t
        if not raw:
            _send_telegram("⚠️ 원문 텍스트를 보내주세요. (대기 유지)")
            return True
        _op_clear(gh, now_iso)
        u = ctx.get("unit")
        _send_telegram("📥 반영 중…")
        mode = _maybe_personal_tweet(raw, title="", tag=None, channel_key=u, now_iso=now_iso, via="ops")
        _send_telegram(f"🐦 {u} 트윗 {'교체됨' if mode in ('added','replaced') else mode}.")
        return True

    # ── edit preview 마법사 ──
    if cmd != "edit" or contents != "preview":
        return False

    prev, _ = gh.read_json(_PREVIEW_PATH)
    items = (prev or {}).get("items", []) or []

    if step == "await_unit":
        u = t.lower()
        if u not in _UNIT_KEYS:
            _send_telegram(f"⚠️ 유닛명을 보내주세요 ({', '.join(_UNIT_KEYS)}). 취소 aNoneTokyo")
            return True
        ctx["unit"] = u
        _op_set(gh, now_iso, cmd="edit", contents="preview", step="await_idx", ctx=ctx)
        _send_telegram(f"{u} 의 몇 번 항목을 편집할까요? (번호 — /list {u} 로 확인)")
        return True

    if step == "await_idx":
        u = ctx.get("unit")
        try:
            idx = int(t)
        except ValueError:
            _send_telegram("⚠️ 번호(숫자)를 보내주세요.")
            return True
        unit_items = _sorted_unit_broadcasts({"items": items}, u)
        if idx < 1 or idx > len(unit_items):
            _op_clear(gh, now_iso)
            _send_telegram(f"⚠️ {u} #{idx} 없음. /edit 로 다시 시작하세요.")
            return True
        it = unit_items[idx - 1]
        ctx.update({"id": it.get("id"), "idx": idx, "patch": {},
                    "pre": {f: (it.get("scheduled_start") if f == "date" else it.get(f))
                            for f in _EDIT_FIELDS}})
        # 아이템 단위 편집 락
        st, sh = gh.read_json(_ADMIN_STATE_PATH)
        st = admin.set_pending_op(st or admin.default_admin_state(), cmd="edit",
                                  contents="preview", step="await_field", ctx=ctx, now_iso=now_iso)
        st = admin.set_edit_lock(st, id=it.get("id"), now_iso=now_iso, ttl_sec=_OP_TTL_SEC)
        gh.write_json(_ADMIN_STATE_PATH, st, prev_sha=sh,
                      message=f"data: /edit preview lock {it.get('id')} {now_iso}")
        name = channels_cfg.get("channels", {}).get(u, {}).get("name_ko", u)
        _send_telegram(_edit_form_preview(name, idx, it, {}))
        return True

    if step == "await_field":
        f = t.lower()
        if f == "done":
            writeclient.call_write("apply_preview_edit", gh=gh, now_iso=now_iso, ctx=ctx,
                                   label="예고편집")
            _dm_sent_ctx.set(True)  # DM 은 apply_preview_edit 내부(원격)에서 이미 보냄
            return True
        if f == "ingest":
            _op_set(gh, now_iso, cmd="edit", contents="preview", step="await_raw_pv", ctx=ctx)
            _send_telegram("교체할 예고 원문을 보내세요. (취소 aNoneTokyo)")
            return True
        if f not in _EDIT_FIELDS:
            _send_telegram(f"⚠️ title/state/date/url/done/ingest 중 하나. 지금 patch: {ctx.get('patch')}")
            return True
        ctx["_field"] = f
        _op_set(gh, now_iso, cmd="edit", contents="preview", step="await_value", ctx=ctx)
        hint = {"date": " (YYYY-MM-DD HH:MM, KST)", "state": " (announced/upcoming/…)"}.get(f, "")
        _send_telegram(f"새 {f} 값을 보내세요{hint}.")
        return True

    if step == "await_value":
        f = ctx.get("_field")
        patch = dict(ctx.get("patch") or {})
        if f == "date":
            m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})\s*$", t)
            if not m:
                _send_telegram("⚠️ 형식: YYYY-MM-DD HH:MM (KST). 다시 보내세요.")
                return True
            kst = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]),
                           tzinfo=timezone(timedelta(hours=9)))
            patch["date"] = kst.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif f == "url":
            patch["url"] = t if t.startswith("http") else "https://" + t.lstrip("/")
        else:
            patch[f] = t
        ctx["patch"] = patch
        ctx.pop("_field", None)
        _op_set(gh, now_iso, cmd="edit", contents="preview", step="await_field", ctx=ctx)
        u = ctx.get("unit")
        name = channels_cfg.get("channels", {}).get(u, {}).get("name_ko", u)
        it = next((x for x in items if x.get("id") == ctx.get("id")), {})
        _send_telegram(_edit_form_preview(name, ctx.get("idx", 0), it, patch))
        return True

    if step == "await_raw_pv":
        raw = t
        _op_clear(gh, now_iso, release_lock_id=ctx.get("id"))
        rows = xrelay.parse(raw, now_iso) if xrelay else []
        if not rows:
            _send_telegram("ℹ️ 예고 형식으로 파싱 못 함 — 편집 취소.")
            return True
        rows = _confirm_relay_rows_collab(gh, raw, rows, channels_cfg, now_iso, via="ops")
        writeclient.call_write("merge_rows", gh=gh, rows=rows, now_iso=now_iso,
                               message=f"data: /edit preview ingest {now_iso}",
                               action="/edit preview ingest")
        try:
            log_event(gh, now_iso, "relay", RESULT_OK, detail=f"mode: added · 파싱 {len(rows)}건(수동 교체)", via="ops")
        except Exception:  # noqa: BLE001
            log.warning("monitor_log 기록 실패(relay via ops)")
        _send_telegram("✏️ 원문으로 교체 반영됨. /undo 로 되돌릴 수 있습니다.")
        return True

    return False


def _apply_preview_edit(gh, now_iso: str, ctx: dict) -> None:
    """답한 필드만 preview.json 아이템에 병합. edit_lock 해제. tick 충돌 필드 알림."""
    patch = ctx.get("patch") or {}
    pid = ctx.get("id")
    pre = ctx.get("pre") or {}
    if not patch:
        _op_clear(gh, now_iso, release_lock_id=pid)
        _send_telegram("변경 사항이 없습니다.")
        return
    field_map = {"title": "title", "state": "state", "date": "scheduled_start", "url": "url"}
    conflicts = []
    for _try in (1, 2):
        prev, sha = gh.read_json(_PREVIEW_PATH)
        prev = prev or {"items": []}
        items = list(prev.get("items", []) or [])
        i = next((k for k, x in enumerate(items) if x.get("id") == pid), None)
        if i is None:
            _op_clear(gh, now_iso, release_lock_id=pid)
            _send_telegram("⚠️ 편집하려던 아이템이 사라졌습니다 — 취소.")
            return
        it = dict(items[i])
        for f, val in patch.items():
            key = field_map[f]
            cur = it.get(key)
            want_pre = pre.get(f)
            if cur != want_pre:
                conflicts.append(f"{f}: 운영자값 유지 (그 사이 tick: {want_pre!r}→{cur!r})")
            it[key] = val
        if "state" in patch:
            # FSM 판정 기준(state_since) 을 리셋 — "방금 이 상태로 막 진입"한 것으로 취급.
            # 안 하면 예전 state_since 가 그대로 남아 end→none(30분 경과) 같은 판정이
            # 리셋 없이 즉시 발동해버릴 수 있다(실측 버그).
            it["state_since"] = now_iso
        it["last_updated"] = now_iso
        items[i] = it
        new = dict(prev)
        new["items"] = items
        new["generated_at"] = now_iso
        try:
            _, nsha = gh.write_json(_PREVIEW_PATH, new, prev_sha=sha,
                                    message=f"data: /edit preview {pid} {now_iso}")
            _save_undo(gh, action=f"/edit preview {pid}", prev_content=prev,
                       new_sha=nsha, now_iso=now_iso, path=_PREVIEW_PATH)
            break
        except ConflictError:
            if _try == 2:
                raise
            log.warning("/edit preview: 충돌 — 재시도")
    _op_clear(gh, now_iso, release_lock_id=pid)
    msg = f"✏️ 예고 편집 반영 ({', '.join(patch)}). /undo 로 되돌릴 수 있습니다."
    if "state" in patch:
        msg += "\n" + _activate_state_edit(gh, it, now_iso)
    if conflicts:
        msg += "\n\n" + "\n".join(conflicts)
    _send_telegram(msg)


def _activate_state_edit(gh, item: dict, now_iso: str) -> str:
    """`/edit preview` 로 state 를 바꾼 직후, 그 상태에 맞는 실제 로직을 마저 이행.

    라벨만 바꾸고 끝내면(v3.1.16 까지의 동작) FSM 파생·Cloud Tasks wake 재예약·
    archive 반영이 전혀 안 일어나 다음 tick(최대 3h) 까지 방치되는 문제가 있었다
    (실측: 외부 채널 합동방송이 그 사이 아예 사라진 사례).

    - "none" → preview.json 에서 즉시 제거 + preview_archive.json 에 기록
      (FSM 의 end→none 전이와 동일하게 취급).
    - video_id 있음(live/end/watching/upcoming — API 로 실물 검증 가능) → 메인 서비스
      `/wake` 를 OIDC 로 호출해 실제 상태로 재확인 + Cloud Tasks wake 재예약까지 그쪽에
      맡긴다. 운영자가 잘못 짚었어도 API 확인 결과가 우선하므로 안전하다.
    - video_id 없음(announced 자리표시) → API 로 확인할 게 없으므로 로컬에서
      statemachine.derive() 1회만 돌려 state_since 리셋 기준으로 다음 체크를 재계산.
    """
    pid = item.get("id")
    state = item.get("state")
    video_id = item.get("video_id")

    if state == "none":
        for attempt in (1, 2):
            prev, sha = gh.read_json(_PREVIEW_PATH)
            prev = prev or {"items": []}
            items = list(prev.get("items", []) or [])
            idx = next((k for k, x in enumerate(items) if x.get("id") == pid), None)
            if idx is None:
                return "(이미 다른 경로로 제거됨)"
            gone = items.pop(idx)
            new_pv = dict(prev)
            new_pv["items"] = items
            new_pv["generated_at"] = now_iso
            try:
                gh.write_json(_PREVIEW_PATH, new_pv, prev_sha=sha,
                               message=f"data: /edit preview→none {pid} {now_iso}")
                break
            except ConflictError:
                if attempt == 2:
                    raise
                log.warning("/edit preview→none: 충돌 — 재시도")
        try:
            arch, arch_sha = gh.read_json(_PREVIEW_ARCHIVE_PATH)
            arch = dict(arch or {"items": []})
            arch["items"] = list(arch.get("items", []) or []) + [
                preview_mod.to_archive_record(gone, now_iso)
            ]
            arch["generated_at"] = now_iso
            gh.write_json(_PREVIEW_ARCHIVE_PATH, arch, prev_sha=arch_sha,
                           message=f"data: preview_archive += {pid} {now_iso}")
        except Exception:  # noqa: BLE001
            log.warning("preview_archive 반영 실패 — preview.json 제거는 유지", exc_info=True)
        return "🗑 즉시 제거 + 아카이브 반영 완료."

    if video_id:
        main_url = os.environ.get("MAIN_SERVICE_URL", "").strip().rstrip("/")
        if not (fetch_id_token and Request and requests and main_url):
            return "⚠️ 메인 서비스 호출 불가(설정 없음) — 다음 정기 tick 이 처리합니다."
        try:
            tok = fetch_id_token(Request(), main_url)
            resp = requests.post(
                f"{main_url}/wake", json={"video_id": video_id},
                headers={"Authorization": f"Bearer {tok}"}, timeout=30,
            )
            if resp.status_code == 200:
                return "✅ 메인 서비스 /wake 로 실물 재확인 + 다음 체크 재예약 완료."
            return f"⚠️ /wake 호출 실패(HTTP {resp.status_code}) — 다음 정기 tick 이 처리합니다."
        except Exception as e:  # noqa: BLE001
            return f"⚠️ /wake 호출 실패({e}) — 다음 정기 tick 이 처리합니다."

    # video_id 없는 announced 자리표시 — API 검증 대상 아님, FSM 1회만 로컬 파생.
    tick = statemachine.derive(item, now_iso, live_seen=None)
    if tick.next_state == item.get("state"):
        return f"FSM 재판정: 변화 없음(다음 체크 {tick.next_check_at or '다음 tick'})."
    for attempt in (1, 2):
        prev, sha = gh.read_json(_PREVIEW_PATH)
        prev = prev or {"items": []}
        items = list(prev.get("items", []) or [])
        idx = next((k for k, x in enumerate(items) if x.get("id") == pid), None)
        if idx is None:
            return "(이미 다른 경로로 제거됨)"
        it2 = preview_mod.set_state(items[idx], tick.next_state, now_iso)
        gone2 = None
        if tick.next_state == "none":
            items.pop(idx)
            gone2 = it2
        else:
            items[idx] = it2
        new_pv = dict(prev)
        new_pv["items"] = items
        new_pv["generated_at"] = now_iso
        try:
            gh.write_json(_PREVIEW_PATH, new_pv, prev_sha=sha,
                           message=f"data: /edit preview FSM 재판정 {pid} {now_iso}")
            break
        except ConflictError:
            if attempt == 2:
                raise
            log.warning("/edit preview FSM 재판정: 충돌 — 재시도")
    if gone2 is not None:
        try:
            arch, arch_sha = gh.read_json(_PREVIEW_ARCHIVE_PATH)
            arch = dict(arch or {"items": []})
            arch["items"] = list(arch.get("items", []) or []) + [
                preview_mod.to_archive_record(gone2, now_iso)
            ]
            arch["generated_at"] = now_iso
            gh.write_json(_PREVIEW_ARCHIVE_PATH, arch, prev_sha=arch_sha,
                           message=f"data: preview_archive += {pid} {now_iso}")
        except Exception:  # noqa: BLE001
            log.warning("preview_archive 반영 실패", exc_info=True)
    return f"FSM 재판정: {tick.next_state}(다음 체크 {tick.next_check_at or '없음'})."


_MONITOR_LIVE_TTL_SEC = 60
_monitor_live_cache: dict = {"at": 0.0, "html": ""}
_monitor_live_lock = threading.Lock()


def _monitor_live_html() -> str:
    """웹 monitor 페이지용: 가장 최근 06:00 KST 경계부터 지금까지의 리포트 HTML.

    락을 잡은 채 생성해 동시 접속이 GitHub/healthchecks 를 중복 호출하지 않게 하고,
    TTL 안의 재요청은 캐시를 돌려준다.
    """
    with _monitor_live_lock:
        if _monitor_live_cache["html"] and time.monotonic() - _monitor_live_cache["at"] < _MONITOR_LIVE_TTL_SEC:
            return _monitor_live_cache["html"]
        gh = _make_gh()
        if gh is None:
            raise RuntimeError("GitHub 설정 없음")
        result = monitor_report.run(
            gh, date_kst=None,
            healthchecks_api_key=os.environ.get("HEALTHCHECKS_IO_READONLEY_TOKEN", "").strip(),
            healthchecks_uuid=_healthchecks_uuid(),
            github_token_for_commits=gh.token,
        )
        _monitor_live_cache["html"] = result["html"]
        _monitor_live_cache["at"] = time.monotonic()
        return result["html"]


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
        _dm_sent_ctx.set(False)   # (v3.6) 안전망 — 아래 어느 return 이든 이 값을 거쳐 나간다

        def _done(ok: bool = True):
            """(v3.6) 이 웹훅의 모든 return 지점을 통과시키는 안전망.

            버그리포트 20260916 #4: `/del preview`(유닛/번호 누락)처럼 인식은 되지만
            처리할 수 없는 명령이 응답 DM 없이 조용히 끝나면, 운영자는 명령이 씹혔는지
            처리 중인지 구분할 방법이 없다. 개별 핸들러(또는 대기 중인 마법사 후속
            처리)마다 "이 경로는 DM을 보내는가"를 하나하나 감사하는 대신, 실제로
            반환되는 모든 지점을 여기 하나로 모아 `_dm_sent_ctx` 가 여전히 False 면
            대신 안내 DM 을 보낸다 — 새 명령/새 return 경로가 추가돼도 자동으로 커버됨.
            """
            if text and not _dm_sent_ctx.get():
                log.warning("명령 처리 후 DM 미발송 — 안전망 발동: %r", text[:200])
                _send_telegram(
                    f"⚠️ <code>{html.escape(text[:200])}</code> 처리 결과를 알려드리지 못했습니다"
                    "(응답 누락 — 코드 버그일 수 있습니다). 형식을 확인해 다시 시도하거나 "
                    "개발자에게 이 메시지를 공유해 주세요."
                )
            return jsonify({"ok": ok}), 200

        try:
            # GitHub 저장소 초기화
            gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
            gh_repo = os.environ.get("GITHUB_REPO", "").strip()
            gh_branch = os.environ.get("DATA_BRANCH", "data").strip() or "data"

            if not gh_token or not gh_repo:
                log.warning("GitHub config missing")
                _send_telegram("⚠️ GitHub 설정 누락")
                return _done(False)

            gh = GitHubStore(gh_token, gh_repo, gh_branch)
            channels_cfg = _load_channels_config()

            # v2.5: 대기 중인 /del 확인(y/N) 이 있으면 명령 디스패치보다 먼저 처리.
            # admin_state.json 읽기 실패는 일반 명령 처리를 막지 않는다(무시하고 통과).
            if admin is not None:
                try:
                    _admin_state, _ = gh.read_json(_ADMIN_STATE_PATH)
                    _pending = admin.get_pending_del(_admin_state)
                    _pending_undo = admin.get_pending_undo(_admin_state)
                except Exception:
                    log.warning("admin_state.json 조회 실패 — /del·/undo 확인 스킵하고 일반 명령으로 처리")
                    _pending = _pending_undo = None
                _low = text.strip().lower()
                _is_yn = _low in ("y", "yes", "n", "no")
                _is_del_ans = _is_yn or _low == "terminate"
                if _pending and not admin.pending_del_expired(_pending, now_utc) and _is_del_ans:
                    _handle_del_confirm(gh, now_utc, _low)
                    return _done()
                if _pending_undo:
                    if admin.pending_undo_expired(_pending_undo, now_utc):
                        # 60초 자동 N — 안내만 하고 이 메시지는 정상 디스패치로 흘려보냄
                        try:
                            _st2, _sh2 = gh.read_json(_ADMIN_STATE_PATH)
                            gh.write_json(_ADMIN_STATE_PATH,
                                          admin.clear_pending_undo(_st2 or admin.default_admin_state()),
                                          prev_sha=_sh2, message=f"data: /undo 확인 만료 {now_utc}")
                        except Exception:
                            log.exception("pending_undo 만료 정리 실패")
                        _send_telegram("🚫 undo 확인 시간(60초)이 지나 자동 취소되었습니다.")
                    elif _is_yn:
                        _handle_undo_confirm(gh, now_utc, yes=_low in ("y", "yes"))
                        return _done()

            # v2.5.1: /ingest(무인자) 후 원문/파일 대기 중이면 이 메시지를 그쪽이 소진.
            # (만료·타 명령이면 False → 아래 정상 디스패치로 흘러감)
            if admin is not None and _handle_ingest_followup(
                gh, channels_cfg, now_utc, message, text
            ):
                return _done()

            # v2.8.1+: 개인 예고 유닛 되묻기(1~5/이름) 응답 대기 중이면 그쪽이 소진.
            if admin is not None and _handle_member_followup(
                gh, channels_cfg, now_utc, text
            ):
                return _done()

            # v2.7: /notice(무인자) 후 원문/파일 대기 중이면 그쪽이 소진.
            if admin is not None and _handle_notice_followup(gh, now_utc, message, text):
                return _done()

            # v2.7.x: /notice-edit 마법사(title→date→url) 응답 대기 중이면 그쪽이 소진.
            if admin is not None and _handle_notice_edit_followup(gh, now_utc, text):
                return _done()

            # v3: /edit·/ingest tweet 마법사(pending_op) 응답 대기 중이면 그쪽이 소진.
            if admin is not None and _handle_op_followup(gh, channels_cfg, now_utc, message, text):
                return _done()

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
                _c, _rest = _split_contents(arg)
                if _c == "notice":
                    _handle_notice_list(gh, now_utc)
                elif _c == "tweet":
                    _handle_tweet_list(gh, channels_cfg)
                else:
                    _handle_list(gh, channels_cfg, _rest)   # preview (rest=유닛 필터)
            elif cmd == "/edit":
                _c, _rest = _split_contents(arg)
                _handle_edit(gh, channels_cfg, now_utc, _c, _rest)
            elif cmd == "/del":
                _c, _rest = _split_contents(arg)
                if _c == "notice":
                    _handle_notice_del(gh, now_utc, _rest)
                elif _c == "tweet":
                    _handle_tweet_del(gh, channels_cfg, now_utc, _rest)
                else:
                    parts = _rest.split()
                    _unit = parts[0] if len(parts) >= 1 else ""
                    _idx = parts[1] if len(parts) >= 2 else ""
                    _handle_del_request(gh, channels_cfg, now_utc, _unit, _idx)
            elif cmd in ("/ingest", "/add"):
                _c, _rest = _split_contents(arg)
                if admin is None:
                    _send_telegram("⚠️ admin 모듈 없음 — /ingest 사용 불가")
                elif _c == "tweet":
                    _u = _rest.strip().lower()
                    if _u not in _UNIT_KEYS:
                        _send_telegram(f"사용법: /ingest tweet &lt;유닛&gt;  ({', '.join(_UNIT_KEYS)})")
                    else:
                        _op_set(gh, now_utc, cmd="ingest", contents="tweet",
                                step="await_raw", ctx={"unit": _u})
                        _send_telegram(f"✏️ {_u} 개인 트윗 원문을 보내세요. (취소 <code>aNoneTokyo</code>)")
                elif _c == "notice":
                    try:
                        _st, _sh = gh.read_json(_ADMIN_STATE_PATH)
                        gh.write_json(_ADMIN_STATE_PATH,
                                      admin.set_pending_notice(_st or admin.default_admin_state(), now_iso=now_utc),
                                      prev_sha=_sh, message=f"data: pending_notice 대기 시작 {now_utc}")
                        _send_telegram(_NOTICE_PROMPT)
                    except Exception:
                        log.exception("pending_notice 세팅 실패")
                        _send_telegram("⚠️ /ingest notice 대기 저장 실패")
                else:
                    # preview — 인라인 원문 안 받음(||스포일러|| 마스킹). 무인자 대기 슬롯.
                    try:
                        _st, _sh = gh.read_json(_ADMIN_STATE_PATH)
                        gh.write_json(
                            _ADMIN_STATE_PATH,
                            admin.set_pending_ingest(_st or admin.default_admin_state(), now_iso=now_utc),
                            prev_sha=_sh, message=f"data: pending_ingest 대기 시작 {now_utc}",
                        )
                        _send_telegram(_INGEST_PROMPT)
                    except Exception:
                        log.exception("pending_ingest 세팅 실패")
                        _send_telegram("⚠️ /ingest 대기 상태 저장 실패 — 잠시 후 다시 시도하세요.")
            elif cmd == "/notice":
                # /ingest 와 같은 2단계 — 무인자로 대기 슬롯만 세팅.
                if admin is None or notices is None:
                    _send_telegram("⚠️ notice 모듈 없음 — /notice 사용 불가")
                else:
                    try:
                        _st, _sh = gh.read_json(_ADMIN_STATE_PATH)
                        gh.write_json(
                            _ADMIN_STATE_PATH,
                            admin.set_pending_notice(
                                _st or admin.default_admin_state(), now_iso=now_utc
                            ),
                            prev_sha=_sh, message=f"data: pending_notice 대기 시작 {now_utc}",
                        )
                        _send_telegram(_NOTICE_PROMPT)
                    except Exception:
                        log.exception("pending_notice 세팅 실패")
                        _send_telegram("⚠️ /notice 대기 상태 저장 실패 — 잠시 후 다시 시도하세요.")
            elif cmd in ("/notice-del", "/ndel"):
                _handle_notice_del(gh, now_utc, arg)
            elif cmd in ("/notice-edit", "/nedit"):
                _handle_notice_edit(gh, now_utc, arg)
            elif cmd in ("/notice-list", "/notices"):
                _handle_notice_list(gh, now_utc)
            elif cmd == "/undo":
                _handle_undo_request(gh, now_utc)
            elif cmd == "/translate":
                _handle_translate(gh, now_utc, arg)
            elif cmd == "/monitor":
                _handle_monitor(gh, now_utc, arg)
            else:
                # 도움말
                help_text = (
                    "<b>📱 mewtype 텔레그램 봇 (v3)</b>\n\n"
                    "일반: /status /pause /resume /log [detail|normal|simple]\n"
                    "/monitor [--auto|--off|--monthly|--yearly|YYYY-MM-DD] — 운영 모니터링 리포트 즉시 DM "
                    "(--auto: 매일 KST 06:00 자동, --off: 자동 끔, --monthly: 이번 달 전체(월간 추이 그리드), "
                    "--yearly: 올해 전체(연간 추이 그리드), 날짜: 그날 리포트)\n\n"
                    "<b>콘텐츠</b> (c = preview | notice | tweet, 생략 시 preview):\n"
                    "/list &lt;c&gt; [유닛] — 목록\n"
                    "/ingest &lt;c&gt; — 원문 이어 보내 반영 (tweet 은 유닛 지정)\n"
                    "/edit &lt;c&gt; — 편집 마법사 (preview: 필드 하나씩 · notice: 제목→날짜→URL)\n"
                    "/del &lt;c&gt; … — 삭제 (preview: &lt;유닛&gt; &lt;번호&gt;, 확인 <code>y</code>/<code>terminate</code>/N)\n"
                    "/translate &lt;notice|tweet&gt; — 미번역 행 번역 (원문 보존)\n"
                    "/undo — 직전 mutating 명령 되돌리기 (y/N, 60초)\n\n"
                    "별칭: /notice /notice-list /notice-del /notice-edit /add"
                )
                _send_telegram(help_text)

        except Exception as e:
            log.exception("Webhook processing error")
            _send_telegram(f"⚠️ 처리 오류: {str(e)[:100]}")

        # 항상 200 반환 (Telegram 재시도 방지) — _done() 이 DM 미발송 안전망까지 처리
        return _done()

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

        # 원본 바디를 form 파싱 전에 먼저 캐시한다. Werkzeug 는 request.form 을 건드리는
        # 순간 입력 스트림을 소비하면서 get_data() 캐시를 안 채우므로, 그 뒤에 부르는
        # request.get_data() 는 form-urlencoded 요청에서 항상 빈 문자열이 된다
        # (그동안 ECHO DM 의 "raw body" 칸이 늘 비어 보이던 원인). cache=True 로 먼저
        # 읽어두면 이후 request.form 은 캐시된 바디를 다시 파싱한다.
        raw_body = request.get_data(cache=True, parse_form_data=False, as_text=True)

        payload = request.form if request.form else (request.get_json(silent=True) or {})
        # (v3.7.3) 유튜브 앱 알림 중계(`source=yt`)는 트윗 파이프라인이 아니라 별도 처리.
        if (payload.get("source") or "").strip() == "yt":
            body, code = _handle_yt_relay(payload)
            return jsonify(body), code
        raw = (payload.get("text") or "").strip()
        title = (payload.get("title") or "").strip()      # (v2.3.x) nx["android.title"] — 게시자 표시 이름
        tmpl = (payload.get("template") or "").strip()     # (v2.3.x) nx["android.template"] — BigTextStyle 등
        x_tag = (payload.get("tag") or "").strip()         # (v2.3.x) nx["pde_noti_tag"] — 트윗 태그
        tweet_url = _tweet_url_from_tag(x_tag)

        # 폰 Automate 빌드가 `urlEncode({"text": expr})` 를 `<expr값>=` 로 만들어버린다
        # (트윗 본문이 값이 아니라 폼 키 자리로 샌다). text 값이 비었는데 정체불명 키가
        # 딱 하나 있고 그 값도 비어 있으면, 그 키 이름을 원문으로 간주한다.
        # ponytail: Automate 빌드 특유의 urlEncode 딕셔너리 버그 우회. 폰에서 body 를
        #           `"text=" ++ urlEncode(...)` 로 제대로 보낼 수 있게 되면 이 블록 삭제.
        if not raw and request.form:
            odd = [k for k in request.form.keys()
                   if k not in ("text", "title", "template", "tag")]
            if len(odd) == 1 and not (request.form.get(odd[0]) or "").strip():
                raw = odd[0].strip()

        # 폰이 보낸 본문이 깨졌거나(이모지 서로게이트쌍 처리 오류) 잘렸으면, 같은 트윗을
        # vxtwitter 로 다시 조회해 원문을 통째로 교체한다 — 원문 없이는 파싱도 번역도
        # "제대로 ingest" 한 게 아니므로 아래 모든 파이프라인(소식/스케줄/개인트윗) 전에 선행.
        raw, _vx_ex = _recover_raw_via_vxtwitter(raw, x_tag)

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        gh = _make_gh()

        # (v2.8) android.title 라우팅 (INGEST_FLOW 3↔4 노드 사이).
        #   개인 5인      → tweets.json 파이프라인으로 빼고 즉시 종료 (4번 이하 안 탐)
        #   테스트 부계정 → 4번은 거치되 force_echo (INGEST_ECHO env 무관, 헬스체크)
        #   공식·그 외    → 기존 경로 그대로
        force_echo = False
        if xtweet is not None:
            try:
                _test_titles = tuple(
                    s.strip() for s in os.environ.get("INGEST_TEST_TITLES", "jehy").split(",")
                    if s.strip()
                )
                _route = xtweet.route_by_title(
                    title, _load_channels_config(), test_titles=_test_titles
                )
            except Exception:
                log.exception("route_by_title 실패 — official 로 폴백")
                _route = "official"
            if _route == "test":
                force_echo = True
            elif _route != "official":
                mode = _maybe_personal_tweet(raw, title=title, tag=x_tag, channel_key=_route,
                                            now_iso=now_iso, vx_extract=_vx_ex)
                return jsonify({"ok": True, "personal": _route, "mode": mode}), 200

        # (v2.7) 소식 게시판 — schedule.json 과 별개 파이프라인. INGEST_ECHO/DRY-RUN 과
        # 무관하게 여기서 항상 시도한다(소식이 아니면 GitHub 도 안 건드림).
        _maybe_auto_notice(raw, now_iso, tag=x_tag, title=title)

        # ─── v2.3 임시 ECHO 테스트 훅 (INGEST_ECHO 가 참일 때만) ───────────────
        # 폰 Automate 가 `@BDP_yumemita` 푸시알림을 키워드 필터 없이 그대로 relay 할 때,
        # 백엔드 처리(파싱·저장) 전혀 없이 "들어온 텍스트 그대로"만 DM 으로 회신한다.
        # 웹푸시 본문이 온전히/잘려서/비어서 오는지 확인용.
        # 확인 끝나면 env 에서 INGEST_ECHO 만 내리면 아래 실제 로직으로 복귀.
        # (이 블록 자체를 지워도 무방 — 나머지 로직은 이 블록에 의존하지 않음.)
        if force_echo or os.environ.get("INGEST_ECHO", "").strip() not in ("", "0", "false", "False", "no"):
            # 잘림 판정용 계측 — DM 없이 Cloud Run 로그만으로도 확인 가능해야.
            #   tail_ok = 트윗 말미 고정 문구가 왔는가 (오면 본문이 안 잘린 것)
            tail_ok = "予告なく変更" in raw or "時刻は予告" in raw
            log.warning(
                "ingest ECHO: len=%d blen=%d clen=%s tail_ok=%s ct=%r form_keys=%r "
                "head=%r tail=%r",
                len(raw), len(raw_body), request.content_length, tail_ok,
                request.content_type, list(request.form.keys()), raw[:120], raw[-120:],
            )
            # raw body 는 form-urlencoded 라 %XX 로 찍힌다 — 사람이 읽게 디코드해서 보여준다.
            # (form 파싱 순서 문제로 raw_body 가 비어 오면 request.form 에서 재구성)
            body_src = raw_body or "&".join(
                f"{k}={v}" for k, v in request.form.items(multi=True)
            )
            try:
                body_dec = unquote_plus(body_src)
            except Exception:
                body_dec = body_src
            _send_telegram(
                "📡 <b>ingest ECHO</b> — 백엔드 처리 안 함\n"
                f"ct=<code>{html.escape(request.content_type or '-')}</code> · "
                f"form_keys={list(request.form.keys())}\n"
                f"title=<code>{html.escape(title) or '(없음)'}</code> · "
                f"template=<code>{html.escape(tmpl) or '(없음)'}</code>\n"
                f"tweet=<code>{html.escape(tweet_url) or '(태그 없음/파싱실패)'}</code>\n"
                f"len(text)={len(raw)} · len(body)={len(raw_body)}(enc)/"
                f"{len(body_dec)}(dec) · 말미문구 {'✅' if tail_ok else '❌'}\n"
                "───── text ─────\n"
                f"<code>{html.escape(raw) if raw else '(빈 text)'}</code>"
            )
            # raw body 디코드본 — 길이 제한 없이 모두 회신. Telegram sendMessage 4096자
            # 상한 때문에 통째로 넣으면 DM 자체가 실패하므로 청크로 나눠 보낸다.
            _body_chunk = 3500
            if not body_dec:
                _send_telegram("───── raw body(decoded) ─────\n<code>(빈 body)</code>")
            else:
                _parts = [body_dec[i:i + _body_chunk]
                          for i in range(0, len(body_dec), _body_chunk)]
                for _idx, _part in enumerate(_parts, 1):
                    _tag = f" ({_idx}/{len(_parts)})" if len(_parts) > 1 else ""
                    _send_telegram(
                        f"───── raw body(decoded){_tag} ─────\n"
                        f"<code>{html.escape(_part)}</code>"
                    )
            # 스케줄 트윗이면 큐에 적재 — 실배포 전환 시 반영되도록 (유실 방지).
            if raw and xrelay is not None and xrelay.looks_relayable(raw):
                writeclient.call_write("ingest_queue_push", gh=gh, raw=raw, title=title, now_iso=now_iso,
                                       label="큐 적재")
            return jsonify({"ok": True, "echo": True, "len": len(raw), "tail_ok": tail_ok}), 200
        # ─────────────────────────────────────────────────────────────────────

        if not raw:
            # 폰(Automate)이 text 를 빈 값으로 보내는 원인 추적용 계측.
            # (로그는 무한정 길어지면 안 되므로 여기서는 raw_body 를 800자로 자른다.)
            log.warning(
                "ingest empty text: ct=%r len=%s form_keys=%r json=%r body[:800]=%r",
                request.content_type,
                request.content_length,
                list(request.form.keys()),
                request.get_json(silent=True),
                raw_body[:800],
            )
            return jsonify({"ok": False, "error": "empty text"}), 400
        if xrelay is None:
            return jsonify({"ok": False, "error": "xrelay unavailable"}), 500

        dry = os.environ.get("INGEST_DRY_RUN", "").strip() not in ("", "0", "false", "False", "no")

        try:
            channels_cfg = _load_channels_config()
            rows = xrelay.parse(raw, now_iso)
            rows = _confirm_relay_rows_collab(gh, raw, rows, channels_cfg, now_iso, via="ingest")

            if dry:
                cut = 3500
                body = raw if len(raw) <= cut else raw[:cut] + "\n…(len 초과 잘림)"
                brief = " / ".join(
                    f"{r['channel_key']} {xrelay._jst_hm(r['scheduled_start'])}(JST)"
                    f"{'🔒' if r['members_only'] else ''}"
                    for r in rows
                ) or "(파싱 0건)"
                _failed = xrelay.unparsed_lines(raw)
                _send_telegram(
                    "🧪 <b>ingest DRY-RUN</b> — 저장 안 함\n"
                    f"title: <code>{html.escape(title) or '(없음)'}</code> · "
                    f"template: <code>{html.escape(tmpl) or '(없음)'}</code>\n"
                    f"tweet: <code>{html.escape(tweet_url) or '(없음)'}</code>\n"
                    f"len(text)={len(raw)} · 파싱 {len(rows)}건 · 인식 실패 {len(_failed)}줄\n"
                    f"{html.escape(brief)}\n"
                    "─────\n"
                    f"<code>{html.escape(body)}</code>"
                )
                if xrelay is not None and xrelay.looks_relayable(raw):
                    writeclient.call_write("ingest_queue_push", gh=gh, raw=raw, title=title, now_iso=now_iso,
                                           label="큐 적재")
                return jsonify({"ok": True, "dry_run": True, "parsed": len(rows)}), 200

            if gh is None:
                _send_telegram("⚠️ ingest: GitHub 설정 누락")
                return jsonify({"ok": False, "error": "gh config"}), 200

            control, _ = gh.read_json("control.json")
            if is_paused(control or default_control()):
                log.info("ingest: paused — skip")
                _auto_dm(gh, "ingest", "⏸ 일시정지 중 — ingest 무시")
                return jsonify({"ok": True, "paused": True}), 200

            # 실배포 전환 후 첫 호출 — 테스트 기간(ECHO/DRY-RUN)에 쌓인 트윗 먼저 반영.
            _drain = writeclient.call_write("ingest_queue_drain", gh=gh, now_iso=now_iso, label="큐 반영")
            drained, drained_rows = _drain.get("applied", 0), _drain.get("rows", 0)
            failed = xrelay.unparsed_lines(raw)

            if not rows:
                # 소식 자동 인입은 라우트 상단 _maybe_auto_notice 에서 이미 처리됨(ECHO 무관).
                if failed:
                    msg = (
                        f"⚠️ ingest: 스케줄 트윗이나 {len(failed)}줄 모두 인식 실패\n"
                        + _failed_lines_block(failed)
                    )
                else:
                    msg = "ℹ️ ingest: 스케줄·소식 형식 아님 — 무시\n" + raw[:200]
                if drained:
                    msg += f"\n📥 대기열 {drained}건({drained_rows}행) 반영됨"
                # 대기열 반영이 있었으면(=실제 scheduled 변경) scheduled, 아니면 잡음성 ingest.
                _auto_dm(gh, "scheduled" if drained else "ingest", msg)
                try:
                    log_event(gh, now_iso, "relay", RESULT_DEGRADED if failed else RESULT_OK,
                              detail=f"mode: none · 인식 실패 {len(failed)}줄" if failed else "mode: none", via="ingest")
                except Exception:  # noqa: BLE001
                    log.warning("monitor_log 기록 실패(relay)")
                return jsonify(
                    {"ok": True, "parsed": 0, "failed": len(failed), "drained": drained}
                ), 200

            changed = writeclient.call_write(
                "merge_rows", gh=gh, rows=rows, now_iso=now_iso,
                message=f"data: xrelay scheduled {now_iso}",
                action=f"ingest {title or raw[:40]}".strip(),
            ).get("changed")

            summary = xrelay.summary_text(rows, channels_cfg)
            if tweet_url:
                summary += f"\n🔗 {tweet_url}"
            if failed:
                summary += (
                    f"\n\n⚠️ 인식 실패 {len(failed)}줄 (반영 안 됨):\n"
                    + _failed_lines_block(failed)
                )
            if drained:
                summary += f"\n\n📥 대기열 {drained}건({drained_rows}행)도 함께 반영"
            if changed:
                summary += "\n\n↩️ /undo 로 되돌릴 수 있습니다."
            _auto_dm(gh, "scheduled", summary)   # 공식 일일 스케줄 → scheduled 행 반영
            try:
                log_event(gh, now_iso, "relay", RESULT_DEGRADED if failed else RESULT_OK,
                          detail=f"mode: added · 파싱 {len(rows)}건" + (f" · 실패 {len(failed)}줄" if failed else ""), via="ingest")
            except Exception:  # noqa: BLE001
                log.warning("monitor_log 기록 실패(relay)")
            return jsonify(
                {"ok": True, "parsed": len(rows), "changed": changed, "drained": drained}
            ), 200
        except Exception as e:
            log.exception("ingest failed")
            _send_telegram(f"⚠️ ingest 오류: {str(e)[:200]}")
            if gh is not None:
                try:
                    log_event(gh, now_iso, "relay", RESULT_ERR, detail=f"mode: error · {str(e)[:100]}", via="ingest")
                except Exception:  # noqa: BLE001
                    log.warning("monitor_log 기록 실패(relay)")
            return jsonify({"ok": False, "error": str(e)}), 200

    @app.get("/monitor-live")
    def _monitor_live():
        """웹 monitor 페이지(이스터에그) 전용 — 접속 시각 기준 리포트. 읽기 전용·공개(latest.html 과 동일 정보)."""
        try:
            body = _monitor_live_html()
        except Exception:
            log.exception("monitor-live 생성 실패")
            return Response("error", status=500, headers={"Access-Control-Allow-Origin": "*"})
        return Response(body, mimetype="text/html", headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store",
        })

    @app.get("/")
    def _health():
        """헬스체크."""
        return "ok", 200


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 60)
    print("telegram_app.py v3 smoke test")
    print("=" * 60)

    # 전역 _enqueue_wake_now 스텁 (Cloud Tasks API 호출 방지)
    _orig_enqueue_wake_now_global = globals().get("_enqueue_wake_now")
    def _stub_enqueue_wake_global(*a, **kw):
        pass
    globals()["_enqueue_wake_now"] = _stub_enqueue_wake_global

    # ── 순수 헬퍼 ──────────────────────────────────────────────
    assert _tweet_url_from_tag("p#https://x.com/#1tweet-2096552878769152326") ==         "https://x.com/i/status/2096552878769152326"
    assert _tweet_url_from_tag("DownloadNotificationService") == ""
    assert _tweet_url_from_tag("") == "" and _tweet_url_from_tag(None) == ""
    print("[OK] _tweet_url_from_tag")

    # ── _expand_truncated_yt (버그리포트 #2) — 네트워크 안 타는 조기반환만 ──
    _TAG = "p#https://x.com/#1tweet-2096552878769152326"
    assert _TRUNC_YT_RE.search("見てね youtube.com/watch?v=4yH9F6…")
    assert not _TRUNC_YT_RE.search("youtube.com/watch?v=PAfMVT3GTLg")
    _full = "本日21時 配信\nhttps://www.youtube.com/watch?v=PAfMVT3GTLg"
    assert _expand_truncated_yt(_full, _TAG) == _full          # 온전한 URL 이미 있음
    assert _expand_truncated_yt("今日は歌枠やります", _TAG) == "今日は歌枠やります"  # 잘린 흔적 없음
    _tr = "配信 youtube.com/watch?v=4yH9F6…"
    assert _expand_truncated_yt(_tr, None) == _tr              # tweet id 없음 → 네트워크 미시도
    print("[OK] _expand_truncated_yt (조기반환)")

    # ── _recover_raw_via_vxtwitter (버그리포트 20260913, #2 조용한 잘림) — 조기반환만 ──
    assert _recover_raw_via_vxtwitter("", _TAG) == ("", None)      # 빈 raw → 네트워크 미시도
    _clean = "오늘 21시 방송해요"
    assert _recover_raw_via_vxtwitter(_clean, None) == (_clean, None)  # tweet id 없음 → 무회귀
    print("[OK] _recover_raw_via_vxtwitter (조기반환)")

    # ── _maybe_tag_cast_participants (v3.2 — 크로스오버 출연진 비전 OCR) ──
    _p1 = {"src_handle": "@BDP_yumemita"}
    _maybe_tag_cast_participants(_p1, _TAG)
    assert "participants" not in _p1, "대상 계정 아니면 손 안 댐"

    _p2 = {"src_handle": "RT @bang_dream_on"}
    _maybe_tag_cast_participants(_p2, None)  # tweet id 없음 → 네트워크 미시도
    assert "participants" not in _p2, "tweet id 없으면 손 안 댐"

    class _FakeVX:
        @staticmethod
        def fetch_tweet(tid):
            return {"id": tid}

        @staticmethod
        def extract(j):
            return {"media": ["https://pbs.twimg.com/media/fake.jpg"]}

    class _FakeVisionClient:
        def __init__(self, *a, **kw):
            pass

        def cast_names(self, *, image_url=None, image_bytes=None):
            return ["羊宮 妃那", "宮永 ののか", "?"]

    class _FakeVisionModule:
        VisionClient = _FakeVisionClient
        DEFAULT_VISION_MODEL = "fake-main"
        FALLBACK_VISION_MODEL = "fake-fallback"

    _orig_vxtwitter, _orig_vision = vxtwitter, vision
    _orig_groq_key = os.environ.get("GROQ_API_KEY")
    try:
        globals()["vxtwitter"] = _FakeVX
        globals()["vision"] = _FakeVisionModule
        os.environ["GROQ_API_KEY"] = "test-key"
        _p3 = {"src_handle": "RT @bang_dream_on"}
        _maybe_tag_cast_participants(_p3, _TAG)
        assert _p3["participants"] == ["nonoka"], _p3
    finally:
        globals()["vxtwitter"] = _orig_vxtwitter
        globals()["vision"] = _orig_vision
        if _orig_groq_key is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = _orig_groq_key
    print("[OK] _maybe_tag_cast_participants (대상 계정 필터 · 매칭 · 무회귀)")

    # ── _enrich_personal_media (v3.4.5 — 개인 트윗 미디어 + 인용 카드) ──
    assert _enrich_personal_media(None) == ([], None)          # tweet id 없음 → 무회귀
    assert _enrich_personal_media("DownloadNotificationService") == ([], None)

    _orig_vxtwitter = vxtwitter

    class _FakeVXQuote:
        @staticmethod
        def fetch_tweet(tid):
            if tid == "2096552878769152326":
                return {"id": tid, "qrtURL": "https://twitter.com/i/status/999"}
            if tid == "999":
                return {"id": tid, "text": "🎶楽曲情報🎶",
                        "mediaURLs": ["https://pbs.twimg.com/media/cover.jpg"]}
            return None

        @staticmethod
        def extract(j):
            return _orig_vxtwitter.extract(j) if j else {}

        qrt_id = staticmethod(lambda u: _orig_vxtwitter.qrt_id(u))

    try:
        globals()["vxtwitter"] = _FakeVXQuote
        media, quote = _enrich_personal_media(_TAG)
        assert media == [], media                    # 본인 트윗 자체엔 미디어 없음(인용만 있음)
        assert quote == {"text": "🎶楽曲情報🎶",
                          "media": ["https://pbs.twimg.com/media/cover.jpg"]}, quote
    finally:
        globals()["vxtwitter"] = _orig_vxtwitter
    print("[OK] _enrich_personal_media (인용 트윗 텍스트+이미지 · 무회귀)")

    # ── _enrich_personal_media: prefetched 로 본인 트윗 재조회 생략 (중복 fetch 방지) ──
    class _FakeVXNoRefetch:
        @staticmethod
        def fetch_tweet(tid):
            if tid == "2096552878769152326":
                raise AssertionError("본인 트윗은 prefetched 로 넘겼으니 재조회하면 안 됨")
            if tid == "999":
                return {"id": tid, "text": "🎶楽曲情報🎶", "mediaURLs": []}
            return None

        @staticmethod
        def extract(j):
            return _orig_vxtwitter.extract(j) if j else {}

        qrt_id = staticmethod(lambda u: _orig_vxtwitter.qrt_id(u))

    try:
        globals()["vxtwitter"] = _FakeVXNoRefetch
        prefetched = {"media": [], "qrt_url": "https://twitter.com/i/status/999"}
        media, quote = _enrich_personal_media(_TAG, prefetched=prefetched)
        assert media == [] and quote == {"text": "🎶楽曲情報🎶", "media": []}, (media, quote)
    finally:
        globals()["vxtwitter"] = _orig_vxtwitter
    print("[OK] _enrich_personal_media (prefetched 재사용 — 본인 트윗 중복 fetch 없음)")

    # ── 6상태 정렬·표시 ───────────────────────────────────────
    _pv = {"items": [
        {"id": "pv_a", "channel_key": "arale", "state": "announced",
         "scheduled_start": "2026-09-10T05:00:00Z", "title": "예고A"},
        {"id": "pv_b", "channel_key": "arale", "state": "live",
         "scheduled_start": "2026-09-09T12:00:00Z", "title": "라이브B"},
        {"id": "pv_c", "channel_key": "nonoka", "state": "watching",
         "collab_with": ["arale"], "scheduled_start": "2026-09-09T13:00:00Z"},
    ]}
    _s = _sorted_unit_broadcasts(_pv, "arale")
    assert [b["id"] for b in _s] == ["pv_b", "pv_c", "pv_a"], [b["id"] for b in _s]
    _cfg = {"channels": {"arale": {"name_ko": "아라레"}, "nonoka": {"name_ko": "노노카"}}}
    _txt = _format_list_text(_cfg, _pv, "arale")
    assert "아라레" in _txt and "#1" in _txt
    print("[OK] _sorted_unit_broadcasts / _format_list_text (state 정렬)")

    # ── _merge_rows_into_schedule → preview.json items ────────
    class _FakeGH:
        def __init__(self):
            self.store = {}
        def read_json(self, path):
            return (self.store.get(path), "sha0" if path in self.store else None)
        def write_json(self, path, data, *, prev_sha=None, message=""):
            before = self.store.get(path)
            self.store[path] = data
            return (before != data, "sha1")
        def read_text(self, path):
            return (self.store.get(path), "sha0" if path in self.store else None)
        def write_text(self, path, text, *, prev_sha=None, message=""):
            before = self.store.get(path)
            self.store[path] = text
            return (before != text, "sha1")

    if xrelay is not None:
        g = _FakeGH()
        _nl = chr(10)
        _sample = _nl.join([
            "🛸#ゆめみた",
            "9/10(水) 配信スケジュール",
            "🎮21:00〜 峰月律",
            "youtube.com/@ritsu_yumemita",
            "※時刻は予告なく変更の場合がございます。",
        ])
        rows = xrelay.parse(_sample, "2026-09-09T00:00:00Z")
        if rows:
            ch = _merge_rows_into_schedule(g, rows, "2026-09-09T00:00:00Z",
                                          message="test", action="test ingest")
            pv = g.store.get(_PREVIEW_PATH) or {}
            assert pv.get("items"), "preview.items 반영 안 됨"
            assert all(it.get("state") == "announced" for it in pv["items"]), pv["items"]
            # undo 스냅샷
            adm = g.store.get(_ADMIN_STATE_PATH) or {}
            assert adm.get("undo", {}).get("path") == "preview.json"
            print(f"[OK] _merge_rows_into_schedule → preview.json ({len(pv['items'])} items, undo path 확인)")

            # _remove_broadcast — id 매칭
            snap = dict(pv["items"][0])
            g.store[_PREVIEW_PATH]["items"][0]["last_updated"] = "changed"  # volatile 변화
            removed = _remove_broadcast(g, snap, "2026-09-09T01:00:00Z", "test del")
            assert removed and not g.store[_PREVIEW_PATH]["items"], "id 매칭 삭제 실패"
            print("[OK] _remove_broadcast (id 매칭)")
        else:
            print("[skip] xrelay.parse 0행 — 파서 픽스처 확인")

    # ── (v3.6) _maybe_url_confirmed_schedule — URL 우선 ingest ────
    _CFG6 = {
        "channel_order": ["arale", "yuno", "nonoka", "ritsu", "miyako"],
        "channels": {
            "arale": {"channel_id": "UC_arale", "name_ko": "아라레"},
            "yuno": {"channel_id": "UC_yuno", "name_ko": "유노"},
            "nonoka": {"channel_id": "UC_nonoka", "name_ko": "노노카"},
            "ritsu": {"channel_id": "UC_ritsu", "name_ko": "리츠"},
            "miyako": {"channel_id": "UC_miyako", "name_ko": "미야코"},
            "group": {"channel_id": "UC_group", "name_ko": "그룹"},
        },
    }

    class _FakeVideoInfo:
        def __init__(self, video_id, channel_id, title, live_state,
                     scheduled_start=None, actual_start=None, concurrent_viewers=None):
            self.video_id = video_id
            self.channel_id = channel_id
            self.title = title
            self.thumbnail = "thumb.jpg"
            self.live_state = live_state
            self.scheduled_start = scheduled_start
            self.actual_start = actual_start
            self.concurrent_viewers = concurrent_viewers

    class _FakeYouTubeClient:
        _RESP = {}
        def __init__(self, api_key):
            pass
        def videos_list(self, ids):
            return {vid: self._RESP[vid] for vid in ids if vid in self._RESP}

    _orig_YTC = YouTubeClient
    _orig_env = dict(os.environ)
    _orig_enqueue = _enqueue_wake_now
    try:
        globals()["YouTubeClient"] = _FakeYouTubeClient
        globals()["_enqueue_wake_now"] = lambda video_id, when: None  # 실제 Cloud Tasks 호출 스킵
        os.environ["YOUTUBE_API_KEY"] = "test-key"

        # URL 없음 → False(호출부가 기존 텍스트 파싱 경로로)
        g6 = _FakeGH()
        assert _maybe_url_confirmed_schedule(
            g6, "配信するよ〜 詳細は後で", "nonoka", "2026-09-16T12:00:05Z", _CFG6
        ) is False
        print("[OK] _maybe_url_confirmed_schedule (유튜브 URL 없음 → False, 텍스트 파싱에 위임)")

        # 유튜브 URL은 있는데 API로 확정을 못함(videos.list 예외) → False 로 폴백
        # (구버전 최소 신뢰도 보장 — 조용히 드롭하면 안 됨)
        class _FailingYouTubeClient:
            def __init__(self, api_key):
                pass
            def videos_list(self, ids):
                raise RuntimeError("network down")
        globals()["YouTubeClient"] = _FailingYouTubeClient
        g6b = _FakeGH()
        assert _maybe_url_confirmed_schedule(
            g6b, "配信するよ https://www.youtube.com/watch?v=abcdEFGH123",
            "nonoka", "2026-09-16T12:00:05Z", _CFG6,
        ) is False
        globals()["YouTubeClient"] = _FakeYouTubeClient
        print("[OK] _maybe_url_confirmed_schedule (videos.list 예외 → False, 텍스트 파싱 폴백)")

        # (v3.6) 조용히 스킵하지 않고 monitor 이벤트 로그에 degraded 로 남기는지 확인
        _ev_log = next((v for k, v in g6b.store.items() if k.startswith("monitoring/events-")), "")
        assert '"result": "degraded"' in _ev_log and "videos.list" in _ev_log, _ev_log
        print("[OK] _maybe_url_confirmed_schedule (폴백 사유를 monitor 이벤트 로그에 degraded 로 기록)")

        # 같은 상황을 _maybe_nonyt_url_notice 로 잘못 흘려보내 소식으로 오분류하지 않는지 확인
        assert _maybe_nonyt_url_notice(
            g6b, "配信するよ https://www.youtube.com/watch?v=abcdEFGH123",
            None, "2026-09-16T12:00:05Z",
        ) is False
        print("[OK] _maybe_nonyt_url_notice (유튜브 URL 은 비유튜브로 오분류 안 함)")

        # 본인 채널의 라이브 시작 트윗 — 버그리포트 20260916 #1 재현 (配信 키워드 없어도 잡힘)
        _FakeYouTubeClient._RESP = {
            "9Di14qEQJH8": _FakeVideoInfo(
                "9Di14qEQJH8", "UC_nonoka", "방송 시작!", "live",
                scheduled_start="2026-09-16T11:06:58Z",
                actual_start="2026-09-16T11:07:20Z", concurrent_viewers=627,
            )
        }
        g7 = _FakeGH()
        ok = _maybe_url_confirmed_schedule(
            g7,
            "お待たせしました！はじまりますたー https://www.youtube.com/live/9Di14qEQJH8?si=xxx",
            "nonoka", "2026-09-16T12:00:05Z", _CFG6,
        )
        assert ok is True
        pv7 = g7.store.get(_PREVIEW_PATH) or {}
        items7 = pv7.get("items") or []
        assert len(items7) == 1 and items7[0]["state"] == "live", items7
        assert items7[0]["channel_key"] == "nonoka"
        print("[OK] _maybe_url_confirmed_schedule (配信 키워드 없는 트윗도 URL 로 잡아 live 로 즉시 등록)")

        # undo 스냅샷 — /undo 로 되돌릴 수 있어야 함(LLM/videos.list 오판 대비 안전장치)
        adm7 = g7.store.get(_ADMIN_STATE_PATH) or {}
        assert adm7.get("undo", {}).get("path") == _PREVIEW_PATH, adm7
        print("[OK] _maybe_url_confirmed_schedule (undo 스냅샷 기록 — /undo 가능)")

        # 다른 멤버 채널에서 열린 콜라보 — host=그 채널, collab_with=작성자
        g8 = _FakeGH()
        _FakeYouTubeClient._RESP = {
            "collabVid12": _FakeVideoInfo("collabVid12", "UC_ritsu", "합동 방송", "upcoming",
                                        scheduled_start="2026-09-20T10:00:00Z")
        }
        _maybe_url_confirmed_schedule(
            g8, "りっちゃんと一緒に配信するよ https://www.youtube.com/watch?v=collabVid12",
            "nonoka", "2026-09-16T12:00:05Z", _CFG6,
        )
        pv8 = (g8.store.get(_PREVIEW_PATH) or {}).get("items") or []
        assert pv8 and pv8[0]["channel_key"] == "ritsu" and pv8[0]["collab_with"] == ["nonoka"], pv8
        print("[OK] _maybe_url_confirmed_schedule (타 멤버 채널 콜라보 → host=그 채널, collab_with=작성자)")

        # (v3.8.3) 본인 채널 합동 — 리츠 채널 영상 제목에 千石ユノ → 게스트 후보.
        # (v3.8.6) 언급만으론 확정 안 함 — LLM collab_partners() 로 재확인해야 collab_with 반영.
        _CFG8 = {**_CFG6, "channels": {**_CFG6["channels"],
                 "yuno": {**_CFG6["channels"]["yuno"], "x_names": ["千石ユノ"]},
                 "ritsu": {**_CFG6["channels"]["ritsu"], "x_names": ["峰月律"]}}}

        import src.backend.llm as _llm_mod2

        class _FakeCollabLLM:
            _CONFIRMED = []
            def __init__(self, api_key):
                pass
            def collab_partners(self, text, *, host_name, candidate_names):
                return self._CONFIRMED

        _orig_llm_cls2 = _llm_mod2.LLMClient
        try:
            _llm_mod2.LLMClient = _FakeCollabLLM

            # GROQ_API_KEY 없음 → LLM 호출 자체가 불가 → 게스트 미추가(안전한 실패)
            g9a = _FakeGH()
            _FakeYouTubeClient._RESP = {
                "Fd47-ZE1GVs": _FakeVideoInfo("Fd47-ZE1GVs", "UC_ritsu",
                                              "【#ぷりはとDay1】ユノ＆律こらぼ【峰月律/千石ユノ】", "upcoming",
                                              scheduled_start="2026-09-21T12:00:00Z")
            }
            _maybe_url_confirmed_schedule(
                g9a, "配信予定 9/21 21:00 ユノ＆律こらぼ https://www.youtube.com/live/Fd47-ZE1GVs",
                "ritsu", "2026-09-21T04:34:41Z", _CFG8,
            )
            pv9a = (g9a.store.get(_PREVIEW_PATH) or {}).get("items") or []
            assert pv9a and pv9a[0]["collab_with"] is None, pv9a
            print("[OK] _maybe_url_confirmed_schedule (이름 언급 + GROQ_API_KEY 없음 → 게스트 미추가, 안전한 실패)")

            os.environ["GROQ_API_KEY"] = "test-key"

            # LLM "합동 아님"(안부/오탐 등) → 이름이 나와도 collab_with 미추가
            _FakeCollabLLM._CONFIRMED = []
            g9b = _FakeGH()
            _FakeYouTubeClient._RESP = {
                "Fd47-ZE1GVs": _FakeVideoInfo("Fd47-ZE1GVs", "UC_ritsu",
                                              "【#ぷりはとDay1】ユノ＆律こらぼ【峰月律/千石ユノ】", "upcoming",
                                              scheduled_start="2026-09-21T12:00:00Z")
            }
            _maybe_url_confirmed_schedule(
                g9b, "配信予定 9/21 21:00 ユノ＆律こらぼ https://www.youtube.com/live/Fd47-ZE1GVs",
                "ritsu", "2026-09-21T04:34:41Z", _CFG8,
            )
            pv9b = (g9b.store.get(_PREVIEW_PATH) or {}).get("items") or []
            assert pv9b and pv9b[0]["collab_with"] is None, pv9b
            print("[OK] _maybe_url_confirmed_schedule (이름 언급 + LLM 미확인 → collab_with 미추가, 오탐 방지)")

            # LLM "실제 합동" 확인 → collab_with=[yuno] 반영
            _FakeCollabLLM._CONFIRMED = ["유노"]
            g9 = _FakeGH()
            _FakeYouTubeClient._RESP = {
                "Fd47-ZE1GVs": _FakeVideoInfo("Fd47-ZE1GVs", "UC_ritsu",
                                              "【#ぷりはとDay1】ユノ＆律こらぼ【峰月律/千石ユノ】", "upcoming",
                                              scheduled_start="2026-09-21T12:00:00Z")
            }
            _maybe_url_confirmed_schedule(
                g9, "配信予定 9/21 21:00 ユノ＆律こらぼ https://www.youtube.com/live/Fd47-ZE1GVs",
                "ritsu", "2026-09-21T04:34:41Z", _CFG8,
            )
            pv9 = (g9.store.get(_PREVIEW_PATH) or {}).get("items") or []
            assert pv9 and pv9[0]["channel_key"] == "ritsu" and pv9[0]["collab_with"] == ["yuno"]                 and pv9[0]["kind"] == "collab", pv9
            print("[OK] _maybe_url_confirmed_schedule (LLM 이 합동으로 확인 → collab_with=[yuno])")
        finally:
            _llm_mod2.LLMClient = _orig_llm_cls2
            os.environ.pop("GROQ_API_KEY", None)

        # (v3.8.5 핫픽스) 실측 버그(2026-09-22) — 리츠가 유노의 예고를 QRT, 자기 코멘트엔
        # URL 이 없고 인용문에만 있음. raw 단독으론 등록 안 되던 것 → quote 합본으로 등록.
        g10 = _FakeGH()
        _FakeYouTubeClient._RESP = {
            "nC4Bkg96ujM": _FakeVideoInfo("nC4Bkg96ujM", "UC_yuno", "お食べ。", "upcoming",
                                          scheduled_start="2026-09-22T13:00:00Z")
        }
        assert _maybe_url_confirmed_schedule(
            g10, "肉、食べます\nユノちゃんちに来ました", "ritsu", "2026-09-22T11:35:37Z", _CFG6,
        ) is False, "quote 미지정 + raw 에 URL 없음 → False (기존 동작 보존)"
        pv10 = (g10.store.get(_PREVIEW_PATH) or {}).get("items") or []
        assert not pv10
        print("[OK] _maybe_url_confirmed_schedule (quote 미지정시 raw 만 검색 — 기존 동작 보존)")

        g11c = _FakeGH()
        _maybe_url_confirmed_schedule(
            g11c, "肉、食べます\nユノちゃんちに来ました", "ritsu", "2026-09-22T11:35:37Z", _CFG6,
            quote="〈配信のおしらせ〉\n9/22 22:00～ #ぷりはとDay2\n\n肉を食べます\n\n"
                  "https://www.youtube.com/live/nC4Bkg96ujM",
        )
        pv11c = (g11c.store.get(_PREVIEW_PATH) or {}).get("items") or []
        assert pv11c and pv11c[0]["channel_key"] == "yuno" and pv11c[0]["collab_with"] == ["ritsu"], pv11c
        print("[OK] _maybe_url_confirmed_schedule (URL이 quote에만 있어도 raw+quote 합본으로 등록, collab_with=[ritsu])")

        # (v3.8.6) _confirm_relay_rows_collab — 공식 계정 일일 스케줄(× 콜라보)도
        # 이름 매치만으론 확정 안 하고 무조건 LLM 재확인
        import src.backend.llm as _llm_mod4

        class _FakeRelayLLM:
            _CONFIRMED: list[str] = []
            def __init__(self, api_key):
                pass
            def collab_partners(self, text, *, host_name, candidate_names):
                return self._CONFIRMED

        _orig_llm_cls4 = _llm_mod4.LLMClient
        try:
            _llm_mod4.LLMClient = _FakeRelayLLM
            _RAW_COLLAB = (
                "／\n🛸夢限大みゅーたいぷ\n8/29(土) 配信スケジュール🌟\n＼\n\n"
                "💪12:00〜 仲町あられ×藤都子\n"
            )
            rows_src = xrelay.parse(_RAW_COLLAB, "2026-09-03T00:00:00Z")
            col_row = next(r for r in rows_src if r.get("kind") == "collab")
            assert col_row["channel_key"] == "arale" and col_row["collab_with"] == ["miyako"], col_row

            # GROQ_API_KEY 없음 → × 매치돼도 게스트 미추가(kind 도 되돌림)
            os.environ.pop("GROQ_API_KEY", None)
            g14 = _FakeGH()
            out14 = _confirm_relay_rows_collab(
                g14, _RAW_COLLAB, [dict(r) for r in rows_src], _CFG6,
                "2026-09-03T00:00:05Z", via="ingest")
            c14 = next(r for r in out14 if r["channel_key"] == "arale")
            assert c14["collab_with"] is None and c14["kind"] is None, c14
            print("[OK] _confirm_relay_rows_collab (GROQ_API_KEY 없음 → × 콜라보도 게스트 미추가)")

            os.environ["GROQ_API_KEY"] = "test-key"

            # LLM "합동 아님" → × 매치돼도 collab_with 제거
            _FakeRelayLLM._CONFIRMED = []
            g15 = _FakeGH()
            out15 = _confirm_relay_rows_collab(
                g15, _RAW_COLLAB, [dict(r) for r in rows_src], _CFG6,
                "2026-09-03T00:00:05Z", via="ingest")
            c15 = next(r for r in out15 if r["channel_key"] == "arale")
            assert c15["collab_with"] is None and c15["kind"] is None, c15
            print("[OK] _confirm_relay_rows_collab (LLM 미확인 → × 매치돼도 collab_with 제거, 오탐 방지)")

            # LLM "실제 합동" 확인 → 그대로 유지
            _FakeRelayLLM._CONFIRMED = ["미야코"]
            g16 = _FakeGH()
            out16 = _confirm_relay_rows_collab(
                g16, _RAW_COLLAB, [dict(r) for r in rows_src], _CFG6,
                "2026-09-03T00:00:05Z", via="ingest")
            c16 = next(r for r in out16 if r["channel_key"] == "arale")
            assert c16["collab_with"] == ["miyako"] and c16["kind"] == "collab", c16
            print("[OK] _confirm_relay_rows_collab (LLM 이 합동으로 확인 → × 콜라보 유지)")

            # host="group"(전원 팬아웃)은 이름 언급이 아니라 인원수/전체 표기 신호라 게이트 제외
            _RAW_GROUP = (
                "＼🛸出演情報📢／\n\n9/10(木) 22:00頃〜\n「이벤트」\n\n"
                "夢限大みゅーたいぷ 5名が出演🛸\n\nhttps://youtube.com/live/ri2_BimgJIA"
            )
            rows_group = xrelay.parse(_RAW_GROUP, "2026-09-03T00:00:00Z")
            g17 = _FakeGH()
            out17 = _confirm_relay_rows_collab(
                g17, _RAW_GROUP, [dict(r) for r in rows_group], _CFG6,
                "2026-09-03T00:00:05Z", via="ingest")
            assert out17[0]["host"] == "group" and out17[0]["collab_with"] == [
                "yuno", "nonoka", "ritsu", "miyako"], out17
            print("[OK] _confirm_relay_rows_collab (host=group 전원 팬아웃은 게이트 제외)")
        finally:
            _llm_mod4.LLMClient = _orig_llm_cls4
            os.environ.pop("GROQ_API_KEY", None)
    finally:
        globals()["YouTubeClient"] = _orig_YTC
        globals()["_enqueue_wake_now"] = _orig_enqueue
        os.environ.clear()
        os.environ.update(_orig_env)

    # ── (v3.6) 비유튜브 URL → 소식(notice) 이관 ──────────────
    if xnotice is not None:
        g9 = _FakeGH()
        handled = _maybe_nonyt_url_notice(
            g9, "9/20 bilibiliでも同時配信するよ〜 https://live.bilibili.com/12345678",
            None, "2026-09-16T12:00:00Z",
        )
        assert handled is True
        nj9 = g9.store.get(_NOTICES_PATH) or {}
        assert (nj9.get("notices") or []), "비유튜브 URL 이 notices.json 에 안 실림"
        pv9 = g9.store.get(_PREVIEW_PATH)
        assert not pv9, "비유튜브 URL 이 preview.json 에 잘못 등록됨"
        print("[OK] _maybe_nonyt_url_notice (bilibili 링크 → notices.json 이관, preview 는 안 건드림)")

        g10 = _FakeGH()
        assert _maybe_nonyt_url_notice(g10, "配信するよ〜 詳細は後で", None, "2026-09-16T12:00:00Z") is False
        print("[OK] _maybe_nonyt_url_notice (URL 자체 없음 → False, 텍스트 경로에 위임)")

    # ── (v3.6) URL 없는 텍스트 예고 — LLM 최종 확인 게이트 ────
    if xtweet is not None:
        import src.backend.llm as _llm_mod

        class _FakeAnnounceLLM:
            _ANSWER = True
            def __init__(self, api_key):
                pass
            def announces_own_broadcast(self, text):
                return self._ANSWER

        _orig_llm_cls = _llm_mod.LLMClient
        _orig_make_gh = _make_gh
        _orig_env2 = dict(os.environ)
        try:
            os.environ["GROQ_API_KEY"] = "test-key"
            _llm_mod.LLMClient = _FakeAnnounceLLM

            # 진짜 예고 + LLM "yes" → preview.json 에 등록됨
            _FakeAnnounceLLM._ANSWER = True
            g11 = _FakeGH()
            globals()["_make_gh"] = lambda: g11
            _maybe_personal_schedule(
                "明日22時から歌枠やります🎤", tag=None, channel_key="ritsu",
                name="리츠", handle="ritsu_yumemita", now_iso="2026-09-16T12:00:00Z",
            )
            pv11 = (g11.store.get(_PREVIEW_PATH) or {}).get("items") or []
            assert pv11 and pv11[0]["channel_key"] == "ritsu", pv11
            print("[OK] _maybe_personal_schedule (텍스트 예고 + LLM yes → 등록됨)")

            # 아라레 후기 실사례 — 정규식은 후보를 뽑지만 LLM "no" → 미등록
            _FakeAnnounceLLM._ANSWER = False
            g12 = _FakeGH()
            globals()["_make_gh"] = lambda: g12
            _maybe_personal_schedule(
                "#アワーノーツ 先行プレイ配信\nありがとうございました！"
                "ガッツリ2時間プレイ！！\n9/24まで待ち遠しい〜〜〜！！！",
                tag=None, channel_key="arale", name="아라레", handle="arale_yumemita",
                now_iso="2026-09-16T12:00:00Z",
            )
            pv12 = (g12.store.get(_PREVIEW_PATH) or {}).get("items") or []
            assert not pv12, pv12
            print("[OK] _maybe_personal_schedule (아라레 후기 실사례 + LLM no → 미등록, 오탐 방지)")

            # GROQ_API_KEY 없으면 LLM 호출 자체가 불가 → 안전한 실패(미등록)
            del os.environ["GROQ_API_KEY"]
            g13 = _FakeGH()
            globals()["_make_gh"] = lambda: g13
            _maybe_personal_schedule(
                "明日22時から歌枠やります🎤", tag=None, channel_key="ritsu",
                name="리츠", handle="ritsu_yumemita", now_iso="2026-09-16T12:00:00Z",
            )
            assert not (g13.store.get(_PREVIEW_PATH) or {}).get("items")
            print("[OK] _maybe_personal_schedule (GROQ_API_KEY 없음 → 미등록, 안전한 실패)")
            _ev13 = next((v for k, v in g13.store.items() if k.startswith("monitoring/events-")), "")
            assert '"result": "degraded"' in _ev13 and "GROQ_API_KEY" in _ev13, _ev13
            print("[OK] _maybe_personal_schedule (GROQ_API_KEY 없음도 monitor 이벤트 로그에 degraded 로 기록)")
        finally:
            _llm_mod.LLMClient = _orig_llm_cls
            globals()["_make_gh"] = _orig_make_gh
            os.environ.clear()
            os.environ.update(_orig_env2)

    # ── (v3.8.7) _maybe_broadcast_change — 기존 예고 취소/변경 LLM 판정 ────
    if xtweet is not None:
        assert _parse_kst_mmdd_hhmm("09/23 23:00", "2026-09-22T12:00:00Z") == "2026-09-23T14:00:00Z", \
            _parse_kst_mmdd_hhmm("09/23 23:00", "2026-09-22T12:00:00Z")
        assert _parse_kst_mmdd_hhmm("헛소리", "2026-09-22T12:00:00Z") is None
        print("[OK] _parse_kst_mmdd_hhmm (KST MM/DD HH:MM → UTC ISO, 파싱 실패 → None)")

        _CFG_BC = {"channels": {"nonoka": {"name_ko": "노노카"}}}
        _NONOKA_ITEM = {
            "id": "pv_nonoka1", "channel_key": "nonoka", "state": "watching",
            "scheduled_start": "2026-09-22T11:30:00Z", "collab_with": None,
        }

        import src.backend.llm as _llm_mod5

        class _FakeChangeLLM:
            _RESULT = None
            def __init__(self, api_key):
                pass
            def broadcast_change(self, text):
                return self._RESULT

        _orig_llm_cls5 = _llm_mod5.LLMClient
        _orig_env5 = dict(os.environ)
        try:
            _llm_mod5.LLMClient = _FakeChangeLLM
            os.environ["GROQ_API_KEY"] = "test-key"

            # del → state=none 패치 + _activate_state_edit 로 즉시 제거·아카이브
            _FakeChangeLLM._RESULT = {"action": "del", "when": None}
            gbc1 = _FakeGH()
            gbc1.store[_PREVIEW_PATH] = {"items": [dict(_NONOKA_ITEM)]}
            _maybe_broadcast_change(gbc1, "本日こちらの配信なしで、今日おやすみです！",
                                    "nonoka", "2026-09-22T12:30:00Z", _CFG_BC)
            pv_bc1 = (gbc1.store.get(_PREVIEW_PATH) or {}).get("items") or []
            assert not pv_bc1, pv_bc1
            arch_bc1 = (gbc1.store.get(_PREVIEW_ARCHIVE_PATH) or {}).get("items") or []
            assert any(a.get("id") == "pv_nonoka1" for a in arch_bc1), arch_bc1
            print("[OK] _maybe_broadcast_change (LLM del → 기존 예고 즉시 제거+아카이브)")

            # edit → scheduled_start 갱신, 항목은 유지
            _FakeChangeLLM._RESULT = {"action": "edit", "when": "09/23 23:00"}
            gbc2 = _FakeGH()
            gbc2.store[_PREVIEW_PATH] = {"items": [dict(_NONOKA_ITEM)]}
            _maybe_broadcast_change(gbc2, "오늘 配信 못하고 내일 23시로 미룰게요",
                                    "nonoka", "2026-09-22T12:30:00Z", _CFG_BC)
            pv_bc2 = (gbc2.store.get(_PREVIEW_PATH) or {}).get("items") or []
            assert pv_bc2 and pv_bc2[0]["scheduled_start"] == "2026-09-23T14:00:00Z", pv_bc2
            print("[OK] _maybe_broadcast_change (LLM edit → scheduled_start 갱신, 항목 유지)")

            # none → 아무 변화 없음
            _FakeChangeLLM._RESULT = {"action": "none", "when": None}
            gbc3 = _FakeGH()
            gbc3.store[_PREVIEW_PATH] = {"items": [dict(_NONOKA_ITEM)]}
            _maybe_broadcast_change(gbc3, "오늘 방송 완전 재밌었다ㅎㅎ 配信 최고",
                                    "nonoka", "2026-09-22T12:30:00Z", _CFG_BC)
            pv_bc3 = (gbc3.store.get(_PREVIEW_PATH) or {}).get("items") or []
            assert pv_bc3 == [_NONOKA_ITEM], pv_bc3
            print("[OK] _maybe_broadcast_change (LLM none → 무변화, 평소 후기 오탐 방지)")

            # 대상 예고 자체가 없으면 LLM 호출 없이 스킵(호출됐으면 위 _RESULT=none 이라 통과했을 것이므로,
            # 여기선 store 자체가 안 변하는지만 확인 — 활성 아이템 없는 상태)
            gbc4 = _FakeGH()
            gbc4.store[_PREVIEW_PATH] = {"items": []}
            _maybe_broadcast_change(gbc4, "配信します!", "nonoka",
                                    "2026-09-22T12:30:00Z", _CFG_BC)
            assert not (gbc4.store.get(_PREVIEW_PATH) or {}).get("items")
            print("[OK] _maybe_broadcast_change (대상 활성 예고 없음 → 스킵)")

            # 配信 키워드 자체가 없으면 스킵(대상이 있어도)
            gbc5 = _FakeGH()
            gbc5.store[_PREVIEW_PATH] = {"items": [dict(_NONOKA_ITEM)]}
            _maybe_broadcast_change(gbc5, "오늘 날씨 좋다", "nonoka",
                                    "2026-09-22T12:30:00Z", _CFG_BC)
            assert gbc5.store[_PREVIEW_PATH]["items"] == [_NONOKA_ITEM]
            print("[OK] _maybe_broadcast_change (配信 키워드 없음 → 스킵)")

            # GROQ_API_KEY 없음 → 안전한 실패(미반영) + degraded 로그
            del os.environ["GROQ_API_KEY"]
            gbc6 = _FakeGH()
            gbc6.store[_PREVIEW_PATH] = {"items": [dict(_NONOKA_ITEM)]}
            _maybe_broadcast_change(gbc6, "本日こちらの配信なしで、今日おやすみです！",
                                    "nonoka", "2026-09-22T12:30:00Z", _CFG_BC)
            assert gbc6.store[_PREVIEW_PATH]["items"] == [_NONOKA_ITEM]
            _ev_bc6 = next((v for k, v in gbc6.store.items() if k.startswith("monitoring/events-")), "")
            assert '"result": "degraded"' in _ev_bc6 and "GROQ_API_KEY" in _ev_bc6, _ev_bc6
            print("[OK] _maybe_broadcast_change (GROQ_API_KEY 없음 → 미반영, degraded 로그)")
        finally:
            _llm_mod5.LLMClient = _orig_llm_cls5
            os.environ.clear()
            os.environ.update(_orig_env5)

    # ── (v3.7) notice 의미 중복 게이트 — 같은 날짜만 후보(threshold=0일), LLM 판정 ──
    if notices is not None:
        import src.backend.llm as _llm_mod3

        class _FakeDupLLM:
            _DUP = None
            def __init__(self, api_key, **kw):
                pass
            def duplicate_notice(self, new_text, candidates):
                return self._DUP

        _orig_llm_cls3 = _llm_mod3.LLMClient
        _orig_env3 = dict(os.environ)
        try:
            os.environ["GROQ_API_KEY"] = "test-key"
            _llm_mod3.LLMClient = _FakeDupLLM

            _prev = {"notices": [
                {"id": "a1", "date": "2026-09-20", "title": "유노 생일 축하", "body_raw": "오늘은 유노 생일!"},
                {"id": "b1", "date": "2026-09-21", "title": "아라레 생일 축하", "body_raw": "오늘은 아라레 생일!"},
            ]}
            new_p = {"date": "2026-09-20", "body_raw": "유노쨩 생일이래! 다들 축하해줘"}

            # 같은 날짜 후보만 넘어가는지 확인 + LLM 이 그 중 하나를 중복으로 판정하면 그 id 반환
            _FakeDupLLM._DUP = "a1"
            assert _inline_notice_dup_check(new_p, _prev) == "a1"
            print("[OK] _inline_notice_dup_check (같은 날짜 후보만 LLM 에 넘김 — LLM 판정 그대로 반환)")

            # threshold=0일 — 후보 자체가 없으면(그 날짜 소식이 없음) LLM 호출 없이 None
            assert _inline_notice_dup_check({"date": "2026-09-22", "body_raw": "x"}, _prev) is None
            print("[OK] _inline_notice_dup_check (해당 날짜 후보 없음 → LLM 호출 없이 None)")

            # LLM 이 "중복 없음"(None) 판정하면 그대로 None — 새 소식으로 진행
            _FakeDupLLM._DUP = None
            assert _inline_notice_dup_check(new_p, _prev) is None
            print("[OK] _inline_notice_dup_check (LLM 이 중복없음 판정 → None, 새 소식 진행)")

            # GROQ_API_KEY 없으면 LLM 호출 자체가 불가 → 안전하게 None(새 소식으로 진행)
            del os.environ["GROQ_API_KEY"]
            assert _inline_notice_dup_check(new_p, _prev) is None
            print("[OK] _inline_notice_dup_check (GROQ_API_KEY 없음 → None, 안전한 실패)")
        finally:
            _llm_mod3.LLMClient = _orig_llm_cls3
            os.environ.clear()
            os.environ.update(_orig_env3)

    # ── _build_status_text ───────────────────────────────────
    class _StatusGH:
        def __init__(self, d):
            self.d = d
        def read_json(self, path):
            return (self.d.get(path), None)
    sg = _StatusGH({
        _PREVIEW_PATH: {"generated_at": "2026-09-09T12:00:00Z", "items": [
            {"state": "announced"}, {"state": "live"}, {"state": "live"}]},
        _NOTICES_PATH: {"notices": [{"date": "2026-09-11"}, {"date": "2026-09-20", "needs_tl": True}]},
        # 계약 I — tweets[ck] 는 배열. yuno 는 2건(둘 다 needs_tl), nonoka 는 v2.8 단건 dict 호환.
        _TWEETS_PATH: {"tweets": {
            "arale": [{"id": "a1"}],
            "yuno": [{"id": "y1", "needs_tl": True}, {"id": "y2", "needs_tl": True}],
            "nonoka": {"id": "n1"},
        }},
        "control.json": default_control(),
    })
    st = _build_status_text("2026-09-09T12:05:00Z", sg, _cfg)
    assert "mewtype v3" in st and "announced 1" in st and "live 2" in st
    assert "notice   2건" in st and "LLM 큐   3건" in st, st          # notice 1 + tweet 2
    assert "yuno×2" in st, st
    print("[OK] _build_status_text (v3)")

    # ── {cmd}×{contents} 격자 + /edit preview 마법사 ──────────
    assert _split_contents("notice 3") == ("notice", "3")
    assert _split_contents("arale") == ("preview", "arale")   # v2 하위호환
    assert _split_contents("") == ("preview", "")
    assert _split_contents("tweet") == ("tweet", "")
    print("[OK] _split_contents")

    # ── /translate 결과 보고 ──────────
    assert _translate_report("소식", 0, 0, 0) == "번역할 소식이 없습니다."
    assert _translate_report("소식", 7, 0, 0) == "소식 7건 모두 번역돼 있습니다."
    r = _translate_report("소식", 7, 2, 1)
    assert "총 7건" in r and "시도 2건" in r and "성공 1 / 실패 1" in r and "기존 5건" in r, r
    assert "needs_tl" in r, r
    assert "재시도" not in _translate_report("트윗", 3, 3, 3)   # 전부 성공이면 재시도 문구 없음
    print("[OK] _translate_report")

    class _GH:
        def __init__(self):
            self.store = {}
        def read_json(self, path):
            return (self.store.get(path), "s" if path in self.store else None)
        def write_json(self, path, data, *, prev_sha=None, message=""):
            ch = self.store.get(path) != data
            import copy
            self.store[path] = copy.deepcopy(data)
            return (ch, "s2")

    if admin is not None:
        g = _GH()
        g.store[_PREVIEW_PATH] = {"items": [
            {"id": "pv_x1", "channel_key": "arale", "state": "watching",
             "scheduled_start": "2026-09-10T05:00:00Z", "title": "구제목",
             "url": "https://youtube.com/watch?v=vvv"},
        ]}
        _cfg2 = {"channels": {"arale": {"name_ko": "아라레"}}}
        NW = "2026-09-09T12:00:00Z"
        _handle_edit(g, _cfg2, NW, "preview", "")
        assert admin.get_pending_op(g.store[_ADMIN_STATE_PATH])["cmd"] == "edit"
        assert _handle_op_followup(g, _cfg2, NW, {}, "arale") is True     # await_unit
        assert _handle_op_followup(g, _cfg2, NW, {}, "1") is True         # await_idx → lock
        assert admin.get_edit_lock(g.store[_ADMIN_STATE_PATH])["id"] == "pv_x1"
        assert _handle_op_followup(g, _cfg2, NW, {}, "title") is True     # await_field
        assert _handle_op_followup(g, _cfg2, NW, {}, "새제목") is True     # await_value
        assert _handle_op_followup(g, _cfg2, NW, {}, "done") is True      # 적용
        _it = g.store[_PREVIEW_PATH]["items"][0]
        assert _it["title"] == "새제목" and _it["state"] == "watching", _it
        assert admin.get_pending_op(g.store[_ADMIN_STATE_PATH]) is None
        assert admin.get_edit_lock(g.store[_ADMIN_STATE_PATH]) is None
        assert g.store[_ADMIN_STATE_PATH]["undo"]["path"] == "preview.json"
        # 취소 토큰
        _handle_edit(g, _cfg2, NW, "preview", "")
        assert _handle_op_followup(g, _cfg2, NW, {}, _INGEST_CANCEL_TOKEN) is True
        assert admin.get_pending_op(g.store[_ADMIN_STATE_PATH]) is None
        print("[OK] /edit preview 마법사 (unit→idx→field→value→done, 락·undo·취소)")

        # (v3.1.17) state 를 직접 바꾸면 라벨만 안 바뀌고 그 상태에 맞는 로직이 실제로
        # 이행되는지 — _activate_state_edit 경로.
        os.environ.pop("MAIN_SERVICE_URL", None)  # 메인 서비스 미설정 상태로 고정

        # (a) video_id 없는 announced 자리표시 → state="none" 직접 지정 시 즉시 제거+아카이브.
        g2 = _GH()
        g2.store[_PREVIEW_PATH] = {"items": [
            {"id": "pv_none1", "channel_key": "arale", "state": "announced",
             "scheduled_start": "2026-09-10T05:00:00Z", "title": "제거될 예고",
             "video_id": None},
        ]}
        r_none = _activate_state_edit(
            g2, {"id": "pv_none1", "state": "none", "channel_key": "arale", "video_id": None}, NW,
        )
        assert "아카이브" in r_none, r_none
        assert g2.store[_PREVIEW_PATH]["items"] == [], g2.store[_PREVIEW_PATH]
        assert g2.store[_PREVIEW_ARCHIVE_PATH]["items"][0]["id"] == "pv_none1", g2.store[_PREVIEW_ARCHIVE_PATH]
        print("[OK] _activate_state_edit: state→none 즉시 제거+아카이브")

        # (b) video_id 있는 아이템 → MAIN_SERVICE_URL 미설정이면 안 죽고 안내만.
        item_b = {"id": "pv_x1", "state": "live", "video_id": "vvv", "channel_key": "arale"}
        r_video = _activate_state_edit(g2, item_b, NW)
        assert "다음 정기 tick" in r_video, r_video
        print("[OK] _activate_state_edit: video_id 있음 + 메인서비스 미설정 → 경고만(안 죽음)")

        # (c) video_id 없는 announced, 아직 30분 안 지난 상태로 state="end" 강제 지정
        #     → FSM 재판정 결과 그대로(end 창 유지, none 으로 안 건너뜀).
        g3 = _GH()
        g3.store[_PREVIEW_PATH] = {"items": [
            {"id": "pv_end1", "channel_key": "arale", "state": "end", "state_since": NW,
             "scheduled_start": "2026-09-09T11:00:00Z", "video_id": None},
        ]}
        item_c = {"id": "pv_end1", "channel_key": "arale", "state": "end", "state_since": NW,
                  "scheduled_start": "2026-09-09T11:00:00Z", "video_id": None}
        r_end = _activate_state_edit(g3, item_c, NW)
        assert "변화 없음" in r_end, r_end
        assert g3.store[_PREVIEW_PATH]["items"][0]["state"] == "end", g3.store[_PREVIEW_PATH]
        print("[OK] _activate_state_edit: video_id 없음 → FSM 1회 파생(state_since 리셋 기준)")

    # ── (v3.6) 웹훅 DM 미발송 안전망 — 버그리포트 20260916 #4 ────────────
    if _FLASK_AVAILABLE:
        class _FakeGHStore:
            _store: dict = {}
            def __init__(self, *a, **kw):
                pass
            def read_json(self, path):
                return (self._store.get(path), "sha0" if path in self._store else None)
            def write_json(self, path, data, *, prev_sha=None, message=""):
                before = self._store.get(path)
                self._store[path] = data
                return (before != data, "sha1")

        _sent_msgs: list = []
        def _fake_send_telegram(text, silent=False):
            _dm_sent_ctx.set(True)
            _sent_msgs.append(text)
            return True

        _orig_send_tg = globals()["_send_telegram"]
        _orig_gh_store = globals()["GitHubStore"]
        _orig_del_req = globals()["_handle_del_request"]
        _orig_env4 = dict(os.environ)
        try:
            os.environ["GITHUB_TOKEN"] = "test-token"
            os.environ["GITHUB_REPO"] = "test/repo"
            globals()["_send_telegram"] = _fake_send_telegram
            globals()["GitHubStore"] = _FakeGHStore
            _FakeGHStore._store = {}
            client = app.test_client()

            # 실사례 재현: /del preview (유닛/번호 누락) — 현재 코드는 이미 사용법
            # 안내를 보낸다(버그리포트 당시엔 조용히 끝났다는 보고 — 재현 안 됨은
            # 배포 지연/환경차 가능성. 그래도 이 경로가 DM 을 보낸다는 걸 고정한다).
            _sent_msgs.clear()
            resp = client.post("/telegram", json={"message": {"chat": {"id": 0}, "text": "/del preview"}})
            assert resp.status_code == 200
            assert len(_sent_msgs) == 1, _sent_msgs
            assert "사용법" in _sent_msgs[0], _sent_msgs
            print("[OK] 안전망: /del preview(유닛·번호 누락) → 사용법 안내 DM 정상 발송")

            # 안전망 자체 검증: 핸들러가 DM 없이 끝나는 상황을 인위로 만들어도
            # _done() 이 대신 알린다.
            _sent_msgs.clear()
            globals()["_handle_del_request"] = lambda *a, **kw: None
            resp2 = client.post("/telegram", json={"message": {"chat": {"id": 0}, "text": "/del arale 1"}})
            assert resp2.status_code == 200
            assert len(_sent_msgs) == 1, _sent_msgs
            assert "결과를 알려드리지 못했습니다" in _sent_msgs[0], _sent_msgs
            print("[OK] 안전망: 핸들러가 DM 없이 끝나는 경로 → _done() 이 대신 안내 DM 발송")
        finally:
            globals()["_send_telegram"] = _orig_send_tg
            globals()["GitHubStore"] = _orig_gh_store
            globals()["_handle_del_request"] = _orig_del_req
            os.environ.clear()
            os.environ.update(_orig_env4)

    # ── WP-1: /ingest 개인 트윗 500 수정 ────────────────────────────
    if _FLASK_AVAILABLE:
        # 공유 저장소 (두 모듈 인스턴스가 같은 dict 참조)
        _shared_store_wp1 = {}

        class _FakeGHWP1:
            def __init__(self, store=None, *a, **kw):
                self.store = store if store is not None else {}
            def read_json(self, path):
                return (self.store.get(path), "sha0" if path in self.store else None)
            def write_json(self, path, data, *, prev_sha=None, message=""):
                before = self.store.get(path)
                self.store[path] = data
                return (before != data, "sha1")
            def read_text(self, path):
                return (self.store.get(path), "sha0" if path in self.store else None)
            def write_text(self, path, text, *, prev_sha=None, message=""):
                before = self.store.get(path)
                self.store[path] = text
                return (before != text, "sha1")

        _orig_make_gh = globals()["_make_gh"]
        _orig_recover_vx = globals()["_recover_raw_via_vxtwitter"]
        _orig_send_tg_wp1 = globals()["_send_telegram"]
        _orig_enrich_media_wp1 = globals().get("_enrich_personal_media")
        _orig_enqueue_wake_now = globals().get("_enqueue_wake_now")
        _orig_env_wp1 = dict(os.environ)

        # 별도 모듈 인스턴스 패치
        import src.backend.telegram_app as _tm
        _tm_orig_make_gh = _tm._make_gh
        _tm_orig_send_tg = _tm._send_telegram
        _tm_orig_recover_vx = _tm._recover_raw_via_vxtwitter
        _tm_orig_enrich_media = _tm._enrich_personal_media if hasattr(_tm, "_enrich_personal_media") else None
        _tm._orig_enqueue_wake_now = _tm._enqueue_wake_now if hasattr(_tm, "_enqueue_wake_now") else None

        try:
            os.environ["INGEST_SECRET"] = "s"
            os.environ["GITHUB_TOKEN"] = "t"
            os.environ["GITHUB_REPO"] = "o/r"
            os.environ.pop("MAIN_SERVICE_URL", None)
            os.environ.pop("GROQ_API_KEY", None)

            # 두 인스턴스 모두 패치 (같은 저장소 공유)
            fake_gh_maker = lambda: _FakeGHWP1(store=_shared_store_wp1)
            globals()["_make_gh"] = fake_gh_maker
            _tm._make_gh = fake_gh_maker

            globals()["_recover_raw_via_vxtwitter"] = lambda raw, tag: (raw, None)
            _tm._recover_raw_via_vxtwitter = lambda raw, tag: (raw, None)

            globals()["_send_telegram"] = lambda *a, **k: True
            _tm._send_telegram = lambda *a, **k: True

            globals()["_enrich_personal_media"] = lambda tag, prefetched=None: ([], None)
            _tm._enrich_personal_media = lambda tag, prefetched=None: ([], None)

            # _enqueue_wake_now 스텁 (Cloud Tasks API 호출 방지)
            _enqueue_wake_now_counts = {"count": 0}
            def _stub_enqueue_wake(*a, **kw):
                _enqueue_wake_now_counts["count"] += 1
            globals()["_enqueue_wake_now"] = _stub_enqueue_wake
            _tm._enqueue_wake_now = _stub_enqueue_wake

            client = app.test_client()

            # 케이스 1: 개인 5인 — title=仲町あられ
            r1 = client.post(
                "/ingest",
                data={"text": "ねむい", "title": "仲町あられ", "tag": ""},
                headers={"X-Ingest-Secret": "s"}
            )
            assert r1.status_code == 200, (r1.status_code, r1.get_json())
            j1 = r1.get_json()
            assert j1.get("personal") == "arale", j1
            assert j1.get("mode") == "added", f"mode 기대 'added', 받음 {j1.get('mode')}"
            assert _TWEETS_PATH in _shared_store_wp1, f"tweets.json 미저장: {_shared_store_wp1.keys()}"
            print("[OK] WP-1: /ingest 개인 5인 (title=仲町あられ) → 200, personal=arale, mode=added, tweets.json 저장")

            # 케이스 2: 테스트 부계정 — title=jehy
            r2 = client.post(
                "/ingest",
                data={"text": "hello", "title": "jehy", "tag": ""},
                headers={"X-Ingest-Secret": "s"}
            )
            assert r2.status_code == 200, (r2.status_code, r2.get_json())
            j2 = r2.get_json()
            assert j2.get("echo") is True, j2
            print("[OK] WP-1: /ingest 테스트 부계정 (title=jehy) → 200, echo=True")

            # 케이스 3: 공식·스케줄 아님 — title="", text=ただの雑談
            r3 = client.post(
                "/ingest",
                data={"text": "ただの雑談", "title": "", "tag": ""},
                headers={"X-Ingest-Secret": "s"}
            )
            assert r3.status_code == 200, (r3.status_code, r3.get_json())
            print("[OK] WP-1: /ingest 공식·스케줄 아님 → 200")

            # 케이스 4: 빈 text → 400 (title="" 로 personal 라우팅 회피)
            r4 = client.post(
                "/ingest",
                data={"text": "", "title": "", "tag": ""},
                headers={"X-Ingest-Secret": "s"}
            )
            assert r4.status_code == 400, (r4.status_code, r4.get_json())
            print("[OK] WP-1: /ingest 빈 text → 400")

            # 케이스 5: 시크릿 틀림 → 403
            r5 = client.post(
                "/ingest",
                data={"text": "テキスト", "title": "仲町あられ", "tag": ""},
                headers={"X-Ingest-Secret": "wrong"}
            )
            assert r5.status_code == 403, (r5.status_code, r5.get_json())
            print("[OK] WP-1: /ingest 시크릿 틀림 → 403")

            # ── WP-3b (e): _url_confirmed_commit _enqueue_wake_now 검증 ────────────────────
            # (스텁 활성 상태에서, WP-1 블록 안이므로 _enqueue_wake_now 스텁 적용됨)
            _enqueue_wake_now_counts["count"] = 0  # 카운트 리셋
            gh_test_url = _FakeGHWP1()  # WP-1 블록 내 클래스 사용
            new_item = {"state": "upcoming", "scheduled_start": "2026-09-20T12:00:00Z", "url": "https://youtube.com/watch?v=test"}
            res_url = _url_confirmed_commit(gh_test_url, "test_video_id", new_item,
                                            "2026-09-20T11:45:00Z", "arale", "2026-09-17T16:00:00Z", via="ingest")
            assert res_url.get("changed") is True, f"changed=True 기대, 받음 {res_url.get('changed')}"
            assert res_url.get("error") is False, f"error=False 기대, 받음 {res_url.get('error')}"
            assert _PREVIEW_PATH in gh_test_url.store, "preview.json 저장 안 됨"
            assert _enqueue_wake_now_counts["count"] == 1, f"_enqueue_wake_now 호출 1회 기대, 받음 {_enqueue_wake_now_counts['count']}"
            print("[OK] WP-3b: _url_confirmed_commit (next_check_at 있음) → _enqueue_wake_now 1회, preview.json 저장, changed=True")

            # ── v3.7.3: 유튜브 앱 회원 전용 라이브 알림 (source=yt) ─────────────────────
            # 실측 폼(Cloud Run 로그 2026-09-18 12:12Z) 그대로. yt-dlp 는 스텁(네트워크 없음).
            _MT = "【🟡メン限】今の鼻事情いつもの気ままあーんど作業？？【 仲町あられ / 夢限大みゅーたいぷ 】"
            _yt_form = {
                "source": "yt", "video_id": "default",
                "title": f"仲町あられ -Nakamachi Arale- / 夢限大みゅーたいぷ 실시간 스트리밍 시작: {_MT}",
                "kind": "a:NOTIFICATION_TYPE_SPONSORSHIPS_LIVESTREAM_START:946ff57868de0000",
                "tag": "default::514a3c5a-fa4e-42f4-8b2b-d61ecc567b66",
            }
            _yt_hdr = {"X-Ingest-Secret": "s"}
            _probe_calls = []
            _orig_find = ytdlp_probe.find_member_live

            def _seed_holder():
                holder = preview_mod.make_item(
                    channel_key="arale", state="announced", source="x-relay",
                    now_iso=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    scheduled_start=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                )
                _shared_store_wp1[_PREVIEW_PATH] = {"items": [holder]}
                return holder

            try:
                ytdlp_probe.find_member_live = lambda cid, title, **kw: (
                    _probe_calls.append((cid, title)) or
                    {"video_id": "HN2xeIVMqWI", "url": "https://www.youtube.com/watch?v=HN2xeIVMqWI",
                     "title": title, "live_status": "is_live", "via_cookie": False})

                holder = _seed_holder()
                ry1 = client.post("/ingest", data=_yt_form, headers=_yt_hdr)
                jy1 = ry1.get_json()
                assert ry1.status_code == 200 and jy1["ok"] and jy1["mode"] == "upgraded", (ry1.status_code, jy1)
                assert jy1["video_id"] == "HN2xeIVMqWI" and jy1["member_live"] == "arale"
                assert _probe_calls == [("UCWfF0DB6m_t2CE3KcOOOX7g", _MT)], _probe_calls
                it = _shared_store_wp1[_PREVIEW_PATH]["items"]
                assert len(it) == 1 and it[0]["id"] == holder["id"] and it[0]["state"] == "live"
                assert it[0]["membership"] is True and it[0]["url"].endswith("v=HN2xeIVMqWI")
                print("[OK] v3.7.3: /ingest source=yt 회원 전용 시작 → yt-dlp 조회 → 자리표시 live 승격 (200)")

                ry2 = client.post("/ingest", data=_yt_form, headers=_yt_hdr)
                assert ry2.status_code == 200 and ry2.get_json()["mode"] == "noop", ry2.get_json()
                assert len(_shared_store_wp1[_PREVIEW_PATH]["items"]) == 1
                print("[OK] v3.7.3: 같은 알림 재도착 → noop (중복 항목 없음)")

                before = json.dumps(_shared_store_wp1[_PREVIEW_PATH], sort_keys=True)
                for bad in (
                    # (v3.8.4) TUNEIN 은 더 이상 여기 안 걸림 — 실물 video_id 면 wake 대상이라
                    # 아래 별도 블록에서 검증. 여기는 알려진 LIVESTREAM 종류가 아예 아닌 kind.
                    dict(_yt_form, kind="a:NOTIFICATION_TYPE_UPLOADED:abc", video_id="bgzve7Y7S50"),
                    dict(_yt_form, title="조코딩 JoCoding 실시간 스트리밍 시작: 무관"),
                    {"source": "yt", "video_id": "x", "title": "", "kind": "", "tag": ""},
                ):
                    rb = client.post("/ingest", data=bad, headers=_yt_hdr)
                    assert rb.status_code == 200 and rb.get_json().get("ignored"), (rb.status_code, rb.get_json())
                assert json.dumps(_shared_store_wp1[_PREVIEW_PATH], sort_keys=True) == before
                print("[OK] v3.7.3: 회원 전용 아님/5인 아님/미지 kind/빈 알림 → 200 무시 (400 아님, 상태 불변)")

                # 조회 실패 폴백: video_id 없이 채널 링크로 live
                ytdlp_probe.find_member_live = lambda cid, title, **kw: None
                holder = _seed_holder()
                ry3 = client.post("/ingest", data=_yt_form, headers=_yt_hdr)
                jy3 = ry3.get_json()
                assert ry3.status_code == 200 and jy3["mode"] == "upgraded" and jy3["video_id"] is None, jy3
                it = _shared_store_wp1[_PREVIEW_PATH]["items"][0]
                assert it["state"] == "live" and it["video_id"] is None and "/channel/UCWfF0DB6m" in it["url"]
                print("[OK] v3.7.3: yt-dlp 조회 실패 → 채널 링크로 live 처리 (폴백)")

                # 조회 예외도 삼키고 200
                def _boom(*a, **k): raise RuntimeError("yt-dlp down")
                ytdlp_probe.find_member_live = _boom
                _seed_holder()
                ry4 = client.post("/ingest", data=_yt_form, headers=_yt_hdr)
                assert ry4.status_code == 200 and ry4.get_json()["mode"] == "upgraded", ry4.get_json()
                print("[OK] v3.7.3: yt-dlp 예외 → 200 유지, 폴백 live")

                ry5 = client.post("/ingest", data=_yt_form, headers={"X-Ingest-Secret": "wrong"})
                assert ry5.status_code == 403
                print("[OK] v3.7.3: source=yt 도 시크릿 검증 통과해야 처리 (틀리면 403)")

                # ── (v3.8.4) TUNEIN/REMINDER/SUBSCRIPTION_LIVESTREAM_START 일반 중계 ──────
                # 09-22 09:33 千石ユノ TUNEIN 실측 재현 — video_id 실물 확보 → 즉시 wake.
                _enqueue_wake_now_counts["count"] = 0
                _woken_ids: list[str] = []

                def _stub_enqueue_wake2(video_id, *a, **kw):
                    _enqueue_wake_now_counts["count"] += 1
                    _woken_ids.append(video_id)

                globals()["_enqueue_wake_now"] = _stub_enqueue_wake2
                _tm._enqueue_wake_now = _stub_enqueue_wake2

                _tunein_form = {
                    "source": "yt", "video_id": "mn4Jjd7KdXY",
                    "title": "【 #アワーノーツ 】バンドリ！新作リズムゲームを先行プレイ！【 #千石ユノ / #バンドリ 】",
                    "kind": "a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:fa7ca7b21bde0000",
                    "tag": "mn4Jjd7KdXY::199826f2-810d-4770-a851-c23591a45b10",
                }
                rt1 = client.post("/ingest", data=_tunein_form, headers=_yt_hdr)
                jt1 = rt1.get_json()
                assert rt1.status_code == 200 and jt1.get("woken") is True, (rt1.status_code, jt1)
                assert jt1["public_relay"] == "tunein" and jt1["video_id"] == "mn4Jjd7KdXY", jt1
                assert _enqueue_wake_now_counts["count"] == 1 and _woken_ids == ["mn4Jjd7KdXY"]
                print("[OK] v3.8.4: /ingest source=yt TUNEIN(실물 video_id) → 즉시 _enqueue_wake_now 1회"
                      " (09-22 09:33 千石ユノ 실측 회귀 테스트 — 예전엔 조용히 ignored 였음)")

                # REMINDER(일반 채널 라이브 시작)도 동일 — video_id 실물 확보 케이스.
                _enqueue_wake_now_counts["count"] = 0
                _woken_ids.clear()
                _reminder_form = {
                    "source": "yt", "video_id": "bgzve7Y7S50",
                    "title": "峰月律-Minetsuki Ritsu- / 夢限大みゅーたいぷ 실시간 스트리밍 시작",
                    "kind": "a:NOTIFICATION_TYPE_LIVESTREAM_REMINDER:14e3012e805e0000",
                    "tag": "bgzve7Y7S50::12f0bd2b-1837-4b1f-9e79-6a4b50244186",
                }
                rt2 = client.post("/ingest", data=_reminder_form, headers=_yt_hdr)
                jt2 = rt2.get_json()
                assert rt2.status_code == 200 and jt2.get("woken") is True and jt2["public_relay"] == "reminder", jt2
                assert _enqueue_wake_now_counts["count"] == 1 and _woken_ids == ["bgzve7Y7S50"]
                print("[OK] v3.8.4: /ingest source=yt REMINDER(실물 video_id) → 즉시 _enqueue_wake_now 1회")

                # 회원전용 추정 TUNEIN(video_id=default) — 실측 미확인 포맷이라 승격 스킵(무시 유지).
                _enqueue_wake_now_counts["count"] = 0
                _member_tunein = dict(
                    _tunein_form, video_id="default",
                    kind="a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:xxx",
                    title=f"仲町あられ -Nakamachi Arale- / 夢限大みゅーたいぷ 30분 후에 실시간 스트림 시청하기: {_MT}",
                )
                rt3 = client.post("/ingest", data=_member_tunein, headers=_yt_hdr)
                jt3 = rt3.get_json()
                assert rt3.status_code == 200 and jt3.get("ignored") == "member-tunein-unresolved", jt3
                assert _enqueue_wake_now_counts["count"] == 0, "미확인 포맷은 wake 도 승격도 안 해야 함"
                print("[OK] v3.8.4: 회원전용 추정 TUNEIN(video_id=default, 미확인 포맷) → 승격 스킵, 무시 유지")

                # 회원전용 추정 REMINDER(video_id=default) → 기존 검증된 회원-라이브 경로로 위임돼야
                # 함 + item 7 핫픽스: 이번엔 flow="preview" 모니터 로그도 같이 남아야 한다.
                holder2 = _seed_holder()
                _member_reminder = {
                    "source": "yt", "video_id": "default",
                    "title": f"仲町あられ -Nakamachi Arale- / 夢限大みゅーたいぷ 실시간 스트리밍 시작: {_MT}",
                    "kind": "a:NOTIFICATION_TYPE_LIVESTREAM_REMINDER:zzzz0000",
                    "tag": "default::synthetic-reminder",
                }
                ytdlp_probe.find_member_live = lambda cid, title, **kw: (
                    {"video_id": "REMINDERvid", "url": "https://www.youtube.com/watch?v=REMINDERvid",
                     "title": title, "live_status": "is_live", "via_cookie": False})
                _now_iso_test = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                rt4 = client.post("/ingest", data=_member_reminder, headers=_yt_hdr)
                jt4 = rt4.get_json()
                assert rt4.status_code == 200 and jt4.get("member_live") == "arale" and jt4["mode"] == "upgraded", jt4
                it4 = _shared_store_wp1[_PREVIEW_PATH]["items"]
                assert len(it4) == 1 and it4[0]["id"] == holder2["id"] and it4[0]["state"] == "live", it4
                print("[OK] v3.8.4: 회원전용 추정 REMINDER(video_id=default) → 기존 회원-라이브 경로로 위임(live 승격)")

                from src.backend import monitor_log as _monlog
                _ev_path = _monlog.event_path(_now_iso_test)
                _ev_text = _shared_store_wp1.get(_ev_path, "")
                _ev_lines = [json.loads(l) for l in _ev_text.strip().split("\n") if l.strip()]
                _preview_lines = [l for l in _ev_lines if l.get("flow") == "preview"]
                assert any(l.get("to_state") == "live" and l.get("video_id") == "REMINDERvid"
                           for l in _preview_lines), (
                    f"item 7 핫픽스: 회원전용 live 전이의 flow=preview 모니터로그가 안 남음: {_preview_lines}")
                print("[OK] v3.8.4 (item 7): 회원전용 live 커밋이 flow=preview 모니터 로그도 같이 남김"
                      " — 이전엔 /monitor 간트에서 이 전이가 안 보였음(announced/upcoming/end 만 보이던 버그)")
            finally:
                ytdlp_probe.find_member_live = _orig_find
        finally:
            # __main__ 인스턴스 원복
            globals()["_make_gh"] = _orig_make_gh
            globals()["_recover_raw_via_vxtwitter"] = _orig_recover_vx
            globals()["_send_telegram"] = _orig_send_tg_wp1
            if _orig_enrich_media_wp1:
                globals()["_enrich_personal_media"] = _orig_enrich_media_wp1

            # 별도 모듈 인스턴스 원복
            _tm._make_gh = _tm_orig_make_gh
            _tm._send_telegram = _tm_orig_send_tg
            _tm._recover_raw_via_vxtwitter = _tm_orig_recover_vx
            if _tm_orig_enrich_media:
                _tm._enrich_personal_media = _tm_orig_enrich_media

            # _enqueue_wake_now 원복
            if "_orig_enqueue_wake_now" in locals():
                globals()["_enqueue_wake_now"] = _orig_enqueue_wake_now
                _tm._enqueue_wake_now = _tm._orig_enqueue_wake_now

            os.environ.clear()
            os.environ.update(_orig_env_wp1)

    # ── WP-2: 외부 LLM 폴백 기본값 통일 ────────────────────────────
    _orig_env_wp2 = dict(os.environ)
    try:
        os.environ.pop("GROQ_API_KEY", None)
        os.environ.pop("GROQ_MODEL", None)
        os.environ.pop("GROQ_MODEL_FALLBACK", None)
        client = _make_llm_client()
        assert client is None, "GROQ_API_KEY 없으면 None"

        os.environ["GROQ_API_KEY"] = "dummy"
        client = _make_llm_client()
        assert client is not None, "GROQ_API_KEY 있으면 객체 생성"
        assert client.model == llm.DEFAULT_MODEL, f"model={client.model}, expected={llm.DEFAULT_MODEL}"
        assert client.fallback == llm.FALLBACK_MODEL, f"fallback={client.fallback}, expected={llm.FALLBACK_MODEL}"
        print("[OK] WP-2: _make_llm_client(GROQ_API_KEY=dummy) → model/fallback이 llm 상수 값")
    finally:
        os.environ.clear()
        os.environ.update(_orig_env_wp2)

    # ── WP-3a: 소식 경로 분리 — 준비(LLM) + 커밋(쓰기) ────────────────
    _sample_notice_raw = "【速報】7月28日(火)にみゅーたいぷが新曲MVをTwitterで初公開！"
    _memo_gh_wp3a = {}

    # (1) _prepare_notice 결과가 json.dumps 가능
    prep = _prepare_notice(_sample_notice_raw, "2026-09-17T12:00:00Z", tag=None, title=None, gh=None)
    assert prep is not None, "_prepare_notice: 표본 원문 파싱 실패"
    json.dumps(prep)  # json 직렬화 가능해야 함
    print("[OK] WP-3a: _prepare_notice 결과가 json.dumps 가능")

    # (2) _commit_notice 는 외부 호출을 하지 않음 (메모리 GH로 테스트)
    class _GHMemory:
        def __init__(self):
            self.store = {}
        def read_json(self, path):
            return (self.store.get(path), "sha0" if path in self.store else None)
        def write_json(self, path, data, *, prev_sha=None, message=""):
            before = self.store.get(path)
            self.store[path] = data
            return (before != data, f"sha_{path}_{len(self.store)}")

    # LLM/vision/vxtwitter 호출 시도 시 AssertionError 발생하도록 스텁
    _orig_make_llm = globals().get("_make_llm_client")
    _orig_make_vision = globals().get("_make_vision_client")
    _orig_vxtwitter_fetch = vxtwitter.fetch_tweet if vxtwitter else None

    def _fail_llm(*a, **kw):
        raise AssertionError("_commit_notice 가 외부 LLM 호출해서는 안 됨")
    def _fail_vision(*a, **kw):
        raise AssertionError("_commit_notice 가 비전 OCR 호출해서는 안 됨")
    def _fail_vxtwitter(*a, **kw):
        raise AssertionError("_commit_notice 가 vxtwitter 호출해서는 안 됨")

    try:
        # 준비: LLM 활성 상태에서 prepared 구하기
        raw = "新曲PV公開〜 9月20日(土)18時生配信にて🎵"
        prep_test = _prepare_notice(raw, "2026-09-17T13:00:00Z", tag=None, title=None, gh=None)
        assert prep_test is not None, "_prepare_notice: 테스트 원문 파싱 실패"

        # 커밋 단계에서는 LLM을 비활성화 (외부 호출이 발생하면 실패)
        globals()["_make_llm_client"] = _fail_llm
        globals()["_make_vision_client"] = _fail_vision
        if vxtwitter:
            vxtwitter.fetch_tweet = _fail_vxtwitter

        # (c) dup_id 없으면 added, 있으면 updated
        gh_test = _GHMemory()

        # (c-i) dup_id=None → added
        mode1, parsed1 = _commit_notice(gh_test, prep_test, "2026-09-17T13:00:00Z")
        assert mode1 == "added", f"dup_id=None: added 기대, 받음 {mode1}"
        assert _NOTICES_PATH in gh_test.store, "notices.json 커밋되지 않음"
        n1 = gh_test.store[_NOTICES_PATH]
        assert n1.get("notices") and len(n1["notices"]) == 1, "첫 소식 등록 실패"
        added_id = n1["notices"][0]["id"]
        print("[OK] WP-3a: _commit_notice(dup_id=None) → added")

        # (c-ii) dup_id 있음 → updated (다른 원문으로 새 prep, 준비시 LLM 활성화)
        # LLM 임시 복구 (prep_test2 생성에 필요)
        globals()["_make_llm_client"] = _orig_make_llm
        _tm._make_llm_client = _tm_orig_make_gh  # 별도 인스턴스도 복구

        raw2 = "トークイベント — 9月25日(木)渋谷"
        prep_test2 = _prepare_notice(raw2, "2026-09-17T13:30:00Z", tag=None, title=None, gh=None)
        assert prep_test2 is not None, "updated 테스트용 원문 파싱 실패"

        # 다시 LLM 비활성화 (커밋 테스트)
        globals()["_make_llm_client"] = _fail_llm
        _tm._make_llm_client = _fail_llm

        prep_test2["dup_id"] = added_id
        mode2, parsed2 = _commit_notice(gh_test, prep_test2, "2026-09-17T13:30:00Z")
        assert mode2 == "updated", f"dup_id={added_id}: updated 기대, 받음 {mode2}"
        n2 = gh_test.store[_NOTICES_PATH]
        assert n2.get("notices") and len(n2["notices"]) == 1, "중복 병합 후에도 1건만"
        print("[OK] WP-3a: _commit_notice(dup_id=존재하는_id) → updated")

        # (c-iii) dup_id 없는 id → added (세 번째 원문)
        # LLM 임시 복구 (prep_test3 생성)
        globals()["_make_llm_client"] = _orig_make_llm
        _tm._make_llm_client = _tm_orig_make_gh

        raw3 = "【イベント開催】10月20日(日) 有料トークショー"
        prep_test3 = _prepare_notice(raw3, "2026-09-17T14:00:00Z", tag=None, title=None, gh=None)
        assert prep_test3 is not None, "added 테스트용 원문 파싱 실패"

        # 다시 LLM 비활성화 (커밋 테스트)
        globals()["_make_llm_client"] = _fail_llm
        _tm._make_llm_client = _fail_llm

        prep_test3["dup_id"] = "nonexistent_id"
        mode3, parsed3 = _commit_notice(gh_test, prep_test3, "2026-09-17T14:00:00Z")
        assert mode3 == "added", f"dup_id=없는_id: added 기대, 받음 {mode3}"
        n3 = gh_test.store[_NOTICES_PATH]
        assert n3.get("notices") and len(n3["notices"]) == 2, "새 소식 추가 실패"
        print("[OK] WP-3a: _commit_notice(dup_id=없는_id) → added (안전한 기본값)")

        print("[OK] WP-3a: _commit_notice 외부호출 0회")
    finally:
        if _orig_make_llm:
            globals()["_make_llm_client"] = _orig_make_llm
        if _orig_make_vision:
            globals()["_make_vision_client"] = _orig_make_vision
        if vxtwitter and _orig_vxtwitter_fetch:
            vxtwitter.fetch_tweet = _orig_vxtwitter_fetch

    # ── WP-3b: 개인 트윗 경로 분리 — 준비(vxtwitter·LLM) + 커밋(쓰기) ────────────────
    # (1) _prepare_personal_tweet 결과가 json.dumps 가능
    _sample_tweet_raw = "ねむい… 明日も頑張ろう"
    prep_tweet = _prepare_personal_tweet(
        _sample_tweet_raw, title="仲町あられ", tag="p#xxx", channel_key="arale",
        now_iso="2026-09-17T15:00:00Z", gh=None,
    )
    if prep_tweet is not None:
        json.dumps(prep_tweet)  # json 직렬화 가능해야 함
    print("[OK] WP-3b: _prepare_personal_tweet 결과가 json.dumps 가능")

    # (2) _commit_personal_tweet 는 외부 호출을 하지 않음
    _orig_make_llm = globals().get("_make_llm_client")
    _orig_inline_translate = globals().get("_inline_translate")

    def _fail_inline_translate(*a, **kw):
        raise AssertionError("_commit_personal_tweet 가 _inline_translate 호출해서는 안 됨 (prepared 에서 번역 완료)")

    try:
        # 메모리 GH 에서 테스트
        gh_test_tweet = _GHMemory()

        # 테스트용 prepared 데이터 (번역 완료)
        test_parsed = {"id": "123", "text": "Hello", "channel_key": "arale"}
        prepared_with_ko = {
            "parsed": test_parsed,
            "text_src": "Hello",
            "text_ko": "안녕하세요",
            "quote_src": None,
            "quote_ko": None,
        }

        # 커밋: 번역을 건너뛰어야 하므로 LLM 비활성화
        globals()["_make_llm_client"] = lambda: None  # LLM 비활성
        globals()["_inline_translate"] = _fail_inline_translate

        res = _commit_personal_tweet(gh_test_tweet, prepared_with_ko, channel_key="arale",
                                     now_iso="2026-09-17T15:30:00Z", via="ingest")
        assert res.get("mode") in ("added", "none"), f"mode 기대값과 다름: {res.get('mode')}"
        assert res.get("n_thread", 0) >= 0, "n_thread 음수?"
        assert isinstance(res.get("needs_tl", False), bool), "needs_tl 타입?"
        print("[OK] WP-3b: _commit_personal_tweet 외부호출 0회")

        # (d) text_ko 있으면 저장, None 이면 needs_tl
        assert _TWEETS_PATH in gh_test_tweet.store, "tweets.json 커밋 안 됨"
        t_data = gh_test_tweet.store[_TWEETS_PATH]
        if t_data.get("tweets", {}).get("arale"):
            row = t_data["tweets"]["arale"][0] if isinstance(t_data["tweets"]["arale"], list) else \
                  list(t_data["tweets"]["arale"].values())[0] if isinstance(t_data["tweets"]["arale"], dict) else None
            if row:
                assert row.get("text_ko") == "안녕하세요", f"text_ko 미반영: {row}"
                assert "needs_tl" not in row or not row["needs_tl"], f"needs_tl 제거 안 됨: {row}"
        print("[OK] WP-3b: _commit_personal_tweet text_ko 처리")

    finally:
        if _orig_make_llm:
            globals()["_make_llm_client"] = _orig_make_llm
        if _orig_inline_translate:
            globals()["_inline_translate"] = _orig_inline_translate
        # 전역 _enqueue_wake_now 원복
        if _orig_enqueue_wake_now_global:
            globals()["_enqueue_wake_now"] = _orig_enqueue_wake_now_global

    print(chr(10) + "=" * 60)
    print("SUCCESS: telegram_app v3 smoke test 통과")
    print("=" * 60)