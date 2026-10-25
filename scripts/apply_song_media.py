"""곡 목록에 「음원 영상 · MV」 정보를 반영한다 (v4.8.3). 입력 songs.json 의 곡에 `alt`(다른 음원 영상) · `mv`(MV 영상)를 넣고, 표에 없는 새 곡 1건을 추가한다.

출처: 2026-10-25 yt-dlp 조사 결과(곡별 같은 소리의 다른 음원 영상 · MV 영상 id 표, 운영자 확정). 표의 id 는 songs.json 의 대표 id 다.
기준: 「歌ってみた」 표시가 붙은 영상은 그 자체로 한 곡이다 — MV 로 묶지 않고 별도 곡으로 둔다(唱 2024 처럼 따로 추가). 표시는 「아라레, 리츠」.

사용: python scripts/apply_song_media.py <입력 songs.json> [<출력 경로>]   (출력 생략 = 입력에 덮어쓴다)
- 곡 문서의 다른 키(`rejected` · `seen` …)는 그대로 둔다.
- MEDIA 표의 id 와 같은 곡에 alt · mv 를 넣는다(이미 있으면 덮어씀). 빈 목록은 키를 넣지 않는다.
- NEW 곡은 같은 id 가 없을 때만 맨 뒤에 추가한다. 표에 있는데 문서에 없는 id 는 건너뛰고 그 수를 출력한다.
- 직렬화는 build_songs_json.py 와 같다(sort_keys · indent 2 · ensure_ascii=False · 끝 개행 1개).
"""
import json
import re
import sys
from pathlib import Path

# 표: 한 줄 = 곡 id, 그 뒤 `alt` 로 시작하는 음원 영상 목록, `mv` 로 시작하는 MV 목록
MEDIA = """
zFsTGz60TLY  alt fdXuZ47vNec KXbC2U_jBwU   mv _awcveMOhc0
SI8q0trRdOE  alt GZO1yxWxNyM               mv rfA_P10FGQQ
oD74b35UNVc  alt ZHdR3lIu_Zo HEoKwUmjNgs   mv 49huUnynCPQ
_iX9WOOierg  alt UrHGouRCkQ8               mv W4ib6g0KeZI
xosxYF29mvk  alt 4_dKW9eN7zM               mv A3lRSM6v44c
3WpaXoun2Tc  alt 3irTSJwcoxU               mv z1ga6_4K2io
XYCI2LzEnZA  alt JCb1ks0bPvE o6Unc8Kpr1A   mv dkeX5Qy_ths
J_zCYMoy1Cw                                mv EvbVMKvTY4U
vS2MCoSUEVs  alt Q_KhNpXkWuQ               mv GB2MEvY2sQk
mKiBvYqfBfk  alt dihT5By_Jqs QJsZ5EKMbCs   mv GN_0T7cClGM
a1-SB-tFYmI  alt pUNK6ANdaxw               mv 2ecjo9jpoPM
fDnYCRzvCco  alt gcP4wgxPi-E
QMcU8T8wOd4  alt 3701FJSYZEY 5aKAFvgYLxo   mv nYkNrdsjK0k
KD-EeGTr53I  alt 9DRqNxD0Xdw               mv QmrVn2ckUr8
g9fpSuTbouI  alt 9lxoZNa8rZU               mv ZcKt-aAmKfA
gJqvYYkdkC8  alt znm-Rn5sxhs               mv rkpYy32ik7E QARyadS-0zY
a6oOosacMxc  alt X05Zl1z2XMk               mv HuyK2j3EH7Y
qnHJDWgLkvw                                mv uab9GICZjy4
DvZohC30iOw                                mv i4wpfobHHkc
jr_xt37IcRc                                mv WFOobNlAr3I
4XbNBhZuBoA  alt jlnbYlVunfg               mv ojgoIwE1fL0
TedsUWY90Vs  alt zPieTviOC54               mv Ps8vxSKsbOc
eZG4sXy0zPM                                mv 3m6JMKsF2x8
tRS9u2YlqdM  alt W3_XJnrC9Jw
Fp2a-MhCFVw                                mv c_T1QlWWsOE
1_WyE1U0f4E                                mv ekZUC5KaJFw
XbqG3T4MGJE                                mv beTgKM4yo2o
"""

# 표에 없는 새 곡 — 歌ってみた 표시(「唱」)가 붙은 별개 곡. 같은 id 가 이미 있으면 추가하지 않는다.
NEW = {"id": "zVdR0urFjnc", "title": "唱", "kind": "cover", "who": "group", "singers": ["arale", "ritsu"], "date": "2024-04-05",
       "reading": "しょう", "reading_manual": True, "manual": True, "added_at": "2026-10-25T00:00:00Z"}

ID_RE = re.compile(r"[\w-]{11}")


def parse_media(text):
    """표 → {id: {"alt": [...], "mv": [...]}}. 토큰 `alt` · `mv` 뒤에 오는 영상 ID 들을 그 목록에 담는다."""
    out = {}
    for line in text.splitlines():
        toks = line.split()
        if not toks:
            continue
        vid, mode, bucket = toks[0], None, {"alt": [], "mv": []}
        if not ID_RE.fullmatch(vid):
            raise SystemExit(f"표의 영상 ID 형식이 아닙니다: {vid}")
        for t in toks[1:]:
            if t in ("alt", "mv"):
                mode = t
                continue
            if mode is None or not ID_RE.fullmatch(t):
                raise SystemExit(f"표 해석 실패: {line.strip()}")
            bucket[mode].append(t)
        out[vid] = {k: v for k, v in bucket.items() if v}
    return out


def main(argv):
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    src = Path(argv[1])
    dst = Path(argv[2]) if len(argv) == 3 else src
    doc = json.loads(src.read_text(encoding="utf-8"))
    songs = doc["songs"]
    media = parse_media(MEDIA)
    by_id = {s.get("id"): s for s in songs}

    applied, skipped = 0, []
    for vid, m in media.items():
        song = by_id.get(vid)
        if song is None:
            skipped.append(vid)
            continue
        for k in ("alt", "mv"):
            if k in m:
                song[k] = m[k]
        applied += 1

    added = 0
    if NEW["id"] not in by_id:
        songs.append(dict(NEW))
        added = 1

    text = json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    dst.write_text(text, encoding="utf-8", newline="\n")
    print(f"표 {len(media)}곡 중 반영 {applied}곡 · 건너뜀 {len(skipped)}곡 · 새 곡 추가 {added}곡 → {dst}")
    if skipped:
        print("건너뜀(문서에 없는 id): " + ", ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
