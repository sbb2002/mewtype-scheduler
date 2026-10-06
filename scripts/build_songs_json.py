"""플레이어 곡 목록(assets/songs.json) 생성 — ref/player/songs_release.json 에서 프론트가 쓰는 필드만 추려 만든다. (v4.2.0)

실행(저장소 루트에서): python scripts/build_songs_json.py
- 입력은 BPM 프로젝트(bandori-playlist-maker-data)의 곡 데이터를 YouTube 업로드 시각과 합쳐 만든 스냅샷이다.
  신곡을 반영하려면 먼저 그 스냅샷을 갱신해야 한다 — 동기화 방법은 아직 정해지지 않았다(docs/SPEC.md 「플레이어 — 확인 필요」).
- BPM · 키 · energy · valence 는 일부러 넣지 않는다 — 오디오 분석(GPU 필요, 메인 로컬)이 있어야 얻는 값이고 플레이어가 쓰지 않는다.
- 독음(reading)은 아래 READ 에 있는 15곡만 채워져 있다(검수 전 예시). 나머지는 빈 문자열.
"""
from pathlib import Path
import json, re, sys
ROOT = Path(__file__).resolve().parent.parent
src = ROOT / 'ref' / 'player' / 'songs_release.json'          # BPM 프로젝트 곡 데이터 스냅샷 (YouTube 업로드 시각 포함)
dst = ROOT / 'src' / 'frontend' / 'assets' / 'songs.json'      # 프론트가 정적으로 배포하는 곡 목록
d = json.load(open(src, encoding='utf-8'))

# 독음(가나)은 예시로 채운 15곡만. 나머지는 빈 문자열 — 검수 · 보충 필요.
READ = {
 '君が飛び降りるのならば (Solo)': 'きみがとびおりるのならば', 'ユキトキ (Solo)': 'ゆきとき',
 '絶え間なく藍色 (Solo)': 'たえまなくあいいろ', '撫でんな (Solo)': 'なでんな',
 '夜もすがら君想ふ (Solo)': 'よもすがらきみおもふ', '翼をください (Solo)': 'つばさをください',
 'これはぼくたちの生存のあらすじ': 'これはぼくたちのせいぞんのあらすじ', '真夜中遊園地': 'まよなかゆうえんち',
 '超惑星Xへの旅': 'ちょうわくせいXへのたび', 'アイの夢限': 'あいのむげん', 'コハク': 'こはく',
 'テレパシー': 'てれぱしー', 'オリオンをなぞる (Cover)': 'おりおんをなぞる',
 '時をかける少女 (Solo)': 'ときをかけるしょうじょ', 'ジレンマ (Solo)': 'じれんま',
}

def who(ch):
    ch = ch or ''
    for k, key in (('あられ', 'arale'), ('ユノ', 'yuno'), ('ののか', 'nonoka'), ('律', 'ritsu'), ('都子', 'miyako'),
                   ('Arale', 'arale'), ('Yuno', 'yuno'), ('Nonoka', 'nonoka'), ('Ritsu', 'ritsu'), ('Miyako', 'miyako')):
        if k in ch:   # 「Yuno Sengoku - Topic」 같은 자동 생성 토픽 채널은 영문 이름
            return key
    if ch:
        return 'group'   # 夢限大みゅーたいぷ(그룹 공식) 채널
    return ''            # 채널 정보 없음 — 누가 불렀는지 모름

# 구분은 original / cover 둘뿐(운영자 결정 2026-10-06). 기존 BPM 데이터의 「(Solo)」 표기는 일회성으로 cover 로 옮긴다 — 신곡 감지(songs.py)에는
# solo 규칙이 없다(정규 규칙은 「(Cover)」 뿐). feat. 곡은 목록에서 뺀다.
FEAT = re.compile(r'(?<![a-z])(?:feat|ft)\.', re.I)

out = []
for x in sorted(d, key=lambda s: s['published_at']):
    if FEAT.search(x['song']):
        continue
    title = re.sub(r' \((Solo|Cover)\)$', '', x['song'])
    title = re.sub(r'【Covered by.*】', '', title).strip()
    out.append({
        'id': x['video_id'], 'title': title, 'kind': 'cover' if x['kind'] in ('solo', 'cover') else x['kind'], 'who': who(x['channel']),
        'date': x['published_date'],
        'reading': READ.get(x['song'], ''),
    })
assert len({o['id'] for o in out}) == len(out)
text = json.dumps({'songs': out}, ensure_ascii=False, indent=2, sort_keys=True) + chr(10)
open(dst, 'w', encoding='utf-8', newline=chr(10)).write(text)
# 백엔드(Cloud Run 이미지는 src/frontend 를 제외)가 시드 전 미리보기 기준으로 쓰는 사본
open(ROOT / 'config' / 'songs_seed.json', 'w', encoding='utf-8', newline=chr(10)).write(text)
print(len(out), sum(1 for o in out if o['reading']), sum(1 for o in out if o['who'] == ''))
