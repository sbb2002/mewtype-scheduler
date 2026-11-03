from pathlib import Path
import json,hashlib,subprocess,shutil
B=Path(__file__).parent;R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
assert subprocess.check_output(['git','branch','--show-current'],cwd=R,text=True).strip()=='feat/birthday-music-scene'
m=json.loads((B/'monitor-manifest.json').read_text(encoding='utf8'))
for n,expected in m.items():
 target=R/n;source=B/'monitor-delivery'/n
 actual=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
 assert actual in (expected,hashlib.sha256(source.read_bytes()).hexdigest()),f'준비 이후 변경됨: {n}'
for n in sorted(m,key=lambda n:not n.startswith('docs/')):
 target=R/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(B/'monitor-delivery'/n,target)
print(f'모니터 진입 구현·문서 {len(m)}개 적용')
