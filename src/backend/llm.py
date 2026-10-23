"""외부 LLM(Groq) 클라이언트 — 소식 제목 추출 및 트윗 번역.

명세: docs/plan/v3_impl_spec.md §0.3
"""

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests
import contextvars

# (v4a, 2026-10-02) LLM 판단 반려 → 재판단: 관리 페이지에서 반려된 판단을 다시 돌릴 때 판정 호출 앞에 붙는 힌트.
# 판정 6종(참여 · 예고 최종확인 · 게스트 · 취소/변경 · 소식 중복 · 행사)에만 쓰고 번역 · 제목 추출에는 붙이지 않는다.
REVIEW_HINT: contextvars.ContextVar[str] = contextvars.ContextVar("llm_review_hint", default="")


def _with_hint(prompt: str) -> str:
    h = REVIEW_HINT.get()
    return h + "\n\n" + prompt if h else prompt


logger = logging.getLogger(__name__)

# 호출부가 같은 사건을 자기 기록(monitor 이벤트 등)으로 남기는 경로에서는 번역 최종 실패 줄을 INFO 로 낮춘다 — 한 사건에 한 기록만.
_QUIET: contextvars.ContextVar[bool] = contextvars.ContextVar("llm_quiet", default=False)


class quiet_failures:
    """with quiet_failures(): … — 이 안에서 LLM 최종 실패 로그를 WARN 이 아니라 INFO 로 남긴다(호출부가 직접 기록하므로)."""
    def __enter__(self):
        self._tok = _QUIET.set(True)

    def __exit__(self, *exc):
        _QUIET.reset(self._tok)
        return False


def _fail_log(msg: str, *args) -> None:
    (logger.info if _QUIET.get() else logger.warning)(msg, *args)

DEFAULT_MODEL = "openai/gpt-oss-120b"
# llama-3.3-70b-versatile 는 이 Groq 계정에서 404 (2026-09 라인업 변경). 같은 계열
# gpt-oss-20b 로 폴백 — 작고 빠르며 지시이행 동일.
FALLBACK_MODEL = "openai/gpt-oss-20b"

# (v4.6.1) Groq 429 — 받으면 그 모델로는 다시 보내지 않고 한동안 이 프로세스에서 그 모델을 아예 부르지 않는다.
# 전엔 429 에도 `_call_groq` 가 1 · 2 · 4초 뒤 다시 보내고(3번), 판정 함수가 응답이 없어도 다시 묻기를 5회 돌려
# 판정 1건에 최대 30요청(5 × 두 모델 × 3번)이 나갔다 — 분당 · 일일 한도는 몇 초 뒤에 풀리지 않으니 429 만 키웠다(2026-10-21).
# 막는 시간: 일일 한도(TPD · RPD — 429 본문에 「per day」)면 1시간, 분당 한도면 Groq 가 알려 준 대기 시간(retry-after 헤더 ·
# 본문 「try again in …」, 없으면 60초). `vision.py` 의 v4.5.9 일일 차단과 같은 방식.
# 모델별로 막는다 — 한도가 모델마다 따로인지 공식 문서로 확인하지 못해, 주 모델이 막혀도 폴백 모델은 한 번 불러 본다(그것도 429 면 같이 막힌다).
DAILY_BLOCK_SEC = 3600
MINUTE_BLOCK_DEFAULT_SEC = 60
MINUTE_BLOCK_MAX_SEC = 600
_RATE_BLOCK: dict = {}      # model → {"until": epoch 초, "since": ISO, "kind": "daily" | "minute", "detail": 429 본문 앞부분}


def rate_block_state() -> dict:
    """지금 막혀 있는 모델 → {"kind", "since", "until"(ISO), "detail"} (이 프로세스 기준)."""
    from datetime import datetime, timezone
    now = time.time()
    return {m: {"kind": b["kind"], "since": b["since"], "detail": b["detail"],
                "until": datetime.fromtimestamp(b["until"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            for m, b in _RATE_BLOCK.items() if now < b["until"]}


def _blocked(model: str) -> "dict | None":
    b = _RATE_BLOCK.get(model)
    return b if b and time.time() < b["until"] else None


def _block_model(model: str, kind: str, sec: float, detail: str) -> None:
    from datetime import datetime, timezone
    prev = _blocked(model)
    _RATE_BLOCK[model] = {"until": time.time() + sec, "kind": kind, "detail": (detail or "")[:200],
                          "since": prev["since"] if prev else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def _retry_after_sec(resp) -> "float | None":
    """429 응답이 알려 준 대기 시간(초) — retry-after 헤더, 없으면 본문 「try again in 2m59.5s」 · 「7.66s」 · 「500ms」."""
    headers = getattr(resp, "headers", None) or {}
    try:
        ra = headers.get("retry-after")
        if ra:
            return float(ra)
    except (TypeError, ValueError, AttributeError):
        pass
    m = re.search(r"try again in ([0-9hms.]+)", getattr(resp, "text", "") or "")
    if not m:
        return None
    unit = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
    sec = sum(float(n) * unit[u] for n, u in re.findall(r"([0-9.]+)(ms|h|m|s)", m.group(1)) if n.strip("."))
    return sec or None

# 짧은 단위(1~6자)가 8회 이상 연속 반복 — "もぐもぐもぐ…" 같은 의성어 트윗.
# translate() 가 이 패턴이면 반복 그대로 LLM 에 보내지 않고 압축한다(§translate 참고).
_REPEAT_RE = re.compile(r"^(.{1,6}?)\1{7,}")

# 장음부호류(ー ｰ 〜 ～)가 2회 이상 연속 — 일본어 트윗 특유의 "글자 늘려쓰기" 강조 표기
# (예: "おーまーーたーーせー…" = 「お待たせ」를 늘려 쓴 것). _REPEAT_RE 와 달리 문자열
# 어디서든, 여러 군데 흩어져 나타나도 전부 잡는다(§translate 참고).
_STRETCH_RE = re.compile(r"[ーｰ〜～]{2,}")

# 느낌표·물음표 4회+ 연속 — "ゲットしました！！！！…(80개)" 같은 감정 표현. 문장 중간에 끼면
# _REPEAT_RE(맨 앞 한정) 가 못 잡아 모델이 `!` 를 max_tokens 끝까지 찍는 루프에 빠지고
# (실측 2026-10-07 리츠: 87자 입력 → 7493자 출력), 환각 가드에 매번 걸린다. 번역 전에 3개로
# 접고 번역 뒤 원래 개수로 되펼친다(_collapse_punct_runs / _restore_punct_runs).
_PUNCT_RUN_RE = re.compile(r"[！!]{4,}|[？?]{4,}")
_PUNCT_OUT_RE = re.compile(r"[！!]{3,}|[？?]{3,}")

# 같은 가나·한자 1글자가 8회+ 연속 — "うれしいぁぁぁ…(40개)" 처럼 문장 중간에 끼면 위와 같은
# 폭주 루프(실측: 46자 입력 → 7715자 출력 → 환각 가드 → None). 문장부호와 달리 번역하면
# 글자가 바뀌므로(ぁ→아) 개수를 복원하지 않고 5개로만 접는다. 구분선 기호(･ ━ 등)·이모지·
# 영문은 폭주 사례가 없고 번역문에 그대로 남아야 해서(스케줄 트윗 `🩵 ･････ 🩵`) 대상 아님.
# 접은 구간은 번역문에서 `ㅏㅏㅏㅏㅏ` 같은 단독 모음 자모로 나오기 쉬워 부자연스러우므로
# (기뻐요ㅏㅏㅏㅏㅏ) `~` 로 바꾼다. 개수는 원문 연속 개수 그대로(ぁ×40 → ~×40) — 자모 군집
# 수가 접은 구간 수와 같을 때만 순서대로 대응시키고, 안 맞으면 추측 없이 `~` 하나씩.
_JAMO_VOWEL_RUN_RE = re.compile(r"[ㅏ-ㅣ]{2,}")


def _fold_kana_runs(text: str) -> "tuple[str, list[int]]":
    """가나·한자 1글자 8회+ 연속을 5개로 접고 원래 개수 목록을 순서대로 돌려준다."""
    counts: "list[int]" = []

    def _fold(m: "re.Match[str]") -> str:
        counts.append(len(m.group(0)))
        return m.group(1) * 5

    return _KANA_RUN_RE.sub(_fold, text), counts


def _jamo_runs_to_tilde(text: str, counts: "list[int]") -> str:
    """번역문의 단독 모음 자모 군집을 `~` 로 — 군집 수 == 접은 구간 수면 원래 개수만큼."""
    found = _JAMO_VOWEL_RUN_RE.findall(text)
    if len(found) != len(counts):
        return _JAMO_VOWEL_RUN_RE.sub("~", text)
    it = iter(counts)
    return _JAMO_VOWEL_RUN_RE.sub(lambda m: "~" * next(it), text)
_KANA_RUN_RE = re.compile(r"([ぁ-ゖァ-ヺｦ-ﾟ一-龥々])\1{7,}")

# 고정 번역 용어집 — LLM 이 호출마다 다르게 옮기는 고유명사를 여기 등록하면 항상 이 값으로
# 고정된다(2026-09-13, 그룹명이 "꿈한계대 뮤타입"/"꿈꾸다"/"유메미타" 등으로 매번 달라지던
# 문제). preview/notice/tweet 번역 전부 이 용어집을 거친다 — 입력에서 원문을 자리표시자로
# 감싸 LLM 이 못 건드리게 막고(플레이스홀더는 일반 텍스트와 절대 안 겹치는 ASCII 토큰),
# 응답에서 다시 고정값으로 되돌린다. LLM 프롬프트 지시만으로는 100% 보장이 안 되므로
# (지시를 무시하고 여전히 의역하는 사례 실측) 이 기계적 치환이 최종 보증선이다.
#   등록값에 구두점(느낌표 등)은 넣지 않는다 — 원문에 있으면 번역문에도 그대로 남으므로
#   ("バンドリ！" → "뱅드림！"/"뱅드림!") 굳이 고정할 필요가 없다. 용어 자체만 고정.
GLOSSARY: dict[str, str] = {
    "夢限大みゅーたいぷ": "무겐다이 뮤타입",
    "バンドリ": "뱅드림",
}


def _mask_glossary(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    """용어집 항목을 LLM 이 건드리지 않을 자리표시자로 치환.

    토큰이 영숫자에 바로 들러붙으면(예: "バンドリ13thライブ" → "@@GLOSSARY@@13th")
    LLM 이 그 뒤 문장을 통째로 못 알아보고 미번역으로 남기는 사례가 실측됐다 — 그
    경우에만 한 칸 띄운다. 이미 공백·구두점과 붙어 있으면 그대로 둬(예: 「바로 뒤)
    불필요한 공백이 안 생기게.

    Returns:
        (치환된 텍스트, [(토큰, 일본어원문, 고정한국어역), ...])
    """
    masked = text or ""
    mapping: list[tuple[str, str, str]] = []
    for i, (ja, ko) in enumerate(GLOSSARY.items()):
        if ja in masked:
            token = f"@@GLOSSARY{i}@@"
            masked = masked.replace(ja, token)
            masked = re.sub(rf"(?<=[0-9A-Za-z]){re.escape(token)}", f" {token}", masked)
            masked = re.sub(rf"{re.escape(token)}(?=[0-9A-Za-z])", f"{token} ", masked)
            mapping.append((token, ja, ko))
    return masked, mapping


_GLOSSARY_LEAK_RE = re.compile(r"@+\s*GLOSSARY\s*\d*\s*@+")


def _unmask_glossary(text: str, mapping: list[tuple[str, str, str]], *, to: str) -> str:
    """자리표시자를 복원. to='ja' 면 일본어 원문으로, to='ko' 면 고정 한국어역으로.

    (버그리포트 20260916) LLM 이 토큰을 정확히 그대로 안 남기고 공백을 끼워 넣는 등
    변형하면(예: "@@ GLOSSARY0 @@") 아래 정확 일치 replace 가 못 잡아 원본 지시
    토큰이 번역 결과에 그대로 노출된 채 트윗/소식으로 게시되는 사고가 났다(아라레
    트윗 실사례). 정확 치환 후에도 남은 GLOSSARY 형태 잔재는 전부 지운다 — 이 함수가
    translate()/notice_title() 의 유일한 언마스크 경로라 여기서 한 번만 막으면 된다.
    """
    if not text:
        return text
    for token, ja, ko in mapping:
        text = text.replace(token, ja if to == "ja" else ko)
    cleaned, n = _GLOSSARY_LEAK_RE.subn("", text)
    if n:
        logger.warning("unmask_glossary: 잔여 GLOSSARY 토큰 %d개 제거 — %r", n, text)
        text = re.sub(r"\s{2,}", " ", cleaned).strip()
    return text


# (2026-10-14) 번역 프롬프트 · 부분 번역 감시.
# 배경: 옛 프롬프트의 "고유명사는 보존" 한 줄을 모델이 万バズ · ラーメン · リリース 같은 일반어 · 외래어에까지
# 적용해 일본어가 섞인 채 저장됐고(부분 번역), 성공 응답이라 로그도 INFO 뿐이었다. 또 配信 을 배송으로 옮기는 오역이
# 27건 있었다(ref/translation_audit_2026-10-14.md). 규칙을 구체화하고 멤버 이름 표를 함께 준다.
_CHANNELS_PATH = Path(__file__).resolve().parents[2] / "config" / "channels.json"
_member_cache: "tuple[str, list[str]] | None" = None


def _member_info() -> "tuple[str, list[str]]":
    """(프롬프트용 멤버 이름 줄, 가나 검사에서 뺄 이름 목록) — config/channels.json 에서 만든다.
    짧은 호칭(call_names)까지 줘야 みやこ 같은 호칭을 다른 멤버로 오역하지 않는다. 읽기 실패 시 빈 값."""
    global _member_cache
    if _member_cache is not None:
        return _member_cache
    line_parts: list[str] = []
    keep: list[str] = []
    try:
        cfg = json.loads(_CHANNELS_PATH.read_text(encoding="utf-8"))
        for k in cfg.get("channel_order", []):
            ch = (cfg.get("channels") or {}).get(k) or {}
            xn = (ch.get("x_names") or [None])[0]
            ko = ch.get("name_ko")
            if not xn or not ko:
                continue
            calls = "·".join(ch.get("call_names") or [])
            line_parts.append(f"{xn}({calls})={ko}" if calls else f"{xn}={ko}")
            keep += [*(ch.get("x_names") or []), *(ch.get("call_names") or [])]
    except Exception as e:
        logger.warning("translate: 멤버 이름 표를 못 읽음(%s) — 이름 표 없이 진행", e)
    _member_cache = (", ".join(line_parts), keep)
    return _member_cache


def _translate_prompt(masked_text: str) -> str:
    names_line, _ = _member_info()
    names_rule = (
        f"5. 멤버 이름(괄호는 짧은 호칭): {names_line}. 호칭만 나오면 해당 멤버의 이름으로 옮긴다"
        f"(みやこ=미야코, ののか=노노카 …). 서로 바꾸지 말 것. "
        if names_line else "5. "
    )
    return (
        "너는 일본 버추얼 유튜버 그룹 「무겐다이 뮤타입(夢限大みゅーたいぷ)」의 한국 팬 사이트 번역가다. "
        "아래 일본어 트윗/영상 제목을 자연스러운 한국어로 번역하라.\n"
        "규칙:\n"
        "1. 번역문만 출력한다(설명·주석·원문 병기 금지). 줄바꿈·이모지·기호·URL·@멘션은 그대로 둔다.\n"
        "2. 일본어 글자(히라가나·가타카나·한자)를 번역문에 남기지 않는다. 은어·신조어·인터넷 용어·외래어·음식/상품명·의성어·애칭도 "
        "뜻이 통하게 한국어로 번역하거나, 번역이 어려운 고유한 이름은 한국어 독음으로 적는다. "
        "(예: 万バズ→1만 버즈, ラーメン→라멘, リリース→릴리스, ついに→드디어, ありがとう→고마워) "
        "이모지 옆에 붙은 짧은 가타카나 단어·말장난·줄임말(예: 🍭ペロキャン)도 예외 없이 처리한다 — 뜻이 분명하면 뜻으로, 불분명하면 "
        "한국어 독음으로 적는다(ペロキャン→페로캔).\n"
        "3. 원문 그대로 두는 것: URL, @멘션, #해시태그, 「」『』 괄호와 그 안의 작품·곡 제목(괄호 모양도 바꾸지 말 것), "
        "@@GLOSSARY0@@ 같은 토큰(절대 번역·수정 금지).\n"
        "4. 방송 용어: 配信=방송(배송 아님), 配信予定/配信よてい=방송 예정, 〈配信のおしらせ〉=〈방송 안내〉, 歌枠=노래 방송, "
        "雑談=잡담, 朝活=아침 활동, 切り抜き=클립, メン限=멤버십 한정, 弾き語り=기타 치며 노래하기, 振り返り=회고.\n"
        + names_rule
        + "그 밖의 사람·지명·가게명은 일본어 발음대로 한국어 독음으로 적고, 호칭 さん·ちゃん·くん은 씨·짱·군으로 옮긴다.\n"
        "6. 그룹 애칭 「ゆめみた」는 항상 '유메미타'로 음차한다(꿈, 꿈꾸다 등으로 번역하지 말 것). 「ゆめ∞みた」는 '유메∞미타'.\n\n"
        f"일본어:\n{masked_text}"
    )


_SPECIAL_SPACE_RE = re.compile("[    ]")
_KANA_RE = re.compile("[぀-ヿｦ-ﾟ]")   # (v4.5.7) 반각 가나(U+FF66~FF9F)도 일본어 글자로 본다 — 전엔 전각만 봐서 「ﾍﾟﾛｷｬﾝ」 이 남아도 경고가 없었다
_HALFWIDTH_KANA_RUN_RE = re.compile("[ｦ-ﾟ]+")


def _widen_halfwidth_kana(text: str) -> str:
    """반각 가나 구간만 전각으로(NFKC) — 「ﾍﾟﾛｷｬﾝ」→「ペロキャン」. 모델이 반각 표기를 이모티콘 · 효과음처럼 보고
    번역하지 않고 그대로 두는 일을 막는다(2026-10-19 미야코 트윗, 번역 3/3 잔존 재현). ！ ～ 같은 다른 전각/반각 문자는 건드리지 않는다.
    모델에 보내는 문장에만 쓰고 저장되는 원문(text)은 그대로다."""
    return _HALFWIDTH_KANA_RUN_RE.sub(lambda m: unicodedata.normalize("NFKC", m.group()), text)


def _clean_translation(text: str) -> str:
    """모델이 섞는 특수 공백(U+202F 좁은 줄바꿈 금지 공백 등)을 일반 공백으로."""
    return _SPECIAL_SPACE_RE.sub(" ", text)


def _residual_kana(ko_text: str) -> list[str]:
    """번역문에 남은 히라가나·가타카나(부분 번역 의심). 일부러 원문으로 두는 것은 뺀다:
    URL · 해시태그 · 「」『』 안 · 괄호(이모티콘) 안 · 멤버 이름/호칭 · 용어집 원문 · ゆめみた · 장음/기호류."""
    s = re.sub(r"https?://\S+", "", ko_text)
    s = re.sub(r"[#＃]\S+", "", s)
    s = re.sub(r"「[^」]*」|『[^』]*』", "", s)
    s = re.sub(r"\([^)]*\)|（[^）]*）", "", s)
    keep = [*_member_info()[1], *GLOSSARY.keys(), "ゆめみた", "ユメミタ", "ゆめ∞みた"]
    for w in sorted(keep, key=len, reverse=True):
        s = s.replace(w, "")
    s = re.sub(r"[ー〜・ｰヮ゜]", "", s)
    return _KANA_RE.findall(s)


# Groq structured outputs (strict) — gpt-oss-120b/20b·qwen3.8-27b 지원.
# strict 규칙: 모든 필드 required, additionalProperties:false.
# https://console.groq.com/docs/structured-outputs
_NOTICE_TITLE_SCHEMA = {
    "name": "notice_title",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "title_ja": {"type": "string"},
            "title_ko": {"type": "string"},
        },
        "required": ["title_ja", "title_ko"],
        "additionalProperties": False,
    },
}

# (v3.6) URL 우선 ingest — 트윗에 걸린 유튜브 URL 이 우리 5인/공식 채널이 아닐 때,
# 그 트윗 작성자가 실제로 참여하는 콘텐츠인지 LLM 에게 확인(외부 콜라보 오탐 방지 게이트).
_PARTICIPATION_SCHEMA = {
    "name": "participation",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "participates": {"type": "boolean"},
        },
        "required": ["participates"],
        "additionalProperties": False,
    },
}

# (v3.6) URL 없는 개인 트윗 — 정규식 게이트(`配信` 키워드 + 날짜/시각)를 통과한 "후보"를
# 실제로 등록하기 전 마지막으로 묻는 확인. 실측(2026-09-16, 아라레 후기 트윗): 정규식은
# "配信"·"2時間"·"9/24" 를 각각 문맥 없이 따로 캐치해 오탐 후보를 만들지만, 이 질문을
# 그대로 던지면 LLM 은 "이건 후기지 예고가 아니다"라고 정확히 답한다.
# (v4.5.5) 근거 필수 — evidence(원문 그대로 복사한 구절) · reason(한 문장). 원문에 없는 근거 · 빈 근거는 받지 않고 다시 묻는다.
_ANNOUNCE_SCHEMA = {
    "name": "announces_own_broadcast",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "announces": {"type": "boolean"},
            "evidence": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["announces", "evidence", "reason"],
        "additionalProperties": False,
    },
}


def _norm_quote(t: str) -> str:
    """근거 구절 대조용 — NFKC 후 글자(L*) · 숫자(N*)만 남긴다. 공백 · 기호 · 장식 문자(❑ ━ ┊ ～ 이모지 등)는 LLM 이 옮겨 적으며
    바꾸거나 빼기 쉬워(실측: 아라레 「❑ ━━━ 配信予定 ━━━ ❑ ┊ 10/15(木) 6:30~┊」 5회 모두 불일치) 비교에서 뺀다."""
    import unicodedata
    t = unicodedata.normalize("NFKC", t or "")
    return "".join(c for c in t if unicodedata.category(c)[0] in ("L", "N"))


def evidence_in_text(evidence: str, text: str) -> bool:
    """(v4.5.5) LLM 이 낸 근거 구절이 원문에 실제로 있나(정규화 후 부분 문자열). 2자 미만은 근거로 보지 않는다."""
    e = _norm_quote(evidence)
    return len(e) >= 2 and e in _norm_quote(text)


def _banner_title(title: str, text: str) -> str:
    """(v4.5.10) 행사 · 가챠 제목 정리 — 「…」 로 감싼 부분이 있으면 그 안쪽만(「チャレンジライブイベント「アイの奔流 AtoZ」」 → アイの奔流 AtoZ),
    본문에 대소문자 · 전각/반각만 다르게 있으면 본문 표기(비전이 「shake your 魂」 처럼 읽어도 본문 「Shake Your 魂」 으로). 본문 우선(2026-10-21 운영자 지시)."""
    import unicodedata
    t = (title or "").strip()
    m = re.search(r"「([^「」]+)」", t)
    if m:
        t = m.group(1).strip()
    t = t.strip("「」『』 　")
    if not t:
        return t
    r = unicodedata.normalize("NFKC", text or "")
    i = r.casefold().find(unicodedata.normalize("NFKC", t).casefold())
    return r[i:i + len(unicodedata.normalize("NFKC", t))] if i >= 0 else t


_DAY_WORDS_JA = {"本日": 0, "今日": 0, "今夜": 0, "このあと": 0, "この後": 0, "明日": 1, "あす": 1, "あした": 1}


def _jst_in_evidence(value: str | None, evidence: str, posted_jst: str) -> bool:
    """(v4.5.10) "YYYY-MM-DD[ HH:MM]" 값이 **그 값의 근거 구절**에 적혀 있나 — 날짜(10月7日 · 10/7 · 2026.10.7 · 明日 등 게시일 기준 상대 표현)와,
    시각이 있으면 시각(20:59 · 15時)까지. 다른 항목의 기간을 빌려 쓴 값(실측: AtoZ 가챠 종료에 이벤트 종료 10/7 을 옮김)을 거른다."""
    import datetime as _dt
    import unicodedata
    m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?\s*$", value or "")
    if not m:
        return False
    t = unicodedata.normalize("NFKC", evidence or "")
    mo, d = int(m.group(2)), int(m.group(3))
    ok = bool(re.search(rf"(?<!\d)0?{mo}\s*月\s*0?{d}\s*日", t) or re.search(rf"(?<!\d)0?{mo}\s*[/.]\s*0?{d}(?!\d)", t))
    if not ok:
        pm = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})", posted_jst or "")
        if pm:
            base = _dt.date(int(pm.group(1)), int(pm.group(2)), int(pm.group(3)))
            want = _dt.date(int(m.group(1)), mo, d)
            ok = any(w in t and base + _dt.timedelta(days=off) == want for w, off in _DAY_WORDS_JA.items())
    if not ok:
        return False
    if m.group(4) is not None:
        h, mi = int(m.group(4)), m.group(5)
        return bool(re.search(rf"(?<!\d)0?{h}\s*:\s*{mi}(?!\d)", t) or (mi == "00" and re.search(rf"(?<!\d)0?{h}\s*時", t)))
    return True


def _near_event_word(title: str, full: str) -> bool:
    """(v4.5.10) 인게임 이벤트 표지 — 제목 앞 40자 · 뒤 20자 안에 「イベント」가 있나(본문 · 이미지 글자).
    실측: 「BanG Dream! 13th☆LIVE「DIMENSIONAL OVERLAP」開催記念 ミッションパス」 의 라이브(공연) 이름을 이벤트로 뽑은 일이 있었다."""
    import unicodedata
    f = unicodedata.normalize("NFKC", full or "").casefold()
    k = unicodedata.normalize("NFKC", title or "").casefold()
    i = f.find(k) if k else -1
    while i >= 0:
        if "イベント" in f[max(0, i - 40):i + len(k) + 20]:
            return True
        i = f.find(k, i + 1)
    return False


# (v4.5.10) 행사 판정 2단계 — 1단계 = 게임 안/밖(근거 구절 목록), 2단계 = 이벤트 · 가챠 옮겨 적기. 배너 처리는 코드(banners.plan_post).
_NOTICE_TIMING_SCHEMA = {
    "name": "notice_timing",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["announce", "report"]},
            "subject": {"type": "string"},
            "subject_date": {"type": ["string", "null"]},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "next_lines": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["kind", "subject", "subject_date", "evidence", "next_lines", "reason"],
        "additionalProperties": False,
    },
}
# (v4.7.0) 소식 분류 — LLM 이 고르는 4분류. Our Notes(game) · 기타(etc)는 코드가 정한다(telegram_app._notice_categories).
NOTICE_LLM_CATS = ("live", "event", "goods", "broadcast")
_NOTICE_CATS_SCHEMA = {
    "name": "notice_categories",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "cats": {"type": "array", "items": {"type": "string", "enum": list(NOTICE_LLM_CATS)}},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["cats", "evidence", "reason"],
        "additionalProperties": False,
    },
}
# (v4.7.0) 라이브공연 소식의 공연 이름 · 공연일 — 라이브공연 탭의 공연별 묶음 열쇠
_LIVE_INFO_SCHEMA = {
    "name": "live_info",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "name_evidence": {"type": "string"},
            "date": {"type": "string"},
            "date_evidence": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["name", "name_evidence", "date", "date_evidence", "reason"],
        "additionalProperties": False,
    },
}
# (v4.7.0) 분류 프롬프트 = 소식 분류 시험 4차 A 안(devpapers ref/notice-category/round4/prompt_A_batch0.txt)을 글 하나용으로 옮긴 것.
# 시험은 9건씩 묶어 보냈다 — 묶음 표현(「글 여러 개」 · 「글 번호(n)마다」)만 바꾸고 분류 정의 · 경계 예시 문장은 그대로 둔다.
# 개량은 핫픽스로 이 문자열만 바꾼다(2026-10-23 운영자 결정). 바꾸면 NOTICE_CAT_PROMPT 도 올린다.
NOTICE_CAT_PROMPT = "r4"
_NOTICE_CAT_HEAD = (
    "아래는 X(트위터) 글이다. 이 글은 성우 밴드 「夢限大みゅーたいぷ」(유메미타 — 仲町あられ · 宮永ののか · 峰月律 · 藤都子 · 千石ユノ)의 "
    "공식 계정이 쓰거나 리포스트한 글이다. 이 글이 알리는 것에 해당하는 분류를 아래에서 **모두** 골라라. 없으면 빈 목록.\n"
    "- live (라이브공연): 유메미타 전체 또는 일부 멤버가 무대에 서는 공연 — 단독 · 합동 · 프리 라이브, 투어. "
    "그 공연의 티켓 판매 · 추첨 · 중지 · 변경 안내도 포함. 공연 굿즈 판매 · 통판 안내는 live 와 goods 둘 다.\n"
    "- event (오프라인행사): 공연이 아닌, 유메미타 멤버가 나오는 행사 — 사인회(인터넷 사인회 포함) · お渡し会 · 릴리즈 이벤트 · "
    "토크쇼 · 전시 · 팝업 스토어 · 콜라보 행사.\n"
    "- goods (음원·굿즈): 유메미타의 CD(싱글 · 앨범) · 음원 · 커버곡 출시(커버곡 · MV 영상 공개 포함), 굿즈 · Blu-ray · 코믹스 등 "
    "판매되는 물건과 그 예약 · 판매 · 특전 안내. 유메미타가 잡지에 실린다는 소식(雑誌掲載 · 인터뷰 · 특집 · 포스터)도 goods. "
    "공연장 · 행사장 물판, CD 발매 기념 행사(릴리즈 이벤트 · 사인회 · お渡し会)도 포함(그 공연 · 행사 분류와 함께).\n"
    "- broadcast (방송): 유메미타 멤버가 출연하는 방송 — 유튜브 생방송 · 동시 시청 · 생일 방송, 「バンドリ！TV LIVE」, 라디오, "
    "TV · 니코니코 프로그램 출연, 멤버가 나오는 행사의 생중계(「様子を生配信」). 공연의 유튜브 생중계는 live 와 broadcast 둘 다. "
    "애니메이션 「ゆめ∞みた」의 방영 · 방송 시작 · 배신 · 몰아보기 안내는 멤버가 출연하는 방송이 아니므로 broadcast 가 아니다.\n"
    "경계 예시 — 한 글이 둘 이상에 걸치는 일이 많다. 분류 하나를 고른 뒤에도 나머지 분류를 하나씩 다시 확인해 빠뜨리지 말 것.\n"
    "- 공연 굿즈의 판매 · 선행 판매 · 통판 · 사후 통판 안내 → live, goods. 굿즈만 다루는 글이라도 어느 공연의 굿즈인지 적혀 있으면 live 도 고른다. "
    "「BanG Dream! ○th LIVE」처럼 여러 밴드가 함께 서는 공연도, 글에 유메미타(夢限大みゅーたいぷ · #ゆめみた)가 나오면 유메미타 공연이다. "
    "(공연 티켓 판매는 live 만 — goods 아님. 「バンドリ！TV LIVE」는 방송 프로그램 이름이라 live 가 아니라 broadcast.)\n"
    "- CD(싱글 · 앨범) 발매를 기념하는 릴리즈 이벤트 · 사인회 · お渡し会의 개최 · 중지 · 참가 감사 · 다음 회차 안내 → event, goods. "
    "CD 발매와 무관한 행사(전시 · 생일 · 기념일을 기념하는 お渡し会 · 사인회 등)는 event 만 — 행사에서 무언가를 받거나 산다는 것만으로는 goods 가 아니다.\n"
    "- 팬 · 영상 제작자 등 다른 사람이 만든 유메미타 커버곡 영상 · MV 를 리포스트하거나 소개하는 글(「covered by 夢限大みゅーたいぷ」) → goods. "
    "만든 사람이 외부여도, 판매가 아니어도 같다.\n"
    "- 공연(프리 라이브 포함)을 유튜브 등으로 생중계(「フリーライブ … YouTubeにて生配信」 「全編無料配信」) → live, broadcast.\n"
    "evidence = 판단 근거가 된 구절들 — 글에서 한 줄씩 그대로 복사(바꾸지 말 것).\n"
    "reason = 판단 이유 한국어 한 문장.\nJSON 으로만 답하라.\n"
)


def _md_in_evidence(date: str, evidence: str, posted_date: str = "") -> bool:
    """(v4.7.0) 공연일 YYYY-MM-DD 의 월 · 일이 근거 줄에 실제로 적혀 있나 — 「12/24」 「12月24日」 「12.24」 「2026.12.24」.
    「本日」 「今日」 「今夜」 는 게시일과 같을 때만. 티켓 접수일 같은 다른 날짜를 공연일로 고른 것은 못 거른다(그건 프롬프트 몫)."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date or "")
    if not m:
        return False
    import unicodedata
    ev = unicodedata.normalize("NFKC", evidence or "")
    mo, d = int(m.group(2)), int(m.group(3))
    if re.search(rf"(?<!\d)0?{mo}\s*[/月.\-]\s*0?{d}(?!\d)", ev):
        return True
    return bool(posted_date) and date == posted_date and bool(re.search(r"本日|今日|今夜", ev))


_BANNER_SCOPE_SCHEMA = {
    "name": "banner_scope",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": ["in_game", "outside"]},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["scope", "evidence", "reason"],
        "additionalProperties": False,
    },
}
_BANNER_EXTRACT_SCHEMA = {
    "name": "banner_extract",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["event", "gacha"]},
                    "status": {"type": "string", "enum": ["normal", "postponed", "cancelled"]},
                    "title_ja": {"type": "string"}, "title_ko": {"type": "string"},
                    "start_jst": {"type": ["string", "null"]}, "start_evidence": {"type": "string"},
                    "end_jst": {"type": ["string", "null"]}, "end_evidence": {"type": "string"},
                },
                "required": ["kind", "status", "title_ja", "title_ko", "start_jst", "start_evidence", "end_jst", "end_evidence"],
                "additionalProperties": False,
            }},
            "image_roles": {"type": "array", "items": {"type": "string", "enum": ["event", "gacha", "none"]}},
            "reason": {"type": "string"},
        },
        "required": ["items", "image_roles", "reason"],
        "additionalProperties": False,
    },
}


def _strip_json_fence(text: str) -> str:
    """```json ... ``` 펜스나 앞뒤 잡텍스트를 벗겨 JSON 본체만 남긴다."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if 0 <= i < j else t.strip()


def _normalize_stretch(text: str) -> str:
    """장음부호류 연속(2회+)을 1회로 접는다 — 의미는 그대로 두고 문체적 강조만 정규화.

    (버그리포트 20260913 #4) "おーまーーたーーせー…"처럼 글자마다 다른 길이로 장음부호가
    끼어드는 늘려쓰기는 `_REPEAT_RE`(맨 앞·단일 유닛 8회+ 반복) 로는 못 잡는다. 그대로
    보내면 v3.1.8 이 대응한 것과 같은 LLM 반복 루프에 빠져 환각 가드에 매번 걸린다
    (실측: 204자 입력 → 2035자 응답, `temperature=0`이라 재시도해도 항상 동일 실패).
    표적을 장음부호류로 한정한 이유: 아무 문자나 2연속을 접으면 "宮永ののか"(멤버명 자체의
    반복 글자) → "宮永のか", "かわいい" → "かわい", "https://www." → "htps:/w." 처럼 정상
    단어·고유명사·URL 이 깨진다(실측 확인 후 표적 축소).
    """
    return _STRETCH_RE.sub(lambda m: m.group(0)[0], text)


def _punct_class(ch: str) -> str:
    return "!" if ch in "！!" else "?"


def _collapse_punct_runs(text: str) -> "tuple[str, list[tuple[str, int]]]":
    """！/？ 4회+ 연속을 3개로 접고 (종류, 원래 개수) 목록을 순서대로 돌려준다."""
    runs: "list[tuple[str, int]]" = []

    def _fold(m: "re.Match[str]") -> str:
        runs.append((_punct_class(m.group(0)[0]), len(m.group(0))))
        return m.group(0)[:3]

    return _PUNCT_RUN_RE.sub(_fold, text), runs


def _restore_punct_runs(text: str, runs: "list[tuple[str, int]]") -> str:
    """번역문의 ！/？ 3회+ 군집을 접기 전 개수로 되펼친다. 군집 수·종류 순서가 입력과
    안 맞으면(모델이 합치거나 쪼갠 경우) 추측하지 않고 접힌 채로 둔다."""
    if not runs:
        return text
    found = _PUNCT_OUT_RE.findall(text)
    if len(found) != len(runs) or any(_punct_class(f[0]) != r[0] for f, r in zip(found, runs)):
        return text
    it = iter(runs)
    return _PUNCT_OUT_RE.sub(lambda m: m.group(0)[0] * next(it)[1], text)


class LLMClient:
    """Groq 외부 LLM 클라이언트."""

    _last_err: str = ""   # 마지막 Groq 호출 실패 원인(최종 실패 로그 한 줄에 넣기 위함)

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        fallback: str = FALLBACK_MODEL,
        session: "requests.Session | None" = None,
        timeout: float = 20.0,
    ):
        """
        Groq LLM 클라이언트 초기화.

        Args:
            api_key: Groq API 키. 비어있으면 disabled.
            model: 메인 모델 (기본 gpt-oss-120b)
            fallback: 폴백 모델 (기본 openai/gpt-oss-20b)
            session: 선택사항 requests.Session (테스트 mock 용)
            timeout: API 호출 타임아웃 (초)
        """
        self.api_key = api_key.strip() if api_key else ""
        self.model = model
        self.fallback = fallback
        self.session = session or requests.Session()
        self.timeout = timeout
        self.disabled = not self.api_key

    def notice_title(
        self, body_no_date_url: str, *, lang_hint: str = "ja"
    ) -> dict | None:
        """
        소식 본문에서 이벤트 제목 1줄 추출 및 번역.

        Args:
            body_no_date_url: 본문 텍스트 (날짜/URL 제거됨)
            lang_hint: 입력 언어 힌트 (기본 "ja")

        Returns:
            {"title_ja": str, "title_ko": str} 또는 실패 시 None
        """
        if self.disabled:
            logger.warning("LLMClient disabled (api_key missing)")
            return None

        masked_body, mapping = _mask_glossary(body_no_date_url)
        prompt = (
            f"다음 이벤트 공지 본문에서 자연스러운 제목 1줄을 뽑아내고 일본어와 한국어로 제시하라. "
            f"JSON 포맷만 출력 (다른 텍스트 제외). 고유명사 보존. "
            f"@@GLOSSARY0@@ 같은 토큰은 절대 번역·수정하지 말고 그대로 출력에 남겨라.\n\n"
            f"본문:\n{masked_body}\n\n"
            f"출력:\n"
            f'{{"title_ja": "<일본어>", "title_ko": "<한국어>"}}'
        )

        response = self._call_groq(self.model, prompt, json_schema=_NOTICE_TITLE_SCHEMA)
        if not response:
            logger.warning(
                f"notice_title: 메인 모델 실패/빈 응답, fallback 시도"
            )
            response = self._call_groq(
                self.fallback, prompt, json_schema=_NOTICE_TITLE_SCHEMA
            )

        if not response:
            logger.warning("notice_title: 폴백도 실패")
            return None

        # 환각 가드: 출력 비었거나 입력 길이 3배 초과
        if self._is_hallucination(response, masked_body):
            logger.warning(
                f"notice_title: 환각 가드 발동 (input={len(body_no_date_url)}, "
                f"output={len(response)})"
            )
            return None

        try:
            result = json.loads(_strip_json_fence(response))
            if isinstance(result, dict) and "title_ja" in result and "title_ko" in result:
                result["title_ja"] = _unmask_glossary(result["title_ja"], mapping, to="ja")
                result["title_ko"] = _unmask_glossary(result["title_ko"], mapping, to="ko")
                return result
            else:
                logger.warning(f"notice_title: 예상 필드 부재 {result}")
                return None
        except json.JSONDecodeError as e:
            logger.warning(f"notice_title: JSON 파싱 실패 — {e}")
            return None

    def song_reading(self, title: str) -> str | None:
        """(v4.2.0) 곡명의 독음(읽는 법)을 히라가나로. 라틴 문자 곡명은 가타카나 발음으로(검색은 가타카나 = 히라가나로 정규화됨).

        신곡 자동 등록(`handlers._detect_new_songs`) · 독음 재요청(`admin_api.regenerate_song_reading`)이 쓴다.
        Returns: 독음 문자열. 키 없음 · 호출 실패 · 빈 응답 · 이상한 응답(가나 · 공백 · 기호 외 글자만 있는 등)이면 None —
        호출부가 `needs_reading` 으로 남겨 다음 tick 에 재시도한다.
        """
        if self.disabled or not (title or "").strip():
            return None
        prompt = (
            "다음은 일본 음악 그룹의 곡명이다. 이 곡명을 일본어로 읽는 법(독음)을 가나로만 적어라. "
            "한자 · 숫자 · 기호는 읽는 소리 그대로 히라가나로, 알파벳 · 영어 곡명은 일본어식 발음의 가타카나로 적는다. "
            "띄어쓰기 · 괄호 · 느낌표 등 기호는 모두 빼고 이어서 적는다. 의미 설명 · 번역 · 따옴표 없이 JSON 만 출력.\n\n"
            f"곡명: {title}\n\n"
            "출력:\n"
            '{"reading": "<가나 독음>"}'
        )
        schema = {
            "name": "song_reading",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"reading": {"type": "string"}},
                "required": ["reading"],
                "additionalProperties": False,
            },
        }
        prompt = _with_hint(prompt)
        response = self._call_groq(self.model, prompt, json_schema=schema)
        if not response:
            response = self._call_groq(self.fallback, prompt, json_schema=schema)
        if not response:
            logger.warning("song_reading: 두 모델 모두 실패/빈 응답 (%r)", title)
            return None
        try:
            result = json.loads(_strip_json_fence(response))
        except json.JSONDecodeError as e:
            logger.warning("song_reading: JSON 파싱 실패 — %s", e)
            return None
        reading = result.get("reading") if isinstance(result, dict) else None
        if not isinstance(reading, str):
            return None
        reading = re.sub(r"\s+", "", reading)
        # 가나(+장음 ー ・ 중점)와 영숫자만 허용 — 한글 번역이나 설명이 섞여 오면 버린다
        if not reading or len(reading) > 120 or not re.fullmatch(r"[ぁ-ゖァ-ヺー・ヽヾゝゞA-Za-z0-9]+", reading):
            logger.warning("song_reading: 가나가 아닌 응답 버림 (%r → %r)", title, reading)
            return None
        return reading

    def participation(self, text_ja: str, *, member_name: str) -> bool | None:
        """
        (v3.6) 트윗 원문이 `member_name` 이 직접 출연·참여하는 콘텐츠를 가리키는지 판정.

        URL 우선 ingest 경로에서, 걸려있는 유튜브 URL 의 채널이 우리 5인/공식 채널이
        아닐 때만 호출된다(외부 채널 콜라보 오탐 방지 게이트). 제대로 된 JSON 응답을
        받을 때까지 최대 5회 시도(5xx 백오프는 `_call_groq` 담당, v4.6.1 부터 호출 실패 · 429 면 다시 묻지 않고 바로) — 5회 모두
        실패하면 None 을 반환하고, 호출부는 등록하지 않는 쪽(안전한 실패)으로 처리한다.

        Args:
            text_ja: 트윗 원문(원어 그대로 — 마스킹만 적용, 번역은 안 함)
            member_name: 참여 여부를 판정할 멤버 이름(한국어 표기)

        Returns:
            True/False 또는 5회 모두 실패 시 None
        """
        if self.disabled:
            logger.warning("LLMClient disabled (api_key missing)")
            return None

        masked_text, _mapping = _mask_glossary(text_ja or "")
        prompt = (
            f"다음은 X(트위터) 게시물 원문이다. 이 글이 '{member_name}'이(가) 직접 "
            f"출연·참여하는 영상/콘텐츠를 홍보 또는 언급하는 글인지 판단하라. "
            f"단순 감상·잡담·무관한 리트윗이면 false. JSON 포맷만 출력.\n\n"
            f"원문:\n{masked_text}\n\n출력:\n"
            f'{{"participates": <true 또는 false>}}'
        )

        for attempt in range(1, 6):
            prompt = _with_hint(prompt)   # (v4a) 재판단이면 「반려됐다」 힌트를 앞에 붙인다
            response = self._call_groq(self.model, prompt, json_schema=_PARTICIPATION_SCHEMA)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=_PARTICIPATION_SCHEMA)
            if not response:
                break   # (v4.6.1) 호출 실패(429 · 5xx · 네트워크)면 다시 묻지 않는다 — 다시 묻기는 답이 틀렸을 때만
            try:
                result = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"participation: JSON 파싱 실패 (attempt {attempt}/5) — {response!r}")
                continue
            if isinstance(result, dict) and isinstance(result.get("participates"), bool):
                return result["participates"]
            logger.info(f"participation: 예상 필드 부재 (attempt {attempt}/5) — {result!r}")

        logger.info("participation: 호출 실패 또는 5회 모두 실패 — None (호출부 미등록 처리) — 호출부가 기록")
        return None

    def announces_own_broadcast(self, text_ja: str, unit_name: str | None = None) -> bool | None:
        """
        (v3.6) 트윗 원문이 작성자 본인이 추후 진행할 방송을 예고하는 글인지 최종 확인.

        URL 없는 개인 트윗 경로(3-2)의 마지막 관문 — 정규식 게이트+날짜/시각 추출까지
        통과한 후보에 대해서만 호출된다(비용 절감). 최대 5회 시도, 5회 모두 실패하면 None(안전한 실패 — 호출부는 미등록 처리).

        (v4.5.5) **근거 필수** — 판정마다 `evidence`(원문에서 그대로 복사한 구절) · `reason`(한 문장)을 받는다.
        근거가 비었거나 원문에 없는 구절이면 그 판정을 받지 않고 「근거가 없었다」는 안내를 붙여 다시 묻는다(5회 안에서).
        통과한 근거는 `self.last_reason` 에 남는다(호출부가 LLM 판단 기록에 적는다).
        프롬프트도 다시 썼다 — 2026-10-06~19 판정 10건 중 9건이 틀렸다(「グッズ紹介」 「#APEX」 「13thライブ振り返り」 「朝活」 처럼
        방송 **주제**에 걸려 진짜 예고를 false 로, 「配信延期します」(연기 공지)를 true 로). 주제는 따지지 않고, 플랫폼이 없으면
        본인 유튜브 방송으로 보며, 연기 · 취소 · 휴방 · 후기는 false 로 분명히 적었다.

        Args:
            text_ja: 트윗 원문(원어 그대로)
            unit_name: 작성자(유닛) 이름

        Returns:
            True/False 또는 5회 모두 실패(응답 없음 · 근거 없음 포함) 시 None
        """
        self.last_reason = ""
        if self.disabled:
            logger.warning("LLMClient disabled (api_key missing)")
            return None

        masked_text, _mapping = _mask_glossary(text_ja or "")
        who = unit_name or "작성자"
        base = (
            f"다음은 {who}(작성자)가 쓴 X(트위터) 게시물 원문이다.\n\n{masked_text}\n\n"
            "질문: 이 글은 작성자가 앞으로 직접 할 방송(配信 — 라이브 · 프리미어)의 일정을 알리는 예고인가?\n\n"
            "판단 기준:\n"
            "- 「配信」 「配信のおしらせ」 「配信告知」 「配信予定」 「配信よてい」 처럼 작성자 자신의 방송을 알리는 표현과 "
            "앞으로의 날짜 · 시각(本日 · 今夜 · 明日 · 10/19 22:30～ · あさ7:00 등)이 함께 있으면 예고다 → true.\n"
            "- 방송 **주제는 따지지 않는다**. 게임(APEX 등) · 잡담 · 노래(歌枠) · 굿즈 소개 · 라이브(공연) 회고 · 발표(おしらせ) · "
            "아침 방송(朝活) · 네일 · 작업 방송 모두 방송이면 true. 「グッズ」 「13thライブ」 「#APEX」 같은 단어가 있다는 이유로 false 하지 않는다.\n"
            "- 플랫폼이 적혀 있지 않으면 작성자의 유튜브 방송으로 본다. 「URLは直前」 「縦型配信」 「サムネなし」 「30分くらい」 같은 안내는 예고의 일부다.\n"
            "- false 인 경우: 이미 끝난 방송의 후기 · 감사 인사(「配信ありがとうございました」), 방송 **연기 · 취소 · 휴방** 공지"
            "(「延期」 「中止」 「お休み」 — 예정됐던 방송을 미루거나 안 한다는 글. **새 날짜가 함께 적혀 있어도 false** — 일정 변경은 다른 판정이 처리한다), "
            "방송이 아닌 일정 그 자체(공연 · 이벤트 출연 · 발매 · 굿즈 판매), "
            "다른 사람의 방송 홍보, 다른 플랫폼이 적힌 방송(ニコ生 · Twitch · ツイキャス · SHOWROOM · bilibili 등), "
            "날짜 · 시각 없이 「また配信します」 정도의 언급.\n\n"
            "JSON 만 출력한다:\n"
            "- announces: true 또는 false\n"
            "- evidence: 판단의 근거가 된 원문 구절을 **원문 그대로 복사**한다(예: 「10/19 22:30～」 「配信延期します」). 원문에 없는 말을 쓰지 않는다.\n"
            "- reason: 왜 그렇게 판단했는지 한국어 한 문장."
        )
        base = _with_hint(base)   # (v4a) 재판단이면 「반려됐다」 힌트를 앞에 붙인다(한 번만)
        prompt = base
        for attempt in range(1, 6):
            response = self._call_groq(self.model, prompt, json_schema=_ANNOUNCE_SCHEMA)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=_ANNOUNCE_SCHEMA)
            if not response:
                break   # (v4.6.1) 호출 실패(429 · 5xx · 네트워크)면 다시 묻지 않는다 — 다시 묻기는 답이 틀렸을 때만
            try:
                result = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"announces_own_broadcast: JSON 파싱 실패 (attempt {attempt}/5) — {response!r}")
                continue
            if not (isinstance(result, dict) and isinstance(result.get("announces"), bool)):
                logger.info(f"announces_own_broadcast: 예상 필드 부재 (attempt {attempt}/5) — {result!r}")
                continue
            ev, why = str(result.get("evidence") or "").strip(), str(result.get("reason") or "").strip()
            if len(why) < 5 or not evidence_in_text(ev, masked_text):
                logger.info(f"announces_own_broadcast: 근거 없음 · 원문에 없는 근거 — 다시 묻는다 (attempt {attempt}/5) — {result!r}")
                prompt = (base + "\n\n주의: 바로 전 답은 근거가 없거나 원문에 없는 구절을 근거로 들어 받지 않았다. "
                          "evidence 에는 위 원문에 실제로 있는 구절을 그대로 복사하고, reason 에 판단 이유를 한 문장으로 적어라.")
                continue
            self.last_reason = f"{why} (근거: 「{ev}」)"
            return result["announces"]

        logger.info("announces_own_broadcast: 호출 실패 또는 5회 모두 실패(응답 · 근거) — None (호출부 미등록 처리) — 호출부가 기록")
        return None

    def collab_partners(self, text_ja: str, *, host_name: str,
                        candidate_names: list[str]) -> list[str] | None:
        """
        (v3.8.6) 호스트 멤버의 트윗에 다른 멤버 이름이 하나 이상 언급됐을 때, 그 방송이
        언급된 멤버(들)와 실제로 합동하는 방송인지 판정.

        발동 조건은 호출부(`_maybe_url_confirmed_schedule`)가 `xtweet.find_guest_members`로
        이미 걸러둔다 — 여기서는 "언급됐다"를 "실제로 같이 나온다"로 그대로 승격하지
        않고 문맥으로 재확인만 한다(실측: 이름 언급이 안부 인사·잡담·과거 회상일 수도
        있음). `candidate_names`에 없는 멤버는 애초에 텍스트에 언급이 없었던 것이므로
        판정 대상이 아니다 — 언급된 멤버만 카운팅.

        Args:
            text_ja: 트윗 원문(+인용 트윗 있으면 합본, 원어 그대로)
            host_name: 이 방송을 진행하는 호스트 멤버 이름(한국어 표기)
            candidate_names: 텍스트에서 정식 표기로 발견된 다른 멤버 이름(한국어 표기) 후보 목록

        Returns:
            candidate_names 의 부분집합(실제 합동으로 확인된 멤버만) 또는 5회 모두
            실패 시 None(호출부는 안전하게 "게스트 미추가"로 처리).
        """
        if not candidate_names:
            return []
        if self.disabled:
            logger.warning("LLMClient disabled (api_key missing)")
            return None

        masked_text, _mapping = _mask_glossary(text_ja or "")
        cand_list = "、".join(candidate_names)
        prompt = (
            f"다음은 '{host_name}'이(가) 작성한 X(트위터) 게시물 원문이다. 이 글에는 "
            f"다른 멤버 이름이 언급되어 있다: {cand_list}.\n"
            f"이 게시물이 예고/설명하는 방송이 언급된 멤버와 실제로 함께 진행하는 "
            f"합동(콜라보) 방송인지 판단하라. 이름이 언급됐다고 항상 합동은 아니다 — "
            f"안부 인사·잡담·과거 회상처럼 이번 방송과 무관하게 언급된 경우는 포함하지 "
            f"마라. 실제로 이번 방송에 함께 출연/참가하는 멤버만 후보 중에서 골라라. "
            f"아무도 해당 없으면 빈 배열. JSON 포맷만 출력.\n\n"
            f"원문:\n{masked_text}\n\n출력:\n"
            f'{{"collab_with": [<후보 중 실제 합동 멤버 이름들>]}}'
        )
        schema = {
            "name": "collab_partners",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "collab_with": {
                        "type": "array",
                        "items": {"type": "string", "enum": candidate_names},
                    },
                },
                "required": ["collab_with"],
                "additionalProperties": False,
            },
        }

        for attempt in range(1, 6):
            prompt = _with_hint(prompt)   # (v4a) 재판단이면 「반려됐다」 힌트를 앞에 붙인다
            response = self._call_groq(self.model, prompt, json_schema=schema)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=schema)
            if not response:
                break   # (v4.6.1) 호출 실패(429 · 5xx · 네트워크)면 다시 묻지 않는다 — 다시 묻기는 답이 틀렸을 때만
            try:
                result = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"collab_partners: JSON 파싱 실패 (attempt {attempt}/5) — {response!r}")
                continue
            if isinstance(result, dict) and isinstance(result.get("collab_with"), list):
                return [n for n in result["collab_with"] if n in candidate_names]
            logger.info(f"collab_partners: 예상 필드 부재 (attempt {attempt}/5) — {result!r}")

        logger.info("collab_partners: 호출 실패 또는 5회 모두 실패 — None (호출부 미추가 처리) — 호출부가 기록")
        return None

    def broadcast_change_targets(self, text_ja: str, candidates: list[dict], now_kst: str) -> dict | None:
        """
        (v4a) 취소·변경 글 판정 + **어느 방송인지 선택**. 옛 `broadcast_change`(2026-10-01 삭제)는 종류만 판정해 호출부가
        "가장 이른 1개"를 고르는 규칙이라, "오늘 휴방"인데 오늘 방송이 2개인 경우 1개만 내려갔다
        (2026-09-30 리츠). 여기서는 그 멤버의 활성 예고 목록을 주고 영향받는 방송의 id 를 고르게 한다.

        Args:
            text_ja: 트윗 원문
            candidates: [{"id", "when": "MM/DD HH:MM"(KST), "title"}] — 그 멤버가 호스트인 활성 예고
            now_kst: 지금 KST "MM/DD(요일) HH:MM" — 오늘/내일 · 아침/밤 같은 상대 표현의 기준

        Returns:
            {"action": "del"|"edit"|"none", "target_ids": [...], "when": "MM/DD HH:MM"|None, "reason": str}
            reason = 판정 근거 한 줄(한국어) — "없음"일 때도 쓴다(놓친 사례를 나중에 확인·프롬프트 조정하는 자료).
            5회 모두 실패 시 None(호출부는 아무것도 바꾸지 않는다).
        """
        if self.disabled:
            logger.warning("LLMClient disabled (api_key missing)")
            return None
        masked_text, _mapping = _mask_glossary(text_ja or "")
        lines = "\n".join(f"- id={c['id']} | {c['when']} | {c['title']}" for c in candidates)
        prompt = (
            f"다음은 유메미타 멤버가 올린 X(트위터) 게시물 원문이다.\n\n{masked_text}\n\n"
            f"지금(KST)은 {now_kst} 이다. 이 멤버가 예고해 둔 방송 목록(KST):\n{lines}\n\n"
            f"질문: 이 글이 위 방송 중 일부 또는 전부를 취소하거나 일정을 변경한다고 알리는 글인가?\n"
            f"- 취소라면 action=\"del\". target_ids 에는 취소되는 방송의 id 만 넣는다.\n"
            f"  · 범위 표현이 없으면(예: \"오늘 방송 쉽니다\") 그 날짜(오늘/내일 등)의 방송을 모두 넣는다.\n"
            f"  · 범위가 있으면(아침/낮/밤, 시각, 방송 제목·내용) 그에 맞는 방송만 넣는다.\n"
            f"- 새 날짜/시각으로 변경(연기)이라면 action=\"edit\", when 에 KST 기준 새 일정을 "
            f"\"MM/DD HH:MM\" 형식으로 채우고 target_ids 에 변경되는 방송의 id 를 넣는다.\n"
            f"- 취소도 변경도 아니면(평소 예고·잡담·후기 등) 또는 목록의 어떤 방송인지 알 수 없으면 "
            f"action=\"none\", target_ids=[], when=null\n"
            f"target_ids 는 반드시 위 목록의 id 에서만 고른다.\n"
            f"reason 에는 그렇게 판정한 근거를 글의 어느 표현 때문인지 드러내 한국어 한 문장으로 쓴다"
            f"(action 이 none 일 때도 왜 취소·변경이 아니라고 봤는지 쓴다). JSON 포맷만 출력.\n\n출력:\n"
            f'{{"action": "del" 또는 "edit" 또는 "none", "target_ids": ["id", ...], "when": "MM/DD HH:MM" 또는 null, '
            f'"reason": "근거 한 문장"}}'
        )
        schema = {
            "name": "broadcast_change_targets",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["del", "edit", "none"]},
                    "target_ids": {"type": "array", "items": {"type": "string"}},
                    "when": {"type": ["string", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["action", "target_ids", "when", "reason"],
                "additionalProperties": False,
            },
        }
        for attempt in range(1, 6):
            prompt = _with_hint(prompt)   # (v4a) 재판단이면 「반려됐다」 힌트를 앞에 붙인다
            response = self._call_groq(self.model, prompt, json_schema=schema)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=schema)
            if not response:
                break   # (v4.6.1) 호출 실패(429 · 5xx · 네트워크)면 다시 묻지 않는다 — 다시 묻기는 답이 틀렸을 때만
            try:
                result = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"broadcast_change_targets: JSON 파싱 실패 (attempt {attempt}/5) — {response!r}")
                continue
            if (isinstance(result, dict) and result.get("action") in ("del", "edit", "none")
                    and isinstance(result.get("target_ids"), list)):
                return {"action": result["action"],
                        "target_ids": [str(x) for x in result["target_ids"]],
                        "when": result.get("when"),
                        "reason": str(result.get("reason") or "").strip()[:200]}
            logger.info(f"broadcast_change_targets: 예상 필드 부재 (attempt {attempt}/5) — {result!r}")
        logger.info("broadcast_change_targets: 호출 실패 또는 5회 모두 실패 — None (호출부 미반영 처리) — 호출부가 기록")
        return None

    def notice_timing(self, text: str, posted_jst: str) -> dict | None:
        """
        (v4.6.2) 소식 시점 판정 — 이 글이 **앞으로 / 지금 기간 중인 일을 알리는 글(announce)**인지, **이미 있었거나 지금 막 열리고 있는
        특정 일에 대한 감사 · 소감 · 현장 보고 · 회고(report)**인지 묻는다. 올릴지는 코드(`notices.timing_decision`)가 정한다 —
        report 이고 그 일의 날짜가 게시일보다 앞이면 안 올림, 게시일과 같으면 그날 자정까지, 소감에 붙은 다음 일정(next_lines)은 그 부분만 소식으로.
        2026-10-21 운영자 결정: 지난 행사의 소감은 소식으로 올리지 않는다 · 규칙(정규식)이 아니라 LLM 으로 판단한다.
        **근거 필수** — evidence · next_lines 는 원문에서 그대로 복사한 줄 목록. 비었거나 원문에 없으면 다시 묻는다(5회).
        Returns: {"kind": "announce"|"report", "subject": str, "subject_date": "YYYY-MM-DD"|None, "evidence": [...], "next_lines": [...],
                  "reason": str} — 5회 모두 실패하면 None(호출부가 올리고 실패 기록을 남긴다).
        """
        if self.disabled:
            return None
        base = _with_hint(
            "아래는 X(트위터) 글이다. 게시 시각: " + (posted_jst or "?") + " (일본 시간).\n"
            "이 글을 report 와 announce 중 하나로 판단하라. **아래 순서대로** 본다.\n"
            "1) report — 이미 있었거나 지금 막 열리고 있는 **특정 일**(라이브 · 방송 · 동시 시청 · 출연 · 이벤트 · 릴리즈 이벤트 · お渡し会 · 사인회 · 토크쇼 · 점검 등)에 대해 "
            "감사(「ありがとうございました」 「ご視聴ありがとう」 「ご来場ありがとう」 「ご参加ありがとう」) · 소감 · 현장 보고(「始まりました」 「スタートしました」) · "
            "종료 보고(「終了しました」 「終了いたしました」 「完了しました」)를 하는 글, 또는 과거를 돌아보는 회고(今日は何の日 · N年前). "
            "이런 감사 · 보고가 글의 첫머리 · 중심이면 아카이브 링크 · 다음 일정 홍보 · 보상 안내 · 해시태그가 붙어 있어도 report 다(붙은 앞으로의 일정은 next_lines 로).\n"
            "2) announce — 1)이 아닌 글. 앞으로 있을 일(행사 개최 · 발매 · 판매 · 접수 · 방송 · 출연 · 배포 예정), 지금 기간 중이라 팬이 찾아가거나 이용할 수 있는 것"
            "(판매 중 · 방영 중 · 게시 중 · 접수 중 · 배포 중 · 개최 중인 전시), 오늘 끝나는 접수 · 판매의 마감 안내(「本日受付終了」 — 아직 참여할 수 있다).\n"
            "subject = report 면 그 일의 이름(원문 표기), announce 면 알리는 것의 이름.\n"
            "subject_date = report 면 그 일이 열린 날짜(일본 시간 YYYY-MM-DD). 글에 날짜가 있으면 그 날짜, 本日 · 今日 · 今夜 · 本番 직후 인사면 게시일, "
            "昨日 · 昨夜면 게시일 전날, 회고면 그 옛날 날짜. 24시 이상 표기(25:00 등)는 다음 날로 환산한다(9月12日 25:00 = 9月13日 01:00 → 2026-09-13). "
            "알 수 없으면 null. announce 면 null.\n"
            "next_lines = report 글 안에 **다른 앞으로의 일정**(다음 회차 · 다음 행사 · 발매 · 수령 기한 등)을 알리는 줄이 있으면 그 줄들을 "
            "원문에서 한 줄씩 그대로 복사(날짜 · 장소 · 링크 줄 포함). 없거나 announce 면 [].\n"
            "evidence = 판단 근거가 된 구절들 — 글에서 한 줄씩 **그대로 복사**한다(바꾸거나 여러 줄을 이어 붙이지 말 것).\n"
            "reason = 판단 이유 한국어 한 문장.\nJSON 으로만 답하라.\n\n글:\n" + (text or ""))
        prompt = base
        for attempt in range(1, 6):
            response = self._call_groq(self.model, prompt, json_schema=_NOTICE_TIMING_SCHEMA)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=_NOTICE_TIMING_SCHEMA)
            if not response:
                break   # (v4.6.1) 호출 실패(429 · 5xx · 네트워크)면 다시 묻지 않는다 — 다시 묻기는 답이 틀렸을 때만
            try:
                r = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"notice_timing: JSON 파싱 실패 (attempt {attempt}/5) — {response!r}")
                continue
            if not isinstance(r, dict) or r.get("kind") not in ("announce", "report"):
                logger.info(f"notice_timing: 예상 필드 부재 (attempt {attempt}/5) — {r!r}")
                continue
            ev = [str(e).strip() for e in (r.get("evidence") or []) if str(e).strip()]
            nx = [str(e).strip() for e in (r.get("next_lines") or []) if str(e).strip()] if r["kind"] == "report" else []
            why = str(r.get("reason") or "").strip()
            sd = r.get("subject_date") if r["kind"] == "report" else None
            bad_date = sd is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(sd))
            if (not ev or len(why) < 5 or bad_date or not all(evidence_in_text(e, text or "") for e in ev)
                    or not all(evidence_in_text(e, text or "") for e in nx)):
                logger.info(f"notice_timing: 근거 없음 · 원문에 없는 구절 · 날짜 형식 — 다시 묻는다 (attempt {attempt}/5) — {r!r}")
                prompt = (base + "\n\n주의: 바로 전 답은 근거가 없거나 원문에 없는 구절을 들었거나 날짜 형식이 틀려 받지 않았다. "
                          "evidence · next_lines 의 각 구절은 위 글에 실제로 있는 한 줄을 그대로 복사하고, subject_date 는 YYYY-MM-DD 또는 null.")
                continue
            return {"kind": r["kind"], "subject": str(r.get("subject") or "").strip()[:80], "subject_date": sd,
                    "evidence": ev, "next_lines": nx, "reason": why[:200]}
        logger.info("notice_timing: 호출 실패 또는 5회 모두 실패(응답 · 근거) — None (호출부가 올리고 실패 기록)")
        return None

    def notice_categories(self, text: str) -> list[str] | None:
        """
        (v4.7.0) 소식 분류 — live(라이브공연) · event(오프라인행사) · goods(음원·굿즈) · broadcast(방송) 중 해당하는 것을 모두.
        프롬프트 = 분류 시험 4차 A 안(`_NOTICE_CAT_HEAD`, `NOTICE_CAT_PROMPT`). 빈 목록 = 해당 없음(호출부가 기타로).
        **근거 필수** — 분류를 골랐으면 evidence 가 하나 이상, 모두 원문에 있어야 한다. 아니면 다시 묻는다(3회).
        Returns: 분류 목록(NOTICE_LLM_CATS 순서) | None(호출 실패 · 3회 모두 근거 없음 — 호출부가 옛 분류로 둔다)
        """
        self.last_reason = ""
        if self.disabled:
            return None
        base = _with_hint(_NOTICE_CAT_HEAD + "\n글:\n" + (text or ""))
        prompt = base
        for attempt in range(1, 4):
            response = self._call_groq(self.model, prompt, json_schema=_NOTICE_CATS_SCHEMA)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=_NOTICE_CATS_SCHEMA)
            if not response:
                break   # 호출 실패(429 · 5xx · 네트워크)면 다시 묻지 않는다(v4.6.1)
            try:
                r = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"notice_categories: JSON 파싱 실패 (attempt {attempt}/3) — {response!r}")
                continue
            if not isinstance(r, dict) or not isinstance(r.get("cats"), list):
                logger.info(f"notice_categories: 예상 필드 부재 (attempt {attempt}/3) — {r!r}")
                continue
            cats = [c for c in NOTICE_LLM_CATS if c in r["cats"]]
            ev = [str(e).strip() for e in (r.get("evidence") or []) if str(e).strip()]
            why = str(r.get("reason") or "").strip()
            if len(why) < 5 or (cats and not ev) or not all(evidence_in_text(e, text or "") for e in ev):
                logger.info(f"notice_categories: 근거 없음 · 원문에 없는 구절 — 다시 묻는다 (attempt {attempt}/3) — {r!r}")
                prompt = (base + "\n\n주의: 바로 전 답은 근거가 없거나 원문에 없는 구절을 들어 받지 않았다. "
                          "분류를 골랐으면 evidence 에 위 글에 실제로 있는 줄을 그대로 복사하고, reason 에 판단 이유를 한 문장으로 적어라.")
                continue
            self.last_reason = why[:200] + (f" (근거: 「{ev[0][:60]}」)" if ev else "")
            return cats
        logger.info("notice_categories: 호출 실패 또는 3회 모두 실패(응답 · 근거) — None (호출부가 옛 분류로 둔다)")
        return None

    def live_info(self, text: str, posted_jst: str) -> dict | None:
        """
        (v4.7.0) 라이브공연 소식의 공연 이름 · 공연일 — 라이브공연 탭에서 같은 공연 소식을 한데 모으는 열쇠.
        name = 공연 타이틀을 원문 표기 그대로(「」 안쪽), date = 공연 당일(티켓 · 통판 날짜 아님).
        **근거 필수** — name · name_evidence · date_evidence 가 원문에 있어야 하고, date 의 월 · 일이 date_evidence 에 적혀 있어야 한다(3회).
        3회 모두 날짜 근거가 안 맞으면 날짜만 비우고 이름은 살린다.
        Returns: {"name": str|None, "date": "YYYY-MM-DD"|None, "reason": str} | None(호출 실패 · 이름 근거도 끝내 없음)
        """
        if self.disabled:
            return None
        posted_date = (posted_jst or "")[:10]
        base = _with_hint(
            "아래는 성우 밴드 「夢限大みゅーたいぷ」(유메미타) 소식 글이다. 게시 시각: " + (posted_jst or "?") + " (일본 시간).\n"
            "이 글이 다루는 공연(라이브)의 이름과 공연일을 뽑아라.\n"
            # (v4.7.1) 멤버 솔로 공연도 공연 — 120b 가 「○○ LIVE 2026 「タイトル」」 을 「유메미타 공연 타이틀이 아님」 으로 보고 이름을 비웠다(10-23 실측)
            "- name = 이 글이 다루는 공연의 고유 제목을 글에 적힌 표기 그대로. 유메미타 전체 공연뿐 아니라 **멤버 한 명의 솔로 공연** · 투어 · 프리 라이브 · "
            "여러 밴드가 서는 합동 공연도 모두 공연이다. 「」 · 『』 · “” 안에 든 공연 타이틀이 있으면 괄호를 뺀 안쪽만"
            "(예: 「DIMENSIONAL OVERLAP」 → DIMENSIONAL OVERLAP, ○○ LIVE 2026 「タイトル」 → タイトル). 괄호 타이틀이 없으면 공연 이름 그대로"
            "(예: NAKAMACHI ARALE LIVE 2026). 「BanG Dream! 13th LIVE」처럼 여러 밴드가 서는 공연 안에서 유메미타 공연의 타이틀이 따로 있으면 그 타이틀. "
            "해시태그 · 회장 이름 · 굿즈 이름은 공연 이름이 아니다. 공연을 가리키는 이름이 글에 전혀 없을 때만 \"\".\n"
            "- name_evidence = name 이 나온 원문 줄을 그대로 복사. name 이 \"\"면 \"\".\n"
            "- date = 공연이 열리는 날(일본 시간 YYYY-MM-DD). 티켓 판매 · 접수 · 통판 · 발표 날짜가 아니라 공연 당일. 여러 날이면 첫날. "
            "연도가 없으면 게시 시각 기준으로 정한다. 글에 공연일이 없으면 \"\".\n"
            "- date_evidence = 공연일이 적힌 원문 줄을 그대로 복사. date 가 \"\"면 \"\".\n"
            "- reason = 판단 이유 한국어 한 문장.\nJSON 으로만 답하라.\n\n글:\n" + (text or ""))
        prompt = base
        name_only = None
        for attempt in range(1, 4):
            response = self._call_groq(self.model, prompt, json_schema=_LIVE_INFO_SCHEMA)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=_LIVE_INFO_SCHEMA)
            if not response:
                break
            try:
                r = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"live_info: JSON 파싱 실패 (attempt {attempt}/3) — {response!r}")
                continue
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "").strip().strip("「」『』“”\"")
            nev, date, dev = (str(r.get(k) or "").strip() for k in ("name_evidence", "date", "date_evidence"))
            why = str(r.get("reason") or "").strip()
            name_ok = not name or (evidence_in_text(name, text or "") and evidence_in_text(nev, text or ""))
            date_ok = not date or (evidence_in_text(dev, text or "") and _md_in_evidence(date, dev, posted_date))
            if name_ok and date_ok and len(why) >= 5:
                return {"name": name or None, "date": date or None, "reason": why[:200]}
            if name_ok and name and len(why) >= 5:
                name_only = {"name": name, "date": None, "reason": why[:200]}
            logger.info(f"live_info: 근거 없음 · 원문에 없는 구절 · 날짜 근거 불일치 — 다시 묻는다 (attempt {attempt}/3) — {r!r}")
            prompt = (base + "\n\n주의: 바로 전 답은 이름 · 근거가 원문에 없거나, 공연일의 월 · 일이 date_evidence 에 적혀 있지 않아 받지 않았다. "
                      "원문에 있는 표기를 그대로 복사하고, 공연일이 적힌 줄이 없으면 date 는 \"\"로 둬라.")
        if name_only:
            logger.info("live_info: 날짜 근거가 끝내 안 맞아 이름만 — %s", name_only["name"])
        else:
            logger.info("live_info: 호출 실패 또는 3회 모두 실패 — None (공연 이름 없이 올림)")
        return name_only

    def duplicate_notice(self, new_text: str, candidates: list[dict]) -> str | None:
        """
        (v3.7) 신규 소식이 `candidates`(같은 날짜의 기존 소식들) 중 하나와 같은 행사를
        가리키는지 의미로 판정 — 문구가 달라도 같은 행사를 다른 말로 쓴 것이면 중복.

        threshold=0일: 호출부가 이미 "같은 date" 인 후보만 추려서 넘긴다 — 같은 이름의
        행사가 여러 날에 걸쳐 진행되는 경우(예: 3일 연속 페스티벌) 일차마다 별개 소식이라
        날짜가 다르면 애초에 후보에 안 들어온다. 제목 문자열 일치는 요구하지 않는다
        (요구하면 문구만 다른 진짜 중복을 못 잡음 — 애초에 이 게이트를 만든 이유).

        candidates: [{"id": str, "text": str}, ...] — text 는 원문(body_raw) 비교용.

        Returns:
            같은 행사로 판정된 후보의 id, 없거나 5회 모두 실패하면 None(신규로 등록 —
            정보 손실 방지가 우선인 안전한 기본값. 잘못 병합해 소식을 잃는 것보다
            중복이 잠깐 남는 쪽이 낫다).
        """
        if self.disabled or not candidates:
            return None

        ids = [c["id"] for c in candidates]
        masked_new, _m1 = _mask_glossary(new_text or "")
        cand_lines = "\n".join(
            f'- id="{c["id"]}": {_mask_glossary(c.get("text") or "")[0]}' for c in candidates
        )
        prompt = (
            "다음은 오늘 새로 들어온 소식 원문과, 같은 날짜에 이미 등록된 기존 소식 "
            "후보 목록이다. 새 소식이 후보 중 하나와 같은 행사(사건)를 가리키면 그 id를, "
            "아니면 null을 출력하라. 제목 문구가 다르더라도 같은 행사를 다른 말로 표현한 "
            "것이면 같은 것으로 본다. 이름이 같아도 명백히 다른 회차/일차의 행사라면 "
            "다른 것으로 본다. JSON 포맷만 출력.\n\n"
            f"새 소식:\n{masked_new}\n\n기존 후보:\n{cand_lines}\n\n출력:\n"
            '{"duplicate_of": <후보 id 문자열 또는 null>}'
        )
        schema = {
            "name": "duplicate_notice",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "duplicate_of": {"type": ["string", "null"], "enum": [*ids, None]},
                },
                "required": ["duplicate_of"],
                "additionalProperties": False,
            },
        }

        for attempt in range(1, 6):
            prompt = _with_hint(prompt)   # (v4a) 재판단이면 「반려됐다」 힌트를 앞에 붙인다
            response = self._call_groq(self.model, prompt, json_schema=schema)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=schema)
            if not response:
                break   # (v4.6.1) 호출 실패(429 · 5xx · 네트워크)면 다시 묻지 않는다 — 다시 묻기는 답이 틀렸을 때만
            try:
                result = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"duplicate_notice: JSON 파싱 실패 (attempt {attempt}/5) — {response!r}")
                continue
            if isinstance(result, dict) and "duplicate_of" in result:
                dup = result["duplicate_of"]
                return dup if dup in ids else None
            logger.info(f"duplicate_notice: 예상 필드 부재 (attempt {attempt}/5) — {result!r}")

        logger.warning("duplicate_notice: 호출 실패 또는 5회 모두 실패 — None (신규로 등록)")
        return None

    def banner_scope(self, text: str) -> dict | None:
        """
        (v4.5.10) 행사 판정 1단계 — 게임 계정(`bang_dream_on`) 글이 알리는 것이 **게임 앱 안의 일**인지 **게임 앱 밖의 일**인지만 묻는다.

        2026-10-21 운영자 확정 기준: 게임 밖 행사(타 기업 · 장소 콜라보 · 오프라인 행사 · 굿즈 등 유저 대상 일반 행사) = 소식,
        게임 안의 일 = 2단계(`banner_extract`)로 이벤트 · 가챠를 뽑아 코드가 배너를 정한다. 전엔 한 번의 판정에 「행사인가 · 무엇을 할까 ·
        소식인가」를 다 물어 같은 글에도 실행마다 답이 흔들렸고, 행사 정의를 좁히자 가챠 글이 엉뚱한 행사에 붙었다(ref/v4.5.9).

        **근거 필수**(v4.5.5 와 같은 방식) — evidence = 원문에서 그대로 복사한 구절 목록. 비었거나 원문에 없는 구절이 있으면 다시 묻는다.
        구절 하나로 받으면 떨어진 두 줄을 이어 붙여 「원문에 없음」으로 계속 실패했다(실측 JR 콜라보 글 3/3) — 그래서 목록.

        Returns: {"scope": "in_game"|"outside", "evidence": [구절…], "reason": str} — 5회 모두 실패하면 None(호출부가 올리지 않음).
        """
        if self.disabled:
            return None
        base = _with_hint(
            "게임 「BanG Dream! Our Notes(バンドリ！ アワーノーツ)」 공식 계정 글이다. "
            "이 글이 알리는 것이 **게임 앱 안에서 하는 일**인지 **게임 앱 밖의 일**인지만 판단하라.\n"
            "- in_game: 플레이어가 게임 앱 안에서 하는 것 — 이벤트 · 이벤트 스토리 · 가챠 · 미션 · 로그인 보너스 · 보상 · 곡 추가 · 업데이트 · 점검. "
            "영화 · 라이브 등을 기념하는 것이라도 게임 안에서 하는 것이면 in_game.\n"
            "- outside: 게임 앱 밖에서 하는 것 — 타 기업 · 장소와의 콜라보(카페 · 철도 · 매장), 오프라인 행사 · 토크쇼 · 사인회 · 전시, "
            "굿즈 · 음반 · 특전, 광고 게재, 방송 · 영상 공개, 생방송 프로그램.\n"
            "evidence = 판단 근거가 된 구절들 — 글에서 한 줄씩 **그대로 복사**한다(바꾸거나 여러 줄을 이어 붙이지 말 것). "
            "reason = 판단 이유 한국어 한 문장.\nJSON 으로만 답하라.\n\n글:\n" + (text or ""))
        prompt = base
        for attempt in range(1, 6):
            response = self._call_groq(self.model, prompt, json_schema=_BANNER_SCOPE_SCHEMA)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=_BANNER_SCOPE_SCHEMA)
            if not response:
                break   # (v4.6.1) 호출 실패(429 · 5xx · 네트워크)면 다시 묻지 않는다 — 다시 묻기는 답이 틀렸을 때만
            try:
                r = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"banner_scope: JSON 파싱 실패 (attempt {attempt}/5) — {response!r}")
                continue
            if not isinstance(r, dict) or r.get("scope") not in ("in_game", "outside"):
                logger.info(f"banner_scope: 예상 필드 부재 (attempt {attempt}/5) — {r!r}")
                continue
            ev = [str(e).strip() for e in (r.get("evidence") or []) if str(e).strip()]
            why = str(r.get("reason") or "").strip()
            if not ev or len(why) < 5 or not all(evidence_in_text(e, text or "") for e in ev):
                logger.info(f"banner_scope: 근거 없음 · 원문에 없는 근거 — 다시 묻는다 (attempt {attempt}/5) — {r!r}")
                prompt = (base + "\n\n주의: 바로 전 답은 근거가 없거나 원문에 없는 구절을 근거로 들어 받지 않았다. "
                          "evidence 의 각 구절은 위 글에 실제로 있는 한 줄을 그대로 복사하라.")
                continue
            return {"scope": r["scope"], "evidence": ev, "reason": why[:200]}
        logger.info("banner_scope: 호출 실패 또는 5회 모두 실패(응답 · 근거) — None (올리지 않음) — 호출부가 기록")
        return None

    def banner_extract(self, text: str, posted_jst: str, images_ocr: list[dict] | None = None) -> dict | None:
        """
        (v4.5.10) 행사 판정 2단계 — 게임 안의 일을 알리는 글에서 **인게임 이벤트**와 **가챠**만 적힌 그대로 뽑는다(판단은 코드 — `banners.plan_post`).

        인게임 이벤트 = 게임 속 인물들의 스토리가 있는 이벤트(챌린지 라이브 등). 미션 · 로그인 보너스 · 캠페인 · 시리얼 코드는 뽑지 않는다(버림 —
        2026-10-21 운영자 결정: 이 앱은 유메미타 활동 소식이 목적이라 게임 잡소식을 채우지 않는다).
        **본문이 정본**, 이미지 글자(`images_ocr`, 비전 OCR)는 본문에 없는 정보(주로 개최기간)를 채우는 보조(2026-10-21 운영자 지시).
        제목 · 기간 근거가 본문 · 이미지 글자에 없으면 다시 묻는다. 제목은 본문 표기로 맞추고(`_banner_title`) 「…」 안쪽만 남긴다.

        Returns:
            {"items": [{"kind": "event"|"gacha", "status": "normal"|"postponed"|"cancelled", "title_ja", "title_ko",
                        "start_jst", "end_jst", "period_evidence"} …],     # 날짜는 "YYYY-MM-DD HH:MM" | "YYYY-MM-DD" | None
                        # 날짜는 자기 근거 구절(start/end_evidence)에 적혀 있을 때만 남는다(`_jst_in_evidence`, 3회 다시 묻고도 안 되면 그 날짜만 비움).
                        # event 는 제목 근처에 「イベント」가 있을 때만(`_near_event_word`) — 공연 · 영화 이름 거르기.
             "image_roles": [event|gacha|none …] (이미지 수와 같을 때만, 아니면 []), "reason": str}
            5회 모두 실패하면 None.
        """
        if self.disabled:
            return None
        ocr = [o for o in (images_ocr or []) if isinstance(o, dict)]
        n_img = len(ocr)
        ocr_txt = "".join(f"\n이미지 글자 {o.get('idx')}:\n{(o.get('text') or '(글자 없음)').strip()}\n" for o in ocr)
        full = (text or "") + "\n" + ocr_txt
        rules = [
            "게임 공식 계정 글(본문)과 첨부 이미지에서 읽은 글자(이미지 글자)다. 이 글이 알리는 **인게임 이벤트**와 **가챠**만 **적힌 그대로** 뽑아라. "
            "판단하지 말고 옮겨 적기만 한다.",
            "- event = 게임 속 인물들의 스토리가 있는 인게임 이벤트(예: チャレンジライブイベント「…」, ○○初イベント「…」予告). "
            "gacha = 「…ガチャ」 또는 ガチャ「…」.",
            "- 미션 · 미션패스 · 로그인 보너스 · 기념 캠페인 · 시리얼 코드 · 곡 추가 · 보상 소개 자체는 뽑지 않는다"
            "(이벤트 · 가챠 이름이 함께 적혀 있으면 그 이벤트 · 가챠는 뽑는다). 뽑을 것이 없으면 items 는 빈 배열.",
            "- **본문이 정본이다.** 이미지 글자는 본문에 없는 정보(주로 개최기간)를 채우는 보조다. 같은 정보가 둘 다 있으면 본문의 표기 · 값을 쓴다. "
            "이미지 글자는 판독 오류가 있을 수 있다.",
            "- title_ja: 「」 안에 적힌 이름만 그대로(앞뒤의 「チャレンジライブイベント」 같은 꾸밈말 · 이모지 제외) — 본문에 있으면 본문 표기. "
            "이름이 적혀 있지 않으면 그 항목은 뽑지 않는다. title_ko: 자연스러운 한국어 번역.",
            "- status: 보통 normal. 개최가 보류 · 연기되어 새 날짜가 없다 → postponed. 취소 · 조기 종료 → cancelled.",
            "- start_jst / end_jst: \"YYYY-MM-DD HH:MM\"(시각을 모르면 \"YYYY-MM-DD\"). 연도가 없으면 게시일 기준. "
            "「明日15:00」 같은 상대 표현은 게시 시각 기준으로 계산. 「~10月8日(木)20:59まで」의 종료는 그 날짜 20:59. "
            "**본문 · 이미지 글자에 적혀 있지 않은 날짜는 null.** 다른 항목의 기간을 빌려 쓰지 말 것.",
            "- start_evidence / end_evidence: **그 항목의** 시작 · 종료 날짜(와 시각)가 적힌 구절을 본문(없으면 이미지 글자)에서 그대로 복사(날짜가 null 이면 빈 문자열). "
            "이벤트와 가챠의 기간이 따로 적혀 있으면 각자 자기 구절을 쓴다(가챠 기간은 가챠 소개 쪽).",
            "- 실제 공연(○th☆LIVE 등) · 영화 · 방송의 이름은 event 가 아니다.",
        ]
        if n_img:
            rules.append(f"- image_roles: 이미지 {n_img}장 각각의 용도를 순서대로 {n_img}개. **이벤트 키비주얼 그 자체**(로고 · 일러스트 · 개최기간 · 저작권 표기만 있는 "
                         "온전한 그림)만 event. 「初回イベント情報」 「ガチャ紹介」 「あらすじ紹介」 처럼 제목 막대와 설명문이 붙은 소개 카드 · 방송 캡처 · "
                         "멤버 소개 · 보상 소개는 none, 가챠 이미지는 gacha.")
        else:
            rules.append("- image_roles 는 빈 배열 [].")
        rules += ["- reason: 무엇을 뽑았는지(또는 왜 없는지) 한국어 한 문장.", "JSON 으로만 답하라."]
        base = _with_hint("\n".join(rules) + f"\n\n게시 시각(JST): {posted_jst}\n본문:\n{text or ''}\n{ocr_txt}")
        prompt = base
        for attempt in range(1, 6):
            response = self._call_groq(self.model, prompt, json_schema=_BANNER_EXTRACT_SCHEMA)
            if not response:
                response = self._call_groq(self.fallback, prompt, json_schema=_BANNER_EXTRACT_SCHEMA)
            if not response:
                break   # (v4.6.1) 호출 실패(429 · 5xx · 네트워크)면 다시 묻지 않는다 — 다시 묻기는 답이 틀렸을 때만
            try:
                r = json.loads(_strip_json_fence(response))
            except json.JSONDecodeError:
                logger.info(f"banner_extract: JSON 파싱 실패 (attempt {attempt}/5) — {response!r}")
                continue
            if not isinstance(r, dict) or not isinstance(r.get("items"), list):
                logger.info(f"banner_extract: 예상 필드 부재 (attempt {attempt}/5) — {r!r}")
                continue
            items, bad, dropped = [], None, []
            for it in r["items"]:
                if not isinstance(it, dict) or it.get("kind") not in ("event", "gacha"):
                    bad = f"항목 형식 {it!r}"[:80]
                    break
                title = _banner_title(str(it.get("title_ja") or ""), text or "")
                if not evidence_in_text(title, full):
                    bad = f"제목 「{title[:20]}」 원문에 없음"
                    break
                if it["kind"] == "event" and not _near_event_word(title, full):
                    dropped.append(title)          # 공연 · 영화 이름 — 다시 묻지 않고 뺀다
                    continue
                dates = {}
                for side in ("start", "end"):
                    v = (str(it.get(f"{side}_jst") or "").strip() or None)
                    ev = str(it.get(f"{side}_evidence") or "").strip()
                    if v and not (ev and evidence_in_text(ev, full) and _jst_in_evidence(v, ev, posted_jst)):
                        if attempt <= 3:
                            bad = f"「{title[:20]}」 {'시작' if side == 'start' else '종료'} {v} 가 근거 구절 「{ev[:30]}」 에 없음"
                            break
                        v = None                   # 끝까지 근거가 없으면 그 날짜만 비운다(지어낸 날짜보다 빈 날짜가 낫다)
                    dates[side] = (v, ev if v else "")
                if bad:
                    break
                items.append({"kind": it["kind"], "status": it.get("status") if it.get("status") in ("normal", "postponed", "cancelled") else "normal",
                              "title_ja": title, "title_ko": (str(it.get("title_ko") or "").strip() or None),
                              "start_jst": dates["start"][0], "end_jst": dates["end"][0],
                              "period_evidence": " / ".join(x for x in (dates["start"][1], dates["end"][1]) if x)})
            if bad:
                logger.info(f"banner_extract: {bad} — 다시 묻는다 (attempt {attempt}/5)")
                prompt = (base + f"\n\n주의: 바로 전 답은 받지 않았다({bad}). 제목 · start_evidence · end_evidence 는 위 본문 · 이미지 글자에 실제로 있는 글자를 "
                          "그대로 복사하고, 날짜는 그 구절에 적힌 것만 써라(다른 항목의 기간을 빌려 쓰지 말 것).")
                continue
            roles = [x if x in ("event", "gacha", "none") else "none" for x in (r.get("image_roles") or [])]
            why = str(r.get("reason") or "").strip()
            if dropped:
                why += f" (이벤트 표지 없음 — 뺌: {', '.join(dropped)[:60]})"
            return {"items": items, "image_roles": roles if n_img and len(roles) == n_img else [], "reason": why[:200]}
        logger.info("banner_extract: 호출 실패 또는 5회 모두 실패 — None (올리지 않음) — 호출부가 기록")
        return None

    def translate(self, text_ja: str) -> str | None:
        """
        일본어 트윗을 한국어로 번역.

        (버그리포트 20260913 #3) "もぐもぐもぐ…"(의성어 8회+ 연속반복) 같은 입력은
        LLM 이 반복 루프에 빠져 수백~수천자를 토해내고, 환각 가드에 매번 걸려
        temperature=0 이라 재시도해도 항상 같은 실패를 반복한다. 반복 구간을 미리
        압축해 단위만 번역시키고 다시 펼치면 이 루프를 원천 회피한다.

        Args:
            text_ja: 일본어 텍스트

        Returns:
            한국어 번역 또는 실패 시 None
        """
        if self.disabled:
            logger.warning("LLMClient disabled (api_key missing)")
            return None

        text_ja = _widen_halfwidth_kana(text_ja or "")
        text_ja = _normalize_stretch(text_ja)
        text_ja, punct_runs = _collapse_punct_runs(text_ja)
        text_ja, kana_counts = _fold_kana_runs(text_ja)
        m = _REPEAT_RE.match(text_ja)
        if m:
            out = self._translate_repeated(text_ja, m)
        else:
            out = self._translate_once(text_ja)
        if not out:
            return out
        if kana_counts:
            out = _jamo_runs_to_tilde(out, kana_counts)
        return _restore_punct_runs(out, punct_runs)

    def _translate_repeated(self, text_ja: str, m: "re.Match[str]") -> str | None:
        """짧은 단위(1~6자)가 8회 이상 연속 반복되는 구간을 압축 번역 후 재조립."""
        unit = m.group(1)
        count = len(m.group(0)) // len(unit)
        remainder = text_ja[m.end():]

        unit_ko = self._translate_repeat_unit(unit, count)
        if unit_ko is None:
            return None

        rest_ko = ""
        if remainder.strip():
            rest_ko = self._translate_once(remainder)
            if rest_ko is None:
                rest_ko = remainder.strip()  # 나머지 번역 실패해도 통째 실패시키지 않음
            if remainder.startswith("\n") and not rest_ko.startswith("\n"):
                rest_ko = "\n" + rest_ko

        logger.info(
            "translate: 반복 압축 (unit=%r x%d, remainder_len=%d)",
            unit, count, len(remainder),
        )
        return (unit_ko * count) + rest_ko

    def _translate_repeat_unit(self, unit: str, count: int) -> str | None:
        """반복 단위 하나만 번역. 단위를 맨입으로 넘기면 문맥이 없어 오역되기 쉬워서
        ("もぐ" 단독 → "몰입" 오역, "もぐ"×40 문맥 제공 시 "우걱"으로 정확히 번역됨 —
        실측 확인) 반복 횟수·의성어/의태어 문맥을 프롬프트에 명시한다."""
        prompt = (
            f"다음은 일본어 트윗에서 '{unit}'가 {count}번 연속 반복되는 의성어/의태어다. "
            f"자연스러운 한국어 의성어/의태어를 딱 한 번만 출력하라(설명·반복 금지).\n\n"
            f"일본어 반복 단위: {unit}"
        )
        response = self._call_groq(self.model, prompt)
        if not response:
            response = self._call_groq(self.fallback, prompt)
        if not response:
            return None
        if self._is_hallucination(response, unit):
            return None
        return response.strip()

    def _translate_once(self, text_ja: str) -> str | None:
        """단발 번역 호출(메인→폴백 모델) + 환각 가드. 반복 압축 없이 그대로 1회 요청."""
        masked_text, mapping = _mask_glossary(text_ja)
        prompt = _translate_prompt(masked_text)

        response = self._call_groq(self.model, prompt)
        main_err, used_fallback = self._last_err, False
        if not response:
            used_fallback = True
            response = self._call_groq(self.fallback, prompt)

        if not response:
            _fail_log("translate: 메인·폴백 모델 모두 실패 → 번역 없음 (원인: %s / %s)", main_err, self._last_err)
            return None

        # 환각 가드
        if self._is_hallucination(response, masked_text):
            _fail_log("translate: 환각 가드 발동 → 번역 없음 (input=%d, output=%d)", len(text_ja), len(response))
            return None

        if used_fallback:   # 정의된 폴백(보조 모델)으로 수행됨 — WARN 1건
            logger.warning("translate: 메인 모델 실패(%s) → 폴백 모델로 수행", main_err)
        result = _clean_translation(_unmask_glossary(response.strip(), mapping, to="ko"))

        # 부분 번역 감시 — 성공 응답이라 다른 로그가 없으므로 여기서 WARN 으로 남긴다(저장은 그대로 한다).
        left = _residual_kana(result)
        if left:
            retry = self._retranslate_residual(masked_text, prompt, result, left, mapping)   # (v4.5.7) 남은 글자를 짚어 1회 재요청
            if retry is not None:
                result, left = retry, _residual_kana(retry)
        if left:
            logger.warning(
                "translate: 부분 번역 의심 — 번역문에 일본어 가나 %d자 잔존 %r (input=%d자, 번역=%r)",
                len(left), "".join(left)[:20], len(text_ja), result[:80],
            )
        return result

    def _retranslate_residual(self, masked_text: str, prompt: str, prev: str, left: "list[str]", mapping) -> "str | None":
        """부분 번역(가나 잔존) 1회 재요청. 이전 번역과 남은 글자를 알려 주고 전체를 다시 받는다.
        재요청이 실패 · 환각이거나 가나가 줄지 않으면 None(= 이전 결과 유지)."""
        again = (
            f"{prompt}\n\n이전 번역에 일본어 글자({''.join(dict.fromkeys(left))})가 남아 있다. "
            f"남은 부분을 한국어로 번역하거나 한국어 독음으로 적어, 번역문 전체를 다시 출력하라(설명 금지).\n이전 번역: {prev}"
        )
        response = self._call_groq(self.model, again) or self._call_groq(self.fallback, again)
        if not response or self._is_hallucination(response, masked_text):
            return None
        retry = _clean_translation(_unmask_glossary(response.strip(), mapping, to="ko"))
        if len(_residual_kana(retry)) >= len(left):
            return None
        logger.info("translate: 가나 잔존 %d자 → 재요청으로 %d자", len(left), len(_residual_kana(retry)))
        return retry

    def _call_groq(
        self, model: str, prompt: str, *, json_schema: "dict | None" = None
    ) -> str | None:
        """
        Groq API 호출 (지수 백오프 3회).

        Args:
            model: 사용할 모델 이름
            prompt: 프롬프트

        Returns:
            응답 텍스트 또는 실패 시 None
        """
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "reasoning_effort": "low",
            # 반복 루프 방어 2중선(1중선은 translate() 의 _normalize_stretch/_REPEAT_RE
            # 전처리) — 미지 패턴이 전처리를 뚫고 들어와도 폭주를 API 단에서 조기 절단.
            # 하한 500 (구 200) — reasoning_effort="low" 도 내부 추론에 토큰을 쓰는데,
            # 프롬프트가 짧으면 하한이 낮아 추론만으로 예산을 다 써 content가 빈 문자열로
            # 돌아오는 사례 실측(버그리포트 20260916 #2, in=155/out='' 4회 재현·모두 동일
            # 입력에서 결정적으로 실패 — temperature=0 이라 재시도해도 같은 결과).
            "max_tokens": max(500, len(prompt) // 2),
        }
        # 구조화 출력이 필요한 호출(notice_title)만 json_schema strict 를 붙인다.
        # translate 는 자유텍스트라 안 붙임(json_object 는 gpt-oss 가 거부하므로 안 씀).
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": json_schema,
            }

        # (v4.6.1) 429 로 막혀 있는 모델이면 보내지 않는다(위 _RATE_BLOCK)
        blk = _blocked(model)
        if blk:
            self._last_err = f"Groq {'일일' if blk['kind'] == 'daily' else '분당'} 한도로 호출 멈춤 중 ({int(blk['until'] - time.time())}초 남음)"
            logger.info("Groq: %s — %s 요청 안 보냄", self._last_err, model)
            return None

        # ponytail: 지수 백오프 3회 (1s/2s/4s) — 5xx · 타임아웃만. 429 는 다시 보내지 않는다(v4.6.1)
        delays = [1.0, 2.0, 4.0]

        for attempt, delay in enumerate(delays):
            try:
                # ponytail: requests.post의 json 인자와 호환, 테스트 mock도 지원
                _t0 = time.monotonic()
                resp = self.session.post(
                    url, json=payload, headers=headers, timeout=self.timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["message"]["content"]
                        # 번역 품질 사후 검토용 — 모델·지연·입출력 미리보기를 남긴다.
                        logger.info(
                            "Groq ok model=%s %.1fs in=%d out=%r",
                            model, time.monotonic() - _t0, len(prompt),
                            (content or "")[:160],
                        )
                        return content
                    self._last_err = "응답 구조 없음"
                    logger.info(f"Groq: 예상 응답 구조 없음 {data}")
                    return None
                elif resp.status_code == 429:
                    body = getattr(resp, "text", "") or ""
                    daily = bool(re.search(r"per day|\(TPD\)|\(RPD\)", body))
                    if daily:
                        kind, sec = "daily", float(DAILY_BLOCK_SEC)
                    else:
                        kind, sec = "minute", min(max(_retry_after_sec(resp) or MINUTE_BLOCK_DEFAULT_SEC, 1.0), MINUTE_BLOCK_MAX_SEC)
                    _block_model(model, kind, sec, body)
                    self._last_err = f"HTTP 429 {'일일' if daily else '분당'} 한도"
                    logger.warning("Groq 429 (%s 한도) — %s 를 %d초 동안 부르지 않음: %s",
                                   "일일" if daily else "분당", model, int(sec), body[:200])
                    return None
                elif resp.status_code in (500, 502, 503, 504):
                    if attempt < len(delays) - 1:
                        logger.info(
                            f"Groq {resp.status_code}: {delay}초 후 재시도 (attempt {attempt+1}/3)"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        self._last_err = f"HTTP {resp.status_code} 백오프 소진"
                        logger.info(
                            f"Groq {resp.status_code}: 백오프 소진 ({attempt+1}/3)"
                        )
                        return None
                else:
                    self._last_err = f"HTTP {resp.status_code}"
                    logger.info(
                        f"Groq {resp.status_code}: {resp.text[:200]}"
                    )
                    return None
            except requests.Timeout:
                if attempt < len(delays) - 1:   # 재시도 중 — 정상 경로의 일부 (INFO). 소진되면 WARN
                    logger.info(f"Groq: 타임아웃 (attempt {attempt+1}/3) — 재시도")
                    time.sleep(delay)
                    continue
                self._last_err = "타임아웃 재시도 소진"
                logger.info("Groq: 타임아웃 — 재시도 소진 (3/3)")
                return None
            except requests.RequestException as e:
                self._last_err = f"네트워크 오류 {type(e).__name__}"
                logger.info(f"Groq: 네트워크 오류 — {e}")
                return None

        return None

    def _is_hallucination(self, response: str, input_text: str) -> bool:
        """
        환각 가드: 출력이 비었거나 입력의 3배 초과 길이.

        Args:
            response: 모델 응답
            input_text: 입력 텍스트

        Returns:
            환각 의심이면 True
        """
        if not response or not response.strip():
            return True
        if len(response) > len(input_text) * 3:
            return True
        return False


if __name__ == "__main__":
    import sys

    # Windows UTF-8 콘솔 가드
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 70)
    print("LLM llm.py 스모크 테스트")
    print("=" * 70)

    # ──── 시나리오 1: disabled 상태 (api_key 없음) ────
    print("\n[시나리오 1] disabled 상태 (api_key 없음)")
    print("-" * 70)

    llm_disabled = LLMClient("")
    assert llm_disabled.disabled is True
    result = llm_disabled.notice_title("test body")
    assert result is None, "disabled 상태에서 None 반환해야 함"
    result = llm_disabled.translate("test text")
    assert result is None, "disabled 상태에서 None 반환해야 함"
    print("✓ disabled 상태: notice_title/translate 모두 None 반환")

    # ──── 시나리오 2: 200 정상 응답 (notice_title) ────
    print("\n[시나리오 2] 200 정상 응답 (notice_title)")
    print("-" * 70)

    class FakeSession:
        def __init__(self, status_code=200, body=None):
            self.status_code = status_code
            self.body = body or {}

        def post(self, url, **kwargs):
            class FakeResp:
                pass

            resp = FakeResp()
            resp.status_code = self.status_code
            resp.text = json.dumps(self.body) if isinstance(self.body, dict) else str(self.body)

            def json_method():
                return self.body

            def raise_for_status():
                pass

            resp.json = json_method
            resp.raise_for_status = raise_for_status
            return resp

    session_200 = FakeSession(
        status_code=200,
        body={
            "choices": [
                {
                    "message": {
                        "content": '{"title_ja": "新年イベント", "title_ko": "신정 이벤트"}'
                    }
                }
            ]
        },
    )

    llm_200 = LLMClient("test-key", session=session_200)
    # 입력을 충분히 길게 해서 환각 가드를 통과하도록 (응답 44자 * 3 = 132자 필요)
    long_input = "뭔가 이벤트 소식이 있는데요. " * 10  # 충분히 긴 입력
    result = llm_200.notice_title(long_input)
    assert result is not None, "200 응답에서 None이 아닌 값 기대"
    assert result.get("title_ja") == "新年イベント"
    assert result.get("title_ko") == "신정 이벤트"
    print("✓ 정상 응답 파싱: title_ja/title_ko 추출됨")

    # ──── 시나리오 3: (v4.6.1) 429 → 다시 보내지 않고 그 모델을 한동안 막음 ────
    print("\n[시나리오 3] 429 → 재시도 없음 · 모델별 차단 · 판정 다시 묻기 중단")
    print("-" * 70)

    class Fake429Session:
        """모델별로 응답을 정한다 — {model: (status, body, headers)}. 보낸 요청 수를 모델별로 센다."""
        def __init__(self, plan):
            self.plan, self.sent = plan, {}

        def post(self, url, **kwargs):
            model = kwargs["json"]["model"]
            self.sent[model] = self.sent.get(model, 0) + 1
            status, body, hdr = self.plan[model]

            class FakeResp:
                pass
            resp = FakeResp()
            resp.status_code, resp.headers = status, hdr
            resp.text = body if isinstance(body, str) else json.dumps(body)
            resp.json = lambda: body
            return resp

    _ok = lambda c: {"choices": [{"message": {"content": c}}]}
    _RPM = ("Rate limit reached for model `x` in organization `o` service tier `on_demand` on requests per minute (RPM): "
            "Limit 30, Used 30, Requested 1. Please try again in 7.5s.")
    _TPD = ("Rate limit reached for model `x` on tokens per day (TPD): Limit 200000, Used 199990, Requested 900. "
            "Please try again in 6m12.3s.")

    # 분당 429 — 1번만 보내고 retry-after 만큼 막는다. 막힌 동안은 요청을 안 보낸다
    _RATE_BLOCK.clear()
    s3 = Fake429Session({DEFAULT_MODEL: (429, _RPM, {"retry-after": "8"}), FALLBACK_MODEL: (200, _ok("폴백 응답"), {})})
    c3 = LLMClient("test-key", session=s3)
    _t = time.monotonic()
    assert c3._call_groq(DEFAULT_MODEL, "test") is None and s3.sent[DEFAULT_MODEL] == 1, s3.sent
    assert time.monotonic() - _t < 0.5, "429 에 sleep 하지 않는다"
    assert _blocked(DEFAULT_MODEL)["kind"] == "minute" and 7 < _RATE_BLOCK[DEFAULT_MODEL]["until"] - time.time() <= 8.1
    assert c3._call_groq(DEFAULT_MODEL, "test") is None and s3.sent[DEFAULT_MODEL] == 1, "막힌 동안은 안 보냄"
    assert "멈춤 중" in c3._last_err, c3._last_err
    assert c3._call_groq(FALLBACK_MODEL, "test") == "폴백 응답", "폴백 모델은 따로 — 한 번 불러 본다"
    assert set(rate_block_state()) == {DEFAULT_MODEL}
    print("✓ 분당 429: 요청 1회 · sleep 없음 · retry-after 동안 차단 · 폴백은 별도")

    # 일일 429 — 1시간 차단(본문의 「6m12s」 보다 길게 — 일일 한도는 몇 분 뒤에도 거의 안 풀린다)
    _RATE_BLOCK.clear()
    s3d = Fake429Session({DEFAULT_MODEL: (429, _TPD, {}), FALLBACK_MODEL: (429, _TPD, {})})
    c3d = LLMClient("test-key", session=s3d)
    assert c3d._call_groq(DEFAULT_MODEL, "test") is None
    b3 = _blocked(DEFAULT_MODEL)
    assert b3["kind"] == "daily" and b3["until"] - time.time() > DAILY_BLOCK_SEC - 5, b3
    print("✓ 일일 429(TPD): 1시간 차단")

    # 판정 함수 — 두 모델 다 429 면 다시 묻지 않고 바로 None. 요청은 모델마다 1번(전엔 최대 30번)
    _RATE_BLOCK.clear()
    s3j = Fake429Session({DEFAULT_MODEL: (429, _RPM, {}), FALLBACK_MODEL: (429, _RPM, {})})
    assert LLMClient("test-key", session=s3j).participation("원문", member_name="노노카") is None
    assert s3j.sent == {DEFAULT_MODEL: 1, FALLBACK_MODEL: 1}, s3j.sent
    assert _blocked(DEFAULT_MODEL)["until"] - time.time() <= MINUTE_BLOCK_DEFAULT_SEC + 1, "대기 시간이 없으면 60초"
    # 막힌 동안 다른 판정 · 번역은 요청을 하나도 안 보낸다
    assert LLMClient("test-key", session=s3j).banner_scope("글") is None
    assert LLMClient("test-key", session=s3j).translate("こんにちは") is None
    assert s3j.sent == {DEFAULT_MODEL: 1, FALLBACK_MODEL: 1}, s3j.sent
    print("✓ 판정: 두 모델 429 → 요청 2회로 끝 · 막힌 동안 다른 판정 · 번역 요청 0회")

    # 차단이 풀리면 다시 보낸다
    _RATE_BLOCK[DEFAULT_MODEL]["until"] = time.time() - 1
    s3j.plan[DEFAULT_MODEL] = (200, _ok('{"participates": true}'), {})
    assert LLMClient("test-key", session=s3j).participation("원문", member_name="노노카") is True
    print("✓ 차단 시간이 지나면 다시 호출")

    # 대기 시간 읽기
    class _R:
        def __init__(self, text, headers=None):
            self.text, self.headers = text, headers or {}
    assert _retry_after_sec(_R("", {"retry-after": "12"})) == 12.0
    assert abs(_retry_after_sec(_R("Please try again in 2m59.5s.")) - 179.5) < 1e-6
    assert abs(_retry_after_sec(_R("Please try again in 500ms")) - 0.5) < 1e-6
    assert _retry_after_sec(_R("Rate limited")) is None
    print("✓ 대기 시간: retry-after 헤더 · 「try again in …」(분 · 초 · ms)")

    # 5xx 는 전처럼 백오프 재시도(한도와 무관) — 다만 sleep 은 테스트에서 빼고 센다
    _RATE_BLOCK.clear()
    _saved_sleep, time.sleep = time.sleep, (lambda s: None)
    try:
        s5 = Fake429Session({DEFAULT_MODEL: (503, "busy", {})})
        assert LLMClient("test-key", session=s5)._call_groq(DEFAULT_MODEL, "test") is None and s5.sent[DEFAULT_MODEL] == 3
        assert not _blocked(DEFAULT_MODEL), "5xx 는 차단하지 않음"
    finally:
        time.sleep = _saved_sleep
    print("✓ 5xx: 백오프 3회(차단 없음)")
    _RATE_BLOCK.clear()

    # ──── 시나리오 4: JSON 파싱 실패 ────
    print("\n[시나리오 4] JSON 파싱 실패")
    print("-" * 70)

    session_bad_json = FakeSession(
        status_code=200,
        body={"choices": [{"message": {"content": "not valid json {"}}]},
    )

    llm_bad = LLMClient("test-key", session=session_bad_json)
    result = llm_bad.notice_title("test body")
    assert result is None, "JSON 파싱 실패 시 None 기대"
    print("✓ JSON 파싱 실패 → None 반환")

    # ──── 시나리오 5: 환각 가드 (과길이) ────
    print("\n[시나리오 5] 환각 가드 (과길이)")
    print("-" * 70)

    short_input = "short"
    long_output = "x" * (len(short_input) * 4)  # 입력의 4배

    session_hallucination = FakeSession(
        status_code=200,
        body={
            "choices": [{"message": {"content": long_output}}]
        },
    )

    llm_hallu = LLMClient("test-key", session=session_hallucination)
    result = llm_hallu.notice_title(short_input)
    assert result is None, "환각 가드(과길이) 발동 시 None 기대"
    print("✓ 환각 가드(과길이) 발동 → None 반환")

    # ──── 시나리오 6: translate 정상 작동 ────
    print("\n[시나리오 6] translate 정상 작동")
    print("-" * 70)

    session_translate = FakeSession(
        status_code=200,
        body={
            "choices": [
                {
                    "message": {
                        "content": "안녕하세요, 새로운 배경음악입니다."
                    }
                }
            ]
        },
    )

    llm_tl = LLMClient("test-key", session=session_translate)
    result = llm_tl.translate("こんにちは、新しいBGMです。")
    assert result == "안녕하세요, 새로운 배경음악입니다."
    print("✓ translate 정상 작동")

    # ──── 시나리오 7: 환각 가드 (빈 응답) ────
    print("\n[시나리오 7] 환각 가드 (빈 응답)")
    print("-" * 70)

    session_empty = FakeSession(
        status_code=200,
        body={"choices": [{"message": {"content": ""}}]},
    )

    llm_empty = LLMClient("test-key", session=session_empty)
    result = llm_empty.translate("test")
    assert result is None, "빈 응답 시 None 기대"
    print("✓ 환각 가드(빈 응답) 발동 → None 반환")

    # ──── 시나리오 8: json_schema strict 조건부 전송 + 펜스 제거 파싱 ────
    print("\n[시나리오 8] json_schema strict (notice_title만) + JSON 펜스 제거")
    print("-" * 70)
    assert _strip_json_fence('```json\n{"a":1}\n```') == '{"a":1}'
    assert _strip_json_fence('설명\n{"title_ja":"あ","title_ko":"아"} 끝') == '{"title_ja":"あ","title_ko":"아"}'
    print("✓ _strip_json_fence: 펜스·잡텍스트 제거")
    assert _NOTICE_TITLE_SCHEMA["strict"] is True
    assert _NOTICE_TITLE_SCHEMA["schema"]["additionalProperties"] is False
    assert set(_NOTICE_TITLE_SCHEMA["schema"]["required"]) == {"title_ja", "title_ko"}
    print("✓ _NOTICE_TITLE_SCHEMA: strict 규칙 준수")

    # ──── 시나리오 8b: participation (URL 우선 ingest 콜라보 판별) ────
    print("\n[시나리오 8b] participation — 5회 재시도 + 성공/실패 경로")
    print("-" * 70)
    assert _PARTICIPATION_SCHEMA["strict"] is True
    assert _PARTICIPATION_SCHEMA["schema"]["additionalProperties"] is False

    class ParticipationSession:
        """처음 N회는 깨진 응답, 그 뒤엔 정상 JSON — 재시도 횟수를 셈."""
        def __init__(self, fail_times: int, final: str):
            self.fail_times = fail_times
            self.final = final
            self.call_count = 0

        def post(self, url, **kwargs):
            self.call_count += 1
            class FakeResp:
                status_code = 200
                def __init__(self, text):
                    self.text = text
                def json(self):
                    return {"choices": [{"message": {"content": self.text}}]}
            # _call_groq 가 model→fallback 순으로 한 번씩 부르므로, 실패 횟수는
            # "호출 횟수"가 아니라 "완전한 시도 라운드" 기준으로 2배.
            if self.call_count <= self.fail_times * 2:
                return FakeResp("이건 JSON 이 아님")
            return FakeResp(self.final)

    llm_participation_ok = LLMClient(
        "test-key", session=ParticipationSession(2, '{"participates": true}')
    )
    result = llm_participation_ok.participation("어떤 트윗 원문", member_name="노노카")
    assert result is True, result
    print("✓ participation: 2회 실패 후 3회차 성공 → True")

    llm_participation_no = LLMClient(
        "test-key", session=ParticipationSession(0, '{"participates": false}')
    )
    result = llm_participation_no.participation("무관한 트윗", member_name="아라레")
    assert result is False, result
    print("✓ participation: 정상 false 응답 파싱")

    llm_participation_fail = LLMClient(
        "test-key", session=ParticipationSession(99, '{"participates": true}')
    )
    result = llm_participation_fail.participation("계속 깨진 응답", member_name="유노")
    assert result is None, result
    print("✓ participation: 5회 모두 실패 → None (호출부 미등록 처리)")

    # ──── 시나리오 8c: announces_own_broadcast (아라레 후기 실사례 재현) ────
    print("\n[시나리오 8c] announces_own_broadcast — 후기 오탐 방지 실사례")
    print("-" * 70)
    assert _ANNOUNCE_SCHEMA["strict"] is True
    assert _ANNOUNCE_SCHEMA["schema"]["additionalProperties"] is False
    assert set(_ANNOUNCE_SCHEMA["schema"]["required"]) == {"announces", "evidence", "reason"}

    llm_announce_yes = LLMClient(
        "test-key", session=ParticipationSession(0, '{"announces": true, "evidence": "明日22時から歌枠", "reason": "내일 22시 노래 방송 예고다."}')
    )
    result = llm_announce_yes.announces_own_broadcast("明日22時から歌枠やります🎤")
    assert result is True, result
    assert "근거: 「明日22時から歌枠」" in llm_announce_yes.last_reason, llm_announce_yes.last_reason
    print("✓ announces_own_broadcast: 진짜 예고 → True (근거 기록)")

    # (v4.5.5) 근거가 비었거나 원문에 없는 구절이면 받지 않고 다시 묻는다 — 5회 모두 그러면 None
    llm_announce_noev = LLMClient(
        "test-key", session=ParticipationSession(0, '{"announces": false, "evidence": "", "reason": ""}')
    )
    assert llm_announce_noev.announces_own_broadcast("〈配信のおしらせ〉\n10/19 22:30～") is None
    llm_announce_fake = LLMClient(
        "test-key", session=ParticipationSession(0, '{"announces": false, "evidence": "配信ありがとうございました", "reason": "후기다."}')
    )
    assert llm_announce_fake.announces_own_broadcast("〈配信のおしらせ〉\n10/19 22:30～") is None, "원문에 없는 근거는 받지 않음"
    assert evidence_in_text("「10/19 22:30～」", "〈配信のおしらせ〉\n10/19 22:30～ #おしらせ") and not evidence_in_text("x", "abc")
    print("✓ announces_own_broadcast: 근거 없음 · 지어낸 근거 → 다시 묻기(5회 모두면 None)")

    llm_announce_recap = LLMClient(
        "test-key", session=ParticipationSession(0, '{"announces": false, "evidence": "配信\\nありがとうございました", "reason": "끝난 방송의 후기다."}')
    )
    result = llm_announce_recap.announces_own_broadcast(
        "#アワーノーツ 先行プレイ配信\nありがとうございました！"
        "ガッツリ2時間プレイ！！\n9/24まで待ち遠しい〜〜〜！！！"
    )
    assert result is False, result
    print("✓ announces_own_broadcast: 아라레 후기 실사례 → False (오탐 방지)")

    llm_announce_fail = LLMClient(
        "test-key", session=ParticipationSession(99, '{"announces": true}')
    )
    result = llm_announce_fail.announces_own_broadcast("계속 깨진 응답")
    assert result is None, result
    print("✓ announces_own_broadcast: 5회 모두 실패 → None")

    # ──── 시나리오 8d: collab_partners — 이름 언급 → LLM 최종 확인 (v3.8.6) ────
    print("\n[시나리오 8d] collab_partners — 언급된 이름이 실제 합동인지 재확인")
    print("-" * 70)

    llm_collab_yes = LLMClient(
        "test-key", session=ParticipationSession(0, '{"collab_with": ["유노"]}')
    )
    result = llm_collab_yes.collab_partners(
        "配信予定 9/21 21:00 ユノ＆律こらぼ", host_name="리츠", candidate_names=["유노"],
    )
    assert result == ["유노"], result
    print("✓ collab_partners: 실제 합동 → 후보 그대로 확인")

    llm_collab_no = LLMClient(
        "test-key", session=ParticipationSession(0, '{"collab_with": []}')
    )
    result = llm_collab_no.collab_partners(
        "유노 잘 지내? 오랜만이다ㅋㅋ 오늘은 혼자 노래방 콜라보 방송할게요",
        host_name="리츠", candidate_names=["유노"],
    )
    assert result == [], result
    print("✓ collab_partners: 안부 인사 등 무관한 언급 → 빈 배열 (오탐 방지)")

    # 후보 여럿 중 일부만 확인되는 경우
    llm_collab_partial = LLMClient(
        "test-key", session=ParticipationSession(0, '{"collab_with": ["아라레"]}')
    )
    result = llm_collab_partial.collab_partners(
        "아라레랑 같이 방송해요! 노노카는 다음에 놀러온대~",
        host_name="유노", candidate_names=["아라레", "노노카"],
    )
    assert result == ["아라레"], result
    print("✓ collab_partners: 여러 후보 중 실제 합동만 부분 확인")

    llm_collab_fail = LLMClient(
        "test-key", session=ParticipationSession(99, '{"collab_with": ["유노"]}')
    )
    result = llm_collab_fail.collab_partners(
        "계속 깨진 응답", host_name="리츠", candidate_names=["유노"],
    )
    assert result is None, result
    print("✓ collab_partners: 5회 모두 실패 → None (호출부 미추가 처리)")

    assert LLMClient("test-key").collab_partners("아무 글", host_name="유노", candidate_names=[]) == []
    print("✓ collab_partners: 후보 없음 → API 호출 없이 빈 배열")

    # ──── 시나리오 8e: broadcast_change_targets — 취소/변경/무관 + 대상 선택 (v4a) ────
    # (2026-10-01) 옛 broadcast_change(종류만 판정, 호출부가 가장 이른 1개 선택)는 호출처가 없어 지웠다 — 이 판정으로 대체됨
    print("\n[시나리오 8e] broadcast_change_targets — 취소/변경 판정 + 영향받는 방송 선택")
    print("-" * 70)

    bc_cands = [{"id": "pv_a", "when": "09/30 22:30", "title": "雑談"},
                {"id": "pv_b", "when": "09/30 23:00", "title": "ゲーム"}]
    llm_bc_del = LLMClient(
        "test-key", session=ParticipationSession(
            0, '{"action": "del", "target_ids": ["pv_a", "pv_b"], "when": null, "reason": "오늘 쉰다고 함"}')
    )
    result = llm_bc_del.broadcast_change_targets("今日は配信お休みします", bc_cands, "09/30(화) 18:00")
    assert result == {"action": "del", "target_ids": ["pv_a", "pv_b"], "when": None, "reason": "오늘 쉰다고 함"}, result
    print("✓ broadcast_change_targets: 휴방 → action=del + 그날 방송 전부")

    llm_bc_edit = LLMClient(
        "test-key", session=ParticipationSession(
            0, '{"action": "edit", "target_ids": ["pv_b"], "when": "10/01 23:00", "reason": "내일로 미룸"}')
    )
    result = llm_bc_edit.broadcast_change_targets("ゲーム配信は明日23時に変更！", bc_cands, "09/30(화) 18:00")
    assert result["action"] == "edit" and result["target_ids"] == ["pv_b"] and result["when"] == "10/01 23:00", result
    print("✓ broadcast_change_targets: 일정 변경 → action=edit + when + 대상 1건")

    llm_bc_none = LLMClient(
        "test-key", session=ParticipationSession(
            0, '{"action": "none", "target_ids": [], "when": null, "reason": "평소 예고"}')
    )
    result = llm_bc_none.broadcast_change_targets("今日も配信するよ！", bc_cands, "09/30(화) 18:00")
    assert result["action"] == "none" and result["target_ids"] == [] and result["reason"] == "평소 예고", result
    print("✓ broadcast_change_targets: 평소 예고 → action=none (근거는 남김)")

    llm_bc_fail = LLMClient(
        "test-key", session=ParticipationSession(99, '{"action": "del", "target_ids": [], "when": null, "reason": ""}')
    )
    result = llm_bc_fail.broadcast_change_targets("계속 깨진 응답", bc_cands, "09/30(화) 18:00")
    assert result is None, result
    print("✓ broadcast_change_targets: 5회 모두 실패 → None (호출부 미반영 처리)")

    # ──── 시나리오 8f: ！ 연속 접기/되펼치기 (2026-10-07 리츠 트윗) ────
    print("\n[시나리오 8f] 느낌표 4회+ 연속 접기 → 번역 → 개수 복원")
    real = "無事に、完凸峰月律をゲットしました" + "！" * 80 + "\n編み込み赤ちゃんだ" + "！" * 8
    folded, runs = _collapse_punct_runs(real)
    assert runs == [("!", 80), ("!", 8)] and len(folded) < 40, (runs, len(folded))
    assert _collapse_punct_runs("すごい！！！")[1] == []            # 3개 이하는 그대로
    ko = "무사히 얻었습니다!!!\n뜨개질 아기다!!!"
    restored = _restore_punct_runs(ko, runs)
    assert restored == "무사히 얻었습니다" + "!" * 80 + "\n뜨개질 아기다" + "!" * 8, restored
    assert _restore_punct_runs("합쳐졌다!!!", runs) == "합쳐졌다!!!"   # 군집 수 불일치 → 추측 안 함

    class BangLoopSession:
        """실측 재현 — 입력에 ！ 4개+ 가 있으면 `!` 폭주, 접힌 입력이면 정상 번역."""
        def post(self, url, **kwargs):
            c = kwargs["json"]["messages"][0]["content"]
            reply = ("번역" + "!" * 3000) if "！！！！" in c else "무사히 얻었습니다!!!"
            class R:
                status_code = 200
                def json(self_inner):
                    return {"choices": [{"message": {"content": reply}}]}
            return R()

    got = LLMClient("test-key", session=BangLoopSession()).translate("無事にゲットしました" + "！" * 80)
    assert got == "무사히 얻었습니다" + "!" * 80, got
    assert _KANA_RUN_RE.sub(lambda m: m.group(1) * 5, "うれしい" + "ぁ" * 40 + "です") == "うれしい" + "ぁ" * 5 + "です"
    assert _KANA_RUN_RE.sub(lambda m: m.group(1) * 5, "🩵 " + "･" * 21 + " 🩵") == "🩵 " + "･" * 21 + " 🩵"   # 구분선은 불변
    assert _KANA_RUN_RE.sub(lambda m: m.group(1) * 5, "ななななななな") == "ななななななな"           # 7회는 미달
    assert _jamo_runs_to_tilde("기뻐요ㅏㅏㅏㅏㅏ!", [40]) == "기뻐요" + "~" * 40 + "!"
    assert _jamo_runs_to_tilde("ㅏㅏㅏ와 ㅡㅡㅡ", [9, 12]) == "~" * 9 + "와 " + "~" * 12   # 순서 대응
    assert _jamo_runs_to_tilde("ㅏㅏㅏ와 ㅡㅡㅡ", [9]) == "~와 ~"                      # 수 불일치 → 하나씩
    assert _jamo_runs_to_tilde("ㅋㅋㅋ 웃겨", [9]) == "ㅋㅋㅋ 웃겨"                      # 자음(ㅋ)·완성형은 불변
    assert _fold_kana_runs("うれしい" + "ぁ" * 40 + "です") == ("うれしい" + "ぁ" * 5 + "です", [40])
    class KanaSession:
        def post(self, url, **kwargs):
            class R:
                status_code = 200
                def json(self_inner):
                    return {"choices": [{"message": {"content": "기뻐요ㅏㅏㅏㅏㅏ!!!"}}]}
            return R()
    got = LLMClient("test-key", session=KanaSession()).translate("うれしい" + "ぁ" * 40 + "です" + "！" * 21)
    assert got == "기뻐요" + "~" * 40 + "!" * 21, got
    print("✓ ！ 80개 트윗: 접어서 번역 → 80개로 복원 (폭주 입력 재현 세션 통과)")

    # ──── 시나리오 9: translate 반복 압축 (버그리포트 20260913 #3) ────
    print("\n[시나리오 9] translate 반복 압축 (의성어 8회+ 연속반복)")
    print("-" * 70)

    assert _REPEAT_RE.match("もぐ" * 8)                       # 8회 = 경계값, 매치
    assert not _REPEAT_RE.match("もぐ" * 7)                    # 7회는 미달, 비매치
    assert not _REPEAT_RE.match("こんにちは、今日は良い天気です")  # 반복 아님, 비매치

    class RepeatAwareSession:
        """프롬프트 내용으로 "반복 단위" 호출과 "나머지" 호출을 구분해 각각 응답."""
        def post(self, url, **kwargs):
            content = kwargs["json"]["messages"][0]["content"]
            if "번 연속 반복되는 의성어" in content:      # _translate_repeat_unit 전용 프롬프트
                reply = "냠"
            else:
                reply = "#애니메유메미타"
            class FakeResp:
                status_code = 200
                def json(self):
                    return {"choices": [{"message": {"content": reply}}]}
            return FakeResp()

    llm_repeat = LLMClient("test-key", session=RepeatAwareSession())
    repeated_input = "もぐ" * 40 + "\n#アニメゆめみた"
    result = llm_repeat.translate(repeated_input)
    assert result == "냠" * 40 + "\n#애니메유메미타", result
    print(f"✓ 반복 압축: 단위만 문맥과 함께 번역 후 40회 재조립 (폭주 없이 {len(result)}자)")

    # 반복 단위 뒤에 나머지가 없는 경우(순수 반복만)도 정상 조립.
    llm_repeat2 = LLMClient("test-key", session=RepeatAwareSession())
    result2 = llm_repeat2.translate("もぐ" * 10)
    assert result2 == "냠" * 10, result2
    print("✓ 반복 압축: 나머지 없이 단위만 반복되는 경우도 처리")

    class PayloadCapturingSession:
        def __init__(self):
            self.last_payload = None

        def post(self, url, **kwargs):
            self.last_payload = kwargs.get("json")
            class FakeResp:
                pass

            resp = FakeResp()
            resp.status_code = 200
            resp.text = '{"choices":[{"message":{"content":"test"}}]}'

            def json_method():
                return {
                    "choices": [
                        {
                            "message": {"content": "test"}
                        }
                    ]
                }

            resp.json = json_method
            return resp

    session_payload = PayloadCapturingSession()
    llm_payload = LLMClient("test-key", session=session_payload)
    # translate 경로: json_schema 안 붙음
    llm_payload._call_groq(DEFAULT_MODEL, "test")
    assert "response_format" not in session_payload.last_payload, "translate 는 response_format 없음"
    assert session_payload.last_payload["max_tokens"] == 500, "짧은 prompt 는 max_tokens 하한(500)"
    # notice_title 경로: json_schema strict 붙음
    llm_payload._call_groq(DEFAULT_MODEL, "test", json_schema=_NOTICE_TITLE_SCHEMA)
    rf = session_payload.last_payload["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    print("✓ json_schema strict 는 notice_title 경로에만, max_tokens 상한 동봉")

    # ──── 시나리오 10: 장음부호 늘려쓰기 정규화 (버그리포트 20260913 #4) ────
    print("\n[시나리오 10] 장음부호 늘려쓰기 정규화 (もぐもぐ 반복과는 다른 케이스)")
    print("-" * 70)

    assert _normalize_stretch("おーまーーたーーせーーーしーーーーました") == "おーまーたーせーしーました"
    # 멤버명·단어의 정상적인 글자 반복(장음부호가 아님)은 안 건드림.
    assert _normalize_stretch("宮永ののか") == "宮永ののか"
    assert _normalize_stretch("かわいい") == "かわいい"
    assert _normalize_stretch("https://www.youtube.com") == "https://www.youtube.com"
    print("✓ _normalize_stretch: 장음부호만 표적, 멤버명·단어·URL 은 보존")

    class StretchLoopSession:
        """정규화 안 된 원문(장음부호 다량)이 오면 반복 루프를 흉내(과길이 응답)."""
        def post(self, url, **kwargs):
            content = kwargs["json"]["messages"][0]["content"]
            reply = "정상 번역" if "ーーー" not in content else "폭주" * 500
            class FakeResp:
                status_code = 200
                def json(self):
                    return {"choices": [{"message": {"content": reply}}]}
            return FakeResp()

    llm_stretch = LLMClient("test-key", session=StretchLoopSession())
    stretched = "おーまーーたーーせーーーしーーーーました🙇‍♀️"
    result = llm_stretch.translate(stretched)
    assert result == "정상 번역", result  # 정규화 안 됐으면 "폭주"*500 이 나와 환각 가드에 걸림
    print("✓ translate(): 정규화 후 전송 — 반복 루프 회피, 정상 응답 통과")

    # ──── 시나리오 11: 용어집 고정 번역 (2026-09-13) ────
    print("\n[시나리오 11] 용어집(GLOSSARY) — 그룹명 고정 번역")
    print("-" * 70)

    masked, mapping = _mask_glossary("夢限大みゅーたいぷ 5th Single 発売記念")
    assert masked == "@@GLOSSARY0@@ 5th Single 発売記念", masked
    assert mapping == [("@@GLOSSARY0@@", "夢限大みゅーたいぷ", "무겐다이 뮤타입")], mapping
    assert _unmask_glossary(masked, mapping, to="ko") == "무겐다이 뮤타입 5th Single 発売記念"
    assert _unmask_glossary(masked, mapping, to="ja") == "夢限大みゅーたいぷ 5th Single 発売記念"
    print("✓ _mask_glossary/_unmask_glossary: 왕복 변환 정확")

    # LLM 이 프롬프트 지시대로 플레이스홀더를 그대로 남겨 응답했다고 가정 — 그래도 다른
    # 호출마다 그룹명을 다르게 옮기던 문제(꿈한계대 뮤타입/꿈꾸다/유메미타 등)가
    # _unmask_glossary 로 항상 "무겐다이 뮤타입" 하나로 고정되는지 확인.
    session_glossary = FakeSession(
        status_code=200,
        body={"choices": [{"message": {
            "content": "@@GLOSSARY0@@ 5th 싱글 발매 기념 사인회입니다."
        }}]},
    )
    llm_glossary = LLMClient("test-key", session=session_glossary)
    result = llm_glossary.translate("夢限大みゅーたいぷ 5th Single リリース記念サイン会です。")
    assert result == "무겐다이 뮤타입 5th 싱글 발매 기념 사인회입니다.", result
    print("✓ translate(): 그룹명이 매번 '무겐다이 뮤타입'으로 고정됨")

    # ──── 시나리오 12: バンドリ 고정 번역(구두점 제외) + 토큰-영숫자 들러붙음 방지 ────
    print("\n[시나리오 12] バンドリ → '뱅드림' 고정 + 토큰 뒤 영숫자 들러붙음 방지")
    print("-" * 70)

    # 구두점(느낌표)은 등록값에 안 넣는다 — 원문에 있으면 그대로 남아 번역에도 반영되므로.
    masked, mapping = _mask_glossary("「バンドリ！ ゆめ∞みた」×極楽湯 RAKU SPAコラボ")
    assert masked == "「@@GLOSSARY1@@！ ゆめ∞みた」×極楽湯 RAKU SPAコラボ", masked
    assert _unmask_glossary(masked, mapping, to="ko") == "「뱅드림！ ゆめ∞みた」×極楽湯 RAKU SPAコラボ"
    print("✓ バンドリ만 고정, 뒤의 느낌표는 원문 그대로 보존")

    # 뒤에 바로 영숫자("13th")가 붙은 경우 — 예전엔 토큰이 그대로 들러붙어 LLM 이 그 뒤
    # 문장을 통째로 미번역으로 남기던 버그(실측). 공백 삽입으로 방지.
    masked2, mapping2 = _mask_glossary("バンドリ13thライブ DAY")
    assert masked2 == "@@GLOSSARY1@@ 13thライブ DAY", masked2
    assert _unmask_glossary(masked2, mapping2, to="ko") == "뱅드림 13thライブ DAY"
    print("✓ バンドリ13th… 처럼 영숫자가 바로 붙은 경우 → 토큰 뒤에 공백 삽입")

    # 이미 공백/구두점과 붙어 있으면 불필요한 공백을 추가하지 않는다(「바로 뒤 등).
    masked3, _m3 = _mask_glossary("バンドリ 13th")
    assert masked3 == "@@GLOSSARY1@@ 13th", masked3  # 원래 있던 공백 그대로, 중복 안 됨
    print("✓ 이미 공백 있는 경우엔 추가 공백 안 생김")

    # ──── 시나리오 13: LLM 이 토큰을 변형해 남겨도 잔재가 새지 않음 (버그리포트 20260916) ────
    print("\n[시나리오 13] 변형된 GLOSSARY 토큰 잔재 — 최종 출력에 새지 않음")
    print("-" * 70)

    assert _unmask_glossary("@@ GLOSSARY0 @@ 5th 싱글 발매", [], to="ko") == "5th 싱글 발매", \
        _unmask_glossary("@@ GLOSSARY0 @@ 5th 싱글 발매", [], to="ko")
    assert _unmask_glossary("사인회 @@GLOSSARY0@@ 입니다", [], to="ko") == "사인회 입니다"
    print("✓ _unmask_glossary: mapping 에 없는(=치환 실패한) GLOSSARY 잔재도 최종 텍스트에서 제거됨")

    # ──── 시나리오 14: 메인 모델이 200+빈 content 로 응답해도 fallback 시도 (버그리포트 20260916 #2) ────
    print("\n[시나리오 14] 메인 모델 200 + content='' → fallback 모델로 넘어감")
    print("-" * 70)

    class EmptyThenOkSession:
        """메인 모델(첫 호출)은 200에 content='' (reasoning이 max_tokens 다 씀 재현),
        폴백 모델(둘째 호출)은 정상 응답."""
        def __init__(self):
            self.call_count = 0
        def post(self, url, **kwargs):
            self.call_count += 1
            cc = self.call_count
            class FakeResp:
                status_code = 200
                def json(self):
                    return {"choices": [{"message": {"content": "" if cc == 1 else "정상 번역"}}]}
            return FakeResp()

    llm_empty_ok = LLMClient("test-key", session=EmptyThenOkSession())
    result = llm_empty_ok.translate("こんにちは")
    assert result == "정상 번역", result
    print("✓ translate(): content='' (빈 문자열, None 아님) 도 fallback 트리거 — 이전엔 `is None`만"
          " 검사해 곧장 환각 가드로 떨어져 폴백을 건너뛰었음(실측: 같은 입력 4회 모두 in=155/out='')")

    # ──── WP-2: 외부 LLM 폴백 기본값 통일 ────
    print("\n[WP-2] LLMClient 기본값이 상수 DEFAULT_MODEL/FALLBACK_MODEL 을 사용")
    print("-" * 70)

    test_client = LLMClient("dummy-key")
    assert test_client.model == DEFAULT_MODEL, f"model should be {DEFAULT_MODEL}, got {test_client.model}"
    assert test_client.fallback == FALLBACK_MODEL, f"fallback should be {FALLBACK_MODEL}, got {test_client.fallback}"
    print(f"✓ LLMClient(api_key): model={DEFAULT_MODEL}, fallback={FALLBACK_MODEL}")

    # ──── (v4.2.0) song_reading ────
    print("\n[v4.2.0] song_reading — 곡명 독음(가나)")
    print("-" * 70)

    class _ReadingSession:
        def __init__(self, contents):
            self.contents = list(contents)
            self.calls = 0
        def post(self, url, **kwargs):
            self.calls += 1
            c = self.contents.pop(0) if self.contents else ""
            class R:
                status_code = 200
                def json(self_inner):
                    return {"choices": [{"message": {"content": c}}]}
            return R()

    _s = _ReadingSession(['{"reading": "ゆめがむちゅう"}'])
    assert LLMClient("k", session=_s).song_reading("夢我夢中") == "ゆめがむちゅう"
    print("✓ 정상 응답 → 가나 독음")
    assert LLMClient("k", session=_ReadingSession(['{"reading": "ふぇいす ざ ねくすと"}'])).song_reading("Face The Next") == "ふぇいすざねくすと"
    print("✓ 공백 제거")
    assert LLMClient("k", session=_ReadingSession(['{"reading": "꿈이 꿈중"}'])).song_reading("夢我夢中") is None
    print("✓ 한글(번역) 응답은 버림 → None")
    _s2 = _ReadingSession(["", '{"reading": "ふぇいす"}'])
    assert LLMClient("k", session=_s2).song_reading("Face") == "ふぇいす" and _s2.calls == 2
    print("✓ 메인 모델 빈 응답 → 폴백 모델")
    assert LLMClient("").song_reading("夢我夢中") is None and LLMClient("k", session=_ReadingSession([])).song_reading("  ") is None
    print("✓ 키 없음 · 빈 제목 → None")

    # ──── (v4.5.7) 반각 가나 번역 ────
    print("\n[v4.5.7] 반각 가나 — 전각 변환 · 잔존 검사 · 1회 재요청")
    print("-" * 70)
    assert _widen_halfwidth_kana("🍭ﾍﾟﾛｷｬﾝ ﾊｯ！！ あしたﾏﾃﾞ") == "🍭ペロキャン ハッ！！ あしたマデ"
    assert _widen_halfwidth_kana("かわいい ＃みるみやこ ～ ！") == "かわいい ＃みるみやこ ～ ！", "반각 가나 밖은 불변"
    print("✓ 반각 가나 구간만 전각으로 (！ ～ 등은 그대로)")
    assert _residual_kana("🎃🍭🐶ﾍﾟﾛｷｬﾝ") and not _residual_kana("🎃🍭🐶페로캔 #ﾐﾙﾐﾔｺ")
    print("✓ 번역문에 남은 반각 가나도 감시 (해시태그 안은 제외)")
    _s3 = _ReadingSession(["🍭ﾍﾟﾛｷｬﾝ", "🍭페로캔"])   # 1차: 반각이 남은 번역 → 재요청이 고침
    assert LLMClient("k", session=_s3).translate("🍭ペロキャン") == "🍭페로캔" and _s3.calls == 2
    _s4 = _ReadingSession(["🍭ペロキャン", "🍭ペロキャン"])   # 재요청도 못 고침 → 이전 결과 유지(저장은 그대로)
    assert LLMClient("k", session=_s4).translate("🍭ペロキャン") == "🍭ペロキャン" and _s4.calls == 2
    _s5 = _ReadingSession(["🍭페로캔"])                       # 처음부터 깨끗하면 재요청 없음
    assert LLMClient("k", session=_s5).translate("🍭ペロキャン") == "🍭페로캔" and _s5.calls == 1
    print("✓ 가나 잔존 → 1회 재요청(고치면 채택 · 못 고치면 유지 · 깨끗하면 호출 1회)")

    # ──── (v4.5.10) 행사 판정 2단계 — banner_scope(게임 안/밖, 근거 목록) · banner_extract(이벤트 · 가챠 옮겨 적기) ────
    print("\n[v4.5.10] banner_scope · banner_extract")
    print("-" * 70)
    _jr = "📢#推し旅 コラボ開催決定！🚅\nJR東海×『BanG Dream! Our Notes』\n\n・東海道新幹線乗車特典"
    _ss = _ReadingSession([
        '{"scope": "outside", "evidence": ["JR東海×『BanG Dream! Our Notes』ここだけ"], "reason": "철도 콜라보다."}',   # 원문에 없는 구절 → 거절
        '{"scope": "outside", "evidence": ["JR東海×『BanG Dream! Our Notes』", "東海道新幹線乗車特典"], "reason": "철도 콜라보다."}'])
    _r = LLMClient("k", session=_ss).banner_scope(_jr)
    assert _r and _r["scope"] == "outside" and len(_r["evidence"]) == 2 and _ss.calls == 2, _r
    assert LLMClient("k", session=_ReadingSession(['{"scope": "in_game", "evidence": [], "reason": "게임 안 이벤트다."}'] * 10)).banner_scope("x") is None
    print("✓ banner_scope: 원문에 없는 근거 · 빈 근거는 다시 묻기")
    _txt = "明日15:00より開催🎉\nチャレンジライブイベント「Shake Your 魂, Baby!!」"
    _ocr = [{"idx": 1, "text": "イベント\nshake your 魂, Baby!!\n開催期間：10月18日 15:00 ～ 10月26日 14:59"}]
    _ex = LLMClient("k", session=_ReadingSession([
        '{"items": [{"kind": "event", "status": "normal", "title_ja": "チャレンジライブイベント「shake your 魂, Baby!!」", "title_ko": "셰이크", '
        '"start_jst": "2026-10-18 15:00", "start_evidence": "明日15:00より開催", "end_jst": "2026-10-26 14:59", '
        '"end_evidence": "開催期間：10月18日 15:00 ～ 10月26日 14:59"}], "image_roles": ["event"], "reason": "이벤트 1건."}']))
    _r = _ex.banner_extract(_txt, "2026-10-17 18:00", _ocr)
    assert _r["items"][0]["title_ja"] == "Shake Your 魂, Baby!!", _r      # 「」 안쪽만 + 본문 표기(대소문자)
    assert _r["items"][0]["end_jst"] == "2026-10-26 14:59" and _r["image_roles"] == ["event"], _r
    assert _banner_title("ガチャ「差し込む光、始まりのとき」", "ガチャ「差し込む光、始まりのとき」") == "差し込む光、始まりのとき"
    _bad = LLMClient("k", session=_ReadingSession([
        '{"items": [{"kind": "gacha", "status": "normal", "title_ja": "없는 가챠", "title_ko": "", "start_jst": null, "end_jst": null, '
        '"start_evidence": "", "end_evidence": ""}], "image_roles": [], "reason": "."}'] * 10))
    assert _bad.banner_extract(_txt, "2026-10-17 18:00") is None, "원문에 없는 제목은 받지 않음"
    _none = LLMClient("k", session=_ReadingSession(['{"items": [], "image_roles": ["event", "none"], "reason": "미션 안내라 없음."}']))
    assert _none.banner_extract("限定ミッション", "2026-10-15 22:43", _ocr) == {"items": [], "image_roles": [], "reason": "미션 안내라 없음."}
    # 남의 기간을 빌린 날짜(근거 구절에 없음) — 3회까지 다시 묻고, 그래도면 그 날짜만 비운다
    _borrow = ('{"items": [{"kind": "gacha", "status": "normal", "title_ja": "ワタシが主役のサイバーナイトガチャ", "title_ko": "", '
               '"start_jst": "2026-09-28 15:00", "start_evidence": "9月28日(月)15:00より", "end_jst": "2026-10-07 20:59", "end_evidence": "9月28日(月)15:00より"}], '
               '"image_roles": [], "reason": "."}')
    _at = "9月28日(月)15:00よりチャレンジライブイベント「アイの奔流 AtoZ」\nイベントガチャ「ワタシが主役のサイバーナイトガチャ」"
    _sb = _ReadingSession([_borrow] * 5)
    _r = LLMClient("k", session=_sb).banner_extract(_at, "2026-09-24 22:08")
    assert _r["items"][0]["start_jst"] == "2026-09-28 15:00" and _r["items"][0]["end_jst"] is None and _sb.calls == 4, (_r, _sb.calls)
    assert _jst_in_evidence("2026-10-09 15:00", "明日15:00より開催", "2026-10-08 21:04") and not _jst_in_evidence("2026-10-09 16:00", "明日15:00より", "2026-10-08 21:04")
    assert _jst_in_evidence("2026-11-30", "2026.11.30 - 2027.2.28", "2026-10-20 14:42") and _jst_in_evidence("2026-10-18 15:00", "10月18日 15時から", "")
    # 공연 이름(「イベント」 표지 없음)은 event 로 받지 않는다
    _live = LLMClient("k", session=_ReadingSession(['{"items": [{"kind": "event", "status": "normal", "title_ja": "DIMENSIONAL OVERLAP", "title_ko": "", '
                                                   '"start_jst": null, "start_evidence": "", "end_jst": null, "end_evidence": ""}], "image_roles": [], "reason": "."}']))
    _r = _live.banner_extract("BanG Dream! 13th☆LIVE\n「DIMENSIONAL OVERLAP」\n開催記念 ミッションパス🛸", "2026-10-11 21:02")
    assert _r["items"] == [] and "이벤트 표지 없음" in _r["reason"], _r
    print("✓ banner_extract: 「」 안쪽 · 본문 표기 · 근거 없는 제목 거절 · 이미지 수 안 맞는 용도 버림 · 남의 기간 빌림 거름 · 공연 이름 거름")

    # ──── (v4.7.0) 소식 분류 · 공연 이름 ────
    _nt = "＼先行通販開始📢／\nBanG Dream! 13th☆LIVE\n先行通販がこのあと15時00分より開始です！\n#ゆめみた"
    _s = _ReadingSession(['{"cats": ["goods", "live"], "evidence": ["先行通販がこのあと15時00分より開始です！"], "reason": "공연 굿즈 통판이다."}'])
    assert LLMClient("k", session=_s).notice_categories(_nt) == ["live", "goods"], "분류 순서 = NOTICE_LLM_CATS"
    _s = _ReadingSession(['{"cats": ["live"], "evidence": ["없는 구절"], "reason": "공연 소식이다."}',
                          '{"cats": ["live"], "evidence": [], "reason": "공연 소식이다."}',
                          '{"cats": ["live"], "evidence": ["BanG Dream! 13th☆LIVE"], "reason": "공연 소식이다."}'])
    assert LLMClient("k", session=_s).notice_categories(_nt) == ["live"] and _s.calls == 3, "근거 없으면 다시 묻는다"
    _s = _ReadingSession(['{"cats": [], "evidence": [], "reason": "애니 방영 안내라 해당 없음."}'])
    assert LLMClient("k", session=_s).notice_categories("アニメ放送開始") == [], "빈 목록 = 해당 없음(근거 없어도 됨)"
    _s = _ReadingSession(['{"cats": ["live"], "evidence": ["x"], "reason": "."}'] * 3)
    assert LLMClient("k", session=_s).notice_categories(_nt) is None and _s.calls == 3, "3회 모두 근거 없음 → None"
    assert LLMClient("k", session=_ReadingSession([""])).notice_categories(_nt) is None, "호출 실패 → None"
    _lt = "＼チケット一般発売 明日開始📢／\n12/24(木)開催\n🎤NAKAMACHI ARALE LIVE 2026 「RESONEXT」🎤\n⏰受付期間 明日10/3(土) 12:00〜"
    _s = _ReadingSession(['{"name": "RESONEXT", "name_evidence": "🎤NAKAMACHI ARALE LIVE 2026 「RESONEXT」🎤", "date": "2026-12-24", '
                          '"date_evidence": "12/24(木)開催", "reason": "공연 타이틀과 개최일이다."}'])
    assert LLMClient("k", session=_s).live_info(_lt, "2026-10-02 12:00") == {"name": "RESONEXT", "date": "2026-12-24", "reason": "공연 타이틀과 개최일이다."}
    _bad_date = ('{"name": "RESONEXT", "name_evidence": "🎤NAKAMACHI ARALE LIVE 2026 「RESONEXT」🎤", "date": "2026-10-03", '
                 '"date_evidence": "12/24(木)開催", "reason": "공연 타이틀과 개최일이다."}')
    _s = _ReadingSession([_bad_date] * 3)
    _r = LLMClient("k", session=_s).live_info(_lt, "2026-10-02 12:00")
    assert _r == {"name": "RESONEXT", "date": None, "reason": "공연 타이틀과 개최일이다."} and _s.calls == 3, "날짜 근거 불일치 → 이름만"
    _s = _ReadingSession(['{"name": "없는 공연", "name_evidence": "없는 줄", "date": "", "date_evidence": "", "reason": "공연 이름이다."}'] * 3)
    assert LLMClient("k", session=_s).live_info(_lt, "2026-10-02 12:00") is None, "원문에 없는 이름 → None"
    assert _md_in_evidence("2026-12-24", "12月24日(木)") and _md_in_evidence("2026-10-11", "2026.10.11 東京") and not _md_in_evidence("2026-10-03", "12/24(木)")
    assert _md_in_evidence("2026-10-11", "本日開催", "2026-10-11") and not _md_in_evidence("2026-10-12", "本日開催", "2026-10-11")
    print("✓ notice_categories · live_info: 분류 순서 · 근거 다시 묻기 · 빈 목록 · 실패 None · 공연일 근거 · 이름만")

    print("\n" + "=" * 70)
    print("SUCCESS: 모든 스모크 테스트 통과 (WP-2 포함)")
    print("=" * 70)
