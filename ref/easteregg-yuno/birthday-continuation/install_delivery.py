from pathlib import Path
import hashlib,json,subprocess,shutil
BASE=Path(__file__).parent
ROOT=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='feat/birthday-music-scene'
manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf8'))
for name,expected in manifest.items():
 target=ROOT/name;source=BASE/'delivery'/name
 actual=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
 desired=hashlib.sha256(source.read_bytes()).hexdigest()
 assert actual in (expected,desired),f'준비 이후 변경됨: {name}'
for name in sorted(manifest,key=lambda n:not n.startswith('docs/')):
 target=ROOT/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/'delivery'/name,target)
print(f'인계 워크트리에 {len(manifest)}개 파일 적용')
