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
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import unquote_plus

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
    from . import vxtwitter                  # (v3) 트윗 unfurl — 잘린 URL 복원
except ImportError:
    vxtwitter = None

try:
    # (v2.8.1+) 수동 /ingest 개인 예고: 본문 YT URL → 채널 판별 (videos.list 1 quota)
    from ..collector.youtube import YouTubeClient
except Exception:                           # pragma: no cover
    YouTubeClient = None

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
_NOTICES_PATH = "notices.json"                 # (v2.7) 소식 게시판
_NOTICE_ARCHIVE_PATH = "notice_archive.json"
_TWEETS_PATH = "tweets.json"                   # (v2.8) 멤버 개인 트윗
_TWEET_ARCHIVE_PATH = "tweet_archive.json"
_UNIT_KEYS = ("arale", "yuno", "nonoka", "ritsu", "miyako")


def _tw_list(v):
    """tweets[ck] → 메시지 list (계약 I v3.1). v2.8 단건 dict 는 [dict], xtweet 미탑재에도 안전."""
    if isinstance(v, list):
        return [m for m in v if isinstance(m, dict)]
    if isinstance(v, dict):
        return [v]
    return []
_PREVIEW_PATH = "preview.json"                 # (v3) schedule.json 대체
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
        removed = _remove_broadcast(gh, snapshot, now_iso, action)

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
    changed = _merge_rows_into_schedule(
        gh, [row], now_iso,
        message=f"data: telegram /ingest personal {channel_key} {now_iso}",
        action=f"/ingest 개인예고 {name} ({raw[:40].strip()})",
        merge_fn=xtweet.merge_personal_schedule,
    )
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

        drained, drained_rows = _ingest_queue_drain(gh, now_iso)
        rows = xrelay.parse(raw, now_iso)
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

        changed = _merge_rows_into_schedule(
            gh, rows, now_iso,
            message=f"data: telegram /ingest {now_iso}",
            action=f"/ingest {raw[:40].strip()}",
        )
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
_NOTICE_PROMPT = (
    "📝 <b>/notice 대기 중</b> (3분)\n"
    "소식으로 올릴 트윗 원문(또는 /ingest 릴레이 DM)을 붙여넣거나 텍스트 파일을 올려주세요.\n"
    "취소: <code>aNoneTokyo</code>"
)


def _apply_notice(gh, raw: str, now_iso: str, *, tag=None, title=None) -> tuple[str, dict | None]:
    """원문 → xnotice.parse → notices.merge_notice → 커밋.

    반환 (mode, parsed): mode ∈ none | added | updated | recap | dup | skip | error.
    added/updated 면 notices.json 에 대한 /undo 스냅샷도 남긴다.
    """
    if xnotice is None or notices is None:
        return "error", None
    parsed = xnotice.parse(raw, now_iso, tag=tag, title=title)
    if not parsed:
        return "none", None
    # 파싱 직후 1회 LLM 제목추출·번역 (재시도와 무관하게 한 번만). (v3.1.2)
    _tl = None
    if not parsed.get("title_ko"):
        _tl = _inline_notice_title(
            parsed.get("body_for_llm") or parsed.get("body_raw") or parsed.get("title"))
    for _try in (1, 2):
        prev, psha = gh.read_json(_NOTICES_PATH)
        arch, asha = gh.read_json(_NOTICE_ARCHIVE_PATH)
        prev = prev or notices.default_notices()
        arch = arch or notices.default_archive()
        new_n, new_a, changed, mode = notices.merge_notice(prev, parsed, now_iso, archive=arch)
        if not changed:
            return mode, parsed
        # 방금 병합된 소식 행에 번역 반영 (없으면 needs_tl 로 다음 tick sweep 에 넘김).
        row = next((n for n in new_n.get("notices", [])
                    if parsed.get("id") == n.get("id")
                    or parsed.get("id") in (n.get("seen_ids") or [])), None)
        if row and not row.get("title_ko"):
            if _tl and _tl.get("title_ko"):
                row["title"] = _tl.get("title_ja") or row.get("title")
                row["title_ko"] = _tl["title_ko"]
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
    try:
        _notice_sweep(gh, now_iso)
        mode, parsed = _apply_notice(gh, raw, now_iso)
    except Exception as e:
        log.exception("Error handling /notice")
        _send_telegram(f"⚠️ 오류: /notice 처리 실패\n{str(e)[:100]}")
        return True
    _notice_result_dm(mode, parsed, raw)
    return True


def _handle_notice_del(gh, now_iso: str, arg: str) -> None:
    """/notice-del <id | 번호> — 소식 1건 제거 (+ /undo 스냅샷)."""
    if notices is None:
        _send_telegram("⚠️ notices 모듈 없음")
        return
    nid = (arg or "").strip()
    if not nid:
        _send_telegram("사용법: /notice-del &lt;id | 번호&gt;  (/notice-list 로 확인)")
        return
    try:
        prev, psha = gh.read_json(_NOTICES_PATH)
        prev = prev or notices.default_notices()
        lst = prev.get("notices", []) or []
        if nid.isdigit() and 1 <= int(nid) <= len(lst):
            nid = lst[int(nid) - 1].get("id")
        new_n, removed = notices.remove_notice(prev, nid)
        if not removed:
            _send_telegram(f"해당 소식이 없습니다: {html.escape(nid)}")
            return
        _, nsha = gh.write_json(_NOTICES_PATH, new_n, prev_sha=psha,
                                message=f"data: notice del {now_iso}")
        _save_undo(gh, action=f"소식 삭제 ({nid})", prev_content=prev, new_sha=nsha,
                   now_iso=now_iso, path=_NOTICES_PATH)
        _send_telegram(f"🗑 소식 삭제됨 (<code>{html.escape(nid)}</code>). /undo 로 되돌릴 수 있습니다.")
    except Exception as e:
        log.exception("notice-del")
        _send_telegram(f"⚠️ 오류: /notice-del 실패\n{str(e)[:100]}")


def _handle_notice_list(gh, now_iso: str) -> None:
    if notices is None:
        _send_telegram("⚠️ notices 모듈 없음")
        return
    try:
        _notice_sweep(gh, now_iso)
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
        new_n = None
        for _try in (1, 2):
            prevn, psha = gh.read_json(_NOTICES_PATH)
            new_n, changed = notices.edit_notice(
                prevn or notices.default_notices(), nid, patch, now_iso)
            if not changed:
                _send_telegram("변경 사항이 없습니다 — 소식은 그대로입니다.")
                return True
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
            break
        row2 = next((n for n in (new_n or {}).get("notices", []) if n.get("id") == nid), row)
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
    """
    if not raw or xnotice is None or notices is None:
        return "none"
    if xnotice.parse(raw, now_iso, tag=tag, title=title) is None:
        return "none"
    gh = _make_gh()
    if gh is None:
        return "no-gh"
    try:
        _notice_sweep(gh, now_iso)
        mode, parsed = _apply_notice(gh, raw, now_iso, tag=tag, title=title)
    except Exception:
        log.exception("auto notice 실패")
        return "error"
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


# 웹푸시 알림이 긴 URL 을 …/... 로 잘라 보낸 흔적 — 11자 영상 ID 를 못 뽑는 경우.
_TRUNC_YT_RE = re.compile(r"(?:youtube\.com|youtu\.be)/\S*?(?:…|\.\.\.)")

# 폰(Automate) 이 이모지(서로게이트쌍 필요한 U+10000 이상, 🛸📢💪 등)를 다루다 바이트를
# 깨뜨린 흔적 — U+FFFD(치환문자) 또는 짝 없는 서로게이트가 섞여 들어온다(버그리포트 20260913).
# 한 번 이렇게 오면 그 바이트는 복구 불가 — 원문을 다시 구해와야 한다.
_MOJIBAKE_RE = re.compile("[�\ud800-\udfff]")


def _recover_raw_via_vxtwitter(raw: str, tag: str | None) -> str:
    """raw 가 깨졌거나(치환문자/서로게이트) 잘렸으면 tweet id 로 vxtwitter 원문으로 통째 교체.

    폰이 보낸 텍스트에서 발생한 손상은 서버에서 복구 불가(바이트 자체가 유실) — 같은
    트윗을 vxtwitter API 로 다시 조회해 원문을 통째로 갈아끼우는 것만이 유일한 복구 경로.
    tweet id 없음 · vxtwitter 모듈/조회 실패 · 응답에 text 없음 → raw 그대로(무회귀).
    """
    if not raw or vxtwitter is None or xtweet is None:
        return raw
    corrupted = bool(_MOJIBAKE_RE.search(raw))
    truncated = bool(_TRUNC_YT_RE.search(raw))
    if not (corrupted or truncated):
        return raw
    tid = xtweet._tweet_id(tag) if tag else ""
    if not tid or not tid.isdigit():
        return raw
    j = vxtwitter.fetch_tweet(tid)
    text = vxtwitter.extract(j).get("text") if j else None
    if not text:
        log.warning("ingest: raw 손상 복구 실패 (tweet %s, corrupted=%s truncated=%s)",
                    tid, corrupted, truncated)
        return raw
    log.info("ingest: raw 손상 복구(vxtwitter) tweet=%s corrupted=%s truncated=%s",
              tid, corrupted, truncated)
    return text


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


def _maybe_personal_tweet(raw: str, *, title: str, tag: str | None,
                          channel_key: str, now_iso: str) -> str:
    """개인 트윗 인입 — `_ingest` 3.5 라우팅이 개인 5인으로 판정하면 여기로.

    ECHO/DRY-RUN/paused 와 무관하게 실행(이 갈래에 온 시점에서 이미 개인 트윗). 반환: mode(로그용).
    파싱이 트윗이 아니면(본문 없음) GitHub 은 안 건드린다.
    """
    if xtweet is None:
        return "no-xtweet"
    channels_cfg = _load_channels_config()
    handle = channels_cfg.get("channels", {}).get(channel_key, {}).get("handle", "")
    parsed = xtweet.parse(raw, title=title, tag=tag, channel_key=channel_key,
                          now_iso=now_iso, handle=handle)
    if not parsed:
        return "none"
    gh = _make_gh()
    if gh is None:
        return "no-gh"
    mode = "error"
    try:
        for _try in (1, 2):
            prev, psha = gh.read_json(_TWEETS_PATH)
            arch, asha = gh.read_json(_TWEET_ARCHIVE_PATH)
            prev = prev or xtweet.default_tweets()
            arch = arch or xtweet.default_archive()
            new_t, new_a, changed, mode = xtweet.merge_thread(prev, parsed, now_iso, archive=arch)
            if not changed:
                break
            # 방금 들어온 메시지만 인라인 번역 (나머지는 이미 채워져 있음). (계약 I — 스레드)
            row = next((m for m in _tw_list(new_t["tweets"].get(channel_key))
                        if str(m.get("id")) == str(parsed.get("id"))), None)
            if row and not row.get("text_ko"):
                ko = _inline_translate(row.get("text") or "")
                if ko:
                    row["text_ko"] = ko
                    row.pop("needs_tl", None)
                else:
                    row["needs_tl"] = True
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
        _tweet_sweep(gh, now_iso)      # 만료 슬롯 정리 (best-effort)
    except Exception:
        log.exception("personal tweet 반영 실패")
        return "error"

    name = channels_cfg.get("channels", {}).get(channel_key, {}).get("name_ko", channel_key)
    if mode in ("added", "rolled"):
        n_thread = len(_tw_list((new_t or {}).get("tweets", {}).get(channel_key)))
        _auto_dm(gh, "tweet",
                 f"🐦 <b>{html.escape(name)}</b> 새 트윗 (스레드 {n_thread}/{xtweet.MAX_THREAD})\n"
                 f"{html.escape(xtweet.summary_line(parsed))}")
    else:
        log.info("personal tweet: %s (%s)", mode, channel_key)

    # (v2.8.1) 예고글이면 schedule.json 의 scheduled 행으로도 승격
    _maybe_personal_schedule(raw, tag=tag, channel_key=channel_key, name=name,
                             handle=handle, now_iso=now_iso)
    return mode


def _maybe_personal_schedule(raw: str, *, tag: str | None, channel_key: str,
                             name: str, handle: str, now_iso: str) -> None:
    """(v2.8.1) 개인 트윗이 방송 예고면 `xtweet.merge_personal_schedule` 로 scheduled 행 반영.

    `_maybe_personal_tweet` 이 배지 처리 후 호출. 게이트 미통과면 no-op(배지만).
    관측 DM(초반 튜닝용) — precision 안정되면 제거.
    """
    if xtweet is None:
        return
    raw = _expand_truncated_yt(raw, tag)
    try:
        row = xtweet.parse_schedule(raw, channel_key=channel_key, tag=tag,
                                    now_iso=now_iso, handle=handle)
    except Exception:
        log.exception("parse_schedule 실패")
        return
    if not row:
        return
    gh = _make_gh()
    if gh is None:
        return
    try:
        control, _ = gh.read_json("control.json")
        if is_paused(control or default_control()):
            return
        changed = _merge_rows_into_schedule(
            gh, [row], now_iso,
            message=f"data: personal schedule {channel_key} {now_iso}",
            action=f"본인 예고 {name} ({(raw[:40] or '').strip()})",
            merge_fn=xtweet.merge_personal_schedule,
        )
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
        cur, cur_sha = gh.read_json(_path)
        if cur_sha != undo.get("new_sha"):
            state = admin.clear_pending_undo(admin.clear_undo(state))
            gh.write_json(_ADMIN_STATE_PATH, state, prev_sha=sha,
                          message=f"data: undo 슬롯 정리({_path} 갱신) {now_iso}")
            _hint = ("/list 로 현재 상태를 확인한 뒤 /del 로 수동 처리하세요."
                     if _path == _PREVIEW_PATH else "/notice-list 로 확인 후 /notice-del 하세요.")
            _send_telegram(f"↩️ 되돌리기 불가 — 그 사이 {_path} 이 갱신됐습니다.\n{_hint}")
            return

        diff = _undo_diff_text(undo.get("prev_content") or {}, cur or {}, path=_path)
        target = _undo_target_text(undo)
        gh.write_json(
            _path, undo["prev_content"], prev_sha=cur_sha,
            message=f"data: undo({undo.get('action')}) {now_iso}",
        )
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
            model=os.environ.get("GROQ_MODEL", "").strip() or "openai/gpt-oss-120b",
            fallback=os.environ.get("GROQ_MODEL_FALLBACK", "").strip()
            or "llama-3.3-70b-versatile",
        )
    except Exception:
        log.exception("LLMClient 생성 실패")
        return None


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
            total = 0
            n = 0
            pending = 0
            for _k, lst in list(tw.items()):
                norm = _tw_list(lst)
                tw[_k] = norm                       # v2.8 단건 → 배열로 승계
                for row in norm:
                    total += 1
                    if row.get("text_ko"):
                        continue
                    pending += 1
                    ko = llm.translate(row.get("text") or "")
                    if ko:
                        row["text_ko"] = ko
                        row.pop("needs_tl", None)
                        n += 1
                    else:
                        row["needs_tl"] = True
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
        for row in thread:                       # 오래된 → 최신
            body = (row.get("text_ko") or row.get("text") or "").replace("\n", " ")[:80]
            msgs.append(f"· {html.escape(body)}")
        lines.append(head + "\n" + "\n".join(msgs) + f"\n{thread[-1].get('url') or ''}")
    _send_telegram("\n\n".join(lines))


def _handle_tweet_del(gh, channels_cfg: dict, now_iso: str, unit: str) -> None:
    """/del tweet <유닛> — 그 유닛의 트윗 배지 슬롯을 즉시 제거(+undo)."""
    u = (unit or "").strip().lower()
    if u not in _UNIT_KEYS:
        _send_telegram(f"사용법: /del tweet &lt;유닛&gt;  ({', '.join(_UNIT_KEYS)})")
        return
    try:
        prev, sha = gh.read_json(_TWEETS_PATH)
        prev = prev or {}
        tw = dict(prev.get("tweets", {}) or {})
        if u not in tw:
            _send_telegram(f"ℹ️ {u} 트윗이 없습니다.")
            return
        tw.pop(u)
        new = dict(prev)
        new["tweets"] = tw
        new["generated_at"] = now_iso
        _, nsha = gh.write_json(_TWEETS_PATH, new, prev_sha=sha,
                                message=f"data: /del tweet {u} {now_iso}")
        _save_undo(gh, action=f"/del tweet {u}", prev_content=prev, new_sha=nsha,
                   now_iso=now_iso, path=_TWEETS_PATH)
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
        mode = _maybe_personal_tweet(raw, title="", tag=None, channel_key=u, now_iso=now_iso)
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
            _apply_preview_edit(gh, now_iso, ctx)
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
        _merge_rows_into_schedule(gh, rows, now_iso, message=f"data: /edit preview ingest {now_iso}",
                                  action="/edit preview ingest")
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
        msg += "\n⚠️ state 는 FSM 파생값 — 다음 tick 이 덮을 수 있습니다."
    if conflicts:
        msg += "\n\n" + "\n".join(conflicts)
    _send_telegram(msg)


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
                    _pending_undo = admin.get_pending_undo(_admin_state)
                except Exception:
                    log.warning("admin_state.json 조회 실패 — /del·/undo 확인 스킵하고 일반 명령으로 처리")
                    _pending = _pending_undo = None
                _low = text.strip().lower()
                _is_yn = _low in ("y", "yes", "n", "no")
                _is_del_ans = _is_yn or _low == "terminate"
                if _pending and not admin.pending_del_expired(_pending, now_utc) and _is_del_ans:
                    _handle_del_confirm(gh, now_utc, _low)
                    return jsonify({"ok": True}), 200
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
                        return jsonify({"ok": True}), 200

            # v2.5.1: /ingest(무인자) 후 원문/파일 대기 중이면 이 메시지를 그쪽이 소진.
            # (만료·타 명령이면 False → 아래 정상 디스패치로 흘러감)
            if admin is not None and _handle_ingest_followup(
                gh, channels_cfg, now_utc, message, text
            ):
                return jsonify({"ok": True}), 200

            # v2.8.1+: 개인 예고 유닛 되묻기(1~5/이름) 응답 대기 중이면 그쪽이 소진.
            if admin is not None and _handle_member_followup(
                gh, channels_cfg, now_utc, text
            ):
                return jsonify({"ok": True}), 200

            # v2.7: /notice(무인자) 후 원문/파일 대기 중이면 그쪽이 소진.
            if admin is not None and _handle_notice_followup(gh, now_utc, message, text):
                return jsonify({"ok": True}), 200

            # v2.7.x: /notice-edit 마법사(title→date→url) 응답 대기 중이면 그쪽이 소진.
            if admin is not None and _handle_notice_edit_followup(gh, now_utc, text):
                return jsonify({"ok": True}), 200

            # v3: /edit·/ingest tweet 마법사(pending_op) 응답 대기 중이면 그쪽이 소진.
            if admin is not None and _handle_op_followup(gh, channels_cfg, now_utc, message, text):
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
            else:
                # 도움말
                help_text = (
                    "<b>📱 mewtype 텔레그램 봇 (v3)</b>\n\n"
                    "일반: /status /pause /resume /log [detail|normal|simple]\n\n"
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

        # 원본 바디를 form 파싱 전에 먼저 캐시한다. Werkzeug 는 request.form 을 건드리는
        # 순간 입력 스트림을 소비하면서 get_data() 캐시를 안 채우므로, 그 뒤에 부르는
        # request.get_data() 는 form-urlencoded 요청에서 항상 빈 문자열이 된다
        # (그동안 ECHO DM 의 "raw body" 칸이 늘 비어 보이던 원인). cache=True 로 먼저
        # 읽어두면 이후 request.form 은 캐시된 바디를 다시 파싱한다.
        raw_body = request.get_data(cache=True, parse_form_data=False, as_text=True)

        payload = request.form if request.form else (request.get_json(silent=True) or {})
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
        raw = _recover_raw_via_vxtwitter(raw, x_tag)

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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
                mode = _maybe_personal_tweet(
                    raw, title=title, tag=x_tag, channel_key=_route, now_iso=now_iso
                )
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
                _gh = _make_gh()
                if _gh is not None:
                    _ingest_queue_push(_gh, raw, title, now_iso)
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
                _auto_dm(gh, "ingest", "⏸ 일시정지 중 — ingest 무시")
                return jsonify({"ok": True, "paused": True}), 200

            # 실배포 전환 후 첫 호출 — 테스트 기간(ECHO/DRY-RUN)에 쌓인 트윗 먼저 반영.
            drained, drained_rows = _ingest_queue_drain(gh, now_iso)
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
                return jsonify(
                    {"ok": True, "parsed": 0, "failed": len(failed), "drained": drained}
                ), 200

            changed = _merge_rows_into_schedule(
                gh, rows, now_iso, message=f"data: xrelay scheduled {now_iso}",
                action=f"ingest {title or raw[:40]}".strip(),
            )

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
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 60)
    print("telegram_app.py v3 smoke test")
    print("=" * 60)

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

    # ── _recover_raw_via_vxtwitter (버그리포트 20260913) — 조기반환만 (네트워크 미시도) ──
    assert _MOJIBAKE_RE.search("正常な文字列です") is None
    assert _MOJIBAKE_RE.search("�깨짐") is not None          # 치환문자
    assert _MOJIBAKE_RE.search("\udce3짝없는서로게이트") is not None  # 잘못된 서로게이트
    assert _recover_raw_via_vxtwitter("", _TAG) == ""            # 빈 raw
    _clean = "오늘 21시 방송해요"
    assert _recover_raw_via_vxtwitter(_clean, _TAG) == _clean    # 손상·잘림 흔적 없음 → 그대로
    _broken = "配信�開始\udce3"
    assert _recover_raw_via_vxtwitter(_broken, None) == _broken  # 손상됐지만 tweet id 없음 → 무회귀
    print("[OK] _recover_raw_via_vxtwitter (조기반환)")

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

    print(chr(10) + "=" * 60)
    print("SUCCESS: telegram_app v3 smoke test 통과")
    print("=" * 60)