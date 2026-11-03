from pathlib import Path
import json,hashlib,tempfile
B=Path(__file__).parent;D=B/'delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene');V=Path(tempfile.gettempdir())/'birthday-verify-third'
g=json.loads((V/'performance-headed.json').read_text(encoding='utf8'));c=json.loads((V/'performance-software.json').read_text(encoding='utf8'))
rows='\n'.join(f"| {t} | {g[t]['mean']:.2f} | {g[t]['p95']:.2f} | {g[t]['max']:.2f} | {c[t]['mean']:.2f} | {c[t]['p95']:.2f} |" for t in ['7.5','14','17.3','25','110'])
p=D/'docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md';s=p.read_text(encoding='utf8')
s=s.replace('기존 장면 RAF는 화면 밖으로 옮겨 정지시켰다.', '기존 장면 RAF는 테스트 응답에만 주입한 취소 함수로 정지시키고 장면을 실제 화면에 표시했다.')
s=s.replace('오디오·별도 브라우저 검사는 성능 계측과 동시에 실행하지 않았다.', '별도 브라우저 검사는 성능 계측과 동시에 실행하지 않았다. Chromium '+g['browser_version']+'의 SystemInfo에서도 2D Canvas와 GPU 합성 enabled를 확인했다.')
a=s.index('| 곡 시각(s)');z=s.index('\n## 동작 검증',a)
s=s[:a]+f'''| 곡 시각(s) | GPU 평균(ms) | GPU p95(ms) | GPU 최대(ms) | 소프트웨어 평균(ms) | 소프트웨어 p95(ms) |
|---|---:|---:|---:|---:|---:|
{rows}

**GPU 환경 통과**: 측정한 600프레임의 평균·p95·최대가 모두 8ms 이하다(전체 최대 4.8ms). 소프트웨어는 8ms를 넘으며 바닥 합성이 병목이다. 이 데스크톱 GPU 수치로 모바일이나 모든 기기의 상한을 보증하지 않는다. 초기 캐시 생성은 별도 첫 실행이며 표는 워밍업 후 값이다. 화면 밖 Canvas 측정에서는 소비되지 않은 GPU 명령의 일괄 처리 지연이 섞였으므로 해당 후보 수치를 최종 판정으로 쓰지 않았다.
'''+s[z:]
s=s.replace('점등 전파 중 외부 CSS brightness는 .30이며 내부 태양 중심 마스크가 밝기를 합성한다.', '점등 전파 중 기본 장면 Canvas의 CSS brightness는 .30이고, 별도 전파 Canvas가 태양 중심 마스크와 최종 밝기를 합성한다. 유노도 별도 Canvas에서 최종 밝기를 적용해 중간 클리핑으로 회색이 되는 문제를 수정했다.')
p.write_text(s,encoding='utf8',newline='\n')
p=D/'docs/BIRTHDAY_SKIN.md';s=p.read_text(encoding='utf8')
s=s.replace('캐릭터 밝기·점등 파면은 필요한 영역만 필터링한다.', '캐릭터 조명과 점등 파면은 별도 Canvas의 최종 CSS 밝기로 합성해 색의 중간 클리핑을 피한다.')
s=s.replace('GPU 평균 8ms 기준은 충족했으나 일부 p95와 소프트웨어 렌더링은 기준을 넘었다. 전체 출시 기준 통과로 처리하지 않는다.', 'GPU 환경의 600프레임 평균·p95·최대는 모두 8ms 이내(최대 4.8ms)였다. 소프트웨어는 평균 17.38~32.81ms이고 실제 iPhone은 미확인이므로 전체 출시 기준 통과로 처리하지 않는다.')
p.write_text(s,encoding='utf8',newline='\n')
p=D/'docs/VERSION.md';s=p.read_text(encoding='utf8')
s=s.replace('GPU 평균 CPU 제출 비용은 0.72~3.76ms지만 일부 p95는 8ms를 넘었다.', '실제 화면 표시·GPU 가속 환경의 CPU 제출 비용은 평균 0.83~3.24ms, 최대 4.8ms였다. 소프트웨어는 평균 17.38~32.81ms이며 실제 iPhone은 미확인이다.')
p.write_text(s,encoding='utf8',newline='\n')
m=json.loads((B/'manifest.json').read_text(encoding='utf8'))
for n in m:m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
print(rows)
