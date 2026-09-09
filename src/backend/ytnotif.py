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

    print("\n✅ All 6 assertions passed")
