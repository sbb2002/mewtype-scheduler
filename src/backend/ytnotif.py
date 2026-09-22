"""유튜브 앱 푸시 알림 파서 (순수 함수).

업스트림 폰 Automate 플로우가 유튜브 앱(`com.google.android.youtube`)
알림을 JSON 으로 변환해 POST /ingest 로 중계. 이 모듈이 JSON 객체를
파싱해 스케줄 candidate 로 변환한다.

payload 명세: v3_backend_surgery.md "결정 (2026-09-08) > 1. 유튜브 앱 알림 중계"
self-test: python -m src.backend.ytnotif
"""

import re
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

# thread_id 접두어 분류 — 제목 필드 결정
_THREAD_KINDS = {
    "NOTIFICATION_TYPE_LIVESTREAM_TUNEIN": ("tunein", "android.text"),
    "NOTIFICATION_TYPE_LIVESTREAM_REMINDER": ("reminder", "android.title"),
    "NOTIFICATION_TYPE_SUBSCRIPTION_LIVESTREAM_START": ("sub_start", "android.text"),
}

# 제목 앞의 🔴 제거. 【…】 는 유튜브 방송 제목의 관용적 접두(게임명·카테고리)라
# 정보이므로 남긴다 — v3 계획 문서의 "【…】 정리" 는 열화가 커서 채택 안 함.
_CLEAN_EMOJI_RE = re.compile(r"^🔴\s*")


def parse_yt_notif(nx: dict, now_iso: str) -> dict | None:
    """
    유튜브 앱 알림 JSON → preview item dict (또는 None).

    입력:
      nx: notification payload dict (chime.*, android.*, pde_* 키 포함)
      now_iso: 현재 시각 ISO string (e.g., "2026-09-09T12:34:56Z")

    반환:
      {
        video_id: str,
        url: str,
        thumbnail: str,
        title: str,
        kind: "tunein" | "reminder" | "sub_start",
        scheduled_start: str (ISO),
        time_approx: bool,
        source: "yt-notif"
      }
      또는 필터 조건 위반 시 None.
    """
    # 1. 패키지 필터 (YouTube 앱만)
    if nx.get("pde_noti_pkg") != "com.google.android.youtube":
        return None

    # 2. SUMMARY 태그 필터 (노이즈)
    tag = nx.get("pde_noti_tag", "")
    if "::SUMMARY::" in tag:
        return None

    # 3. thread_id 접두어로 종류 분기
    thread_id = nx.get("chime.thread_id", "")
    kind = None
    title_field = None
    for prefix, (k, tf) in _THREAD_KINDS.items():
        if prefix in thread_id:
            kind = k
            title_field = tf
            break

    if not kind:
        return None  # 알려진 종류 아님

    # 4. video_id 검증 (chime.slot_key, 정확히 11자)
    video_id = nx.get("chime.slot_key", "")
    if not video_id or len(video_id) != 11:
        return None

    # 5. 제목 필드 선택 및 정리
    title = nx.get(title_field, "") or ""
    title = _CLEAN_EMOJI_RE.sub("", title.strip()).strip()

    if not title:
        return None  # 빈 제목

    # 6. URL / thumbnail
    url = f"https://www.youtube.com/watch?v={video_id}"
    thumbnail = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"

    # 7. scheduled_start 계산
    # TUNEIN: now + 30분, time_approx=True
    # REMINDER/SUB_START: now, time_approx=False
    try:
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None  # 시간 파싱 실패

    if kind == "tunein":
        scheduled_dt = now_dt + timedelta(minutes=30)
        time_approx = True
    else:  # reminder, sub_start
        scheduled_dt = now_dt
        time_approx = False

    scheduled_start = scheduled_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "video_id": video_id,
        "url": url,
        "thumbnail": thumbnail,
        "title": title,
        "kind": kind,
        "scheduled_start": scheduled_start,
        "time_approx": time_approx,
        "source": "yt-notif",
    }


_MEMBER_START = "NOTIFICATION_TYPE_SPONSORSHIPS_LIVESTREAM_START"

# 실제 유튜브 video_id 형태(11자, URL-safe base64 문자셋). 회원전용 알림처럼 실물 ID 대신
# "default" 같은 placeholder 가 오는 경우와 구분하는 데 쓴다.
_REAL_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _nfkc(s: str | None) -> str:
    import unicodedata
    return " ".join(unicodedata.normalize("NFKC", s or "").split())


def _match_channel_key(raw_text: str, channels_cfg: dict) -> tuple[str | None, str | None]:
    """제목 표시명으로 5인 채널 판별 + 콜론 뒤 영상 제목 분리.

    `parse_member_live_relay`/`parse_public_live_relay`(video_id 미상 분기)가 공유.
    반환: (channel_key|None, video_title|None)
    """
    text = _nfkc(raw_text)
    if not text:
        return None, None
    channel_key = None
    for ck, ch in ((channels_cfg or {}).get("channels") or {}).items():
        name = _nfkc(ch.get("name"))
        if ck != "group" and name and text.startswith(name):
            channel_key = ck
            break
    if channel_key is None:
        return None, None
    _head, sep, video_title = raw_text.partition(": ")
    title = video_title.strip() if sep and video_title.strip() else None
    return channel_key, title


def parse_member_live_relay(form, channels_cfg: dict) -> dict | None:
    """(v3.7.3) 업스트림 중계 폼(`source=yt&video_id&title&kind&tag`) → 회원 전용 라이브 시작 알림.

    실측(2026-09-18, Cloud Run 로그): 회원 전용 시작 알림은 `kind` 가
    `a:NOTIFICATION_TYPE_SPONSORSHIPS_LIVESTREAM_START:…`, `video_id` 는 영상 ID 가 아니라
    `default`, `title` 은 `"<채널 표시명> / <그룹명> 실시간 스트리밍 시작: <영상 제목>"`.
    5인 채널 표시명(`channels.json` `name`)으로 멤버를 판별한다. 5인이 아니거나 회원 전용
    시작 알림이 아니면 None (호출부가 200 무시).

    반환: {"channel_key", "title"(영상 제목, 없으면 None), "tag"}
    """
    if (form.get("source") or "").strip() != "yt":
        return None
    if _MEMBER_START not in (form.get("kind") or ""):
        return None
    raw_text = (form.get("title") or "").strip()
    if not raw_text:
        return None
    channel_key, title = _match_channel_key(raw_text, channels_cfg)
    if channel_key is None:
        return None
    return {"channel_key": channel_key, "title": title, "tag": (form.get("tag") or "").strip()}


def parse_public_live_relay(form, channels_cfg: dict | None = None) -> dict | None:
    """(v3.8.4) 업스트림 중계 폼 → TUNEIN(30분전)/REMINDER/SUBSCRIPTION_LIVESTREAM_START 알림.

    `parse_member_live_relay` 와 같은 폼(`source=yt&video_id&title&kind&tag`)을 쓰지만 회원전용
    시작(`SPONSORSHIPS_LIVESTREAM_START`)이 아닌 나머지 LIVESTREAM 계열을 다룬다.
    `ref/v3_automate_wire.md` 배선상 업스트림은 `chime.thread_id` 에 "LIVESTREAM" 이 있으면 전부
    이 폼으로 중계하므로(실측 2026-09-22 09:33 千石ユノ TUNEIN), 폰 쪽 변경 없이 바로 들어온다.

    `video_id` 는 보통 `chime.slot_key` 그대로(실제 11자 ID)지만, 회원전용 알림에서 관측된 것처럼
    `"default"` 같은 placeholder 일 수도 있어 `resolved=False` 로 표시한다(회원전용 TUNEIN 이 실제로
    이 포맷으로 오는지는 미확인 — 확인 전까지는 방어적 best-effort). `resolved=False` 이고
    `channels_cfg` 가 주어지면 `title` 표시명으로 채널까지 판별해본다.

    반환: {"relay_kind": "tunein"|"reminder"|"sub_start", "video_id": str, "resolved": bool,
           "channel_key": str|None, "title": str|None, "tag": str} 또는 형식 밖이면 None.
    """
    if (form.get("source") or "").strip() != "yt":
        return None
    kind_raw = form.get("kind") or ""
    if _MEMBER_START in kind_raw:
        return None  # 회원전용 시작은 parse_member_live_relay 전담
    relay_kind = None
    for prefix, (k, _tf) in _THREAD_KINDS.items():
        if prefix in kind_raw:
            relay_kind = k
            break
    if relay_kind is None:
        return None
    video_id = (form.get("video_id") or "").strip()
    if not video_id:
        return None
    resolved = bool(_REAL_VIDEO_ID_RE.match(video_id))
    raw_title = (form.get("title") or "").strip()
    channel_key = None
    title = raw_title or None
    if not resolved and channels_cfg is not None and raw_title:
        channel_key, matched_title = _match_channel_key(raw_title, channels_cfg)
        if matched_title:
            title = matched_title
    return {
        "relay_kind": relay_kind,
        "video_id": video_id,
        "resolved": resolved,
        "channel_key": channel_key,
        "title": title,
        "tag": (form.get("tag") or "").strip(),
    }


if __name__ == "__main__":
    # Self-test: 실측 payload 3건 + 노이즈 필터 3건

    # TUNEIN (ritsu) — line 964 요약
    ritsu_tunein = {
        "pde_noti_pkg": "com.google.android.youtube",
        "chime.slot_key": "bgzve7Y7S50",
        "chime.thread_id": "a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:536ba428805e0000",
        "android.text": "【チラズアート新作「雪葬」＃2】雪かきだけで終わらせない【峰月律/ゆめみた】",
        "android.title": "🔴 30分 후에 峰月律-Minetsuki Ritsu- / 夢限大み... 실시간 스트림 시청하기",
        "pde_noti_tag": "bgzve7Y7S50::12f0bd2b-1837-4b1f-9e79-6a4b50244186",
    }

    # REMINDER (ritsu) — line 970 요약
    ritsu_reminder = {
        "pde_noti_pkg": "com.google.android.youtube",
        "chime.slot_key": "bgzve7Y7S50",
        "chime.thread_id": "a:NOTIFICATION_TYPE_LIVESTREAM_REMINDER:14e3012e805e0000",
        "android.title": "🔴 【チラズアート新作「雪葬」＃2】雪かきだけで終わらせない【峰月律/ゆめみた】",
        "android.text": "峰月律-Minetsuki Ritsu- / 夢限大みゅーたいぷ 실시간 스트리밍 시작",
        "pde_noti_tag": "bgzve7Y7S50::12f0bd2b-1837-4b1f-9e79-6a4b50244186",
    }

    # SUBSCRIPTION_LIVESTREAM_START (yuno) — line 974 요약
    yuno_sub_start = {
        "pde_noti_pkg": "com.google.android.youtube",
        "chime.slot_key": "2eigVMdk3Pg",
        "chime.thread_id": "a:NOTIFICATION_TYPE_SUBSCRIPTION_LIVESTREAM_START:04971ca8205e0000",
        "android.text": "【 #バイオ7 】3回目のバイオ7！怖さマシマシ【 #千石ユノ / #バンドリ 】",
        "android.title": "🔴 千石ユノ -Sengoku Yuno- / 夢限大みゅーたいぷ",
        "pde_noti_tag": "2eigVMdk3Pg::44e5e067-a823-4e7b-a1f6-4e6ecf6b9532",
    }

    # NOISE: SUMMARY 태그
    noise_summary = {
        "pde_noti_pkg": "com.google.android.youtube",
        "pde_noti_tag": "1611430723::SUMMARY::3337484090864764516",
    }

    # NOISE: 잘못된 video_id (10자)
    noise_bad_video_id = {
        "pde_noti_pkg": "com.google.android.youtube",
        "chime.slot_key": "12345678901",  # 11자이지만 이건 테스트 케이스
        "chime.thread_id": "a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:xxx",
        "android.text": "제목",
        "pde_noti_tag": "valid_tag",
    }

    # NOISE: 다운로드 알림 (다른 패키지)
    noise_download = {
        "pde_noti_pkg": "com.sec.android.app.sbrowser",
        "pde_noti_tag": "DownloadNotificationService",
    }

    # NOISE: 빈 제목
    noise_empty_title = {
        "pde_noti_pkg": "com.google.android.youtube",
        "chime.slot_key": "bgzve7Y7S50",
        "chime.thread_id": "a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:xxx",
        "android.text": "",
        "pde_noti_tag": "valid",
    }

    test_now = "2026-09-08T20:30:59Z"

    # TUNEIN 테스트
    result = parse_yt_notif(ritsu_tunein, test_now)
    assert result is not None, "TUNEIN parse failed"
    assert result["video_id"] == "bgzve7Y7S50", f"TUNEIN video_id: {result['video_id']}"
    assert result["kind"] == "tunein", f"TUNEIN kind: {result['kind']}"
    assert result["title"] == "【チラズアート新作「雪葬」＃2】雪かきだけで終わらせない【峰月律/ゆめみた】", f"TUNEIN title: {result['title']}"
    assert result["time_approx"] is True, "TUNEIN time_approx should be True"
    # scheduled_start는 now + 30min
    expected_dt = datetime.fromisoformat(test_now.replace("Z", "+00:00")) + timedelta(minutes=30)
    expected_start = expected_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert result["scheduled_start"] == expected_start, f"TUNEIN scheduled_start: {result['scheduled_start']} vs {expected_start}"
    print("✓ TUNEIN (ritsu, bgzve7Y7S50)")

    # REMINDER 테스트
    result = parse_yt_notif(ritsu_reminder, test_now)
    assert result is not None, "REMINDER parse failed"
    assert result["video_id"] == "bgzve7Y7S50", f"REMINDER video_id: {result['video_id']}"
    assert result["kind"] == "reminder", f"REMINDER kind: {result['kind']}"
    assert result["title"] == "【チラズアート新作「雪葬」＃2】雪かきだけで終わらせない【峰月律/ゆめみた】", f"REMINDER title: {result['title']}"
    assert result["time_approx"] is False, "REMINDER time_approx should be False"
    assert result["scheduled_start"] == test_now, f"REMINDER scheduled_start: {result['scheduled_start']}"
    print("✓ REMINDER (ritsu, bgzve7Y7S50)")

    # SUB_START 테스트
    result = parse_yt_notif(yuno_sub_start, test_now)
    assert result is not None, "SUB_START parse failed"
    assert result["video_id"] == "2eigVMdk3Pg", f"SUB_START video_id: {result['video_id']}"
    assert result["kind"] == "sub_start", f"SUB_START kind: {result['kind']}"
    assert result["title"] == "【 #バイオ7 】3回目のバイオ7！怖さマシマシ【 #千石ユノ / #バンドリ 】", f"SUB_START title: {result['title']}"
    assert result["time_approx"] is False, "SUB_START time_approx should be False"
    print("✓ SUB_START (yuno, 2eigVMdk3Pg)")

    # NOISE: SUMMARY 필터
    result = parse_yt_notif(noise_summary, test_now)
    assert result is None, "SUMMARY should be filtered"
    print("✓ NOISE: SUMMARY filtered")

    # NOISE: 잘못된 패키지
    result = parse_yt_notif(noise_download, test_now)
    assert result is None, "Non-YouTube package should be filtered"
    print("✓ NOISE: Non-YouTube package filtered")

    # NOISE: 빈 제목
    result = parse_yt_notif(noise_empty_title, test_now)
    assert result is None, "Empty title should be filtered"
    print("✓ NOISE: Empty title filtered")

    # ── (v3.7.3) 회원 전용 시작 알림 — 실측 Cloud Run 로그(2026-09-18 12:12Z) 폼 ──
    import json, os
    _cfg = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "config", "channels.json"), encoding="utf-8"))
    member_form = {
        "source": "yt", "video_id": "default",
        "title": "仲町あられ -Nakamachi Arale- / 夢限大みゅーたいぷ 실시간 스트리밍 시작: 【🟡メン限】今の鼻事情いつもの気ままあーんど作業？？【 仲町あられ / 夢限大みゅーたいぷ 】",
        "kind": "a:NOTIFICATION_TYPE_SPONSORSHIPS_LIVESTREAM_START:946ff57868de0000",
        "tag": "default::514a3c5a-fa4e-42f4-8b2b-d61ecc567b66",
    }
    r = parse_member_live_relay(member_form, _cfg)
    assert r and r["channel_key"] == "arale", r
    assert r["title"] == "【🟡メン限】今の鼻事情いつもの気ままあーんど作業？？【 仲町あられ / 夢限大みゅーたいぷ 】", r["title"]
    print("✓ MEMBER_START (arale, video_id=default → 채널·제목 추출)")

    r = parse_member_live_relay(dict(member_form, title="仲町あられ -Nakamachi Arale- / 夢限大みゅーたいぷ 실시간 스트리밍 시작"), _cfg)
    assert r and r["channel_key"] == "arale" and r["title"] is None
    print("✓ MEMBER_START (제목 콜론 없음 → title None)")

    assert parse_member_live_relay(dict(member_form, title="조코딩 JoCoding 실시간 스트리밍 시작: x"), _cfg) is None
    assert parse_member_live_relay(dict(member_form, kind="a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:abc"), _cfg) is None
    assert parse_member_live_relay(dict(member_form, source="x"), _cfg) is None
    assert parse_member_live_relay(dict(member_form, title=""), _cfg) is None
    print("✓ MEMBER_START 필터 (타 채널·타 kind·타 source·빈 제목 → None)")

    for ck, ch in _cfg["channels"].items():
        if ck == "group":
            continue
        rr = parse_member_live_relay(dict(member_form, title=f"{ch['name']} / 夢限大みゅーたいぷ 실시간 스트리밍 시작: t"), _cfg)
        assert rr and rr["channel_key"] == ck, (ck, rr)
    print("✓ MEMBER_START 5인 전원 판별")

    # ── (v3.8.4) parse_public_live_relay — TUNEIN/REMINDER/SUB_START 중계 폼 ──
    # 실측(2026-09-22 09:33:23 KST, ref/flow-11-20260922.log:7731-7735) 千石ユノ TUNEIN.
    yuno_tunein_relay = {
        "source": "yt", "video_id": "mn4Jjd7KdXY",
        "title": "【 #アワーノーツ 】バンドリ！新作リズムゲームを先行プレイ！【 #千石ユノ / #バンドリ 】",
        "kind": "a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:fa7ca7b21bde0000",
        "tag": "mn4Jjd7KdXY::199826f2-810d-4770-a851-c23591a45b10",
    }
    r = parse_public_live_relay(yuno_tunein_relay)
    assert r is not None, "TUNEIN relay parse failed"
    assert r["relay_kind"] == "tunein", r
    assert r["video_id"] == "mn4Jjd7KdXY" and r["resolved"] is True, r
    assert r["channel_key"] is None, "resolved=True 면 채널 판별 안 함(호출부가 videos.list 로 확정)"
    print("✓ PUBLIC_RELAY: TUNEIN (yuno, 09-22 09:33 실측 재현) → resolved video_id")

    reminder_relay = {
        "source": "yt", "video_id": "bgzve7Y7S50",
        "title": "峰月律-Minetsuki Ritsu- / 夢限大みゅーたいぷ 실시간 스트리밍 시작",
        "kind": "a:NOTIFICATION_TYPE_LIVESTREAM_REMINDER:14e3012e805e0000",
        "tag": "bgzve7Y7S50::12f0bd2b-1837-4b1f-9e79-6a4b50244186",
    }
    r = parse_public_live_relay(reminder_relay)
    assert r and r["relay_kind"] == "reminder" and r["resolved"] is True, r
    print("✓ PUBLIC_RELAY: REMINDER (ritsu) → resolved")

    sub_start_relay = {
        "source": "yt", "video_id": "2eigVMdk3Pg",
        "title": "【 #バイオ7 】3回目のバイオ7！怖さマシマシ【 #千石ユノ / #バンドリ 】",
        "kind": "a:NOTIFICATION_TYPE_SUBSCRIPTION_LIVESTREAM_START:04971ca8205e0000",
        "tag": "2eigVMdk3Pg::44e5e067-a823-4e7b-a1f6-4e6ecf6b9532",
    }
    r = parse_public_live_relay(sub_start_relay)
    assert r and r["relay_kind"] == "sub_start" and r["resolved"] is True, r
    print("✓ PUBLIC_RELAY: SUBSCRIPTION_LIVESTREAM_START (yuno) → resolved")

    # 회원전용 TUNEIN(미확인 포맷) — SPONSORSHIPS_LIVESTREAM_START 와 동일하게 video_id="default"
    # 로 온다고 가정한 방어적 케이스. 실측 로그 없음 — 합성 데이터.
    member_tunein_synth = {
        "source": "yt", "video_id": "default",
        "title": "仲町あられ -Nakamachi Arale- / 夢限大みゅーたいぷ 30분 후에 실시간 스트림 시청하기: 제목",
        "kind": "a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:aaaa0000",
        "tag": "default::synthetic",
    }
    r = parse_public_live_relay(member_tunein_synth, _cfg)
    assert r and r["relay_kind"] == "tunein" and r["resolved"] is False, r
    assert r["channel_key"] == "arale", r
    assert r["title"] == "제목", r
    print("✓ PUBLIC_RELAY: 회원전용 TUNEIN(합성, video_id=default) → 미확정 + 채널 판별")

    # channels_cfg 안 주면 채널 판별 스킵(호출부가 원하면 나중에 다시 판별)
    r2 = parse_public_live_relay(member_tunein_synth)  # channels_cfg 생략
    assert r2 and r2["channel_key"] is None, r2
    print("✓ PUBLIC_RELAY: channels_cfg 생략 시 채널 판별 스킵")

    # 노이즈: 회원전용 시작(SPONSORSHIPS_LIVESTREAM_START)은 parse_member_live_relay 전담 → None
    assert parse_public_live_relay(member_form) is None, "회원전용 시작은 public_relay 가 안 먹어야 함"
    # 노이즈: source 틀림 / 알려지지 않은 kind / video_id 없음
    assert parse_public_live_relay(dict(yuno_tunein_relay, source="x")) is None
    assert parse_public_live_relay(dict(yuno_tunein_relay, kind="a:NOTIFICATION_TYPE_UPLOAD:xxx")) is None
    assert parse_public_live_relay(dict(yuno_tunein_relay, video_id="")) is None
    print("✓ PUBLIC_RELAY 필터 (회원전용 시작·source 틀림·미지 kind·video_id 없음 → None)")

    print("\n✅ All assertions passed")
